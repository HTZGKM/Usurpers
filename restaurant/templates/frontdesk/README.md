# Front desk 前台工作台

在首页 **My account** 用前台员工账号登录，进入 `/#workspace`。前台模板为 `_workspace.html`，样式和交互分别在 `restaurant/static/css/frontdesk.css` 与 `restaurant/static/js/frontdesk.js`。

全屏目录和紧凑导航共用 **Reservations**、**Table service**、**Billing records**。可以从预约区的占用桌进入服务，也可以在 Table service 选择占用桌。账单列表读取 SQLite 订单，可展开查看明细与金额。

前台和顾客端共用 `restaurant/templates/_floor_map.html`、桌位坐标、容纳人数和桌子造型。前台用颜色区分 **Available**、**Reserved** 与 **Occupied**。日期和时段筛选同时更新列表与预订桌位，手机号筛选只更新列表。

- 点 **New booking** 代订。可以指定桌位或交给 Flask 分配。编辑时默认选择原桌，时段冲突由后端返回错误。取消后列表保留 **Cancelled** 记录。
- 当天预约可从桌位或列表进入签到。预分配的桌位可直接确认，也可选择另一张合适的桌位。签到后列表显示 **Checked in**，桌位显示 **Occupied**。
- 点今日桌位图里显示为 **Available** 的桌位，再用 **Seat walk-in** 填人数。确认后桌位变为 **Occupied**，点该桌可看到散客人数。散客不出现在预约列表中。
- 在 **Walk-in waitlist** 选当前可用桌，点 **Call next party**，顾客到台后点 **Seat party**。正式站叫号后的桌位保留 1 分钟，前台显示剩余时间。

- 点已占用的桌位，再选 **Open table service**。选择菜品、数量与可选备注，添加明细并提交。未付款且未开始制作的整单可以编辑，尚在排队的明细可以取消。签到后同一桌的预点单也会显示。厨房标记 **Ready** 后，在前台点击 **Refresh** 即可确认 **Served**。
- **Record payment** 可提前记录模拟收款。当前桌所有未取消的订单结清，且各道菜均已上菜或取消后，才可使用 **Close visit → Release table**。确认释放后桌位更新，预约保留已完成状态。

正式站的前台、顾客和厨房共用 Neon PostgreSQL 中的预约与订单。前台未提交的点餐草稿保存在当前工作台。

## 接入接口

写操作复用 `restaurant/api/frontdesk/routes.py` 的表单接口。已到店列表由首页的 `GET /?fragment=seating` 模板片段提供，前台权限由 Flask 会话确认。

| 方法与路径 | 数据与分工 |
| --- | --- |
| `GET /frontdesk/bookings` | 后端接收可选 `date`、`time_slot_id`、`phone_number`，返回预约、桌号与桌位状态。前端接入当日列表和桌位图。 |
| `POST /frontdesk/bookings` | 工作台内代订表单提交 `contact_name`、`phone_number`、`booking_date`、`time_slot_id`、`party_size` 和可选 `table_id`。 |
| `GET /frontdesk/bookings/<booking_id>/edit`、`POST /frontdesk/bookings/<booking_id>/edit` | 读取预约及 `version`。保存时提交 `expected_version` 与修改后的日期、时段、人数和可选桌号。版本不符返回 409，页面保留草稿供核对。 |
| `POST /frontdesk/bookings/<booking_id>/cancel` | 带 `csrf_token`。后端校验可取消状态和时限，释放预订桌位。 |
| `POST /frontdesk/bookings/<booking_id>/check-in` | 普通签到仅提交 `csrf_token`，使用预约的最新桌号。选择换桌时额外提交 `change_table=true`、替代的 `table_id` 和 `expected_version`。后端只接受餐厅当天的预约。 |
| `POST /frontdesk/walk-ins` | 提交 `party_size`、`table_id` 与 `csrf_token`，由后端校验并建立到店记录。当前表单按路由说明只收人数和桌位。 |
| `GET /frontdesk/menu` | 返回 `dish_id`、菜名、实际价格和供应状态，供代客点单选择。 |
| `GET /frontdesk/orders`、`GET /frontdesk/orders/<order_id>` | 按桌或联系人查询订单。详情包含菜品明细、数量、备注、制作状态、金额和付款状态。 |
| `POST /frontdesk/orders` | 提交 `visit_id`、`idempotency_key`、菜品、数量、备注与当前报价。重复提交同一份内容返回原订单。 |
| `POST /frontdesk/orders/<order_id>/edit` | 提交 `expected_version` 和新的点餐明细。需要核对最新订单时，页面保留草稿并给出加载入口。 |
| `POST /frontdesk/orders/<order_id>/items/<order_item_id>/cancel`、`POST /frontdesk/orders/<order_id>/items/<order_item_id>/serve` | 带 `csrf_token`。后端校验订单与明细的关联和状态，取消后重算金额，上菜仅适用于已完成制作的明细。 |
| `POST /frontdesk/orders/<order_id>/pay`、`POST /frontdesk/visits/<visit_id>/close` | 带 `csrf_token`。后端分别确认付款与结桌，记录付款时间并在结束用餐后释放桌位。 |
