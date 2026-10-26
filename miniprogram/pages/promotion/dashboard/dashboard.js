const api = require('../../../utils/api');
const share = require('../../../utils/share');
const statusStyle = require('../../../utils/status-style');

Page({
  ...share.create({ title: '立即修｜推广工作台' }),

  data: {
    loading: true,
    loadFailed: false,
    customers: [],
    profits: [],
    stats: { customers: 0, profits: 0, pending: 0, settled: 0, commission: '0.00', balance: '0.00' },
    focusHint: {
      title: '暂无客户',
      desc: '推广客户会显示',
    },
    profitStatusMap: {
      pending: '待结算',
      settled: '已结算',
      paid: '已打款',
      cancelled: '已取消',
    },
  },

  onShow() {
    share.enable();
    if (!wx.getStorageSync('userInfo')) {
      wx.reLaunch({ url: '/pages/customer/home/home' });
      return;
    }
    this.loadData();
  },

  async loadData() {
    this.setData({ loading: true, loadFailed: false });
    try {
      const userInfo = wx.getStorageSync('userInfo');
      const [users, profitsRaw, wallet] = await Promise.all([
        api.get('/api/v1/users?limit=100').catch(() => []),
        api.get(`/api/v1/finance/profit/user/${userInfo.id}?limit=100`).catch(() => []),
        api.get(`/api/v1/wallet/balance/${userInfo.id}`).catch(() => ({})),
      ]);
      const customers = users
        .filter(item => item.promotion_manager_id === userInfo.id)
        .map(item => this.formatCustomer(item));
      const profits = profitsRaw.map(item => ({
        ...item,
        amountText: Number(item.amount || 0).toFixed(2),
        statusText: this.data.profitStatusMap[item.status] || item.status || '待结算',
        statusTone: statusStyle.financeStatusTone(item.status),
        nextStep: this.profitNextStep(item.status),
      }));
      const commission = profits.reduce((sum, item) => sum + Number(item.amount || 0), 0);
      const stats = {
        customers: customers.length,
        profits: profits.length,
        pending: profits.filter(item => item.status === 'pending').length,
        settled: profits.filter(item => ['settled', 'paid'].includes(item.status)).length,
        commission: commission.toFixed(2),
        balance: Number(wallet.available_balance || wallet.balance || 0).toFixed(2),
      };
      this.setData({
        customers,
        profits,
        stats,
        focusHint: this.buildFocusHint(customers, profits, stats),
        loading: false,
      });
    } catch (e) {
      this.setData({ loading: false, loadFailed: true });
      wx.showToast({ title: e.message || '加载失败', icon: 'none' });
    }
  },

  formatCustomer(item) {
    return {
      ...item,
      displayName: item.name || `客户 #${item.id}`,
      phoneText: item.phone || '未绑定手机号',
      nextStep: {
        title: '等待首单',
        desc: '首单后结算',
      },
    };
  },

  buildFocusHint(customers, profits, stats) {
    const pending = profits.filter(item => item.status === 'pending');
    const payable = Number(stats.balance || 0);
    if (payable > 0) {
      return {
        title: '可提现',
        desc: `¥${stats.balance} 可提现`,
      };
    }
    if (pending.length) {
      return {
        title: '待结算',
        desc: `${pending.length} 笔待结算`,
      };
    }
    if (!customers.length) {
      return {
        title: '暂无客户',
        desc: '推广客户会显示',
      };
    }
    if (!profits.length) {
      return {
        title: '等待首单',
        desc: '首单后结算',
      };
    }
    return {
      title: '推广稳定',
      desc: '查看客户和佣金',
    };
  },

  profitNextStep(status) {
    const map = {
      pending: { title: '等待结算', desc: '结算后入账' },
      settled: { title: '可提现', desc: '到钱包提现' },
      paid: { title: '已打款', desc: '查看流水' },
      cancelled: { title: '已取消', desc: '不再结算' },
    };
    return map[status] || { title: '查看佣金', desc: '跟进入账' };
  },

  goCustomer() {
    wx.redirectTo({ url: '/pages/staff/proxy-order/proxy-order' });
  },

  onPullDownRefresh() {
    this.loadData().then(() => wx.stopPullDownRefresh());
  },
});
