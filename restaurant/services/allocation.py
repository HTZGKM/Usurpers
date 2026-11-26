"""PostgreSQL reservation and table allocation, shared by all service entry points."""

from datetime import datetime, time, timedelta, timezone
import json

from psycopg.errors import ExclusionViolation, UniqueViolation

from restaurant.business_time import RESTAURANT_TIME
from restaurant.db.database import begin_read, begin_write, get_connection, insert_id, using_postgres
from . import submission
from .booking_service import TIME_SLOT_MAP, booking_conflict
from .common import ServiceError, clock_time, phone_number, positive_int, required_text, valid_date


SERVICE_WINDOWS = ((time(11), time(14)), (time(17), time(21)))
ARRIVAL_GRACE = timedelta(minutes=10)
EARLY_ARRIVAL = timedelta(minutes=15)
ONLINE_LEAD = timedelta(minutes=30)
CALL_HOLD = timedelta(minutes=1)
OFFER_HOLD = timedelta(minutes=5)
CLEANING = timedelta(minutes=10)
TABLE_CONSTRAINTS = {"no_overlapping_table_holds", "uq_dining_active_table"}
TABLE_REASONS = {
    "disabled": "Table is out of service.",
    "capacity": "This table is too small for this party.",
    "occupied": "Guests are still dining at this table.",
    "cleaning": "This table is being cleared.",
    "reservation": "There is not enough time before a protected reservation.",
    "call": "This table is held for a called party.",
    "offer": "This table is being held as a replacement.",
    "reported": "A reserved party has arrived and is waiting for this table.",
    "replacement": "This table fits a checked-in reservation waiting for a replacement.",
    "closed": "There is not enough service time left for this party.",
}


def enabled(db=None):
    if not using_postgres():
        return False
    if db is not None:
        return db.execute("SELECT to_regclass('reservation_schema_versions') IS NOT NULL").fetchone()[0]
    with get_connection() as connection:
        return enabled(connection)


def legacy_write_guard(db):
    if enabled(db):
        raise ServiceError("Refresh this page to use the new reservation workflow.", 409, code="RESERVATION_REFRESH")


def database_now(db):
    epoch = db.execute("SELECT extract(epoch FROM clock_timestamp())").fetchone()[0]
    return datetime.fromtimestamp(epoch, timezone.utc)


def timestamp(value):
    if value is None:
        return None
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def at_local(day, clock):
    return datetime.combine(datetime.fromisoformat(day).date(), clock, RESTAURANT_TIME)


def service_cutoff(value):
    local = value.astimezone(RESTAURANT_TIME)
    return next((datetime.combine(local.date(), end, RESTAURANT_TIME)
                 for start, end in SERVICE_WINDOWS if start <= local.time() < end), None)


def protection(size):
    return timedelta(minutes=45 if size <= 2 else 60 if size <= 4 else 75) + CLEANING


def arrival_times():
    return [f"{minute // 60:02d}:{minute % 60:02d}"
            for start, end in SERVICE_WINDOWS
            for minute in range(start.hour * 60, end.hour * 60, 15)]


def booking_interval(day, arrival, size, now, online):
    day = valid_date(day)
    arrival = clock_time(arrival, "arrival_time")
    start = at_local(day, time.fromisoformat(arrival))
    if start.date() < now.astimezone(RESTAURANT_TIME).date():
        raise ServiceError("Select today or a future dining date.", code="BOOKING_DATE_IN_PAST")
    if start < now + (ONLINE_LEAD if online else timedelta()):
        message = "Book at least 30 minutes ahead." if online else "Choose a future arrival time."
        raise ServiceError(message, code="ARRIVAL_TOO_SOON")
    deadline = start + ARRIVAL_GRACE
    end = deadline + protection(size)
    cutoff = service_cutoff(start)
    if arrival not in arrival_times() or cutoff is None or end > cutoff:
        raise ServiceError("Choose a 15-minute arrival time that leaves enough time before the end of service.",
                           field="arrival_time", code="OUTSIDE_SERVICE")
    return start, deadline, end


def conflict(reason="reservation"):
    return ServiceError(TABLE_REASONS.get(reason, "This table and arrival time are no longer available."),
                        409, "table_id", "TABLE_UNAVAILABLE")


def _table(db, table_id):
    row = db.execute("SELECT * FROM dining_tables WHERE table_id=?", (table_id,)).fetchone()
    if row is None:
        raise ServiceError("Table not found.", 404, code="NOT_FOUND")
    return row


def _required_seats(ticket):
    return max(ticket["party_size"], ticket["table_type"] or 0)


def _table_reason(db, table, size, start, end, now, *, immediate=False, booking_id=None, queue_id=None,
                  check_waiting=True):
    if table["is_disabled"]:
        return "disabled"
    if table["capacity"] < size:
        return "capacity"
    table_id = table["table_id"]
    occupied = db.execute("""SELECT seated_at,party_size FROM dining_sessions
        WHERE table_id=? AND status IN ('seated','waiting') LIMIT 1""", (table_id,)).fetchone()
    if occupied:
        seated = timestamp(occupied["seated_at"])
        projected = seated + protection(occupied["party_size"]) if seated else None
        if immediate or (start.date() == now.astimezone(RESTAURANT_TIME).date()
                         and (projected is None or projected <= now or projected > start)):
            return "occupied"
    closed_at = db.execute("SELECT max(closed_at) FROM dining_sessions WHERE table_id=?", (table_id,)).fetchone()[0]
    if closed_at and timestamp(closed_at) + CLEANING > start:
        return "cleaning"
    holds = db.execute("""SELECT h.kind FROM table_holds h LEFT JOIN bookings b ON b.booking_id=h.booking_id
        WHERE h.table_id=? AND h.protected_during && tstzrange(?, ?, '[)')
        AND (CAST(? AS integer) IS NULL OR h.booking_id IS DISTINCT FROM ?)
        AND (CAST(? AS integer) IS NULL OR h.queue_id IS DISTINCT FROM ?)
        AND (h.expires_at IS NULL OR h.expires_at >= ?)
        AND (b.arrival_deadline IS NULL OR b.arrival_deadline >= ? OR b.checked_in_at IS NOT NULL)
        ORDER BY lower(h.protected_during) LIMIT 1""",
        (table_id, start, end, booking_id, booking_id, queue_id, queue_id, now, now)).fetchone()
    if holds:
        return holds["kind"]
    if check_waiting:
        reported = db.execute("""SELECT b.party_size FROM bookings b WHERE b.table_id=? AND b.status='booked'
            AND b.checked_in_at IS NOT NULL AND b.booking_date=?
            AND (CAST(? AS integer) IS NULL OR b.booking_id<>?) ORDER BY b.checked_in_at LIMIT 1""",
            (table_id, now.astimezone(RESTAURANT_TIME).date(), booking_id, booking_id)).fetchone()
        if reported and (immediate or start < now + protection(reported["party_size"])):
            return "reported"
    return None


def _add_hold(db, table_id, kind, start, end, *, booking_id=None, queue_id=None, expires_at=None):
    db.execute("""INSERT INTO table_holds(table_id,kind,booking_id,queue_id,protected_during,expires_at)
        VALUES(?,?,?,?,tstzrange(?,?,'[)'),?)""", (table_id, kind, booking_id, queue_id, start, end, expires_at))


def _pending_tickets(db):
    return db.execute("SELECT * FROM waiting_queue WHERE status='waiting' ORDER BY queue_position,queue_id").fetchall()


def _call_next(db, table, now):
    cutoff = service_cutoff(now)
    if cutoff is None or table["table_id"] in _replacement_priorities(db, now):
        return None
    until = now + CALL_HOLD
    for ticket in _pending_tickets(db):
        size = _required_seats(ticket)
        end = until + protection(size)
        if end > cutoff or _table_reason(db, table, size, now, end, now, immediate=True):
            continue
        db.execute("""UPDATE waiting_queue SET status='called',called_at=(?::timestamptz AT TIME ZONE 'UTC'),
            called_table_id=?,call_expires_at=? WHERE queue_id=? AND status='waiting'""",
            (now, table["table_id"], until, ticket["queue_id"]))
        _add_hold(db, table["table_id"], "call", now, end, queue_id=ticket["queue_id"], expires_at=until)
        return dict(queue_id=ticket["queue_id"], table_id=table["table_id"], status="called",
                    call_expires_at=until.isoformat())
    return None


def _call_tables(db, table_ids, now):
    tables = [_table(db, table_id) for table_id in sorted(set(table_ids)) if table_id is not None]
    calls = []
    for table in sorted(tables, key=lambda row: (row["capacity"], row["table_id"])):
        called = _call_next(db, table, now)
        if called is not None:
            calls.append(called)
    return calls


def _cancel_unseated_preorders(db, booking_id, now):
    orders = db.execute("""UPDATE orders SET status='cancelled'
        WHERE booking_id=? AND visit_id IS NULL AND order_type='preorder' AND status='active'
        AND payment_status='unpaid' AND NOT EXISTS(SELECT 1 FROM order_items i WHERE i.order_id=orders.order_id
            AND i.status IN ('cooking','ready','served')) RETURNING order_id""", (booking_id,)).fetchall()
    for order in orders:
        db.execute("UPDATE order_items SET status='cancelled' WHERE order_id=? AND status='waiting'", (order[0],))
        db.execute("""UPDATE kitchen_queue SET status='cancelled',completed_at=(?::timestamptz AT TIME ZONE 'UTC')
            WHERE order_id=? AND status='waiting'""", (now, order[0]))


def _reconcile(db, now):
    released = set()
    for row in db.execute("""UPDATE bookings SET status='no_show',no_show_at=?,ready_at=NULL,ready_table_id=NULL,
            offered_table_id=NULL,offer_expires_at=NULL,version=version+1
        WHERE status='booked' AND checked_in_at IS NULL AND arrival_deadline < ?
        RETURNING booking_id,table_id""", (now, now)).fetchall():
        holds = db.execute("DELETE FROM table_holds WHERE booking_id=? RETURNING table_id", (row["booking_id"],)).fetchall()
        _cancel_unseated_preorders(db, row["booking_id"], now)
        released.update(hold["table_id"] for hold in holds)
        released.add(row["table_id"])
    for row in db.execute("""UPDATE waiting_queue SET status='expired',ended_at=?
        WHERE status='called' AND call_expires_at < ? RETURNING queue_id,called_table_id""", (now, now)).fetchall():
        db.execute("DELETE FROM table_holds WHERE queue_id=?", (row["queue_id"],))
        released.add(row["called_table_id"])
    for row in db.execute("""UPDATE bookings SET offered_table_id=NULL,offer_expires_at=NULL,version=version+1
        WHERE status='booked' AND offer_expires_at < ? RETURNING booking_id""", (now,)).fetchall():
        hold = db.execute("DELETE FROM table_holds WHERE booking_id=? AND kind='offer' RETURNING table_id",
                          (row["booking_id"],)).fetchone()
        if hold:
            released.add(hold["table_id"])
    for row in db.execute("""UPDATE dining_sessions SET clearance_processed_at=?
        WHERE status='closed' AND clearance_processed_at IS NULL
        AND closed_at <= (?::timestamptz AT TIME ZONE 'UTC')
        RETURNING table_id""", (now, now - CLEANING)).fetchall():
        released.add(row["table_id"])
    return _call_tables(db, released, now)


def _run(work, *, write=True):
    if not using_postgres():
        raise ServiceError("The new reservation workflow is unavailable.", 503, code="RESERVATION_UPGRADE")
    with get_connection() as db:
        begin_write(db)
        state = db.execute("SELECT writes_enabled FROM reservation_schema_versions WHERE version=2").fetchone() if enabled(db) else None
        if not state or not state["writes_enabled"]:
            if write:
                raise ServiceError("Reservations are temporarily read-only. Please try again shortly.", 503,
                                   code="RESERVATION_UPGRADE")
            if not state:
                raise ServiceError("The new reservation workflow is unavailable.", 503, code="RESERVATION_UPGRADE")
        now = database_now(db)
        if state["writes_enabled"]:
            _reconcile(db, now)
        outcome = None
        try:
            with db.transaction():
                result = work(db, now)
        except ServiceError as error:
            outcome = error
        except (ExclusionViolation, UniqueViolation) as error:
            if error.diag.constraint_name not in TABLE_CONSTRAINTS:
                raise
            outcome = conflict()
    if outcome:
        raise outcome
    return result


def _booking(db, booking_id, owner=None):
    row = db.execute("SELECT * FROM bookings WHERE booking_id=?", (booking_id,)).fetchone()
    if not row or (owner and row["customer_phone"] != owner):
        raise ServiceError("Reservation not found.", 404, code="NOT_FOUND")
    return row


def _schedule_start(row):
    return timestamp(row["arrival_at"]) or at_local(row["booking_date"], time.fromisoformat(row["time_slot"][:5]))


def preorder_time(db, booking):
    now = database_now(db)
    if _visible(booking, now)["phase"] not in ("reserved", "ready", "waiting_to_seat"):
        raise ServiceError("This reservation is no longer open for preorders.", 409, code="STATE_CONFLICT")
    return _schedule_start(booking).astimezone(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")


def _visible(row, now):
    data = dict(row)
    source = timestamp(row["arrival_at"])
    data["arrival_time"] = source.astimezone(RESTAURANT_TIME).strftime("%H:%M") if source else None
    data["arrival_label"] = data["arrival_time"] or row["time_slot"]
    deadline = timestamp(row["arrival_deadline"])
    data["deadline_label"] = deadline.astimezone(RESTAURANT_TIME).strftime("%H:%M") if deadline else None
    if row["status"] == "arrived":
        data["phase"] = "seated"
    elif row["status"] != "booked":
        data["phase"] = row["status"]
    elif row["checked_in_at"]:
        data["phase"] = ("arrival_unresolved" if row["booking_date"] != now.astimezone(RESTAURANT_TIME).date().isoformat()
                         else "ready" if row["ready_at"] else "waiting_to_seat")
    elif deadline and deadline < now:
        data["phase"] = "no_show"
    elif not deadline and row["booking_date"] < now.astimezone(RESTAURANT_TIME).date().isoformat():
        data["phase"] = "past"
    else:
        data["phase"] = "ready" if row["ready_at"] else "reserved"
    data["can_check_in"] = (row["status"] == "booked" and not row["checked_in_at"] and deadline is not None
                            and now.astimezone(RESTAURANT_TIME).date().isoformat() == row["booking_date"]
                            and _schedule_start(row) - (EARLY_ARRIVAL if source else timedelta()) <= now <= deadline)
    data["can_customer_edit"] = (row["status"] == "booked" and not row["checked_in_at"]
                                 and data["phase"] in ("reserved", "ready"))
    return data


def _customer_for_phone(db, phone):
    return db.execute("SELECT customer_phone FROM customers WHERE customer_phone=? AND is_active=1", (phone,)).fetchone()


def _booking_table(db, size, start, end, now, table_id, booking_id=None):
    tables = [_table(db, table_id)] if table_id else db.execute(
        "SELECT * FROM dining_tables ORDER BY capacity,table_id").fetchall()
    replacements = _replacement_priorities(db, now)
    for table in tables:
        reason = _table_reason(db, table, size, start, end, now, booking_id=booking_id)
        replacement = replacements.get(table["table_id"])
        if reason is None and replacement and replacement[0] != booking_id and start < replacement[1]:
            reason = "replacement"
        if reason is None:
            return table["table_id"]
        if table_id:
            raise conflict(reason)
    raise conflict()


def _legacy_slot(fields):
    raw = str(fields.get("time_slot_id") or "")
    return TIME_SLOT_MAP.get(raw, raw)


def create_booking(fields, user):
    online = user["role"] == "customer"
    owner = user["username"] if online else None
    date = valid_date(fields.get("booking_date"))
    size = positive_int(fields.get("party_size"), "party_size")
    table_id = positive_int(fields["table_id"], "table_id") if fields.get("table_id") else None
    arrival = fields.get("arrival_time")
    raw_key = fields.get("idempotency_key")
    request_key = required_text(raw_key, "idempotency_key", limit=80) if online or raw_key else None
    request_fields = json.dumps([date, arrival or _legacy_slot(fields), size, table_id], separators=(",", ":"))
    name = user["name"] if online else required_text(fields.get("contact_name"), "contact_name", limit=100)
    phone = owner if online else phone_number(fields.get("phone_number"))
    actor = user["role"] + ":" + user["username"]
    staff_payload = [date, arrival, size, table_id, name, phone]

    def create(db, now):
        if not online:
            recovered = submission.replay(db, "staff-booking", actor, request_key, staff_payload)
            if recovered is not None:
                return recovered
        previous = db.execute("""SELECT * FROM booking_create_requests
            WHERE customer_phone=? AND request_key=?""", (owner, request_key)).fetchone() if online else None
        if previous:
            if previous["request_fields"] != request_fields:
                raise ServiceError("This submission key was used with different reservation details.", 409,
                                   code="IDEMPOTENCY_KEY_REUSED")
            return dict(booking_id=previous["booking_id"], table_id=previous["initial_table_id"], status="booked", version=1)
        if not arrival:
            legacy_write_guard(db)
        start, deadline, end = booking_interval(date, arrival, size, now, online)
        selected = _booking_table(db, size, start, end, now, table_id)
        customer = _customer_for_phone(db, phone)
        booking_id = insert_id(db, """INSERT INTO bookings(contact_name,phone_number,customer_phone,
            booking_date,time_slot,party_size,table_id,arrival_at,arrival_deadline)
            VALUES(?,?,?,?,?,?,?,?,?)""", (name, phone, customer[0] if customer else None, date,
            f"{arrival}-{end:%H:%M}", size, selected, start, deadline), "booking_id")
        _add_hold(db, selected, "reservation", start, end, booking_id=booking_id)
        if online and request_key:
            db.execute("""INSERT INTO booking_create_requests(customer_phone,request_key,request_fields,booking_id,initial_table_id)
                VALUES(?,?,?,?,?)""", (owner, request_key, request_fields, booking_id, selected))
        result = dict(booking_id=booking_id, table_id=selected, status="booked", version=1)
        return result if online else submission.record(db, "staff-booking", actor, request_key, staff_payload, result)

    return _run(create)


def update_booking(booking_id, fields, owner=None):
    version = positive_int(fields.get("expected_version"), "expected_version")
    size = positive_int(fields.get("party_size"), "party_size")
    table_id = positive_int(fields["table_id"], "table_id") if fields.get("table_id") else None
    date, arrival = fields.get("booking_date"), fields.get("arrival_time")

    def update(db, now):
        old = _booking(db, booking_id, owner)
        if old["version"] != version or old["status"] != "booked":
            raise booking_conflict()
        if old["checked_in_at"]:
            raise ServiceError("This party has already arrived. Use the seating actions.", 409, code="STATE_CONFLICT")
        start, deadline, end = booking_interval(date, arrival, size, now, bool(owner))
        selected = _booking_table(db, size, start, end, now, table_id, booking_id)
        released = db.execute("DELETE FROM table_holds WHERE booking_id=? RETURNING table_id", (booking_id,)).fetchall()
        db.execute("""UPDATE bookings SET booking_date=?,time_slot=?,party_size=?,table_id=?,arrival_at=?,arrival_deadline=?,
            ready_at=NULL,ready_table_id=NULL,offered_table_id=NULL,offer_expires_at=NULL,table_consent_at=NULL,version=version+1
            WHERE booking_id=? AND version=?""",
            (date, f"{arrival}-{end:%H:%M}", size, selected, start, deadline, booking_id, version))
        _add_hold(db, selected, "reservation", start, end, booking_id=booking_id)
        db.execute("""UPDATE orders SET table_id=? WHERE booking_id=? AND order_type='preorder'
            AND visit_id IS NULL AND status='active'""", (selected, booking_id))
        db.execute("""UPDATE order_items SET estimated_ready_at=(?::timestamptz AT TIME ZONE 'UTC')
            WHERE status='waiting' AND order_id IN (SELECT order_id FROM orders WHERE booking_id=?
                AND order_type='preorder' AND visit_id IS NULL AND status='active')""", (start, booking_id))
        _call_tables(db, (row["table_id"] for row in released), now)
        return _visible(_booking(db, booking_id), now)

    return _run(update)


def cancel_booking(booking_id, owner=None):
    def cancel(db, now):
        row = _booking(db, booking_id, owner)
        if row["status"] != "booked" or (owner and row["checked_in_at"]):
            raise ServiceError("This reservation can no longer be cancelled here.", 409, code="STATE_CONFLICT")
        if db.execute("""SELECT 1 FROM orders JOIN order_items USING(order_id)
            WHERE booking_id=? AND order_type='preorder' AND orders.status<>'cancelled'
            AND (payment_status='paid' OR order_items.status IN ('cooking','ready','served'))""", (booking_id,)).fetchone():
            raise ServiceError("A paid or started preorder needs to be resolved first.", 409, code="STATE_CONFLICT")
        db.execute("""UPDATE bookings SET status='cancelled',version=version+1,ready_at=NULL,ready_table_id=NULL,
            offered_table_id=NULL,offer_expires_at=NULL WHERE booking_id=?""", (booking_id,))
        hold = db.execute("DELETE FROM table_holds WHERE booking_id=? RETURNING table_id", (booking_id,)).fetchall()
        _cancel_unseated_preorders(db, booking_id, now)
        _call_tables(db, (entry["table_id"] for entry in hold), now)
        return dict(booking_id=booking_id, status="cancelled")

    return _run(cancel)


def set_booking_phase(booking_id, action, fields):
    def change(db, now):
        row = _booking(db, booking_id)
        if row["status"] != "booked":
            raise booking_conflict()
        table_id = row["table_id"]
        if action == "arrive":
            if fields.get("table_id"):
                legacy_write_guard(db)
            if row["checked_in_at"]:
                return _visible(row, now)
            if not _visible(row, now)["can_check_in"]:
                raise ServiceError("This reservation is outside its check-in window.", 409, code="ARRIVAL_WINDOW")
            db.execute("UPDATE bookings SET checked_in_at=?,version=version+1 WHERE booking_id=?", (now, booking_id))
            return _visible(_booking(db, booking_id), now)

        if action in ("offer", "accept_offer"):
            version = positive_int(fields.get("expected_version"), "expected_version")
            if version != row["version"]:
                raise booking_conflict()
            if action == "offer":
                replacement = positive_int(fields.get("table_id"), "table_id")
                if replacement == table_id:
                    raise ServiceError("Choose a different table.", field="table_id")
                old_offer = db.execute("""DELETE FROM table_holds WHERE booking_id=? AND kind='offer'
                    RETURNING table_id""", (booking_id,)).fetchone()
                until = now + OFFER_HOLD
                end = _booking_seat_check(db, row, replacement, now, offer_until=until)
                _add_hold(db, replacement, "offer", now, end, booking_id=booking_id, expires_at=until)
                db.execute("""UPDATE bookings SET offered_table_id=?,offer_expires_at=?,version=version+1
                    WHERE booking_id=?""", (replacement, until, booking_id))
                if old_offer and old_offer["table_id"] != replacement:
                    _call_tables(db, [old_offer["table_id"]], now)
            else:
                if fields.get("customer_agreed") != "true":
                    raise ServiceError("Confirm the guest has agreed to change tables.", field="customer_agreed")
                replacement = row["offered_table_id"]
                if not replacement:
                    raise booking_conflict()
                end = _booking_seat_check(db, row, replacement, now)
                db.execute("DELETE FROM table_holds WHERE booking_id=?", (booking_id,))
                _add_hold(db, replacement, "reservation", now, end, booking_id=booking_id)
                db.execute("""UPDATE bookings SET table_id=?,ready_table_id=NULL,ready_at=NULL,table_consent_at=?,
                    offered_table_id=NULL,offer_expires_at=NULL,version=version+1 WHERE booking_id=?""",
                    (replacement, now, booking_id))
                db.execute("UPDATE orders SET table_id=? WHERE booking_id=? AND visit_id IS NULL AND order_type='preorder'",
                           (replacement, booking_id))
                _call_tables(db, [table_id], now)
            return _visible(_booking(db, booking_id), now)

        if action == "seat" and (not row["checked_in_at"] or not row["ready_at"] or row["ready_table_id"] != table_id):
            raise ServiceError("Record arrival and confirm the reserved table is ready first.", 409, code="TABLE_NOT_READY")
        if (row["version"] != positive_int(fields.get("expected_version"), "expected_version")
                or table_id != positive_int(fields.get("table_id"), "table_id")):
            raise booking_conflict()
        _booking_seat_check(db, row, table_id, now)
        if action == "ready":
            db.execute("UPDATE bookings SET ready_at=?,ready_table_id=?,version=version+1 WHERE booking_id=?",
                       (now, table_id, booking_id))
            return _visible(_booking(db, booking_id), now)
        db.execute("UPDATE bookings SET status='arrived',version=version+1,offered_table_id=NULL,offer_expires_at=NULL WHERE booking_id=?",
                   (booking_id,))
        offered = row["offered_table_id"]
        db.execute("DELETE FROM table_holds WHERE booking_id=?", (booking_id,))
        visit = _insert_visit(db, now, row, table_id, booking_id=booking_id)
        db.execute("""UPDATE orders SET visit_id=?,table_id=? WHERE booking_id=? AND order_type='preorder'
            AND visit_id IS NULL AND status<>'cancelled'""", (visit["visit_id"], table_id, booking_id))
        _call_tables(db, [offered], now)
        return visit

    return _run(change)


def _booking_seat_check(db, row, table_id, now, *, offer_until=None):
    start = _schedule_start(row)
    deadline = timestamp(row["arrival_deadline"])
    local = now.astimezone(RESTAURANT_TIME)
    earliest = start - (EARLY_ARRIVAL if row["arrival_at"] else timedelta())
    if not table_id or not deadline or local.date().isoformat() != row["booking_date"] or now < earliest:
        raise ServiceError("This reservation is outside its seating window.", 409, code="ARRIVAL_WINDOW")
    cutoff = service_cutoff(start)
    end = ((max(now, deadline, offer_until or now) + protection(row["party_size"]))
           if row["arrival_at"] else max(deadline, (offer_until or now) + protection(row["party_size"])))
    # An existing reservation may be served late, while its actual seating still protects later promises.
    if row["arrival_at"] and cutoff is not None and end > cutoff:
        end = max(cutoff, now + protection(row["party_size"]))
    reason = _table_reason(db, _table(db, table_id), row["party_size"], now, end, now,
                           immediate=True, booking_id=row["booking_id"])
    if reason:
        raise conflict(reason)
    return end


def _replacement_priorities(db, now):
    date = now.astimezone(RESTAURANT_TIME).date()
    arrivals = db.execute("""SELECT * FROM bookings WHERE status='booked' AND booking_date=? AND checked_in_at IS NOT NULL
        AND offered_table_id IS NULL ORDER BY checked_in_at,booking_id""", (date,)).fetchall()
    if not arrivals:
        return {}
    tables = db.execute("SELECT * FROM dining_tables WHERE NOT is_disabled ORDER BY capacity,table_id").fetchall()
    priorities = {}
    for booking in arrivals:
        try:
            _booking_seat_check(db, booking, booking["table_id"], now)
            continue
        except ServiceError:
            pass
        for table in tables:
            table_id = table["table_id"]
            if table_id == booking["table_id"] or table_id in priorities or table["capacity"] < booking["party_size"]:
                continue
            try:
                end = _booking_seat_check(db, booking, table_id, now)
            except ServiceError:
                continue
            priorities[table_id] = (booking["booking_id"], end)
            break
    return priorities


def _insert_visit(db, now, party, table_id, *, booking_id=None, queue_id=None):
    visit_id = insert_id(db, """INSERT INTO dining_sessions(booking_id,queue_id,customer_phone,contact_name,
        phone_number,party_size,table_id,status,arrived_at,seated_at)
        VALUES(?,?,?,?,?,?,?,'seated',(?::timestamptz AT TIME ZONE 'UTC'),?)""",
        (booking_id, queue_id, party["customer_phone"], party["contact_name"], party["phone_number"],
         party["party_size"], table_id, now, now), "visit_id")
    return dict(visit_id=visit_id, booking_id=booking_id, queue_id=queue_id, table_id=table_id, status="seated")


def walk_in(table_id, size, name=None, phone=None, visit_id=None):
    def seat(db, now):
        party = db.execute("SELECT * FROM dining_sessions WHERE visit_id=? AND status='waiting'", (visit_id,)).fetchone() if visit_id else None
        if visit_id and not party:
            raise ServiceError("This visit has already changed.", 409, code="STATE_CONFLICT")
        count = party["party_size"] if party else positive_int(size, "party_size")
        table = _table(db, table_id)
        if _pending_tickets(db) and _call_next(db, table, now):
            return None
        end, cutoff = now + protection(count), service_cutoff(now)
        reason = ("closed" if cutoff is None or end > cutoff else
                  _table_reason(db, table, count, now, end, now, immediate=True))
        if reason is None and table_id in _replacement_priorities(db, now):
            reason = "replacement"
        if reason:
            raise conflict(reason)
        if visit_id:
            db.execute("UPDATE dining_sessions SET table_id=?,status='seated',seated_at=? WHERE visit_id=?",
                       (table_id, now, visit_id))
            return dict(visit_id=visit_id, table_id=table_id, status="seated")
        contact_name = required_text(name, "contact_name", limit=100) if name else None
        contact_phone = phone_number(phone) if phone else None
        account = _customer_for_phone(db, contact_phone) if contact_phone else None
        return _insert_visit(db, now, dict(party_size=count, contact_name=contact_name, phone_number=contact_phone,
                                          customer_phone=account[0] if account else None), table_id)

    visit = _run(seat)
    if visit is None:
        raise ServiceError("This table was held for a party already on the waitlist.", 409, code="WAITLIST_PRIORITY")
    return visit


def join_waitlist(size, name=None, phone=None, table_type=None):
    count = positive_int(size, "party_size")
    preference = positive_int(table_type, "table_type") if table_type else None
    contact_name = required_text(name, "contact_name", limit=100) if name else None
    contact_phone = phone_number(phone) if phone else None

    def join(db, now):
        if not db.execute("SELECT 1 FROM dining_tables WHERE capacity>=? AND NOT is_disabled",
                          (max(count, preference or 0),)).fetchone():
            raise conflict("capacity")
        if contact_phone and db.execute("""SELECT 1 FROM waiting_queue WHERE phone_number=?
            AND status IN ('waiting','called')""", (contact_phone,)).fetchone():
            raise ServiceError("This guest already has an active ticket.", 409, code="DUPLICATE")
        account = _customer_for_phone(db, contact_phone) if contact_phone else None
        position = db.execute("SELECT coalesce(max(queue_position),0)+1 FROM waiting_queue").fetchone()[0]
        ticket = insert_id(db, """INSERT INTO waiting_queue(party_size,contact_name,phone_number,customer_phone,
            table_type,queue_position) VALUES(?,?,?,?,?,?)""",
            (count, contact_name, contact_phone, account[0] if account else None, preference, position), "queue_id")
        return dict(queue_id=ticket, status="waiting")

    return _run(join)


def call_next(table_id):
    def call(db, now):
        table = _table(db, table_id)
        existing = db.execute("""SELECT queue_id,called_table_id AS table_id,status,call_expires_at
            FROM waiting_queue WHERE called_table_id=? AND status='called' AND call_expires_at>=?""",
            (table_id, now)).fetchone()
        return dict(existing) if existing else _call_next(db, table, now)

    return _run(call)


def finish_ticket(ticket_id, action, table_id=None):
    def finish(db, now):
        row = db.execute("SELECT * FROM waiting_queue WHERE queue_id=?", (ticket_id,)).fetchone()
        allowed = ("called",) if action in ("seat", "pass") else ("waiting", "called")
        if not row or row["status"] not in allowed:
            raise ServiceError("This waitlist ticket is no longer available.", 409, code="WAITLIST_CHANGED")
        called_table = row["called_table_id"]
        if action == "seat":
            if called_table != table_id or not row["call_expires_at"] or timestamp(row["call_expires_at"]) < now:
                raise ServiceError("The table call changed or expired.", 409, code="WAITLIST_CHANGED")
            reason = _table_reason(db, _table(db, table_id), _required_seats(row), now,
                                   now + protection(_required_seats(row)), now, immediate=True, queue_id=ticket_id)
            if reason:
                raise conflict(reason)
            status = "seated"
        else:
            status = "passed" if action == "pass" else "cancelled"
        db.execute("UPDATE waiting_queue SET status=?,ended_at=? WHERE queue_id=?", (status, now, ticket_id))
        db.execute("DELETE FROM table_holds WHERE queue_id=?", (ticket_id,))
        if action == "seat":
            return _insert_visit(db, now, row, table_id, queue_id=ticket_id)
        return dict(queue_id=ticket_id, status=status, next_queue=_call_tables(db, [called_table], now))

    return _run(finish)


def close_visit(visit_id):
    def close(db, now):
        visit = db.execute("SELECT * FROM dining_sessions WHERE visit_id=? AND status='seated'", (visit_id,)).fetchone()
        if not visit:
            raise ServiceError("This visit is no longer seated.", 409, code="STATE_CONFLICT")
        if db.execute("SELECT 1 FROM orders WHERE visit_id=? AND status<>'cancelled' AND payment_status<>'paid'",
                      (visit_id,)).fetchone():
            raise ServiceError("""Settle the visit's remaining orders before closing the table.""", 409,
                               code="STATE_CONFLICT")
        if db.execute("""SELECT 1 FROM orders JOIN order_items USING(order_id)
            WHERE visit_id=? AND order_items.status NOT IN ('served','cancelled') LIMIT 1""", (visit_id,)).fetchone():
            raise ServiceError("Serve all remaining dishes before closing the table.", 409, code="VISIT_UNFINISHED_ITEMS")
        db.execute("""UPDATE dining_sessions SET status='closed',closed_at=(?::timestamptz AT TIME ZONE 'UTC'),
            clearance_processed_at=NULL WHERE visit_id=?""", (now, visit_id))
        return dict(visit_id=visit_id, status="closed", next_queue=None)

    return _run(close)


def set_table_disabled(table_id, disabled):
    def update(db, now):
        _table(db, table_id)
        if disabled and db.execute("""SELECT 1 FROM dining_sessions WHERE table_id=? AND status IN ('seated','waiting')
            UNION ALL SELECT 1 FROM table_holds WHERE table_id=? LIMIT 1""", (table_id, table_id)).fetchone():
            raise ServiceError("Resolve the current visits and table holds before disabling this table.", 409, code="TABLE_IN_USE")
        db.execute("UPDATE dining_tables SET is_disabled=? WHERE table_id=?", (disabled, table_id))
        if not disabled:
            _call_tables(db, [table_id], now)
        return dict(table_id=table_id, is_disabled=disabled)

    return _run(update)


def available_tables(day, arrival, size, user, edit_id=None):
    online = user["role"] == "customer"
    count = positive_int(size, "party_size")
    day = valid_date(day)
    with get_connection() as db:
        begin_read(db)
        now = database_now(db)
        if edit_id:
            _booking(db, edit_id, user["username"] if online else None)
        choices = []
        for choice in arrival_times():
            try:
                booking_interval(day, choice, count, now, online)
                choices.append(choice)
            except ServiceError:
                continue
        rows = []
        if arrival in choices:
            start, _, end = booking_interval(day, arrival, count, now, online)
            replacements = _replacement_priorities(db, now)
            rows = [dict(table) for table in db.execute("SELECT * FROM dining_tables ORDER BY capacity,table_id")
                    if not _table_reason(db, table, count, start, end, now, booking_id=edit_id)
                    and (table["table_id"] not in replacements
                         or replacements[table["table_id"]][0] == edit_id or replacements[table["table_id"]][1] <= start)]
        return dict(times=choices, tables=rows, server_now=now.isoformat())


def _party_band(size):
    return 0 if size <= 2 else 1 if size <= 4 else 2


def _estimate_context(db, now):
    cutoff = service_cutoff(now)
    if cutoff is None:
        return None
    tables = [dict(row) for row in db.execute("SELECT * FROM dining_tables WHERE NOT is_disabled ORDER BY capacity,table_id")]
    samples = {band: [] for band in range(3)}
    for row in db.execute("""SELECT party_size,extract(epoch FROM ((closed_at AT TIME ZONE 'UTC') - seated_at))/60 AS minutes
            FROM dining_sessions WHERE status='closed' AND seated_at IS NOT NULL
            AND (closed_at AT TIME ZONE 'UTC')>seated_at ORDER BY closed_at DESC LIMIT 360"""):
        samples[_party_band(row["party_size"])].append(row["minutes"])
    occupied = {row["table_id"]: row for row in db.execute("""SELECT table_id,party_size,seated_at FROM dining_sessions
        WHERE table_id IS NOT NULL AND status IN ('seated','waiting')""")}
    cleaned = {row["table_id"]: timestamp(row["closed_at"]) + CLEANING for row in db.execute("""
        SELECT table_id,max(closed_at) AS closed_at FROM dining_sessions WHERE closed_at IS NOT NULL AND table_id IS NOT NULL
        GROUP BY table_id""")}
    holds = {}
    for row in db.execute("""SELECT h.table_id,h.booking_id,lower(h.protected_during) AS starts,upper(h.protected_during) AS ends
        FROM table_holds h LEFT JOIN bookings b ON b.booking_id=h.booking_id
        WHERE upper(h.protected_during)>? AND (h.expires_at IS NULL OR h.expires_at>=?)
        AND (b.arrival_deadline IS NULL OR b.checked_in_at IS NOT NULL OR b.arrival_deadline>=?)""", (now, now, now)):
        holds.setdefault(row["table_id"], []).append((timestamp(row["starts"]), timestamp(row["ends"]), row["booking_id"]))
    bookings = db.execute("""SELECT booking_id,party_size FROM bookings WHERE status='booked' AND checked_in_at IS NOT NULL
        AND booking_date=? ORDER BY checked_in_at,booking_id""", (now.astimezone(RESTAURANT_TIME).date(),)).fetchall()
    return tables, samples, occupied, cleaned, holds, bookings, _pending_tickets(db), cutoff


def _meal_minutes(samples, size, elapsed, upper):
    band = _party_band(size)
    historical = sorted(value for value in samples[band] if value > elapsed)
    if len(historical) >= 5:
        return historical[round((len(historical)-1) * (.75 if upper else .25))] - elapsed
    lower, high = ((25,40),(35,55),(45,70))[band]
    if elapsed >= high:
        return None
    return max(1, (high if upper else max(lower, elapsed + (high - elapsed) * .25)) - elapsed)


def _estimate(ctx, now, *, booking_id=None, queue_id=None):
    if ctx is None:
        return None
    tables, samples, occupied, cleaned, holds, bookings, waiters, cutoff = ctx
    parties = [(row["party_size"], row["booking_id"], None) for row in bookings]
    parties += [(_required_seats(row), None, row["queue_id"]) for row in waiters]
    estimates = []
    for upper in (False, True):
        open_at = {table["table_id"]: max(now, cleaned.get(table["table_id"], now)) for table in tables}
        for table_id, row in occupied.items():
            seated = timestamp(row["seated_at"])
            elapsed = max(0, (now - seated).total_seconds() / 60) if seated else None
            remaining = _meal_minutes(samples, row["party_size"], elapsed, upper) if elapsed is not None else None
            open_at[table_id] = now + timedelta(minutes=remaining) + CLEANING if remaining is not None else cutoff
        for size, owner, ticket in parties:
            duration = protection(size)
            candidates = []
            for table in tables:
                if table["capacity"] < size:
                    continue
                table_id = table["table_id"]
                start = open_at[table_id]
                for begin, end, held_for in sorted(holds.get(table_id, [])):
                    if owner and owner == held_for:
                        continue
                    if begin < start + duration and end > start:
                        start = end
                if start + duration <= cutoff:
                    candidates.append((start, table["capacity"], table_id))
            chosen = min(candidates, default=None)
            if (booking_id is not None and owner == booking_id) or (queue_id is not None and ticket == queue_id):
                estimates.append(chosen[0] if chosen else None)
                break
            if chosen:
                open_at[chosen[2]] = chosen[0] + timedelta(minutes=_meal_minutes(samples, size, 0, upper)) + CLEANING
    if len(estimates) != 2 or any(value is None for value in estimates):
        return None
    low, high = sorted(estimates)
    return dict(earliest_at=low.isoformat(), latest_at=high.isoformat())


def _bookings(db, now, *, owner=None, day=None, booking_id=None, staff=False):
    filters, args = [], []
    for column, value in (("customer_phone", owner), ("booking_date", day), ("booking_id", booking_id)):
        if value is not None:
            filters.append("b." + column + "=?")
            args.append(value)
    where = " WHERE " + " AND ".join(filters) if filters else ""
    rows = db.execute("""SELECT b.*,v.status AS visit_status,v.visit_id FROM bookings b
        LEFT JOIN dining_sessions v ON b.booking_id=v.booking_id""" + where +
        " ORDER BY b.booking_date,b.time_slot,b.booking_id", args).fetchall()
    estimates = _estimate_context(db, now) if any(row["checked_in_at"] and row["status"] == "booked" for row in rows) else None
    result = []
    for row in rows:
        data = _visible(row, now)
        if row["visit_status"] == "closed":
            data["phase"] = "closed"
        if ((staff or row["ready_at"]) and row["status"] == "booked"
                and (data["can_check_in"] or data["phase"] in ("ready", "waiting_to_seat"))):
            try:
                _booking_seat_check(db, row, row["table_id"], now)
            except ServiceError as error:
                if data["phase"] == "ready":
                    data["phase"] = "waiting_to_seat" if row["checked_in_at"] else "reserved"
                if staff:
                    data["table_note"] = error.message
            else:
                data["can_prepare"] = True
        if data["phase"] == "waiting_to_seat":
            data["estimate"] = _estimate(estimates, now, booking_id=row["booking_id"])
        result.append(data)
    return result


def customer_bookings(owner, booking_id=None):
    with get_connection() as db:
        begin_read(db)
        now = database_now(db)
        rows = _bookings(db, now, owner=owner, booking_id=booking_id)
        visit = db.execute("""SELECT visit_id,booking_id,table_id FROM dining_sessions
            WHERE customer_phone=? AND status='seated' ORDER BY COALESCE(seated_at,arrived_at AT TIME ZONE 'UTC') DESC LIMIT 1""",
            (owner,)).fetchone() if owner and booking_id is None else None
    if booking_id is not None:
        if not rows:
            raise ServiceError("Reservation not found.", 404, code="NOT_FOUND")
        return rows[0]
    return dict(bookings=rows, server_now=now.isoformat(), visit=dict(visit) if visit else None)


def reconcile_customer_order_deadlines(db, owner):
    if not enabled(db):
        return
    deadlines = db.execute("""SELECT b.arrival_deadline FROM orders o JOIN bookings b USING(booking_id)
        WHERE o.customer_phone=? AND o.visit_id IS NULL AND o.order_type='preorder' AND o.status='active'
        AND b.status='booked' AND b.checked_in_at IS NULL AND b.arrival_deadline IS NOT NULL""", (owner,)).fetchall()
    if deadlines:
        now = database_now(db)
        if any(timestamp(row[0]) < now for row in deadlines):
            _run(lambda connection, tick: None, write=False)


def table_projection(db, now):
    tables = []
    cutoff = service_cutoff(now)
    replacements = _replacement_priorities(db, now)
    for row in db.execute("SELECT * FROM dining_tables ORDER BY table_id"):
        end = now + protection(1)
        reason = _table_reason(db, row, 1, now, end, now, immediate=True)
        replacement = replacements.get(row["table_id"])
        if reason is None and replacement:
            reason = "replacement"
        if reason is None and (cutoff is None or end > cutoff):
            reason = "closed"
        upcoming = db.execute("""SELECT b.booking_id,b.arrival_at,b.time_slot,b.booking_date FROM bookings b
            JOIN table_holds h ON h.booking_id=b.booking_id AND h.kind='reservation'
            WHERE h.table_id=? AND b.status='booked' AND upper(h.protected_during)>?
            AND (b.checked_in_at IS NOT NULL OR b.arrival_deadline>=?)
            ORDER BY lower(h.protected_during) LIMIT 1""", (row["table_id"], now, now)).fetchone()
        next_booking = None
        if upcoming:
            next_booking = dict(upcoming)
            next_booking["label"] = (timestamp(upcoming["arrival_at"]).astimezone(RESTAURANT_TIME).strftime("%H:%M")
                                     if upcoming["arrival_at"] else upcoming["time_slot"])
        tables.append(dict(row, reason=reason, reason_text=TABLE_REASONS.get(reason),
                           next_booking=next_booking, replacement_for=replacement[0] if replacement else None,
                           status=("occupied" if reason == "occupied" else "disabled" if reason == "disabled"
                                   else "reserved" if reason else "available")))
    return tables


def desk_snapshot(day=None):
    _run(lambda db, now: None, write=False)
    with get_connection() as db:
        begin_read(db)
        now = database_now(db)
        local_day = now.astimezone(RESTAURANT_TIME).date().isoformat()
        date = valid_date(day) if day else local_day
        tickets = [dict(row) for row in db.execute("""SELECT * FROM waiting_queue
            WHERE status IN ('waiting','called') ORDER BY queue_position,queue_id""")]
        recent = [dict(row) for row in db.execute("""SELECT queue_id,status,called_table_id,ended_at FROM waiting_queue
            WHERE ended_at>=? AND status IN ('expired','passed','cancelled') ORDER BY ended_at DESC LIMIT 8""",
            (now-timedelta(minutes=10),))]
        context = _estimate_context(db, now) if tickets else None
        for index, ticket in enumerate(tickets):
            ticket["position"] = index + 1
            if ticket["status"] == "waiting":
                ticket["estimate"] = _estimate(context, now, queue_id=ticket["queue_id"])
        tables = table_projection(db, now)
        arrivals = db.execute("""SELECT count(*) FROM bookings WHERE booking_date=? AND status='booked'
            AND checked_in_at IS NULL AND arrival_deadline>=?""", (local_day, now)).fetchone()[0]
        return dict(bookings=_bookings(db, now, day=date, staff=True), queue=tickets, recent_tickets=recent, arrivals=arrivals,
                    tables=tables, server_now=now.isoformat(), service_date=local_day)

def timeline(first_day, last_day):
    start = at_local(valid_date(first_day), time())
    end = at_local(valid_date(last_day), time()) + timedelta(days=1)
    if not timedelta() < end - start <= timedelta(days=93):
        raise ServiceError("Choose a date range of at most 93 days.", field="end")
    with get_connection() as db:
        begin_read(db)
        now = database_now(db)
        bookings = [dict(row) for row in db.execute("""SELECT b.booking_id,b.booking_date,b.arrival_at,b.time_slot,
            b.table_id,b.party_size,CASE WHEN b.status='booked' AND b.checked_in_at IS NULL
                AND b.arrival_deadline<? THEN 'no_show' ELSE b.status END AS status,b.contact_name,b.checked_in_at,
            lower(h.protected_during) AS protected_start,upper(h.protected_during) AS protected_end
            FROM bookings b LEFT JOIN table_holds h ON h.booking_id=b.booking_id AND h.kind='reservation'
            WHERE b.booking_date>=? AND b.booking_date<? ORDER BY b.booking_date,b.time_slot,b.booking_id""",
            (now, first_day, end.date().isoformat()))]
        visits = [dict(row) for row in db.execute("""SELECT v.visit_id,v.booking_id,v.queue_id,v.table_id,v.party_size,
            v.status,v.contact_name,v.seated_at,v.arrived_at AT TIME ZONE 'UTC' AS recorded_at,
            v.closed_at AT TIME ZONE 'UTC' AS closed_at,b.arrival_at,b.time_slot AS legacy_reservation_window,
            b.booking_date AS reservation_date FROM dining_sessions v LEFT JOIN bookings b USING(booking_id)
            WHERE v.status IN ('seated','closed')
            AND COALESCE(v.seated_at,v.arrived_at AT TIME ZONE 'UTC')<?
            AND COALESCE(v.closed_at AT TIME ZONE 'UTC',?)>? ORDER BY COALESCE(v.seated_at,v.arrived_at AT TIME ZONE 'UTC')""",
            (end, now, start))]
        tables = [dict(row) for row in db.execute("SELECT * FROM dining_tables ORDER BY table_id")]
    return dict(bookings=bookings, visits=visits, tables=tables, server_now=now.isoformat())
