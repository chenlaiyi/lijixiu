const api = require('../../../utils/api');
const role = require('../../../utils/role');

function roleLabel(value) {
  const labels = {
    customer: '客户',
    repairer: '师傅',
    second_receiver: '兜底师傅',
    store_manager: '店长',
    city_manager: '城市经理',
    promotion_manager: '推广经理',
    tech_support: '技术支持',
    finance: '财务',
    platform_admin: '管理员',
  };
  return labels[value] || '用户';
}

function maskPhone(phone) {
  const value = String(phone || '');
  if (value.length < 7) return value || '未绑定';
  return `${value.slice(0, 3)}****${value.slice(-4)}`;
}

Page({
  data: {
    loading: true,
    saving: false,
    userInfo: null,
    name: '',
    phoneText: '未绑定',
    roleText: '用户',
    accountIdText: '-',
    errorText: '',
  },

  onShow() {
    const user = wx.getStorageSync('userInfo');
    if (!user) {
      wx.reLaunch({ url: '/pages/login/login' });
      return;
    }
    this.applyUser(user);
    this.loadProfile();
  },

  applyUser(user) {
    this.setData({
      userInfo: user,
      name: user.name || '',
      phoneText: maskPhone(user.phone),
      roleText: roleLabel(role.getBusinessRole(user)),
      accountIdText: user.id ? String(user.id) : '-',
      loading: false,
    });
  },

  async loadProfile() {
    this.setData({ loading: true, errorText: '' });
    try {
      const user = await api.get('/api/v1/auth/me');
      wx.setStorageSync('userInfo', user);
      const app = getApp();
      if (app && app.globalData) app.globalData.userInfo = user;
      this.applyUser(user);
    } catch (error) {
      this.setData({
        loading: false,
        errorText: error.message || '个人信息加载失败',
      });
    }
  },

  onNameInput(event) {
    this.setData({ name: event.detail.value, errorText: '' });
  },

  async saveProfile() {
    if (this.data.saving) return;
    const name = String(this.data.name || '').trim();
    if (!name) {
      this.setData({ errorText: '请输入姓名' });
      return;
    }
    if (name.length > 50) {
      this.setData({ errorText: '姓名不能超过50个字' });
      return;
    }

    const user = this.data.userInfo;
    if (!user || !user.id) {
      this.setData({ errorText: '账号信息无效，请重新登录' });
      return;
    }

    this.setData({ saving: true, errorText: '' });
    try {
      const updated = await api.patch(`/api/v1/users/${user.id}`, { name });
      wx.setStorageSync('userInfo', updated);
      const app = getApp();
      if (app && app.globalData) app.globalData.userInfo = updated;
      this.applyUser(updated);
      wx.showToast({ title: '已保存', icon: 'success' });
    } catch (error) {
      this.setData({ errorText: error.message || '保存失败' });
    } finally {
      this.setData({ saving: false });
    }
  },
});
