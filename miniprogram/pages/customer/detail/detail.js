// pages/customer/detail/detail.js
const api = require('../../../utils/api');
const share = require('../../../utils/share');
const statusStyle = require('../../../utils/status-style');
const serviceBill = require('../../../utils/service-bill');

let orderAudioContext = null;

function money(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(2) : '0.00';
}

function parseJSONList(value) {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch (e) {
    return [];
  }
}

function mediaTypeText(type) {
  const map = { audio: '语音', image: '照片', video: '视频' };
  return map[type] || '素材';
}

function mediaIcon(type) {
  const map = {
    audio: '/assets/ui/mic.png',
    image: '/assets/ui/image.png',
    video: '/assets/ui/video.png',
  };
  return map[type] || '/assets/ui/bill-file.png';
}

function categoryIcon(category) {
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
}

function mediaSummary(mediaList) {
  const audioCount = mediaList.filter(item => item.type === 'audio').length;
  const imageCount = mediaList.filter(item => item.type === 'image').length;
  const videoCount = mediaList.filter(item => item.type === 'video').length;
  const parts = [
    audioCount ? `${audioCount}条语音` : '',
    imageCount ? `${imageCount}张照片` : '',
    videoCount ? `${videoCount}个视频` : '',
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : '无素材';
}

Page({
  ...share.create({
    title() {
      const order = this.data.order;
      return order ? `立即修｜${order.categoryText || '维修'}订单详情` : '立即修｜订单详情';
    },
  }),

  data: {
    orderId: null,
    order: null,
    bill: null,
    billItems: [],
    mediaList: [],
    mediaSummaryText: '无素材',
    loading: true,
    loadFailed: false,
    errorText: '',
    canPay: false,
    detailHint: {
      title: '加载中…',
      desc: '',
      icon: '/assets/ui/receipt.png',
      tone: 'progress',
    },
    statusMap: {
      created: '待受理',
      store_pending: '待受理',
      store_accepted: '已受理',
      dispatched: '已派单',
      assigned: '已派单',
      repairer_accepted: '师傅已接',
      accepted: '已接单',
      servicing: '服务中',
      bill_submitted: '待确认',
      bill_returned: '服务单退回',
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

  onLoad(options) {
    share.enable();
    if (options.orderId) {
      this.setData({ orderId: parseInt(options.orderId, 10) });
      this.loadOrder();
      return;
    }
    this.setData({
      loading: false,
      loadFailed: true,
      errorText: '缺少订单编号',
    });
  },

  onShow() {
    share.enable();
  },

  async loadOrder() {
    if (!this.data.orderId) return;
    this.setData({ loading: true, loadFailed: false, errorText: '' });
    try {
      const [rawOrder, bill] = await Promise.all([
        api.get(`/api/v1/orders/${this.data.orderId}`),
        api.get(`/api/v1/orders/${this.data.orderId}/service-bill/latest`).catch(() => null),
      ]);
      const order = this.formatOrder(rawOrder);
      const billItems = this.parseBillItems(bill);
      const mediaList = parseJSONList(order && order.media_json).map(item => ({
        ...item,
        fullUrl: api.resolveURL(item.url),
        typeText: mediaTypeText(item.type),
        icon: mediaIcon(item.type),
        durationText: item.duration ? `${item.duration}s` : '',
        name: item.name || mediaTypeText(item.type),
      }));
      this.setData({
        order,
        bill: this.formatBill(bill, order),
        billItems,
        mediaList,
        mediaSummaryText: mediaSummary(mediaList),
        canPay: order
          ? ['bill_submitted', 'wait_payment'].includes(order.status)
            && Math.max(Number(order.price || 0), Number((bill && bill.amount) || 0)) > Number(order.paid_amount || 0)
          : false,
        detailHint: this.buildDetailHint(order),
        loading: false,
      });
    } catch (e) {
      this.setData({
        order: null,
        bill: null,
        billItems: [],
        mediaList: [],
        loading: false,
        loadFailed: true,
        errorText: e.message || '加载失败',
      });
    }
  },

  formatOrder(order) {
    if (!order) return null;
    return {
      ...order,
      statusText: this.data.statusMap[order.status] || order.status,
      statusTone: statusStyle.orderStatusTone(order.status),
      categoryText: this.data.categoryMap[order.category] || order.category,
      categoryIcon: categoryIcon(order.category),
      priceText: money(order.price || 0),
    };
  },

  formatBill(bill, order) {
    if (!bill) return null;
    const amount = bill.amount || (order && order.price) || 0;
    return {
      ...bill,
      amountText: money(amount),
      warrantyText: Number.isFinite(Number(bill.warranty_days)) ? `${Number(bill.warranty_days)}天` : '未设置',
    };
  },

  parseBillItems(bill) {
    return serviceBill.parseItems(bill);
  },

  buildDetailHint(order) {
    if (!order) {
      return {
        title: '订单信息未加载',
        desc: '返回重试',
        icon: '/assets/ui/receipt.png',
        tone: 'progress',
      };
    }
    if (['store_pending', 'created'].includes(order.status)) {
      return {
        title: '等待门店受理',
        desc: '已提交',
        icon: '/assets/ui/admin.png',
        tone: 'progress',
      };
    }
    if (['store_accepted', 'assigned', 'dispatched'].includes(order.status)) {
      return {
        title: '等待接单',
        desc: '门店已受理',
        icon: '/assets/ui/repairer.png',
        tone: 'progress',
      };
    }
    if (['repairer_accepted', 'accepted', 'servicing'].includes(order.status)) {
      return {
        title: '服务中',
        desc: '服务后生成明细',
        icon: '/assets/ui/bill-file.png',
        tone: 'progress',
      };
    }
    if (['bill_submitted', 'wait_payment'].includes(order.status)) {
      return {
        title: '确认并支付',
        desc: '核对服务单',
        icon: '/assets/ui/pay.png',
        tone: 'pay',
      };
    }
    if (['paid', 'paid_pending_review'].includes(order.status)) {
      return {
        title: '等待审核',
        desc: '审核后完成',
        icon: '/assets/ui/bill-check.png',
        tone: 'review',
      };
    }
    if (order.status === 'completed') {
      return {
        title: '订单已完成',
        desc: '服务记录已保存',
        icon: '/assets/ui/bill-check.png',
        tone: 'done',
      };
    }
    if (order.status === 'cancelled') {
      return {
        title: '订单已取消',
        desc: '可重新报修',
        icon: '/assets/ui/receipt.png',
        tone: 'progress',
      };
    }
    return {
      title: '查看进度',
      desc: '看详情',
      icon: '/assets/ui/receipt.png',
      tone: 'progress',
    };
  },

  previewOrderMedia(e) {
    const index = Number(e.currentTarget.dataset.index);
    const item = this.data.mediaList[index];
    if (!item) return;
    if (item.type === 'image') {
      const urls = this.data.mediaList.filter(media => media.type === 'image').map(media => media.fullUrl);
      wx.previewImage({ current: item.fullUrl, urls });
      return;
    }
    if (item.type === 'video') {
      wx.previewMedia({ sources: [{ url: item.fullUrl, type: 'video' }], current: 0 });
      return;
    }
    if (orderAudioContext) {
      orderAudioContext.stop();
      orderAudioContext.destroy();
    }
    orderAudioContext = wx.createInnerAudioContext();
    orderAudioContext.src = item.fullUrl;
    orderAudioContext.play();
    wx.showToast({ title: '正在播放语音', icon: 'none' });
  },

  goPay() {
    wx.navigateTo({ url: `/pages/customer/pay/pay?orderId=${this.data.orderId}` });
  },

  retryLoad() {
    this.loadOrder();
  },

  goOrders() {
    wx.redirectTo({ url: '/pages/customer/orders/orders' });
  },

  onPullDownRefresh() {
    this.loadOrder().then(() => wx.stopPullDownRefresh());
  },

  onUnload() {
    if (orderAudioContext) {
      orderAudioContext.destroy();
      orderAudioContext = null;
    }
  },
});
