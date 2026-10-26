const api = require('../../../utils/api');
const auth = require('../../../utils/auth');
const share = require('../../../utils/share');
const statusStyle = require('../../../utils/status-style');
const serviceBill = require('../../../utils/service-bill');

Page({
  ...share.create({
    title: '立即修｜平台工作台',
  }),

  data: {
    loading: true,
    metrics: {},
    metricsView: {
      ordersTotal: 0,
      ordersCompleted: 0,
    },
    opsView: {
      needDispatch: 0,
      needBill: 0,
      needReview: 0,
      pendingWithdrawals: 0,
      alertCount: 0,
      totalPending: 0,
      hintTitle: '暂无待办',
      hintDesc: '工单、提现、告警正常',
    },
    orders: [],
    users: [],
    repairers: [],
    repairerOptions: [],
    stores: [],
    withdrawals: [],
    alerts: [],
    loadFailed: false,
    loadWarningText: '',
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
      appliance: '家电维修',
      plumbing: '水路管道',
      electrical: '电路照明',
      door_window: '门窗维修',
      furniture_install: '家具安装',
      appliance_install: '家电安装',
      pipe_dredge: '管道疏通',
      cleaning: '清洁保养',
      other: '其他服务',
    },
  },

  onShow() {
    share.enable();
    const userInfo = wx.getStorageSync('userInfo');
    if (!userInfo) {
      wx.reLaunch({ url: '/pages/customer/home/home' });
      return;
    }
    this.loadData();
  },

  async loadData() {
    this.setData({ loading: true, loadFailed: false, loadWarningText: '' });
    try {
      const failures = [];
      const safeGet = async (url, fallback, label) => {
        try {
          return await api.get(url);
        } catch (e) {
          failures.push(label);
          return fallback;
        }
      };
      const [metrics, orders, users, repairers, stores, withdrawals, alerts] = await Promise.all([
        safeGet('/metrics', {}, '统计'),
        safeGet('/api/v1/orders?limit=50', [], '订单'),
        safeGet('/api/v1/users?limit=20', [], '用户'),
        safeGet('/api/v1/repairers?limit=100', [], '师傅'),
        safeGet('/api/v1/stores', [], '门店'),
        safeGet('/api/v1/wallet/withdrawals?limit=20', [], '提现'),
        safeGet('/api/v1/admin/alerts?limit=20', [], '告警'),
      ]);
      const userInfo = wx.getStorageSync('userInfo');
      const managerRepairer = repairers.find(item => userInfo && item.user_id === userInfo.id);
      const repairerOptions = repairers.map(item => ({
        id: item.id,
        label: `#${item.id} ${item.skills || '师傅'}`,
      }));
      const billMap = {};
      await Promise.all(orders
        .filter(item => ['bill_submitted', 'wait_payment', 'paid', 'paid_pending_review', 'store_reviewed', 'completed'].includes(item.status))
        .map(async item => {
          billMap[item.id] = await api.get(`/api/v1/orders/${item.id}/service-bill/latest`).catch(() => null);
        }));
      const criticalFailed = failures.includes('订单');
      const formattedOrders = orders.map(item => this.formatOrder(item, repairerOptions, managerRepairer, billMap[item.id]));
      const formattedWithdrawals = withdrawals.map(item => ({
        ...item,
        statusTone: statusStyle.financeStatusTone(item.status),
      }));
      const formattedAlerts = alerts;
      this.setData({
        metrics,
        metricsView: {
          ordersTotal: metrics.orders_total || orders.length,
          ordersCompleted: metrics.orders_completed || 0,
        },
        opsView: this.buildOpsView(formattedOrders, formattedWithdrawals, formattedAlerts),
        orders: formattedOrders,
        users,
        repairers,
        repairerOptions,
        stores: stores.map(item => ({ ...item, statusTone: statusStyle.resourceStatusTone(item.status) })),
        withdrawals: formattedWithdrawals,
        alerts: formattedAlerts,
        loadFailed: criticalFailed,
        loadWarningText: !criticalFailed && failures.length ? `${failures.join('、')}加载失败` : '',
        loading: false,
      });
    } catch (e) {
      this.setData({ loading: false, loadFailed: true, loadWarningText: '' });
      wx.showToast({ title: e.message || '加载失败', icon: 'none' });
    }
  },

  buildOpsView(orders, withdrawals, alerts) {
    const needDispatch = orders.filter(item => item.canAssign || item.canStoreAccept).length;
    const needBill = orders.filter(item => item.canConfirmBill).length;
    const needReview = orders.filter(item => item.canStoreReview).length;
    const pendingWithdrawals = withdrawals.filter(item => item.status === 'pending').length;
    const alertCount = alerts.length;
    const hint = this.buildOpsHint({ needDispatch, needBill, needReview, pendingWithdrawals, alertCount });
    return {
      needDispatch,
      needBill,
      needReview,
      pendingWithdrawals,
      alertCount,
      totalPending: needDispatch + needBill + needReview + pendingWithdrawals + alertCount,
      hintTitle: hint.title,
      hintDesc: hint.desc,
    };
  },

  buildOpsHint(summary) {
    if (summary.needDispatch) {
      return {
        title: '处理受理和派单',
        desc: `${summary.needDispatch} 单待跟进`,
      };
    }
    if (summary.needBill) {
      return {
        title: '确认服务单',
        desc: `${summary.needBill} 单待确认`,
      };
    }
    if (summary.needReview) {
      return {
        title: '确认计薪',
        desc: `${summary.needReview} 单待审核`,
      };
    }
    if (summary.pendingWithdrawals) {
      return {
        title: '审核提现',
        desc: `${summary.pendingWithdrawals} 笔待审核`,
      };
    }
    if (summary.alertCount) {
      return {
        title: '查看告警',
        desc: `${summary.alertCount} 条待确认`,
      };
    }
    return {
      title: '暂无待办',
      desc: '工单、提现、告警正常',
    };
  },

  formatOrder(item, repairerOptions, managerRepairer, bill) {
    const selectedIndex = Math.max(
      0,
      repairerOptions.findIndex(option => option.id === item.assigned_repairer_id),
    );
    const selectedRepairer = repairerOptions[selectedIndex];
    const canStoreAccept = item.status === 'store_pending';
    const canAssign = ['store_pending', 'store_accepted', 'created'].includes(item.status);
    const managerRepairerId = managerRepairer ? managerRepairer.id : null;
    const isManagerAssigned = Boolean(
      managerRepairerId
      && (item.repairer_id === managerRepairerId || item.assigned_repairer_id === managerRepairerId),
    );
    const canSelfServe = canAssign || (isManagerAssigned && ['assigned', 'dispatched'].includes(item.status));
    const canOpenService = isManagerAssigned && ['repairer_accepted', 'servicing'].includes(item.status);
    const canConfirmBill = item.status === 'bill_submitted';
    const canStoreReview = ['paid', 'paid_pending_review'].includes(item.status);
    const defaultWage = Number(item.technician_wage_amount || 0) > 0
      ? Number(item.technician_wage_amount)
      : Number(item.price || 0) * 0.6;
    const wageAmount = defaultWage > 0 ? defaultWage.toFixed(2) : '';
    const billItems = this.parseBillItems(bill);
    const mediaList = this.parseOrderMedia(item);
    return {
      ...item,
      categoryText: this.data.categoryMap[item.category] || item.category,
      categoryIcon: this.categoryIcon(item.category),
      statusText: this.data.statusMap[item.status] || item.status,
      statusTone: statusStyle.orderStatusTone(item.status),
      priceText: Number(item.price || 0).toFixed(2),
      assignIndex: selectedIndex,
      selectedRepairerId: selectedRepairer ? selectedRepairer.id : null,
      selectedRepairerText: selectedRepairer ? selectedRepairer.label : '暂无师傅',
      managerRepairerId,
      isManagerAssigned,
      canStoreAccept,
      canAssign,
      canSelfServe,
      canOpenService,
      canConfirmBill,
      canStoreReview,
      wageAmount,
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
      nextStep: this.orderNextStep(item.status),
      hasOrderActions: canStoreAccept || canAssign || canSelfServe || canOpenService || canConfirmBill || canStoreReview,
    };
  },

  orderNextStep(status) {
    const map = {
      store_pending: { title: '受理工单', desc: '确认门店开始处理' },
      store_accepted: { title: '安排上门人员', desc: '指派师傅或自己服务' },
      created: { title: '安排上门人员', desc: '指派师傅或自己服务' },
      assigned: { title: '跟进接单', desc: '师傅接单' },
      dispatched: { title: '跟进接单', desc: '上门准备' },
      repairer_accepted: { title: '等待服务单', desc: '服务后提交' },
      accepted: { title: '等待服务单', desc: '服务后提交' },
      servicing: { title: '生成服务单', desc: '明细和保修' },
      bill_submitted: { title: '确认服务单', desc: '确认后客户可支付' },
      wait_payment: { title: '客户支付', desc: '支付后审核' },
      paid: { title: '确认计薪', desc: '按单或月薪' },
      paid_pending_review: { title: '确认计薪', desc: '按单或月薪' },
      store_reviewed: { title: '已审核', desc: '等待归档' },
      completed: { title: '已完成', desc: '服务已完成' },
      cancelled: { title: '已取消', desc: '无需处理' },
    };
    return map[status] || { title: '查看详情', desc: '继续跟进' };
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
    ].filter(Boolean).join('、');
  },

  parseBillItems(bill) {
    return serviceBill.parseItems(bill);
  },

  onRepairerChange(e) {
    const orderId = Number(e.currentTarget.dataset.id);
    const assignIndex = Number(e.detail.value);
    const selected = this.data.repairerOptions[assignIndex];
    const orders = this.data.orders.map(order => {
      if (order.id !== orderId) return order;
      return {
        ...order,
        assignIndex,
        selectedRepairerId: selected ? selected.id : null,
        selectedRepairerText: selected ? selected.label : '暂无师傅',
      };
    });
    this.setData({ orders });
  },

  async storeAccept(e) {
    const id = e.currentTarget.dataset.id;
    const userInfo = wx.getStorageSync('userInfo');
    wx.showLoading({ title: '受理中' });
    try {
      await api.post(`/api/v1/orders/${id}/store-accept?manager_id=${userInfo && userInfo.id ? userInfo.id : ''}`);
      wx.hideLoading();
      wx.showToast({ title: '已受理', icon: 'success' });
      this.loadData();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '受理失败', icon: 'none' });
    }
  },

  async ensureManagerRepairer(order) {
    const userInfo = wx.getStorageSync('userInfo');
    if (!userInfo || !userInfo.id) {
      throw new Error('请先登录');
    }

    const existing = this.data.repairers.find(item => item.user_id === userInfo.id);
    if (existing) return existing;

    try {
      const created = await api.post('/api/v1/repairers', {
        user_id: userInfo.id,
        skills: '门店店长自营服务',
        region_id: order.region_id || null,
        intro: '店长本人上门服务档案',
      });
      const repairers = this.data.repairers.concat(created);
      const repairerOptions = repairers.map(item => ({
        id: item.id,
        label: `#${item.id} ${item.skills || '师傅'}`,
      }));
      this.setData({ repairers, repairerOptions });
      return created;
    } catch (e) {
      const latest = await api.get('/api/v1/repairers?limit=100');
      const repairer = latest.find(item => item.user_id === userInfo.id);
      if (!repairer) throw e;
      this.setData({
        repairers: latest,
        repairerOptions: latest.map(item => ({
          id: item.id,
          label: `#${item.id} ${item.skills || '师傅'}`,
        })),
      });
      return repairer;
    }
  },

  async selfServe(e) {
    const id = Number(e.currentTarget.dataset.id);
    const order = this.data.orders.find(item => item.id === id);
    const userInfo = wx.getStorageSync('userInfo');
    if (!order) return;

    wx.showLoading({ title: '接单中' });
    try {
      const repairer = await this.ensureManagerRepairer(order);
      let status = order.status;

      if (status === 'store_pending') {
        await api.post(`/api/v1/orders/${id}/store-accept?manager_id=${userInfo && userInfo.id ? userInfo.id : ''}`);
        status = 'store_accepted';
      }

      if (['store_accepted', 'store_pending', 'created'].includes(status)) {
        await api.post(`/api/v1/orders/${id}/assign`, { repairer_id: repairer.id });
        status = status === 'created' ? 'assigned' : 'dispatched';
      }

      if (['assigned', 'dispatched'].includes(status)) {
        await api.post(`/api/v1/orders/${id}/transition`, {
          to_status: 'repairer_accepted',
          operator_type: 'repairer',
          operator_id: userInfo && userInfo.id ? userInfo.id : null,
          remark: '店长本人接单',
        });
      }

      wx.hideLoading();
      wx.showToast({ title: '已接单', icon: 'success' });
      wx.navigateTo({ url: `/pages/repairer/detail/detail?orderId=${id}` });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '接单失败', icon: 'none' });
    }
  },

  goServiceDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/repairer/detail/detail?orderId=${id}` });
  },

  openOrderDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/repairer/detail/detail?orderId=${id}` });
  },

  async assignRepairer(e) {
    const id = Number(e.currentTarget.dataset.id);
    const order = this.data.orders.find(item => item.id === id);
    const repairerId = order && order.selectedRepairerId;
    if (!repairerId) {
      wx.showToast({ title: '先选师傅', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '派单中' });
    try {
      await api.post(`/api/v1/orders/${id}/assign`, { repairer_id: repairerId });
      wx.hideLoading();
      wx.showToast({ title: '已派单', icon: 'success' });
      this.loadData();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '派单失败', icon: 'none' });
    }
  },

  async confirmServiceBill(e) {
    const id = Number(e.currentTarget.dataset.id);
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
    const orders = this.data.orders.map(order => (
      order.id === id ? { ...order, wageAmount } : order
    ));
    this.setData({ orders });
  },

  onWageModeChange(e) {
    const id = Number(e.currentTarget.dataset.id);
    const wageModeIndex = Number(e.detail.value);
    const selected = this.data.wageModes[wageModeIndex] || this.data.wageModes[0];
    const orders = this.data.orders.map(order => (
      order.id === id
        ? { ...order, wageModeIndex, wageMode: selected.value, wageModeText: selected.label }
        : order
    ));
    this.setData({ orders });
  },

  applyWageRate(e) {
    const id = Number(e.currentTarget.dataset.id);
    const rate = Number(e.currentTarget.dataset.rate);
    const orders = this.data.orders.map(order => {
      if (order.id !== id) return order;
      return {
        ...order,
        wageMode: 'per_order',
        wageModeIndex: 0,
        wageModeText: '按单',
        wageAmount: (Number(order.price || 0) * rate).toFixed(2),
      };
    });
    this.setData({ orders });
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
      await api.post(`/api/v1/orders/${id}/store-review?manager_id=${userInfo && userInfo.id ? userInfo.id : ''}`, {
        technician_wage_amount: wageAmount,
        remark: isMonthly ? '门店审核通过，师傅工资按月发放' : '门店审核并记录服务工资',
      });
      wx.hideLoading();
      wx.showToast({ title: '审核完成', icon: 'success' });
      this.loadData();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '审核失败', icon: 'none' });
    }
  },

  async runReconcile() {
    wx.showLoading({ title: '对账中' });
    try {
      const res = await api.post('/api/v1/admin/reconcile/run');
      wx.hideLoading();
      wx.showToast({ title: `异常${res.mismatch || 0}条`, icon: 'none' });
      this.loadData();
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message || '对账失败', icon: 'none' });
    }
  },

  scrollToSection(e) {
    const selector = e.currentTarget.dataset.target;
    if (!selector) return;
    wx.pageScrollTo({
      selector,
      duration: 240,
    });
  },

  async approveWithdraw(e) {
    const id = e.currentTarget.dataset.id;
    wx.showLoading({ title: '处理中' });
    try {
      await api.post(`/api/v1/wallet/withdraw/${id}/review`, {
        action: 'approve',
        remark: '小程序平台审核通过',
      });
      wx.hideLoading();
      wx.showToast({ title: '已通过', icon: 'success' });
      this.loadData();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '处理失败', icon: 'none' });
    }
  },

  goCustomer() {
    wx.redirectTo({ url: '/pages/staff/proxy-order/proxy-order' });
  },

  logout() {
    auth.logout();
  },

  onPullDownRefresh() {
    this.loadData().then(() => wx.stopPullDownRefresh());
  },
});
