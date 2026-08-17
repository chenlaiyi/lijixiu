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

function getBusinessRole(user = {}) {
  if (user.business_role) return user.business_role;
  const phone = String(user.phone || '');
  if (ROLE_BY_PHONE[phone]) return ROLE_BY_PHONE[phone];
  if (user.is_promotion_manager) return 'promotion_manager';
  return user.role || 'customer';
}

function getBackendRole(phone) {
  return BACKEND_ROLE_BY_BUSINESS[ROLE_BY_PHONE[String(phone || '')] || 'customer'] || 'customer';
}

function getEntryPath(user = {}) {
  return ENTRY_BY_BUSINESS[getBusinessRole(user)] || ENTRY_BY_BUSINESS.customer;
}

module.exports = {
  getBusinessRole,
  getBackendRole,
  getEntryPath,
};
