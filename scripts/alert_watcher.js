/**
 * 告警 watcher:轮询 /api/v1/admin/alerts 推送告警到钉钉/飞书/通用 webhook
 *
 * 用法:
 *   # 默认(读 .env)
 *   node scripts/alert_watcher.js
 *
 *   # 轮询间隔 30s
 *   POLL_INTERVAL_SEC=30 node scripts/alert_watcher.js
 *
 *   # 自定义通道
 *   DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=XXX \
 *   FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/XXX \
 *   node scripts/alert_watcher.js
 *
 *   # 单次跑(用于 CI / cron)
 *   node scripts/alert_watcher.js --once
 *
 * 必需环境变量:
 *   - API_BASE              (默认 https://x.iddg.cn)
 *   - ADMIN_TOKEN 或 配合 ADMIN_PHONE/ADMIN_NAME 自动登录
 *
 * 可选(任一):
 *   - DINGTALK_WEBHOOK  钉钉机器人 webhook(加 ?access_token=XXX)
 *   - FEISHU_WEBHOOK    飞书机器人 webhook
 *   - WEBHOOK_URL       通用 webhook(POST JSON {title, body, severity, type})
 *   - DINGTALK_SECRET   钉钉签名密钥(可选,加签验证)
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const BASE = process.env.API_BASE || 'https://x.iddg.cn';
const INTERVAL = parseInt(process.env.POLL_INTERVAL_SEC || '60', 10) * 1000;
const STATE_FILE = process.env.STATE_FILE || path.join(__dirname, '..', 'docs', 'alert-watcher-state.json');
const ONLY_ONCE = process.argv.includes('--once');

let _token = process.env.ADMIN_TOKEN || '';
let _tokenExpiresAt = 0;

async function loginAdmin() {
  const phone = process.env.ADMIN_PHONE || '18800000000';
  const name = process.env.ADMIN_NAME || '演示管理员';
  const res = await fetch(`${BASE}/api/v1/auth/wechat-login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: `${phone}:${name}:admin` }),
  });
  if (!res.ok) throw new Error(`admin login failed: ${res.status} ${await res.text()}`);
  const data = await res.json();
  return data.token;
}

async function getToken() {
  if (_token && Date.now() < _tokenExpiresAt - 5 * 60 * 1000) return _token;
  _token = await loginAdmin();
  _tokenExpiresAt = Date.now() + 23 * 60 * 60 * 1000;  // 23h
  return _token;
}

async function fetchAlerts() {
  const token = await getToken();
  const res = await fetch(`${BASE}/api/v1/admin/alerts?resolved=false&limit=200`, {
    headers: { Authorization: 'Bearer ' + token },
  });
  if (!res.ok) throw new Error(`fetch alerts failed: ${res.status}`);
  return (await res.json()) || [];
}

function loadState() {
  try {
    return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
  } catch (e) {
    return { sent: {}, last_run: null };
  }
}

function saveState(state) {
  fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true });
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), 'utf8');
}

function escapeHtml(s) {
  return String(s || '').replace(/[<>&"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]));
}

function alertToMessage(alert) {
  const sev = String(alert.severity || 'info').toUpperCase();
  return {
    title: `[${sev}] ${alert.type}`,
    body: [
      `Alert #${alert.id}`,
      `Type: ${alert.type}`,
      `Severity: ${sev}`,
      alert.user_id ? `User: #${alert.user_id}` : null,
      alert.amount != null ? `Amount: ${alert.amount}` : null,
      `Message: ${alert.message}`,
      alert.detail ? `Detail: ${alert.detail}` : null,
      `Created: ${alert.created_at}`,
    ].filter(Boolean).join('\n'),
    severity: alert.severity,
    type: alert.type,
    alert,
  };
}

async function sendDingtalk(msg) {
  const url = process.env.DINGTALK_WEBHOOK;
  if (!url) return { skipped: true };
  const payload = {
    msgtype: 'markdown',
    markdown: {
      title: msg.title,
      text: `## ${msg.title}\n\n${msg.body.replace(/\n/g, '\n\n')}`,
    },
  };
  // 签名
  if (process.env.DINGTALK_SECRET) {
    const ts = Date.now();
    const stringToSign = `${ts}\n${process.env.DINGTALK_SECRET}`;
    const sign = crypto.createHmac('sha256', process.env.DINGTALK_SECRET)
      .update(stringToSign).digest('base64');
    payload.timestamp = ts;
    payload.sign = sign;
  }
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return { status: res.status, body: await res.text() };
}

async function sendFeishu(msg) {
  const url = process.env.FEISHU_WEBHOOK;
  if (!url) return { skipped: true };
  const payload = {
    msg_type: 'interactive',
    card: {
      header: {
        title: { tag: 'plain_text', content: msg.title },
        template: msg.severity === 'critical' ? 'red' : msg.severity === 'warning' ? 'orange' : 'blue',
      },
      elements: [
        { tag: 'markdown', content: msg.body },
      ],
    },
  };
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return { status: res.status, body: await res.text() };
}

async function sendGeneric(msg) {
  const url = process.env.WEBHOOK_URL;
  if (!url) return { skipped: true };
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(msg),
  });
  return { status: res.status, body: await res.text() };
}

async function dispatch(msg) {
  const results = await Promise.all([
    sendDingtalk(msg).catch(e => ({ error: e.message })),
    sendFeishu(msg).catch(e => ({ error: e.message })),
    sendGeneric(msg).catch(e => ({ error: e.message })),
  ]);
  return results;
}

async function tick() {
  let alerts;
  try {
    alerts = await fetchAlerts();
  } catch (e) {
    console.error('[' + new Date().toISOString() + '] fetch alerts failed:', e.message);
    return;
  }

  const state = loadState();
  const toSend = alerts.filter(a => !state.sent[String(a.id)]);

  if (toSend.length === 0) {
    console.log('[' + new Date().toISOString() + '] no new alerts (total=' + alerts.length + ')');
    state.last_run = new Date().toISOString();
    saveState(state);
    return;
  }

  console.log('[' + new Date().toISOString() + '] new alerts: ' + toSend.length);
  for (const a of toSend) {
    const msg = alertToMessage(a);
    console.log('  → alert#' + a.id + ' ' + a.severity + ' ' + a.type);
    const results = await dispatch(msg);
    results.forEach((r, i) => {
      const channel = ['dingtalk', 'feishu', 'generic'][i];
      if (r.skipped) return;
      if (r.error) console.log('    ' + channel + ' err: ' + r.error);
      else console.log('    ' + channel + ' ' + r.status);
    });
    state.sent[String(a.id)] = new Date().toISOString();
  }

  state.last_run = new Date().toISOString();
  saveState(state);
}

async function main() {
  if (!process.env.DINGTALK_WEBHOOK && !process.env.FEISHU_WEBHOOK && !process.env.WEBHOOK_URL) {
    console.log('WARNING: 未配置任何通知通道(DINGTALK_WEBHOOK / FEISHU_WEBHOOK / WEBHOOK_URL)');
    console.log('只会拉取并打印告警,不会推送。');
  }

  if (ONLY_ONCE) {
    await tick();
    return;
  }

  console.log('==> alert watcher 启动');
  console.log('    base: ' + BASE);
  console.log('    interval: ' + INTERVAL + 'ms');
  console.log('    state: ' + STATE_FILE);

  while (true) {
    await tick();
    await new Promise(r => setTimeout(r, INTERVAL));
  }
}

main().catch(e => { console.error(e); process.exit(1); });
