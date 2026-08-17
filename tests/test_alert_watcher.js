/**
 * alert_watcher 单元测试:用本地 mock webhook server 验证推送逻辑
 *
 * 启动 mock server → 注入 env → 跑单次 tick → 验证推送内容
 */
const http = require('http');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PROJECT_ROOT = path.join(__dirname, '..');
const STATE_FILE = path.join(os.tmpdir(), 'alert-watcher-test-state.json');

function startMockServer(port) {
  return new Promise((resolve) => {
    const received = [];
    const server = http.createServer((req, res) => {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', () => {
        received.push({ method: req.method, url: req.url, body: body || null });
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end('{"ok":true}');
      });
    });
    server.listen(port, '127.0.0.1', () => resolve({ server, received }));
  });
}

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const port = 18901 + Math.floor(Math.random() * 100);
  const { server, received } = await startMockServer(port);
  console.log('mock server on :' + port);

  // 删除 state file 重新开始
  try { fs.unlinkSync(STATE_FILE); } catch (e) {}

  // 跑 watcher 进程(单次模式)
  const child = spawn(process.execPath, [path.join(PROJECT_ROOT, 'scripts', 'alert_watcher.js'), '--once'], {
    env: {
      ...process.env,
      API_BASE: 'https://x.iddg.cn',
      DINGTALK_WEBHOOK: 'http://127.0.0.1:' + port + '/dingtalk',
      FEISHU_WEBHOOK: 'http://127.0.0.1:' + port + '/feishu',
      WEBHOOK_URL: 'http://127.0.0.1:' + port + '/generic',
      STATE_FILE,
      POLL_INTERVAL_SEC: '5',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  let stdout = '';
  let stderr = '';
  child.stdout.on('data', d => stdout += d);
  child.stderr.on('data', d => stderr += d);

  const exitCode = await new Promise(resolve => {
    child.on('exit', code => resolve(code));
    setTimeout(() => child.kill(), 20000);
  });

  server.close();

  console.log('---child exit code: ' + exitCode);
  console.log('---stdout:');
  console.log(stdout);
  if (stderr.trim()) {
    console.log('---stderr:');
    console.log(stderr);
  }
  console.log('---received (' + received.length + ' requests):');
  received.forEach((r, i) => {
    const body = r.body ? r.body.substring(0, 200) : '(empty)';
    console.log('  [' + (i + 1) + '] ' + r.method + ' ' + r.url + '  body=' + body);
  });

  // 校验
  let ok = true;
  const tests = [
    { name: 'child-exit-0', pass: exitCode === 0 },
    { name: 'received-some-requests', pass: received.length > 0 },
    { name: 'dingtalk-called', pass: received.some(r => r.url.includes('/dingtalk')) },
    { name: 'feishu-called', pass: received.some(r => r.url.includes('/feishu')) },
    { name: 'generic-called', pass: received.some(r => r.url.includes('/generic')) },
  ];

  // 验证推送 body 包含告警特征(reconcile_mismatch 或 critical)
  const allBodies = received.map(r => r.body || '').join('\n');
  tests.push({ name: 'body-contains-critical-or-reconcile', pass: /critical|reconcile|alert/i.test(allBodies) });

  // 验证 state file 写入
  const stateWritten = fs.existsSync(STATE_FILE);
  tests.push({ name: 'state-file-written', pass: stateWritten });

  console.log('---');
  let pass = 0, fail = 0;
  for (const t of tests) {
    console.log((t.pass ? 'OK  ' : 'FAIL') + ' ' + t.name);
    if (t.pass) pass++; else { fail++; ok = false; }
  }
  console.log(pass + '/' + (pass + fail) + ' passed');

  process.exit(ok ? 0 : 1);
}

main().catch(e => { console.error(e); process.exit(1); });
