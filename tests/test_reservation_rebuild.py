from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from unittest.mock import patch
import unittest

import test_postgres_booking_consistency as postgres
from restaurant.db.database import get_connection


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
        ticket = self.send(desk, DESK + "/tickets", {"party_size": count}).json["queue"]["queue_id"]
        self.assertEqual(self.send(desk, f"{DESK}/tables/{table}/call").json["queue"]["queue_id"], ticket)
        return ticket

    def upgrade(self):
        import psycopg

        migration = postgres.DB_SQL / "migrations" / "002_reservation_allocation.sql"
        with psycopg.connect(self.dsn, autocommit=True) as db:
            db.execute(migration.read_text(encoding="utf-8"))

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
        from restaurant.services.queue_manager import QueueManager
        self.assertEqual(QueueManager.enqueue_due_preorders(DAY + "T18:59:00+08:00"), 0)
        self.assertEqual(QueueManager.enqueue_due_preorders(DAY + "T19:00:00+08:00"), 1)
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
                sweep = pool.submit(request, self.actor(staff=True), DESK + "/snapshot", "GET")
                self.assertEqual(arrive.result(timeout=10).status_code, 200)
                self.assertEqual(sweep.result(timeout=10).status_code, 200)
        with clock(19, 10, 1):
            late = self.send(self.actor(staff=True), f"{DESK}/bookings/{ids[1]}/arrive")
            self.assertEqual(late.status_code, 409)
        with get_connection() as db:
            self.assertEqual([row["status"] for row in db.execute("SELECT status FROM bookings ORDER BY booking_id")],
                             ["booked", "no_show"])
            self.assertEqual(db.execute("SELECT booking_id FROM table_holds").fetchone()[0], ids[0])

    def test_waitlist_wins_released_table_before_online_conflict_is_returned(self):
        self.upgrade()
        guest, desk = self.actor(), self.actor(staff=True)
        with clock(18):
            prior = self.reserve(guest).json["booking"]["booking_id"]
        with clock(18, 50):
            protected = self.send(desk, DESK + "/walk-ins", {"table_id": 1, "party_size": 2})
            self.assertEqual(protected.json["error"], "TABLE_UNAVAILABLE")
            ticket = self.send(desk, DESK + "/tickets", {"party_size": 2}).json["queue"]["queue_id"]
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
            second = self.send(desk, DESK + "/tickets", {"party_size": 2}).json["queue"]["queue_id"]
        with clock(17, 1, 1):
            denied = self.send(desk, f"{DESK}/tickets/{first}/seat", {"table_id": 1})
            self.assertEqual((denied.status_code, denied.json["error"]), (409, "WAITLIST_CHANGED"))
            self.assertEqual(self.send(desk, f"{DESK}/tickets/{second}/pass").status_code, 200)
        with get_connection() as db:
            self.assertEqual([row[0] for row in db.execute("SELECT status FROM waiting_queue ORDER BY queue_id")],
                             ["expired", "passed"])
            self.assertEqual(db.execute("SELECT count(*) FROM dining_sessions").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM table_holds").fetchone()[0], 0)
        with clock(17, 3):
            third = self.call_party(desk)
        with clock(17, 4):
            self.assertEqual(self.send(desk, f"{DESK}/tickets/{third}/seat", {"table_id": 1}).status_code, 201)

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
                self.assertEqual(sum(response.status_code == 409 and response.json["error"] == "TABLE_UNAVAILABLE"
                                     for response in responses), count-1)
                self.assertEqual([response.status_code for response in responses if response.status_code >= 500], [])
            self.assertEqual(self.reserve(actors[0], "19:45", 1, "overlapping").json["error"], "TABLE_UNAVAILABLE")
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
            seat = pool.submit(submit, desk1, "/seat", {"table_id": 1})
            passed = pool.submit(submit, desk2, "/pass", {})
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
        with clock(18, 50):
            reported = self.send(desk, f"{DESK}/bookings/{reservation}/arrive")
            self.assertEqual(reported.json["booking"]["phase"], "waiting_to_seat")
            ticket = self.send(desk, DESK + "/tickets", {"party_size": 2}).json["queue"]["queue_id"]
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
            self.assertEqual(self.reserve(guest, "19:00", key="after-window").status_code, 201)
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
