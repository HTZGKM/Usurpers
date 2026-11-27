"""A telephone contact is not account ownership: customers explicitly consent."""
from time import time

from restaurant.db.database import begin_write, get_connection, insert_id
from .common import ServiceError, positive_int
from .phone_identity import normalize_phone

TARGETS = {"booking": ("bookings", "booking_id"), "visit": ("dining_sessions", "visit_id"), "queue": ("waiting_queue", "queue_id")}


def _target(db, kind, identifier):
    if kind not in TARGETS:
        raise ServiceError("Choose a reservation, visit or waitlist ticket.", field="target_type")
    table, key = TARGETS[kind]
    row = db.execute(f"SELECT * FROM {table} WHERE {key}=?", (positive_int(identifier, "target_id"),)).fetchone()
    if not row:
        raise ServiceError("The requested record no longer exists.", 404)
    return dict(row)


def _linkable(kind, row):
    eligible = {"booking": {"booked", "arrived", "transferred"}, "visit": {"seated"}, "queue": {"waiting", "called"}}
    if row["status"] not in eligible[kind]:
        raise ServiceError("This record is no longer available for account linking.", 409, code="LINK_UNAVAILABLE")


def _request(db, kind, target_id, candidate_phone, actor):
    phone = normalize_phone(candidate_phone)
    row = _target(db, kind, target_id)
    _linkable(kind, row)
    if row.get("customer_phone"):
        raise ServiceError("This record already belongs to an account.", 409, code="LINK_UNAVAILABLE")
    if not db.execute("SELECT 1 FROM customers WHERE customer_phone=? AND is_active=1", (phone,)).fetchone():
        raise ServiceError("No active account matches this phone number. The front desk can continue without linking.", 404, code="ACCOUNT_NOT_FOUND")
    now = int(time())
    db.execute("UPDATE account_link_requests SET status='expired',resolved_at=? WHERE status='pending' AND expires_at<=?", (now, now))
    previous = db.execute("""SELECT link_id FROM account_link_requests
                             WHERE target_type=? AND target_id=? AND candidate_phone=? AND status='pending'""",
                          (kind, target_id, phone)).fetchone()
    if previous:
        return {"link_id": previous["link_id"], "status": "pending"}
    link_id = insert_id(db, """INSERT INTO account_link_requests(target_type,target_id,candidate_phone,requested_by,created_at,expires_at)
                              VALUES(?,?,?,?,?,?)""", (kind, target_id, phone, actor, now, now + 24 * 3600), "link_id")
    return {"link_id": link_id, "status": "pending"}


def request_booking_link(db, booking_id, candidate_phone, requested_by_actor):
    return _request(db, "booking", booking_id, candidate_phone, requested_by_actor)


def request_link(kind, target_id, candidate_phone, actor):
    with get_connection() as db:
        begin_write(db)
        return _request(db, kind, positive_int(target_id,"target_id"), candidate_phone, actor)


def pending_links(phone):
    now = int(time())
    with get_connection() as db:
        requests = db.execute("SELECT * FROM account_link_requests WHERE candidate_phone=? AND status='pending' AND expires_at>? ORDER BY created_at", (phone, now)).fetchall()
        result = []
        for request in requests:
            try:
                target = _target(db, request["target_type"], request["target_id"])
                _linkable(request["target_type"], target)
            except ServiceError:
                continue
            # No contact information, order details or table assignment before consent.
            result.append({"link_id": request["link_id"], "target_type": request["target_type"],
                           "party_size": target["party_size"], "booking_date": str(target.get("booking_date") or ""),
                           "arrival_at": str(target.get("arrival_at") or ""), "version": target.get("version"),
                           "expires_at": request["expires_at"]})
        return result


def resolve_link(link_id, phone, action, expected_version=None):
    if action not in {"confirm", "decline"}:
        raise ServiceError("Choose confirm or decline.", 400)
    now = int(time())
    with get_connection() as db:
        begin_write(db)
        request = db.execute("SELECT * FROM account_link_requests WHERE link_id=? AND candidate_phone=?",
                             (positive_int(link_id,"link_id"), phone)).fetchone()
        if not request:
            raise ServiceError("Link request not found.", 404)
        desired = "confirmed" if action == "confirm" else "declined"
        if request["status"] == desired:
            return {"status": desired, "already_resolved": True}
        if request["status"] != "pending" or request["expires_at"] <= now:
            raise ServiceError("This link request is no longer active.", 409, code="LINK_UNAVAILABLE")
        if action == "confirm":
            kind, target_id = request["target_type"], request["target_id"]
            row = _target(db, kind, target_id)
            _linkable(kind, row)
            if row.get("customer_phone") and row["customer_phone"] != phone:
                raise ServiceError("This record already belongs to another account.", 409, code="LINK_UNAVAILABLE")
            bid = target_id if kind == "booking" else row.get("source_booking_id" if kind == "queue" else "booking_id")
            if kind in {"booking", "queue"} and (expected_version is None or positive_int(expected_version,"expected_version") != row.get("version")):
                raise ServiceError("The reservation or waitlist ticket changed. Review the latest request before confirming.",
                                   409, code="BOOKING_CHANGED" if kind == "booking" else "QUEUE_CHANGED")
            from .allocation import assert_can_link_booking
            assert_can_link_booking(db, bid, phone)
            table, key = TARGETS[kind]
            db.execute(f"UPDATE {table} SET customer_phone=? WHERE {key}=?", (phone, target_id))
            if bid:
                db.execute("UPDATE bookings SET customer_phone=?,version=version+1 WHERE booking_id=?", (phone, bid))
                db.execute("UPDATE orders SET customer_phone=?,version=version+1 WHERE booking_id=?", (phone, bid))
                db.execute("UPDATE dining_sessions SET customer_phone=? WHERE booking_id=?", (phone, bid))
                booking = _target(db, "booking", bid)
                queue_id = booking.get("transferred_queue_id")
                if queue_id:
                    db.execute("UPDATE waiting_queue SET customer_phone=?,version=version+1 WHERE queue_id=?", (phone, queue_id))
            if kind == "visit":
                db.execute("UPDATE orders SET customer_phone=?,version=version+1 WHERE visit_id=? AND customer_phone IS DISTINCT FROM ?", (phone, target_id, phone))
            elif kind == "queue":
                if not bid:
                    db.execute("UPDATE waiting_queue SET version=version+1 WHERE queue_id=?", (target_id,))
                db.execute("UPDATE orders SET customer_phone=?,version=version+1 WHERE queue_id=? AND customer_phone IS DISTINCT FROM ?", (phone, target_id, phone))
            db.execute("""UPDATE account_link_requests SET status='expired',resolved_at=?
                          WHERE target_type=? AND target_id=? AND status='pending' AND link_id<>?""",
                       (now, kind, target_id, link_id))
        db.execute("UPDATE account_link_requests SET status=?,resolved_at=? WHERE link_id=?", (desired, now, link_id))
        return {"status": desired, "already_resolved": False}
