from datetime import datetime
from flask_wtf import FlaskForm
from wtforms.validators import ValidationError


class ActionForm(FlaskForm):
    """Validate CSRF for an action whose record ID comes from the URL."""


def positive_number(form, field):
    if field.data is None or not field.data.is_finite() or field.data <= 0:
        raise ValidationError("Enter a finite number greater than zero.")


def nonnegative_number(form, field):
    if field.data is None or not field.data.is_finite() or field.data < 0:
        raise ValidationError("Enter a finite number greater than or equal to zero.")


def nonzero_number(form, field):
    if field.data is None or not field.data.is_finite() or field.data == 0:
        raise ValidationError("Enter a finite, nonzero number.")


def monetary_amount(form, field):
    positive_number(form, field)
    if field.data.as_tuple().exponent < -2:
        raise ValidationError("Use at most two decimal places.")


def iso_date_time(form, field):
    try:
        datetime.fromisoformat(field.data)
    except ValueError as error:
        raise ValidationError("Enter an ISO date or date and time.") from error
