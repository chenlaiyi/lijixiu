const api = require('../../../utils/api');
const auth = require('../../../utils/auth');
const share = require('../../../utils/share');

const PAYMENT_STATUS_MAP = {
  pending: { text: '待支付', tone: 'tone-warning' },
  paid: { text: '已支付', tone: 'tone-success' },
  failed: { text: '失败', tone: 'tone-danger' },
  refunded: { text: '已退款', tone: 'tone-neutral' },
  partially_refunded: { text: '部分退款', tone: 'tone-warning' },
  closed: { text: '已关闭', tone: 'tone-neutral' },
};

function formatStatus(status, map) {
  if (!status) return { text: '', tone: 'tone-neutral' };
  return map[status] || { text: status, tone: 'tone-neutral' };
}

Page({
  ...share.create({ title: '立即修｜财务工作台' }),
  data: {
    payments: [],
    refunds: [],
    wages: [],
    payroll: { items: [] },
    loading: true,
    errorText: '',
    totals: { paid: '0.00', refund: '0.00', wage: '0.00' },
  },
  onShow() { share.enable(); this.load(); },
  onPullDownRefresh() { this.load().finally(() => wx.stopPullDownRefresh()); },
  async load() {
    this.setData({ loading: true, errorText: '' });
    try {
      const [payments, refunds, wages, payroll] = await Promise.all([
        api.get('/api/v1/payment/list?limit=100'),
        api.get('/api/v1/payment/refunds?limit=100'),
        api.get('/api/v1/business/wages'),
        api.get('/api/v1/business/payroll'),
      ]);
      const sum = (items, statuses) => (items || [])
        .filter(item => !statuses || statuses.includes(item.status))
        .reduce((n, item) => n + Number(item.amount || 0), 0)
        .toFixed(2);
      const paymentList = (payments || []).map(item => {
        const meta = formatStatus(item.status, PAYMENT_STATUS_MAP);
        return { ...item, statusText: meta.text, statusTone: meta.tone };
      });
      this.setData({
        payments: paymentList,
        refunds: refunds || [],
        wages: wages || [],
        payroll: payroll || { items: [] },
        totals: {
          paid: sum(paymentList, ['paid', 'partially_refunded']),
          refund: sum(refunds, ['success']),
          wage: sum(wages, ['paid']),
        },
      });
    } catch (e) {
      this.setData({ errorText: e.message || '加载失败，请稍后再试' });
    } finally {
      this.setData({ loading: false });
    }
  },
  async reconcile() {
    wx.showLoading({ title: '对账中' });
    try {
      const r = await api.post('/api/v1/admin/reconcile/run', {});
      wx.hideLoading();
      wx.showModal({
        title: '对账完成',
        content: `正常 ${r.ok || 0}，异常 ${r.mismatch || 0}`,
        showCancel: false,
      });
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message || '对账失败', icon: 'none' });
    }
  },
  logout() { auth.logout(); },
});
