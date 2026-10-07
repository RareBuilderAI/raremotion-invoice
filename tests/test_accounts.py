import unittest
from unittest.mock import Mock, patch
from accounts import Accounts, PdfDelivery, TrialExhausted, AccountUnavailable, SignInExpired

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.api = Mock()
        self.api.user.return_value = {'id': 'verified-user', 'email_confirmed_at': '2026-10-06'}
        self.delivery = PdfDelivery()

    def test_each_click_claims_even_for_identical_pdf(self):
        self.api.claim.side_effect = [1, 2, TrialExhausted()]
        for _ in range(2):
            self.assertEqual(self.delivery.download(self.api, 'jwt', b'%PDF-identical'), b'%PDF-identical')
        with self.assertRaises(TrialExhausted):
            self.delivery.download(self.api, 'jwt', b'%PDF-identical')
        self.assertEqual(self.api.claim.call_count, 3)
        self.assertEqual(self.delivery.status()[0], 2)

    def test_new_browser_still_asks_database(self):
        self.api.claim.side_effect = TrialExhausted()
        with self.assertRaises(TrialExhausted):
            PdfDelivery().download(self.api, 'new-session', b'%PDF')

    def test_unverified_account_cannot_claim(self):
        self.api.user.return_value = {'id': 'unverified'}
        with self.assertRaises(SignInExpired):
            self.delivery.download(self.api, 'jwt', b'%PDF')
        self.api.claim.assert_not_called()

    def test_failed_backend_never_releases_pdf(self):
        self.api.claim.side_effect = AccountUnavailable('Unavailable')
        with self.assertRaises(AccountUnavailable):
            self.delivery.download(self.api, 'jwt', b'%PDF')

    def test_invalid_response_never_releases_pdf(self):
        self.api.claim.return_value = True
        with self.assertRaises(AccountUnavailable):
            self.delivery.download(self.api, 'jwt', b'%PDF')

    def test_sign_out_revokes_old_download_callback(self):
        self.delivery.revoke()
        with self.assertRaises(SignInExpired):
            self.delivery.download(self.api, 'jwt', b'%PDF')
        self.api.claim.assert_not_called()

    @patch('accounts.requests.request')
    def test_download_requests_have_distinct_ids_and_verified_token(self, request):
        response = Mock(ok=True, status_code=200, content=b'1')
        response.json.return_value = 1
        request.return_value = response
        api = Accounts('https://example.supabase.co', 'public-test-key')
        api.claim('jwt'); api.claim('jwt')
        first, second = [call.kwargs for call in request.call_args_list]
        self.assertNotEqual(first['json'], second['json'])
        self.assertEqual(first['headers']['Authorization'], 'Bearer jwt')
        self.assertEqual(set(first['json']), {'p_fingerprint'})

    @patch('accounts.requests.request')
    def test_exhaustion_response(self, request):
        request.return_value = Mock(ok=False, status_code=400, text='INVOICE_TRIAL_EXHAUSTED')
        with self.assertRaises(TrialExhausted):
            Accounts('https://example.supabase.co', 'key').claim('jwt')

if __name__ == '__main__':
    unittest.main()
