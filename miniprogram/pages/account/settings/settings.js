const auth = require('../../../utils/auth');

function maskPhone(phone) {
  const value = String(phone || '');
  if (value.length < 7) return value || '未绑定';
  return `${value.slice(0, 3)}****${value.slice(-4)}`;
}

Page({
  data: {
    phoneText: '未绑定',
    versionText: '体验版',
  },

  onShow() {
    const user = wx.getStorageSync('userInfo');
    if (!user) {
      wx.reLaunch({ url: '/pages/login/login' });
      return;
    }
    let versionText = '体验版';
    try {
      const info = wx.getAccountInfoSync();
      const miniProgram = info && info.miniProgram ? info.miniProgram : {};
      versionText = miniProgram.version || (miniProgram.envVersion === 'release' ? '正式版' : '体验版');
    } catch (error) {}
    this.setData({ phoneText: maskPhone(user.phone), versionText });
  },

  goPersonalInfo() {
    wx.navigateTo({ url: '/pages/account/personal-info/personal-info' });
  },

  openSystemSettings() {
    wx.openSetting({
      fail: () => wx.showToast({ title: '暂时无法打开系统权限', icon: 'none' }),
    });
  },

  openPrivacyContract() {
    wx.navigateTo({
      url: '/pages/common/agreement/agreement?tab=privacy',
      fail: () => {
        if (typeof wx.openPrivacyContract === 'function') {
          wx.openPrivacyContract({ fail: () => wx.showToast({ title: '隐私指引暂时无法打开', icon: 'none' }) });
        } else {
          wx.showToast({ title: '当前版本暂不支持查看', icon: 'none' });
        }
      },
    });
  },

  openTerms() {
    wx.navigateTo({ url: '/pages/common/agreement/agreement?tab=terms' });
  },

  showAbout() {
    wx.showModal({
      title: '立即修',
      content: `上门维修服务平台\n当前版本：${this.data.versionText}`,
      showCancel: false,
      confirmText: '知道了',
    });
  },

  handleLogout() {
    wx.showModal({
      title: '确认退出',
      content: '退出后需重新登录',
      confirmColor: '#b42318',
      success: (result) => {
        if (result.confirm) auth.logout();
      },
    });
  },
});
