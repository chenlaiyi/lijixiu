# 部署

## 目录

- `nginx.conf` — 反代 + SSL 终止 + 安全 headers + 静态服务
- `backup.sh` — 每日 03:00 数据库 + 上传目录备份,保留 7 天
- `../Dockerfile` — 后端镜像(Python 3.12-slim,4 uvicorn worker)
- `../docker-compose.yml` — api + nginx + 可选 backup cron
- `../scripts/deploy.sh` — 部署编排

## 快速开始

### 本地起 staging

```bash
# 1. 准备 .env
cp .env.example .env
# 改 PAYMENT_ALLOW_MOCK=true SMS_PROVIDER=debug

# 2. 启
docker compose up -d --build

# 3. 看
docker compose ps
docker compose logs -f api
curl http://localhost/health
```

### 跑备份服务(可选)

```bash
docker compose --profile backup up -d
```

### 部署生产

```bash
# 在服务器上
git pull
ENV=production ./scripts/deploy.sh
```

## SSL 证书

把 `fullchain.pem` + `privkey.pem` 放到 `deploy/certs/`,nginx 配置里加 `listen 443 ssl;` 段(当前默认 80)。

可以用 `acme.sh` 申请免费证书:
```bash
acme.sh --issue -d your-domain --nginx
cp ~/.acme.sh/your-domain/fullchain.cer deploy/certs/
cp ~/.acme.sh/your-domain/your-domain.key deploy/certs/
```

## 首次部署后必做

1. **填真实支付配置**(`.env` 里的 `WECHAT_PAY_*`)
2. **生成 htpasswd**:`htpasswd -c deploy/certs/.htpasswd admin`
3. **申请 SSL 证书**(上面)
4. **跑种子数据**:`docker compose exec api python scripts/seed_demo_data.py https://your-domain`
5. **配外部监控**:Prometheus / 阿里云监控,接 `/metrics`
6. **配告警通知**:钉钉 / 飞书机器人,消费 `/api/v1/admin/alerts?resolved=false`
7. **首次对账**:`curl -X POST https://your-domain/api/v1/admin/reconcile/run`
