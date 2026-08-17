# 日志接入指南

> 2026-08-09 落地

## 输出格式

应用启动时输出 JSON 到 stdout(每行一条),字段:

```json
{
  "ts": "2026-08-09T13:30:45.123456+00:00",
  "level": "INFO",
  "logger": "xiulijiu.audit",
  "msg": "提现申请",
  "request_id": "a1b2c3d4",
  "trace_id": "trc-xyz-12345",
  "user_id": 5,
  "withdrawal_id": 42,
  "amount": 195.0,
  "actor_business_role": "repairer"
}
```

| 字段 | 说明 |
|---|---|
| `ts` | UTC ISO 8601 时间 |
| `level` | DEBUG / INFO / WARNING / ERROR |
| `logger` | logger 名称 |
| `msg` | 日志消息 |
| `request_id` | 8 字符请求 ID(RequestIDMiddleware 注入) |
| `trace_id` | 12 字符链路 ID(支持客户端 X-Trace-ID 透传) |
| `user_id` / `order_id` / `actor_*` / `amount` / `withdrawal_id` 等 | 业务上下文 |

## Logger 分组

| Logger | 用途 | 级别 |
|---|---|---|
| `xiulijiu` | 应用通用 | INFO |
| `xiulijiu.observability` | 请求/响应/中间件 | INFO |
| `xiulijiu.audit` | 资金/订单/提现关键操作(合规留痕) | INFO |
| `xiulijiu.security` | 登录/越权/敏感数据访问(可选) | INFO |
| `uvicorn.access` / `uvicorn.error` | uvicorn 内置 | INFO |

## 配置

环境变量:

| 变量 | 默认 | 说明 |
|---|---|---|
| `LOG_FORMAT` | `json` | `json`(生产)/ `text`(本地调试) |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

`docker-compose.yml` 默认就是 JSON 输出,接 docker logs 即可看到。

## 收集与查询

### 方案 A:阿里云 SLS(国内推荐)

1. 创建 Project + Logstore
2. **数据接入方式**:用 `Logtail` + Docker stdout
   - 安装 Logtail(ECS 上)
   - 配置数据源:Docker stdout,匹配 `xiulijiu-*` 容器
   - 解析:JSON 模式(Logtail 自动解析)
3. 索引:`ts`, `level`, `logger`, `request_id`, `user_id`
4. 查询示例:
   ```
   msg:"对账修复" AND actor_user_id:*
   ```
5. 告警:对账修复 / 提现审核 等 audit 事件可单独告警

### 方案 B:Loki + Promtail(开源)

1. docker-compose 加:
   ```yaml
   loki:
     image: grafana/loki:3.2.0
     command: -config.file=/etc/loki/local-config.yaml
     ports: ["3100:3100"]
     volumes:
       - ./deploy/loki/loki-config.yaml:/etc/loki/local-config.yaml
       - loki_data:/loki
   promtail:
     image: grafana/promtail:3.2.0
     command: -config.file=/etc/promtail/config.yaml
     volumes:
       - /var/lib/docker/containers:/var/lib/docker/containers:ro
       - /var/run/docker.sock:/var/run/docker.sock:ro
       - ./deploy/promtail/config.yaml:/etc/promtail/config.yaml
   ```
2. `deploy/promtail/config.yaml`:
   ```yaml
   server:
     http_listen_port: 9080
   positions:
     filename: /tmp/positions.yaml
   clients:
     - url: http://loki:3100/loki/api/v1/push
   scrape_configs:
     - job_name: docker
       static_configs:
         - targets: [localhost]
           labels:
             job: docker
             __path__: /var/lib/docker/containers/**/*-json.log
       pipeline_stages:
         - json:
             expressions:
               level: level
               logger: logger
               msg: msg
               request_id: request_id
         - labels:
             level:
             logger:
   ```
3. Grafana → Explore → Loki 数据源,LogQL 查询:
   ```logql
   {job="docker"} |= "对账修复" | json | actor_user_id="2"
   ```

### 方案 C:Filebeat + Elasticsearch(重型方案)

不推荐(运维成本高),仅当已有 ELK 栈时考虑。

## 本地调试

```bash
# 本地用文本格式(易读)
LOG_FORMAT=text LOG_LEVEL=DEBUG uvicorn app.main:app --reload
```

输出:
```
2026-08-09 21:30:45 [INFO] xiulijiu.audit [req=a1b2c3d4 trc=trc-xyz-12345] 提现申请
```

## 关键路径 audit trail(2026-08-09 已加)

| 端点 | logger | 字段 |
|---|---|---|
| `POST /admin/reconcile/run` | `xiulijiu.audit` | actor_user_id, actor_business_role |
| `POST /admin/wallet/adjust` | `xiulijiu.audit` | actor_user_id, target_user_id, amount, ledger_id |
| `POST /api/v1/wallet/withdraw/{user_id}` | `xiulijiu.audit` | actor_user_id, withdrawal_id, amount, remark |
| `POST /api/v1/wallet/withdraw/{id}/review` | `xiulijiu.audit` | actor_user_id, withdrawal_id, action, new_status |

合规:以上 audit 日志**不可被关闭**(除非整体降级),要保留 ≥ 180 天(金融行业要求)。

## 测试

```bash
python tests/test_logging.py  # 18/18
```

覆盖 JSON 格式 / 异常序列化 / extra 字段 / audit logger 集成。

## 故障排查

| 现象 | 排查 |
|---|---|
| 看不到 JSON | `LOG_FORMAT` 环境变量是否被覆盖;进程是否走 `python` 直起而非 `uvicorn` |
| request_id 全是 - | 检查 `RequestIDMiddleware` 是否注册在 router 之前(`app.add_middleware`) |
| 日志太多 | 调高 `LOG_LEVEL=WARNING` |
| 关键 audit 没出现 | 检查 router 里 `audit_log.info(...)` 是否还在(没被覆盖) |
| 中文字段乱码 | `ensure_ascii=False` 已在 JsonFormatter 配置 |
