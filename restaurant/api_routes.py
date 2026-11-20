from flask import Blueprint, jsonify, request, session
from restaurant.services import booking_service, dining_service, order_service, kitchen_service, menu_service

api_bp = Blueprint("api", __name__)

@api_bp.before_request
def enforce_role():
    from flask import session
    from restaurant.db.database import get_connection
    path=request.path
    role=session.get("user",{}).get("role")
    public = path == "/menu"
    allowed = None
    if path.startswith("/admin/"): allowed={"admin"}
    elif path.startswith("/kitchen/"): allowed={"kitchen","admin"}
    elif path.startswith("/frontdesk/"): allowed={"frontdesk","admin"}
    elif path.startswith("/pay/"): allowed={"customer"}
    elif path.startswith("/visits/") or path.startswith("/orders/"): allowed={"customer","frontdesk","admin"}
    elif path.startswith("/bookings"): allowed={"customer","frontdesk","admin"}
    elif path.startswith("/waiting-queue"): allowed={"customer","frontdesk","admin"}
    if public: return None
    if not role:
        return jsonify({"ok":False,"success":False,"error":"UNAUTHENTICATED","message":"请先登录。"}),401
    if allowed and role not in allowed:
        return jsonify({"ok":False,"success":False,"error":"FORBIDDEN","message":"无权执行此操作。"}),403
    user=session.get("user",{})
    if role in {"frontdesk","kitchen","admin"}:
        with get_connection() as db:
            active=db.execute("SELECT is_active FROM staff WHERE email=?",(user.get("username"),)).fetchone()
        if not active or not active["is_active"]:
            session.pop("user",None)
            return jsonify({"ok":False,"success":False,"error":"FORBIDDEN","message":"员工账号已停用。"}),403
    elif role == "customer":
        with get_connection() as db:
            active=db.execute("SELECT is_active FROM customers WHERE customer_phone=?",(user.get("username"),)).fetchone()
        if not active or not active["is_active"]:
            session.pop("user",None)
            return jsonify({"ok":False,"success":False,"error":"FORBIDDEN","message":"顾客账号已停用。"}),403

def payload():
    data=request.get_json(silent=True)
    if not isinstance(data,dict):
        from restaurant.services.common import ServiceError
        raise ServiceError("请求体必须是 JSON 对象。")
    return data

@api_bp.get("/menu")
def menu(): return jsonify({"ok":True,"items":menu_service.get_available_items()})

@api_bp.post("/bookings")
def create_booking():
    d=payload(); user=session.get("user",{}); customer_phone=user.get("username") if user.get("role")=="customer" else None
    contact_name=user.get("name") if customer_phone else d.get("contact_name",d.get("name"))
    phone=customer_phone or d.get("phone_number",d.get("phone"))
    return jsonify({"ok":True,"booking":booking_service.create_booking(contact_name,phone,d.get("booking_date",d.get("date")),d.get("time_slot_id",d.get("time_slot")),d.get("party_size",d.get("guests")),customer_phone)}),201

@api_bp.post("/frontdesk/bookings")
def frontdesk_create_booking(): return create_booking()

@api_bp.get("/bookings")
def my_bookings(): return jsonify({"ok":True,"bookings":booking_service.get_customer_bookings(session["user"]["username"])})

@api_bp.post("/bookings/<int:booking_id>/preorders")
def preorder(booking_id):
    user=session.get("user",{})
    return jsonify({"ok":True,"order":order_service.create_preorder(booking_id,user["username"],payload().get("items"),payload().get("estimated_ready_at"))}),201

@api_bp.get("/tables/available")
def available_tables():
    return jsonify({"ok":True,"tables":booking_service.find_available_tables(request.args.get("date"),request.args.get("time_slot_id"),request.args.get("party_size"))})

@api_bp.post("/bookings/<int:booking_id>/edit")
def edit_booking(booking_id):
    d=payload(); owner=session["user"]["username"] if session["user"]["role"]=="customer" else None
    if owner:
        with __import__('restaurant.db.database',fromlist=['get_connection']).get_connection() as db:
            row=db.execute("SELECT customer_phone FROM bookings WHERE booking_id=?",(booking_id,)).fetchone()
        if not row or row["customer_phone"] != owner:
            from restaurant.services.common import ServiceError
            raise ServiceError("预订不存在。",404)
    return jsonify({"ok":True,"booking":booking_service.update_booking(booking_id,d.get("booking_date"),d.get("time_slot_id"),d.get("party_size"),owner)})

@api_bp.post("/bookings/<int:booking_id>/cancel")
def cancel_booking(booking_id):
    owner=session["user"]["username"] if session["user"]["role"]=="customer" else None
    return jsonify({"ok":True,"booking":booking_service.cancel_booking(booking_id,owner)})

@api_bp.get("/frontdesk/bookings")
def frontdesk_bookings():
    return jsonify({"ok":True,"bookings":booking_service.get_all_bookings(request.args.get("date"),request.args.get("time_slot_id"),request.args.get("phone_number"))})

@api_bp.post("/frontdesk/bookings/<int:booking_id>/check-in")
def check_in(booking_id): return jsonify({"ok":True,"visit":dining_service.register_arrival(booking_id,payload().get("table_id"))}),201

@api_bp.get("/frontdesk/tables")
def table_occupancy():
    return jsonify({"ok":True,"tables":booking_service.get_table_occupancy(request.args.get("date"),request.args.get("time_slot_id"))})

@api_bp.post("/frontdesk/walk-ins")
def walk_in():
    d=payload(); return jsonify({"ok":True,"visit":dining_service.register_walk_in(d.get("party_size"),d.get("table_id"),d.get("contact_name"),d.get("phone_number"))}),201

@api_bp.post("/visits/<int:visit_id>/orders")
def create_order(visit_id):
    user=session.get("user",{}); owner=user.get("username") if user.get("role")=="customer" else None
    return jsonify({"ok":True,"order":order_service.create_dine_in_order(visit_id,payload().get("items"),owner)}),201

@api_bp.post("/orders")
def customer_create_order():
    from restaurant.services.dining_service import get_active_customer_visit
    user=session["user"]
    visit_id=get_active_customer_visit(user["username"])
    return jsonify({"ok":True,"order":order_service.create_dine_in_order(visit_id,payload().get("items"),user["username"])}),201

@api_bp.post("/frontdesk/visits/<int:visit_id>/close")
def close_visit(visit_id): return jsonify({"ok":True,"visit":dining_service.close_dining_session(visit_id)})

@api_bp.post("/frontdesk/visits/<int:visit_id>/assign")
def assign_visit(visit_id): return jsonify({"ok":True,"visit":dining_service.assign_table(visit_id,payload().get("table_id"))})

@api_bp.post("/frontdesk/orders")
def frontdesk_create_order():
    d=payload(); return jsonify({"ok":True,"order":order_service.create_dine_in_order(d.get("visit_id"),d.get("items"))}),201

@api_bp.post("/frontdesk/orders/<int:order_id>/edit")
def frontdesk_edit_order(order_id): return jsonify({"ok":True,"order":order_service.update_order(order_id,payload().get("items"))})

@api_bp.post("/orders/<int:order_id>/pay")
def pay(order_id):
    owner=session["user"]["username"] if session["user"]["role"]=="customer" else None
    return jsonify({"ok":True,"payment":order_service.pay_order(order_id,owner)})

@api_bp.post("/pay/<int:order_id>")
def customer_pay(order_id): return pay(order_id)

@api_bp.post("/frontdesk/orders/<int:order_id>/pay")
def frontdesk_pay(order_id): return jsonify({"ok":True,"payment":order_service.pay_order(order_id)})

@api_bp.get("/orders")
def my_orders():
    role=session["user"]["role"]
    if role=="customer": rows=order_service.get_customer_orders(session["user"]["username"])
    else: rows=order_service.get_orders(phone=request.args.get("phone_number"),table_id=request.args.get("table_id"))
    return jsonify({"ok":True,"orders":rows})

@api_bp.get("/frontdesk/orders/<int:order_id>")
def frontdesk_order_detail(order_id): return jsonify({"ok":True,"order":order_service.get_order(order_id)})

@api_bp.post("/frontdesk/orders/<int:order_id>/items/<int:item_id>/cancel")
def frontdesk_cancel_item(order_id,item_id): return jsonify({"ok":True,"item":order_service.cancel_order_item(order_id,item_id)})

@api_bp.post("/frontdesk/orders/<int:order_id>/items/<int:item_id>/serve")
def frontdesk_serve_item(order_id,item_id):
    with __import__('restaurant.db.database',fromlist=['get_connection']).get_connection() as db:
        row=db.execute("SELECT 1 FROM order_lines WHERE order_id=? AND order_item_id=?",(order_id,item_id)).fetchone()
    if not row:
        from restaurant.services.common import ServiceError
        raise ServiceError("订单明细不存在。",404)
    return jsonify({"ok":True,"item":kitchen_service.serve_item(item_id)})

@api_bp.get("/orders/<int:order_id>")
def order_detail(order_id):
    owner=session["user"]["username"] if session["user"]["role"]=="customer" else None
    return jsonify({"ok":True,"order":order_service.get_order(order_id,owner)})

@api_bp.post("/orders/<int:order_id>/cancel")
def cancel_order(order_id):
    owner=session["user"]["username"] if session["user"]["role"]=="customer" else None
    return jsonify({"ok":True,"order":order_service.cancel_order(order_id,owner)})

@api_bp.post("/orders/<int:order_id>/edit")
def customer_edit_order(order_id):
    owner=session["user"]["username"] if session["user"]["role"]=="customer" else None
    return jsonify({"ok":True,"order":order_service.update_order(order_id,payload().get("items"),owner)})

@api_bp.post("/orders/<int:order_id>/items/<int:item_id>/cancel")
def cancel_item(order_id,item_id):
    owner=session["user"]["username"] if session["user"]["role"]=="customer" else None
    return jsonify({"ok":True,"item":order_service.cancel_order_item(order_id,item_id,owner)})

@api_bp.get("/kitchen/queue")
def kitchen_queue():
    state=request.args.get("status","waiting")
    fn={"waiting":kitchen_service.get_waiting_items,"cooking":kitchen_service.get_cooking_items,"ready":kitchen_service.get_ready_items}.get(state)
    if not fn:
        from restaurant.services.common import ServiceError
        raise ServiceError("队列状态不合法。",field="status")
    return jsonify({"ok":True,"items":fn()})

@api_bp.get("/kitchen/menu")
def kitchen_menu():
    items=menu_service.get_all_items()
    if request.args.get("available") == "true": items=[item for item in items if item["is_available"] and not item["is_archived"]]
    return jsonify({"ok":True,"items":items})

@api_bp.get("/kitchen/orders/<int:order_id>")
def kitchen_order_detail(order_id): return jsonify({"ok":True,"order":order_service.get_order(order_id)})

@api_bp.post("/waiting-queue")
def join_waitlist():
    from restaurant.services.queue_manager import QueueManager
    d=payload(); user=session.get("user",{}); phone=d.get("phone_number") if user.get("role")!="customer" else user.get("username")
    return jsonify({"ok":True,"queue":QueueManager.join_waitlist(d.get("party_size"),d.get("contact_name"),phone,phone if user.get("role")=="customer" else None,d.get("table_type"))}),201

@api_bp.delete("/waiting-queue/<int:queue_id>")
def leave_waitlist(queue_id):
    from restaurant.services.queue_manager import QueueManager
    user=session.get("user",{}); owner=user.get("username") if user.get("role")=="customer" else None
    return jsonify({"ok":True,"queue":QueueManager.cancel(queue_id,owner)})

@api_bp.get("/waiting-queue/mine")
def my_waitlist():
    from restaurant.services.queue_manager import QueueManager
    return jsonify({"ok":True,"queue":QueueManager.get_customer_entry(session["user"]["username"])})

@api_bp.get("/frontdesk/waiting-queue")
def waiting_queue():
    from restaurant.services.queue_manager import QueueManager
    return jsonify({"ok":True,"queue":QueueManager.list_waiting()})

@api_bp.post("/frontdesk/tables/<int:table_id>/call-next")
def call_next(table_id):
    from restaurant.services.queue_manager import QueueManager
    return jsonify({"ok":True,"queue":QueueManager.call_next(table_id)})

@api_bp.post("/frontdesk/waiting-queue/<int:queue_id>/seat")
def seat_waiting(queue_id):
    from restaurant.services.queue_manager import QueueManager
    return jsonify({"ok":True,"visit":QueueManager.seat(queue_id,payload().get("table_id"))}),201

@api_bp.post("/kitchen/items/<int:item_id>/start")
def start_item(item_id): return jsonify({"ok":True,"item":kitchen_service.start_item(item_id)})

@api_bp.post("/kitchen/items/<int:item_id>/complete")
def finish_item(item_id): return jsonify({"ok":True,"item":kitchen_service.finish_item(item_id)})

@api_bp.post("/kitchen/order-items/<int:item_id>/complete")
def finish_order_item(item_id): return finish_item(item_id)

@api_bp.post("/kitchen/items/<int:item_id>/serve")
def serve_item(item_id): return jsonify({"ok":True,"item":kitchen_service.serve_item(item_id)})

@api_bp.get("/kitchen/remakes")
def kitchen_remakes():
    from restaurant.services.remake_service import list_remakes
    return jsonify({"ok":True,"tasks":list_remakes(request.args.get("status","waiting"))})

@api_bp.post("/kitchen/remakes/<int:remake_id>/start")
def start_remake(remake_id):
    from restaurant.services.remake_service import start_remake as start
    return jsonify({"ok":True,"task":start(remake_id)})

@api_bp.post("/kitchen/remakes/<int:remake_id>/complete")
def complete_remake(remake_id):
    from restaurant.services.remake_service import complete_remake as complete
    return jsonify({"ok":True,"task":complete(remake_id)})

@api_bp.post("/frontdesk/orders/<int:order_id>/items/<int:item_id>/remakes")
def create_remake(order_id,item_id):
    from restaurant.db.database import get_connection
    from restaurant.services.remake_service import create_remake as create
    from restaurant.services.common import ServiceError
    user=session.get("user",{})
    with get_connection() as db:
        staff=db.execute("SELECT staff_id FROM staff WHERE email=? AND is_active=1",(user.get("username"),)).fetchone()
        belongs=db.execute("SELECT 1 FROM order_lines WHERE order_id=? AND order_item_id=?",(order_id,item_id)).fetchone()
    if not belongs: raise ServiceError("订单菜品不存在。",404)
    return jsonify({"ok":True,"task":create(item_id,payload().get("reason"),staff["staff_id"])}),201

@api_bp.post("/frontdesk/orders/<int:order_id>/refunds")
def refund_order(order_id):
    from restaurant.db.database import get_connection
    from restaurant.services.refund_service import create_refund
    user=session.get("user",{})
    with get_connection() as db: staff=db.execute("SELECT staff_id FROM staff WHERE email=? AND is_active=1",(user.get("username"),)).fetchone()
    d=payload()
    result=create_refund(order_id,d.get("amount"),d.get("reason"),staff["staff_id"],d.get("idempotency_key"))
    return jsonify({"ok":True,"refund":result}),200

@api_bp.get("/frontdesk/orders/<int:order_id>/refunds")
def list_order_refunds(order_id):
    from restaurant.services.refund_service import get_refunds
    return jsonify({"ok":True,"refunds":get_refunds(order_id)})

@api_bp.post("/kitchen/menu/<int:dish_id>/availability")
def kitchen_availability(dish_id):
    d=payload(); value=d.get("is_available")
    if value in ("true","1",1,True): value=True
    elif value in ("false","0",0,False): value=False
    else:
        from restaurant.services.common import ServiceError
        raise ServiceError("is_available 必须是 true 或 false。",field="is_available")
    item=menu_service.update_item(dish_id,is_available=value)
    if item["is_archived"] and value:
        from restaurant.services.common import ServiceError
        raise ServiceError("已归档菜品不能恢复供应。",409,code="STATE_CONFLICT")
    return jsonify({"ok":True,"item":item})

@api_bp.get("/admin/staff")
def admin_staff():
    from restaurant.services.staff_account_service import get_staff_accounts
    return jsonify({"ok":True,"staff":get_staff_accounts(request.args.get("role"))})

@api_bp.get("/admin/accounts")
def admin_accounts():
    from restaurant.services.auth_service import get_customer_accounts
    return jsonify({"ok":True,"staff":__import__('restaurant.services.staff_account_service',fromlist=['get_staff_accounts']).get_staff_accounts(),"customers":get_customer_accounts()})

@api_bp.post("/admin/customers/<path:customer_phone>/deactivate")
def admin_deactivate_customer(customer_phone):
    from restaurant.services.auth_service import set_customer_active
    return jsonify({"ok":True,"customer":set_customer_active(customer_phone,False)})

@api_bp.post("/admin/customers/<path:customer_phone>/activate")
def admin_activate_customer(customer_phone):
    from restaurant.services.auth_service import set_customer_active
    return jsonify({"ok":True,"customer":set_customer_active(customer_phone,True)})

@api_bp.post("/admin/staff")
def admin_create_staff():
    from restaurant.services.staff_account_service import create_staff_account
    d=payload(); return jsonify({"ok":True,"staff":create_staff_account(d.get("name"),d.get("phone_number"),d.get("email"),d.get("password"),d.get("role"))}),201

@api_bp.post("/admin/staff/<int:staff_id>/edit")
def admin_edit_staff(staff_id):
    from restaurant.services.staff_account_service import update_staff_account
    d=payload(); return jsonify({"ok":True,"staff":update_staff_account(staff_id,d.get("name"),d.get("phone_number"),d.get("email"),d.get("role"))})

@api_bp.post("/admin/staff/<int:staff_id>/deactivate")
def admin_deactivate_staff(staff_id):
    from restaurant.services.staff_account_service import set_staff_active
    return jsonify({"ok":True,"staff":set_staff_active(staff_id,False)})

@api_bp.post("/admin/staff/<int:staff_id>/activate")
def admin_activate_staff(staff_id):
    from restaurant.services.staff_account_service import set_staff_active
    return jsonify({"ok":True,"staff":set_staff_active(staff_id,True)})

@api_bp.post("/admin/staff/<int:staff_id>/reset-password")
def admin_reset_staff_password(staff_id):
    from restaurant.services.staff_account_service import reset_staff_password
    return jsonify({"ok":True,"staff":reset_staff_password(staff_id,payload().get("password","123456"))})

@api_bp.get("/admin/dishes")
def admin_dishes():
    dishes=menu_service.get_all_items()
    if request.args.get("available") == "true": dishes=[dish for dish in dishes if dish["is_available"] and not dish["is_archived"]]
    return jsonify({"ok":True,"dishes":dishes})

@api_bp.post("/admin/dishes")
def admin_create_dish():
    d=payload(); return jsonify({"ok":True,"dish":menu_service.create_item(d.get("name"),d.get("price"),d.get("ingredients",""),d.get("prep_time_minutes",10),d.get("image_url"))}),201

@api_bp.post("/admin/dishes/<int:dish_id>/edit")
def admin_edit_dish(dish_id):
    d=payload(); return jsonify({"ok":True,"dish":menu_service.update_item(dish_id,d.get("name"),d.get("price"))})

@api_bp.post("/admin/dishes/<int:dish_id>/archive")
def admin_archive_dish(dish_id): return jsonify({"ok":True,"dish":menu_service.archive_item(dish_id)})

@api_bp.get("/admin/inventory/ingredients")
def admin_inventory_ingredients():
    from restaurant.services.inventory_service import list_ingredients
    return jsonify({"ok":True,"ingredients":list_ingredients()})

@api_bp.post("/admin/inventory/ingredients")
def admin_create_ingredient():
    from restaurant.services.inventory_service import create_ingredient
    d=payload(); return jsonify({"ok":True,"ingredient":create_ingredient(d.get("name"),d.get("unit"),d.get("on_hand"),d.get("expires_at"))}),201

@api_bp.post("/admin/inventory/ingredients/<int:ingredient_id>/adjust")
def admin_adjust_ingredient(ingredient_id):
    from restaurant.services.inventory_service import adjust_stock
    d=payload(); return jsonify({"ok":True,"ingredient":adjust_stock(ingredient_id,d.get("quantity"),d.get("movement_type","adjustment"),d.get("reference"))})

@api_bp.put("/admin/dishes/<int:dish_id>/recipe")
def admin_set_recipe(dish_id):
    from restaurant.services.inventory_service import set_recipe
    return jsonify({"ok":True,"recipe":set_recipe(dish_id,payload().get("ingredients"))})

@api_bp.get("/admin/orders")
def admin_orders():
    rows=order_service.get_orders(active_only=request.args.get("active_only")=="true",phone=request.args.get("phone_number"),table_id=request.args.get("table_id"))
    state=request.args.get("status")
    if state: rows=[r for r in rows if r["status"]==state]
    return jsonify({"ok":True,"orders":rows})

@api_bp.get("/admin/orders/<int:order_id>")
def admin_order_detail(order_id): return jsonify({"ok":True,"order":order_service.get_order(order_id)})

@api_bp.get("/admin/kitchen-queue")
def admin_kitchen_queue(): return jsonify({"ok":True,"items":kitchen_service.get_waiting_items()})

@api_bp.get("/admin/bookings")
def admin_bookings(): return jsonify({"ok":True,"bookings":booking_service.get_all_bookings(request.args.get("booking_date"),request.args.get("time_slot_id"),request.args.get("phone_number"))})

@api_bp.get("/admin/tables")
def admin_tables(): return jsonify({"ok":True,"tables":booking_service.get_table_occupancy(request.args.get("date"),request.args.get("time_slot_id"))})

@api_bp.get("/admin/dining-sessions")
def admin_visits(): return jsonify({"ok":True,"visits":dining_service.get_dining_sessions()})

@api_bp.get("/admin/dashboard")
def admin_dashboard():
    from restaurant.db.database import get_connection
    with get_connection() as db:
        data={"orders":db.execute("SELECT count(*) FROM order_headers").fetchone()[0],
              "active_orders":db.execute("SELECT count(*) FROM order_headers WHERE status='active'").fetchone()[0],
              "bookings":db.execute("SELECT count(*) FROM bookings WHERE status='booked'").fetchone()[0],
              "open_visits":db.execute("SELECT count(*) FROM dining_sessions WHERE status IN ('waiting','seated')").fetchone()[0],
              "waiting_queue":db.execute("SELECT count(*) FROM waiting_queue WHERE status IN ('waiting','called')").fetchone()[0],
              "kitchen_waiting":db.execute("SELECT count(*) FROM kitchen_queue WHERE status='waiting'").fetchone()[0]}
    return jsonify({"ok":True,"summary":data})
