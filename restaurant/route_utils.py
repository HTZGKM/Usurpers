from flask import g, jsonify, request

from datetime import date
from decimal import Decimal
from restaurant.services.common import ServiceError


class FormValidationError(ServiceError):
    def __init__(self, errors):
        super().__init__("Please correct the form fields and try again.")
        self.errors = errors

    def as_dict(self):
        return {**super().as_dict(), "errors": self.errors}


def require_form_request():
    if request.is_json:
        raise ServiceError(
            "Submit form data instead of a JSON request body.",
            415,
            code="UNSUPPORTED_MEDIA_TYPE",
        )


def _service_value(value):
    if isinstance(value, dict):
        return {key: _service_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_service_value(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def validated_data(form_class):
    require_form_request()
    form = form_class()
    if not form.validate_on_submit():
        raise FormValidationError(form.errors)
    return {
        field.name: _service_value(field.data)
        for field in form
        if field.type not in ("CSRFTokenField", "SubmitField")
    }


def require_api_role(*roles):
    from restaurant.api.auth.routes import current_account

    account = current_account()
    if account is None:
        if g.account_inactive:
            return (
                jsonify(
                    ok=False,
                    success=False,
                    error="FORBIDDEN",
                    message="The account is inactive or no longer exists.",
                ),
                403,
            )
        return (
            jsonify(
                ok=False,
                success=False,
                error="UNAUTHENTICATED",
                message="Please log in first.",
            ),
            401,
        )
    if account["role"] not in roles:
        return (
            jsonify(
                ok=False,
                success=False,
                error="FORBIDDEN",
                message="You do not have permission to perform this action.",
            ),
            403,
        )
    return None
