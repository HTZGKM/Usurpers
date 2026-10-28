# Usurpers

COMP3019J 小组餐厅网站项目（Topic 2 — Restaurant Booking and Ordering Website）。

当前可运行的「双份」前端原型在 [`prototype/`](prototype/)：中文界面、桌面优先，使用 HTML、CSS 和 JavaScript。

## 本地运行

在仓库根目录执行：

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory prototype
```

浏览器打开 <http://127.0.0.1:8765/>。详细功能、素材来源和演示边界见 [原型说明](prototype/README.md)。

后续计划接入 Flask/Jinja；当前版本没有后端、真实订单或真实预订服务。

## SQLite 初始化

项目已补充最小可运行的 SQLite 初始化脚本。首次执行会自动创建 `restaurant/data/shuangfen.db`，并写入默认员工、顾客、餐桌、菜品、订单和订单明细。

在仓库根目录执行：

```bash
python -m restaurant.db
```

这条命令默认是“有库就复用、没库才创建”，不会覆盖现有 `.db`。

如果要强制删除旧库并重新生成一份干净的数据库，执行：

```bash
python -m restaurant.db --reset
```

初始化完成后会在终端输出各张表的记录数。默认种子账号的原始密码都是 `123456`，数据库中保存的是 SHA-256 哈希值。
