"""Shared validation and JSON-friendly service errors."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass
class ServiceError(ValueError):
    message: str
    status_code: int = 400
    field: str | None = None
    code: str = "VALIDATION_ERROR"

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"ok": False, "success": False, "error": self.code, "message": self.message}
        if self.field:
            body["field"] = self.field
        return body


def required_text(value: Any, field: str, *, limit: int = 200) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ServiceError(f"{field}不能为空。", field=field)
    value = value.strip()
    if len(value) > limit:
        raise ServiceError(f"{field}不能超过{limit}个字符。", field=field)
    return value


def positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not (isinstance(value, int) or (isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value.strip()))):
        raise ServiceError(f"{field}必须是正整数。", field=field)
    result = int(value)
    if result < 1:
        raise ServiceError(f"{field}必须是正整数。", field=field)
    return result


def valid_date(value: Any, field: str = "booking_date") -> str:
    value = required_text(value, field, limit=10)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ServiceError("日期格式必须为 YYYY-MM-DD。", field=field) from exc
    if parsed.isoformat() != value:
        raise ServiceError("日期格式必须为 YYYY-MM-DD。", field=field)
    return value


def money(value: Any, field: str = "price") -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ServiceError("金额格式不正确。", field=field) from exc
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
        raise ServiceError("金额必须大于 0 且最多两位小数。", field=field)
    return amount.quantize(Decimal("0.01"))


def clock_time(value: Any, field: str = "time") -> str:
    value = required_text(value, field, limit=5)
    if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
        raise ServiceError("时间格式必须为 HH:MM。", field=field)
    return value


def date_time(value: Any, field: str = "estimated_ready_at") -> str:
    value=required_text(value,field,limit=32)
    try: parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as exc: raise ServiceError("时间必须是 ISO 日期时间格式。",field=field) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.isoformat(sep=" ", timespec="seconds")


def enum_value(value: Any, choices: set[str] | tuple[str, ...], field: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ServiceError(f"{field}取值不合法。", field=field)
    return value


def phone_number(value: Any, field: str = "phone_number") -> str:
    phone = required_text(value, field, limit=20)
    if not re.fullmatch(r"\+?[0-9 -]{7,20}", phone):
        raise ServiceError("手机号格式不正确。", field=field)
    return phone


def order_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ServiceError("订单至少需要一道菜。", field="items")
    validated = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ServiceError("菜品明细格式不正确。", field=f"items[{index}]")
        dish_id = positive_int(item.get("dish_id"), f"items[{index}].dish_id")
        quantity = positive_int(item.get("quantity"), f"items[{index}].quantity")
        note = item.get("note", item.get("remarks", ""))
        if not isinstance(note, str) or len(note) > 200:
            raise ServiceError("备注不能超过200个字符。", field=f"items[{index}].note")
        validated.append({"dish_id": dish_id, "quantity": quantity, "note": note.strip()})
    return validated
