# Kitchen 厨房工作台

通过首页 **My account** 使用厨房员工账号登录，进入 `/#workspace`。工作台使用现有 Flask 会话判断角色。前端模板为 `_workspace.html`，样式和交互分别在 `restaurant/static/css/kitchen.css` 和 `restaurant/static/js/kitchen.js`。

- **Queue** 按订单显示桌号、菜品、数量和备注。点击单项的 **Complete** 后，该项显示 **Completed**。全部菜品完成后，订单显示 **Ready**，保留在队列中供查看。
- **Availability** 按菜单分类显示现有菜品的供应状态。可以切换 **Available** 和 **Unavailable**。
- 队列使用演示订单，供应状态从顾客端目录取初始值。同一标签页切换前台和厨房账号可继续演示新订单、制作完成和上菜。前台取消的明细会离开厨房队列。厨房供应切换影响同标签页内前台的演示菜单，顾客菜单和 SQLite 沿用现有数据来源。

## 后续联调

复用 `restaurant/kitchen/routes.py` 中已有的接口定义。当前蓝图和业务逻辑待后端接通，前端没有新增 Flask 路由。

| 方法与路径 | 后端提供的数据或动作 |
| --- | --- |
| `GET /kitchen/queue` | 制作队列和每项明细，包含订单号、桌位、明细 ID、菜品、数量、备注和制作状态。 |
| `POST /kitchen/order-items/<order_item_id>/complete` | 按订单明细 ID 标记制作完成，返回更新后的状态。前台确认上桌是另一个操作。 |
| `GET /kitchen/menu` | 菜品 ID、菜名、分类和当前 `is_available`。 |
| `POST /kitchen/menu/<dish_id>/availability` | 根据 `is_available` 更新对应菜品的供应状态。 |
