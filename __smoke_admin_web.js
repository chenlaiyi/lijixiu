/**
 * 临时脚本:管理后台 admin-web 端到端冒烟测试(登录态 + 15 个视图)。
 *
 * 前置:
 *   1. 后端:uvicorn app.main:app --port 8010
 *   2. 静态服务:python -m http.server 8020 --directory admin-web
 *
 * 用 Playwright 的 route 拦截把 /api/** 反向代理到 8010,保持同源。
 * 跑完即删。
 */
const { chromium } = require('playwright');

const ADMIN_BASE = 'http://127.0.0.1:8020';
const API_BASE = 'http://127.0.0.1:8010';

const VIEWS = [
  'overview', 'orders', 'users', 'repairers', 'stores', 'regions', 'proxy',
  'domestic', 'payroll', 'warranties', 'wallet', 'finance', 'support',
  'packages', 'ops',
];

async function fetchAdminToken() {
  const res = await fetch(`${API_BASE}/api/v1/auth/wechat-login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: '18800000000:演示管理员:admin' }),
  });
  if (!res.ok) throw new Error(`login failed ${res.status}`);
  const data = await res.json();
  return data.token;
}

(async () => {
  const token = await fetchAdminToken();
  // 本机 ms-playwright 里是 chromium-1223,而当前 playwright 包期望 1234,
  // 所以显式指定已安装的二进制。
  const os = require('os');
  const path = require('path');
  const exe = path.join(
    os.homedir(),
    'AppData/Local/ms-playwright/chromium-1223/chrome-win64/chrome.exe'
  );
  const browser = await chromium.launch({
    headless: false,
    args: ['--headless=new'],
    executablePath: exe,
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });

  // 同源反向代理(/api,/health,/metrics 都归后端)
  await context.route('**', async (route) => {
    const url = new URL(route.request().url());
    if (
      url.pathname.startsWith('/api/') ||
      url.pathname === '/health' ||
      url.pathname.startsWith('/metrics')
    ) {
      const response = await route.fetch({ url: API_BASE + url.pathname + url.search });
      await route.fulfill({ response });
      return;
    }
    await route.continue();
  });

  const page = await context.newPage();
  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`));

  const badResponses = [];
  page.on('response', (res) => {
    if (res.status() >= 400) {
      badResponses.push(`HTTP ${res.status()} ${res.url()}`);
    }
  });

  const results = [];
  const check = (label, ok, detail = '') => {
    results.push({ label, ok, detail });
    console.log(`  ${ok ? 'OK  ' : 'FAIL'} ${label}${detail ? ' — ' + detail : ''}`);
  };

  console.log('== 1. 未登录应看到登录页 ==');
  await page.goto(`${ADMIN_BASE}/index.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  const gateTitle = await page.locator('.auth-gate h2').first().textContent().catch(() => null);
  check('登录页渲染', gateTitle === '后台登录', `h2=${gateTitle}`);

  console.log('\n== 2. 错误 token 应被拒绝 ==');
  await page.fill('#auth-token', 'not-a-real-token');
  await page.click('.auth-gate button[type=submit]');
  await page.waitForTimeout(900);
  const stillGate = await page.locator('.auth-gate').count();
  const notice = await page.locator('.auth-gate .notice').first().textContent().catch(() => '');
  check('错误 token 停留在登录页', stillGate === 1, `notice=${(notice || '').trim().slice(0, 40)}`);

  console.log('\n== 3. 正确 token 登录并加载概览 ==');
  await page.fill('#auth-token', token);
  await page.click('.auth-gate button[type=submit]');
  await page.waitForTimeout(1500);
  const actor = await page.locator('#auth-actor').textContent().catch(() => '');
  check('顶部显示登录身份', /平台管理员|platform_admin/.test(actor), `actor=${(actor || '').trim()}`);
  const sections = await page.locator('#content .section').count();
  check('概览页渲染出区块', sections > 0, `sections=${sections}`);

  console.log('\n== 4. 逐个切换 15 个视图 ==');
  for (const view of VIEWS) {
    await page.click(`.nav-item[data-view="${view}"]`);
    await page.waitForTimeout(700);
    const title = (await page.locator('#view-title').textContent().catch(() => '')) || '';
    const body = await page.locator('#content').innerText().catch(() => '');
    const hasError = /请求失败|admin only|not logged in|加载失败/.test(body);
    check(`视图 ${view}`, title.trim().length > 0 && !hasError, `title=${title.trim().slice(0, 20)}`);
    if (/401|403/.test(body)) console.log('     body 片段:', body.slice(0, 160).replace(/\s+/g, ' '));
  }

  console.log('\n== 5. 提现视图应能拿到真实数据(需要 admin token)==');
  await page.click('.nav-item[data-view="wallet"]');
  await page.waitForTimeout(900);
  const walletBody = await page.locator('#content').innerText();
  check('提现页无鉴权报错', !/not logged in|admin only/.test(walletBody));

  console.log('\n== 6. 对账告警视图 ==');
  await page.click('.nav-item[data-view="ops"]');
  await page.waitForTimeout(900);
  const opsBody = await page.locator('#content').innerText();
  check('对账告警页无鉴权报错', !/not logged in|admin only/.test(opsBody));

  console.log('\n== 7. 退出登录 ==');
  await page.goto(`${ADMIN_BASE}/index.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const reloginGate = await page.locator('.auth-gate').count();
  check('刷新后仍保持登录(有 token)', reloginGate === 0, `auth-gate=${reloginGate}`);

  const shotDir = path.join(__dirname, 'design', 'screenshots');
  require('fs').mkdirSync(shotDir, { recursive: true });
  await page.click('.nav-item[data-view="ops"]');
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(shotDir, 'admin-ops-authed.png'), fullPage: false });
  await page.click('.nav-item[data-view="overview"]');
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(shotDir, 'admin-overview-authed.png'), fullPage: false });
  console.log('  截图: design/screenshots/admin-overview-authed.png / admin-ops-authed.png');

  await page.click('#logout-btn');
  await page.waitForTimeout(400);
  const afterLogout = await page.locator('.auth-gate').count();
  check('退出后回到登录页', afterLogout === 1);
  await page.screenshot({ path: path.join(shotDir, 'admin-login-gate.png'), fullPage: false });

  console.log('\n== console 错误 ==');
  if (consoleErrors.length === 0) {
    console.log('  OK   无 console 报错');
  } else {
    consoleErrors.slice(0, 10).forEach((e) => console.log('  ERR  ' + e.slice(0, 160)));
  }

  console.log('\n== 4xx/5xx 响应 ==');
  const unique = [...new Set(badResponses)];
  unique.slice(0, 20).forEach((e) => console.log('  ' + e));

  const failed = results.filter((r) => !r.ok);
  console.log(`\n结果:${results.length - failed.length}/${results.length} 通过`);
  // 唯一允许的 4xx:步骤 2 故意用错误 token 触发的一次 401
  const unexpected = [...new Set(badResponses)].filter(
    (e) => !/401 .*\/api\/v1\/auth\/me/.test(e)
  );
  if (unexpected.length) {
    console.log('非预期 4xx/5xx:', unexpected.join(' | '));
  }
  await browser.close();
  const offendingConsole = consoleErrors.filter((e) => !/status of 401/.test(e));
  process.exit(failed.length === 0 && unexpected.length === 0 && offendingConsole.length === 0 ? 0 : 1);
})();
