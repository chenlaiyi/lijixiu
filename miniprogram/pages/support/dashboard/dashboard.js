const api = require('../../../utils/api');
const auth = require('../../../utils/auth');
const share = require('../../../utils/share');

const TICKET_STATUS_MAP = {
  open: { text: '待处理', tone: 'tone-warning' },
  pending: { text: '待处理', tone: 'tone-warning' },
  in_progress: { text: '处理中', tone: 'tone-progress' },
  processing: { text: '处理中', tone: 'tone-progress' },
  resolved: { text: '已解决', tone: 'tone-success' },
  closed: { text: '已关闭', tone: 'tone-neutral' },
  completed: { text: '已完成', tone: 'tone-success' },
  cancelled: { text: '已取消', tone: 'tone-neutral' },
  rejected: { text: '已拒绝', tone: 'tone-danger' },
};

const DEMAND_STATUS_MAP = {
  submitted: { text: '待联系', tone: 'tone-warning' },
  matching: { text: '匹配中', tone: 'tone-progress' },
  contracted: { text: '已签约', tone: 'tone-progress' },
  completed: { text: '已完成', tone: 'tone-success' },
  complaint: { text: '投诉', tone: 'tone-danger' },
  cancelled: { text: '已取消', tone: 'tone-neutral' },
};

function formatStatus(status, map) {
  if (!status) return { text: '', tone: 'tone-neutral' };
  return map[status] || { text: status, tone: 'tone-neutral' };
}

Page({
  ...share.create({ title: '立即修｜服务保障工作台' }),
  data: {
    tickets: [],
    demands: [],
    loading: true,
    errorText: '',
    stats: { open: 0, domestic: 0, complaint: 0 },
  },
  onShow() { share.enable(); this.load(); },
  onPullDownRefresh() { this.load().finally(() => wx.stopPullDownRefresh()); },
  async load() {
    this.setData({ loading: true, errorText: '' });
    try {
      const [tickets, demands] = await Promise.all([
        api.get('/api/v1/support/tickets'),
        api.get('/api/v1/business/domestic/demands'),
      ]);
      const ticketList = (tickets || []).map(item => {
        const meta = formatStatus(item.status, TICKET_STATUS_MAP);
        return { ...item, statusText: meta.text, statusTone: meta.tone };
      });
      const demandList = (demands || []).map(item => {
        const meta = formatStatus(item.status, DEMAND_STATUS_MAP);
        return { ...item, statusText: meta.text, statusTone: meta.tone };
      });
      const complaint = demandList.filter(item => item.status === 'complaint').length;
      this.setData({
        tickets: ticketList,
        demands: demandList,
        stats: {
          open: ticketList.filter(item => item.status !== 'closed' && item.status !== 'cancelled').length,
          domestic: demandList.length,
          complaint,
        },
      });
    } catch (e) {
      this.setData({ errorText: e.message || '加载失败，请稍后再试' });
    } finally {
      this.setData({ loading: false });
    }
  },
  logout() { auth.logout(); },
});
