/**
 * 安全头 + 鉴权审计(2026-08-09)
 *
 * 检查项:
 *  - 安全响应头(HSTS / X-Frame-Options / X-Content-Type-Options / CSP / Permissions-Policy)
 *  - 公网可访问的端点是否带鉴权(/docs, /metrics, /admin, /api/v1/auth/*)
 *  - SSL 证书
 *
 * 用法:
 *   node scripts/security_audit.js                  # 跑全部
 *   node scripts/security_audit.js --url https://x.iddg.cn
 */
const https = require('https');
const http = require('http');
const { URL } = require('url');

const DEFAULT_URL = process.env.BASE_URL || 'https://x.iddg.cn';
const URL_ = process.argv.includes('--url')
  ? process.argv[process.argv.indexOf('--url') + 1]
  : DEFAULT_URL;

const CHECKS = [
  // 头检查
  { type: 'header', url: '/', expect: 'X-Frame-Options', required: true },
  { type: 'header', url: '/', expect: 'X-Content-Type-Options', required: true },
  { type: 'header', url: '/', expect: 'Strict-Transport-Security', required: true },
  { type: 'header', url: '/', expect: 'Content-Security-Policy', required: true },
  { type: 'header', url: '/', expect: 'Referrer-Policy', required: true },
  { type: 'header', url: '/', expect: 'Permissions-Policy', required: false, note: '建议加,部分老浏览器不识别' },
  { type: 'header', url: '/', expect: 'Server', required: false, expectMissing: true, note: '应隐藏 server 版本信息' },
  { type: 'header', url: '/', expect: 'X-Powered-By', required: false, expectMissing: true, note: '应隐藏框架信息' },

  // 公网可访问端点
  { type: 'auth', url: '/docs', expectStatus: 401, required: true, note: 'Swagger UI 必须带鉴权' },
  { type: 'auth', url: '/redoc', expectStatus: 401, required: true, note: 'Redoc UI 必须带鉴权' },
  { type: 'auth', url: '/openapi.json', expectStatus: 401, required: true, note: 'OpenAPI schema 必须带鉴权' },
  { type: 'auth', url: '/metrics', expectStatus: 401, required: true, note: 'Prometheus 指标必须带鉴权' },
  // 2026-10-07:后台改为「一层鉴权」——静态页(登录卡片)公网可读,
  // 鉴权落在后台登录接口 + 管理 API 上。因此这里断言:
  //   /admin/ 返回 200,但只是页面外壳(登录表单由 app.js 渲染),
  //   且不含任何真实业务数据 / 演示账号手机号
  //   管理 API 无 token 必须 401(见下面两条)
  {
    type: 'body', url: '/admin/', expectStatus: 200, required: true,
    // 外壳标志:标题 + 挂载点 + 自己的脚本
    mustInclude: ['立即修管理后台', 'app.js', '<body'],
    // 真数据才算泄露;platform_admin 是前端做角色判断的字面量,不算数据
    mustExclude: ['演示管理员', '18800000000', 'available_balance', '演示客户'],
    note: 'Admin 页面外壳可读,但不含业务数据/账号',
  },
  { type: 'auth', url: '/admin/index.html', expectStatus: 200, required: true, note: 'Admin 登录页入口' },
  { type: 'auth', url: '/.env', expectStatus: [404, 401], required: true, note: '.env 不可外泄' },
  { type: 'auth', url: '/api/v1/wallet/balance/1', expectStatus: 401, required: true, note: '钱包余额必须鉴权' },
  { type: 'auth', url: '/api/v1/admin/alerts', expectStatus: 401, required: true, note: 'Admin API 必须鉴权' },
  { type: 'auth', url: '/api/v1/admin/reconcile/run', expectStatus: 401, required: true, method: 'POST' },
  { type: 'auth', url: '/health', expectStatus: 200, required: true, note: '健康检查必须 200' },
];

function fetch_(urlStr, method = 'GET', redirect = 'manual') {
  return new Promise((resolve, reject) => {
    const u = new URL(urlStr);
    const lib = u.protocol === 'https:' ? https : http;
    const req = lib.request({
      hostname: u.hostname,
      port: u.port || (u.protocol === 'https:' ? 443 : 80),
      path: u.pathname + u.search,
      method,
      headers: { 'User-Agent': 'xiulijiu-security-audit/1.0' },
    }, (res) => {
      const headers = {};
      for (const [k, v] of Object.entries(res.headers)) headers[k.toLowerCase()] = v;
      let body = '';
      res.on('data', d => body += d);
      res.on('end', () => resolve({ status: res.statusCode, headers, body, redirected: res.statusCode >= 300 && res.statusCode < 400 }));
    });
    req.on('error', reject);
    req.end();
  });
}

async function main() {
  console.log('==> 安全头 + 鉴权审计');
  console.log('    target: ' + URL_);
  console.log('');

  const results = [];
  for (const c of CHECKS) {
    const url = URL_.replace(/\/$/, '') + c.url;
    let res;
    try {
      res = await fetch_(url, c.method || 'GET');
    } catch (e) {
      results.push({ ...c, status: null, error: e.message, ok: false });
      console.log('  ERR  ' + c.url + '  ' + e.message);
      continue;
    }

    let ok = false;
    let detail = '';
    if (c.type === 'header') {
      const present = Object.keys(res.headers).includes(c.expect.toLowerCase());
      if (c.expectMissing) {
        ok = !present;
        detail = c.expect + (present ? ' 不应出现(出现了)' : ' 未出现 ✓');
      } else {
        ok = present;
        detail = c.expect + (present ? ' = ' + res.headers[c.expect.toLowerCase()] : ' 缺失 ✗');
      }
    } else if (c.type === 'auth') {
      const expectStatuses = Array.isArray(c.expectStatus) ? c.expectStatus : [c.expectStatus];
      ok = expectStatuses.includes(res.status);
      detail = 'status=' + res.status + ' (期望 ' + expectStatuses.join('/') + ')';
    } else if (c.type === 'body') {
      // 2026-10-07:/admin/ 现在是公网可读的登录页(一层鉴权),
      // 所以必须证明它「只有登录表单、没有业务数据」。
      const expectStatuses = Array.isArray(c.expectStatus) ? c.expectStatus : [c.expectStatus];
      const statusOk = expectStatuses.includes(res.status);
      const hasMarker = c.mustInclude.every(s => res.body.includes(s));
      const forbidden = (c.mustExclude || []).filter(s => res.body.includes(s));
      ok = statusOk && hasMarker && forbidden.length === 0;
      detail = 'status=' + res.status
        + (hasMarker ? ' 含必需标志' : ' 缺必需标志 ✗')
        + (forbidden.length ? ' 含禁用标记:' + forbidden.join(',') + ' ✗' : ' 无禁用标记');
    }

    const required = c.required;
    const pass = ok;
    const mark = pass ? 'OK  ' : (required ? 'FAIL' : 'WARN');
    results.push({ ...c, status: res.status, ok: pass, detail });
    console.log('  ' + mark + ' ' + (c.url + '  ' + c.expect + '  ' + detail).padEnd(80) + (c.note ? '  # ' + c.note : ''));
  }

  console.log('');
  const required_failed = results.filter(r => r.required && !r.ok).length;
  const passed = results.filter(r => r.ok).length;
  const total = results.length;
  console.log('==> ' + passed + '/' + total + ' 通过');
  if (required_failed > 0) {
    console.log('    ' + required_failed + ' 个 required 项未通过,需要修复后才能上线');
    process.exit(1);
  }
}

main().catch(e => { console.error(e); process.exit(1); });
