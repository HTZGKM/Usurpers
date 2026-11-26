from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, SubmitField
from wtforms.validators import InputRequired, NumberRange


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
