from __future__ import annotations

import argparse
import hashlib
import random
import sqlite3
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from restaurant.business_time import RESTAURANT_TIME

PACKAGE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PACKAGE_DIR / "data"
DB_PATH = Path(os.environ.get("USURPERS_DB_PATH", DATA_DIR / "shuangfen.db"))


def configured_db_path() -> Path:
    """Resolve the database path at call time so test suites can isolate DBs."""
    return Path(os.environ.get("USURPERS_DB_PATH", DB_PATH))


def using_postgres() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


class ClosingConnection(sqlite3.Connection):
    """Make `with get_connection()` commit/rollback and close the handle."""
    def __exit__(self, exc_type, exc, traceback):
        try:
            return super().__exit__(exc_type, exc, traceback)
        finally:
            self.close()


def hash_password(raw_password: str) -> str:
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


DEFAULT_STAFF = [
    {
        "staff_id": 1,
        "name": "系统管理员",
        "role": "admin",
        "phone": "13800000001",
        "email": "admin@shuangfen.local",
        "password_hash": hash_password("123456"),
    },
    {
        "staff_id": 2,
        "name": "前台小二",
        "role": "frontdesk",
        "phone": "13800000002",
        "email": "frontdesk@shuangfen.local",
        "password_hash": hash_password("123456"),
    },
    {
        "staff_id": 3,
        "name": "后厨小刘",
        "role": "kitchen",
        "phone": "13800000003",
        "email": "kitchen@shuangfen.local",
        "password_hash": hash_password("123456"),
    },
]

ALLOWED_STAFF_ROLES = {"admin", "frontdesk", "kitchen"}

DEFAULT_CUSTOMERS = [
    {
        "customer_phone": "13900000001",
        "name": "演示顾客",
        "password_hash": hash_password("123456"),
    },
    {
        "customer_phone": "13900000002",
        "name": "测试顾客",
        "password_hash": hash_password("123456"),
    },
    {
        "customer_phone": "13900000003",
        "name": "散客甲",
        "password_hash": hash_password("123456"),
    },
    {
        "customer_phone": "13900000004",
        "name": "散客乙",
        "password_hash": hash_password("123456"),
    },
    {
        "customer_phone": "13900000005",
        "name": "常客丙",
        "password_hash": hash_password("123456"),
    },
    {
        "customer_phone": "18612345678",
        "name": "朱哥",
        "password_hash": hash_password("111111"),
    },
]

DEFAULT_TABLES = [
    {"table_id": 1, "capacity": 2},
    {"table_id": 2, "capacity": 2},
    {"table_id": 3, "capacity": 4},
    {"table_id": 4, "capacity": 4},
    {"table_id": 5, "capacity": 6},
    {"table_id": 6, "capacity": 6},
]

DEFAULT_DISHES = [
    {"dish_id": 1, "dish_name": "House Cheeseburger", "price": 38.00, "is_available": 1, "category": "burgers"},
    {"dish_id": 2, "dish_name": "Double Cheddar", "price": 48.00, "is_available": 1, "category": "burgers"},
    {"dish_id": 3, "dish_name": "Herb Chicken", "price": 42.00, "is_available": 1, "category": "burgers"},
    {"dish_id": 4, "dish_name": "Portobello", "price": 40.00, "is_available": 1, "category": "burgers"},
    {"dish_id": 5, "dish_name": "Crisp Fish", "price": 46.00, "is_available": 1, "category": "burgers"},
    {"dish_id": 6, "dish_name": "Margherita", "price": 58.00, "is_available": 1, "category": "pizzas"},
    {"dish_id": 7, "dish_name": "Mushroom & Pepper", "price": 62.00, "is_available": 1, "category": "pizzas"},
    {"dish_id": 8, "dish_name": "Bianca", "price": 60.00, "is_available": 1, "category": "pizzas"},
    {"dish_id": 9, "dish_name": "Olive & Oregano", "price": 56.00, "is_available": 1, "category": "pizzas"},
    {"dish_id": 10, "dish_name": "Potato & Rosemary", "price": 64.00, "is_available": 1, "category": "pizzas"},
    {"dish_id": 11, "dish_name": "Sea Salt Fries", "price": 18.00, "is_available": 1, "category": "sides"},
    {"dish_id": 12, "dish_name": "Crispy Onion Rings", "price": 22.00, "is_available": 0, "category": "sides"},
    {"dish_id": 13, "dish_name": "Lemon Soda", "price": 16.00, "is_available": 1, "category": "drinks"},
    {"dish_id": 14, "dish_name": "Iced Black Tea", "price": 14.00, "is_available": 1, "category": "drinks"},
]


def sqlite_connection(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, factory=ClosingConnection, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_connection():
    if using_postgres():
        from .postgres import connect

        return connect(os.environ["DATABASE_URL"])
    return sqlite_connection(configured_db_path())


def begin_write(connection, *, legacy_allocation=False):
    if isinstance(connection, sqlite3.Connection):
        connection.execute("BEGIN IMMEDIATE")
    else:
        # Preserve SQLite's serial writer semantics for workflows that read before writing.
        connection.execute("SELECT pg_advisory_xact_lock(731593001)")
        if legacy_allocation:
            from restaurant.services.allocation import legacy_write_guard

            legacy_write_guard(connection)


def begin_read(connection):
    connection.execute("BEGIN" if isinstance(connection, sqlite3.Connection) else
                       "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")


def insert_id(connection, query, params, column):
    row = connection.execute(query + " RETURNING " + column, params).fetchone()
    return row[0] if row else None


def create_schema(connection: sqlite3.Connection) -> None:
    for table, required in (("bookings", "time_slot"), ("staff", "password_hash"), ("customers", "password_hash")):
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if columns and required not in columns:
            raise RuntimeError(
                "The SQLite database uses the old schema. Back it up before running "
                "python -m restaurant.db --reset, or set USURPERS_DB_PATH to a new file."
            )
    connection.executescript(
        """
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS staff (
            staff_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1))
        );

        CREATE TABLE IF NOT EXISTS customers (
            customer_phone TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1))
        );

        CREATE TABLE IF NOT EXISTS dining_tables (
            table_id INTEGER PRIMARY KEY,
            capacity INTEGER NOT NULL CHECK (capacity > 0)
        );

        CREATE TABLE IF NOT EXISTS dishes (
            dish_id INTEGER PRIMARY KEY,
            dish_name TEXT NOT NULL UNIQUE,
            price NUMERIC NOT NULL CHECK (price >= 0),
            is_available INTEGER NOT NULL DEFAULT 1 CHECK (is_available IN (0, 1)),
            is_archived INTEGER NOT NULL DEFAULT 0 CHECK (is_archived IN (0,1)),
            ingredients TEXT NOT NULL DEFAULT '', prep_time_minutes INTEGER NOT NULL DEFAULT 10,
            image_url TEXT
        );

        CREATE TABLE IF NOT EXISTS bookings (
            booking_id INTEGER PRIMARY KEY AUTOINCREMENT, contact_name TEXT NOT NULL, phone_number TEXT NOT NULL,
            customer_phone TEXT,
            booking_date TEXT NOT NULL, time_slot TEXT NOT NULL, party_size INTEGER NOT NULL CHECK(party_size > 0),
            status TEXT NOT NULL DEFAULT 'booked' CHECK(status IN ('booked','arrived','cancelled')),
            version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
            table_id INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(table_id) REFERENCES dining_tables(table_id),
            FOREIGN KEY(customer_phone) REFERENCES customers(customer_phone)
        );
        CREATE TABLE IF NOT EXISTS booking_create_requests (
            customer_phone TEXT NOT NULL REFERENCES customers(customer_phone),
            request_key TEXT NOT NULL,
            request_fields TEXT NOT NULL,
            booking_id INTEGER NOT NULL REFERENCES bookings(booking_id),
            initial_table_id INTEGER NOT NULL REFERENCES dining_tables(table_id),
            PRIMARY KEY (customer_phone, request_key)
        );
        CREATE TABLE IF NOT EXISTS dining_sessions (
            visit_id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER, customer_phone TEXT,
            contact_name TEXT, phone_number TEXT, party_size INTEGER NOT NULL CHECK(party_size > 0),
            table_id INTEGER, status TEXT NOT NULL DEFAULT 'seated' CHECK(status IN ('waiting','seated','closed')),
            arrived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, closed_at TEXT,
            FOREIGN KEY(booking_id) REFERENCES bookings(booking_id),
            FOREIGN KEY(customer_phone) REFERENCES customers(customer_phone),
            FOREIGN KEY(table_id) REFERENCES dining_tables(table_id)
        );
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT, visit_id INTEGER, booking_id INTEGER, customer_phone TEXT,
            contact_name TEXT, phone_number TEXT, table_id INTEGER, order_type TEXT NOT NULL DEFAULT 'dine_in',
            status TEXT NOT NULL DEFAULT 'active', payment_status TEXT NOT NULL DEFAULT 'unpaid',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, paid_at TEXT,
            FOREIGN KEY(visit_id) REFERENCES dining_sessions(visit_id),
            FOREIGN KEY(booking_id) REFERENCES bookings(booking_id),
            FOREIGN KEY(customer_phone) REFERENCES customers(customer_phone)
        );
        CREATE TABLE IF NOT EXISTS order_items (
            order_item_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, dish_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0), unit_price NUMERIC NOT NULL CHECK(unit_price >= 0),
            total_price NUMERIC NOT NULL DEFAULT 0 CHECK(total_price >= 0),
            note TEXT, status TEXT NOT NULL DEFAULT 'waiting' CHECK(status IN ('waiting','cooking','ready','served','cancelled')),
            enqueued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            estimated_ready_at TEXT,
            FOREIGN KEY(order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
            FOREIGN KEY(dish_id) REFERENCES dishes(dish_id)
        );
        CREATE TABLE IF NOT EXISTS waiting_queue (
            queue_id INTEGER PRIMARY KEY AUTOINCREMENT, contact_name TEXT, phone_number TEXT,
            customer_phone TEXT, party_size INTEGER NOT NULL CHECK(party_size>0),
            table_type INTEGER, queue_position INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'waiting'
              CHECK(status IN ('waiting','called','seated','cancelled','expired')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, called_at TEXT, called_table_id INTEGER,
            FOREIGN KEY(customer_phone) REFERENCES customers(customer_phone),
            FOREIGN KEY(called_table_id) REFERENCES dining_tables(table_id)
        );
        CREATE TABLE IF NOT EXISTS kitchen_queue (
            queue_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL,
            order_item_id INTEGER NOT NULL UNIQUE, dish_id INTEGER NOT NULL, quantity INTEGER NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0, estimated_ready_at TEXT,
            status TEXT NOT NULL DEFAULT 'waiting' CHECK(status IN ('waiting','cooking','ready','served','cancelled')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, started_at TEXT, completed_at TEXT,
            FOREIGN KEY(order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
            FOREIGN KEY(order_item_id) REFERENCES order_items(order_item_id) ON DELETE CASCADE,
            FOREIGN KEY(dish_id) REFERENCES dishes(dish_id)
        );
        CREATE TABLE IF NOT EXISTS ingredients (
            ingredient_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            unit TEXT NOT NULL, on_hand REAL NOT NULL CHECK(on_hand>=0),
            expires_at TEXT, is_available INTEGER NOT NULL DEFAULT 1 CHECK(is_available IN (0,1))
        );
        CREATE TABLE IF NOT EXISTS dish_ingredients (
            dish_id INTEGER NOT NULL, ingredient_id INTEGER NOT NULL,
            quantity_per_dish REAL NOT NULL CHECK(quantity_per_dish>0),
            PRIMARY KEY(dish_id,ingredient_id), FOREIGN KEY(dish_id) REFERENCES dishes(dish_id),
            FOREIGN KEY(ingredient_id) REFERENCES ingredients(ingredient_id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_bookings_table_slot ON bookings(table_id, booking_date, time_slot) WHERE status = 'booked';
        CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(booking_date, time_slot, status);
        CREATE INDEX IF NOT EXISTS idx_sessions_table_status ON dining_sessions(table_id, status);
        CREATE INDEX IF NOT EXISTS idx_order_items_status_queue ON order_items(status, enqueued_at);
        CREATE INDEX IF NOT EXISTS idx_orders_service_day ON orders(date(created_at, '+8 hours'));
        CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
        CREATE INDEX IF NOT EXISTS idx_kitchen_queue_order ON kitchen_queue(status, priority, estimated_ready_at, created_at);
        CREATE INDEX IF NOT EXISTS idx_waiting_queue_order ON waiting_queue(status, queue_position);
        """
    )
    for table, field, declaration in (
        ("bookings", "customer_phone", "TEXT REFERENCES customers(customer_phone)"),
        ("bookings", "version", "INTEGER NOT NULL DEFAULT 1 CHECK(version > 0)"),
        ("orders", "booking_id", "INTEGER REFERENCES bookings(booking_id)"),
        ("staff", "is_active", "INTEGER NOT NULL DEFAULT 1"),
        ("customers", "is_active", "INTEGER NOT NULL DEFAULT 1"),
        ("dishes", "is_archived", "INTEGER NOT NULL DEFAULT 0"),
        ("order_items", "estimated_ready_at", "TEXT"),
        ("waiting_queue", "called_table_id", "INTEGER REFERENCES dining_tables(table_id)"),
        ("dishes", "ingredients", "TEXT NOT NULL DEFAULT ''"),
        ("dishes", "prep_time_minutes", "INTEGER NOT NULL DEFAULT 10"),
        ("dishes", "image_url", "TEXT"),
        ("dishes", "category", "TEXT"),
    ):
        known = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if field not in known:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {field} {declaration}")


def seed_defaults(connection: sqlite3.Connection) -> None:
    placeholders = ", ".join("?" for _ in ALLOWED_STAFF_ROLES)
    connection.execute(
        f"DELETE FROM staff WHERE role NOT IN ({placeholders})",
        tuple(ALLOWED_STAFF_ROLES),
    )
    connection.executemany(
        """
        INSERT OR IGNORE INTO staff (staff_id, name, role, phone, email, password_hash)
        VALUES (:staff_id, :name, :role, :phone, :email, :password_hash)
        """,
        DEFAULT_STAFF,
    )
    connection.executemany(
        """
        INSERT OR IGNORE INTO customers (customer_phone, name, password_hash)
        VALUES (:customer_phone, :name, :password_hash)
        """,
        DEFAULT_CUSTOMERS,
    )
    connection.executemany(
        """
        INSERT OR IGNORE INTO dining_tables (table_id, capacity)
        VALUES (:table_id, :capacity)
        """,
        DEFAULT_TABLES,
    )
    connection.executemany(
        """
        INSERT OR IGNORE INTO dishes (dish_id, dish_name, price, is_available, category)
        VALUES (:dish_id, :dish_name, :price, :is_available, :category)
        """,
        DEFAULT_DISHES,
    )
    # Stable demo records make the new booking/visit/order flows inspectable.
    connection.execute("INSERT OR IGNORE INTO bookings (booking_id,contact_name,phone_number,booking_date,time_slot,party_size,status,table_id,customer_phone) VALUES (1,'演示预约','13900000001','2026-12-01','11:00-14:00',2,'booked',1,'13900000001')")
    # 额外顾客预约：覆盖今天/明天、不同时段、已入座/未入座
    connection.execute("INSERT OR IGNORE INTO bookings (booking_id,contact_name,phone_number,booking_date,time_slot,party_size,status,table_id,customer_phone) VALUES "
        "(2,'朱哥','18612345678',date('now','+8 hours'),'11:00-14:00',4,'arrived',3,'18612345678'),"
        "(3,'散客甲','13900000003',date('now','+8 hours'),'17:00-19:00',6,'arrived',5,'13900000003'),"
        "(4,'常客丙','13900000005',date('now','+8 hours'),'19:00-21:00',4,'arrived',4,'13900000005'),"
        "(5,'散客乙','13900000004',date('now','+1 day','+8 hours'),'11:00-14:00',2,'booked',2,'13900000004')")
    connection.execute("INSERT OR IGNORE INTO dining_sessions (visit_id,booking_id,customer_phone,contact_name,phone_number,party_size,table_id,status) VALUES "
        "(1,NULL,'13900000002','测试顾客','13900000002',2,2,'seated'),"
        "(2,2,'18612345678','朱哥','18612345678',4,3,'seated'),"
        "(3,3,'13900000003','散客甲','13900000003',6,5,'seated'),"
        "(4,4,'13900000005','常客丙','13900000005',4,4,'seated')")
    connection.execute("""UPDATE bookings SET status='arrived',version=version+1 WHERE status='booked' AND EXISTS (
        SELECT 1 FROM dining_sessions s WHERE s.booking_id=bookings.booking_id
        AND s.table_id=bookings.table_id AND s.status IN ('seated','closed'))""")
    connection.execute("""UPDATE orders SET
        visit_id=(SELECT s.visit_id FROM dining_sessions s WHERE s.booking_id=orders.booking_id AND s.status='seated' ORDER BY s.visit_id DESC LIMIT 1),
        table_id=(SELECT s.table_id FROM dining_sessions s WHERE s.booking_id=orders.booking_id AND s.status='seated' ORDER BY s.visit_id DESC LIMIT 1)
        WHERE order_type='preorder' AND visit_id IS NULL AND status<>'cancelled'
        AND EXISTS (SELECT 1 FROM dining_sessions s WHERE s.booking_id=orders.booking_id AND s.status='seated')""")
    connection.execute("INSERT OR IGNORE INTO orders (order_id,visit_id,customer_phone,contact_name,phone_number,table_id,order_type,status,payment_status) VALUES "
        "(9001,1,'13900000002','测试顾客','13900000002',2,'dine_in','active','unpaid'),"
        "(9002,2,'18612345678','朱哥','18612345678',3,'dine_in','active','unpaid'),"
        "(9003,3,'13900000003','散客甲','13900000003',5,'dine_in','active','unpaid')")
    connection.execute("INSERT OR IGNORE INTO order_items (order_item_id,order_id,dish_id,quantity,unit_price,total_price,note,status) VALUES "
        "(9001,9001,1,1,38.00,38.00,'演示：少酱','waiting'),"
        "(9002,9001,11,1,18.00,18.00,'演示：不加盐','cooking'),"
        "(9003,9002,2,1,48.00,48.00,NULL,'cooking'),"
        "(9004,9002,3,1,42.00,42.00,'不要香菜','ready'),"
        "(9005,9002,11,1,18.00,18.00,NULL,'waiting'),"
        "(9006,9003,4,1,40.00,40.00,NULL,'ready'),"
        "(9007,9003,13,2,16.00,32.00,'少冰','waiting')")
    connection.execute("INSERT OR IGNORE INTO kitchen_queue(order_id,order_item_id,dish_id,quantity,status,started_at,completed_at) VALUES "
        "(9001,9001,1,1,'waiting',NULL,NULL),"
        "(9001,9002,11,1,'cooking',datetime('now','-12 minutes'),NULL),"
        "(9002,9003,2,1,'cooking',datetime('now','-10 minutes'),NULL),"
        "(9002,9004,3,1,'ready',datetime('now','-20 minutes'),datetime('now','-5 minutes')),"
        "(9002,9005,11,1,'waiting',NULL,NULL),"
        "(9003,9006,4,1,'ready',datetime('now','-25 minutes'),datetime('now','-8 minutes')),"
        "(9003,9007,13,2,'waiting',NULL,NULL)")

    # Historical demo orders for the admin dashboard (last 7 days, UTC timestamps).
    # Deterministic generation with a fixed seed so the dataset is reproducible.
    # Service hours in +8 timezone: lunch 11:00-14:00, dinner 17:00-21:00.
    # In UTC that maps to 03:00-06:00 and 09:00-13:00 so date(created_at, '+8 hours')
    # stays on the intended calendar day.
    #
    # Auto-roll: delete previously generated seed history (order_id 2000-2999) and
    # regenerate so the "last 7 days" window always ends on the current date.
    # Real user orders (order_id >= 9000) are left untouched.
    connection.execute("DELETE FROM order_items WHERE order_id BETWEEN 2000 AND 2999")
    connection.execute("DELETE FROM kitchen_queue WHERE order_id BETWEEN 2000 AND 2999")
    connection.execute("DELETE FROM orders WHERE order_id BETWEEN 2000 AND 2999")
    dish_ids = [d["dish_id"] for d in DEFAULT_DISHES]
    dish_prices = {d["dish_id"]: float(d["price"]) for d in DEFAULT_DISHES}
    rng = random.Random(20261123)

    customers = [
        ("13900000001", "演示顾客"),
        ("13900000002", "测试顾客"),
        ("13900000003", "散客甲"),
        ("13900000004", "散客乙"),
        ("13900000005", "常客丙"),
    ]
    now_utc = datetime.now(timezone.utc)
    local_today = now_utc.astimezone(RESTAURANT_TIME).date()
    line_id = 9100

    for day_offset in range(7):  # 0 = today, 6 = six days ago
        service_day = local_today - timedelta(days=day_offset)
        # Number of orders this day: 8-13, today gets a few more
        order_count = rng.randint(8, 13) if day_offset > 0 else rng.randint(10, 15)
        for _ in range(order_count):
            order_id = 2000 + day_offset * 100 + rng.randint(1, 99)
            # Pick a service hour in UTC so date(created_at, '+8 hours') lands on the
            # intended service day. For historical days use the normal lunch/dinner
            # windows (Beijing 11-14 and 17-21). For today, only generate orders in
            # already-passed hours (Beijing 08-10) so the dashboard never shows
            # paid orders for times that haven't happened yet.
            if day_offset == 0:
                hour_utc = rng.choice([0, 0, 1, 1, 2])  # Beijing 08:00-10:00, already passed
            elif rng.random() < 0.45:
                hour_utc = rng.randint(3, 6)  # Beijing 11:00-14:00
            else:
                hour_utc = rng.randint(9, 13)  # Beijing 17:00-21:00
            minute = rng.choice([0, 15, 30, 45])
            order_time = datetime.combine(service_day, time(hour_utc, minute), timezone.utc)
            created_at = order_time.strftime("%Y-%m-%d %H:%M:%S")

            phone, contact = rng.choice(customers)
            table_id = rng.randint(1, 6)
            is_paid = rng.random() < 0.92
            pay_status = "paid" if is_paid else "unpaid"
            paid_at = created_at if is_paid else None

            has_occurred = order_time <= now_utc
            if has_occurred:
                connection.execute(
                    "INSERT OR IGNORE INTO orders(order_id,customer_phone,contact_name,phone_number,table_id,order_type,status,payment_status,created_at,paid_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (order_id, phone, contact, phone, table_id, "dine_in",
                     "completed", pay_status, created_at, paid_at),
                )

            # 1-4 items per order, weighted so sides/drinks appear more often
            item_count = rng.randint(1, 4)
            chosen = rng.sample(dish_ids, k=min(item_count, len(dish_ids)))
            for did in chosen:
                qty = rng.choices([1, 2, 3], weights=[7, 2, 1])[0]
                line_id += 1
                if not has_occurred:
                    continue
                unit_price = dish_prices[did]
                total_price = round(unit_price * qty, 2)
                connection.execute(
                    "INSERT OR IGNORE INTO order_items(order_item_id,order_id,dish_id,quantity,unit_price,total_price,status) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (line_id, order_id, did, qty, unit_price, total_price, "served"),
                )


def ensure_database(reset: bool = False) -> Path:
    db_path=configured_db_path()
    if reset and db_path.exists():
        db_path.unlink()

    with sqlite_connection(db_path) as connection:
        create_schema(connection)
        seed_defaults(connection)
        connection.commit()

    return db_path


def database_summary() -> dict[str, int]:
    with get_connection() as connection:
        return {
            "staff": connection.execute("SELECT COUNT(*) FROM staff").fetchone()[0],
            "customers": connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
            "dining_tables": connection.execute("SELECT COUNT(*) FROM dining_tables").fetchone()[0],
            "dishes": connection.execute("SELECT COUNT(*) FROM dishes").fetchone()[0],
            "orders": connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "order_items": connection.execute("SELECT COUNT(*) FROM order_items").fetchone()[0],
        }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Initialize the SQLite database for the restaurant project.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the configured database file before recreating it.",
    )
    args = parser.parse_args(argv)

    try:
        db_path = ensure_database(reset=args.reset)
    except RuntimeError as exc:
        parser.exit(1, f"{exc}\n")
    summary = database_summary()
    print(f"SQLite database ready: {db_path}")
    print(f"Initialized at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    for table_name, row_count in summary.items():
        print(f"- {table_name}: {row_count}")
    print(f"Reset mode: {'on' if args.reset else 'off'}")
    print("Default login password for seeded users: 123456")


if __name__ == "__main__":
    main()
