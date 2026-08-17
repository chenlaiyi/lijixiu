# 对账修复 dry-run 报告

- 跑测时间:2026-08-09T07:39:23.188Z
- 目标环境:https://x.iddg.cn
- 模式:**DRY_RUN**(只生成报告,不直接修复)

## 总览

- 钱包总数:13
- OK:9
- Mismatch:4
- 未解决 reconcile 告警:12

## 修复计划(每个 mismatch 钱包)

| Wallet | User | 余额 | 期望 | 实际 | 差异 | 操作 | 调整 amount |
|---|---|---|---|---|---|---|---|
| 2 | 4 | 0/88 | 0 | 88 | -88 | CREDIT | -88 |
| 3 | 5 | 0/200 | 0 | 200 | -200 | CREDIT | -200 |
| 5 | 7 | 0/42007.700000000004 | 0 | 42007.7 | -42007.7 | CREDIT | -42007.7 |
| 12 | 15 | 100/0 | 99 | 100 | -1 | CREDIT | -1 |

## 告警 resolve 计划

| Alert | Type | Severity | Message | Amount | Created |
|---|---|---|---|---|---|
| 9 | reconcile_mismatch | critical | 钱包#2 对账差异: -88.0 | -88 | 2026-08-09T07:39:21 |
| 10 | reconcile_mismatch | critical | 钱包#3 对账差异: -200.0 | -200 | 2026-08-09T07:39:21 |
| 11 | reconcile_mismatch | critical | 钱包#5 对账差异: -42007.7 | -42007.7 | 2026-08-09T07:39:21 |
| 12 | reconcile_mismatch | critical | 钱包#12 对账差异: -1.0 | -1 | 2026-08-09T07:39:21 |
| 5 | reconcile_mismatch | critical | 钱包#2 对账差异: -88.0 | -88 | 2026-08-09T07:34:49 |
| 6 | reconcile_mismatch | critical | 钱包#3 对账差异: -200.0 | -200 | 2026-08-09T07:34:49 |
| 7 | reconcile_mismatch | critical | 钱包#5 对账差异: -42007.7 | -42007.7 | 2026-08-09T07:34:49 |
| 8 | reconcile_mismatch | critical | 钱包#12 对账差异: -1.0 | -1 | 2026-08-09T07:34:49 |
| 4 | reconcile_mismatch | critical | 钱包#3 对账差异: -1013.6 | -1013.6 | 2026-07-04T02:27:21 |
| 3 | reconcile_mismatch | critical | 钱包#3 对账差异: -120.0 | -120 | 2026-07-03T12:29:16 |
| 2 | reconcile_mismatch | critical | 钱包#3 对账差异: -120.0 | -120 | 2026-06-29T14:48:52 |
| 1 | reconcile_mismatch | warning | [??] ????????? | null | 2026-06-29T14:48:16 |

## 修复步骤(需人工确认后执行)

1. **部署代码**:把 `app/services/safety.py` 和 `app/models/ledger.py` 改动上线
2. **写 ADJUST 流水**:为每个 plan 里的钱包调 `POST /api/v1/wallet/admin/adjust` (待实现) 或直接 SQL
3. **resolve 告警**:调 `POST /api/v1/admin/alerts/{id}/resolve`
4. **复跑对账**:再次 `POST /api/v1/admin/reconcile/run` 确认 mismatch=0
5. **回归测试**:跑 `tests/test_reconcile_balance.py` 确认新流程无差异
