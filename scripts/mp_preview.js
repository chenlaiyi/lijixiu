/**
 * 生成小程序预览二维码(proof that the uploaded build is previewable)。
 *
 * 用法:
 *   node scripts/mp_preview.js            # 输出 dist/mp-preview.jpg
 *   $env:PAGE_PATH="pages/login/login"; node scripts/mp_preview.js
 *
 * 需要 miniprogram-ci 私钥(默认 D:/private.wx2273201e59e280bc.key)。
 * 产物落在 dist/(已 gitignore),不要提交。
 */
const fs = require('fs');
const path = require('path');

// Node 25 的 global.localStorage 没有 getItem,会让 miniprogram-ci 抛
// `r.getItem is not a function`;清掉它回落到主进程分支。
if (typeof globalThis.localStorage === 'object' && typeof globalThis.localStorage?.getItem !== 'function') {
  delete globalThis.localStorage;
}

const ci = require('miniprogram-ci');

const appid = 'wx2273201e59e280bc';
const privateKeyPath = process.env.WX_PRIVATE_KEY_PATH || 'D:/private.wx2273201e59e280bc.key';
const outDir = path.join(__dirname, '..', 'dist');
const outFile = path.join(outDir, 'mp-preview.jpg');

const project = new ci.Project({
  appid,
  type: 'miniProgram',
  projectPath: path.join(__dirname, '..', 'miniprogram'),
  privateKeyPath,
  ignores: ['node_modules/**/*'],
});

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  const result = await ci.preview({
    project,
    desc: process.env.DESC || '立即修 预览(v1.0.222 鉴权收口)',
    setting: { es6: true, es7: true, minify: true, autoPrefixWXSS: true },
    qrcodeFormat: 'image',
    qrcodeOutputDest: outFile,
    pagePath: process.env.PAGE_PATH || 'pages/login/login',
    onProgressUpdate: () => {},
  });
  const size = fs.existsSync(outFile) ? fs.statSync(outFile).size : 0;
  console.log('preview ok:', JSON.stringify(result));
  console.log(`二维码:${outFile}(${size} bytes)`);
}

main().catch((error) => {
  console.error('preview failed:', error && error.message ? error.message : error);
  process.exit(1);
});
