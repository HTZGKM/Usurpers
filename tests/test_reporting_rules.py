from datetime import datetime, timedelta
from unittest.mock import patch

from backend_test_helpers import RestaurantTestCase
from restaurant.db.database import get_connection
from restaurant.services.admin_workspace_service import get_ledger, get_workspace, RESTAURANT_TIME


class ReportingRulesTests(RestaurantTestCase):
    def test_history_preserves_name_and_uncategorized_snapshot_after_menu_change(self):
        with get_connection() as db:
            db.execute("""UPDATE order_items SET dish_name_snapshot='Original burger',category_snapshot=NULL
                WHERE order_item_id=9001""")
            db.execute("UPDATE dishes SET dish_name='Renamed burger',category='drinks' WHERE dish_id=1")
        order = next(row for row in get_ledger(None) if row['order_id'] == 9001)
        item = next(row for row in order['items'] if row['dish_id'] == 1)
        self.assertEqual(item['dish_name'], 'Original burger')
        self.assertIsNone(item['category'])

    def test_paid_today_fetches_old_orders_and_uses_beijing_midnight(self):
        now = datetime.now(RESTAURANT_TIME).replace(hour=12,minute=0,second=0,microsecond=0)
        yesterday = now.date() - timedelta(days=1)
        old = now.date() - timedelta(days=60)
        with get_connection() as db:
            db.execute("""UPDATE orders SET created_at=?,paid_at=?,payment_status='paid',status='completed'
                WHERE order_id=9001""", (str(old)+' 04:00:00',str(yesterday)+' 16:01:00'))
        with patch('restaurant.services.admin_workspace_service.datetime') as clock:
            clock.now.return_value = now
            workspace = get_workspace()
        order = next(row for row in workspace['orders'] if row['order_id'] == 9001)
        self.assertEqual(order['paid_at'],str(yesterday)+' 16:01:00')
        self.assertEqual(workspace['history_days'],30)
        self.assertNotEqual(order['created_at'][:10],workspace['service_date'])
