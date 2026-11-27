from contextlib import closing
from hashlib import sha256
from hmac import compare_digest
from secrets import token_urlsafe
from time import time

from werkzeug.security import check_password_hash, generate_password_hash

from restaurant.db.database import begin_write, get_connection, hash_password
from .phone_identity import normalize_phone
from .common import ServiceError


SESSION_SECONDS = 12 * 60 * 60


def _token_hash(token):
    return sha256(token.encode("utf-8")).hexdigest()


def password_matches(stored, password):
    if not isinstance(password, str):
        return False
    return compare_digest(stored, hash_password(password)) if "$" not in stored else check_password_hash(stored, password)


def assert_current_actor_active(db):
    """Recheck the authenticated actor after acquiring the shared write lock.

    Public login/recovery and workers have no authenticated request actor. Staff
    acting for a disabled customer are checked as staff, not as that customer.
    """
    from flask import g, has_request_context, session

    if not has_request_context() or not getattr(g, "account", None):
        return
    token = session.get("session_token")
    row = db.execute("""SELECT COALESCE(s.email,c.customer_phone) AS username,
                        COALESCE(s.role,'customer') AS role,COALESCE(s.is_active,c.is_active) AS is_active
                        FROM web_sessions w LEFT JOIN staff s USING(staff_id)
                        LEFT JOIN customers c ON c.customer_phone=w.customer_phone
                        WHERE w.token_hash=? AND w.expires_at>?""",
                     (_token_hash(token) if token else "", int(time()))).fetchone()
    if not row or not row["is_active"] or row["role"] != g.account["role"] or row["username"] != g.account["username"]:
        raise ServiceError("Your account or session changed. Sign in again; contact the front desk if your account is inactive.",
                           403, code="ACCOUNT_INACTIVE")


def create_session(db, *, staff_id=None, customer_phone=None):
    token = token_urlsafe(32)
    now = int(time())
    db.execute("DELETE FROM web_sessions WHERE expires_at<=?", (now,))
    db.execute(
        "INSERT INTO web_sessions(token_hash,staff_id,customer_phone,expires_at) VALUES(?,?,?,?)",
        (_token_hash(token), staff_id, customer_phone, now + SESSION_SECONDS),
    )
    return token


def sign_in(account, password, previous_token=None):
    staff = "@" in account
    if not staff:
        try:
            account = normalize_phone(account)
        except ServiceError:
            return None
    # These identifiers are selected by the server. Account values are bound parameters.
    table, key, lookup = ("staff", "staff_id", "email") if staff else (
        "customers", "customer_phone", "customer_phone"
    )
    with closing(get_connection()) as db:
        member = db.execute(
            f"SELECT {key},password_hash FROM {table} WHERE {lookup}=? AND is_active=1",
            (account.lower() if staff else account,),
        ).fetchone()
    if member is None:
        return None
    stored = member["password_hash"]
    legacy = "$" not in stored
    valid = password_matches(stored, password)
    if not valid:
        return None
    replacement = generate_password_hash(password) if legacy else None
    identity = member[key]
    with get_connection() as db:
        begin_write(db)
        current = db.execute(
            f"SELECT password_hash FROM {table} WHERE {key}=? AND is_active=1",
            (identity,),
        ).fetchone()
        if current is None or current["password_hash"] != stored:
            return None
        if replacement is not None:
            db.execute(f"UPDATE {table} SET password_hash=? WHERE {key}=?", (replacement, identity))
        if previous_token:
            db.execute("DELETE FROM web_sessions WHERE token_hash=?", (_token_hash(previous_token),))
        return create_session(db, **{key: identity})


def session_account(token):
    if not token:
        return None
    with closing(get_connection()) as db:
        account = db.execute(
            """SELECT COALESCE(staff.email, customers.customer_phone) AS username,
                      COALESCE(staff.name, customers.name) AS name,
                      COALESCE(staff.role, 'customer') AS role,
                      COALESCE(staff.is_active, customers.is_active) AS is_active
               FROM web_sessions
               LEFT JOIN staff USING(staff_id)
               LEFT JOIN customers ON customers.customer_phone=web_sessions.customer_phone
               WHERE token_hash=? AND expires_at>?""",
            (_token_hash(token), int(time())),
        ).fetchone()
        return dict(account) if account is not None else None


def revoke_session(token):
    if token:
        with get_connection() as db:
            begin_write(db)
            db.execute("DELETE FROM web_sessions WHERE token_hash=?", (_token_hash(token),))
