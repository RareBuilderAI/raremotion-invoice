"""Email accounts and persistent, server-enforced invoice trial allowance."""
from uuid import uuid4
from threading import Lock
import time
from urllib.parse import urlparse

import requests
import streamlit as st


class AccountUnavailable(Exception):
    pass


class SignInExpired(AccountUnavailable):
    pass


class TrialExhausted(Exception):
    pass


TRIAL_LIMIT = 2
EXHAUSTED_MESSAGE = "You’ve used your 2 free PDF downloads. Payment or an upgrade will be required for further downloads. Payments are not available yet."


class Accounts:
    def __init__(self, url, publishable_key):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
            raise AccountUnavailable("Account service configuration is invalid.")
        self.url = url.rstrip("/")
        self.key = publishable_key

    def request(self, path, payload=None, token=None, method="POST"):
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            response = requests.request(method, self.url + path, headers=headers, json=payload, timeout=15)
        except requests.RequestException:
            raise AccountUnavailable("The account service could not be reached. Please try again.") from None
        if response.status_code == 401:
            raise SignInExpired("Please sign in again.")
        if not response.ok:
            if path.endswith("/claim_invoice_trial") and "INVOICE_TRIAL_EXHAUSTED" in response.text:
                raise TrialExhausted(EXHAUSTED_MESSAGE)
            if response.status_code == 429:
                raise AccountUnavailable("Too many attempts. Please wait a minute before trying again.")
            if path.endswith("/verify"):
                raise AccountUnavailable("That code is invalid or expired. Check it or request a new code.")
            raise AccountUnavailable("This request could not be completed. Please try again later.")
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            raise AccountUnavailable("The account service returned an unexpected response.") from None

    def send_code(self, email):
        self.request("/auth/v1/otp", {"email": email, "create_user": True})

    def verify_code(self, email, code):
        return self.request("/auth/v1/verify", {"email": email, "token": code, "type": "email"})

    def refresh(self, refresh_token):
        return self.request("/auth/v1/token?grant_type=refresh_token", {"refresh_token": refresh_token})

    def user(self, token):
        return self.request("/auth/v1/user", token=token, method="GET")

    def usage(self, token):
        return self.request("/rest/v1/rpc/invoice_trial_usage", {}, token)

    def claim(self, token):
        # A fresh ID for EVERY download, including the same invoice. Do not retry
        # automatically: a timeout may mean the transaction already committed.
        return self.request("/rest/v1/rpc/claim_invoice_trial", {"p_fingerprint": uuid4().hex + uuid4().hex}, token)


def remember_session(session):
    if not session.get("access_token") or not session.get("refresh_token"):
        raise AccountUnavailable("Sign-in could not be completed. Please request a new code.")
    st.session_state.account_session = {
        "access_token": session["access_token"],
        "refresh_token": session["refresh_token"],
        "expires_at": time.time() + int(session.get("expires_in", 3600)),
    }


def clear_account():
    # Clear invoice fields too, preventing a later user from seeing the prior account's data.
    delivery = st.session_state.get("pdf_delivery")
    if delivery:
        delivery.revoke()
    st.session_state.clear()


def require_account():
    try:
        config = st.secrets["accounts"]
        api = Accounts(config["supabase_url"], config["publishable_key"])
    except (KeyError, FileNotFoundError, AccountUnavailable):
        st.title("Raremotion Invoice")
        st.info("Account sign-in is being set up. Please check back shortly.")
        st.stop()
    if "account_session" not in st.session_state:
        st.title("Welcome to Raremotion Invoice")
        st.write("Create an account or sign in with your email to get exactly 2 free PDF downloads.")
        st.caption("We’ll send you a one-time code. No password needed. Your email and trial usage are stored securely with our account provider.")
        with st.form("email_sign_in"):
            email = st.text_input("Email address", value=st.session_state.get("sign_in_email", ""))
            send = st.form_submit_button("Send sign-in code")
        if send:
            email = email.strip().lower()
            if "@" not in email or len(email) > 254:
                st.error("Enter a valid email address.")
            else:
                try:
                    api.send_code(email)
                    st.session_state.sign_in_email = email
                    st.success("Check your email for your sign-in code.")
                except AccountUnavailable as exc:
                    st.error(str(exc))
        if st.session_state.get("sign_in_email"):
            with st.form("verify_email_code"):
                code = st.text_input("Sign-in code", type="password")
                verify = st.form_submit_button("Verify and continue")
            if verify:
                try:
                    remember_session(api.verify_code(st.session_state.sign_in_email, code.strip()))
                    st.rerun()
                except AccountUnavailable as exc:
                    st.error(str(exc))
        st.stop()
    try:
        session = st.session_state.account_session
        if time.time() >= session["expires_at"] - 60:
            remember_session(api.refresh(session["refresh_token"]))
            session = st.session_state.account_session
        user = api.user(session["access_token"])
        if not user.get("id") or not user.get("email_confirmed_at"):
            raise SignInExpired("Please verify your email to continue.")
        used = api.usage(session["access_token"])
        if type(used) is not int or used < 0:
            raise AccountUnavailable("Your trial allowance could not be checked. Please try again.")
    except SignInExpired:
        clear_account()
        st.rerun()
    except AccountUnavailable as exc:
        st.error(str(exc))
        if st.button("Try again"):
            st.rerun()
        st.stop()
    with st.sidebar:
        st.write("Signed in as " + user.get("email", ""))
        st.caption("Your download allowance is shown below your invoice.")
        if st.button("Sign out"):
            try:
                api.request("/auth/v1/logout?scope=local", token=session["access_token"])
            except AccountUnavailable:
                pass
            clear_account()
            st.rerun()
    return api, session["access_token"], used


class PdfDelivery:
    """Per-session callback status, never the source of quota truth.

    Streamlit executes deferred downloads on a worker thread. This object avoids
    reading/writing Streamlit session state from that thread.
    """
    def __init__(self):
        self.lock = Lock()
        self.active = True
        self.used = None
        self.message = None

    def revoke(self):
        with self.lock:
            self.active = False

    def status(self):
        with self.lock:
            return self.used, self.message

    def download(self, api, token, pdf):
        with self.lock:
            try:
                if not self.active:
                    raise SignInExpired("Please sign in again.")
                if not isinstance(pdf, bytes) or not pdf:
                    raise AccountUnavailable("Prepare your invoice PDF before downloading.")
                user = api.user(token)
                if not user.get("id") or not user.get("email_confirmed_at"):
                    raise SignInExpired("Please verify your email to continue.")
                used = api.claim(token)
                if type(used) is not int or not 1 <= used <= TRIAL_LIMIT:
                    raise AccountUnavailable("Your download could not be authorized. Please refresh your allowance.")
                self.used, self.message = used, None
                return pdf
            except TrialExhausted:
                self.used, self.message = TRIAL_LIMIT, EXHAUSTED_MESSAGE
                raise
            except AccountUnavailable as exc:
                self.message = str(exc)
                raise
