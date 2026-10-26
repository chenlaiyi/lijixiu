// pages/customer/home/home.js
const api = require('../../../utils/api');
const share = require('../../../utils/share');
const statusStyle = require('../../../utils/status-style');

const HOME_RECENT_ORDER_LIMIT = 3;
const HOME_RECENT_FETCH_LIMIT = 5;

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

function displayName(userInfo) {
  if (!userInfo) return '你好';
  const name = String(userInfo.name || userInfo.nickname || '').trim();
  if (name) return name;
  const phone = String(userInfo.phone || '').trim();
  return phone ? `尾号${phone.slice(-4)}` : '你好';
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

function formatSyncTime(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  return `${hour}:${minute}`;
}

function orderPriceMeta(order) {
  const price = Number(order && order.price);
  const hasPrice = Number.isFinite(price) && price > 0;
  if (hasPrice) {
    return {
      priceLabel: `¥${price.toFixed(2)}`,
      priceHint: '服务金额',
      priceTone: 'priced',
    };
  }
  if (order && order.status === 'cancelled') {
    return {
      priceLabel: '已取消',
      priceHint: '订单状态',
      priceTone: 'muted',
    };
  }
  return {
    priceLabel: '待报价',
    priceHint: '报价状态',
    priceTone: 'pending',
  };
}

function buildHomeNotice(activeCount, waitPayCount) {
  if (waitPayCount > 0) {
    return {
      tone: 'pay',
      icon: '/assets/ui/pay.png',
      title: '有服务单待支付',
      desc: '核对服务单后支付',
      highlight: '待支付',
      actionText: '去处理',
      action: 'orders',
    };
  }
  if (activeCount > 0) {
    return {
      tone: 'progress',
      icon: '/assets/ui/repairer.png',
      title: '维修进行中',
      desc: '查看最新进度',
      highlight: '处理中',
      actionText: '看进度',
      action: 'orders',
    };
  }
  return {
    tone: 'ready',
    icon: '/assets/ui/bill-file.png',
    title: '开始报修',
    desc: '选类型补故障',
    highlight: '开始报修',
    actionText: '开始报修',
    action: 'order',
  };
}

function buildHeroSummary(activeCount, waitPayCount) {
  if (waitPayCount > 0) {
    return {
      tone: 'pay',
      icon: '/assets/ui/pay.png',
      label: '需要处理',
      title: `${waitPayCount} 单待支付`,
      desc: '核对服务单后支付',
      action: 'orders',
    };
  }
  if (activeCount > 0) {
    return {
      tone: 'progress',
      icon: '/assets/ui/repairer.png',
      label: '处理中',
      title: `${activeCount} 单正在处理`,
      desc: '查看最新进度',
      action: 'orders',
    };
  }
  return {
    tone: 'ready',
      icon: '/assets/ui/bill-file.png',
      label: '报修',
      title: '暂无进行中',
      desc: '选类型即可报修',
    action: 'order',
  };
}

function buildLoadingHeroSummary() {
  return {
    tone: 'sync',
    icon: '/assets/ui/receipt.png',
    label: '加载中',
    title: '加载订单',
    desc: '加载中',
    action: 'orders',
  };
}

function buildLoadFailedNotice() {
  return {
    tone: 'failed',
    icon: '/assets/ui/receipt.png',
    title: '加载失败',
    desc: '点击重试',
    highlight: '加载失败',
    actionText: '重试',
    action: 'reload',
  };
}

function buildLoadFailedHeroSummary() {
  return {
    tone: 'failed',
    icon: '/assets/ui/receipt.png',
    label: '加载失败',
    title: '订单暂未加载',
    desc: '点此重试',
    action: 'reload',
  };
}

function buildRecentSubtitle(activeCount, waitPayCount) {
  if (waitPayCount > 0) return `${waitPayCount} 单待支付`;
  if (activeCount > 0) return `${activeCount} 单进行中`;
  return '暂无进行中';
}

function buildStatusHighlightCount(activeCount, waitPayCount) {
  if (waitPayCount > 0) return `${waitPayCount} 单待支付`;
  if (activeCount > 0) return `${activeCount} 单进行中`;
  return '暂无进行中';
}

function buildOrderBadgeText(activeCount, waitPayCount) {
  const count = waitPayCount > 0 ? waitPayCount : activeCount;
  if (!count) return '';
  return count > 9 ? '9+' : String(count);
}

function buildOrderBadgeTone(activeCount, waitPayCount) {
  if (waitPayCount > 0) return 'pay';
  if (activeCount > 0) return 'progress';
  return '';
}

function shortNextStepTitle(status, nextStep) {
  if (['bill_submitted', 'wait_payment'].includes(status)) return '确认并支付';
  if (['repairer_accepted', 'accepted', 'servicing'].includes(status)) return '等待服务单';
  if (['store_accepted', 'assigned', 'dispatched'].includes(status)) return '等待接单';
  if (['store_pending', 'created'].includes(status)) return '等待受理';
  if (['paid', 'paid_pending_review'].includes(status)) return '等待审核';
  if (status === 'completed') return '服务记录已归档';
  if (status === 'cancelled') return '订单已取消';
  return nextStep.title;
}

function homeActionMeta(status, canPay) {
  if (canPay) {
    return {
      actionLabel: '待支付',
      actionIcon: '/assets/ui/pay.png',
      actionTone: 'pay',
    };
  }
  if (['store_pending', 'created'].includes(status)) {
    return {
      actionLabel: '受理',
      actionIcon: '/assets/ui/receipt.png',
      actionTone: 'waiting',
    };
  }
  if (['store_accepted', 'assigned', 'dispatched'].includes(status)) {
    return {
      actionLabel: '派单',
      actionIcon: '/assets/ui/repairer.png',
      actionTone: 'progress',
    };
  }
  if (['repairer_accepted', 'accepted', 'servicing'].includes(status)) {
    return {
      actionLabel: '服务',
      actionIcon: '/assets/ui/repairer.png',
      actionTone: 'progress',
    };
  }
  if (['paid', 'paid_pending_review', 'store_reviewed'].includes(status)) {
    return {
      actionLabel: '审核',
      actionIcon: '/assets/ui/bill-check.png',
      actionTone: 'success',
    };
  }
  if (status === 'completed') {
    return {
      actionLabel: '记录',
      actionIcon: '/assets/ui/bill-check.png',
      actionTone: 'success',
    };
  }
  if (status === 'cancelled') {
    return {
      actionLabel: '看详情',
      actionIcon: '/assets/ui/receipt.png',
      actionTone: 'neutral',
    };
  }
  return {
    actionLabel: '看详情',
    actionIcon: '/assets/ui/receipt.png',
    actionTone: 'neutral',
  };
}

function buildHomeChips(order, mediaText) {
  return [
    {
      icon: mediaText ? '/assets/ui/image.png' : '/assets/ui/mic.png',
      text: mediaText ? `素材 ${mediaText}` : '无素材',
    },
    {
      icon: '/assets/ui/address.png',
      text: order.address ? '地址已填写' : '待补地址',
    },
    {
      icon: '/assets/ui/bill-file.png',
      text: order.created_at || order.createdAt ? `提交 ${formatShortTime(order.created_at || order.createdAt)}` : '已提交',
    },
  ];
}

Page({
  ...share.create({
    title: '立即修｜上门维修',
  }),

  data: {
    promiseItems: [
      { title: '明细报价', desc: '价格清楚', icon: '/assets/ui/bill-check.png', tone: 'tone-quote' },
      { title: '现场素材', desc: '先看现场', icon: '/assets/ui/mic.png', tone: 'tone-material' },
      { title: '服务后付', desc: '核对再付', icon: '/assets/ui/pay.png', tone: 'tone-pay' },
    ],
    guideChecks: [
      { label: '师傅可见', icon: '/assets/ui/repairer.png' },
      { label: '准备工具', icon: '/assets/ui/bill-file.png' },
      { label: '判断更准', icon: '/assets/ui/bill-check.png' },
    ],
    serviceFlow: [
      { step: '01', title: '提交', desc: '现场素材', icon: '/assets/ui/bill-file.png', tone: 'tone-submit' },
      { step: '02', title: '受理', desc: '查看后派单', icon: '/assets/ui/admin.png', tone: 'tone-store' },
      { step: '03', title: '上门', desc: '带工具服务', icon: '/assets/ui/repairer.png', tone: 'tone-worker' },
      { step: '04', title: '支付', desc: '明细和凭证', icon: '/assets/ui/bill-check.png', tone: 'tone-pay' },
    ],
    mediaBadges: [
      { type: 'audio', label: '语音', desc: '录声音', icon: '/assets/ui/mic.png', tone: 'tone-audio' },
      { type: 'image', label: '照片', desc: '拍现场', icon: '/assets/ui/image.png', tone: 'tone-image' },
      { type: 'video', label: '视频', desc: '拍过程', icon: '/assets/ui/video.png', tone: 'tone-video' },
    ],
    loadingSteps: [
      { label: '订单', icon: '/assets/ui/receipt.png' },
      { label: '接单', icon: '/assets/ui/repairer.png' },
      { label: '支付', icon: '/assets/ui/pay.png' },
    ],
    syncFailedTips: [
      { label: '订单不会丢失', icon: '/assets/ui/bill-check.png' },
      { label: '可下拉刷新', icon: '/assets/ui/receipt.png' },
      { label: '也可继续报修', icon: '/assets/ui/plus.png' },
    ],
    emptyGuides: [
      { title: '选类型', desc: '直接选择', icon: '/assets/ui/bill-file.png', tone: 'tone-submit' },
      { title: '补素材', desc: '便于判断', icon: '/assets/ui/mic.png', tone: 'tone-material' },
      { title: '受理', desc: '进度可查', icon: '/assets/ui/admin.png', tone: 'tone-store' },
      { title: '服务后付', desc: '核对再付', icon: '/assets/ui/pay.png', tone: 'tone-pay' },
    ],
    categories: [
      { id: 'appliance', name: '家电维修', desc: '空调、冰箱、洗衣机', tag: '热门', tone: 'tone-appliance', icon: '/assets/categories/appliance.png' },
      { id: 'plumbing', name: '水路管道', desc: '漏水、堵塞、水龙头', tag: '急修', tone: 'tone-water', icon: '/assets/categories/plumbing.png' },
      { id: 'electrical', name: '电路照明', desc: '跳闸、灯具、开关', tag: '安全', tone: 'tone-electric', icon: '/assets/categories/electrical.png' },
      { id: 'door_window', name: '门窗维修', desc: '门锁、窗户、合页', tag: '上门', tone: 'tone-door', icon: '/assets/categories/door_window.png' },
      { id: 'furniture_install', name: '家具安装', desc: '柜体、床、桌椅安装', tag: '安装', tone: 'tone-furniture', icon: '/assets/categories/furniture_install.png' },
      { id: 'pipe_dredge', name: '管道疏通', desc: '下水道、地漏、马桶', tag: '疏通', tone: 'tone-pipe', icon: '/assets/categories/pipe_dredge.png' },
      { id: 'cleaning', name: '清洁保养', desc: '清洗、保养、巡检', tag: '保养', tone: 'tone-clean', icon: '/assets/categories/cleaning.png' },
      { id: 'other', name: '其他服务', desc: '无法归类的问题', tag: '咨询', tone: 'tone-other', icon: '/assets/categories/other.png' },
    ],
    featuredCategories: [
      { id: 'appliance', shortName: '家电', name: '家电维修', desc: '空调冰箱', tag: '热门', tone: 'tone-appliance', icon: '/assets/categories/appliance.png' },
      { id: 'plumbing', shortName: '水路', name: '水路管道', desc: '漏水堵塞', tag: '急修', tone: 'tone-water', icon: '/assets/categories/plumbing.png' },
      { id: 'electrical', shortName: '电路', name: '电路照明', desc: '跳闸灯具', tag: '安全', tone: 'tone-electric', icon: '/assets/categories/electrical.png' },
      { id: 'pipe_dredge', shortName: '疏通', name: '管道疏通', desc: '马桶地漏', tag: '高频', tone: 'tone-pipe', icon: '/assets/categories/pipe_dredge.png' },
    ],
    moreCategories: [
      { id: 'door_window', name: '门窗维修', desc: '门锁、窗户、合页', tag: '上门', tone: 'tone-door', icon: '/assets/categories/door_window.png' },
      { id: 'furniture_install', name: '家具安装', desc: '柜体、床、桌椅安装', tag: '安装', tone: 'tone-furniture', icon: '/assets/categories/furniture_install.png' },
      { id: 'cleaning', name: '清洁保养', desc: '清洗、保养、巡检', tag: '保养', tone: 'tone-clean', icon: '/assets/categories/cleaning.png' },
      { id: 'other', name: '其他服务', desc: '无法归类的问题', tag: '咨询', tone: 'tone-other', icon: '/assets/categories/other.png' },
    ],
    selectedCategory: '',
    recentOrders: [],
    userInfo: null,
    activeCount: 0,
    waitPayCount: 0,
    recentLoading: true,
    recentLoadFailed: false,
    displayName: '你好',
    greeting: '',
    syncStatusText: '加载中',
    syncHint: '加载订单',
    homeNotice: buildHomeNotice(0, 0),
    showStatusDock: false,
    statusHighlightCount: buildStatusHighlightCount(0, 0),
    heroSummary: buildLoadingHeroSummary(),
    orderBadgeText: '',
    orderBadgeTone: '',
    recentSubtitle: '加载订单',
    navPaddingTop: 72,
    capsuleRightReserve: 108,
  },

  onLoad() {
    this._applyNavSafeArea();
    this._updateGreeting();
  },

  onShow() {
    share.enable();
    this._updateGreeting();
    this._loadRecentOrders();
  },

  _updateGreeting() {
    const hour = new Date().getHours();
    let greeting = '你好';
    if (hour < 5) greeting = '夜深了';
    else if (hour < 11) greeting = '上午好';
    else if (hour < 13) greeting = '中午好';
    else if (hour < 18) greeting = '下午好';
    else greeting = '晚上好';
    this.setData({ greeting });
  },

  _checkLogin() {
    return Boolean(wx.getStorageSync('token'));
  },

  _applyNavSafeArea() {
    const app = getApp();
    const metrics = app.getNavMetrics ? app.getNavMetrics() : null;
    if (!metrics) return;
    this.setData({
      navPaddingTop: metrics.customPageTop,
      capsuleRightReserve: metrics.capsuleRightReserve,
    });
  },

  async _loadRecentOrders() {
    const hasExistingOrders = this.data.recentOrders.length > 0;
    this.setData({
      recentLoading: true,
      recentLoadFailed: false,
      syncStatusText: '加载中',
      syncHint: hasExistingOrders ? '刷新订单' : '加载订单',
      recentSubtitle: hasExistingOrders ? '刷新中' : '加载中',
      showStatusDock: hasExistingOrders || this.data.activeCount > 0 || this.data.waitPayCount > 0,
      heroSummary: hasExistingOrders ? this.data.heroSummary : buildLoadingHeroSummary(),
      orderBadgeText: hasExistingOrders ? this.data.orderBadgeText : '',
      orderBadgeTone: hasExistingOrders ? this.data.orderBadgeTone : '',
    });
    try {
      const userInfo = wx.getStorageSync('userInfo');
      if (!wx.getStorageSync('token') || !userInfo) {
        this.setData({
          recentLoading: false,
          recentOrders: [], activeCount: 0, waitPayCount: 0,
          heroSummary: buildHeroSummary(0, 0), homeNotice: buildHomeNotice(0, 0),
          syncStatusText: '未登录',
          syncHint: '可先浏览服务，登录后查看订单',
          recentSubtitle: '登录后查看',
          showStatusDock: false,
          statusHighlightCount: '未登录',
          orderBadgeText: '',
          orderBadgeTone: '',
        });
        return;
      }
      this.setData({ userInfo, displayName: displayName(userInfo) });
      const orders = await api.get(`/api/v1/orders?customer_id=${userInfo.id}&limit=${HOME_RECENT_FETCH_LIMIT}`);
      const activeCount = orders.filter(o => !['completed', 'cancelled'].includes(o.status)).length;
      const waitPayCount = orders.filter(o => ['wait_payment', 'bill_submitted'].includes(o.status) && Number(o.price || 0) > 0).length;
      const formatted = orders.slice(0, HOME_RECENT_ORDER_LIMIT).map(item => {
        const mediaList = parseOrderMedia(item);
        const mediaText = mediaSummary(mediaList);
        const nextStep = this.customerNextStep(item.status);
        const priceMeta = orderPriceMeta(item);
        const canPay = ['bill_submitted', 'wait_payment'].includes(item.status) && Number(item.price || 0) > 0;
        const actionMeta = homeActionMeta(item.status, canPay);
        return {
          ...item,
          statusText: this.statusText(item.status),
          statusTone: statusStyle.orderStatusTone(item.status),
          categoryText: this.categoryText(item.category),
          categoryIcon: categoryIcon(item.category),
          priceText: Number(item.price || 0).toFixed(2),
          priceLabel: priceMeta.priceLabel,
          priceHint: canPay ? '待确认金额' : priceMeta.priceHint,
          priceTone: priceMeta.priceTone,
          createdText: formatShortTime(item.created_at || item.createdAt),
          mediaSummary: mediaText,
          homeChips: buildHomeChips(item, mediaText),
          canPay,
          payActionText: item.status === 'bill_submitted' ? '确认并支付' : '去支付',
          nextStepTitle: nextStep.title,
          nextStepDesc: nextStep.desc,
          homeActionLabel: actionMeta.actionLabel,
          homeActionIcon: actionMeta.actionIcon,
          homeActionTone: actionMeta.actionTone,
          homePriorityText: shortNextStepTitle(item.status, nextStep),
        };
      });
      const syncTime = formatSyncTime();
      this.setData({
        recentOrders: formatted,
        activeCount,
        waitPayCount,
        homeNotice: buildHomeNotice(activeCount, waitPayCount),
        showStatusDock: activeCount > 0 || waitPayCount > 0,
        statusHighlightCount: buildStatusHighlightCount(activeCount, waitPayCount),
        heroSummary: buildHeroSummary(activeCount, waitPayCount),
        orderBadgeText: buildOrderBadgeText(activeCount, waitPayCount),
        orderBadgeTone: buildOrderBadgeTone(activeCount, waitPayCount),
        recentSubtitle: buildRecentSubtitle(activeCount, waitPayCount),
        recentLoading: false,
        syncStatusText: `${syncTime} 更新`,
        syncHint: `最近更新 ${syncTime}`,
      });
    } catch {
      this.setData({
        recentLoading: false,
        recentLoadFailed: true,
        homeNotice: buildLoadFailedNotice(),
        showStatusDock: true,
        statusHighlightCount: '加载失败',
        heroSummary: buildLoadFailedHeroSummary(),
        orderBadgeText: '',
        orderBadgeTone: '',
        recentSubtitle: '加载失败',
        syncStatusText: '加载失败',
        syncHint: '请稍后重试',
      });
    }
  },

  selectCategory(e) {
    const cat = e.currentTarget.dataset.cat;
    this.setData({ selectedCategory: cat });
    wx.navigateTo({ url: `/pages/customer/order/order?category=${cat}` });
  },

  statusText(status) {
    const map = {
      store_pending: '待受理', dispatched: '已派单', assigned: '已派单',
      repairer_accepted: '已接单', accepted: '已接单', servicing: '服务中',
      bill_submitted: '待确认', wait_payment: '待支付',
      paid: '已支付', paid_pending_review: '待审核', store_reviewed: '已审核',
      completed: '已完成', cancelled: '已取消', store_accepted: '已受理',
      created: '待受理',
    };
    return map[status] || status;
  },

  categoryText(category) {
    const found = this.data.categories.find(item => item.id === category);
    return found ? found.name : category;
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
        desc: '完成后提交明细',
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
      desc: '查看详情',
    };
  },

  handleHomeNoticeAction() {
    if (this.data.homeNotice && this.data.homeNotice.action === 'reload') {
      this.reloadRecentOrders();
      return;
    }
    if (this.data.homeNotice && this.data.homeNotice.action === 'order') {
      this.goOrder();
      return;
    }
    this.goOrders();
  },
  handleHeroSummaryAction() {
    const action = this.data.heroSummary && this.data.heroSummary.action;
    if (action === 'reload') {
      this.reloadRecentOrders();
      return;
    }
    if (action === 'order') {
      this.goOrder();
      return;
    }
    this.goOrders();
  },
  goOrder() { wx.navigateTo({ url: '/pages/customer/order/order' }); },
  goDomestic(e) {
    const type = e.currentTarget.dataset.type || 'maternity';
    wx.navigateTo({ url: `/pages/customer/domestic/list/list?type=${type}` });
  },
  goOrders() { wx.navigateTo({ url: '/pages/customer/orders/orders' }); },
  goPay(e) {
    wx.navigateTo({ url: `/pages/customer/pay/pay?orderId=${e.currentTarget.dataset.id}` });
  },
  goOrderDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/customer/detail/detail?orderId=${id}` });
  },
  goProfile() { wx.navigateTo({ url: wx.getStorageSync('token') ? '/pages/customer/profile/profile' : '/pages/login/login?intent=login' }); },
  reloadRecentOrders() { return this._loadRecentOrders(); },
  onPullDownRefresh() {
    Promise.resolve(this._loadRecentOrders()).catch(() => {}).then(() => {
      if (wx.stopPullDownRefresh) wx.stopPullDownRefresh();
    });
  },
});
