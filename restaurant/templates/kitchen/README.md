# Kitchen 厨房工作台

通过首页 **My account** 使用厨房员工账号登录，进入 `/#workspace`。工作台使用现有 Flask 会话判断角色。前端模板为 `_workspace.html`，样式和交互分别在 `restaurant/static/css/kitchen.css` 和 `restaurant/static/js/kitchen.js`。

- **Queue** 按订单显示菜品、数量和备注。单项通过 **Start preparation** 进入制作，随后点 **Mark ready**。前台标记上菜后，该菜品从队列移出。
- **Availability** 按菜单分类显示现有菜品的供应状态。可以切换 **Available** 和 **Unavailable**。
- 队列定时刷新，也可点 **Refresh**。供应状态写入 SQLite，顾客重新进入或刷新菜单时读取更新。

## 接入接口

复用 `restaurant/api/kitchen/routes.py` 的接口。写操作包含 Flask-WTF 的 CSRF 表单字段。

| 方法与路径 | 后端提供的数据或动作 |
| --- | --- |
| `GET /kitchen/queue?status=waiting\|cooking\|ready` | 按状态读取订单号、明细 ID、菜品 ID、数量与备注。 |
| `POST /kitchen/items/<order_item_id>/start`、`POST /kitchen/items/<order_item_id>/complete` | 开始制作和标记出餐就绪。上菜由前台确认。 |
| `GET /kitchen/menu` | 菜品 ID、菜名、分类和当前 `is_available`。 |
| `POST /kitchen/menu/<dish_id>/availability` | 根据 `is_available` 更新对应菜品的供应状态。 |
