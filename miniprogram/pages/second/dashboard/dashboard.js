const api = require('../../../utils/api');
const share = require('../../../utils/share');
const statusStyle = require('../../../utils/status-style');

Page({
  ...share.create({ title: '立即修｜兜底工单' }),

  data: {
    loading: true,
    loadFailed: false,
    repairer: null,
    fallbackStoreIds: [],
    orders: [],
    stats: { fallback: 0, assigned: 0, servicing: 0, bills: 0 },
    focusHint: {
      title: '暂无待接',
      desc: '派单后显示',
    },
    statusMap: {
      store_pending: '待接单',
      assigned: '待接单',
      dispatched: '待接单',
      repairer_accepted: '已接单',
      servicing: '服务中',
      bill_submitted: '待确认',
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
      wx.reLaunch({ url: '/pages/customer/home/home' });
      return;
    }
    this.loadData();
  },

  async loadData() {
    this.setData({ loading: true, loadFailed: false });
    try {
      const userInfo = wx.getStorageSync('userInfo');
      const [repairers, stores] = await Promise.all([
        api.get('/api/v1/repairers?limit=100').catch(() => []),
        api.get('/api/v1/stores').catch(() => []),
      ]);
      const repairer = repairers.find(item => item.user_id === userInfo.id);
      if (!repairer) {
        this.setData({
          repairer: null,
          orders: [],
          stats: { fallback: 0, assigned: 0, servicing: 0, bills: 0 },
          focusHint: this.buildFocusHint(null, [], { fallback: 0, assigned: 0, servicing: 0, bills: 0 }),
          loading: false,
        });
        return;
      }
      const fallbackStoreIds = stores
        .filter(item => item.default_second_receiver_id === repairer.id)
        .map(item => item.id);
      const requests = [
        api.get(`/api/v1/orders?assigned_repairer_id=${repairer.id}&status=assigned&limit=100`).catch(() => []),
        api.get(`/api/v1/orders?assigned_repairer_id=${repairer.id}&status=dispatched&limit=100`).catch(() => []),
        api.get(`/api/v1/orders?repairer_id=${repairer.id}&status=servicing&limit=100`).catch(() => []),
        api.get(`/api/v1/orders?repairer_id=${repairer.id}&status=bill_submitted&limit=100`).catch(() => []),
      ];
      fallbackStoreIds.forEach(storeId => {
        requests.push(api.get(`/api/v1/orders?store_id=${storeId}&status=store_pending&limit=100`).catch(() => []));
      });
      const groups = await Promise.all(requests);
      const byId = {};
      groups.flat().forEach(item => { byId[item.id] = this.formatOrder(item); });
      const orders = Object.keys(byId).map(id => byId[id]);
      const stats = this.buildStats(orders);
      this.setData({
        repairer,
        fallbackStoreIds,
        orders,
        stats,
        focusHint: this.buildFocusHint(repairer, orders, stats),
        loading: false,
      });
    } catch (e) {
      this.setData({ loading: false, loadFailed: true });
      wx.showToast({ title: e.message || '加载失败', icon: 'none' });
    }
  },

  formatOrder(item) {
    let mediaList = [];
    try {
      mediaList = item.media_json ? JSON.parse(item.media_json) : [];
      if (!Array.isArray(mediaList)) mediaList = [];
    } catch (e) {
      mediaList = [];
    }
    const audioCount = mediaList.filter(media => media.type === 'audio').length;
    const imageCount = mediaList.filter(media => media.type === 'image').length;
    const videoCount = mediaList.filter(media => media.type === 'video').length;
    return {
      ...item,
      statusText: this.data.statusMap[item.status] || item.status,
      statusTone: statusStyle.orderStatusTone(item.status),
      categoryText: this.data.categoryMap[item.category] || item.category,
      categoryIcon: this.categoryIcon(item.category),
      canAccept: ['assigned', 'dispatched'].includes(item.status),
      canFallback: item.status === 'store_pending',
      priceText: Number(item.price || 0).toFixed(2),
      nextStep: this.orderNextStep(item.status),
      mediaSummary: [
        audioCount ? `${audioCount}条语音` : '',
        imageCount ? `${imageCount}张照片` : '',
        videoCount ? `${videoCount}个视频` : '',
      ].filter(Boolean).join('、'),
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

  buildStats(orders) {
    return {
      fallback: orders.filter(item => item.status === 'store_pending').length,
      assigned: orders.filter(item => ['assigned', 'dispatched'].includes(item.status)).length,
      servicing: orders.filter(item => item.status === 'servicing').length,
      bills: orders.filter(item => item.status === 'bill_submitted').length,
    };
  },

  buildFocusHint(repairer, orders, stats) {
    if (!repairer) {
      return {
        title: '绑定师傅档案',
        desc: '绑定后处理工单',
      };
    }
    if (stats.fallback) {
      return {
        title: '兜底接单',
        desc: `${stats.fallback} 单待接`,
      };
    }
    if (stats.assigned) {
      return {
        title: '确认接单',
        desc: `${stats.assigned} 单待接`,
      };
    }
    if (stats.servicing) {
      return {
        title: '推进服务',
        desc: `${stats.servicing} 单服务中`,
      };
    }
    if (stats.bills) {
      return {
        title: '跟进服务单',
        desc: `${stats.bills} 单待确认`,
      };
    }
    return {
        title: orders.length ? '查看工单' : '暂无待接',
        desc: orders.length ? '看素材和进度' : '派单后显示',
    };
  },

  orderNextStep(status) {
    const map = {
      store_pending: { title: '兜底接单', desc: '看素材和地址' },
      assigned: { title: '确认接单', desc: '接单后看详情' },
      dispatched: { title: '确认接单', desc: '接单后看详情' },
      repairer_accepted: { title: '开始服务', desc: '准备工具物料' },
      accepted: { title: '开始服务', desc: '准备工具物料' },
      servicing: { title: '生成服务单', desc: '明细和保修' },
      bill_submitted: { title: '待确认', desc: '门店确认后支付' },
    };
    return map[status] || { title: '查看详情', desc: '看素材和进度' };
  },

  async acceptOrder(e) {
    const id = Number(e.currentTarget.dataset.id);
    const order = this.data.orders.find(item => item.id === id);
    if (!order) return;
    wx.showLoading({ title: '接单中' });
    try {
      await api.post(`/api/v1/orders/${id}/transition`, {
        to_status: order.status === 'assigned' ? 'accepted' : 'repairer_accepted',
        operator_type: 'repairer',
        operator_id: wx.getStorageSync('userInfo').id,
        remark: '兜底接单',
      });
      wx.hideLoading();
      wx.navigateTo({ url: `/pages/repairer/detail/detail?orderId=${id}` });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '接单失败', icon: 'none' });
    }
  },

  async fallbackOrder(e) {
    const id = Number(e.currentTarget.dataset.id);
    const userInfo = wx.getStorageSync('userInfo');
    if (!this.data.repairer) return;
    wx.showLoading({ title: '接单中' });
    try {
      await api.post(`/api/v1/orders/${id}/store-accept?manager_id=${userInfo.id}`);
      await api.post(`/api/v1/orders/${id}/assign`, { repairer_id: this.data.repairer.id });
      await api.post(`/api/v1/orders/${id}/transition`, {
        to_status: 'repairer_accepted',
        operator_type: 'repairer',
        operator_id: userInfo.id,
        remark: '兜底接单',
      });
      wx.hideLoading();
      wx.navigateTo({ url: `/pages/repairer/detail/detail?orderId=${id}` });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: err.message || '接单失败', icon: 'none' });
    }
  },

  openDetail(e) {
    wx.navigateTo({ url: `/pages/repairer/detail/detail?orderId=${e.currentTarget.dataset.id}` });
  },

  goRepairer() {
    wx.redirectTo({ url: '/pages/repairer/jobs/jobs' });
  },

  onPullDownRefresh() {
    this.loadData().then(() => wx.stopPullDownRefresh());
  },
});
