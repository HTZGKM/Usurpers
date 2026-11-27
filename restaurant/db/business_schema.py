"""Shared order fields for the isolated SQLite compatibility test database.

The reservation allocator remains PostgreSQL-only; production changes are the
numbered SQL migrations, which are deployed explicitly before the application.
"""


def ensure_sqlite_business_schema(db):
    for table, column, declaration in (
        ("orders", "queue_id", "INTEGER REFERENCES waiting_queue(queue_id)"),
        ("orders", "replaces_item_id", "INTEGER REFERENCES order_items(order_item_id)"),
        ("orders", "served_by", "TEXT"),
        ("orders", "served_at", "TEXT"),
        ("order_items", "dish_name_snapshot", "TEXT"),
        ("order_items", "category_snapshot", "TEXT"),
        ("order_items", "supply_issue", "TEXT"),
        ("order_items", "issue_reported_by", "TEXT"),
        ("order_items", "issue_reported_at", "TEXT"),
        ("waiting_queue", "source_booking_id", "INTEGER REFERENCES bookings(booking_id)"),
        ("waiting_queue", "service_ends_at", "TEXT"),
        ("waiting_queue", "version", "INTEGER NOT NULL DEFAULT 1"),
    ):
        known = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in known:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
    for statement in (
        """CREATE TABLE IF NOT EXISTS kitchen_settings (
            id INTEGER PRIMARY KEY CHECK(id=1), max_active_orders INTEGER NOT NULL DEFAULT 5,
            version INTEGER NOT NULL DEFAULT 1)""",
        "INSERT OR IGNORE INTO kitchen_settings(id) VALUES(1)",
        """CREATE TABLE IF NOT EXISTS kitchen_settings_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL,
            old_limit INTEGER NOT NULL, new_limit INTEGER NOT NULL,
            changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS order_resolution_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_item_id INTEGER NOT NULL REFERENCES order_items,
            action TEXT NOT NULL, reason TEXT NOT NULL, actor TEXT NOT NULL,
            replacement_order_id INTEGER REFERENCES orders,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    ):
        db.execute(statement)
    # Existing rows predate snapshots; preserve their current known labels once.
    db.execute("""UPDATE order_items SET
        dish_name_snapshot=(SELECT dish_name FROM dishes WHERE dishes.dish_id=order_items.dish_id),
        category_snapshot=(SELECT category FROM dishes WHERE dishes.dish_id=order_items.dish_id)
        WHERE dish_name_snapshot IS NULL""")
