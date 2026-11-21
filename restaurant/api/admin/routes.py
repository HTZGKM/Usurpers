from restaurant.forms import ActionForm
from .forms import (
    CreateStaffForm,
    EditStaffForm,
    DeactivateStaffForm,
    ResetStaffPasswordForm,
    DishForm,
    EditDishForm,
    ArchiveDishForm,
    IngredientForm,
    StockAdjustmentForm,
    RecipeForm,
)
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

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
def require_admin_role():
    return require_api_role("admin")


@admin_bp.get("/staff")
def admin_staff():
    from restaurant.services.staff_account_service import get_staff_accounts

    return jsonify({"ok": True, "staff": get_staff_accounts(request.args.get("role"))})


@admin_bp.get("/accounts")
def staff_accounts():
    from restaurant.services.auth_service import get_customer_accounts
    from restaurant.services.staff_account_service import get_staff_accounts

    return jsonify(
        {
            "ok": True,
            "staff": get_staff_accounts(),
            "customers": get_customer_accounts(),
        }
    )


@admin_bp.post("/customers/<path:customer_phone>/deactivate")
def admin_deactivate_customer(customer_phone):
    data = validated_data(ActionForm)
    from restaurant.services.auth_service import set_customer_active

    return jsonify({"ok": True, "customer": set_customer_active(customer_phone, False)})


@admin_bp.post("/customers/<path:customer_phone>/activate")
def admin_activate_customer(customer_phone):
    data = validated_data(ActionForm)
    from restaurant.services.auth_service import set_customer_active

    return jsonify({"ok": True, "customer": set_customer_active(customer_phone, True)})


@admin_bp.post("/staff")
def create_staff():
    data = validated_data(CreateStaffForm)
    from restaurant.services.staff_account_service import create_staff_account

    return (
        jsonify(
            {
                "ok": True,
                "staff": create_staff_account(
                    data.get("name"),
                    data.get("phone_number"),
                    data.get("email"),
                    data.get("password"),
                    data.get("role"),
                ),
            }
        ),
        201,
    )


@admin_bp.route("/staff/<int:staff_id>/edit", methods=["GET", "POST"])
def edit_staff(staff_id):
    if request.method == "GET":
        from restaurant.services.staff_account_service import get_staff_accounts

        staff = next(
            (entry for entry in get_staff_accounts() if entry["staff_id"] == staff_id),
            None,
        )
        if staff is None:
            raise ServiceError("Staff account not found.", 404)
        return jsonify({"ok": True, "staff": staff})
    data = validated_data(EditStaffForm)
    from restaurant.services.staff_account_service import update_staff_account

    return jsonify(
        {
            "ok": True,
            "staff": update_staff_account(
                staff_id,
                data.get("name"),
                data.get("phone_number"),
                data.get("email"),
                data.get("role"),
            ),
        }
    )


@admin_bp.post("/staff/<int:staff_id>/deactivate")
def deactivate_staff(staff_id):
    data = validated_data(DeactivateStaffForm)
    from restaurant.services.staff_account_service import set_staff_active

    return jsonify({"ok": True, "staff": set_staff_active(staff_id, False)})


@admin_bp.post("/staff/<int:staff_id>/activate")
def admin_activate_staff(staff_id):
    data = validated_data(ActionForm)
    from restaurant.services.staff_account_service import set_staff_active

    return jsonify({"ok": True, "staff": set_staff_active(staff_id, True)})


@admin_bp.post("/staff/<int:staff_id>/reset-password")
def admin_reset_staff_password(staff_id):
    data = validated_data(ResetStaffPasswordForm)
    from restaurant.services.staff_account_service import reset_staff_password

    return jsonify(
        {
            "ok": True,
            "staff": reset_staff_password(staff_id, data.get("password", "123456")),
        }
    )


@admin_bp.get("/dishes")
def menu():
    dishes = menu_service.get_all_items()
    if request.args.get("available") == "true":
        dishes = [
            dish
            for dish in dishes
            if dish["is_available"] and (not dish["is_archived"])
        ]
    return jsonify({"ok": True, "dishes": dishes})


@admin_bp.post("/dishes")
def create_dish():
    data = validated_data(DishForm)
    return (
        jsonify(
            {
                "ok": True,
                "dish": menu_service.create_item(
                    data.get("name"),
                    data.get("price"),
                    data.get("ingredients", ""),
                    data.get("prep_time_minutes", 10),
                    data.get("image_path"),
                ),
            }
        ),
        201,
    )


@admin_bp.route("/dishes/<int:dish_id>/edit", methods=["GET", "POST"])
def edit_dish(dish_id):
    if request.method == "GET":
        dish = next(
            (
                entry
                for entry in menu_service.get_all_items()
                if entry["dish_id"] == dish_id
            ),
            None,
        )
        if dish is None:
            raise ServiceError("Dish not found.", 404)
        return jsonify({"ok": True, "dish": dish})
    data = validated_data(EditDishForm)
    return jsonify(
        {
            "ok": True,
            "dish": menu_service.update_item(
                dish_id, data.get("name"), data.get("price")
            ),
        }
    )


@admin_bp.post("/dishes/<int:dish_id>/archive")
def archive_dish(dish_id):
    data = validated_data(ArchiveDishForm)
    return jsonify({"ok": True, "dish": menu_service.archive_item(dish_id)})


@admin_bp.get("/inventory/ingredients")
def admin_inventory_ingredients():
    from restaurant.services.inventory_service import list_ingredients

    return jsonify({"ok": True, "ingredients": list_ingredients()})


@admin_bp.post("/inventory/ingredients")
def admin_create_ingredient():
    data = validated_data(IngredientForm)
    from restaurant.services.inventory_service import create_ingredient

    return (
        jsonify(
            {
                "ok": True,
                "ingredient": create_ingredient(
                    data.get("name"),
                    data.get("unit"),
                    data.get("on_hand"),
                    data.get("expires_at"),
                ),
            }
        ),
        201,
    )


@admin_bp.post("/inventory/ingredients/<int:ingredient_id>/adjust")
def admin_adjust_ingredient(ingredient_id):
    data = validated_data(StockAdjustmentForm)
    from restaurant.services.inventory_service import adjust_stock

    return jsonify(
        {
            "ok": True,
            "ingredient": adjust_stock(
                ingredient_id,
                data.get("quantity"),
                data.get("movement_type", "adjustment"),
                data.get("reference"),
            ),
        }
    )


@admin_bp.put("/dishes/<int:dish_id>/recipe")
def admin_set_recipe(dish_id):
    data = validated_data(RecipeForm)
    from restaurant.services.inventory_service import set_recipe

    return jsonify({"ok": True, "recipe": set_recipe(dish_id, data.get("ingredients"))})


@admin_bp.get("/orders")
def orders():
    rows = order_service.get_orders(
        active_only=request.args.get("active_only") == "true",
        phone=request.args.get("phone_number"),
        table_id=request.args.get("table_id"),
    )
    state = request.args.get("status")
    if state:
        rows = [r for r in rows if r["status"] == state]
    return jsonify({"ok": True, "orders": rows})


@admin_bp.get("/orders/<int:order_id>")
def order_detail(order_id):
    return jsonify({"ok": True, "order": order_service.get_order(order_id)})


@admin_bp.get("/kitchen-queue")
def waiting_items():
    return jsonify({"ok": True, "items": kitchen_service.get_waiting_items()})


@admin_bp.get("/bookings")
def admin_bookings():
    return jsonify(
        {
            "ok": True,
            "bookings": booking_service.get_all_bookings(
                request.args.get("booking_date"),
                request.args.get("time_slot_id"),
                request.args.get("phone_number"),
            ),
        }
    )


@admin_bp.get("/tables")
def table_occupancy():
    return jsonify(
        {
            "ok": True,
            "tables": booking_service.get_table_occupancy(
                request.args.get("date"), request.args.get("time_slot_id")
            ),
        }
    )


@admin_bp.get("/dining-sessions")
def admin_visits():
    return jsonify({"ok": True, "visits": dining_service.get_dining_sessions()})


@admin_bp.get("/dashboard")
def admin_dashboard():
    from restaurant.services.queue_manager import QueueManager

    orders = order_service.get_orders()
    bookings = booking_service.get_all_bookings()
    visits = dining_service.get_dining_sessions()
    waiting = kitchen_service.get_waiting_items()
    summary = {
        "orders": len(orders),
        "active_orders": sum((order["status"] == "active" for order in orders)),
        "bookings": sum((booking["status"] == "booked" for booking in bookings)),
        "open_visits": sum(
            (visit["status"] in ("waiting", "seated") for visit in visits)
        ),
        "waiting_queue": len(QueueManager.list_waiting()),
        "kitchen_waiting": sum(
            (item.get("task_type", "order") == "order" for item in waiting)
        ),
    }
    return jsonify({"ok": True, "summary": summary})


@admin_bp.get("/staff/new")
def new_staff():
    raise ServiceError(
        "The staff account form page is not implemented yet.",
        501,
        code="NOT_IMPLEMENTED",
    )


@admin_bp.get("/dishes/new")
def new_dish():
    raise ServiceError(
        "The dish form page is not implemented yet.", 501, code="NOT_IMPLEMENTED"
    )
