const api = require('../../../utils/api');

Page({
  data: { token: '', access: null, loading: true, claiming: false, resultMessage: '' },
  onLoad(options) {
    const token = decodeURIComponent(options.scene || options.token || '');
    this.setData({ token });
    if (token) wx.setStorageSync('pendingAccessToken', token);
    this.loadAccess();
  },
  onShow() {
    if (!this.data.access && this.data.token) this.loadAccess();
  },
  async loadAccess() {
    if (!this.data.token) { this.setData({ loading: false, resultMessage: '二维码信息不完整' }); return; }
    try {
      const access = await api.get(`/api/v1/business/access/${this.data.token}`);
      this.setData({ access });
      wx.setNavigationBarTitle({ title: access.purpose === 'payment' ? '订单付款' : '订单确认' });
    } catch (e) {
      this.setData({ resultMessage: e.message || '二维码已失效' });
    } finally { this.setData({ loading: false }); }
  },
  goLogin() {
    wx.setStorageSync('pendingAccessToken', this.data.token);
    wx.navigateTo({ url: '/pages/login/login?intent=login' });
  },
  async claimOrder() {
    const user = wx.getStorageSync('userInfo');
    if (!user) { this.goLogin(); return; }
    this.setData({ claiming: true });
    try {
      const result = await api.post('/api/v1/business/orders/claim', {
        token: this.data.token,
        user_id: user.id,
      });
      this.setData({ resultMessage: result.message });
      if (result.action === 'claimed') wx.removeStorageSync('pendingAccessToken');
    } catch (e) {
      this.setData({ resultMessage: e.message || '认领失败，请稍后再试' });
    } finally { this.setData({ claiming: false }); }
  },
  goPay() {
    const user = wx.getStorageSync('userInfo');
    if (!user) { this.goLogin(); return; }
    wx.navigateTo({ url: `/pages/customer/pay/pay?id=${this.data.access.order_id}&proxyToken=${encodeURIComponent(this.data.token)}` });
  },
  openOrder() {
    wx.navigateTo({ url: `/pages/customer/detail/detail?id=${this.data.access.order_id}` });
  },
  onShareAppMessage() {
    return {
      title: this.data.access && this.data.access.purpose === 'payment' ? '请协助支付服务订单' : '请确认您的服务订单',
      path: `/pages/proxy/access/access?token=${encodeURIComponent(this.data.token)}`,
    };
  },
  onShareTimeline() {
    return { title: '立即修服务订单', query: `token=${encodeURIComponent(this.data.token)}` };
  },
});
