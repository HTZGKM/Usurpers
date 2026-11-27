"""Account races against the opt-in disposable PostgreSQL fixture."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch
import unittest

import psycopg

import test_postgres_booking_consistency as fixture
from restaurant.db.database import begin_write, get_connection
from restaurant.services import account_linking, account_recovery, auth_service, order_service
from restaurant.services.common import ServiceError


@unittest.skipUnless(fixture.TEST_DSN, "requires a disposable PostgreSQL database on loopback")
class AccountPostgresTests(unittest.TestCase):
    phone = staticmethod(fixture.PostgresBookingConsistencyTests.phone)
    actor = fixture.PostgresBookingConsistencyTests.actor
    send = staticmethod(fixture.PostgresBookingConsistencyTests.send)

    def setUp(self):
        fixture.PostgresBookingConsistencyTests.setUp(self)
        with psycopg.connect(self.dsn) as db:
            for migration in sorted((fixture.DB_SQL / "migrations").glob("*.sql")):
                db.execute(migration.read_text(encoding="utf-8"))

    def test_one_time_reset_only_one_competing_request_succeeds(self):
        from werkzeug.security import generate_password_hash
        phone=self.phone(0)
        with get_connection() as db:
            db.execute("UPDATE customers SET password_hash=? WHERE customer_phone=?",(generate_password_hash('old-password'),phone))
        self.actor(index=0)
        tokens=[]
        settings=dict(host='example.test',sender='noreply@example.test',base='https://example.test',security='ssl',port=465,user='',password='')
        with patch.object(account_recovery,'smtp_settings',return_value=settings), patch.object(account_recovery,'_send',side_effect=lambda settings,email,purpose,token:tokens.append(token)):
            account_recovery.request_email_change(phone,'customer@example.test','old-password')
            account_recovery.verify_email(tokens[-1])
            account_recovery.request_password_reset(phone,'test-source')
        token=tokens[-1]
        gate=Barrier(2)
        def reset(index):
            gate.wait()
            try:
                account_recovery.reset_password(token,'new-password-'+str(index))
                return 'success'
            except ServiceError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(reset,range(2)))
        self.assertCountEqual(results,['success','TOKEN_INVALID'])
        with get_connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM web_sessions WHERE customer_phone=?',(phone,)).fetchone()[0],0)

    def test_smtp_delivery_does_not_hold_restaurant_write_lock(self):
        from werkzeug.security import generate_password_hash
        phone = self.phone(0)
        with get_connection() as db:
            db.execute("UPDATE customers SET password_hash=? WHERE customer_phone=?", (generate_password_hash('old-password'), phone))
        def while_sending(settings, email, purpose, token):
            # This independent connection would time out on the global advisory
            # lock if SMTP were called from inside the token transaction.
            with get_connection() as db:
                begin_write(db)
                db.execute("UPDATE customers SET name='Business write succeeded' WHERE customer_phone=?", (phone,))
            raise ServiceError('SMTP unavailable', 503, code='EMAIL_UNAVAILABLE')
        with patch.object(account_recovery, 'smtp_settings', return_value={}), patch.object(account_recovery, '_send', side_effect=while_sending):
            with self.assertRaises(ServiceError) as failed:
                account_recovery.request_email_change(phone, 'customer@example.test', 'old-password')
            self.assertEqual(failed.exception.code, 'EMAIL_UNAVAILABLE')
        with get_connection() as db:
            self.assertEqual(db.execute('SELECT name FROM customers WHERE customer_phone=?', (phone,)).fetchone()[0], 'Business write succeeded')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM account_tokens WHERE consumed_at IS NULL').fetchone()[0], 0)

    def test_disable_commits_before_inflight_order_prevents_every_write(self):
        with get_connection() as db:
            dish=db.execute("INSERT INTO dishes(dish_name,price,is_available,category) VALUES('Account race',10,1,'burgers') RETURNING dish_id").fetchone()[0]
            visit=db.execute("INSERT INTO dining_sessions(customer_phone,party_size,table_id,status) VALUES(?,2,1,'seated') RETURNING visit_id",(self.phone(0),)).fetchone()[0]
        actor=self.actor(index=0)
        reached,release=Event(),Event()
        original=order_service.begin_write
        def delayed(db):
            reached.set()
            if not release.wait(8):
                raise RuntimeError('test writer was not released')
            original(db)
        with patch.object(order_service,'begin_write',side_effect=delayed):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending=pool.submit(self.send,actor,f'/visits/{visit}/orders',{'items-0-dish_id':dish,'items-0-quantity':1,'idempotency_key':'disable-race'})
                try:
                    self.assertTrue(reached.wait(8))
                    auth_service.set_customer_active(self.phone(0),False)
                finally:
                    release.set()
                response=pending.result()
        self.assertEqual(response.status_code,403)
        with get_connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM kitchen_queue').fetchone()[0],0)

    def test_two_link_confirmations_cannot_bypass_single_active_reservation(self):
        bookings=[]
        with get_connection() as db:
            for table in (1,2):
                bid=db.execute("""INSERT INTO bookings(contact_name,phone_number,booking_date,time_slot,party_size,table_id,status)
                                  VALUES('Telephone guest',?,'2048-02-20','19:00-20:00',2,?,'booked') RETURNING booking_id""",(self.phone(0),table)).fetchone()[0]
                bookings.append(bid)
        requests=[account_linking.request_link('booking',bid,self.phone(0),'frontdesk:fixture')['link_id'] for bid in bookings]
        pending=account_linking.pending_links(self.phone(0))
        self.assertEqual(len(pending),2)
        self.assertFalse({'contact_name','phone_number','table_id','orders'} & set(pending[0]))
        customer=self.actor(index=0)
        self.assertEqual(customer[0].get('/reservation-api/bookings/'+str(bookings[0])).status_code,404)
        gate=Barrier(2)
        def confirm(link_id):
            gate.wait()
            try:
                account_linking.resolve_link(link_id,self.phone(0),'confirm',1)
                return 'success'
            except ServiceError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(confirm,requests))
        self.assertCountEqual(result,['success','ACTIVE_RESERVATION_EXISTS'])
        with get_connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM bookings WHERE customer_phone=?',(self.phone(0),)).fetchone()[0],1)

    def test_link_confirmation_rejects_other_owner_and_changed_booking(self):
        with get_connection() as db:
            bid=db.execute("""INSERT INTO bookings(contact_name,phone_number,booking_date,time_slot,party_size,table_id,status)
                              VALUES('Guest',?,'2048-02-20','19:00-20:00',2,1,'booked') RETURNING booking_id""",(self.phone(0),)).fetchone()[0]
        link=account_linking.request_link('booking',bid,self.phone(0),'frontdesk:fixture')['link_id']
        with self.assertRaises(ServiceError) as outsider:
            account_linking.resolve_link(link,self.phone(1),'confirm',1)
        self.assertEqual(outsider.exception.status_code,404)
        with get_connection() as db:
            db.execute('UPDATE bookings SET version=version+1 WHERE booking_id=?',(bid,))
        with self.assertRaises(ServiceError) as stale:
            account_linking.resolve_link(link,self.phone(0),'confirm',1)
        self.assertEqual(stale.exception.code,'BOOKING_CHANGED')
