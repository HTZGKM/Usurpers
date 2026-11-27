"""One canonical phone identifier for registration, sign-in and staff contacts."""
import re

from .common import ServiceError


def normalize_phone(value, field="phone_number"):
    if not isinstance(value, str):
        raise ServiceError("Enter a valid phone number.", field=field)
    raw = value.strip()
    if not raw or len(raw) > 32 or not re.fullmatch(r"[+0-9 ()-]+", raw):
        raise ServiceError("Use digits, spaces, brackets or hyphens for the phone number.", field=field)
    phone = re.sub(r"[ ()-]", "", raw)
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if phone.startswith("+86") and re.fullmatch(r"1[3-9][0-9]{9}", phone[3:]):
        phone = phone[3:]
    if re.fullmatch(r"1[3-9][0-9]{9}", phone):
        return phone
    if re.fullmatch(r"\+[1-9][0-9]{6,14}", phone):
        return phone
    raise ServiceError("Enter an 11-digit mainland mobile number or an international number starting with + and country code.", field=field)
