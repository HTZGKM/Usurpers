from restaurant.db.database import get_connection
from .common import ServiceError, money, positive_int, required_text


def get_available_items():
    with get_connection() as db:
        return [dict(r) for r in db.execute("SELECT * FROM dishes WHERE is_available=1 AND is_archived=0 ORDER BY dish_id")]


def get_all_items():
    with get_connection() as db: return [dict(r) for r in db.execute("SELECT * FROM dishes ORDER BY dish_id")]


def get_listed_items(): return get_available_items()


def archive_item(dish_id):
    did=positive_int(dish_id,"dish_id")
    with get_connection() as db:
        cur=db.execute("UPDATE dishes SET is_archived=1,is_available=0 WHERE dish_id=?",(did,))
        if not cur.rowcount: raise ServiceError("菜品不存在。",404)
        return {"dish_id":did,"is_archived":True}


def create_item(name, price, ingredients="", prep_time_minutes=10, image_url=None):
    name=required_text(name,"name",limit=100); amount=str(money(price))
    prep=positive_int(prep_time_minutes,"prep_time_minutes")
    ingredients=ingredients if isinstance(ingredients,str) else None
    if ingredients is None or len(ingredients)>1000: raise ServiceError("原料描述格式不正确。",field="ingredients")
    if image_url is not None and (not isinstance(image_url,str) or len(image_url)>500): raise ServiceError("图片地址格式不正确。",field="image_url")
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM dishes WHERE dish_name=?",(name,)).fetchone(): raise ServiceError("菜品名称已存在。",409,"name","DUPLICATE")
        cur=db.execute("INSERT INTO dishes(dish_name,price,ingredients,prep_time_minutes,image_url) VALUES(?,?,?,?,?)",(name,amount,ingredients,prep,image_url))
        return dict(db.execute("SELECT * FROM dishes WHERE dish_id=?",(cur.lastrowid,)).fetchone())


def update_item(dish_id, name=None, price=None, is_available=None):
    did=positive_int(dish_id,"dish_id")
    with get_connection() as db:
        db.execute("BEGIN IMMEDIATE")
        existing=db.execute("SELECT * FROM dishes WHERE dish_id=?",(did,)).fetchone()
        if not existing: raise ServiceError("菜品不存在。",404,"dish_id","NOT_FOUND")
        if name is not None: name=required_text(name,"name",limit=100)
        if price is not None: price=str(money(price))
        if is_available is not None and is_available not in (True,False,0,1): raise ServiceError("供应状态不合法。",field="is_available")
        if existing["is_archived"] and is_available: raise ServiceError("已归档菜品不能恢复供应。",409,code="STATE_CONFLICT")
        if name is not None and db.execute("SELECT 1 FROM dishes WHERE dish_name=? AND dish_id<>?",(name,did)).fetchone():
            raise ServiceError("菜品名称已被使用。",409,"name","DUPLICATE")
        if name is not None: db.execute("UPDATE dishes SET dish_name=? WHERE dish_id=?",(name,did))
        if price is not None: db.execute("UPDATE dishes SET price=? WHERE dish_id=?",(price,did))
        if is_available is not None: db.execute("UPDATE dishes SET is_available=? WHERE dish_id=?",(int(is_available),did))
        return dict(db.execute("SELECT * FROM dishes WHERE dish_id=?",(did,)).fetchone())


def update_price(dish_id, price): return update_item(dish_id,price=price)
def mark_sold_out(dish_id): return update_item(dish_id,is_available=False)
def restore_availability(dish_id): return update_item(dish_id,is_available=True)
