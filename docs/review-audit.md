# 微信提审前核对报告

- 跑测时间:2026-08-09T07:01:13.262Z
- 目标环境:https://x.iddg.cn
- 结果:**13 / 13 通过**

## 核对项

| # | 项目 | 结果 | 详情 |
|---|---|---|---|
| 1 | wrong-password-401 | ✅ | status=401 |
| 2 | review-phone | ✅ | 18800000999 |
| 3 | review-role | ✅ | repairer |
| 4 | review-balance | ✅ | available=100 |
| 5 | review-withdraw | ✅ | id=25 amount=1 status=pending |
| 6 | withdrawal-listed | ✅ | status=pending |
| 7 | review-reset | ✅ | available=100 frozen=0 |
| 8 | withdrawal-rejected-after-reset | ✅ | id=25 |
| 9 | wxml:手机号快捷登录 | ✅ | present |
| 10 | wxml:进入功能体验 | ✅ | present |
| 11 | wxml:微信快捷登录 | ✅ | absent |
| 12 | wxml:微信登录 | ✅ | absent |
| 13 | icon-phone | ✅ | phone.png present |

## 涵盖维度

### API 行为
- 错误密码 401 拒绝
- 审核账号 login 返回 phone=18800000999 / role=repairer
- 余额恢复 ≥ 100
- 提现 1 元成功,返回申请 id + status=pending
- 重新 login 触发 reset:余额回 100,冻结清 0,历史提现被自动 reject

### 小程序登录页文案/图标(静态检查)
- 出现"手机号快捷登录"(合规)
- 出现"进入功能体验"(体验完整功能入口)
- 不出现"微信快捷登录" / "微信登录"
- 图标使用 `phone.png`(电话听筒,非微信 Logo)

## 提审就绪

**结论:代码层 + API 层均通过,可进入提审阶段。**

剩余 P1 阻塞:design-qa 小程序端 30 页面截图(需微信开发者工具扫码登录)

## 复跑

```powershell
node scripts/review_audit.js
node scripts/write_review_audit_report.js
```