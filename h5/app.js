const app = document.querySelector("#app");
const toastEl = document.querySelector("#toast");

const categoryOptions = [
  ["appliance", "家电维修", "空调、冰箱、洗衣机等"],
  ["plumbing", "水路管道", "漏水、堵塞、水龙头"],
  ["electrical", "电路照明", "跳闸、灯具、开关"],
  ["door_window", "门窗维修", "门锁、窗户、合页"],
  ["furniture_install", "家具安装", "柜体、床、桌椅安装"],
  ["appliance_install", "家电安装", "热水器、烟机、净水器"],
  ["pipe_dredge", "管道疏通", "下水道、地漏、马桶"],
  ["other", "其他服务", "无法归类的问题"],
];

const statusText = {
  created: "已创建",
  store_pending: "门店待接",
  store_accepted: "门店已接",
  dispatched: "已派单",
  assigned: "已指派",
  repairer_accepted: "师傅已接",
  accepted: "已接单",
  servicing: "服务中",
  bill_submitted: "服务单待确认",
  bill_returned: "服务单退回",
  wait_payment: "待支付",
  paid: "已支付",
  paid_pending_review: "待门店审核",
  store_reviewed: "门店已审核",
  completed: "已完成",
  cancelled: "已取消",
  pending: "待处理",
  in_progress: "进行中",
};

const roleText = {
  customer: "客户端",
  repairer: "师傅端",
  store_manager: "门店店长",
  second_receiver: "二接师傅",
  promotion_manager: "推广经理",
  city_manager: "城市经理",
  tech_support: "服务保障",
  finance: "财务",
  platform_admin: "平台管理",
  admin: "平台管理",
};

const tabs = {
  customer: [
    ["home", "首页"],
    ["orders", "订单"],
    ["domestic", "月嫂保姆"],
    ["warranties", "保修凭证"],
    ["addresses", "地址簿"],
    ["packages", "套餐"],
    ["support", "客服"],
    ["wallet", "我的"],
  ],
  repairer: [
    ["jobs", "接单"],
    ["workbench", "工单"],
    ["earnings", "收入"],
    ["repairerProfile", "资料"],
    ["proxyOrders", "代客下单"],
  ],
  admin: [
    ["overview", "概览"],
    ["adminOrders", "订单"],
    ["adminUsers", "用户"],
    ["adminRepairers", "师傅"],
    ["adminStores", "门店"],
    ["adminPackages", "套餐"],
    ["adminFinance", "财务"],
    ["adminSupport", "客服"],
    ["adminAlerts", "告警"],
    ["proxyOrders", "代客订单"],
    ["domestic", "家政服务"],
    ["payroll", "工资"],
    ["warranties", "保修凭证"],
  ],
};

tabs.second_receiver = tabs.repairer;
tabs.store_manager = [
  ["overview", "门店概览"], ["adminOrders", "订单"], ["proxyOrders", "代客订单"],
  ["domestic", "家政服务"], ["adminRepairers", "人员"], ["payroll", "工资"],
  ["adminFinance", "收益"], ["adminSupport", "售后"],
];
tabs.city_manager = [
  ["overview", "城市概览"], ["adminOrders", "订单"], ["adminStores", "门店"],
  ["domestic", "家政服务"], ["adminFinance", "财务"], ["adminAlerts", "风险"],
];
tabs.promotion_manager = [
  ["proxyOrders", "代客下单"], ["orders", "关联订单"], ["earnings", "推广收益"],
];
tabs.tech_support = [["domestic", "服务保障"], ["adminSupport", "投诉售后"], ["adminOrders", "服务订单"]];
tabs.finance = [["adminFinance", "资金"], ["payroll", "工资"], ["adminOrders", "订单"], ["adminAlerts", "对账"]];
tabs.platform_admin = tabs.admin;

const state = {
  token: localStorage.getItem("h5_token") || "",
  user: JSON.parse(localStorage.getItem("h5_user") || "null"),
  viewRole: localStorage.getItem("h5_view_role") || "",
  tab: localStorage.getItem("h5_tab") || "",
  selectedCategory: "plumbing",
  loading: false,
  cache: {},
};

function currentRole() {
  return state.user?.business_role || state.user?.role || "customer";
}

function currentTabs() {
  return tabs[currentRole()] || tabs.customer;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function money(value) {
  return `¥${Number(value || 0).toFixed(2)}`;
}

function dateText(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function badge(status) {
  const color = {
    completed: "green",
    paid: "green",
    store_reviewed: "green",
    store_accepted: "blue",
    dispatched: "blue",
    assigned: "blue",
    repairer_accepted: "blue",
    accepted: "blue",
    servicing: "blue",
    wait_payment: "yellow",
    bill_submitted: "yellow",
    paid_pending_review: "yellow",
    store_pending: "yellow",
    cancelled: "red",
    rejected: "red",
    mismatch: "red",
    critical: "red",
    open: "yellow",
    replied: "blue",
    closed: "green",
    approved: "green",
    pending: "yellow",
  }[status] || "";
  return `<span class="badge ${color}">${escapeHtml(statusText[status] || status || "-")}</span>`;
}

function toast(message, type = "") {
  toastEl.textContent = message;
  toastEl.className = `toast ${type}`.trim();
  toastEl.hidden = false;
  clearTimeout(toastEl._timer);
  toastEl._timer = setTimeout(() => {
    toastEl.hidden = true;
  }, 2600);
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(path, {
    ...options,
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const message = data?.detail || data?.error || `请求失败(${res.status})`;
    throw new Error(message);
  }
  return data;
}

async function safeList(path) {
  try {
    return await api(path);
  } catch {
    return [];
  }
}

function saveSession(token, user) {
  state.token = token;
  state.user = user;
  state.viewRole = user.business_role || user.role;
  localStorage.setItem("h5_token", token);
  localStorage.setItem("h5_user", JSON.stringify(user));
  localStorage.setItem("h5_view_role", state.viewRole);
}

function clearSession() {
  localStorage.removeItem("h5_token");
  localStorage.removeItem("h5_user");
  localStorage.removeItem("h5_view_role");
  localStorage.removeItem("h5_tab");
  state.token = "";
  state.user = null;
  state.viewRole = "";
  state.tab = "";
  state.cache = {};
  render();
}

function ensureTab() {
  const available = currentTabs();
  if (!available.some(([key]) => key === state.tab)) {
    state.tab = available[0][0];
  }
  localStorage.setItem("h5_tab", state.tab);
}

async function navigate(tab) {
  state.tab = tab;
  localStorage.setItem("h5_tab", tab);
  await refresh();
}

async function refresh() {
  if (!state.user) {
    render();
    return;
  }
  ensureTab();
  state.loading = true;
  render();
  try {
    await loadCurrent();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    state.loading = false;
    render();
  }
}

async function loadCurrent() {
  const role = currentRole();
  const tab = state.tab;
  if (["customer", "promotion_manager"].includes(role)) {
    if (["domestic", "warranties", "addresses", "proxyOrders", "earnings"].includes(tab)) {
      await loadBusiness(tab);
      return;
    }
    await loadCustomer(tab);
  } else if (["repairer", "second_receiver"].includes(role)) {
    if (tab === "proxyOrders") { await loadBusiness(tab); return; }
    await loadRepairer(tab);
  } else {
    if (["domestic", "warranties", "addresses", "proxyOrders", "payroll"].includes(tab)) {
      await loadBusiness(tab);
      return;
    }
    await loadAdmin(tab);
  }
}

async function loadBusiness(tab) {
  if (tab === "domestic") {
    const [workers, demands, contracts, stores, regions] = await Promise.all([
      safeList("/api/v1/business/domestic/workers?active=true"),
      safeList("/api/v1/business/domestic/demands"),
      safeList("/api/v1/business/domestic/contracts"),
      safeList("/api/v1/stores"),
      safeList("/api/v1/regions"),
    ]);
    Object.assign(state.cache, { domesticWorkers: workers, domesticDemands: demands, domesticContracts: contracts, stores, regions });
  }
  if (tab === "proxyOrders") state.cache.proxyOrders = await safeList("/api/v1/orders?is_proxy_order=true&limit=100");
  if (tab === "payroll") {
    const [wages, payroll] = await Promise.all([
      safeList("/api/v1/business/wages"),
      api("/api/v1/business/payroll").catch(() => ({ periods: [], items: [] })),
    ]);
    Object.assign(state.cache, { wages, payroll });
  }
  if (tab === "warranties") state.cache.warranties = await safeList(`/api/v1/business/warranties?customer_id=${state.user.id}`);
  if (tab === "addresses") state.cache.addresses = await safeList(`/api/v1/business/addresses?user_id=${state.user.id}`);
  if (tab === "earnings") await loadWallet(state.user.id);
}

async function loadCommonLists() {
  const [regions, stores] = await Promise.all([
    safeList("/api/v1/regions"),
    safeList("/api/v1/stores"),
  ]);
  state.cache.regions = regions;
  state.cache.stores = stores;
}

async function loadCustomer(tab) {
  if (tab === "home") {
    const [orders, serviceAddresses] = await Promise.all([
      safeList(`/api/v1/orders?customer_id=${state.user.id}&limit=5`),
      safeList("/api/v1/stores/addresses?enabled=true"),
    ]);
    state.cache.customerRecentOrders = orders;
    state.cache.serviceAddresses = serviceAddresses;
  }
  if (tab === "orders") {
    state.cache.customerOrders = await safeList(
      `/api/v1/orders?customer_id=${state.user.id}&limit=80`,
    );
  }
  if (tab === "packages") {
    const [packages, mine, stores] = await Promise.all([
      safeList("/api/v1/service-packages"),
      safeList(`/api/v1/service-packages/customer?user_id=${state.user.id}`),
      safeList("/api/v1/stores"),
    ]);
    state.cache.packages = packages;
    state.cache.customerPackages = mine;
    state.cache.stores = stores;
  }
  if (tab === "support") {
    const [tickets, stores, orders] = await Promise.all([
      safeList(`/api/v1/support/tickets?user_id=${state.user.id}`),
      safeList("/api/v1/stores"),
      safeList(`/api/v1/orders?customer_id=${state.user.id}&limit=50`),
    ]);
    state.cache.supportTickets = tickets;
    state.cache.stores = stores;
    state.cache.customerOrders = orders;
  }
  if (tab === "wallet") {
    await loadWallet(state.user.id);
  }
}

async function loadRepairer(tab) {
  await ensureRepairerProfile();
  if (tab === "jobs") {
    const repairer = state.cache.myRepairer;
    const [assigned, dispatched] = await Promise.all([
      safeList(`/api/v1/orders?assigned_repairer_id=${repairer?.id || 0}&status=assigned&limit=50`),
      safeList(`/api/v1/orders?assigned_repairer_id=${repairer?.id || 0}&status=dispatched&limit=50`),
    ]);
    state.cache.availableJobs = [...assigned, ...dispatched];
  }
  if (tab === "workbench") {
    const repairer = state.cache.myRepairer;
    const statuses = ["repairer_accepted", "accepted", "servicing", "bill_submitted", "bill_returned", "wait_payment", "paid"];
    const groups = await Promise.all(
      statuses.map((s) => safeList(`/api/v1/orders?repairer_id=${repairer?.id || 0}&status=${s}&limit=50`)),
    );
    state.cache.myJobs = groups.flat();
  }
  if (tab === "earnings") {
    await loadWallet(state.user.id);
    state.cache.myProfits = await safeList(`/api/v1/finance/profit/user/${state.user.id}`);
  }
  if (tab === "repairerProfile") {
    await loadCommonLists();
  }
}

async function loadAdmin(tab) {
  if (tab === "overview") {
    const [metrics, orders, users, repairers, alerts] = await Promise.all([
      api("/metrics").catch(() => ({})),
      safeList("/api/v1/orders?limit=10"),
      safeList("/api/v1/users?limit=10"),
      safeList("/api/v1/repairers?limit=10"),
      safeList("/api/v1/admin/alerts?resolved=false&limit=10"),
    ]);
    Object.assign(state.cache, { metrics, adminOrders: orders, users, repairers, alerts });
  }
  if (tab === "adminOrders") {
    const [orders, repairers, stores] = await Promise.all([
      safeList("/api/v1/orders?limit=100"),
      safeList("/api/v1/repairers?limit=100"),
      safeList("/api/v1/stores"),
    ]);
    Object.assign(state.cache, { adminOrders: orders, repairers, stores });
  }
  if (tab === "adminUsers") {
    state.cache.users = await safeList("/api/v1/users?limit=100");
  }
  if (tab === "adminRepairers") {
    const [repairers, users, regions] = await Promise.all([
      safeList("/api/v1/repairers?limit=100"),
      safeList("/api/v1/users?limit=100"),
      safeList("/api/v1/regions"),
    ]);
    Object.assign(state.cache, { repairers, users, regions });
  }
  if (tab === "adminStores") {
    const [stores, addresses, users, repairers, regions] = await Promise.all([
      safeList("/api/v1/stores"),
      safeList("/api/v1/stores/addresses"),
      safeList("/api/v1/users?limit=100"),
      safeList("/api/v1/repairers?limit=100"),
      safeList("/api/v1/regions"),
    ]);
    Object.assign(state.cache, { stores, addresses, users, repairers, regions });
  }
  if (tab === "adminPackages") {
    const [packages, customerPackages, schedules, stores] = await Promise.all([
      safeList("/api/v1/service-packages"),
      safeList("/api/v1/service-packages/customer"),
      safeList("/api/v1/service-packages/schedules"),
      safeList("/api/v1/stores"),
    ]);
    Object.assign(state.cache, { packages, customerPackages, schedules, stores });
  }
  if (tab === "adminFinance") {
    const [payments, withdrawals, logs] = await Promise.all([
      safeList("/api/v1/payment/list?limit=100"),
      safeList("/api/v1/wallet/withdrawals?limit=100"),
      safeList("/api/v1/admin/reconcile/logs?limit=30"),
    ]);
    Object.assign(state.cache, { payments, withdrawals, reconcileLogs: logs });
  }
  if (tab === "adminSupport") {
    const [tickets, users] = await Promise.all([
      safeList("/api/v1/support/tickets"),
      safeList("/api/v1/users?limit=100"),
    ]);
    Object.assign(state.cache, { supportTickets: tickets, users });
  }
  if (tab === "adminAlerts") {
    state.cache.alerts = await safeList("/api/v1/admin/alerts?limit=100");
  }
}

async function loadWallet(userId) {
  const [wallet, ledger, withdrawals] = await Promise.all([
    api(`/api/v1/wallet/balance/${userId}`).catch(() => null),
    safeList(`/api/v1/wallet/ledger/${userId}?limit=80`),
    safeList(`/api/v1/wallet/withdrawals?user_id=${userId}&limit=50`),
  ]);
  Object.assign(state.cache, { wallet, ledger, withdrawals });
}

async function ensureRepairerProfile() {
  const [repairers, regions] = await Promise.all([
    safeList("/api/v1/repairers?limit=100"),
    safeList("/api/v1/regions"),
  ]);
  state.cache.repairers = repairers;
  state.cache.regions = regions;
  state.cache.myRepairer = repairers.find((item) => item.user_id === state.user.id) || null;
}

function renderLogin() {
  app.innerHTML = `
    <main class="login-page">
      <div class="login-bg" aria-hidden="true">
        <div class="login-bg-blob login-bg-blob-1"></div>
        <div class="login-bg-blob login-bg-blob-2"></div>
        <div class="login-bg-blob login-bg-blob-3"></div>
        <div class="login-bg-grid"></div>
      </div>

      <section class="login-shell">
        <!-- 左侧品牌区(PC/平板展示) -->
        <aside class="login-brand" aria-label="品牌介绍">
          <div class="login-brand-top">
            <div class="brand">
              <div class="brand-mark"><img src="./assets/logo-mark.png" alt="立即修"></div>
              <div>
                <h1>立即修</h1>
                <p>厦门 · 上门维修领导品牌</p>
              </div>
            </div>
          </div>

          <div class="login-brand-hero">
            <h2>厦门的家,<span class="hl">一个电话</span><br/>30 分钟就有师傅上门</h2>
            <p class="login-brand-sub">
              家电 · 水电 · 门窗 · 家具 · 管道疏通 · 家电清洗,
              <br/>明码标价 · 持证师傅 · 原厂配件 · 7 天质保。
            </p>
          </div>

          <div class="login-stats" role="list">
            <div class="login-stat" role="listitem">
              <strong>30<small>分钟</small></strong>
              <span>平均响应时间</span>
            </div>
            <div class="login-stat" role="listitem">
              <strong>168<small>+位</small></strong>
              <span>认证师傅</span>
            </div>
            <div class="login-stat" role="listitem">
              <strong>4.98<small>/5</small></strong>
              <span>客户好评</span>
            </div>
          </div>

          <ul class="login-trust" aria-label="服务承诺">
            <li><span class="dot"></span>明码标价,无任何隐形消费</li>
            <li><span class="dot"></span>百万平台责任险,维修更安心</li>
            <li><span class="dot"></span>原厂配件,7 天无理由返修</li>
            <li><span class="dot"></span>全程留痕,服务节点实时通知</li>
          </ul>

          <div class="login-brand-foot">
            <span class="login-brand-chip">已为 <em>2,800+</em> 厦门家庭解决维修难题</span>
          </div>
        </aside>

        <!-- 右侧登录表单 -->
        <section class="login-panel" aria-label="登录">
          <div class="login-panel-head">
            <div class="login-panel-mark">
              <img src="./assets/logo-mark.png" alt="" />
            </div>
            <div>
              <h3>欢迎回来</h3>
              <p>登录后进入您的工作台</p>
            </div>
          </div>

          <div class="login-tabs" role="tablist">
            <button type="button" class="login-tab active" data-login-tab="phone" role="tab" aria-selected="true">
              <span class="ico" aria-hidden="true">📱</span>手机号登录
            </button>
            <button type="button" class="login-tab" data-login-tab="wechat" role="tab" aria-selected="false">
              <span class="ico" aria-hidden="true">💬</span>微信一键登录
            </button>
          </div>

          <form data-form="login" class="login-form" data-login-mode="phone">
            <input type="hidden" name="role" value="customer" />

            <!-- 手机号登录面板 -->
            <div class="login-pane" data-login-pane="phone">
              <div class="field">
                <label>手机号</label>
                <div class="input-wrap">
                  <span class="input-prefix">+86</span>
                  <input name="phone" inputmode="tel" autocomplete="tel" maxlength="20" value="13800138000" required />
                </div>
              </div>
              <div class="field">
                <label>姓名</label>
                <div class="input-wrap">
                  <input name="name" autocomplete="name" maxlength="50" value="测试用户" required />
                </div>
              </div>
              <div class="field">
                <label>验证码</label>
                <div class="input-wrap">
                  <input name="sms_code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="请输入短信验证码" required />
                  <button type="button" class="input-action" data-action="requestSms">获取验证码</button>
                </div>
              </div>
            </div>

            <!-- 微信登录面板 -->
            <div class="login-pane" data-login-pane="wechat" hidden>
              <div class="wechat-card">
                <div class="wechat-illu" aria-hidden="true">
                  <div class="wechat-illu-bg"></div>
                  <div class="wechat-illu-icon">💬</div>
                </div>
                <h4>微信扫码 / 授权登录</h4>
                <p>使用微信扫一扫,2 秒进入工作台</p>
                <button type="button" class="wechat-btn" data-action="wechatLogin" disabled>
                  <span class="wx-ico" aria-hidden="true">🟢</span>
                  微信一键登录(开发中)
                </button>
                <span class="wechat-hint">线上环境配置微信开放平台参数后即可启用</span>
              </div>
            </div>

            <label class="agreement-check">
              <input type="checkbox" name="agreed_terms" required />
              <span>我已阅读并同意
                <a href="./legal/user-agreement.html" target="_blank" rel="noopener">《用户服务协议》</a>
                和
                <a href="./legal/privacy-policy.html" target="_blank" rel="noopener">《隐私政策》</a>
              </span>
            </label>

            <button class="primary login-submit" type="submit">进入工作台</button>
          </form>

          <div class="login-divider"><span>没有账号?直接体验</span></div>

          <div class="demo-strip" role="group" aria-label="演示角色">
            <button type="button" data-demo-login="18800000001|演示客户|customer">
              <span class="demo-emoji" aria-hidden="true">👤</span>
              <span class="demo-text"><strong>客户</strong><small>下单 · 评价</small></span>
            </button>
            <button type="button" data-demo-login="18800000002|演示师傅张工|repairer">
              <span class="demo-emoji" aria-hidden="true">🛠️</span>
              <span class="demo-text"><strong>师傅</strong><small>接单 · 提交</small></span>
            </button>
            <button type="button" data-demo-login="18800000000|演示管理员|admin">
              <span class="demo-emoji" aria-hidden="true">⚙️</span>
              <span class="demo-text"><strong>管理</strong><small>运营 · 财务</small></span>
            </button>
          </div>
        </section>
      </section>
    </main>
  `;
}

function render() {
  if (!state.user) {
    renderLogin();
    return;
  }
  ensureTab();
  const role = currentRole();
  const navItems = currentTabs();
  const title = navItems.find(([key]) => key === state.tab)?.[1] || roleText[role];
  app.innerHTML = `
    <div class="layout role-${role}">
      <aside class="sidebar">
        <div class="brand">
          <div class="brand-mark"><img src="./assets/logo-mark.png" alt="立即修"></div>
          <div>
            <h1>立即修</h1>
            <p>${roleText[role]}工作台</p>
          </div>
        </div>
        <nav class="nav">
          ${navItems.map(([key, label]) => navButton(key, label)).join("")}
        </nav>
        <div class="sidebar-footer">
          ${roleSwitchHtml()}
          <div class="user-line">${escapeHtml(state.user.name)} · ${escapeHtml(state.user.phone || "")}</div>
          <button class="secondary" data-action="logout">退出登录</button>
        </div>
      </aside>
      <main class="main">
        <header class="topbar">
          <div>
            <h2>${title}</h2>
            <p><span class="role-chip">${roleText[role]}</span>${state.loading ? " 正在同步数据" : " 今日工作台"}</p>
          </div>
          <div class="actions">
            ${roleSwitchHtml(true)}
            <button class="secondary" data-action="refresh">刷新</button>
          </div>
        </header>
        <section class="content">${renderContent(role)}</section>
      </main>
      ${mobileNav(navItems)}
    </div>
  `;
}

function navButton(key, label) {
  return `<button data-tab="${key}" class="${state.tab === key ? "active" : ""}">${label}</button>`;
}

function mobileNav(items) {
  const primaryItems = items.slice(0, 4);
  const moreItems = items.slice(4);
  const moreActive = moreItems.some(([key]) => key === state.tab);
  return `
    <nav class="mobile-nav" aria-label="主要功能">
      ${primaryItems.map(([key, label]) => navButton(key, label)).join("")}
      ${moreItems.length ? `
        <details class="mobile-more">
          <summary class="${moreActive ? "active" : ""}"><span aria-hidden="true">•••</span>更多</summary>
          <div class="mobile-more-menu">
            ${moreItems.map(([key, label]) => navButton(key, label)).join("")}
          </div>
        </details>
      ` : ""}
    </nav>
  `;
}

function roleSwitchHtml(compact = false) {
  return "";
}

function renderContent(role) {
  if (["domestic", "warranties", "addresses", "proxyOrders", "payroll"].includes(state.tab)) return renderBusiness();
  if (["customer", "promotion_manager"].includes(role)) return state.tab === "earnings" ? walletPanel(state.user.id) : renderCustomer();
  if (["repairer", "second_receiver"].includes(role)) return renderRepairer();
  return renderAdmin();
}

function renderCustomer() {
  if (state.tab === "home") return customerHome();
  if (state.tab === "orders") return customerOrders();
  if (state.tab === "packages") return customerPackages();
  if (state.tab === "support") return supportCenter(false);
  if (state.tab === "wallet") return walletPanel(state.user.id, true);
  if (state.tab === "earnings") return walletPanel(state.user.id);
  return empty("请选择页面");
}

function customerHome() {
  const serviceAddresses = state.cache.serviceAddresses || [];
  const recent = state.cache.customerRecentOrders || [];
  return `
    <div class="split">
      <div class="stack">
        <section class="panel">
          <div class="card-head">
            <div>
              <h3 class="card-title">快速报修</h3>
              <p class="small">选择服务类型后提交地址和问题描述</p>
            </div>
          </div>
          <div class="quick-cats">
            ${categoryOptions
              .map(
                ([id, name, desc]) => `
                  <button data-category="${id}" class="${state.selectedCategory === id ? "active" : ""}">
                    <strong>${name}</strong><span>${desc}</span>
                  </button>
                `,
              )
              .join("")}
          </div>
          <form class="form-grid" data-form="createOrder" style="margin-top:16px">
            <input type="hidden" name="category" value="${state.selectedCategory}" />
            <div class="field wide">
              <label>标准上门地址</label>
              <select name="address_book_id" required>
                <option value="">请选择平台已开通地址</option>
                ${serviceAddresses.map((item) => `<option value="${item.id}">${escapeHtml(item.full_address)} · ${escapeHtml(item.address_code)}</option>`).join("")}
              </select>
              <span class="small">订单区域、门店和业务归属由唯一地址编号确定</span>
            </div>
            <div class="field wide">
              <label>问题描述</label>
              <textarea name="description" maxlength="2000" required placeholder="例如：厨房水龙头持续漏水，需要尽快上门"></textarea>
            </div>
            <div class="field">
              <label>联系电话</label>
              <input name="contact_phone" inputmode="tel" value="${escapeHtml(state.user.phone || "")}" />
            </div>
            <div class="field">
              <label>预约时间</label>
              <input name="scheduled_time" type="datetime-local" />
            </div>
            <div class="wide">
              <button class="primary" type="submit" ${serviceAddresses.length ? "" : "disabled"}>${serviceAddresses.length ? "提交订单" : "暂无已开通地址"}</button>
            </div>
          </form>
        </section>
      </div>
      <aside class="stack">
        <section class="panel">
          <div class="card-head">
            <h3 class="card-title">最近订单</h3>
            <button class="link-btn" data-tab="orders">全部订单</button>
          </div>
          ${recent.length ? recent.map(orderCard).join("") : empty("暂无订单", false)}
        </section>
      </aside>
    </div>
  `;
}

function customerOrders() {
  const orders = state.cache.customerOrders || [];
  return `
    <div class="toolbar">
      <div>
        <h3 class="card-title">我的订单</h3>
        <p class="small">查看进度、支付费用、完成后评价</p>
      </div>
      <button class="primary" data-tab="home">去下单</button>
    </div>
    ${orders.length ? `<div class="grid two">${orders.map(orderCard).join("")}</div>` : empty("还没有订单")}
  `;
}

function orderCard(order) {
  return `
    <article class="card">
      <div class="card-head">
        <strong>${categoryLabel(order.category)}</strong>
        ${badge(order.status)}
      </div>
      <p class="card-desc">${escapeHtml(order.description)}</p>
      <p class="small">${escapeHtml(order.address)}</p>
      <div class="metric-row">
        <span class="muted">订单 #${order.id}</span>
        <strong>${money(order.price)}</strong>
      </div>
      <div class="actions" style="margin-top:12px">
        ${order.status === "wait_payment" && Number(order.price) > 0 ? `<button class="primary" data-action="payOrder" data-id="${order.id}" data-amount="${order.price}">支付</button>` : ""}
        ${["completed", "paid", "store_reviewed"].includes(order.status) ? `<button class="secondary" data-action="rateOrder" data-id="${order.id}">评价</button>` : ""}
      </div>
    </article>
  `;
}

function customerPackages() {
  const packages = state.cache.packages || [];
  const mine = state.cache.customerPackages || [];
  const stores = state.cache.stores || [];
  return `
    <div class="grid two">
      <section class="panel">
        <h3 class="card-title">服务套餐</h3>
        <div class="stack" style="margin-top:14px">
          ${
            packages.length
              ? packages.map((pkg) => packageCard(pkg, stores)).join("")
              : empty("暂无可购买套餐", false)
          }
        </div>
      </section>
      <section class="panel">
        <h3 class="card-title">我的套餐</h3>
        <div class="stack" style="margin-top:14px">
          ${
            mine.length
              ? mine.map(
                  (item) => `
                    <article class="card">
                      <div class="card-head">
                        <strong>套餐 #${item.package_id}</strong>
                        ${badge(item.status)}
                      </div>
                      <p class="small">${escapeHtml(item.address)}</p>
                      <p class="small">有效期 ${item.start_date} 至 ${item.end_date}</p>
                      <strong>${item.used_times}/${item.total_times} 次已使用</strong>
                    </article>
                  `,
                ).join("")
              : empty("还没有购买套餐", false)
          }
        </div>
      </section>
    </div>
  `;
}

function packageCard(pkg, stores) {
  return `
    <article class="card">
      <div class="card-head">
        <strong>${escapeHtml(pkg.name)}</strong>
        <strong>${money(pkg.price)}</strong>
      </div>
      <p class="card-desc">${escapeHtml(pkg.description || "年度维护服务")}</p>
      <p class="small">${pkg.service_years} 年 · 每年 ${pkg.annual_times} 次 · ${pkg.device_count} 台设备</p>
      <form class="form-grid" data-form="buyPackage" style="margin-top:12px">
        <input type="hidden" name="package_id" value="${pkg.id}" />
        <div class="field">
          <label>服务门店</label>
          <select name="store_id" required>${stores.map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join("")}</select>
        </div>
        <div class="field">
          <label>开始日期</label>
          <input type="date" name="start_date" value="${todayISO()}" required />
        </div>
        <div class="field wide">
          <label>服务地址</label>
          <input name="address" required placeholder="套餐服务地址" />
        </div>
        <div class="field">
          <label>联系电话</label>
          <input name="contact_phone" value="${escapeHtml(state.user.phone || "")}" required />
        </div>
        <div class="field">
          <label>&nbsp;</label>
          <button class="primary" type="submit">购买套餐</button>
        </div>
      </form>
    </article>
  `;
}

function supportCenter(isAdmin) {
  const tickets = state.cache.supportTickets || [];
  const stores = state.cache.stores || [];
  const orders = state.cache.customerOrders || [];
  return `
    <div class="split">
      ${
        isAdmin
          ? ""
          : `
            <section class="panel">
              <h3 class="card-title">提交客服工单</h3>
              <form class="form-grid" data-form="createSupport" style="margin-top:14px">
                <div class="field">
                  <label>门店</label>
                  <select name="store_id" required>${stores.map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join("")}</select>
                </div>
                <div class="field">
                  <label>关联订单</label>
                  <select name="order_id">
                    <option value="">不关联</option>
                    ${orders.map((o) => `<option value="${o.id}">#${o.id} ${categoryLabel(o.category)}</option>`).join("")}
                  </select>
                </div>
                <div class="field">
                  <label>问题类型</label>
                  <select name="category">
                    <option value="general">通用咨询</option>
                    <option value="order">订单问题</option>
                    <option value="payment">支付/退款</option>
                    <option value="after_sales">售后服务</option>
                  </select>
                </div>
                <div class="field">
                  <label>标题</label>
                  <input name="title" maxlength="120" required />
                </div>
                <div class="field wide">
                  <label>内容</label>
                  <textarea name="content" required></textarea>
                </div>
                <div class="wide"><button class="primary" type="submit">提交工单</button></div>
              </form>
            </section>
          `
      }
      <section class="panel">
        <h3 class="card-title">${isAdmin ? "客服工单" : "我的工单"}</h3>
        <div class="stack" style="margin-top:14px">
          ${tickets.length ? tickets.map((ticket) => ticketCard(ticket, isAdmin)).join("") : empty("暂无客服工单", false)}
        </div>
      </section>
    </div>
  `;
}

function ticketCard(ticket, isAdmin) {
  return `
    <article class="card">
      <div class="card-head">
        <strong>#${ticket.id} ${escapeHtml(ticket.title)}</strong>
        ${badge(ticket.status)}
      </div>
      <p class="card-desc">${escapeHtml(ticket.content)}</p>
      <p class="small">门店 #${ticket.store_id} · 用户 #${ticket.user_id} · ${dateText(ticket.created_at)}</p>
      ${
        isAdmin
          ? `
            <form class="form-grid" data-form="replySupport" style="margin-top:12px">
              <input type="hidden" name="ticket_id" value="${ticket.id}" />
              <div class="field wide">
                <label>回复内容</label>
                <input name="content" required placeholder="输入客服回复" />
              </div>
              <label class="small"><input type="checkbox" name="close" /> 回复后关闭</label>
              <button class="secondary" type="submit">回复</button>
            </form>
          `
          : ""
      }
    </article>
  `;
}

function walletPanel(userId, customerMode = false) {
  const wallet = state.cache.wallet;
  const ledger = state.cache.ledger || [];
  const withdrawals = state.cache.withdrawals || [];
  return `
    <div class="grid two">
      <section class="panel">
        <h3 class="card-title">${customerMode ? "我的钱包" : "收入钱包"}</h3>
        <div class="grid three" style="margin-top:14px">
          <div class="metric"><span class="muted">可提现</span><strong>${money(wallet?.available_balance)}</strong></div>
          <div class="metric"><span class="muted">累计收入</span><strong>${money(wallet?.total_income)}</strong></div>
          <div class="metric"><span class="muted">冻结金额</span><strong>${money(wallet?.frozen_balance)}</strong></div>
        </div>
        <form class="form-grid" data-form="withdraw" style="margin-top:16px">
          <input type="hidden" name="user_id" value="${userId}" />
          <div class="field">
            <label>提现金额</label>
            <input name="amount" inputmode="decimal" required placeholder="0.00" />
          </div>
          <div class="field">
            <label>备注</label>
            <input name="remark" placeholder="选填" />
          </div>
          <button class="primary" type="submit">申请提现</button>
        </form>
      </section>
      <section class="panel">
        <h3 class="card-title">提现记录</h3>
        ${withdrawals.length ? table(["编号", "金额", "状态", "时间"], withdrawals.map((w) => [w.id, money(w.amount), badge(w.status), dateText(w.created_at)])) : empty("暂无提现记录", false)}
      </section>
    </div>
    <section class="panel" style="margin-top:16px">
      <h3 class="card-title">资金流水</h3>
      ${ledger.length ? table(["编号", "类型", "金额", "余额", "备注", "时间"], ledger.map((l) => [l.id, l.type, money(l.amount), money(l.balance_after), escapeHtml(l.remark || ""), dateText(l.created_at)])) : empty("暂无流水", false)}
    </section>
  `;
}

function renderRepairer() {
  const repairer = state.cache.myRepairer;
  if (!repairer && state.tab !== "repairerProfile") {
    return repairerProfile(true);
  }
  if (state.tab === "jobs") return repairerJobs();
  if (state.tab === "workbench") return repairerWorkbench();
  if (state.tab === "earnings") return repairerEarnings();
  if (state.tab === "repairerProfile") return repairerProfile(false);
  return empty("请选择页面");
}

function repairerProfile(forceCreate) {
  const repairer = state.cache.myRepairer;
  const regions = state.cache.regions || [];
  if (repairer && !forceCreate) {
    return `
      <div class="grid two">
        <section class="panel">
          <div class="card-head">
            <h3 class="card-title">师傅资料</h3>
            ${badge(repairer.status)}
          </div>
          <p class="card-desc">${escapeHtml(repairer.intro || "暂无简介")}</p>
          <div class="grid three" style="margin-top:14px">
            <div class="metric"><span class="muted">评分</span><strong>${repairer.rating}</strong></div>
            <div class="metric"><span class="muted">完成单</span><strong>${repairer.order_count}</strong></div>
            <div class="metric"><span class="muted">认证</span><strong>${repairer.id_verified ? "已认证" : "待认证"}</strong></div>
          </div>
          <form class="form-grid" data-form="updateRepairerProfile" style="margin-top:16px">
            <input type="hidden" name="repairer_id" value="${repairer.id}" />
            <div class="field">
              <label>技能标签</label>
              <input name="skills" value="${escapeHtml(repairer.skills)}" required />
            </div>
            <div class="field">
              <label>接单状态</label>
              <select name="status">
                ${["online", "offline", "busy"].map((s) => `<option value="${s}" ${repairer.status === s ? "selected" : ""}>${s}</option>`).join("")}
              </select>
            </div>
            <div class="field">
              <label>服务区域</label>
              <select name="region_id">
                <option value="">暂不指定</option>
                ${regions.map((r) => `<option value="${r.id}" ${repairer.region_id === r.id ? "selected" : ""}>${escapeHtml(r.name)}</option>`).join("")}
              </select>
            </div>
            <div class="field wide">
              <label>个人简介</label>
              <textarea name="intro">${escapeHtml(repairer.intro || "")}</textarea>
            </div>
            <button class="primary" type="submit">保存资料</button>
          </form>
        </section>
      </div>
    `;
  }
  return `
    <section class="panel">
      <h3 class="card-title">完善师傅资料</h3>
      <p class="small">当前账号还没有师傅档案，创建后即可接收派单。</p>
      <form class="form-grid" data-form="createRepairerProfile" style="margin-top:16px">
        <div class="field">
          <label>技能标签</label>
          <input name="skills" value="水电维修,家电维修" required />
        </div>
        <div class="field">
          <label>服务区域</label>
          <select name="region_id">
            <option value="">暂不指定</option>
            ${regions.map((r) => `<option value="${r.id}">${escapeHtml(r.name)}</option>`).join("")}
          </select>
        </div>
        <div class="field wide">
          <label>个人简介</label>
          <textarea name="intro" placeholder="例如：5 年家电维修经验，擅长水电和厨卫维修"></textarea>
        </div>
        <button class="primary" type="submit">创建师傅档案</button>
      </form>
    </section>
  `;
}

function repairerJobs() {
  const jobs = state.cache.availableJobs || [];
  return `
    <div class="toolbar">
      <div>
        <h3 class="card-title">待接工单</h3>
        <p class="small">显示指派给当前师傅的待接订单</p>
      </div>
    </div>
    ${jobs.length ? `<div class="grid two">${jobs.map((order) => repairerOrderCard(order, "available")).join("")}</div>` : empty("暂无待接工单")}
  `;
}

function repairerWorkbench() {
  const jobs = state.cache.myJobs || [];
  return `
    <div class="toolbar">
      <div>
        <h3 class="card-title">我的工单</h3>
        <p class="small">接单、开始服务、提交服务单和跟进支付</p>
      </div>
    </div>
    ${jobs.length ? `<div class="grid two">${jobs.map((order) => repairerOrderCard(order, "mine")).join("")}</div>` : empty("暂无进行中工单")}
  `;
}

function repairerOrderCard(order, mode) {
  return `
    <article class="card">
      <div class="card-head">
        <strong>#${order.id} ${categoryLabel(order.category)}</strong>
        ${badge(order.status)}
      </div>
      <p class="card-desc">${escapeHtml(order.description)}</p>
      <p class="small">${escapeHtml(order.address)}</p>
      <div class="actions" style="margin-top:12px">
        ${mode === "available" ? `<button class="primary" data-action="acceptOrder" data-id="${order.id}" data-status="${order.status}">立即接单</button>` : ""}
        ${["repairer_accepted", "accepted"].includes(order.status) ? `<button class="primary" data-action="startService" data-id="${order.id}">开始服务</button>` : ""}
        ${["servicing", "bill_returned"].includes(order.status) ? `<button class="primary" data-action="showBillForm" data-id="${order.id}">提交服务单</button>` : ""}
      </div>
      <div id="bill-form-${order.id}"></div>
    </article>
  `;
}

function repairerEarnings() {
  const profits = state.cache.myProfits || [];
  return `
    ${walletPanel(state.user.id)}
    <section class="panel" style="margin-top:16px">
      <h3 class="card-title">分润记录</h3>
      ${profits.length ? table(["订单", "角色", "金额", "比例", "状态"], profits.map((p) => [p.order_id, p.role_type, money(p.amount), `${p.ratio}%`, badge(p.status)])) : empty("暂无分润记录", false)}
    </section>
  `;
}

function renderBusiness() {
  if (state.tab === "domestic") return domesticPanel();
  if (state.tab === "proxyOrders") return proxyOrdersPanel();
  if (state.tab === "payroll") return payrollPanel();
  if (state.tab === "warranties") return warrantiesPanel();
  if (state.tab === "addresses") return addressesPanel();
  return empty("请选择业务模块");
}

function domesticPanel() {
  const workers = state.cache.domesticWorkers || [];
  const demands = state.cache.domesticDemands || [];
  const contracts = state.cache.domesticContracts || [];
  const stores = state.cache.stores || [];
  const regions = state.cache.regions || [];
  const customerMode = currentRole() === "customer";
  const form = customerMode ? `
    <section class="panel">
      <h3 class="card-title">发布月嫂/保姆需求</h3>
      <form class="form-grid" data-form="createDomesticDemand" style="margin-top:16px">
        <div class="field"><label>服务类型</label><select name="service_type"><option value="maternity">月嫂</option><option value="nanny">保姆</option></select></div>
        <div class="field"><label>开始日期</label><input type="date" name="service_start" required></div>
        <div class="field"><label>联系人</label><input name="contact_name" value="${escapeHtml(state.user.name)}" required></div>
        <div class="field"><label>联系电话</label><input name="contact_phone" value="${escapeHtml(state.user.phone)}" required></div>
        <div class="field"><label>服务区域</label><select name="region_id" required>${regions.map((r) => `<option value="${r.id}">${escapeHtml(r.name)}</option>`).join("")}</select></div>
        <div class="field"><label>匹配门店</label><select name="store_id"><option value="">自动匹配</option>${stores.filter((s) => s.enabled).map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join("")}</select></div>
        <div class="field wide"><label>服务地址</label><input name="address" required></div>
        <div class="field wide"><label>需求说明</label><textarea name="description" required></textarea></div>
        <div class="field"><label>最低预算</label><input type="number" name="budget_min" min="0"></div>
        <div class="field"><label>最高预算</label><input type="number" name="budget_max" min="0"></div>
        <button class="primary" type="submit">提交需求</button>
      </form>
    </section>` : `
    <section class="panel">
      <h3 class="card-title">新增服务人员</h3>
      <form class="form-grid" data-form="createDomesticWorker" style="margin-top:16px">
        <div class="field"><label>服务类型</label><select name="service_type"><option value="maternity">月嫂</option><option value="nanny">保姆</option></select></div>
        <div class="field"><label>姓名</label><input name="name" required></div>
        <div class="field"><label>所属门店</label><select name="store_id"><option value="">平台</option>${stores.map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join("")}</select></div>
        <div class="field"><label>从业年限</label><input type="number" name="years_experience" min="0" value="1"></div>
        <div class="field"><label>最低价格</label><input type="number" name="price_min" min="0"></div>
        <div class="field"><label>最高价格</label><input type="number" name="price_max" min="0"></div>
        <div class="field wide"><label>技能（逗号分隔）</label><input name="skills" required></div>
        <div class="field wide"><label>档期与介绍</label><textarea name="intro"></textarea></div>
        <button class="primary" type="submit">保存人员档案</button>
      </form>
    </section>`;
  return `
    <div class="grid three">
      <div class="metric"><span class="muted">公开人员</span><strong>${workers.length}</strong></div>
      <div class="metric"><span class="muted">服务需求</span><strong>${demands.length}</strong></div>
      <div class="metric"><span class="muted">服务合同</span><strong>${contracts.length}</strong></div>
    </div>
    <div class="grid two" style="margin-top:16px">${form}
      <section class="panel"><h3 class="card-title">人员档案</h3>${workers.length ? table(["姓名", "类型", "经验", "价格", "核验"], workers.map((w) => [escapeHtml(w.name), w.service_type === "maternity" ? "月嫂" : "保姆", `${w.years_experience}年`, `${money(w.price_min)}-${money(w.price_max)}`, w.id_verified && w.health_verified ? "已核验" : "待完善"])) : empty("暂无人员", false)}</section>
    </div>
    <section class="panel" style="margin-top:16px"><h3 class="card-title">需求与匹配</h3>${demands.length ? table(["编号", "类型", "客户", "状态", "开始日期", "预算"], demands.map((d) => [d.id, d.service_type === "maternity" ? "月嫂" : "保姆", d.contact_name, badge(d.status), d.service_start || "-", `${money(d.budget_min)}-${money(d.budget_max)}`])) : empty("暂无需求", false)}</section>
    <section class="panel" style="margin-top:16px"><h3 class="card-title">服务合同</h3>${contracts.length ? table(["编号", "需求", "人员", "服务费", "代收", "状态"], contracts.map((c) => [c.id, c.demand_id, c.worker_id, money(c.service_fee), money(c.pass_through_amount), badge(c.status)])) : empty("暂无合同", false)}</section>
  `;
}

function proxyOrdersPanel() {
  const orders = state.cache.proxyOrders || [];
  return `
    <div class="toolbar"><div><h3 class="card-title">代客订单</h3><p class="small">客户身份、录单人、付款人和佣金归属分别记录</p></div><a class="button primary" href="./#proxy-create">新建代客订单</a></div>
    ${orders.length ? table(["订单", "客户电话", "状态", "认领", "金额", "二维码"], orders.map((o) => [o.id, escapeHtml(o.customer_phone_snapshot || o.contact_phone || ""), badge(o.status), o.claim_status, money(o.price), `<button class="small-button" data-action="showAccessCode" data-id="${o.id}" data-purpose="${o.status === "wait_payment" ? "payment" : "claim"}">${o.status === "wait_payment" ? "付款码" : "认领码"}</button>`])) : empty("暂无代客订单")}
  `;
}

function payrollPanel() {
  const wages = state.cache.wages || [];
  const payroll = state.cache.payroll || { periods: [], items: [] };
  return `
    <div class="grid three"><div class="metric"><span class="muted">订单计薪记录</span><strong>${wages.length}</strong></div><div class="metric"><span class="muted">月薪周期</span><strong>${payroll.periods.length}</strong></div><div class="metric"><span class="muted">待发项目</span><strong>${payroll.items.filter((i) => i.status !== "paid").length}</strong></div></div>
    <section class="panel" style="margin-top:16px"><h3 class="card-title">订单计薪</h3>${wages.length ? table(["订单", "员工", "方式", "金额", "工作量", "状态"], wages.map((w) => [w.order_id, w.employee_user_id, w.wage_mode === "monthly" ? "月薪" : "按单", money(w.amount), w.work_units, badge(w.status)])) : empty("暂无计薪记录", false)}</section>
    <section class="panel" style="margin-top:16px"><h3 class="card-title">月度工资单</h3>${payroll.items.length ? table(["周期", "门店", "员工", "金额", "状态", "备注"], payroll.items.map((i) => [i.period_id, i.store_id, i.user_id, money(i.amount), badge(i.status), escapeHtml(i.remark || "")])) : empty("暂无月度工资单", false)}</section>
  `;
}

function warrantiesPanel() {
  const items = state.cache.warranties || [];
  return `<section class="panel"><h3 class="card-title">保修凭证</h3>${items.length ? table(["凭证号", "订单", "金额", "保修", "开始", "到期"], items.map((w) => [w.certificate_no, w.order_id, money(w.amount), `${w.warranty_days}天`, dateText(w.starts_at), dateText(w.expires_at)])) : empty("暂无保修凭证", false)}</section>`;
}

function addressesPanel() {
  const items = state.cache.addresses || [];
  return `
    <div class="grid two">
      <section class="panel"><h3 class="card-title">新增地址</h3><form class="form-grid" data-form="createAddress" style="margin-top:16px"><div class="field"><label>联系人</label><input name="contact_name" value="${escapeHtml(state.user.name)}" required></div><div class="field"><label>手机号</label><input name="contact_phone" value="${escapeHtml(state.user.phone)}" required></div><div class="field wide"><label>详细地址</label><input name="address" required></div><label class="check"><input type="checkbox" name="is_default" value="true">设为默认</label><button class="primary" type="submit">保存地址</button></form></section>
      <section class="panel"><h3 class="card-title">我的地址簿</h3>${items.length ? table(["联系人", "电话", "地址", "默认"], items.map((a) => [a.contact_name, a.contact_phone, escapeHtml(a.address), a.is_default ? "是" : "否"])) : empty("暂无地址", false)}</section>
    </div>`;
}

function renderAdmin() {
  if (state.tab === "overview") return adminOverview();
  if (state.tab === "adminOrders") return adminOrders();
  if (state.tab === "adminUsers") return adminUsers();
  if (state.tab === "adminRepairers") return adminRepairers();
  if (state.tab === "adminStores") return adminStores();
  if (state.tab === "adminPackages") return adminPackages();
  if (state.tab === "adminFinance") return adminFinance();
  if (state.tab === "adminSupport") return supportCenter(true);
  if (state.tab === "adminAlerts") return adminAlerts();
  return empty("请选择管理模块");
}

function adminOverview() {
  const metrics = state.cache.metrics || {};
  const orders = state.cache.adminOrders || [];
  const users = state.cache.users || [];
  const repairers = state.cache.repairers || [];
  const alerts = state.cache.alerts || [];
  return `
    <div class="grid four">
      <div class="metric"><span class="muted">订单总数</span><strong>${metrics.orders_total ?? orders.length}</strong></div>
      <div class="metric"><span class="muted">已完成</span><strong>${metrics.orders_completed ?? 0}</strong></div>
      <div class="metric"><span class="muted">钱包数</span><strong>${metrics.wallets_total ?? 0}</strong></div>
      <div class="metric"><span class="muted">活跃告警</span><strong>${metrics.alerts_active ?? alerts.length}</strong></div>
    </div>
    <div class="grid two" style="margin-top:16px">
      <section class="panel">
        <h3 class="card-title">最新订单</h3>
        ${orders.length ? table(["编号", "类型", "状态", "金额"], orders.map((o) => [o.id, categoryLabel(o.category), badge(o.status), money(o.price)])) : empty("暂无订单", false)}
      </section>
      <section class="panel">
        <h3 class="card-title">运营概况</h3>
        <div class="grid two" style="margin-top:14px">
          <div class="metric"><span class="muted">用户样本</span><strong>${users.length}</strong></div>
          <div class="metric"><span class="muted">师傅样本</span><strong>${repairers.length}</strong></div>
        </div>
      </section>
    </div>
  `;
}

function adminOrders() {
  const orders = state.cache.adminOrders || [];
  const repairers = state.cache.repairers || [];
  return `
    <div class="toolbar">
      <div>
        <h3 class="card-title">订单管理</h3>
        <p class="small">派单、改价、服务单确认、门店审核和取消</p>
      </div>
    </div>
    ${
      orders.length
        ? table(
            ["编号", "客户", "类型", "状态", "金额", "地址", "操作"],
            orders.map((o) => [
              o.id,
              o.customer_id,
              categoryLabel(o.category),
              badge(o.status),
              money(o.price),
              escapeHtml(o.address),
              adminOrderActions(o, repairers),
            ]),
          )
        : empty("暂无订单")
    }
  `;
}

function adminOrderActions(order, repairers) {
  const repairerOptions = repairers.map((r) => `<option value="${r.id}">#${r.id} ${escapeHtml(r.skills)}</option>`).join("");
  return `
    <div class="actions">
      <button class="secondary" data-action="storeAccept" data-id="${order.id}">门店接单</button>
      <button class="secondary" data-action="autoDispatch" data-id="${order.id}">自动派单</button>
      <form data-form="assignOrder" style="display:flex;gap:8px">
        <input type="hidden" name="order_id" value="${order.id}" />
        <select name="repairer_id" required style="min-width:120px">${repairerOptions}</select>
        <button class="ghost" type="submit">指派</button>
      </form>
      <button class="secondary" data-action="adminPrice" data-id="${order.id}">改价</button>
      ${order.status === "bill_submitted" ? `<button class="secondary" data-action="confirmBill" data-id="${order.id}">确认服务单</button>` : ""}
      ${["paid", "paid_pending_review"].includes(order.status) ? `<button class="secondary" data-action="storeReview" data-id="${order.id}">门店审核</button>` : ""}
      ${!["completed", "cancelled"].includes(order.status) ? `<button class="danger" data-action="cancelOrder" data-id="${order.id}">取消</button>` : ""}
    </div>
  `;
}

function adminUsers() {
  const users = state.cache.users || [];
  return `
    <div class="split">
      <section class="panel">
        <h3 class="card-title">新增用户</h3>
        <form class="form-grid" data-form="createUser" style="margin-top:14px">
          <div class="field"><label>手机号</label><input name="phone" required /></div>
          <div class="field"><label>姓名</label><input name="name" required /></div>
          <div class="field">
            <label>角色</label>
            <select name="role">
              <option value="customer">客户</option>
              <option value="repairer">师傅</option>
              <option value="admin">管理员</option>
            </select>
          </div>
          <label class="small"><input type="checkbox" name="is_promotion_manager" /> 推广经理</label>
          <button class="primary" type="submit">创建用户</button>
        </form>
      </section>
      <section class="panel">
        <h3 class="card-title">用户列表</h3>
        ${users.length ? table(["编号", "姓名", "手机号", "角色", "推广经理"], users.map((u) => [u.id, escapeHtml(u.name), escapeHtml(u.phone), roleText[u.role] || u.role, u.is_promotion_manager ? "是" : "否"])) : empty("暂无用户", false)}
      </section>
    </div>
  `;
}

function adminRepairers() {
  const users = state.cache.users || [];
  const repairerUsers = users.filter((user) => user.role === "repairer");
  const selectableUsers = repairerUsers.length ? repairerUsers : users;
  const repairers = state.cache.repairers || [];
  const regions = state.cache.regions || [];
  return `
    <div class="split">
      <section class="panel">
        <h3 class="card-title">新增师傅档案</h3>
        <form class="form-grid" data-form="adminCreateRepairer" style="margin-top:14px">
          <div class="field">
            <label>师傅用户</label>
            <select name="user_id" required>${selectableUsers.map((u) => `<option value="${u.id}">#${u.id} ${escapeHtml(u.name)}</option>`).join("")}</select>
          </div>
          <div class="field">
            <label>区域</label>
            <select name="region_id"><option value="">暂不指定</option>${regions.map((r) => `<option value="${r.id}">${escapeHtml(r.name)}</option>`).join("")}</select>
          </div>
          <div class="field wide"><label>技能</label><input name="skills" value="水电维修,家电维修" required /></div>
          <div class="field wide"><label>简介</label><textarea name="intro"></textarea></div>
          <button class="primary" type="submit">创建档案</button>
        </form>
      </section>
      <section class="panel">
        <h3 class="card-title">师傅列表</h3>
        ${repairers.length ? table(["编号", "用户", "技能", "状态", "评分", "完成单"], repairers.map((r) => [r.id, r.user_id, escapeHtml(r.skills), badge(r.status), r.rating, r.order_count])) : empty("暂无师傅", false)}
      </section>
    </div>
  `;
}

function adminStores() {
  const stores = state.cache.stores || [];
  const users = state.cache.users || [];
  const regions = state.cache.regions || [];
  const repairers = state.cache.repairers || [];
  const addresses = state.cache.addresses || [];
  return `
    <div class="grid two">
      <section class="panel">
        <h3 class="card-title">新增区域</h3>
        <form class="form-grid" data-form="createRegion" style="margin-top:14px">
          <div class="field"><label>区域名称</label><input name="name" required /></div>
          <div class="field"><label>层级</label><select name="level"><option value="1">省/大区</option><option value="2">城市</option><option value="3">区县</option></select></div>
          <button class="primary" type="submit">创建区域</button>
        </form>
      </section>
      <section class="panel">
        <h3 class="card-title">新增门店</h3>
        <form class="form-grid" data-form="createStore" style="margin-top:14px">
          <div class="field"><label>门店名称</label><input name="name" required /></div>
          <div class="field"><label>区域</label><select name="region_id" required>${optionList(regions, "请选择区域")}</select></div>
          <div class="field"><label>店长</label><select name="manager_id" required>${users.map((u) => `<option value="${u.id}">${escapeHtml(u.name)}</option>`).join("")}</select></div>
          <div class="field"><label>城市经理</label><select name="city_manager_id"><option value="">无</option>${users.map((u) => `<option value="${u.id}">${escapeHtml(u.name)}</option>`).join("")}</select></div>
          <div class="field wide"><label>默认二接师傅</label><select name="default_second_receiver_id"><option value="">暂不指定</option>${repairers.map((r) => `<option value="${r.id}">#${r.id} ${escapeHtml(r.skills)}</option>`).join("")}</select></div>
          <button class="primary" type="submit">创建门店</button>
        </form>
      </section>
    </div>
    <section class="panel" style="margin-top:16px">
      <h3 class="card-title">门店列表</h3>
      ${stores.length ? table(["编号", "名称", "区域", "店长", "状态", "启用"], stores.map((s) => [s.id, escapeHtml(s.name), s.region_id, s.manager_id, badge(s.status), s.enabled ? "是" : "否"])) : empty("暂无门店", false)}
    </section>
    <section class="panel" style="margin-top:16px">
      <h3 class="card-title">服务地址</h3>
      ${addresses.length ? table(["编号", "门店", "城市", "小区", "提示", "启用"], addresses.map((a) => [a.id, a.store_id, escapeHtml(a.city), escapeHtml(a.community), escapeHtml(a.detail_hint || ""), a.enabled ? "是" : "否"])) : empty("暂无服务地址", false)}
    </section>
  `;
}

function adminPackages() {
  const packages = state.cache.packages || [];
  const customerPackages = state.cache.customerPackages || [];
  const schedules = state.cache.schedules || [];
  return `
    <div class="split">
      <section class="panel">
        <h3 class="card-title">新增套餐</h3>
        <form class="form-grid" data-form="createPackage" style="margin-top:14px">
          <div class="field"><label>名称</label><input name="name" required /></div>
          <div class="field"><label>类型</label><select name="category">${categoryOptions.map(([id, name]) => `<option value="${id}">${name}</option>`).join("")}</select></div>
          <div class="field"><label>服务年限</label><input name="service_years" type="number" min="1" value="1" required /></div>
          <div class="field"><label>每年次数</label><input name="annual_times" type="number" min="1" value="1" required /></div>
          <div class="field"><label>设备数量</label><input name="device_count" type="number" min="1" value="1" required /></div>
          <div class="field"><label>服务月份</label><input name="service_month" type="number" min="1" max="12" value="3" required /></div>
          <div class="field"><label>价格</label><input name="price" inputmode="decimal" value="199" required /></div>
          <div class="field wide"><label>描述</label><textarea name="description"></textarea></div>
          <button class="primary" type="submit">创建套餐</button>
        </form>
      </section>
      <section class="panel">
        <h3 class="card-title">套餐列表</h3>
        ${packages.length ? table(["编号", "名称", "类型", "价格", "状态"], packages.map((p) => [p.id, escapeHtml(p.name), categoryLabel(p.category), money(p.price), badge(p.status)])) : empty("暂无套餐", false)}
      </section>
    </div>
    <section class="panel" style="margin-top:16px">
      <h3 class="card-title">客户套餐</h3>
      ${customerPackages.length ? table(["编号", "用户", "门店", "套餐", "使用", "有效期"], customerPackages.map((p) => [p.id, p.user_id, p.store_id, p.package_id, `${p.used_times}/${p.total_times}`, `${p.start_date} 至 ${p.end_date}`])) : empty("暂无客户套餐", false)}
    </section>
    <section class="panel" style="margin-top:16px">
      <h3 class="card-title">服务计划</h3>
      ${schedules.length ? table(["编号", "客户套餐", "计划日期", "状态", "订单"], schedules.map((s) => [s.id, s.customer_package_id, s.due_date, badge(s.status), s.order_id || "-"])) : empty("暂无服务计划", false)}
    </section>
  `;
}

function adminFinance() {
  const payments = state.cache.payments || [];
  const withdrawals = state.cache.withdrawals || [];
  const logs = state.cache.reconcileLogs || [];
  return `
    <div class="toolbar">
      <div>
        <h3 class="card-title">财务中心</h3>
        <p class="small">支付、提现、分润和对账</p>
      </div>
      <div class="actions">
        <button class="primary" data-action="runReconcile">运行对账</button>
        <button class="secondary" data-action="queryProfit">查询订单分润</button>
      </div>
    </div>
    <section class="panel">
      <h3 class="card-title">提现审核</h3>
      ${withdrawals.length ? table(["编号", "用户", "金额", "状态", "时间", "操作"], withdrawals.map((w) => [w.id, w.user_id, money(w.amount), badge(w.status), dateText(w.created_at), withdrawalActions(w)])) : empty("暂无提现记录", false)}
    </section>
    <section class="panel" style="margin-top:16px">
      <h3 class="card-title">支付记录</h3>
      ${payments.length ? table(["编号", "订单", "用户", "金额", "状态", "渠道", "时间"], payments.map((p) => [p.id, p.order_id, p.user_id, money(p.amount), badge(p.status), p.provider, dateText(p.created_at)])) : empty("暂无支付记录", false)}
    </section>
    <section class="panel" style="margin-top:16px">
      <h3 class="card-title">对账日志</h3>
      ${logs.length ? table(["编号", "钱包", "用户", "差异", "状态", "时间"], logs.map((l) => [l.id, l.wallet_id, l.user_id, money(l.difference), badge(l.status), dateText(l.created_at)])) : empty("暂无对账日志", false)}
    </section>
  `;
}

function withdrawalActions(w) {
  if (w.status !== "pending") return "-";
  return `
    <div class="actions">
      <button class="secondary" data-action="reviewWithdraw" data-id="${w.id}" data-review="approve">通过</button>
      <button class="danger" data-action="reviewWithdraw" data-id="${w.id}" data-review="reject">拒绝</button>
    </div>
  `;
}

function adminAlerts() {
  const alerts = state.cache.alerts || [];
  return `
    <section class="panel">
      <h3 class="card-title">告警中心</h3>
      ${
        alerts.length
          ? table(
              ["编号", "类型", "级别", "消息", "状态", "时间", "操作"],
              alerts.map((a) => [
                a.id,
                escapeHtml(a.type),
                badge(a.severity),
                escapeHtml(a.message),
                a.resolved ? badge("closed") : badge("open"),
                dateText(a.created_at),
                a.resolved ? "-" : `<button class="secondary" data-action="resolveAlert" data-id="${a.id}">标记解决</button>`,
              ]),
            )
          : empty("暂无告警", false)
      }
    </section>
  `;
}

function table(headers, rows) {
  return `
    <div class="table-wrap">
      <table>
        <thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows
            .map(
              (row) => `
                <tr>
                  ${row
                    .map(
                      (cell, index) =>
                        `<td data-label="${escapeHtml(headers[index] || "")}">${cell ?? ""}</td>`,
                    )
                    .join("")}
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function empty(message, boxed = true) {
  const html = `<div class="empty">${message}</div>`;
  return boxed ? html : `<div class="empty">${message}</div>`;
}

function optionList(items, placeholder) {
  return `<option value="">${placeholder}</option>${items.map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join("")}`;
}

function categoryLabel(value) {
  return categoryOptions.find(([id]) => id === value)?.[1] || value || "-";
}

function formObject(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  form.querySelectorAll('input[type="checkbox"]').forEach((input) => {
    data[input.name] = input.checked;
  });
  Object.keys(data).forEach((key) => {
    if (data[key] === "") data[key] = null;
  });
  return data;
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

document.addEventListener("click", async (event) => {
  const roleBtn = event.target.closest("[data-role-choice]");
  if (roleBtn) {
    const form = roleBtn.closest("form");
    form.querySelectorAll("[data-role-choice]").forEach((btn) => btn.classList.remove("active"));
    roleBtn.classList.add("active");
    form.elements.role.value = roleBtn.dataset.roleChoice;
    return;
  }

  const demoBtn = event.target.closest("[data-demo-login]");
  if (demoBtn) {
    const [phone, name, role] = demoBtn.dataset.demoLogin.split("|");
    const form = demoBtn.closest("form");
    form.elements.phone.value = phone;
    form.elements.name.value = name;
    form.elements.role.value = role;
    const res = await api("/api/v1/auth/wechat-login", { method: "POST", body: { code: `${phone}:${name}:${role}` } });
    saveSession(res.token, res.user);
    toast("登录成功");
    await refresh();
    return;
  }

  const loginTabBtn = event.target.closest("[data-login-tab]");
  if (loginTabBtn) {
    const target = loginTabBtn.dataset.loginTab;
    const form = loginTabBtn.closest("main") || document;
    form.querySelectorAll("[data-login-tab]").forEach((btn) => {
      const active = btn.dataset.loginTab === target;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    form.querySelectorAll("[data-login-pane]").forEach((pane) => {
      pane.hidden = pane.dataset.loginPane !== target;
    });
    const loginForm = form.querySelector("form[data-form='login']");
    if (loginForm) loginForm.dataset.loginMode = target;
    return;
  }

  const tabBtn = event.target.closest("[data-tab]");
  if (tabBtn) {
    await navigate(tabBtn.dataset.tab);
    return;
  }

  const catBtn = event.target.closest("[data-category]");
  if (catBtn) {
    state.selectedCategory = catBtn.dataset.category;
    render();
    return;
  }

  const actionEl = event.target.closest("[data-action]");
  if (!actionEl || actionEl.tagName === "SELECT") return;
  const action = actionEl.dataset.action;
  try {
    if (action === "requestSms") {
      const form = actionEl.closest("form");
      const phone = form && form.elements.phone.value.trim();
      if (!phone || phone.length !== 11) throw new Error("请输入11位手机号");
      const result = await api("/api/v1/auth/sms/request", { method: "POST", body: { phone } });
      if (result.debug_code) {
        form.elements.sms_code.value = result.debug_code;
        toast(`体验验证码：${result.debug_code}`);
      } else toast("验证码已发送");
    }
    if (action === "logout") clearSession();
    if (action === "refresh") await refresh();
    if (action === "payOrder") await payOrder(actionEl.dataset.id, Number(actionEl.dataset.amount));
    if (action === "rateOrder") await rateOrder(actionEl.dataset.id);
    if (action === "acceptOrder") await acceptOrder(actionEl.dataset.id, actionEl.dataset.status);
    if (action === "startService") await transitionOrder(actionEl.dataset.id, "servicing", "repairer", "已开始服务");
    if (action === "showBillForm") showBillForm(actionEl.dataset.id);
    if (action === "storeAccept") await api(`/api/v1/orders/${actionEl.dataset.id}/store-accept?manager_id=${state.user.id}`, { method: "POST" }).then(done);
    if (action === "autoDispatch") await api(`/api/v1/orders/${actionEl.dataset.id}/auto-dispatch`, { method: "POST" }).then(done);
    if (action === "adminPrice") await adminSetPrice(actionEl.dataset.id);
    if (action === "confirmBill") await api(`/api/v1/orders/${actionEl.dataset.id}/service-bill/confirm`, { method: "POST" }).then(done);
    if (action === "storeReview") await storeReview(actionEl.dataset.id);
    if (action === "cancelOrder") await transitionOrder(actionEl.dataset.id, "cancelled", "admin", "管理员取消");
    if (action === "runReconcile") await api("/api/v1/admin/reconcile/run", { method: "POST" }).then((res) => done(res, `对账完成：${res.ok || 0} 正常，${res.mismatch || 0} 异常`));
    if (action === "queryProfit") await queryProfit();
    if (action === "reviewWithdraw") await reviewWithdraw(actionEl.dataset.id, actionEl.dataset.review);
    if (action === "resolveAlert") await api(`/api/v1/admin/alerts/${actionEl.dataset.id}/resolve`, { method: "POST" }).then(done);
    if (action === "showAccessCode") {
      const access = await api(`/api/v1/business/orders/${actionEl.dataset.id}/access/${actionEl.dataset.purpose}`, {
        method: "POST",
        body: { created_by_user_id: state.user.id },
      });
      window.open(access.code_url, "_blank", "noopener,noreferrer");
    }
  } catch (error) {
    toast(error.message, "error");
  }
});

document.addEventListener("change", async (event) => {
  const select = event.target.closest('select[data-action="switchViewRole"]');
  if (!select) return;
  state.viewRole = select.value;
  state.tab = "";
  localStorage.setItem("h5_view_role", state.viewRole);
  await refresh();
});

document.addEventListener("submit", async (event) => {
  const form = event.target.closest("form[data-form]");
  if (!form) return;
  event.preventDefault();
  const data = formObject(form);
  try {
    await handleForm(form.dataset.form, data);
  } catch (error) {
    toast(error.message, "error");
  }
});

async function handleForm(type, data) {
  if (type === "login") {
    if (!data.agreed_terms) {
      toast("请先同意《用户服务协议》和《隐私政策》");
      return;
    }
    const res = await api("/api/v1/auth/sms/login", {
      method: "POST",
      body: { phone: data.phone, code: data.sms_code, name: data.name },
    });
    saveSession(res.token, res.user);
    toast("登录成功");
    await refresh();
  }

  if (type === "createOrder") {
    const serviceAddress = (state.cache.serviceAddresses || []).find(
      (item) => item.id === Number(data.address_book_id),
    );
    if (!serviceAddress) throw new Error("请选择平台已开通的标准地址");
    await api("/api/v1/orders", {
      method: "POST",
      body: {
        customer_id: state.user.id,
        region_id: serviceAddress.region_id,
        store_id: serviceAddress.store_id,
        address_book_id: serviceAddress.id,
        category: data.category,
        description: data.description,
        address: serviceAddress.full_address,
        contact_phone: data.contact_phone,
        scheduled_time: data.scheduled_time ? new Date(data.scheduled_time).toISOString() : null,
      },
    });
    done(null, "订单已提交");
  }

  if (type === "buyPackage") {
    await api("/api/v1/service-packages/purchase", {
      method: "POST",
      body: {
        package_id: Number(data.package_id),
        user_id: state.user.id,
        store_id: Number(data.store_id),
        address: data.address,
        contact_phone: data.contact_phone,
        start_date: data.start_date,
      },
    });
    done(null, "套餐已购买");
  }

  if (type === "createSupport") {
    await api("/api/v1/support/tickets", {
      method: "POST",
      body: {
        store_id: Number(data.store_id),
        user_id: state.user.id,
        order_id: numberOrNull(data.order_id),
        category: data.category,
        title: data.title,
        content: data.content,
      },
    });
    done(null, "工单已提交");
  }

  if (type === "withdraw") {
    await api(`/api/v1/wallet/withdraw/${data.user_id}`, {
      method: "POST",
      body: { amount: Number(data.amount), remark: data.remark },
    });
    done(null, "提现申请已提交");
  }

  if (type === "createRepairerProfile") {
    await api("/api/v1/repairers", {
      method: "POST",
      body: {
        user_id: state.user.id,
        skills: data.skills,
        region_id: numberOrNull(data.region_id),
        intro: data.intro,
      },
    });
    done(null, "师傅档案已创建");
  }

  if (type === "updateRepairerProfile") {
    await api(`/api/v1/repairers/${data.repairer_id}`, {
      method: "PATCH",
      body: {
        skills: data.skills,
        status: data.status,
        region_id: numberOrNull(data.region_id),
        intro: data.intro,
      },
    });
    done(null, "师傅资料已保存");
  }

  if (type === "serviceBill") {
    const amount = Number(data.amount);
    await api(`/api/v1/orders/${data.order_id}/service-bill`, {
      method: "POST",
      body: {
        repairer_id: Number(data.repairer_id),
        title: data.title || "服务项目单据",
        items_json: JSON.stringify([{ name: data.item_name || "上门维修服务", quantity: 1, unit_price: amount, subtotal: amount }]),
        amount,
        warranty_days: Number(data.warranty_days || 0),
        confirmation_method: "phone",
        confirmation_note: "H5提交，已与客户沟通确认",
      },
    });
    done(null, "服务单已提交");
  }

  if (type === "assignOrder") {
    await api(`/api/v1/orders/${data.order_id}/assign`, {
      method: "POST",
      body: { repairer_id: Number(data.repairer_id) },
    });
    done(null, "已指派师傅");
  }

  if (type === "createUser") {
    await api("/api/v1/users", {
      method: "POST",
      body: {
        phone: data.phone,
        name: data.name,
        role: data.role,
        is_promotion_manager: Boolean(data.is_promotion_manager),
      },
    });
    done(null, "用户已创建");
  }

  if (type === "adminCreateRepairer") {
    await api("/api/v1/repairers", {
      method: "POST",
      body: {
        user_id: Number(data.user_id),
        skills: data.skills,
        region_id: numberOrNull(data.region_id),
        intro: data.intro,
      },
    });
    done(null, "师傅档案已创建");
  }

  if (type === "createRegion") {
    await api("/api/v1/regions", {
      method: "POST",
      body: { name: data.name, level: Number(data.level) },
    });
    done(null, "区域已创建");
  }

  if (type === "createStore") {
    await api("/api/v1/stores", {
      method: "POST",
      body: {
        name: data.name,
        region_id: Number(data.region_id),
        manager_id: Number(data.manager_id),
        city_manager_id: numberOrNull(data.city_manager_id),
        default_second_receiver_id: numberOrNull(data.default_second_receiver_id),
      },
    });
    done(null, "门店已创建");
  }

  if (type === "createPackage") {
    await api("/api/v1/service-packages", {
      method: "POST",
      body: {
        name: data.name,
        category: data.category,
        service_years: Number(data.service_years),
        annual_times: Number(data.annual_times),
        device_count: Number(data.device_count),
        service_month: Number(data.service_month),
        price: Number(data.price),
        description: data.description,
      },
    });
    done(null, "套餐已创建");
  }

  if (type === "replySupport") {
    await api(`/api/v1/support/tickets/${data.ticket_id}/reply`, {
      method: "POST",
      body: {
        user_id: state.user.id,
        content: data.content,
        close: Boolean(data.close),
      },
    });
    done(null, "已回复工单");
  }

  if (type === "createDomesticDemand") {
    await api("/api/v1/business/domestic/demands", {
      method: "POST",
      body: {
        customer_id: state.user.id,
        created_by_user_id: state.user.id,
        store_id: numberOrNull(data.store_id),
        region_id: Number(data.region_id),
        service_type: data.service_type,
        contact_name: data.contact_name,
        contact_phone: data.contact_phone,
        address: data.address,
        description: data.description,
        detail_json: "{}",
        budget_min: Number(data.budget_min || 0),
        budget_max: Number(data.budget_max || 0),
        service_start: data.service_start,
      },
    });
    done(null, "家政需求已提交");
  }

  if (type === "createDomesticWorker") {
    await api("/api/v1/business/domestic/workers", {
      method: "POST",
      body: {
        service_type: data.service_type,
        name: data.name,
        store_id: numberOrNull(data.store_id),
        years_experience: Number(data.years_experience || 0),
        price_min: Number(data.price_min || 0),
        price_max: Number(data.price_max || 0),
        skills_json: JSON.stringify(String(data.skills || "").split(/[，,]/).map((item) => item.trim()).filter(Boolean)),
        intro: data.intro,
        id_verified: false,
        health_verified: false,
        training_verified: false,
      },
    });
    done(null, "服务人员档案已创建");
  }

  if (type === "createAddress") {
    await api("/api/v1/business/addresses", {
      method: "POST",
      body: {
        user_id: state.user.id,
        contact_name: data.contact_name,
        contact_phone: data.contact_phone,
        address: data.address,
        is_default: Boolean(data.is_default),
      },
    });
    done(null, "地址已保存");
  }
}

async function payOrder(orderId, amount) {
  if (!amount || amount <= 0) {
    toast("订单金额为 0，暂不能支付", "error");
    return;
  }
  toast("请在微信小程序内完成微信支付", "error");
}

async function rateOrder(orderId) {
  const rating = Number(prompt("请输入评分 1-5", "5"));
  if (!rating) return;
  const remark = prompt("评价备注", "服务及时，体验不错") || "";
  await api(`/api/v1/orders/${orderId}/rating`, {
    method: "POST",
    body: { rating, remark },
  });
  done(null, "评价已提交");
}

async function acceptOrder(orderId, currentStatus) {
  const target = currentStatus === "assigned" ? "accepted" : "repairer_accepted";
  await transitionOrder(orderId, target, "repairer", "师傅接单");
}

async function transitionOrder(orderId, toStatus, operatorType, remark) {
  await api(`/api/v1/orders/${orderId}/transition`, {
    method: "POST",
    body: {
      to_status: toStatus,
      operator_type: operatorType,
      operator_id: state.user.id,
      remark,
    },
  });
  done();
}

function showBillForm(orderId) {
  const repairer = state.cache.myRepairer;
  const mount = document.querySelector(`#bill-form-${orderId}`);
  if (!mount || !repairer) return;
  mount.innerHTML = `
    <form class="form-grid" data-form="serviceBill" style="margin-top:12px">
      <input type="hidden" name="order_id" value="${orderId}" />
      <input type="hidden" name="repairer_id" value="${repairer.id}" />
      <div class="field">
        <label>服务标题</label>
        <input name="title" value="上门维修服务" required />
      </div>
      <div class="field">
        <label>项目名称</label>
        <input name="item_name" value="维修人工及材料" required />
      </div>
      <div class="field">
        <label>金额</label>
        <input name="amount" inputmode="decimal" value="100" required />
      </div>
      <div class="field">
        <label>质保天数</label>
        <input name="warranty_days" type="number" min="0" value="30" />
      </div>
      <button class="primary" type="submit">提交服务单</button>
    </form>
  `;
}

async function adminSetPrice(orderId) {
  const amount = Number(prompt("输入订单金额", "100"));
  if (!Number.isFinite(amount)) return;
  await api(`/api/v1/orders/${orderId}`, {
    method: "PATCH",
    body: { price: amount },
  });
  toast("金额已更新");
  await refresh();
}

async function storeReview(orderId) {
  const wage = Number(prompt("输入师傅工资金额", "80"));
  if (!Number.isFinite(wage)) return;
  const remark = prompt("审核备注", "门店审核通过") || "";
  await api(`/api/v1/orders/${orderId}/store-review?manager_id=${state.user.id}`, {
    method: "POST",
    body: { technician_wage_amount: wage, wage_mode: "per_order", remark },
  });
  done(null, "门店审核完成");
}

async function reviewWithdraw(id, action) {
  const remark = prompt("审核备注", action === "approve" ? "审核通过" : "审核拒绝") || "";
  await api(`/api/v1/wallet/withdraw/${id}/review`, {
    method: "POST",
    body: { action, remark },
  });
  done(null, "提现审核已处理");
}

async function queryProfit() {
  const orderId = prompt("输入订单编号查看分润");
  if (!orderId) return;
  const result = await api(`/api/v1/finance/profit/order/${orderId}`);
  const lines = result.items
    .map((item) => `${item.role_type}: ${money(item.amount)} (${item.ratio}%)`)
    .join("\n");
  alert(`订单 #${result.order_id}\n订单金额：${money(result.order_price)}\n已分配：${money(result.total_distributed)}\n\n${lines || "暂无分润"}`);
}

async function done(_res, message = "操作成功") {
  toast(message);
  await refresh();
}

async function init() {
  if (!state.token) {
    renderLogin();
    return;
  }
  try {
    const user = await api("/api/v1/auth/me");
    state.user = { ...state.user, ...user };
    localStorage.setItem("h5_user", JSON.stringify(state.user));
    if (!state.viewRole) state.viewRole = state.user.role;
    await refresh();
  } catch {
    clearSession();
  }
}

init();
