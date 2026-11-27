# Double Portion 应用目录

`application.py` 创建 Flask 应用并注册蓝图，根目录 `app.py` 提供启动入口。部署、本地启动和回归命令见 [仓库说明](../README.md)。

| 目录或文件 | 职责 |
| --- | --- |
| `api/` | 各角色接口与表单；`reservation_routes.py` 提供 PostgreSQL 预约流程 |
| `services/` | 业务规则、事务、会话与提交重试 |
| `db/` | SQLite 本地运行支持、PostgreSQL 连接、表结构与迁移 |
| `presentation.py` | 首页菜单、桌位与到店记录的模板数据 |
| `templates/`、`static/` | Jinja、JavaScript、CSS、图片与字体 |
| `scheduler.py` | 独立任务入口；不会随 Web 应用启动常驻 worker |

正式站使用 Vercel 和 Neon PostgreSQL。未配置 `DATABASE_URL` 时使用本地 SQLite；两种环境的预约流程并不完全相同。正式预约与并发行为需要隔离 PostgreSQL 验证。

菜名、价格、供应状态和业务记录来自数据库。`api/customer/catalog.json` 补充菜品照片与描述；浏览器保存未提交的草稿。

页面维护入口：[顾客](templates/customer/README.md)、[前台](templates/frontdesk/README.md)、[厨房](templates/kitchen/README.md)、[主管](templates/admin/README.md)。
