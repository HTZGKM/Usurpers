from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from unittest.mock import patch
import unittest
from uuid import uuid4

import test_postgres_booking_consistency as postgres
from backend_test_helpers import bind_test_session, csrf
from restaurant.db.database import get_connection
from restaurant.scheduler import run_scheduled_tasks


GUEST = "/reservation-api"
DESK = "/frontdesk/reservation-api"
DAY = "2048-02-20"


def clock(hour, minute=0, second=0):
    return patch("restaurant.services.allocation.database_now",
                 return_value=datetime(2048, 2, 20, hour - 8, minute, second, tzinfo=timezone.utc))


@unittest.skipUnless(postgres.TEST_DSN, "requires the disposable PostgreSQL fixture")
class ReservationRebuildTests(unittest.TestCase):
    setUp = postgres.PostgresBookingConsistencyTests.setUp
    phone = staticmethod(postgres.PostgresBookingConsistencyTests.phone)
    actor = postgres.PostgresBookingConsistencyTests.actor
    send = staticmethod(postgres.PostgresBookingConsistencyTests.send)

    def reserve(self, actor, arrival="19:00", table=1, key="first", **fields):
        return self.send(actor, GUEST + "/bookings", {
            "booking_date": DAY, "arrival_time": arrival, "party_size": 2,
            "table_id": table, "idempotency_key": key, **fields,
        })

    def call_party(self, desk, table=1, count=2):
        ticket = self.issue_ticket(desk, count)
        self.assertEqual(self.send(desk, f"{DESK}/tables/{table}/call").json["queue"]["queue_id"], ticket)
        return ticket

    def issue_ticket(self, desk, count=2):
        return self.send(desk, DESK + "/tickets", {
            "party_size": count, "idempotency_key": uuid4().hex,
        }).json["queue"]["queue_id"]

    def upgrade(self):
        import psycopg

        with psycopg.connect(self.dsn, autocommit=True) as db:
            for name in ("002_reservation_allocation.sql", "006_reservation_rules.sql"):
                db.execute((postgres.DB_SQL / "migrations" / name).read_text(encoding="utf-8"))

    def test_at_1908_arrival_is_recorded_separately_from_seating(self):
        self.upgrade()
        guest, desk = self.actor(), self.actor(staff=True)
        with clock(18):
            response = self.reserve(guest)
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        booking_id = response.json["booking"]["booking_id"]
        with clock(19, 8):
            arrived = self.send(desk, f"/frontdesk/reservation-api/bookings/{booking_id}/arrive")
        self.assertEqual(arrived.status_code, 200)
        with clock(19, 11):
            self.assertEqual(self.send(desk, "/operations/refresh").status_code, 200)
            self.assertEqual(self.send(desk, "/frontdesk/reservation-api/snapshot", method="GET").status_code, 200)
            state = self.send(guest, "/reservation-api/bookings", method="GET").json["bookings"][0]
        self.assertEqual(state["phase"], "waiting_to_seat")
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM dining_sessions WHERE booking_id=?", (booking_id,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM table_holds WHERE booking_id=?", (booking_id,)).fetchone()[0], 1)

    def test_ready_and_seating_have_distinct_states_and_link_the_preorder(self):
        self.upgrade()
        guest, desk = self.actor(), self.actor(staff=True)
        with get_connection() as db:
            db.execute("INSERT INTO dishes(dish_name,price) VALUES('Fixture dish',19)")
        with clock(18):
            booking = self.reserve(guest).json["booking"]["booking_id"]
        path = f"{DESK}/bookings/{booking}"
        order = self.send(guest, f"/bookings/{booking}/preorders", {
            "idempotency_key": "fixture-preorder",
            "estimated_ready_at": DAY + "T19:00:00+08:00", "items-0-dish_id": 1, "items-0-quantity": 1,
        })
        self.assertEqual(order.status_code, 201)
        order_id = order.json["order"]["order_id"]
        with clock(18, 50):
            ready = self.send(desk, path + "/ready", {"table_id": 1, "expected_version": 1})
            self.assertEqual(ready.json["booking"]["phase"], "ready")
            self.assertEqual(self.send(desk, path + "/seat").json["error"], "TABLE_NOT_READY")
            checked = self.send(desk, path + "/arrive").json["booking"]
            seated = self.send(desk, path + "/seat", {"table_id": 1, "expected_version": checked["version"]})
            self.assertEqual(seated.status_code, 201)
            visit = seated.json["visit"]["visit_id"]
            self.assertEqual(self.send(guest, GUEST + "/bookings", method="GET").json["visit"]["visit_id"], visit)
        with clock(18, 59):
            self.assertEqual(run_scheduled_tasks(DAY + "T18:59:00+08:00")["promoted_preorders"], 0)
        with clock(19):
            self.assertEqual(run_scheduled_tasks(DAY + "T19:00:00+08:00")["promoted_preorders"], 1)
            self.assertEqual(run_scheduled_tasks(DAY + "T19:00:00+08:00")["promoted_preorders"], 0)
        with get_connection() as db:
            self.assertIsNotNone(db.execute("SELECT seated_at FROM dining_sessions WHERE visit_id=?", (visit,)).fetchone()[0])
            self.assertEqual(db.execute("SELECT visit_id FROM orders WHERE order_id=?", (order_id,)).fetchone()[0], visit)

    def test_1910_arrival_wins_at_exact_deadline_and_late_arrival_loses(self):
        self.upgrade()
        with clock(18):
            ids = [self.reserve(self.actor(index=table), table=table).json["booking"]["booking_id"] for table in (1, 2)]
        with clock(19, 10):
            gate = Barrier(2)

            def request(actor, path, method):
                gate.wait(timeout=5)
                return self.send(actor, path, method=method)

            with ThreadPoolExecutor(max_workers=2) as pool:
                arrive = pool.submit(request, self.actor(staff=True), f"{DESK}/bookings/{ids[0]}/arrive", "POST")
                sweep = pool.submit(request, self.actor(staff=True), "/operations/refresh", "POST")
                self.assertEqual(arrive.result(timeout=10).status_code, 200)
                self.assertEqual(sweep.result(timeout=10).status_code, 200)
        with clock(19, 10, 1):
            late = self.send(self.actor(staff=True), f"{DESK}/bookings/{ids[1]}/arrive")
            self.assertEqual(late.status_code, 409)
        with get_connection() as db:
            self.assertEqual([row["status"] for row in db.execute("SELECT status FROM bookings ORDER BY booking_id")],
                             ["booked", "no_show"])
            self.assertEqual(db.execute("SELECT booking_id FROM table_holds").fetchone()[0], ids[0])

    def test_no_show_closes_unseated_preorder_and_uses_server_schedule(self):
        self.upgrade()
        guest, desk = self.actor(), self.actor(staff=True)
        with get_connection() as db:
            db.execute("INSERT INTO dishes(dish_name,price) VALUES('Fixture dish',19)")
        with clock(18):
            booking = self.reserve(guest).json["booking"]["booking_id"]
            response = self.send(guest, f"/bookings/{booking}/preorders", {
                "idempotency_key": "fixture-missed-preorder",
                "estimated_ready_at": DAY + "T20:00:00+08:00", "items-0-dish_id": 1, "items-0-quantity": 1,
            })
        self.assertEqual(response.status_code, 201)
        order = response.json["order"]
        self.assertEqual(order["estimated_ready_at"], DAY + " 11:00:00")
        with clock(19, 10):
            self.send(desk, DESK + "/snapshot", method="GET")
            self.assertEqual(self.send(guest, f"/orders/{order['order_id']}", method="GET").json["order"]["status"], "active")
        with clock(19, 10, 1):
            history = self.send(guest, "/orders", method="GET").json["orders"]
            self.assertEqual(history[0]["status"], "active")
            self.assertEqual(self.send(guest, "/operations/refresh").status_code, 200)
            history = self.send(guest, "/orders", method="GET").json["orders"]
            self.assertEqual(history[0]["status"], "cancelled")
        expired = self.send(guest, f"/orders/{order['order_id']}", method="GET").json["order"]
        self.assertEqual((expired["status"], expired["total_amount"], expired["items"][0]["status"]), ("cancelled", 0, "cancelled"))

    def test_waitlist_wins_released_table_before_online_conflict_is_returned(self):
        self.upgrade()
        guest, desk = self.actor(), self.actor(staff=True)
        with clock(18):
            prior = self.reserve(guest).json["booking"]["booking_id"]
        with clock(18, 50):
            protected = self.send(desk, DESK + "/walk-ins", {"table_id": 1, "party_size": 2})
            self.assertEqual(protected.json["error"], "TABLE_UNAVAILABLE")
            ticket = self.issue_ticket(desk)
            self.assertEqual(self.send(guest, "/waiting-queue", {"party_size": 2}).status_code, 403)
        with clock(19, 10, 1):
            conflict = self.reserve(guest, "19:45", key="after-release")
            self.assertEqual((conflict.status_code, conflict.json["error"]), (409, "TABLE_UNAVAILABLE"))
            snapshot = self.send(desk, DESK + "/snapshot?date=" + DAY, method="GET").json
        self.assertEqual(snapshot["bookings"][0]["phase"], "no_show")
        self.assertEqual(snapshot["queue"][0]["status"], "called")
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM bookings WHERE booking_id=?", (prior,)).fetchone()[0], "no_show")
            self.assertEqual(db.execute("SELECT queue_id FROM table_holds WHERE kind='call'").fetchone()[0], ticket)
            self.assertEqual(db.execute("SELECT count(*) FROM bookings").fetchone()[0], 1)

    def test_call_deadline_and_pass_do_not_leave_a_visit_or_reservation(self):
        self.upgrade()
        desk = self.actor(staff=True)
        with clock(17):
            first = self.call_party(desk)
            second = self.issue_ticket(desk)
        with clock(17, 1, 1):
            denied = self.send(desk, f"{DESK}/tickets/{first}/seat", {"table_id": 1, "expected_version": 2})
            self.assertEqual((denied.status_code, denied.json["error"]), (409, "WAITLIST_CHANGED"))
            self.assertEqual(self.send(desk, f"{DESK}/tickets/{second}/pass", {"expected_version": 2}).status_code, 200)
        with get_connection() as db:
            self.assertEqual([row[0] for row in db.execute("SELECT status FROM waiting_queue ORDER BY queue_id")],
                             ["expired", "passed"])
            self.assertEqual(db.execute("SELECT count(*) FROM dining_sessions").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM table_holds").fetchone()[0], 0)
        with clock(17, 3):
            third = self.call_party(desk)
        with clock(17, 4):
            self.assertEqual(self.send(desk, f"{DESK}/tickets/{third}/seat", {"table_id": 1, "expected_version": 2}).status_code, 201)

    def test_versions_recovery_and_approved_replacement(self):
        self.upgrade()
        guest, desk = self.actor(), self.actor(staff=True)
        with clock(18):
            original = self.reserve(guest)
            self.assertEqual(original.status_code, 201)
            book = original.json["booking"]["booking_id"]
            self.assertEqual(self.reserve(guest).json, original.json)
            self.assertEqual(self.reserve(guest, table=3).json["error"], "IDEMPOTENCY_KEY_REUSED")
            fields = {"booking_date": DAY, "arrival_time": "19:00", "party_size": 2, "table_id": 2, "expected_version": 1}
            self.assertEqual(self.send(desk, f"{DESK}/bookings/{book}/edit", fields).status_code, 200)
            stale = self.send(guest, f"{GUEST}/bookings/{book}/edit", fields)
            self.assertEqual((stale.status_code, stale.json["error"]), (409, "BOOKING_CHANGED"))
        path = f"{DESK}/bookings/{book}"
        with clock(18, 50):
            legacy = self.send(desk, f"/frontdesk/bookings/{book}/check-in", {"table_id": 1})
            self.assertEqual(legacy.json["error"], "RESERVATION_REFRESH")
            self.assertEqual(self.send(desk, path + "/offer", {"table_id": 3, "expected_version": 1}).json["error"], "BOOKING_CHANGED")
            arrived = self.send(desk, path + "/arrive").json["booking"]
            self.assertEqual(arrived["table_id"], 2)
            offer = self.send(desk, path + "/offer", {"table_id": 3, "expected_version": arrived["version"]}).json["booking"]
            self.assertEqual(offer["table_id"], 2)
            self.assertEqual(self.send(desk, path + "/accept_offer", {"expected_version": offer["version"]}).status_code, 400)
            accepted = self.send(desk, path + "/accept_offer", {"expected_version": offer["version"], "customer_agreed": "true"})
            replacement = accepted.json["booking"]
            self.assertEqual((replacement["table_id"], replacement["phase"]), (3, "waiting_to_seat"))
            old_ready = self.send(desk, path + "/ready", {"table_id": 2, "expected_version": arrived["version"]})
            self.assertEqual(old_ready.json["error"], "BOOKING_CHANGED")
            ready = self.send(desk, path + "/ready", {"table_id": 3, "expected_version": replacement["version"]}).json["booking"]
            self.assertEqual(self.send(desk, path + "/seat", {"table_id": 3, "expected_version": ready["version"]})
                             .json["visit"]["table_id"], 3)

    def test_same_table_time_point_concurrency_and_independent_tables(self):
        self.upgrade()
        actors = [self.actor(index=index) for index in range(20)]
        with clock(18):
            for count, table in ((10, 1), (20, 2)):
                gate = Barrier(count, timeout=10)

                def submit(index):
                    gate.wait()
                    return self.reserve(actors[index], "19:00", table, f"race-{count}-{index}")

                with ThreadPoolExecutor(max_workers=count) as pool:
                    responses = list(pool.map(submit, range(count), timeout=25))
                self.assertEqual(sum(response.status_code == 201 for response in responses), 1)
                self.assertEqual(sum(response.status_code == 409 and response.json["error"] in ("TABLE_UNAVAILABLE", "ACTIVE_RESERVATION_EXISTS")
                                     for response in responses), count-1)
                self.assertEqual([response.status_code for response in responses if response.status_code >= 500], [])
            # A fresh account isolates interval overlap from whichever competitor won.
            overlap = self.reserve(self.actor(index=20), "19:45", 1, "overlapping")
            self.assertEqual((overlap.status_code, overlap.json["error"]), (409, "TABLE_UNAVAILABLE"))
        with get_connection() as db:
            self.assertEqual([row[0] for row in db.execute("SELECT table_id FROM table_holds ORDER BY table_id")], [1, 2])

    def test_two_distinct_tables_accept_the_same_arrival_time_concurrently(self):
        self.upgrade()
        ready = Barrier(2, timeout=8)
        actors = [self.actor(index=table) for table in (1, 2)]

        def submit(table):
            ready.wait()
            return self.reserve(actors[table-1], table=table)

        with clock(18), ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(submit, (1, 2), timeout=15))
        self.assertEqual([response.status_code for response in responses], [201, 201])
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM table_holds").fetchone()[0], 2)

    def test_call_seating_and_passing_compete_for_one_ticket(self):
        self.upgrade()
        with clock(17):
            ticket = self.call_party(self.actor(staff=True))
        path = f"{DESK}/tickets/{ticket}"
        gate = Barrier(2, timeout=8)

        def submit(desk, action, fields):
            gate.wait()
            return self.send(desk, path + action, fields)

        with clock(17, 1), ThreadPoolExecutor(max_workers=2) as pool:
            desk1, desk2 = self.actor(staff=True), self.actor(staff=True)
            seat = pool.submit(submit, desk1, "/seat", {"table_id": 1, "expected_version": 2})
            passed = pool.submit(submit, desk2, "/pass", {"expected_version": 2})
            seating, passing = seat.result(timeout=10), passed.result(timeout=10)
        self.assertIn((seating.status_code, passing.status_code), ((201, 409), (409, 200)))
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM table_holds").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM dining_sessions WHERE queue_id=?", (ticket,)).fetchone()[0],
                             int(seating.status_code == 201))

    def test_checked_in_party_gets_the_usable_replacement_before_onsite_queue(self):
        self.upgrade()
        guest, desk = self.actor(), self.actor(staff=True)
        with clock(17):
            self.assertEqual(self.send(desk, DESK + "/walk-ins", {"table_id": 1, "party_size": 2}).status_code, 201)
        with clock(17, 5):
            reservation = self.reserve(guest).json["booking"]["booking_id"]
        with clock(19):
            reported = self.send(desk, f"{DESK}/bookings/{reservation}/arrive")
            self.assertEqual(reported.json["booking"]["phase"], "waiting_to_seat")
            ticket = self.issue_ticket(desk)
            self.assertIsNone(self.send(desk, f"{DESK}/tables/2/call").json["queue"])
            snapshot = self.send(desk, DESK + "/snapshot", method="GET").json
        self.assertEqual(snapshot["tables"][1]["replacement_for"], reservation)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM waiting_queue WHERE queue_id=?", (ticket,)).fetchone()[0], "waiting")

    def test_legacy_window_adjoins_new_time_without_fabricating_actual_seating(self):
        guest = self.actor()
        original = self.send(guest, "/bookings", {"booking_date": DAY, "time_slot_id": 2, "party_size": 2, "table_id": 1,
                                                  "idempotency_key": "legacy-window"})
        self.assertEqual(original.status_code, 201)
        self.upgrade()
        self.upgrade()
        with clock(17):
            same = self.send(guest, GUEST + "/bookings", {"booking_date": DAY, "time_slot_id": 2, "party_size": 2, "table_id": 1,
                                                         "idempotency_key": "legacy-window"})
            self.assertEqual(same.json, original.json)
            self.assertEqual(self.reserve(guest, "17:45", key="overlaps-window").status_code, 409)
            self.assertEqual(self.reserve(self.actor(index=1), "19:00", key="after-window").status_code, 201)
            legacy = self.send(guest, GUEST + "/bookings", method="GET").json["bookings"][0]
        self.assertEqual((legacy["arrival_at"], legacy["arrival_label"], legacy["deadline_label"]), (None, "17:00-19:00", "19:00"))

    def test_estimate_does_not_clear_a_table_or_create_an_actual_time_for_legacy(self):
        self.upgrade()
        desk = self.actor(staff=True)
        with clock(17):
            visit = self.send(desk, DESK + "/walk-ins", {"table_id": 1, "party_size": 2}).json["visit"]["visit_id"]
        with clock(18, 10):
            snapshot = self.send(desk, DESK + "/snapshot", method="GET").json
            self.assertEqual(snapshot["tables"][0]["reason"], "occupied")
            blocked = self.send(desk, DESK + "/walk-ins", {"table_id": 1, "party_size": 2})
            self.assertEqual(blocked.json["error"], "TABLE_UNAVAILABLE")
            self.assertEqual(self.send(desk, f"/frontdesk/visits/{visit}/close").status_code, 200)
        with clock(18, 15):
            snapshot = self.send(desk, DESK + "/snapshot", method="GET").json
            self.assertEqual(snapshot["tables"][0]["reason"], "cleaning")
        from restaurant.services.allocation import timeline
        records = timeline(DAY, DAY)["visits"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "closed")
        self.assertIsNotNone(records[0]["seated_at"])

    def test_clearing_and_call_are_recovered_together_after_request_failure(self):
        self.upgrade()
        desk = self.actor(staff=True)
        with clock(17):
            visit = self.send(desk, DESK + "/walk-ins", {"party_size": 2, "table_id": 1}).json["visit"]
            ticket = self.issue_ticket(desk)
            self.assertEqual(self.send(desk, f"/frontdesk/visits/{visit['visit_id']}/close").status_code, 200)
        with clock(17, 10):
            with patch("restaurant.services.allocation._call_next", side_effect=RuntimeError("simulated interruption")):
                self.assertEqual(self.send(desk, DESK + "/snapshot", method="GET").status_code, 200)
                self.assertEqual(self.send(desk, "/operations/refresh").status_code, 200)
                self.assertEqual(self.send(desk, DESK + "/tables/1/clear", {
                    "visit_id": visit["visit_id"], "idempotency_key": "clear-once"}).status_code, 500)
            with get_connection() as db:
                self.assertIsNone(db.execute("SELECT clearance_processed_at FROM dining_sessions").fetchone()[0])
                self.assertEqual(db.execute("SELECT status FROM waiting_queue").fetchone()[0], "waiting")
            from app import create_app

            self.app = create_app()
            desk = self.actor(staff=True)
            for _ in range(2):
                self.assertEqual(self.send(desk, DESK + "/tables/1/clear", {
                    "visit_id": visit["visit_id"], "idempotency_key": "clear-once"}).status_code, 200)
                queue = self.send(desk, DESK + "/snapshot", method="GET").json["queue"]
                self.assertEqual([(row["queue_id"], row["status"]) for row in queue], [(ticket, "called")])
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM table_holds WHERE queue_id=?", (ticket,)).fetchone()[0], 1)

    def test_order_migration_recovers_missed_preorder_twice_without_touching_other_orders(self):
        import psycopg

        self.upgrade()
        with get_connection() as db:
            booking = db.execute("""INSERT INTO bookings(contact_name,phone_number,booking_date,time_slot,party_size,status)
                VALUES('Missed','13910000000',?,'19:00-20:30',2,'no_show') RETURNING booking_id""", (DAY,)).fetchone()[0]
            missed = db.execute("INSERT INTO orders(booking_id,order_type) VALUES(?,'preorder') RETURNING order_id",
                                (booking,)).fetchone()[0]
            other = db.execute("INSERT INTO orders DEFAULT VALUES RETURNING order_id").fetchone()[0]
            db.execute("INSERT INTO dishes(dish_name,price) VALUES('Fixture dish',19)")
            db.execute("INSERT INTO order_items(order_id,dish_id,quantity,unit_price) VALUES(?,1,1,19)", (missed,))
        contents = (postgres.DB_SQL / "migrations" / "003_order_consistency.sql").read_text(encoding="utf-8")
        with psycopg.connect(self.dsn, autocommit=True) as db:
            for _ in range(2):
                db.execute(contents)
        with get_connection() as db:
            states = {row["order_id"]: row["status"] for row in db.execute("SELECT order_id,status FROM orders")}
            self.assertEqual(states, {missed: "cancelled", other: "active"})
            self.assertEqual(db.execute("SELECT status FROM order_items WHERE order_id=?", (missed,)).fetchone()[0], "cancelled")
            self.assertEqual(db.execute("SELECT count(*) FROM reservation_schema_versions WHERE version=3").fetchone()[0], 1)

    def test_order_retry_and_stale_kitchen_card_share_the_same_database_state(self):
        self.upgrade()
        first_desk, second_desk = self.actor(staff=True), self.actor(staff=True)
        with get_connection() as db:
            db.execute("INSERT INTO dishes(dish_name,price) VALUES('Fixture dish',19)")
            db.execute("""INSERT INTO staff(name,role,phone,email,password_hash)
                          VALUES ('Kitchen','kitchen','13910000001','kitchen@example.test','unused')""")
        client = self.app.test_client()
        bind_test_session(client, staff_id=2)
        kitchen = client, csrf(client)
        with clock(17):
            visit = self.send(first_desk, DESK + "/walk-ins", {"party_size": 2, "table_id": 1}).json["visit"]
        items = {"items-0-dish_id": 1, "items-0-quantity": 1, "items-0-quoted_unit_cents": 1900}
        fields = {**items, "visit_id": visit["visit_id"], "idempotency_key": "desk-order-key"}
        barrier = Barrier(2)

        def submit(desk):
            barrier.wait(timeout=6)
            return self.send(desk, "/frontdesk/orders", fields)

        with ThreadPoolExecutor(max_workers=2) as workers:
            placed = list(workers.map(submit, (first_desk, second_desk)))
        self.assertEqual([result.status_code for result in placed], [201, 201])
        ids = {result.json["order"]["order_id"] for result in placed}
        self.assertEqual(len(ids), 1)
        order_id = ids.pop()
        queue = self.send(kitchen, "/kitchen/queue?status=active", method="GET").json["items"]
        self.assertEqual(len(queue), 1)
        line = queue[0]
        edit = f"/frontdesk/orders/{order_id}/edit"
        start = f"/kitchen/items/{line['order_item_id']}/start"
        stale_version = line["order_version"]
        self.assertEqual(self.send(first_desk, edit, {**items, "items-0-quantity": 2, "expected_version": stale_version}).status_code, 200)
        self.assertEqual(self.send(second_desk, edit, {**items, "expected_version": stale_version}).json["error"], "ORDER_CHANGED")
        self.assertEqual(self.send(kitchen, start, {"expected_version": stale_version}).json["error"], "ORDER_CHANGED")
        updated = self.send(kitchen, "/kitchen/queue?status=active", method="GET").json["items"][0]
        self.assertEqual(updated["quantity"], 2)
        version = updated["order_version"]
        self.assertEqual(self.send(kitchen, start, {"expected_version": version}).status_code, 200)
        self.assertEqual(self.send(kitchen, start, {"expected_version": version}).status_code, 409)
        self.assertEqual(self.send(first_desk, edit, {**items, "expected_version": version}).status_code, 409)

        new_order = self.send(first_desk, "/frontdesk/orders", {**fields, "idempotency_key": "another-order"}).json["order"]
        current = next(row for row in self.send(kitchen, "/kitchen/queue?status=active", method="GET").json["items"]
                       if row["order_id"] == new_order["order_id"])
        version = current["order_version"]
        gate = Barrier(2)

        def compete(actor, path, data):
            gate.wait(timeout=6)
            return self.send(actor, path, data)

        with ThreadPoolExecutor(max_workers=2) as workers:
            saved = workers.submit(compete, first_desk, f"/frontdesk/orders/{new_order['order_id']}/edit",
                                   {**items, "items-0-quantity": 2, "expected_version": version})
            started = workers.submit(compete, kitchen, f"/kitchen/items/{current['order_item_id']}/start",
                                     {"expected_version": version})
            pair = saved.result(timeout=10).status_code, started.result(timeout=10).status_code
        self.assertIn(pair, ((200, 409), (409, 200)))

    def test_database_rejects_overlapping_holds_and_double_seating_without_api(self):
        from psycopg.errors import ExclusionViolation, UniqueViolation

        self.upgrade()
        with clock(18):
            self.assertEqual(self.reserve(self.actor()).status_code, 201)
        desk = self.actor(staff=True)
        with clock(17):
            self.assertEqual(self.send(desk, DESK + "/walk-ins", {"table_id": 2, "party_size": 2}).status_code, 201)
        with self.assertRaises(ExclusionViolation) as overlap, get_connection() as db:
            db.execute("""INSERT INTO waiting_queue(party_size,queue_position) VALUES(2,1)""")
            db.execute("""INSERT INTO table_holds(table_id,queue_id,kind,protected_during,expires_at)
                SELECT 1,queue_id,'call',tstzrange('2048-02-20 19:40:00+08','2048-02-20 20:30:00+08','[)'),
                    '2048-02-20 19:41:00+08'::timestamptz FROM waiting_queue""")
        self.assertEqual(overlap.exception.diag.constraint_name, "no_overlapping_table_holds")
        with self.assertRaises(UniqueViolation) as double_seat, get_connection() as db:
            db.execute("INSERT INTO dining_sessions(table_id,party_size,status) VALUES(2,2,'seated')")
        self.assertEqual(double_seat.exception.diag.constraint_name, "uq_dining_active_table")
