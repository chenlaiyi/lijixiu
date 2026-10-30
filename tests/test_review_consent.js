const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
function page(file, storage = {}) {
  let definition;
  const calls = [];
  vm.runInNewContext(fs.readFileSync(`miniprogram/pages/${file}.js`, 'utf8'), {
    Page(value) { definition = value; },
    require(name) {
      if (name.endsWith('/share')) return { create: () => ({}), enable() {} };
      if (name.endsWith('/role')) return { getEntryPath: () => '/pages/store/dashboard/dashboard' };
      return new Proxy({}, { get: (_, key) => async () => { calls.push(key); return []; } });
    },
    wx: new Proxy({ getStorageSync: key => storage[key], getPrivacySetting: undefined }, {
      get: (obj, key) => key in obj ? obj[key] : (...args) => calls.push([key, ...args]),
    }),
    getApp: () => ({}), console, Date, setTimeout, clearTimeout, clearInterval,
  });
  const instance = { ...definition, data: JSON.parse(JSON.stringify(definition.data)), setData(value) { Object.assign(this.data, value); } };
  return { instance, calls };
}
(async () => {
  const { instance: login, calls } = page('login/login');
  assert.strictEqual(login.data.agreementAccepted, false);
  for (const name of ['sendSmsCode', 'handleAccountLogin', 'prepareWechatPhoneLogin', 'enterFullExperience', 'handleDemoLogin', 'handleWechatPhoneLogin', 'handleLogin']) await login[name]();
  assert(calls.every(call => Array.isArray(call) && call[0] === 'showToast'), 'No authentication or SMS request before consent');
  login.onAgreementChange({ detail: { value: ['accept'] } });
  assert(login.requireAgreement());
  login.onAgreementChange({ detail: { value: [] } });
  assert(!login.requireAgreement());
  const { instance: home, calls: homeCalls } = page('customer/home/home', { userInfo: { id: 1 } });
  home.onShow();
  await Promise.resolve();
  assert(!homeCalls.some(call => !Array.isArray(call) || ['reLaunch', 'redirectTo', 'login', 'getUserProfile', 'getPhoneNumber'].includes(call[0])), 'Guest home neither redirects nor calls private APIs, even with stale cached user');
  const { instance: order, calls: orderCalls } = page('customer/order/order');
  await order.submitOrder();
  assert(orderCalls.some(call => Array.isArray(call) && call[0] === 'showModal'));
  assert(!orderCalls.some(call => call === 'post'));
  order.data.submitting = true; orderCalls.length = 0;
  await order.submitOrder();
  assert.strictEqual(orderCalls.length, 0, 'Repeated taps must not submit twice');
  order.data.submitting = false;
  const markup = fs.readFileSync('miniprogram/pages/login/login.wxml', 'utf8');
  assert(markup.includes('phoneAuthReady && agreementAccepted'));
  assert(!/微信|登录即表示/.test(markup));
  assert.strictEqual(JSON.parse(fs.readFileSync('miniprogram/app.json')).entryPagePath, 'pages/customer/home/home');

  const config = JSON.parse(fs.readFileSync('miniprogram/app.json'));
  assert.strictEqual(config.pages[0], 'pages/customer/home/home');
  const { instance: oldLogin, calls: oldCalls } = page('login/login');
  oldLogin.onLoad({});
  assert.strictEqual(oldCalls[0][0], 'reLaunch');
  assert.strictEqual(oldCalls[0][1].url, '/pages/customer/home/home');
  const { instance: earnings, calls: earningsCalls } = page('repairer/earnings/earnings');
  await earnings.onShow();
  assert(earningsCalls.every(call => Array.isArray(call) && call[0] === 'reLaunch'));
  assert.strictEqual(earningsCalls[0][1].url, '/pages/customer/home/home');
  const { instance: domestic, calls: domesticCalls } = page('customer/domestic/list/list');
  await domestic.loadWorkers();
  assert.strictEqual(domestic.data.guest, true);
  assert.strictEqual(domesticCalls.length, 0, 'Guest service description has no private personnel or demand requests');
  const { instance: demand, calls: demandCalls } = page('customer/domestic/demand/demand');
  demandCalls.length = 0;
  await demand.loadDefaults();
  assert.strictEqual(demandCalls.length, 0);
  await demand.submit();
  assert.strictEqual(demandCalls[0][0], 'showModal');
  const rules = fs.readFileSync('miniprogram/pages/repairer/earnings/earnings.wxml', 'utf8');
  assert(earnings.data.withdrawalTiming.includes('提交成功后 7 天内完成审核'));
  assert(earnings.data.withdrawalTiming.includes('审核通过后 7 天内到账'));
  assert(rules.includes('每日次数') && rules.includes('申请时间') && rules.includes('审核及到账时间') && rules.includes('可提现额度'));
  assert(rules.indexOf('提现规则') < rules.indexOf('class="withdraw-btn"'));
  console.log('PASS: explicit revocable consent gates all login methods; guest browsing has no forced login or private requests; order submission requests login');
})().catch(error => { console.error(error); process.exitCode = 1; });

