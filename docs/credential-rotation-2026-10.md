# 生产凭据轮换记录(2026-10-07)

## 背景

本次会话期间,以下**生产凭据以明文出现在对话记录里**:

| 凭据 | 出现原因 |
|---|---|
| 平台管理员 token | 用户要求「给个 token」,我用接口签发并打印 |
| 后台账号密码 `HyvC6!AQZqWOoqz^` | 新增管理后台账号密码登录时设置并打印 |
| 审核账号密码 `PmRzU@*x$kjcr9I9` | 提审前设置并打印 |
| SSH 密码 `Baofa2025` | 会话早期为部署恢复出来的 |

对话记录可能被日志、终端回滚、会话存档持久化,因此**等同于凭据泄露**。

## 已完成:轮换 AUTH_SECRET(作废所有 token)

token 的签名算法是 `HMAC-SHA256(AUTH_SECRET)` 取前 16 位十六进制,
载荷只有 `{user_id, role, iat}`,**没有 `exp`** —— 所以只要 secret 不变,
任何签发过的 token 都长期有效。

### 操作

```bash
# 备份
cp -a /www/wwwroot/xiulijiu_api/shared/.env .../env.bak-rotate-<时间戳>
# 生成 64 位十六进制新 secret,原位替换 AUTH_SECRET
# 重启
systemctl restart xiulijiu-api
```

新 secret 存放于服务器 `/www/wwwroot/xiulijiu_api/shared/.env`(**不在仓库里**,
`.env` 已 gitignore)。

### 轮换前后对照(实测)

轮换前先证明旧 token 有效,否则「轮换后 401」不能说明任何问题:

| 检查 | 轮换前 | 轮换后 |
|---|---|---|
| 旧 token `GET /api/v1/auth/me` | **200** | **401** |
| 旧 token `GET /api/v1/users?limit=3` | **200** | **401** |

### 轮换后全面复验:**24/24 通过**

| 类别 | 结果 |
|---|---|
| 旧 token 失效 | 401 / 401 |
| 后台账号密码登录 → 新 token 调 用户/提现/告警/对账 | 200,全部可用 |
| 审核账号登录 → 余额 100.00 / 提现记录 10 条 | 200 |
| 小程序演示账号(客户 / 师傅 / 管理员)登录 + token 可用 | 全 200 |
| 客户端「体验完整功能」白名单直登 | 200 |
| `/docs` `/redoc` `/openapi.json` `/metrics` | 仍 401 |
| `/health` `/admin/` | 200 |

## 连带影响(正向)

`_sms_hash(phone, code)` 也把 `AUTH_SECRET` 拼进 SHA256,且验证码**只存哈希** ——
所以轮换顺带**作废了所有在途短信验证码**。这正是想要的:
任何此前泄露的验证码都不能再用。

生产短信通道本身是关闭的(`/sms/request` → 503 `SMS provider is not configured`),
所以没有可用验证码可被利用。实测 `/sms/login` → 400 `Verification code was not requested`。

## 仍然待办:SSH 密码与两条业务密码

| 凭据 | 状态 | 建议 |
|---|---|---|
| SSH `root@8.134.99.53` | **未轮换** | 到腾讯云控制台改密码,或改用密钥登录并关闭密码登录 |
| 后台密码 `HyvC6!AQZqWOoqz^` | 未轮换 | `python scripts/set_admin_account.py --password '新密码'`,然后重启 |
| 审核密码 `PmRzU@*x$kjcr9I9` | 未轮换 | 提审期建议**先别改**(提审表单已填该密码);审核通过后再轮换 |

> 注意:改 `ADMIN_WEB_PASSWORD` 或 `WECHAT_REVIEW_PASSWORD` **不会**作废已发出的 token;
> 要作废 token 必须换 `AUTH_SECRET`(已做)。

## 生成凭据的脚本

```bash
python scripts/set_admin_account.py --dry-run                 # 管理后台账号密码
python scripts/set_review_account.py --dry-run                # 微信审核账号密码
```

两个脚本都是生成 16 位强随机密码(大小写+数字+符号)并原位替换 `.env`,
**只打印一次**,请立即记入密码管理器。
