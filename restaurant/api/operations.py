from flask import Blueprint, g, jsonify

from restaurant.forms import ActionForm
from restaurant.route_utils import require_api_role, validated_data
from restaurant.services import allocation
from restaurant.services.queue_manager import QueueManager


operations_bp = Blueprint("operations", __name__, url_prefix="/operations")


@operations_bp.post("/refresh")
def refresh():
    denied = require_api_role("customer", "frontdesk", "kitchen", "admin")
    if denied is not None:
        return denied
    validated_data(ActionForm)
    role = g.account["role"]
    if role == "customer":
        allocation.advance_customer_deadlines(g.account["username"])
    elif role == "frontdesk":
        if allocation.enabled():
            allocation.advance_service()
        else:
            QueueManager.expire_called()
    else:
        QueueManager.enqueue_due_preorders()
    return jsonify(ok=True)
