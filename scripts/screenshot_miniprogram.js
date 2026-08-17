const { chromium } = require('playwright-core');
const path = require('path');

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9222', { timeout: 8000 });
  const ctx = await browser.newContext({
    viewport: { width: 800, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();
  const fileUrl = 'file:///' + path.resolve('D:/app/xiulijiu/scripts/preview_miniprogram.html').replace(/\\/g, '/');
  await page.goto(fileUrl, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);

  const outDir = 'D:/app/xiulijiu/design/screenshots/login-v2';
  // 默认 wechat tab
  await page.screenshot({ path: path.join(outDir, 'miniprogram-wechat.png'), fullPage: false });
  console.log('OK wechat');

  // 切到 phone
  await page.click('.login-tab[data-mode="phone"]');
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(outDir, 'miniprogram-phone.png'), fullPage: false });
  console.log('OK phone');

  // 切到 account
  await page.evaluate(() => {
    // 先点 wechat tab 让自己能切换,再模拟账号密码(实际是 phone tab 的 link row)
    document.querySelector('.login-tab[data-mode="phone"]').click();
    setTimeout(() => {
      const links = document.querySelectorAll('.login-pane[data-pane="phone"] .login-link');
      if (links[0]) links[0].click();
    }, 200);
  });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(outDir, 'miniprogram-account.png'), fullPage: false });
  console.log('OK account');

  await browser.close();
})();
