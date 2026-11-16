from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField
from wtforms.validators import InputRequired


class FinishCookingForm(FlaskForm):
    submit = SubmitField("Mark as Completed")


class DishAvailabilityForm(FlaskForm):
    is_available = SelectField(
        "Availability",
        choices=[("true", "Available"), ("false", "Unavailable")],
        validators=[InputRequired("Select an availability status.")],
    )
    submit = SubmitField("Update Availability")
