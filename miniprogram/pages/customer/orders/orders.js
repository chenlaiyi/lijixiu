// pages/customer/orders/orders.js
const api = require('../../../utils/api');
const share = require('../../../utils/share');
const statusStyle = require('../../../utils/status-style');
const serviceBill = require('../../../utils/service-bill');

function categoryIcon(category) {
  const map = {
    appliance: '/assets/categories/appliance.png',
    plumbing: '/assets/categories/plumbing.png',
    electrical: '/assets/categories/electrical.png',
    door_window: '/assets/categories/door_window.png',
    furniture_install: '/assets/categories/furniture_install.png',
    appliance_install: '/assets/categories/appliance.png',
    pipe_dredge: '/assets/categories/pipe_dredge.png',
    cleaning: '/assets/categories/cleaning.png',
    other: '/assets/categories/other.png',
  };
  return map[category] || map.other;
}

function parseOrderMedia(order) {
  try {
    const mediaList = order.media_json ? JSON.parse(order.media_json) : [];
    return Array.isArray(mediaList) ? mediaList : [];
  } catch (e) {
    return [];
  }
}

function mediaSummary(mediaList) {
  const audioCount = mediaList.filter(media => media.type === 'audio').length;
  const imageCount = mediaList.filter(media => media.type === 'image').length;
  const videoCount = mediaList.filter(media => media.type === 'video').length;
  return [
    audioCount ? `${audioCount}条语音` : '',
    imageCount ? `${imageCount}张照片` : '',
    videoCount ? `${videoCount}个视频` : '',
  ].filter(Boolean).join('、');
}

function formatShortTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  return `${month}-${day} ${hour}:${minute}`;
}

function orderPriceMeta(order) {
  const price = Number(order && order.price);
  const hasPrice = Number.isFinite(price) && price > 0;
  if (hasPrice) {
    return {
      priceLabel: `¥${price.toFixed(2)}`,
      priceTone: 'priced',
    };
  }
  if (order && order.status === 'cancelled') {
    return {
      priceLabel: '已取消',
      priceTone: 'muted',
    };
  }
  return {
    priceLabel: '待报价',
    priceTone: 'pending',
  };
}

Page({
  ...share.create({
    title: '立即修｜订单',
  }),

  data: {
    orders: [],
    loading: true,
    loadFailed: false,
    summary: { active: 0, waitPay: 0, completed: 0 },
    nextHint: {
      title: '暂无待办',
      desc: '无需处理',
      icon: '/assets/ui/receipt.png',
      orderId: null,
      action: 'none',
      tone: 'neutral',
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
      appliance: '家电维修', plumbing: '水路管道', electrical: '电路照明',
      door_window: '门窗维修', furniture_install: '家具安装',
      appliance_install: '家电安装', pipe_dredge: '管道疏通',
      cleaning: '清洁保养', other: '其他服务',
    },
  },

  onShow() {
    share.enable();
    this.loadOrders();
  },

  async loadOrders() {
    this.setData({ loading: true, loadFailed: false });
    try {
      const userInfo = wx.getStorageSync('userInfo');
      if (!userInfo) {
        this.setData({ loading: false });
        return;
      }
      const orders = await api.get(`/api/v1/orders?customer_id=${userInfo.id}&limit=100`);
      const billMap = {};
      await Promise.all(orders
        .filter(item => ['bill_submitted', 'wait_payment', 'paid', 'paid_pending_review', 'store_reviewed', 'completed'].includes(item.status))
        .map(async item => {
          billMap[item.id] = await api.get(`/api/v1/orders/${item.id}/service-bill/latest`).catch(() => null);
        }));
      const formatted = orders.map(item => {
        const mediaList = parseOrderMedia(item);
        const bill = billMap[item.id];
        const billItems = serviceBill.parseItems(bill);
        const totalAmount = Math.max(
          Number(item.price || 0),
          Number((bill && bill.amount) || 0),
        );
        const canPay = ['wait_payment', 'bill_submitted'].includes(item.status)
          && totalAmount > Number(item.paid_amount || 0);
        const nextStep = this.customerNextStep(item.status);
        const priceMeta = orderPriceMeta(item);
        return {
          ...item,
          statusText: this.data.statusMap[item.status] || item.status,
          statusTone: statusStyle.orderStatusTone(item.status),
          categoryText: this.data.categoryMap[item.category] || item.category,
          categoryIcon: categoryIcon(item.category),
          priceText: Number(item.price || 0).toFixed(2),
          priceLabel: priceMeta.priceLabel,
          priceTone: priceMeta.priceTone,
          createdText: formatShortTime(item.created_at || item.createdAt),
          mediaSummary: mediaSummary(mediaList),
          bill,
          billItems,
          hasBill: Boolean(bill),
          billAmountText: Number((bill && bill.amount) || item.price || 0).toFixed(2),
          billWarrantyText: bill ? `${Number(bill.warranty_days || 0)}天` : '',
          canPay,
          payActionText: item.status === 'bill_submitted' ? '确认并支付' : '支付',
          nextStepTitle: nextStep.title,
          nextStepDesc: nextStep.desc,
        };
      });
      const summary = this.buildSummary(formatted);
      this.setData({
        orders: formatted,
        summary,
        nextHint: this.buildNextHint(formatted, summary),
        loading: false,
      });
    } catch {
      this.setData({ loading: false, loadFailed: true });
    }
  },

  buildSummary(orders) {
    return {
      active: orders.filter(item => !['completed', 'cancelled'].includes(item.status)).length,
      waitPay: orders.filter(item => item.canPay).length,
      completed: orders.filter(item => item.status === 'completed').length,
    };
  },

  buildNextHint(orders, summary) {
    const firstPayOrder = orders.find(item => item.canPay);
    if (firstPayOrder) {
      return {
        title: '确认并支付',
        desc: `#${firstPayOrder.id} 待支付`,
        icon: '/assets/ui/pay.png',
        orderId: firstPayOrder.id,
        action: 'pay',
        tone: 'pay',
      };
    }
    const activeOrder = orders.find(item => !['completed', 'cancelled'].includes(item.status));
    if (activeOrder) {
      return {
        title: '查看进度',
        desc: `#${activeOrder.id} 进行中`,
        icon: '/assets/ui/bill-file.png',
        orderId: activeOrder.id,
        action: 'detail',
        tone: 'active',
      };
    }
    if (summary.completed) {
      return {
        title: '历史记录',
        desc: '可回看',
        icon: '/assets/ui/bill-check.png',
        orderId: null,
        action: 'none',
        tone: 'done',
      };
    }
    return {
      title: '暂无待办',
      desc: '无需处理',
      icon: '/assets/ui/receipt.png',
      orderId: null,
      action: 'none',
      tone: 'neutral',
    };
  },

  handleNextHint(e) {
    const { id, action } = e.currentTarget.dataset;
    if (action === 'pay' && id) {
      wx.navigateTo({ url: `/pages/customer/pay/pay?orderId=${id}` });
      return;
    }
    if (action === 'detail' && id) {
      wx.navigateTo({ url: `/pages/customer/detail/detail?orderId=${id}` });
    }
  },

  customerNextStep(status) {
    if (['store_pending', 'created'].includes(status)) {
      return {
        title: '等待门店受理',
        desc: '已提交',
      };
    }
    if (['store_accepted', 'assigned', 'dispatched'].includes(status)) {
      return {
        title: '等待接单',
        desc: '门店已受理',
      };
    }
    if (['repairer_accepted', 'accepted', 'servicing'].includes(status)) {
      return {
        title: '等待服务单',
        desc: '服务后生成明细',
      };
    }
    if (['bill_submitted', 'wait_payment'].includes(status)) {
      return {
        title: '确认并支付',
        desc: '核对服务单',
      };
    }
    if (['paid', 'paid_pending_review'].includes(status)) {
      return {
        title: '等待审核',
        desc: '审核后完成',
      };
    }
    if (status === 'store_reviewed') {
      return {
        title: '等待归档',
        desc: '服务记录已保存',
      };
    }
    if (status === 'completed') {
      return {
        title: '订单已完成',
        desc: '服务记录已保存',
      };
    }
    if (status === 'cancelled') {
      return {
        title: '订单已取消',
        desc: '可重新报修',
      };
    }
    return {
      title: '查看订单进度',
      desc: '看详情',
    };
  },

  /** 点击去支付 */
  async goPay(e) {
    const id = e.currentTarget.dataset.id;
    const status = e.currentTarget.dataset.status;
    if (status === 'bill_submitted') {
      wx.showLoading({ title: '确认中' });
      try {
        await api.post(`/api/v1/orders/${id}/service-bill/confirm`);
      } catch (err) {
        wx.hideLoading();
        wx.showToast({ title: err.message || '确认失败', icon: 'none' });
        return;
      }
      wx.hideLoading();
    }
    wx.navigateTo({ url: `/pages/customer/pay/pay?orderId=${id}` });
  },

  /** 查看详情 */
  goDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/customer/detail/detail?orderId=${id}` });
  },

  goHome() {
    wx.redirectTo({ url: '/pages/customer/home/home' });
  },

  /** 下拉刷新 */
  onPullDownRefresh() {
    this.loadOrders().then(() => wx.stopPullDownRefresh());
  },
});
