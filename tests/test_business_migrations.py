"""Production-style 005 -> 008 upgrades in disposable loopback PostgreSQL schemas."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import os
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from restaurant.db.upgrade import upgrade


TEST_DSN = os.environ.get("USURPERS_TEST_POSTGRES_URL")
DB_SQL = Path(__file__).resolve().parents[1] / "restaurant" / "db"


@unittest.skipUnless(TEST_DSN, "requires disposable loopback PostgreSQL")
class BusinessMigrationTests(unittest.TestCase):
    def setUp(self):
        config = conninfo_to_dict(TEST_DSN)
        if (config.get("host") not in {"127.0.0.1", "::1"}
                or config.get("hostaddr", config["host"]) != config["host"]
                or config.get("dbname") != "usurpers_test"):
            self.fail("Use a disposable database named usurpers_test on loopback.")
        self.schema = "business_migration_test_" + uuid4().hex
        self.probe = self.enterContext(psycopg.connect(TEST_DSN, autocommit=True))
        self.probe.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.probe.execute, sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))
        self.dsn = make_conninfo(TEST_DSN, options="-csearch_path=" + self.schema)
        self.migrations = sorted((DB_SQL / "migrations").glob("*.sql"))
        self.release = [path for path in self.migrations if 6 <= int(path.name[:3]) <= 8]
        with psycopg.connect(self.dsn, autocommit=True) as db:
            db.execute((DB_SQL / "postgres.sql").read_text(encoding="utf-8"))
            # The current bootstrap includes the release's convenience tables. Remove
            # only those additions inside this isolated schema to exercise actual DDL.
            db.execute("""DROP TABLE account_link_requests, account_mail_limits, account_tokens,
                customer_recovery, order_resolution_audit, kitchen_settings_audit, kitchen_settings;
                ALTER TABLE orders DROP COLUMN queue_id, DROP COLUMN replaces_item_id,
                    DROP COLUMN served_by, DROP COLUMN served_at;
                ALTER TABLE waiting_queue DROP COLUMN source_booking_id, DROP COLUMN service_ends_at,
                    DROP COLUMN version;
                ALTER TABLE order_items DROP COLUMN dish_name_snapshot, DROP COLUMN category_snapshot,
                    DROP COLUMN supply_issue, DROP COLUMN issue_reported_by, DROP COLUMN issue_reported_at;""")
            for path in self.migrations:
                if 2 <= int(path.name[:3]) <= 5:
                    db.execute(path.read_text(encoding="utf-8"))
            self.assertEqual(self.versions(db), [2, 3, 4, 5])
            db.execute("INSERT INTO dining_tables(capacity) VALUES(4)")
            db.execute("INSERT INTO customers(customer_phone,name,password_hash) VALUES('13920000000','Historical guest','fixture-only')")
            db.execute("INSERT INTO dishes(dish_name,category,price) VALUES('Historical dish','sides',29.90)")
            db.execute("""INSERT INTO bookings(contact_name,phone_number,customer_phone,booking_date,time_slot,
                party_size,table_id,arrival_at,arrival_deadline,version)
                VALUES('Historical guest','13920000000','13920000000','2048-02-20','19:00-20:10',3,1,
                       '2048-02-20 11:00+00','2048-02-20 11:10+00',7)""")
            db.execute("""INSERT INTO orders(booking_id,customer_phone,contact_name,phone_number,table_id,order_type,version)
                VALUES(1,'13920000000','Historical guest','13920000000',1,'preorder',4)""")
            db.execute("""INSERT INTO order_items(order_id,dish_id,quantity,unit_price,total_price,note,estimated_ready_at)
                VALUES(1,1,2,19.25,38.50,'No chilli','2048-02-20 11:00')""")
            db.execute("""INSERT INTO waiting_queue(contact_name,phone_number,party_size,queue_position,created_at)
                VALUES('Lunch wait','13920000001',2,1,'2048-02-20 03:30')""")
            self.before = self.historical_values(db)

    @staticmethod
    def versions(db):
        return [row[0] for row in db.execute("SELECT version FROM reservation_schema_versions ORDER BY version")]

    @staticmethod
    def historical_values(db):
        return {
            "booking": db.execute("""SELECT booking_id,contact_name,phone_number,customer_phone,booking_date,
                time_slot,party_size,table_id,status,version,arrival_at,arrival_deadline,created_at FROM bookings""").fetchall(),
            "order": db.execute("""SELECT order_id,booking_id,visit_id,customer_phone,table_id,order_type,
                status,payment_status,version,created_at FROM orders""").fetchall(),
            "items": db.execute("""SELECT order_item_id,order_id,dish_id,quantity,unit_price,total_price,
                note,status,enqueued_at,estimated_ready_at FROM order_items""").fetchall(),
            "queue": db.execute("SELECT queue_id,contact_name,phone_number,party_size,queue_position,status,created_at FROM waiting_queue").fetchall(),
        }

    def assert_upgraded(self, db):
        self.assertEqual(self.versions(db), list(range(2, 9)))
        self.assertEqual(self.historical_values(db), self.before)
        self.assertEqual(db.execute("SELECT unit_price,total_price,dish_name_snapshot,category_snapshot FROM order_items").fetchone(),
                         (Decimal("19.25"), Decimal("38.50"), "Historical dish", "sides"))
        self.assertEqual(db.execute("SELECT service_ends_at,version FROM waiting_queue").fetchone(),
                         (datetime(2048, 2, 20, 6, tzinfo=timezone.utc), 1))
        self.assertEqual(db.execute("SELECT COUNT(*) FROM account_link_requests").fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM booking_table_changes").fetchone()[0], 0)

    def test_raw_migrations_can_run_twice_without_losing_history_or_resetting_settings(self):
        with psycopg.connect(self.dsn, autocommit=True) as db:
            for path in self.release:
                db.execute(path.read_text(encoding="utf-8"))
            self.assert_upgraded(db)
            db.execute("UPDATE kitchen_settings SET max_active_orders=8,version=3 WHERE id=1")
            db.execute("UPDATE dishes SET dish_name='Renamed after acceptance',category='new category',price=39.90")
            for path in self.release:
                db.execute(path.read_text(encoding="utf-8"))
            self.assert_upgraded(db)
            self.assertEqual(db.execute("SELECT max_active_orders,version FROM kitchen_settings WHERE id=1").fetchone(), (8, 3))

    def test_upgrade_dry_run_actual_upgrade_and_repeat_are_safe(self):
        expected = [path.name for path in self.release]
        self.assertEqual(upgrade(self.dsn, 8, dry_run=True), expected)
        with psycopg.connect(self.dsn) as db:
            self.assertEqual(self.versions(db), [2, 3, 4, 5])
            self.assertIsNone(db.execute("SELECT to_regclass('account_link_requests')").fetchone()[0])
            self.assertEqual(self.historical_values(db), self.before)
        self.assertEqual(upgrade(self.dsn, 8), expected)
        self.assertEqual(upgrade(self.dsn, 8), [])
        self.assertEqual(upgrade(self.dsn, 8, dry_run=True), [])
        with psycopg.connect(self.dsn) as db:
            self.assert_upgraded(db)
