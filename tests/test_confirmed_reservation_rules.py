"""Business-rule regressions against disposable PostgreSQL schemas, never production."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from unittest.mock import patch

import test_postgres_booking_consistency as postgres
import test_reservation_rebuild as rebuild
from test_reservation_rebuild import clock, DAY, DESK, GUEST
from restaurant.db.database import get_connection
from restaurant.services import allocation


@unittest.skipUnless(postgres.TEST_DSN, "requires the disposable PostgreSQL fixture")
class ConfirmedReservationRulesTests(unittest.TestCase):
    phone = staticmethod(postgres.PostgresBookingConsistencyTests.phone)
    actor = postgres.PostgresBookingConsistencyTests.actor
    send = staticmethod(postgres.PostgresBookingConsistencyTests.send)
    reserve = rebuild.ReservationRebuildTests.reserve
    issue_ticket = rebuild.ReservationRebuildTests.issue_ticket

    def setUp(self):
        postgres.PostgresBookingConsistencyTests.setUp(self)
        rebuild.ReservationRebuildTests.upgrade(self)

    def capacities(self):
        with get_connection() as db:
            db.execute("UPDATE dining_tables SET capacity=CASE table_id WHEN 1 THEN 2 WHEN 2 THEN 4 ELSE 8 END")

    def arrived(self, guest, desk, *, table=1, size=2, arrival="19:00"):
        with clock(18):
            response = self.reserve(guest, table=table, party_size=size, arrival=arrival)
            self.assertEqual(response.status_code, 201, response.json)
            booking_id = response.json["booking"]["booking_id"]
        with clock(19):
            response = self.send(desk, f"{DESK}/bookings/{booking_id}/arrive")
            self.assertEqual(response.status_code, 200, response.json)
            return response.json["booking"]

    def preorder_fixture(self, booking_id):
        with get_connection() as db:
            dish = db.execute("INSERT INTO dishes(dish_name,price) VALUES('Saved-price dish',29) RETURNING dish_id").fetchone()[0]
            order = db.execute("""INSERT INTO orders(booking_id,customer_phone,table_id,order_type)
                VALUES(?,?,1,'preorder') RETURNING order_id""", (booking_id, self.phone(0))).fetchone()[0]
            line = db.execute("""INSERT INTO order_items(order_id,dish_id,quantity,unit_price,total_price,estimated_ready_at)
                VALUES(?,?,1,19,19,?) RETURNING order_item_id""", (order, dish, DAY + " 11:00:00")).fetchone()[0]
            return order, line

    def test_online_table_band_is_based_on_existing_capacity_not_current_availability(self):
        self.capacities()
        guest, desk = self.actor(), self.actor(staff=True)
        with clock(18):
            data = self.send(guest, GUEST + "/available?date=" + DAY + "&arrival_time=19:00&party_size=3", method="GET").json
            self.assertEqual([row["capacity"] for row in data["tables"]], [4])
            refused = self.reserve(guest, table=3, party_size=3)
            self.assertEqual((refused.status_code, refused.json["error"]), (409, "TABLE_SIZE_POLICY"))
            self.assertEqual(self.send(desk, DESK + "/tables/2/disabled", {"disabled": "true"}).status_code, 200)
            data = self.send(guest, GUEST + "/available?date=" + DAY + "&arrival_time=19:00&party_size=3", method="GET").json
            self.assertEqual(data["tables"], [])
            staff = self.send(desk, DESK + "/bookings", {"booking_date": DAY, "arrival_time": "19:00", "party_size": 3,
                "table_id": 3, "contact_name": "Guest", "phone_number": self.phone(0), "idempotency_key": "staff-exception"})
            self.assertEqual(staff.status_code, 201, staff.json)
        with get_connection() as db:
            self.assertIsNone(db.execute("SELECT customer_phone FROM bookings").fetchone()[0])

    def test_only_one_active_reservation_even_for_different_dates_and_concurrent_tabs(self):
        actors = self.actor(), self.actor()
        barrier = Barrier(2)
        def book(index):
            barrier.wait(timeout=5)
            return self.reserve(actors[index], table=index + 1, key="different-key-" + str(index))
        with clock(18), ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(book, [0, 1]))
        self.assertEqual(sorted(row.status_code for row in responses), [201, 409])
        self.assertEqual(next(row.json["error"] for row in responses if row.status_code == 409), "ACTIVE_RESERVATION_EXISTS")
        with clock(18):
            later = self.reserve(actors[0], table=3, key="tomorrow", booking_date="2048-02-21")
            self.assertEqual(later.json["error"], "ACTIVE_RESERVATION_EXISTS")

    def test_linking_checks_arrival_deadline_even_before_the_worker_runs(self):
        with clock(18):
            bid = self.reserve(self.actor()).json["booking"]["booking_id"]
        with clock(19, 11), get_connection() as db:
            with self.assertRaises(allocation.ServiceError) as failure:
                allocation.assert_can_link_booking(db, bid, self.phone(1))
            self.assertEqual(failure.exception.code, "LINK_UNAVAILABLE")
            allocation.assert_can_link_booking(db, None, self.phone(0))
            self.assertEqual(db.execute("SELECT status FROM bookings WHERE booking_id=?", (bid,)).fetchone()[0], "booked")

    def test_staff_retry_cannot_change_account_link_consent(self):
        desk = self.actor(staff=True)
        fields = {"booking_date": DAY, "arrival_time": "19:00", "party_size": 2,
                  "table_id": 1, "contact_name": "Guest", "phone_number": self.phone(0), "idempotency_key": "consent-retry"}
        with clock(18):
            self.assertEqual(self.send(desk, DESK + "/bookings", fields).status_code, 201)
            changed = self.send(desk, DESK + "/bookings", dict(fields, request_account_link="true"))
            self.assertEqual((changed.status_code, changed.json["error"]), (409, "IDEMPOTENCY_KEY_REUSED"))

    def test_stale_cancellation_preserves_new_reservation_and_preorder(self):
        guest, desk = self.actor(), self.actor(staff=True)
        with clock(18):
            bid = self.reserve(guest).json["booking"]["booking_id"]
            order, line = self.preorder_fixture(bid)
            edited = self.send(desk, f"{DESK}/bookings/{bid}/edit", {"booking_date": DAY,
                "arrival_time": "19:30", "party_size": 2, "table_id": 2, "expected_version": 1})
            self.assertEqual(edited.status_code, 200)
            stale = self.send(guest, f"{GUEST}/bookings/{bid}/cancel", {"expected_version": 1})
            self.assertEqual((stale.status_code, stale.json["error"]), (409, "BOOKING_CHANGED"))
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM bookings WHERE booking_id=?", (bid,)).fetchone()[0], "booked")
            self.assertEqual(db.execute("SELECT status FROM orders WHERE order_id=?", (order,)).fetchone()[0], "active")

    def test_party_correction_failure_preserves_original_then_transfer_keeps_price_and_retries_once(self):
        self.capacities()
        guest, desk = self.actor(), self.actor(staff=True)
        booking = self.arrived(guest, desk)
        bid = booking["booking_id"]
        order, line = self.preorder_fixture(bid)
        with clock(19):
            earlier = self.issue_ticket(desk)
            failed = self.send(desk, f"{DESK}/bookings/{bid}/party-size", {"party_size": 3, "expected_version": booking["version"]})
            self.assertEqual(failed.json["error"], "PARTY_CHANGE_REQUIRES_WAITLIST")
            with get_connection() as db:
                self.assertEqual(db.execute("SELECT party_size FROM bookings WHERE booking_id=?", (bid,)).fetchone()[0], 2)
            fields = {"party_size": 3, "expected_version": booking["version"], "idempotency_key": "move-once"}
            first = self.send(desk, f"{DESK}/bookings/{bid}/transfer-to-waitlist", fields)
            second = self.send(desk, f"{DESK}/bookings/{bid}/transfer-to-waitlist", fields)
            self.assertEqual(first.status_code, 201, first.json)
            self.assertEqual(first.json, second.json)
            ticket_id = first.json["transfer"]["queue_id"]
            self.assertGreater(ticket_id, earlier)
            denied = self.reserve(guest, table=2, party_size=3, key="other-reservation", booking_date="2048-02-21")
            self.assertEqual(denied.json["error"], "ACTIVE_RESERVATION_EXISTS")
            self.assertEqual(self.send(guest, GUEST + "/bookings", method="GET").json["queue"]["queue_id"], ticket_id)
        with get_connection() as db:
            header = db.execute("SELECT queue_id,table_id,visit_id,status FROM orders WHERE order_id=?", (order,)).fetchone()
            self.assertEqual(tuple(header.values()), (ticket_id, None, None, "active"))
            self.assertEqual(db.execute("SELECT unit_price,status FROM order_items WHERE order_item_id=?", (line,)).fetchone()[0], 19)
            self.assertEqual(db.execute("SELECT count(*) FROM kitchen_queue WHERE order_id=?", (order,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM waiting_queue WHERE source_booking_id=?", (bid,)).fetchone()[0], 1)

    def test_transfer_expiry_cancels_preorders_but_preserves_arrived_reservation_waiting(self):
        guest, desk, other = self.actor(), self.actor(staff=True), self.actor(index=1)
        booking = self.arrived(guest, desk)
        other_booking = self.arrived(other, desk, table=2)
        order, line = self.preorder_fixture(booking["booking_id"])
        with clock(19):
            response = self.send(desk, f"{DESK}/bookings/{booking['booking_id']}/transfer-to-waitlist",
                {"party_size": 3, "expected_version": booking["version"], "idempotency_key": "transfer"})
            self.assertEqual(response.status_code, 201, response.json)
        with clock(21):
            self.assertEqual(self.send(desk, "/operations/refresh").status_code, 200)
            self.assertEqual(self.send(desk, "/operations/refresh").status_code, 200)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM waiting_queue WHERE source_booking_id=?", (booking["booking_id"],)).fetchone()[0], "service_ended")
            self.assertEqual(db.execute("SELECT status FROM orders WHERE order_id=?", (order,)).fetchone()[0], "cancelled")
            self.assertEqual(db.execute("SELECT status FROM order_items WHERE order_item_id=?", (line,)).fetchone()[0], "cancelled")
            self.assertEqual(db.execute("SELECT status FROM bookings WHERE booking_id=?", (other_booking["booking_id"],)).fetchone()[0], "booked")

    def test_waitlist_stops_admission_when_no_meal_can_finish_and_stale_cancel_is_rejected(self):
        desk = self.actor(staff=True)
        with clock(20, 50):
            refused = self.send(desk, DESK + "/tickets", {"party_size": 2, "idempotency_key": "late"})
            self.assertEqual((refused.status_code, refused.json["error"]), (409, "SERVICE_CLOSED"))
        with clock(19):
            ticket = self.issue_ticket(desk)
            self.send(desk, DESK + "/tables/1/call")
            stale = self.send(desk, f"{DESK}/tickets/{ticket}/cancel", {"expected_version": 1})
            self.assertEqual((stale.status_code, stale.json["error"]), (409, "WAITLIST_CHANGED"))

    def test_timer_never_releases_table_before_manual_clearance(self):
        desk = self.actor(staff=True)
        with clock(17):
            visit = self.send(desk, DESK + "/walk-ins", {"party_size": 2, "table_id": 1}).json["visit"]
            self.assertEqual(self.send(desk, f"/frontdesk/visits/{visit['visit_id']}/close").status_code, 200)
            ticket = self.issue_ticket(desk)
        with clock(18):
            self.send(desk, "/operations/refresh")
            snapshot = self.send(desk, DESK + "/snapshot", method="GET").json
            table = snapshot["tables"][0]
            self.assertEqual(table["reason"], "cleaning")
            self.assertTrue(table["cleaning_overdue"])
            self.assertEqual(snapshot["queue"][0]["status"], "waiting")
            fields = {"visit_id": visit["visit_id"], "idempotency_key": "cleaned-once"}
            first = self.send(desk, DESK + "/tables/1/clear", fields)
            again = self.send(desk, DESK + "/tables/1/clear", fields)
            self.assertEqual(first.status_code, 200, first.json)
            self.assertEqual(first.json, again.json)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM table_holds WHERE queue_id=?", (ticket,)).fetchone()[0], 1)
            self.assertIsNotNone(db.execute("SELECT cleared_by_actor FROM dining_sessions").fetchone()[0])

    def test_early_arrival_does_not_claim_replacement_priority_before_reserved_time(self):
        guest, desk = self.actor(), self.actor(staff=True)
        with clock(17):
            self.send(desk, DESK + "/walk-ins", {"party_size": 2, "table_id": 1})
            bid = self.reserve(guest).json["booking"]["booking_id"]
        with clock(18, 50):
            self.send(desk, f"{DESK}/bookings/{bid}/arrive")
            ticket = self.issue_ticket(desk)
            called = self.send(desk, DESK + "/tables/2/call")
            self.assertEqual(called.json["queue"]["queue_id"], ticket)

    def test_party_change_with_agreed_table_records_actor_and_original_table(self):
        self.capacities()
        guest, desk = self.actor(), self.actor(staff=True)
        booking = self.arrived(guest, desk)
        with clock(19):
            fields = {"party_size": 3, "table_id": 2, "expected_version": booking["version"]}
            denied = self.send(desk, f"{DESK}/bookings/{booking['booking_id']}/party-size", fields)
            self.assertEqual(denied.status_code, 400)
            changed = self.send(desk, f"{DESK}/bookings/{booking['booking_id']}/party-size", {**fields, "customer_agreed": "true"})
            self.assertEqual(changed.status_code, 200, changed.json)
            self.assertEqual((changed.json["booking"]["party_size"], changed.json["booking"]["table_id"]), (3, 2))
        with get_connection() as db:
            audit = db.execute("SELECT from_table_id,to_table_id,actor FROM booking_table_changes").fetchone()
            self.assertEqual((audit[0], audit[1]), (1, 2))
            self.assertTrue(audit[2].startswith("frontdesk:"))

    def test_transferred_preorder_seats_once_and_keeps_original_unit_price(self):
        self.capacities()
        guest, desk = self.actor(), self.actor(staff=True)
        booking = self.arrived(guest, desk)
        order, line = self.preorder_fixture(booking["booking_id"])
        with clock(19):
            moved = self.send(desk, f"{DESK}/bookings/{booking['booking_id']}/transfer-to-waitlist",
                {"party_size": 3, "expected_version": booking["version"], "idempotency_key": "transfer"})
            ticket = moved.json["transfer"]["queue_id"]
            call = self.send(desk, DESK + "/tables/2/call")
            self.assertEqual(call.json["queue"]["queue_id"], ticket)
            seated = self.send(desk, f"{DESK}/tickets/{ticket}/seat", {"table_id": 2, "expected_version": 2})
            self.assertEqual(seated.status_code, 201, seated.json)
            repeat = self.send(desk, f"{DESK}/tickets/{ticket}/seat", {"table_id": 2, "expected_version": 2})
            self.assertEqual(repeat.status_code, 409)
        with get_connection() as db:
            row = db.execute("SELECT visit_id,table_id,status FROM orders WHERE order_id=?", (order,)).fetchone()
            self.assertEqual((row["visit_id"], row["table_id"], row["status"]), (seated.json["visit"]["visit_id"], 2, "active"))
            self.assertEqual(db.execute("SELECT unit_price FROM order_items WHERE order_item_id=?", (line,)).fetchone()[0], 19)
            self.assertEqual(db.execute("SELECT count(*) FROM dining_sessions WHERE queue_id=?", (ticket,)).fetchone()[0], 1)

    def test_due_reservation_priority_uses_reserved_time_before_checkin_time(self):
        desk, early, late = self.actor(staff=True), self.actor(), self.actor(index=1)
        with clock(17):
            for table in (1, 2):
                self.send(desk, DESK + "/walk-ins", {"table_id": table, "party_size": 2})
            first = self.reserve(early, table=1, arrival="19:00").json["booking"]["booking_id"]
            second = self.reserve(late, table=2, arrival="19:15").json["booking"]["booking_id"]
        with clock(19):
            self.send(desk, f"{DESK}/bookings/{second}/arrive")
        with clock(19, 5):
            self.send(desk, f"{DESK}/bookings/{first}/arrive")
        with clock(19, 15):
            snapshot = self.send(desk, DESK + "/snapshot", method="GET").json
            replacement = next(table for table in snapshot["tables"] if table["table_id"] == 3)
            self.assertEqual(replacement["replacement_for"], first)
            late_record = next(row for row in snapshot["bookings"] if row["booking_id"] == second)
            rejected = self.send(desk, f"{DESK}/bookings/{second}/offer",
                {"table_id": 3, "expected_version": late_record["version"]})
            self.assertEqual((rejected.status_code, rejected.json["error"]), (409, "TABLE_UNAVAILABLE"))
