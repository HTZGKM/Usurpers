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
        self.assertEqual(caught.exception.status_code, 409)

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
        from restaurant.services.order_service import get_visit_bill, pay_visit
        with get_connection() as db:
            db.execute("UPDATE order_items SET status='served' WHERE order_id IN (SELECT order_id FROM orders WHERE visit_id=1)")
        bill=get_visit_bill(1)
        first=pay_visit(1,None,bill['order_ids'],bill['total_cents'],request_key='duplicate-pay',actor='desk')
        second=pay_visit(1,None,bill['order_ids'],bill['total_cents'],request_key='duplicate-pay',actor='desk')
        self.assertFalse(first["already_paid"])
        self.assertTrue(second["already_paid"])
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM orders WHERE order_id=9001 AND paid_at IS NOT NULL").fetchone()[0],1)

    def test_visit_payment_is_atomic_and_scoped_to_the_confirmed_balance(self):
        from restaurant.db.database import insert_id
        from restaurant.services.order_service import create_dine_in_order, get_order

        owner_phone = "13900000001"
        owner = self.signed_in(owner_phone)
        other = self.signed_in("13900000002")
        frontdesk = self.signed_in("frontdesk@shuangfen.local")
        with get_connection() as db:
            old_visit = insert_id(db, "INSERT INTO dining_sessions(customer_phone,party_size,table_id) VALUES(?,2,6)",
                                  (owner_phone,), "visit_id")
        line = {"dish_id": 1, "quantity": 1}
        history = create_dine_in_order(old_visit, [line], owner_phone)
        with get_connection() as db:
            db.execute("UPDATE dining_sessions SET status='closed' WHERE visit_id=?", (old_visit,))
            visit = insert_id(db, "INSERT INTO dining_sessions(customer_phone,party_size,table_id) VALUES(?,2,6)",
                              (owner_phone,), "visit_id")
        first = create_dine_in_order(visit, [line], owner_phone)
        settled = create_dine_in_order(visit, [line], owner_phone)
        with get_connection() as db:
            db.execute("UPDATE orders SET payment_status='paid',paid_at=CURRENT_TIMESTAMP WHERE order_id=?",(settled['order_id'],))
            db.execute("UPDATE order_items SET status='served' WHERE order_id=?",(settled['order_id'],))
        cancelled = create_dine_in_order(visit, [line], owner_phone)
        self.assertEqual(write(owner, f"/orders/{cancelled['order_id']}/cancel", {"expected_version":1}).status_code, 200)
        second = create_dine_in_order(visit, [line], owner_phone)
        with get_connection() as db:
            db.execute("UPDATE order_items SET status='served' WHERE order_id IN (?,?)",(first['order_id'],second['order_id']))
        endpoint = f"/visits/{visit}/pay"
        quote = {"idempotency_key":"table-quote", "order_ids": str(first["order_id"]), "total_cents": round(first["total_amount"] * 100)}
        self.assertEqual(write(other, endpoint, quote).status_code, 404)
        self.assertEqual(write(frontdesk, endpoint, quote).status_code, 409)
        stale = write(owner, endpoint, quote)
        self.assertEqual((stale.status_code, stale.json["error"]), (409, "BILL_CHANGED"))
        ids = [first["order_id"], second["order_id"]]
        quote = {"idempotency_key":"table-quote", "order_ids": ",".join(map(str, ids)), "total_cents": round((first["total_amount"] + second["total_amount"]) * 100)}
        self.assertEqual(write(owner, endpoint, {**quote, "total_cents": quote["total_cents"] - 1}).status_code, 409)
        self.assertTrue(all(get_order(oid)["payment_status"] == "unpaid" for oid in ids))
        payment = write(owner, endpoint, quote)
        self.assertEqual(payment.status_code, 200)
        self.assertEqual(payment.json["payment"]["order_ids"], ids)
        self.assertTrue(all(get_order(oid)["payment_status"] == "paid" for oid in ids))
        later = create_dine_in_order(visit, [line], owner_phone)
        self.assertTrue(write(owner, endpoint, quote).json["payment"]["already_paid"])
        self.assertEqual(get_order(later["order_id"])["payment_status"], "unpaid")
        self.assertEqual(get_order(history["order_id"])["payment_status"], "unpaid")
        self.assertEqual(get_order(cancelled["order_id"])["status"], "cancelled")

    def test_frontdesk_order_retry_recovers_first_order_without_another_kitchen_line(self):
        desk = self.signed_in("frontdesk@shuangfen.local")
        with get_connection() as db:
            visit = db.execute("INSERT INTO dining_sessions(party_size,table_id) VALUES(2,6) RETURNING visit_id").fetchone()[0]
        fields = {"visit_id": visit, "items-0-dish_id": 1, "items-0-quantity": 1, "idempotency_key": "same-draft"}
        first = write(desk, "/frontdesk/orders", fields)
        second = write(desk, "/frontdesk/orders", fields)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.json["order"]["order_id"], first.json["order"]["order_id"])
        conflict = write(desk, "/frontdesk/orders", {**fields, "items-0-quantity": 2})
        self.assertEqual((conflict.status_code, conflict.json["error"]), (409, "IDEMPOTENCY_KEY_REUSED"))
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM orders WHERE visit_id=?", (visit,)).fetchone()[0], 1)

    def test_order_with_stale_price_or_excessive_quantity_keeps_database_unchanged(self):
        desk = self.signed_in("frontdesk@shuangfen.local")
        with get_connection() as db:
            visit = db.execute("INSERT INTO dining_sessions(party_size,table_id) VALUES(2,6) RETURNING visit_id").fetchone()[0]
        fields = {"visit_id": visit, "items-0-dish_id": 1, "items-0-quantity": 1,
                  "items-0-quoted_unit_cents": 100, "idempotency_key": "fixture-stale-price"}
        stale = write(desk, "/frontdesk/orders", fields)
        self.assertEqual((stale.status_code, stale.json["error"]), (409, "PRICE_CHANGED"))
        self.assertEqual(write(desk, "/frontdesk/orders", {**fields, "items-0-quantity": 100}).status_code, 400)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM orders WHERE visit_id=?", (visit,)).fetchone()[0], 0)

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
        from restaurant.services.kitchen_service import finish_item, serve_order
        from restaurant.services.order_service import cancel_order_item, get_visit_bill, pay_visit
        from restaurant.services.queue_manager import QueueManager

        entry = QueueManager.join_waitlist(2, contact_name="Release fixture", phone="13900000066")
        cancel_order_item(9001, 9001)

        with self.assertRaises(ServiceError) as cooking:
            close_dining_session(1)
        self.assertEqual(cooking.exception.status_code, 409)
        finish_item(9002)
        with self.assertRaises(ServiceError) as ready:
            close_dining_session(1)
        self.assertEqual(ready.exception.status_code, 409)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM dining_sessions WHERE visit_id=1").fetchone()[0], "seated")
            self.assertEqual(db.execute("SELECT status FROM waiting_queue WHERE queue_id=?", (entry["queue_id"],)).fetchone()[0], "waiting")
        serve_order(9001,actor='desk')
        bill=get_visit_bill(1)
        pay_visit(1,None,bill['order_ids'],bill['total_cents'],request_key='close-bill',actor='desk')
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
