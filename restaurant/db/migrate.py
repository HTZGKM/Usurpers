"""Copy the current SQLite database into an empty PostgreSQL database."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
import sqlite3

from psycopg import sql
from werkzeug.security import check_password_hash, generate_password_hash

from .database import begin_write, hash_password
from .postgres import connect


TABLES = {
    "staff": "staff_id",
    "customers": None,
    "dining_tables": "table_id",
    "dishes": "dish_id",
    "bookings": "booking_id",
    "dining_sessions": "visit_id",
    "orders": "order_id",
    "order_items": "order_item_id",
    "waiting_queue": "queue_id",
    "kitchen_queue": "queue_id",
    "ingredients": "ingredient_id",
    "dish_ingredients": None,
}

TIMESTAMPS = {
    "created_at", "arrived_at", "closed_at", "paid_at", "enqueued_at",
    "estimated_ready_at", "called_at", "started_at", "completed_at",
}


def _timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _demo_password(value):
    if "$" in value:
        return check_password_hash(value, "123456")
    return secrets.compare_digest(value, hash_password("123456"))


def migrate(source_path, database_url, credentials_path, *, rotate_demo=True):
    source_path = source_path.resolve(strict=True)
    schema = Path(__file__).with_name("postgres.sql").read_text(encoding="utf-8")
    if credentials_path.exists():
        raise RuntimeError("Choose a new credentials output file to preserve the existing copy.")
    counts = {}
    credentials = []
    with closing(sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)) as source, connect(database_url) as target:
        source.row_factory = sqlite3.Row
        source.execute("BEGIN")
        sequences = dict(source.execute("SELECT name, seq FROM sqlite_sequence"))
        begin_write(target)
        with target.cursor() as cursor:
            cursor.execute(schema)
            for table, key in TABLES.items():
                identifier = sql.Identifier(table)
                cursor.execute(sql.SQL("SELECT 1 FROM {} LIMIT 1").format(identifier))
                if cursor.fetchone() is not None:
                    raise RuntimeError(f"Destination table {table} already contains data.")
                source_rows = source.execute(f"SELECT * FROM {table}")
                columns = [column[0] for column in source_rows.description]
                insert = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    identifier, sql.SQL(", ").join(map(sql.Identifier, columns)),
                    sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                )
                rows = []
                for source_row in source_rows:
                    row = dict(source_row)
                    if rotate_demo and table in ("staff", "customers") and _demo_password(row["password_hash"]):
                        password = secrets.token_urlsafe(18)
                        login = row["email"] if table == "staff" else row["customer_phone"]
                        role = row.get("role", "customer")
                        credentials.append(f"{role}\t{login}\t{password}")
                        row["password_hash"] = generate_password_hash(password)
                    rows.append(tuple(_timestamp(row[column]) if row[column] is not None and column in TIMESTAMPS
                                      else row[column] for column in columns))
                if rows:
                    cursor.executemany(insert, rows)
                counts[table] = len(rows)
                if key:
                    cursor.execute(sql.SQL("SELECT COALESCE(MAX({}), 0) AS last_id FROM {}").format(
                        sql.Identifier(key), identifier,
                    ))
                    last_id = max(cursor.fetchone()["last_id"], sequences.get(table, 0))
                    cursor.execute("SELECT setval(pg_get_serial_sequence(%s,%s),%s,%s)",
                                   (table, key, max(last_id, 1), last_id > 0))
            for table, count in counts.items():
                cursor.execute(sql.SQL("SELECT COUNT(*) AS count FROM {}").format(sql.Identifier(table)))
                if cursor.fetchone()["count"] != count:
                    raise RuntimeError(f"Row count mismatch in {table}.")
        if credentials:
            with credentials_path.open("x", encoding="utf-8") as report:
                report.write("Role\tLogin\tNew password\n" + "\n".join(credentials) + "\n")
    return counts, len(credentials)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--credentials-file", type=Path, required=True)
    args = parser.parse_args()
    if not os.environ.get("DATABASE_URL"):
        parser.exit(2, "Set DATABASE_URL to the empty PostgreSQL destination.\n")
    counts, rotated = migrate(args.source, os.environ["DATABASE_URL"], args.credentials_file)
    for table, count in counts.items():
        print(f"{table}: {count}")
    print(f"Replaced {rotated} publicly documented demo passwords.")


if __name__ == "__main__":
    main()
