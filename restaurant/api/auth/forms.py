from flask_wtf import FlaskForm
from wtforms import HiddenField, IntegerField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, InputRequired, Length, ValidationError
from restaurant.services.phone_identity import normalize_phone
from restaurant.services.common import ServiceError


def phone_identity(form, field):
    try:
        field.data = normalize_phone(field.data)
    except ServiceError as error:
        raise ValidationError(error.message) from None


def password_content(form, field):
    if not (field.data or "").strip():
        raise ValidationError("The password cannot contain only spaces.")


class LoginForm(FlaskForm):
    account = StringField(
        "Phone number or email address",
        filters=[lambda value: (value or "").strip()],
        validators=[DataRequired("Enter your phone number or email address."), Length(max=254)],
    )
    password = PasswordField(
        "Password",
        validators=[InputRequired("Enter your password."), Length(max=128)],
    )
    submit = SubmitField("Log In")


class RegisterForm(FlaskForm):
    name = StringField(
        "Name",
        filters=[lambda value: (value or "").strip()],
        validators=[DataRequired("Enter your name."), Length(max=100)],
    )
    phone_number = StringField(
        "Phone number",
        filters=[lambda value: (value or "").strip()],
        validators=[
            DataRequired("Enter your phone number."),
            phone_identity,
        ],
    )
    password = PasswordField(
        "Password",
        validators=[InputRequired("Enter a password."), Length(min=6, max=128), password_content],
    )
    submit = SubmitField("Create Account")


class LogoutForm(FlaskForm):
    submit = SubmitField("Log Out")


class ProfileForm(FlaskForm):
    name = StringField("Name", filters=[lambda v: (v or "").strip()], validators=[DataRequired(), Length(max=100)])
    submit = SubmitField("Save name")


class RecoveryEmailForm(FlaskForm):
    email = StringField("Recovery email", validators=[DataRequired(), Length(max=254)])
    current_password = PasswordField("Current password", validators=[InputRequired(), Length(max=128)])
    submit = SubmitField("Send verification email")


class ForgotPasswordForm(FlaskForm):
    phone_number = StringField("Sign-in phone number", validators=[DataRequired(), phone_identity])
    submit = SubmitField("Send reset link")


class VerifyEmailForm(FlaskForm):
    token = HiddenField("Verification token", validators=[InputRequired(), Length(min=32,max=128)])
    submit = SubmitField("Verify recovery email")


class ResetPasswordForm(VerifyEmailForm):
    password = PasswordField("New password", validators=[InputRequired(), Length(min=6,max=128), password_content])
    password_confirmation = PasswordField("Confirm password", validators=[InputRequired(), EqualTo("password", message="The passwords must match.")])
    submit = SubmitField("Reset password")


class LinkRequestForm(FlaskForm):
    target_type = SelectField("Record type", choices=[("booking","Reservation"),("visit","Visit"),("queue","Waitlist ticket")], validators=[InputRequired()])
    target_id = IntegerField("Record ID", validators=[InputRequired()])
    candidate_phone = StringField("Customer phone", validators=[DataRequired(), phone_identity])


class LinkConfirmationForm(FlaskForm):
    expected_version = StringField("Reservation version")
