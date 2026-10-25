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
  const markup = fs.readFileSync('miniprogram/pages/login/login.wxml', 'utf8');
  assert(markup.includes('phoneAuthReady && agreementAccepted'));
  assert(!/微信|登录即表示/.test(markup));
  assert.strictEqual(JSON.parse(fs.readFileSync('miniprogram/app.json')).entryPagePath, 'pages/index/index');
  console.log('PASS: explicit revocable consent gates all login methods; guest browsing has no forced login or private requests; order submission requests login');
})().catch(error => { console.error(error); process.exitCode = 1; });

