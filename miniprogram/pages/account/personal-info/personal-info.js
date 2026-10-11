const api = require('../../../utils/api');
const role = require('../../../utils/role');

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
    roleListText: '',
    roleCount: 1,
    canSwitchRole: false,
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
    const options = role.roleOptions(user);
    this.setData({
      userInfo: user,
      name: user.name || '',
      phoneText: maskPhone(user.phone),
      // 多角色:账号角色一行显示全部关联角色,当前身份单独标注
      roleText: options.map((item) => (item.active ? `${item.label}（当前）` : item.label)).join(' · ') || '客户',
      roleListText: role.roleText(user),
      roleCount: options.length,
      canSwitchRole: options.length > 1,
      accountIdText: user.id ? String(user.id) : '-',
      loading: false,
    });
  },

  /** 多角色账号:直接在这里切换当前身份 */
  switchRole() {
    const user = this.data.userInfo || wx.getStorageSync('userInfo') || {};
    const options = role.roleOptions(user);
    if (options.length < 2) {
      wx.showToast({ title: '当前账号只有一个角色', icon: 'none' });
      return;
    }
    wx.showActionSheet({
      itemList: options.map((item) => (item.active ? `${item.label}（当前）` : item.label)),
      success: async (res) => {
        const picked = options[res.tapIndex];
        if (!picked || picked.active) return;
        wx.showLoading({ title: '切换中', mask: true });
        try {
          const latest = await api.post(`/api/v1/users/${user.id}/switch-active-role`, {
            business_role: picked.value,
          });
          const merged = Object.assign({}, user, latest, {
            business_roles: latest.business_roles || user.business_roles,
            active_business_role: latest.active_business_role || picked.value,
            business_role: latest.business_role || user.business_role,
          });
          wx.setStorageSync('userInfo', merged);
          const app = getApp();
          if (app && app.globalData) {
            app.globalData.userInfo = merged;
            app.globalData.role = role.getBusinessRole(merged);
          }
          wx.hideLoading();
          this.applyUser(merged);
          wx.showToast({ title: `已切换为${role.roleLabel(picked.value)}`, icon: 'none' });
        } catch (error) {
          wx.hideLoading();
          wx.showToast({ title: error.message || '切换失败', icon: 'none' });
        }
      },
      fail: () => {},
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
