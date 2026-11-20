from restaurant.db.database import get_connection
from .common import ServiceError, date_time, order_items, positive_int
from .inventory_service import reserve_for_order_line, release_for_order_line


def refresh_order_status(db, order_id):
    counts=db.execute("SELECT COUNT(*) total,SUM(status='served') served,SUM(status='cancelled') cancelled FROM order_lines WHERE order_id=?",(order_id,)).fetchone()
    if not counts or not counts["total"]: return
    if counts["cancelled"]==counts["total"]: status="cancelled"
    elif counts["served"]+counts["cancelled"]==counts["total"]: status="completed"
    else: status="active"
    db.execute("UPDATE order_headers SET status=? WHERE order_id=?",(status,order_id))


def create_dine_in_order(visit_id, items, customer_phone=None):
    visit = positive_int(visit_id, "visit_id")
    lines = order_items(items)
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        session = db.execute("SELECT * FROM dining_sessions WHERE visit_id=? AND status='seated'", (visit,)).fetchone()
        if not session: raise ServiceError("堂食记录不存在或已结束。", 409, "visit_id")
        if customer_phone and session["customer_phone"] != customer_phone: raise ServiceError("无权为该堂食记录下单。",403,code="FORBIDDEN")
        header = db.execute("INSERT INTO order_headers(visit_id,customer_phone,contact_name,phone_number,table_id) VALUES(?,?,?,?,?)", (visit, customer_phone or session["customer_phone"],session["contact_name"],session["phone_number"],session["table_id"]))
        order_id = header.lastrowid
        total = 0
        for line in lines:
            dish = db.execute("SELECT price FROM dishes WHERE dish_id=? AND is_available=1",(line["dish_id"],)).fetchone()
            if not dish: raise ServiceError(f"菜品 {line['dish_id']} 不存在或当前停售。",409,"items")
            price = float(dish["price"]); total += price * line["quantity"]
            line_cur=db.execute("INSERT INTO order_lines(order_id,dish_id,quantity,unit_price,note) VALUES(?,?,?,?,?)",(order_id,line["dish_id"],line["quantity"],price,line["note"]))
            reserve_for_order_line(db,line_cur.lastrowid,line["dish_id"],line["quantity"])
            db.execute("INSERT INTO kitchen_queue(order_id,order_item_id,dish_id,quantity) VALUES(?,?,?,?)",(order_id,line_cur.lastrowid,line["dish_id"],line["quantity"]))
        return {"order_id": order_id, "total_amount": round(total,2), "status":"active", "payment_status":"unpaid"}


def create_preorder(booking_id, customer_phone, items, estimated_ready_at):
    bid=positive_int(booking_id,"booking_id"); ready=date_time(estimated_ready_at)
    lines=order_items(items)
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        booking=db.execute("SELECT * FROM bookings WHERE booking_id=? AND customer_phone=? AND status='booked'",(bid,customer_phone)).fetchone()
        if not booking: raise ServiceError("预订不存在、已取消或不属于当前顾客。",404)
        header=db.execute("INSERT INTO order_headers(booking_id,customer_phone,contact_name,phone_number,table_id,order_type) VALUES(?,?,?,?,?,'preorder')",(bid,customer_phone,booking["contact_name"],booking["phone_number"],booking["table_id"]))
        oid=header.lastrowid; total=0
        for item in lines:
            dish=db.execute("SELECT price FROM dishes WHERE dish_id=? AND is_available=1 AND is_archived=0",(item["dish_id"],)).fetchone()
            if not dish: raise ServiceError(f"菜品 {item['dish_id']} 不存在或停售。",409,"items","RESOURCE_CONFLICT")
            price=float(dish["price"]); total+=price*item["quantity"]
            cur=db.execute("INSERT INTO order_lines(order_id,dish_id,quantity,unit_price,note,estimated_ready_at) VALUES(?,?,?,?,?,?)",(oid,item["dish_id"],item["quantity"],price,item["note"],ready))
            reserve_for_order_line(db,cur.lastrowid,item["dish_id"],item["quantity"])
        return {"order_id":oid,"total_amount":round(total,2),"status":"active","payment_status":"unpaid","estimated_ready_at":ready,"kitchen_queued":False}


def calculate_total(order_id):
    oid=positive_int(order_id,"order_id")
    with get_connection() as db:
        row=db.execute("SELECT COALESCE(SUM(quantity*unit_price),0) total FROM order_lines WHERE order_id=? AND status<>'cancelled'",(oid,)).fetchone()
        if not db.execute("SELECT 1 FROM order_headers WHERE order_id=?",(oid,)).fetchone(): raise ServiceError("订单不存在。",404)
        return float(row["total"])


def cancel_order_item(order_id, order_item_id, customer_phone=None):
    oid=positive_int(order_id,"order_id"); iid=positive_int(order_item_id,"order_item_id")
    with get_connection() as db:
        q="SELECT l.status,h.payment_status,h.customer_phone FROM order_lines l JOIN order_headers h USING(order_id) WHERE l.order_id=? AND l.order_item_id=?"
        row=db.execute(q,(oid,iid)).fetchone()
        if not row: raise ServiceError("订单明细不存在。",404)
        if customer_phone and row["customer_phone"]!=customer_phone: raise ServiceError("无权修改此订单。",403,code="FORBIDDEN")
        if row["payment_status"]!="unpaid" or row["status"]!="waiting": raise ServiceError("仅未付款且尚未开始制作的菜品可以取消。",409)
        release_for_order_line(db,iid)
        db.execute("UPDATE order_lines SET status='cancelled' WHERE order_item_id=? AND status='waiting'",(iid,))
        db.execute("UPDATE kitchen_queue SET status='cancelled',completed_at=CURRENT_TIMESTAMP WHERE order_item_id=? AND status='waiting'",(iid,))
        refresh_order_status(db,oid)
        return {"order_id":oid,"order_item_id":iid,"total_amount":calculate_total(oid)}


def pay_order(order_id, customer_phone=None):
    oid=positive_int(order_id,"order_id")
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        q="SELECT status,payment_status FROM order_headers WHERE order_id=?"; args=[oid]
        if customer_phone: q += " AND customer_phone=?"; args.append(customer_phone)
        row=db.execute(q,args).fetchone()
        if not row: raise ServiceError("订单不存在。",404)
        if row["payment_status"]=="paid": return {"order_id":oid,"payment_status":"paid","already_paid":True}
        if row["status"]=="cancelled": raise ServiceError("已取消订单不能付款。",409)
        amount=db.execute("SELECT COALESCE(SUM(quantity*unit_price),0) FROM order_lines WHERE order_id=? AND status<>'cancelled'",(oid,)).fetchone()[0]
        db.execute("INSERT INTO payments(order_id,amount) VALUES(?,?)",(oid,amount))
        db.execute("UPDATE order_headers SET payment_status='paid',paid_at=CURRENT_TIMESTAMP WHERE order_id=? AND payment_status='unpaid'",(oid,))
        return {"order_id":oid,"payment_status":"paid","already_paid":False}


def get_order(order_id, customer_phone=None):
    oid=positive_int(order_id,"order_id")
    with get_connection() as db:
        query="SELECT * FROM order_headers WHERE order_id=?"; args=[oid]
        if customer_phone: query += " AND customer_phone=?"; args.append(customer_phone)
        order=db.execute(query,args).fetchone()
        if not order: raise ServiceError("订单不存在。",404,"order_id","NOT_FOUND")
        result=dict(order)
        result["items"]=[dict(r) for r in db.execute("SELECT l.*,d.dish_name FROM order_lines l JOIN dishes d USING(dish_id) WHERE l.order_id=? ORDER BY l.order_item_id",(oid,))]
        result["total_amount"]=float(db.execute("SELECT COALESCE(SUM(quantity*unit_price),0) FROM order_lines WHERE order_id=? AND status<>'cancelled'",(oid,)).fetchone()[0])
        result["refunded_amount"]=float(db.execute("SELECT COALESCE(SUM(amount),0) FROM refunds WHERE order_id=?",(oid,)).fetchone()[0])
        return result


def get_customer_orders(customer_phone):
    with get_connection() as db:
        return [dict(r) for r in db.execute("SELECT * FROM order_headers WHERE customer_phone=? ORDER BY created_at DESC",(customer_phone,))]


def get_orders(active_only=False, phone=None, table_id=None):
    sql="SELECT * FROM order_headers WHERE 1=1"; args=[]
    if active_only: sql += " AND status='active'"
    if phone is not None: sql += " AND phone_number=?"; args.append(phone)
    if table_id is not None: sql += " AND table_id=?"; args.append(positive_int(table_id,"table_id"))
    sql += " ORDER BY created_at DESC"
    with get_connection() as db: return [dict(r) for r in db.execute(sql,args)]


def cancel_order(order_id, customer_phone=None):
    oid=positive_int(order_id,"order_id")
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        q="SELECT * FROM order_headers WHERE order_id=?"; args=[oid]
        if customer_phone: q += " AND customer_phone=?"; args.append(customer_phone)
        row=db.execute(q,args).fetchone()
        if not row: raise ServiceError("订单不存在。",404)
        if row["payment_status"]!="unpaid": raise ServiceError("已付款订单不能取消。",409)
        if db.execute("SELECT 1 FROM order_lines WHERE order_id=? AND status<>'waiting' AND status<>'cancelled'",(oid,)).fetchone(): raise ServiceError("已有菜品开始制作，不能取消订单。",409)
        old_lines=db.execute("SELECT order_item_id FROM order_lines WHERE order_id=? AND status='waiting'",(oid,)).fetchall()
        for line in old_lines: release_for_order_line(db,line[0])
        db.execute("UPDATE order_lines SET status='cancelled' WHERE order_id=? AND status='waiting'",(oid,))
        db.execute("UPDATE kitchen_queue SET status='cancelled',completed_at=CURRENT_TIMESTAMP WHERE order_id=? AND status='waiting'",(oid,))
        refresh_order_status(db,oid)
        return {"order_id":oid,"status":"cancelled"}


def update_order(order_id, items, customer_phone=None):
    oid=positive_int(order_id,"order_id"); lines=order_items(items)
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        query="SELECT * FROM order_headers WHERE order_id=?"; args=[oid]
        if customer_phone: query+=" AND customer_phone=?"; args.append(customer_phone)
        order=db.execute(query,args).fetchone()
        if not order: raise ServiceError("订单不存在。",404)
        if order["status"]!="active" or order["payment_status"]!="unpaid": raise ServiceError("当前订单状态不可修改。",409)
        if db.execute("SELECT 1 FROM order_lines WHERE order_id=? AND status<>'waiting' AND status<>'cancelled'",(oid,)).fetchone(): raise ServiceError("菜品已开始制作，订单不能修改。",409)
        # Validate every new dish before mutating any existing line.
        dishes={}
        for line in lines:
            dish=db.execute("SELECT price FROM dishes WHERE dish_id=? AND is_available=1 AND is_archived=0",(line["dish_id"],)).fetchone()
            if not dish: raise ServiceError(f"菜品 {line['dish_id']} 不存在或停售。",409,"items","RESOURCE_CONFLICT")
            dishes[line["dish_id"]]=float(dish["price"])
        old_lines=db.execute("SELECT order_item_id FROM order_lines WHERE order_id=? AND status='waiting'",(oid,)).fetchall()
        for old_line in old_lines: release_for_order_line(db,old_line[0])
        db.execute("UPDATE order_lines SET status='cancelled' WHERE order_id=? AND status='waiting'",(oid,))
        db.execute("UPDATE kitchen_queue SET status='cancelled',completed_at=CURRENT_TIMESTAMP WHERE order_id=? AND status='waiting'",(oid,))
        for line in lines:
            cur=db.execute("INSERT INTO order_lines(order_id,dish_id,quantity,unit_price,note) VALUES(?,?,?,?,?)",(oid,line["dish_id"],line["quantity"],dishes[line["dish_id"]],line["note"]))
            reserve_for_order_line(db,cur.lastrowid,line["dish_id"],line["quantity"])
            db.execute("INSERT INTO kitchen_queue(order_id,order_item_id,dish_id,quantity) VALUES(?,?,?,?)",(oid,cur.lastrowid,line["dish_id"],line["quantity"]))
        result=dict(db.execute("SELECT * FROM order_headers WHERE order_id=?",(oid,)).fetchone())
        result["items"]=[dict(r) for r in db.execute("SELECT l.*,d.dish_name FROM order_lines l JOIN dishes d USING(dish_id) WHERE l.order_id=? ORDER BY l.order_item_id",(oid,))]
        result["total_amount"]=sum(float(r["unit_price"])*r["quantity"] for r in result["items"] if r["status"]!="cancelled")
        return result
