from flask import Blueprint

from .forms import (
    CancelBookingForm,
    CancelOrderItemForm,
    CheckInForm,
    CloseVisitForm,
    ConfirmPaymentForm,
    ServeItemForm,
    StaffBookingEditForm,
    StaffBookingForm,
    StaffOrderForm,
    WalkInForm,
)

frontdesk_bp = Blueprint("frontdesk", __name__, url_prefix="/frontdesk")

# TODO: Require the frontdesk role.


@frontdesk_bp.get("/bookings")
def bookings():
    # TODO: Filter bookings and table availability.
    pass


@frontdesk_bp.get("/bookings/new")
def new_booking():
    # TODO: Show the staff booking form.
    pass


@frontdesk_bp.post("/bookings")
def create_booking():
    form = StaffBookingForm()
    if form.validate_on_submit():
        # TODO: Create the guest booking.
        pass

    # TODO: Handle form errors.


@frontdesk_bp.route("/bookings/<int:booking_id>/edit", methods=["GET", "POST"])
def edit_booking(booking_id):
    form = StaffBookingEditForm()
    if form.validate_on_submit():
        # TODO: Update the booking.
        pass

    # TODO: Load the existing booking. Show the form or errors.


@frontdesk_bp.post("/bookings/<int:booking_id>/cancel")
def cancel_booking(booking_id):
    form = CancelBookingForm()
    if form.validate_on_submit():
        # TODO: Cancel the booking.
        pass

    # TODO: Handle form errors.


@frontdesk_bp.post("/bookings/<int:booking_id>/check-in")
def register_arrival(booking_id):
    form = CheckInForm()
    if form.validate_on_submit():
        # TODO: Check in the guest.
        pass

    # TODO: Handle form errors.


@frontdesk_bp.post("/walk-ins")
def register_walk_in():
    form = WalkInForm()
    if form.validate_on_submit():
        # TODO: Register the walk-in.
        pass

    # TODO: Handle form errors.


@frontdesk_bp.get("/menu")
def menu():
    # TODO: Show the current menu.
    pass


@frontdesk_bp.get("/orders")
def orders():
    # TODO: Filter guest orders.
    pass


@frontdesk_bp.get("/orders/<int:order_id>")
def order_detail(order_id):
    # TODO: Show the order details.
    pass


@frontdesk_bp.post("/orders")
def create_dine_in_order():
    form = StaffOrderForm()
    if form.validate_on_submit():
        # TODO: Create the dine-in order.
        pass

    # TODO: Handle form errors.


@frontdesk_bp.post("/orders/<int:order_id>/items/<int:order_item_id>/cancel")
def cancel_order_item(order_id, order_item_id):
    form = CancelOrderItemForm()
    if form.validate_on_submit():
        # TODO: Cancel the order item.
        pass

    # TODO: Handle form errors.


@frontdesk_bp.post("/orders/<int:order_id>/items/<int:order_item_id>/serve")
def serve_item(order_id, order_item_id):
    form = ServeItemForm()
    if form.validate_on_submit():
        # TODO: Mark the item as served.
        pass

    # TODO: Handle form errors.


@frontdesk_bp.post("/orders/<int:order_id>/pay")
def confirm_payment(order_id):
    form = ConfirmPaymentForm()
    if form.validate_on_submit():
        # TODO: Record the in-person payment.
        pass

    # TODO: Handle form errors.


@frontdesk_bp.post("/visits/<int:visit_id>/close")
def close_dining_session(visit_id):
    form = CloseVisitForm()
    if form.validate_on_submit():
        # TODO: Close the visit and release the table.
        pass

    # TODO: Handle form errors.
