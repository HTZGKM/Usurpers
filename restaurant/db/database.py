from __future__ import annotations

import argparse
import hashlib
import sqlite3
import os
from datetime import datetime
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PACKAGE_DIR / "data"
DB_PATH = Path(os.environ.get("USURPERS_DB_PATH", DATA_DIR / "shuangfen.db"))


def configured_db_path() -> Path:
    """Resolve the database path at call time so test suites can isolate DBs."""
    return Path(os.environ.get("USURPERS_DB_PATH", DB_PATH))


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
        "password": hash_password("123456"),
    },
    {
        "staff_id": 2,
        "name": "前台小二",
        "role": "frontdesk",
        "phone": "13800000002",
        "email": "frontdesk@shuangfen.local",
        "password": hash_password("123456"),
    },
    {
        "staff_id": 3,
        "name": "后厨小刘",
        "role": "kitchen",
        "phone": "13800000003",
        "email": "kitchen@shuangfen.local",
        "password": hash_password("123456"),
    },
]

ALLOWED_STAFF_ROLES = {"admin", "frontdesk", "kitchen"}

DEFAULT_CUSTOMERS = [
    {
        "customer_phone": "13900000001",
        "name": "演示顾客",
        "password": hash_password("123456"),
    },
    {
        "customer_phone": "13900000002",
        "name": "测试顾客",
        "password": hash_password("123456"),
    },
    {
        "customer_phone": "18612345678",
        "name": "朱哥",
        "password": hash_password("111111"),
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
    {"dish_id": 1, "dish_name": "芝士牛肉堡", "price": 38.00, "is_available": 1},
    {"dish_id": 2, "dish_name": "双层招牌堡", "price": 46.00, "is_available": 1},
    {"dish_id": 3, "dish_name": "番茄芝麻菜披萨", "price": 62.00, "is_available": 1},
    {"dish_id": 4, "dish_name": "蘑菇白酱披萨", "price": 68.00, "is_available": 1},
    {"dish_id": 5, "dish_name": "炸薯条", "price": 16.00, "is_available": 1},
    {"dish_id": 6, "dish_name": "冰柠檬茶", "price": 14.00, "is_available": 1},
]

DEFAULT_ORDERS = [
    {
        "order_id": 1001,
        "created_at": "2026-10-28 18:00:00",
        "paid_at": "2026-10-28 18:05:00",
        "table_id": 3,
        "total_amount": 130.00,
        "customer_phone": "13900000001",
    }
]

DEFAULT_ORDER_ITEMS = [
    {
        "order_id": 1001,
        "dish_id": 1,
        "quantity": 1,
        "total_price": 38.00,
        "remarks": "少冰",
    },
    {
        "order_id": 1001,
        "dish_id": 3,
        "quantity": 1,
        "total_price": 62.00,
        "remarks": "薄底",
    },
    {
        "order_id": 1001,
        "dish_id": 6,
        "quantity": 2,
        "total_price": 28.00,
        "remarks": "正常糖",
    },
]


def get_connection() -> sqlite3.Connection:
    db_path=configured_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, factory=ClosingConnection, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS staff (
            staff_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1))
        );

        CREATE TABLE IF NOT EXISTS customers (
            customer_phone TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            password TEXT NOT NULL,
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

        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            paid_at TEXT,
            table_id INTEGER NOT NULL,
            total_amount NUMERIC NOT NULL CHECK (total_amount >= 0),
            customer_phone TEXT NOT NULL,
            FOREIGN KEY (table_id) REFERENCES dining_tables(table_id),
            FOREIGN KEY (customer_phone) REFERENCES customers(customer_phone)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            order_id INTEGER NOT NULL,
            dish_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            total_price NUMERIC NOT NULL CHECK (total_price >= 0),
            remarks TEXT,
            status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting','cooking','ready','served','cancelled')),
            PRIMARY KEY (order_id, dish_id),
            FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
            FOREIGN KEY (dish_id) REFERENCES dishes(dish_id)
        );

        CREATE TABLE IF NOT EXISTS time_slots (
            time_slot_id INTEGER PRIMARY KEY, label TEXT NOT NULL UNIQUE, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS bookings (
            booking_id INTEGER PRIMARY KEY AUTOINCREMENT, contact_name TEXT NOT NULL, phone_number TEXT NOT NULL,
            customer_phone TEXT,
            booking_date TEXT NOT NULL, time_slot_id INTEGER NOT NULL, party_size INTEGER NOT NULL CHECK(party_size > 0),
            status TEXT NOT NULL DEFAULT 'booked' CHECK(status IN ('booked','arrived','cancelled')),
            table_id INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(time_slot_id) REFERENCES time_slots(time_slot_id),
            FOREIGN KEY(table_id) REFERENCES dining_tables(table_id),
            FOREIGN KEY(customer_phone) REFERENCES customers(customer_phone)
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
        CREATE TABLE IF NOT EXISTS order_headers (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT, visit_id INTEGER, booking_id INTEGER, customer_phone TEXT,
            contact_name TEXT, phone_number TEXT, table_id INTEGER, order_type TEXT NOT NULL DEFAULT 'dine_in',
            status TEXT NOT NULL DEFAULT 'active', payment_status TEXT NOT NULL DEFAULT 'unpaid',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, paid_at TEXT,
            FOREIGN KEY(visit_id) REFERENCES dining_sessions(visit_id),
            FOREIGN KEY(booking_id) REFERENCES bookings(booking_id),
            FOREIGN KEY(customer_phone) REFERENCES customers(customer_phone)
        );
        CREATE TABLE IF NOT EXISTS order_lines (
            order_item_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, dish_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0), unit_price NUMERIC NOT NULL CHECK(unit_price >= 0),
            note TEXT, status TEXT NOT NULL DEFAULT 'waiting' CHECK(status IN ('waiting','cooking','ready','served','cancelled')),
            enqueued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            estimated_ready_at TEXT,
            FOREIGN KEY(order_id) REFERENCES order_headers(order_id) ON DELETE CASCADE,
            FOREIGN KEY(dish_id) REFERENCES dishes(dish_id)
        );
        CREATE TABLE IF NOT EXISTS table_reservations (
            booking_id INTEGER NOT NULL, table_id INTEGER NOT NULL,
            PRIMARY KEY(booking_id, table_id), FOREIGN KEY(booking_id) REFERENCES bookings(booking_id),
            FOREIGN KEY(table_id) REFERENCES dining_tables(table_id)
        );
        CREATE TABLE IF NOT EXISTS waiting_queue (
            queue_id INTEGER PRIMARY KEY AUTOINCREMENT, contact_name TEXT, phone_number TEXT,
            customer_phone TEXT, party_size INTEGER NOT NULL CHECK(party_size>0),
            table_type INTEGER, queue_position INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'waiting'
              CHECK(status IN ('waiting','called','seated','cancelled','expired')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, called_at TEXT,
            FOREIGN KEY(customer_phone) REFERENCES customers(customer_phone)
        );
        CREATE TABLE IF NOT EXISTS kitchen_queue (
            queue_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL,
            order_item_id INTEGER NOT NULL UNIQUE, dish_id INTEGER NOT NULL, quantity INTEGER NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0, estimated_ready_at TEXT,
            status TEXT NOT NULL DEFAULT 'waiting' CHECK(status IN ('waiting','cooking','ready','served','cancelled')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, started_at TEXT, completed_at TEXT,
            FOREIGN KEY(order_id) REFERENCES order_headers(order_id) ON DELETE CASCADE,
            FOREIGN KEY(order_item_id) REFERENCES order_lines(order_item_id) ON DELETE CASCADE,
            FOREIGN KEY(dish_id) REFERENCES dishes(dish_id)
        );
        CREATE TABLE IF NOT EXISTS payments (
            payment_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL UNIQUE,
            amount NUMERIC NOT NULL CHECK(amount>=0), paid_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(order_id) REFERENCES order_headers(order_id)
        );
        CREATE TABLE IF NOT EXISTS ingredients (
            ingredient_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            unit TEXT NOT NULL, on_hand REAL NOT NULL CHECK(on_hand>=0),
            reserved REAL NOT NULL DEFAULT 0 CHECK(reserved>=0 AND reserved<=on_hand),
            expires_at TEXT, is_available INTEGER NOT NULL DEFAULT 1 CHECK(is_available IN (0,1))
        );
        CREATE TABLE IF NOT EXISTS dish_ingredients (
            dish_id INTEGER NOT NULL, ingredient_id INTEGER NOT NULL,
            quantity_per_dish REAL NOT NULL CHECK(quantity_per_dish>0),
            PRIMARY KEY(dish_id,ingredient_id), FOREIGN KEY(dish_id) REFERENCES dishes(dish_id),
            FOREIGN KEY(ingredient_id) REFERENCES ingredients(ingredient_id)
        );
        CREATE TABLE IF NOT EXISTS inventory_reservations (
            order_item_id INTEGER NOT NULL, ingredient_id INTEGER NOT NULL, quantity REAL NOT NULL CHECK(quantity>0),
            status TEXT NOT NULL CHECK(status IN ('reserved','consumed','released')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(order_item_id,ingredient_id), FOREIGN KEY(order_item_id) REFERENCES order_lines(order_item_id),
            FOREIGN KEY(ingredient_id) REFERENCES ingredients(ingredient_id)
        );
        CREATE TABLE IF NOT EXISTS inventory_movements (
            movement_id INTEGER PRIMARY KEY AUTOINCREMENT, ingredient_id INTEGER NOT NULL,
            quantity REAL NOT NULL, movement_type TEXT NOT NULL, reference TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(ingredient_id) REFERENCES ingredients(ingredient_id)
        );
        CREATE TABLE IF NOT EXISTS remake_tickets (
            remake_id INTEGER PRIMARY KEY AUTOINCREMENT, order_item_id INTEGER NOT NULL,
            reason TEXT NOT NULL, staff_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'waiting'
              CHECK(status IN ('waiting','cooking','ready','completed','cancelled')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, started_at TEXT, completed_at TEXT,
            FOREIGN KEY(order_item_id) REFERENCES order_lines(order_item_id), FOREIGN KEY(staff_id) REFERENCES staff(staff_id)
        );
        CREATE TABLE IF NOT EXISTS refunds (
            refund_id INTEGER PRIMARY KEY AUTOINCREMENT, payment_id INTEGER NOT NULL, order_id INTEGER NOT NULL,
            amount NUMERIC NOT NULL CHECK(amount>0), reason TEXT NOT NULL, staff_id INTEGER NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(payment_id) REFERENCES payments(payment_id), FOREIGN KEY(order_id) REFERENCES order_headers(order_id),
            FOREIGN KEY(staff_id) REFERENCES staff(staff_id)
        );
        CREATE INDEX IF NOT EXISTS idx_bookings_slot ON bookings(booking_date,time_slot_id,status);
        CREATE INDEX IF NOT EXISTS idx_sessions_table_status ON dining_sessions(table_id,status);
        CREATE INDEX IF NOT EXISTS idx_order_lines_status_queue ON order_lines(status,enqueued_at);
        CREATE INDEX IF NOT EXISTS idx_order_headers_service_day ON order_headers(date(created_at, '+8 hours'));
        CREATE INDEX IF NOT EXISTS idx_order_headers_status ON order_headers(status);
        CREATE INDEX IF NOT EXISTS idx_kitchen_queue_order ON kitchen_queue(status,priority,estimated_ready_at,created_at);
        CREATE INDEX IF NOT EXISTS idx_waiting_queue_order ON waiting_queue(status,queue_position);
        """
    )
    # Migrate databases created before item-level kitchen tracking.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(order_items)")}
    if "status" not in columns:
        connection.execute("ALTER TABLE order_items ADD COLUMN status TEXT NOT NULL DEFAULT 'waiting'")
    for table, field, declaration in (
        ("bookings", "customer_phone", "TEXT REFERENCES customers(customer_phone)"),
        ("order_headers", "booking_id", "INTEGER REFERENCES bookings(booking_id)"),
        ("staff", "is_active", "INTEGER NOT NULL DEFAULT 1"),
        ("customers", "is_active", "INTEGER NOT NULL DEFAULT 1"),
        ("dishes", "is_archived", "INTEGER NOT NULL DEFAULT 0"),
        ("order_lines", "estimated_ready_at", "TEXT"),
        ("dishes", "ingredients", "TEXT NOT NULL DEFAULT ''"),
        ("dishes", "prep_time_minutes", "INTEGER NOT NULL DEFAULT 10"),
        ("dishes", "image_url", "TEXT"),
        ("dishes", "category", "TEXT"),
    ):
        known = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if field not in known:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {field} {declaration}")


def seed_defaults(connection: sqlite3.Connection) -> None:
    connection.executemany(
        "INSERT OR IGNORE INTO time_slots (time_slot_id,label,starts_at,ends_at) VALUES (?,?,?,?)",
        [(1, "午餐", "11:00", "14:00"), (2, "晚餐早段", "17:00", "19:00"), (3, "晚餐晚段", "19:00", "21:00")],
    )
    placeholders = ", ".join("?" for _ in ALLOWED_STAFF_ROLES)
    connection.execute(
        f"DELETE FROM staff WHERE role NOT IN ({placeholders})",
        tuple(ALLOWED_STAFF_ROLES),
    )
    connection.executemany(
        """
        INSERT OR IGNORE INTO staff (staff_id, name, role, phone, email, password)
        VALUES (:staff_id, :name, :role, :phone, :email, :password)
        """,
        DEFAULT_STAFF,
    )
    connection.executemany(
        """
        INSERT OR IGNORE INTO customers (customer_phone, name, password)
        VALUES (:customer_phone, :name, :password)
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
        INSERT OR IGNORE INTO dishes (dish_id, dish_name, price, is_available)
        VALUES (:dish_id, :dish_name, :price, :is_available)
        """,
        DEFAULT_DISHES,
    )
    # Stable demo records make the new booking/visit/order flows inspectable.
    connection.execute("INSERT OR IGNORE INTO bookings (booking_id,contact_name,phone_number,booking_date,time_slot_id,party_size,status,table_id,customer_phone) VALUES (1,'演示预约','13900000001','2026-12-01',1,2,'booked',1,'13900000001')")
    connection.execute("INSERT OR IGNORE INTO dining_sessions (visit_id,booking_id,customer_phone,contact_name,phone_number,party_size,table_id,status) VALUES (1,NULL,'13900000002','测试顾客','13900000002',2,2,'seated')")
    connection.execute("INSERT OR IGNORE INTO order_headers (order_id,visit_id,customer_phone,contact_name,phone_number,table_id,order_type,status,payment_status) VALUES (9001,1,'13900000002','测试顾客','13900000002',2,'dine_in','active','unpaid')")
    connection.execute("INSERT OR IGNORE INTO order_lines (order_item_id,order_id,dish_id,quantity,unit_price,note,status) VALUES (9001,9001,1,1,38,'演示：少酱','waiting'),(9002,9001,5,1,16,'演示：不加盐','cooking')")
    connection.execute("INSERT OR IGNORE INTO kitchen_queue(order_id,order_item_id,dish_id,quantity,status) VALUES (9001,9001,1,1,'waiting'),(9001,9002,5,1,'cooking')")
    connection.executemany(
        """
        INSERT OR IGNORE INTO orders (order_id, created_at, paid_at, table_id, total_amount, customer_phone)
        VALUES (:order_id, :created_at, :paid_at, :table_id, :total_amount, :customer_phone)
        """,
        DEFAULT_ORDERS,
    )
    connection.executemany(
        """
        INSERT OR IGNORE INTO order_items (order_id, dish_id, quantity, total_price, remarks)
        VALUES (:order_id, :dish_id, :quantity, :total_price, :remarks)
        """,
        DEFAULT_ORDER_ITEMS,
    )
    # One-time, idempotent bridge from the original sample order tables.
    connection.execute("""INSERT OR IGNORE INTO order_headers(order_id,customer_phone,table_id,status,payment_status,created_at,paid_at)
        SELECT order_id,customer_phone,table_id,'active',CASE WHEN paid_at IS NULL THEN 'unpaid' ELSE 'paid' END,created_at,paid_at FROM orders""")
    connection.execute("""INSERT INTO order_lines(order_id,dish_id,quantity,unit_price,note,status)
        SELECT oi.order_id,oi.dish_id,oi.quantity,oi.total_price/oi.quantity,oi.remarks,
        CASE WHEN o.paid_at IS NOT NULL THEN 'served' ELSE COALESCE(oi.status,'waiting') END
        FROM order_items oi JOIN orders o USING(order_id)
        WHERE NOT EXISTS (SELECT 1 FROM order_lines x WHERE x.order_id=oi.order_id AND x.dish_id=oi.dish_id AND x.quantity=oi.quantity AND x.unit_price=oi.total_price/oi.quantity)""")
    connection.execute("""INSERT OR IGNORE INTO kitchen_queue(order_id,order_item_id,dish_id,quantity,status)
        SELECT l.order_id,l.order_item_id,l.dish_id,l.quantity,l.status FROM order_lines l
        WHERE l.status IN ('waiting','cooking','ready','served')""")
    connection.execute("""INSERT OR IGNORE INTO payments(order_id,amount,paid_at)
        SELECT order_id,total_amount,paid_at FROM orders WHERE paid_at IS NOT NULL""")


def ensure_database(reset: bool = False) -> Path:
    db_path=configured_db_path()
    if reset and db_path.exists():
        db_path.unlink()

    with get_connection() as connection:
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
        help="Delete the existing shuangfen.db file before recreating it.",
    )
    args = parser.parse_args(argv)

    db_path = ensure_database(reset=args.reset)
    summary = database_summary()
    print(f"SQLite database ready: {db_path}")
    print(f"Initialized at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    for table_name, row_count in summary.items():
        print(f"- {table_name}: {row_count}")
    print(f"Reset mode: {'on' if args.reset else 'off'}")
    print("Default login password for seeded users: 123456")


if __name__ == "__main__":
    main()
