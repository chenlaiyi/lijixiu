const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

function page(file, api, user) {
  let definition;
  const wx = { getStorageSync: () => user, showToast() {}, showLoading() {}, hideLoading() {} };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../miniprogram', file), 'utf8'), {
    Page: value => { definition = value; }, wx, setTimeout,
    require(name) {
      if (name.endsWith('/api')) return api;
      if (name.endsWith('/share')) return { create: () => ({}) };
      if (name.endsWith('/status-style')) return { orderStatusTone: () => '' };
      if (name.endsWith('/service-bill')) return { parseItems: bill => bill ? JSON.parse(bill.items_json) : [] };
      throw new Error(name);
    },
  });
  definition.data = { ...definition.data, orderId: 6 };
  definition.setData = value => Object.assign(definition.data, value);
  return definition;
}

(async () => {
  let order = { id: 6, status: 'wait_payment', repairer_id: 2, assigned_repairer_id: 2,
    price: 80, paid_amount: 0, category: 'other' };
  const bill = { revision: 1, amount: 80, items_json: JSON.stringify([
    { name: '原有明细', quantity: 2, unit_price: 40, subtotal: 80 },
  ]), warranty_days: 0, confirmation_method: 'phone', confirmation_note: '已电话确认' };
  const posts = [];
  const api = {
    async get(url) {
      if (url.endsWith('/service-bill/latest')) return bill;
      if (url.includes('/repairers')) return [{ id: 2, user_id: 10 }];
      return { ...order };
    },
    async post(url, data) { posts.push({ url, data }); order.price = data.amount; return {}; },
  };
  const tech = page('pages/repairer/detail/detail.js', api, { id: 10 });
  await tech.loadOrder();
  assert(tech.data.canReviseBill);
  assert(!tech.data.canComplete);
  await tech.beginBillRevision();
  assert(tech.data.editingBill && tech.data.canComplete);
  assert.strictEqual(tech.data.serviceItems[0].name, '原有明细');
  assert.strictEqual(tech.data.warrantyDays, '0');
  tech.data.serviceItems[0].price = '2.00';
  await tech.completeService();
  assert.strictEqual(posts[0].data.amount, 4);
  assert.strictEqual(posts[0].data.expected_revision, 1);
  assert(!posts[0].url.includes('store-review'));
  await new Promise(resolve => setImmediate(resolve));
  order.paid_amount = 1;
  await tech.loadOrder();
  assert(!tech.data.canReviseBill);
  order.paid_amount = 0;
  const other = page('pages/repairer/detail/detail.js', api, { id: 99 });
  await other.loadOrder();
  assert(!other.data.canReviseBill);

  // A reduced order price must not be overridden by a stale higher service bill.
  const customer = page('pages/customer/pay/pay.js', api, { id: 20 });
  await customer.loadOrder();
  assert.strictEqual(customer.data.amount, '4.00');
  order.price = 6;
  const previousPostCount = posts.length;
  await customer.doPay();
  assert.strictEqual(customer.data.amount, '6.00');
  assert(customer.data.payErrorText.includes('价格已更新'));
  assert.strictEqual(posts.length, previousPostCount);
  console.log('PASS: technician revision, owner/paid guards, latest payment amount and stale-screen protection');
})().catch(error => { console.error(error); process.exitCode = 1; });
