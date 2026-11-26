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
    FieldList,
    Form,
    FormField,
)
from wtforms.validators import (
    DataRequired,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)
from restaurant.forms import (
    iso_date_time,
    monetary_amount,
    nonnegative_number,
    nonzero_number,
    positive_number,
)
from restaurant.services.menu_service import MENU_CATEGORIES


def dish_category_field():
    return SelectField(
        "Category",
        choices=[("", "Uncategorized")] + [(key, key.title()) for key in MENU_CATEGORIES],
        validators=[Optional()],
    )


class EditStaffForm(FlaskForm):
    name = StringField(
        "Name",
        filters=[lambda value: (value or "").strip()],
        validators=[DataRequired("Enter the staff member's name."), Length(max=100)],
    )
    phone_number = StringField(
        "Phone number",
        filters=[lambda value: (value or "").strip()],
        validators=[
            DataRequired("Enter a phone number."),
            Regexp(
                r"\+?[0-9]+\Z", message="Enter digits only, with an optional leading +."
            ),
        ],
    )
    email = EmailField(
        "Email address",
        filters=[lambda value: (value or "").strip()],
        validators=[
            DataRequired("Enter an email address."),
            Regexp(
                r"[^@\s]+@[^@\s]+\.[^@\s]+\Z", message="Enter a valid email address."
            ),
        ],
    )
    role = SelectField(
        "Role",
        choices=[("frontdesk", "Front Desk"), ("kitchen", "Kitchen")],
        validators=[InputRequired("Select a staff role.")],
    )
    submit = SubmitField("Save Staff Changes")


class CreateStaffForm(EditStaffForm):
    password = PasswordField(
        "Password", validators=[InputRequired("Enter a password."), Length(min=6)]
    )
    submit = SubmitField("Create Staff Account")


class DeactivateStaffForm(FlaskForm):
    submit = SubmitField("Deactivate Staff Account")


class DishForm(FlaskForm):
    category = dish_category_field()
    name = StringField(
        "Dish name",
        filters=[lambda value: (value or "").strip()],
        validators=[DataRequired("Enter the dish name."), Length(max=100)],
    )
    price = DecimalField(
        "Price", places=None, validators=[InputRequired("Enter a price.")]
    )
    ingredients = TextAreaField(
        "Ingredients", default="", validators=[Optional(), Length(max=1000)]
    )
    prep_time_minutes = IntegerField(
        "Estimated preparation time (minutes)",
        validators=[
            InputRequired("Enter the estimated preparation time."),
            NumberRange(min=1),
        ],
    )
    image_path = StringField(
        "Image path",
        filters=[lambda value: (value or "").strip()],
        validators=[Optional(), Length(max=500)],
    )
    submit = SubmitField("Add Dish")

    def validate_price(self, field):
        price = field.data
        if price is None:
            return
        if not price.is_finite() or price <= 0 or price.as_tuple().exponent < -2:
            raise ValidationError(
                "Enter a price greater than zero with at most two decimal places."
            )


class EditDishForm(FlaskForm):
    name = StringField("Dish name", validators=[Optional(), Length(max=100)])
    price = DecimalField("Price", places=None, validators=[Optional(), monetary_amount])
    category = dish_category_field()
    ingredients = TextAreaField("Ingredients", validators=[Optional(), Length(max=1000)])
    prep_time_minutes = IntegerField("Preparation (min)", validators=[Optional(), NumberRange(min=1)])
    submit = SubmitField("Save Dish Changes")


class ArchiveDishForm(FlaskForm):
    submit = SubmitField("Archive Dish")


class ResetStaffPasswordForm(FlaskForm):
    password = PasswordField(
        "New password", validators=[InputRequired(), Length(min=6)]
    )


class IngredientForm(FlaskForm):
    name = StringField("Ingredient name", validators=[DataRequired(), Length(max=100)])
    unit = StringField("Unit", validators=[DataRequired(), Length(max=20)])
    on_hand = DecimalField(
        "Stock quantity", places=None, validators=[InputRequired(), nonnegative_number]
    )
    expires_at = StringField(
        "Expiry date",
        filters=[lambda value: value or None],
        validators=[Optional(), Length(max=32), iso_date_time],
    )


class StockAdjustmentForm(FlaskForm):
    idempotency_key = StringField("Stock adjustment submission ID", validators=[Optional(), Length(max=80)])
    quantity = DecimalField(
        "Quantity change", places=None, validators=[InputRequired(), nonzero_number]
    )
    movement_type = SelectField(
        "Movement type",
        choices=[
            (value, value.title())
            for value in ("adjustment", "delivery", "spoilage", "correction")
        ],
        default="adjustment",
    )
    reference = StringField(
        "Reference",
        filters=[lambda value: value or None],
        validators=[Optional(), Length(max=120)],
    )


class RecipeIngredientForm(Form):
    ingredient_id = IntegerField(
        "Ingredient ID", validators=[InputRequired(), NumberRange(min=1)]
    )
    quantity_per_dish = DecimalField(
        "Quantity per dish", places=None, validators=[InputRequired(), positive_number]
    )


class RecipeForm(FlaskForm):
    ingredients = FieldList(FormField(RecipeIngredientForm))
