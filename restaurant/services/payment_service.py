"""Payment operations; amounts are always derived from persisted order lines."""
from .order_service import pay_order


def collect_payment(order_id, customer_phone=None):
    return pay_order(order_id, customer_phone)
