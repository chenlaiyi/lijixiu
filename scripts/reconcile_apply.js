/**
 * 对账修复执行:用 admin 鉴权调 /admin/wallet/adjust + /admin/alerts/{id}/resolve
 *
 * 流程:
 *  1. 拉 admin token(账号密码登录)
 *  2. 触发对账,获取 mismatch 列表
 *  3. 为每个 mismatch 调 /admin/wallet/adjust(写 ADJUST ledger)
 *  4. 复跑对账,确认 mismatch=0
 *  5. 把未解决的 reconcile_mismatch 告警全部 resolve
 *
 * 用法:
 *   # dry-run(默认,只生成报告)
 *   node scripts/reconcile_apply.js
 *
 *   # 真跑(慎用!)
 *   node scripts/reconcile_apply.js --apply
 *
 *   # 换 base
 *   BASE_URL=https://x.iddg.cn node scripts/reconcile_apply.js
 *
 *   # 换 admin 账号
 *   ADMIN_PHONE=18800000000 node scripts/reconcile_apply.js
 */
const fs = require('fs');
const path = require('path');

const BASE = process.env.BASE_URL || 'https://x.iddg.cn';
const APPLY = process.argv.includes('--apply');
const ADMIN_PHONE = process.env.ADMIN_PHONE || '18800000000';
const ADMIN_NAME = process.env.ADMIN_NAME || '演示管理员';
const OUT_JSON = path.join(__dirname, '..', 'docs', 'reconcile-apply.json');

async function call(method, urlPath, body, token) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = 'Bearer ' + token;
  const res = await fetch(BASE + urlPath, { method, headers, body: body ? JSON.stringify(body) : undefined });
  let json = null;
  try { json = await res.json(); } catch (e) {}
  return { status: res.status, body: json };
}

async function loginAdmin() {
  // 用 wechat-login 拿 admin token(demo 模式)
  const r = await call('POST', '/api/v1/auth/wechat-login', {
    code: `${ADMIN_PHONE}:${ADMIN_NAME}:admin`,
  });
  if (r.status !== 200) {
    throw new Error(`admin login failed: ${r.status} ${JSON.stringify(r.body)}`);
  }
  return r.body.token;
}

async function main() {
  console.log('==> 对账修复 ' + (APPLY ? '[APPLY MODE - 真实执行]' : '[DRY-RUN]'));
  console.log('    base: ' + BASE);
  console.log('');

  // 1. 登录 admin
  console.log('1. 登录 admin...');
  let token;
  try {
    token = await loginAdmin();
    console.log('   OK, token len=' + token.length);
  } catch (e) {
    console.log('   FAIL: ' + e.message);
    process.exit(1);
  }

  // 2. 触发对账
  console.log('2. 触发对账...');
  let r = await call('POST', '/api/v1/admin/reconcile/run', null, token);
  if (r.status !== 200) {
    console.log('   FAIL: status=' + r.status + ' body=' + JSON.stringify(r.body));
    process.exit(1);
  }
  const total = r.body;
  console.log('   total=' + total.total_wallets + ' ok=' + total.ok + ' mismatch=' + total.mismatch);

  // 3. 拉告警
  console.log('3. 拉告警列表...');
  r = await call('GET', '/api/v1/admin/alerts?resolved=false&limit=200', null, token);
  const alerts = (r.body || []).filter(a => a.type === 'reconcile_mismatch');
  console.log('   未解决 reconcile 告警:' + alerts.length);

  // 4. 对每个 mismatch 调 adjust
  const adjustResults = [];
  for (const d of total.details || []) {
    // difference 是负的(ledger_sum - actual),要让 ledger_sum 追上 actual
    // adjust amount = -difference(正数)
    const adjustAmount = -d.difference;
    console.log('4. adjust user=' + d.user_id + ' wallet=' + d.wallet_id + ' amount=' + adjustAmount);

    if (APPLY) {
      const ar = await call('POST', '/api/v1/admin/wallet/adjust', {
        user_id: d.user_id,
        amount: adjustAmount,
        remark: '2026-08-09 P0 收尾:消化历史对账差异',
      }, token);
      adjustResults.push({
        user_id: d.user_id, wallet_id: d.wallet_id, original_diff: d.difference,
        adjust_amount: adjustAmount, status: ar.status, body: ar.body,
      });
      console.log('   ' + (ar.status === 200 ? 'OK' : 'FAIL ' + ar.status) + ' ledger_id=' + (ar.body && ar.body.ledger_id));
    } else {
      adjustResults.push({
        user_id: d.user_id, wallet_id: d.wallet_id, original_diff: d.difference,
        adjust_amount: adjustAmount, status: 'DRY_RUN', body: null,
      });
      console.log('   DRY-RUN (will apply)');
    }
  }

  // 5. 复跑对账
  console.log('5. 复跑对账...');
  r = await call('POST', '/api/v1/admin/reconcile/run', null, token);
  const recheck = r.body;
  console.log('   total=' + recheck.total_wallets + ' mismatch=' + recheck.mismatch + ' details=' + JSON.stringify(recheck.details));

  // 6. resolve 告警
  const resolveResults = [];
  if (recheck.mismatch === 0) {
    console.log('6. resolve 告警...');
    for (const a of alerts) {
      if (APPLY) {
        const rr = await call('POST', '/api/v1/admin/alerts/' + a.id + '/resolve', null, token);
        resolveResults.push({ alert_id: a.id, status: rr.status, body: rr.body });
        console.log('   alert#' + a.id + ' ' + (rr.status === 200 ? 'OK' : 'FAIL ' + rr.status));
      } else {
        resolveResults.push({ alert_id: a.id, status: 'DRY_RUN' });
        console.log('   alert#' + a.id + ' DRY-RUN');
      }
    }
  } else {
    console.log('6. 仍有 ' + recheck.mismatch + ' 个差异,跳过 resolve');
  }

  // 7. 写报告
  const report = {
    base_url: BASE,
    mode: APPLY ? 'APPLY' : 'DRY_RUN',
    timestamp: new Date().toISOString(),
    initial: { total_wallets: total.total_wallets, mismatch: total.mismatch },
    after_fix: { total_wallets: recheck.total_wallets, mismatch: recheck.mismatch },
    adjust_results: adjustResults,
    resolve_results: resolveResults,
  };
  fs.writeFileSync(OUT_JSON, JSON.stringify(report, null, 2), 'utf8');
  console.log('');
  console.log('报告:' + OUT_JSON);
  console.log('模式:' + (APPLY ? '已真实执行' : 'DRY-RUN(没改线上数据)'));
  if (!APPLY) {
    console.log('');
    console.log('确认要执行?加 --apply 重跑:');
    console.log('  node scripts/reconcile_apply.js --apply');
  }
}

main().catch(e => { console.error(e); process.exit(1); });
