// pages/customer/profile/profile.js
const auth = require('../../../utils/auth');
const share = require('../../../utils/share');
const role = require('../../../utils/role');

function formatMoney(value) {
  return Number(value || 0).toFixed(2);
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
    roleCount: 1,
    showRoleSwitch: false,
    switchingRole: false,
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
    const businessRoles = role.getBusinessRoles(userInfo || {});
    // 多角色:身份可切换时按钮文案用「切换身份」,并显示全部角色标签
    const showRoleSwitch = Boolean(userInfo) && businessRoles.length > 1;
    // 钱包只对能产生收益的角色有意义(师傅 / 兜底)
    const walletRoles = ['repairer', 'second_receiver'];
    const showWallet = Boolean(userInfo) && role.hasAnyBusinessRole(userInfo, walletRoles);
    this.setData({
      ready: true,
      userInfo,
      userName: userInfo && userInfo.name ? userInfo.name : '未设置',
      phoneText: userInfo && userInfo.phone ? userInfo.phone : '未绑定手机号',
      roleLabel: role.roleText(userInfo || {}),
      roleCount: businessRoles.length,
      showRoleSwitch,
      showWallet,
      showCustomerServices: businessRoles.indexOf('customer') >= 0,
      showWorkbench: Boolean(userInfo) && businessRole !== 'customer',
      workbenchLabel: role.workbenchLabel(businessRole),
      workbenchIcon: workbenchIcon(businessRole),
      accountHint: accountHint(businessRole),
    });
    if (showWallet && userInfo && userInfo.id) this.loadWallet(userInfo.id);
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

  /**
   * 切换当前身份(多角色账号)。
   *
   * 全局生效:切换后首页/底部导航/工作台都按新身份走 —— 所以直接跳新身份
   * 的入口页,而不是只更新一个标签。选择范围仅限后端配好的关联角色。
   */
  switchRole() {
    const userInfo = wx.getStorageSync('userInfo') || {};
    const options = role.roleOptions(userInfo);
    if (options.length < 2) {
      wx.showToast({ title: '当前账号只有一个角色', icon: 'none' });
      return;
    }
    if (this.data.switchingRole) return;

    wx.showActionSheet({
      itemList: options.map((item) => (item.active ? `${item.label}（当前）` : item.label)),
      success: (res) => {
        const picked = options[res.tapIndex];
        if (!picked || picked.active) return;
        this.applyRoleSwitch(picked.value);
      },
      fail: () => {},
    });
  },

  async applyRoleSwitch(roleValue) {
    const userInfo = wx.getStorageSync('userInfo') || {};
    if (!userInfo.id) {
      wx.showToast({ title: '请先登录', icon: 'none' });
      return;
    }
    this.setData({ switchingRole: true });
    wx.showLoading({ title: '切换中', mask: true });
    try {
      const api = require('../../../utils/api');
      const latest = await api.post(`/api/v1/users/${userInfo.id}/switch-active-role`, {
        business_role: roleValue,
      });
      const merged = Object.assign({}, userInfo, latest, {
        business_roles: latest.business_roles || userInfo.business_roles,
        active_business_role: latest.active_business_role || roleValue,
        business_role: latest.business_role || userInfo.business_role,
      });
      wx.setStorageSync('userInfo', merged);
      const app = getApp();
      if (app && app.globalData) {
        app.globalData.userInfo = merged;
        app.globalData.role = role.getBusinessRole(merged);
      }
      wx.hideLoading();
      wx.showToast({ title: `已切换为${role.roleLabel(roleValue)}`, icon: 'none' });
      const url = role.getEntryPathForRole(roleValue);
      setTimeout(() => {
        wx.redirectTo({ url, fail: () => wx.reLaunch({ url }) });
      }, 400);
    } catch (error) {
      wx.hideLoading();
      wx.showToast({ title: error.message || '切换失败', icon: 'none' });
    } finally {
      this.setData({ switchingRole: false });
    }
  },

  goWorkbench() {
    const userInfo = wx.getStorageSync('userInfo');
    const url = role.getEntryPath(userInfo || {});
    wx.redirectTo({ url, fail: () => wx.reLaunch({ url }) });
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
    wx.reLaunch({ url: '/pages/customer/home/home' });
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
