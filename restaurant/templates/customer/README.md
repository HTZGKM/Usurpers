# 顾客端维护说明

顾客入口为 `/`，界面文案使用英文。启动与测试见 [仓库说明](../../../README.md)。

## 文件索引

| 内容 | 文件 |
| --- | --- |
| 首页上下文 | `restaurant/application.py`、`restaurant/presentation.py` |
| 页面组合与导航 | `guest.html`、`_guest_parts.html` |
| 菜单与详情 | `_guest_menu.html`、`_guest_dish.html`、`restaurant/api/customer/catalog.json` |
| 预约、账户、内容页 | `_guest_reservation.html`、`_guest_account.html`、`_guest_delivery.html`、`_guest_journal*.html` |
| 布局、字体与视觉 | `restaurant/static/css/guest.css`、`guest-type.css`、`guest-ember.css` |
| 交互 | `restaurant/static/js/guest.js`、`guest-calendar.js`、`guest-meal.js`、`guest-lens.js`、`guest-motion.js` |
| 共用请求、重试与改单 | `restaurant/static/js/restaurant-api.js` |

## 数据与业务边界

正式站通过 Flask 接口读写 Neon PostgreSQL。`catalog.json` 提供照片与描述，实际菜名、价格和供应状态以数据库为准。购物袋及未提交草稿保存在浏览器，已提交记录由后端管理。

- 正式预约走 `/reservation-api`；前台办理到店、备桌和入座。预点单只有实际入座且到达制作时间后才进入厨房。
- 顾客查看自己的预约、订单和本次桌账。改单与取消受付款、制作状态和版本校验限制。
- 提交编号支持丢响应后的原请求恢复；版本冲突时保留输入并核对最新记录。价格变动需重新确认。
- 页面自动刷新；`POST /operations/refresh` 推进当前顾客相关期限，查询接口保持只读。
- 付款为模拟记账。Delivery 仍为 Coming soon；数量与备注不等于已实现付费规格或加料。
- 本地 SQLite 流程不能代替正式预约与并发验收。

## 页面验收

检查匿名浏览和登录后返回、订座及改约失败、购物袋与订单恢复、厨房备注、到店与制作进度、模拟付款和退出登录。写入与异常场景使用隔离数据库。

检查桌面与窄屏、键盘焦点、Esc、图片加载和减少动态效果。视觉规范与历史设计依据见 [顾客端设计工作流](../../../docs/customer-design-workflow.md)，字体许可见 [字体说明](../../static/fonts/README.md)。
