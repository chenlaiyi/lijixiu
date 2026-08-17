/**
 * 立即修小程序 - 入口文件
 * 单小程序多角色：登录后根据 user.role 切换用户端/师傅端
 */
const api = require('./utils/api');

App({
  globalData: {
    userInfo: null,
    token: '',
    role: '',
    baseURL: 'https://x.iddg.cn',
    navMetrics: null,
  },

  onLaunch() {
    // 尝试恢复登录态
    const token = wx.getStorageSync('token');
    const cachedUser = wx.getStorageSync('userInfo');
    if (token && cachedUser) {
      this.globalData.token = token;
      this.globalData.userInfo = cachedUser;
      this.globalData.role = cachedUser.business_role || cachedUser.role;
      api.setToken(token);
    }
  },

  /**
   * 登录：wx.login → 后端换取 token
   */
  async login() {
    const { code } = await wx.login();
    const res = await api.post('/api/v1/auth/wechat-login', { code });
    const { token, user } = res;

    this.globalData.token = token;
    this.globalData.userInfo = user;
    this.globalData.role = user.business_role || user.role;

    wx.setStorageSync('token', token);
    wx.setStorageSync('userInfo', user);
    api.setToken(token);

    return user;
  },

  /** 切换角色（师傅也可能是用户） */
  switchRole(role) {
    this.globalData.role = role;
    // 触发页面重新渲染 tabbar
  },

  getNavMetrics() {
    if (this.globalData.navMetrics) return this.globalData.navMetrics;

    let statusBarHeight = 24;
    let windowWidth = 375;
    try {
      const windowInfo = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
      statusBarHeight = windowInfo.statusBarHeight || statusBarHeight;
      windowWidth = windowInfo.windowWidth || windowWidth;
    } catch (e) {}

    let capsuleBottom = statusBarHeight + 40;
    let capsuleLeft = windowWidth;
    try {
      const capsule = wx.getMenuButtonBoundingClientRect && wx.getMenuButtonBoundingClientRect();
      if (capsule && capsule.bottom) {
        capsuleBottom = capsule.bottom;
        capsuleLeft = capsule.left || capsuleLeft;
      }
    } catch (e) {}

    this.globalData.navMetrics = {
      statusBarHeight,
      capsuleBottom,
      customPageTop: capsuleBottom + 12,
      capsuleRightReserve: Math.max(0, windowWidth - capsuleLeft + 12),
    };
    return this.globalData.navMetrics;
  },

  /** 退出登录 */
  logout() {
    wx.removeStorageSync('token');
    wx.removeStorageSync('userInfo');
    this.globalData.token = '';
    this.globalData.userInfo = null;
    this.globalData.role = '';
    wx.reLaunch({ url: '/pages/login/login' });
  }
});
