"""Order command races against an isolated schema in disposable PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest

import test_postgres_booking_consistency as pg_fixture
TEST_DSN=pg_fixture.TEST_DSN
from restaurant.db.database import get_connection
from restaurant.services import order_service as orders, kitchen_service as kitchen
from restaurant.services.common import ServiceError


@unittest.skipUnless(TEST_DSN, 'requires disposable loopback PostgreSQL')
class PostgresOrderRulesTests(unittest.TestCase):
    phone=staticmethod(pg_fixture.PostgresBookingConsistencyTests.phone)
    def setUp(self):
        pg_fixture.PostgresBookingConsistencyTests.setUp(self)
        with get_connection() as db:
            db.execute("INSERT INTO dishes(dish_name,category,price) VALUES('Test dish','sides',12.50)")
            self.visit=db.execute("INSERT INTO dining_sessions(customer_phone,contact_name,phone_number,party_size,table_id,status) VALUES(?,'Test',?,2,1,'seated') RETURNING visit_id",(self.phone(0),self.phone(0))).fetchone()[0]

    def order(self):
        return orders.get_order(orders.create_dine_in_order(self.visit,[dict(dish_id=1,quantity=1)])['order_id'])

    def race(self,*actions):
        gate=Barrier(len(actions))
        def run(action):
            gate.wait()
            try:return ('ok',action())
            except ServiceError as error:return ('error',error.code)
        with ThreadPoolExecutor(max_workers=len(actions)) as workers:return list(workers.map(run,actions))

    def test_two_kitchens_cannot_take_last_capacity_slot(self):
        batch=[self.order() for _ in range(6)]
        for order in batch[:4]:kitchen.start_order(order['order_id'],1)
        results=self.race(*(lambda o=o:kitchen.start_order(o['order_id'],1) for o in batch[4:]))
        self.assertEqual(sum(r[0]=='ok' for r in results),1)
        self.assertEqual([r[1] for r in results if r[0]=='error'],['KITCHEN_CAPACITY'])
        self.assertEqual(kitchen.get_settings()['active_orders'],5)

    def test_cancel_and_start_same_version_have_one_winner(self):
        order=self.order();oid=order['order_id'];iid=order['items'][0]['order_item_id']
        results=self.race(lambda:kitchen.start_order(oid,1),lambda:orders.cancel_order_item(oid,iid,expected_version=1))
        self.assertEqual(sum(r[0]=='ok' for r in results),1)
        self.assertEqual([r[1] for r in results if r[0]=='error'],['ORDER_CHANGED'])
        with get_connection() as db:
            status=db.execute('SELECT i.status AS item_status,q.status AS queue_status FROM order_items i JOIN kitchen_queue q USING(order_item_id) WHERE i.order_item_id=?',(iid,)).fetchone()
            self.assertEqual(status[0],status[1])

    def test_supply_resolution_competing_requests_create_only_one_replacement(self):
        order=self.order();oid=order['order_id'];iid=order['items'][0]['order_item_id']
        kitchen.report_unavailable(iid,'Out of ingredients','chef',1)
        def resolve(key):return orders.resolve_supply_issue(oid,iid,'replace','Guest agreed','desk',2,True,[dict(dish_id=1,quantity=1,quoted_unit_cents=1250)],key)
        results=self.race(lambda:resolve('replacement-a'),lambda:resolve('replacement-b'))
        self.assertEqual(sum(r[0]=='ok' for r in results),1)
        with get_connection() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM orders WHERE replaces_item_id=?',(iid,)).fetchone()[0],1)
