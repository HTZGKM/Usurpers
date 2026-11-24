"""食材库存管理。只判断现存量，不做预留。"""
from restaurant.db.database import get_connection
from .common import ServiceError, positive_int, required_text
import math
from datetime import date, datetime


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
        if float(row[0])+delta < 0: raise ServiceError("调整后库存不能为负。",409,code="INVENTORY_CONFLICT")
        db.execute("UPDATE ingredients SET on_hand=on_hand+? WHERE ingredient_id=?",(delta,iid))
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
