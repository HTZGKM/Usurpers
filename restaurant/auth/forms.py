from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, InputRequired, Regexp


class LoginForm(FlaskForm):
    account = StringField(
        "Phone number or email address",
        filters=[lambda value: (value or "").strip()],
        validators=[DataRequired("Enter your phone number or email address.")],
    )
    password = PasswordField(
        "Password",
        validators=[InputRequired("Enter your password.")],
    )
    submit = SubmitField("Log In")


class RegisterForm(FlaskForm):
    name = StringField(
        "Name",
        filters=[lambda value: (value or "").strip()],
        validators=[DataRequired("Enter your name.")],
    )
    phone_number = StringField(
        "Phone number",
        filters=[lambda value: (value or "").strip()],
        validators=[
            DataRequired("Enter your phone number."),
            Regexp(r"\+?[0-9]+\Z", message="Enter digits only, with an optional leading +."),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[InputRequired("Enter a password.")],
    )
    submit = SubmitField("Create Account")


class LogoutForm(FlaskForm):
    submit = SubmitField("Log Out")
