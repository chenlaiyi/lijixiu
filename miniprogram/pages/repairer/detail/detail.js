// pages/repairer/detail/detail.js
const api = require('../../../utils/api');
const share = require('../../../utils/share');
const statusStyle = require('../../../utils/status-style');

let orderAudioContext = null;

function toMoney(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(2) : '0.00';
}

function lineAmount(item) {
  return Number(item.quantity || item.qty || 0) * Number(item.unit_price || item.price || 0);
}

function sumItems(items) {
  return toMoney(items.reduce((total, item) => total + lineAmount(item), 0));
}

function buildBillReadiness(items, warrantyDays, remark = '') {
  const validCount = items.filter((item) => {
    const name = (item.name || '').trim();
    const qty = Number(item.qty || 0);
    const price = Number(item.price || 0);
    return name && qty > 0 && price > 0;
  }).length;
  const totalCount = items.length;
  const invalidCount = Math.max(0, totalCount - validCount);
  const warrantyValue = parseInt(warrantyDays, 10);
  const warrantyValid = Number.isFinite(warrantyValue) && warrantyValue >= 0;
  const hasRemark = Boolean(String(remark || '').trim());
  let title = '待完善';
  let desc = '补明细和保修';
  let tone = 'tone-warning';

  if (totalCount && validCount === totalCount && warrantyValid) {
    title = '可提交';
    desc = hasRemark ? '明细和备注已填' : '明细和保修已填';
    tone = 'tone-success';
  } else if (validCount > 0) {
    title = '继续补充';
    desc = invalidCount ? `${invalidCount} 项需补齐` : '确认保修后提交';
    tone = 'tone-waiting';
  }

  return {
    title,
    desc,
    tone,
    validCount,
    totalCount,
    totalText: sumItems(items),
    warrantyText: warrantyValid ? `${Math.max(0, warrantyValue || 0)}天` : '未填写',
    remarkText: hasRemark ? '已填写' : '可选',
  };
}

function defaultServiceItems(order) {
  const price = Number(order && order.price);
  if (Number.isFinite(price) && price > 0) {
    return [{ name: '维修服务费', qty: '1', price: toMoney(price), amount: toMoney(price) }];
  }
  return [
    { name: '上门检修服务', qty: '1', price: '80.00', amount: '80.00' },
    { name: '材料费', qty: '1', price: '48.00', amount: '48.00' },
  ];
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

function orderMediaTypeText(type) {
  const map = { audio: '语音', image: '照片', video: '视频' };
  return map[type] || '素材';
}

function orderMediaIcon(type) {
  const map = {
    audio: '/assets/ui/mic.png',
    image: '/assets/ui/image.png',
    video: '/assets/ui/video.png',
  };
  return map[type] || '/assets/ui/bill-file.png';
}

function mediaSummaryText(mediaList) {
  const audioCount = mediaList.filter(media => media.type === 'audio').length;
  const imageCount = mediaList.filter(media => media.type === 'image').length;
  const videoCount = mediaList.filter(media => media.type === 'video').length;
  const parts = [
    audioCount ? `${audioCount}条语音` : '',
    imageCount ? `${imageCount}张照片` : '',
    videoCount ? `${videoCount}个视频` : '',
  ].filter(Boolean);
  return parts.length ? `素材 ${parts.join(' · ')}` : '无素材';
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

Page({
  ...share.create({
    title() {
      const order = this.data.order;
      return order ? `立即修｜${order.categoryText || '维修'}订单详情` : '立即修｜维修订单详情';
    },
  }),

  data: {
    order: null,
    canStart: false,
    canComplete: false,
    canPay: false,
    loading: true,
    loadFailed: false,
    errorText: '',
    orderId: null,
    serviceItems: defaultServiceItems(null),
    billTotal: '128.00',
    billReadiness: buildBillReadiness(defaultServiceItems(null), '30', ''),
    warrantyDays: '30',
    warrantyErrorText: '',
    activeBillItemIndex: -1,
    focusBillField: '',
    serviceRemark: '',
    confirmationMethods: [
      { value: 'face_to_face', label: '现场口头确认' },
      { value: 'phone', label: '电话确认' },
      { value: 'wechat', label: '微信确认' },
      { value: 'other', label: '其他方式' },
    ],
    confirmationMethodIndex: 0,
    confirmationMethod: 'face_to_face',
    confirmationNote: '',
    serviceInitialized: false,
    mediaList: [],
    mediaSummaryText: '无素材',
    detailHint: {
      title: '先看素材',
      desc: '确认故障、地址、电话',
    },
    statusMap: {
      created: '待受理', assigned: '已派单', accepted: '已接单',
      store_pending: '待受理', dispatched: '已派单',
      repairer_accepted: '已接单', servicing: '服务中',
      bill_submitted: '待确认', wait_payment: '待支付',
      paid: '已支付', paid_pending_review: '待审核',
      completed: '已完成', cancelled: '已取消',
    },
    categoryMap: {
      appliance: '家电维修', plumbing: '水路管道', electrical: '电路照明',
      door_window: '门窗维修', furniture_install: '家具安装', appliance_install: '家电安装',
      pipe_dredge: '管道疏通', cleaning: '清洁保养', other: '其他服务',
    },
  },

  onLoad(options) {
    share.enable();
    if (options.orderId) {
      this.setData({ orderId: parseInt(options.orderId) });
      this.loadOrder();
    } else {
      this.setData({
        loading: false,
        loadFailed: true,
        errorText: '缺少订单编号',
      });
    }
  },

  onShow() {
    share.enable();
    if (this.data.orderId) this.loadOrder();
  },

  async loadOrder() {
    this.setData({ loading: true, loadFailed: false, errorText: '' });
    try {
      const [order, repairers] = await Promise.all([
        api.get(`/api/v1/orders/${this.data.orderId}`),
        api.get('/api/v1/repairers?limit=100').catch(() => []),
      ]);
      if (order) {
        order.statusText = this.data.statusMap[order.status] || order.status;
        order.statusTone = statusStyle.orderStatusTone(order.status);
        order.categoryText = this.data.categoryMap[order.category] || order.category;
        order.categoryIcon = categoryIcon(order.category);
        order.priceText = Number(order.price || 0).toFixed(2);
      }
      const mediaList = parseJSONList(order && order.media_json).map(item => ({
        ...item,
        fullUrl: api.resolveURL(item.url),
        durationText: item.duration ? `${item.duration}s` : '',
        typeText: orderMediaTypeText(item.type),
        icon: orderMediaIcon(item.type),
      }));
      const currentUser = wx.getStorageSync('userInfo') || {};
      const currentRepairer = repairers.find(item => item.user_id === currentUser.id);
      const isOrderRepairer = Boolean(currentRepairer && order && (
        order.repairer_id === currentRepairer.id || order.assigned_repairer_id === currentRepairer.id
      ));
      const canStart = order ? isOrderRepairer && ['accepted', 'repairer_accepted'].includes(order.status) : false;
      const canComplete = order ? isOrderRepairer && order.status === 'servicing' : false;
      const canPay = order ? order.status === 'wait_payment' && currentUser.id === order.customer_id : false;
      const viewData = {
        order: order || null,
        mediaList,
        mediaSummaryText: mediaSummaryText(mediaList),
        canStart,
        canComplete,
        canPay,
        detailHint: this.buildDetailHint(order, { canStart, canComplete, canPay, isOrderRepairer }),
        loading: false,
      };
      if (order && isOrderRepairer && order.status === 'servicing' && !this.data.serviceInitialized) {
        const serviceItems = defaultServiceItems(order);
        viewData.serviceItems = serviceItems;
        viewData.billTotal = sumItems(serviceItems);
        viewData.billReadiness = buildBillReadiness(serviceItems, this.data.warrantyDays, this.data.serviceRemark);
        viewData.serviceInitialized = true;
      } else if (canComplete) {
        viewData.billReadiness = buildBillReadiness(this.data.serviceItems, this.data.warrantyDays, this.data.serviceRemark);
      }
      this.setData(viewData);
    } catch (e) {
      this.setData({
        order: null,
        loading: false,
        loadFailed: true,
        errorText: e.message || '加载失败',
        canStart: false,
        canComplete: false,
        canPay: false,
      });
    }
  },

  buildDetailHint(order, flags) {
    if (!order) {
      return {
        title: '工单未加载',
        desc: '返回重试',
      };
    }
    if (flags.canStart) {
      return {
        title: '开始服务',
        desc: '先核对素材和地址',
      };
    }
    if (flags.canComplete) {
      return {
        title: '提交服务单',
        desc: '明细、价格、保修',
      };
    }
    if (flags.canPay) {
      return {
        title: '等待客户支付',
        desc: '客户支付后完成',
      };
    }
    if (order.status === 'bill_submitted') {
      return {
        title: '等待确认',
        desc: '门店确认后客户支付',
      };
    }
    if (order.status === 'wait_payment') {
      return {
        title: '等待支付',
        desc: '客户支付后计薪',
      };
    }
    if (['paid', 'paid_pending_review'].includes(order.status)) {
      return {
        title: '等待审核',
        desc: '审核后记工资',
      };
    }
    if (order.status === 'completed') {
      return {
        title: '订单已完成',
        desc: '服务记录已归档',
      };
    }
    if (order.status === 'cancelled') {
      return {
        title: '订单已取消',
        desc: '无需处理',
      };
    }
      return {
        title: '查看工单',
        desc: '描述、素材、地址',
    };
  },

  previewOrderMedia(e) {
    const index = Number(e.currentTarget.dataset.index);
    const item = this.data.mediaList[index];
    if (!item) return;
    if (item.type === 'image') {
      const urls = this.data.mediaList
        .filter(media => media.type === 'image')
        .map(media => media.fullUrl);
      wx.previewImage({ current: item.fullUrl, urls });
      return;
    }
    if (item.type === 'video') {
      wx.previewMedia({
        sources: [{ url: item.fullUrl, type: 'video' }],
        current: 0,
      });
      return;
    }
    if (orderAudioContext) {
      orderAudioContext.stop();
      orderAudioContext.destroy();
    }
    orderAudioContext = wx.createInnerAudioContext();
    orderAudioContext.src = item.fullUrl;
    orderAudioContext.play();
  },

  /** 开始服务（接单后 -> 服务中） */
  async startService() {
    wx.showLoading({ title: '确认中' });
    try {
      await api.post(`/api/v1/orders/${this.data.orderId}/transition`, {
        to_status: 'servicing',
        operator_type: 'repairer',
        operator_id: wx.getStorageSync('userInfo').id,
      });
      wx.hideLoading();
      wx.showToast({ title: '已开始服务', icon: 'success' });
      this.setData({ serviceInitialized: false });
      this.loadOrder();
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message || '操作失败', icon: 'none' });
    }
  },

  onBillItemFocus(e) {
    this.setData({ activeBillItemIndex: Number(e.currentTarget.dataset.index) });
  },

  onBillItemBlur() {
    this.setData({ activeBillItemIndex: -1 });
  },

  onBillFieldFocus(e) {
    this.setData({ focusBillField: e.currentTarget.dataset.field || '' });
  },

  onBillFieldBlur() {
    this.setData({ focusBillField: '' });
  },

  onBillItemInput(e) {
    const index = Number(e.currentTarget.dataset.index);
    const field = e.currentTarget.dataset.field;
    const value = e.detail.value;
    const serviceItems = this.data.serviceItems.map((item, itemIndex) => {
      if (itemIndex !== index) return item;
      const next = { ...item, [field]: value, errorText: '' };
      next.amount = toMoney(lineAmount(next));
      return next;
    });
    this.setData({
      serviceItems,
      billTotal: sumItems(serviceItems),
      billReadiness: buildBillReadiness(serviceItems, this.data.warrantyDays, this.data.serviceRemark),
    });
  },

  addBillItem() {
    const serviceItems = this.data.serviceItems.concat({
      name: '',
      qty: '1',
      price: '',
      amount: '0.00',
      errorText: '',
    });
    this.setData({
      serviceItems,
      billTotal: sumItems(serviceItems),
      billReadiness: buildBillReadiness(serviceItems, this.data.warrantyDays, this.data.serviceRemark),
    });
  },

  removeBillItem(e) {
    const index = Number(e.currentTarget.dataset.index);
    if (this.data.serviceItems.length <= 1) {
      wx.showToast({ title: '至少保留一项', icon: 'none' });
      return;
    }
    const serviceItems = this.data.serviceItems.filter((_, itemIndex) => itemIndex !== index);
    this.setData({
      serviceItems,
      billTotal: sumItems(serviceItems),
      billReadiness: buildBillReadiness(serviceItems, this.data.warrantyDays, this.data.serviceRemark),
    });
  },

  onWarrantyInput(e) {
    const warrantyDays = e.detail.value;
    this.setData({
      warrantyDays,
      warrantyErrorText: '',
      billReadiness: buildBillReadiness(this.data.serviceItems, warrantyDays, this.data.serviceRemark),
    });
  },

  onRemarkInput(e) {
    const serviceRemark = e.detail.value;
    this.setData({
      serviceRemark,
      billReadiness: buildBillReadiness(this.data.serviceItems, this.data.warrantyDays, serviceRemark),
    });
  },

  onConfirmationMethodChange(e) {
    const index = Number(e.detail.value);
    const item = this.data.confirmationMethods[index] || this.data.confirmationMethods[0];
    this.setData({ confirmationMethodIndex: index, confirmationMethod: item.value });
  },

  onConfirmationNoteInput(e) { this.setData({ confirmationNote: e.detail.value }); },

  /** 提交服务单，等待客户/门店确认 */
  async completeService(e) {
    const saveAsDraft = Boolean(e && e.currentTarget && e.currentTarget.dataset.draft);
    try {
      let hasItemError = false;
      const serviceItems = this.data.serviceItems.map((item) => {
        const name = (item.name || '').trim();
        const qty = Number(item.qty || 0);
        const price = Number(item.price || 0);
        let errorText = '';
        if (!name) {
          errorText = '填写项目名称';
        } else if (!qty || qty <= 0) {
          errorText = '数量必须大于 0';
        } else if (!price || price <= 0) {
          errorText = '单价必须大于 0';
        }
        if (errorText) hasItemError = true;
        return { ...item, errorText };
      });
      const items = serviceItems
        .filter(item => !item.errorText)
        .map(item => ({
          name: (item.name || '').trim(),
          quantity: Number(item.qty || 0),
          unit_price: Number(item.price || 0),
          subtotal: Number(lineAmount(item).toFixed(2)),
        }));
      const amount = Number(sumItems(items));
      const warrantyValue = parseInt(this.data.warrantyDays, 10);
      const warrantyErrorText = Number.isFinite(warrantyValue) && warrantyValue >= 0 ? '' : '保修天数无效';
      const warrantyDays = Math.max(0, warrantyValue || 0);

      if (hasItemError || !items.length || amount <= 0 || warrantyErrorText) {
        this.setData({
          serviceItems,
          warrantyErrorText,
          billReadiness: buildBillReadiness(serviceItems, this.data.warrantyDays, this.data.serviceRemark),
        });
        wx.showToast({ title: '完善服务单', icon: 'none' });
        return;
      }

      wx.showLoading({ title: '提交中' });
      const userInfo = wx.getStorageSync('userInfo');
      const repairers = await api.get('/api/v1/repairers?limit=100');
      const repairer = repairers.find(item => item.user_id === userInfo.id);
      const repairerId = repairer ? repairer.id : this.data.order.repairer_id;
      if (!repairerId) {
        throw new Error('未找到服务档案');
      }
      await api.post(`/api/v1/orders/${this.data.orderId}/service-bill`, {
        repairer_id: repairerId,
        title: '上门维修服务单',
        items_json: JSON.stringify(items),
        amount,
        warranty_days: warrantyDays,
        media_json: JSON.stringify({
          remark: this.data.serviceRemark || '',
          source: 'miniprogram',
        }),
        save_as_draft: saveAsDraft,
        confirmation_method: this.data.confirmationMethod,
        confirmation_note: this.data.confirmationNote || this.data.serviceRemark || '',
      });
      wx.hideLoading();
      wx.showToast({ title: saveAsDraft ? '草稿已保存' : '服务单已提交', icon: 'success' });
      this.loadOrder();
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message || '操作失败', icon: 'none' });
    }
  },

  goPay() {
    wx.navigateTo({ url: `/pages/customer/pay/pay?orderId=${this.data.orderId}` });
  },

  retryLoad() {
    if (!this.data.orderId) {
      this.goJobs();
      return;
    }
    this.loadOrder();
  },

  goJobs() {
    wx.redirectTo({ url: '/pages/repairer/jobs/jobs' });
  },

  onUnload() {
    if (orderAudioContext) {
      orderAudioContext.destroy();
      orderAudioContext = null;
    }
  },
});
