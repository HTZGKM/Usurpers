from __future__ import annotations

import argparse
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PACKAGE_DIR / "data"
DB_PATH = DATA_DIR / "shuangfen.db"


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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
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
            password TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS customers (
            customer_phone TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            password TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dining_tables (
            table_id INTEGER PRIMARY KEY,
            capacity INTEGER NOT NULL CHECK (capacity > 0)
        );

        CREATE TABLE IF NOT EXISTS dishes (
            dish_id INTEGER PRIMARY KEY,
            dish_name TEXT NOT NULL UNIQUE,
            price NUMERIC NOT NULL CHECK (price >= 0),
            is_available INTEGER NOT NULL DEFAULT 1 CHECK (is_available IN (0, 1))
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
            PRIMARY KEY (order_id, dish_id),
            FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
            FOREIGN KEY (dish_id) REFERENCES dishes(dish_id)
        );
        """
    )


def seed_defaults(connection: sqlite3.Connection) -> None:
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


def ensure_database(reset: bool = False) -> Path:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()

    with get_connection() as connection:
        create_schema(connection)
        seed_defaults(connection)
        connection.commit()

    return DB_PATH


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
