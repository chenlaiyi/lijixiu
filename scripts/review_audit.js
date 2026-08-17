/**
 * 微信提审前最后核对脚本
 *
 * 走完审核路径,核对:
 *  1. 审核账号 login 成功
 *  2. 余额 ≥ 100
 *  3. 提现 5 元成功,返回申请编号
 *  4. 再次 login,余额恢复 100,提现被 reject
 *  5. 错误密码返回 401
 *  6. 登录页合规关键词检查(纯字符串,不调 API)
 */
const fs = require('fs');
const path = require('path');

const BASE = process.env.BASE_URL || 'https://x.iddg.cn';
const REVIEW_PASSWORD = process.env.WECHAT_REVIEW_PASSWORD;
const RESULTS = [];

function ok(name, detail) { RESULTS.push({ name, ok: true, detail }); console.log(`  OK  ${name}` + (detail ? '  ' + detail : '')); }
function fail(name, detail) { RESULTS.push({ name, ok: false, detail }); console.log(`  FAIL ${name}  ${detail || ''}`); }

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
  console.log('==> 微信提审核对 (base: ' + BASE + ')');
  if (!REVIEW_PASSWORD) { console.error('缺少环境变量 WECHAT_REVIEW_PASSWORD(审核账号密码)'); process.exit(1); }

  // 1. 错误密码
  let r = await call('POST', '/api/v1/auth/review-login', { account: 'reviewer', password: 'WRONG' });
  if (r.status === 401) ok('wrong-password-401', 'status=401'); else fail('wrong-password-401', 'expected 401 got ' + r.status);

  // 2. 正确密码 login
  r = await call('POST', '/api/v1/auth/review-login', { account: 'reviewer', password: REVIEW_PASSWORD });
  if (r.status !== 200) { fail('review-login', JSON.stringify(r.body)); return; }
  const reviewUser = r.body.user;
  if (reviewUser.phone !== '18800000999') fail('review-phone', 'got ' + reviewUser.phone);
  else ok('review-phone', reviewUser.phone);
  if (reviewUser.business_role !== 'repairer') fail('review-role', 'got ' + reviewUser.business_role);
  else ok('review-role', reviewUser.business_role);
  const reviewUserId = reviewUser.id;

  // 3. 余额
  r = await call('GET', `/api/v1/wallet/balance/${reviewUserId}`);
  if (r.status !== 200) { fail('review-balance', JSON.stringify(r.body)); return; }
  if (r.body.available_balance >= 100) ok('review-balance', 'available=' + r.body.available_balance);
  else fail('review-balance', 'available=' + r.body.available_balance + ' (want >=100)');

  // 4. 提现 1 元(沿用 wechat-review-guide.md 推荐的体验金额)
  r = await call('POST', `/api/v1/wallet/withdraw/${reviewUserId}`, { amount: 1.0, remark: 'review audit' });
  if (r.status >= 400) { fail('review-withdraw', JSON.stringify(r.body)); return; }
  const withdrawalId = r.body.id;
  ok('review-withdraw', 'id=' + withdrawalId + ' amount=' + r.body.amount + ' status=' + r.body.status);

  // 5. 提现记录
  r = await call('GET', `/api/v1/wallet/withdrawals?user_id=${reviewUserId}`);
  if (r.status !== 200) { fail('review-withdrawals', JSON.stringify(r.body)); return; }
  const myRecord = (r.body || []).find(item => item.id === withdrawalId);
  if (myRecord) ok('withdrawal-listed', 'status=' + myRecord.status);
  else fail('withdrawal-listed', 'not in list');

  // 6. 再次 login 触发 reset
  r = await call('POST', '/api/v1/auth/review-login', { account: 'reviewer', password: REVIEW_PASSWORD });
  if (r.status !== 200) { fail('review-relogin', JSON.stringify(r.body)); return; }

  // 7. 余额恢复
  r = await call('GET', `/api/v1/wallet/balance/${reviewUserId}`);
  if (r.body.available_balance >= 100 && r.body.frozen_balance === 0) {
    ok('review-reset', 'available=' + r.body.available_balance + ' frozen=' + r.body.frozen_balance);
  } else {
    fail('review-reset', 'available=' + r.body.available_balance + ' frozen=' + r.body.frozen_balance);
  }

  // 8. 历史提现被 reject
  r = await call('GET', `/api/v1/wallet/withdrawals?user_id=${reviewUserId}`);
  const myRecord2 = (r.body || []).find(item => item.id === withdrawalId);
  if (myRecord2 && myRecord2.status === 'rejected') {
    ok('withdrawal-rejected-after-reset', 'id=' + withdrawalId);
  } else {
    fail('withdrawal-rejected-after-reset', 'status=' + (myRecord2 && myRecord2.status));
  }

  // 9. 登录页关键词扫描(login.wxml)
  const wxml = fs.readFileSync(path.join(__dirname, '..', 'miniprogram', 'pages', 'login', 'login.wxml'), 'utf8');
  const checks = [
    { kw: '手机号快捷登录', must: true },
    { kw: '进入功能体验', must: true },
    { kw: '微信快捷登录', must: false },  // 这个文案应该不存在
    { kw: '微信登录', must: false },
  ];
  for (const c of checks) {
    const present = wxml.includes(c.kw);
    if (c.must && !present) fail('wxml-must:' + c.kw, 'not found');
    else if (!c.must && present) fail('wxml-mustnot:' + c.kw, 'should not appear');
    else ok('wxml:' + c.kw, c.must ? 'present' : 'absent');
  }

  // 10. icons 使用 phone.png(非 wechat.png)
  const usesPhoneIcon = wxml.includes('phone.png') || wxml.includes('phone-icon');
  if (usesPhoneIcon) ok('icon-phone', 'phone.png present');
  else fail('icon-phone', 'phone icon not found');

  // summary
  const passed = RESULTS.filter(r => r.ok).length;
  const failed = RESULTS.filter(r => !r.ok).length;
  console.log('');
  console.log('==> Summary: ' + passed + ' / ' + RESULTS.length + ' passed' + (failed > 0 ? ', ' + failed + ' FAILED' : ''));

  // write report
  const report = {
    base_url: BASE,
    timestamp: new Date().toISOString(),
    passed, failed, total: RESULTS.length,
    results: RESULTS,
  };
  const out = path.join(__dirname, '..', 'docs', 'review-audit.json');
  fs.writeFileSync(out, JSON.stringify(report, null, 2));
  console.log('==> Report: ' + out);

  process.exit(failed > 0 ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(1); });
