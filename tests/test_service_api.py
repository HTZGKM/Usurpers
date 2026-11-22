import os
import unittest
from pathlib import Path

_test_db_dir = Path(__file__).resolve().parent / ".runtime"
_test_db_dir.mkdir(exist_ok=True)
os.environ["USURPERS_DB_PATH"] = str(_test_db_dir / "service-test.db")

from app import create_app
from restaurant.db.database import ensure_database, get_connection
from restaurant.services.booking_service import create_booking
from restaurant.services.common import ServiceError
from restaurant.services.order_service import pay_order


class ServiceAndApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["USURPERS_DB_PATH"] = str(_test_db_dir / "service-test.db")
        ensure_database(reset=True)
        ensure_database()
        cls.client = create_app().test_client()
        cls.client.post("/auth/login", json={"username":"13900000001", "password":"123456"})

    def test_invalid_booking_is_json_and_does_not_write(self):
        with get_connection() as db:
            before = db.execute("SELECT count(*) FROM bookings").fetchone()[0]
        response = self.client.post("/bookings", json={"contact_name":"", "phone_number":"13900000001", "booking_date":"2026-12-20", "time_slot_id":1, "party_size":-2})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.is_json)
        self.assertFalse(response.json["success"])
        with get_connection() as db:
            after = db.execute("SELECT count(*) FROM bookings").fetchone()[0]
        self.assertEqual(before, after)

    def test_valid_booking_and_conflict(self):
        self.client.post("/auth/login", json={"username":"13900000001", "password":"123456"})
        response = self.client.post("/bookings", json={"contact_name":"测试客人", "phone_number":"13900000009", "booking_date":"2026-12-20", "time_slot_id":1, "party_size":2})
        self.assertEqual(response.status_code, 201)
        duplicate = self.client.post("/bookings", json={"contact_name":"另一位", "phone_number":"13900000010", "booking_date":"2026-12-20", "time_slot_id":1, "party_size":2})
        self.assertEqual(duplicate.status_code, 201)  # a second two-person table is available

    def test_service_rejects_bad_data_and_missing_id(self):
        with self.assertRaises(ServiceError):
            create_booking("", "13900000001", "bad-date", 1, 2)
        with self.assertRaises(ServiceError) as caught:
            pay_order(999999)
        self.assertEqual(caught.exception.status_code, 404)

    def test_health_and_menu_routes(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/menu").status_code, 200)

    def test_role_protected_kitchen_route(self):
        self.client.post("/auth/login",json={"username":"13900000001","password":"123456"})
        self.assertEqual(self.client.get("/admin/staff").status_code,403)
        self.client.post("/auth/logout")
        denied=self.client.get("/kitchen/queue")
        self.assertEqual(denied.status_code,401)
        self.client.post("/auth/login",json={"username":"kitchen@shuangfen.local","password":"123456"})
        self.assertEqual(self.client.get("/kitchen/queue").status_code,200)

    def test_waiting_queue_duplicate_and_cancel(self):
        from restaurant.services.queue_manager import QueueManager
        entry=QueueManager.join_waitlist(2,contact_name="排队测试",phone="13900000088")
        with self.assertRaises(ServiceError): QueueManager.join_waitlist(3,contact_name="排队测试",phone="13900000088")
        self.assertEqual(QueueManager.cancel(entry["queue_id"])["status"],"cancelled")

    def test_customer_order_isolation_and_duplicate_payment(self):
        self.client.post("/auth/login",json={"account":"13900000001","password":"123456"})
        response=self.client.get("/orders/9001")
        self.assertEqual(response.status_code,404)
        self.client.post("/auth/login",json={"account":"13900000002","password":"123456"})
        self.assertEqual(self.client.get("/orders/9001").status_code,200)
        from restaurant.services.order_service import pay_order
        first=pay_order(9001)
        second=pay_order(9001)
        self.assertFalse(first["already_paid"])
        self.assertTrue(second["already_paid"])
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM payments WHERE order_id=9001").fetchone()[0],1)

    def test_preorder_waits_until_ready_time(self):
        from restaurant.services.order_service import create_preorder
        from restaurant.services.queue_manager import QueueManager
        result=create_preorder(1,"13900000001",[{"dish_id":6,"quantity":1}],"2099-01-01T12:00:00")
        with get_connection() as db:
            item_id=db.execute("SELECT order_item_id FROM order_lines WHERE order_id=?",(result["order_id"],)).fetchone()[0]
        self.assertEqual(QueueManager.enqueue_due_preorders("2098-01-01 00:00:00"),0)
        self.assertEqual(QueueManager.enqueue_due_preorders("2099-01-02 00:00:00"),1)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM kitchen_queue WHERE order_item_id=?",(item_id,)).fetchone()[0],"waiting")

    def test_called_waitlist_entry_expires(self):
        from restaurant.services.queue_manager import QueueManager
        entry=QueueManager.join_waitlist(2,contact_name="超时测试",phone="13900000077")
        with get_connection() as db:
            db.execute("UPDATE waiting_queue SET status='called',called_at=datetime('now','-30 minutes') WHERE queue_id=?",(entry["queue_id"],))
        self.assertEqual(QueueManager.expire_called(),1)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM waiting_queue WHERE queue_id=?",(entry["queue_id"],)).fetchone()[0],"expired")

    def test_kitchen_updates_only_one_line(self):
        from restaurant.services.kitchen_service import start_item, finish_item
        before=get_connection()
        with before as db: other=db.execute("SELECT status FROM order_lines WHERE order_item_id=9002").fetchone()[0]
        start_item(9001); finish_item(9001)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM order_lines WHERE order_item_id=9001").fetchone()[0],"ready")
            self.assertEqual(db.execute("SELECT status FROM order_lines WHERE order_item_id=9002").fetchone()[0],other)

    def test_reinitialization_does_not_duplicate_seed_rows(self):
        from restaurant.db.database import seed_defaults
        with get_connection() as db:
            seed_defaults(db)
            count1=db.execute("SELECT count(*) FROM bookings").fetchone()[0]
            seed_defaults(db)
            count2=db.execute("SELECT count(*) FROM bookings").fetchone()[0]
        self.assertEqual(count1,count2)

    def test_z_closing_visit_calls_next_waiting_party(self):
        from restaurant.services.order_service import pay_order
        from restaurant.services.queue_manager import QueueManager
        entry=QueueManager.join_waitlist(2,contact_name="释放桌测试",phone="13900000066")
        pay_order(9001)
        from restaurant.services.dining_service import close_dining_session
        result=close_dining_session(1)
        self.assertEqual(result["status"],"closed")
        self.assertEqual(result["next_queue"]["queue_id"],entry["queue_id"])

    def test_large_party_reservations_exhaust_distinct_tables(self):
        from restaurant.services.booking_service import create_booking
        from restaurant.services.common import ServiceError
        day="2026-12-29"
        a=create_booking("甲","13900000041",day,3,6)
        b=create_booking("乙","13900000042",day,3,6)
        self.assertNotEqual(a["table_id"],b["table_id"])
        with self.assertRaises(ServiceError) as caught:
            create_booking("丙","13900000043",day,3,6)
        self.assertEqual(caught.exception.status_code,409)

    def test_invalid_writes_return_json_errors(self):
        cases=[
            ("customer", "/bookings", {"booking_date":"bad","time_slot_id":1,"party_size":2}),
            ("frontdesk", "/frontdesk/walk-ins", {"party_size":0,"table_id":1}),
            ("frontdesk", "/frontdesk/orders", {"visit_id":1,"items":[]}),
            ("kitchen", "/kitchen/menu/1/availability", {"is_available":"maybe"}),
            ("admin", "/admin/staff", {"name":"","phone_number":"x","email":"bad","password":"1","role":"admin"}),
            ("admin", "/admin/dishes", {"name":"","price":-1}),
        ]
        login={"customer":("13900000001","123456"),"frontdesk":("frontdesk@shuangfen.local","123456"),"kitchen":("kitchen@shuangfen.local","123456"),"admin":("admin@shuangfen.local","123456")}
        for role,path,body in cases:
            self.client.post("/auth/login",json={"account":login[role][0],"password":login[role][1]})
            response=self.client.post(path,json=body)
            self.assertGreaterEqual(response.status_code,400,(role,path,response.status_code))
            self.assertLess(response.status_code,500,(role,path,response.status_code))
            self.assertTrue(response.is_json,(role,path))


if __name__ == "__main__":
    unittest.main()
