const api = require('../../../utils/api');
const auth = require('../../../utils/auth');
const share = require('../../../utils/share');

function formatTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = n => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatWithdrawalStatus(status) {
  const map = {
    pending: { text: '财务审核中', className: 'waiting' },
    approved: { text: '已完成', className: 'success' },
    rejected: { text: '已退回', className: 'rejected' },
  };
  return map[status] || { text: status || '处理中', className: 'waiting' };
}

Page({
  ...share.create({ title: '立即修｜收益' }),

  data: {
    withdrawalTiming: '申请提交成功后 7 天内完成审核；审核通过后 7 天内到账。以上均为自然日。可在提现记录查看处理状态，超过时限未处理或未到账，请联系客服核实。',
    wallet: null,
    walletView: {
      available_balance: '0.00',
      total_income: '0.00',
      frozen_balance: '0.00',
    },
    ledger: [],
    withdrawals: [],
    loading: true,
    loadFailed: false,
    loadWarningText: '',
    canWithdraw: false,
    withdrawAmount: '',
    withdrawErrorText: '',
    withdrawing: false,
    isReviewExperience: false,
    userInfo: null,
    earningsHint: {
      title: '暂无可提现',
      desc: '审核后显示',
    },
  },

  async onShow() {
    share.enable();
    let userInfo = wx.getStorageSync('userInfo');
    if (!wx.getStorageSync('token') || !userInfo) {
      wx.reLaunch({ url: '/pages/customer/home/home' });
      return;
    }
    this.setData({
      userInfo,
      isReviewExperience: Boolean(wx.getStorageSync('reviewExperience')),
    });
    this.loadData();
  },

  async enterExperienceAccount() {
    const wxCode = await new Promise((resolve) => {
      wx.login({ success: resolve, fail: () => resolve({}) });
    });
    const user = await auth.login('18800000999:审核功能体验:repairer', {
      phone: '18800000999',
      name: '审核功能体验',
      role: 'repairer',
      wx_code: wxCode.code || undefined,
    });
    wx.setStorageSync('reviewExperience', true);
    return user;
  },

  async loadData() {
    this.setData({ loading: true, loadFailed: false, loadWarningText: '' });
    try {
      const userId = this.data.userInfo.id;
      const failures = [];
      const safeGet = async (url, fallback, label) => {
        try {
          return await api.get(url);
        } catch (e) {
          failures.push(label);
          return fallback;
        }
      };
      const [wallet, ledger, withdrawals] = await Promise.all([
        safeGet(`/api/v1/wallet/balance/${userId}`, null, '余额'),
        safeGet(`/api/v1/wallet/ledger/${userId}`, [], '流水'),
        safeGet(`/api/v1/wallet/withdrawals?user_id=${userId}&limit=10`, [], '提现记录'),
      ]);
      const criticalFailed = failures.includes('余额');
      const available = Number((wallet && wallet.available_balance) || 0);
      const currentAmount = Number(this.data.withdrawAmount || 0);
      const amountAllowed = currentAmount > 0
        && currentAmount <= available
        && (!this.data.isReviewExperience || currentAmount <= 5);
      const withdrawAmount = amountAllowed
        ? this.data.withdrawAmount
        : (available > 0 ? Math.min(1, available).toFixed(2) : '');
      this.setData({
        wallet,
        walletView: {
          available_balance: Number((wallet && wallet.available_balance) || 0).toFixed(2),
          total_income: Number((wallet && wallet.total_income) || 0).toFixed(2),
          frozen_balance: Number((wallet && wallet.frozen_balance) || 0).toFixed(2),
        },
        canWithdraw: available > 0,
        withdrawAmount,
        withdrawErrorText: '',
        ledger: (ledger || []).map(item => ({
          ...item,
          displayType: item.remark || item.type,
          created_at: formatTime(item.created_at),
          amountText: `${Number(item.amount || 0) >= 0 ? '+' : ''}¥${Number(item.amount || 0).toFixed(2)}`,
          amountClass: Number(item.amount || 0) >= 0 ? 'income' : 'outcome',
        })),
        withdrawals: (withdrawals || []).map(item => {
          const statusView = formatWithdrawalStatus(item.status);
          return {
            ...item,
            amountText: `¥${Number(item.amount || 0).toFixed(2)}`,
            created_at: formatTime(item.created_at),
            statusText: statusView.text,
            statusClass: statusView.className,
          };
        }),
        loadFailed: criticalFailed,
        loadWarningText: failures.length ? `${failures.join('、')}加载失败` : '',
        earningsHint: this.buildEarningsHint(wallet, criticalFailed, failures),
        loading: false,
      });
    } catch (e) {
      this.setData({ loading: false, loadFailed: true, loadWarningText: '' });
      wx.showToast({ title: e.message || '加载失败', icon: 'none' });
    }
  },

  buildEarningsHint(wallet, criticalFailed, failures) {
    if (criticalFailed) {
      return {
        title: '余额未加载',
        desc: '加载后提现',
      };
    }
    const available = Number((wallet && wallet.available_balance) || 0);
    const frozen = Number((wallet && wallet.frozen_balance) || 0);
    const total = Number((wallet && wallet.total_income) || 0);
    if (available > 0) {
      return {
        title: '可提现',
        desc: `¥${available.toFixed(2)} 可提现`,
      };
    }
    if (frozen > 0) {
      return {
        title: '等待门店审核',
        desc: `冻结 ¥${frozen.toFixed(2)}`,
      };
    }
    if (total > 0) {
      return {
        title: '查看历史收益',
        desc: '看流水',
      };
    }
    if (failures.length) {
      return {
        title: '部分数据未加载',
        desc: '点击重试',
      };
    }
    return {
      title: '暂无可提现',
      desc: '审核后显示',
    };
  },

  onWithdrawAmountInput(e) {
    this.setData({
      withdrawAmount: e.detail.value,
      withdrawErrorText: '',
    });
  },

  useAllBalance() {
    const available = Number((this.data.wallet && this.data.wallet.available_balance) || 0);
    if (available <= 0) return;
    if (this.data.isReviewExperience) {
      this.setData({ withdrawAmount: Math.min(5, available).toFixed(2), withdrawErrorText: '' });
      return;
    }
    this.setData({ withdrawAmount: available.toFixed(2), withdrawErrorText: '' });
  },

  async withdraw() {
    if (!this.data.wallet || this.data.wallet.available_balance <= 0) {
      wx.showToast({ title: '暂无可提现', icon: 'none' });
      return;
    }
    const available = Number(this.data.wallet.available_balance || 0);
    const amount = Math.round(Number(this.data.withdrawAmount || 0) * 100) / 100;
    if (!Number.isFinite(amount) || amount <= 0) {
      this.setData({ withdrawErrorText: '请输入正确的提现金额' });
      return;
    }
    if (amount > available) {
      this.setData({ withdrawErrorText: `最多可提现 ¥${available.toFixed(2)}` });
      return;
    }
    if (this.data.isReviewExperience && amount > 5) {
      this.setData({ withdrawErrorText: '功能体验单次最多提交 ¥5.00' });
      return;
    }
    this.setData({ withdrawing: true, withdrawErrorText: '' });
    wx.showLoading({ title: '提交中' });
    try {
      const submitted = await api.post(`/api/v1/wallet/withdraw/${this.data.userInfo.id}`, {
        amount,
        remark: '小程序提现申请',
      });
      await this.loadData();
      wx.hideLoading();
      wx.showModal({
        title: '提现申请已提交',
        content: `申请金额 ¥${amount.toFixed(2)}，当前状态为财务审核中。申请编号：${submitted.id}`,
        showCancel: false,
        confirmText: '知道了',
      });
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message || '提现失败', icon: 'none' });
    } finally {
      this.setData({ withdrawing: false });
    }
  },

  goProxyOrder() {
    wx.redirectTo({ url: '/pages/staff/proxy-order/proxy-order' });
  },
});
