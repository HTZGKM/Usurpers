# 双份 · 餐厅前端

Flask 在 `/` 渲染 Double Portion 的英文界面。页面和登录接口由同一个 Flask 服务提供。

## 启动

在仓库根目录运行：

```bash
python -m pip install Flask Flask-WTF
python app.py
```

浏览器打开 <http://127.0.0.1:5000/>。开发预览与验收步骤见 [顾客端交接](templates/customer/README.md)。

## 文件结构

| 路径 | 用途 |
| --- | --- |
| `templates/customer/` | 当前顾客端 Jinja 模板、设计简报和交接 |
| `templates/frontdesk/`、`templates/kitchen/`、`templates/admin/` | 各角色工作台模板和接口交接 |
| `static/css/guest.css`、`static/css/guest-type.css` | 页面样式和字体 |
| `static/js/guest.js`、`static/js/guest-lens.js` | 页面交互和导航动效 |
| `static/images/atelier/` | 当前页面、菜单和后续编辑内容使用的照片 |
| `api/customer/catalog.json` | 14 道演示菜品 |

## 数据和后续页面

账号登录、注册和退出使用 Flask-WTF 与 SQLite。顾客业务使用当前标签页内的演示数据。员工从相同的登录表单进入 `/#workspace`，按角色显示 [前台](templates/frontdesk/README.md)、[厨房](templates/kitchen/README.md) 或 [主管理员](templates/admin/README.md) 工作台。三类员工页面共享本标签页的演示业务状态，正式业务接口待联调。顾客端其余内容见[设计简报](templates/customer/FRONTEND_BRIEF.md)。

旧前端移除的路由和文件见[删除清单](templates/customer/README.md#旧前端删除清单)。
