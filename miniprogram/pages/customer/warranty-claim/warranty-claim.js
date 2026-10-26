const api = require('../../../utils/api');

const REASONS = ['原故障再次出现', '维修项目异常', '材料或配件问题', '其他保修问题'];

Page({
  data: {
    orderId: 0,
    loading: true,
    loadFailed: false,
    submitting: false,
    certificate: null,
    reasonOptions: REASONS,
    reasonIndex: 0,
    description: '',
    errorText: '',
    existingTicket: null,
  },

  onLoad(options) {
    const orderId = Number(options.orderId || 0);
    this.setData({ orderId });
  },

  onShow() {
    if (!this.data.orderId) {
      this.setData({ loading: false, loadFailed: true, errorText: '缺少订单编号' });
      return;
    }
    this.loadData();
  },

  async loadData() {
    const user = wx.getStorageSync('userInfo');
    if (!user) {
      wx.reLaunch({ url: '/pages/customer/home/home' });
      return;
    }
    this.setData({ loading: true, loadFailed: false, errorText: '' });
    try {
      const [warranties, tickets] = await Promise.all([
        api.get('/api/v1/business/warranties', { customer_id: user.id }),
        api.get('/api/v1/support/tickets', { user_id: user.id }),
      ]);
      const certificate = (warranties || []).find(item => Number(item.order_id) === this.data.orderId);
      if (!certificate) throw new Error('没有找到该订单的保修凭证');

      const expiresAt = new Date(certificate.expires_at).getTime();
      if (certificate.status !== 'active' || (Number.isFinite(expiresAt) && expiresAt < Date.now())) {
        throw new Error('该保修凭证已过期');
      }
      if (!certificate.store_id) throw new Error('该订单缺少服务门店，请联系平台处理');

      const existingTicket = (tickets || []).find(ticket => (
        ticket.category === 'warranty'
        && Number(ticket.order_id) === this.data.orderId
        && ticket.status !== 'closed'
      )) || null;
      this.setData({ certificate, existingTicket, loading: false });
    } catch (error) {
      this.setData({
        loading: false,
        loadFailed: true,
        errorText: error.message || '保修信息加载失败',
      });
    }
  },

  onReasonChange(event) {
    this.setData({ reasonIndex: Number(event.detail.value || 0), errorText: '' });
  },

  onDescriptionInput(event) {
    this.setData({ description: event.detail.value, errorText: '' });
  },

  async submitClaim() {
    if (this.data.submitting || this.data.existingTicket) return;
    const user = wx.getStorageSync('userInfo');
    const certificate = this.data.certificate;
    const description = String(this.data.description || '').trim();
    if (!user || !certificate) {
      this.setData({ errorText: '保修信息无效，请重新进入' });
      return;
    }
    if (description.length < 5) {
      this.setData({ errorText: '请至少填写5个字的问题描述' });
      return;
    }

    const reason = REASONS[this.data.reasonIndex] || REASONS[0];
    this.setData({ submitting: true, errorText: '' });
    wx.showLoading({ title: '提交中' });
    try {
      const ticket = await api.post('/api/v1/support/tickets', {
        store_id: certificate.store_id,
        user_id: user.id,
        order_id: certificate.order_id,
        category: 'warranty',
        title: `保修申请｜${reason}`,
        content: `保修凭证：${certificate.certificate_no}\n问题类型：${reason}\n问题描述：${description}`,
      });
      wx.hideLoading();
      wx.showModal({
        title: '保修申请已提交',
        content: `申请编号 #${ticket.id}，门店和服务保障人员将跟进处理。`,
        showCancel: false,
        confirmText: '完成',
        success: () => wx.navigateBack(),
      });
    } catch (error) {
      wx.hideLoading();
      this.setData({ errorText: error.message || '提交失败，请稍后重试' });
    } finally {
      this.setData({ submitting: false });
    }
  },
});
