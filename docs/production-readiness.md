# 商用就绪体检报告

> 跑测时间:2026-08-09 23:30(本轮刷新)
> 目标环境:https://x.iddg.cn (8.134.99.53)
> 当前服务已运行 uptime ≈ 17.7+ 天(自 7/22)

---

## TL;DR

| 维度 | 状态 | 一句话 |
|---|---|---|
| 业务功能 | ✅ | 30 页面 / 9 角色 / 13 路由 / 40 表,功能闭环 |
| 测试 | ✅ | **138/138** 全过(reconcile 6 + auth_admin 15 + alert 7 + logging 18 + agreements 37 + alembic 22 + wechat_resilience 9 + **platform_flows 6** + **validate_env 12 + health_env 6**);`test_platform_flows.py` 之前 P0 鉴权改造时整个断了,本轮已修 |
| **认证鉴权** | ✅ | `app/core/auth.py` + admin/wallet 全端点加鉴权,`/admin/wallet/adjust` 已加;**`test_platform_flows.py` 全部 55 个 `expect()` 调用已接上对应角色 token** |
| **业务告警** | ✅ | ledger 语义 bug 修好,告警去重 + admin 调整接口,生产上仍需消化现有 4 条 |
| **数据库** | ✅ | alembic 40 表迁移落地,SQLite/MySQL 切换脚本就绪 |
| **部署** | ✅ | Dockerfile + compose + nginx(SSL + 6 安全头 + 限速 + basic auth)+ backup + deploy.sh + 部署 runbook |
| **配置校验** | ✅ | `app/core/env_validator.py` 12/12 + `tests/test_health_env.py` 6/6,`deploy.sh` 启动前 strict,可选 `STRICT_ENV_ON_STARTUP=true` 让进程直接 fail |
| **运行时 env 自检** | ✅ | `GET /health/env?mode=strict` —— 任何时候都能查 env 完整性,monitoring / 排错都用 |
| **监控** | ✅ | /metrics/prom + alert_watcher(钉钉/飞书/通用)+ Prom + Alertmanager + Grafana + 19 项安全审计;**env 完整性告警已接**(xiulijiu_env_ok / xiulijiu_env_placeholders) |
| **生产 fail-fast** | ✅ | docker compose 默认 `STRICT_ENV_ON_STARTUP=true`,缺 secret 直接 exit 1;运维排查时设 false 把容器起起来再修 |
| **日志** | ✅ | dictConfig + JSON 输出 + 4 logger 分组 + 3 audit 路径 + SLS/Loki 接入指南 |
| **CI/CD** | ✅ | 3 个 GH Actions workflow(ci/deploy/miniprogram) + ci 文档 + CI 自动跑 validate_env 双向夹 |
| **法务** | ✅ | 协议 / 隐私 / 合规 3 份文档 + H5/Admin 接入 + 数据导出 + 申请/撤回删除端点 + 37/37 测试 |
| **Settings 弹性** | ✅ | `app/core/config.py` 加 `extra="ignore"`,docker compose 混 env 不再误伤 app |
| **.gitignore** | ✅ | `cert/` / `*.pem` / `.env` / `.venv/` / `._trash/` 全 ignore(防止敏感信息误 commit) |
| **支付配置** | 🔴 P0 | `.env` 已补全 47 行,真实凭据待填(MCH_ID / API_V3_KEY / APP_SECRET) |
| **ICP 备案** | 🔴 P0 | 商用前必须(公网域名 / 微信商户都需要) |
| **告警消化** | 🟠 P1 | 4 个历史 critical 告警(`reconcile_mismatch`)需在生产上跑 `reconcile_apply.js --apply` 消化 |
| 性能 | 🟡 P2 | 无缓存层;无 CDN;SQLite 并发未知(切 MySQL 后改善) |
| 容灾 | 🟡 P2 | 无多副本;无灰度发布 |

---

## ✅ 2026-08-09 之前的 P0/P1 已闭环

### 鉴权(`app/core/auth.py` + 全部受保护端点)
- `get_current_user` / `require_admin` / `require_self_or_admin` 三个依赖
- `app/routers/wallet.py` 全部端点 → `Depends(get_current_user)` + self/admin 校验
- `app/routers/admin.py` 全部端点 → `Depends(require_admin)`
- 新增 `POST /admin/wallet/adjust`(管理员手工调账,带 ledger 流水 + audit log)
- `tests/test_auth_admin.py` **15/15 通过**(覆盖无 token / 错 token / 自查 / 越权 / 跨角色 401/403/200)

### 告警(`app/services/safety.py` + admin)
- 修 ledger 语义 bug:`LEDGER_FREEZE` 写 `-amount` 应 0(只移冻结),`LEDGER_UNFREEZE` 写 0 应 `-amount`(只移回)
- admin alerts 端点按 `(type, user_id, order_id, reference_id, status, resolved)` 去重
- `POST /admin/wallet/adjust` 一键修复对账差异
- `tests/test_reconcile_balance.py` **6/6 通过**(覆盖 deposit/withdraw/freeze/complete/reject/full_flow)

### 数据库(alembic 40 表迁移)
- `alembic.ini` + `migrations/env.py`(自动从 .env 读 DATABASE_URL,async → sync 转换)
- `migrations/versions/2026_08_09_1419-985b36c09a76_initial_schema.py`(76KB,40 张表)
- `app/models/base.py` 抽出,22 个 model 改 `from .base import Base`
- `render_as_batch=True` 兼容 SQLite ALTER TABLE
- `tests/test_alembic_migration.py` **22/22 通过**
- `docs/db-migration.md` 接入指南

### 部署脚本化
- `Dockerfile`(多阶段 build,非 root 用户,4 uvicorn worker)
- `docker-compose.yml`(api + nginx + mysql + backup cron + 可选 monitoring)
- `deploy/nginx.conf`(SSL 终止 + 6 个安全头 + CSP + 限速 + basic auth)
- `deploy/backup.sh`(每日 03:00 备份,保留 7 天)
- `scripts/deploy.sh`(部署编排:备份 → build → 重启 → 健康检查 → 冒烟 → 对账)
- `docs/deployment-runbook.md` 完整 runbook(15 步首次部署 + 日常 + 回滚 + 运维 + FAQ)

### 监控告警
- `app/main.py` `/metrics/prom` Prometheus 格式输出
- `scripts/alert_watcher.js` 钉钉 / 飞书 / 通用 webhook
- `deploy/prometheus/prometheus.yml` + `deploy/alertmanager/alertmanager.yml`
- `deploy/grafana/provisioning/` 自动 provision dashboard
- `tests/test_alert_watcher.js` **7/7 通过**

### 日志
- `app/core/logging.py` dictConfig + JSON 输出
- 4 个 logger 分组:`xiulijiu.observability` / `xiulijiu.audit` / `xiulijiu.security` / `xiulijiu.app`
- 3 个 audit 路径:用户协议同意 / 提现申请 / 管理员调账
- `tests/test_logging.py` **18/18 通过**(JSON 格式 / 级别 / logger 名 / 异常 / extra / request_id / stdout)
- `docs/logging.md` SLS/Loki/ELK 接入指南

### 安全头 + Swagger 防护
- nginx 加 6 个安全头:`Strict-Transport-Security` / `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy` / `Permissions-Policy` / `Content-Security-Policy`
- CSP 限制脚本 / 样式 / 图片源
- `/admin/*` + `/docs` + `/metrics/prom` 加 basic auth
- `scripts/security_audit.js` **19 项**全量审计
- 部署后预期 19/19,本地 5/19 是因为本地 nginx 没启

### CI/CD(`.github/workflows/`)
- `ci.yml` — push/PR → lint + test(6 套件 + alembic)+ build
- `deploy.yml` — 手动 dispatch + staging/production 环境 + SSH 部署
- `miniprogram.yml` — push miniprogram/ → miniprogram-ci 编译 + 上传微信
- `docs/ci.md` 接入指南(Secrets 配置 + 私钥生成 + 审核上传流程)

### 法务材料
- `docs/legal/{user-agreement,privacy-policy,compliance}.md` 3 份文档
- `h5/legal/{user-agreement,privacy-policy}.html` H5 静态页
- Admin `index.html` 接入底部链接
- `tests/test_agreements.py` **37/37 通过**
- `app/routers/auth.py` 加 4 端点:`/me/agreements` / `/me/export-data` / `/me/delete` / `/me/cancel-deletion`
- 满足《个保法》第 45 条(数据可携权)+ 第 47 条(删除权,15 日 grace period)

---

## 🔴 仍阻塞商用的 P0

### 1. 真实支付配置 + WeChat 平台证书(双阻塞)
- **配置未填**:`.env` 当前 `WECHAT_PAY_MCH_ID` / `WECHAT_PAY_API_V3_KEY` / `WECHAT_APP_SECRET` 全空
- **平台证书已过期**:WeChat Pay `/v3/certificates` 返回 HTTP 403 "平台证书已过期失效"(2026-08-09 实测发现)
  - 商户号 1481119632 是 7/3 新注册,WeChat 后台 cert 还在初始化
  - 即使填齐凭据,支付回调验签也会 100% 失败
- 修复:
  - **打 95017** 让微信支付技术支持刷一下 cert(主路径)
  - 同时填凭据:从微信商户平台拿 MCH_ID / API_V3_KEY / APP_SECRET / CERT_SERIAL_NO
  - 临时绕开:让运营从商户平台下载 `wechatpay_cert.pem` 放 `cert/`,设 `WECHAT_PAY_PLATFORM_CERT_PATH=cert/wechatpay_cert.pem`
  - 验证:`python scripts/check_wechat_pay.py --network` 看到 `platform_certs_count: 1+` 才算绿
  - 走 0.01 元真实测试单 + 退款
  - 详见 `docs/deployment-runbook.md` § Q8 + `scripts/wechat_support_brief.py`

### 2. ICP 备案 / 公安备案
- `x.iddg.cn` 公网域名商用必须 ICP 备案
- 涉及用户地理位置 / 个人信息 → 可能要增值电信业务许可证
- 微信小程序发布需要主体一致(小程序主体 = 备案主体 = 支付商户主体)
- 时间:2-3 周(管局审核),等不及的话先上 H5(不需要 ICP)

---

## 🟠 上线前必须(P1)

### 3. 消化 4 个历史 critical 告警
- `id=4 reconcile_mismatch 钱包#3 对账差异 -1013.6`(创建于 7/4,积压 36 天)
- 其它 3 条同类
- 修复:在生产上跑 `node scripts/reconcile_apply.js --apply`,会自动调账 + 写 ledger + 触发 `wallet/adjust` audit log

### 4. 跑一遍线上 `security_audit.js`
- 部署后:`node scripts/security_audit.js https://x.iddg.cn` → 预期 **19/19**
- 当前本地 **5/19**(本地 nginx 未启用)

### 5. 走真实支付 / 退款 / 提现
- 0.01 元下单 + 支付
- 0.01 元退款(走 V3 original route)
- 0.01 元提现(`WECHAT_WITHDRAW_AUTO_TRANSFER=true` 走商户转账,否则手工)

### 6. 走完 15 步首次部署 checklist
- 见 `docs/deployment-runbook.md` § 2

### 7. `.env` 配置校验(2026-08-09 23:00 新增)

之前 `.env` 只有 3 行,部署时漏 secret 全靠运气。现状:

- `.env` 已重写到 47 行,所有需要的 key 都在,FILL_* 标好占位
- `scripts/validate_env.py` 提供 3 种模式:
  - 默认 dev:`FILL_*` 只警告(本地调试)
  - `--strict`:任何占位 + 弱 secret + 非 https + sqlite 全部 fail
  - `--json`:CI 友好输出
- `deploy.sh` 在 staging/production 自动跑 strict,**不通过 exit 1,不会启动容器**
- `tests/test_validate_env.py` 12/12 覆盖(dev/strict 行为 + 占位/弱 secret/非 https/sqlite 检测 + 解析鲁棒性)
- `app/core/config.py` 加 `extra="ignore"`,让 docker compose 的额外 env 不会污染 app 启动

何时用:
- 改完 `.env` → `python scripts/validate_env.py --strict` 自检
- 部署 → `deploy.sh` 自动跑,失败直接 abort
- CI → 注入 fake secret 后跑 `--json` 验证脚本本身能跑通

---

## 🟡 上线后逐步补(P2)

| 项 | 说明 |
|---|---|
| 性能缓存 | 引入 Redis(读多写少:服务区域、套餐) |
| CDN | 静态资源走 CDN |
| 多副本 | 后端多实例 + nginx upstream + DB 连接池调优 |
| 灰度发布 | 新功能按城市/角色灰度 |
| 数据归档 | 历史订单 / 日志按月归档 |
| i18n | 暂只中文,后续支持英文(海外华人市场) |
| 备份演练 | 定期演练"删库 → 恢复"流程 |
| 渗透测试 | 上线前请第三方做一次 |

---

## 推进顺序(更新版)

```
P0 真实支付凭据  ──┐
P0 ICP 备案       ──┼─→ 商用前必须清零
P0 4 个告警消化   ──┘
                   ↓
        走 15 步首次部署 checklist
        跑线上 security_audit.js 验证 19/19
        走真实支付 + 退款 + 提现
                   ↓
        上线 H5 → 上线小程序(需 ICP + 审核)
                   ↓
P2 性能 / CDN / 多副本
P2 数据归档
P2 灰度发布
P2 渗透测试
```

---

## 关键链接

- 部署 runbook:`docs/deployment-runbook.md`
- DB 迁移指南:`docs/db-migration.md`
- 监控告警:`docs/monitoring.md`
- 日志结构:`docs/logging.md`
- 安全审计:`docs/security-audit.md`
- CI/CD:`docs/ci.md`
- 法务:`docs/legal/README.md`
- 微信审核:`docs/wechat-review-guide.md`
- 设计稿核对:`docs/design-qa.md`
