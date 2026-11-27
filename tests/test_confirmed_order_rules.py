"""Confirmed order rules, using a fresh local test database for every case."""
from backend_test_helpers import RestaurantTestCase, write
from restaurant.db.database import get_connection
from restaurant.services import kitchen_service as kitchen, order_service as orders
from restaurant.services.common import ServiceError
from restaurant.services.dining_service import get_frontdesk_visits


class ConfirmedOrderRulesTests(RestaurantTestCase):
    def setUp(self):
        super().setUp()
        with get_connection() as db:
            db.execute("UPDATE kitchen_queue SET status='served'")
            db.execute("UPDATE order_items SET status='served'")
            db.execute("UPDATE orders SET status='completed',payment_status='paid'")
            self.visit = db.execute("SELECT visit_id FROM dining_sessions WHERE status='seated' ORDER BY visit_id LIMIT 1").fetchone()[0]

    def create_order(self, dishes=(1,2)):
        result=orders.create_dine_in_order(self.visit,[dict(dish_id=d,quantity=1) for d in dishes])
        return orders.get_order(result['order_id'])

    def ready_order(self, order):
        kitchen.start_order(order['order_id'],order['version'])
        for item in order['items']:kitchen.finish_item(item['order_item_id'])
        return orders.get_order(order['order_id'])

    def serve(self, order):
        order=self.ready_order(order)
        kitchen.serve_order(order['order_id'],order['version'],'frontdesk@test')
        return orders.get_order(order['order_id'])

    def test_whole_order_queue_and_service_are_atomic(self):
        order=self.create_order(); oid=order['order_id']; a,b=order['items']
        kitchen.start_order(oid,order['version'])
        kitchen.finish_item(a['order_item_id'])
        self.assertEqual(orders.get_order(oid)['kitchen_stage'],'cooking')
        self.assertEqual({r['order_id'] for r in kitchen.get_ready_items()},set())
        visit=next(v for v in get_frontdesk_visits() if v['visit_id']==self.visit)
        self.assertEqual(visit['ready_count'],0)
        with self.assertRaises(ServiceError):kitchen.serve_order(oid,actor='desk')
        kitchen.finish_item(b['order_item_id'])
        order=orders.get_order(oid)
        self.assertEqual(order['kitchen_stage'],'ready')
        self.assertEqual(len(kitchen.get_ready_items()),2)
        self.assertEqual(next(v for v in get_frontdesk_visits() if v['visit_id']==self.visit)['ready_count'],1)
        kitchen.serve_order(oid,order['version'],'desk-first')
        self.assertTrue(kitchen.serve_order(oid,order['version'],'desk-second')['already_served'])
        self.assertEqual(orders.get_order(oid)['served_by'],'desk-first')
        chef=self.signed_in('kitchen@shuangfen.local')
        self.assertEqual(write(chef,f"/kitchen/items/{a['order_item_id']}/serve").status_code,403)

    def test_capacity_limit_version_and_reduction_preserve_existing_work(self):
        batch=[self.create_order((1,)) for _ in range(6)]
        for order in batch[:5]:kitchen.start_order(order['order_id'],order['version'])
        with self.assertRaises(ServiceError) as caught:kitchen.start_order(batch[-1]['order_id'],1)
        self.assertEqual(caught.exception.code,'KITCHEN_CAPACITY')
        setting=kitchen.get_settings(); kitchen.update_settings(2,setting['version'],'manager')
        self.assertEqual(kitchen.get_settings()['active_orders'],5)
        with self.assertRaises(ServiceError):kitchen.update_settings(7,setting['version'],'stale-manager')
        with get_connection() as db:
            audit=db.execute('SELECT actor,old_limit,new_limit FROM kitchen_settings_audit').fetchone()
            self.assertEqual(tuple(audit),('manager',5,2))

    def test_cancel_version_prevents_stale_start(self):
        order=self.create_order(); oid=order['order_id']
        orders.cancel_order_item(oid,order['items'][0]['order_item_id'],expected_version=order['version'])
        with self.assertRaises(ServiceError) as caught:kitchen.start_order(oid,order['version'])
        self.assertEqual(caught.exception.code,'ORDER_CHANGED')
        current=orders.get_order(oid);kitchen.start_order(oid,current['version'])
        with self.assertRaises(ServiceError):orders.cancel_order_item(oid,order['items'][1]['order_item_id'],expected_version=current['version'])

    def test_supply_replacement_is_linked_atomic_and_independent(self):
        order=self.create_order(); oid=order['order_id']; a,b=order['items']
        kitchen.report_unavailable(a['order_item_id'],'Ingredient unavailable','chef',order['version'])
        current=orders.get_order(oid);kitchen.start_order(oid,current['version'])
        kitchen.finish_item(b['order_item_id'])
        current=orders.get_order(oid);self.assertEqual(current['kitchen_stage'],'cooking')
        with self.assertRaises(ServiceError):orders.cancel_order_item(oid,a['order_item_id'],expected_version=current['version'])
        with self.assertRaises(ServiceError):
            orders.resolve_supply_issue(oid,a['order_item_id'],'replace','Guest choice','desk',current['version'],True,[dict(dish_id=2,quantity=1,quoted_unit_cents=1)],'bad-price')
        self.assertEqual(orders.get_order(oid)['items'][0]['status'],'waiting')
        with get_connection() as db:price=round(float(db.execute('SELECT price FROM dishes WHERE dish_id=2').fetchone()[0])*100)
        result=orders.resolve_supply_issue(oid,a['order_item_id'],'replace','Guest choice','desk',current['version'],True,[dict(dish_id=2,quantity=1,quoted_unit_cents=price)],'resolution-1')
        replay=orders.resolve_supply_issue(oid,a['order_item_id'],'replace','Guest choice','desk',current['version'],True,[dict(dish_id=2,quantity=1,quoted_unit_cents=price)],'resolution-1')
        self.assertEqual(result,replay)
        original=orders.get_order(oid); replacement=orders.get_order(result['replacement_order_id'])
        self.assertEqual(original['kitchen_stage'],'ready')
        self.assertEqual(replacement['kitchen_stage'],'waiting')
        self.assertEqual(replacement['visit_id'],self.visit)
        self.assertEqual(replacement['replaces_item_id'],a['order_item_id'])
        kitchen.serve_order(oid,original['version'],'desk')
        self.assertFalse(orders.get_visit_bill(self.visit)['can_pay'])

    def test_table_bill_rechecks_all_orders_and_replays_payment(self):
        first=self.create_order((1,));second=self.create_order((2,))
        self.assertFalse(orders.get_visit_bill(self.visit)['can_pay'])
        with self.assertRaises(ServiceError):orders.pay_order(first['order_id'])
        for order in (first,second):self.serve(order)
        bill=orders.get_visit_bill(self.visit)
        with self.assertRaises(ServiceError):orders.pay_visit(self.visit,None,[first['order_id']],bill['total_cents'],request_key='subset',actor='desk')
        with self.assertRaises(ServiceError):orders.pay_visit(self.visit,None,bill['order_ids'],bill['total_cents']-1,request_key='amount',actor='desk')
        paid=orders.pay_visit(self.visit,None,bill['order_ids'],bill['total_cents'],request_key='payment-1',actor='desk')
        self.assertFalse(paid['already_paid'])
        self.assertTrue(orders.pay_visit(self.visit,None,bill['order_ids'],bill['total_cents'],request_key='payment-1',actor='desk')['already_paid'])
        extra=self.serve(self.create_order((1,)))
        self.assertEqual(orders.get_visit_bill(self.visit)['order_ids'],[extra['order_id']])

    def test_name_category_snapshot_and_retained_sold_out_dish(self):
        order=self.create_order(); first=order['items'][0]
        with get_connection() as db:
            db.execute("UPDATE dishes SET dish_name='Renamed',category='drinks',is_available=0 WHERE dish_id=1")
        current=orders.get_order(order['order_id'])
        self.assertEqual(current['items'][0]['dish_name'],first['dish_name'])
        self.assertEqual(current['items'][0]['category_snapshot'],first['category_snapshot'])
        result=orders.update_order(order['order_id'],[dict(dish_id=1,quantity=1),dict(dish_id=2,quantity=2)],expected_version=order['version'])
        self.assertEqual(result['items'][0]['order_item_id'],first['order_item_id'])
        self.assertEqual(result['items'][0]['unit_price'],first['unit_price'])

    def test_staff_api_requires_order_version_and_table_payment_contract(self):
        order=self.create_order((1,));chef=self.signed_in('kitchen@shuangfen.local');desk=self.signed_in('frontdesk@shuangfen.local')
        path=f"/kitchen/orders/{order['order_id']}/start"
        self.assertEqual(write(chef,path).status_code,400)
        self.assertEqual(write(chef,path,{'expected_version':order['version']}).status_code,200)
        item=order['items'][0]
        self.assertEqual(write(chef,f"/kitchen/items/{item['order_item_id']}/complete").status_code,200)
        current=orders.get_order(order['order_id'])
        self.assertEqual(write(desk,f"/frontdesk/orders/{order['order_id']}/serve",{'expected_version':current['version']}).status_code,200)
        bill=desk.get(f'/visits/{self.visit}/bill').get_json()['bill']
        self.assertEqual(write(desk,f'/visits/{self.visit}/pay',{'order_ids':','.join(map(str,bill['order_ids'])),'total_cents':bill['total_cents'],'idempotency_key':'api-table-payment'}).status_code,200)
