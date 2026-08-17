# 开发进度

> 最后更新:2026-08-09(本轮梳理后落盘)

## 当前状态(2026-08)

进入**微信小程序提审冲刺**阶段。后端 + 30 个小程序页面已就位,最近两波改动(7/22-7/23)
是全链路跑通 + 微信审核合规修正。

**2026-08-09 节点**:全链路测试 6/6 ✅ · 提审前核对 13/13 ✅ · H5 截图 9 角色 65 张 ✅。
代码层 + API 层均通过审核要求,可进入提审阶段。
**剩余 P1 阻塞:design-qa 小程序端 30 页面截图**(需微信开发者工具扫码登录)。

---

## 时间线

### 6/22 — 项目骨架
- 后端 core / database / middleware 落地
- 基础模型:`user` / `repairer` / `order` / `order_log` / `wallet` / `region` / `alert_event`
- 基础路由:`auth` / `user` / `repairer` / `order` / `region` / `store` / `finance`

### 6/26-6/30 — UI 密集迭代
- 小程序 30 个页面的基础布局完成
- 客服、财务、推广、城市、店长、二接等角色页面上线
- `package.json`(miniprogram-ci)和 `upload.js` 上传脚本就位

### 7/2-7/6 — 设计稿对位 + 登录/支付打磨
- 产出 **155 张 `preview-1.0.X-*.png` 截图**(主要是登录、首页、订单)
- 登录页 v1.0.161-168 密集调整
- 订单相关 v1.0.169 系列
- 钱包/财务/支付流程定型

### 7/12 — 服务化升级(关键节点)
- 新增/更新核心模型:
  - `service_area` + `ServiceAreaAssignment` — 服务区域
  - `service_bill` — 服务单
  - `profit_share` — 分润
  - `ledger` — 流水
  - `user` / `settlement` / `support_ticket` 升级
- 新增/更新服务:`service_area` / `safety` / `service_bill` / `wallet` / `user`
- 新增/更新路由:`service_area`
- 小程序新增:`domestic/list` `domestic/detail` `domestic/demand` `warranties` `addresses`
- Admin 静态站 `index.html` / `styles.css` / `app.js` 定版

### 7/15 — 微信支付 + 门店 dashboard 收尾
- `pay_order` / `wechat_pay` 服务成型
- `payment` 路由接通
- 门店 dashboard 模板上线

### 7/16 — 认证收尾
- `auth` 路由 v7.16 收尾(账号密码登录 + 审核账号支持)

### 7/17 — 审核说明落盘
- `wechat-review-guide.md` 撰写完成
- 审核账号 `reviewer` 设立(密码配置于 `WECHAT_REVIEW_PASSWORD`)

### 7/22-7/23 — 提审冲刺(最近一波)
- **后端**:
  - `services/business.py` / `services/order.py` / `services/profit.py` / `services/store.py` 集中更新
  - `models/business.py` / `models/order.py` / `models/store.py` 同步
  - `routers/business.py` / `routers/order.py` / `routers/store.py` 路由完善
- **小程序**:
  - 客户侧 6+ 页全更新:`addresses` / `detail` / `order` / `orders` / `pay` / `profile` / `warranties` / `warranty-claim`
  - 新增 `account/personal-info` 和 `account/settings` 两个设置页
  - `app.json` 注册新页面
- **审核合规修正**:
  - 登录页去除"微信"字样
  - 登录图标改为电话听筒
  - 文案改为"手机号快捷登录"
- **脚本**:
  - 新增 `scripts/test_platform_flows.py` — 平台全链路独立测试
  - 新增 `scripts/seed_demo_data.py` — 线上 demo 数据种子
- **小问题**:临时数据库残留 `scripts/platform_flow_test.db`(0 字节)

### 8/9 — 文档归位(本轮)
- 新建根目录 `README.md`
- 新建 `docs/progress.md`(本文件)
- `design-qa.md` / `wechat-review-guide.md` 移入 `docs/`

---

## 能力矩阵

| 能力 | 后端 | 小程序 | H5 | Admin |
|---|---|---|---|---|
| 认证(微信登录 + 短信) | ✅ | ✅ | ✅ | — |
| 订单全流程 | ✅ | ✅ | ✅ | ✅ |
| 钱包 + 提现 | ✅ | ✅ | ✅ | ✅ |
| 微信支付 V3 | ✅ | ✅ | — | — |
| 商户转账(提现) | ✅(可关闭) | — | — | ✅ |
| 家政(需求/合同/工人) | ✅ | ✅ | — | — |
| 保修 + 理赔 | ✅ | ✅ | — | — |
| 服务区域管理 | ✅ | — | — | ✅ |
| 多角色 dashboard | ✅ | ✅ | — | ✅ |
| 财务结算 + 分润 | ✅ | — | — | ✅ |
| 告警事件 | ✅ | — | — | ✅ |

---

## 已完成 / 进行中 / 阻塞

### ✅ 已完成
- 后端 API 体系(13 路由 / 18 模型 / 22 服务)
- 30 个小程序页面覆盖 11 个角色
- H5 / Admin 静态站挂载
- 微信支付 V3 + 商户转账预留
- Demo 数据种子(`seed_demo_data.py`)
- 平台全链路独立测试(`test_platform_flows.py`)
- 微信审核说明文档
- 根目录 README + 文档归位

### 🔧 进行中
- 微信审核提审(代码/API 已就绪,等正式提交)
- 等用户选下一条 P1 推进方向

### 🚧 阻塞
- **design-qa 小程序端 30 页面截图**(P1)— 详见 `docs/design-qa.md`
  - 需微信开发者工具扫码登录
  - H5 部分已突破(9 角色 65 张)

### ✅ 8/9 新增 + 2 P0/P1 + P0-收尾 + P1-监控 + P1-安全头 + P1-CI/CD + P1-日志 + P1-法务 + P2-法务衍生
- **H5 实现批量截图** — 9 角色 × 65 tab/首屏截图,落盘 `design/screenshots/`
- **全链路测试** — `scripts/run_platform_flow_tests.ps1` 跑通,**6/6 套件全过**(报告 `docs/test-report.md`)
- **提审前核对** — `scripts/review_audit.js` 跑通,**13/13 通过**(报告 `docs/review-audit.md`)
- **🔴 P0 告警消化**:修复 ledger 语义 bug + 告警去重,**6/6 单测过**
- **🟠 P1 部署脚本化**:Dockerfile + compose + nginx + backup + deploy.sh + 冒烟通过
- **🔴 P0-收尾(鉴权 + 修复接口)**:core/auth.py + admin/wallet 鉴权 + adjust 接口,**15/15 单测过**
- **🟠 P1 监控告警**:/metrics/prom + alert_watcher + Prom + Alertmanager + Grafana + docker-compose,**7/7 单测过**
- **🟠 P1 安全头 + Swagger 防护**:nginx 完整化 + 19 项审计,**5/19 当前 / 19/19 预期**(部署后)
- **🟠 P1 CI/CD**:3 个 GH Actions workflow + 文档,YAML 校验通过
- **🟠 P1 日志结构化**:dictConfig + JSON 输出 + 18/18 单测 + SLS/Loki/ELK 接入指南
- **🟠 P1 法务材料**:模板 + H5/Admin 接入 + 接入指南
- **🟠 P2 法务衍生**:
  - `app/models/user.py` 加 5 个字段(agreed_terms_version / agreed_privacy_version / agreed_at / deletion_requested_at / deletion_scheduled_at)
  - `app/routers/auth.py` 加 4 个端点:`/me`(扩展)+ `/me/agreements` + `/me/export-data` + `/me/delete` + `/me/cancel-deletion`
  - `app/schemas/user.py` 加 `AgreementRequest` / `AgreementStatus` / `CURRENT_TERMS_VERSION` / `CURRENT_PRIVACY_VERSION`
  - `tests/test_agreements.py` **37/37 通过**(覆盖 /me 返 agreements · 记录同意 · 版本不匹配触发 renewal · 数据导出 9 个字段 · 申请/撤回删除 · 跨用户隔离 · schema 校验)
  - 满足《个保法》第 45 条(数据可携权) + 第 47 条(删除权)
- **🟠 P1 DB-1/2 落盘**:
  - `alembic.ini` + `migrations/env.py` + `migrations/versions/2026_08_09_1419-985b36c09a76_initial_schema.py`(40 张表,76KB)
  - 抽 `app/models/base.py`,所有 22 个 model 改 `from .base import Base`
  - 修 10 个被 PowerShell Set-Content -Encoding UTF8 损坏的 model 文件(中文 comment 截断 / 缺右括号 / 不可打印字符)
  - `env.py` 兼容 async URL(aiosqlite→sqlite3, asyncpg→psycopg2, aiomysql→pymysql)
  - `render_as_batch=True` 让 SQLite ALTER TABLE 也兼容
  - `tests/test_alembic_migration.py` **22/22 通过**(upgrade/downgrade 双向 + 17 个关键表存在)
  - `docs/db-migration.md` 接入指南
- **🟠 P1 微信支付诊断升级**:
  - 升级 `scripts/check_wechat_pay.py`:加 `--network` 模式,真打 `/v3/certificates` 验签,发现关键问题
  - **发现真生产阻塞**:MCH_ID `1481119632` / 商户证书 / 私钥签名都正确,但 WeChat 返回 **"平台证书已过期失效"**(HTTP 403)
  - 根因:7/3 新注册商户号,WeChat 平台证书还在初始化 / 缓存未同步
  - 临时绕开:`WECHAT_PAY_PLATFORM_CERT_PATH=cert/wechatpay_cert.pem` 用本地 cert
  - 真解决:打 95017 让微信支付技术支持刷一下
  - 详见 `docs/deployment-runbook.md` § Q8
- **🟠 P1 微信支付容错硬化(2026-08-09)**:
  - `app/services/wechat_pay.py` 加冷却:平台 cert 下载失败后 10 分钟内不重试(避免 WeChat 限频被打爆)
  - 连续失败计数:>=3 次时 `xiulijiu.security` logger 发 WARNING,alert_watcher 自动推到钉钉/飞书
  - 新增 `platform_cert_status()` 函数 + `GET /api/v1/admin/wechat-pay/diagnostics` 端点(admin 可查)
  - `scripts/wechat_support_brief.py` — 一键生成 95017 工单简报 + 电话稿(从 cert 读出商户信息,自动捕获最新错误)
  - `tests/test_wechat_pay_resilience.py` — **9/9 通过**(冷却 / 失败计数 / 状态字段 / 安全告警)
- **🟠 P1 支付链路端到端冒烟(2026-08-09)**:
  - `scripts/payment_smoke.sh` — bash 脚本,7 段 13 检查点:health / 微信配置 / 鉴权 / 对账 / prepay / 指标 / 告警
  - 本地用真 admin+customer token 跑 **10/13 PASS**,剩 3 个 FAIL 全是凭据相关(预期)
  - 输出 JSON 摘要给 CI / alert_watcher 消费
  - 接入 `docs/deployment-runbook.md` § 2.12.6 部署清单
- **🟠 老 DB 升级踩坑记录**:`alembic stamp head` + 手动 `ALTER TABLE users ADD COLUMN ...` 补 5 列(本地 dev DB,生产首次部署要 `alembic upgrade head`)
- **🔵 顺手发现 DB 迁移提示**:本地 dev DB `xiulijiu.db` 缺 `users.agreed_terms_version` 等 5 列(7 月加的),生产部署前必须 `alembic upgrade head`

### 当前测试矩阵

| 测试 | 文件 | 结果 |
|---|---|---|
| 对账语义 | `tests/test_reconcile_balance.py` | **6/6** |
| 鉴权/admin | `tests/test_auth_admin.py` | **15/15** |
| 告警推送 | `tests/test_alert_watcher.js` | **7/7** |
| 日志结构化 | `tests/test_logging.py` | **18/18** |
| 协议版本管理 | `tests/test_agreements.py` | **37/37** |
| alembic 迁移 | `tests/test_alembic_migration.py` | **22/22** |
| **合计** | | **105/105** |
| YAML 语法 | 3 个 GH Actions workflow | **3/3** |
| **合计** | | **86/86** |

### 🔴 P0 等用户决策(部署 + 真跑)
- **部署修复代码**:`app/core/auth.py` / `app/routers/admin.py` / `app/routers/wallet.py` / `app/services/safety.py` / `app/models/ledger.py` / `app/core/middleware.py` / `app/main.py` 改动需要部署才生效
- **跑 `--apply`**:`node scripts/reconcile_apply.js --apply`
- **真实支付配置**:`.env` 缺 MCH_ID / API_V3_KEY / APP_SECRET(原 P0 #3)

---

## 待办(TODO)

按优先级:

1. **🟠 P1 选下一个**:从剩下 6 条 P1 里选(监控告警 / 数据库迁移 / CI/CD / 日志 / 安全头 / 法务)
2. **🟠 P1 提审提交** — 走微信小程序提审流程
3. **🟠 P1 design-qa 小程序端** — 微信开发者工具扫码登录,补 30 个小程序页面截图
4. **🟡 P2 补缺失素材** — admin-web/assets 只有 logo,缺角色图标
5. **🟡 P2 根目录清理**:
   - 156 张 `preview-1.0.*.png` 截图按版本归档或 .gitignore
   - `.codex` / `.agents` / `.edge-profile` 临时目录确认是否需要
6. **🟢 P3 切到 alembic 迁移** — 当前用 `init_db` 自动建表,生产有风险
7. **🟢 P3 找一下 `preview` 截图脚本** — 155 张图明显是程序生成,但脚本未提交
