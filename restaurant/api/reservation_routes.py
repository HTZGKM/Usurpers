"""Time-point reservation API, enabled by the PostgreSQL migration."""

from flask import Blueprint, g, jsonify, request

from restaurant.forms import ActionForm
from restaurant.route_utils import require_api_role, validated_data
from restaurant.services import allocation
from restaurant.services.common import ServiceError, positive_int

reservation_bp = Blueprint("reservation", __name__)
GUEST = "/reservation-api"
DESK = "/frontdesk/reservation-api"
ADMIN = "/admin/reservation-api"


@reservation_bp.before_request
def access():
    roles = ("admin",) if request.path.startswith(ADMIN) else (
        ("frontdesk", "admin") if request.path.startswith(DESK) else ("customer",))
    denied = require_api_role(*roles)
    if denied is not None:
        return denied
    if not allocation.enabled():
        raise ServiceError("The new reservation workflow is unavailable.", 503, code="RESERVATION_UPGRADE")
    if request.method == "POST":
        validated_data(ActionForm)
    return None


@reservation_bp.get(GUEST + "/available")
@reservation_bp.get(DESK + "/available")
def available():
    edit_id = request.args.get("booking_id")
    return jsonify(ok=True, **allocation.available_tables(
        request.args.get("date"), request.args.get("arrival_time"), request.args.get("party_size"),
        g.account, positive_int(edit_id, "booking_id") if edit_id else None))


@reservation_bp.post(GUEST + "/bookings")
@reservation_bp.post(DESK + "/bookings")
def create():
    return jsonify(ok=True, booking=allocation.create_booking(request.form, g.account)), 201


@reservation_bp.get(GUEST + "/bookings")
def bookings():
    return jsonify(ok=True, **allocation.customer_bookings(g.account["username"]))


@reservation_bp.get(GUEST + "/bookings/<int:booking_id>")
@reservation_bp.get(DESK + "/bookings/<int:booking_id>")
def booking(booking_id):
    owner = g.account["username"] if g.account["role"] == "customer" else None
    return jsonify(ok=True, booking=allocation.customer_bookings(owner, booking_id))


@reservation_bp.post(GUEST + "/bookings/<int:booking_id>/edit")
@reservation_bp.post(DESK + "/bookings/<int:booking_id>/edit")
def edit(booking_id):
    owner = g.account["username"] if g.account["role"] == "customer" else None
    return jsonify(ok=True, booking=allocation.update_booking(booking_id, request.form, owner, g.account["role"] + ":" + g.account["username"]))


@reservation_bp.post(GUEST + "/bookings/<int:booking_id>/cancel")
@reservation_bp.post(DESK + "/bookings/<int:booking_id>/cancel")
def cancel(booking_id):
    owner = g.account["username"] if g.account["role"] == "customer" else None
    return jsonify(ok=True, booking=allocation.cancel_booking(booking_id, owner, request.form.get("expected_version")))


@reservation_bp.get(DESK + "/snapshot")
def snapshot():
    return jsonify(ok=True, **allocation.desk_snapshot(request.args.get("date")))


@reservation_bp.post(DESK + "/bookings/<int:booking_id>/<action>")
def booking_action(booking_id, action):
    if action not in {"arrive", "ready", "seat", "offer", "accept_offer"}:
        raise ServiceError("Reservation action not found.", 404, code="NOT_FOUND")
    data = allocation.set_booking_phase(booking_id, action, request.form, g.account["role"] + ":" + g.account["username"])
    return (jsonify(ok=True, visit=data), 201) if action == "seat" else jsonify(ok=True, booking=data)


@reservation_bp.post(DESK + "/walk-ins")
def walk_in():
    return jsonify(ok=True, visit=allocation.walk_in(
        positive_int(request.form.get("table_id"), "table_id"), request.form.get("party_size"),
        request.form.get("contact_name"), request.form.get("phone_number"))), 201


@reservation_bp.post(DESK + "/tickets")
def join():
    user = g.account
    return jsonify(ok=True, queue=allocation.join_waitlist(
        request.form.get("party_size"), request.form.get("contact_name"), request.form.get("phone_number"),
        request.form.get("table_type"), actor=user["role"] + ":" + user["username"],
        request_key=request.form.get("idempotency_key"))), 201


@reservation_bp.post(DESK + "/tables/<int:table_id>/call")
def call(table_id):
    return jsonify(ok=True, queue=allocation.call_next(table_id))


@reservation_bp.post(DESK + "/tables/<int:table_id>/disabled")
def disable(table_id):
    value = request.form.get("disabled")
    if value not in ("true", "false"):
        raise ServiceError("Choose whether the table is out of service.", field="disabled")
    return jsonify(ok=True, table=allocation.set_table_disabled(table_id, value == "true"))


@reservation_bp.post(DESK + "/tickets/<int:ticket_id>/<action>")
def ticket_action(ticket_id, action):
    if action not in {"cancel", "pass", "seat"}:
        raise ServiceError("Ticket action not found.", 404, code="NOT_FOUND")
    table = positive_int(request.form.get("table_id"), "table_id") if action == "seat" else None
    data = allocation.finish_ticket(ticket_id, action, table, request.form.get("expected_version"))
    return (jsonify(ok=True, visit=data), 201) if action == "seat" else jsonify(ok=True, queue=data)


@reservation_bp.get(ADMIN + "/timeline")
def timeline():
    return jsonify(ok=True, **allocation.timeline(request.args.get("start"), request.args.get("end")))


@reservation_bp.post(DESK + "/bookings/<int:booking_id>/party-size")
def party_size(booking_id):
    return jsonify(ok=True, booking=allocation.change_party_size(
        booking_id, request.form, g.account["role"] + ":" + g.account["username"]))


@reservation_bp.post(DESK + "/bookings/<int:booking_id>/transfer-to-waitlist")
def transfer(booking_id):
    return jsonify(ok=True, transfer=allocation.transfer_to_waitlist(
        booking_id, request.form, g.account["role"] + ":" + g.account["username"])), 201


@reservation_bp.post(DESK + "/tables/<int:table_id>/clear")
def clear(table_id):
    return jsonify(ok=True, clearance=allocation.clear_table(table_id, request.form.get("visit_id"),
        g.account["role"] + ":" + g.account["username"], request.form.get("idempotency_key")))
