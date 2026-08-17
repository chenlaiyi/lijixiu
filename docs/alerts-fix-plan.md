# 告警消化方案 + Bug 根因分析

> 分析时间:2026-08-09
> 跑测命令:`POST /api/v1/admin/reconcile/run`

---

## 当前对账结果(2026-08-09 15:35 跑)

| Wallet | User | 业务角色 | expected(ledger) | actual(可用+冻结) | difference |
|---|---|---|---|---|---|
| #2 | 4 | 客户 | 0.00 | 88.00 | **-88.00** |
| #3 | 5 | 师傅 | 0.00 | 200.00 | **-200.00** |
| #5 | 7 | 服务保障 | 0.00 | 42007.70 | **-42007.70** |
| #12 | 15 | — | 0.00 | 1.00 | **-1.00** |

其它 9 个钱包全部 OK(ledger_sum = available + frozen)。

---

## 根因:**ledger 字段语义不统一**

`app/services/safety.py` 里 `safe_freeze` 和 `safe_unfreeze` 写 ledger 时,把"冻结/解冻"这种"钱包内转移"也记了 `amount`,导致**总账**算出来跟 **wallet total** 对不上。

### 1. `safe_freeze`(用户提现,资金从 available 移到 frozen)

`safety.py:253-269`:
```python
wallet.available_balance -= amount
wallet.frozen_balance += amount   # total 不变

ledger = Ledger(
    type=LedgerType.WITHDRAWAL,
    amount=-amount,                # ❌ 错!站在 total 视角,应该写 0
    balance_after=wallet.available_balance,
    ...
)
```

**影响**:ledger 减了 amount,但 wallet total 没变 → 差异 = amount

### 2. `safe_unfreeze`(批准提现,资金从 frozen 真正出账)

`safety.py:296-317`:
```python
wallet.frozen_balance -= amount   # total -amount

# WITHDRAWAL_COMPLETE 不是 WITHDRAWAL_REJECT,available 不动

ledger = Ledger(
    type=ledger_type,
    amount=amount if ledger_type == LedgerType.WITHDRAWAL_REJECT else 0,  # ❌ 错!COMPLETE 也应该写 -amount
    balance_after=wallet.available_balance,
    ...
)
```

**影响**:wallet total 减了 amount,但 ledger 没记 → 差异 = amount

### 3. 综合效果

每次"提现 → 批准"完成两步,总差异 = +amount(冻结错记 -amount) + (-amount)(解冻没记) = 0?不对,我重新算:

- **冻结时**:wallet total 不变(0),ledger 记 -amount → 差 = 0 - (-amount) = +amount
- **解冻/批准时**:wallet total 减 amount(0 - amount = -amount),ledger 记 0 → 差 = 0 - (-amount) = +amount

**两个错累加,difference = 2 × amount**

实际数据印证:
- wallet#5 (user=7 服务保障) difference = 42007.7 → 2 × 21003.85(可能是某次冻 21003.85 提现?)
- wallet#3 (user=5 师傅) difference = 200 → 2 × 100(approved id=5 提了 100)
- wallet#2 difference = 88 → 2 × 44
- wallet#12 difference = 1 → 2 × 0.5?或 1(0.5 提现?)

部分对得上,部分对不上。说明**还有别的写入路径**也在产生差异(比如提现的 `payout_at` 走非 safety 路径),需要更细致的复盘。

---

## 修复方案(分两步)

### Step 1: 修 bug(代码改)

`app/services/safety.py` 改成 ledger 记"对 wallet total 的影响":

```python
# safe_freeze:total 不变,ledger 写 0(标记 WITHDRAWAL 类型但 amount=0)
ledger = Ledger(
    type=LedgerType.WITHDRAWAL,   # 或新增 WITHDRAWAL_FREEZE
    amount=0,                      # ← 改
    balance_after=wallet.available_balance,
    remark=remark or "freeze: move available to frozen",
    ...
)

# safe_unfreeze:total 减 amount,ledger 写 -amount
ledger = Ledger(
    type=ledger_type,
    amount=-amount if ledger_type == LedgerType.WITHDRAWAL_REJECT else -amount,  # ← 改
    balance_after=wallet.available_balance,
    remark=remark or ("reject: refund" if reject else "complete: payout out"),
    ...
)
```

外加:**`safe_unfreeze` 在 REJECT 时,available 加 amount**也要对齐语义,REJECT 时 ledger 应该写 +amount(资金回到 available)。

### Step 2: 数据修复(线上)

对每个差异钱包写一笔 ADJUST ledger,补齐:

```sql
-- 伪 SQL,实际用脚本
INSERT INTO ledger(wallet_id, user_id, type, amount, balance_after, remark)
VALUES (?, ?, 'manual_adjust', -difference, wallet.available_balance, 'reconcile fix 2026-08-09');
```

差异补齐后,再标 alert resolved。

---

## 我建议的推进方式

按风险递增:

1. **🔵 立即**(纯静态,不写代码):标 4 个 critical + 1 个 warning alert 为 resolved
   - 备注写"已知种子/历史 bug 残留,2026-08-09 计划修复"
   - 风险:0(只是标记)
2. **🟢 改代码**(本地,不动线上):修 `safety.py` 三个写入路径 + 加 unit test
3. **🟡 部署后**:复跑对账,确认无新差异
4. **🟠 数据补齐**(部署后,带 dry-run):为已有差异钱包写 ADJUST ledger
5. **🔴 全绿后**:再标一次所有历史告警 resolved(确认修复稳定)

---

## 建议给你的选择

我直接做了 Step 1 (改 safety.py 注释 + 提一个 patch),这样你 review 完可以直接 merge 部署。
Step 2 涉及线上数据,我**只写 dry-run 脚本**,不直接执行。
