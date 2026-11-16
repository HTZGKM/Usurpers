from flask_wtf import FlaskForm
from wtforms import (
    DecimalField,
    EmailField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, InputRequired, NumberRange, Optional, Regexp, ValidationError


class EditStaffForm(FlaskForm):
    name = StringField(
        "Name",
        filters=[lambda value: (value or "").strip()],
        validators=[DataRequired("Enter the staff member's name.")],
    )
    phone_number = StringField(
        "Phone number",
        filters=[lambda value: (value or "").strip()],
        validators=[
            DataRequired("Enter a phone number."),
            Regexp(r"\+?[0-9]+\Z", message="Enter digits only, with an optional leading +."),
        ],
    )
    email = EmailField(
        "Email address",
        filters=[lambda value: (value or "").strip()],
        validators=[
            DataRequired("Enter an email address."),
            Regexp(r"[^@\s]+@[^@\s]+\.[^@\s]+\Z", message="Enter a valid email address."),
        ],
    )
    role = SelectField(
        "Role",
        choices=[("frontdesk", "Front Desk"), ("kitchen", "Kitchen")],
        validators=[InputRequired("Select a staff role.")],
    )
    submit = SubmitField("Save Staff Changes")


class CreateStaffForm(EditStaffForm):
    password = PasswordField("Password", validators=[DataRequired("Enter a password.")])
    submit = SubmitField("Create Staff Account")


class DeactivateStaffForm(FlaskForm):
    submit = SubmitField("Deactivate Staff Account")


class DishForm(FlaskForm):
    name = StringField(
        "Dish name",
        filters=[lambda value: (value or "").strip()],
        validators=[DataRequired("Enter the dish name.")],
    )
    price = DecimalField("Price", places=None, validators=[InputRequired("Enter a price.")])
    ingredients = TextAreaField("Ingredients", validators=[DataRequired("Enter the ingredients.")])
    prep_time_minutes = IntegerField(
        "Estimated preparation time (minutes)",
        validators=[InputRequired("Enter the estimated preparation time."), NumberRange(min=1)],
    )
    image_path = StringField(
        "Image path",
        filters=[lambda value: (value or "").strip()],
        validators=[Optional()],
    )
    submit = SubmitField("Add Dish")

    def validate_price(self, field):
        price = field.data
        if price is None:
            return
        if not price.is_finite() or price <= 0 or price.as_tuple().exponent < -2:
            raise ValidationError("Enter a price greater than zero with at most two decimal places.")


class EditDishForm(DishForm):
    submit = SubmitField("Save Dish Changes")


class ArchiveDishForm(FlaskForm):
    submit = SubmitField("Archive Dish")
