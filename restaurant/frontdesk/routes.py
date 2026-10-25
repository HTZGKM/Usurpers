# 前台工作首页
def dashboard():
    pass


# 查看和筛选订座记录
def bookings():
    pass


# 代顾客创建订座
def create_booking():
    pass


# 代顾客修改订座
def edit_booking(booking_id):
    pass


# 代顾客取消订座
def cancel_booking(booking_id):
    pass


# 查看餐桌和时段占用情况
def tables():
    pass


# 登记预约顾客到店
def register_arrival(booking_id):
    pass


# 登记没有预约的现场顾客
def register_walk_in():
    pass


# 为堂食顾客分配餐桌
def assign_table(dining_session_id):
    pass


# 修改餐桌状态
def update_table_status(table_id):
    pass


# 结束堂食并释放餐桌
def close_dining_session(dining_session_id):
    pass


# 查看和筛选订单
def orders():
    pass


# 代顾客提前订菜
def create_preorder():
    pass


# 代顾客提交堂食订单
def create_dine_in_order(dining_session_id):
    pass


# 代顾客修改订单
def edit_order(order_id):
    pass


# 代顾客取消订单
def cancel_order(order_id):
    pass


# 查看菜单管理页面
def menu():
    pass


# 调整菜品价格
def update_menu_price(menu_item_id):
    pass


# 调整菜品上架和供应状态
def update_menu_availability(menu_item_id):
    pass


# 查看正在制作的菜品
def cooking_items():
    pass


# 按菜品状态查询已经制作完成、等待上桌的菜品
def ready_items():
    pass


# 确认菜品已经上桌
def serve_item(order_item_id):
    pass
