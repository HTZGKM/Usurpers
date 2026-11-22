"""Recipe-based stock reservation. Callers share the surrounding SQLite transaction."""
from restaurant.db.database import get_connection
from .common import ServiceError, positive_int, required_text
import math
from datetime import date, datetime


def reserve_for_order_line(db, order_item_id, dish_id, quantity):
    recipe = db.execute("SELECT di.ingredient_id,di.quantity_per_dish,i.on_hand,i.reserved,i.is_available,i.expires_at,i.name "
                        "FROM dish_ingredients di JOIN ingredients i USING(ingredient_id) WHERE di.dish_id=?", (dish_id,)).fetchall()
    # Dishes without configured recipes remain untracked until an admin defines one.
    for item in recipe:
        needed = float(item["quantity_per_dish"]) * quantity
        if not item["is_available"] or (item["expires_at"] and item["expires_at"] < __import__('datetime').datetime.now().isoformat(sep=" ")):
            raise ServiceError(f"食材 {item['name']} 已停用或过期。", 409, "items", "INVENTORY_UNAVAILABLE")
        if float(item["on_hand"])-float(item["reserved"]) < needed:
            raise ServiceError(f"食材 {item['name']} 库存不足。", 409, "items", "INSUFFICIENT_INVENTORY")
    for item in recipe:
        needed = float(item["quantity_per_dish"]) * quantity
        db.execute("UPDATE ingredients SET reserved=reserved+? WHERE ingredient_id=?", (needed,item["ingredient_id"]))
        db.execute("INSERT INTO inventory_reservations(order_item_id,ingredient_id,quantity,status) VALUES(?,?,?,'reserved')",
                   (order_item_id,item["ingredient_id"],needed))


def release_for_order_line(db, order_item_id):
    rows=db.execute("SELECT ingredient_id,quantity FROM inventory_reservations WHERE order_item_id=? AND status='reserved'",(order_item_id,)).fetchall()
    for row in rows:
        db.execute("UPDATE ingredients SET reserved=reserved-? WHERE ingredient_id=?",(row["quantity"],row["ingredient_id"]))
    db.execute("UPDATE inventory_reservations SET status='released' WHERE order_item_id=? AND status='reserved'",(order_item_id,))


def consume_for_order_line(db, order_item_id):
    rows=db.execute("SELECT r.ingredient_id,r.quantity,i.is_available,i.expires_at,i.name FROM inventory_reservations r JOIN ingredients i USING(ingredient_id) WHERE r.order_item_id=? AND r.status='reserved'",(order_item_id,)).fetchall()
    for row in rows:
        if not row["is_available"] or (row["expires_at"] and row["expires_at"] < __import__('datetime').datetime.now().isoformat(sep=" ")):
            raise ServiceError(f"预留食材 {row['name']} 已不可用，请前台处理订单。",409,code="INVENTORY_UNAVAILABLE")
        db.execute("UPDATE ingredients SET on_hand=on_hand-?,reserved=reserved-? WHERE ingredient_id=? AND on_hand>=? AND reserved>=?",
                   (row["quantity"],row["quantity"],row["ingredient_id"],row["quantity"],row["quantity"]))
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise ServiceError("库存预留状态已变化，请重试。",409,code="INVENTORY_CONFLICT")
        db.execute("INSERT INTO inventory_movements(ingredient_id,quantity,movement_type,reference) VALUES(?,?,'consumed',?)",
                   (row["ingredient_id"],-row["quantity"],str(order_item_id)))
    db.execute("UPDATE inventory_reservations SET status='consumed' WHERE order_item_id=? AND status='reserved'",(order_item_id,))


def adjust_stock(ingredient_id, quantity, movement_type="adjustment", reference=None):
    iid=positive_int(ingredient_id,"ingredient_id")
    try: delta=float(quantity)
    except (TypeError,ValueError): raise ServiceError("quantity 必须是有效数字。",field="quantity")
    if not math.isfinite(delta) or not delta: raise ServiceError("quantity 必须是非零有效数字。",field="quantity")
    movement_type=required_text(movement_type,"movement_type",limit=40)
    if movement_type not in {"adjustment","delivery","spoilage","correction"}: raise ServiceError("movement_type 取值不合法。",field="movement_type")
    reference=required_text(reference,"reference",limit=120) if reference is not None else None
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT on_hand FROM ingredients WHERE ingredient_id=?",(iid,)).fetchone()
        if not row: raise ServiceError("食材不存在。",404)
        if float(row[0])+delta < 0 or float(row[0])+delta < db.execute("SELECT reserved FROM ingredients WHERE ingredient_id=?",(iid,)).fetchone()[0]: raise ServiceError("调整后库存不能低于已预留数量。",409,code="INVENTORY_CONFLICT")
        db.execute("UPDATE ingredients SET on_hand=on_hand+? WHERE ingredient_id=?",(delta,iid))
        db.execute("INSERT INTO inventory_movements(ingredient_id,quantity,movement_type,reference) VALUES(?,?,?,?)",(iid,delta,movement_type,reference))
        return dict(db.execute("SELECT * FROM ingredients WHERE ingredient_id=?",(iid,)).fetchone())


def create_ingredient(name, unit, on_hand, expires_at=None):
    name=required_text(name,"name",limit=100); unit=required_text(unit,"unit",limit=20)
    try: quantity=float(on_hand)
    except (TypeError,ValueError): raise ServiceError("on_hand 必须是数字。",field="on_hand")
    if not math.isfinite(quantity) or quantity < 0: raise ServiceError("库存必须是非负有效数字。",field="on_hand")
    if expires_at is not None:
        expires_at=required_text(expires_at,"expires_at",limit=32)
        try: expires_at=datetime.fromisoformat(expires_at).isoformat(sep=" ")
        except ValueError:
            try: expires_at=date.fromisoformat(expires_at).isoformat()+" 23:59:59"
            except ValueError as exc: raise ServiceError("expires_at 必须是 ISO 日期或日期时间。",field="expires_at") from exc
    with get_connection() as db:
        try:
            cur=db.execute("INSERT INTO ingredients(name,unit,on_hand,expires_at) VALUES(?,?,?,?)",(name,unit,quantity,expires_at))
        except __import__('sqlite3').IntegrityError as exc:
            raise ServiceError("食材名称已存在。",409,"name","DUPLICATE") from exc
        if quantity: db.execute("INSERT INTO inventory_movements(ingredient_id,quantity,movement_type,reference) VALUES(?,?,'initial_stock','admin')",(cur.lastrowid,quantity))
        return dict(db.execute("SELECT * FROM ingredients WHERE ingredient_id=?",(cur.lastrowid,)).fetchone())


def set_recipe(dish_id, ingredients):
    did=positive_int(dish_id,"dish_id")
    if not isinstance(ingredients,list) or not ingredients: raise ServiceError("ingredients 必须是非空数组。",field="ingredients")
    values=[]
    for index,item in enumerate(ingredients):
        if not isinstance(item,dict): raise ServiceError("配方明细格式不合法。",field=f"ingredients[{index}]")
        iid=positive_int(item.get("ingredient_id"),f"ingredients[{index}].ingredient_id")
        try: amount=float(item.get("quantity_per_dish"))
        except (TypeError,ValueError): raise ServiceError("配方用量必须是数字。",field=f"ingredients[{index}].quantity_per_dish")
        if not math.isfinite(amount) or amount<=0: raise ServiceError("配方用量必须是大于 0 的有效数字。",field=f"ingredients[{index}].quantity_per_dish")
        values.append((iid,amount))
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM dishes WHERE dish_id=?",(did,)).fetchone(): raise ServiceError("菜品不存在。",404)
        for iid,_ in values:
            if not db.execute("SELECT 1 FROM ingredients WHERE ingredient_id=?",(iid,)).fetchone(): raise ServiceError("配方食材不存在。",404)
        db.execute("DELETE FROM dish_ingredients WHERE dish_id=?",(did,))
        db.executemany("INSERT INTO dish_ingredients(dish_id,ingredient_id,quantity_per_dish) VALUES(?,?,?)",[(did,iid,amount) for iid,amount in values])
        return [dict(r) for r in db.execute("SELECT * FROM dish_ingredients WHERE dish_id=?",(did,))]


def list_ingredients():
    with get_connection() as db: return [dict(r) for r in db.execute("SELECT * FROM ingredients ORDER BY name")]
