from flask import Blueprint, abort, redirect, url_for

from restaurant.auth.routes import current_account

from .forms import DishAvailabilityForm, FinishCookingForm

kitchen_bp = Blueprint("kitchen", __name__, url_prefix="/kitchen")


@kitchen_bp.before_request
def require_kitchen_role():
    account = current_account()
    if account is None:
        return redirect(url_for("auth.login"), code=303)
    if account["role"] != "kitchen":
        abort(403)


@kitchen_bp.get("/menu")
def menu():
    # TODO: Show all or currently available dishes.
    pass


@kitchen_bp.post("/menu/<int:dish_id>/availability")
def update_menu_availability(dish_id):
    form = DishAvailabilityForm()
    if form.validate_on_submit():
        # TODO: Update dish availability.
        pass

    # TODO: Handle form errors.


@kitchen_bp.get("/queue")
def queue():
    # TODO: Show the preparation queue.
    pass


@kitchen_bp.post("/order-items/<int:order_item_id>/complete")
def finish_item(order_item_id):
    form = FinishCookingForm()
    if form.validate_on_submit():
        # TODO: Mark the item as completed.
        pass

    # TODO: Handle form errors.
