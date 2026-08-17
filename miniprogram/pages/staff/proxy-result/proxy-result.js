const api = require('../../../utils/api');
const role = require('../../../utils/role');

Page({
  data: { order: null, access: null, loading: true, errorText: '' },
  onLoad(options) { this.orderId = Number(options.id); this.refresh(); },
  async refresh() {
    this.setData({ loading: true, errorText: '' });
    try {
      const order = await api.get(`/api/v1/orders/${this.orderId}`);
      const purpose = order.status === 'wait_payment' ? 'payment' : 'claim';
      const user = wx.getStorageSync('userInfo') || {};
      const access = await api.post(`/api/v1/business/orders/${order.id}/access/${purpose}`, { created_by_user_id: user.id });
      access.imageUrl = api.resolveURL(access.code_url);
      this.setData({ order, access, errorText: '' });
    } catch (e) {
      this.setData({ errorText: e.message || '二维码生成失败' });
    } finally { this.setData({ loading: false }); }
  },
  goWorkbench() {
    const user = wx.getStorageSync('userInfo') || {};
    wx.redirectTo({ url: role.getEntryPath(user) });
  },
  onShareAppMessage() {
    const access = this.data.access;
    return access ? {
      title: access.purpose === 'payment' ? '请协助支付服务订单' : '请确认您的服务订单',
      path: `/pages/proxy/access/access?token=${encodeURIComponent(access.token)}`,
    } : { title: '立即修服务订单' };
  },
});
