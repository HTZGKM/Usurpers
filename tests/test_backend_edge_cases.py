"""Edge-case tests for backend behavior; each test gets a fresh isolated SQLite DB."""
import sqlite3
import unittest

from backend_test_helpers import RestaurantTestCase, login, restaurant_date_in, write
from restaurant.db.database import ensure_database, get_connection
from restaurant.services.booking_service import create_booking, update_booking
from restaurant.services.common import ServiceError
from restaurant.services.order_service import create_dine_in_order, get_visit_bill, pay_visit
from restaurant.services.queue_manager import QueueManager


class BackendEdgeCaseTests(RestaurantTestCase):
    def test_pay_alias_rejects_kitchen_role_without_writing(self):
        """PAY-002: only customer/frontdesk payment routes can collect payment."""
        self.assertEqual(login(self.client, "kitchen@shuangfen.local").status_code, 303)
        response = write(self.client, "/pay/9001")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.is_json)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT payment_status FROM orders WHERE order_id=9001").fetchone()[0], "unpaid")
            self.assertEqual(db.execute("SELECT count(*) FROM orders WHERE order_id=9001 AND paid_at IS NOT NULL").fetchone()[0], 0)

    def test_duplicate_dish_name_edit_is_conflict_without_partial_write(self):
        """MENU-002: duplicate names should be a clean 409 and leave the dish unchanged."""
        self.assertEqual(login(self.client, "admin@shuangfen.local").status_code, 303)
        response = write(self.client, "/admin/dishes/2/edit", {"name":"House Cheeseburger", "price":47, "expected_version":1})
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.is_json)
        with get_connection() as db:
            row=db.execute("SELECT dish_name,price FROM dishes WHERE dish_id=2").fetchone()
            self.assertEqual(row["dish_name"], "Double Cheddar")
            self.assertEqual(float(row["price"]), 48.0)

    def test_failed_booking_edit_preserves_original(self):
        """RES-003: impossible edit fails atomically, original booking remains."""
        original_day, other_day = restaurant_date_in(10), restaurant_date_in(11)
        first=create_booking("甲","13910000001",original_day,1,2)
        create_booking("乙","13910000002",other_day,3,6)
        create_booking("丙","13910000003",other_day,3,6)
        with self.assertRaises(ServiceError):
            update_booking(first["booking_id"],other_day,3,6, expected_version=1)
        with get_connection() as db:
            row=db.execute("SELECT booking_date,time_slot,party_size,table_id,status FROM bookings WHERE booking_id=?",(first["booking_id"],)).fetchone()
            self.assertEqual(tuple(row),(original_day,"11:00-14:00",2,1,"booked"))

    def test_customer_cannot_access_another_customers_booking(self):
        """AUTH-002: foreign booking id should not disclose or mutate another account."""
        self.assertEqual(login(self.client, "13900000002").status_code,303)
        response=write(self.client, "/bookings/1/cancel")
        self.assertEqual(response.status_code,409)  # Ownership is hidden as unavailable.
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM bookings WHERE booking_id=1").fetchone()[0],"booked")

    def test_kitchen_queue_insert_failure_rolls_back_entire_order(self):
        """ORD-003/DB-001: line insertion cannot commit without its queue row."""
        with get_connection() as db:
            db.execute("CREATE TRIGGER fail_queue_insert BEFORE INSERT ON kitchen_queue BEGIN SELECT RAISE(ABORT,'injected queue outage'); END")
            before=db.execute("SELECT count(*) FROM orders").fetchone()[0]
            before_lines=db.execute("SELECT count(*) FROM order_items").fetchone()[0]
            before_queue=db.execute("SELECT count(*) FROM kitchen_queue").fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            create_dine_in_order(1,[{"dish_id":6,"quantity":1}],"13900000002")
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM orders").fetchone()[0],before)
            self.assertEqual(db.execute("SELECT count(*) FROM order_items").fetchone()[0],before_lines)
            self.assertEqual(db.execute("SELECT count(*) FROM kitchen_queue").fetchone()[0],before_queue)

    def test_payment_update_failure_does_not_record_payment(self):
        """PAY-004: payment status and timestamp stay unchanged on an aborted update."""
        with get_connection() as db:
            db.execute("UPDATE order_items SET status='served' WHERE order_id IN (SELECT order_id FROM orders WHERE visit_id=1)")
            db.execute("CREATE TRIGGER fail_mark_paid BEFORE UPDATE OF payment_status ON orders WHEN NEW.payment_status='paid' BEGIN SELECT RAISE(ABORT,'injected payment outage'); END")
        bill=get_visit_bill(1)
        with self.assertRaises(sqlite3.IntegrityError):
            pay_visit(1,None,bill['order_ids'],bill['total_cents'],request_key='abort-payment',actor='desk')
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM orders WHERE order_id=9001 AND paid_at IS NOT NULL").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT payment_status FROM orders WHERE order_id=9001").fetchone()[0],"unpaid")

    def test_called_waitlist_party_can_only_be_seated_once(self):
        """WQ-002: repeated seat request cannot create two visits for one queue entry."""
        entry=QueueManager.join_waitlist(2,"等位客","13910000003")
        called=QueueManager.call_next(6)
        self.assertEqual(called["queue_id"],entry["queue_id"])
        QueueManager.seat(entry["queue_id"],6)
        with self.assertRaises(ServiceError):
            QueueManager.seat(entry["queue_id"],6)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM dining_sessions WHERE table_id=6 AND status='seated'").fetchone()[0],1)

    def test_app_recreation_preserves_committed_kitchen_work(self):
        """REC-001: Flask recreation reuses durable DB state without duplicate queue rows."""
        with get_connection() as db:
            before=db.execute("SELECT count(*) FROM kitchen_queue").fetchone()[0]
            db.execute("UPDATE kitchen_queue SET status='cooking',started_at=CURRENT_TIMESTAMP WHERE order_item_id=9001")
        from app import create_app
        create_app()
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM kitchen_queue WHERE order_item_id=9001").fetchone()[0],"cooking")
            self.assertEqual(db.execute("SELECT count(*) FROM kitchen_queue").fetchone()[0],before)

    def test_simplified_schema_is_created_idempotently(self):
        ensure_database()
        with get_connection() as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(tables - {"sqlite_sequence"}, {
            "staff", "customers", "dining_tables", "dishes", "bookings", "booking_create_requests", "dining_sessions",
            "orders", "order_items", "mutation_requests", "waiting_queue", "kitchen_queue", "ingredients", "dish_ingredients",
            "web_sessions", "kitchen_settings", "kitchen_settings_audit", "order_resolution_audit",
            "account_tokens", "account_link_requests", "account_mail_limits", "customer_recovery",
        })


if __name__ == "__main__":
    unittest.main()
