# 顾客端开发交接

从仓库根目录启动 Flask。新对话从本文件、`app.py` 和本目录的 `guest.html` 开始。页面与交互的维护来源是仓库内的 Jinja、CSS、JavaScript 和图片，运行时无需原型生成脚本、Figma CLI 或本机 Codex 文件。

## 当前视觉基准

烛火石厅延续主管页的氛围。顾客页采用纯黑、暖白和少量浅金，菜单使用黑底菜图、Forum 菜名与价格，以及 Satoshi Light 描述。配色、排版和切页动效见 [顾客端设计工作流](../../../docs/customer-design-workflow.md)。

顾客专用样式为 `restaurant/static/css/guest-ember.css`，仅在公共/顾客身份加载，不影响三类员工工作区。四张原创场景图位于 `restaurant/static/images/ember/`，生成提示词和来源见该目录 `assets.json`。菜品目录图、菜名与价格保持原有对应关系。

## 运行与预览

按 [仓库启动说明](../../../README.md#本地启动) 从 `Usurpers` 根目录启动 Flask，再打开 [顾客首页](http://127.0.0.1:5000/)。

## 文件索引

| 要改的内容 | 从仓库根目录进入 |
| --- | --- |
| 首页入口、真实菜单、桌位和时段的模板上下文 | `app.py` 的 `home()`、`restaurant/presentation.py` |
| 页面组合、导航弹窗、Your visit 和 Journal 容器 | `restaurant/templates/customer/guest.html` |
| 首页、导航、封面和面板宏 | `restaurant/templates/customer/_guest_parts.html` |
| 双栏菜单、分类锚点、菜品弹层 | `restaurant/templates/customer/_guest_menu.html`、`_guest_dish.html` |
| Delivery 封面、配送时间和范围 | `restaurant/templates/customer/_guest_delivery.html` |
| Journal 近期正文、归档和共享文章内容 | `restaurant/templates/customer/_guest_journal.html`、`_guest_journal_archive.html`、`_guest_journal_entries.html` |
| 单页订座、二维桌位图和表单 | `restaurant/templates/customer/_guest_reservation.html` |
| My account 登录、注册与登录后资料 | `restaurant/templates/customer/_guest_account.html`，表单定义在 `restaurant/api/auth/forms.py` |
| 菜品照片和描述 | `restaurant/api/customer/catalog.json` |
| 布局、响应式、字号与字体 | `restaurant/static/css/guest.css`、`guest-type.css` |
| 页面跳转、账号表单、订座、购物袋、堂食订单和模拟付款 | `restaurant/static/js/guest.js` |
| 订座月历、日期选中和键盘操作 | `restaurant/static/js/guest-calendar.js` |
| 购物袋金额与草稿 | `restaurant/static/js/guest-meal.js` |
| Flask 表单请求、CSRF 和到店状态读取 | `restaurant/static/js/restaurant-api.js` |
| 切页照片叠化、标题逐字淡入和减少动态效果 | `restaurant/static/js/guest-motion.js`、`guest.js`、`restaurant/static/css/guest-ember.css` |
| 封面、菜单缩略图、五款高清披萨 | `restaurant/static/images/atelier/{editorial,catalog,detail}/` |

界面文案用英文。菜单保留左侧照片和右侧分组菜品。桌面端滚动时保留左侧封面，各端都将当前分类和购物袋入口放在吸顶栏。订座与确认在同一页完成，下单、付款和回执在 Your visit 内切换。原 `/#Your%20table` 地址继续有效。顾客页封面大标题使用 Palatino 字体栈，菜单字体来源见 [字体说明](../../static/fonts/README.md)。

## 验收路径

1. 未登录打开 `/`，检查 Menu、Book a table、Your visit、Delivery 和 Journal 都可浏览。点订座页 **Sign in to check availability**、菜品详情 **Add to bag** 或 Your visit 的 **Sign in to view your visit**，应弹出登录提醒。顾客登录后回原视图。选日期、人数、时段和相容桌位，确认后可原地改单、取消。
2. 前台在 **Reservations** 选同一笔预约并点 **Confirm arrival**。顾客进入 **Your visit**，确认已签到。进入 **Pizzas**，将两份 **Margherita** 加到购物袋，可加厨房备注。
3. 点击 **View bag (2) · ¥116**，提交订单。厨房接单并标记 **Ready**。前台标记上菜、结账和释放桌位。顾客可刷新 **Your visit** 查看订单详情，主管可看到同一笔记录。
4. 首页、菜单和订座均应支持窄屏。打开玻璃导航时用键盘检查焦点和 Esc；系统选择减少动态效果时，过渡应减弱。
5. 从首页打开左上角导航，点 **My account**。试一次空表单和错误密码，核对英文提示及焦点。点 **Register**，用测试号码注册，成功后应回到 **Sign in** 并填好号码。同一号码重复注册应提示已注册。
6. 登录后在同页看到 **My profile** 及账号资料，刷新后仍保持登录。点 **Sign out** 后应看到英文退出提示，且 `GET /auth/me` 返回 HTTP 401。需要测试注册写入时用独立 SQLite 测试库，避免在日常开发库累积账号。

## 当前进度

- **已完成 My account。** 入口为 `/#My%20account`，`/#account` 也可打开。封面、导航、字体和面板沿用当前顾客端。账号表单复用 Flask-WTF 字段、CSRF 校验及原有 `/auth/*` 路由。前端根据原生表单响应显示英文必填、登录失败、重复号码、提交中和退出反馈。认证模板为原有错误提示补充了字段标记。
- **公共首页与角色导航。** 未登录访客可以浏览，登录后从原位置继续。员工进入 `/#workspace`，通过 `#workspace/…` 切换各角色视图。
- **数据位置。** 预约、签到、下单和记账付款使用 SQLite。未提交的购物袋和订座草稿按顾客保存在当前标签页。
- **已验收。** 在隔离 Flask 预览走通 A1 订座、前台签到、两份 Margherita 下单、厨房出餐、前台记账结清和关桌。主管概览能找到同一订单。
- **Delivery** 保留封面与 **Coming soon** 信息。
- **Journal 已改为长页。** 首页卡片和全屏导航进入 `/#Journal`。左侧封面尺寸独立，右侧按日期列出近期五篇正文。底部 **See more** 打开 `/#Journal/archive`，左栏目录定位文章，右栏按日期列出所有已有文章并支持展开纯文字正文。两页共用文章内容。
- **菜品和购物袋。** 菜品 ID、价格和供应由 SQLite 提供。点餐表单提交数量与厨房备注。购物袋支持改数量、改备注和移除。
- **预约和订单记录。** **Your visit** 与 **My account** 从 Flask 读取顾客名下的记录。展开订单可查看菜品、备注和金额；未结账、尚未开始制作的订单可以整单修改或取消，尚未制作的明细可单独取消。
- **等位和预点菜。** 未入座时可在 **Your visit** 取号、刷新叫号状态或退出等位。有有效预约时，可把购物袋提交为预点单，签到并到预约时间才会入厨房。

## 待联调与内容确认

| 项目 | 当前状态与跟进人 |
| --- | --- |
| 规格与加料 | 当前订单表单支持菜品、数量和备注。付费规格与加料等待后端提供可定价的字段。 |
| 配送 | 保留 **Coming soon**。先确认取餐或配送方式、营业时间和范围，再确定是否需要配送下单入口。 |

## 路由协作

已有路由优先复用。缺路由时，前端负责建立已对齐的 Flask 路由入口并完成页面联调。纯渲染的 GET 可以由前端完成。涉及业务查询的 GET，以及预订、下单等 POST，前端负责表单和页面状态，后端与数据库同学负责权限、业务校验、查询、事务及写入。接口尚未实现时在交接中注明，联调完成后再标为已接通。

本轮复用 `GET /tables/available`、`GET/POST /bookings`、改约和取消接口、`POST /visits/<visit_id>/orders`、`GET /orders` 与 `POST /orders/<order_id>/pay`。写操作提交 Flask-WTF 的表单字段和 CSRF。现有首页增加 `GET /?fragment=seating` 模板片段，顾客只读取自己的进行中到店会话。

顾客提交订座时生成 `idempotency_key`，同一次重试使用相同的键和原始表单。收到原预约后可再改约。改约提交页面读取到的 `version` 作为 `expected_version`，版本冲突返回 409，并保留输入供顾客核对。

## 旧前端删除清单

以下为历史记录。Forum 字体及 OFL 许可已随菜单排版恢复。

- 路由：`GET /classic`、`GET /album`。顾客和员工入口统一使用 `GET /`，认证和业务接口继续使用原有定义。
- `restaurant/templates/customer/`：`index.html`、`_booking.html`、`_home.html`、`_editorial.html`、`_components.html`、`_pixels.html`、`album.html`。旧前台、厨房和管理员工作台共用其中的模板和脚本。
- `restaurant/static/css/`：`styles.css`、`album.css`。
- `restaurant/static/js/`：`main.js`、`customer-records.js`、`album.js`。
- `restaurant/static/fonts/`：`Forum-Regular.ttf`、`Forum-OFL.txt`、`Inter-Latin.woff2`、`Inter-OFL.txt`、`restaurant-sign.ttf`、`restaurant-sign-subset.ttf`、`subset.css`、`OFL.txt`。
- `restaurant/static/vendor/`：`lucide.min.js`、`LICENSE`。
- `restaurant/static/images/album/`：`burger-beige.jpg`、`burger-table.jpg`、`dining-room.jpg`、`lemonade.jpg`、`pizza-box.jpg`、`pizza-grey.jpg`、`pizza-oven.jpg`、`pizza-table.jpg`、`pizza-white.jpg`、`storefront.jpg`、`takeaway-pizza.jpg`、`window-seats.jpg`。
- `restaurant/static/images/`：`burger.jpg`、`double-burger.jpg`、`interior.jpg`、`mushroom-pizza.jpg`、`pizza.jpg`、`shared-table.jpg`、`wood-burger.jpg`、`shuangfen-mark.svg`，以及 `pixels/` 下的 `burger.png`、`drinks.png`、`pizza.png`、`sides.png`。
- `restaurant/static/images/atelier/editorial/`：`home-portrait.webp`、`oven-wide.webp`、`pizza-table-menu.webp`、`room-wide.webp`。当前封面与计划用于 Delivery、Journal 的素材保留。
- `restaurant/SOURCES.json`：上述旧照片、字体和图标的来源清单。
- 另外，`atelier/` 下 12 个未跟踪的旧 WebP 和 `atelier/menu/` 下 8 张旧缩略图已移出项目，备份在本次对话的 `retired-untracked-frontend/` 目录。
