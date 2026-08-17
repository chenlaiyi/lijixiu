# 部署 Runbook — `https://x.iddg.cn` (8.134.99.53)

> 2026-08-09 落地 · 一份从 0 到 production 的完整 checklist

## 0. 部署形态

```
                 ┌─────────────┐
   Internet ────▶│   nginx     │ (SSL 终止 + 安全头 + 限速)
                 │  8.134.99.53│
                 └──────┬──────┘
                        │
            ┌───────────┼───────────┐
            ▼                       ▼
   ┌─────────────────┐    ┌────────────────┐
   │  backend:api    │    │  admin-web/    │  (静态)
   │  (4 uvicorn     │    │  h5/           │
   │   workers)      │    └────────────────┘
   └────────┬────────┘
            │
   ┌────────▼────────┐
   │  mysql:8.0      │  (数据 + 备份)
   │  (3306 内网)    │
   └─────────────────┘
```

`prometheus + alertmanager + grafana` 可选,用 `docker compose --profile monitoring up -d` 启。

---

## 1. 服务器一次性初始化(只在第一台机器上做)

### 1.1 操作系统

- Ubuntu 22.04 LTS / 24.04 LTS,root 或 sudo 权限
- 最小 2C4G,生产建议 4C8G + 80G SSD
- 开放端口:`80 443 22`(SSH 限定 IP)

### 1.2 安装基础

```bash
# docker
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin

# 常用工具
apt install -y git curl jq ufw fail2ban logrotate

# 防火墙
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

### 1.3 申请 SSL 证书(acme.sh 免费)

```bash
# 装 acme.sh
curl https://get.acme.sh | sh -s email=ops@x.iddg.cn
source ~/.bashrc

# 申请 + 部署到 nginx
acme.sh --issue -d x.iddg.cn --nginx
# 或者用 DNS API(更稳,不需要 nginx 80 端口)
# acme.sh --issue -d x.iddg.cn --dns dns_cf
```

把证书放好:

```bash
mkdir -p /opt/xiulijiu/deploy/certs
acme.sh --install-cert -d x.iddg.cn \
  --cert-file /opt/xiulijiu/deploy/certs/fullchain.pem \
  --key-file  /opt/xiulijiu/deploy/certs/privkey.pem \
  --reloadcmd "docker compose -f /opt/xiulijiu/docker-compose.yml exec nginx nginx -s reload"
```

### 1.4 拉代码 + 配 `.env`

```bash
cd /opt
git clone https://github.com/<your-org>/xiulijiu.git
cd xiulijiu
cp .env.example .env
chmod 600 .env
# 用 vim / VSCode Remote 改 .env
```

**`.env` 必须改的字段**(见 `.env.example`):

| 字段 | 值 | 来源 |
|---|---|---|
| `DATABASE_URL` | `mysql+aiomysql://xiulijiu:STRONG_PWD@mysql:3306/xiulijiu` | 自定 |
| `DEBUG` | `false` | — |
| `AUTH_SECRET` | `openssl rand -hex 48` | 48 字节随机 |
| `WECHAT_PAY_MCH_ID` | 1xxxxxxxxx | 微信商户平台 |
| `WECHAT_PAY_API_V3_KEY` | 32 字节 | 微信商户平台 → API 安全 |
| `WECHAT_PAY_CERT_SERIAL_NO` | 从证书解析 | `openssl x509 -in apiclient_cert.pem -noout -serial` |
| `WECHAT_APP_SECRET` | 32 字节 | 微信小程序后台 |
| `WECHAT_REVIEW_ACCOUNT` / `WECHAT_REVIEW_PASSWORD` | 审核专用 | 自己设 |

### 1.4.1 部署前 `validate_env` 校验(2026-08-09 新增)

```bash
python3 scripts/validate_env.py --strict
```

- 默认 dev 模式:`FILL_*` 占位只警告,本地调试可放行
- `--strict` 模式:任何 `FILL_*` 占位 + 弱 `AUTH_SECRET` + 非 https `PUBLIC_BASE_URL` + `sqlite` 都 fail
- `deploy.sh` 在 staging/production 模式下自动跑 strict 校验,**未通过直接 exit 1,不会启动容器**
- 常见错误处理:
  - `PLACEHOLDER: WECHAT_PAY_API_V3_KEY` → 去商户平台拿 v3 key
  - `WEAK_SECRET: AUTH_SECRET` → `openssl rand -hex 48` 重生
  - `DATABASE_URL uses sqlite` → 改成 mysql URL

### 1.5 放微信支付证书

```bash
mkdir -p /opt/xiulijiu/cert
# 把从商户平台下载的 apiclient_cert.pem / apiclient_key.pem 拷进来
scp apiclient_*.pem root@8.134.99.53:/opt/xiulijiu/cert/
chmod 600 /opt/xiulijiu/cert/apiclient_*
```

### 1.6 生成 nginx basic auth(防 /admin / /docs 公网暴露)

```bash
apt install -y apache2-utils
htpasswd -c deploy/certs/.htpasswd admin
# 输两次密码
```

### 1.7 启

```bash
cd /opt/xiulijiu
ENV=production docker compose up -d --build
```

---

## 2. 首次部署后必做(15 步)

按顺序走,卡哪步看 § 5 FAQ。

- [ ] **2.1** `docker compose ps` — api / nginx / mysql 都 healthy
- [ ] **2.2** `curl https://x.iddg.cn/health` — `{"status":"ok"}`
- [ ] **2.3** `docker compose exec api alembic upgrade head` — 跑迁移
- [ ] **2.4** `docker compose exec api python scripts/seed_demo_data.py https://x.iddg.cn` — 种 demo 数据
- [ ] **2.5** 浏览器开 `https://x.iddg.cn/admin-web/` — basic auth 弹窗,登录后看到 dashboard
- [ ] **2.6** 跑对账:管理员 token → `POST /api/v1/admin/reconcile/run` — 应该全 OK
- [ ] **2.7** `curl https://x.iddg.cn/metrics/prom` — Prometheus 格式输出
- [ ] **2.8** 浏览器开 `https://x.iddg.cn/docs` — 应该要 basic auth(不能裸访问)
- [ ] **2.9** 跑安全审计:`node scripts/security_audit.js https://x.iddg.cn` — 19/19 全过
- [ ] **2.10** 配外部监控:接 `/metrics/prom` 到你的 Prometheus / 阿里云 ARMS
- [ ] **2.11** 配告警 webhook:钉钉/飞书机器人 URL 填到 alert_watcher 配置
- [ ] **2.12** `node scripts/alert_watcher.js https://x.iddg.cn` — daemon 起来(用 systemd / supervisord 保活)
- [ ] **2.12.5** 验证微信支付:`python scripts/check_wechat_pay.py --network` 看到 `platform_certs_count: 1+` 才算绿;若还是 403,用 `GET /api/v1/admin/wechat-pay/diagnostics`(admin token)看 `consecutive_failures` 是否在涨
- [ ] **2.12.6** 跑支付链路冒烟:`./scripts/payment_smoke.sh` — 端到端测 health / 配置 / 鉴权 / 对账 / 指标 / 告警,带真 admin+customer token 跑应当 10+/13 PASS;剩 FAIL 都是凭据相关(填了凭据 + 95017 修完应该全 PASS)
- [ ] **2.13** 走一笔 0.01 元真实支付:小程序下单 → 支付 → 查 `pay_orders.out_trade_no` → 看微信商户平台回执
- [ ] **2.14** 走一笔 0.01 元真实退款
- [ ] **2.15** 确认每日 03:00 备份 cron 在跑:`docker compose --profile backup ps`

---

## 3. 日常部署(代码改了之后)

### 3.1 自动(推荐,接 GitHub Actions)

`main` 分支 push → `.github/workflows/deploy.yml` 自动跑 `lint → test → build → deploy staging`。

生产部署走手动 dispatch + approval。

### 3.2 手动

```bash
ssh root@8.134.99.53
cd /opt/xiulijiu
git pull
ENV=production ./scripts/deploy.sh
```

`scripts/deploy.sh` 会:
1. 检查 docker / compose / .env
2. 备份当前 db(`/data/db/pre-deploy-YYYYmmdd_HHMMSS.db`)
3. build 新镜像
4. 滚动重启 api
5. 等待 healthy(10 次 × 3 秒)
6. 冒烟 `/health`
7. 跑对账检查
8. 启 nginx

### 3.3 回滚

```bash
# 1. 镜像回滚
cd /opt/xiulijiu
git log --oneline -10          # 找上一个稳定版 commit
git checkout <prev-commit>
ENV=production ./scripts/deploy.sh

# 2. 数据库回滚(谨慎!)
docker compose exec api alembic downgrade -1   # 回滚一步
# 或指定版本
docker compose exec api alembic downgrade <revision_id>
```

更稳的方式:启新容器跑旧镜像(`docker compose up -d --no-deps --force-recreate api`),db 不动。

---

## 4. 运维手册(线上出问题先看这)

### 4.1 看健康

```bash
# 容器状态
docker compose ps

# 日志
docker compose logs -f --tail=100 api
docker compose logs -f --tail=100 nginx

# 健康
curl https://x.iddg.cn/health
```

### 4.2 看指标

```bash
curl https://x.iddg.cn/metrics/prom | head -50
```

关键指标:
- `xiulijiu_http_request_duration_seconds_bucket{...}` — 接口延迟
- `xiulijiu_orders_total` — 订单数
- `xiulijiu_alerts_active` — 未处理告警
- `xiulijiu_wallet_balance_total` — 全平台钱包余额总和

### 4.3 重启某服务

```bash
docker compose restart api
docker compose restart nginx
docker compose restart mysql  # ⚠️ 会停 5-10 秒,慎用
```

### 4.4 数据库备份 + 恢复

手动备份:

```bash
docker compose exec mysql mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" xiulijiu | gzip > /backup/xiulijiu_$(date +%Y%m%d_%H%M%S).sql.gz
```

自动备份:`deploy/backup.sh` 已挂在 cron,每天 03:00 跑,保留 7 天。

恢复:

```bash
gunzip -c /backup/xiulijiu_xxx.sql.gz | docker compose exec -T mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" xiulijiu
```

### 4.5 清告警

```bash
# 1. 看未处理
curl -H "Authorization: Bearer $ADMIN_TOKEN" https://x.iddg.cn/api/v1/admin/alerts

# 2. 跑对账
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" https://x.iddg.cn/api/v1/admin/reconcile/run

# 3. 手工调账(谨慎)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id":123,"amount":50.0,"remark":"manual fix"}' \
  https://x.iddg.cn/api/v1/admin/wallet/adjust
```

### 4.6 日志位置

- 应用 stdout → `docker compose logs` (JSON 格式,带 request_id / trace_id)
- nginx 访问日志 → `deploy/nginx/logs/access.log`(挂卷)
- nginx 错误日志 → `deploy/nginx/logs/error.log`
- MySQL binlog → `mysql:/var/lib/mysql`(挂卷)

按 request_id 查:

```bash
docker compose logs api | grep '"request_id":"abc123"'
```

---

## 5. FAQ

### Q1. /health 返回 503

**原因**:数据库连不上 / alembic 没跑 / 表损坏。

```bash
docker compose exec api alembic current    # 看当前版本
docker compose exec api alembic upgrade head
docker compose logs mysql | tail -50
```

### Q2. 支付回调 401

**原因**:`WECHAT_PAY_API_V3_KEY` 配错 / 回调 URL 没在商户平台白名单。

```bash
# 验证 key
docker compose exec api python -c "
from app.core.config import settings
print('MCH:', settings.WECHAT_PAY_MCH_ID)
print('KEY len:', len(settings.WECHAT_PAY_API_V3_KEY or ''))
"
```

### Q3. 502 Bad Gateway

**原因**:api 容器挂了 / 没起来。

```bash
docker compose ps api
docker compose logs --tail=100 api
docker compose restart api
```

### Q4. 上传文件 413

**原因**:nginx 限制太小。改 `deploy/nginx.conf` 的 `client_max_body_size 20M;` → 重启 nginx。

### Q5. /docs 能裸访问

**原因**:nginx basic auth 没配。检查 `deploy/nginx.conf` 里的 `auth_basic` 段 + `deploy/certs/.htpasswd` 是否存在。

### Q6. 数据库连接耗尽

**原因**:没设连接池 / 长连接没释放。

```bash
docker compose exec mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SHOW STATUS LIKE 'Threads_connected';"
```

调整 `app/core/database.py` 的 `pool_size` + `pool_recycle`(默认 5+10,生产可以 20+300)。

### Q7. 告警 webhook 没收到

```bash
# 1. 看 watcher 日志
journalctl -u xiulijiu-alert-watcher -f
# 或
docker compose logs alert-watcher

# 2. 手动测 webhook
curl -X POST https://oapi.dingtalk.com/robot/send?access_token=XXX \
  -H "Content-Type: application/json" \
  -d '{"msgtype":"text","text":{"content":"test"}}'
```

### Q8. 微信支付 "平台证书已过期失效" 🔴 已知生产阻塞

**症状**:`python scripts/check_wechat_pay.py --network` 返回:

```
HTTP 403: {"code":"NOT_ENOUGH","message":"平台证书已过期失效，请联系微信支付技术支持。"}
```

**根因**:WeChat Pay 在 `/v3/certificates` 端点返回的平台证书被微信侧认为"过期"。这通常发生在:
1. 商户号新开通(7/3 刚注册,初始化未完成)
2. 微信缓存 / 同步问题
3. 商户号被风控冻结

**影响**:即便 `WECHAT_PAY_API_V3_KEY` / `WECHAT_APP_SECRET` 配齐,`/v3/certificates` 还是 403,导致:
- 支付回调验签失败(因为我们用平台证书验签)
- 退款 / 提现 / 查询全部挂

**临时绕开**(上线前必做):

1. 让运营同学从微信商户平台 → API 安全 → 平台证书管理,下载最新的 `wechatpay_cert.pem`
2. 放到服务器 `/opt/xiulijiu/cert/wechatpay_cert.pem`
3. 在 `.env` 加:
   ```
   WECHAT_PAY_PLATFORM_CERT_PATH=cert/wechatpay_cert.pem
   ```
4. 代码 (`app/services/wechat_pay.py:263`) 会优先用本地证书,绕开下载
5. 重启 api

**真解决**:打微信支付技术支持 **95017** 转 2(商户),让后台同事帮刷一下 platform cert。刷完后:
- `python scripts/check_wechat_pay.py --network` 应该返回 "platform_certs_count: 1+"
- `first_cert_expires` 应该是未来 1-3 年

**预防**:每次证书操作前先跑 `check_wechat_pay.py --network`,确保 5 分钟内是绿的就操作。

---

## 6. 关键文件清单(部署前 sanity check)

```
✅ Dockerfile                                  # 多阶段 build,非 root 用户
✅ docker-compose.yml                          # api + nginx + mysql + backup
✅ deploy/nginx.conf                           # SSL + 安全头 + 限速 + basic auth
✅ deploy/backup.sh                            # 每日 03:00 备份
✅ deploy/prometheus/                          # 监控配置
✅ deploy/grafana/                             # dashboard
✅ scripts/deploy.sh                           # 部署编排
✅ scripts/reconcile_dryrun.js                 # 对账预演
✅ scripts/reconcile_apply.js                  # 对账修复
✅ scripts/alert_watcher.js                    # 告警推送
✅ scripts/security_audit.js                   # 19 项安全审计
✅ scripts/seed_demo_data.py                   # demo 数据种子
✅ scripts/migrate_sqlite_to_mysql.py          # SQLite→MySQL 迁移
✅ .github/workflows/{ci,deploy,miniprogram}.yml  # CI/CD
✅ alembic.ini + migrations/                   # 40 张表迁移
✅ docs/{db-migration,monitoring,logging,security-audit,legal/*}.md
```

---

## 7. 上线 checklist(给业务方)

- [ ] 工商营业执照 → 增值电信业务许可证(上门服务类)
- [ ] ICP 备案号(`x.iddg.cn`)
- [ ] 公安备案
- [ ] 用户协议 / 隐私政策 → 法务出 PDF
- [ ] 客服电话 / 邮箱
- [ ] 投诉处理流程
- [ ] 退款 / 提现 SLA
- [ ] 微信支付商户号 + 提现产品开通
- [ ] 小程序类目 → "工具 → 效率 / 生活服务"(选对类目审核更快)
- [ ] 测试号 / 体验号 / 正式号 三套环境
