# 管理后台登录方式变更(2026-10-07)

## 为什么改

原来 `/admin/` 的登录框要求粘贴一串 **平台管理员 Bearer token**,
而这串 token 只能通过调 `POST /api/v1/auth/wechat-login` 拿到:

```json
{"code": "18800000000:演示管理员:admin"}
```

对运营来说这太绕了 —— 要会调接口、要找到演示手机号、还要处理 `Bearer` 前缀。
现在改成**填账号 + 密码**,和普通后台一样。

## 改了什么

### 1. 新增后端接口 `POST /api/v1/auth/admin-login`

```json
// 请求
{"account": "admin", "password": "……"}

// 响应(200)
{"token": "……", "user": {"id": 3, "name": "演示管理员", "business_role": "platform_admin", ...}}
```

凭据来自 `.env`:

| 键 | 说明 |
|---|---|
| `ADMIN_WEB_ACCOUNT` | 后台账号(默认 `admin`) |
| `ADMIN_WEB_PASSWORD` | 后台密码(明文,与 `WECHAT_REVIEW_PASSWORD` 做法一致) |
| `ADMIN_WEB_PHONE` | 登录后映射到的用户手机号,**必须**是演示白名单里 `platform_admin` 的角色(默认 `18800000000`) |

行为:

- 账号或密码错 → **401**
- 没配 `.env` → **503 `Admin login is not configured`**
- 手机号不在白名单 / 角色不是 `platform_admin` → **503**
- 比较用 `hmac.compare_digest`(定时安全),与 `review-login` 一致

### 2. 后台登录框改成账号密码

[`admin-web/app.js`](../admin-web/app.js) 的登录卡片:

- 主表单:`账号` + `密码` → 提交到 `/api/v1/auth/admin-login`
- **保留 token 登录**作为应急入口(折叠在「改用 Token 登录(应急)」里)
- 登录成功后 token 仍存 `localStorage`,后续请求自动带 `Authorization`,
  401 时自动退回登录页 —— 这部分逻辑没动

### 3. 新增配置脚本

```bash
python scripts/set_admin_account.py                    # 写 ./.env,随机 16 位密码
python scripts/set_admin_account.py --account ops --password 'MyPass123!'
python scripts/set_admin_account.py --dry-run
```

与 `scripts/set_review_account.py` 对称,同样是原位替换、保留其余行。

### 4. 环境校验登记

`ADMIN_WEB_ACCOUNT` / `ADMIN_WEB_PASSWORD` 加入 `env_validator.RECOMMENDED`,
没配时 `/health/env` 会给出 RECOMMENDED 警告(不阻塞启动)。

## 后台现在是「一层」鉴权(2026-10-07 最终形态)

原先是两层,第 1 层 nginx basic auth 已按需求**移除**:

```
第 1 层  ~~nginx basic auth~~          ← 2026-10-07 已删除(location ^~ /admin/ 里的 auth_basic 两行)
第 2 层  后台登录卡片:账号 + 密码 → /api/v1/auth/admin-login
```

### 为什么第 2 层不能去

后台调管理接口必须带 `Bearer` token。如果只靠 nginx basic auth,
浏览器会把 `Authorization` 头占用来做 basic 认证,后台就没法再带 Bearer token,
管理接口全部 401。所以**后台登录卡片是必需的那一层**。

### 去掉 basic auth 的代价(已知并接受)

`/admin/`、`/admin/index.html`、`/admin/app.js`、`/admin/styles.css` 变成公网可读:

- 能看到后台的页面结构、接口路径、前端逻辑
- **拿不到任何业务数据**(数据全靠 API,而 API 无 token 一律 401)
- 已用审计断言把这个边界固化下来(见下)

### 审计断言(2026-10-07 调整)

`scripts/security_audit.js` 里原来把 `/admin/` 期望写成 401,改动后改为:

```js
{
  type: 'body', url: '/admin/', expectStatus: 200, required: true,
  mustInclude: ['立即修管理后台', 'app.js', '<body'],   // 页面外壳
  mustExclude: ['演示管理员', '18800000000', 'available_balance', '演示客户'],  // 真数据才算泄露
}
```

`type: 'body'` 是本轮新增的检查类型:同时校验状态码、必需标志、禁用标记。
这样「页面可读」和「数据不可泄露」两件事都被断言住,审计仍为 **18/19**
(唯一 WARN 是 nginx `Server` 头,与本次无关)。

> 注:登录表单由 `app.js` 动态渲染,不在 `index.html` 里 ——
> 所以 `mustInclude` 查的是页面外壳标志,不是 `auth-login` 这类 JS 内字符串。

## 验证记录(2026-10-07 线上实测)

| 检查 | 结果 |
|---|---|
| `/admin/` `/admin/index.html` `/admin/app.js` `/admin/styles.css` | 全部 **200**(无需 basic auth) |
| `POST /api/v1/auth/admin-login` 正确凭据 | 200,`演示管理员` / `platform_admin` |
| 错误密码 / 错误账号 | 401 / 401 |
| 未配置 `ADMIN_WEB_*`(本地另起进程) | 503 `Admin login is not configured` |
| 无 token 调 `/wallet/withdrawals`、`/admin/alerts`、`/users` | 全部 **401** |
| 有 token 调 `/wallet/withdrawals` | 200 |
| 普通客户 token 调 `/admin/alerts` | 403 |
| `/docs` `/redoc` `/openapi.json` `/metrics` | 仍 **401**(snippet 里的鉴权未动) |
| `/health` | 200 |
| 安全审计 | **18/19** |

回归:`tests/test_auth_admin.py` 从 15 项扩到 **22 项**(新增 6 项覆盖
未配置 503 / 正确 200 / 角色校验 / token 可用 / 错误密码 401 / 错误账号 401)。

## 🔴 真正的「两层」根因:后台概览在 fetch `/metrics`(2026-10-07 修复)

删掉 nginx `auth_basic` 之后,用户反馈**仍然弹原生账号密码框**,而且顺序很关键:

> 「页面输入账号密码正确登录后,又有一个账号密码弹窗。」

也就是说:**不是打开页面时弹,是后台登录成功、渲染概览时才弹。**

### 根因

`admin-web/app.js` 的 `loadOverview()` 里:

```js
const [metrics, orders, users, ...] = await Promise.all([
  api("/metrics"),        // ← 就是这里
  ...
]);
```

后台概览页用 `/metrics`(JSON)填「订单总数 / 钱包数 / 总余额 / 活跃告警」等 KPI 卡片。
而 `/metrics` 在 2026-10-06 被我加了 **nginx basic auth**(防止公网裸访问指标)。

链路:后台登录成功 → 渲染概览 → `fetch("/metrics")` → nginx 返回
**401 + `WWW-Authenticate: Basic realm="Xiulijiu Metrics"`** →
**浏览器弹出原生认证框**。

所以用户看到的是「两层」,但第二层不是配置在那儿的登录页,而是**一个 API 请求撞上了 basic auth**。

### 修复

1. 把业务指标采集从 `app/main.py` 抽到 **`app/services/business_metrics.py`**
   (目的是让 admin 路由能复用;若留在 main.py,admin 路由 import main 会循环导入)
2. 新增 **`GET /api/v1/admin/metrics`**,`require_admin` 鉴权,与 `/metrics` 共用同一份口径
3. 后台 `loadOverview()` 改调 `/api/v1/admin/metrics`
4. `admin-web/index.html` 的 cache-bust 版本号 `?v=20261005-auth` → **`?v=20261007-metrics`**
   (HTML 本身没有 `Cache-Control`,不递增版本号的话浏览器会继续用缓存的旧 `app.js`)

### 验证

| 检查 | 结果 |
|---|---|
| 部署后 `app.js` 仍调 `api("/metrics")` | **无** |
| 部署后 `app.js` 含 `/api/v1/admin/metrics` | 是 |
| `/api/v1/admin/metrics` 带 token | 200,`orders_total=39 ...` |
| `/api/v1/admin/metrics` 无 token | 401 |
| `/api/v1/admin/metrics` 普通客户 token | 403 |
| 新端点与 `/metrics` 的 9 个业务字段 | **逐一相同**(`/metrics` 只多一个 `uptime_seconds`) |
| 后台会调的 10 个路径的 `WWW-Authenticate` | 全部 **—**(不再触发弹窗) |
| `/docs` `/metrics` `/openapi.json` 对照 | 仍 401 + `Basic realm` ✅ |

回归:`tests/test_auth_admin.py` 从 22 项扩到 **32 项**。

### 排查教训

**「弹窗」要先问清楚触发时机。** 我第一轮判断成"浏览器缓存了旧的 401",
方向错了 —— 真正原因是登录**之后**某个 API 请求撞上了 basic auth。
下次遇到同类问题,先确认:打开就弹 = 页面本身被拦;操作后才弹 = **某个 XHR 被拦**。

## 部署

- 应用:release `20261007101859`(含 `/api/v1/admin/metrics` 修复),
  上一个 `20261007095818`(账号密码登录)
- 备份:`backups/admin-login-20261007095818/`、`backups/admin-metrics-20261007101859/`
- nginx:站点配置备份在 `x.iddg.cn.conf.bak-noauth-20261007100339`
  (回滚只需还原该文件并 `nginx -t && nginx -s reload`)
- 改 `.env` 后必须 `systemctl restart xiulijiu-api` 才生效(settings 启动时读取)
- 本机 nginx **不是 systemd 单元**,reload 用 `/www/server/nginx/sbin/nginx -s reload`


