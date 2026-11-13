# Usurpers

COMP3019J 小组餐厅网站项目（Topic 2 — Restaurant Booking and Ordering Website）。

「双份」前端由 Flask 提供：页面在 [`restaurant/templates/customer/`](restaurant/templates/customer/)，样式、脚本和素材在 [`restaurant/static/`](restaurant/static/)。

## 本地运行

在仓库根目录执行：

```bash
python -m pip install Flask
python app.py
```

浏览器打开 <http://127.0.0.1:5000/>；摄影相册位于 <http://127.0.0.1:5000/album>。页面和登录接口使用同一个 Flask 服务，无需另外启动静态文件服务器。

账号登录和注册使用 SQLite。菜单、订座和下单仍是前端演示。详细功能、素材来源和演示边界见 [前端说明](restaurant/README.md)。

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
