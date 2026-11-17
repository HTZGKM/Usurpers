from flask import Blueprint

from .forms import (
    BookingEditForm,
    BookingForm,
    CancelBookingForm,
    OrderForm,
    PaymentForm,
)

customer_bp = Blueprint("customer", __name__)

# TODO: Check customer access and record ownership.


@customer_bp.get("/menu")
def menu():
    # TODO: Show the menu.
    pass


@customer_bp.get("/bookings")
def bookings():
    # TODO: List the customer's bookings.
    pass


@customer_bp.get("/bookings/new")
def new_booking():
    # TODO: Show the booking form and time slots.
    pass


@customer_bp.post("/bookings")
def create_booking():
    form = BookingForm()
    if form.validate_on_submit():
        # TODO: Create the booking.
        pass

    # TODO: Handle form errors.


@customer_bp.route("/bookings/<int:booking_id>/edit", methods=["GET", "POST"])
def edit_booking(booking_id):
    form = BookingEditForm()
    if form.validate_on_submit():
        # TODO: Update the customer's booking.
        pass

    # TODO: Load the existing booking. Show the form or errors.


@customer_bp.post("/bookings/<int:booking_id>/cancel")
def cancel_booking(booking_id):
    form = CancelBookingForm()
    if form.validate_on_submit():
        # TODO: Cancel the customer's booking.
        pass

    # TODO: Handle form errors.


@customer_bp.get("/orders")
def orders():
    # TODO: List the customer's orders.
    pass


@customer_bp.post("/orders")
def confirm_order():
    form = OrderForm()
    if form.validate_on_submit():
        # TODO: Create the order.
        pass

    # TODO: Handle form errors.


@customer_bp.get("/orders/<int:order_id>")
def order_status(order_id):
    # TODO: Show the customer's order progress.
    pass


@customer_bp.post("/pay/<int:order_id>")
def pay_order(order_id):
    form = PaymentForm()
    if form.validate_on_submit():
        # TODO: Record the simulated payment.
        pass

    # TODO: Handle form errors.
