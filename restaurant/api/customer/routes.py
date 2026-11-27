from restaurant.forms import ActionForm
from .forms import (
    BookingForm,
    BookingEditForm,
    CancelBookingForm,
    OrderCreateForm,
    OrderEditForm,
    PaymentForm,
    PreorderForm,
    VisitPaymentForm,
    OrderVersionForm,
    WaitlistForm,
)
from restaurant.api.frontdesk.forms import StaffBookingForm
from flask import Blueprint, g, jsonify, request
from restaurant.route_utils import validated_data, require_api_role
from restaurant.services import allocation, booking_service, order_service, menu_service
from restaurant.services.common import ServiceError, positive_int

customer_bp = Blueprint("customer", __name__)


@customer_bp.before_request
def require_customer_access():
    if request.endpoint == "customer.menu":
        return None
    if request.path.startswith("/pay/"):
        return require_api_role("customer")
    if request.path == "/tables/available":
        return require_api_role("customer", "frontdesk", "kitchen", "admin")
    return require_api_role("customer", "frontdesk", "admin")


@customer_bp.get("/menu")
def menu():
    return jsonify({"ok": True, "items": menu_service.get_available_items()})


@customer_bp.post("/bookings")
def create_booking():
    data = validated_data(
        BookingForm if g.account["role"] == "customer" else StaffBookingForm
    )
    user = g.account
    if allocation.enabled():
        return jsonify(ok=True, booking=allocation.create_booking(data, user)), 201
    customer_phone = user.get("username") if user.get("role") == "customer" else None
    contact_name = (
        user.get("name")
        if customer_phone
        else data.get("contact_name", data.get("name"))
    )
    phone = customer_phone or data.get("phone_number", data.get("phone"))
    return (
        jsonify(
            {
                "ok": True,
                "booking": booking_service.create_booking(
                    contact_name,
                    phone,
                    data.get("booking_date", data.get("date")),
                    data.get("time_slot_id", data.get("time_slot")),
                    data.get("party_size", data.get("guests")),
                    customer_phone,
                    data.get("table_id"),
                    idempotency_key=data.get("idempotency_key") or None,
                    actor=None if customer_phone else user["role"] + ":" + user["username"],
                ),
            }
        ),
        201,
    )


@customer_bp.get("/bookings")
def bookings():
    return jsonify(
        {
            "ok": True,
            "bookings": booking_service.get_customer_bookings(
                g.account["username"]
            ),
        }
    )


@customer_bp.post("/bookings/<int:booking_id>/preorders")
def preorder(booking_id):
    data = validated_data(PreorderForm)
    user = g.account
    return (
        jsonify(
            {
                "ok": True,
                "order": order_service.create_preorder(
                    booking_id,
                    user["username"],
                    data.get("items"),
                    data.get("estimated_ready_at"),
                    request_key=data.get("idempotency_key"),
                ),
            }
        ),
        201,
    )


@customer_bp.get("/tables/available")
def available_tables():
    return jsonify(
        {
            "ok": True,
            "tables": booking_service.find_available_tables(
                request.args.get("date"),
                request.args.get("time_slot_id"),
                request.args.get("party_size"),
            ),
        }
    )


@customer_bp.route("/bookings/<int:booking_id>/edit", methods=["GET", "POST"])
def edit_booking(booking_id):
    if request.method == "GET":
        return _booking_details(booking_id)
    data = validated_data(BookingEditForm)
    owner = (
        g.account["username"] if g.account["role"] == "customer" else None
    )
    return jsonify(
        {
            "ok": True,
            "booking": booking_service.update_booking(
                booking_id,
                data.get("booking_date"),
                data.get("time_slot_id"),
                data.get("party_size"),
                owner,
                data.get("table_id"),
                expected_version=data["expected_version"],
            ),
        }
    )


@customer_bp.post("/bookings/<int:booking_id>/cancel")
def cancel_booking(booking_id):
    data = validated_data(CancelBookingForm)
    owner = (
        g.account["username"] if g.account["role"] == "customer" else None
    )
    return jsonify(
        {"ok": True, "booking": booking_service.cancel_booking(booking_id, owner)}
    )


@customer_bp.post("/visits/<int:visit_id>/orders")
def create_visit_order(visit_id):
    data = validated_data(OrderCreateForm)
    user = g.account
    owner = user.get("username") if user.get("role") == "customer" else None
    return (
        jsonify(
            {
                "ok": True,
                "order": order_service.create_dine_in_order(
                    visit_id, data.get("items"), owner, request_key=data.get("idempotency_key"),
                    actor=g.account["role"] + ":" + g.account["username"],
                ),
            }
        ),
        201,
    )


@customer_bp.post("/orders")
def confirm_order():
    data = validated_data(OrderCreateForm)

    user = g.account
    return (
        jsonify(
            {
                "ok": True,
                "order": order_service.create_dine_in_order(
                    None, data.get("items"), user["username"], request_key=data.get("idempotency_key"),
                    actor=user["role"] + ":" + user["username"],
                ),
            }
        ),
        201,
    )


@customer_bp.post("/orders/<int:order_id>/pay")
@customer_bp.post("/pay/<int:order_id>")
def pay_order(order_id):
    data = validated_data(PaymentForm)
    owner = (
        g.account["username"] if g.account["role"] == "customer" else None
    )
    return jsonify({"ok": True, "payment": order_service.pay_order(order_id, owner)})


@customer_bp.post("/visits/<int:visit_id>/pay")
def pay_visit(visit_id):
    data = validated_data(VisitPaymentForm)
    order_ids = {positive_int(value, "order_ids") for value in data["order_ids"].split(",")}
    payment = order_service.pay_visit(visit_id, g.account["username"] if g.account["role"]=="customer" else None, order_ids, data["total_cents"], request_key=data["idempotency_key"], actor=g.account["role"]+":"+g.account["username"])
    return jsonify(ok=True, payment=payment)


@customer_bp.get("/orders")
def orders():
    role = g.account["role"]
    if role == "customer":
        rows = order_service.get_customer_orders(g.account["username"])
    else:
        rows = order_service.get_orders(
            phone=request.args.get("phone_number"),
            table_id=request.args.get("table_id"),
        )
    return jsonify({"ok": True, "orders": rows})


@customer_bp.get("/orders/<int:order_id>")
def order_status(order_id):
    owner = (
        g.account["username"] if g.account["role"] == "customer" else None
    )
    return jsonify({"ok": True, "order": order_service.get_order(order_id, owner)})


@customer_bp.post("/orders/<int:order_id>/cancel")
def cancel_order(order_id):
    data = validated_data(OrderVersionForm)
    owner = (
        g.account["username"] if g.account["role"] == "customer" else None
    )
    return jsonify({"ok": True, "order": order_service.cancel_order(order_id, owner, expected_version=data["expected_version"])})


@customer_bp.post("/orders/<int:order_id>/edit")
def edit_order(order_id):
    data = validated_data(OrderEditForm)
    owner = (
        g.account["username"] if g.account["role"] == "customer" else None
    )
    return jsonify(
        {
            "ok": True,
            "order": order_service.update_order(order_id, data.get("items"), owner, expected_version=data["expected_version"]),
        }
    )


@customer_bp.post("/orders/<int:order_id>/items/<int:item_id>/cancel")
def cancel_item(order_id, item_id):
    data = validated_data(OrderVersionForm)
    owner = (
        g.account["username"] if g.account["role"] == "customer" else None
    )
    return jsonify(
        {"ok": True, "item": order_service.cancel_order_item(order_id, item_id, owner, expected_version=data["expected_version"])}
    )


@customer_bp.post("/waiting-queue")
def join_waitlist():
    if allocation.enabled():
        raise ServiceError("Ask the front desk to issue a waitlist ticket.", 403, code="WAITLIST_STAFF_ONLY")
    data = validated_data(WaitlistForm)
    from restaurant.services.queue_manager import QueueManager

    user = g.account
    phone = (
        data.get("phone_number")
        if user.get("role") != "customer"
        else user.get("username")
    )
    return (
        jsonify(
            {
                "ok": True,
                "queue": QueueManager.join_waitlist(
                    data.get("party_size"),
                    data.get("contact_name"),
                    phone,
                    phone if user.get("role") == "customer" else None,
                    data.get("table_type"),
                ),
            }
        ),
        201,
    )


@customer_bp.delete("/waiting-queue/<int:queue_id>")
def leave_waitlist(queue_id):
    if allocation.enabled():
        raise ServiceError("Ask the front desk to change a waitlist ticket.", 403, code="WAITLIST_STAFF_ONLY")
    data = validated_data(ActionForm)
    from restaurant.services.queue_manager import QueueManager

    user = g.account
    owner = user.get("username") if user.get("role") == "customer" else None
    return jsonify({"ok": True, "queue": QueueManager.cancel(queue_id, owner)})


@customer_bp.get("/waiting-queue/mine")
def my_waitlist():
    if allocation.enabled():
        return jsonify(ok=True, queue=None)
    from restaurant.services.queue_manager import QueueManager

    return jsonify(
        {
            "ok": True,
            "queue": QueueManager.get_customer_entry(g.account["username"]),
        }
    )


def _booking_details(booking_id):
    user = g.account
    bookings = (
        booking_service.get_customer_bookings(user["username"])
        if user["role"] == "customer"
        else booking_service.get_all_bookings()
    )
    booking = next(
        (entry for entry in bookings if entry["booking_id"] == booking_id), None
    )
    if booking is None:
        raise ServiceError("Booking not found.", 404)
    return jsonify({"ok": True, "booking": booking})


@customer_bp.get("/visits/<int:visit_id>/bill")
def visit_bill(visit_id):
    owner=g.account["username"] if g.account["role"]=="customer" else None
    return jsonify(ok=True,bill=order_service.get_visit_bill(visit_id,owner))
