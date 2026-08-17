/**
 * 对账修复 dry-run:为当前 mismatch 钱包生成 ADJUST 流水计划 + resolve 告警计划
 *
 * 不直接调用修复端点,只生成报告(让人审完再跑)
 *
 * 用法:
 *   node scripts/reconcile_dryrun.js              # 默认 base = https://x.iddg.cn
 *   BASE_URL=http://localhost:8000 node scripts/reconcile_dryrun.js
 */
const fs = require('fs');
const path = require('path');

const BASE = process.env.BASE_URL || 'https://x.iddg.cn';

async function call(method, urlPath, body) {
  const res = await fetch(BASE + urlPath, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  let json = null;
  try { json = await res.json(); } catch (e) {}
  return { status: res.status, body: json };
}

async function main() {
  console.log('==> 对账修复 dry-run (base: ' + BASE + ')');
  console.log('(不直接执行修复,只生成报告)\n');

  // 1) 触发对账
  console.log('触发对账...');
  const r = await call('POST', '/api/v1/admin/reconcile/run');
  if (r.status !== 200) {
    console.log('FAIL reconcile/run: status=' + r.status);
    process.exit(1);
  }
  console.log('  total=' + r.body.total_wallets + ' ok=' + r.body.ok + ' mismatch=' + r.body.mismatch);

  // 2) 拉最新对账日志
  const log = await call('GET', '/api/v1/admin/reconcile/logs?limit=50');
  const logs = log.body || [];
  const latestByWallet = {};
  for (const l of logs) {
    if (!latestByWallet[l.wallet_id]) latestByWallet[l.wallet_id] = l;
  }
  const mismatches = Object.values(latestByWallet).filter(l => l.status === 'mismatch');

  // 3) 拉告警
  const alerts = await call('GET', '/api/v1/admin/alerts?resolved=false');
  const alertList = alerts.body || [];
  const reconcileAlerts = alertList.filter(a => a.type === 'reconcile_mismatch');

  // 4) 拉每个钱包余额,生成 ADJUST 计划
  const plans = [];
  for (const m of mismatches) {
    const bal = await call('GET', `/api/v1/wallet/balance/${m.user_id}`);
    if (bal.status !== 200) {
      plans.push({ wallet_id: m.wallet_id, user_id: m.user_id, error: bal.body });
      continue;
    }
    const w = bal.body;
    plans.push({
      wallet_id: m.wallet_id,
      user_id: m.user_id,
      available_balance: w.available_balance,
      frozen_balance: w.frozen_balance,
      total: w.available_balance + w.frozen_balance,
      expected_ledger: m.expected_balance,
      actual_wallet: m.actual_balance,
      difference: m.difference,
      adjust_action: m.difference < 0 ? 'CREDIT' : 'DEBIT',  // ledger 比 wallet 少,需要加 ledger
      adjust_amount: Math.abs(m.difference),
      // 修复后这条 ledger 的目标值(让 ledger_sum = wallet total)
      // 当前 ledger_sum = expected_balance,需要 ledger_sum 调整到 actual_balance
      // amount = actual - expected = -difference
      adjust_ledger_amount: m.difference,
    });
  }

  // 5) 写报告
  const report = {
    base_url: BASE,
    timestamp: new Date().toISOString(),
    run_mode: 'DRY_RUN',
    summary: {
      wallets_total: r.body.total_wallets,
      wallets_ok: r.body.ok,
      wallets_mismatch: r.body.mismatch,
      alerts_unresolved: reconcileAlerts.length,
    },
    plans,
    alert_resolve_plan: reconcileAlerts.map(a => ({
      alert_id: a.id,
      type: a.type,
      severity: a.severity,
      message: a.message,
      amount: a.amount,
      created_at: a.created_at,
      rationale: '差异将由 ADJUST 流水补齐,标 resolved 留档',
    })),
  };

  const outJson = path.join(__dirname, '..', 'docs', 'reconcile-fix-dryrun.json');
  const outMd = path.join(__dirname, '..', 'docs', 'reconcile-fix-dryrun.md');
  fs.writeFileSync(outJson, JSON.stringify(report, null, 2), 'utf8');

  // markdown
  const md = [];
  md.push('# 对账修复 dry-run 报告');
  md.push('');
  md.push(`- 跑测时间:${report.timestamp}`);
  md.push(`- 目标环境:${BASE}`);
  md.push(`- 模式:**DRY_RUN**(只生成报告,不直接修复)`);
  md.push('');
  md.push('## 总览');
  md.push('');
  md.push(`- 钱包总数:${report.summary.wallets_total}`);
  md.push(`- OK:${report.summary.wallets_ok}`);
  md.push(`- Mismatch:${report.summary.wallets_mismatch}`);
  md.push(`- 未解决 reconcile 告警:${report.summary.alerts_unresolved}`);
  md.push('');
  md.push('## 修复计划(每个 mismatch 钱包)');
  md.push('');
  md.push('| Wallet | User | 余额 | 期望 | 实际 | 差异 | 操作 | 调整 amount |');
  md.push('|---|---|---|---|---|---|---|---|');
  for (const p of plans) {
    if (p.error) { md.push(`| ${p.wallet_id} | ${p.user_id} | ERR | - | - | - | ${JSON.stringify(p.error)} | - |`); continue; }
    md.push(`| ${p.wallet_id} | ${p.user_id} | ${p.available_balance}/${p.frozen_balance} | ${p.expected_ledger} | ${p.actual_wallet} | ${p.difference} | ${p.adjust_action} | ${p.adjust_ledger_amount} |`);
  }
  md.push('');
  md.push('## 告警 resolve 计划');
  md.push('');
  md.push('| Alert | Type | Severity | Message | Amount | Created |');
  md.push('|---|---|---|---|---|---|');
  for (const a of report.alert_resolve_plan) {
    md.push(`| ${a.alert_id} | ${a.type} | ${a.severity} | ${a.message} | ${a.amount} | ${a.created_at} |`);
  }
  md.push('');
  md.push('## 修复步骤(需人工确认后执行)');
  md.push('');
  md.push('1. **部署代码**:把 `app/services/safety.py` 和 `app/models/ledger.py` 改动上线');
  md.push('2. **写 ADJUST 流水**:为每个 plan 里的钱包调 `POST /api/v1/wallet/admin/adjust` (待实现) 或直接 SQL');
  md.push('3. **resolve 告警**:调 `POST /api/v1/admin/alerts/{id}/resolve`');
  md.push('4. **复跑对账**:再次 `POST /api/v1/admin/reconcile/run` 确认 mismatch=0');
  md.push('5. **回归测试**:跑 `tests/test_reconcile_balance.py` 确认新流程无差异');
  md.push('');

  fs.writeFileSync(outMd, md.join('\n'), 'utf8');

  console.log('\n报告:');
  console.log('  ' + outJson);
  console.log('  ' + outMd);
  console.log('\n差异钱包 ' + plans.length + ' 个,未解决告警 ' + reconcileAlerts.length + ' 条');
  console.log('\n下一步:审 reports -> 部署代码 -> 跑修复脚本(待实现)');
}

main().catch(e => { console.error(e); process.exit(1); });
