const api = require('../../../utils/api');
const auth = require('../../../utils/auth');
const share = require('../../../utils/share');
const statusStyle = require('../../../utils/status-style');
const serviceBill = require('../../../utils/service-bill');

Page({
  ...share.create({ title: '立即修｜门店工作台' }),

  data: {
    loading: true,
    store: null,
    storeName: '门店',
    orders: [],
    repairers: [],
    repairerOptions: [],
    loadFailed: false,
    loadWarningText: '',
    stats: { pending: 0, billConfirm: 0, waitPay: 0, review: 0, done: 0 },
    workflowHint: {
      title: '优先处理待受理工单',
      desc: '先受理，再指派师傅或自己服务',
    },
    wageModes: [
      { value: 'per_order', label: '按单' },
      { value: 'monthly', label: '月薪' },
    ],
    statusMap: {
      store_pending: '待受理',
      store_accepted: '已受理',
      created: '待派单',
      assigned: '已派单',
      dispatched: '已派单',
      repairer_accepted: '已接单',
      servicing: '服务中',
      bill_submitted: '待确认',
      wait_payment: '待支付',
      paid: '已支付',
      paid_pending_review: '待审核',
      store_reviewed: '已审核',
      completed: '已完成',
      cancelled: '已取消',
    },
    categoryMap: {
      appliance: '家电',
      plumbing: '水路',
      electrical: '电路',
      door_window: '门窗',
      furniture_install: '安装',
      appliance_install: '家电安装',
      pipe_dredge: '疏通',
      cleaning: '清洁',
      other: '其他',
    },
  },

  onShow() {
    share.enable();
    if (!wx.getStorageSync('userInfo')) {
      wx.reLaunch({ url: '/pages/login/login' });
      return;
    }
    this.loadData();
  },

  async loadData() {
    this.setData({ loading: true, loadFailed: false, loadWarningText: '' });
    try {
      const userInfo = wx.getStorageSync('userInfo');
      const failures = [];
      const safeGet = async (url, fallback, label) => {
        try {
          return await api.get(url);
        } catch (e) {
          failures.push(label);
          return fallback;
        }
      };
      const [stores, repairers] = await Promise.all([
        safeGet('/api/v1/stores', [], '门店'),
        safeGet('/api/v1/repairers?limit=100', [], '师傅'),
      ]);
      const store = stores.find(item => item.manager_id === userInfo.id) || stores[0] || null;
      const orders = store ? await safeGet(`/api/v1/orders?store_id=${store.id}&limit=100`, [], '订单') : [];
      const billMap = {};
      await Promise.all(orders
        .filter(item => ['bill_submitted', 'wait_payment', 'paid', 'paid_pending_review', 'store_reviewed', 'completed'].includes(item.status))
        .map(async item => {
          billMap[item.id] = await api.get(`/api/v1/orders/${item.id}/service-bill/latest`).catch(() => null);
        }));
      const managerRepairer = repairers.find(item => item.user_id === userInfo.id);
      const repairerOptions = repairers.map(item => ({
        id: item.id,
        label: `#${item.id} ${item.skills || '师傅'}`,
      }));
      const formatted = orders.map(item => this.formatOrder(item, repairerOptions, managerRepairer, billMap[item.id]));
      const stats = this.buildStats(formatted);
      const criticalFailed = failures.includes('门店') || failures.includes('订单');
      this.setData({
        store,
        storeName: store ? store.name : '未绑定门店',
        orders: formatted,
        repairers,
        repairerOptions,
        stats,
        workflowHint: this.buildWorkflowHint(formatted, stats),
        loadFailed: criticalFailed,
        loadWarningText: !criticalFailed && failures.length ? '部分数据加载失败' : '',
        loading: false,
      });
    } catch (e) {
      this.setData({ loading: false, loadFailed: true, loadWarningText: '' });
      wx.showToast({ title: e.message || '加载失败', icon: 'none' });
    }
  },

  buildStats(orders) {
    return {
      pending: orders.filter(item => ['store_pending', 'store_accepted', 'created'].includes(item.status)).length,
      billConfirm: orders.filter(item => item.status === 'bill_submitted').length,
      waitPay: orders.filter(item => item.status === 'wait_payment').length,
      review: orders.filter(item => ['paid', 'paid_pending_review'].includes(item.status)).length,
      done: orders.filter(item => item.status === 'completed').length,
    };
  },

  buildWorkflowHint(orders, stats) {
    if (stats.pending > 0) {
      return {
        title: `${stats.pending} 单待受理`,
        desc: '先受理，再指派或自己服务',
      };
    }
    if (stats.billConfirm > 0) {
      return {
        title: `${stats.billConfirm} 单待确认`,
        desc: '确认后客户可支付',
      };
    }
    if (stats.waitPay > 0) {
      return {
        title: `${stats.waitPay} 单待支付`,
        desc: '支付后进入计薪',
      };
    }
    if (stats.review > 0) {
      return {
        title: `${stats.review} 单待计薪`,
        desc: '选择按单或月薪',
      };
    }
    return {
      title: '暂无工单',
      desc: '新工单会自动显示',
    };
  },

  parseOrderMedia(order) {
    try {
      const mediaList = order.media_json ? JSON.parse(order.media_json) : [];
      return Array.isArray(mediaList) ? mediaList : [];
    } catch (e) {
      return [];
    }
  },

  mediaSummary(mediaList) {
    const audioCount = mediaList.filter(media => media.type === 'audio').length;
    const imageCount = mediaList.filter(media => media.type === 'image').length;
    const videoCount = mediaList.filter(media => media.type === 'video').length;
    return [
      audioCount ? `${audioCount}条语音` : '',
      imageCount ? `${imageCount}张照片` : '',
      videoCount ? `${videoCount}个视频` : '',
    ].filter(Boolean).join(' · ');
  },

  formatOrder(item, repairerOptions, managerRepairer, bill) {
    const selectedIndex = Math.max(0, repairerOptions.findIndex(option => option.id === item.assigned_repairer_id));
    const selectedRepairer = repairerOptions[selectedIndex];
    const managerRepairerId = managerRepairer ? managerRepairer.id : null;
    const isManagerAssigned = Boolean(managerRepairerId && (item.repairer_id === managerRepairerId || item.assigned_repairer_id === managerRepairerId));
    const canStoreAccept = item.status === 'store_pending';
    const canAssign = ['store_pending', 'store_accepted', 'created'].includes(item.status);
    const canSelfServe = canAssign || (isManagerAssigned && ['assigned', 'dispatched'].includes(item.status));
    const canOpenService = isManagerAssigned && ['repairer_accepted', 'servicing'].includes(item.status);
    const canConfirmBill = item.status === 'bill_submitted';
    const canStoreReview = ['paid', 'paid_pending_review'].includes(item.status);
    const defaultWage = Number(item.technician_wage_amount || 0) > 0 ? Number(item.technician_wage_amount) : Number(item.price || 0) * 0.6;
    const billItems = this.parseBillItems(bill);
    const mediaList = this.parseOrderMedia(item);
    const nextStep = this.getOrderNextStep(item.status, {
      canStoreAccept,
      canAssign,
      canSelfServe,
      canOpenService,
      canConfirmBill,
      canStoreReview,
      hasBill: Boolean(bill),
    });
    return {
      ...item,
      categoryText: this.data.categoryMap[item.category] || item.category,
      categoryIcon: this.categoryIcon(item.category),
      statusText: this.data.statusMap[item.status] || item.status,
      statusTone: statusStyle.orderStatusTone(item.status),
      priceText: Number(item.price || 0).toFixed(2),
      hasPrice: Number(item.price || 0) > 0,
      assignIndex: selectedIndex,
      selectedRepairerId: selectedRepairer ? selectedRepairer.id : null,
      selectedRepairerText: selectedRepairer ? selectedRepairer.label : '选师傅',
      canStoreAccept,
      canAssign,
      canSelfServe,
      canOpenService,
      canConfirmBill,
      canStoreReview,
      wageAmount: defaultWage > 0 ? defaultWage.toFixed(2) : '',
      wageMode: 'per_order',
      wageModeIndex: 0,
      wageModeText: '按单',
      bill,
      billItems,
      hasBill: Boolean(bill),
      billAmountText: bill ? Number(bill.amount || 0).toFixed(2) : '',
      billWarrantyText: bill ? `${bill.warranty_days || 0}天` : '',
      hasMedia: mediaList.length > 0,
      mediaSummary: this.mediaSummary(mediaList),
      hasActions: canStoreAccept || canAssign || canSelfServe || canOpenService || canConfirmBill || canStoreReview,
      nextStepTitle: nextStep.title,
      nextStepDesc: nextStep.desc,
    };
  },

  getOrderNextStep(status, flags) {
    if (flags.canStoreAccept) {
      return {
        title: '受理工单',
        desc: '确认门店开始处理',
      };
    }
    if (flags.canOpenService) {
      return {
        title: '服务单',
        desc: '填写明细、价格、保修',
      };
    }
    if (flags.canAssign) {
      return {
        title: '安排上门人员',
        desc: '指派师傅或自己服务',
      };
    }
    if (flags.canConfirmBill) {
      return {
        title: '确认服务单',
        desc: '确认后客户可支付',
      };
    }
    if (status === 'wait_payment') {
      return {
        title: '等待支付',
        desc: '支付后进入计薪',
      };
    }
    if (flags.canStoreReview) {
      return {
        title: '确认计薪',
        desc: '选择按单或月薪',
      };
    }
    if (['store_reviewed', 'completed'].includes(status)) {
      return {
        title: '订单已完成',
        desc: '已完成',
      };
    }
    return {
      title: '跟进工单',
      desc: '看进度',
    };
  },

  categoryIcon(category) {
    const map = {
      appliance: '/assets/categories/appliance.png',
      appliance_install: '/assets/categories/appliance.png',
      plumbing: '/assets/categories/plumbing.png',
      electrical: '/assets/categories/electrical.png',
      door_window: '/assets/categories/door_window.png',
      furniture_install: '/assets/categories/furniture_install.png',
      pipe_dredge: '/assets/categories/pipe_dredge.png',
      cleaning: '/assets/categories/cleaning.png',
      other: '/assets/categories/other.png',
    };
    return map[category] || map.other;
  },

  parseBillItems(bill) {
    return serviceBill.parseItems(bill);
  },

  onRepairerChange(e) {
    const orderId = Number(e.currentTarget.dataset.id);
    const assignIndex = Number(e.detail.value);
    const selected = this.data.repairerOptions[assignIndex];
    this.setData({
      orders: this.data.orders.map(order => (
        order.id === orderId
          ? { ...order, assignIndex, selectedRepairerId: selected ? selected.id : null, selectedRepairerText: selected ? selected.label : '选师傅' }
          : order
      )),
    });
  },

  async storeAccept(e) {
    const id = e.currentTarget.dataset.id;
    const userInfo = wx.getStorageSync('userInfo');
    wx.showLoading({ title: '处理中' });
    try {
      await api.post(`/api/v1/orders/${id}/store-accept?manager_id=${userInfo.id}`);
      wx.hideLoading();
      wx.showToast({ title: '已受理', icon: 'success' });
      this.loadData();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '操作失败', icon: 'none' });
    }
  },

  async ensureManagerRepairer(order) {
    const userInfo = wx.getStorageSync('userInfo');
    const existing = this.data.repairers.find(item => item.user_id === userInfo.id);
    if (existing) return existing;
    const created = await api.post('/api/v1/repairers', {
      user_id: userInfo.id,
      skills: '店长服务',
      region_id: order.region_id || null,
      intro: '店长本人服务',
    });
    this.setData({ repairers: this.data.repairers.concat(created) });
    return created;
  },

  async selfServe(e) {
    const id = Number(e.currentTarget.dataset.id);
    const order = this.data.orders.find(item => item.id === id);
    const userInfo = wx.getStorageSync('userInfo');
    if (!order) return;
    wx.showLoading({ title: '接单中' });
    try {
      await api.post(`/api/v1/orders/${id}/self-service`, {
        manager_id: userInfo.id,
        skills: '门店综合服务',
      });
      await api.post(`/api/v1/orders/${id}/transition`, {
        to_status: 'repairer_accepted',
        operator_type: 'repairer',
        operator_id: userInfo.id,
        remark: '店长本人服务',
      });
      wx.hideLoading();
      wx.navigateTo({ url: `/pages/repairer/detail/detail?orderId=${id}` });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '接单失败', icon: 'none' });
    }
  },

  async assignRepairer(e) {
    const id = Number(e.currentTarget.dataset.id);
    const order = this.data.orders.find(item => item.id === id);
    if (!order || !order.selectedRepairerId) {
      wx.showToast({ title: '先选师傅', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '派单中' });
    try {
      if (order.status === 'store_pending') {
        await api.post(`/api/v1/orders/${id}/store-accept?manager_id=${wx.getStorageSync('userInfo').id}`);
      }
      await api.post(`/api/v1/orders/${id}/assign`, { repairer_id: order.selectedRepairerId });
      wx.hideLoading();
      wx.showToast({ title: '已派单', icon: 'success' });
      this.loadData();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '派单失败', icon: 'none' });
    }
  },

  goServiceDetail(e) {
    wx.navigateTo({ url: `/pages/repairer/detail/detail?orderId=${e.currentTarget.dataset.id}` });
  },

  openOrderDetail(e) {
    wx.navigateTo({ url: `/pages/repairer/detail/detail?orderId=${e.currentTarget.dataset.id}` });
  },

  async confirmServiceBill(e) {
    const id = e.currentTarget.dataset.id;
    wx.showLoading({ title: '确认中' });
    try {
      await api.post(`/api/v1/orders/${id}/service-bill/confirm`);
      wx.hideLoading();
      wx.showToast({ title: '已确认', icon: 'success' });
      this.loadData();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '确认失败', icon: 'none' });
    }
  },

  onWageInput(e) {
    const id = Number(e.currentTarget.dataset.id);
    const wageAmount = e.detail.value;
    this.setData({ orders: this.data.orders.map(order => (order.id === id ? { ...order, wageAmount } : order)) });
  },

  onWageModeChange(e) {
    const id = Number(e.currentTarget.dataset.id);
    const wageModeIndex = Number(e.detail.value);
    const selected = this.data.wageModes[wageModeIndex] || this.data.wageModes[0];
    this.setData({
      orders: this.data.orders.map(order => (
        order.id === id ? { ...order, wageModeIndex, wageMode: selected.value, wageModeText: selected.label } : order
      )),
    });
  },

  async storeReview(e) {
    const id = Number(e.currentTarget.dataset.id);
    const order = this.data.orders.find(item => item.id === id);
    const isMonthly = order && order.wageMode === 'monthly';
    const wageAmount = isMonthly ? 0 : Number(order && order.wageAmount);
    const userInfo = wx.getStorageSync('userInfo');
    if (!isMonthly && (!Number.isFinite(wageAmount) || wageAmount < 0)) {
      wx.showToast({ title: '填写工资', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '审核中' });
    try {
      await api.post(`/api/v1/orders/${id}/store-review?manager_id=${userInfo.id}`, {
        technician_wage_amount: wageAmount,
        wage_mode: isMonthly ? 'monthly' : 'per_order',
        remark: isMonthly ? '按月工资' : '按单工资',
      });
      wx.hideLoading();
      wx.showToast({ title: '已审核', icon: 'success' });
      this.loadData();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '审核失败', icon: 'none' });
    }
  },

  goCustomer() {
    wx.redirectTo({ url: '/pages/staff/proxy-order/proxy-order' });
  },

  goPayroll() { wx.navigateTo({ url: '/pages/store/payroll/payroll' }); },

  onPullDownRefresh() {
    this.loadData().then(() => wx.stopPullDownRefresh());
  },

  logout() {
    auth.logout();
  },
});
