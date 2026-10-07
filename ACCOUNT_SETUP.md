# Raremotion Invoice accounts and two-download trial

Uses the existing Invoice Supabase project `lgvgrauoatjhlmyiqzvv`. No payment integration is required for this release. Do not use the CRM or Analytics database.

## Activation

1. Apply `database/trial.sql` to the existing Invoice Supabase database. It preserves the existing usage rows, enables row-level security, removes direct anonymous/authenticated table access, and restricts quota functions to authenticated users with verified email addresses.
2. Complete custom SMTP for this project's Supabase Auth. Use the existing Resend setup once the domain is verified. The Magic Link template must include `{{ .Token }}` for the email-code form. Do not disable email verification to work around delivery problems.
3. Set the following in the local `.streamlit/secrets.toml` and Streamlit Cloud's private Secrets settings (replace placeholders privately):

```toml
[accounts]
supabase_url = "https://lgvgrauoatjhlmyiqzvv.supabase.co"
publishable_key = "YOUR_PUBLISHABLE_KEY"
```

Never put service-role keys, SMTP credentials, `.env`, or private secrets in Git.

4. Run the transactional SQL checks in `tests/trial_database.sql` and the Python checks with `python -m unittest discover -s tests -v`.
5. Run one real end-to-end check: create a verified account through the email-code form; fill in a valid invoice; prepare it; download twice; confirm the third attempt is disabled and the upgrade-required message is visible. Sign in from another browser/session and confirm the exhausted allowance persists. Do not claim this check passed until real Supabase authentication and PDF downloads have been observed.
6. Publish the tested commit to the existing Streamlit deployment. Keep the same app URL and Raremotion Labs links.

## Behavior

Email-code verification creates an account on first use and signs in returning users. Every download click invokes a deferred server callback. The callback verifies the account, then claims one of exactly two database slots before releasing PDF bytes. Preparation/editing does not consume a slot. Downloading the same invoice twice consumes both slots. Each callback uses a new opaque request identifier; invoice content is not stored in the database.

The database serializes concurrent claims per user. It checks the two-slot cap before inserting a usage row, so two tabs/devices cannot exceed the allowance. The user cannot reset the table or query other accounts. Existing usage rows count toward the limit.

Usage persists across sign-out, cookies, devices, and app restarts. Session tokens stay in server-side Streamlit session state; refreshing the browser may require signing in again. Signing out revokes that session's outstanding download callbacks.

A slot is consumed when the server authorizes release of the PDF, before the browser saves it. A network failure after authorization can consume a slot; there is no automatic refund or automatic retry that could reopen an exhausted allowance. Files already saved by users cannot be revoked.

After both slots are consumed, further PDF requests are denied and the UI explains that payment or an upgrade will be required. Payment collection is intentionally absent; invoice Paid/Unpaid remains the existing manual invoice status.

## Validation status

Python unit checks cover repeated identical PDFs, database denial after a new session, unverified users, service failures, malformed responses, sign-out, unique download IDs and authenticated quota calls. These are not substitutes for the SQL checks or real sign-up/download test.

Live database migration applied on 6 October 2026. Transactional checks passed in the existing Invoice Supabase project: first and second claims accepted; third claim and exhausted replay denied; account isolation; anonymous denial; direct table read/reset denied. Test accounts and usage were rolled back.

Email activation remains blocked: Supabase custom SMTP is disabled; Resend shows raremotionlabs.com verification as Not Started; public DNS lookup returned no records for resend._domainkey (TXT), rsend (CNAME), or send (CNAME); the signed-in Olitt DNS domain list is empty. The existing domain zone must be restored/linked by its provider before adding the Resend records. Do not create a replacement zone or change nameservers.

Private Streamlit settings, real email sign-up and two-download browser test, and deployment remain pending. No payment is needed for activation.
