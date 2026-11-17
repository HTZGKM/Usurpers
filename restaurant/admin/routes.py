from flask import Blueprint

from .forms import (
    ArchiveDishForm,
    CreateStaffForm,
    DeactivateStaffForm,
    DishForm,
    EditDishForm,
    EditStaffForm,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# TODO: Require the admin role.


@admin_bp.get("/orders")
def orders():
    # TODO: Filter all orders.
    pass


@admin_bp.get("/orders/<int:order_id>")
def order_detail(order_id):
    # TODO: Show order details.
    pass


@admin_bp.get("/kitchen-queue")
def waiting_items():
    # TODO: Show the preparation queue.
    pass


@admin_bp.get("/tables")
def table_occupancy():
    # TODO: Filter tables by date and time slot.
    pass


@admin_bp.get("/accounts")
def staff_accounts():
    # TODO: List accounts by role.
    pass


@admin_bp.get("/staff/new")
def new_staff():
    # TODO: Show the staff account form.
    pass


@admin_bp.post("/staff")
def create_staff():
    form = CreateStaffForm()
    if form.validate_on_submit():
        # TODO: Create a staff account.
        pass

    # TODO: Handle form errors.


@admin_bp.route("/staff/<int:staff_id>/edit", methods=["GET", "POST"])
def edit_staff(staff_id):
    form = EditStaffForm()
    if form.validate_on_submit():
        # TODO: Update the staff account.
        pass

    # TODO: Load the existing staff account. Show the form or errors.


@admin_bp.post("/staff/<int:staff_id>/deactivate")
def deactivate_staff(staff_id):
    form = DeactivateStaffForm()
    if form.validate_on_submit():
        # TODO: Deactivate the staff account.
        pass

    # TODO: Handle form errors.


@admin_bp.get("/dishes")
def menu():
    # TODO: Show all or currently available dishes.
    pass


@admin_bp.get("/dishes/new")
def new_dish():
    # TODO: Show the dish form.
    pass


@admin_bp.post("/dishes")
def create_dish():
    form = DishForm()
    if form.validate_on_submit():
        # TODO: Create the dish.
        pass

    # TODO: Handle form errors.


@admin_bp.route("/dishes/<int:dish_id>/edit", methods=["GET", "POST"])
def edit_dish(dish_id):
    form = EditDishForm()
    if form.validate_on_submit():
        # TODO: Update the dish and its price.
        pass

    # TODO: Load the existing dish. Show the form or errors.


@admin_bp.post("/dishes/<int:dish_id>/archive")
def archive_dish(dish_id):
    form = ArchiveDishForm()
    if form.validate_on_submit():
        # TODO: Archive the dish.
        pass

    # TODO: Handle form errors.
