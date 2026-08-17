const { chromium } = require('playwright-core');
(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9222', { timeout: 8000 });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:8765/h5/', { waitUntil: 'networkidle' });
  await page.evaluate(() => localStorage.clear());
  await page.goto('http://127.0.0.1:8765/h5/', { waitUntil: 'networkidle' });
  const info = await page.evaluate(() => {
    const img = document.querySelector('.login-brand .brand-mark img');
    const cs = getComputedStyle(img);
    return {
      cssWidth: cs.width,
      cssHeight: cs.height,
      cssMaxWidth: cs.maxWidth,
      cssMaxHeight: cs.maxHeight,
      objectFit: cs.objectFit,
      parent: img.parentElement.className,
      parentCss: (() => { const p = getComputedStyle(img.parentElement); return { width: p.width, height: p.height, overflow: p.overflow, display: p.display }; })(),
    };
  });
  console.log(JSON.stringify(info, null, 2));
  await browser.close();
})();
