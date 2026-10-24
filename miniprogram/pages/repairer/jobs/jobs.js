// pages/repairer/jobs/jobs.js
const api = require('../../../utils/api');
const share = require('../../../utils/share');
const statusStyle = require('../../../utils/status-style');

Page({
  ...share.create({
    title: '立即修｜工单',
  }),

  data: {
    orders: [],
    workOrders: [],
    loading: true,
    loadFailed: false,
    userInfo: null,
    repairer: null,
    stats: { pending: 0, working: 0 },
    nextHint: {
      title: '暂无工单',
      desc: '派单后显示',
    },
  },

  onShow() {
    share.enable();
    const ui = wx.getStorageSync('userInfo');
    if (!ui) {
      wx.reLaunch({ url: '/pages/login/login' });
      return;
    }
    this.setData({ userInfo: ui });
    this.loadJobs();
  },

  async loadJobs() {
    this.setData({ loading: true, loadFailed: false });
    try {
      const repairers = await api.get('/api/v1/repairers?limit=100');
      const repairer = repairers.find(item => item.user_id === this.data.userInfo.id);
      if (!repairer) {
        this.setData({
          repairer: null,
          orders: [],
          workOrders: [],
          stats: { pending: 0, working: 0 },
          nextHint: this.getNextHint(0, 0),
          loading: false,
        });
        return;
      }
      const [assigned, dispatched, servicing, billSubmitted, waitPayment] = await Promise.all([
        api.get(`/api/v1/orders?assigned_repairer_id=${repairer.id}&status=assigned&limit=100`).catch(() => []),
        api.get(`/api/v1/orders?assigned_repairer_id=${repairer.id}&status=dispatched&limit=100`).catch(() => []),
        api.get(`/api/v1/orders?repairer_id=${repairer.id}&status=servicing&limit=100`).catch(() => []),
        api.get(`/api/v1/orders?repairer_id=${repairer.id}&status=bill_submitted&limit=100`).catch(() => []),
        api.get(`/api/v1/orders?repairer_id=${repairer.id}&status=wait_payment&limit=100`).catch(() => []),
      ]);
      const pendingOrders = [...assigned, ...dispatched].map(item => this.formatOrder(item));
      const workingOrders = [...servicing, ...billSubmitted, ...waitPayment].map(item => this.formatOrder(item));
      this.setData({
        repairer,
        orders: pendingOrders,
        workOrders: workingOrders,
        stats: { pending: pendingOrders.length, working: workingOrders.length },
        nextHint: this.getNextHint(pendingOrders.length, workingOrders.length),
        loading: false,
      });
    } catch {
      this.setData({ loading: false, loadFailed: true });
    }
  },

  /** 接单 */
  async acceptOrder(e) {
    const orderId = e.currentTarget.dataset.id;
    wx.showLoading({ title: '接单中' });
    try {
      await api.post(`/api/v1/orders/${orderId}/transition`, {
        to_status: e.currentTarget.dataset.status === 'assigned' ? 'accepted' : 'repairer_accepted',
        operator_type: 'repairer',
        operator_id: this.data.userInfo.id,
      });
      wx.hideLoading();
      wx.showToast({ title: '接单成功', icon: 'success' });
      wx.navigateTo({ url: `/pages/repairer/detail/detail?orderId=${orderId}` });
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message || '接单失败', icon: 'none' });
    }
  },

  formatOrder(item) {
    const statusMap = {
      assigned: '待接单', dispatched: '待接单', repairer_accepted: '已接单',
      accepted: '已接单', servicing: '服务中', bill_submitted: '待确认',
      wait_payment: '待支付，可修改服务单',
    };
    const categoryMap = {
      appliance: '家电维修', plumbing: '水路管道', electrical: '电路照明',
      door_window: '门窗维修', furniture_install: '家具安装', appliance_install: '家电安装',
      pipe_dredge: '管道疏通', cleaning: '清洁保养', other: '其他服务',
    };
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
      statusText: statusMap[item.status] || item.status,
      statusTone: statusStyle.orderStatusTone(item.status),
      categoryText: categoryMap[item.category] || item.category,
      categoryIcon: this.categoryIcon(item.category),
      mediaSummary: [
        audioCount ? `${audioCount}条语音` : '',
        imageCount ? `${imageCount}张照片` : '',
        videoCount ? `${videoCount}个视频` : '',
      ].filter(Boolean).join(' · '),
      primaryActionText: '接单',
    };
  },

  getNextHint(pendingCount, workingCount) {
    if (pendingCount > 0) {
      return {
        title: `${pendingCount} 单待接`,
        desc: '看素材和地址',
      };
    }
    if (workingCount > 0) {
      return {
        title: `${workingCount} 单服务中`,
        desc: '完成后提交明细',
      };
    }
    return {
      title: '暂无工单',
      desc: '派单后显示',
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

  /** 查看详情 */
  goDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/repairer/detail/detail?orderId=${id}` });
  },

  /** 切换为用户身份 */
  goProxyOrder() {
    wx.redirectTo({ url: '/pages/staff/proxy-order/proxy-order' });
  },

  onPullDownRefresh() {
    this.loadJobs().then(() => wx.stopPullDownRefresh());
  },
});
