from restaurant.db.database import begin_read, begin_write, get_connection, insert_id, using_postgres
from . import submission
from .common import ServiceError, date_time, order_items, positive_int


def refresh_order_status(db, order_id):
    counts=db.execute("""SELECT COUNT(*) total, SUM(CASE WHEN status='served' THEN 1 ELSE 0 END) served,
        SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) cancelled
        FROM order_items WHERE order_id=?""", (order_id,)).fetchone()
    if not counts or not counts["total"]: return
    if counts["cancelled"]==counts["total"]: status="cancelled"
    elif counts["served"]+counts["cancelled"]==counts["total"]: status="completed"
    else: status="active"
    db.execute("UPDATE orders SET status=?,version=version+1 WHERE order_id=?",(status,order_id))


def _order_total(db, order_id):
    row = db.execute("""SELECT COALESCE(SUM(total_price),0) FROM order_items
        WHERE order_id=? AND status<>'cancelled'""", (order_id,)).fetchone()
    return round(float(row[0]), 2)


def _sale_price(db, line):
    dish = db.execute("SELECT price FROM dishes WHERE dish_id=? AND is_available=1 AND is_archived=0",
                      (line["dish_id"],)).fetchone()
    if dish is None:
        raise ServiceError("A dish is no longer available. Review your order.", 409, "items", "DISH_UNAVAILABLE")
    price = float(dish["price"])
    if "quoted_unit_cents" in line and round(price * 100) != line["quoted_unit_cents"]:
        raise ServiceError("A dish price changed. Review the updated amount before placing the order.",
                           409, "items", "PRICE_CHANGED")
    return price


def _check_order_total(total):
    if total > 1_000_000:
        raise ServiceError("The order exceeds the maximum amount of ¥1,000,000.", field="items")


def create_dine_in_order(visit_id, items, customer_phone=None, *, request_key=None, actor=None):
    visit = positive_int(visit_id, "visit_id") if visit_id is not None else None
    lines = order_items(items)
    with get_connection() as db:
        begin_write(db)
        identity, payload = actor or customer_phone, [visit, lines]
        previous = submission.replay(db, "dine-in", identity, request_key, payload)
        if previous is not None:
            return previous
        if visit is None:
            current = db.execute("""SELECT visit_id FROM dining_sessions WHERE customer_phone=? AND status='seated'
                                     ORDER BY arrived_at DESC, visit_id DESC LIMIT 1""", (customer_phone,)).fetchone()
            if not current:
                raise ServiceError("Check in and be seated before ordering.", 409, "visit_id")
            visit = current[0]
        session = db.execute("SELECT * FROM dining_sessions WHERE visit_id=? AND status='seated'", (visit,)).fetchone()
        if not session: raise ServiceError("堂食记录不存在或已结束。", 409, "visit_id")
        if customer_phone and session["customer_phone"] != customer_phone: raise ServiceError("无权为该堂食记录下单。",403,code="FORBIDDEN")
        order_id = insert_id(db, "INSERT INTO orders(visit_id,customer_phone,contact_name,phone_number,table_id) VALUES(?,?,?,?,?)",
                             (visit, customer_phone or session["customer_phone"],session["contact_name"],session["phone_number"],session["table_id"]), "order_id")
        total = 0
        for line in lines:
            price = _sale_price(db, line)
            line_total = round(price * line["quantity"], 2)
            total += line_total
            item_id = insert_id(db, "INSERT INTO order_items(order_id,dish_id,quantity,unit_price,total_price,note) VALUES(?,?,?,?,?,?)",
                                (order_id,line["dish_id"],line["quantity"],price,line_total,line["note"]), "order_item_id")
            db.execute("INSERT INTO kitchen_queue(order_id,order_item_id,dish_id,quantity) VALUES(?,?,?,?)",(order_id,item_id,line["dish_id"],line["quantity"]))
        _check_order_total(total)
        result = {"order_id": order_id, "total_amount": round(total,2), "status":"active", "payment_status":"unpaid"}
        return submission.record(db, "dine-in", identity, request_key, payload, result)


def create_preorder(booking_id, customer_phone, items, estimated_ready_at, *, request_key=None):
    bid=positive_int(booking_id,"booking_id")
    lines=order_items(items)
    with get_connection() as db:
        begin_write(db)
        payload = [bid, lines, estimated_ready_at]
        previous = submission.replay(db, "preorder", customer_phone, request_key, payload)
        if previous is not None:
            return previous
        booking=db.execute("SELECT * FROM bookings WHERE booking_id=? AND customer_phone=? AND status='booked'",(bid,customer_phone)).fetchone()
        if not booking: raise ServiceError("预订不存在、已取消或不属于当前顾客。",404)
        from . import allocation

        ready = allocation.preorder_time(db, booking) if allocation.enabled(db) else date_time(estimated_ready_at)
        oid = insert_id(db, "INSERT INTO orders(booking_id,customer_phone,contact_name,phone_number,table_id,order_type) VALUES(?,?,?,?,?,'preorder')",
                        (bid,customer_phone,booking["contact_name"],booking["phone_number"],booking["table_id"]), "order_id")
        total = 0
        for item in lines:
            price = _sale_price(db, item)
            item_total = round(price * item["quantity"], 2)
            total += item_total
            db.execute("INSERT INTO order_items(order_id,dish_id,quantity,unit_price,total_price,note,estimated_ready_at) VALUES(?,?,?,?,?,?,?)",(oid,item["dish_id"],item["quantity"],price,item_total,item["note"],ready))
        _check_order_total(total)
        result = {"order_id":oid,"total_amount":round(total,2),"status":"active","payment_status":"unpaid",
                  "estimated_ready_at":ready,"kitchen_queued":False}
        return submission.record(db, "preorder", customer_phone, request_key, payload, result)


def calculate_total(order_id):
    oid=positive_int(order_id,"order_id")
    with get_connection() as db:
        if not db.execute("SELECT 1 FROM orders WHERE order_id=?",(oid,)).fetchone(): raise ServiceError("订单不存在。",404)
        return _order_total(db, oid)


def cancel_order_item(order_id, order_item_id, customer_phone=None):
    oid=positive_int(order_id,"order_id"); iid=positive_int(order_item_id,"order_item_id")
    with get_connection() as db:
        begin_write(db)
        q="SELECT l.status,h.payment_status,h.customer_phone FROM order_items l JOIN orders h USING(order_id) WHERE l.order_id=? AND l.order_item_id=?"
        row=db.execute(q,(oid,iid)).fetchone()
        if not row: raise ServiceError("订单明细不存在。",404)
        if customer_phone and row["customer_phone"]!=customer_phone: raise ServiceError("无权修改此订单。",403,code="FORBIDDEN")
        if row["payment_status"]!="unpaid" or row["status"]!="waiting": raise ServiceError("仅未付款且尚未开始制作的菜品可以取消。",409)
        db.execute("UPDATE order_items SET status='cancelled' WHERE order_item_id=? AND status='waiting'",(iid,))
        db.execute("UPDATE kitchen_queue SET status='cancelled',completed_at=CURRENT_TIMESTAMP WHERE order_item_id=? AND status='waiting'",(iid,))
        refresh_order_status(db,oid)
        return {"order_id":oid,"order_item_id":iid,"total_amount":_order_total(db, oid)}


def pay_order(order_id, customer_phone=None):
    oid=positive_int(order_id,"order_id")
    with get_connection() as db:
        begin_write(db)
        q="SELECT status,payment_status,order_type,visit_id FROM orders WHERE order_id=?"; args=[oid]
        if customer_phone: q += " AND customer_phone=?"; args.append(customer_phone)
        row=db.execute(q,args).fetchone()
        if not row: raise ServiceError("订单不存在。",404)
        if row["payment_status"]=="paid": return {"order_id":oid,"payment_status":"paid","already_paid":True}
        if row["status"]=="cancelled": raise ServiceError("已取消订单不能付款。",409)
        if row["payment_status"] != "unpaid":
            raise ServiceError("This order is not awaiting payment.", 409)
        if row["order_type"] == "preorder" and row["visit_id"] is None:
            raise ServiceError("预点订单须到店后结账。",409,code="STATE_CONFLICT")
        db.execute("UPDATE orders SET payment_status='paid',paid_at=CURRENT_TIMESTAMP WHERE order_id=? AND payment_status='unpaid'",(oid,))
        return {"order_id":oid,"payment_status":"paid","already_paid":False}


def pay_visit(visit_id, customer_phone, expected_ids, expected_cents):
    with get_connection() as db:
        begin_write(db)
        suffix = " FOR UPDATE" if using_postgres() else ""
        visit = db.execute("SELECT status FROM dining_sessions WHERE visit_id=? AND customer_phone=?" + suffix,
                           (visit_id, customer_phone)).fetchone()
        if not visit:
            raise ServiceError("Dining visit not found.", 404, code="NOT_FOUND")

        rows = db.execute("""SELECT o.order_id,o.payment_status,ROUND(COALESCE(SUM(i.total_price),0),2) AS total
                            FROM orders o LEFT JOIN order_items i ON i.order_id=o.order_id AND i.status<>'cancelled'
                            WHERE o.visit_id=? AND o.customer_phone=? AND o.status<>'cancelled'
                            AND o.payment_status IN ('unpaid','paid') GROUP BY o.order_id""",
                          (visit_id, customer_phone)).fetchall()
        paid = {row["order_id"]: round(float(row["total"]) * 100) for row in rows if row["payment_status"] == "paid"}
        due = {row["order_id"]: round(float(row["total"]) * 100) for row in rows if row["payment_status"] == "unpaid"}
        result = {"order_ids": sorted(expected_ids), "total_cents": expected_cents, "payment_status": "paid"}
        if expected_ids and expected_ids <= paid.keys() and sum(paid[oid] for oid in expected_ids) == expected_cents:
            return dict(result, already_paid=True)
        if visit["status"] != "seated" or not due or due.keys() != expected_ids or sum(due.values()) != expected_cents:
            raise ServiceError("Your table bill changed. Review the updated total before paying.", 409, code="BILL_CHANGED")

        placeholders = ",".join("?" for _ in due)
        updated = db.execute(f"""UPDATE orders SET payment_status='paid',paid_at=CURRENT_TIMESTAMP
                                 WHERE visit_id=? AND customer_phone=? AND payment_status='unpaid'
                                 AND order_id IN ({placeholders})""", (visit_id, customer_phone, *due))
        if updated.rowcount != len(due):
            raise ServiceError("Your table bill changed. Review the updated total before paying.", 409, code="BILL_CHANGED")
        return dict(result, already_paid=False)


def _order_detail_items(db, order_id):
    return [dict(row) for row in db.execute("""
        SELECT l.*, d.dish_name, q.status AS kitchen_status
        FROM order_items l JOIN dishes d USING(dish_id)
        LEFT JOIN kitchen_queue q USING(order_item_id)
        WHERE l.order_id=? ORDER BY l.order_item_id
    """, (order_id,))]


def get_order(order_id, customer_phone=None):
    oid=positive_int(order_id,"order_id")
    with get_connection() as db:
        begin_read(db)
        query="SELECT * FROM orders WHERE order_id=?"; args=[oid]
        if customer_phone: query += " AND customer_phone=?"; args.append(customer_phone)
        order=db.execute(query,args).fetchone()
        if not order: raise ServiceError("订单不存在。",404,"order_id","NOT_FOUND")
        result=dict(order)
        result["items"] = _order_detail_items(db, oid)
        result["total_amount"]=_order_total(db, oid)
        result["refunded_amount"]=0.0
        return result


def get_customer_orders(customer_phone):
    with get_connection() as db:
        rows = db.execute("""
            SELECT o.*, ROUND(COALESCE(SUM(i.total_price), 0), 2) AS total_amount
            FROM orders o
            LEFT JOIN order_items i ON i.order_id=o.order_id AND i.status<>'cancelled'
            WHERE o.customer_phone=?
            GROUP BY o.order_id
            ORDER BY o.created_at DESC, o.order_id DESC
        """, (customer_phone,))
        return [dict(row) for row in rows]


def get_orders(active_only=False, phone=None, table_id=None):
    sql="SELECT * FROM orders WHERE 1=1"; args=[]
    if active_only: sql += " AND status='active'"
    if phone is not None: sql += " AND phone_number=?"; args.append(phone)
    if table_id is not None: sql += " AND table_id=?"; args.append(positive_int(table_id,"table_id"))
    sql += " ORDER BY created_at DESC"
    with get_connection() as db: return [dict(r) for r in db.execute(sql,args)]


def cancel_order(order_id, customer_phone=None):
    oid=positive_int(order_id,"order_id")
    with get_connection() as db:
        begin_write(db)
        q="SELECT * FROM orders WHERE order_id=?"; args=[oid]
        if customer_phone: q += " AND customer_phone=?"; args.append(customer_phone)
        row=db.execute(q,args).fetchone()
        if not row: raise ServiceError("订单不存在。",404)
        if row["payment_status"]!="unpaid": raise ServiceError("已付款订单不能取消。",409)
        if db.execute("SELECT 1 FROM order_items WHERE order_id=? AND status<>'waiting' AND status<>'cancelled'",(oid,)).fetchone(): raise ServiceError("已有菜品开始制作，不能取消订单。",409)
        db.execute("UPDATE order_items SET status='cancelled' WHERE order_id=? AND status='waiting'",(oid,))
        db.execute("UPDATE kitchen_queue SET status='cancelled',completed_at=CURRENT_TIMESTAMP WHERE order_id=? AND status='waiting'",(oid,))
        refresh_order_status(db,oid)
        return {"order_id":oid,"status":"cancelled"}


def update_order(order_id, items, customer_phone=None, *, expected_version=None):
    oid=positive_int(order_id,"order_id"); lines=order_items(items)
    with get_connection() as db:
        begin_write(db)
        query="SELECT * FROM orders WHERE order_id=?"; args=[oid]
        if customer_phone: query+=" AND customer_phone=?"; args.append(customer_phone)
        order=db.execute(query,args).fetchone()
        if not order: raise ServiceError("订单不存在。",404)
        if expected_version is not None and order["version"] != expected_version:
            raise ServiceError("This order changed. Review the latest order before saving your draft.",
                               409, code="ORDER_CHANGED")
        if order["status"]!="active" or order["payment_status"]!="unpaid": raise ServiceError("当前订单状态不可修改。",409)
        if db.execute("SELECT 1 FROM order_items WHERE order_id=? AND status<>'waiting' AND status<>'cancelled'",(oid,)).fetchone(): raise ServiceError("菜品已开始制作，订单不能修改。",409)
        # Validate every new dish before mutating any existing line.
        dishes={}
        for line in lines:
            dish=db.execute("SELECT price FROM dishes WHERE dish_id=? AND is_available=1 AND is_archived=0",(line["dish_id"],)).fetchone()
            if not dish: raise ServiceError(f"菜品 {line['dish_id']} 不存在或停售。",409,"items","RESOURCE_CONFLICT")
            dishes[line["dish_id"]]=float(dish["price"])
        preorder = order["order_type"] == "preorder"
        ready_at = None
        if preorder:
            schedule = db.execute("""SELECT estimated_ready_at FROM order_items
                WHERE order_id=? AND estimated_ready_at IS NOT NULL ORDER BY order_item_id DESC LIMIT 1""", (oid,)).fetchone()
            if not schedule:
                raise ServiceError("预点订单缺少制作时段。",409,code="STATE_CONFLICT")
            ready_at = schedule["estimated_ready_at"]
        remaining = db.execute("""SELECT * FROM order_items WHERE order_id=? AND status='waiting'
                                 ORDER BY order_item_id""", (oid,)).fetchall()
        matched = []
        for line in lines:
            existing = next((item for item in remaining if item["dish_id"] == line["dish_id"]
                             and item["quantity"] == line["quantity"] and (item["note"] or "") == line["note"]), None)
            matched.append(existing)
            if existing is not None:
                remaining.remove(existing)
        for line, existing in zip(lines, matched):
            if existing is not None:
                continue
            replacement = next((item for item in remaining if item["dish_id"] == line["dish_id"]), None)
            if replacement is not None:
                item_id = replacement["order_item_id"]
                total = round(float(replacement["unit_price"]) * line["quantity"], 2)
                db.execute("UPDATE order_items SET quantity=?, note=?, total_price=? WHERE order_item_id=?",
                           (line["quantity"], line["note"], total, item_id))
                db.execute("UPDATE kitchen_queue SET quantity=? WHERE order_item_id=? AND status='waiting'",
                           (line["quantity"], item_id))
                remaining.remove(replacement)
                continue
            price = dishes[line["dish_id"]]
            if "quoted_unit_cents" in line and round(price * 100) != line["quoted_unit_cents"]:
                raise ServiceError("A new dish price changed. Review its updated price before saving.",
                                   409, "items", "PRICE_CHANGED")
            line_total = round(price * line["quantity"], 2)
            item_id = insert_id(db, "INSERT INTO order_items(order_id,dish_id,quantity,unit_price,total_price,note,estimated_ready_at) VALUES(?,?,?,?,?,?,?)",
                                (oid,line["dish_id"],line["quantity"],price,line_total,line["note"],ready_at), "order_item_id")
            if not preorder:
                db.execute("INSERT INTO kitchen_queue(order_id,order_item_id,dish_id,quantity) VALUES(?,?,?,?)",(oid,item_id,line["dish_id"],line["quantity"]))
        for item in remaining:
            item_id = item["order_item_id"]
            db.execute("UPDATE order_items SET status='cancelled' WHERE order_item_id=?", (item_id,))
            db.execute("""UPDATE kitchen_queue SET status='cancelled',completed_at=CURRENT_TIMESTAMP
                          WHERE order_item_id=? AND status='waiting'""", (item_id,))
        result = dict(order)
        result["items"] = _order_detail_items(db, oid)
        result["total_amount"] = _order_total(db, oid)
        _check_order_total(result["total_amount"])
        db.execute("UPDATE orders SET version=version+1 WHERE order_id=?", (oid,))
        result["version"] += 1
        return result
