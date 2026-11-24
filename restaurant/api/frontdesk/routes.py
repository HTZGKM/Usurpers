from restaurant.forms import ActionForm
from .forms import (
    StaffBookingForm,
    StaffBookingEditForm,
    CancelBookingForm,
    CheckInForm,
    WalkInForm,
    CloseVisitForm,
    AssignTableForm,
    StaffOrderForm,
    ConfirmPaymentForm,
    CancelOrderItemForm,
    ServeItemForm,
    RemakeForm,
    RefundForm,
)
from restaurant.api.customer.forms import OrderForm
from flask import Blueprint, jsonify, request, session
from restaurant.route_utils import validated_data, require_api_role
from restaurant.services import (
    booking_service,
    dining_service,
    order_service,
    kitchen_service,
    menu_service,
)
from restaurant.services.common import ServiceError

frontdesk_bp = Blueprint("frontdesk", __name__, url_prefix="/frontdesk")


@frontdesk_bp.before_request
def require_frontdesk_role():
    return require_api_role("frontdesk", "admin")


@frontdesk_bp.post("/bookings")
def create_booking():
    data = validated_data(StaffBookingForm)
    user = session.get("user", {})
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
                ),
            }
        ),
        201,
    )


@frontdesk_bp.get("/bookings")
def bookings():
    return jsonify(
        {
            "ok": True,
            "bookings": booking_service.get_all_bookings(
                request.args.get("date"),
                request.args.get("time_slot_id"),
                request.args.get("phone_number"),
            ),
        }
    )


@frontdesk_bp.post("/bookings/<int:booking_id>/check-in")
def register_arrival(booking_id):
    data = validated_data(CheckInForm)
    return (
        jsonify(
            {
                "ok": True,
                "visit": dining_service.register_arrival(
                    booking_id, data.get("table_id")
                ),
            }
        ),
        201,
    )


@frontdesk_bp.get("/tables")
def table_occupancy():
    return jsonify(
        {
            "ok": True,
            "tables": booking_service.get_table_occupancy(
                request.args.get("date"), request.args.get("time_slot_id")
            ),
        }
    )


@frontdesk_bp.post("/walk-ins")
def register_walk_in():
    data = validated_data(WalkInForm)
    return (
        jsonify(
            {
                "ok": True,
                "visit": dining_service.register_walk_in(
                    data.get("party_size"),
                    data.get("table_id"),
                    data.get("contact_name"),
                    data.get("phone_number"),
                ),
            }
        ),
        201,
    )


@frontdesk_bp.post("/visits/<int:visit_id>/close")
def close_dining_session(visit_id):
    data = validated_data(CloseVisitForm)
    return jsonify({"ok": True, "visit": dining_service.close_dining_session(visit_id)})


@frontdesk_bp.post("/visits/<int:visit_id>/assign")
def assign_visit(visit_id):
    data = validated_data(AssignTableForm)
    return jsonify(
        {
            "ok": True,
            "visit": dining_service.assign_table(visit_id, data.get("table_id")),
        }
    )


@frontdesk_bp.post("/orders")
def create_dine_in_order():
    data = validated_data(StaffOrderForm)
    return (
        jsonify(
            {
                "ok": True,
                "order": order_service.create_dine_in_order(
                    data.get("visit_id"), data.get("items")
                ),
            }
        ),
        201,
    )


@frontdesk_bp.post("/orders/<int:order_id>/edit")
def frontdesk_edit_order(order_id):
    data = validated_data(OrderForm)
    return jsonify(
        {"ok": True, "order": order_service.update_order(order_id, data.get("items"))}
    )


@frontdesk_bp.post("/orders/<int:order_id>/pay")
def confirm_payment(order_id):
    data = validated_data(ConfirmPaymentForm)
    return jsonify({"ok": True, "payment": order_service.pay_order(order_id)})


@frontdesk_bp.get("/orders/<int:order_id>")
def order_detail(order_id):
    return jsonify({"ok": True, "order": order_service.get_order(order_id)})


@frontdesk_bp.post("/orders/<int:order_id>/items/<int:order_item_id>/cancel")
def cancel_order_item(order_id, order_item_id):
    data = validated_data(CancelOrderItemForm)
    return jsonify(
        {"ok": True, "item": order_service.cancel_order_item(order_id, order_item_id)}
    )


@frontdesk_bp.post("/orders/<int:order_id>/items/<int:order_item_id>/serve")
def serve_item(order_id, order_item_id):
    data = validated_data(ServeItemForm)
    _order_item(order_id, order_item_id)
    return jsonify({"ok": True, "item": kitchen_service.serve_item(order_item_id)})


@frontdesk_bp.get("/waiting-queue")
def waiting_queue():
    from restaurant.services.queue_manager import QueueManager

    return jsonify({"ok": True, "queue": QueueManager.list_waiting()})


@frontdesk_bp.post("/tables/<int:table_id>/call-next")
def call_next(table_id):
    data = validated_data(ActionForm)
    from restaurant.services.queue_manager import QueueManager

    return jsonify({"ok": True, "queue": QueueManager.call_next(table_id)})


@frontdesk_bp.post("/waiting-queue/<int:queue_id>/seat")
def seat_waiting(queue_id):
    data = validated_data(AssignTableForm)
    from restaurant.services.queue_manager import QueueManager

    return (
        jsonify(
            {"ok": True, "visit": QueueManager.seat(queue_id, data.get("table_id"))}
        ),
        201,
    )


@frontdesk_bp.post("/orders/<int:order_id>/items/<int:order_item_id>/remakes")
def create_remake(order_id, order_item_id):
    # 补做功能已移除（remake_tickets 表已删除）
    return jsonify({"ok": False, "error": "补做功能已移除。"}), 501


@frontdesk_bp.post("/orders/<int:order_id>/refunds")
def refund_order(order_id):
    # 退款功能已移除（payments/refunds 表已删除）
    return jsonify({"ok": False, "error": "退款功能已移除。"}), 501


@frontdesk_bp.get("/orders/<int:order_id>/refunds")
def list_order_refunds(order_id):
    return jsonify({"ok": True, "refunds": []})


def _order_item(order_id, order_item_id):
    order = order_service.get_order(order_id)
    item = next(
        (entry for entry in order["items"] if entry["order_item_id"] == order_item_id),
        None,
    )
    if item is None:
        raise ServiceError("Order item not found.", 404)
    return item


def _current_staff_id():
    from restaurant.services.staff_account_service import get_staff_accounts

    member = next(
        (
            entry
            for entry in get_staff_accounts()
            if entry["email"] == session["user"]["username"]
        ),
        None,
    )
    if member is None or not member["is_active"]:
        raise ServiceError("Staff account is inactive.", 403, code="FORBIDDEN")
    return member["staff_id"]


@frontdesk_bp.route("/bookings/<int:booking_id>/edit", methods=["GET", "POST"])
def edit_booking(booking_id):
    if request.method == "GET":
        booking = next(
            (
                entry
                for entry in booking_service.get_all_bookings()
                if entry["booking_id"] == booking_id
            ),
            None,
        )
        if booking is None:
            raise ServiceError("Booking not found.", 404)
        return jsonify({"ok": True, "booking": booking})
    data = validated_data(StaffBookingEditForm)
    data = data
    return jsonify(
        {
            "ok": True,
            "booking": booking_service.update_booking(
                booking_id,
                data.get("booking_date"),
                data.get("time_slot_id"),
                data.get("party_size"),
                None,
                data.get("table_id"),
            ),
        }
    )


@frontdesk_bp.post("/bookings/<int:booking_id>/cancel")
def cancel_booking(booking_id):
    data = validated_data(CancelBookingForm)
    return jsonify({"ok": True, "booking": booking_service.cancel_booking(booking_id)})


@frontdesk_bp.get("/menu")
def menu():
    return jsonify({"ok": True, "items": menu_service.get_available_items()})


@frontdesk_bp.get("/orders")
def orders():
    return jsonify(
        {
            "ok": True,
            "orders": order_service.get_orders(
                phone=request.args.get("phone_number"),
                table_id=request.args.get("table_id"),
            ),
        }
    )
