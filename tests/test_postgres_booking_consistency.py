"""Opt-in integration tests against a disposable, loopback PostgreSQL database."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from threading import Barrier, Event
from time import monotonic, sleep
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.errors import UniqueViolation

from backend_test_helpers import csrf
from restaurant.db.database import begin_write, get_connection
from restaurant.services.common import ServiceError
from restaurant.services.dining_service import require_seatable_table
from restaurant.services.queue_manager import QueueManager


TEST_DSN = os.environ.get("USURPERS_TEST_POSTGRES_URL")
DB_SQL = Path(__file__).resolve().parents[1] / "restaurant" / "db"


@unittest.skipUnless(TEST_DSN, "requires a disposable PostgreSQL database on loopback")
class PostgresBookingConsistencyTests(unittest.TestCase):
    def setUp(self):
        config = conninfo_to_dict(TEST_DSN)
        if (
            config.get("host") not in {"127.0.0.1", "::1"}
            or config.get("hostaddr", config["host"]) != config["host"]
            or config.get("dbname") != "usurpers_test"
        ):
            self.fail("Use a disposable database named usurpers_test on loopback.")
        self.schema = f"booking_test_{uuid4().hex}"
        self.probe = self.enterContext(psycopg.connect(TEST_DSN, autocommit=True))
        self.probe.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.probe.execute, sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))
        self.options = "-csearch_path=" + self.schema
        self.dsn = make_conninfo(TEST_DSN, options=self.options, application_name=self.schema)
        self.enterContext(patch.dict(os.environ, {"DATABASE_URL": self.dsn, "USURPERS_HTTPS": "0"}))
        with psycopg.connect(self.dsn) as db:
            db.execute((DB_SQL / "postgres.sql").read_text(encoding="utf-8"))
            db.execute("INSERT INTO dining_tables(capacity) VALUES (6), (6), (6)")
            with db.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO customers(customer_phone,name,password_hash) VALUES (%s,'Fixture','unused')",
                    [(self.phone(index),) for index in range(21)],
                )
            db.execute("""INSERT INTO staff(name,role,phone,email,password_hash)
                VALUES ('Desk','frontdesk','13910000000','desk@example.test','unused')""")
        from app import create_app

        self.app = create_app()

    @staticmethod
    def phone(index):
        return f"139200{index:05}"

    def actor(self, *, index=0, staff=False):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account"] = {"staff_id": 1} if staff else {"customer_phone": self.phone(index)}
        return client, csrf(client)

    @staticmethod
    def send(actor, path, fields=None, *, method="POST"):
        client, token = actor
        return client.open(path, method=method, data={**(fields or {}), "csrf_token": token})

    def booking(self, **overrides):
        return {"booking_date": "2048-02-20", "time_slot_id": 1, "party_size": 2, "table_id": 1, **overrides}

    def wait_for_blocked(self, blocker_pid, request=None):
        deadline = monotonic() + 4
        while monotonic() < deadline:
            blocked = self.probe.execute(
                "SELECT 1 FROM pg_stat_activity WHERE application_name=%s AND %s=ANY(pg_blocking_pids(pid))",
                (self.schema, blocker_pid),
            ).fetchone()
            if blocked:
                return
            if request is not None and request.done():
                self.fail(f"The request completed without waiting for transaction {blocker_pid}.")
            sleep(0.01)
        self.fail(f"No request waited for transaction {blocker_pid}.")

    def test_additive_migration_keeps_legacy_rows_and_can_rerun(self):
        with psycopg.connect(self.dsn, autocommit=True) as db:
            db.execute("DROP TABLE booking_create_requests")
            db.execute("ALTER TABLE bookings DROP COLUMN version")
            legacy = db.execute("""INSERT INTO bookings(contact_name,phone_number,booking_date,time_slot,party_size,table_id)
                VALUES ('Legacy','13920000000','2048-02-20','11:00-14:00',2,1) RETURNING booking_id""").fetchone()[0]
            migration = (DB_SQL / "migrations" / "001_booking_consistency.sql").read_text(encoding="utf-8")
            db.execute(migration)
            db.execute(migration)
            self.assertEqual(db.execute("SELECT contact_name,version FROM bookings WHERE booking_id=%s", (legacy,)).fetchone(),
                             ("Legacy", 1))
            self.assertEqual(db.execute("SELECT count(*) FROM booking_create_requests").fetchone()[0], 0)

    def test_concurrent_booking_edits_and_same_key_creation(self):
        guest, desk = self.actor(), self.actor(staff=True)
        fields = self.booking(idempotency_key="one-attempt")
        start = Barrier(2, timeout=10)

        def submit(actor, path, payload):
            start.wait()
            return self.send(actor, path, payload)

        with ThreadPoolExecutor(max_workers=2) as workers:
            retry = self.actor()
            requests = [workers.submit(submit, actor, "/bookings", fields) for actor in (guest, retry)]
            first, second = [request.result(timeout=10) for request in requests]
            self.assertEqual([first.status_code, second.status_code], [201, 201])
            self.assertEqual(first.json, second.json)
            booking_id = first.json["booking"]["booking_id"]
            path = f"/bookings/{booking_id}/edit"
            edits = [
                workers.submit(submit, guest, path, self.booking(table_id=2, expected_version=1)),
                workers.submit(submit, desk, "/frontdesk" + path, self.booking(table_id=3, expected_version=1)),
            ]
            results = [edit.result(timeout=10) for edit in edits]
        self.assertCountEqual([response.status_code for response in results], [200, 409])
        winner = next(result.json["booking"] for result in results if result.status_code == 200)
        loser = next(result.json for result in results if result.status_code == 409)
        self.assertEqual(loser["error"], "BOOKING_CHANGED")
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM bookings").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM booking_create_requests").fetchone()[0], 1)
            row = db.execute("SELECT table_id,version FROM bookings WHERE booking_id=?", (booking_id,)).fetchone()
            self.assertEqual((row["table_id"], row["version"]), (winner["table_id"], 2))

    def test_same_table_has_exactly_one_winner_at_10_and_20_requests(self):
        for count in (10, 20):
            with self.subTest(count=count):
                start = Barrier(count, timeout=10)
                actors = [self.actor(index=index) for index in range(count)]
                fields = self.booking(booking_date=f"2048-02-{count}")

                def submit(index):
                    start.wait()
                    return self.send(actors[index], "/bookings", {**fields, "idempotency_key": f"race-{count}-{index}"})

                with ThreadPoolExecutor(max_workers=count) as workers:
                    responses = list(workers.map(submit, range(count), timeout=25))
                accepted = sum(response.status_code == 201 for response in responses)
                conflicts = sum(response.status_code == 409 and response.json["error"] == "TABLE_UNAVAILABLE"
                                for response in responses)
                infrastructure = [response.status_code for response in responses if response.status_code >= 500]
                self.assertEqual((accepted, conflicts, infrastructure), (1, count - 1, []))
                with get_connection() as db:
                    self.assertEqual(db.execute("""SELECT count(*) FROM bookings
                        WHERE booking_date=? AND time_slot='11:00-14:00' AND table_id=1 AND status='booked'""",
                        (fields["booking_date"],)).fetchone()[0], 1)
                with self.assertRaises(UniqueViolation) as error, get_connection() as db:
                    db.execute("""INSERT INTO bookings(contact_name,phone_number,booking_date,time_slot,party_size,table_id)
                        VALUES('Duplicate','13920000000',?,'11:00-14:00',2,1)""", (fields["booking_date"],))
                self.assertEqual(error.exception.diag.constraint_name, "uq_bookings_table_slot")

    def test_global_lock_blocks_other_tables_and_timeout_is_not_a_table_conflict(self):
        guest = self.actor()
        with ThreadPoolExecutor(max_workers=1) as workers:
            with get_connection() as db:
                begin_write(db)
                other_table = workers.submit(self.send, guest, "/bookings", self.booking(table_id=2))
                self.wait_for_blocked(db.info.backend_pid, other_table)
            self.assertEqual(other_table.result(timeout=5).status_code, 201)
        time_limited = make_conninfo(self.dsn, options=self.options + " -clock_timeout=100ms")
        with get_connection() as db:
            begin_write(db)
            with patch.dict(os.environ, {"DATABASE_URL": time_limited}):
                busy = self.send(guest, "/bookings", self.booking(table_id=3))
        self.assertEqual((busy.status_code, busy.json["error"]), (503, "DATABASE_BUSY"))
        self.assertEqual(self.send(guest, "/bookings", self.booking(table_id=3)).status_code, 201)

    def called_ticket(self, *, table=1):
        ticket = QueueManager.join_waitlist(2, phone=self.phone(0), customer_phone=self.phone(0))
        QueueManager.call_next(table)
        return ticket["queue_id"]

    def assert_ticket_and_visits(self, ticket, status, visits):
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM waiting_queue WHERE queue_id=?", (ticket,)).fetchone()[0], status)
            self.assertEqual(db.execute("SELECT count(*) FROM dining_sessions").fetchone()[0], visits)

    def test_cancellation_wins_while_seating_waits_for_ticket(self):
        guest, desk = self.actor(), self.actor(staff=True)
        ticket = self.called_ticket()
        with ThreadPoolExecutor(max_workers=1) as workers:
            with get_connection() as db:
                db.execute("SELECT queue_id FROM waiting_queue WHERE queue_id=? FOR UPDATE", (ticket,))
                seating = workers.submit(self.send, desk, f"/frontdesk/waiting-queue/{ticket}/seat", {"table_id": 1})
                self.wait_for_blocked(db.info.backend_pid, seating)
                with patch("restaurant.services.queue_manager.get_connection", return_value=nullcontext(db)):
                    cancelled = self.send(guest, f"/waiting-queue/{ticket}", method="DELETE")
                self.assertEqual(cancelled.status_code, 200)
            result = seating.result(timeout=5)
        self.assertEqual((result.status_code, result.json["error"]), (409, "WAITLIST_CHANGED"))
        self.assert_ticket_and_visits(ticket, "cancelled", 0)

    def test_seating_wins_while_cancellation_waits(self):
        guest, desk = self.actor(), self.actor(staff=True)
        ticket = self.called_ticket()
        seat_holds_ticket = Event()
        finish_seating = Event()
        transaction = []

        def pause_after_ticket_lock(db, *args, **kwargs):
            transaction.append(db.info.backend_pid)
            seat_holds_ticket.set()
            if not finish_seating.wait(8):
                self.fail("The seating test did not release its transaction.")
            return require_seatable_table(db, *args, **kwargs)

        with (
            patch("restaurant.services.queue_manager.require_seatable_table", side_effect=pause_after_ticket_lock),
            ThreadPoolExecutor(max_workers=2) as workers,
        ):
            seated = workers.submit(self.send, desk, f"/frontdesk/waiting-queue/{ticket}/seat", {"table_id": 1})
            try:
                self.assertTrue(seat_holds_ticket.wait(5))
                cancelled = workers.submit(self.send, guest, f"/waiting-queue/{ticket}", method="DELETE")
                self.wait_for_blocked(transaction[0], cancelled)
            finally:
                finish_seating.set()
            self.assertEqual(seated.result(timeout=5).status_code, 201)
            self.assertEqual(cancelled.result(timeout=5).status_code, 404)
        self.assert_ticket_and_visits(ticket, "seated", 1)

    def test_expiry_checks_clock_after_waiting_and_keeps_exact_boundary(self):
        ticket = self.called_ticket()
        with get_connection() as db:
            called_at = db.execute("SELECT called_at FROM waiting_queue WHERE queue_id=?", (ticket,)).fetchone()[0]
        cutoff = datetime.fromisoformat(called_at).replace(tzinfo=timezone.utc)
        clock = cutoff

        def read_clock(minutes=0):
            return (clock + timedelta(minutes=10 - minutes)).strftime("%Y-%m-%d %H:%M:%S")

        with patch("restaurant.services.queue_manager.utc_clock", side_effect=read_clock):
            self.assertEqual(QueueManager.expire_called(), 0)
            with ThreadPoolExecutor(max_workers=1) as workers:
                with get_connection() as db:
                    db.execute("SELECT queue_id FROM waiting_queue WHERE queue_id=? FOR UPDATE", (ticket,))
                    seating = workers.submit(QueueManager.seat, ticket, 1)
                    self.wait_for_blocked(db.info.backend_pid, seating)
                    clock += timedelta(seconds=1)
                with self.assertRaises(ServiceError) as error:
                    seating.result(timeout=5)
                self.assertEqual(error.exception.code, "WAITLIST_CHANGED")
            self.assertEqual(QueueManager.expire_called(), 1)
            self.assert_ticket_and_visits(ticket, "expired", 0)
            clock = cutoff
            with get_connection() as db:
                db.execute("UPDATE waiting_queue SET status='called' WHERE queue_id=?", (ticket,))
            QueueManager.seat(ticket, 1)
        self.assert_ticket_and_visits(ticket, "seated", 1)

    def test_failed_visit_insert_rolls_back_ticket_change(self):
        ticket = self.called_ticket()
        with get_connection() as db:
            db.execute("ALTER TABLE dining_sessions ADD CHECK (party_size > 3)")
        with self.assertRaises(psycopg.errors.CheckViolation):
            QueueManager.seat(ticket, 1)
        self.assert_ticket_and_visits(ticket, "called", 0)
