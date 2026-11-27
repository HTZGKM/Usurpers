"""Account lifecycle checks use isolated databases and explicit SMTP test doubles."""
import os
from unittest.mock import patch

from backend_test_helpers import RestaurantTestCase, bind_test_session, csrf, login, write
from restaurant.db.database import get_connection
from restaurant.services import account_recovery as recovery
from restaurant.services.common import ServiceError
from restaurant.services.phone_identity import normalize_phone
from restaurant.services.session_service import sign_in


class AccountRecoveryTests(RestaurantTestCase):
    phone = "13900000001"

    def setUp(self):
        super().setUp()
        self.mail = []
        self.enterContext(patch.dict(os.environ, {
            "USURPERS_SMTP_HOST": "smtp.example.test", "USURPERS_SMTP_FROM": "restaurant@example.test",
            "USURPERS_PUBLIC_URL": "https://restaurant.example.test", "USURPERS_SMTP_TLS": "starttls",
            "USURPERS_SMTP_USER": "", "USURPERS_SMTP_PASSWORD": "",
        }))
        self.enterContext(patch.object(recovery, "_send", side_effect=lambda settings,email,purpose,token: self.mail.append((email,purpose,token))))
        self.clock = self.enterContext(patch.object(recovery, "time", return_value=2_000_000_000))

    def bind_email(self, email="first@example.test"):
        recovery.request_email_change(self.phone, email, "123456")
        token = self.mail[-1][2]
        recovery.verify_email(token)
        return token

    def test_phone_formats_and_registration_share_one_identity(self):
        for phone in ("139 0000 0001", "+86 (139) 0000-0001", "0086 13900000001"):
            self.assertEqual(normalize_phone(phone), self.phone)
            self.assertIsNotNone(sign_in(phone, "123456"))
        self.assertEqual(normalize_phone("+44 20 7946 0958"), "+442079460958")
        with self.assertRaises(ServiceError):
            normalize_phone("-------")
        client = self.app.test_client()
        response = client.post("/auth/register", data={"name":"Alias","phone_number":"+86 13900000001","password":"123456","role":"admin","csrf_token":csrf(client)})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"already registered", response.data)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM customers WHERE customer_phone=?",(self.phone,)).fetchone()[0],1)

    def test_email_replacement_preserves_verified_address_until_confirmation(self):
        self.bind_email()
        self.clock.return_value += 61
        recovery.request_email_change(self.phone,"second@example.test","123456")
        token = self.mail[-1][2]
        self.assertEqual(recovery.profile(self.phone)["email"],"first@example.test")
        recovery.verify_email(token)
        self.assertEqual(recovery.profile(self.phone)["email"],"second@example.test")
        with self.assertRaises(ServiceError):
            recovery.verify_email(token)

    def test_reset_requires_verified_address_and_revokes_all_sessions(self):
        recovery.request_password_reset(self.phone,"test-source")
        self.assertEqual(self.mail,[])
        self.bind_email()
        one, two = self.app.test_client(), self.app.test_client()
        bind_test_session(one,customer_phone=self.phone)
        bind_test_session(two,customer_phone=self.phone)
        with get_connection() as db:
            before = db.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
        self.clock.return_value += 61
        recovery.request_password_reset(self.phone,"test-source")
        self.assertEqual(self.mail[-1][1],"reset_password")
        token = self.mail[-1][2]
        with get_connection() as db:
            stored=db.execute("SELECT token_hash FROM account_tokens WHERE purpose='reset_password'").fetchone()[0]
        self.assertNotEqual(stored,token)
        recovery.reset_password(token,"new-fixture-password")
        for client in (one,two):
            self.assertEqual(client.get("/auth/me").status_code,401)
        self.assertIsNone(sign_in(self.phone,"123456"))
        self.assertIsNotNone(sign_in(self.phone,"new-fixture-password"))
        with self.assertRaises(ServiceError):
            recovery.reset_password(token,"another-password")
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM bookings").fetchone()[0],before)

    def test_token_expiry_and_superseded_email_reset(self):
        self.bind_email()
        recovery.request_password_reset(self.phone,"source")
        reset = self.mail[-1][2]
        self.clock.return_value += 61
        recovery.request_email_change(self.phone,"new@example.test","123456")
        recovery.verify_email(self.mail[-1][2])
        with self.assertRaises(ServiceError):
            recovery.reset_password(reset,"new-password")
        recovery.request_password_reset(self.phone,"source")
        expired=self.mail[-1][2]
        self.clock.return_value += recovery.RESET_SECONDS
        with self.assertRaises(ServiceError):
            recovery.reset_password(expired,"new-password")

    def test_reset_responses_do_not_enumerate_accounts_and_throttle_delivery(self):
        self.bind_email()
        known=recovery.request_password_reset(self.phone,"source1")
        unknown=recovery.request_password_reset("13977778888","source2")
        self.assertEqual(known,unknown)
        sent=len(self.mail)
        self.assertEqual(recovery.request_password_reset(self.phone,"source3"),known)
        self.assertEqual(len(self.mail),sent)

    def test_smtp_configuration_failure_is_explicit_and_keeps_old_email(self):
        self.bind_email()
        self.clock.return_value += 61
        with patch.dict(os.environ,{"USURPERS_SMTP_HOST":""}):
            with self.assertRaises(ServiceError) as caught:
                recovery.request_email_change(self.phone,"new@example.test","123456")
            self.assertEqual(caught.exception.code,"EMAIL_UNAVAILABLE")
            response=self.client.post('/auth/forgot-password',data={'phone_number':self.phone,'csrf_token':csrf(self.client)})
            self.assertEqual(response.status_code,503)
        self.assertEqual(recovery.profile(self.phone)["email"],"first@example.test")

    def test_email_send_failure_invalidates_verification_and_reset_stays_generic(self):
        self.bind_email()
        self.clock.return_value += 61
        with patch.object(recovery,"_send",side_effect=ServiceError("SMTP unavailable",503,code="EMAIL_UNAVAILABLE")):
            with self.assertRaises(ServiceError):
                recovery.request_email_change(self.phone,"new@example.test","123456")
            self.assertEqual(recovery.request_password_reset(self.phone,"source1"),recovery.request_password_reset("13977778888","source2"))
        self.assertEqual(recovery.profile(self.phone)["email"],"first@example.test")
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM account_tokens WHERE purpose='reset_password' AND consumed_at IS NULL").fetchone()[0],0)

    def test_late_delivery_failure_does_not_invalidate_a_newer_email_request(self):
        self.bind_email()
        self.clock.return_value += 61
        newer = []
        def delayed_failure(settings, email, purpose, token):
            self.clock.return_value += 61
            with patch.object(recovery, '_send', side_effect=lambda settings,email,purpose,token: newer.append(token)):
                recovery.request_email_change(self.phone, 'newer@example.test', '123456')
            raise ServiceError('SMTP unavailable', 503, code='EMAIL_UNAVAILABLE')
        with patch.object(recovery, '_send', side_effect=delayed_failure):
            with self.assertRaises(ServiceError):
                recovery.request_email_change(self.phone, 'failed@example.test', '123456')
        self.assertEqual(recovery.profile(self.phone)['email'], 'first@example.test')
        recovery.verify_email(newer[0])
        self.assertEqual(recovery.profile(self.phone)['email'], 'newer@example.test')

    def test_profile_requires_csrf_and_updates_only_name(self):
        customer=self.signed_in(self.phone)
        self.assertEqual(customer.post('/auth/profile',data={'name':'New'}).status_code,400)
        response=write(customer,'/auth/profile',{'name':'Updated name','phone_number':'13977778888','role':'admin'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(customer.get('/auth/me').json['user']['name'],'Updated name')
        self.assertEqual(customer.get('/auth/me').json['user']['username'],self.phone)
        self.assertEqual(customer.get('/auth/me').json['user']['role'],'customer')

    def test_link_get_does_not_consume_email_token(self):
        recovery.request_email_change(self.phone,'first@example.test','123456')
        token=self.mail[-1][2]
        response=self.client.get('/auth/verify-email',query_string={'token':token})
        self.assertEqual(response.status_code,200)
        self.assertIsNone(recovery.profile(self.phone)['email'])
        recovery.verify_email(token)
        self.assertEqual(recovery.profile(self.phone)['email'],'first@example.test')
