# 全链路测试报告

- 跑测时间:2026-08-11 11:57:20
- 运行环境:XWBOOK · Python 3.14.5
- 脚本:`scripts/test_platform_flows.py`
- 结果:**6 / 6 通过**

| # | Suite | Result |
|---|---|---|
| 1 | auth_roles_and_sms | [OK] ok |
| 2 | review_login_and_partial_withdrawal | [OK] ok |
| 3 | xiamen_service_area_assignment_and_routing | [OK] ok |
| 4 | repair_proxy_claim_payment_warranty | [OK] ok |
| 5 | per_order_and_monthly_payroll | [OK] ok |
| 6 | domestic_matching_installments_profit | [OK] ok |

## 套件覆盖

1. **auth_roles_and_sms** - 9 角色微信登录 + SMS 登录 + 非法账号拒登
2. **review_login_and_partial_withdrawal** - 审核账号 login + 提现 + 自动重置
3. **xiamen_service_area_assignment_and_routing** - 厦门思明区 98 个服务区查询 + 批量分配
4. **repair_proxy_claim_payment_warranty** - 报修 → 师傅接单 → 服务单 → 支付 → 保修
5. **per_order_and_monthly_payroll** - 单笔订单结算 + 月度工资单
6. **domestic_matching_installments_profit** - 家政需求匹配 + 分期支付 + 分润

## Known cleanup noise

After tests pass, Python `tempfile.TemporaryDirectory` cleanup can race with SQLite handle release on Windows and print `PermissionError: [WinError 32]`. This is teardown only and does not affect assertions.

## Re-run

```powershell
.\scripts\run_platform_flow_tests.ps1
```
