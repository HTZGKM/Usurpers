# 双份 · 餐厅前端

Flask 在 `/` 渲染 Double Portion 的英文界面。页面和登录接口由同一个 Flask 服务提供。

## 启动

在 `Usurpers` 根目录按 [仓库启动说明](../README.md#本地启动) 安装和启动，再打开 [餐厅首页](http://127.0.0.1:5000/)。页面验收见 [顾客端交接](templates/customer/README.md)。

## 文件结构

| 路径 | 用途 |
| --- | --- |
| `templates/customer/` | 当前顾客端 Jinja 模板、设计简报和交接 |
| `templates/frontdesk/`、`templates/kitchen/`、`templates/admin/` | 各角色工作台模板和接口交接 |
| `static/css/guest.css`、`static/css/guest-type.css` | 页面样式和字体 |
| `static/js/guest.js`、`static/js/guest-motion.js` | 页面交互和切页动效 |
| `static/images/atelier/` | 当前页面、菜单和后续编辑内容使用的照片 |
| `api/customer/catalog.json` | 菜品照片和描述。实际菜名、价格和供应状态来自 SQLite。 |

## 数据和后续页面

账号登录、注册和退出使用 Flask-WTF 与 SQLite。顾客的预约和已提交订单与 [前台](templates/frontdesk/README.md)、[厨房](templates/kitchen/README.md) 及 [主管](templates/admin/README.md) 工作台共用 `restaurant/data/shuangfen.db`。未提交的购物袋保存在当前标签页。

旧前端移除的路由和文件见[删除清单](templates/customer/README.md#旧前端删除清单)。
