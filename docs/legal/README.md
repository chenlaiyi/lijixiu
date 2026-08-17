# 法务材料接入指南

> 2026-08-09 落地

## 已落地的文件

### 模板(在 `docs/legal/`)

| 文件 | 用途 | 状态 |
|---|---|---|
| `user-agreement.md` | 用户服务协议 Markdown 源 | 通用模板,需律师审核 |
| `privacy-policy.md` | 隐私政策 Markdown 源 | 通用模板,需律师审核 |
| `compliance.md` | 合规资质 + ICP 备案 + 增值电信业务许可证 申请说明 | 内部参考 |

### H5 静态页(在 `h5/legal/`)

| 文件 | 用途 |
|---|---|
| `h5/legal/user-agreement.html` | H5 用户协议展示页(已样式化,可直接打开) |
| `h5/legal/privacy-policy.html` | H5 隐私政策展示页 |

### 接入位置

- **H5 登录页**(`h5/app.js`):登录按钮上方加必勾"我已阅读并同意《用户协议》和《隐私政策》"
- **H5 首页底部**(`h5/index.html`):加 footer(协议链接 + ICP 备案位)
- **Admin 后台底部**(`admin-web/index.html`):加 footer

## 还需做

### 必须做(微信小程序审核要求)

- [ ] **小程序登录页加协议勾选 + 链接**
- [ ] **小程序"设置-服务类目"上传用户协议 + 隐私政策**
- [ ] **后端加协议版本管理**(用户协议变更时强制重新同意)
  - 用户表加 `agreed_terms_version` / `agreed_privacy_version` / `agreed_at`
  - 登录时校验,如不匹配,前端弹窗重新同意
- [ ] **后端加数据访问请求接口**
  - `POST /api/v1/me/export-data` — 用户请求导出个人数据(JSON)
  - `POST /api/v1/me/delete` — 用户请求删除个人数据(15 日后执行,留反悔期)
- [ ] **后端日志保留 ≥ 180 天**(金融行业要求)

### 强烈建议

- [ ] **找执业律师审核** user-agreement.md + privacy-policy.md
- [ ] **公司主体注册**(营业执照,经营范围含"家政/维修/信息服务")
- [ ] **ICP 备案**([beian.miit.gov.cn](https://beian.miit.gov.cn/))
- [ ] **ICP 经营许可证**(增值电信业务,涉及抽佣收费)
- [ ] **ICP 备案号填入 footer**:`京ICP备XXXX号-X`

### 规模化后

- [ ] **等保 2.0 二级测评**(用户量 > 1 万)
- [ ] **等保 2.0 三级测评**(用户量 > 50 万 或 涉及金融)
- [ ] **支付合规**(钱包沉淀资金处理)
- [ ] **数据出境合规**(如接海外业务)

## 协议版本管理(待实现)

```python
# 用户表加字段
class User(Base):
    # ... 已有字段
    agreed_terms_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    agreed_privacy_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# 登录后端
@router.post("/me/agreements")
async def record_agreement(
    data: AgreementRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.agreed_terms_version = data.terms_version
    user.agreed_privacy_version = data.privacy_version
    user.agreed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "agreed_at": user.agreed_at}


# 登录时校验
@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "user": user_payload(user),
        "agreements_current": {
            "terms": CURRENT_TERMS_VERSION,      # "v1.0"
            "privacy": CURRENT_PRIVACY_VERSION,  # "v1.0"
        },
        "agreements_need_renewal": (
            user.agreed_terms_version != CURRENT_TERMS_VERSION or
            user.agreed_privacy_version != CURRENT_PRIVACY_VERSION
        ),
    }
```

## 数据访问请求(待实现)

```python
# POST /api/v1/me/export-data
# 鉴权 + 异步生成数据导出包(JSON + CSV),发邮件或提供下载链接

# POST /api/v1/me/delete
# 鉴权 + 标记账户为"待删除",15 日后自动删除(留反悔期)
```

## 协议页面跳转示例

```html
<!-- H5 登录页 -->
<a href="./legal/user-agreement.html" target="_blank" rel="noopener">《用户服务协议》</a>
<a href="./legal/privacy-policy.html" target="_blank" rel="noopener">《隐私政策》</a>

<!-- 小程序(用 web-view 打开 H5 协议页) -->
<web-view src="https://x.iddg.cn/h5/legal/user-agreement.html" />
<web-view src="https://x.iddg.cn/h5/legal/privacy-policy.html" />
```

## 测试

```bash
# 法律页面访问测试
node -e "
const fs = require('fs');
for (const f of ['h5/legal/user-agreement.html', 'h5/legal/privacy-policy.html']) {
  if (!fs.existsSync(f)) { console.log('MISSING: ' + f); process.exit(1); }
  const html = fs.readFileSync(f, 'utf8');
  if (!html.includes('立即修')) { console.log('INVALID: ' + f); process.exit(1); }
  console.log('OK: ' + f + ' (' + html.length + ' bytes)');
}
"
```

## 注意事项

1. **协议一旦上线,不要随意修改内容** — 每次修改后保留历史版本,让老用户能查看
2. **协议必须能完整展示** — 不能折叠、不能"已读视为同意"
3. **必须有"我已阅读并同意"勾选** — 不能默认勾选
4. **勾选后才能登录/下单** — 前端 + 后端都要校验
5. **协议变更后,老用户需重新同意** — 后端版本管理 + 前端弹窗

## 联系

- 律师:________________
- 代办公司:________________
- 工信部备案:[https://beian.miit.gov.cn/](https://beian.miit.gov.cn/)
