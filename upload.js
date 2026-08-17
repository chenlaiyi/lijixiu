const path = require('path');
const ci = require('miniprogram-ci');

const appid = 'wx2273201e59e280bc';
const version = process.env.VERSION || '1.0.0';
const desc = process.env.DESC || '立即修小程序体验版：客户/师傅/管理端前端';
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
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
