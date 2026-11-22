# 顾客端开发交接

从仓库根目录启动 Flask。新对话从本文件、`app.py` 和本目录的 `guest.html` 开始。页面与交互的维护来源是仓库内的 Jinja、CSS、JavaScript 和图片，运行时无需原型生成脚本、Figma CLI 或本机 Codex 文件。

## 当前视觉基准（2026-11-22）

顾客端以主管页同源的「类魂游戏史诗风格」为核心：炭黑、旧金、Palatino 衬线字与烛火石厅。Qitchen 用于首页大图与入口列、内页双栏及摄影排印质量参考。后续修改先读 [顾客端设计工作流](../../../docs/customer-design-workflow.md)。

顾客专用样式为 `restaurant/static/css/guest-ember.css`，仅在公共/顾客身份加载，不影响三类员工工作区。四张原创场景图位于 `restaurant/static/images/ember/`，生成提示词和来源见该目录 `assets.json`。菜品目录图、菜名与价格保持原有对应关系。

本轮预览：`http://127.0.0.1:5001/`。启动：`.venv/bin/python -m flask --app app run --host 127.0.0.1 --port 5001`。

## 运行与预览

```powershell
.\.venv\Scripts\python.exe -m flask --app app run --debug --no-debugger --port 18749
```

浏览器打开 [顾客首页](http://127.0.0.1:18749/)。也可以按仓库根 README 运行 `python app.py`，默认端口 5000。在当前对话侧边预览本机 Flask 地址，修改模板或静态资源后刷新。旧的 18748 端口是独立 HTML 演示。

## 文件索引

| 要改的内容 | 从仓库根目录进入 |
| --- | --- |
| 首页入口、模板上下文、桌号/容量/坐标和时段 | `app.py` 的 `home()` |
| 页面组合、导航弹窗、Your visit 和 Journal 容器 | `restaurant/templates/customer/guest.html` |
| 首页、导航、封面和面板宏 | `restaurant/templates/customer/_guest_parts.html` |
| 双栏菜单、分类锚点、菜品弹层 | `restaurant/templates/customer/_guest_menu.html`、`_guest_dish.html` |
| Delivery 封面、配送时间和范围 | `restaurant/templates/customer/_guest_delivery.html` |
| Journal 近期正文、归档和共享文章内容 | `restaurant/templates/customer/_guest_journal.html`、`_guest_journal_archive.html`、`_guest_journal_entries.html` |
| 单页订座、二维桌位图和表单 | `restaurant/templates/customer/_guest_reservation.html` |
| My account 登录、注册与登录后资料 | `restaurant/templates/customer/_guest_account.html`，表单定义在 `restaurant/api/auth/forms.py` |
| 菜名、配料、示例价格、售罄标志 | `restaurant/api/customer/catalog.json` |
| 布局、响应式、字号与字体 | `restaurant/static/css/guest.css`、`guest-type.css` |
| 页面跳转、账号表单、订座、购物袋、堂食订单和模拟付款 | `restaurant/static/js/guest.js` |
| 订座月历、日期选中和键盘操作 | `restaurant/static/js/guest-calendar.js` |
| 菜品可选项、演示加价和旧购物袋数据兼容 | `restaurant/static/js/guest-meal.js` |
| 导航的玻璃悬停、按下、键盘与减少动态效果 | `restaurant/static/js/guest-lens.js` |
| 封面、菜单缩略图、五款高清披萨 | `restaurant/static/images/atelier/{editorial,catalog,detail}/` |

界面文案用英文。菜单保留左侧照片和右侧分组菜品。桌面端滚动时保留左侧封面，各端都将当前分类和购物袋入口放在吸顶栏。订座与确认在同一页完成，下单、付款和回执在 Your visit 内切换。原 `/#Your%20table` 地址继续有效。顾客端标题使用与主管页一致的 Palatino 字体栈。

## 验收路径

1. 未登录打开 `/`，检查 Menu、Book a table、Your visit、Delivery 和 Journal 都可浏览。点订座页 **Sign in to check availability**、菜品详情 **Add to bag** 或 Your visit 的 **Sign in to view your visit**，应弹出登录提醒。顾客登录后回原视图。选日期、人数、时段和相容桌位，确认后可原地改单、取消。
2. 点 **Preview host check-in**。进入菜单后切换到 **Pizzas**，打开 **Margherita**，选两份，加到购物袋。关闭详情时回到原列表位置。
3. 在菜单分类栏点 **View bag (2) · ¥116**，点 **Place order**，再点 **Pay ¥116 · demo**。同页显示 **Payment received**。刷新后该标签页仍可查看回执。
4. 首页、菜单和订座均应支持窄屏。打开玻璃导航时用键盘检查焦点和 Esc；系统选择减少动态效果时，过渡应减弱。
5. 从首页打开左上角导航，点 **My account**。试一次空表单和错误密码，核对英文提示及焦点。点 **Register**，用测试号码注册，成功后应回到 **Sign in** 并填好号码。同一号码重复注册应提示已注册。
6. 登录后在同页看到 **My profile** 及账号资料，刷新后仍保持登录。点 **Sign out** 后应看到英文退出提示，且 `GET /auth/me` 返回 HTTP 401。需要测试注册写入时用独立 SQLite 测试库，避免在日常开发库累积账号。

## 当前进度

- **已完成 My account。** 入口为 `/#My%20account`，`/#account` 也可打开。封面、导航、字体和面板沿用当前顾客端。账号表单复用 Flask-WTF 字段、CSRF 校验及原有 `/auth/*` 路由。前端根据原生表单响应显示英文必填、登录失败、重复号码、提交中和退出反馈。认证模板为原有错误提示补充了字段标记。
- **公共首页与角色导航。** 未登录和顾客使用同一份餐厅目录，公共内容可浏览。需要账号的动作通过弹窗引导至现有 My account 登录表单，顾客登录后回到原视图。员工登录后进入 `/#workspace`，工作区内部使用 `#workspace/…` 切换。前台和厨房共享当前标签页的演示业务状态，主管侧栏和 Logo 目录连接读取 SQLite 的工作区。见 [厨房交接](../kitchen/README.md)、[前台交接](../frontdesk/README.md) 和 [管理员交接](../admin/README.md)。
- **数据位置。** 当前本机 Flask 使用 `restaurant/data/shuangfen.db` 保存账号和密码哈希，浏览器用会话 Cookie 保持登录。订座、签到、购物袋、订单和付款仍按标签页和身份保存在 sessionStorage，属于演示数据，厨房收不到这些操作。
- **已验收。** 在侧边浏览器走通 A2 订座、模拟到店、两份 Margherita、¥116 下单及模拟付款，刷新后仍可看到回执。在连接独立 SQLite 的侧边预览中验证注册、号码回填、重复号码、错误密码、登录后刷新及退出。
- **Delivery 已接入。** 从全屏导航进入 `/#Delivery`，左侧封面和右侧四格沿用旧构图，字体与当前顾客端一致。配送时间与范围显示 **Coming soon**。仓库只有 `create_delivery_order()` 占位，尚未确认到店自取还是送上门，页面目前只展示信息并提供看菜单和订座入口。本轮没有新增 Flask 路由或业务接口。
- **Journal 已改为长页。** 首页卡片和全屏导航进入 `/#Journal`。左侧封面尺寸独立，右侧按日期列出近期五篇正文。底部 **See more** 打开 `/#Journal/archive`，左栏目录定位文章，右栏按日期列出所有已有文章并支持展开纯文字正文。两页共用文章内容。
- **菜品和购物袋。** 披萨可选尺寸、饼底和加料，汉堡可选酱料和加料。菜品可写厨房备注，菜品小计和购物袋合计会随操作更新并从个位开始依次停止滚动。购物袋支持改选项、改数量和移除，同菜不同配置可分别保留。加价沿用旧版演示数据。
- **预约和订单记录。** **Your visit** 以及已登录顾客的 **My account** 显示当前及同标签页历史。保留已取消或已完成的预约及订单快照，订单可展开查看菜品、选项、备注和金额。

## 待联调与内容确认

| 项目 | 当前状态与跟进人 |
| --- | --- |
| 真实订单记录 | 复用 `restaurant/api/customer/routes.py` 中的 `GET /orders`。当前 Flask 已注册顾客蓝图；顾客前端仍使用 sessionStorage 演示记录，尚未接入该查询。后端实现时从当前会话确定顾客身份，无需前端传手机号。建议响应包含订单 ID、下单时间、金额、付款状态与菜品明细，前端据此接入 **My orders**。当前开发库中已有订单 `#1001`，可用所属的测试账号验证。 |
| 订座与堂食 | 顾客自行选桌。真实桌位、预订冲突、签到、订单创建及付款等组员确认后再接，界面继续使用本地演示数据。真实菜价及售罄也在接口确认后对齐。 |
| 配送 | 保留 **Coming soon**。先确认取餐或配送方式、营业时间和范围，再确定是否需要配送下单入口。 |

## 路由协作

已有路由优先复用。缺路由时，前端负责建立已对齐的 Flask 路由入口并完成页面联调。纯渲染的 GET 可以由前端完成。涉及业务查询的 GET，以及预订、下单等 POST，前端负责表单和页面状态，后端与数据库同学负责权限、业务校验、查询、事务及写入。接口尚未实现时在交接中注明，联调完成后再标为已接通。

新增或变更路由时及时同步后端同学，写清方法、路径、用途、请求字段、预期响应或跳转，以及是否需要后端或数据库工作。本轮 My account 使用已有的 `/` 和 `/auth/*`，没有新增 Flask 路由。

## 旧前端删除清单

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
