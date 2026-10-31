const state = {
  view: "overview",
  cache: {},
  selectedServiceAreas: new Set(),
  addressLibraryOpen: false,
  titles: {
    overview: ["概览", "平台运行和关键业务指标"],
    orders: ["订单", "派单、改价、状态流转和服务审核"],
    users: ["用户", "客户、师傅账号和推广经理标记"],
    repairers: ["师傅", "师傅资料、接单状态和区域"],
    stores: ["门店", "服务门店、负责人和默认接单师傅"],
    regions: ["区域", "城市/区域层级和负责人"],
    proxy: ["代客订单", "订单认领、代付和协助奖励"],
    domestic: ["家政服务", "月嫂保姆人员、需求和合同"],
    payroll: ["工资", "按单计薪、月薪工资单和发放记录"],
    warranties: ["保修凭证", "维修项目、期限和客户权益"],
    wallet: ["提现", "钱包提现申请和审核"],
    finance: ["财务", "支付订单和分润明细"],
    support: ["客服", "工单列表和回复处理"],
    packages: ["服务包", "年度服务包和计划"],
    ops: ["对账告警", "资金对账、告警处理和系统日志"]
  }
};

const statusText = {
  draft:"未开通", active:"已开通", suspended:"已暂停", closed:"已关闭",
  created: "待派单",
  store_pending: "门店待接",
  store_accepted: "门店已接",
  dispatched: "已派单",
  repairer_accepted: "师傅已接",
  servicing: "服务中",
  bill_submitted: "服务单待确认",
  bill_returned: "服务单退回",
  wait_payment: "待支付",
  paid: "已支付",
  paid_pending_review: "待门店复核",
  store_reviewed: "门店已复核",
  completed: "已完成",
  cancelled: "已取消",
  assigned: "已派单",
  accepted: "已接单",
  pending: "待处理",
  in_progress: "服务中"
};

const statusOptions = [
  "created",
  "store_pending",
  "store_accepted",
  "dispatched",
  "repairer_accepted",
  "servicing",
  "bill_submitted",
  "bill_returned",
  "wait_payment",
  "paid",
  "paid_pending_review",
  "store_reviewed",
  "completed",
  "cancelled"
];

const categoryText = {
  appliance: "家电维修",
  door_window: "门窗维修",
  plumbing: "水管维修",
  electrical: "电路维修",
  furniture_install: "家具安装",
  appliance_install: "家电安装",
  pipe_dredge: "管道疏通",
  carpentry: "木工维修",
  locksmith: "开锁换锁",
  painting: "墙面翻新",
  cleaning: "保洁清洗",
  other: "其他"
};

const roleText = {
  customer: "用户",
  repairer: "师傅",
  admin: "管理员"
};

const els = {
  content: document.querySelector("#content"),
  title: document.querySelector("#view-title"),
  subtitle: document.querySelector("#view-subtitle"),
  apiStatus: document.querySelector("#api-status"),
  toast: document.querySelector("#toast"),
  modal: document.querySelector("#modal"),
  modalTitle: document.querySelector("#modal-title"),
  modalBody: document.querySelector("#modal-body")
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmtDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return escapeHtml(value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function money(value) {
  const num = Number(value || 0);
  return `¥${num.toFixed(2)}`;
}

function badge(value, kind = "") {
  return `<span class="badge ${kind}">${escapeHtml(value)}</span>`;
}

function statusBadge(value) {
  const danger = ["cancelled", "failed", "rejected", "critical"];
  const warn = ["wait_payment", "pending", "paid_pending_review", "bill_submitted", "mismatch"];
  const ok = ["completed", "paid", "settled", "approved", "ok", "resolved"];
  const kind = danger.includes(value) ? "danger" : warn.includes(value) ? "warn" : ok.includes(value) ? "ok" : "";
  return badge(statusText[value] || value || "-", kind);
}

function notify(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.clearTimeout(notify.timer);
  notify.timer = window.setTimeout(() => els.toast.classList.remove("show"), 2600);
}

function setLoading(label = "加载中") {
  els.content.innerHTML = `<div class="section"><div class="empty">${label}...</div></div>`;
}

// ── 2026-10-05:后台登录态 ─────────────────────────────────────────────
// 之前 admin-web 完全不带 Authorization 头,导致 /api/v1/admin/* 与
// /api/v1/wallet/* 全部 401,对账告警、提现审核这些功能点开就报错。
const TOKEN_KEY = "xiulijiu.admin.token";
const ACTOR_KEY = "xiulijiu.admin.actor";
let authToken = "";
let authWarned = false;

function readToken() {
  try {
    return window.localStorage.getItem(TOKEN_KEY) || "";
  } catch (error) {
    return "";
  }
}

function writeToken(token) {
  authToken = token || "";
  try {
    if (authToken) window.localStorage.setItem(TOKEN_KEY, authToken);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch (error) {
    /* localStorage 不可用时退化为内存态 */
  }
  renderAuthActor();
}

function readActor() {
  try {
    const raw = window.localStorage.getItem(ACTOR_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    return null;
  }
}

function writeActor(actor) {
  try {
    if (actor) window.localStorage.setItem(ACTOR_KEY, JSON.stringify(actor));
    else window.localStorage.removeItem(ACTOR_KEY);
  } catch (error) {
    /* ignore */
  }
  renderAuthActor();
}

function renderAuthActor() {
  const node = document.querySelector("#auth-actor");
  const logout = document.querySelector("#logout-btn");
  if (!node) return;
  const actor = readActor();
  if (authToken && actor) {
    node.textContent = `${actor.name || '已登录'} · ${({platform_admin:'平台管理员',store_manager:'店长',city_manager:'城市经理',repairer:'师傅',second_receiver:'二接师傅',customer:'客户',promotion_manager:'推广经理',finance:'财务',tech_support:'客服'})[actor.business_role] || actor.business_role || '-'}`;
    node.classList.remove("muted");
    if (logout) logout.hidden = false;
  } else if (authToken) {
    node.textContent = "已登录(未校验)";
    node.classList.remove("muted");
    if (logout) logout.hidden = false;
  } else {
    node.textContent = "未登录";
    node.classList.add("muted");
    if (logout) logout.hidden = true;
  }
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  return headers;
}

function handleUnauthorized() {
  writeToken("");
  writeActor(null);
  if (!authWarned) {
    authWarned = true;
    notify("登录已失效,请重新登录");
  }
  renderAuthGate();
}

async function verifyToken(token) {
  const response = await fetch("/api/v1/auth/me", {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!response.ok) throw new Error(`Token 无效或已过期(${response.status})`);
  return response.json();
}

function renderAuthGate(message = "") {
  const logout = document.querySelector("#logout-btn");
  if (logout) logout.hidden = true;
  els.content.innerHTML = `
    <section class="section auth-gate">
      <div class="section-head">
        <div class="section-title">
          <h2>后台登录</h2>
          <span>用平台管理员账号密码登录</span>
        </div>
      </div>
      <div class="notice ${message ? "notice-warn" : ""}">${escapeHtml(
        message || "请输入管理后台账号和密码"
      )}</div>
      <form class="form-grid" data-form="auth-login" autocomplete="on">
        <div class="field">
          <label for="auth-account">账号</label>
          <input id="auth-account" name="account" type="text" autocomplete="username" placeholder="管理后台账号">
        </div>
        <div class="field">
          <label for="auth-password">密码</label>
          <input id="auth-password" name="password" type="password" autocomplete="current-password" placeholder="密码">
        </div>
        <button class="btn primary" type="submit">登录</button>
      </form>
      <details style="margin-top:14px">
        <summary class="muted" style="cursor:pointer">改用 Token 登录(应急)</summary>
        <form class="form-grid" data-form="auth-token" style="margin-top:10px">
          <div class="field wide">
            <label for="auth-token">平台管理员 Token</label>
            <textarea id="auth-token" name="token" rows="3" placeholder="粘贴 Bearer token(不含 Bearer 前缀)"></textarea>
          </div>
          <button class="btn" type="submit">用 Token 登录</button>
        </form>
      </details>
    </section>
  `;
}

async function completeLogin(token, me) {
  writeToken(token);
  writeActor({ id: me.id, name: me.name, business_role: me.business_role });
  authWarned = false;
  if (me.business_role !== "platform_admin") {
    notify(`当前角色 ${me.business_role} 非平台管理员,管理接口会返回 403`);
  } else {
    notify("登录成功");
  }
  await loadView("overview");
}

async function submitAuthTokenLogin(formEl) {
  const formData = new FormData(formEl);
  const token = String(formData.get("token") || "").trim().replace(/^Bearer\s+/i, "");
  if (!token) {
    renderAuthGate("请先填写 token");
    return;
  }
  authToken = token;
  try {
    const me = await verifyToken(token);
    await completeLogin(token, me);
  } catch (error) {
    authToken = "";
    renderAuthGate(error.message || "登录失败");
  }
}

async function submitAuthLogin(formEl) {
  const formData = new FormData(formEl);
  const account = String(formData.get("account") || "").trim();
  const password = String(formData.get("password") || "");
  if (!account || !password) {
    renderAuthGate("请输入账号和密码");
    return;
  }
  authToken = "";
  try {
    const response = await fetch("/api/v1/auth/admin-login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account, password })
    });
    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (error) {
        data = null;
      }
    }
    if (!response.ok) {
      const detail = data && (data.detail || data.error);
      if (response.status === 503) {
        throw new Error("后台登录未配置(服务器 .env 缺 ADMIN_WEB_ACCOUNT / ADMIN_WEB_PASSWORD)");
      }
      throw new Error(typeof detail === "string" ? detail : "账号或密码不正确");
    }
    if (!data || !data.token) {
      throw new Error("登录响应异常");
    }
    await completeLogin(data.token, data.user);
  } catch (error) {
    authToken = "";
    renderAuthGate(error.message || "登录失败");
  }
}

function logout() {
  writeToken("");
  writeActor(null);
  authWarned = false;
  renderAuthGate("已退出登录");
}

async function api(path, options = {}) {
  const init = {
    method: options.method || "GET",
    headers: authHeaders({ "Content-Type": "application/json" })
  };
  if (options.body !== undefined) {
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (error) {
      data = text;
    }
  }
  if (!response.ok) {
    if (response.status === 401) {
      handleUnauthorized();
      throw new Error("登录已失效,请重新登录");
    }
    const detail = data && (data.detail || data.error);
    throw new Error(
      typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `请求失败 ${response.status}`
    );
  }
  return data;
}

function query(path, params) {
  const url = new URL(path, window.location.origin);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  });
  return `${url.pathname}${url.search}`;
}

function table(columns, rows, emptyText = "暂无数据") {
  if (!rows || rows.length === 0) {
    return `<div class="empty">${emptyText}</div>`;
  }
  const head = columns.map((col) => `<th>${escapeHtml(col.label)}</th>`).join("");
  const body = rows.map((row) => {
    const cells = columns.map((col) => {
      const html = typeof col.render === "function" ? col.render(row) : escapeHtml(row[col.key]);
      return `<td class="${col.wrap ? "wrap" : ""}">${html}</td>`;
    }).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function section(title, subtitle, body, toolbar = "") {
  return `
    <section class="section">
      <div class="section-head">
        <div class="section-title">
          <h2>${escapeHtml(title)}</h2>
          ${subtitle ? `<span>${escapeHtml(subtitle)}</span>` : ""}
        </div>
        ${toolbar ? `<div class="toolbar">${toolbar}</div>` : ""}
      </div>
      ${body}
    </section>
  `;
}

function choiceField(name, label, options, hint, required = false) {
  return {name, label, type: 'search', options, hint, placeholder: '输入名称或手机号搜索后选择', required};
}
function userChoices(users, roles) {
  return users.filter(u => u.is_active && (u.business_roles || [u.business_role]).some(r => roles.includes(r))).map(u => ({value:u.id,label:`${u.name} · ${u.phone}`}));
}
function regionChoices(regions, all = regions) {
  return regions.map(r => ({value:r.id,label:`${all.find(p => p.id === r.parent_id)?.name ? all.find(p => p.id === r.parent_id).name + ' / ' : ''}${r.name}`}));
}
async function allUsers() {
  const rows = [];
  for (let skip = 0; ; skip += 100) {
    const page = await api(`/api/v1/users?limit=100&skip=${skip}`);
    rows.push(...page); if (page.length < 100) return rows;
  }
}
let regionFormData = {regions:[], filters:{districts:[]}};
function updateRegionChoices(resetName = true) {
  const f = document.querySelector('[data-form="create-region"]'); if (!f) return;
  const level = Number(f.elements.level.value);
  const parent = f.elements.parent_id;
  const candidates = regionFormData.regions.filter(r => r.level === level - 1);
  parent.disabled = level === 1; parent.required = level > 1;
  document.getElementById(parent.getAttribute('list')).innerHTML = regionChoices(candidates, regionFormData.regions).map(o => `<option value="${escapeHtml(o.label)}" data-value="${o.value}"></option>`).join('');
  if (!candidates.some(r => regionChoices([r])[0].label === parent.value) && !Array.from(document.getElementById(parent.getAttribute('list')).options).some(o => o.value === parent.value)) parent.value = '';
  const chosen = Array.from(document.getElementById(parent.getAttribute('list')).options).find(o => o.value === parent.value);
  const parentRegion = regionFormData.regions.find(r => r.id === Number(chosen?.dataset.value));
  const geo = regionFormData.filters;
  let names = level === 1 ? [geo.city || '厦门市'] : [];
  if (level === 2 && parentRegion?.name === geo.city) names = geo.districts.map(d => d.name);
  document.getElementById('create-region-name-list').innerHTML = names.map(name => `<option value="${escapeHtml(name)}"></option>`).join('');
  if (resetName) f.elements.name.value = '';
  f.elements.name.placeholder = level === 1 ? '例如：厦门市' : '例如：海沧区，先选择上级城市';
}
document.addEventListener('change', e => {
  if (e.target.closest('[data-form="create-region"]') && ['level','parent_id'].includes(e.target.name)) updateRegionChoices();
});
document.addEventListener('input', e => {
  if (e.target.matches('[data-choice]')) e.target.setCustomValidity('');
  if (e.target.closest('[data-form="create-region"]') && e.target.name === 'parent_id') updateRegionChoices();
});
function form(fields, action, submitText = "保存") {
  const controls = fields.map((field) => {
    const id = `${action}-${field.name}`;
    const hint = `<small class="field-hint" id="${id}-hint">${escapeHtml(field.hint || field.placeholder || '请填写' + field.label)}</small>`;
    if (field.type === 'search') {
      return `<div class="field"><label for="${id}">${escapeHtml(field.label)}</label><input id="${id}" name="${field.name}" list="${id}-list" data-choice autocomplete="off" placeholder="${escapeHtml(field.placeholder)}" aria-describedby="${id}-hint" ${field.required ? 'required' : ''}><datalist id="${id}-list">${field.options.map(o => `<option value="${escapeHtml(o.label)}" data-value="${o.value}"></option>`).join('')}</datalist>${hint}</div>`;
    }
    if (field.type === "select") {
      const opts = (field.options || []).map((option) => {
        const value = typeof option === "string" ? option : option.value;
        const label = typeof option === "string" ? option : option.label;
        return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
      }).join("");
      return `<div class="field"><label for="${id}">${escapeHtml(field.label)}</label><select id="${id}" name="${field.name}">${opts}</select>${hint}</div>`;
    }
    if (field.type === "textarea") {
      return `<div class="field wide"><label for="${id}">${escapeHtml(field.label)}</label><textarea id="${id}" name="${field.name}" placeholder="${escapeHtml(field.placeholder || "")}"></textarea></div>`;
    }
    return `<div class="field"><label for="${id}">${escapeHtml(field.label)}</label><input id="${id}" name="${field.name}" type="${field.type || "text"}" placeholder="${escapeHtml(field.placeholder || "")}" ${field.required ? "required" : ""} ${field.suggestions ? `list="${id}-list"` : ""} aria-describedby="${id}-hint">${field.suggestions ? `<datalist id="${id}-list">${field.suggestions.map(v => `<option value="${escapeHtml(v)}"></option>`).join("")}</datalist>` : ""}${hint}</div>`;
  }).join("");
  return `<form class="form-grid" data-form="${action}">${controls}<button class="btn primary" type="submit">${escapeHtml(submitText)}</button></form>`;
}

function actionButton(label, action, attrs = {}, kind = "") {
  const data = Object.entries(attrs)
    .map(([key, value]) => `data-${key}="${escapeHtml(value)}"`)
    .join(" ");
  return `<button class="btn compact ${kind}" data-action="${escapeHtml(action)}" ${data}>${escapeHtml(label)}</button>`;
}

async function checkApi() {
  try {
    await api("/health");
    els.apiStatus.textContent = "API 正常";
    els.apiStatus.className = "status-dot ok";
  } catch {
    els.apiStatus.textContent = "API 异常";
    els.apiStatus.className = "status-dot bad";
  }
}

async function loadOverview() {
  const [metrics, orders, users, repairers, withdrawals, alerts, stores, regions] = await Promise.all([
    // 2026-10-07:改走 Bearer token 的管理端点。
    // 原来调 "/metrics",那个路径有 nginx basic auth,浏览器会弹原生账号密码框。
    api("/api/v1/admin/metrics").catch(() => ({})),
    api("/api/v1/orders?limit=100").catch(() => []),
    api("/api/v1/users").catch(() => []),
    api("/api/v1/repairers").catch(() => []),
    api("/api/v1/wallet/withdrawals?limit=100").catch(() => []),
    api("/api/v1/admin/alerts?resolved=false").catch(() => []),
    api("/api/v1/stores").catch(() => []),
    api("/api/v1/regions").catch(() => [])
  ]);
  const pendingWithdrawals = withdrawals.filter((item) => item.status === "pending").length;
  const activeOrders = orders.filter((item) => !["completed", "cancelled"].includes(item.status)).length;
  const cards = [
    ["订单总数", metrics.orders_total ?? orders.length],
    ["进行中订单", activeOrders],
    ["用户数", users.length],
    ["师傅数", repairers.length],
    ["钱包数", metrics.wallets_total ?? "-"],
    ["总余额", money(metrics.total_balance || 0)],
    ["待审提现", pendingWithdrawals],
    ["未处理告警", alerts.length]
  ].map(([label, value]) => `
    <div class="metric-card">
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-value">${escapeHtml(value)}</div>
    </div>
  `).join("");

  const recentOrders = table([
    { label: "订单", render: (row) => `#${row.id}` },
    { label: "客户", key: "customer_id" },
    { label: "分类", render: (row) => categoryText[row.category] || row.category },
    { label: "金额", render: (row) => money(row.price) },
    { label: "状态", render: (row) => statusBadge(row.status) },
    { label: "创建时间", render: (row) => fmtDate(row.created_at) }
  ], orders.slice(0, 8), "暂无订单");

  const storeSummary = table([
    { label: "门店", key: "name" },
    { label: "所属区县", render: row => escapeHtml(regionChoices(regions.filter(r => r.id === row.region_id),regions)[0]?.label || "未设置") },
    { label: "负责人", key: "manager_id" },
    { label: "默认师傅", key: "default_second_receiver_id" },
    { label: "状态", render: (row) => statusBadge(row.status) }
  ], stores.slice(0, 6), "暂无门店");

  els.content.innerHTML = `
    <div class="metric-grid">${cards}</div>
    <div class="split">
      ${section("最近订单", "最新创建的订单", recentOrders)}
      ${section("门店概况", "已配置门店", storeSummary)}
    </div>
  `;
}

async function loadOrders() {
  const status = document.querySelector("#order-status-filter")?.value || "";
  const orders = await api(query("/api/v1/orders", { limit: 100, status }));
  const filter = `
    <select id="order-status-filter">
      <option value="">全部状态</option>
      ${statusOptions.map((item) => `<option value="${item}" ${item === status ? "selected" : ""}>${statusText[item] || item}</option>`).join("")}
    </select>
    <button class="btn" data-action="filter-orders">筛选</button>
  `;
  const body = table([
    { label: "ID", render: (row) => `#${row.id}` },
    { label: "客户", key: "customer_id" },
    { label: "师傅", render: (row) => row.repairer_id || row.assigned_repairer_id || "-" },
    { label: "门店", render: (row) => row.store_id || "-" },
    { label: "分类", render: (row) => categoryText[row.category] || row.category },
    { label: "金额", render: (row) => money(row.price) },
    { label: "状态", render: (row) => statusBadge(row.status) },
    { label: "地址", key: "address", wrap: true },
    { label: "创建时间", render: (row) => fmtDate(row.created_at) },
    {
      label: "操作",
      render: (row) => `<div class="actions">
        ${actionButton("改价", "order-price", { id: row.id })}
        ${actionButton("派单", "order-assign", { id: row.id })}
        ${actionButton("自动派", "order-auto", { id: row.id })}
        ${actionButton("改状态", "order-status", { id: row.id })}
        ${actionButton("复核", "order-review", { id: row.id })}
        ${actionButton("日志", "order-logs", { id: row.id })}
      </div>`
    }
  ], orders, "暂无订单");
  els.content.innerHTML = section("订单列表", "最多显示 100 条", body, filter);
}

async function loadUsers() {
  const users = await allUsers();
  const search = document.querySelector('#users-search')?.value?.trim() || '';
  const matchingUsers = users.filter(u => !search || `${u.name} ${u.phone}`.includes(search));
  const body = table([
    { label: "ID", key: "id" },
    { label: "手机号", key: "phone" },
    { label: "姓名", key: "name" },
    { label: "角色", render: (row) => badge(({customer:"客户",repairer:"师傅",second_receiver:"二接师傅",store_manager:"店长",city_manager:"城市经理",promotion_manager:"推广经理",tech_support:"客服",finance:"财务",platform_admin:"平台管理员"})[row.business_role] || row.business_role) },
    { label: "兼任身份", render: row => escapeHtml((row.business_roles || []).filter(r => r !== row.business_role && r !== "customer").map(r => ({store_manager:"店长",repairer:"师傅",promotion_manager:"推广经理"})[r] || r).join("、") || "—") },
    { label: "账号状态", render: (row) => badge(row.is_active ? "已启用" : "已停用", row.is_active ? "ok" : "warn") },
    { label: "推广经理", render: (row) => row.is_promotion_manager ? badge("是", "ok") : "-" },
    { label: "上级推广", render: (row) => row.promotion_manager_id || "-" },
    { label: "创建时间", render: (row) => fmtDate(row.created_at) },
    {
      label: "操作",
      render: (row) => `<div class="actions">
        ${actionButton(row.is_active ? "停用" : "启用", "user-status", { id: row.id, active: row.is_active ? "1" : "0" })}
        ${row.phone.startsWith("1880000") ? "" : actionButton("改名", "user-name", { id: row.id, name: row.name })}
        ${actionButton("业务身份", "user-business-roles", {id:row.id, roles:(row.business_roles || [row.business_role]).join(","), primary:row.business_role, fixed:row.phone.startsWith("1880000") ? "1" : "0"})}
        ${row.phone.startsWith("1880000") ? "" : actionButton("其他管理角色", "user-role", { id: row.id, role: row.business_role })}
      </div>`
    }
  ], matchingUsers, "没有匹配的用户，请确认对方已在小程序注册");
  els.content.innerHTML = section("人员账号与授权", "新成员先在小程序注册，再搜索手机号设置店长、城市经理、师傅或其他管理角色", body, `<input id="users-search" placeholder="搜索姓名或手机号" value="${escapeHtml(search)}"><button class="btn" data-action="search-users">查找人员</button>`);
}

async function loadRepairers() {
  const [repairers, users, regions] = await Promise.all([api("/api/v1/repairers?limit=100"), allUsers(), api("/api/v1/regions")]);
  const createForm = form([
    choiceField('user_id', '师傅账号', userChoices(users.filter(u => !repairers.some(r => r.user_id === u.id)), ['repairer','second_receiver']), '搜索姓名或手机号，选择已注册并获得师傅角色的账号；已有档案的账号不重复显示', true),
    { name: 'skills', label: '技能', placeholder: '例如：水电,家电维修', required:true, hint:'用逗号分隔，例如：水电,家电维修' },
    choiceField('region_id', '服务区域', regionChoices(regions), '先在区域页新增城市和区县，再搜索选择服务区域'),
    { name:'intro', label:'简介', placeholder:'例如：从事水电维修 8 年，可服务海沧区' }
  ], "create-repairer", "新增师傅");
  const body = createForm + table([
    { label: "ID", key: "id" },
    { label: "姓名 / 手机号", render: row => { const u=users.find(u=>u.id===row.user_id); return escapeHtml(u ? `${u.name} / ${u.phone}` : String(row.user_id)); } },
    { label: "技能", key: "skills", wrap: true },
    { label: "区域", render: (row) => row.region_id || "-" },
    { label: "评分", key: "rating" },
    { label: "接单数", key: "order_count" },
    { label: "状态", render: (row) => badge(({online:"在线",offline:"休息",busy:"服务中"})[row.status] || "待确认", row.status==="online"?"ok":"warn") },
    {
      label: "操作",
      render: (row) => `<div class="actions">
        ${actionButton("完善资料", "repairer-profile", { id: row.id })}
        ${actionButton("改状态", "repairer-status", { id: row.id, status: row.status })}
        ${actionButton("改技能", "repairer-skills", { id: row.id, skills: row.skills })}
      </div>`
    }
  ], repairers, "暂无师傅");
  els.content.innerHTML = section("师傅列表", "授权师傅身份后自动入列；完善技能、服务区域后再接单", body);
}


function addressEditor(areas, row = {}) {
  const field = (key, label, placeholder = '') => `<div class="field"><label>${label}</label><input name="${key}" value="${escapeHtml(row[key] || '')}" placeholder="${escapeHtml(placeholder)}" maxlength="${key === 'door_number' ? 240 : 160}"></div>`;
  const districts=[...new Set(areas.map(a=>`${a.city}/${a.district}`))];
  return `<input type="hidden" name="id" value="${row.id || ''}"><div class="field"><label>城市/区县</label><select name="city_region" required><option value="">请选择区县</option>${districts.map(text=>`<option value="${escapeHtml(text)}" ${text===`${row.city}/${row.district}`?'selected':''}>${escapeHtml(text)}</option>`).join('')}</select><small>先在门店分配小区服务范围，再在该区县录入具体门牌。</small></div>` +
    field('estate','小区 / 分期（可粘贴贝壳名称）','未来海岸蓝月湾一期') +
    field('building','楼栋','S5栋') + field('unit','单元（无则留空）','1单元') + field('room','房号','2605') +
    field('door_number','标准门牌写法（可选，默认由楼栋单元房号组成）','嵩屿北五里27号2605室') +
    `<div class="field"><label>同址别名（一行一种写法，不新增实体地址）</label><textarea name="aliases" maxlength="4000" placeholder="厦门市海沧区蓝月湾一期S5栋2605室">${escapeHtml(row.aliases || '')}</textarea></div><div class="field"><label>内部备注（不向游客公开）</label><textarea name="detail_hint" maxlength="300">${escapeHtml(row.detail_hint || '')}</textarea></div>` +
    field('source_name','来源名称','贝壳 / 人工核验') + field('source_ref','来源小区编号或链接（选填）');
}

async function loadStores() {
  const [stores, regions, users, repairers, addresses, addressAreas] = await Promise.all([api("/api/v1/stores"), api("/api/v1/regions"), allUsers(), api("/api/v1/repairers?limit=100"), api("/api/v1/stores/addresses"), api("/api/v1/service-areas/address-catalog")]);
  state.cache.addressAreas = addressAreas;
  state.cache.storeAddresses = addresses;
  state.cache.storeForm = {stores,regions,users,repairers};
  const createForm = form([
    {name:'name', label:'门店名称', required:true, placeholder:'例如：立即修海沧店'},
    choiceField('region_id', '所属区县', regionChoices(regions.filter(r => r.level === 2), regions), '搜索并选择已创建的区域，例如：厦门市 / 海沧区', true),
    choiceField('manager_id', '门店负责人', userChoices(users, ['store_manager']), '搜索店长姓名或手机号，选择负责人', true),
    choiceField('city_manager_id', '城市经理', userChoices(users, ['city_manager']), '选填：搜索城市经理姓名或手机号'),
    choiceField('default_second_receiver_id', '默认接单师傅', repairers.filter(r => users.some(u => u.id === r.user_id && u.is_active)).map(r => ({value:r.id,label:`${users.find(u => u.id === r.user_id)?.name} · ${users.find(u => u.id === r.user_id)?.phone}`})), '选填：先在师傅页创建档案，再选择默认接单师傅'),
    {name:'remark',label:'备注',placeholder:'例如：服务海沧区，营业时间 08:00—20:00'}
  ], "create-store", "新增门店");
  const body = createForm + table([
    { label: "ID", key: "id" },
    { label: "名称", key: "name" },
    { label: "所属区县", render: row => escapeHtml(regionChoices(regions.filter(r => r.id === row.region_id),regions)[0]?.label || "未设置") },
    { label: "负责人", render: row => escapeHtml(users.find(u => u.id === row.manager_id)?.name || "未设置") },
    { label: "城市经理", render: row => escapeHtml(users.find(u => u.id === row.city_manager_id)?.name || "未设置") },
    { label: "默认师傅", render: (row) => row.default_second_receiver_id || "-" },
    { label: "开通状态", render: row => row.enabled && row.status === "active" ? badge("已开通", "ok") : badge("未开通", "warn") },
    {
      label: "操作",
      render: (row) => `<div class="actions">
        ${actionButton(row.enabled && row.status === "active" ? "停用门店" : "启用并开通", "store-enabled", { id: row.id, enabled: row.enabled && row.status === "active" ? "1" : "0" })}
        ${actionButton("修改", "edit-store", {id:row.id})}
        ${actionButton("分配小区服务范围", "store-coverage", {id:row.id})}
        ${actionButton("默认师傅", "store-default-repairer", { id: row.id })}
      </div>`
    }
  ], stores, "暂无门店");
  els.content.innerHTML = section("创建与开通门店", "1. 选择区域和店长 → 2. 新增门店 → 3. 启用并开通 → 4. 分配服务范围", body);
  els.content.innerHTML += section('门店地址库', '小区 / 楼栋 / 单元 / 房号；同址别名共用一个地址。删除后不影响历史订单' ,
    `<form class="form-grid" data-form="create-store-address">${addressEditor(addressAreas)}<button class="btn primary" type="submit">新增地址</button></form>` +
    table([{label:'城市/区域',render: row => escapeHtml(`${row.city}/${row.district}`)},
      {label:'小区',key:'estate'}, {label:'门牌号',render: row => escapeHtml(row.door_number || [row.building,row.unit,row.room].filter(Boolean).join(''))},
      {label:'楼栋 / 单元 / 房号',render:row => escapeHtml([row.building,row.unit,row.room].filter(Boolean).join(' / '))},
      {label:'同址别名 / 备注',render:row => escapeHtml([row.aliases,row.detail_hint].filter(Boolean).join('；'))},
      {label:'接单门店',render: row => escapeHtml(stores.find(store => store.id === row.store_id)?.name || '')},
      {label:'操作',render:row => actionButton('修改','edit-store-address',{id:row.id}) + actionButton('删除','delete-store-address',{id:row.id})}], addresses.filter(row => row.enabled), '暂无地址'));


}

async function loadRegions() {
  const currentDistrict = document.querySelector("#service-area-district")?.value || "";
  const currentStreet = document.querySelector("#service-area-street")?.value || "";
  const currentStatus = document.querySelector("#service-area-status")?.value || "";
  const currentQuery = document.querySelector("#service-area-query")?.value?.trim() || "";
  const [regions, filters, stores, users] = await Promise.all([
    api("/api/v1/regions"),
    api("/api/v1/service-areas/filters"),
    api("/api/v1/stores"),
    allUsers(),
  ]);
  const areaData = await api(query("/api/v1/service-areas", {
    district: currentDistrict,
    street: currentStreet,
    assignment_status: currentStatus,
    q: currentQuery,
    limit: 1000,
  }));
  const logs = await api("/api/v1/service-areas/assignment-logs?limit=30");
  regionFormData = {regions, filters};
  const createForm = form([
    {name:'level',label:'区域层级',type:'select',options:[{value:'1',label:'一级：城市'},{value:'2',label:'二级：区县'}],hint:'先新增厦门市，再新增其下属区县'},
    choiceField('parent_id','上级区域',[], '二级区县选择上级城市；一级城市无需上级'),
    {name:'name',label:'区域名称',required:true,placeholder:'例如：厦门市',suggestions:[filters.city || '厦门市'],hint:'输入关键词搜索，例如厦门；选中上级后，下一级会显示匹配的区县，也可填写其他实际区域'},
    choiceField('manager_id','区域负责人',userChoices(users,['city_manager','store_manager','platform_admin']), '选填：搜索负责人姓名或手机号')
  ], 'create-region', '新增区域');
  const regionBody = createForm + table([
    { label: "ID", key: "id" },
    { label: "名称", key: "name" },
    { label: "层级", key: "level" },
    { label: "上级", render: (row) => row.parent_id || "-" },
    { label: "负责人", render: (row) => row.manager_id || "-" },
    { label: "创建时间", render: (row) => fmtDate(row.created_at) },
    {
      label: "操作",
      render: (row) => `<div class="actions">
        ${actionButton("改名", "region-name", { id: row.id, name: row.name })}
        ${actionButton("负责人", "region-manager", { id: row.id })}
      </div>`
    }
  ], regions, "暂无区域");

  const districts = filters.districts || [];
  const selectedDistrict = districts.find((item) => item.name === currentDistrict);
  const districtOptions = districts.map((item) =>
    `<option value="${escapeHtml(item.name)}" ${item.name === currentDistrict ? "selected" : ""}>${escapeHtml(item.name)}（${item.count}）</option>`
  ).join("");
  const streetOptions = (selectedDistrict?.streets || []).map((item) =>
    `<option value="${escapeHtml(item.name)}" ${item.name === currentStreet ? "selected" : ""}>${escapeHtml(item.name)}（${item.count}）</option>`
  ).join("");
  const activeStores = stores.filter((item) => item.enabled && item.status === "active");
  const storeOptions = stores.map(item => `<option value="${item.id}" ${item.enabled && item.status === 'active' ? '' : 'disabled'}>${escapeHtml(item.name)}${item.enabled && item.status === 'active' ? '' : '（未开通，请到门店页开通）'}</option>`).join('');
  const statusLabel = { assigned: "已分配", unassigned: "未分配", conflict: "需处理" };
  const selectedCount = state.selectedServiceAreas.size;

  const filterToolbar = `
    <select id="service-area-district" aria-label="行政区"><option value="">全部行政区</option>${districtOptions}</select>
    <select id="service-area-street" aria-label="街道或镇"><option value="">全部街道/镇</option>${streetOptions}</select>
    <select id="service-area-status" aria-label="分配状态">
      <option value="">全部状态</option>
      <option value="unassigned" ${currentStatus === "unassigned" ? "selected" : ""}>未分配</option>
      <option value="assigned" ${currentStatus === "assigned" ? "selected" : ""}>已分配</option>
      <option value="conflict" ${currentStatus === "conflict" ? "selected" : ""}>需处理</option>
    </select>
    <input id="service-area-query" value="${escapeHtml(currentQuery)}" placeholder="搜索社区、村、街道或编码">
    <button class="btn primary" data-action="service-area-filter">查询</button>
    <button class="btn" data-action="service-area-sync">同步厦门地址库</button>
  `;
  const assignmentToolbar = `
    <label class="check-control"><input id="service-area-select-all" type="checkbox"> 全选当前结果</label>
    <span class="selection-count">已选择 <strong>${selectedCount}</strong> 条</span>
    <select id="service-area-primary-store" aria-label="主服务门店"><option value="">选择主服务门店</option>${storeOptions}</select>
    <select id="service-area-backup-store" aria-label="备用服务门店"><option value="">选择备用门店</option>${storeOptions}</select>
    <select id="service-area-conflict-mode" aria-label="冲突处理">
      <option value="skip">跳过已有分配</option>
      <option value="fill_empty">只补充空缺项</option>
      <option value="replace">覆盖原分配</option>
    </select>
    <input id="service-area-remark" placeholder="分配备注">
    <button class="btn primary" data-action="service-area-assign">确认分配所选地址</button>
    <button class="btn danger" data-action="service-area-clear">清除分配</button>
    <button class="btn" data-action="service-area-clear-selection">取消选择</button>
  `;
  const summary = `
    <div class="area-summary">
      <span>查询结果 <strong>${areaData.total}</strong></span>
      <span>已分配 <strong>${areaData.assigned_count}</strong></span>
      <span>未分配 <strong>${areaData.unassigned_count}</strong></span>
      <span class="${areaData.conflict_count ? "text-danger" : ""}">需处理 <strong>${areaData.conflict_count}</strong></span>
      <span>数据源：${escapeHtml(areaData.source_name)}，发布于 ${escapeHtml(areaData.source_published_at)}</span>
    </div>`;
  const areaTable = table([
    {
      label: "选择",
      render: (row) => `<input class="area-checkbox" type="checkbox" data-service-area-id="${row.id}" ${state.selectedServiceAreas.has(row.id) ? "checked" : ""} aria-label="选择${escapeHtml(row.name)}">`,
    },
    { label: "行政区", key: "district" },
    { label: "街道/镇", key: "street" },
    { label: "社区/村", render: (row) => `${escapeHtml(row.name)} ${badge(row.area_type === "community" ? "社区" : "村", "")}` },
    { label: "主服务门店", render: (row) => row.primary_store_name ? escapeHtml(row.primary_store_name) : "-" },
    { label: "备用门店", render: (row) => row.backup_store_name ? escapeHtml(row.backup_store_name) : "-" },
    { label: "负责人", render: (row) => row.manager_name ? escapeHtml(row.manager_name) : "-" },
    { label: "状态", render: (row) => badge(statusLabel[row.assignment_status] || row.assignment_status, row.assignment_status === "assigned" ? "ok" : row.assignment_status === "conflict" ? "danger" : "warn") },
    { label: "生效时间", render: (row) => fmtDate(row.effective_from) },
    { label: "备注", render: (row) => escapeHtml(row.remark || "-"), wrap: true },
  ], areaData.items, "没有符合条件的厦门地址");
  const logTable = table([
    { label: "时间", render: (row) => fmtDate(row.created_at) },
    { label: "地址", key: "area_name", wrap: true },
    { label: "动作", render: (row) => badge(row.action) },
    { label: "操作人", render: (row) => row.operator_user_id || "-" },
    { label: "修改前", render: (row) => escapeHtml(row.before_json || "-"), wrap: true },
    { label: "修改后", render: (row) => escapeHtml(row.after_json || "-"), wrap: true },
  ], logs, "暂无分配记录");

  els.content.innerHTML = `
    ${section("区域列表", "现有城市、区域和负责人", regionBody)}
    <section class="section address-library"><div class="section-head"><h2>厦门地址库</h2><button class="btn" data-action="toggle-address-library" aria-expanded="${state.addressLibraryOpen}">${state.addressLibraryOpen ? '收起' : '展开'}</button></div>
    <div id="address-library-body" ${state.addressLibraryOpen ? '' : 'hidden'}>
      <div class="workflow-note"><strong>分配服务范围</strong><p>第一步：选择行政区和街道，查询需要服务的社区。第二步：勾选社区，选择已开通的主服务门店。第三步：确认分配，客户即可选择社区并填写小区、楼栋、单元和房号下单。负责人跟随门店，操作人记录当前登录账号。</p>${activeStores.length ? '' : '<p class="text-danger">当前没有已开通门店。请到门店页点击“启用并开通”，再分配服务范围。</p>'}<button class="btn" data-action="guide-view" data-target="stores">去门店管理</button></div>
      <div class="toolbar area-filters">${filterToolbar}</div>${summary}<div class="assignment-bar">${assignmentToolbar}</div>${areaTable}
      <details class="audit-fold"><summary>查看分配记录</summary>${logTable}</details>
    </div></section>
  `;
  updateRegionChoices(false);
}

async function loadWallet() {
  const withdrawals = await api("/api/v1/wallet/withdrawals?limit=100");
  const body = table([
    { label: "ID", key: "id" },
    { label: "用户", key: "user_id" },
    { label: "钱包", key: "wallet_id" },
    { label: "金额", render: (row) => money(row.amount) },
    { label: "状态", render: (row) => statusBadge(row.status) },
    { label: "备注", key: "remark", wrap: true },
    { label: "申请时间", render: (row) => fmtDate(row.created_at) },
    { label: "审核时间", render: (row) => fmtDate(row.reviewed_at) },
    {
      label: "操作",
      render: (row) => row.status === "pending" ? `<div class="actions">
        ${actionButton("通过", "withdraw-approve", { id: row.id }, "primary")}
        ${actionButton("拒绝", "withdraw-reject", { id: row.id }, "danger")}
      </div>` : "-"
    }
  ], withdrawals, "暂无提现申请");
  els.content.innerHTML = section("提现申请", "管理员审核提现", body);
}

async function loadFinance() {
  const [payments, wechatStatus] = await Promise.all([
    api("/api/v1/payment/list?limit=100").catch(() => []),
    api("/api/v1/payment/wechat/config-status").catch((error) => ({
      ready: false,
      issues: [error.message || "微信支付配置状态读取失败"]
    }))
  ]);
  const wechatStatusBody = `
    <div class="form-grid">
      <div class="field"><label>状态</label>${wechatStatus.ready ? badge("已就绪", "ok") : badge("未就绪", "warn")}</div>
      <div class="field"><label>AppID</label><span>${escapeHtml(wechatStatus.appid || "-")}</span></div>
      <div class="field"><label>商户号</label><span>${escapeHtml(wechatStatus.mch_id || "-")}</span></div>
      <div class="field"><label>证书序列号</label><span>${escapeHtml(wechatStatus.merchant_serial_no || "-")}</span></div>
      <div class="field wide"><label>回调地址</label><span>${escapeHtml(wechatStatus.notify_url || "-")}</span></div>
      <div class="field"><label>APIv3密钥</label>${wechatStatus.api_v3_key_configured ? badge("已配置", "ok") : badge("未配置", "danger")}</div>
      <div class="field"><label>AppSecret</label>${wechatStatus.app_secret_configured ? badge("已配置", "ok") : badge("未配置", "danger")}</div>
      <div class="field"><label>商户证书</label>${wechatStatus.cert_exists ? badge("已找到", "ok") : badge("缺失", "danger")}</div>
      <div class="field"><label>商户私钥</label>${wechatStatus.key_exists ? badge("已找到", "ok") : badge("缺失", "danger")}</div>
    </div>
    ${(wechatStatus.issues || []).length ? `<div class="empty">${wechatStatus.issues.map(escapeHtml).join("<br>")}</div>` : ""}
  `;
  const body = `
    <div class="form-grid">
      <div class="field"><label for="profit-order-id">订单ID</label><input id="profit-order-id" type="number"></div>
      <button class="btn" data-action="profit-order">查订单分润</button>
      <div class="field"><label for="profit-user-id">用户ID</label><input id="profit-user-id" type="number"></div>
      <button class="btn" data-action="profit-user">查用户分润</button>
    </div>
    ${table([
      { label: "支付单", render: (row) => `#${row.id}` },
      { label: "订单", key: "order_id" },
      { label: "用户", key: "user_id" },
      { label: "金额", render: (row) => money(row.amount) },
      { label: "状态", render: (row) => statusBadge(row.status) },
      { label: "渠道", key: "provider" },
      { label: "商户单号", render: (row) => row.out_trade_no || "-" },
      { label: "预支付单", render: (row) => row.prepay_id || "-" },
      { label: "交易号", render: (row) => row.transaction_id || "-" },
      { label: "付款时间", render: (row) => fmtDate(row.paid_at) },
      { label: "创建时间", render: (row) => fmtDate(row.created_at) },
      {
        label: "操作",
        render: (row) => row.provider === "wechat" && row.status === "pending"
          ? actionButton("同步微信", "payment-sync", { id: row.id }, "primary")
          : "-"
      }
    ], payments, "暂无支付记录")}
  `;
  els.content.innerHTML = `
    ${section("微信支付配置", "仅显示非敏感诊断信息", wechatStatusBody)}
    ${section("支付与分润", "支付订单列表和分润查询", body)}
  `;
}

async function loadSupport() {
  const tickets = await api("/api/v1/support/tickets").catch(() => []);
  const body = table([
    { label: "ID", key: "id" },
    { label: "门店", key: "store_id" },
    { label: "用户", key: "user_id" },
    { label: "订单", render: (row) => row.order_id || "-" },
    { label: "分类", key: "category" },
    { label: "标题", key: "title", wrap: true },
    { label: "状态", render: (row) => statusBadge(row.status) },
    { label: "更新时间", render: (row) => fmtDate(row.updated_at) },
    {
      label: "操作",
      render: (row) => `<div class="actions">
        ${actionButton("回复", "ticket-reply", { id: row.id })}
        ${actionButton("查看", "ticket-view", { id: row.id })}
      </div>`
    }
  ], tickets, "暂无客服工单");
  els.content.innerHTML = section("客服工单", "用户和门店工单处理", body);
}

async function loadPackages() {
  const packages = await api("/api/v1/service-packages");
  const createForm = form([
    { name: "name", label: "名称" },
    { name: "category", label: "分类", placeholder: "appliance" },
    { name: "service_years", label: "年限", type: "number" },
    { name: "annual_times", label: "每年次数", type: "number" },
    { name: "device_count", label: "设备数", type: "number" },
    { name: "service_month", label: "服务月份", type: "number" },
    { name: "price", label: "价格", type: "number" },
    { name: "description", label: "说明" }
  ], "create-package", "新增服务包");
  const body = createForm + table([
    { label: "ID", key: "id" },
    { label: "名称", key: "name" },
    { label: "分类", key: "category" },
    { label: "年限", key: "service_years" },
    { label: "次数", key: "annual_times" },
    { label: "设备", key: "device_count" },
    { label: "月份", key: "service_month" },
    { label: "价格", render: (row) => money(row.price) },
    { label: "状态", render: (row) => statusBadge(row.status) },
    { label: "启用", render: (row) => row.enabled ? badge("启用", "ok") : badge("停用", "warn") }
  ], packages, "暂无服务包");
  els.content.innerHTML = section("服务包", "年度服务包配置", body);
}

async function loadProxy() {
  const orders = await api("/api/v1/orders?is_proxy_order=true&limit=100").catch(() => []);
  const body = table([
    { label: "订单", key: "id" },
    { label: "录单人", render: (row) => row.proxy_creator_id || "-" },
    { label: "客户电话", render: (row) => row.customer_phone_snapshot || row.contact_phone || "-" },
    { label: "状态", render: (row) => statusBadge(row.status) },
    { label: "认领", render: (row) => statusBadge(row.claim_status) },
    { label: "付款人", render: (row) => row.latest_payer_user_id || "-" },
    { label: "金额", render: (row) => money(row.price) },
    { label: "风险", render: (row) => row.risk_review_required ? badge("复核", "warn") : badge("正常", "ok") },
    { label: "二维码", render: (row) => actionButton(row.status === "wait_payment" ? "付款码" : "认领码", "proxy-code", { id: row.id, purpose: row.status === "wait_payment" ? "payment" : "claim" }, "primary") },
  ], orders, "暂无代客订单");
  els.content.innerHTML = section("代客订单", "认领、代付、佣金和风险记录", body);
}

async function loadDomestic() {
  const [workers, demands, contracts, stores] = await Promise.all([
    api("/api/v1/business/domestic/workers?active=true").catch(() => []),
    api("/api/v1/business/domestic/demands").catch(() => []),
    api("/api/v1/business/domestic/contracts").catch(() => []),
    api("/api/v1/stores").catch(() => []),
  ]);
  const workerForm = form([
    { name: "service_type", label: "类型", type: "select", options: [{ value: "maternity", label: "月嫂" }, { value: "nanny", label: "保姆" }] },
    { name: "name", label: "姓名" },
    { name: "store_id", label: "门店", type: "select", options: [{ value: "", label: "平台" }, ...stores.map((s) => ({ value: s.id, label: s.name }))] },
    { name: "years_experience", label: "从业年限", type: "number" },
    { name: "price_min", label: "最低价格", type: "number" },
    { name: "price_max", label: "最高价格", type: "number" },
    { name: "skills", label: "技能（逗号分隔）" },
    { name: "intro", label: "档期与介绍", type: "textarea" },
  ], "create-domestic-worker", "新增人员");
  const workerTable = table([
    { label: "ID", key: "id" }, { label: "姓名", key: "name" },
    { label: "类型", render: (row) => row.service_type === "maternity" ? "月嫂" : "保姆" },
    { label: "门店", render: (row) => row.store_id || "平台" },
    { label: "经验", render: (row) => `${row.years_experience}年` },
    { label: "价格", render: (row) => `${money(row.price_min)}-${money(row.price_max)}` },
    { label: "核验", render: (row) => row.id_verified && row.health_verified && row.training_verified ? badge("完整", "ok") : badge("待完善", "warn") },
  ], workers, "暂无人员档案");
  const demandTable = table([
    { label: "需求", key: "id" }, { label: "类型", key: "service_type" }, { label: "客户", key: "contact_name" },
    { label: "电话", key: "contact_phone" }, { label: "开始", key: "service_start" },
    { label: "预算", render: (row) => `${money(row.budget_min)}-${money(row.budget_max)}` }, { label: "状态", render: (row) => statusBadge(row.status) },
  ], demands, "暂无家政需求");
  const contractTable = table([
    { label: "合同", key: "id" }, { label: "需求", key: "demand_id" }, { label: "人员", key: "worker_id" },
    { label: "服务费", render: (row) => money(row.service_fee) }, { label: "代收", render: (row) => money(row.pass_through_amount) },
    { label: "付款方案", key: "payment_plan" }, { label: "状态", render: (row) => statusBadge(row.status) },
  ], contracts, "暂无服务合同");
  els.content.innerHTML = `${section("新增服务人员", "资料建立后需继续完成核验", workerForm)}${section("人员档案", "月嫂和保姆", workerTable)}${section("需求匹配", "客户需求和候选流程", demandTable)}${section("服务合同", "分期付款和服务状态", contractTable)}`;
}

async function loadPayroll() {
  const [wages, payroll] = await Promise.all([
    api("/api/v1/business/wages").catch(() => []),
    api("/api/v1/business/payroll").catch(() => ({ periods: [], items: [] })),
  ]);
  const wageTable = table([
    { label: "订单", key: "order_id" }, { label: "门店", key: "store_id" }, { label: "员工", key: "employee_user_id" },
    { label: "方式", render: (row) => row.wage_mode === "monthly" ? "月薪" : "按单" },
    { label: "金额", render: (row) => money(row.amount) }, { label: "工作量", key: "work_units" }, { label: "状态", render: (row) => statusBadge(row.status) },
  ], wages, "暂无计薪记录");
  const payrollTable = table([
    { label: "周期", key: "period_id" }, { label: "门店", key: "store_id" }, { label: "员工", key: "user_id" },
    { label: "金额", render: (row) => money(row.amount) }, { label: "状态", render: (row) => statusBadge(row.status) }, { label: "备注", key: "remark", wrap: true },
  ], payroll.items, "暂无月度工资单");
  els.content.innerHTML = `${section("订单计薪", "按单工资从门店85%收入中拆分", wageTable)}${section("月度工资单", "月薪人员工作量和发放记录", payrollTable)}`;
}

async function loadWarranties() {
  const items = await api("/api/v1/business/warranties").catch(() => []);
  const body = table([
    { label: "凭证号", key: "certificate_no" }, { label: "订单", key: "order_id" }, { label: "客户", key: "customer_id" },
    { label: "门店", render: (row) => row.store_id || "-" }, { label: "师傅", render: (row) => row.repairer_id || "-" },
    { label: "金额", render: (row) => money(row.amount) }, { label: "保修", render: (row) => `${row.warranty_days}天` },
    { label: "开始", render: (row) => fmtDate(row.starts_at) }, { label: "到期", render: (row) => fmtDate(row.expires_at) },
  ], items, "暂无保修凭证");
  els.content.innerHTML = section("保修凭证", "客户权益、项目和有效期", body);
}

async function loadOps() {
  const [alerts, logs] = await Promise.all([
    api("/api/v1/admin/alerts?limit=100").catch(() => []),
    api("/api/v1/admin/reconcile/logs?limit=100").catch(() => [])
  ]);
  const alertsBody = table([
    { label: "ID", key: "id" },
    { label: "类型", key: "type" },
    { label: "级别", render: (row) => statusBadge(row.severity) },
    { label: "用户", render: (row) => row.user_id || "-" },
    { label: "订单", render: (row) => row.order_id || "-" },
    { label: "金额", render: (row) => row.amount == null ? "-" : money(row.amount) },
    { label: "信息", key: "message", wrap: true },
    { label: "状态", render: (row) => row.resolved ? badge("已处理", "ok") : badge("未处理", "warn") },
    {
      label: "操作",
      render: (row) => row.resolved ? "-" : actionButton("处理", "alert-resolve", { id: row.id }, "primary")
    }
  ], alerts, "暂无告警");
  const logsBody = table([
    { label: "ID", key: "id" },
    { label: "钱包", key: "wallet_id" },
    { label: "用户", key: "user_id" },
    { label: "预期", render: (row) => money(row.expected_balance) },
    { label: "实际", render: (row) => money(row.actual_balance) },
    { label: "差异", render: (row) => money(row.difference) },
    { label: "状态", render: (row) => statusBadge(row.status) },
    { label: "时间", render: (row) => fmtDate(row.created_at) }
  ], logs, "暂无对账记录");
  els.content.innerHTML = `
    ${section("告警", "资金和系统告警", alertsBody, actionButton("运行对账", "reconcile-run", {}, "primary"))}
    ${section("对账记录", "最近 100 条", logsBody)}
  `;
}

async function loadView(view = state.view) {
  state.view = view;
  const [title, subtitle] = state.titles[view];
  els.title.textContent = title;
  els.subtitle.textContent = subtitle;
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === view);
  });
  setLoading();
  await checkApi();
  try {
    const loaders = {
      overview: loadOverview,
      orders: loadOrders,
      users: loadUsers,
      repairers: loadRepairers,
      stores: loadStores,
      regions: loadRegions,
      proxy: loadProxy,
      domestic: loadDomestic,
      payroll: loadPayroll,
      warranties: loadWarranties,
      wallet: loadWallet,
      finance: loadFinance,
      support: loadSupport,
      packages: loadPackages,
      ops: loadOps
    };
    await loaders[view]();
  } catch (error) {
    els.content.innerHTML = `<div class="section"><div class="error">${escapeHtml(error.message)}</div></div>`;
  }
}

function readForm(formEl) {
  const data = {};
  new FormData(formEl).forEach((value, key) => {
    const trimmed = String(value).trim();
    if (trimmed === "") return;
    data[key] = ["id", "_id", "years", "times", "count", "month", "level", "price"].some((part) => key.includes(part))
      ? Number(trimmed)
      : trimmed;
  });
  return data;
}

async function handleForm(formEl) {
  const action = formEl.dataset.form;
  for (const input of formEl.querySelectorAll('[data-choice]')) {
    if (input.disabled || !input.value.trim()) continue;
    const option = Array.from(document.getElementById(input.getAttribute('list')).options).find(o => o.value === input.value.trim());
    if (!option) { input.setCustomValidity('请从搜索候选项中选择，不能填写未匹配的名称'); input.reportValidity(); return; }
  }
  const data = readForm(formEl);
  for (const input of formEl.querySelectorAll('[data-choice]')) {
    if (input.disabled) { delete data[input.name]; continue; }
    const option = Array.from(document.getElementById(input.getAttribute('list')).options).find(o => o.value === input.value.trim());
    if (option) data[input.name] = Number(option.dataset.value);
  }
  if (action === 'edit-store') {
    await api(`/api/v1/stores/${Number(data.id)}`, {method:'PATCH',body:{name:data.name,region_id:Number(data.region_id),manager_id:Number(data.manager_id),city_manager_id:data.city_manager_id?Number(data.city_manager_id):null,default_second_receiver_id:data.default_second_receiver_id?Number(data.default_second_receiver_id):null,remark:data.remark || ''}});
    els.modal.hidden=true; await loadStores();notify('门店已保存');return;
  }
  if (action === 'store-coverage') {
    await api(`/api/v1/stores/${Number(data.id)}/coverage`, {method:'PUT',body:{estates:String(data.estates || '').split(/\n|；|;/).map(s=>s.trim()).filter(Boolean)}});
    els.modal.hidden=true;await loadStores();notify('小区服务范围已保存');return;
  }
  if (action === "create-store-address" || action === "edit-store-address") {
    const me = await api('/api/v1/auth/me');
    const area=(state.cache.addressAreas || []).find(a=>`${a.city}/${a.district}`===data.city_region && a.name===data.estate.trim());
    if (!area) throw new Error('该区县的小区尚未分配门店，请先在门店分配小区服务范围；小区名称需与分配名称一致');
    const fields = {service_area_id:area.id,estate:data.estate.trim(),building:data.building || '', unit:data.unit || '',room:data.room || '', aliases:data.aliases || '', detail_hint:data.detail_hint || '',source_name:data.source_name || '',source_ref:data.source_ref || '',catalog_published:true};
    if (!fields.estate || (!data.door_number && !fields.room)) throw new Error('请填写小区，以及房号或标准门牌写法');
    // Empty door is synthesized from the structural fields; PATCH must send the resulting value.
    fields.door_number = data.door_number || [fields.building,fields.unit,fields.room && `${fields.room}室`].filter(Boolean).join('');
    if (action === 'edit-store-address') await api(`/api/v1/stores/addresses/${Number(data.id)}`, {method:'PATCH',body:fields});
    else await api('/api/v1/stores/addresses', {method:'POST',body:{...fields,created_by_user_id:me.id}});
    els.modal.hidden = true;
    await loadStores(); return;
  }
  if (action === "create-domestic-worker") {
    await api("/api/v1/business/domestic/workers", {
      method: "POST",
      body: {
        service_type: data.service_type,
        name: data.name,
        store_id: data.store_id || null,
        years_experience: Number(data.years_experience || 0),
        price_min: Number(data.price_min || 0),
        price_max: Number(data.price_max || 0),
        skills_json: JSON.stringify(String(data.skills || "").split(/[，,]/).map((item) => item.trim()).filter(Boolean)),
        intro: data.intro || null,
      },
    });
    formEl.reset();
    notify("人员档案已创建");
    await loadView("domestic");
    return;
  }
  const endpoints = {
    "create-user": ["/api/v1/users", data],
    "create-repairer": ["/api/v1/repairers", data],
    "create-store": ["/api/v1/stores", data],
    "create-region": ["/api/v1/regions", data],
    "create-package": ["/api/v1/service-packages", data]
  };
  const target = endpoints[action];
  if (!target) return;
  await api(target[0], { method: "POST", body: target[1] });
  formEl.reset();
  notify(action === "create-store" ? "门店已创建，请点击“启用并开通”，再分配服务范围" : "已保存");
  await loadView();
}

async function promptNumber(label, current = "") {
  const value = window.prompt(label, current ?? "");
  if (value === null) return null;
  const num = Number(value);
  if (!Number.isFinite(num)) throw new Error("请输入有效数字");
  return num;
}

async function promptText(label, current = "") {
  const value = window.prompt(label, current ?? "");
  if (value === null) return null;
  return value.trim();
}

function showModal(title, html) {
  els.modalTitle.textContent = title;
  els.modalBody.innerHTML = html;
  els.modal.querySelector(".modal-panel").classList.toggle("status-modal-panel", !!els.modalBody.querySelector('[data-form="repairer-status"]'));
  els.modal.hidden = false;
}

async function handleAction(button) {
  const action = button.dataset.action;
  const id = button.dataset.id;

  if (action === 'edit-store-address') {
    const row = (state.cache.storeAddresses || []).find(item => item.id === Number(button.dataset.id));
    if (!row) throw new Error('地址不存在，请刷新');
    showModal('修改实体地址及同址别名', `<form class="form-grid" data-form="edit-store-address">${addressEditor(state.cache.addressAreas || [],row)}<button class="btn primary" type="submit">保存修改</button></form>`); return;
  }
  if (action === 'delete-store-address') {
    if (!confirm('删除后客户端不能再选择此地址；历史订单保留原地址。确认删除？')) return;
    await api(`/api/v1/stores/addresses/${Number(button.dataset.id)}`, {method:'DELETE'});
    await loadStores(); return;
  }
  if (action === 'close-modal') { els.modal.hidden=true;return; }
  if (action === 'repairer-profile') {
    const [r, regions] = await Promise.all([api(`/api/v1/repairers/${id}`), api('/api/v1/regions')]);
    showModal('完善师傅资料', `<form class="form-grid" data-form="repairer-profile"><input type="hidden" name="id" value="${r.id}"><div class="field"><label>技能</label><input name="skills" required value="${escapeHtml(r.skills==='待完善'?'':r.skills)}" placeholder="例如：水电,家电维修"></div><div class="field"><label>服务区域</label><select name="region_id" required><option value="">请选择</option>${regionChoices(regions).map(o=>`<option value="${o.value}" ${Number(o.value)===r.region_id?'selected':''}>${escapeHtml(o.label)}</option>`).join('')}</select></div><div class="field"><label>简介</label><input name="intro" value="${escapeHtml(r.intro || '')}"></div><button class="btn primary" type="submit">保存资料</button></form>`);
    return;
  }
  if (action === 'user-business-roles') {
    const granted = (button.dataset.roles || '').split(',');
    showModal('勾选业务身份', `<form data-form="user-business-roles"><input type="hidden" name="user_id" value="${id}"><p>同一手机号可同时拥有以下三个身份；保存后请该用户重新登录。</p>${Object.entries({store_manager:'店长',repairer:'师傅',promotion_manager:'推广经理'}).map(([r,label]) => `<label class="identity-choice"><input type="checkbox" name="business_roles" value="${r}" ${granted.includes(r) ? 'checked' : ''} ${button.dataset.fixed === '1' && button.dataset.primary === r ? 'disabled' : ''}>${label}</label>${button.dataset.fixed === '1' && button.dataset.primary === r ? `<input type="hidden" name="business_roles" value="${r}">` : ''}`).join('')}<p class="muted">admin 保留最高管理员权限，基础账号原有主角色保持不变。勾选师傅身份会自动建立档案，请到师傅页完善技能和服务区域。</p><button class="btn primary" type="submit">保存身份</button></form>`);
    return;
  }
  if (action === 'search-users') return loadUsers();
  if (action === 'toggle-address-library') {
    state.addressLibraryOpen = !state.addressLibraryOpen;
    document.querySelector('#address-library-body').hidden = !state.addressLibraryOpen;
    button.textContent = state.addressLibraryOpen ? '收起' : '展开';
    button.setAttribute('aria-expanded', String(state.addressLibraryOpen));
    return;
  }
  if (action === 'guide-view') return loadView(button.dataset.target);
  if (action === 'store-coverage') {
    const id = Number(button.dataset.id);
    const row = state.cache.storeForm.stores.find(item => item.id === id);
    const assigned = await api(`/api/v1/stores/${id}/coverage`);
    showModal('分配小区服务范围', `<form class="form-grid" data-form="store-coverage"><input type="hidden" name="id" value="${id}"><p>${escapeHtml(row.name)}：只分配本门店所属区县内的小区，同一区县可以有多家门店。</p><p>原街道/社区范围（仅供迁移参考，保存后由下面的小区列表替换）：${escapeHtml(assigned.filter(a=>a.area_type!=='estate').map(a=>a.name).join('、') || '无')}</p><div class="field"><label>小区 / 分期名称（一行一个）</label><textarea name="estates" rows="12" placeholder="蓝月湾一期&#10;浪琴湾">${escapeHtml(assigned.filter(a=>a.area_type==='estate').map(a=>a.name).join('\n'))}</textarea><small>保存会替换本店原服务范围。留空保存表示清空。已属于其他门店的小区不能重复分配。</small></div><button class="btn primary" type="submit">保存小区服务范围</button></form>`);return;
  }
  if (action === 'edit-store') {
    const {stores,regions,users,repairers}=state.cache.storeForm;
    const row=stores.find(item=>item.id===Number(button.dataset.id));
    const options=(items,value,empty=true)=>(empty?'<option value="">未设置</option>':'')+items.map(item=>`<option value="${item.value}" ${Number(item.value)===Number(value)?'selected':''}>${escapeHtml(item.label)}</option>`).join('');
    showModal('修改门店', `<form class="form-grid" data-form="edit-store"><input type="hidden" name="id" value="${row.id}"><div class="field"><label>门店名称</label><input name="name" required value="${escapeHtml(row.name)}"></div><div class="field"><label>所属区县</label><select name="region_id" required>${options(regionChoices(regions.filter(r=>r.level===2),regions),row.region_id)}</select></div><div class="field"><label>店长</label><select name="manager_id" required>${options(users.filter(u=>u.is_active).map(u=>({value:u.id,label:u.name})),row.manager_id,false)}</select></div><div class="field"><label>城市经理</label><select name="city_manager_id">${options(userChoices(users,['city_manager']),row.city_manager_id)}</select></div><div class="field"><label>默认师傅</label><select name="default_second_receiver_id">${options(repairers.map(r=>({value:r.id,label:users.find(u=>u.id===r.user_id)?.name || String(r.id)})),row.default_second_receiver_id)}</select></div><div class="field"><label>备注</label><textarea name="remark">${escapeHtml(row.remark || '')}</textarea></div><button class="btn primary" type="submit">保存门店</button></form>`);return;
  }
  if (action === "filter-orders") return loadOrders();
  if (action === "service-area-filter") return loadRegions();
  if (action === "service-area-sync") {
    const result = await api("/api/v1/service-areas/sync-xiamen", { method: "POST", body: {} });
    notify(`地址库已同步，共 ${result.total} 条`);
    await loadRegions();
    return;
  }
  if (action === "service-area-clear-selection") {
    state.selectedServiceAreas.clear();
    await loadRegions();
    return;
  }
  if (action === "service-area-assign") {
    const ids = [...state.selectedServiceAreas];
    if (!ids.length) throw new Error("请先勾选要分配的地址");
    const numberValue = (selector) => {
      const value = document.querySelector(selector)?.value;
      return value ? Number(value) : null;
    };
    if (!numberValue("#service-area-primary-store")) throw new Error("请选择已开通的主服务门店；未开通门店请先到门店页开通");
    const body = {
      service_area_ids: ids,
      primary_store_id: numberValue("#service-area-primary-store"),
      backup_store_id: numberValue("#service-area-backup-store"),
      conflict_mode: document.querySelector("#service-area-conflict-mode")?.value || "skip",
      remark: document.querySelector("#service-area-remark")?.value?.trim() || null,
      dry_run: true,
    };
    const preview = await api("/api/v1/service-areas/assignments/bulk", { method: "POST", body });
    const samples = preview.conflict_samples.length ? `\n冲突示例：\n${preview.conflict_samples.join("\n")}` : "";
    const approved = window.confirm(`共选择 ${preview.selected} 条，可新增 ${preview.created} 条、更新 ${preview.updated} 条、跳过 ${preview.skipped} 条，已有分配 ${preview.conflicts} 条。${samples}\n\n确认执行吗？`);
    if (!approved) return;
    body.dry_run = false;
    const result = await api("/api/v1/service-areas/assignments/bulk", { method: "POST", body });
    state.selectedServiceAreas.clear();
    notify(`分配完成：新增 ${result.created}，更新 ${result.updated}，跳过 ${result.skipped}`);
    await loadRegions();
    return;
  }
  if (action === "service-area-clear") {
    const ids = [...state.selectedServiceAreas];
    if (!ids.length) throw new Error("请先勾选要清除分配的地址");
    const preview = await api("/api/v1/service-areas/assignments/bulk-clear", {
      method: "POST", body: { service_area_ids: ids, dry_run: true },
    });
    if (!window.confirm(`将清除 ${preview.cleared} 条已有分配，未分配的 ${preview.unchanged} 条保持不变。确认继续吗？`)) return;
    await api("/api/v1/service-areas/assignments/bulk-clear", {
      method: "POST", body: { service_area_ids: ids, remark: "管理后台批量清除", dry_run: false },
    });
    state.selectedServiceAreas.clear();
    notify("地址分配已清除");
    await loadRegions();
    return;
  }

  if (action === "order-price") {
    const price = await promptNumber("订单金额");
    if (price === null) return;
    await api(`/api/v1/orders/${id}`, { method: "PATCH", body: { price } });
  } else if (action === "order-assign") {
    const repairerId = await promptNumber("师傅ID");
    if (repairerId === null) return;
    await api(`/api/v1/orders/${id}/assign`, { method: "POST", body: { repairer_id: repairerId } });
  } else if (action === "order-auto") {
    await api(`/api/v1/orders/${id}/auto-dispatch`, { method: "POST", body: {} });
  } else if (action === "order-status") {
    const next = await promptText(`目标状态：${statusOptions.join(", ")}`);
    if (!next) return;
    await api(`/api/v1/orders/${id}/transition`, { method: "POST", body: { to_status: next, operator_type: "admin" } });
  } else if (action === "order-review") {
    const wage = await promptNumber("师傅工资金额", 0);
    if (wage === null) return;
    await api(`/api/v1/orders/${id}/store-review`, { method: "POST", body: { technician_wage_amount: wage, wage_mode: "per_order", remark: "后台复核" } });
  } else if (action === "order-logs") {
    const logs = await api(`/api/v1/orders/${id}/logs`);
    showModal(`订单 #${id} 日志`, table([
      { label: "从", key: "from_status" },
      { label: "到", key: "to_status" },
      { label: "操作者", key: "operator_type" },
      { label: "ID", render: (row) => row.operator_id || "-" },
      { label: "备注", key: "remark", wrap: true },
      { label: "时间", render: (row) => fmtDate(row.created_at) }
    ], logs, "暂无日志"));
    return;
  } else if (action === "user-status") {
    if (!window.confirm(button.dataset.active === "1" ? "停用后该用户将无法登录和操作，确认停用？" : "确认启用该用户？")) return;
    await api(`/api/v1/users/${id}/account-status`, { method: "PATCH", body: { is_active: button.dataset.active !== "1" } });
  } else if (action === "user-role") {
    const roles = { customer: "客户", repairer: "师傅", second_receiver: "二接师傅", store_manager: "店长", city_manager: "城市经理", promotion_manager: "推广经理", tech_support: "客服", finance: "财务", platform_admin: "平台管理员" };
    showModal("设置业务角色", `<form data-form="user-role"><input type="hidden" name="user_id" value="${id}"><select name="business_role">${Object.entries(roles).map(([key, label]) => `<option value="${key}" ${button.dataset.role === key ? "selected" : ""}>${label}</option>`).join("")}</select><button class="btn primary" type="submit">保存</button></form>`);
    return;
  } else if (action === "user-name") {
    const name = await promptText("姓名", button.dataset.name);
    if (!name) return;
    await api(`/api/v1/users/${id}`, { method: "PATCH", body: { name } });
  } else if (action === "user-promo") {
    await api(`/api/v1/users/${id}`, { method: "PATCH", body: { is_promotion_manager: button.dataset.active !== "1" } });
  } else if (action === "repairer-status") {
    showModal('修改师傅接单状态', `<form class="status-dialog-form" data-form="repairer-status"><input type="hidden" name="id" value="${id}"><div class="field"><label>接单状态</label><select name="status" required><option value="online" ${button.dataset.status==='online'?'selected':''}>在线</option><option value="offline" ${button.dataset.status!=='online'?'selected':''}>休息</option></select><small class="field-hint">在线：可以接单；休息：暂停接单。</small></div><div class="status-dialog-actions"><button class="btn" type="button" data-action="close-modal">取消</button><button class="btn primary" type="submit">确认修改</button></div></form>`);
    return;
  } else if (action === "repairer-skills") {
    const skills = await promptText("技能", button.dataset.skills);
    if (!skills) return;
    await api(`/api/v1/repairers/${id}`, { method: "PATCH", body: { skills } });
  } else if (action === "store-enabled") {
    await api(`/api/v1/stores/${id}`, { method: "PATCH", body: { enabled: button.dataset.enabled !== "1" } });
  } else if (action === "store-default-repairer") {
    const repairerId = await promptNumber("默认接单师傅ID");
    if (repairerId === null) return;
    await api(`/api/v1/stores/${id}`, { method: "PATCH", body: { default_second_receiver_id: repairerId } });
  } else if (action === "region-name") {
    const name = await promptText("区域名称", button.dataset.name);
    if (!name) return;
    await api(`/api/v1/regions/${id}`, { method: "PATCH", body: { name } });
  } else if (action === "region-manager") {
    const managerId = await promptNumber("负责人用户ID");
    if (managerId === null) return;
    await api(`/api/v1/regions/${id}`, { method: "PATCH", body: { manager_id: managerId } });
  } else if (action === "withdraw-approve" || action === "withdraw-reject") {
    const approve = action === "withdraw-approve";
    const remark = await promptText(approve ? "通过备注" : "拒绝原因", approve ? "审核通过" : "审核拒绝");
    if (remark === null) return;
    await api(`/api/v1/wallet/withdraw/${id}/review`, {
      method: "POST",
      body: { action: approve ? "approve" : "reject", remark }
    });
  } else if (action === "profit-order") {
    const orderId = document.querySelector("#profit-order-id").value;
    if (!orderId) return notify("请输入订单ID");
    const summary = await api(`/api/v1/finance/profit/order/${orderId}`);
    showModal(`订单 #${orderId} 分润`, `<pre class="pre">${escapeHtml(JSON.stringify(summary, null, 2))}</pre>`);
    return;
  } else if (action === "profit-user") {
    const userId = document.querySelector("#profit-user-id").value;
    if (!userId) return notify("请输入用户ID");
    const items = await api(`/api/v1/finance/profit/user/${userId}`);
    showModal(`用户 #${userId} 分润`, `<pre class="pre">${escapeHtml(JSON.stringify(items, null, 2))}</pre>`);
    return;
  } else if (action === "payment-sync") {
    const result = await api(`/api/v1/payment/order/${id}/wechat-sync`, { method: "POST", body: {} });
    showModal(`支付单 #${id}`, `<pre class="pre">${escapeHtml(JSON.stringify(result, null, 2))}</pre>`);
    await loadView("finance");
    return;
  } else if (action === "ticket-view") {
    const ticketButton = [...document.querySelectorAll("button[data-action='ticket-view']")]
      .find((item) => item.dataset.id === id);
    const row = ticketButton
      ? [...ticketButton.closest("tr").children].map((cell) => cell.textContent.trim()).join("\n")
      : "";
    showModal(`工单 #${id}`, `<pre class="pre">${escapeHtml(row)}</pre>`);
    return;
  } else if (action === "ticket-reply") {
    const userId = await promptNumber("回复人用户ID");
    if (userId === null) return;
    const content = await promptText("回复内容");
    if (!content) return;
    const close = window.confirm("是否同时关闭工单？");
    await api(`/api/v1/support/tickets/${id}/reply`, { method: "POST", body: { user_id: userId, content, close } });
  } else if (action === "alert-resolve") {
    await api(`/api/v1/admin/alerts/${id}/resolve`, { method: "POST", body: {} });
  } else if (action === "reconcile-run") {
    const result = await api("/api/v1/admin/reconcile/run", { method: "POST", body: {} });
    showModal("对账结果", `<pre class="pre">${escapeHtml(JSON.stringify(result, null, 2))}</pre>`);
    await loadView("ops");
    return;
  } else if (action === "proxy-code") {
    const result = await api(`/api/v1/business/orders/${id}/access/${button.dataset.purpose}`, {
      method: "POST",
      body: { created_by_user_id: null },
    });
    showModal(`订单 #${id} 二维码`, `<div style="text-align:center"><img src="${escapeHtml(result.code_url)}" alt="订单二维码" style="width:min(430px,100%);aspect-ratio:1;object-fit:contain"><p class="muted">二维码具有时效，重新生成后旧码失效</p></div>`);
    return;
  } else {
    return;
  }

  notify("操作完成");
  await loadView();
}

document.querySelector(".nav").addEventListener("click", (event) => {
  const button = event.target.closest("[data-view]");
  if (button) loadView(button.dataset.view);
});

document.querySelector("#refresh-btn").addEventListener("click", () => loadView());

const logoutBtn = document.querySelector("#logout-btn");
if (logoutBtn) logoutBtn.addEventListener("click", logout);

els.content.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  try {
    await handleAction(button);
  } catch (error) {
    notify(error.message || "操作失败");
  }
});

document.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const formName = event.target.dataset.form;
    if (formName === 'repairer-status') {
      const values=new FormData(event.target);const status=values.get('status');
      if (!['online','offline'].includes(status)) throw new Error('请选择在线或休息');
      await api(`/api/v1/repairers/${values.get('id')}`, {method:'PATCH',body:{status}});
      els.modal.hidden=true;notify(status==='online'?'已设为在线':'已设为休息');await loadView('repairers');return;
    }
    if (formName === 'repairer-profile') {
      const values = new FormData(event.target);
      await api(`/api/v1/repairers/${values.get('id')}`, {method:'PATCH',body:{skills:values.get('skills'),region_id:Number(values.get('region_id')),intro:values.get('intro')}});
      els.modal.hidden=true;notify('师傅资料已完善');await loadView('repairers');return;
    }
    if (formName === 'user-business-roles') {
      const fields=new FormData(event.target);
      await api(`/api/v1/users/${fields.get('user_id')}/business-roles`,{method:'PATCH',body:{roles:fields.getAll('business_roles')}});
      els.modal.hidden=true;notify('身份已保存，请用户重新登录');await loadUsers();return;
    }
    if (formName === "user-role") {
      const fields = new FormData(event.target);
      await api(`/api/v1/users/${fields.get("user_id")}`, { method: "PATCH", body: { business_role: fields.get("business_role") } });
      els.modal.hidden = true; await loadView("users"); return;
    }
    if (formName === "auth-login") {
      await submitAuthLogin(event.target);
      return;
    }
    if (formName === "auth-token") {
      await submitAuthTokenLogin(event.target);
      return;
    }
    await handleForm(event.target);
  } catch (error) {
    notify(error.message || "保存失败");
  }
});

els.content.addEventListener("change", async (event) => {
  const checkbox = event.target.closest("[data-service-area-id]");
  if (checkbox) {
    const id = Number(checkbox.dataset.serviceAreaId);
    if (checkbox.checked) state.selectedServiceAreas.add(id);
    else state.selectedServiceAreas.delete(id);
    const counter = els.content.querySelector(".selection-count strong");
    if (counter) counter.textContent = String(state.selectedServiceAreas.size);
    return;
  }
  if (event.target.id === "service-area-select-all") {
    els.content.querySelectorAll("[data-service-area-id]").forEach((item) => {
      item.checked = event.target.checked;
      const id = Number(item.dataset.serviceAreaId);
      if (item.checked) state.selectedServiceAreas.add(id);
      else state.selectedServiceAreas.delete(id);
    });
    const counter = els.content.querySelector(".selection-count strong");
    if (counter) counter.textContent = String(state.selectedServiceAreas.size);
  }
});

document.querySelector("#modal-close").addEventListener("click", () => {
  els.modal.hidden = true;
});

els.modal.addEventListener("click", (event) => {
  if (event.target === els.modal) els.modal.hidden = true;
});

loadWallet = async function loadWalletWechat() {
  const [withdrawals, transferStatus] = await Promise.all([
    api("/api/v1/wallet/withdrawals?limit=100"),
    api("/api/v1/wallet/wechat-transfer/config-status").catch((error) => ({
      ready: false,
      issues: [error.message || "wechat transfer config failed"],
    })),
  ]);

  const statusBody = `
    <div class="form-grid">
      <div class="field"><label>Wechat transfer</label>${transferStatus.ready ? badge("ready", "ok") : badge("not ready", "warn")}</div>
      <div class="field"><label>Auto transfer</label>${transferStatus.auto_enabled ? badge("enabled", "ok") : badge("disabled", "warn")}</div>
      <div class="field"><label>Scene ID</label>${transferStatus.scene_id_configured ? badge("configured", "ok") : badge("missing", "danger")}</div>
      <div class="field"><label>AppSecret</label>${transferStatus.app_secret_configured ? badge("configured", "ok") : badge("missing", "danger")}</div>
    </div>
    ${(transferStatus.issues || []).length ? `<div class="empty">${transferStatus.issues.map(escapeHtml).join("<br>")}</div>` : ""}
  `;

  const body = table([
    { label: "ID", key: "id" },
    { label: "用户", key: "user_id" },
    { label: "Wallet", key: "wallet_id" },
    { label: "金额", render: (row) => money(row.amount) },
    { label: "状态", render: (row) => statusBadge(row.status) },
    { label: "Payout", render: (row) => `${row.payout_provider || "-"} / ${row.payout_status || "-"}` },
    { label: "Wechat bill", render: (row) => row.transfer_out_bill_no || "-" },
    { label: "Remark", key: "remark", wrap: true },
    { label: "创建时间", render: (row) => fmtDate(row.created_at) },
    { label: "Reviewed", render: (row) => fmtDate(row.reviewed_at) },
    {
      label: "操作",
      render: (row) => {
        if (row.status === "pending") {
          return `<div class="actions">
            ${actionButton("Manual approve", "withdraw-approve-manual", { id: row.id }, "primary")}
            ${actionButton("Wechat payout", "withdraw-approve-wechat", { id: row.id }, "primary")}
            ${actionButton("Reject", "withdraw-reject", { id: row.id }, "danger")}
          </div>`;
        }
        if (row.payout_provider === "wechat" && row.payout_status !== "success") {
          return actionButton("Sync", "withdraw-sync", { id: row.id }, "primary");
        }
        return "-";
      },
    },
  ], withdrawals, "No withdrawal requests");

  els.content.innerHTML = `
    ${section("Wechat Transfer Config", "For real payouts, merchant transfer product, scene ID and user openid are required.", statusBody)}
    ${section("Withdrawals", "Approve manually or initiate WeChat payout.", body)}
  `;
};

loadFinance = async function loadFinanceWechat() {
  const [payments, refunds, wechatStatus] = await Promise.all([
    api("/api/v1/payment/list?limit=100").catch(() => []),
    api("/api/v1/payment/refunds?limit=100").catch(() => []),
    api("/api/v1/payment/wechat/config-status").catch((error) => ({
      ready: false,
      issues: [error.message || "wechat config failed"],
    })),
  ]);

  const wechatStatusBody = `
    <div class="form-grid">
      <div class="field"><label>支付单</label>${wechatStatus.ready ? badge("ready", "ok") : badge("not ready", "warn")}</div>
      <div class="field"><label>AppID</label><span>${escapeHtml(wechatStatus.appid || "-")}</span></div>
      <div class="field"><label>商户号</label><span>${escapeHtml(wechatStatus.mch_id || "-")}</span></div>
      <div class="field"><label>商户证书序列号</label><span>${escapeHtml(wechatStatus.merchant_serial_no || "-")}</span></div>
      <div class="field wide"><label>支付回调地址</label><span>${escapeHtml(wechatStatus.notify_url || "-")}</span></div>
      <div class="field wide"><label>退款回调地址</label><span>${escapeHtml(wechatStatus.refund_notify_url || "-")}</span></div>
      <div class="field"><label>APIv3 key</label>${wechatStatus.api_v3_key_configured ? badge("configured", "ok") : badge("missing", "danger")}</div>
      <div class="field"><label>AppSecret</label>${wechatStatus.app_secret_configured ? badge("configured", "ok") : badge("missing", "danger")}</div>
      <div class="field"><label>证书</label>${wechatStatus.cert_exists ? badge("found", "ok") : badge("missing", "danger")}</div>
      <div class="field"><label>私钥</label>${wechatStatus.key_exists ? badge("found", "ok") : badge("missing", "danger")}</div>
    </div>
    ${(wechatStatus.issues || []).length ? `<div class="empty">${wechatStatus.issues.map(escapeHtml).join("<br>")}</div>` : ""}
  `;

  const tools = `
    <div class="form-grid">
      <div class="field"><label for="profit-order-id">订单编号</label><input id="profit-order-id" type="number"></div>
      <button class="btn" data-action="profit-order">订单分润</button>
      <div class="field"><label for="profit-user-id">用户编号</label><input id="profit-user-id" type="number"></div>
      <button class="btn" data-action="profit-user">用户分润</button>
    </div>
  `;

  const paymentsTable = table([
    { label: "支付单", render: (row) => `#${row.id}` },
    { label: "订单", key: "order_id" },
    { label: "用户", key: "user_id" },
    { label: "金额", render: (row) => money(row.amount) },
    { label: "状态", render: (row) => statusBadge(row.status) },
    { label: "渠道", key: "provider" },
    { label: "商户订单号", render: (row) => row.out_trade_no || "-" },
    { label: "微信交易号", render: (row) => row.transaction_id || "-" },
    { label: "支付时间", render: (row) => fmtDate(row.paid_at) },
    {
      label: "操作",
      render: (row) => `<div class="actions">
        ${row.provider === "wechat" && row.status === "pending" ? actionButton("同步支付", "payment-sync", { id: row.id }, "primary") : ""}
        ${row.provider === "wechat" && ["paid", "partially_refunded"].includes(row.status) ? actionButton("退款", "payment-refund", { id: row.id, amount: row.amount }, "danger") : ""}
      </div>`,
    },
  ], payments, "暂无支付记录");

  const refundsTable = table([
    { label: "退款", render: (row) => `#${row.id}` },
    { label: "支付单", key: "pay_order_id" },
    { label: "订单", key: "order_id" },
    { label: "用户", key: "user_id" },
    { label: "金额", render: (row) => money(row.amount) },
    { label: "状态", render: (row) => statusBadge(row.status) },
    { label: "商户退款号", render: (row) => row.out_refund_no || "-" },
    { label: "微信退款号", render: (row) => row.refund_id || "-" },
    { label: "创建时间", render: (row) => fmtDate(row.created_at) },
    {
      label: "操作",
      render: (row) => row.status === "processing" ? actionButton("同步退款", "refund-sync", { id: row.id }, "primary") : "-",
    },
  ], refunds, "暂无退款记录");

  els.content.innerHTML = `
    ${section("微信支付配置", "支付通道状态", wechatStatusBody)}
    ${section("支付与分润", "支付记录、退款记录及分润查询", `${tools}${paymentsTable}<h3 style="margin:22px 0 12px">退款记录</h3>${refundsTable}`)}
  `;
};

const previousHandleAction = handleAction;
handleAction = async function handleWechatFinanceAction(button) {
  const action = button.dataset.action;
  const id = button.dataset.id;

  if (action === "withdraw-approve-manual" || action === "withdraw-approve-wechat" || action === "withdraw-reject") {
    const approve = action !== "withdraw-reject";
    const payoutMethod = action === "withdraw-approve-wechat" ? "wechat" : "manual";
    const remark = await promptText(approve ? "审核备注" : "驳回原因", approve ? "approved" : "rejected");
    if (remark === null) return;
    await api(`/api/v1/wallet/withdraw/${id}/review`, {
      method: "POST",
      body: { action: approve ? "approve" : "reject", remark, payout_method: payoutMethod },
    });
    notify("操作完成");
    await loadView("wallet");
    return;
  }

  if (action === "withdraw-sync") {
    const result = await api(`/api/v1/wallet/withdraw/${id}/wechat-sync`, { method: "POST", body: {} });
    showModal(`Withdrawal #${id}`, `<pre class="pre">${escapeHtml(JSON.stringify(result, null, 2))}</pre>`);
    await loadView("wallet");
    return;
  }

  if (action === "payment-refund") {
    const amount = await promptNumber("退款金额", button.dataset.amount || "");
    if (amount === null) return;
    const reason = await promptText("退款原因", "refund");
    if (reason === null) return;
    const result = await api("/api/v1/payment/refund", {
      method: "POST",
      body: { pay_order_id: Number(id), amount, reason },
    });
    showModal(`Refund #${result.id}`, `<pre class="pre">${escapeHtml(JSON.stringify(result, null, 2))}</pre>`);
    await loadView("finance");
    return;
  }

  if (action === "refund-sync") {
    const result = await api(`/api/v1/payment/refund/${id}/wechat-sync`, { method: "POST", body: {} });
    showModal(`Refund #${id}`, `<pre class="pre">${escapeHtml(JSON.stringify(result, null, 2))}</pre>`);
    await loadView("finance");
    return;
  }

  return previousHandleAction(button);
};

const WORKFLOW_GUIDES = {
  stores:{title:'创建门店与开通服务',steps:[['users','第一步：准备店长账号','新成员先在小程序注册，在人员页搜索手机号，点击“业务身份”勾选店长。已有基础店长可直接使用。兼任身份保存后，重新登录客户端即可切换。'],['regions','第二步：创建城市和区县','先创建厦门市，再选择上级厦门市创建海沧区等区县。'],['stores','第三步：创建并开通门店','选择所属区域和店长，新增门店后点击“启用并开通”。'],['regions','第四步：分配社区并开通下单','展开厦门地址库，筛选行政区及街道，勾选社区，选择已开通的主服务门店并确认分配。完成后客户即可选择该社区及小区，填写楼栋、单元和房号下单，无需逐户录入。'],['repairers','第五步：准备师傅接单','在用户页勾选师傅身份，再到师傅页建立档案并选择服务区域；店长也可兼任师傅。下单开通无需等待逐户地址录入，实际派单前应备好师傅。']]},
  users:{title:'添加与管理人员',steps:[['users','第一步：本人真实注册','请新成员在小程序主动使用手机号快捷登录完成注册。'],['users','第二步：搜索并授权','在用户页按手机号查找。用“业务身份”勾选店长、师傅、推广经理，可兼任；扫个人推广码注册的客户会绑定推荐人。admin保留最高管理权限。'],['stores','第三步：绑定业务','店长选择为门店负责人；师傅需建立师傅档案，工作人员按所负责业务进入对应页面。'],['users','第四步：账号管理','离职或暂停使用时停用账号；恢复后可以重新登录。基础账号的名称、手机号和角色保持原设置。']]},
  orders:{title:'订单服务与结算',steps:[['stores','第一步：确保地址可下单','门店已开通、社区已分配，即可接收客户订单。'],['orders','第二步：客户提交订单','客户选择服务社区及小区，填写楼栋、单元和房号，再提交问题。门店自动匹配。'],['orders','第三步：接单与派单','门店确认订单并安排师傅，师傅接单上门并提交服务内容与费用。'],['orders','第四步：客户确认与支付','客户确认服务单和金额后付款，门店完成复核。'],['warranties','第五步：完工与售后','核对服务结果和保修凭证，按实际问题处理售后。'],['payroll','第六步：工资与提现','核对工资和资金流水，再审核提现；实际收付款以支付结果为准。']]}
};
function setupWorkflowGuide() {
  const open = document.createElement('button');open.className='btn guide-launch';open.textContent='操作流程';open.id='workflow-guide-open';
  document.querySelector('.top-actions').prepend(open);
  const panel=document.createElement('aside');panel.className='workflow-guide';panel.hidden=true;panel.setAttribute('role','dialog');panel.setAttribute('aria-label','业务操作流程');
  panel.innerHTML=`<div class="guide-head" tabindex="0" aria-label="拖动流程窗口，方向键可移动"><strong>业务操作流程</strong><button class="btn compact" id="guide-close" aria-label="关闭操作流程">关闭</button></div><div class="guide-tabs">${Object.entries(WORKFLOW_GUIDES).map(([key,v])=>`<button class="btn compact" data-guide="${key}">${v.title}</button>`).join('')}</div><div class="guide-body"></div><div class="guide-foot">拖动标题栏可移动窗口；键盘聚焦标题栏后使用方向键移动。</div>`;
  document.body.append(panel);
  const show = key => { const g=WORKFLOW_GUIDES[key];panel.querySelector('.guide-body').innerHTML='<div class="workflow-note">门店启用 → 分配社区 → 客户选址下单。无需逐户开通地址；小区未收录可直接填写，单元可选填。</div>'+g.steps.map(([view,title,text])=>`<article class="guide-step"><h3>${title}</h3><p>${text}</p><button class="btn compact" data-guide-view="${view}">前往${state.titles[view][0]}</button></article>`).join(''); };
  open.addEventListener('click',()=>{panel.hidden=!panel.hidden;if(!panel.hidden)show(WORKFLOW_GUIDES[state.view]?state.view:'stores');});
  panel.querySelector('#guide-close').addEventListener('click',()=>{panel.hidden=true;open.focus();});
  panel.addEventListener('click',e=>{const tab=e.target.closest('[data-guide]');if(tab)show(tab.dataset.guide);const link=e.target.closest('[data-guide-view]');if(link)loadView(link.dataset.guideView).catch(e=>notify(e.message));});
  const header=panel.querySelector('.guide-head');let drag=null;
  const move=(x,y)=>{panel.style.right='auto';panel.style.left=`${Math.max(0,Math.min(x,window.innerWidth-panel.offsetWidth))}px`;panel.style.top=`${Math.max(0,Math.min(y,window.innerHeight-70))}px`;};
  header.addEventListener('pointerdown',e=>{if(e.target.closest('button'))return;const r=panel.getBoundingClientRect();drag={x:e.clientX-r.left,y:e.clientY-r.top};header.setPointerCapture(e.pointerId);});
  header.addEventListener('pointermove',e=>{if(drag)move(e.clientX-drag.x,e.clientY-drag.y);});
  header.addEventListener('pointerup',()=>{drag=null;});header.addEventListener('pointercancel',()=>{drag=null;});
  header.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();const r=panel.getBoundingClientRect();move(r.left+(e.key==='ArrowRight'?20:e.key==='ArrowLeft'?-20:0),r.top+(e.key==='ArrowDown'?20:e.key==='ArrowUp'?-20:0));});
  window.addEventListener('resize',()=>{if(!panel.hidden){const r=panel.getBoundingClientRect();move(r.left,r.top);}});
}
setupWorkflowGuide();

// 2026-10-05:启动时先建立登录态 —— 没有 token 直接进登录页,
// 有 token 先 /auth/me 校验,避免用过期 token 猛打 401。
(async function bootstrap() {
  authToken = readToken();
  renderAuthActor();
  if (!authToken) {
    renderAuthGate();
    return;
  }
  try {
    const me = await verifyToken(authToken);
    writeActor({ id: me.id, name: me.name, business_role: me.business_role });
    await loadView("overview");
  } catch (error) {
    writeToken("");
    writeActor(null);
    renderAuthGate(error.message || "登录已失效,请重新登录");
  }
})();
