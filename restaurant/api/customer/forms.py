from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    FieldList,
    Form,
    FormField,
    IntegerField,
    StringField,
    SubmitField,
)
from wtforms.validators import (
    InputRequired,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)
from restaurant.forms import iso_date_time


class BookingForm(FlaskForm):
    booking_date = DateField(
        "Dining date",
        format="%Y-%m-%d",
        validators=[InputRequired("Select a dining date.")],
    )
    time_slot_id = IntegerField(
        "Time slot",
        validators=[InputRequired("Select a time slot."), NumberRange(min=1)],
    )
    party_size = IntegerField(
        "Party size",
        validators=[InputRequired("Enter the party size."), NumberRange(min=1)],
    )
    table_id = IntegerField(
        "Table ID",
        validators=[Optional(), NumberRange(min=1)],
    )
    idempotency_key = StringField("Reservation submission ID", validators=[Optional(), Length(max=80)])
    submit = SubmitField("Confirm Booking")


class BookingEditForm(BookingForm):
    expected_version = IntegerField("Reservation version", validators=[InputRequired(), NumberRange(min=1)])
    submit = SubmitField("Save Booking Changes")


class CancelBookingForm(FlaskForm):
    submit = SubmitField("Cancel Booking")


class OrderItemForm(Form):
    dish_id = IntegerField(
        "Dish ID",
        validators=[InputRequired("A dish ID is required."), NumberRange(min=1)],
    )
    quantity = IntegerField(
        "Quantity",
        validators=[InputRequired("Enter a quantity."), NumberRange(min=1, max=99)],
    )
    quoted_unit_cents = IntegerField("Displayed unit price", validators=[Optional(), NumberRange(min=0, max=10_000_000)])
    note = StringField("Notes", default="", validators=[Optional(), Length(max=200)])


class OrderForm(FlaskForm):
    items = FieldList(FormField(OrderItemForm))
    submit = SubmitField("Place Order")

    def validate_items(self, items):
        if not items.entries:
            raise ValidationError("Select at least one dish.")
        if len(items.entries) > 50:
            raise ValidationError("An order can contain up to 50 dish lines.")


class OrderCreateForm(OrderForm):
    idempotency_key = StringField("Order submission ID", validators=[InputRequired("Refresh before submitting this order."), Length(max=80)])


class OrderEditForm(OrderForm):
    expected_version = IntegerField("Order version", validators=[InputRequired(), NumberRange(min=1)])


class PaymentForm(FlaskForm):
    submit = SubmitField("Confirm Payment")


class VisitPaymentForm(FlaskForm):
    order_ids = StringField("Orders in this bill", validators=[InputRequired()])
    total_cents = IntegerField("Bill amount", validators=[InputRequired(), NumberRange(min=0)])


class PreorderForm(OrderCreateForm):
    estimated_ready_at = StringField(
        "Requested preparation time",
        validators=[Optional(), Length(max=32), iso_date_time],
    )


class WaitlistForm(FlaskForm):
    party_size = IntegerField(
        "Party size", validators=[InputRequired(), NumberRange(min=1)]
    )
    contact_name = StringField("Contact name", validators=[Optional(), Length(max=100)])
    phone_number = StringField("Phone number", validators=[Optional(), Length(max=20)])
    table_type = IntegerField(
        "Table capacity", validators=[Optional(), NumberRange(min=1)]
    )
