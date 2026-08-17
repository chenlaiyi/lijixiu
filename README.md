# 立即修平台

上门维修 O2O 平台 — **单小程序多角色** + H5 + 管理后台,后端 FastAPI。

> 当前阶段:**微信小程序提审前的最后一轮冲刺**(7/22 完成全链路 + 合规修正)。
> 详见 [docs/progress.md](docs/progress.md) 与 [docs/wechat-review-guide.md](docs/wechat-review-guide.md)。

---

## 技术栈

| 端 | 技术 |
|---|---|
| 后端 | Python 3.11+ · FastAPI 0.115 · SQLAlchemy 2.0(async) · aiosqlite · Pydantic 2 · uvicorn |
| 小程序 | 原生微信小程序(基础库 3.6.0)· AppID `wx2273201e59e280bc` |
| H5 / Admin | 静态资源,挂载在 FastAPI 同源 |
| 数据库 | SQLite(`xiulijiu.db`,生产同样) |
| 支付 | 微信支付 V3 + 商户转账(提现) |

---

## 目录结构

```
xiulijiu/
├── app/                       # FastAPI 后端
│   ├── main.py                # 入口(lifespan + 路由挂载)
│   ├── core/                  # config / database / middleware
│   ├── models/                # SQLAlchemy 模型(18 张表)
│   ├── routers/               # 13 个 API 路由模块
│   ├── schemas/               # Pydantic schema
│   └── services/              # 业务服务层(22 个)
├── miniprogram/               # 微信小程序
│   ├── app.js / app.json      # 单 App 多角色入口
│   ├── pages/                 # 30 个页面(7 大角色)
│   ├── components/            # 自定义组件(角色 tabbar)
│   └── utils/                 # API 封装
├── h5/                        # H5 工作台 → 挂载在 /h5
├── admin-web/                 # 管理后台 → 挂载在 /admin
├── scripts/                   # 工具脚本
│   ├── seed_demo_data.py      # 线上 demo 数据种子
│   ├── test_platform_flows.py # 平台全链路测试
│   ├── check_wechat_pay.py    # 微信支付配置检查
│   └── *_wechat_*.ps1         # 微信密钥/证书部署脚本
├── docs/                      # 项目文档
│   ├── progress.md            # 开发进度
│   ├── wechat-review-guide.md # 微信审核说明
│   └── design-qa.md           # 设计稿对位 QA
├── cert/                      # 微信支付证书(本地)
├── uploads/                   # 用户上传文件
├── design/                    # 设计稿参考图
├── .env.example               # 环境变量模板
├── requirements.txt           # Python 依赖
├── package.json               # miniprogram-ci(小程序上传)
└── upload.js                  # 小程序 CI 上传脚本
```

---

## 快速启动

### 1. 后端

```powershell
# 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt

# 复制环境变量模板
Copy-Item .env.example .env
# 按需修改 .env(微信支付密钥、审核账号等)

# 启动
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动后可访问:
- API Swagger:http://localhost:8000/docs
- H5:http://localhost:8000/h5/
- Admin:http://localhost:8000/admin/
- 健康检查:http://localhost:8000/health
- 指标:http://localhost:8000/metrics

### 2. 小程序

用**微信开发者工具**打开 `miniprogram/` 目录,导入时使用 AppID `wx2273201e59e280bc`。
在工具中"工具 → 构建 npm"如果首次打开提示,运行一次即可。

### 3. H5 / Admin

随 FastAPI 一起启动即可,无需额外步骤。

---

## 角色与页面

| 角色 | 入口页面 | 备注 |
|---|---|---|
| 客户 | `pages/customer/home/home` | 报修 / 订单 / 支付 / 保修 / 家政 |
| 师傅 | `pages/repairer/jobs/jobs` | 接单 / 服务单 / 收益提现 |
| 店长 | `pages/store/dashboard/dashboard` | 门店 dashboard + 工资单 |
| 城市经理 | `pages/city/dashboard/dashboard` | 区域 dashboard |
| 推广经理 | `pages/promotion/dashboard/dashboard` | 推广 dashboard |
| 二接经理 | `pages/second/dashboard/dashboard` | 二接 dashboard |
| 员工(代客) | `pages/staff/proxy-order/proxy-order` | 代下单 |
| 客服 | `pages/support/dashboard/dashboard` | 工单 dashboard |
| 财务 | `pages/finance/dashboard/dashboard` | 财务 dashboard |
| 总管理 | `pages/admin/dashboard/dashboard` | 全局 dashboard |
| 代理 | `pages/proxy/access/access` | 代理接入 |

单 App 多角色,登录后根据 `user.business_role` 自动跳转到对应首页。

---

## Demo 账号(由 `scripts/seed_demo_data.py` 生成)

| 角色 | 手机号 | 名称 |
|---|---|---|
| 总管理 | 18800000000 | 演示管理员 |
| 客户 | 18800000001 | 演示客户 |
| 师傅 | 18800000002 | 演示师傅张工 |
| 二接师傅 | 18800000003 | 演示二接师傅李工 |
| 店长 | 18800000004 | 演示门店店长 |
| 城市经理 | 18800000005 | 演示城市经理 |
| 推广经理 | 18800000006 | 演示推广经理 |
| 服务保障 | 18800000007 | 演示服务保障 |
| 财务 | 18800000008 | 演示财务 |

后台登录使用 `POST /api/v1/auth/wechat-login`,body `{ "code": "18800000001:演示客户:customer" }`
(在 `SMS_PROVIDER=debug` 模式下,验证码固定为 `246810`)。

---

## 微信审核相关

- **审核账号**:`reviewer` / 密码配置在 `.env` 的 `WECHAT_REVIEW_PASSWORD`(账号密码登录入口)
- **审核手机号**:`18800000999`
- **审核路径**:首屏 → "体验完整功能" → 直接进入师傅"收益"页 → 输入 1.00 元 → 申请提现
- **合规修正**(7/22 完成):登录页去除"微信"字样 / 图标改为电话听筒 / 文案改为"手机号快捷登录"

详见 [docs/wechat-review-guide.md](docs/wechat-review-guide.md)。

---

## 常用脚本

```powershell
# 生成 demo 数据(对线上 https://x.iddg.cn)
python scripts/seed_demo_data.py https://x.iddg.cn

# 跑全链路测试(独立临时数据库,不影响主库)
python scripts/test_platform_flows.py

# 微信支付配置检查
python scripts/check_wechat_pay.py

# 部署微信支付密钥/证书
pwsh scripts/set_wechat_runtime_config.ps1
```

---

## 小程序 CI 上传

```powershell
# 一次性安装
npm install

# 上传体验版(需要 miniprogram-ci 私钥)
$env:VERSION = "1.0.220"
$env:DESC = "立即修 v1.0.220"
$env:WX_PRIVATE_KEY_PATH = "D:/private.wx2273201e59e280bc.key"
npm run upload
```

---

## 关键设计取舍

- **SQLite 用于生产** — 简化部署;`alembic` 已装但当前用 `init_db` 自动建表,后续上 MySQL/PG 时切到迁移
- **PAYMENT_ALLOW_MOCK** — 本地调试用 mock 支付,生产必须 `false`
- **WECHAT_WITHDRAW_AUTO_TRANSFER** — 提现走商户转账;false 时只生成申请,人工处理
- **request_id 中间件** — 所有请求带 X-Request-ID,便于排障

---

## 当前进度与阻塞

✅ 已完成:后端 API 体系 / 30 个小程序页面 / 微信支付 V3 / H5+Admin 挂载 / 全链路测试 / demo 种子
🔧 进行中:微信审核合规回归
🚧 阻塞:**设计稿对位验证**(P1)— 详见 [docs/design-qa.md](docs/design-qa.md),需微信开发者工具登录后截图

---

## 文档索引

- [docs/progress.md](docs/progress.md) — 阶段性开发进度
- [docs/wechat-review-guide.md](docs/wechat-review-guide.md) — 微信小程序审核说明
- [docs/design-qa.md](docs/design-qa.md) — 设计稿对位 QA(目前阻塞)
- [docs/test-report.md](docs/test-report.md) — 全链路测试报告(6/6 ✅)
- [docs/review-audit.md](docs/review-audit.md) — 微信提审前核对报告(13/13 ✅)
- [docs/monitoring.md](docs/monitoring.md) — 监控告警接入指南
- [docs/security-audit.md](docs/security-audit.md) — 安全头审计基线
- [docs/ci.md](docs/ci.md) — CI/CD 接入指南
- [docs/logging.md](docs/logging.md) — 结构化日志接入
- [docs/legal/README.md](docs/legal/README.md) — 法务材料接入(用户协议 / 隐私政策 / ICP 备案)
- [docs/production-readiness.md](docs/production-readiness.md) — 商用就绪体检报告
- [docs/alerts-fix-plan.md](docs/alerts-fix-plan.md) — 告警修复方案与 bug 根因
- [deploy/README.md](deploy/README.md) — 部署指南(Docker / nginx / SSL)
- [API 文档(Swagger)](https://x.iddg.cn/docs) — 线上 API 自动文档
