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
