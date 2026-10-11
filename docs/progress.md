# 开发进度

> 最后更新:**2026-10-07**(多角色轮)。
> 上一版:2026-10-05(安全收口轮)。历史时间线保留在文末。

## 当前状态(2026-10)

**安全收口已部署并验收;多角色已实现、待部署。** 后端 API、31 个小程序页面、
15 个管理后台视图、H5 工作台都已成型。

线上 `https://x.iddg.cn` **实测(2026-10-12)跑的是 2026-10-06 的安全收口版**:
`/api/v1/users` → 401、`/api/v1/finance/profit/order/1` → 401(旧代码分别是 200 / 500),
而 `GET /api/v1/users/roles/options` → **404** —— 说明 2026-10-07 的多角色还没上线。
多角色上线步骤见 [deployment-runbook.md](deployment-runbook.md) § 2.13(仍待办 A9 安全头审计、A10 审核账号密码)。

仓库侧:两轮改动已于 2026-10-12 提交为 `a0a992e`(安全收口)与 `4a3330a`(多角色),
此前 8/18 之后的所有工作都只存在于本地工作区。

---

## 2026-10-07 — 一个账号多角色(本轮)

需求:一个手机号可能同时是 **店长 + 师傅 + 业务**(如 18060936373)。
改造前权限只认单个 `users.business_role`,多角色只能三选一。

* 数据模型:`users.business_roles`(JSON,拥有)+ `users.active_business_role`
  (当前身份)+ `user_role_grants`(变更审计);`business_role` 降级为兼容字段。
  启动时轻量迁移自动补列 + 回填,可反复执行。
* 鉴权:`app/services/role.py` 统一口径 —— **拥有任一所需角色即放行(并集)**,
  当前身份只影响展示与入口,不参与放行,避免切换身份时突然 403。
* 接口:`GET/PATCH /api/v1/users/{id}/roles`、`POST .../switch-active-role`、
  `GET /api/v1/users/roles/options`;登录与 `/auth/me` 新增
  `business_roles` / `active_business_role`。防提权与防自锁都有回归用例。
* 小程序:「我的」页显示全部角色标签 + **切换身份**,切换后首页/导航/工作台
  全局跟随;个人信息页同样可切。
* 管理后台:用户列表新增「业务角色 / 当前身份」列与「配置角色」多选弹窗。
* 顺手补上:生产库历史上从未跑过 alembic,6 个用户列
  (`agreed_terms_version` 等)补进轻量迁移,老库启动不再 500。
* 新增文档与测试:[multi-role-2026-10.md](multi-role-2026-10.md)、
  `tests/test_multi_role.py`(37)、`tests/test_multi_role_migration.py`(29)、
  `tests/test_multi_role_miniprogram.js`(12);CI 两个 workflow 都已接入。
* 配置示例账号:`python scripts/seed_multi_role_demo.py 18060936373`
  (幂等,只补齐不删除)。

---

## 2026-10-05 — 安全收口(上一轮)

### 🔴 修掉的 P0

| # | 问题 | 证据 | 修复 |
|---|---|---|---|
| P0-1 | 生产 `SMS_PROVIDER=debug` 把固定验证码回显在 `/api/v1/auth/sms/request` 响应里,`/sms/login` 又无白名单 → **任意手机号账号接管** | 线上实测 `debug_code=246810` → `/sms/login` 返回真实用户 `id=4` | 新增 `ALLOW_SMS_DEBUG_ENDPOINT`(默认 false);闸门放到限流之前;strict env 校验拦截 |
| P0-2 | 71 个写接口 + 6 类含 PII 读接口零鉴权 | `GET /api/v1/users`、`/orders`、`/business/wages` 等线上均 200 | 12 个路由模块全量加 `require_admin` / `require_staff` / `require_staff_or_self` |
| P0-3 | 无 token `PATCH /api/v1/users/{id}` 可把自己改成 `platform_admin` | 线上实测提权成功(已还原) | 权限字段仅平台管理员可改;本人改自己 `business_role` 直接 403 |

### 🟠 修掉的 P1

| # | 问题 | 修复 |
|---|---|---|
| P1-1 | admin-web 不带 `Authorization`,管理接口全 401,提现审核/对账告警不可用 | 新增登录态(localStorage token + 401 自动登出 + 身份显示 + 退出) |
| P1-2 | `GET /api/v1/finance/profit/order/{id}` 因历史枚举名 `PLATFORM` 返回 500 | `enum_column()` + `LEGACY_PROFIT_ROLE_ALIASES` 别名映射 |
| P1-3 | `/metrics` 与 `/metrics/prom` 的 `orders_completed`/`orders_pending` 恒为 0 → Prometheus 告警永不触发 | raw SQL 改用枚举成员名;两个端点共用 `_business_metrics()` |
| P1-4 | 对账统计 `l.status == "mismatch"` 恒为 False,差异永远统计不出来 | 改为 `ReconcileStatus.MISMATCH` |
| P1-5 | 审核账号密码为空,`/auth/review-login` 503 | 新增 `scripts/set_review_account.py`;README/审核指南写明步骤 |

### 🛠 其它

- `app/models/base.py::enum_column()` — 大小写不敏感 + 别名兼容的枚举列,22 个模型文件全部切换
- 仓库清理:156 张 `preview-*.png` 归档到 `._trash/`(已 gitignore);
  删除 `release-*.tgz` / `sqlite-*.tar.gz` / `__tmp_*.py` / 临时 db;`.edge-profile*/` 加入 gitignore
- 新增文档:[security-hardening-2026-10.md](security-hardening-2026-10.md)(含证据链与遗留项)

### ✅ 本轮验证

| 验证项 | 结果 |
|---|---|
| 未登录访问 30 个敏感接口 | **30/30 → 401** |
| 带 token 正常流程(admin/store/customer/repairer) | **21/21 → 200** |
| 越权防护(客户碰管理接口 / 他人数据) | **10/10 → 403** |
| 管理后台端到端(Playwright:登录→15 视图→退出) | **23/23 通过** |
| 分润接口(历史枚举名) | **500 → 200** |
| `/metrics` 口径 | 对齐实际数据 |
| SMS 闸门关闭后 `/sms/request` | **503 且无 `debug_code`** |
| 审核账号登录(+自动发放 100 元体验余额) | **200** |
| 回归测试 | **125/125 通过** |

测试矩阵(全部重跑过):

| 测试 | 文件 | 结果 |
|---|---|---|
| 鉴权 + admin adjust | `tests/test_auth_admin.py` | **15/15** |
| 协议版本管理 | `tests/test_agreements.py` | **37/37** |
| 对账语义 | `tests/test_reconcile_balance.py` | **6/6** |
| 微信支付容错 | `tests/test_wechat_pay_resilience.py` | **9/9** |
| alembic 迁移 | `tests/test_alembic_migration.py` | **22/22** |
| 日志结构化 | `tests/test_logging.py` | **18/18** |
| health/env + validate_env(pytest) | `tests/test_health_env.py` + `tests/test_validate_env.py` | **18/18** |
| **合计** | | **125/125** |

---

## 能力矩阵

| 能力 | 后端 | 小程序 | H5 | Admin |
|---|---|---|---|---|
| 认证(演示账号 + 短信 + 审核密码) | ✅ | ✅ | ✅ | ✅(token) |
| 订单全流程 | ✅ | ✅ | ✅ | ✅ |
| 钱包 + 提现 | ✅ | ✅ | ✅ | ✅ |
| 微信支付 V3 | ✅ | ✅ | — | ✅ |
| 商户转账(提现) | ✅(可关闭) | — | — | ✅ |
| 家政(需求/合同/工人) | ✅ | ✅ | — | ✅ |
| 保修 + 理赔 | ✅ | ✅ | — | ✅ |
| 服务区域管理 | ✅ | — | — | ✅ |
| 多角色 dashboard | ✅ | ✅ | — | ✅ |
| 财务结算 + 分润 | ✅ | — | — | ✅ |
| 告警事件 / 对账 | ✅ | — | — | ✅ |

---

## 待办(TODO)

### 🔴 P0 — 部署(唯一阻塞项)
1. 按 [deployment-runbook.md](deployment-runbook.md) § 2.13 把 **2026-10-07 的多角色**改动
   部署到线上(安全收口那轮已于 10-06 上线;多角色线上实测仍是 404)

### 🟢 已闭环(2026-10-12)
- 两轮工作入库:安全收口 → `a0a992e`,多角色 → `4a3330a`(此前 8/18 之后全部改动仅存在于本地)
- 订正本文与 README 里「线上仍在跑旧代码」的过时口径,改为实测结论
- 回归复跑:79/79(auth_admin / order_authz / role_boundaries / reconcile_balance)
  + 37/29/12(多角色后端/迁移/小程序)+ 25(pytest)= 全部通过

### 🟠 P1
2. 生成审核账号密码(`scripts/set_review_account.py`)后重新走微信提审
3. design-qa 小程序端截图(需微信开发者工具扫码登录,见 [design-qa.md](design-qa.md))
4. 生产 nginx 侧核对 `/docs`、`/metrics` 的 basic auth —— 2026-10-12 实测已收紧
   (`/docs` `/redoc` `/openapi.json` `/metrics` 均 401),待正式归档关闭

### 🟡 P2
5. admin-web 文案中英混排(`loadWallet` / `loadFinance` 两个视图是英文,其余中文)
6. `/sms/login` 仍会自动建号 — 接真实短信商时建议加「手机号必须已存在」
7. `_DEMO_ACCOUNTS` 硬编码白名单 → 迁到配置/数据库,`platform_admin` 加二次校验
8. admin-web 缺角色图标素材(`assets/` 目前只有 logo)
9. 切到 alembic 迁移(当前仍靠 `init_db` 自动建表)

---

## 历史时间线(2026-06 ~ 2026-08)

### 6/22 — 项目骨架
后端 core / database / middleware 落地;基础模型 `user` / `repairer` / `order` /
`order_log` / `wallet` / `region` / `alert_event`;基础路由 7 个。

### 6/26-6/30 — UI 密集迭代
小程序页面布局完成;客服/财务/推广/城市/店长/二接等角色页面上线;
`package.json`(miniprogram-ci)与 `upload.js` 就位。

### 7/2-7/6 — 设计稿对位 + 登录/支付打磨
产出 155 张 `preview-1.0.X-*.png` 截图(2026-10-05 已归档到 `._trash/`);
登录页 v1.0.161-168 密集调整;订单 v1.0.169 系列;钱包/财务/支付流程定型。

### 7/12 — 服务化升级(关键节点)
新增 `service_area` / `service_bill` / `profit_share` / `ledger`;
`user` / `settlement` / `support_ticket` 升级;
小程序新增 `domestic/*` / `warranties` / `addresses`;Admin 静态站定版。

### 7/15-7/17 — 支付 + 认证 + 审核
`pay_order` / `wechat_pay` 服务成型;`payment` 路由接通;门店 dashboard 收尾;
`auth` 路由收尾(账号密码登录 + 审核账号);`wechat-review-guide.md` 落盘。

### 7/22-7/23 — 提审冲刺
后端 `business` / `order` / `profit` / `store` 集中更新;客户侧 6+ 页全更新;
新增 `account/personal-info` / `account/settings`;登录页合规修正
(去除"微信"字样 / 换电话听筒图标 / 文案改"手机号快捷登录");
新增 `scripts/test_platform_flows.py` / `scripts/seed_demo_data.py`。

### 8/9 — 文档归位 + P0/P1 消化
根目录 `README.md` + `docs/progress.md`;H5 批量截图(9 角色 65 张);
全链路测试 6/6;提审前核对 13/13;ledger 语义 bug + 告警去重;
部署脚本化;`core/auth.py` 提取 + admin/wallet 加鉴权(15/15);
监控告警(Prometheus/Alertmanager/Grafana);安全头审计;CI/CD;
结构化日志(18/18);法务材料 + 协议版本管理(37/37);
alembic 初始迁移(22/22);微信支付诊断与容错硬化(9/9)。

### 8/14-8/18 — 登录活跃度 + 发布包
`users.last_login_at` 字段 + 4 个登录端点写入;打包 `release-20260818.tgz`;
`scripts/review_audit.js` / `test_platform_flows.py` 同步更新。

### 8/20 ~ 9/30 — 无代码改动
期间只做过线上排查(用户 21 工单、nginx 日志、告警核对),未产生提交。

### 10/12 — 版本管理归位
把 8/18 之后积压的全部改动分成两个提交入库并推送:`a0a992e` 安全收口(含 10-05 ~ 10-07
的后端实现)、`4a3330a` 多角色(前端 + 文档 + 测试),并订正 README/progress 里
「线上仍跑旧代码」的过时说法。此前 GitHub 上只有 8/18 的两个提交。
