# 监控接入指南

> 2026-08-09 落地

## 架构

```
┌──────────────┐
│  FastAPI app │ /metrics/prom    /admin/alerts
│ (uvicorn)    ├────────────────┬────────────────┐
└──────────────┘                │                │
                                ▼                ▼
                    ┌──────────────────┐  ┌──────────────────┐
                    │   Prometheus     │  │  alert_watcher   │
                    │ (scrape 30s)     │  │  (poll 60s)      │
                    └────────┬─────────┘  └──────┬───────────┘
                             │                    │
                             ▼                    ▼
                    ┌──────────────────┐  ┌──────────────────┐
                    │  Alertmanager    │  │  钉钉 / 飞书     │
                    │ (route告警)      │  │  Webhook 群      │
                    └────────┬─────────┘  └──────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Grafana         │  http://your-host:3001
                    │  (dashboard)     │  admin / $GRAFANA_PASSWORD
                    └──────────────────┘
```

## 指标

### HTTP 指标(`/metrics/prom`,Prometheus 文本格式)

| 指标 | 类型 | 说明 |
|---|---|---|
| `xiulijiu_http_requests_total{method,path}` | counter | 请求总数 |
| `xiulijiu_http_requests_errors_total{method,path}` | counter | 5xx 错误总数 |
| `xiulijiu_http_request_duration_seconds_sum/count` | summary | 请求总耗时 / 次数 |
| `xiulijiu_uptime_seconds` | gauge | 进程运行时长 |

### 业务指标(`/metrics/prom`)

| 指标 | 说明 |
|---|---|
| `xiulijiu_orders_total` | 订单总数 |
| `xiulijiu_orders_completed` | 已完成订单 |
| `xiulijiu_orders_pending` | 处理中订单(store_pending/store_accepted/dispatched/assigned) |
| `xiulijiu_wallets_total` | 钱包数 |
| `xiulijiu_total_balance` | 钱包余额合计 |
| `xiulijiu_alerts_active` | 未解决告警总数 |
| `xiulijiu_alerts_active_critical` | 未解决 critical 告警 |
| `xiulijiu_alerts_active_warning` | 未解决 warning 告警 |
| `xiulijiu_last_recon_mismatch` | 最近一次对账的 mismatch 数 |

### 业务 JSON 端点(`/metrics`,向后兼容)

返回 `{uptime_seconds, orders_total, orders_completed, orders_pending, wallets_total, total_balance, alerts_active, alerts_critical, alerts_warning, last_recon_mismatch}`

## 告警渠道

### 1. 钉钉机器人(推荐)

1. 群里加机器人:群设置 → 智能群助手 → 添加机器人 → 自定义
2. 安全设置:选"加签",记下密钥
3. 拿 webhook URL:`https://oapi.dingtalk.com/robot/send?access_token=XXX`
4. 配 `.env`:
   ```
   DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=XXX
   DINGTALK_SECRET=SEC...   # 加签密钥(可选)
   ```

### 2. 飞书机器人

1. 群里加机器人:群设置 → 群机器人 → 添加机器人 → 自定义
2. 拿 webhook URL
3. 配 `.env`:
   ```
   FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/XXX
   ```

### 3. 通用 webhook(企业微信/Slack/自建)

```
WEBHOOK_URL=https://your-webhook-receiver/xiulijiu-alerts
```

会 POST JSON:
```json
{
  "title": "[CRITICAL] reconcile_mismatch",
  "body": "Alert #5\nType: reconcile_mismatch\nSeverity: CRITICAL\nUser: #5\nAmount: -200\nMessage: 钱包#3 对账差异: -200.0\n...",
  "severity": "critical",
  "type": "reconcile_mismatch",
  "alert": { ... 完整 alert 对象 ... }
}
```

## 启动

### 1. 启动基础(api + nginx + alert_watcher)

```bash
docker compose up -d
```

`alert_watcher` 容器自动跑 `node scripts/alert_watcher.js`,每 60s 拉一次未解决告警并推。

### 2. 启动全套监控(api + nginx + watcher + prometheus + grafana + alertmanager)

```bash
docker compose --profile monitoring up -d
```

访问:
- Grafana:http://your-host:3001,默认 admin / `GRAFANA_PASSWORD`
- Prometheus:http://your-host:9090
- Alertmanager:http://your-host:9093

Grafana 启动后会自动加载"xiulijiu 平台总览"dashboard,无需手配。

### 3. 调整轮询频率

```bash
POLL_INTERVAL_SEC=30 docker compose up -d alert_watcher
```

## Prom 告警规则

5 条规则在 `deploy/prometheus/alerts.yml`:

| 告警 | 触发条件 | 严重度 |
|---|---|---|
| HighErrorRate | 5 分钟内 5xx 率 > 5% | critical |
| HighLatency | P95 延迟 > 2s | warning |
| ServiceDown | 1 分钟不可达 | critical |
| WalletReconcileMismatch | critical 告警 > 0 持续 10m | critical |
| OrdersStuck | pending 订单 > 50 持续 30m | warning |

Prometheus → Alertmanager → `alert_watcher/webhook` → 钉钉/飞书。

## 测试

```bash
# 单元测试
python tests/test_reconcile_balance.py   # 6 个对账场景
python tests/test_auth_admin.py          # 15 个鉴权场景
node tests/test_alert_watcher.js         # 7 个推送场景

# 或用 powershell wrapper
./scripts/run_platform_flow_tests.ps1
```

## 故障排查

| 现象 | 排查 |
|---|---|
| watcher 报 "fetch alerts failed" | 检查 `API_BASE` 网络 + admin token 是否过期 |
| 钉钉收不到 | 检查 webhook URL + 关键字 / 加签配置 |
| 飞书收不到 | 检查 webhook 权限 + sign |
| Prom 抓不到指标 | 访问 `/metrics/prom` 看 200,Prom config 里 `api:8000` 是否能解析 |
| Alertmanager 告警推不出去 | 看 Alertmanager UI 的 Status 页面 |

## 上线 checklist

- [ ] 配 `DINGTALK_WEBHOOK` / `FEISHU_WEBHOOK`
- [ ] 改 `GRAFANA_PASSWORD`(默认 admin 不安全)
- [ ] Prom 告警接收人确认(钉钉群里至少有 1 个值班人)
- [ ] 第一次跑通:`docker compose --profile monitoring up -d` + 访问 9090/3001/9093 验证
- [ ] 测试告警链路:手动制造一个 critical 告警(对账不匹配),看是否推到钉钉
