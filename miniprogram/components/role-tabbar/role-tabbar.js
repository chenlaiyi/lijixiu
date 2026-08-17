const role = require('../../utils/role');

const CUSTOMER_HOME = '/pages/customer/home/home';
const CUSTOMER_ORDERS = '/pages/customer/orders/orders';
const CUSTOMER_PROFILE = '/pages/customer/profile/profile';
const REPAIRER_JOBS = '/pages/repairer/jobs/jobs';
const REPAIRER_EARNINGS = '/pages/repairer/earnings/earnings';
const PROXY_ORDER = '/pages/staff/proxy-order/proxy-order';

const ICON_BASE = '/assets/tabbar';

const MENU_BY_ROLE = {
  customer: [
    { key: 'home', label: '首页', icon: 'home', url: CUSTOMER_HOME },
    { key: 'orders', label: '订单', icon: 'orders', url: CUSTOMER_ORDERS },
    { key: 'profile', label: '我的', icon: 'profile', url: CUSTOMER_PROFILE },
  ],
  repairer: [
    { key: 'jobs', label: '工单', icon: 'jobs', url: REPAIRER_JOBS },
    { key: 'earnings', label: '收益', icon: 'earnings', url: REPAIRER_EARNINGS },
    { key: 'proxy', label: '代下单', icon: 'orders', url: PROXY_ORDER },
    { key: 'profile', label: '我的', icon: 'profile', url: CUSTOMER_PROFILE },
  ],
  second_receiver: [
    { key: 'second', label: '兜底', icon: 'second', url: '/pages/second/dashboard/dashboard' },
    { key: 'jobs', label: '工单', icon: 'jobs', url: REPAIRER_JOBS },
    { key: 'earnings', label: '收益', icon: 'earnings', url: REPAIRER_EARNINGS },
    { key: 'proxy', label: '代下单', icon: 'orders', url: PROXY_ORDER },
    { key: 'profile', label: '我的', icon: 'profile', url: CUSTOMER_PROFILE },
  ],
  store_manager: [
    { key: 'store', label: '门店', icon: 'store', url: '/pages/store/dashboard/dashboard' },
    { key: 'earnings', label: '收益', icon: 'earnings', url: REPAIRER_EARNINGS },
    { key: 'proxy', label: '代下单', icon: 'orders', url: PROXY_ORDER },
    { key: 'profile', label: '我的', icon: 'profile', url: CUSTOMER_PROFILE },
  ],
  city_manager: [
    { key: 'city', label: '城市', icon: 'city', url: '/pages/city/dashboard/dashboard' },
    { key: 'earnings', label: '收益', icon: 'earnings', url: REPAIRER_EARNINGS },
    { key: 'proxy', label: '代下单', icon: 'orders', url: PROXY_ORDER },
    { key: 'profile', label: '我的', icon: 'profile', url: CUSTOMER_PROFILE },
  ],
  promotion_manager: [
    { key: 'promotion', label: '推广', icon: 'promotion', url: '/pages/promotion/dashboard/dashboard' },
    { key: 'earnings', label: '收益', icon: 'earnings', url: REPAIRER_EARNINGS },
    { key: 'proxy', label: '代下单', icon: 'orders', url: PROXY_ORDER },
    { key: 'profile', label: '我的', icon: 'profile', url: CUSTOMER_PROFILE },
  ],
  platform_admin: [
    { key: 'admin', label: '平台', icon: 'admin', url: '/pages/admin/dashboard/dashboard' },
    { key: 'proxy', label: '代下单', icon: 'orders', url: PROXY_ORDER },
    { key: 'profile', label: '我的', icon: 'profile', url: CUSTOMER_PROFILE },
  ],
  tech_support: [
    { key: 'support', label: '保障', icon: 'admin', url: '/pages/support/dashboard/dashboard' },
    { key: 'profile', label: '我的', icon: 'profile', url: CUSTOMER_PROFILE },
  ],
  finance: [
    { key: 'finance', label: '财务', icon: 'earnings', url: '/pages/finance/dashboard/dashboard' },
    { key: 'profile', label: '我的', icon: 'profile', url: CUSTOMER_PROFILE },
  ],
};

const ACTIVE_BY_ROUTE = {
  'pages/customer/order/order': CUSTOMER_HOME,
  'pages/customer/pay/pay': CUSTOMER_ORDERS,
  'pages/repairer/detail/detail': REPAIRER_JOBS,
  'pages/staff/proxy-order/proxy-order': PROXY_ORDER,
};

function normalizeRoute(route) {
  return route ? `/${String(route).replace(/^\/+/, '')}` : '';
}

function currentRoute() {
  const pages = getCurrentPages();
  const page = pages[pages.length - 1];
  return page ? page.route : '';
}

function iconPath(icon, active) {
  return `${ICON_BASE}/${icon}${active ? '-active' : ''}.png`;
}

Component({
  data: {
    visible: false,
    items: [],
  },

  lifetimes: {
    attached() {
      this.refresh();
    },
  },

  pageLifetimes: {
    show() {
      this.refresh();
    },
  },

  methods: {
    refresh() {
      const token = wx.getStorageSync('token');
      const user = wx.getStorageSync('userInfo') || {};
      const businessRole = role.getBusinessRole(user);
      const menu = MENU_BY_ROLE[businessRole] || MENU_BY_ROLE.customer;
      const route = currentRoute();
      const activeUrl = ACTIVE_BY_ROUTE[route] || normalizeRoute(route);
      const items = menu.map((item) => {
        const active = item.url === activeUrl;
        return {
          ...item,
          active,
          stateText: active ? '当前' : '',
          ariaLabel: `${item.label}${active ? '，当前页面' : ''}`,
          iconSrc: iconPath(item.icon, active),
        };
      });

      this.setData({
        visible: Boolean(token && items.length),
        items,
      });
    },

    handleTap(e) {
      const url = e.currentTarget.dataset.url;
      if (!url) return;
      const target = normalizeRoute(url);
      const current = normalizeRoute(currentRoute());
      if (target === current) return;

      wx.redirectTo({
        url,
        fail: () => wx.reLaunch({ url }),
      });
    },
  },
});
