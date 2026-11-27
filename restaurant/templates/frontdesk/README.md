# Front desk 前台工作台

从首页 My account 登录前台账号，进入 `/#workspace`。模板为 `_workspace.html`，样式和交互位于 `restaurant/static/css/frontdesk.css` 与 `restaurant/static/js/frontdesk.js`。

## 正式站流程

- Reservations：代订、修改、取消、登记到店、确认备桌和安排入座。到店登记与入座是不同动作；当前桌况与预约日期筛选分开显示。
- Walk-in waitlist：前台取号、叫号、过号或取消、安排入座。正式站叫号留桌 1 分钟。
- Table service：代客点单、改单、取消尚未制作的明细、确认上菜和记录模拟付款。制作与付款状态决定允许的操作。
- 关桌要求未取消订单已付款，所有菜品已上菜或取消；之后进入清台流程。
- 工作台自动刷新。未确认的提交可恢复原请求，版本冲突保留改单草稿。

正式站业务记录保存在 Neon PostgreSQL。浏览器只保留未提交的草稿；写入请求包含会话和 CSRF 校验。

## 接口维护入口

| 范围 | 源文件与前缀 |
| --- | --- |
| 正式预约、到店、备桌、入座、等位与桌位停用 | `restaurant/api/reservation_routes.py`，`/frontdesk/reservation-api` |
| 菜单、订单、改单、上菜、付款与关桌 | `restaurant/api/frontdesk/routes.py`，`/frontdesk` |
| 独立任务请求 | `restaurant/api/operations.py`，`POST /operations/refresh` |
| 本地 SQLite 兼容预约 | `restaurant/api/frontdesk/routes.py`；页面按 `reservationFlow` 选择接口 |

具体字段以路由与表单定义为准。测试在隔离数据库执行，正式预约及写入竞争使用 PostgreSQL。
