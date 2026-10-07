import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from accounts import Accounts, TrialExhausted

class InterfaceTests(unittest.TestCase):
    def test_account_gate_invoice_and_exhausted_message(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20)
        app.secrets['accounts'] = {'supabase_url': 'https://example.supabase.co', 'publishable_key': 'public-test'}
        with patch.object(Accounts, 'send_code') as send, patch.object(Accounts, 'verify_code', return_value={
            'access_token': 'test-jwt', 'refresh_token': 'test-refresh', 'expires_in': 3600,
        }), patch.object(Accounts, 'user', return_value={'id': 'test', 'email': 'test@example.invalid', 'email_confirmed_at': '2026-10-06'}), patch.object(Accounts, 'usage', return_value=0) as usage, patch.object(Accounts, 'claim', side_effect=[1, 2, TrialExhausted()]):
            app.run()
            self.assertEqual(len(app.get('download_button')), 0)
            app.text_input[0].set_value('test@example.invalid')
            app.button[0].click().run()
            send.assert_called_once_with('test@example.invalid')
            next(w for w in app.text_input if w.label == 'Sign-in code').set_value('123456')
            next(w for w in app.button if w.label == 'Verify and continue').click().run()
            self.assertFalse(app.exception)
            for label, value in [('Business name', 'Raremotion Labs'), ('Customer name', 'Test Client'), ('Description', 'Website Development')]:
                next(w for w in app.text_input if w.label == label).set_value(value)
            for label, value in [('Quantity', 2), ('Unit price', 50000.0), ('Tax (%)', 7.5)]:
                next(w for w in app.number_input if w.label == label).set_value(value)
            app.run()
            next(w for w in app.button if w.label == 'Prepare Invoice PDF').click().run()
            self.assertFalse(app.exception)
            invoice = app.session_state.prepared_invoice
            self.assertEqual(invoice['subtotal'], 100000)
            self.assertEqual(invoice['tax_amount'], 7500)
            self.assertEqual(invoice['total'], 107500)
            pdf = app.session_state.prepared_pdf
            self.assertTrue(pdf.startswith(b'%PDF'))
            delivery = app.session_state.pdf_delivery
            api = Accounts('https://example.supabase.co', 'public-test')
            self.assertEqual(delivery.download(api, 'test-jwt', pdf), pdf)
            self.assertEqual(delivery.download(api, 'test-jwt', pdf), pdf)
            with self.assertRaises(TrialExhausted):
                delivery.download(api, 'test-jwt', pdf)
            usage.return_value = 2
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(app.get('download_button')[0].proto.disabled)
            self.assertTrue(any('2 free PDF downloads' in w.value and 'Payment' in w.value for w in app.warning))

if __name__ == '__main__':
    unittest.main()
