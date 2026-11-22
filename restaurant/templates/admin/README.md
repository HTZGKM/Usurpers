# Administrator 主管理员工作台

在首页 **My account** 用管理员账号登录，进入 `/#workspace`。Jinja 根据现有 Flask 会话选择后台模板。页面使用 `_workspace.html`、`restaurant/static/css/admin.css` 与 `restaurant/static/js/admin.js`。

- **Overview** 显示当日营业指标、按小时的分类曲线、最近订单和 Top 5／Top 12 菜品销量。
- **Orders** 显示近七天曲线。历史订单可按日期、状态和付款状态筛选，点选后显示当时的单价、数量和备注。
- **Kitchen queue** 按出餐和制作状态拆分实际订单明细。**Tables** 提供桌位图、预约时间轴和月历。
- **Accounts** 可新增、编辑和停用前台或厨房员工，顾客列表只读。**Dishes** 可按分类和状态筛选，支持新增、编辑与归档。
- 点击左上角 Logo 打开项目全屏目录。顶部管理员圆标可查看当前账号并退出。

## 数据口径与扩量

主管工作台使用 SQLite 业务数据。`GET /admin/workspace` 返回当前营业时间、最近七天与仍活跃的订单、桌位和预约。`GET /admin/workspace/orders` 支持按营业日查历史订单。`/admin/accounts`、`/admin/staff` 和 `/admin/dishes` 负责账户与菜品操作，写入使用 Flask-WTF 表单与 CSRF。

- 订单时间按后端约定以 UTC 写入，页面按北京时间归档。分类订单数按订单与组别去重，营收使用已付款、未取消明细的快照单价乘数量，按下单时间分桶。这是销售毛额口径，退款记录另行核算。
- 批量写入时使用业务表 `order_headers` 和 `order_lines`，配置 `dishes.category` 为 `burgers`、`pizzas`、`sides` 或 `drinks`。小食和饮料合并为第三条曲线。未分类菜品仍显示在订单和排行榜里，分类曲线会标注排除未分类明细。
- 出餐队列还需要对应的 `kitchen_queue` 状态和完成时间，桌位状态由 `dining_sessions` 和当前营业日的 `bookings` 提供。完整预约时间来自 `time_slots`。
- 前台与厨房页面若仍使用 `staff-demo.js`，其浏览器演示操作独立于 SQLite；主管会反映数据库和业务接口写入的状态。
- 概览和厨房队列在前台可见时定期刷新，操作弹窗和键盘聚焦控件时推迟刷新。

## 素材

- 餐盘来自 [CC0 Tableware Icons](https://opengameart.org/content/cc0-tableware-icons)。
- 汉堡、披萨和饮料像素图来自 [Kenney Pixel Platformer Food Expansion](https://kenney.nl/assets/pixel-platformer-food-expansion)。
- 薯条来自 [Icons Food](https://opengameart.org/content/icons-food)。

## 设计参考

- [DashStack](https://www.figma.com/design/vybKhWOfrtzqKarx6tEwdj/?node-id=0-40222) 的分组侧栏和指标卡。
- [BRIX Chart UI Components](https://www.figma.com/design/P79JJlLYuvtJwRuXkE3lmP/?node-id=9-47) 的条形图和数值标签。
- [shadcn Dashboard Blocks](https://ui.shadcn.com/blocks/dashboard) 的筛选表格与概览到明细的层级。
- [Sales Management Dashboard](https://www.figma.com/design/AdciXRgEJnNHwQt8XiY4Pt/?node-id=0-1) 由用户提供，本轮画布未能加载。
