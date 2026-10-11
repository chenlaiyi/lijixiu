# 生产 nginx 安全加固(2026-10-06)

线上 `x.iddg.cn` 的 nginx 由**宝塔面板**管理,配置文件位于
`/www/server/panel/vhost/nginx/x.iddg.cn.conf`。

## 改动前状态(2026-10-06 实测)

- 整个 `location /` 反代到 `http://127.0.0.1:8112`(uvicorn),`/docs`、`/redoc`、
  `/openapi.json`、`/metrics`、`/metrics/prom` 全都由后端直接暴露 → **公网裸访问**
- **没有任何安全响应头**
- `/admin/` 用 basic auth 保护,但 `alias` 指向 `/www/wwwroot/xiulijiu_api/admin-web/`,
  那是 **7/12 的旧副本**(不含 2026-10-05 加的后台登录态)
- 安全审计 `node scripts/security_audit.js`:**8/19**

## 改动内容

### 1. 新增 snippet 文件

`/www/server/nginx/conf/snippets/xjl-security-headers.conf`

包含:

| 类别 | 内容 |
|---|---|
| 安全头 | `X-Frame-Options: SAMEORIGIN`、`X-Content-Type-Options: nosniff`、`Strict-Transport-Security: max-age=31536000; includeSubDomains`、`Referrer-Policy: strict-origin-when-cross-origin`、`Permissions-Policy`、`Content-Security-Policy: frame-ancestors 'self'` |
| 服务端标识 | `server_tokens off`、`proxy_hide_header Server` |
| 敏感端点鉴权 | `location = /docs`、`= /redoc`、`= /openapi.json` → basic auth(realm `Xiulijiu Internal`) |
| 指标鉴权 | `location = /metrics`、`= /metrics/prom` → basic auth(realm `Xiulijiu Metrics`) |

basic auth 复用 `/www/wwwroot/xiulijiu_api/shared/admin.htpasswd`(**用户名 `admin`**,
和 `/admin/` 同一套凭据),没有新建第二套密码。

> CSP 只用了 `frame-ancestors 'self'` —— 它不影响页面自身资源加载,
> 因此不会破坏 Swagger UI / H5 / Admin。要做完整 CSP(script-src 等)必须先在
> 真实浏览器里过一遍 H5 和 Admin,别直接上严格的 `default-src`。

### 2. 站点配置里加一行 include

在 `x.iddg.cn.conf` 的 **443 server 块**、第一个 location 之前插入:

```nginx
include /www/server/nginx/conf/snippets/xjl-security-headers.conf;
```

### 3. `admin-web` 切到当前 release

宝塔的 `/admin/` alias 原来指向独立目录,任何 release 都不会更新它。
已改为软链,跟着 release 一起走:

```bash
mv /www/wwwroot/xiulijiu_api/admin-web /www/wwwroot/xiulijiu_api/admin-web.old-<时间戳>
ln -sfn /www/wwwroot/xiulijiu_api/current/admin-web /www/wwwroot/xiulijiu_api/admin-web
```

## 重载方式(重要)

这台机器的 nginx **不是 systemd 单元**,`systemctl reload nginx` 会报
`Job for nginx.service invalid`。正确方式:

```bash
/www/server/nginx/sbin/nginx -t && /www/server/nginx/sbin/nginx -s reload
# 或者:/etc/init.d/nginx reload
```

## 改动后验收(2026-10-06)

安全审计 **18/19**(从 8/19),仅剩 `Server` 头一条 WARN。

| 检查 | 结果 |
|---|---|
| `X-Frame-Options` / `X-Content-Type-Options` / `HSTS` / `CSP` / `Referrer-Policy` / `Permissions-Policy` | 全部 OK |
| `/docs` `/redoc` `/openapi.json` | **401**(`WWW-Authenticate: Basic realm="Xiulijiu Internal"`) |
| `/metrics` `/metrics/prom` | **401** |
| `/admin/` `/admin/index.html` | 401(basic auth) |
| `/` `/health` `/h5/` | 200(未受影响) |
| 业务接口 | 无 token 401;带 admin token 200(未受影响) |
| 服务器本机经 nginx 访问 `/metrics` | **200**(白名单放行,见下) |

## 指标端点的内网白名单(2026-10-06 补)

给 `/metrics` 加 basic auth 会让服务器本地/内网的监控抓取也 401。
已改为 `satisfy any` + `allow` 内网段:

```nginx
location = /metrics {
    satisfy any;
    allow 127.0.0.1;  allow ::1;
    allow 10.0.0.0/8; allow 172.16.0.0/12; allow 192.168.0.0/16;
    deny all;
    auth_basic "Xiulijiu Metrics";
    auth_basic_user_file /www/wwwroot/xiulijiu_api/shared/admin.htpasswd;
    proxy_pass http://127.0.0.1:8112;
    ...
}
```

`/metrics/prom` 同样处理。效果:

- 公网访问 → **401**(安全审计仍 18/19)
- 服务器本机 / 内网 → **200**(实测 `curl -k https://127.0.0.1/metrics -H 'Host: x.iddg.cn'` = 200)

> **实测结论:这台服务器上目前没有任何监控组件** ——
> `which prometheus/alertmanager/grafana` 全空,`docker ps` 无监控容器,
> nginx 配置里也没有任何引用 `/metrics/prom` 的地方。
> 也就是说 `deploy/prometheus`、`deploy/grafana` 那套配置**尚未落地到生产**,
> 「监控抓取 401」的风险当前不存在。白名单是为将来接入时准备的。
> 如果以后接外部 Prometheus,把它的出口 IP 加进 `allow` 即可,无需配密码。

## 遗留

1. **`Server` 头仍暴露**(nginx 自己发的,`nginx/1.26.1`)。
   要彻底隐藏需要 `headers-more-nginx-module` 或换 openresty,
   宝塔自带的是普通 nginx,没编进去。属低风险,未处理。
2. **CSP 仍是保守版**(只有 `frame-ancestors`)。要上完整 CSP 需先在真实浏览器
   验证 H5 / Admin / Swagger 三个界面。
3. **本次未验证 basic auth 凭据本身**:我没有 `admin.htpasswd` 里的明文密码,
   所以只确认了「无凭据返回 401 + 响应头带 `WWW-Authenticate`」。
   请用你手上的 `/admin/` 密码试一下 `/docs`(应能打开 Swagger)。
4. **监控体系未落地**:生产没装 Prometheus/Alertmanager/Grafana,
   `scripts/alert_watcher.js` 也未确认在跑。仓库里的监控配置属于「写好了但没部署」。

5. 改动前的站点配置备份在 `/www/server/panel/vhost/nginx/x.iddg.cn.conf.bak-<时间戳>`,
   回滚只需还原该文件并删掉 include 行,然后 `nginx -t && -s reload`。
