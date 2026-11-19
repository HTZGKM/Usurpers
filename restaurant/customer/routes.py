from flask import Blueprint, abort, redirect, url_for

from restaurant.auth.routes import current_account

from .forms import (
    BookingEditForm,
    BookingForm,
    CancelBookingForm,
    OrderForm,
    PaymentForm,
)

customer_bp = Blueprint("customer", __name__)


def _check_customer_access(*, order_id=None, booking_id=None):
    account = current_account()
    if account is None:
        return redirect(url_for("auth.login"), code=303)
    if account["role"] != "customer":
        abort(403)

    if booking_id is not None:
        # TODO: Verify ownership once the booking table is available.
        abort(501, description="Booking ownership checks are not available yet.")

    if order_id is not None:
        # TODO: Verify order ownership through the agreed service interface.
        abort(501, description="Order ownership checks are not available yet.")

    return None


@customer_bp.get("/menu")
def menu():
    # TODO: Show the menu.
    pass


@customer_bp.get("/bookings")
def bookings():
    login_redirect = _check_customer_access()
    if login_redirect is not None:
        return login_redirect

    # TODO: List the customer's bookings.
    pass


@customer_bp.get("/bookings/new")
def new_booking():
    login_redirect = _check_customer_access()
    if login_redirect is not None:
        return login_redirect

    # TODO: Show the booking form and time slots.
    pass


@customer_bp.post("/bookings")
def create_booking():
    login_redirect = _check_customer_access()
    if login_redirect is not None:
        return login_redirect

    form = BookingForm()
    if form.validate_on_submit():
        # TODO: Create the booking.
        pass

    # TODO: Handle form errors.


@customer_bp.route("/bookings/<int:booking_id>/edit", methods=["GET", "POST"])
def edit_booking(booking_id):
    login_redirect = _check_customer_access(booking_id=booking_id)
    if login_redirect is not None:
        return login_redirect

    form = BookingEditForm()
    if form.validate_on_submit():
        # TODO: Update the customer's booking.
        pass

    # TODO: Load the existing booking. Show the form or errors.


@customer_bp.post("/bookings/<int:booking_id>/cancel")
def cancel_booking(booking_id):
    login_redirect = _check_customer_access(booking_id=booking_id)
    if login_redirect is not None:
        return login_redirect

    form = CancelBookingForm()
    if form.validate_on_submit():
        # TODO: Cancel the customer's booking.
        pass

    # TODO: Handle form errors.


@customer_bp.get("/orders")
def orders():
    login_redirect = _check_customer_access()
    if login_redirect is not None:
        return login_redirect

    # TODO: List the customer's orders.
    pass


@customer_bp.post("/orders")
def confirm_order():
    login_redirect = _check_customer_access()
    if login_redirect is not None:
        return login_redirect

    form = OrderForm()
    if form.validate_on_submit():
        # TODO: Create the order.
        pass

    # TODO: Handle form errors.


@customer_bp.get("/orders/<int:order_id>")
def order_status(order_id):
    login_redirect = _check_customer_access(order_id=order_id)
    if login_redirect is not None:
        return login_redirect

    # TODO: Show the customer's order progress.
    pass


@customer_bp.post("/pay/<int:order_id>")
def pay_order(order_id):
    login_redirect = _check_customer_access(order_id=order_id)
    if login_redirect is not None:
        return login_redirect

    form = PaymentForm()
    if form.validate_on_submit():
        # TODO: Record the simulated payment.
        pass

    # TODO: Handle form errors.
