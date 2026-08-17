const api = require('../../../utils/api');
const share = require('../../../utils/share');
const statusStyle = require('../../../utils/status-style');

Page({
  ...share.create({ title: '立即修｜城市工作台' }),

  data: {
    loading: true,
    loadFailed: false,
    stores: [],
    orders: [],
    stats: { stores: 0, orders: 0, pending: 0, billConfirm: 0, payReview: 0, active: 0, revenue: '0.00' },
    focusHint: {
      title: '暂无工单',
      desc: '新工单自动汇总',
    },
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
    this.setData({ loading: true, loadFailed: false });
    try {
      const userInfo = wx.getStorageSync('userInfo');
      const [allStores, allOrders] = await Promise.all([
        api.get('/api/v1/stores').catch(() => []),
        api.get('/api/v1/orders?limit=100').catch(() => []),
      ]);
      const stores = allStores
        .filter(item => item.city_manager_id === userInfo.id)
        .map(item => ({ ...item, statusTone: statusStyle.resourceStatusTone(item.status) }));
      const storeIds = stores.map(item => item.id);
      const scopedOrders = allOrders
        .filter(item => storeIds.includes(item.store_id))
        .map(item => this.formatOrder(item))
        .slice(0, 30);
      const stats = this.buildStats(stores, scopedOrders);
      this.setData({
        stores,
        orders: scopedOrders,
        stats,
        focusHint: this.buildFocusHint(stores, scopedOrders, stats),
        loading: false,
      });
    } catch (e) {
      this.setData({ loading: false, loadFailed: true });
      wx.showToast({ title: e.message || '加载失败', icon: 'none' });
    }
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

  formatOrder(item) {
    const mediaList = this.parseOrderMedia(item);
    return {
      ...item,
      statusText: this.data.statusMap[item.status] || item.status,
      statusTone: statusStyle.orderStatusTone(item.status),
      categoryText: this.data.categoryMap[item.category] || item.category,
      categoryIcon: this.categoryIcon(item.category),
      priceText: Number(item.price || 0).toFixed(2),
      mediaSummary: this.mediaSummary(mediaList),
      nextStep: this.orderNextStep(item.status),
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

  buildStats(stores, orders) {
    const pendingStatuses = ['store_pending', 'store_accepted', 'created', 'assigned', 'dispatched'];
    const payReviewStatuses = ['wait_payment', 'paid', 'paid_pending_review'];
    const pending = orders.filter(item => pendingStatuses.includes(item.status)).length;
    const billConfirm = orders.filter(item => item.status === 'bill_submitted').length;
    const payReview = orders.filter(item => payReviewStatuses.includes(item.status)).length;
    const active = orders.filter(item => !['completed', 'cancelled'].includes(item.status)).length;
    const revenue = orders.reduce((sum, item) => sum + Number(item.price || 0), 0);
    return {
      stores: stores.length,
      orders: orders.length,
      pending,
      billConfirm,
      payReview,
      active,
      revenue: revenue.toFixed(2),
    };
  },

  buildFocusHint(stores, orders, stats) {
    if (!stores.length) {
      return {
        title: '绑定门店',
        desc: '绑定后查看工单',
      };
    }
    const pending = orders.filter(item => ['store_pending', 'store_accepted', 'created', 'assigned', 'dispatched'].includes(item.status));
    if (pending.length) {
      return {
        title: '跟进受理和派单',
        desc: `${pending.length} 单待跟进`,
      };
    }
    const review = orders.filter(item => ['bill_submitted', 'wait_payment', 'paid', 'paid_pending_review'].includes(item.status));
    if (review.length) {
      return {
        title: '跟进支付',
        desc: `${review.length} 单待确认`,
      };
    }
    if (stats.orders) {
      return {
        title: '履约稳定',
        desc: '查看门店和订单',
      };
    }
    return {
      title: '暂无工单',
      desc: '新工单自动汇总',
    };
  },

  orderNextStep(status) {
    const map = {
      store_pending: { title: '受理工单', desc: '确认门店开始处理' },
      store_accepted: { title: '安排上门人员', desc: '指派师傅或自己服务' },
      created: { title: '安排上门人员', desc: '等待门店指派' },
      assigned: { title: '跟进接单', desc: '师傅接单' },
      dispatched: { title: '跟进接单', desc: '上门准备' },
      repairer_accepted: { title: '等待服务单', desc: '服务后提交' },
      accepted: { title: '等待服务单', desc: '服务后提交' },
      servicing: { title: '服务中', desc: '等待服务单' },
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

  goCustomer() {
    wx.redirectTo({ url: '/pages/staff/proxy-order/proxy-order' });
  },

  onPullDownRefresh() {
    this.loadData().then(() => wx.stopPullDownRefresh());
  },
});
