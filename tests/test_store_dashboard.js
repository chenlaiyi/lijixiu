const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const sourcePath = path.join(__dirname, '../miniprogram/pages/store/dashboard/dashboard.js');
const source = fs.readFileSync(sourcePath, 'utf8');

function harness(user, stores) {
  let definition;
  let orders = [];
  let stopped = false;
  const calls = [];
  const api = {
    async get(url) {
      calls.push(url);
      if (url === '/api/v1/stores') return stores;
      if (url.startsWith('/api/v1/repairers')) return [];
      if (url.startsWith('/api/v1/orders?')) return orders;
      throw new Error(`Unexpected request: ${url}`);
    },
  };
  vm.runInNewContext(source, {
    Page(value) { definition = value; },
    require(name) {
      if (name.endsWith('/api')) return api;
      if (name.endsWith('/share')) return { create: () => ({}) };
      return {};
    },
    wx: {
      getStorageSync: () => user,
      stopPullDownRefresh() { stopped = true; },
      showToast() {},
    },
  });
  const page = { ...definition, data: { ...definition.data } };
  page.setData = values => Object.assign(page.data, values);
  page.formatOrder = order => order;
  return { page, calls, setOrders(value) { orders = value; }, stopped: () => stopped };
}

(async () => {
  // Newest store comes first: a manager must still get their own older store.
  const owned = harness({ id: '7' }, [{ id: 4, manager_id: 21 }, { id: 3, manager_id: 7 }]);
  await owned.page.loadData();
  assert.strictEqual(owned.page.data.store.id, 3);
  assert(owned.calls.includes('/api/v1/orders?store_id=3&limit=100'));

  // An unbound account must never query the newest, unrelated store.
  const unbound = harness({ id: 99 }, [{ id: 4, manager_id: 21 }]);
  await unbound.page.loadData();
  assert.strictEqual(unbound.page.data.store, null);
  assert.strictEqual(unbound.page.data.workflowHint.title, '未绑定门店');
  assert(!unbound.calls.some(url => url.startsWith('/api/v1/orders?')));

  // Pull-down refresh must fetch a newly arrived order, then stop the spinner.
  const config = JSON.parse(fs.readFileSync(sourcePath.replace(/\.js$/, '.json'), 'utf8'));
  assert.strictEqual(config.enablePullDownRefresh, true);
  owned.setOrders([{ id: 10, status: 'store_pending' }]);
  owned.page.onPullDownRefresh();
  await new Promise(resolve => setImmediate(resolve));
  assert.strictEqual(owned.page.data.orders[0].id, 10);
  assert.strictEqual(owned.page.data.stats.pending, 1);
  assert(owned.stopped());
  console.log('PASS: own-store binding, unbound account isolation, new-order refresh');
})().catch(error => { console.error(error); process.exitCode = 1; });
