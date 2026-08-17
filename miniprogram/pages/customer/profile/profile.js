// pages/customer/profile/profile.js
const auth = require('../../../utils/auth');
const share = require('../../../utils/share');
const role = require('../../../utils/role');

function formatMoney(value) {
  return Number(value || 0).toFixed(2);
}

function roleLabel(userRole) {
  const map = {
    customer: '客户',
    repairer: '师傅',
    store: '店长',
    city: '城市',
    promotion: '推广',
    second: '兜底',
    admin: '平台',
    store_manager: '店长',
    city_manager: '城市',
    promotion_manager: '推广',
    second_receiver: '兜底',
    tech_support: '技术支持',
    finance: '财务',
    platform_admin: '平台',
  };
  return map[userRole] || '客户';
}

function workbenchLabel(businessRole) {
  const map = {
    repairer: '师傅工作台',
    second_receiver: '兜底工单',
    store_manager: '门店工作台',
    city_manager: '城市工作台',
    promotion_manager: '推广工作台',
    tech_support: '服务保障工作台',
    finance: '财务工作台',
    platform_admin: '平台工作台',
  };
  return map[businessRole] || '工作台';
}

function workbenchIcon(businessRole) {
  const map = {
    repairer: '/assets/ui/repairer.png',
    second_receiver: '/assets/tabbar/second.png',
    store_manager: '/assets/tabbar/store.png',
    city_manager: '/assets/tabbar/city.png',
    promotion_manager: '/assets/tabbar/promotion.png',
    tech_support: '/assets/ui/bill-check.png',
    finance: '/assets/ui/wallet.png',
    platform_admin: '/assets/ui/admin.png',
  };
  return map[businessRole] || '/assets/ui/admin.png';
}

function accountHint(businessRole) {
  const map = {
    repairer: {
      icon: '/assets/ui/repairer.png',
      title: '师傅工作台',
      desc: '接单和收益',
      actionText: '进入',
    },
    second_receiver: {
      icon: '/assets/tabbar/second.png',
      title: '兜底工单',
      desc: '待接和服务',
      actionText: '进入',
    },
    store_manager: {
      icon: '/assets/tabbar/store.png',
      title: '门店工作台',
      desc: '派单和计薪',
      actionText: '进入',
    },
    city_manager: {
      icon: '/assets/tabbar/city.png',
      title: '城市工作台',
      desc: '门店和工单',
      actionText: '进入',
    },
    promotion_manager: {
      icon: '/assets/tabbar/promotion.png',
      title: '推广工作台',
      desc: '客户和佣金',
      actionText: '进入',
    },
    tech_support: {
      icon: '/assets/ui/bill-check.png',
      title: '服务保障工作台',
      desc: '资料核验和售后',
      actionText: '进入',
    },
    finance: {
      icon: '/assets/ui/wallet.png',
      title: '财务工作台',
      desc: '支付、退款和对账',
      actionText: '进入',
    },
    platform_admin: {
      icon: '/assets/ui/admin.png',
      title: '平台工作台',
      desc: '工单和提现',
      actionText: '进入',
    },
  };
  return map[businessRole] || {
      icon: '/assets/ui/receipt.png',
      title: '我的订单',
      desc: '订单和保修',
      actionText: '查看订单',
  };
}

Page({
  ...share.create({
    title: '立即修｜我的',
  }),

  data: {
    ready: false,
    userInfo: null,
    userName: '未设置',
    phoneText: '未绑定手机号',
    roleLabel: '客户',
    walletLoading: false,
    walletError: false,
    wallet: {
      available_balance: 0,
      total_income: 0,
      frozen_balance: 0,
    },
    walletView: {
      available_balance: '0.00',
      total_income: '0.00',
      frozen_balance: '0.00',
    },
    showWallet: false,
    showCustomerServices: false,
    showWorkbench: false,
    workbenchLabel: '工作台',
    workbenchIcon: '/assets/ui/admin.png',
    accountHint: accountHint('customer'),
  },

  onShow() {
    share.enable();
    const userInfo = wx.getStorageSync('userInfo');
    const businessRole = role.getBusinessRole(userInfo || {});
    const walletRoles = ['repairer', 'second_receiver', 'store_manager', 'city_manager', 'promotion_manager'];
    this.setData({
      ready: true,
      userInfo,
      userName: userInfo && userInfo.name ? userInfo.name : '未设置',
      phoneText: userInfo && userInfo.phone ? userInfo.phone : '未绑定手机号',
      roleLabel: roleLabel(businessRole),
      showWallet: Boolean(userInfo && walletRoles.includes(businessRole)),
      showCustomerServices: Boolean(userInfo && businessRole === 'customer'),
      showWorkbench: Boolean(userInfo && businessRole !== 'customer'),
      workbenchLabel: workbenchLabel(businessRole),
      workbenchIcon: workbenchIcon(businessRole),
      accountHint: accountHint(businessRole),
    });
    if (userInfo && walletRoles.includes(businessRole)) this.loadWallet(userInfo.id);
  },

  async loadWallet(userId) {
    this.setData({ walletLoading: true, walletError: false });
    try {
      const api = require('../../../utils/api');
      const wallet = await api.get(`/api/v1/wallet/balance/${userId}`);
      const safeWallet = {
        available_balance: wallet && wallet.available_balance ? wallet.available_balance : 0,
        total_income: wallet && wallet.total_income ? wallet.total_income : 0,
        frozen_balance: wallet && wallet.frozen_balance ? wallet.frozen_balance : 0,
      };
      this.setData({
        wallet: safeWallet,
        walletView: {
          available_balance: formatMoney(safeWallet.available_balance),
          total_income: formatMoney(safeWallet.total_income),
          frozen_balance: formatMoney(safeWallet.frozen_balance),
        },
        walletLoading: false,
      });
    } catch {
      this.setData({ walletLoading: false, walletError: true });
    }
  },

  retryWallet() {
    const userInfo = this.data.userInfo || wx.getStorageSync('userInfo');
    if (!userInfo || !userInfo.id) {
      wx.showToast({ title: '请先登录', icon: 'none' });
      return;
    }
    this.loadWallet(userInfo.id);
  },

  /** 切换为师傅身份 */
  switchToRepairer() {
    const app = getApp();
    app.globalData.role = 'repairer';
    // 更新 storage 中的 role
    const userInfo = wx.getStorageSync('userInfo');
    if (userInfo) {
      userInfo.role = 'repairer';
      wx.setStorageSync('userInfo', userInfo);
    }
    wx.redirectTo({ url: role.getEntryPath(userInfo || { role: 'repairer' }) });
  },

  goWorkbench() {
    const userInfo = wx.getStorageSync('userInfo');
    wx.redirectTo({ url: role.getEntryPath(userInfo || {}) });
  },

  switchToAdmin() {
    const app = getApp();
    app.globalData.role = 'admin';
    const userInfo = wx.getStorageSync('userInfo');
    if (userInfo) {
      userInfo.role = 'admin';
      wx.setStorageSync('userInfo', userInfo);
    }
    wx.redirectTo({ url: role.getEntryPath(userInfo || { role: 'admin' }) });
  },

  /** 查看我的钱包 */
  goWallet() {
    wx.navigateTo({ url: '/pages/repairer/earnings/earnings' });
  },

  goOrders() {
    wx.navigateTo({ url: '/pages/customer/orders/orders' });
  },

  goAddresses() { wx.navigateTo({ url: '/pages/customer/addresses/addresses' }); },
  goWarranties() { wx.navigateTo({ url: '/pages/customer/warranties/warranties' }); },

  goPersonalInfo() {
    wx.navigateTo({ url: '/pages/account/personal-info/personal-info' });
  },

  goSettings() {
    wx.navigateTo({ url: '/pages/account/settings/settings' });
  },

  goHome() {
    wx.redirectTo({ url: '/pages/customer/home/home' });
  },

  goLogin() {
    wx.reLaunch({ url: '/pages/login/login' });
  },

  /** 退出 */
  handleLogout() {
    wx.showModal({
      title: '确认退出',
      content: '退出后需重新登录',
      success: (res) => {
        if (res.confirm) auth.logout();
      }
    });
  },
});
