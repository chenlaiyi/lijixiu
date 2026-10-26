const api = require('../../../utils/api');
const share = require('../../../utils/share');

const DAY_MS = 24 * 60 * 60 * 1000;

function remainingDays(expiresAt, now = Date.now()) {
  const expiresTime = new Date(expiresAt).getTime();
  if (!Number.isFinite(expiresTime) || expiresTime <= now) return 0;
  return Math.ceil((expiresTime - now) / DAY_MS);
}

Page({
  ...share.create({ title: '立即修｜保修凭证' }),
  data: { list: [], loading: true, loadFailed: false },
  onShow() {
    share.enable();
    this.load();
    this.startCountdownTimer();
  },
  async load() {
    const user = wx.getStorageSync('userInfo');
    if (!user) {
      wx.reLaunch({ url: '/pages/customer/home/home' });
      return;
    }
    this.setData({ loading: true, loadFailed: false });
    try {
      const [list, tickets] = await Promise.all([
        api.get('/api/v1/business/warranties', { customer_id: user.id }),
        api.get('/api/v1/support/tickets', { user_id: user.id }).catch(() => []),
      ]);
      const ticketByOrder = {};
      (tickets || []).forEach((ticket) => {
        if (ticket.category !== 'warranty' || ticketByOrder[ticket.order_id]) return;
        ticketByOrder[ticket.order_id] = ticket;
      });
      const today = Date.now();
      const mapped = (list || []).map((item) => {
        const ticket = ticketByOrder[item.order_id] || null;
        const daysLeft = remainingDays(item.expires_at, today);
        const certificateActive = item.status === 'active' && daysLeft > 0;
        const hasOpenTicket = Boolean(ticket && ticket.status !== 'closed');
        let claimText = '提交保修申请';
        if (!certificateActive) claimText = '保修已到期';
        else if (!item.store_id) claimText = '门店信息缺失';
        else if (hasOpenTicket) claimText = ticket.status === 'replied' ? '售后已回复' : '售后处理中';
        return {
          ...item,
          startsText: String(item.starts_at || '').slice(0, 10),
          expiresText: String(item.expires_at || '').slice(0, 10),
          remainingDays: daysLeft,
          certificateActive,
          certificateStatusText: certificateActive ? '保修中' : '已到期',
          claimText,
          canClaim: Boolean(certificateActive && item.store_id && !hasOpenTicket),
          ticketStatusText: ticket
            ? ({ open: '待处理', replied: '已回复', closed: '已关闭' }[ticket.status] || ticket.status)
            : '',
        };
      });
      this.setData({ list: mapped.filter(item => item.certificateActive), loading: false });
    } catch (error) {
      this.setData({ loading: false, loadFailed: true });
      wx.showToast({ title: error.message || '保修凭证加载失败', icon: 'none' });
    } finally { this.setData({ loading: false }); }
  },
  openOrder(e) { wx.navigateTo({ url: `/pages/customer/detail/detail?orderId=${e.currentTarget.dataset.id}` }); },
  applyWarranty(e) {
    if (!e.currentTarget.dataset.enabled) return;
    wx.navigateTo({
      url: `/pages/customer/warranty-claim/warranty-claim?orderId=${e.currentTarget.dataset.id}`,
    });
  },

  startCountdownTimer() {
    this.stopCountdownTimer();
    this.countdownTimer = setInterval(() => this.refreshCountdown(), 60 * 1000);
  },

  stopCountdownTimer() {
    if (!this.countdownTimer) return;
    clearInterval(this.countdownTimer);
    this.countdownTimer = null;
  },

  refreshCountdown() {
    const now = Date.now();
    const list = this.data.list
      .map(item => ({ ...item, remainingDays: remainingDays(item.expires_at, now) }))
      .filter(item => item.remainingDays > 0);
    this.setData({ list });
  },

  onHide() {
    this.stopCountdownTimer();
  },

  onUnload() {
    this.stopCountdownTimer();
  },
});
