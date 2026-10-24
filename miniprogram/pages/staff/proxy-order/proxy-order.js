const api = require('../../../utils/api');
const role = require('../../../utils/role');
const share = require('../../../utils/share');

const recorder = wx.getRecorderManager();
let audioContext = null;

const MAX_AUDIO_DURATION_MS = 10 * 60 * 1000;
const MAX_VIDEO_DURATION_SECONDS = 60;
const MAX_IMAGE_COUNT = 6;

function callWx(method, options = {}) {
  return new Promise((resolve, reject) => {
    if (!wx[method]) {
      reject(new Error(`${method} 当前不可用`));
      return;
    }
    wx[method]({
      ...options,
      success: resolve,
      fail: reject,
    });
  });
}

function isCancelError(error) {
  const message = String((error && (error.errMsg || error.message)) || error || '').toLowerCase();
  return message.indexOf('cancel') !== -1 || message.indexOf('取消') !== -1;
}

function basename(filePath, fallback) {
  const value = String(filePath || '');
  const name = value.split(/[\\/]/).pop();
  return name || fallback;
}

function mediaTypeText(type) {
  const map = { audio: '语音', image: '照片', video: '视频' };
  return map[type] || '素材';
}

function mediaTypeIcon(type) {
  const map = {
    audio: '/assets/ui/mic.png',
    image: '/assets/ui/image.png',
    video: '/assets/ui/video.png',
  };
  return map[type] || '/assets/ui/bill-file.png';
}

function buildMediaStats(mediaList, description = '') {
  const audioCount = mediaList.filter(item => item.type === 'audio').length;
  const imageCount = mediaList.filter(item => item.type === 'image').length;
  const videoCount = mediaList.filter(item => item.type === 'video').length;
  const total = mediaList.length;
  const hasDescription = Boolean(String(description || '').trim());
  const title = total ? `已加 ${total} 个素材` : (hasDescription ? '已写描述' : '可补充素材');
  const desc = total ? '师傅接单前可查看' : '语音、照片、视频可选';
  return { audioCount, imageCount, videoCount, total, title, desc };
}

function makeMediaItem(type, tempFilePath, index, duration = 0) {
  const safeDuration = Math.max(0, Math.round(Number(duration || 0)));
  return {
    key: `${type}_${Date.now()}_${index}_${Math.floor(Math.random() * 10000)}`,
    type,
    tempFilePath,
    duration: safeDuration,
    name: type === 'audio' ? `语音 ${safeDuration || 1}s` : `${mediaTypeText(type)} ${index + 1}`,
    typeText: mediaTypeText(type),
    icon: mediaTypeIcon(type),
    durationText: safeDuration ? `${safeDuration}s` : '',
  };
}

function normalizePhone(value) {
  return String(value || '').replace(/\D/g, '').slice(0, 11);
}

function afterSubmitPath(userInfo) {
  const businessRole = role.getBusinessRole(userInfo || {});
  const map = {
    platform_admin: '/pages/admin/dashboard/dashboard',
    store_manager: '/pages/store/dashboard/dashboard',
    city_manager: '/pages/city/dashboard/dashboard',
    promotion_manager: '/pages/promotion/dashboard/dashboard',
    second_receiver: '/pages/second/dashboard/dashboard',
    repairer: '/pages/repairer/jobs/jobs',
  };
  return map[businessRole] || '/pages/customer/orders/orders';
}

Page({
  ...share.create({
    title: '立即修｜代客下单',
  }),

  data: {
    categories: [
      { id: 'appliance', name: '家电维修' },
      { id: 'plumbing', name: '水路管道' },
      { id: 'electrical', name: '电路照明' },
      { id: 'door_window', name: '门窗维修' },
      { id: 'furniture_install', name: '家具安装' },
      { id: 'appliance_install', name: '家电安装' },
      { id: 'pipe_dredge', name: '管道疏通' },
      { id: 'cleaning', name: '清洁保养' },
      { id: 'other', name: '其他服务' },
    ],
    categoryIndex: 0,
    category: 'appliance',
    categoryName: '家电维修',
    customerName: '',
    customerPhone: '',
    contactPhone: '',
    description: '',
    address: '',
    addressBookId: 0,
    addressCode: '',
    serviceAddresses: [],
    serviceAddressIndex: 0,
    regions: [],
    stores: [],
    storeOptions: [{ id: null, name: '自动匹配' }],
    regionIndex: 0,
    storeIndex: 0,
    regionId: 1,
    storeId: null,
    currentRegionName: '默认服务区域',
    currentStoreName: '自动匹配',
    optionsLoading: true,
    optionsFailed: false,
    submitting: false,
    mediaList: [],
    mediaStats: buildMediaStats([]),
    recording: false,
    recordSeconds: 0,
    recordStartedAt: 0,
    focusField: '',
    validationErrors: {
      customerPhone: '',
      description: '',
      address: '',
    },
    privacyContractName: '用户隐私保护指引',
    privacyLoading: false,
    showPrivacyModal: false,
  },

  onLoad(options = {}) {
    share.enable();
    this.options = options;
    this.initPrivacy();
    this.initRecorder();
    this.loadOptions(options);
  },

  onShow() {
    share.enable();
    if (!wx.getStorageSync('userInfo')) {
      wx.reLaunch({ url: '/pages/login/login' });
    }
  },

  initRecorder() {
    recorder.onStop((res) => {
      clearInterval(this.recordTimer);
      if (!res || !res.tempFilePath) {
        this.setData({ recording: false, recordSeconds: 0, recordStartedAt: 0 });
        wx.showToast({ title: '录音未保存', icon: 'none' });
        return;
      }
      const duration = Math.max(1, Math.round((Date.now() - this.data.recordStartedAt) / 1000));
      this.setMediaList(this.data.mediaList.concat(makeMediaItem('audio', res.tempFilePath, this.data.mediaList.length, duration)), {
        recording: false,
        recordSeconds: 0,
        recordStartedAt: 0,
      });
    });
    recorder.onError(() => {
      clearInterval(this.recordTimer);
      this.voiceStarting = false;
      this.setData({ recording: false, recordSeconds: 0, recordStartedAt: 0 });
      wx.showToast({ title: '录音失败', icon: 'none' });
    });
  },

  initPrivacy() {
    this.privacyResolve = null;
    this.privacyPromise = null;
    this.privacyPromiseResolve = null;

    if (wx.onNeedPrivacyAuthorization) {
      wx.onNeedPrivacyAuthorization((resolve) => {
        this.privacyResolve = resolve;
        this.setData({ showPrivacyModal: true, privacyLoading: false });
      });
    }
    this.refreshPrivacySetting();
  },

  async refreshPrivacySetting() {
    if (!wx.getPrivacySetting) return { needAuthorization: false };
    const setting = await callWx('getPrivacySetting').catch(() => ({ needAuthorization: false }));
    this.setData({
      privacyContractName: setting.privacyContractName || '用户隐私保护指引',
    });
    return setting;
  },

  finishPrivacy(ok) {
    const resolver = this.privacyPromiseResolve;
    this.privacyPromise = null;
    this.privacyPromiseResolve = null;
    this.privacyResolve = null;
    this.setData({ showPrivacyModal: false, privacyLoading: false });
    if (typeof resolver === 'function') resolver(ok);
  },

  async requestPrivacy() {
    if (!wx.getPrivacySetting || !wx.requirePrivacyAuthorize) return true;
    const setting = await this.refreshPrivacySetting();
    if (!setting.needAuthorization) return true;
    if (this.privacyPromise) return this.privacyPromise;

    this.privacyPromise = new Promise((resolve) => {
      this.privacyPromiseResolve = resolve;
      wx.requirePrivacyAuthorize({
        success: () => this.finishPrivacy(true),
        fail: () => {
          this.setData({ showPrivacyModal: true, privacyLoading: false });
        },
      });
    });
    return this.privacyPromise;
  },

  handleAgreePrivacyAuthorization(e) {
    const detail = (e && e.detail) || {};
    if (detail.errMsg && detail.errMsg.indexOf('fail') !== -1) {
      wx.showToast({ title: '请先同意隐私授权', icon: 'none' });
      return;
    }
    this.setData({ privacyLoading: true });
    if (typeof this.privacyResolve === 'function') {
      this.privacyResolve({ buttonId: 'agree-btn', event: 'agree' });
    }
    setTimeout(() => this.finishPrivacy(true), 200);
  },

  handleRejectPrivacy() {
    if (typeof this.privacyResolve === 'function') {
      this.privacyResolve({ event: 'disagree' });
    }
    this.finishPrivacy(false);
    wx.showToast({ title: '同意后再添加素材', icon: 'none' });
  },

  openPrivacyContract() {
    if (!wx.openPrivacyContract) {
      wx.showToast({ title: '当前版本不支持查看', icon: 'none' });
      return;
    }
    wx.openPrivacyContract({
      fail: () => wx.showToast({ title: '打开失败', icon: 'none' }),
    });
  },

  async loadOptions() {
    this.setData({ optionsLoading: false, optionsFailed: false });
  },

  onAddressFieldsChange(e) {
    const value = e.detail;
    this.setData({ addressFieldsValue: value, serviceAreaId: value.service_area_id,
      estate: value.estate, doorNumber: value.door_number, address: value.address,
      regionId: value.region_id, storeId: value.store_id,
      currentRegionName: value.city ? `${value.city}/${value.district}` : '未选择城市/区域',
      currentStoreName: value.store_name || '请选择小区',
      'validationErrors.address': '', optionsFailed: false });
  },

  onServiceAddressChange(e) {
    const index = Number(e.detail.value);
    const selected = this.data.serviceAddresses[index];
    if (!selected) return;
    const store = this.data.stores.find(item => item.id === selected.store_id);
    const validationErrors = { ...this.data.validationErrors };
    validationErrors.address = '';
    this.setData({
      serviceAddressIndex: index,
      addressBookId: selected.id,
      addressCode: selected.address_code || '',
      address: selected.full_address || '',
      regionId: selected.region_id,
      storeId: selected.store_id,
      currentRegionName: `${selected.district || ''}${selected.street || ''}`,
      currentStoreName: store ? store.name : '地址归属门店',
      validationErrors,
    });
  },

  onCategoryChange(e) {
    const categoryIndex = Number(e.detail.value);
    const category = this.data.categories[categoryIndex] || this.data.categories[0];
    this.setData({
      categoryIndex,
      category: category.id,
      categoryName: category.name,
    });
  },

  onRegionChange(e) {
    const regionIndex = Number(e.detail.value);
    const region = this.data.regions[regionIndex];
    this.setData({
      regionIndex,
      regionId: region ? region.id : 1,
      currentRegionName: region ? region.name : '默认服务区域',
    });
  },

  onStoreChange(e) {
    const storeIndex = Number(e.detail.value);
    const store = this.data.storeOptions[storeIndex];
    const region = store && store.region_id
      ? this.data.regions.find(item => item.id === store.region_id)
      : null;
    const patch = {
      storeIndex,
      storeId: store && store.id ? store.id : null,
      currentStoreName: store && store.name ? store.name : '自动匹配',
    };
    if (region) {
      patch.regionId = region.id;
      patch.currentRegionName = region.name;
      patch.regionIndex = Math.max(0, this.data.regions.findIndex(item => item.id === region.id));
    }
    this.setData(patch);
  },

  setMediaList(mediaList, extra = {}) {
    const validationErrors = { ...this.data.validationErrors };
    if (mediaList.length || this.data.description.trim()) validationErrors.description = '';
    this.setData({
      mediaList,
      mediaStats: buildMediaStats(mediaList, this.data.description),
      validationErrors,
      ...extra,
    });
  },

  async ensureRecordAuth() {
    const privacyOk = await this.requestPrivacy();
    if (!privacyOk) return false;
    const setting = await callWx('getSetting').catch(() => ({ authSetting: {} }));
    if (setting.authSetting && setting.authSetting['scope.record']) return true;
    if (setting.authSetting && setting.authSetting['scope.record'] === false) {
      wx.openSetting();
      return false;
    }
    try {
      await callWx('authorize', { scope: 'scope.record' });
      return true;
    } catch (e) {
      wx.showModal({
        title: '需要麦克风权限',
        content: '开启后可代客户补充语音描述。',
        confirmText: '去开启',
        success(res) {
          if (res.confirm) wx.openSetting();
        },
      });
      return false;
    }
  },

  async startVoice() {
    if (this.data.recording || this.voiceStarting) return;
    this.voiceStarting = true;
    const ok = await this.ensureRecordAuth();
    if (!ok) {
      this.voiceStarting = false;
      return;
    }
    recorder.start({
      duration: MAX_AUDIO_DURATION_MS,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      format: 'mp3',
    });
    this.setData({ recording: true, recordStartedAt: Date.now(), recordSeconds: 0 });
    this.voiceStarting = false;
    this.recordTimer = setInterval(() => {
      this.setData({ recordSeconds: Math.round((Date.now() - this.data.recordStartedAt) / 1000) });
    }, 1000);
  },

  stopVoice() {
    if (!this.data.recording) return;
    clearInterval(this.recordTimer);
    recorder.stop();
  },

  async chooseImage() {
    const imageCount = this.data.mediaList.filter(item => item.type === 'image').length;
    const remaining = MAX_IMAGE_COUNT - imageCount;
    if (remaining <= 0) {
      wx.showToast({ title: `最多添加${MAX_IMAGE_COUNT}张照片`, icon: 'none' });
      return;
    }
    if (!await this.requestPrivacy()) return;
    try {
      let files = [];
      if (wx.chooseMedia) {
        const res = await callWx('chooseMedia', {
          count: remaining,
          mediaType: ['image'],
          sourceType: ['album', 'camera'],
          sizeType: ['compressed'],
          camera: 'back',
        });
        files = res.tempFiles || [];
      } else {
        const res = await callWx('chooseImage', {
          count: remaining,
          sourceType: ['album', 'camera'],
          sizeType: ['compressed'],
        });
        files = (res.tempFilePaths || []).map(tempFilePath => ({ tempFilePath }));
      }
      const mediaList = this.data.mediaList.concat(files
        .filter(file => file && file.tempFilePath)
        .map((file, index) => makeMediaItem('image', file.tempFilePath, imageCount + index)));
      this.setMediaList(mediaList);
    } catch (e) {
      if (!isCancelError(e)) wx.showToast({ title: '未添加照片', icon: 'none' });
    }
  },

  async chooseVideo() {
    if (!await this.requestPrivacy()) return;
    try {
      let file = null;
      if (wx.chooseMedia) {
        const res = await callWx('chooseMedia', {
          count: 1,
          mediaType: ['video'],
          sourceType: ['album', 'camera'],
          maxDuration: MAX_VIDEO_DURATION_SECONDS,
          camera: 'back',
        });
        file = res.tempFiles && res.tempFiles[0];
      } else {
        const res = await callWx('chooseVideo', {
          sourceType: ['album', 'camera'],
          maxDuration: MAX_VIDEO_DURATION_SECONDS,
          compressed: true,
        });
        file = res && { tempFilePath: res.tempFilePath, duration: res.duration };
      }
      if (!file || !file.tempFilePath) return;
      this.setMediaList(this.data.mediaList.concat(makeMediaItem(
        'video',
        file.tempFilePath,
        this.data.mediaList.length,
        file.duration || 0,
      )));
    } catch (e) {
      if (!isCancelError(e)) wx.showToast({ title: '未添加视频', icon: 'none' });
    }
  },

  previewMedia(e) {
    const item = this.data.mediaList[Number(e.currentTarget.dataset.index)];
    if (!item) return;
    if (item.type === 'image') {
      const urls = this.data.mediaList.filter(media => media.type === 'image').map(media => media.tempFilePath);
      wx.previewImage({ current: item.tempFilePath, urls });
      return;
    }
    if (item.type === 'video') {
      wx.previewMedia({ sources: [{ url: item.tempFilePath, type: 'video' }], current: 0 });
      return;
    }
    if (audioContext) {
      audioContext.stop();
      audioContext.destroy();
    }
    audioContext = wx.createInnerAudioContext();
    audioContext.src = item.tempFilePath;
    audioContext.play();
  },

  removeMedia(e) {
    const index = Number(e.currentTarget.dataset.index);
    this.setMediaList(this.data.mediaList.filter((_, itemIndex) => itemIndex !== index));
  },

  async findCustomerByPhone(phone, maxPages = 10) {
    for (let page = 0; page < maxPages; page += 1) {
      const users = await api.get(`/api/v1/users?role=customer&skip=${page * 100}&limit=100`).catch(() => []);
      const found = users.find(item => String(item.phone) === String(phone));
      if (found) return found;
      if (!users || users.length < 100) return null;
    }
    return null;
  },

  async ensureCustomer() {
    const phone = normalizePhone(this.data.customerPhone);
    const userInfo = wx.getStorageSync('userInfo') || {};
    const businessRole = role.getBusinessRole(userInfo);
    const name = String(this.data.customerName || '').trim() || `客户${phone.slice(-4)}`;
    const found = await this.findCustomerByPhone(phone);
    if (found) return found;

    try {
      return await api.post('/api/v1/users', {
        phone,
        name,
        role: 'customer',
        promotion_manager_id: businessRole === 'promotion_manager' ? userInfo.id : undefined,
      });
    } catch (e) {
      const latest = await this.findCustomerByPhone(phone, 20);
      if (latest) return latest;

      const res = await api.post('/api/v1/auth/wechat-login', {
        code: `${phone}:${name}:customer`,
        phone,
        name,
        role: 'customer',
      });
      if (res && res.user) return res.user;
      throw e;
    }
  },

  validateForm() {
    const validationErrors = { customerPhone: '', description: '', address: '' };
    const phone = normalizePhone(this.data.customerPhone);
    if (phone.length !== 11) validationErrors.customerPhone = '填写客户手机号';
    if (!this.data.description.trim() && this.data.mediaList.length === 0) {
      validationErrors.description = '填描述或加素材';
    }
    if (!this.data.serviceAreaId || !this.data.estate || !this.data.doorNumber) validationErrors.address = '请选择城市/区域和小区，填写门牌号';

    this.setData({ validationErrors });
    return !validationErrors.customerPhone && !validationErrors.description && !validationErrors.address;
  },

  async submitOrder() {
    if (this.data.submitting) return;
    if (!this.validateForm()) {
      wx.showToast({ title: '补全信息', icon: 'none' });
      return;
    }

    this.setData({ submitting: true });
    wx.showLoading({ title: '提交中' });
    try {
      const actor = wx.getStorageSync('userInfo') || {};
      const customer = await this.ensureCustomer();
      const order = await api.post('/api/v1/orders', {
        customer_id: customer.id,
        region_id: this.data.regionId || 1,
        store_id: this.data.storeId || undefined,
        service_area_id: this.data.serviceAreaId,
        estate: this.data.estate,
        door_number: this.data.doorNumber,
        category: this.data.category || 'other',
        description: this.data.description.trim() || '已由工作人员上传现场素材',
        address: this.data.address.trim(),
        contact_phone: this.data.contactPhone || this.data.customerPhone,
        created_by_user_id: actor.id,
        proxy_creator_id: actor.id,
        is_proxy_order: true,
        proxy_reason: 'phone_request',
        customer_name_snapshot: this.data.customerName || customer.name,
        customer_phone_snapshot: this.data.customerPhone,
        customer_address_snapshot: this.data.address.trim(),
      });

      for (const item of this.data.mediaList) {
        await api.upload(`/api/v1/orders/${order.id}/media`, item.tempFilePath, 'file', {
          media_type: item.type,
          duration: item.duration || 0,
          name: item.name,
          uploader_id: actor.id || customer.id,
          original_name: basename(item.tempFilePath, item.name),
        });
      }

      wx.hideLoading();
      this.showSubmitResult(order);
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message || '提交失败', icon: 'none' });
    } finally {
      this.setData({ submitting: false });
    }
  },

  showSubmitResult(order) {
    wx.redirectTo({ url: `/pages/staff/proxy-result/proxy-result?id=${order.id}` });
  },

  resetForm() {
    this.setData({
      customerName: '',
      customerPhone: '',
      contactPhone: '',
      description: '',
      mediaList: [],
      mediaStats: buildMediaStats([]),
      validationErrors: { customerPhone: '', description: '', address: '' },
    });
  },

  onUnload() {
    clearInterval(this.recordTimer);
    if (this.data.recording) recorder.stop();
    if (audioContext) {
      audioContext.destroy();
      audioContext = null;
    }
  },
});
