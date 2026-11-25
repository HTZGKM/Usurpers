# Usurpers

COMP3019J 小组餐厅网站项目（Topic 2 — Restaurant Booking and Ordering Website）。

「双份」前端由 Flask 提供：页面在 [`restaurant/templates/customer/`](restaurant/templates/customer/)，样式、脚本和素材在 [`restaurant/static/`](restaurant/static/)。

顾客端的新对话请先读 [顾客前端交接与验收路径](restaurant/templates/customer/README.md)。当前首页由 Jinja 渲染，预览、修改和提交均以本仓库为准。

## 本地启动

在包含 `app.py` 的 `Usurpers` 目录执行。使用 Python 3.12，Windows 可先运行 `python --version` 核对版本。首次启动先在该目录创建虚拟环境并安装依赖。

Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

macOS / Linux

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

后续启动时执行最后一行即可。终端显示 Flask 正在运行后，打开 [餐厅首页](http://127.0.0.1:5000/)。服务直接使用 `restaurant/data/shuangfen.db`，首次运行自动建表并写入初始数据，后续继续使用这个文件。四个角色共用此库。

顾客、前台、厨房和主管可以走通选桌预约、签到、下单、制作、上菜、记账付款和关桌。顾客的未提交购物袋保存在当前标签页。

### 顾客账号联调

1. 打开 `/#account`，选择 **Register**，使用新的 11 位测试手机号注册。
2. 在 **Sign in** 先输入错误密码检查提示，再用正确密码登录。刷新页面，访问 `/auth/me` 可看到当前顾客。
3. 在账户页点击 **Sign out**，再次访问 `/auth/me` 应返回 HTTP 401。也可以从 `/auth/register` 和 `/auth/login` 直接测试原生 Jinja 表单。

### 堂食联调

1. 顾客在 **Book a table** 选时段和桌位，或在 **Your visit** 取等位号。已有预约时，可把购物袋作为预点单提交。
2. 前台在 **Reservations** 确认到店，或在 **Walk-in waitlist** 叫号和安排入座。顾客刷新 **Your visit** 后可以提交堂食订单。预点单在签到且到预约时间后进入厨房。未开始制作且未结账的订单可以改单或取消。
3. 厨房在 **Queue** 开始制作并标记 **Ready**。前台在 **Table service** 标记上菜，可提前记录付款。所有订单结清、所有菜已上菜或取消后，才可释放桌位。主管在 **Overview** 或 **Orders** 查看同一笔订单。
4. 主管在 **Inventory** 新增食材、手动调整库存和保存配方，在 **Accounts** 管理员工及顾客账号。

需要并行登录不同角色时，可用独立浏览器配置或无痕窗口分开保存 Flask 会话。

### 队友操作速查

从首页左上角菜单进入 **My account → Sign in**。下列本地演示账号的密码均为 `123456`。员工登录后自动进入各自的工作台。

| 角色 | 演示账号 | 操作 |
| --- | --- | --- |
| 顾客 | `13900000001` 测预约或等位；`13900000002` 初始已入座 A2，可直接看订单 | **Book a table** 预约、改约或取消；**Your visit** 取号、查叫号和取消等位；**Menu** 把菜加入购物袋。有预约可预点菜，入座后可下单，或展开订单查看、修改和取消未开做且未付款的订单。 |
| 前台 | `frontdesk@shuangfen.local` | **Reservations** 代订和签到；**Walk-in waitlist** 选桌、叫号和入座；**Table service** 代客下单、改单、点 **Mark served**、记录付款及放桌；**Billing records** 查账单。 |
| 厨房 | `kitchen@shuangfen.local` | **Queue** 按订单查看菜和备注，依次点 **Start preparation → Mark ready**；由前台确认上菜。**Availability** 可更新菜品是否供应。 |
| 主管 | `admin@shuangfen.local` | **Overview / Orders** 查营业数据和订单；**Tables / Kitchen queue** 查桌况和出餐；**Dishes** 管菜品；**Inventory** 管食材、配方和手动库存；**Accounts** 管账号。 |

## 启动排错

- 若找不到 `app.py`，先切到里面的 `Usurpers` 目录。
- 若提示 5000 端口已占用，先检查该地址是否已经打开本项目。需要重新启动时，先在原来启动项目的终端按 `Ctrl+C`。
- 若提示 `The SQLite database uses the old schema`，说明本机留有早期版本创建的 `restaurant/data/shuangfen.db`。这个文件不随 Git 提交，新克隆不需要处理。若要用新版初始数据，先关闭 Flask 和所有使用该库的 SQLite 工具，再将旧库及可能存在的同名 `-wal`、`-shm`、`-journal` 文件一起移到仓库外备份。重新运行上面的启动命令，新库会在默认路径自动生成。旧记录仍在备份里，新库不会自动导入它们。
- 若 PowerShell 中曾手动设置 `USURPERS_DB_PATH`，运行 `Remove-Item Env:USURPERS_DB_PATH` 清除当前终端的覆盖设置，再按默认方式启动。

公开部署使用 HTTPS，并设置 `USURPERS_HTTPS=1` 和私有的 `USURPERS_SECRET_KEY`。配置后的会话 Cookie 使用 Secure、HttpOnly 和 SameSite=Lax。前端和接口以同源方式运行。

## Vercel 部署

Vercel 从根目录导入 `app.py` 中的 Flask 应用。项目的 Production 环境需要配置 `DATABASE_URL`、`USURPERS_SECRET_KEY` 和 `USURPERS_HTTPS=1`。`DATABASE_URL` 使用 Neon 的 PostgreSQL 连接串。`vercel.json` 中的构建步骤会把样式、脚本、字体和图片发布到原有的 `/static/` 地址。

首次上线前，从有原 SQLite 数据的电脑将数据导入一个空的 PostgreSQL 库。先在本机终端设置目标 `DATABASE_URL`，再运行以下命令。启动 Flask 和更新页面时直接使用已准备好的云数据库。

```powershell
.\.venv\Scripts\python.exe -m restaurant.db.migrate --source restaurant/data/shuangfen.db --credentials-file ..\local-runtime\vercel-accounts.tsv
```

迁移会只读打开源库并保留记录 ID。仍在使用公开演示密码的账号会在目标库获得新密码，登录信息只写到上面指定的本机文件。导入命令会拒绝已有业务数据的目标库。

在已连接 Vercel 项目的目录中发布组员要测试的版本时，运行 `vercel deploy --prod`。部署成功后继续分享该项目的公开网址。更新前后端代码用日常 Git 分支和 PR 流程。修改表结构时单独执行对应的数据库迁移。

已有 PostgreSQL 库升级到预约版本号和提交恢复功能前，先执行 `restaurant/db/migrations/001_booking_consistency.sql`，再发布应用。迁移可重复执行，保留已有预约。
