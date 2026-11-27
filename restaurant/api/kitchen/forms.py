from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, SubmitField, StringField
from wtforms.validators import InputRequired, NumberRange, Length


class FinishCookingForm(FlaskForm):
    submit = SubmitField("Mark as Completed")


class StartCookingForm(FlaskForm):
    expected_version = IntegerField("Order version", validators=[InputRequired(), NumberRange(min=1)])


class DishAvailabilityForm(FlaskForm):
    is_available = SelectField(
        "Availability",
        choices=[("true", "Available"), ("false", "Unavailable")],
        validators=[InputRequired("Select an availability status.")],
    )
    submit = SubmitField("Update Availability")


class CapacityForm(StartCookingForm):
    max_active_orders = IntegerField("Order capacity",validators=[InputRequired(),NumberRange(min=1,max=100)])

class SupplyIssueForm(StartCookingForm):
    reason = StringField("Reason",validators=[InputRequired(),Length(max=500)])
