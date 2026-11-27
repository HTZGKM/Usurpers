from restaurant.db.database import begin_read, begin_write, get_connection
from .common import ServiceError, positive_int, required_text
from .order_service import kitchen_stage, _version, _order_detail_items, refresh_order_status


def _queue_items(status=None):
    with get_connection() as db:
        begin_read(db)
        rows=[dict(r) for r in db.execute("""SELECT q.*,i.note,i.status AS item_status,i.supply_issue,
            COALESCE(i.dish_name_snapshot,d.dish_name) AS dish_name,o.table_id,o.order_type,o.version AS order_version
            FROM kitchen_queue q JOIN order_items i USING(order_item_id) JOIN dishes d ON d.dish_id=i.dish_id
            JOIN orders o ON o.order_id=q.order_id WHERE q.status IN ('waiting','cooking','ready')
            ORDER BY q.priority DESC,COALESCE(q.estimated_ready_at,q.created_at),q.queue_id""")]
        stages={oid:kitchen_stage(_order_detail_items(db,oid)) for oid in {r['order_id'] for r in rows}}
        for row in rows:row['order_stage']=stages[row['order_id']]
        return [r for r in rows if status is None or r['order_stage']==status]


def get_waiting_items():return _queue_items('waiting')
def get_cooking_items():return _queue_items('cooking')
def get_ready_items():return _queue_items('ready')
def get_active_items():return _queue_items()


def get_order_details(order_id):
    with get_connection() as db:
        begin_read(db)
        order=db.execute("SELECT order_id,table_id,order_type,status,version FROM orders WHERE order_id=?",(positive_int(order_id,'order_id'),)).fetchone()
        if not order:raise ServiceError('Order not found.',404)
        items=[{k:v for k,v in row.items() if k in ('order_item_id','dish_id','dish_name','quantity','note','status','kitchen_status','supply_issue')} for row in _order_detail_items(db,order_id)]
        return {**dict(order),'items':items,'kitchen_stage':kitchen_stage(items)}


def _active_count(db):
    orders=db.execute("SELECT DISTINCT order_id FROM kitchen_queue WHERE status IN ('cooking','ready')").fetchall()
    return sum(kitchen_stage(_order_detail_items(db,r[0]))=='cooking' for r in orders)


def get_settings():
    with get_connection() as db:
        begin_read(db)
        return dict(db.execute('SELECT * FROM kitchen_settings WHERE id=1').fetchone(),active_orders=_active_count(db))


def update_settings(limit,expected_version,actor):
    limit=positive_int(limit,'max_active_orders')
    if limit>100:raise ServiceError('Choose a limit from 1 to 100.',400,field='max_active_orders')
    with get_connection() as db:
        begin_write(db)
        current=db.execute('SELECT * FROM kitchen_settings WHERE id=1').fetchone()
        if current['version']!=positive_int(expected_version,'expected_version'):
            raise ServiceError('Kitchen capacity changed. Load the latest setting before saving.',409,code='SETTINGS_CHANGED')
        db.execute('UPDATE kitchen_settings SET max_active_orders=?,version=version+1 WHERE id=1',(limit,))
        db.execute('INSERT INTO kitchen_settings_audit(actor,old_limit,new_limit) VALUES(?,?,?)',(actor,current['max_active_orders'],limit))
        return dict(max_active_orders=limit,version=current['version']+1,active_orders=_active_count(db))


def start_order(order_id,expected_version=None):
    with get_connection() as db:
        begin_write(db)
        order=db.execute('SELECT * FROM orders WHERE order_id=?',(positive_int(order_id,'order_id'),)).fetchone()
        if not order:raise ServiceError('Order not found.',404)
        _version(order,expected_version)
        items=_order_detail_items(db,order_id)
        pending=[i for i in items if i['status']=='waiting' and i['kitchen_status']=='waiting' and not i['supply_issue']]
        if not pending:raise ServiceError('No eligible dishes can start. Resolve supply issues first.',409,code='STATE_CONFLICT')
        stage=kitchen_stage(items)
        limit=db.execute('SELECT max_active_orders FROM kitchen_settings WHERE id=1').fetchone()[0]
        if stage!='cooking' and _active_count(db)>=limit:
            raise ServiceError('Kitchen capacity reached. Finish an active order before starting another.',409,code='KITCHEN_CAPACITY')
        for item in pending:
            db.execute("UPDATE order_items SET status='cooking' WHERE order_item_id=?",(item['order_item_id'],))
            db.execute("UPDATE kitchen_queue SET status='cooking',started_at=CURRENT_TIMESTAMP WHERE order_item_id=?",(item['order_item_id'],))
        db.execute('UPDATE orders SET version=version+1 WHERE order_id=?',(order_id,))
        return dict(order_id=order_id,status='cooking')


def start_item(order_item_id,expected_version=None):
    with get_connection() as db:
        row=db.execute('SELECT order_id FROM order_items WHERE order_item_id=?',(positive_int(order_item_id,'order_item_id'),)).fetchone()
    if not row:raise ServiceError('Order item not found.',404)
    return start_order(row[0],expected_version)


def finish_item(order_item_id):
    with get_connection() as db:
        begin_write(db)
        row=db.execute("SELECT order_id,status FROM order_items WHERE order_item_id=?",(positive_int(order_item_id,'order_item_id'),)).fetchone()
        if not row:raise ServiceError('Order item not found.',404)
        if row['status']!='cooking':raise ServiceError('This dish is not cooking.',409,code='STATE_CONFLICT')
        db.execute("UPDATE order_items SET status='ready' WHERE order_item_id=?",(order_item_id,))
        db.execute("UPDATE kitchen_queue SET status='ready',completed_at=CURRENT_TIMESTAMP WHERE order_item_id=?",(order_item_id,))
        db.execute('UPDATE orders SET version=version+1 WHERE order_id=?',(row['order_id'],))
        return dict(order_item_id=order_item_id,status='ready',order_stage=kitchen_stage(_order_detail_items(db,row['order_id'])))


def report_unavailable(order_item_id,reason,actor,expected_version):
    reason=required_text(reason,'reason',limit=500)
    with get_connection() as db:
        begin_write(db)
        row=db.execute('SELECT i.*,o.version,o.payment_status FROM order_items i JOIN orders o USING(order_id) WHERE order_item_id=?',(positive_int(order_item_id,'order_item_id'),)).fetchone()
        if not row:raise ServiceError('Order item not found.',404)
        _version(row,expected_version)
        if row['status']!='waiting' or row['payment_status']!='unpaid':
            raise ServiceError('Only unstarted dishes can need a replacement.',409,code='STATE_CONFLICT')
        db.execute('UPDATE order_items SET supply_issue=?,issue_reported_by=?,issue_reported_at=CURRENT_TIMESTAMP WHERE order_item_id=?',(reason,actor,order_item_id))
        db.execute('UPDATE orders SET version=version+1 WHERE order_id=?',(row['order_id'],))
        return dict(order_item_id=order_item_id,supply_issue=reason)


def serve_order(order_id,expected_version=None,actor=None):
    with get_connection() as db:
        begin_write(db)
        order=db.execute('SELECT * FROM orders WHERE order_id=?',(positive_int(order_id,'order_id'),)).fetchone()
        if not order:raise ServiceError('Order not found.',404)
        stage=kitchen_stage(_order_detail_items(db,order_id))
        if stage=='served':return dict(order_id=order_id,status='served',already_served=True)
        _version(order,expected_version)
        if not order['visit_id'] or not db.execute("SELECT 1 FROM dining_sessions WHERE visit_id=? AND status='seated'",(order['visit_id'],)).fetchone():
            raise ServiceError('Seat the guest before confirming service.',409,code='VISIT_NOT_SEATED')
        if stage!='ready':raise ServiceError('Every dish must be ready and all supply issues resolved before serving this order.',409,code='ORDER_NOT_READY')
        db.execute("UPDATE order_items SET status='served' WHERE order_id=? AND status='ready'",(order_id,))
        db.execute("UPDATE kitchen_queue SET status='served',completed_at=CURRENT_TIMESTAMP WHERE order_id=? AND status='ready'",(order_id,))
        db.execute('UPDATE orders SET served_by=?,served_at=CURRENT_TIMESTAMP WHERE order_id=?',(actor,order_id))
        refresh_order_status(db,order_id)
        return dict(order_id=order_id,status='served',already_served=False)


def serve_item(order_item_id):
    raise ServiceError('Confirm serving for the whole order from the front desk.',409,code='WHOLE_ORDER_REQUIRED')


def check_order_complete(order_id):
    with get_connection() as db:
        if not db.execute('SELECT 1 FROM orders WHERE order_id=?',(order_id,)).fetchone():raise ServiceError('Order not found.',404)
        return kitchen_stage(_order_detail_items(db,order_id)) in ('served','cancelled')
