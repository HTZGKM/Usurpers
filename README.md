# Double Portion 双份

Usurpers 团队的 COMP3019J 课程项目 · Topic 2 — Restaurant Booking and Ordering Website

Double Portion 是一个单店餐厅预约与点餐系统。顾客、前台、厨房和主管共享预约、堂食与订单记录，从订桌到关桌可以在正式站走完一轮。

## 使用正式站

[打开 Double Portion](https://doubleportion-usurpers.vercel.app/) · [检查服务状态](https://doubleportion-usurpers.vercel.app/health)

顾客可浏览菜单，从 **My account** 注册或登录。员工使用小组提供的账号登录，进入对应工作台。同时演示多个角色时，请用独立的浏览器配置文件，避免标签页共用登录会话。

| 角色 | 主要操作 |
| --- | --- |
| 顾客 | 在 **Book a table** 选日期、人数、到店时间和桌位，可改约或取消。确认预约后可预点单，在 **Your visit** 查看入座进度、订单和本次桌账。 |
| 前台 | 在 **Reservations** 代订、登记到店、确认备桌和安排入座。现场客人由前台取号、叫号及安排入座。在 **Table service** 代客加单、确认上菜、记录付款和关桌。 |
| 厨房 | 在 **Queue** 分别处理待制作、制作中和待上菜的菜品。在 **Availability** 更新售罄和供应状态。 |
| 主管 | 在 **Orders** 查当天和历史订单，在 **Tables** 查桌况、时间轴和日历。在 **Dishes** 新增菜品或改价，也可管理库存和账号。 |

## 堂食演示流程

1. 顾客线上订桌并预点单。
2. 前台在预约签到窗口内登记到店，确认备桌后安排入座。
3. 顾客实际入座且已到制作时间，预点单才进入厨房。厨房按菜品标记开始制作和备妥，前台确认上菜。
4. 顾客核对本次桌账并记录模拟付款。前台处理完所有菜品和账单后关桌，主管可以按桌号和订单查看本次记录。

线上预约使用北京时间，以 15 分钟为到店时间间隔，至少提前 30 分钟。预约宽限为 10 分钟，现场叫号保留 1 分钟。

## 正式部署与维护

- **Vercel** 托管 Flask 和 Jinja 应用。GitHub `main` 是正式发布分支，PR 合并后由 Vercel 构建和部署。
- **Neon PostgreSQL** 保存预约、等位、堂食、订单、菜单和库存。正式环境在 Vercel 配置 `DATABASE_URL`、`USURPERS_SECRET_KEY` 和 `USURPERS_HTTPS=1`。
- 数据库结构变更通过 [增量迁移](restaurant/db/migrations/) 单独应用。当前正式库已应用菜品版本迁移 [004](restaurant/db/migrations/004_dish_versions.sql)。发布前根据变更核对 PR 检查、迁移及合并顺序，发布后检查正式站。

并发处理和验收证据见 [组员交接记录](docs/concurrency-async-handoff.md) 和 [最新接口修复 PR](https://github.com/HTZGKM/Usurpers/pull/33)。
