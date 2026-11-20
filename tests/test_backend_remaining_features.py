"""Regression tests for inventory, remake tickets and simulated refunds."""
import os
import unittest
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path

ROOT=Path(__file__).resolve().parent/".remaining_runtime"
ROOT.mkdir(exist_ok=True)
os.environ["USURPERS_DB_PATH"]=str(ROOT/"remaining.db")

from restaurant.db.database import ensure_database,get_connection
from restaurant.services.common import ServiceError
from restaurant.services.inventory_service import adjust_stock
from restaurant.services.order_service import create_dine_in_order,cancel_order_item,pay_order
from restaurant.services.kitchen_service import start_item,finish_item,serve_item
from restaurant.services.remake_service import create_remake,start_remake,complete_remake
from restaurant.services.refund_service import create_refund
from restaurant.services.kitchen_service import get_waiting_items
from restaurant.scheduler import run_scheduled_tasks
from app import create_app


class RemainingFeatureTests(unittest.TestCase):
    def setUp(self):
        os.environ["USURPERS_DB_PATH"]=str(ROOT/"remaining.db")
        ensure_database(reset=True)

    def configure_recipe(self,stock):
        with get_connection() as db:
            db.execute("INSERT INTO ingredients(name,unit,on_hand) VALUES('test-cheese','g',?)",(stock,))
            db.execute("INSERT INTO dish_ingredients(dish_id,ingredient_id,quantity_per_dish) VALUES(6,1,10)")

    def test_stock_reservation_prevents_oversell_and_cancel_releases(self):
        self.configure_recipe(10)
        first=create_dine_in_order(1,[{"dish_id":6,"quantity":1}],"13900000002")
        with get_connection() as db:
            line=db.execute("SELECT order_item_id FROM order_lines WHERE order_id=?",(first["order_id"],)).fetchone()[0]
            self.assertEqual(db.execute("SELECT reserved FROM ingredients WHERE ingredient_id=1").fetchone()[0],10)
        with self.assertRaises(ServiceError):
            create_dine_in_order(1,[{"dish_id":6,"quantity":1}],"13900000002")
        cancel_order_item(first["order_id"],line,"13900000002")
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT reserved FROM ingredients WHERE ingredient_id=1").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT status FROM inventory_reservations WHERE order_item_id=?",(line,)).fetchone()[0],"released")

    def test_concurrent_orders_cannot_reserve_the_same_last_stock(self):
        self.configure_recipe(10)
        gate=Barrier(2)
        def submit():
            gate.wait()
            try: return create_dine_in_order(1,[{"dish_id":6,"quantity":1}],"13900000002")["order_id"]
            except ServiceError: return None
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:submit(),range(2)))
        self.assertEqual(sum(value is not None for value in results),1)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT reserved FROM ingredients WHERE ingredient_id=1").fetchone()[0],10)
            self.assertEqual(db.execute("SELECT count(*) FROM inventory_reservations WHERE status='reserved'").fetchone()[0],1)

    def test_starting_item_consumes_reserved_stock_once(self):
        self.configure_recipe(30)
        order=create_dine_in_order(1,[{"dish_id":6,"quantity":2}],"13900000002")
        with get_connection() as db: iid=db.execute("SELECT order_item_id FROM order_lines WHERE order_id=?",(order["order_id"],)).fetchone()[0]
        start_item(iid)
        with self.assertRaises(ServiceError): start_item(iid)
        with get_connection() as db:
            ingredient=db.execute("SELECT on_hand,reserved FROM ingredients WHERE ingredient_id=1").fetchone()
            self.assertEqual(tuple(ingredient),(10,0))
            self.assertEqual(db.execute("SELECT status FROM inventory_reservations WHERE order_item_id=?",(iid,)).fetchone()[0],"consumed")
            self.assertEqual(db.execute("SELECT count(*) FROM inventory_movements WHERE reference=?",(str(iid),)).fetchone()[0],1)

    def test_order_header_completes_only_after_all_lines_are_served(self):
        order=create_dine_in_order(1,[{"dish_id":5,"quantity":1},{"dish_id":6,"quantity":1}],"13900000002")
        with get_connection() as db: ids=[r[0] for r in db.execute("SELECT order_item_id FROM order_lines WHERE order_id=? ORDER BY order_item_id",(order["order_id"],))]
        for iid in ids:
            start_item(iid); finish_item(iid); serve_item(iid)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM order_headers WHERE order_id=?",(order["order_id"],)).fetchone()[0],"completed")

    def test_remake_is_separate_duplicate_safe_and_preserves_original(self):
        with get_connection() as db: db.execute("UPDATE order_lines SET status='served' WHERE order_item_id=9001")
        ticket=create_remake(9001,"送错桌",2)
        with self.assertRaises(ServiceError): create_remake(9001,"重复点击",2)
        self.assertEqual(start_remake(ticket["remake_id"])["status"],"cooking")
        self.assertEqual(complete_remake(ticket["remake_id"])["status"],"completed")
        self.assertTrue(any(x.get("task_type")=="remake" for x in get_waiting_items()) is False)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT status FROM order_lines WHERE order_item_id=9001").fetchone()[0],"served")
            self.assertEqual(db.execute("SELECT count(*) FROM remake_tickets WHERE order_item_id=9001").fetchone()[0],1)

    def test_refund_is_idempotent_and_cumulative_amount_is_bounded(self):
        pay_order(9001)
        first=create_refund(9001,20,"顾客反馈",2,"refund-request-1")
        retry=create_refund(9001,20,"顾客反馈",2,"refund-request-1")
        self.assertTrue(retry["already_refunded"])
        with self.assertRaises(ServiceError): create_refund(9001,100,"超额退款",2,"refund-request-2")
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM refunds WHERE order_id=9001").fetchone()[0],1)
            self.assertEqual(float(db.execute("SELECT amount FROM refunds WHERE refund_id=?",(first["refund_id"],)).fetchone()[0]),20)
            self.assertEqual(db.execute("SELECT payment_status FROM order_headers WHERE order_id=9001").fetchone()[0],"paid")

    def test_deactivated_customer_session_is_rejected_and_history_remains(self):
        app=create_app(); customer=app.test_client(); admin=app.test_client()
        self.assertEqual(customer.post("/auth/login",json={"account":"13900000002","password":"123456"}).status_code,200)
        self.assertEqual(admin.post("/auth/login",json={"account":"admin@shuangfen.local","password":"123456"}).status_code,200)
        self.assertEqual(admin.post("/admin/customers/13900000002/deactivate",json={}).status_code,200)
        self.assertEqual(customer.get("/orders").status_code,403)
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT is_active FROM customers WHERE customer_phone='13900000002'").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM order_headers WHERE customer_phone='13900000002'").fetchone()[0],1)
        self.assertEqual(admin.post("/admin/customers/13900000002/activate",json={}).status_code,200)
        self.assertEqual(customer.post("/auth/login",json={"account":"13900000002","password":"123456"}).status_code,200)
        self.assertEqual(customer.get("/orders").status_code,200)

    def test_background_tick_promotes_due_preorder_idempotently(self):
        with get_connection() as db:
            db.execute("INSERT INTO bookings(booking_id,contact_name,phone_number,customer_phone,booking_date,time_slot_id,party_size,status,table_id) VALUES(77,'scheduler','13900000001','13900000001','2026-12-10',1,2,'booked',1)")
        from restaurant.services.order_service import create_preorder
        order=create_preorder(77,"13900000001",[{"dish_id":6,"quantity":1}],"2026-11-20 10:00:00")
        first=run_scheduled_tasks("2026-11-20 11:00:00")
        second=run_scheduled_tasks("2026-11-20 11:00:00")
        with get_connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM kitchen_queue WHERE order_id=?",(order["order_id"],)).fetchone()[0],1)
        self.assertGreaterEqual(first["promoted_preorders"],1)
        self.assertEqual(second["promoted_preorders"],0)

    def test_flask_server_process_restart_recovers_persistent_queue(self):
        with get_connection() as db:
            before=db.execute("SELECT count(*) FROM kitchen_queue").fetchone()[0]
            db.execute("UPDATE kitchen_queue SET status='cooking',started_at=CURRENT_TIMESTAMP WHERE order_item_id=9001")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
        env=dict(os.environ,USURPERS_DB_PATH=str(ROOT/"remaining.db"))
        command=[sys.executable,"-c",f"from app import create_app; create_app().run(host='127.0.0.1',port={port},use_reloader=False)"]
        processes=[]
        log_files=[]
        log_path=ROOT/"server.log"
        try:
            for _ in range(2):
                log_file=log_path.open("w",encoding="utf-8")
                log_files.append(log_file)
                proc=subprocess.Popen(command,cwd=str(Path(__file__).resolve().parents[1]),env=env,stdout=log_file,stderr=subprocess.STDOUT)
                processes.append(proc)
                deadline=time.time()+10
                while time.time()<deadline:
                    if proc.poll() is not None: self.fail("Flask 子进程意外退出")
                    try:
                        import urllib.request
                        urllib.request.urlopen(f"http://127.0.0.1:{port}/health",timeout=0.5); break
                    except Exception: time.sleep(0.1)
                else: self.fail("Flask 子进程未能启动: "+log_path.read_text(encoding="utf-8",errors="replace"))
                proc.terminate(); proc.wait(timeout=5); log_file.close()
            with get_connection() as db:
                self.assertEqual(db.execute("SELECT status FROM kitchen_queue WHERE order_item_id=9001").fetchone()[0],"cooking")
                self.assertEqual(db.execute("SELECT count(*) FROM kitchen_queue").fetchone()[0],before)
        finally:
            for proc in processes:
                if proc.poll() is None: proc.kill(); proc.wait(timeout=5)
            for log_file in log_files:
                if not log_file.closed: log_file.close()


if __name__=="__main__": unittest.main()
