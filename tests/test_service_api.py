import unittest
from unittest.mock import patch

from backend_test_helpers import RestaurantTestCase, restaurant_date_in, write
from restaurant.services.dining_service import register_arrival
from restaurant.db.database import ensure_database, get_connection
from restaurant.services.booking_service import create_booking
from restaurant.services.common import ServiceError
from restaurant.services.order_service import pay_order


class ServiceAndApiTests(RestaurantTestCase):
    def test_invalid_booking_is_json_and_does_not_write(self):
        with get_connection() as db:
            before = db.execute("SELECT count(*) FROM bookings").fetchone()[0]
        client = self.signed_in("13900000001")
        response = write(client, "/bookings", {"booking_date":"2026-12-20", "time_slot_id":1, "party_size":-2})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.is_json)
        self.assertFalse(response.json["success"])
        with get_connection() as db:
            after = db.execute("SELECT count(*) FROM bookings").fetchone()[0]
        self.assertEqual(before, after)

    def test_valid_booking_and_conflict(self):
        client = self.signed_in("13900000001")
        fields = {"booking_date":restaurant_date_in(10), "time_slot_id":1, "party_size":2, "table_id":1}
        self.assertEqual(write(client, "/bookings", fields).status_code, 201)
        self.assertEqual(write(client, "/bookings", fields).status_code, 409)
        self.assertEqual(write(client, "/bookings", {**fields, "time_slot_id":99, "table_id":6}).status_code, 400)

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
        customer = self.signed_in("13900000001")
        self.assertEqual(customer.get("/admin/staff").status_code, 403)
        self.assertEqual(write(customer, "/auth/logout").status_code, 303)
        self.assertEqual(customer.get("/kitchen/queue").status_code, 401)
        kitchen = self.signed_in("kitchen@shuangfen.local")
        self.assertEqual(kitchen.get("/kitchen/queue").status_code, 200)

    def test_waiting_queue_duplicate_and_cancel(self):
        from restaurant.services.queue_manager import QueueManager
        entry=QueueManager.join_waitlist(2,contact_name="排队测试",phone="13900000088")
        with self.assertRaises(ServiceError): QueueManager.join_waitlist(3,contact_name="排队测试",phone="13900000088")
        self.assertEqual(QueueManager.cancel(entry["queue_id"])["status"],"cancelled")

    def test_customer_order_isolation_and_duplicate_payment(self):
        other = self.signed_in("13900000001")
        response = other.get("/orders/9001")
        self.assertEqual(response.status_code,404)
        owner = self.signed_in("13900000002")
        detail = owner.get("/orders/9001")
        self.assertEqual(detail.status_code, 200)
        summary = next(row for row in owner.get("/orders").json["orders"] if row["order_id"] == 9001)
        self.assertEqual(summary["total_amount"], detail.json["order"]["total_amount"])
        from restaurant.services.order_service import pay_order
        first=pay_order(9001)
        second=pay_order(9001)
        self.assertFalse(first["already_paid"])
        self.assertTrue(second["already_paid"])
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM orders WHERE order_id=9001 AND paid_at IS NOT NULL").fetchone()[0],1)

    def test_preorder_waits_until_ready_time(self):
        from restaurant.services.order_service import create_preorder
        from restaurant.services.queue_manager import QueueManager
        result=create_preorder(1,"13900000001",[{"dish_id":6,"quantity":1}],"2099-01-01T12:00:00")
        with get_connection() as db:
            item_id=db.execute("SELECT order_item_id FROM order_items WHERE order_id=?",(result["order_id"],)).fetchone()[0]
        self.assertEqual(QueueManager.enqueue_due_preorders("2099-01-02 00:00:00"),0)
        with patch("restaurant.services.dining_service.current_table_window", return_value=("2026-12-01", None)):
            register_arrival(1)
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
        with before as db: other=db.execute("SELECT status FROM order_items WHERE order_item_id=9002").fetchone()[0]
        start_item(9001); finish_item(9001)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM order_items WHERE order_item_id=9001").fetchone()[0],"ready")
            self.assertEqual(db.execute("SELECT status FROM order_items WHERE order_item_id=9002").fetchone()[0],other)

    def test_reinitialization_does_not_duplicate_seed_rows(self):
        from restaurant.db.database import seed_defaults
        with get_connection() as db:
            seed_defaults(db)
            count1=db.execute("SELECT count(*) FROM bookings").fetchone()[0]
            seed_defaults(db)
            count2=db.execute("SELECT count(*) FROM bookings").fetchone()[0]
        self.assertEqual(count1,count2)

    def test_closing_visit_calls_next_waiting_party(self):
        from restaurant.services.dining_service import close_dining_session
        from restaurant.services.kitchen_service import finish_item, serve_item
        from restaurant.services.order_service import cancel_order_item, pay_order
        from restaurant.services.queue_manager import QueueManager

        entry = QueueManager.join_waitlist(2, contact_name="Release fixture", phone="13900000066")
        cancel_order_item(9001, 9001)
        self.assertEqual(pay_order(9001)["payment_status"], "paid")
        with self.assertRaises(ServiceError) as cooking:
            close_dining_session(1)
        self.assertEqual(cooking.exception.code, "VISIT_UNFINISHED_ITEMS")
        finish_item(9002)
        with self.assertRaises(ServiceError) as ready:
            close_dining_session(1)
        self.assertEqual(ready.exception.status_code, 409)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM dining_sessions WHERE visit_id=1").fetchone()[0], "seated")
            self.assertEqual(db.execute("SELECT status FROM waiting_queue WHERE queue_id=?", (entry["queue_id"],)).fetchone()[0], "waiting")
        serve_item(9002)
        result = close_dining_session(1)
        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["next_queue"]["queue_id"], entry["queue_id"])

    def test_large_party_reservations_exhaust_distinct_tables(self):
        from restaurant.services.booking_service import create_booking
        from restaurant.services.common import ServiceError
        day=restaurant_date_in(10)
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
            client = self.signed_in(*login[role])
            response = write(client, path, body)
            self.assertGreaterEqual(response.status_code,400,(role,path,response.status_code))
            self.assertLess(response.status_code,500,(role,path,response.status_code))
            self.assertTrue(response.is_json,(role,path))


if __name__ == "__main__":
    unittest.main()
