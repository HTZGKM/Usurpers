"""Regression tests for the active database schema and restaurant workflows."""
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from threading import Barrier
from unittest.mock import patch

from backend_test_helpers import RestaurantTestCase, login, restaurant_date_in, write
from restaurant.business_time import current_table_window
from restaurant.db import database
from restaurant.scheduler import run_scheduled_tasks
from restaurant.services.booking_service import create_booking, find_available_tables, update_booking
from restaurant.services.common import ServiceError
from restaurant.services.dining_service import close_dining_session, register_arrival, register_walk_in
from restaurant.services.order_service import create_dine_in_order, get_order
from restaurant.services.queue_manager import QueueManager


def dish(dish_id=1, quantity=1):
    return {"items-0-dish_id": dish_id, "items-0-quantity": quantity}


class RemainingFeatureTests(RestaurantTestCase):
    def test_waitlist_to_payment_across_four_roles(self):
        customer = self.signed_in("13900000001")
        frontdesk = self.signed_in("frontdesk@shuangfen.local")
        kitchen = self.signed_in("kitchen@shuangfen.local")
        admin = self.signed_in("admin@shuangfen.local")

        joined = write(customer, "/waiting-queue", {"party_size": 2, "contact_name": "Waitlist fixture"})
        self.assertEqual(joined.status_code, 201)
        ticket = joined.json["queue"]["queue_id"]
        self.assertEqual(customer.get("/waiting-queue/mine").json["queue"]["status"], "waiting")
        self.assertEqual(write(frontdesk, "/frontdesk/tables/6/call-next").json["queue"]["queue_id"], ticket)
        self.assertEqual(customer.get("/waiting-queue/mine").json["queue"]["called_table_id"], 6)
        self.assertEqual(write(frontdesk, f"/frontdesk/waiting-queue/{ticket}/seat", {"table_id": 1}).status_code, 409)
        visit = write(frontdesk, f"/frontdesk/waiting-queue/{ticket}/seat", {"table_id": 6}).json["visit"]["visit_id"]
        self.assertIsNone(customer.get("/waiting-queue/mine").json["queue"])

        placed = write(customer, f"/visits/{visit}/orders", dish())
        self.assertEqual(placed.status_code, 201)
        order = placed.json["order"]["order_id"]
        original_item = get_order(order)["items"][0]["order_item_id"]
        self.assertEqual(write(customer, f"/orders/{order}/edit", {**dish(quantity=2), "expected_version": 1}).json["order"]["total_amount"], 76)
        self.assertEqual(write(frontdesk, f"/frontdesk/orders/{order}/edit", {**dish(quantity=3), "expected_version": 2}).json["order"]["total_amount"], 114)
        self.assertEqual([row["order_item_id"] for row in get_order(order)["items"]], [original_item])
        items = [item for item in kitchen.get("/kitchen/queue?status=active").json["items"] if item["order_id"] == order]
        self.assertEqual(len(items), 1)
        item = items[0]["order_item_id"]
        self.assertEqual((item, items[0]["status"], items[0]["quantity"]), (original_item, "waiting", 3))
        self.assertEqual(write(kitchen, f"/kitchen/items/{item}/start", {"expected_version": 3}).status_code, 200)
        self.assertEqual(get_order(order)["items"][0]["kitchen_status"], "cooking")
        self.assertEqual(write(customer, f"/orders/{order}/cancel").status_code, 409)
        self.assertEqual(write(kitchen, f"/kitchen/items/{item}/complete").status_code, 200)
        self.assertEqual(write(frontdesk, f"/frontdesk/orders/{order}/items/{item}/serve").status_code, 200)
        self.assertEqual(write(frontdesk, f"/frontdesk/visits/{visit}/close").status_code, 409)
        self.assertEqual(write(frontdesk, f"/frontdesk/orders/{order}/pay").status_code, 200)
        self.assertEqual(write(frontdesk, f"/frontdesk/visits/{visit}/close").status_code, 200)
        self.assertEqual(admin.get(f"/admin/orders/{order}").json["order"]["payment_status"], "paid")
        database.ensure_database()
        self.assertEqual(get_order(order)["total_amount"], 114)

    def test_closed_unpaid_order_can_be_paid_by_owner_or_frontdesk_once(self):
        owner = self.signed_in("13900000002")
        other = self.signed_in("13900000001")
        desk = self.signed_in("frontdesk@shuangfen.local")
        with database.get_connection() as db:
            db.execute("""UPDATE dining_sessions SET status='closed'
                          WHERE visit_id=(SELECT visit_id FROM orders WHERE order_id=9001)""")
        self.assertEqual(write(other, "/orders/9001/pay").status_code, 404)
        paid = write(owner, "/orders/9001/pay")
        self.assertEqual(paid.status_code, 200)
        self.assertFalse(paid.json["payment"]["already_paid"])
        self.assertTrue(write(desk, "/frontdesk/orders/9001/pay").json["payment"]["already_paid"])

    @patch("restaurant.services.booking_service.current_table_window", return_value=("2026-12-20", None))
    def test_preorder_edit_and_promotion_follow_visit(self, _restaurant_clock):
        customer = self.signed_in("13900000001")
        desk = self.signed_in("frontdesk@shuangfen.local")
        kitchen = self.signed_in("kitchen@shuangfen.local")
        booking = create_booking("Preorder fixture", "13900000001", "2026-12-20", 1, 2, "13900000001", 6)["booking_id"]
        response = write(customer, f"/bookings/{booking}/preorders",
                         {**dish(), "estimated_ready_at": "2026-12-20T11:00:00+08:00"})
        self.assertEqual(response.status_code, 201)
        order = response.json["order"]["order_id"]
        original = get_order(order)["items"][0]
        edited = write(customer, f"/orders/{order}/edit", {**dish(quantity=2), "expected_version": 1})
        line = next(item for item in edited.json["order"]["items"] if item["status"] == "waiting")
        self.assertEqual([item["order_item_id"] for item in edited.json["order"]["items"]], [original["order_item_id"]])
        self.assertIsNone(line["kitchen_status"])
        self.assertEqual(write(kitchen, f"/kitchen/items/{line['order_item_id']}/start", {"expected_version": 2}).status_code, 409)
        self.assertEqual(write(customer, f"/orders/{order}/pay").status_code, 409)
        self.assertEqual(QueueManager.enqueue_due_preorders("2026-12-20 04:00:00"), 0)
        update_booking(booking, "2026-12-21", 2, 2, "13900000001", 1, expected_version=1)
        with patch("restaurant.services.dining_service.current_table_window", return_value=("2026-12-21", None)):
            arrival = write(desk, f"/frontdesk/bookings/{booking}/check-in")
        self.assertEqual(arrival.status_code, 201)
        visit = arrival.json["visit"]["visit_id"]
        self.assertEqual(get_order(order)["visit_id"], visit)
        self.assertEqual(get_order(order)["table_id"], 1)
        self.assertEqual(run_scheduled_tasks("2026-12-21 08:59:00")["promoted_preorders"], 0)
        self.assertEqual(run_scheduled_tasks("2026-12-21 09:00:00")["promoted_preorders"], 1)
        self.assertEqual(run_scheduled_tasks("2026-12-21 09:00:00")["promoted_preorders"], 0)
        self.assertEqual(write(desk, f"/frontdesk/visits/{visit}/close").status_code, 409)
        self.assertEqual(write(desk, f"/frontdesk/orders/{order}/pay").status_code, 200)
        blocked = write(desk, f"/frontdesk/visits/{visit}/close")
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json["error"], "VISIT_UNFINISHED_ITEMS")
        item = line["order_item_id"]
        self.assertEqual(write(kitchen, f"/kitchen/items/{item}/start", {"expected_version": 2}).status_code, 200)
        self.assertEqual(write(kitchen, f"/kitchen/items/{item}/complete").status_code, 200)
        self.assertEqual(write(desk, f"/frontdesk/orders/{order}/items/{item}/serve").status_code, 200)
        self.assertEqual(write(desk, f"/frontdesk/visits/{visit}/close").status_code, 200)

    def test_reserved_table_rules_use_current_window_and_release_is_atomic(self):
        date = current_table_window()[0]
        create_booking("Dinner fixture", "13900000001", date, 3, 2, table_id=6)
        with patch("restaurant.services.dining_service.current_table_window", return_value=(date, "11:00-14:00")):
            visit = register_walk_in(2, 6)["visit_id"]
            self.assertEqual(close_dining_session(visit)["status"], "closed")
        entry = QueueManager.join_waitlist(2, "Waiting fixture", "13900000001", "13900000001")
        with patch("restaurant.services.dining_service.current_table_window", return_value=(date, "19:00-21:00")):
            with self.assertRaises(ServiceError):
                QueueManager.call_next(6)
            call = QueueManager.call_next(1)
            self.assertEqual(call["queue_id"], entry["queue_id"])
            with self.assertRaises(ServiceError):
                QueueManager.seat(entry["queue_id"], 6)
            self.assertEqual(QueueManager.seat(entry["queue_id"], 1)["status"], "seated")

    def test_concurrent_booking_cannot_take_same_table(self):
        gate = Barrier(2)
        day = restaurant_date_in(10)

        def submit(phone):
            gate.wait()
            try:
                return create_booking("Concurrent booking", phone, day, 2, 2, table_id=6)["status"]
            except ServiceError as error:
                return error.status_code

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(submit, ["13900000001", "13900000002"]))
        self.assertCountEqual(results, ["booked", 409])

    def test_booking_query_and_write_agree_in_active_slot(self):
        date = current_table_window()[0]
        with patch("restaurant.services.booking_service.current_table_window", return_value=(date, "11:00-14:00")):
            self.assertNotIn(2, [row["table_id"] for row in find_available_tables(date, 1, 2)])
            with self.assertRaises(ServiceError):
                create_booking("Busy table", "13900000001", date, 1, 2, table_id=2)
        future = restaurant_date_in(10)
        self.assertIn(2, [row["table_id"] for row in find_available_tables(future, 1, 2)])
        self.assertEqual(create_booking("Future table", "13900000001", future, 1, 2, table_id=2)["table_id"], 2)

    def test_admin_inventory_recipe_and_manual_stock(self):
        admin = self.signed_in("admin@shuangfen.local")
        response = write(admin, "/admin/inventory/ingredients", {"name": "Test cheese", "unit": "g", "on_hand": 100})
        self.assertEqual(response.status_code, 201)
        ingredient = response.json["ingredient"]["ingredient_id"]
        self.assertEqual(write(admin, f"/admin/inventory/ingredients/{ingredient}/adjust", {"quantity": -5}).status_code, 200)
        path = "/admin/dishes/1/recipe"
        fields = {"ingredients-0-ingredient_id": ingredient, "ingredients-0-quantity_per_dish": 12.5}
        self.assertEqual(write(admin, path, fields, "PUT").status_code, 200)
        self.assertEqual(admin.get(path).json["recipe"][0]["quantity_per_dish"], 12.5)
        duplicate = {**fields, "ingredients-1-ingredient_id": ingredient, "ingredients-1-quantity_per_dish": 4}
        self.assertEqual(write(admin, path, duplicate, "PUT").status_code, 409)
        self.assertEqual(admin.get(path).json["recipe"][0]["quantity_per_dish"], 12.5)
        create_dine_in_order(1, [{"dish_id": 1, "quantity": 1}], "13900000002")
        self.assertEqual(admin.get("/admin/inventory/ingredients").json["ingredients"][0]["on_hand"], 95)
        self.assertEqual(write(admin, path, {}, "PUT").json["recipe"], [])

    def test_deactivation_reset_and_customer_history(self):
        customer = self.signed_in("13900000002")
        admin = self.signed_in("admin@shuangfen.local")
        self.assertEqual(write(admin, "/admin/customers/13900000002/deactivate").status_code, 200)
        self.assertEqual(customer.get("/orders").status_code, 403)
        self.assertEqual(write(admin, "/admin/customers/13900000002/activate").status_code, 200)
        self.assertEqual(login(customer, "13900000002").status_code, 303)
        self.assertIn(9001, [row["order_id"] for row in customer.get("/orders").json["orders"]])
        self.assertEqual(write(admin, "/admin/staff/1/deactivate").status_code, 409)
        self.assertEqual(write(admin, "/admin/staff/2/deactivate").status_code, 200)
        self.assertEqual(write(admin, "/admin/staff/2/activate").status_code, 200)
        self.assertEqual(write(admin, "/admin/staff/2/reset-password", {"password": "TestReset-2026"}).status_code, 200)
        self.signed_in("frontdesk@shuangfen.local", "TestReset-2026")

    def test_seed_does_not_add_future_payments_or_kitchen_tasks(self):
        for now in (
            datetime(2026, 11, 24, 1, tzinfo=timezone.utc),
            datetime(2026, 11, 24, 18, tzinfo=timezone.utc),
        ):
            with self.subTest(now=now):
                with patch.object(database, "datetime", wraps=datetime) as date_time:
                    date_time.now.return_value = now
                    database.ensure_database()
                with database.get_connection() as conn:
                    invalid = conn.execute("SELECT COUNT(*) FROM orders WHERE order_id BETWEEN 2000 AND 2999 AND paid_at>?",
                                           (now.strftime("%Y-%m-%d %H:%M:%S"),)).fetchone()[0]
                    self.assertEqual(invalid, 0)
                    oldest = conn.execute("SELECT MIN(date(created_at,'+8 hours')) FROM orders WHERE order_id BETWEEN 2000 AND 2999").fetchone()[0]
                    self.assertEqual(oldest, (now + timedelta(hours=8, days=-6)).date().isoformat())
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM kitchen_queue WHERE order_id BETWEEN 2000 AND 2999").fetchone()[0], 0)
                    self.assertFalse(conn.execute("""SELECT 1 FROM bookings JOIN dining_sessions USING(booking_id)
                        WHERE bookings.status='booked' AND dining_sessions.status='seated'""").fetchone())

    def test_legacy_database_is_rejected_without_rewriting_it(self):
        legacy = self.db.with_name("legacy.sqlite")
        with closing(sqlite3.connect(legacy)) as conn, conn:
            conn.execute("CREATE TABLE bookings (booking_id INTEGER PRIMARY KEY, time_slot_id INTEGER)")
        before = legacy.read_bytes()
        with patch.dict(os.environ, {"USURPERS_DB_PATH": str(legacy)}):
            with self.assertRaisesRegex(RuntimeError, "Back it up"):
                database.ensure_database()
        self.assertEqual(legacy.read_bytes(), before)

    def test_flask_process_restart_preserves_kitchen_work(self):
        env = dict(os.environ, USURPERS_DB_PATH=str(self.db))
        command = [sys.executable, "-c", """from app import app
from restaurant.db.database import get_connection
from restaurant.services.kitchen_service import start_item
import sys
assert app.test_client().get('/health').status_code == 200
if sys.argv[1] == 'start':
    start_item(9001)
with get_connection() as db:
    assert db.execute('SELECT status FROM kitchen_queue WHERE order_item_id=9001').fetchone()[0] == 'cooking'
"""]
        for action in ("start", "read"):
            result = subprocess.run([*command, action], env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
