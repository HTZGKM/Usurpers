from restaurant.db.database import begin_read, begin_write, get_connection, insert_id, using_postgres
from . import submission
from .common import ServiceError, date_time, order_items, positive_int, required_text


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
            item_id = insert_id(db, "INSERT INTO order_items(order_id,dish_id,quantity,unit_price,total_price,note,dish_name_snapshot,category_snapshot) VALUES(?,?,?,?,?,?,(SELECT dish_name FROM dishes WHERE dish_id=?),(SELECT category FROM dishes WHERE dish_id=?))",
                                (order_id,line["dish_id"],line["quantity"],price,line_total,line["note"],line["dish_id"],line["dish_id"]), "order_item_id")
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
            db.execute("INSERT INTO order_items(order_id,dish_id,quantity,unit_price,total_price,note,estimated_ready_at,dish_name_snapshot,category_snapshot) VALUES(?,?,?,?,?,?,?,(SELECT dish_name FROM dishes WHERE dish_id=?),(SELECT category FROM dishes WHERE dish_id=?))",(oid,item["dish_id"],item["quantity"],price,item_total,item["note"],ready,item["dish_id"],item["dish_id"]))
        _check_order_total(total)
        result = {"order_id":oid,"total_amount":round(total,2),"status":"active","payment_status":"unpaid",
                  "estimated_ready_at":ready,"kitchen_queued":False}
        return submission.record(db, "preorder", customer_phone, request_key, payload, result)


def calculate_total(order_id):
    oid=positive_int(order_id,"order_id")
    with get_connection() as db:
        if not db.execute("SELECT 1 FROM orders WHERE order_id=?",(oid,)).fetchone(): raise ServiceError("订单不存在。",404)
        return _order_total(db, oid)


def cancel_order_item(order_id, order_item_id, customer_phone=None, *, expected_version=None):
    oid=positive_int(order_id,"order_id"); iid=positive_int(order_item_id,"order_item_id")
    with get_connection() as db:
        begin_write(db)
        q="SELECT l.status,l.supply_issue,h.version,h.payment_status,h.customer_phone FROM order_items l JOIN orders h USING(order_id) WHERE l.order_id=? AND l.order_item_id=?"
        row=db.execute(q,(oid,iid)).fetchone()
        if not row: raise ServiceError("订单明细不存在。",404)
        if customer_phone and row["customer_phone"]!=customer_phone: raise ServiceError("无权修改此订单。",403,code="FORBIDDEN")
        _version(row,expected_version)
        if row["supply_issue"]: raise ServiceError("Ask the front desk to resolve this dish.",409,code="SUPPLY_ISSUE")
        if row["payment_status"]!="unpaid" or row["status"]!="waiting": raise ServiceError("仅未付款且尚未开始制作的菜品可以取消。",409)
        db.execute("UPDATE order_items SET status='cancelled' WHERE order_item_id=? AND status='waiting'",(iid,))
        db.execute("UPDATE kitchen_queue SET status='cancelled',completed_at=CURRENT_TIMESTAMP WHERE order_item_id=? AND status='waiting'",(iid,))
        refresh_order_status(db,oid)
        return {"order_id":oid,"order_item_id":iid,"total_amount":_order_total(db, oid)}


def pay_order(order_id, customer_phone=None):
    raise ServiceError("Review and settle the whole table bill after all dishes are served.",409,code="TABLE_BILL_REQUIRED")


def _bill(db, visit_id, customer_phone=None):
    visit=db.execute("SELECT * FROM dining_sessions WHERE visit_id=?",(visit_id,)).fetchone()
    if not visit or (customer_phone and visit["customer_phone"] != customer_phone):
        raise ServiceError("Dining visit not found.",404,code="NOT_FOUND")
    rows=db.execute("""SELECT o.order_id,o.payment_status,COALESCE(SUM(CASE WHEN i.status<>'cancelled' THEN i.total_price ELSE 0 END),0) AS total
        FROM orders o LEFT JOIN order_items i USING(order_id) WHERE o.visit_id=? AND o.status<>'cancelled'
        GROUP BY o.order_id,o.payment_status""",(visit_id,)).fetchall()
    due={r["order_id"]:round(float(r["total"])*100) for r in rows if r["payment_status"]=='unpaid'}
    unfinished=db.execute("""SELECT 1 FROM order_items i JOIN orders o USING(order_id)
        WHERE o.visit_id=? AND (i.status NOT IN ('served','cancelled') OR i.supply_issue IS NOT NULL) LIMIT 1""",(visit_id,)).fetchone()
    reason = "Serve every dish and resolve all substitutions before payment." if unfinished else (
        "This visit is no longer seated." if visit["status"]!='seated' else "No outstanding balance." if not due else None)
    return dict(visit_id=visit_id,order_ids=sorted(due),total_cents=sum(due.values()),can_pay=reason is None,blocked_reason=reason)


def get_visit_bill(visit_id, customer_phone=None):
    with get_connection() as db:
        begin_read(db)
        return _bill(db,positive_int(visit_id,"visit_id"),customer_phone)


def pay_visit(visit_id, customer_phone, expected_ids, expected_cents, *, request_key=None, actor=None):
    visit_id=positive_int(visit_id,"visit_id")
    identity=actor or customer_phone
    payload=[visit_id,sorted(expected_ids),expected_cents]
    with get_connection() as db:
        begin_write(db)
        previous=submission.replay(db,"table-payment",identity,request_key,payload)
        if previous is not None: return dict(previous,already_paid=True)
        bill=_bill(db,visit_id,customer_phone)
        if not bill["can_pay"]: raise ServiceError(bill["blocked_reason"],409,code="BILL_NOT_READY")
        if set(bill["order_ids"]) != set(expected_ids) or bill["total_cents"] != expected_cents:
            raise ServiceError("The table bill changed. Review its current orders and amount.",409,code="BILL_CHANGED")
        for oid in bill["order_ids"]:
            db.execute("UPDATE orders SET payment_status='paid',paid_at=CURRENT_TIMESTAMP,version=version+1 WHERE order_id=? AND payment_status='unpaid'",(oid,))
        result=dict(visit_id=visit_id,order_ids=bill["order_ids"],total_cents=bill["total_cents"],payment_status="paid",already_paid=False)
        return submission.record(db,"table-payment",identity,request_key,payload,result)


def _order_detail_items(db, order_id):
    return [dict(row) for row in db.execute("""
        SELECT l.*, COALESCE(l.dish_name_snapshot,d.dish_name) AS dish_name, q.status AS kitchen_status
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
        result["kitchen_stage"] = kitchen_stage(result["items"])
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


def cancel_order(order_id, customer_phone=None, *, expected_version=None):
    oid=positive_int(order_id,"order_id")
    with get_connection() as db:
        begin_write(db)
        q="SELECT * FROM orders WHERE order_id=?"; args=[oid]
        if customer_phone: q += " AND customer_phone=?"; args.append(customer_phone)
        row=db.execute(q,args).fetchone()
        if not row: raise ServiceError("订单不存在。",404)
        _version(row,expected_version)
        if db.execute("SELECT 1 FROM order_items WHERE order_id=? AND supply_issue IS NOT NULL",(oid,)).fetchone(): raise ServiceError("Resolve supply issues first.",409,code="SUPPLY_ISSUE")
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
                if line["quantity"] > replacement["quantity"]:
                    _sale_price(db,line)
                if replacement["supply_issue"]:
                    raise ServiceError("Resolve the supply issue with the front desk first.",409,code="SUPPLY_ISSUE")
                item_id = replacement["order_item_id"]
                total = round(float(replacement["unit_price"]) * line["quantity"], 2)
                db.execute("UPDATE order_items SET quantity=?, note=?, total_price=? WHERE order_item_id=?",
                           (line["quantity"], line["note"], total, item_id))
                db.execute("UPDATE kitchen_queue SET quantity=? WHERE order_item_id=? AND status='waiting'",
                           (line["quantity"], item_id))
                remaining.remove(replacement)
                continue
            price = _sale_price(db,line)
            if "quoted_unit_cents" in line and round(price * 100) != line["quoted_unit_cents"]:
                raise ServiceError("A new dish price changed. Review its updated price before saving.",
                                   409, "items", "PRICE_CHANGED")
            line_total = round(price * line["quantity"], 2)
            item_id = insert_id(db, "INSERT INTO order_items(order_id,dish_id,quantity,unit_price,total_price,note,estimated_ready_at,dish_name_snapshot,category_snapshot) VALUES(?,?,?,?,?,?,?,(SELECT dish_name FROM dishes WHERE dish_id=?),(SELECT category FROM dishes WHERE dish_id=?))",
                                (oid,line["dish_id"],line["quantity"],price,line_total,line["note"],ready_at,line["dish_id"],line["dish_id"]), "order_item_id")
            if not preorder:
                db.execute("INSERT INTO kitchen_queue(order_id,order_item_id,dish_id,quantity) VALUES(?,?,?,?)",(oid,item_id,line["dish_id"],line["quantity"]))
        for item in remaining:
            if item["supply_issue"]:
                raise ServiceError("Resolve the supply issue with the front desk first.",409,code="SUPPLY_ISSUE")
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


def _version(order, expected_version):
    if expected_version is not None and order["version"] != positive_int(expected_version,"expected_version"):
        raise ServiceError("This order changed. Review its latest details.",409,code="ORDER_CHANGED")


def kitchen_stage(items):
    active=[i for i in items if i["status"]!='cancelled']
    if not active:return 'cancelled'
    if all(i["status"]=='served' for i in active):return 'served'
    if all(i["status"] in ('ready','served') for i in active) and not any(i.get('supply_issue') for i in active):return 'ready'
    if any(i["status"] in ('cooking','ready','served') for i in active):return 'cooking'
    return 'waiting'


def resolve_supply_issue(order_id,item_id,action,reason,actor,expected_version,customer_agreed,items=None,request_key=None):
    oid=positive_int(order_id,"order_id"); iid=positive_int(item_id,"item_id")
    reason=required_text(reason,"reason",limit=500)
    if customer_agreed is not True: raise ServiceError("Confirm the guest agreed to this resolution.",400,field="customer_agreed")
    if action not in ("cancel","replace"): raise ServiceError("Choose cancellation or replacement.",400,field="action")
    key=required_text(request_key,"idempotency_key",limit=80)
    lines=order_items(items) if action=="replace" else []
    if any("quoted_unit_cents" not in line for line in lines):
        raise ServiceError("Confirm the price of every replacement dish.",400,code="PRICE_CONFIRMATION_REQUIRED")
    payload=[oid,iid,action,reason,expected_version,lines]
    with get_connection() as db:
        begin_write(db)
        previous=submission.replay(db,"supply-resolution",actor,key,payload)
        if previous is not None:return previous
        order=db.execute("SELECT * FROM orders WHERE order_id=?",(oid,)).fetchone()
        item=db.execute("SELECT * FROM order_items WHERE order_id=? AND order_item_id=?",(oid,iid)).fetchone()
        if not order or not item:raise ServiceError("Order item not found.",404)
        _version(order,expected_version)
        if order["payment_status"]!='unpaid' or item["status"]!='waiting' or not item["supply_issue"]:
            raise ServiceError("This dish no longer needs this resolution.",409,code="ORDER_CHANGED")
        replacement=None
        if action=='replace':
            prices=[_sale_price(db,line) for line in lines]
            _check_order_total(sum(round(price*line['quantity'],2) for price,line in zip(prices,lines)))
            replacement=insert_id(db,"""INSERT INTO orders(visit_id,booking_id,queue_id,customer_phone,contact_name,phone_number,table_id,order_type,replaces_item_id)
                VALUES(?,?,?,?,?,?,?,?,?)""",(order['visit_id'],order['booking_id'],order['queue_id'],order['customer_phone'],order['contact_name'],order['phone_number'],order['table_id'],order['order_type'],iid),'order_id')
            for line,price in zip(lines,prices):
                new_id=insert_id(db,"""INSERT INTO order_items(order_id,dish_id,quantity,unit_price,total_price,note,estimated_ready_at,dish_name_snapshot,category_snapshot)
                    VALUES(?,?,?,?,?,?,?,(SELECT dish_name FROM dishes WHERE dish_id=?),(SELECT category FROM dishes WHERE dish_id=?))""",
                    (replacement,line['dish_id'],line['quantity'],price,round(price*line['quantity'],2),line['note'],item['estimated_ready_at'],line['dish_id'],line['dish_id']),'order_item_id')
                if order['visit_id'] and order['order_type']!='preorder':
                    db.execute("INSERT INTO kitchen_queue(order_id,order_item_id,dish_id,quantity) VALUES(?,?,?,?)",(replacement,new_id,line['dish_id'],line['quantity']))
        db.execute("UPDATE order_items SET status='cancelled',supply_issue=NULL WHERE order_item_id=?",(iid,))
        db.execute("UPDATE kitchen_queue SET status='cancelled',completed_at=CURRENT_TIMESTAMP WHERE order_item_id=? AND status='waiting'",(iid,))
        refresh_order_status(db,oid)
        db.execute("INSERT INTO order_resolution_audit(order_item_id,action,reason,actor,replacement_order_id) VALUES(?,?,?,?,?)",(iid,action,reason,actor,replacement))
        result=dict(order_id=oid,cancelled_item_id=iid,replacement_order_id=replacement)
        return submission.record(db,"supply-resolution",actor,key,payload,result)
