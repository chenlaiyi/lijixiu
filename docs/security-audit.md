# 安全头 + 鉴权审计

> 跑测时间:2026-08-09(初版) / **2026-10-06(复测 18/19)**
> 目标环境:https://x.iddg.cn
> 工具:`scripts/security_audit.js`(19 项检查)

## 2026-10-06 复测结果:**18/19 通过**

三阶段变化:

| 时间 | 通过 | 说明 |
|---|---|---|
| 2026-08-09 | 5/19 | 初版基线 |
| 2026-10-06(部署鉴权收口后) | 8/19 | 鉴权相关 6 项转绿 |
| 2026-10-06(nginx 加固后) | **18/19** | 安全头 6 项 + `/docs` `/redoc` `/openapi.json` `/metrics` 全部转绿 |

唯一剩余:**`Server` 头仍暴露**(`nginx/1.26.1`),WARN 级。
宝塔自带普通 nginx,未编 `headers-more-nginx-module`,彻底隐藏需换 openresty。

nginx 侧改动明细见 [nginx-hardening-2026-10.md](nginx-hardening-2026-10.md)。

---

## 2026-10-05 复测补记(鉴权部分)

本次独立复测发现的**核心问题不是安全头,而是后端鉴权** —— 详见
[security-hardening-2026-10.md](security-hardening-2026-10.md)。

- 上面 #16 / #17 / #18 的结论**低估了范围**:当时只点了 3 个端点,
  实际是 **71 个写接口 + 6 类含 PII 读接口**全部零鉴权,
  并且可以用无 token 的 `PATCH /api/v1/users/{id}` 把自己提权成 `platform_admin`。
  → 本轮已在代码层全量收口(12 个路由模块)。
- #9-#12 的结论**至今仍然成立**:线上 `/docs`、`/redoc`、`/openapi.json`、`/metrics`
  依然 200 裸访问。仓库里的 `deploy/nginx.conf` 写了 `auth_basic`,但**线上 nginx 没有用这份配置**
  (或 `.htpasswd` 未生效),需要在服务器侧核对。
- 新增一条当时的审计没覆盖的 P0:生产 `SMS_PROVIDER=debug` 把固定验证码回显在
  `/api/v1/auth/sms/request` 响应里 → 任意账号接管。本轮已加 `ALLOW_SMS_DEBUG_ENDPOINT` 闸门。

> 结论:安全头部分继续按下面的清单推进;**鉴权部分以 2026-10-05 的记录为准**。

---

## 结果(2026-08-09):**5/19 通过**(12 个 required 项未过)

| # | 端点 | 检查 | 当前 | 期望 | 状态 |
|---|---|---|---|---|---|
| 1 | / | X-Frame-Options | 缺失 | DENY/SAMEORIGIN | ❌ FAIL |
| 2 | / | X-Content-Type-Options | 缺失 | nosniff | ❌ FAIL |
| 3 | / | Strict-Transport-Security | 缺失 | max-age=31536000 | ❌ FAIL |
| 4 | / | Content-Security-Policy | 缺失 | 严格策略 | ❌ FAIL |
| 5 | / | Referrer-Policy | 缺失 | strict-origin-when-cross-origin | ❌ FAIL |
| 6 | / | Permissions-Policy | 缺失 | 限制浏览器 API | ⚠️ WARN |
| 7 | / | Server 头 | nginx 出现 | 应隐藏 | ⚠️ WARN |
| 8 | / | X-Powered-By | 未出现 | 应隐藏 | ✅ OK |
| 9 | /docs | basic auth | **200 公网可访问** | 401 | ❌ FAIL(10/05 仍未修) |
| 10 | /redoc | basic auth | **200** | 401 | ❌ FAIL(10/05 仍未修) |
| 11 | /openapi.json | basic auth | **200** | 401 | ❌ FAIL(10/05 仍未修) |
| 12 | /metrics | basic auth | **200** | 401 | ❌ FAIL(10/05 仍未修) |
| 13 | /admin/ | basic auth | 401 | 401 | ✅ OK(线上已有) |
| 14 | /admin/index.html | basic auth | 401 | 401 | ✅ OK |
| 15 | /.env | 不应暴露 | 404 | 404/401 | ✅ OK |
| 16 | /api/v1/wallet/balance/1 | 自己/admin | **200 任何人可查** | 401 | ✅ 10/05 已修 |
| 17 | /api/v1/admin/alerts | admin only | **200 任何人可查** | 401 | ✅ 10/05 已修(代码层,待部署) |
| 18 | /api/v1/admin/reconcile/run (POST) | admin only | **200 任何人对账** | 401 | ✅ 10/05 已修(代码层,待部署) |
| 19 | /health | 应 200 | 200 | 200 | ✅ OK |

## 根因

线上 nginx 当前的 server_tokens off 起作用了(Server 头被部分隐藏),但:
- 没有 `add_header` 任何安全响应头
- `/docs` `/redoc` `/openapi.json` `/metrics` 没有任何 auth_basic
- `wallet/balance/{user_id}` 等后端端点也没鉴权

这跟"商用就绪体检"里 P0 #1 的发现完全一致。

## 修复路径

### 1. 部署 `deploy/nginx.conf`(已写好,8/9 完成)

新 nginx 配置包含:
- 6 个安全响应头(HSTS / X-Frame / X-Content-Type / CSP / Referrer-Policy / Permissions-Policy)
- `/docs` `/redoc` `/openapi.json` basic auth
- `/metrics` basic auth
- 登录端点限速(10 req/m,防爆破)
- API 限速(60 req/m,防滥用)
- `server_tokens off` + `proxy_hide_header Server`
- HTTP → HTTPS 301 重定向

### 2. 部署 P0 收尾的鉴权代码(已完成,8/9 完成)

`app/core/auth.py` + `app/routers/admin.py` + `app/routers/wallet.py` 的鉴权改动:
- `/api/v1/admin/*` 全部 `require_admin`
- `/api/v1/wallet/balance/{user_id}` 自己或 admin
- `/api/v1/wallet/ledger/{user_id}` 自己或 admin
- `/api/v1/wallet/withdraw/{user_id}` 自己或 admin
- `/api/v1/wallet/withdraw/{id}/review` 仅 admin
- 等

### 3. 生成 htpasswd(部署前一步)

```bash
# 容器内执行一次
docker compose exec api apk add --no-cache apache2-utils
docker compose exec api htpasswd -cb /etc/nginx/certs/.htpasswd admin 'YOUR_SECURE_PASSWORD'
```

## 重跑审计

```bash
# 部署后
node scripts/security_audit.js
```

期望结果:**19/19 全过**。

## 上线 checklist

- [ ] 部署 `deploy/nginx.conf`(用新文件替换线上 nginx 配置)
- [ ] 生成 `.htpasswd`
- [ ] 部署 2026-10-05 的鉴权收口代码(见 [deployment-runbook.md](deployment-runbook.md) § 2.13)
- [ ] `/admin/` 后台登录框粘贴管理员 token,确认提现/对账视图可用
- [ ] 重跑 `node scripts/security_audit.js` 确认 19/19
- [ ] 浏览器开发者工具看 / 响应头确认 CSP / HSTS 生效
- [ ] `curl -I https://your-domain/.env` 确认 404/401
- [ ] 无 token 试 `curl https://your-domain/api/v1/users` 与 `/api/v1/orders` 确认 401
