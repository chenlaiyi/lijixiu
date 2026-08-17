/**
 * H5 截图工具 — 用 Edge 远程调试 + Playwright connectOverCDP
 *
 * 流程:
 *  1. 启动 Edge 远程调试端口(调用方负责)
 *  2. 对每个 demo 角色,调 /api/v1/auth/wechat-login 拿 token
 *  3. 注入到 H5 的 localStorage(h5_token / h5_user / h5_view_role)
 *  4. 逐个 tab 截图,保存到 design/screenshots/
 *
 * 用法:
 *   # 终端 1:启动 Edge 远程调试
 *   "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" ^
 *     --remote-debugging-port=9222 ^
 *     --user-data-dir=D:\app\xiulijiu\.edge-profile ^
 *     --no-first-run --no-default-browser-check
 *
 *   # 终端 2:跑脚本
 *   node scripts/screenshot_h5.js
 *
 * 环境变量(可选):
 *   BASE_URL  默认 https://x.iddg.cn
 *   OUT_DIR   默认 design/screenshots
 */
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const BASE_URL = process.env.BASE_URL || 'https://x.iddg.cn';
const OUT_DIR = process.env.OUT_DIR || path.join(__dirname, '..', 'design', 'screenshots');
const VIEWPORT = { width: 390, height: 844 };

// demo 角色(与 scripts/seed_demo_data.py 保持一致)
const ROLES = [
  { key: 'admin',          phone: '18800000000', name: '演示管理员',     role: 'admin' },
  { key: 'customer',       phone: '18800000001', name: '演示客户',       role: 'customer' },
  { key: 'repairer',       phone: '18800000002', name: '演示师傅张工',   role: 'repairer' },
  { key: 'second',         phone: '18800000003', name: '演示二接师傅李工', role: 'second_receiver' },
  { key: 'store_manager',  phone: '18800000004', name: '演示门店店长',   role: 'store_manager' },
  { key: 'city_manager',   phone: '18800000005', name: '演示城市经理',   role: 'city_manager' },
  { key: 'channel',        phone: '18800000006', name: '演示推广经理',   role: 'promotion_manager' },
  { key: 'tech_support',   phone: '18800000007', name: '演示服务保障',   role: 'tech_support' },
  { key: 'finance',        phone: '18800000008', name: '演示财务',       role: 'finance' },
];

// 角色对应 H5 的 tab 列表(从 h5/app.js 抽出来)
const TABS = {
  customer: ['home', 'orders', 'domestic', 'warranties', 'addresses', 'packages', 'support', 'wallet'],
  repairer: ['jobs', 'workbench', 'earnings', 'repairerProfile', 'proxyOrders'],
  second_receiver: ['jobs', 'workbench', 'earnings', 'repairerProfile', 'proxyOrders'],
  store_manager: ['overview', 'adminOrders', 'proxyOrders', 'domestic', 'adminRepairers', 'payroll', 'adminFinance', 'adminSupport'],
  city_manager: ['overview', 'adminOrders', 'adminStores', 'domestic', 'adminFinance', 'adminAlerts'],
  promotion_manager: ['proxyOrders', 'orders', 'earnings'],
  tech_support: ['domestic', 'adminSupport', 'adminOrders'],
  finance: ['adminFinance', 'payroll', 'adminOrders', 'adminAlerts'],
  admin: ['overview', 'adminOrders', 'adminUsers', 'adminRepairers', 'adminStores', 'adminPackages', 'adminFinance', 'adminSupport', 'adminAlerts'],
  platform_admin: ['overview', 'adminOrders', 'adminUsers', 'adminRepairers', 'adminStores', 'adminPackages', 'adminFinance', 'adminSupport', 'adminAlerts'],
};

async function fetchToken(role) {
  const res = await fetch(`${BASE_URL}/api/v1/auth/wechat-login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: `${role.phone}:${role.name}:${role.role}` }),
  });
  if (!res.ok) {
    throw new Error(`login ${role.key} ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

async function captureForRole(browser, role) {
  console.log(`\n[${role.key}] login + capture`);
  let loginResp;
  try {
    loginResp = await fetchToken(role);
  } catch (e) {
    console.log(`  SKIP: ${e.message}`);
    return { ok: false, error: e.message };
  }
  const user = loginResp.user;
  const token = loginResp.token;
  const viewRole = user.business_role || user.role;

  const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2 });
  const page = await ctx.newPage();

  // 先打开 host(注入 localStorage 必须在同源)
  await page.goto(`${BASE_URL}/h5/`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(
    ([t, u, r]) => {
      localStorage.setItem('h5_token', t);
      localStorage.setItem('h5_user', JSON.stringify(u));
      localStorage.setItem('h5_view_role', r);
    },
    [token, user, viewRole]
  );

  // 重新加载,让 H5 读取登录态
  await page.goto(`${BASE_URL}/h5/`, { waitUntil: 'networkidle', timeout: 15000 });

  const tabs = TABS[viewRole] || TABS[role.role] || ['overview'];
  const roleDir = path.join(OUT_DIR, role.key);
  fs.mkdirSync(roleDir, { recursive: true });

  // 首屏
  await page.screenshot({ path: path.join(roleDir, '00-home.png'), fullPage: false });

  // 各 tab
  for (const tab of tabs) {
    try {
      // 通过 localStorage 切 tab 然后 reload
      await page.evaluate((t) => {
        localStorage.setItem('h5_tab', t);
      }, tab);
      await page.goto(`${BASE_URL}/h5/`, { waitUntil: 'networkidle', timeout: 15000 });
      await page.waitForTimeout(400);
      const file = path.join(roleDir, `tab-${tab}.png`);
      await page.screenshot({ path: file, fullPage: false });
      console.log(`  ✓ ${tab}`);
    } catch (e) {
      console.log(`  ✗ ${tab}: ${e.message.split('\n')[0]}`);
    }
  }

  await ctx.close();
  return { ok: true, tabs: tabs.length };
}

async function main() {
  if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222', { timeout: 8000 });
  } catch (e) {
    console.error('连接 Edge 远程调试失败:http://localhost:9222');
    console.error('请先启动 Edge:');
    console.error('  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" \\');
    console.error('    --remote-debugging-port=9222 \\');
    console.error('    --user-data-dir=D:\\app\\xiulijiu\\.edge-profile');
    process.exit(1);
  }

  const summary = [];
  for (const role of ROLES) {
    try {
      const r = await captureForRole(browser, role);
      summary.push({ role: role.key, ...r });
    } catch (e) {
      console.log(`[${role.key}] FATAL: ${e.message}`);
      summary.push({ role: role.key, ok: false, error: e.message });
    }
  }

  // 写一份 manifest
  const manifest = {
    base_url: BASE_URL,
    viewport: VIEWPORT,
    generated_at: new Date().toISOString(),
    results: summary,
  };
  fs.writeFileSync(path.join(OUT_DIR, 'manifest.json'), JSON.stringify(manifest, null, 2));
  console.log(`\nManifest: ${path.join(OUT_DIR, 'manifest.json')}`);
  console.log(`OK: ${summary.filter(s => s.ok).length} / ${summary.length}`);

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
