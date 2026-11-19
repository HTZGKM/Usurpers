# 双份 · 新对话前端设计提示词

请接手课程项目 Usurpers 的餐厅前端。餐厅英文名是 Double Portion，主营汉堡、披萨、小食和饮品。和我用中文交流，交付的页面文案、按钮、提示、错误和空状态都用英文。以现有 Flask + Jinja 前端为起点，先完成顾客，再逐个做前台、厨房、管理员。

## 从这里开始

进入 `F:\web开发项目\2026final_PROJECT\Usurpers`，读根 `README.md` 和 `restaurant/templates/customer/README.md`，检查当前分支及 `git status -sb`、`git diff --cached --stat`。交接时分支是 `feat/yiming-win`，上一次迁移的 20 个文件已暂存，等待提交。保留已有修改，按功能分批提交，确认需要 push 时只推本批内容。

先在当前对话侧边浏览器打开 http://127.0.0.1:18749/ 。若服务未启动，在仓库根运行：

```powershell
.\.venv\Scripts\python.exe -m flask --app app run --debug --no-debugger --port 18749
```

先亲自走一遍已有流程：Home → Book a table → 在平面图选 A2 → Confirm reservation → Preview host check-in → Menu → Pizzas → Margherita × 2 → View bag → Place order → Pay ¥116 · demo → Payment received。再从首页分别进入 My account、Delivery、Journal，确定哪些地方还会进入旧版。每轮直接改仓库里的 Jinja、CSS 和原生 JS，改完在侧边浏览器打开本轮页面，给我能从首页点到的预览。Figma 链接用于看设计参考。

## 我的文件在哪里

以下路径都相对仓库根目录。

| 要改什么 | 文件 |
| --- | --- |
| Flask 入口、首页上下文、桌位坐标和时段 | `app.py`。网页统一从 `/` 进入，员工登录后使用 `/#workspace` |
| 顾客 Jinja | `restaurant/templates/customer/guest.html` 组合各视图；同目录的 `_guest_parts.html` 是首页、导航和封面等共用组件，`_guest_menu.html` 是双栏菜单，`_guest_dish.html` 是菜品弹层，`_guest_reservation.html` 是单页订座和平面图 |
| 菜单与样式 | `restaurant/customer/catalog.json` 管 14 道菜的名称、价格和状态；`restaurant/static/css/guest.css` 管布局与响应式，`guest-type.css` 管字体和字号 |
| 页面与组件交互 | `restaurant/static/js/guest.js` 管跳转、订座、购物袋、订单和模拟付款；同目录 `guest-lens.js` 管导航玻璃动效 |
| 图片、像素素材、字体 | `restaurant/static/images/atelier/editorial/` 是封面与编辑摄影，`catalog/` 是菜单缩略图，`detail/` 有五款高清披萨；`restaurant/assets/kenney_pixel-platformer-food-expansion.zip` 是我放的像素素材；授权的 Web 字体放在 `restaurant/static/fonts/` |
| 当前进度与清理清单 | 见 [顾客端交接](README.md) |
| 登录与业务约定 | `restaurant/templates/auth/form.html`、`restaurant/auth/{routes.py,forms.py}`。各角色的 `restaurant/{customer,frontdesk,kitchen,admin}/{routes.py,forms.py}` 写明已有或计划的操作；先核对蓝图注册与接口实现，再对接 |
| 员工工作台模板 | `restaurant/templates/frontdesk/`、`restaurant/templates/kitchen/`、`restaurant/templates/admin/` 各自包含模板和联调交接 |

旧版独立 HTML、Qitchen 样式参考图、设计稿导出、动效 GIF 和验收截图在 `C:\Users\33653\.codex\visualizations\2026\11\18\01a1ec05-f9ac-7aa3-85af-0287865b11a7`。可看 `qit-Menu.jpg`、`qit-uikit.jpg`、`qrefresh-Delivery.png` 和 `Double Portion - Liquid Glass.gif` 对照设计。后续修改的源文件放在仓库。

## 页面范围和先后顺序

1. **顾客公共页面。** 首页、全屏文字导航和 Menu 已有 Jinja 版本。保留满屏摄影、标题压在照片上、左上角 Logo 与导航、圆角入口，以及首页下滑按整屏进入下一部分的体验。菜单左侧是独立高度的刀叉餐盘主图，右侧是可浏览的长菜单；桌面和窄屏都要能跳到分类、打开菜品、返回原位置。
2. **顾客订座与堂食。** 已有 Book a table、二维选桌、Your Table、菜品详情、购物袋、下单和付款回执的演示流程。在一页中完成日期、人数、时段、选桌、确认、修改和取消。Your Table 集中显示到店、订单和付款状态。检查空购物袋、无预订、售罄、未签到、历史记录、返回与刷新。优先复用同页状态或弹层，避免一个确认动作拆出一张几乎相同的页面。
3. **顾客端现状。** My account 复用现有账号接口。Delivery 已有图片和信息分区，营业时间与范围暂显示 Coming soon。Journal 已有五篇近期正文和独立目录式归档。菜品选项、数量、购物袋改餐和预约及订单历史已完成演示。真实订单读取、订座和堂食业务接口的分工见 [顾客端交接](README.md)。
4. **厨房 Kitchen。** 优先实现。厨房账号登录后显示轻量工作台，包含制作队列、单项完成以及菜单供应状态切换。见 [厨房交接](../kitchen/README.md)。
5. **前台 Front desk。** 演示工作台已覆盖桌位图、预约、签到、散客入座、代客点单、取消单项、上菜、收款和结桌。前台与厨房在同一标签页共享演示订单。后续按 [前台交接](../frontdesk/README.md) 接入业务接口。
6. **管理员 Admin。** 演示 Dashboard 已包含运营概览、订单查询、厨房队列、桌位、账号和菜品管理。见 [管理员交接](../admin/README.md)。正式数据和权限以管理员路由为准。

登录、注册、退出和会话查询已接 Flask-WTF 与 SQLite。新版顾客预订、签到、点菜和付款目前按标签页和身份保存在 sessionStorage。保持演示状态明确，遇到业务接口占位就记录具体缺口，和组员对齐后再接。Payment received 目前代表模拟付款回执。

## 已讨论的参考案例和素材

| 案例 | 我希望你看什么 |
| --- | --- |
| [Qitchen · Restaurant Website Template](https://www.figma.com/design/k70rXmeKFMpb20H0Odvvof/) | **首要视觉依据。** 看 Design、UI Kit、Components。重点是全屏文字导航、紧凑的左上角导航、独立高度双栏菜单、Contact 信息分区、Blog 列表与文章详情 |
| [FoodZero](https://www.figma.com/design/wp4L4gLhfAB9vORVBDGgFg/) | 餐厅首页摄影、留白和标题层级 |
| [Free Restaurant Management Dashboard](https://www.figma.com/design/wJBjVxNANuBzXNFTb5q62v/) | 前台、厨房和管理员工作台的信息层级与操作布局 |
| [Restaurant Website](https://www.figma.com/design/9U6o2wvvuDmrlHctuSW6ii/) | 具体菜品如何展示、如何组织详情 |
| [Food Website UI · Burger Website](https://www.figma.com/design/M6xXFo45zsAfQkMN8Q8vnR/) | 汉堡摄影和单品构图 |
| [Modern Retro Beverage Brand](https://www.figma.com/site/lidNQc4WpVAIoL1PRwPFDn/) | 饮品或品牌细节，次要参考 |
| [24th Pizza and Meatballs · One Page Love 归档](https://onepagelove.com/24th-pizza-and-meatballs) | 全屏照片如何承接标题、按钮和下一屏 |
| [Pizzeria Beddia](https://www.pizzeriabeddia.com/) · [Honest Burgers](https://www.honestburgers.co.uk/) | 前者看订座入口和文案，后者看菜单、预订、点单入口如何区分 |
| [Dishoom](https://www.dishoom.com/) · [字体参考](https://uidiscovery.com/fonts/dishoom) · [Bitstream 字样](https://www.myfonts.com/collections/cheltenham-font-bitstream/) | 标题希望用 Cheltenham BT，有旧报纸、书籍和咖啡馆的气质。现有 CSS 用 Georgia 回退；有授权的 Web 字体后放入 `restaurant/static/fonts/CheltenhamBT-Roman.woff2` |
| [Apple · Liquid Glass](https://developer.apple.com/videos/play/wwdc2025/219/) | 导航悬停、滑到相邻栏目和按下时，有轻微的玻璃透光、水滴凝聚感，同时保留键盘焦点和减少动态效果支持 |
| [OpenResto](https://github.com/karanshukla/openresto#screenshots) · [Kenney Pixel Platformer Food Expansion](https://kenney.nl/assets/pixel-platformer-food-expansion) | 前者参考可订时段，后者就是项目的像素食物素材，适合页尾或少量点缀 |

摄影沿用我确认过的方向：自然中性的色温、克制的饱和度、能看清饼皮和配料纹理的柔光。菜单缩略图保持一致的侧面或轻俯视机位与拍摄距离，至少五种汉堡、五种披萨。披萨接近盘子大小。大图可以俯拍深色大理石餐桌，以侧碟、餐具、亚麻桌布衬托。新增图片时用绘图工具分别生成，详情用高清图，留意裁切、清晰度和重复用图。

**接手后的第一轮**：跑通并预览顾客流程，列出新版、旧版和待接接口的具体位置；优先完成顾客剩余页面中的一个完整入口，建议从 My account 开始。把结果放到当前对话侧边让我实际点，更新交接文档中的完成项和下一项。
