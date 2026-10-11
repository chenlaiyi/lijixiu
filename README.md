# 立即修平台

上门维修 O2O 平台 — **单小程序多角色** + H5 + 管理后台,后端 FastAPI。

> 当前阶段:**多角色已开发完成、待部署**(2026-10-07)。
> 上一轮安全收口(调试短信泄露、71 个写接口零鉴权、可自提权三个 P0,以及分润 500
> 与 `/metrics` 口径)已修复、**已于 2026-10-06 部署到线上**并完成 A1–A8 验收;
> 2026-10-07 的「一个账号多角色」尚未上线。详见
> [docs/security-hardening-2026-10.md](docs/security-hardening-2026-10.md)、
> [docs/multi-role-2026-10.md](docs/multi-role-2026-10.md) 与
> [docs/progress.md](docs/progress.md)。

---

## ⚠️ 部署前必读(2026-10-05 安全收口)

1. **`ALLOW_SMS_DEBUG_ENDPOINT` 生产必须为 `false`**
   `true` + `SMS_PROVIDER=debug` 会让 `POST /api/v1/auth/sms/request` 把固定验证码回显在响应里,
   等于把任意手机号账号交出去(已在线上复现)。
   strict 模式下该组合会被 `scripts/validate_env.py --strict` 判为错误。
2. **管理后台需要管理员 token**
   `/admin/` 的 nginx basic auth 只管静态资源;管理接口还需要
   `Authorization: Bearer <平台管理员 token>`。打开后台首屏会要求粘贴 token。
3. **所有业务接口需要登录**
   全量用户/订单/支付/工资/家政/客服/服务区域等接口已加鉴权,客户端必须带 token;
   客户只能看到自己的数据,内部数据仅平台内部角色可见。
4. 这几条**已于 2026-10-06 部署到线上**(releases `20261006075442` / `20261006075802`),
   验收项 A1–A8 全部通过;仍待办:A9 安全头审计复跑、A10 生产审核账号密码。
   部署记录见 [docs/deployment-runbook.md](docs/deployment-runbook.md) § 2.13。
5. **2026-10-07 的多角色改动尚未部署**:线上实测 `GET /api/v1/users/roles/options`
   仍返回 404(线上进程 uptime 也早于该轮开发),部署步骤同上。

---

## 技术栈

| 端 | 技术 |
|---|---|
| 后端 | Python 3.11+ · FastAPI 0.115 · SQLAlchemy 2.0(async) · aiosqlite · Pydantic 2 · uvicorn |
| 小程序 | 原生微信小程序(基础库 3.6.0)· AppID `wx2273201e59e280bc` |
| H5 / Admin | 静态资源,挂载在 FastAPI 同源 |
| 数据库 | SQLite(`xiulijiu.db`,生产同样) |
| 支付 | 微信支付 V3 + 商户转账(提现) |
| 鉴权 | HMAC 签名 token(`app/core/auth.py`)+ 角色依赖(`require_admin` / `require_staff` / `require_staff_or_self`) |

---

## 目录结构

```
xiulijiu/
├── app/                       # FastAPI 后端
│   ├── main.py                # 入口(lifespan + 路由挂载 + /metrics)
│   ├── core/                  # config / database / middleware / auth / env_validator
│   ├── models/                # SQLAlchemy 模型(41 张表,含 base.enum_column)
│   ├── routers/               # 14 个 API 路由模块
│   ├── schemas/               # Pydantic schema
│   └── services/              # 业务服务层(22 个)
├── miniprogram/               # 微信小程序
│   ├── app.js / app.json      # 单 App 多角色入口(31 页)
│   ├── pages/                 # 31 个页面(11 类角色)
│   ├── components/            # 自定义组件(角色 tabbar)
│   └── utils/                 # API 封装 / 角色路由
├── h5/                        # H5 工作台 → 挂载在 /h5
├── admin-web/                 # 管理后台 → 挂载在 /admin(需管理员 token)
├── scripts/                   # 工具脚本
│   ├── seed_demo_data.py      # 线上 demo 数据种子
│   ├── test_platform_flows.py # 平台全链路测试
│   ├── check_wechat_pay.py    # 微信支付配置检查
│   └── set_review_account.py  # 生成审核账号密码(写入 .env)
├── docs/                      # 项目文档
│   └── security-hardening-2026-10.md  # 本轮安全收口记录(必读)
├── cert/                      # 微信支付证书(本地)
├── uploads/                   # 用户上传文件
├── design/                    # 设计稿参考图 + 截图
├── .env.example               # 环境变量模板
└── requirements.txt           # Python 依赖
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

**管理后台登录**(2026-10-05 起):打开 `http://localhost:8000/admin/`,首屏要求填入
**平台管理员 token**。获取方式:

```powershell
curl -X POST http://localhost:8000/api/v1/auth/wechat-login `
  -H "Content-Type: application/json" `
  -d '{\"code\":\"18800000000:演示管理员:admin\"}'
# 取响应里的 token,粘贴到后台登录框(不含 Bearer 前缀)
```

token 存在浏览器 `localStorage`,接口会带 `Authorization: Bearer <token>`;
401 时自动退回登录页。非平台管理员角色可以登录,但管理接口会返回 403。

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

单 App 多角色,登录后根据 `user.business_role` 自动跳转到对应首页(共 31 个页面)。

---

## Demo 账号

`POST /api/v1/auth/wechat-login` 只接受 `app/routers/auth.py::_DEMO_ACCOUNTS` 里的 9 个白名单手机号
(其他手机号返回 403),用于演示与本地联调。

| 角色 | 手机号 | 名称 | business_role |
|---|---|---|---|
| 总管理 | 18800000000 | 演示管理员 | `platform_admin` |
| 客户 | 18800000001 | 演示客户 | `customer` |
| 师傅 | 18800000002 | 演示师傅张工 | `repairer` |
| 二接师傅 | 18800000003 | 演示二接师傅李工 | `second_receiver` |
| 店长 | 18800000004 | 演示门店店长 | `store_manager` |
| 城市经理 | 18800000005 | 演示城市经理 | `city_manager` |
| 推广经理 | 18800000006 | 演示推广经理 | `promotion_manager` |
| 服务保障 | 18800000007 | 演示服务保障 | `tech_support` |
| 财务 | 18800000008 | 演示财务 | `finance` |

```powershell
# 取演示管理员 token
curl -X POST https://x.iddg.cn/api/v1/auth/wechat-login `
  -H "Content-Type: application/json" `
  -d '{\"code\":\"18800000000:演示管理员:admin\"}'
```

> 调试短信通道(固定验证码 `246810`)现在必须显式打开:
> `.env` 里 `ALLOW_SMS_DEBUG_ENDPOINT=true`,**生产保持 false**。

---

## 微信审核相关

- **审核路径(主路径)**:首屏 → "体验完整功能" → 直接进入师傅"收益"页 → 输入 1.00 元 → 申请提现
- **审核手机号**:`18800000999`(白名单内,登录即自动发放 `WECHAT_REVIEW_MIN_BALANCE` 元体验余额)
- **账号密码入口**:`reviewer` / `.env` 的 `WECHAT_REVIEW_PASSWORD`;
  该密码当前为空,`/api/v1/auth/review-login` 会返回 503。
  用 `python scripts/set_review_account.py` 生成并写入本地/生产 `.env`。
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

# 生成审核账号密码并写入 .env(微信提审前)
python scripts/set_review_account.py

# env 严格校验(生产部署前)
python scripts/validate_env.py --strict

# 部署微信支付密钥/证书
pwsh scripts/set_wechat_runtime_config.ps1
```

---

## 小程序 CI 上传

```powershell
# 一次性安装(postinstall 会自动给 miniprogram-ci 打 Node 25 兼容补丁)
npm install

# 上传开发版本(需要 miniprogram-ci 私钥)
$env:VERSION = "1.0.222"
$env:DESC = "立即修 v1.0.222"
$env:WX_PRIVATE_KEY_PATH = "D:/private.wx2273201e59e280bc.key"
npm run upload
```

最近一次上传:**v1.0.222**(2026-10-05,`Upload complete`)。

注意三点:

1. **`miniprogram-ci` 上传的是「开发版本」,不是「体验版」。**
   体验版需要在微信公众平台手动设置一次:
   小程序后台 → 管理 → 版本管理 → 开发版本 → 选中该版本 → **选为体验版**。
   也可以用微信开发者工具「上传」后再点「选为体验版」,效果一致。
   （`ci.upload` 的参数表里没有 `envVersion`,传不了体验版;这一点无法用命令绕开。）
2. **Node 版本**:运行时必须是 ≥ Node 25 时,`miniprogram-ci` 的
   `global.localStorage.getItem` 会抛 `TypeError: r.getItem is not a function`。
   仓库已内置兼容处理:
   - `upload.js` 顶部会清掉不完整的 `globalThis.localStorage`;
   - `scripts/patch_miniprogram_ci.py` 修掉 `dist/utils/debug.js` 的三处调用,
     并由 `package.json` 的 `postinstall` 自动执行(手动核对:`python scripts/patch_miniprogram_ci.py --check`)。
3. **线上小程序码指向哪个版本**:后端 `WECHAT_MINIPROGRAM_ENV_VERSION`
   直接作为微信 `getwxacodeunlimit` 的 `env_version` 发出
   (`app/services/wechat_pay.py::get_mini_program_code`)。
   - `develop` / 非法取值:`validate_env.py --strict` 会拦(只有开发者打得开);
   - `trial`:只告警。**正式版发布之前它是唯一可用的取值**(没有正式版时
     `env_version=release` 不一定出得了码),但发布正式版后必须改成 `release`
     —— 否则线上推广/代理码会把普通客户引到体验版,非体验成员打不开,
     而接口本身并不报错。

---

## 关键设计取舍

- **SQLite 用于生产** — 简化部署;`alembic` 已装但当前用 `init_db` 自动建表,后续上 MySQL/PG 时切到迁移
- **PAYMENT_ALLOW_MOCK** — 本地调试用 mock 支付,生产必须 `false`
- **WECHAT_WITHDRAW_AUTO_TRANSFER** — 提现走商户转账;false 时只生成申请,人工处理
- **request_id 中间件** — 所有请求带 X-Request-ID,便于排障
- **枚举列大小写不敏感**(`app/models/base.py::enum_column`) — 落库统一用枚举成员名(大写),
  读出来再归一化 + 别名映射,兼容历史小写值与旧枚举名。
  这修掉了 `profit_shares.role_type='PLATFORM'` 导致的 500 和 `/metrics` 恒为 0 的问题。

---

## 当前进度与阻塞

✅ 已完成:后端 API 体系 / 31 个小程序页面 / 微信支付 V3 / H5+Admin 挂载 / 全链路测试 / demo 种子
✅ 2026-10-05:~10-06:鉴权全量收口 + 枚举口径修复 + admin-web 登录态,**已部署上线并验收 A1–A8**
✅ 2026-10-07:一个账号多角色(拥有并集放行 + 当前身份切换),后端/小程序/后台/文档齐备
🔧 待办:**把 2026-10-07 的多角色改动部署到线上**(线上实测 `/users/roles/options` 仍 404)
📦 仓库:两轮改动已提交为 `a0a992e`(安全收口)与 `4a3330a`(多角色),tag 见 `git tag`
🚧 阻塞:**设计稿对位验证**(P1)— 详见 [docs/design-qa.md](docs/design-qa.md),需微信开发者工具登录后截图

### 本轮验证结果(2026-10-05 ~ 10-07,2026-10-12 在提交快照上复跑)

| 验证项 | 结果 |
|---|---|
| 未登录访问 30 个敏感接口 | 30/30 返回 401 ✅ |
| 带 token 正常流程(5 类角色 21 个调用) | 21/21 通过 ✅ |
| 越权防护(客户访问管理接口/他人数据) | 10/10 返回 403 ✅ |
| 管理后台端到端冒烟(登录态 + 15 视图 + 退出) | 23/23 通过 ✅ |
| 分润接口(历史枚举名) | 500 → 200 ✅ |
| `/metrics` 口径(枚举大小写) | 已对齐实际数据 ✅ |
| 回归测试(test_auth_admin / order_authz / role_boundaries / reconcile_balance) | 79/79 通过 ✅ |
| 多角色(接口 + 老库迁移 + 小程序) | 37 + 29 + 12 通过 ✅ |
| pytest(env 校验 + health) | 25/25 通过 ✅ |
| 线上版本抽查(2026-10-12) | `/api/v1/users` 401 · `/finance/profit/order/1` 401 · `/users/roles/options` **404** |

---

## 文档索引

- [docs/security-hardening-2026-10.md](docs/security-hardening-2026-10.md) — 安全收口记录(2026-10-05,已部署)
- [docs/multi-role-2026-10.md](docs/multi-role-2026-10.md) — 一个账号多角色(2026-10-07,待部署)
- [docs/progress.md](docs/progress.md) — 阶段性开发进度
- [docs/deployment-runbook.md](docs/deployment-runbook.md) — 部署手册(含本轮部署清单)
- [docs/wechat-review-guide.md](docs/wechat-review-guide.md) — 微信小程序审核说明
- [docs/design-qa.md](docs/design-qa.md) — 设计稿对位 QA(目前阻塞)
- [docs/test-report.md](docs/test-report.md) — 全链路测试报告(6/6 ✅)
- [docs/review-audit.md](docs/review-audit.md) — 微信提审前核对报告(13/13 ✅)
- [docs/monitoring.md](docs/monitoring.md) — 监控告警接入指南
- [docs/security-audit.md](docs/security-audit.md) — 安全头审计基线(2026-10-05 复测更新)
- [docs/ci.md](docs/ci.md) — CI/CD 接入指南
- [docs/logging.md](docs/logging.md) — 结构化日志接入
- [docs/legal/README.md](docs/legal/README.md) — 法务材料接入(用户协议 / 隐私政策 / ICP 备案)
- [docs/production-readiness.md](docs/production-readiness.md) — 商用就绪体检报告
- [docs/region-architecture-2026-10.md](docs/region-architecture-2026-10.md) — 区域架构与数据重置(2026-10-07)
- [docs/admin-login-2026-10.md](docs/admin-login-2026-10.md) — 管理后台账号密码登录(2026-10-07)
- [docs/credential-rotation-2026-10.md](docs/credential-rotation-2026-10.md) — 生产凭据轮换记录(2026-10-07)
- [docs/full-flow-test-sop.md](docs/full-flow-test-sop.md) — 全流程手工测试 SOP
- [docs/wechat-devtools-cli.md](docs/wechat-devtools-cli.md) — 微信开发者工具 CLI 用法
- [docs/alerts-fix-plan.md](docs/alerts-fix-plan.md) — 告警修复方案与 bug 根因
- [deploy/README.md](deploy/README.md) — 部署指南(Docker / nginx / SSL)
- [API 文档(Swagger)](https://x.iddg.cn/docs) — 线上 API 自动文档
