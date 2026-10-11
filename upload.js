const path = require('path');

// Node 25 起 global.localStorage 变成内置对象(默认还没有 --experimental-webstorage
// 的完整实现),而 miniprogram-ci 2.1.31 的 debug.js 会直接调用
// `global.localStorage.getItem(...)`,于是抛 `r.getItem is not a function`。
// 这里在加载 miniprogram-ci 之前把不完整的 localStorage 清掉,让它回落到
// 主进程分支。
if (typeof globalThis.localStorage === 'object' && typeof globalThis.localStorage?.getItem !== 'function') {
  delete globalThis.localStorage;
}

const ci = require('miniprogram-ci');

const appid = 'wx2273201e59e280bc';
const version = process.env.VERSION || '1.0.0';
const desc = process.env.DESC || '立即修小程序:客户/师傅/管理端前端';
const privateKeyPath = process.env.WX_PRIVATE_KEY_PATH || 'D:/private.wx2273201e59e280bc.key';

const project = new ci.Project({
  appid,
  type: 'miniProgram',
  projectPath: path.join(__dirname, 'miniprogram'),
  privateKeyPath,
  ignores: ['node_modules/**/*'],
});

async function main() {
  console.log(`Uploading ${appid} ${version}`);
  await ci.upload({
    project,
    version,
    desc,
    setting: {
      es6: true,
      es7: true,
      minify: true,
      codeProtect: false,
      autoPrefixWXSS: true,
    },
    onProgressUpdate: console.log,
  });
  console.log('Upload complete');
  // ci.upload 的参数表里没有 envVersion(miniprogram-ci 2.1.31),
  // 产物永远是「开发版本」,别以为这里传完就是体验版了。
  console.log(
    '注意: 本次上传的是「开发版本」。体验版需人工在微信公众平台\n' +
      '      管理 → 版本管理 → 开发版本 → 选中该版本 → 选为体验版,\n' +
      '      再在「版本管理」里提交审核。微信未开放这一步的接口。'
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
