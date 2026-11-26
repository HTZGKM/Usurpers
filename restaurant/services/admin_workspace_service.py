from datetime import datetime, timedelta, timezone

from restaurant.db.database import begin_read, get_connection, using_postgres
from restaurant.services.common import valid_date


RESTAURANT_TIME = timezone(timedelta(hours=8))
SALES_HISTORY_DAYS = 30


def _order_rows(db, condition="", values=()):
    headers = [
        dict(row, items=[])
        for row in db.execute(
            f"""SELECT h.order_id, h.table_id, h.created_at, h.status, h.payment_status
                FROM orders h {condition}
                ORDER BY h.created_at DESC, h.order_id DESC""",
            values,
        )
    ]
    orders = {order["order_id"]: order for order in headers}
    for row in db.execute(
        f"""SELECT l.order_id, l.dish_id, l.quantity, l.unit_price, l.note, l.status,
                   d.dish_name, d.category, q.status AS queue_status, q.completed_at AS ready_at
            FROM orders h
            JOIN order_items l ON l.order_id = h.order_id
            JOIN dishes d ON d.dish_id = l.dish_id
            LEFT JOIN kitchen_queue q ON q.order_item_id = l.order_item_id
            {condition}
            ORDER BY l.order_item_id""",
        values,
    ):
        orders[row["order_id"]]["items"].append(dict(row))
    return headers


def get_ledger(day):
    with get_connection() as db:
        begin_read(db)
        if not day:
            return _order_rows(db)
        return _order_rows(
            db, f"WHERE {_service_day_sql('h.created_at')} = ?", (valid_date(day, "date"),)
        )


def _service_day_sql(column):
    if using_postgres():
        return f"to_char({column} + INTERVAL '8 hours', 'YYYY-MM-DD')"
    return f"date({column}, '+8 hours')"


def get_workspace():
    from restaurant.services import allocation
    from restaurant.services.queue_manager import QueueManager

    QueueManager.enqueue_due_preorders()
    now = datetime.now(RESTAURANT_TIME)
    today = now.date()
    first_day = today - timedelta(days=SALES_HISTORY_DAYS - 1)
    with get_connection() as db:
        begin_read(db)
        orders = _order_rows(
            db,
            f"""WHERE {_service_day_sql('h.created_at')} BETWEEN ? AND ?
                     OR h.status = 'active'""",
            (first_day.isoformat(), today.isoformat()),
        )
        days = [
            row[0]
            for row in db.execute(
                f"SELECT DISTINCT {_service_day_sql('created_at')} AS service_day FROM orders "
                "WHERE created_at IS NOT NULL ORDER BY service_day DESC"
            )
        ]
        tables = allocation.table_projection(db, allocation.database_now(db)) if allocation.enabled(db) else [
            dict(row)
            for row in db.execute("SELECT table_id, capacity FROM dining_tables ORDER BY table_id")
        ]
        bookings = [
            dict(row)
            for row in db.execute(
                """SELECT b.*, substr(b.time_slot,1,5) AS starts_at, substr(b.time_slot,7,5) AS ends_at
                   FROM bookings b
                   WHERE b.status IN ('booked', 'arrived')
                   ORDER BY b.booking_date, b.time_slot, b.booking_id"""
            )
        ]
        visits = [
            dict(row)
            for row in db.execute(
                """SELECT visit_id, booking_id, table_id, party_size, contact_name,
                          phone_number, arrived_at
                   FROM dining_sessions WHERE status = 'seated' ORDER BY arrived_at"""
            )
        ]
    return {
        "service_date": today.isoformat(),
        "service_time": now.strftime("%H:%M"),
        "service_windows": [[start.strftime("%H:%M"), end.strftime("%H:%M")]
                            for start, end in allocation.SERVICE_WINDOWS],
        "history_days": SALES_HISTORY_DAYS,
        "orders": orders,
        "order_days": days,
        "tables": tables,
        "bookings": bookings,
        "visits": visits,
    }
