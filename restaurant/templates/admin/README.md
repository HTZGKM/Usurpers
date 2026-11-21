# Administrator 主管理员工作台

在首页 **My account** 用管理员账号登录，进入 `/#workspace`。Jinja 根据现有 Flask 会话选择后台模板。页面使用 `_workspace.html`、`restaurant/static/css/admin.css` 与 `restaurant/static/js/admin.js`。

- **Overview** 显示当日订单数、当日订单中的已付款数、待制作明细和占用桌位。订单状态条形图可进入带对应筛选的订单表。
- **Orders** 按日期、订单状态和付款状态查订单。详情显示下单时的单价、数量、备注和状态。
- **Kitchen queue** 和 **Tables** 用于只读查看队列与桌位。桌位图使用前台和顾客端共用的模板，支持按日期和时段查看。
- **Accounts** 支持角色筛选，顾客账号只读。可新增、编辑和停用前台或厨房的演示账号。演示账号不改变真实登录权限，输入的密码不保存。
- **Dishes** 支持筛选、新增、编辑、改价和归档。归档菜品从同标签页的前台点菜单和厨房供应列表撤下，已有订单保留原菜名和价格。临时供应状态由厨房操作。

运营数据来自同一浏览器标签页中的演示状态，见 `restaurant/static/js/staff-demo.js`。刷新或切换员工账号后仍可继续演示。正式收入汇总的口径和查看权限待确认。

## 后续联调

复用 `restaurant/api/admin/routes.py` 中的路由定义。当前没有新增 Flask 路由，也未更改后端业务或数据库。

| 方法与路径 | 后端处理与前端用途 |
| --- | --- |
| `GET /admin/orders`、`GET /admin/orders/<order_id>` | 按 `date`、`status`、`payment_status` 查询，返回订单和明细、历史单价、制作、上菜和付款状态。用于概览及订单。 |
| `GET /admin/kitchen-queue`、`GET /admin/tables` | 返回制作队列与按 `date`、`time_slot_id` 查询的桌位状态。两个页面只读。 |
| `GET /admin/accounts` | 按 `role` 查询账号及启用状态。顾客账号只读，响应无密码字段。 |
| `POST /admin/staff`、`GET /admin/staff/<staff_id>/edit`、`POST /admin/staff/<staff_id>/edit`、`POST /admin/staff/<staff_id>/deactivate` | 校验管理员角色、账号字段及记录状态。新增表单字段为 `name`、`phone_number`、`email`、`role` 和 `password`，修改沿用前四项。POST 使用 `csrf_token`。 |
| `GET /admin/dishes`、`POST /admin/dishes`、`GET /admin/dishes/<dish_id>/edit`、`POST /admin/dishes/<dish_id>/edit`、`POST /admin/dishes/<dish_id>/archive` | 返回菜品的价格、供应与归档状态，校验并保存 `name`、`price`、`ingredients`、`prep_time_minutes`、可选 `image_path`。POST 使用 `csrf_token`。当前演示表单也包含前端菜单分类，正式字段待确认。 |

## 设计参考

- [DashStack](https://www.figma.com/design/vybKhWOfrtzqKarx6tEwdj/?node-id=0-40222) 的分组侧栏和指标卡。
- [BRIX Chart UI Components](https://www.figma.com/design/P79JJlLYuvtJwRuXkE3lmP/?node-id=9-47) 的条形图和数值标签。
- [shadcn Dashboard Blocks](https://ui.shadcn.com/blocks/dashboard) 的筛选表格与概览到明细的层级。
- [Sales Management Dashboard](https://www.figma.com/design/AdciXRgEJnNHwQt8XiY4Pt/?node-id=0-1) 由用户提供，本轮画布未能加载。
