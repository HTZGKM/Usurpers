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
    submit = SubmitField("Confirm Booking")


class BookingEditForm(BookingForm):
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
        validators=[InputRequired("Enter a quantity."), NumberRange(min=1)],
    )
    note = StringField("Notes", default="", validators=[Optional(), Length(max=200)])


class OrderForm(FlaskForm):
    items = FieldList(FormField(OrderItemForm))
    submit = SubmitField("Place Order")

    def validate_items(self, items):
        if not items.entries:
            raise ValidationError("Select at least one dish.")


class PaymentForm(FlaskForm):
    submit = SubmitField("Confirm Payment")


class PreorderForm(OrderForm):
    estimated_ready_at = StringField(
        "Requested preparation time",
        validators=[InputRequired(), Length(max=32), iso_date_time],
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
