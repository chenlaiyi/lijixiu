// pages/customer/pay/pay.js
const api = require('../../../utils/api');
const share = require('../../../utils/share');
const serviceBill = require('../../../utils/service-bill');

const STATUS_MAP = {
  bill_submitted: '待确认',
  wait_payment: '待支付',
  paid: '已支付',
  paid_pending_review: '待审核',
  completed: '已完成',
};

function callWx(method, options = {}) {
  return new Promise((resolve, reject) => {
    if (!wx[method]) {
      reject(new Error(`${method} 不支持`));
      return;
    }
    wx[method]({
      ...options,
      success: resolve,
      fail: reject,
    });
  });
}

Page({
  ...share.create({
    title: '立即修｜支付',
  }),

  data: {
    orderId: null,
    order: null,
    bill: null,
    billItems: [],
    paying: false,
    loading: true,
    amount: 0,
    orderStatusText: '待支付',
    errorText: '',
    payErrorText: '',
  },

  onLoad(options) {
    share.enable();
    const orderId = options.orderId || options.id;
    if (orderId) {
      this.setData({ orderId: parseInt(orderId) });
      this.loadOrder();
    } else {
      this.setData({ loading: false, errorText: '缺少订单编号' });
    }
  },

  async loadOrder() {
    this.setData({ loading: true, errorText: '', payErrorText: '' });
    try {
      let order = await api.get(`/api/v1/orders/${this.data.orderId}`);
      if (order && order.status === 'bill_submitted') {
        await api.post(`/api/v1/orders/${this.data.orderId}/service-bill/confirm`);
        order = await api.get(`/api/v1/orders/${this.data.orderId}`);
      }
      const bill = await api.get(`/api/v1/orders/${this.data.orderId}/service-bill/latest`).catch(() => null);
      const billItems = this.parseBillItems(bill);
      const totalAmount = Math.max(
        Number(order.price || 0),
        Number((bill && bill.amount) || 0),
      );
      const amount = Math.max(0, totalAmount - Number(order.paid_amount || 0)).toFixed(2);
      const user = wx.getStorageSync('userInfo') || {};
      this.setData({
        order: order || null,
        bill,
        billItems,
        amount,
        orderStatusText: STATUS_MAP[order.status] || order.status || '待支付',
        loading: false,
        isThirdPartyPayer: Boolean(user.id && user.id !== order.customer_id),
      });
    } catch (e) {
      this.setData({
        order: null,
        loading: false,
        errorText: e.message || '加载失败',
      });
    }
  },

  parseBillItems(bill) {
    return serviceBill.parseItems(bill);
  },

  async syncPayment(payOrderId) {
    try {
      await api.post(`/api/v1/payment/order/${payOrderId}/wechat-sync`, {});
    } catch (e) {
      // 微信通知通常会异步到达；主动同步失败时不阻塞用户返回订单页。
    }
  },

  async ensureWechatPayReady() {
    const status = await api.get('/api/v1/payment/wechat/config-status');
    if (status && status.ready) return true;
    const issues = (status && Array.isArray(status.issues)) ? status.issues : [];
    const missingSecret = !status || !status.app_secret_configured;
    const message = missingSecret
      ? '微信支付暂不可用'
      : (issues[0] || '微信支付暂不可用');
    throw new Error(message);
  },

  /** 微信支付 */
  async doPay() {
    if (!this.data.order) return;
    const amount = Number(this.data.amount || 0);
    if (!amount || amount <= 0) {
      this.setData({ payErrorText: '金额无效，返回后重试' });
      wx.showToast({ title: '支付金额无效', icon: 'none' });
      return;
    }
    this.setData({ paying: true, payErrorText: '' });
    try {
      await this.ensureWechatPayReady();
      const loginRes = await callWx('login');
      const payer = wx.getStorageSync('userInfo') || {};
      const payRes = await api.post('/api/v1/payment/create', {
        order_id: this.data.orderId,
        user_id: payer.id,
        amount,
        provider: 'wechat',
        js_code: loginRes.code,
      });
      if (!payRes.payment_params) {
        throw new Error('微信支付参数生成失败');
      }
      await callWx('requestPayment', {
        ...payRes.payment_params,
      });
      await this.syncPayment(payRes.pay_order_id);
      wx.showToast({ title: '支付成功', icon: 'success' });
      setTimeout(() => {
        wx.redirectTo({ url: '/pages/customer/orders/orders' });
      }, 1500);
    } catch (e) {
      const msg = String((e && (e.errMsg || e.message)) || '');
      if (msg.indexOf('cancel') !== -1 || msg.indexOf('取消') !== -1) {
        this.setData({ payErrorText: '支付已取消，订单仍待支付' });
        wx.showToast({ title: '已取消支付', icon: 'none' });
      } else {
        const payErrorText = e.message || '支付失败，请重试';
        this.setData({ payErrorText });
        wx.showToast({ title: payErrorText, icon: 'none' });
      }
    } finally {
      this.setData({ paying: false });
    }
  },

  retryLoad() {
    if (!this.data.orderId) {
      this.goOrders();
      return;
    }
    this.loadOrder();
  },

  goOrders() {
    wx.redirectTo({ url: '/pages/customer/orders/orders' });
  },
});
