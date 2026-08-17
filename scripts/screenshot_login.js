/**
 * 登录页截图工具 — 截 PC 桌面 + 移动端两种尺寸
 * 用法: node scripts/screenshot_login.js
 */
const { chromium } = require('playwright-core');
const path = require('path');
const fs = require('fs');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8765/h5/';
const OUT_DIR = process.env.OUT_DIR || path.join(__dirname, '..', 'design', 'screenshots', 'login-v2');

const VIEWS = [
  { name: 'pc-1440',      width: 1440, height: 900,  dpr: 1 },
  { name: 'pc-1280',      width: 1280, height: 800,  dpr: 1 },
  { name: 'tablet-820',   width: 820,  height: 1180, dpr: 2 },
  { name: 'mobile-390',   width: 390,  height: 844,  dpr: 2 },
];

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222', { timeout: 8000 });
  } catch (e) {
    console.error('连接 Edge 远程调试失败。请先启动 Edge:');
    console.error('  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" \\');
    console.error('    --remote-debugging-port=9222 \\');
    console.error('    --user-data-dir=D:\\app\\xiulijiu\\.edge-profile');
    process.exit(1);
  }

  // 默认手机模式
  for (const v of VIEWS) {
    const ctx = await browser.newContext({
      viewport: { width: v.width, height: v.height },
      deviceScaleFactor: v.dpr,
    });
    const page = await ctx.newPage();
    await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 15000 });
    // 清掉 localStorage,确保看到登录页
    await page.evaluate(() => localStorage.clear());
    await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(500);
    const file = path.join(OUT_DIR, `${v.name}.png`);
    await page.screenshot({ path: file, fullPage: false });
    console.log(`  ✓ ${v.name} → ${file}`);

    // 微信登录 tab 截图(只对第一个视口)
    if (v.name === 'pc-1440' || v.name === 'mobile-390') {
      try {
        const tab = await page.$('[data-login-tab="wechat"]');
        if (tab) {
          await tab.click();
          await page.waitForTimeout(400);
          const file2 = path.join(OUT_DIR, `${v.name}-wechat.png`);
          await page.screenshot({ path: file2, fullPage: false });
          console.log(`  ✓ ${v.name}-wechat → ${file2}`);
        }
      } catch (e) {
        console.log(`  ✗ ${v.name}-wechat: ${e.message}`);
      }
    }
    await ctx.close();
  }

  await browser.close();
  console.log('\nDone.');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
