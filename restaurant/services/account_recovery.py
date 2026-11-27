"""Verified recovery email and single-use password reset, with real SMTP delivery."""
import hashlib
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from secrets import token_urlsafe
from time import time
from urllib.parse import urlencode, urlsplit

from werkzeug.security import generate_password_hash

from restaurant.db.database import begin_write, get_connection
from .common import ServiceError, required_text
from .phone_identity import normalize_phone
from .session_service import password_matches

VERIFY_SECONDS = 30 * 60
RESET_SECONDS = 15 * 60
SEND_COOLDOWN = 60
SEND_HOURLY_LIMIT = 5
GENERIC_RESET_MESSAGE = "If this account has a verified recovery email, a reset link has been requested. Check your inbox and spam folder. If no email arrives, wait before retrying or contact the restaurant."


def email_address(value):
    email = required_text(value, "email", limit=254).lower()
    if not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", email):
        raise ServiceError("Enter a valid email address.", field="email")
    return email


def validate_new_password(password):
    if not isinstance(password, str) or not password.strip() or not 6 <= len(password) <= 128:
        raise ServiceError("Use 6 to 128 characters; the password cannot contain only spaces.", field="password")
    return password


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def smtp_settings():
    host = os.environ.get("USURPERS_SMTP_HOST", "").strip()
    sender = os.environ.get("USURPERS_SMTP_FROM", "").strip()
    base = os.environ.get("USURPERS_PUBLIC_URL", "").rstrip("/")
    security = os.environ.get("USURPERS_SMTP_TLS", "starttls").lower()
    parsed = urlsplit(base)
    if not host or not sender or parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ServiceError("Email delivery is not configured. Contact the restaurant for help.", 503, code="EMAIL_UNAVAILABLE")
    if security not in {"starttls", "ssl"}:
        raise ServiceError("Email delivery is not configured correctly.", 503, code="EMAIL_UNAVAILABLE")
    try:
        port = int(os.environ.get("USURPERS_SMTP_PORT", "465" if security == "ssl" else "587"))
        sender = email_address(sender)
    except (ValueError, ServiceError):
        raise ServiceError("Email delivery is not configured correctly.", 503, code="EMAIL_UNAVAILABLE") from None
    user = os.environ.get("USURPERS_SMTP_USER", "")
    password = os.environ.get("USURPERS_SMTP_PASSWORD", "")
    if bool(user) != bool(password):
        raise ServiceError("Email delivery is not configured correctly.", 503, code="EMAIL_UNAVAILABLE")
    return dict(host=host, port=port, sender=sender, base=base, security=security, user=user, password=password)


def _send(settings, destination, purpose, token):
    route = "/auth/verify-email" if purpose == "verify_email" else "/auth/reset-password"
    url = settings["base"] + route + "?" + urlencode({"token": token})
    message = EmailMessage()
    message["From"] = settings["sender"]
    message["To"] = destination
    message["Subject"] = "Double Portion: " + ("verify recovery email" if purpose == "verify_email" else "reset your password")
    minutes = (VERIFY_SECONDS if purpose == "verify_email" else RESET_SECONDS) // 60
    message.set_content(f"Open this link to {'verify your recovery email' if purpose == 'verify_email' else 'reset your password'}:\n\n{url}\n\nThis single-use link expires in {minutes} minutes. If you did not request it, ignore this email.\n")
    try:
        cls = smtplib.SMTP_SSL if settings["security"] == "ssl" else smtplib.SMTP
        extra = {"context": ssl.create_default_context()} if settings["security"] == "ssl" else {}
        with cls(settings["host"], settings["port"], timeout=5, **extra) as server:
            if settings["security"] == "starttls":
                server.starttls(context=ssl.create_default_context())
            if settings["user"]:
                server.login(settings["user"], settings["password"])
            if server.send_message(message):
                raise ServiceError("The email could not be delivered. Try again later.", 503, code="EMAIL_UNAVAILABLE")
    except (OSError, smtplib.SMTPException):
        raise ServiceError("The email could not be delivered. Try again later.", 503, code="EMAIL_UNAVAILABLE") from None


def _reserve_send(db, key, now, *, cooldown=SEND_COOLDOWN, hourly_limit=SEND_HOURLY_LIMIT):
    key = _digest(key)
    row = db.execute("SELECT * FROM account_mail_limits WHERE limit_key=?", (key,)).fetchone()
    if row and (now - row["last_attempt_at"] < cooldown or
                (now - row["window_started_at"] < 3600 and row["attempts"] >= hourly_limit)):
        return False
    start = row["window_started_at"] if row and now - row["window_started_at"] < 3600 else now
    count = row["attempts"] + 1 if row and start == row["window_started_at"] else 1
    db.execute("""INSERT INTO account_mail_limits(limit_key,last_attempt_at,window_started_at,attempts)
                  VALUES(?,?,?,?) ON CONFLICT(limit_key) DO UPDATE SET
                  last_attempt_at=excluded.last_attempt_at,window_started_at=excluded.window_started_at,attempts=excluded.attempts""",
               (key, now, start, count))
    return True


def _issue(db, member, email, purpose, now):
    token = token_urlsafe(32)
    phone = member["customer_phone"]
    db.execute("UPDATE account_tokens SET consumed_at=? WHERE customer_phone=? AND purpose=? AND consumed_at IS NULL",
               (now, phone, purpose))
    db.execute("""INSERT INTO account_tokens(token_hash,customer_phone,purpose,email,password_fingerprint,created_at,expires_at)
                  VALUES(?,?,?,?,?,?,?)""",
               (_digest(token), phone, purpose, email, _digest(member["password_hash"]), now,
                now + (VERIFY_SECONDS if purpose == "verify_email" else RESET_SECONDS)))
    return token


def _deliver(settings, email, purpose, token):
    # The token and rate reservation are committed before network I/O. SMTP must
    # never hold the global restaurant write lock while other guests are booking.
    try:
        _send(settings, email, purpose, token)
    except ServiceError:
        # One atomic token-only update also works if the requester logged out
        # during SMTP delivery. It cannot invalidate a later concurrent request.
        with get_connection() as db:
            db.execute("UPDATE account_tokens SET consumed_at=? WHERE token_hash=? AND consumed_at IS NULL",
                       (int(time()), _digest(token)))
        raise


def profile(phone):
    with get_connection() as db:
        row = db.execute("""SELECT c.customer_phone,c.name,r.email,r.verified_at FROM customers c
                            LEFT JOIN customer_recovery r USING(customer_phone) WHERE c.customer_phone=?""", (phone,)).fetchone()
        if not row:
            raise ServiceError("Account not found.", 404)
        return dict(row)


def change_name(phone, name):
    name = required_text(name, "name", limit=100)
    with get_connection() as db:
        begin_write(db)
        if not db.execute("UPDATE customers SET name=? WHERE customer_phone=? AND is_active=1", (name, phone)).rowcount:
            raise ServiceError("This account is inactive.", 403, code="ACCOUNT_INACTIVE")
    return {"name": name}


def request_email_change(phone, email, current_password):
    email = email_address(email)
    settings = smtp_settings()
    now = int(time())
    with get_connection() as db:
        begin_write(db)
        member = db.execute("SELECT customer_phone,password_hash FROM customers WHERE customer_phone=? AND is_active=1", (phone,)).fetchone()
        if not member or not password_matches(member["password_hash"], current_password):
            raise ServiceError("The current password is incorrect.", 400, field="current_password")
        if not _reserve_send(db, "verify:" + phone, now):
            raise ServiceError("Wait at least one minute before requesting another email; at most five per hour.", 429, code="EMAIL_RATE_LIMIT")
        token = _issue(db, member, email, "verify_email", now)
    _deliver(settings, email, "verify_email", token)
    return {"message": "Verification email sent. Your existing recovery email stays active until the new address is verified."}


def request_password_reset(phone, requester):
    phone = normalize_phone(phone)
    settings = smtp_settings()  # Same failure for unknown and known accounts.
    now = int(time())
    delivery = None
    with get_connection() as db:
        begin_write(db)
        if not _reserve_send(db, "reset-source:" + requester, now, cooldown=1, hourly_limit=20):
            return {"message": GENERIC_RESET_MESSAGE}
        if not _reserve_send(db, "reset:" + phone, now):
            return {"message": GENERIC_RESET_MESSAGE}
        member = db.execute("""SELECT c.customer_phone,c.password_hash,r.email FROM customers c
                               JOIN customer_recovery r USING(customer_phone)
                               WHERE c.customer_phone=? AND c.is_active=1""", (phone,)).fetchone()
        if member:
            delivery = (member["email"], _issue(db, member, member["email"], "reset_password", now))
    if delivery:
        try:
            _deliver(settings, delivery[0], "reset_password", delivery[1])
        except ServiceError as error:
            if error.code != "EMAIL_UNAVAILABLE":
                raise
            # Preserve limits and avoid leaking account eligibility via SMTP.
            import logging
            logging.getLogger(__name__).warning("Password-reset SMTP delivery failed; request invalidated")
    return {"message": GENERIC_RESET_MESSAGE}


def _consume(db, raw_token, purpose, now):
    if not isinstance(raw_token, str) or not 32 <= len(raw_token) <= 128:
        raise ServiceError("This link is invalid or expired. Request a new email.", 400, code="TOKEN_INVALID")
    row = db.execute("""SELECT t.*,c.password_hash,c.is_active FROM account_tokens t
                        JOIN customers c USING(customer_phone) WHERE token_hash=? AND purpose=?""",
                     (_digest(raw_token), purpose)).fetchone()
    if not row or row["consumed_at"] is not None or row["expires_at"] <= now or not row["is_active"] or row["password_fingerprint"] != _digest(row["password_hash"]):
        raise ServiceError("This link is invalid or expired. Request a new email.", 400, code="TOKEN_INVALID")
    db.execute("UPDATE account_tokens SET consumed_at=? WHERE token_hash=? AND consumed_at IS NULL", (now, row["token_hash"]))
    return row


def verify_email(token):
    now = int(time())
    with get_connection() as db:
        begin_write(db)
        row = _consume(db, token, "verify_email", now)
        db.execute("""INSERT INTO customer_recovery(customer_phone,email,verified_at) VALUES(?,?,?)
                      ON CONFLICT(customer_phone) DO UPDATE SET email=excluded.email,
                      verified_at=excluded.verified_at,version=customer_recovery.version+1""",
                   (row["customer_phone"], row["email"], now))
        db.execute("UPDATE account_tokens SET consumed_at=? WHERE customer_phone=? AND purpose='reset_password' AND consumed_at IS NULL",
                   (now, row["customer_phone"]))
    return {"message": "Recovery email verified. This does not verify ownership of your phone number."}


def reset_password(token, password):
    password = validate_new_password(password)
    replacement = generate_password_hash(password)
    now = int(time())
    with get_connection() as db:
        begin_write(db)
        row = _consume(db, token, "reset_password", now)
        bound = db.execute("SELECT email FROM customer_recovery WHERE customer_phone=?", (row["customer_phone"],)).fetchone()
        if not bound or bound["email"] != row["email"]:
            raise ServiceError("This link is invalid or expired. Request a new email.", 400, code="TOKEN_INVALID")
        db.execute("UPDATE customers SET password_hash=? WHERE customer_phone=?", (replacement, row["customer_phone"]))
        db.execute("DELETE FROM web_sessions WHERE customer_phone=?", (row["customer_phone"],))
        db.execute("UPDATE account_tokens SET consumed_at=? WHERE customer_phone=? AND consumed_at IS NULL", (now, row["customer_phone"]))
    return {"message": "Password updated. Sign in again. Your reservations and orders are unchanged."}
