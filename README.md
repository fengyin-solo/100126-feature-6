# 冷链物流运输管理平台

面向冷链运输全程温控、车辆调度、门到门配送、温度异常处置、签收回单与运力结算的冷链运输管理后台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 车辆档案 | `fleet` | 冷链车 | 车辆编号、车牌号码、车型类别 |
| 司机管理 | `driver` | 驾驶员 | 驾驶员编号、驾驶员姓名、驾驶证号 |
| 运输委托 | `order` | 运输委托单 | 委托编号、委托方、起运地址 |
| 运力调度 | `dispatch3` | 调度任务 | 调度编号、关联委托、指派车辆 |
| 温控监测 | `temp` | 温度记录 | 记录编号、关联调度、温区编号 |
| 门到门配送 | `door` | 配送任务 | 任务编号、关联调度、配送站点 |
| 回单管理 | `returntrip` | 回执单 | 回单编号、关联任务、签收方 |
| 异常处置 | `abnormal2` | 异常记录 | 异常编号、异常类型、关联任务 |
| 续运中转 | `renew` | 中转记录 | 中转编号、关联任务、中转站点 |
| 制冷机组 | `refriger` | 制冷机组 | 机组编号、所属车辆、机组型号 |
| 温控箱体 | `box` | 温控箱体 | 箱体编号、箱体类型、内部容积 |
| 运输路线 | `route` | 路线方案 | 路线编号、出发地、目的地 |
| 温感器管理 | `sensor` | 温度传感器 | 传感器编号、所属车辆、传感器型号 |
| 运输费用 | `cost` | 费用记录 | 费用编号、关联任务、费用类别 |
| 委托方管理 | `client2` | 委托方 | 委托方编号、委托方名称、企业类别 |
| 出车检查 | `checkin` | 检查记录 | 检查编号、检查车辆、检查日期 |
| 事故记录 | `accident` | 事故记录 | 事故编号、关联任务、事故类型 |
| 途中核查 | `roadcheck` | 途中核查 | 核查编号、关联调度、核查时间 |
| 车厢清洗 | `clean2` | 清洗记录 | 清洗编号、清洗车辆、清洗方式 |
| 合作合同 | `contract2` | 运输合同 | 合同编号、签约双方、合同类型 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

### 温控监测超限处置状态流

温控监测（`temp`）已从单纯的温度登记补成完整的处置状态机：

```text
在控 ──实际温度偏离设定温度超过阈值并指派处置人员──▶ 预警
预警 ──挂起──▶ 挂起中 ──恢复处置──▶ 预警（继续派给原处置人员）
预警 ──处置完成（处置措施必填）──▶ 已处置
已处置 ──调度退回（调度身份 + 退回原因）──▶ 预警（温区编号、记录时间保持不变）
```

- 偏离阈值默认 2℃，按 `|实际温度-设定温度|` 判定；登记时已超限的记录必须当场
  指派处置人员，否则不予入库。
- 显示状态由后端 `TempService` 统一计算（`display_status` 同时写入「温度状态」列），
  监测列表页与预警弹窗取同一份口径，不会出现两处状态不一致。
- 每一步动作都写入 `history`（动作、操作人、备注、操作时间），交班后接手人可在
  预警弹窗看到上一步的时间与备注。
- 业务规则回归测试：`cd backend && PYTHONPATH=. python -m unittest discover -s tests`。
