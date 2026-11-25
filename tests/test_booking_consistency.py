from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from backend_test_helpers import RestaurantTestCase, write
from restaurant.business_time import current_table_window
from restaurant.db.database import get_connection


class BookingConsistencyTests(RestaurantTestCase):
    def setUp(self):
        super().setUp()
        self.guest = self.signed_in("13900000001")
        self.staff = self.signed_in("frontdesk@shuangfen.local")

    def booking(self, **overrides):
        return {"booking_date": current_table_window()[0], "time_slot_id": 3,
                "party_size": 1, "table_id": 6, **overrides}

    def test_ordinary_check_in_uses_latest_table_and_legacy_override_is_rejected(self):
        created = write(self.guest, "/bookings", self.booking()).json["booking"]
        booking_id = created["booking_id"]
        modified = write(self.guest, f"/bookings/{booking_id}/edit",
                         self.booking(table_id=1, expected_version=1))
        self.assertEqual(modified.status_code, 200)
        path = f"/frontdesk/bookings/{booking_id}/check-in"
        self.assertEqual(write(self.staff, path, {"table_id": 6}).status_code, 409)
        arrival = write(self.staff, path)
        self.assertEqual(arrival.status_code, 201)
        self.assertEqual(arrival.json["visit"]["table_id"], 1)
        with get_connection() as db:
            visits = db.execute("SELECT table_id FROM dining_sessions WHERE booking_id=?", (booking_id,)).fetchall()
        self.assertEqual([row[0] for row in visits], [1])

    def test_explicit_check_in_table_change_requires_current_version(self):
        date = current_table_window()[0]
        created = write(self.guest, "/bookings", self.booking()).json["booking"]
        booking_id = created["booking_id"]
        path = f"/frontdesk/bookings/{booking_id}/check-in"
        edit_path = f"/bookings/{booking_id}/edit"
        staff_edit = f"/frontdesk/bookings/{booking_id}/edit"
        self.assertEqual(self.staff.get(staff_edit).json["booking"]["version"], 1)
        self.assertEqual(self.guest.get(edit_path).json["booking"]["version"], 1)
        moved = write(self.guest, edit_path, self.booking(table_id=1, expected_version=1))
        self.assertEqual(moved.json["booking"]["version"], 2)
        stale = write(self.staff, path, {"change_table": "true", "table_id": 6, "expected_version": 1})
        self.assertEqual((stale.status_code, stale.json["error"]), (409, "BOOKING_CHANGED"))
        with get_connection() as db:
            self.assertIsNone(db.execute("SELECT visit_id FROM dining_sessions WHERE booking_id=?", (booking_id,)).fetchone())
        with patch("restaurant.services.dining_service.current_table_window", return_value=(date, None)):
            arrival = write(self.staff, path, {"change_table": "true", "table_id": 6, "expected_version": 2})
        self.assertEqual(arrival.status_code, 201)
        self.assertEqual(arrival.json["visit"]["table_id"], 6)
        self.assertEqual(self.staff.get(staff_edit).json["booking"]["version"], 3)

    def test_customer_and_frontdesk_cannot_overwrite_each_others_edits(self):
        created = write(self.guest, "/bookings", self.booking()).json["booking"]
        guest_path = f"/bookings/{created['booking_id']}/edit"
        desk_path = "/frontdesk" + guest_path
        first = write(self.staff, desk_path, self.booking(table_id=1, expected_version=1))
        self.assertEqual(first.status_code, 200)
        stale = write(self.guest, guest_path, self.booking(table_id=6, expected_version=1))
        self.assertEqual((stale.status_code, stale.json["error"]), (409, "BOOKING_CHANGED"))
        latest = self.guest.get(guest_path).json["booking"]
        self.assertEqual((latest["table_id"], latest["version"]), (1, 2))
        saved = write(self.guest, guest_path, self.booking(table_id=6, expected_version=latest["version"]))
        self.assertEqual(saved.json["booking"]["version"], 3)
        stale = write(self.staff, desk_path, self.booking(table_id=1, expected_version=2))
        self.assertEqual((stale.status_code, stale.json["error"]), (409, "BOOKING_CHANGED"))

    def test_lost_response_is_recoverable_after_edit_and_rejects_different_payload(self):
        fields = self.booking(idempotency_key="recover-fixture")
        first = write(self.guest, "/bookings", fields)
        self.assertEqual(first.status_code, 201)
        booking_id = first.json["booking"]["booking_id"]
        invalid = write(self.guest, "/bookings", {**fields, "table_id": 1})
        self.assertEqual((invalid.status_code, invalid.json["error"]), (409, "IDEMPOTENCY_KEY_REUSED"))
        replay = write(self.guest, "/bookings", fields)
        self.assertEqual(replay.json, first.json)
        path = f"/bookings/{booking_id}/edit"
        moved = write(self.guest, path, self.booking(table_id=1, expected_version=1))
        self.assertEqual(moved.status_code, 200)
        self.assertEqual(write(self.guest, "/bookings", fields).json, first.json)
        self.assertEqual(self.guest.get(path).json["booking"]["table_id"], 1)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM booking_create_requests WHERE request_key=?",
                                        ("recover-fixture",)).fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM bookings WHERE booking_date=? AND time_slot=? AND customer_phone=?",
                                        (fields["booking_date"], "19:00-21:00", "13900000001")).fetchone()[0], 1)

    def test_restaurant_date_at_beijing_midnight_applies_to_both_roles(self):
        just_before = current_table_window(datetime(2040, 1, 1, 15, 59, 59, tzinfo=timezone.utc))
        just_after = current_table_window(datetime(2040, 1, 1, 16, tzinfo=timezone.utc))
        self.assertEqual((just_before[0], just_after[0]), ("2040-01-01", "2040-01-02"))
        previous_day, day = just_before[0], just_after[0]
        tomorrow = (datetime.fromisoformat(day) + timedelta(days=1)).date().isoformat()
        desk_fields = {"contact_name": "Date fixture", "phone_number": "13900000002"}
        with patch("restaurant.services.booking_service.current_table_window", return_value=just_before):
            previous = write(self.guest, "/bookings", self.booking(booking_date=previous_day)).json["booking"]
        with (
            patch("restaurant.services.booking_service.current_table_window", return_value=just_after),
            patch("restaurant.services.dining_service.current_table_window", return_value=just_after),
        ):
            for client, prefix, extra in ((self.guest, "", {}), (self.staff, "/frontdesk", desk_fields)):
                with self.subTest(prefix=prefix):
                    rejected = write(client, prefix + "/bookings", self.booking(booking_date=previous_day, **extra))
                    self.assertEqual((rejected.status_code, rejected.json["error"]), (400, "BOOKING_DATE_IN_PAST"))
            present = write(self.guest, "/bookings", self.booking(booking_date=day)).json["booking"]
            future = write(self.staff, "/frontdesk/bookings",
                           self.booking(booking_date=tomorrow, **desk_fields)).json["booking"]
            present_id = present["booking_id"]
            for client, prefix in ((self.guest, ""), (self.staff, "/frontdesk")):
                rejected = write(client, f"{prefix}/bookings/{present_id}/edit",
                                 self.booking(booking_date=previous_day, expected_version=1))
                self.assertEqual((rejected.status_code, rejected.json["error"]), (400, "BOOKING_DATE_IN_PAST"))
            for other in (previous, future):
                rejected = write(self.staff, f"/frontdesk/bookings/{other['booking_id']}/check-in")
                self.assertEqual((rejected.status_code, rejected.json["error"]), (409, "CHECK_IN_DATE_MISMATCH"))
            self.assertEqual(write(self.staff, f"/frontdesk/bookings/{present_id}/check-in").status_code, 201)
