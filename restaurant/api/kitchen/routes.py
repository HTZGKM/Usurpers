from restaurant.forms import ActionForm
from .forms import FinishCookingForm, StartCookingForm, DishAvailabilityForm
from flask import Blueprint, jsonify, request, session
from restaurant.route_utils import validated_data, require_api_role
from restaurant.services import order_service, kitchen_service, menu_service
from restaurant.services.common import ServiceError

kitchen_bp = Blueprint("kitchen", __name__, url_prefix="/kitchen")


@kitchen_bp.before_request
def require_kitchen_role():
    return require_api_role("kitchen", "admin")


@kitchen_bp.get("/queue")
def queue():
    state = request.args.get("status", "waiting")
    fn = {
        "waiting": kitchen_service.get_waiting_items,
        "cooking": kitchen_service.get_cooking_items,
        "ready": kitchen_service.get_ready_items,
        "active": kitchen_service.get_active_items,
    }.get(state)
    if not fn:
        from restaurant.services.common import ServiceError

        raise ServiceError("Invalid queue status.", field="status")
    return jsonify({"ok": True, "items": fn()})


@kitchen_bp.get("/menu")
def menu():
    items = menu_service.get_all_items()
    if request.args.get("available") == "true":
        items = [
            item for item in items if item["is_available"] and (not item["is_archived"])
        ]
    return jsonify({"ok": True, "items": items})


@kitchen_bp.get("/orders/<int:order_id>")
def order_detail(order_id):
    return jsonify({"ok": True, "order": order_service.get_order(order_id)})


@kitchen_bp.post("/items/<int:order_item_id>/start")
def start_item(order_item_id):
    data = validated_data(StartCookingForm)
    return jsonify({"ok": True, "item": kitchen_service.start_item(order_item_id, data["expected_version"])})


@kitchen_bp.post("/items/<int:order_item_id>/complete")
@kitchen_bp.post("/order-items/<int:order_item_id>/complete")
def finish_item(order_item_id):
    data = validated_data(FinishCookingForm)
    return jsonify({"ok": True, "item": kitchen_service.finish_item(order_item_id)})


@kitchen_bp.post("/items/<int:order_item_id>/serve")
def serve_item(order_item_id):
    data = validated_data(ActionForm)
    return jsonify({"ok": True, "item": kitchen_service.serve_item(order_item_id)})


@kitchen_bp.get("/remakes")
def kitchen_remakes():
    # 补做功能已移除（remake_tickets 表已删除）
    return jsonify({"ok": True, "tasks": []})


@kitchen_bp.post("/remakes/<int:remake_id>/start")
def start_remake(remake_id):
    raise ServiceError("The remake feature has been removed.", 501)


@kitchen_bp.post("/remakes/<int:remake_id>/complete")
def complete_remake(remake_id):
    raise ServiceError("The remake feature has been removed.", 501)


@kitchen_bp.post("/menu/<int:dish_id>/availability")
def kitchen_availability(dish_id):
    data = validated_data(DishAvailabilityForm)
    value = data.get("is_available")
    if value in ("true", "1", 1, True):
        value = True
    elif value in ("false", "0", 0, False):
        value = False
    else:
        from restaurant.services.common import ServiceError

        raise ServiceError("is_available must be true or false.", field="is_available")
    item = menu_service.update_item(dish_id, is_available=value)
    if item["is_archived"] and value:
        from restaurant.services.common import ServiceError

        raise ServiceError(
            "Archived dishes cannot be made available.", 409, code="STATE_CONFLICT"
        )
    return jsonify({"ok": True, "item": item})
