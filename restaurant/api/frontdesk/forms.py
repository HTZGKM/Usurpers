from flask_wtf import FlaskForm
from wtforms import BooleanField, DecimalField, IntegerField, StringField, SubmitField
from wtforms.validators import (
    DataRequired,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    Regexp,
)
from restaurant.forms import monetary_amount

from ..customer.forms import BookingEditForm, BookingForm, OrderForm


class StaffBookingForm(BookingForm):
    contact_name = StringField(
        "Contact name",
        filters=[lambda value: (value or "").strip()],
        validators=[DataRequired("Enter the contact name."), Length(max=100)],
    )
    phone_number = StringField(
        "Contact phone number",
        filters=[lambda value: (value or "").strip()],
        validators=[
            DataRequired("Enter the contact phone number."),
            Regexp(
                r"\+?[0-9]+\Z", message="Enter digits only, with an optional leading +."
            ),
        ],
    )
    submit = SubmitField("Book for Customer")


class StaffBookingEditForm(BookingEditForm):
    submit = SubmitField("Save Booking Changes")


class CancelBookingForm(FlaskForm):
    submit = SubmitField("Cancel Booking")


class CheckInForm(FlaskForm):
    change_table = BooleanField("Change table")
    expected_version = IntegerField("Reservation version", validators=[Optional(), NumberRange(min=1)])
    table_id = IntegerField(
        "Table ID",
        validators=[Optional(), NumberRange(min=1)],
    )
    submit = SubmitField("Confirm Arrival")


class WalkInForm(FlaskForm):
    contact_name = StringField("Contact name", validators=[Optional(), Length(max=100)])
    phone_number = StringField("Phone number", validators=[Optional(), Length(max=20)])
    party_size = IntegerField(
        "Party size",
        validators=[InputRequired("Enter the party size."), NumberRange(min=1)],
    )
    table_id = IntegerField(
        "Table ID",
        validators=[InputRequired("Select a table."), NumberRange(min=1)],
    )
    submit = SubmitField("Register Walk-In")


class StaffOrderForm(OrderForm):
    visit_id = IntegerField(
        "Visit ID",
        validators=[InputRequired("Select a visit."), NumberRange(min=1)],
    )
    submit = SubmitField("Place Order for Customer")


class CancelOrderItemForm(FlaskForm):
    submit = SubmitField("Cancel Item")


class ServeItemForm(FlaskForm):
    submit = SubmitField("Mark as Served")


class ConfirmPaymentForm(FlaskForm):
    submit = SubmitField("Record Payment")


class CloseVisitForm(FlaskForm):
    submit = SubmitField("Close Visit and Release Table")


class AssignTableForm(FlaskForm):
    table_id = IntegerField(
        "Table ID", validators=[InputRequired(), NumberRange(min=1)]
    )


class RemakeForm(FlaskForm):
    reason = StringField("Reason", validators=[DataRequired(), Length(max=500)])


class RefundForm(RemakeForm):
    amount = DecimalField(
        "Amount", places=None, validators=[InputRequired(), monetary_amount]
    )
    idempotency_key = StringField(
        "Refund request ID", validators=[DataRequired(), Length(max=120)]
    )
