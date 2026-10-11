/**
 * 多角色工具(2026-10-07)
 *
 * 一个手机号可以同时是店长、师傅、业务(如 18060936373)。后端在 userInfo 上返回:
 *   business_roles:        ["store_manager", "repairer", "promotion_manager"]  ← 全部拥有
 *   active_business_role:  "store_manager"                                     ← 当前身份
 *
 * 兼容:老缓存 / 老响应只有单个 business_role,下面的取值函数会退回单角色逻辑。
 */

// 历史遗留:没有 business_role 字段时按手机号猜角色(仅演示账号会命中)
const ROLE_BY_PHONE = {
  18800000000: 'platform_admin',
  18800000002: 'repairer',
  18800000003: 'second_receiver',
  18800000004: 'store_manager',
  18800000005: 'city_manager',
  18800000006: 'promotion_manager',
  18800000999: 'repairer',
};

const BACKEND_ROLE_BY_BUSINESS = {
  platform_admin: 'admin',
  store_manager: 'admin',
  city_manager: 'admin',
  tech_support: 'admin',
  finance: 'admin',
  repairer: 'repairer',
  second_receiver: 'repairer',
  promotion_manager: 'customer',
  customer: 'customer',
};

const ENTRY_BY_BUSINESS = {
  platform_admin: '/pages/admin/dashboard/dashboard',
  store_manager: '/pages/store/dashboard/dashboard',
  city_manager: '/pages/city/dashboard/dashboard',
  promotion_manager: '/pages/promotion/dashboard/dashboard',
  tech_support: '/pages/support/dashboard/dashboard',
  finance: '/pages/finance/dashboard/dashboard',
  second_receiver: '/pages/second/dashboard/dashboard',
  repairer: '/pages/repairer/jobs/jobs',
  customer: '/pages/customer/home/home',
};

const LABEL_BY_BUSINESS = {
  customer: '客户',
  repairer: '师傅',
  store_manager: '店长',
  city_manager: '城市经理',
  promotion_manager: '业务',
  second_receiver: '兜底',
  tech_support: '技术支持',
  finance: '财务',
  platform_admin: '平台管理员',
};

const WORKBENCH_LABEL = {
  customer: '我的订单',
  repairer: '师傅工作台',
  store_manager: '门店工作台',
  city_manager: '城市工作台',
  promotion_manager: '推广工作台',
  second_receiver: '兜底工单',
  tech_support: '服务保障工作台',
  finance: '财务工作台',
  platform_admin: '平台工作台',
};

/** 有工作台(非纯客户)的角色,顺序即切换列表的展示顺序 */
const ROLE_ORDER = [
  'store_manager',
  'city_manager',
  'platform_admin',
  'tech_support',
  'finance',
  'second_receiver',
  'repairer',
  'promotion_manager',
  'customer',
];

/** 该账号拥有的全部业务角色(至少一个)。 */
function getBusinessRoles(user) {
  const source = user && typeof user === 'object' ? user : {};
  const raw = Array.isArray(source.business_roles) ? source.business_roles : [];
  const seen = [];
  raw.forEach((item) => {
    const value = String(item || '').trim().toLowerCase();
    if (value && ROLE_ORDER.indexOf(value) >= 0 && seen.indexOf(value) < 0) seen.push(value);
  });
  if (seen.length) return seen;

  // 兼容老数据:单个 business_role / 手机号映射 / is_promotion_manager
  const phone = String(source.phone || '');
  const single = source.business_role || ROLE_BY_PHONE[phone] || (source.is_promotion_manager ? 'promotion_manager' : '') || source.role || 'customer';
  const normalized = String(single).trim().toLowerCase();
  return [ROLE_ORDER.indexOf(normalized) >= 0 ? normalized : 'customer'];
}

/** 当前身份:active_business_role 优先,否则取拥有的第一个工作台角色。 */
function getBusinessRole(user) {
  const source = user && typeof user === 'object' ? user : {};
  const roles = getBusinessRoles(source);
  const active = String(source.active_business_role || '').trim().toLowerCase();
  if (active && roles.indexOf(active) >= 0) return active;
  for (let i = 0; i < roles.length; i += 1) {
    if (roles[i] !== 'customer') return roles[i];
  }
  return roles[0] || 'customer';
}

/** 账号是否拥有某个角色(不限当前身份)—— 和后端鉴权「并集」口径一致。 */
function hasBusinessRole(user, roleValue) {
  return getBusinessRoles(user).indexOf(String(roleValue || '').trim().toLowerCase()) >= 0;
}

/** 是否拥有其中任一角色。 */
function hasAnyBusinessRole(user, roleValues) {
  const roles = Array.isArray(roleValues) ? roleValues : [roleValues];
  return roles.some((item) => hasBusinessRole(user, item));
}

/** 是否可切换身份(拥有 2 个以上角色)。 */
function canSwitchRole(user) {
  return getBusinessRoles(user).length > 1;
}

function roleLabel(value) {
  return LABEL_BY_BUSINESS[String(value || '').trim().toLowerCase()] || '客户';
}

function workbenchLabel(value) {
  return WORKBENCH_LABEL[String(value || '').trim().toLowerCase()] || '工作台';
}

/** 拥有的角色 → [{ value, label, active }],按 ROLE_ORDER 排序。 */
function roleOptions(user) {
  const active = getBusinessRole(user);
  const roles = getBusinessRoles(user);
  return roles
    .slice()
    .sort((a, b) => ROLE_ORDER.indexOf(a) - ROLE_ORDER.indexOf(b))
    .map((value) => ({ value, label: roleLabel(value), active: value === active }));
}

/** 标签串:"店长 · 师傅 · 业务" */
function roleText(user) {
  return getBusinessRoles(user).map(roleLabel).join(' · ');
}

function getBackendRole(phone) {
  return BACKEND_ROLE_BY_BUSINESS[ROLE_BY_PHONE[String(phone || '')] || 'customer'] || 'customer';
}

function getEntryPath(user) {
  return ENTRY_BY_BUSINESS[getBusinessRole(user)] || ENTRY_BY_BUSINESS.customer;
}

/** 某个角色对应的入口页(切换身份后跳这里)。 */
function getEntryPathForRole(roleValue) {
  return ENTRY_BY_BUSINESS[roleValue] || ENTRY_BY_BUSINESS.customer;
}

module.exports = {
  ROLE_ORDER,
  getBusinessRole,
  getBusinessRoles,
  hasBusinessRole,
  hasAnyBusinessRole,
  canSwitchRole,
  roleLabel,
  roleOptions,
  roleText,
  workbenchLabel,
  getBackendRole,
  getEntryPath,
  getEntryPathForRole,
};
