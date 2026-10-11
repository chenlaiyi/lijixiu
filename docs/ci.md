# CI/CD 接入指南

> 2026-08-09 落地

## 工作流总览

| 文件 | 触发 | 作用 |
|---|---|---|
| `.github/workflows/ci.yml` | push / PR | 跑后端 + 小程序 + H5 + Admin 全套 lint + test |
| `.github/workflows/deploy.yml` | 手动 dispatch | 部署到 staging / production |
| `.github/workflows/miniprogram.yml` | push (miniprogram/) + 手动 | 小程序编译验证 + 上传微信 |

## 一次性配置

### 1. GitHub Secrets(在 repo Settings → Secrets → Actions)

部署相关:
- `SERVER_SSH_KEY` — 服务器 SSH 私钥(完整 PEM)
- `SERVER_HOST` — 目标主机 IP / 域名
- `SERVER_USER` — SSH 用户(默认 root)
- `DEPLOY_PATH` — 部署目录(默认 `/opt/xiulijiu`)
- `ENV_FILE` — 完整 `.env` 文件内容(直接复制)
- `SLACK_WEBHOOK_URL` — 部署结果通知(可选)

小程序相关:
- `WX_PRIVATE_KEY` — miniprogram-ci 私钥(从微信开发者工具导出)

### 2. 生成 miniprogram-ci 私钥

1. 微信开发者工具 → 设置 → 安全设置 → "下载代码上传密钥"
2. 私钥内容存 `WX_PRIVATE_KEY` secret
3. 项目代码里把 `miniprogram/appid` 配好(已配 `wx2273201e59e280bc`)

### 3. Server 端预置

```bash
# 服务器上(假设已 docker / docker compose plugin)
mkdir -p /opt/xiulijiu
cd /opt/xiulijiu
git clone <repo-url> .
# 一次性 cert / .env / htpasswd 准备
```

## 跑流程

### 每次 push / PR

自动跑 `ci.yml`:
- 后端 ruff lint + Python 单测 + 全链路测试
- 小程序 JSON / WXML / WXSS 格式校验 + appid 检查
- H5 / Admin 关键文件检查
- 全部过才 ✅ 绿

### 部署 staging

1. GitHub → Actions → "Deploy" → Run workflow
2. Environment: `staging`
3. 跑完:自动 ssh 到服务器,跑 `scripts/deploy.sh`,跑 `security_audit.js`
4. 结果推 Slack(可选)

### 部署生产

1. GitHub → Settings → Environments → New environment: `production`
2. 加 `ENV_FILE` / `SERVER_SSH_KEY` / `SERVER_HOST` 等 secrets
3. (可选)加 Required reviewers(手动审核)
4. Actions → Deploy → Environment: `production` → Run
5. 审核人通过后自动跑

### 小程序出包

1. Actions → "Miniprogram CI" → Run workflow
2. 填 Version(如 1.0.220)+ Description
3. 跑完:该版本出现在微信公众平台的**开发版本**列表里

> **`ci.upload` 只能产出「开发版本」。** 它的参数表里没有 `envVersion`
> (miniprogram-ci 2.1.31 实测:`dist/@types/ci/upload.d.ts` 与 `preview.d.ts`
> 都没有这个字段),所以工作流里原来那个 `env_version` 下拉是**静默失效**的
> —— 选了 trial 也照样只是开发版本,已于 2026-10-07 移除。
>
> 体验版与提审都只能人工在公众平台操作:
> 管理 → 版本管理 → 开发版本 → 选中该版本 → **选为体验版** → **提交审核**。
> 详见 [wechat-review-guide.md](wechat-review-guide.md)。
>
> 另:小程序码(`getwxacodeunlimit`)的 `env_version` 取自后端
> `WECHAT_MINIPROGRAM_ENV_VERSION`。`develop` 或非法取值在 strict 模式下会被
> `validate_env.py --strict` 拦下;`trial` 只告警(正式版发布前它是唯一可用取值),
> 但正式版发布后必须改成 `release`,否则生成的推广码只有体验成员打得开。

## 阶段拆分(按团队规模)

### 起步(单人 / 1-2 周)

只配 `ci.yml`,无 deploy:
- push 触发 lint + test
- 5 分钟知道有没有回归
- 不用 ssh 密钥,secret 0 个

### 进阶(3-5 人)

加 `deploy.yml`:
- staging 自动部署
- production 手动 dispatch
- secret 加 4-5 个

### 正式(团队 / 商业化)

加 miniprogram / Docker registry / 灰度:
- Docker 镜像推到阿里云 ACR / GitHub Container Registry
- 多环境(预发 / 蓝绿)
- miniprogram 自动出包
- 集成钉钉/飞书机器人

## 故障排查

| 现象 | 排查 |
|---|---|
| ci 后端测试失败 | 看 GitHub Actions 日志,本地 `python tests/test_reconcile_balance.py` 重现 |
| deploy ssh 失败 | 检查 `SERVER_SSH_KEY` secret 是否完整(注意换行) |
| deploy.sh 报 health check fail | 服务器上 `docker compose logs api` 看具体错 |
| miniprogram 编译失败 | 看 miniprogram-ci 报错,通常是 WXML 标签不匹配 |
| 上传成功但体验版没更新 | 上传的只是**开发版本**,要去公众平台手动「选为体验版」 |
| miniprogram 上传被拒(密钥相关) | 确认该上传密钥是否开了 IP 白名单(公众平台「开发管理 → 开发设置」),开了的话 GitHub Actions 的动态 IP 不在名单里;可改用本机 `npm run upload` |
| secret 找不到 | Settings → Secrets → Actions,确认名字拼写完全一致 |

## 改用 GitLab CI?

如果团队用 GitLab,把三个文件改 `.gitlab-ci.yml` 即可。结构相同(Stages / Jobs / Scripts)。
