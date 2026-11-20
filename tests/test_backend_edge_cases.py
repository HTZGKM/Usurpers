"""Edge-case tests for backend behavior; each test gets a fresh isolated SQLite DB."""
import os
import unittest
from pathlib import Path

_test_root = Path(__file__).resolve().parent / ".edge_runtime"
_test_root.mkdir(exist_ok=True)
os.environ["USURPERS_DB_PATH"] = str(_test_root / "edge.db")

from app import create_app
from restaurant.db.database import ensure_database, get_connection
from restaurant.services.booking_service import create_booking, update_booking
from restaurant.services.common import ServiceError
from restaurant.services.order_service import create_dine_in_order, pay_order
from restaurant.services.queue_manager import QueueManager


class BackendEdgeCaseTests(unittest.TestCase):
    def setUp(self):
        os.environ["USURPERS_DB_PATH"] = str(_test_root / "edge.db")
        ensure_database(reset=True)  # Path is confined to tests/.edge_runtime.
        self.app = create_app()
        self.client = self.app.test_client()

    def login(self, account, password="123456"):
        return self.client.post("/auth/login", json={"account": account, "password": password})

    def test_pay_alias_rejects_kitchen_role_without_writing(self):
        """PAY-002: only customer/frontdesk payment routes can collect payment."""
        self.assertEqual(self.login("kitchen@shuangfen.local").status_code, 200)
        response = self.client.post("/pay/9001", json={})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.is_json)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT payment_status FROM order_headers WHERE order_id=9001").fetchone()[0], "unpaid")
            self.assertEqual(db.execute("SELECT count(*) FROM payments WHERE order_id=9001").fetchone()[0], 0)

    def test_duplicate_dish_name_edit_is_conflict_without_partial_write(self):
        """MENU-002: duplicate names should be a clean 409 and leave the dish unchanged."""
        self.assertEqual(self.login("admin@shuangfen.local").status_code, 200)
        response = self.client.post("/admin/dishes/2/edit", json={"name":"芝士牛肉堡", "price":47})
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.is_json)
        with get_connection() as db:
            row=db.execute("SELECT dish_name,price FROM dishes WHERE dish_id=2").fetchone()
            self.assertEqual(row["dish_name"], "双层招牌堡")
            self.assertEqual(float(row["price"]), 46.0)

    def test_failed_booking_edit_preserves_original(self):
        """RES-003: impossible edit fails atomically, original booking remains."""
        first=create_booking("甲","13910000001","2026-12-27",1,2)
        create_booking("乙","13910000002","2026-12-28",3,6)
        create_booking("丙","13910000003","2026-12-28",3,6)
        with self.assertRaises(ServiceError):
            update_booking(first["booking_id"],"2026-12-28",3,6)
        with get_connection() as db:
            row=db.execute("SELECT booking_date,time_slot_id,party_size,table_id,status FROM bookings WHERE booking_id=?",(first["booking_id"],)).fetchone()
            self.assertEqual(tuple(row),("2026-12-27",1,2,1,"booked"))

    def test_customer_cannot_access_another_customers_booking(self):
        """AUTH-002: foreign booking id should not disclose or mutate another account."""
        self.assertEqual(self.login("13900000002").status_code,200)
        response=self.client.post("/bookings/1/cancel",json={})
        self.assertEqual(response.status_code,409)  # Ownership is hidden as unavailable.
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM bookings WHERE booking_id=1").fetchone()[0],"booked")

    def test_kitchen_queue_insert_failure_rolls_back_entire_order(self):
        """ORD-003/DB-001: line insertion cannot commit without its queue row."""
        with get_connection() as db:
            db.execute("CREATE TRIGGER fail_queue_insert BEFORE INSERT ON kitchen_queue BEGIN SELECT RAISE(ABORT,'injected queue outage'); END")
            before=db.execute("SELECT count(*) FROM order_headers").fetchone()[0]
            before_lines=db.execute("SELECT count(*) FROM order_lines").fetchone()[0]
            before_queue=db.execute("SELECT count(*) FROM kitchen_queue").fetchone()[0]
        with self.assertRaises(Exception):
            create_dine_in_order(1,[{"dish_id":6,"quantity":1}],"13900000002")
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM order_headers").fetchone()[0],before)
            self.assertEqual(db.execute("SELECT count(*) FROM order_lines").fetchone()[0],before_lines)
            self.assertEqual(db.execute("SELECT count(*) FROM kitchen_queue").fetchone()[0],before_queue)

    def test_payment_status_update_failure_rolls_back_payment_row(self):
        """PAY-004: payment row and order state must commit or roll back together."""
        with get_connection() as db:
            db.execute("CREATE TRIGGER fail_mark_paid BEFORE UPDATE OF payment_status ON order_headers WHEN NEW.payment_status='paid' BEGIN SELECT RAISE(ABORT,'injected payment outage'); END")
        with self.assertRaises(Exception):
            pay_order(9001)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM payments WHERE order_id=9001").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT payment_status FROM order_headers WHERE order_id=9001").fetchone()[0],"unpaid")

    def test_called_waitlist_party_can_only_be_seated_once(self):
        """WQ-002: repeated seat request cannot create two visits for one queue entry."""
        entry=QueueManager.join_waitlist(2,"等位客","13910000003")
        called=QueueManager.call_next(1)
        self.assertEqual(called["queue_id"],entry["queue_id"])
        QueueManager.seat(entry["queue_id"],1)
        with self.assertRaises(ServiceError):
            QueueManager.seat(entry["queue_id"],1)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM dining_sessions WHERE table_id=1 AND status='seated'").fetchone()[0],1)

    def test_app_recreation_preserves_committed_kitchen_work(self):
        """REC-001: Flask recreation reuses durable DB state without duplicate queue rows."""
        with get_connection() as db:
            before=db.execute("SELECT count(*) FROM kitchen_queue").fetchone()[0]
            db.execute("UPDATE kitchen_queue SET status='cooking',started_at=CURRENT_TIMESTAMP WHERE order_item_id=9001")
        create_app()
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM kitchen_queue WHERE order_item_id=9001").fetchone()[0],"cooking")
            self.assertEqual(db.execute("SELECT count(*) FROM kitchen_queue").fetchone()[0],before)

    def test_inventory_and_remake_schema_is_created_idempotently(self):
        """INV/KITCH: new durable business tables exist after repeatable initialization."""
        ensure_database()
        with get_connection() as db:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("ingredients",tables)
        self.assertIn("inventory_reservations",tables)
        self.assertIn("remake_tickets",tables)
        self.assertIn("refunds",tables)


if __name__ == "__main__":
    unittest.main()
