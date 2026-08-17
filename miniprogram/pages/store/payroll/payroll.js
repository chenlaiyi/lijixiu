const api = require('../../../utils/api');
const share = require('../../../utils/share');

function currentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

const PAYROLL_STATUS_MAP = {
  pending: { text: '待发放', tone: 'tone-warning' },
  generated: { text: '已生成', tone: 'tone-progress' },
  paid: { text: '已发放', tone: 'tone-success' },
  cancelled: { text: '已取消', tone: 'tone-neutral' },
};

function formatPayrollStatus(status) {
  if (!status) return { text: '', tone: 'tone-neutral' };
  return PAYROLL_STATUS_MAP[status] || { text: status, tone: 'tone-neutral' };
}

Page({
  ...share.create({ title: '立即修｜工资管理' }),
  data: {
    store: null,
    employees: [],
    payroll: { periods: [], items: [] },
    month: currentMonth(),
    loading: true,
    errorText: '',
    saving: false,
  },
  onShow() { share.enable(); this.load(); },
  onPullDownRefresh() { this.load().finally(() => wx.stopPullDownRefresh()); },
  async load() {
    const user = wx.getStorageSync('userInfo') || {};
    this.setData({ loading: true, errorText: '' });
    try {
      const [stores, users] = await Promise.all([
        api.get('/api/v1/stores'),
        api.get('/api/v1/users?limit=100'),
      ]);
      const store = (stores || []).find(item => item.manager_id === user.id);
      if (!store) throw new Error('未找到店长所属门店');
      const [wages, payroll] = await Promise.all([
        api.get('/api/v1/business/wages', { store_id: store.id, wage_mode: 'monthly' }),
        api.get('/api/v1/business/payroll', { store_id: store.id }),
      ]);
      const userMap = Object.fromEntries((users || []).map(item => [item.id, item]));
      const grouped = {};
      (wages || []).forEach(item => {
        if (!grouped[item.employee_user_id]) {
          grouped[item.employee_user_id] = {
            userId: item.employee_user_id,
            workUnits: 0,
            salary: '',
            name: (userMap[item.employee_user_id] || {}).name || `员工#${item.employee_user_id}`,
          };
        }
        grouped[item.employee_user_id].workUnits += Number(item.work_units || 0);
      });
      const periods = (payroll && payroll.periods ? payroll.periods : []).map(item => {
        const meta = formatPayrollStatus(item.status);
        return { ...item, statusText: meta.text, statusTone: meta.tone };
      });
      this.setData({
        store,
        employees: Object.values(grouped),
        payroll: { ...(payroll || {}), periods },
      });
    } catch (e) {
      this.setData({ errorText: e.message || '加载失败，请稍后再试' });
    } finally {
      this.setData({ loading: false });
    }
  },
  monthChange(e) { this.setData({ month: e.detail.value }); },
  salaryInput(e) {
    const id = Number(e.currentTarget.dataset.id);
    this.setData({
      employees: this.data.employees.map(item => (item.userId === id ? { ...item, salary: e.detail.value } : item)),
    });
  },
  async generatePayroll() {
    const lines = this.data.employees
      .filter(item => Number(item.salary) > 0)
      .map(item => ({
        employee_user_id: item.userId,
        amount: Number(item.salary),
        remark: `本月工作量 ${item.workUnits}`,
      }));
    if (!lines.length) {
      wx.showToast({ title: '请填写月薪金额', icon: 'none' });
      return;
    }
    const user = wx.getStorageSync('userInfo') || {};
    this.setData({ saving: true });
    try {
      await api.post('/api/v1/business/payroll', {
        month: this.data.month,
        store_id: this.data.store.id,
        manager_id: user.id,
        lines,
      });
      wx.showToast({ title: '工资单已生成', icon: 'success' });
      await this.load();
    } catch (err) {
      wx.showToast({ title: err.message || '生成失败', icon: 'none' });
    } finally {
      this.setData({ saving: false });
    }
  },
  async payPayroll(e) {
    const periodId = Number(e.currentTarget.dataset.id);
    const user = wx.getStorageSync('userInfo') || {};
    wx.showLoading({ title: '发放中' });
    try {
      await api.post(`/api/v1/business/payroll/${periodId}/pay`, {
        store_id: this.data.store.id,
        manager_id: user.id,
      });
      wx.showToast({ title: '工资已发放', icon: 'success' });
      await this.load();
    } catch (err) {
      wx.showToast({ title: err.message || '发放失败', icon: 'none' });
    } finally {
      wx.hideLoading();
    }
  },
});
