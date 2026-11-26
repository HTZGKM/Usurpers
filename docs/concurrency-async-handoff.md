# Double Portion 并发与异步修复交接

本轮处理会造成重复下单、旧页面覆盖、预点单悬挂或桌位分配异常的场景。面向顾客、前台、厨房和主管四个角色。代码链接固定到应用提交 [`7a72cb4`](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/README.md)，便于之后对照。

## 预点单与订单

| 组员可能遇到的情况 | 现在的处理 | 验收结果与代码 |
| --- | --- | --- |
| 顾客已预点单，但超过最晚报到时间仍未到店 | 制作时间由预约生成。到期释放预约时，同一事务取消该笔未入座、未付款且尚未制作的预点单。顾客单独刷新订单也会检查自己的到期预约。 | 隔离 PostgreSQL 中，19:10 整仍可报到，19:10:01 未到订单转取消。提交比预约晚的制作时间，服务器仍按预约时间记录。迁移重复运行也只处理符合条件的旧记录。 [逾时处理](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/services/allocation.py#L193) · [顾客刷新](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/services/allocation.py#L840) · [测试](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/tests/test_reservation_rebuild.py#L119) |
| 已经下单，页面没收到成功结果，顾客或前台再次提交 | 每次下单带提交编号。重试同一份内容直接返回原订单。原结果未确认时，页面会询问是否先恢复原提交，并保留用户后来改动的草稿。明确加一单时使用新编号。 | 两个独立请求使用同一编号，返回同一个订单号，数据库只有一份厨房明细。同编号内容不同会返回 409。浏览器测试还检查了丢响应后恢复原请求。 [请求记录](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/services/submission.py#L12) · [下单](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/services/order_service.py#L40) · [页面恢复](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/static/js/restaurant-api.js#L63) · [并发测试](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/tests/test_reservation_rebuild.py#L371) |
| 前台改数量时厨房点了开工，或顾客和前台都在编辑 | 改单和厨房开工都提交读取时的订单版本。前台先保存时，厨房旧卡片会要求刷新。厨房先开工时，旧改单会被拒绝。改单草稿保留，可先加载最新订单再人工核对。订单详情、菜品和总价在同一读取事务中返回。 | 两个请求同时发起，只允许一方成功。厨房刷新后看到已保存的新数量。重复开工不会生成第二条制作记录。 [订单编辑](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/services/order_service.py#L238) · [厨房变更](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/services/kitchen_service.py#L45) · [前端草稿](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/static/js/restaurant-api.js#L136) · [并发测试](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/tests/test_reservation_rebuild.py#L371) |
| 主管改价，顾客或前台仍打开旧菜单 | 订单提交核对页面显示的单价与当前售价。价格变化后显示新金额，用户确认后再提交。售罄时保留草稿，提示移除该菜。改单保留原有菜品的成交价，新加的菜按当前已确认价格。后端同时限制份数、明细条数和总价。 | 旧价返回 409，超过每行 99 份返回 400，两种失败都没有新增订单。 [单价校验](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/services/order_service.py#L23) · [输入边界](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/services/common.py#L54) · [测试](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/tests/test_service_api.py#L131) |
| 前台代订或主管调整库存时断网后重试 | 当前页面沿用提交编号和原结果恢复。两次确认为不同操作时会得到不同编号。 | 办理路径与请求记录共用同一事务。团队操作验收可从前台 **New booking** 和主管 **Inventory** 重试同一笔提交。 [前台代订](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/services/allocation.py#L333) · [库存调整](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/services/inventory_service.py#L9) |

## 桌位和等位

| 情况 | 验收结果与代码 |
| --- | --- |
| 10 人或 20 人抢同一张桌 | 隔离 PostgreSQL 中，分别是 **1 成功、9 冲突**和 **1 成功、19 冲突**，数据库各只留一份有效保护。选同一桌不同到店时间但保护区间重叠会冲突。两张不同的桌可同时订到。 [抢桌测试](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/tests/test_reservation_rebuild.py#L215) · [不同桌测试](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/tests/test_reservation_rebuild.py#L236) |
| 等位票入座、取消、过号或超时相撞 | 已跑取消先赢、入座先赢、精确截止、入座写入失败回滚等用例。只有赢的一方留下有效状态，失败一方不会留下多余堂食或占桌。 [新版等位转换](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/services/allocation.py#L624) · [竞争测试](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/tests/test_postgres_booking_consistency.py#L190) |
| 关桌成功后，清台到期的处理请求中断 | 模拟清台释放与叫号之间的异常，两项在同一事务回滚。创建新应用实例并再次查询后，清台与叫号一起完成，重复查询只保留一份叫号留桌。正式站的恢复由前台打开页面、轮询或业务请求触发。独立定时 worker 的持续运行属于部署配置。 [清台事务](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/services/allocation.py#L204) · [恢复测试](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/tests/test_reservation_rebuild.py#L326) · [调度入口](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/scheduler.py#L15) |
| 排队等锁和业务抢桌冲突 | 保留同一写锁，默认最长等锁 3 秒。受控等锁超时走 503 `DATABASE_BUSY`，桌位冲突走 409 `TABLE_UNAVAILABLE`。本地 PostgreSQL 验收结果用于判断正确性，生产吞吐量应另行监测。前台桌况标题标明显示当前桌况，预约依日期筛选。 [锁设置](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/db/database.py#L145) · [锁验证](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/tests/test_postgres_booking_consistency.py#L164) |

## 主管加菜和改价

登录主管账号后进入 **Dishes**。

- 点 **New dish**，填菜名、分类、价格和菜品资料后保存。
- 点现有菜品，在右侧修改 **Price (¥)**，再点 **Save changes**。顾客刷新菜单后可看到新价。旧订单继续按下单时的单价显示。
- 厨房通过 **Availability** 管理供应状态，主管通过 **Dishes** 管理菜品资料和价格。

[主管菜品表单](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/static/js/admin.js#L1106) · [主管新增与修改接口](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/api/admin/routes.py#L164)

## 发布与复测

本轮 80 项 Python 测试和 25 项 JavaScript 测试全部通过。Python 回归覆盖临时 SQLite 和仅监听本机的 PostgreSQL 17。正式环境先应用 [数据库迁移 003](https://github.com/HTZGKM/Usurpers/blob/7a72cb4fd19abc8b760d7d3ad58aefd6ba86f65f/restaurant/db/migrations/003_order_consistency.sql#L1)，再部署应用。迁移会增加订单版本和提交记录，清理已有的逾时预点单，保留订单与菜品历史。

正式站用于核对版本、迁移状态和角色入口。多人抢桌、故障注入和写入竞争在隔离库执行。组员可从 [Double Portion 正式站](https://doubleportion-usurpers.vercel.app) 开始演练。
