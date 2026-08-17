// pages/customer/order/order.js
const api = require('../../../utils/api');
const share = require('../../../utils/share');

const recorder = wx.getRecorderManager();
let audioContext = null;
const MAX_AUDIO_DURATION_MS = 10 * 60 * 1000;
const MAX_VIDEO_DURATION_SECONDS = 60;
const MAX_IMAGE_COUNT = 6;

function buildMediaStats(mediaList, description = '') {
  const audioCount = mediaList.filter(item => item.type === 'audio').length;
  const imageCount = mediaList.filter(item => item.type === 'image').length;
  const videoCount = mediaList.filter(item => item.type === 'video').length;
  const total = mediaList.length;
  const hasDescription = Boolean(String(description || '').trim());
  const hasVisual = imageCount > 0 || videoCount > 0;
  let title = '可补充素材';
  let desc = '师傅可见';
  let tone = 'tone-warning';

  if (hasDescription && !total) {
    title = '已写描述';
    desc = '可加素材';
    tone = 'tone-waiting';
  }
  if (total && !hasVisual) {
    title = '已加语音';
    desc = '可加照片';
    tone = 'tone-progress';
  }
  if (hasVisual && !audioCount) {
    title = '已加照片/视频';
    desc = '可加语音';
    tone = 'tone-progress';
  }
  if (audioCount && hasVisual) {
    title = '素材完整';
    desc = '可提交';
    tone = 'tone-success';
  }

  return {
    audioCount,
    imageCount,
    videoCount,
    total,
    title,
    desc,
    tone,
    limitText: `照片${MAX_IMAGE_COUNT}张内 · 视频${MAX_VIDEO_DURATION_SECONDS}秒内 · 语音10分钟内`,
  };
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

function basename(filePath, fallback) {
  const value = String(filePath || '');
  const name = value.split(/[\\/]/).pop();
  return name || fallback;
}

function callWx(method, options = {}) {
  return new Promise((resolve, reject) => {
    if (!wx[method]) {
      reject(new Error(`${method} 不支持`));
      return;
    }
    wx[method]({
      ...options,
      success: resolve,
      fail: reject,
    });
  });
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function getErrorMessage(error) {
  return String((error && (error.errMsg || error.message)) || error || '');
}

function isPrivacyError(error) {
  const message = getErrorMessage(error).toLowerCase();
  return message.includes('privacy') || message.includes('隐私');
}

function isCancelError(error) {
  const message = getErrorMessage(error).toLowerCase();
  return message.includes('cancel') || message.includes('取消');
}

Page({
  ...share.create({
    title() {
      return `立即修｜${this.data.categoryName || '上门维修'}`;
    },
  }),

  data: {
    category: '',
    categoryName: '其他服务',
    description: '',
    address: '',
    addressBookId: 0,
    addressCode: '',
    serviceAddresses: [],
    serviceAddressIndex: 0,
    contactPhone: '',
    regions: [],
    stores: [],
    optionsLoading: true,
    optionsFailed: false,
    regionIndex: 0,
    storeIndex: 0,
    currentRegionName: '选择区域',
    currentStoreName: '自动匹配',
    regionId: null,
    storeId: null,
    submitting: false,
    mediaList: [],
    focusField: '',
    validationErrors: {
      description: '',
      address: '',
    },
    recording: false,
    recordSeconds: 0,
    recordStartedAt: 0,
    mediaStats: buildMediaStats([]),
    showPrivacyModal: false,
    privacyLoading: false,
    privacyContractName: '用户隐私保护指引',
  },

  onLoad(options) {
    share.enable();
    if (options.category) {
      this.setData({
        category: options.category,
        categoryName: this.categoryText(options.category),
      });
    }
    const userInfo = wx.getStorageSync('userInfo');
    if (userInfo && userInfo.phone) this.setData({ contactPhone: userInfo.phone });
    this.initPrivacy();
    this.initRecorder();
    this.loadOptions();
  },

  onFieldFocus(e) {
    this.setData({ focusField: e.currentTarget.dataset.field || '' });
  },

  onFieldBlur() {
    this.setData({ focusField: '' });
  },

  setMediaList(mediaList, extra = {}) {
    const validationErrors = { ...this.data.validationErrors };
    if (mediaList.length || this.data.description.trim()) {
      validationErrors.description = '';
    }
    this.setData({
      mediaList,
      mediaStats: buildMediaStats(mediaList, this.data.description),
      validationErrors,
      ...extra,
    });
  },

  onDescInput(e) {
    const description = e.detail.value;
    const validationErrors = { ...this.data.validationErrors };
    if (description.trim() || this.data.mediaList.length) {
      validationErrors.description = '';
    }
    this.setData({
      description,
      validationErrors,
      mediaStats: buildMediaStats(this.data.mediaList, description),
    });
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
  onPhoneInput(e) { this.setData({ contactPhone: e.detail.value }); },
  onRegionChange(e) {
    const index = Number(e.detail.value);
    const region = this.data.regions[index];
    this.setData({
      regionIndex: index,
      currentRegionName: region ? region.name : '选择区域',
      regionId: region ? region.id : null,
    });
  },

  initRecorder() {
    recorder.onStop(res => {
      clearInterval(this.recordTimer);
      if (!res || !res.tempFilePath) {
        this.setData({ recording: false, recordSeconds: 0, recordStartedAt: 0 });
        wx.showToast({ title: '未保存录音', icon: 'none' });
        return;
      }
      const duration = Math.max(1, Math.round((Date.now() - this.data.recordStartedAt) / 1000));
      const mediaList = this.data.mediaList.concat({
        type: 'audio',
        tempFilePath: res.tempFilePath,
        duration,
        name: `语音 ${duration}s`,
        typeText: mediaTypeText('audio'),
        icon: mediaTypeIcon('audio'),
        durationText: `${duration}s`,
      });
      this.setMediaList(mediaList, { recording: false, recordSeconds: 0, recordStartedAt: 0 });
    });
    recorder.onError((error) => {
      this.setData({ recording: false, recordSeconds: 0, recordStartedAt: 0 });
      this.voiceStarting = false;
      if (isPrivacyError(error)) {
        this.requestPrivacy('voice').then((ok) => {
          if (ok) {
            setTimeout(() => this.startVoice(true), 100);
          } else {
            this.showPrivacyGuideModal('麦克风');
          }
        });
        return;
      }
      wx.showToast({ title: '录音失败', icon: 'none' });
    });
  },

  initPrivacy() {
    this.pendingPrivacyAction = '';
    this.activePrivacyAction = '';
    this.privacyRequestPromise = null;
    this.privacyRequestResolve = null;
    this.privacyResolve = null;
    this.privacyRequireFailed = false;

    if (wx.onNeedPrivacyAuthorization) {
      wx.onNeedPrivacyAuthorization((resolve, eventInfo) => {
        this.privacyResolve = resolve;
        this.privacyEventInfo = eventInfo || {};
        this.setData({ showPrivacyModal: true, privacyLoading: false });
      });
    }

    this.refreshPrivacySetting();
  },

  async refreshPrivacySetting() {
    if (!wx.getPrivacySetting) {
      return { needAuthorization: false };
    }

    const setting = await callWx('getPrivacySetting').catch(() => ({ needAuthorization: false }));
    this.setData({ privacyContractName: setting.privacyContractName || '用户隐私保护指引' });
    return setting;
  },

  async confirmPrivacyAccepted() {
    for (let i = 0; i < 5; i += 1) {
      await delay(i === 0 ? 150 : 300);
      const setting = await this.refreshPrivacySetting();
      if (!setting.needAuthorization) return true;
    }
    return false;
  },

  finishPrivacyRequest(ok) {
    clearTimeout(this.privacyAgreeTimer);
    this.privacyAgreeTimer = null;
    clearTimeout(this.privacyFailTimer);
    this.privacyFailTimer = null;
    const resolve = this.privacyRequestResolve;
    this.privacyRequestResolve = null;
    this.privacyRequestPromise = null;
    this.privacyResolve = null;
    this.privacyRequireFailed = false;
    this.pendingPrivacyAction = '';
    this.activePrivacyAction = '';
    this.setData({ showPrivacyModal: false, privacyLoading: false });
    if (typeof resolve === 'function') resolve(ok);
  },

  async requestPrivacy(action) {
    if (!wx.getPrivacySetting || !wx.requirePrivacyAuthorize) return true;

    const setting = await this.refreshPrivacySetting();
    if (!setting.needAuthorization) return true;

    if (this.privacyRequestPromise) return this.privacyRequestPromise;

    this.pendingPrivacyAction = action;

    this.privacyRequestPromise = new Promise((resolve) => {
      this.privacyRequestResolve = resolve;
      wx.requirePrivacyAuthorize({
        success: () => this.finishPrivacyRequest(true),
        fail: () => {
          this.privacyRequireFailed = true;
          clearTimeout(this.privacyFailTimer);
          this.privacyFailTimer = setTimeout(() => {
            if (!this.privacyRequestPromise) return;
            if (this.privacyResolve || this.data.showPrivacyModal) return;
            this.finishPrivacyRequest(false);
          }, 1500);
        },
      });
    });

    return this.privacyRequestPromise;
  },

  openPrivacyContract() {
    if (!wx.openPrivacyContract) {
      wx.showToast({ title: '当前微信版本不支持查看', icon: 'none' });
      return;
    }
    wx.openPrivacyContract({
      fail: () => wx.showToast({ title: '打开失败', icon: 'none' }),
    });
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
      clearTimeout(this.privacyAgreeTimer);
      this.privacyAgreeTimer = setTimeout(() => {
        if (!this.privacyRequestPromise) return;
        this.finishPrivacyRequest(true);
      }, 300);
      return;
    }
    this.finishPrivacyRequest(true);
  },

  handleRejectPrivacy() {
    if (!this.data.showPrivacyModal && !this.privacyResolve) return;
    if (typeof this.privacyResolve === 'function') {
      this.privacyResolve({ event: 'disagree' });
    }
    this.finishPrivacyRequest(false);
    wx.showToast({ title: '同意后再添加素材', icon: 'none' });
  },

  openRecordSetting() {
    wx.showModal({
      title: '需要麦克风权限',
      content: '开启麦克风后重试',
      confirmText: '去开启',
      success(res) {
        if (res.confirm) wx.openSetting();
      },
    });
  },

  showPrivacyGuideModal(label) {
    wx.showModal({
      title: '授权未完成',
      content: `同意隐私授权并允许${label}`,
      showCancel: false,
      confirmText: '知道了',
    });
  },

  async ensureRecordAuth(retried = false) {
    const setting = await callWx('getSetting').catch(() => ({ authSetting: {} }));
    if (setting.authSetting && setting.authSetting['scope.record']) return true;
    if (setting.authSetting && setting.authSetting['scope.record'] === false) {
      this.openRecordSetting();
      return false;
    }

    try {
      this.activePrivacyAction = 'voice';
      await callWx('authorize', { scope: 'scope.record' });
      this.activePrivacyAction = '';
      return true;
    } catch (e) {
      this.activePrivacyAction = '';
      if (isPrivacyError(e)) {
        if (!retried) {
          const ok = await this.requestPrivacy('voice');
          if (ok) return this.ensureRecordAuth(true);
          this.showPrivacyGuideModal('麦克风');
          return false;
        }
        this.showPrivacyGuideModal('麦克风');
        return false;
      }
      this.openRecordSetting();
      return false;
    }
  },

  async startVoice(retried = false) {
    if (this.data.recording || this.voiceStarting) return;
    this.voiceStarting = true;
    const ok = await this.ensureRecordAuth();
    if (!ok) {
      this.voiceStarting = false;
      return;
    }

    try {
      this.activePrivacyAction = 'voice';
      recorder.start({
        duration: MAX_AUDIO_DURATION_MS,
        sampleRate: 16000,
        numberOfChannels: 1,
        encodeBitRate: 48000,
        format: 'mp3',
      });
      this.activePrivacyAction = '';
    } catch (e) {
      this.activePrivacyAction = '';
      this.voiceStarting = false;
      if (isPrivacyError(e)) {
        if (!retried) {
          const privacyOk = await this.requestPrivacy('voice');
          if (privacyOk) {
            setTimeout(() => this.startVoice(true), 100);
          } else {
            this.showPrivacyGuideModal('麦克风');
          }
        } else {
          this.showPrivacyGuideModal('麦克风');
        }
        return;
      }
      wx.showToast({ title: '录音启动失败', icon: 'none' });
      return;
    }
    this.setData({ recording: true, recordStartedAt: Date.now(), recordSeconds: 0 });
    this.voiceStarting = false;
    wx.showToast({ title: '正在录音', icon: 'none' });
    this.recordTimer = setInterval(() => {
      this.setData({ recordSeconds: Math.round((Date.now() - this.data.recordStartedAt) / 1000) });
    }, 1000);
  },

  stopVoice() {
    if (!this.data.recording) return;
    clearInterval(this.recordTimer);
    recorder.stop();
  },

  async chooseVideo(retried = false) {
    if (this.videoChoosing) return;
    this.videoChoosing = true;
    try {
      let file = null;
      this.activePrivacyAction = 'video';
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
      this.activePrivacyAction = '';
      if (!file || !file.tempFilePath) return;
      const mediaList = this.data.mediaList.concat({
        type: 'video',
        tempFilePath: file.tempFilePath,
        duration: Math.round(file.duration || 0),
        name: `视频 ${Math.round(file.duration || 0)}s`,
        typeText: mediaTypeText('video'),
        icon: mediaTypeIcon('video'),
        durationText: file.duration ? `${Math.round(file.duration)}s` : '',
      });
      this.setMediaList(mediaList);
    } catch (e) {
      this.activePrivacyAction = '';
      if (isPrivacyError(e)) {
        if (!retried) {
          const privacyOk = await this.requestPrivacy('video');
          if (privacyOk) {
            setTimeout(() => this.chooseVideo(true), 100);
          } else {
            this.showPrivacyGuideModal('摄像头或相册');
          }
        } else {
          this.showPrivacyGuideModal('摄像头或相册');
        }
        return;
      }
      if (isCancelError(e)) return;
      wx.showToast({
        title: '未添加视频',
        icon: 'none',
      });
    } finally {
      this.videoChoosing = false;
    }
  },

  async chooseImage(retried = false) {
    if (this.imageChoosing) return;
    const imageCount = this.data.mediaList.filter(item => item.type === 'image').length;
    const remaining = MAX_IMAGE_COUNT - imageCount;
    if (remaining <= 0) {
      wx.showToast({ title: `最多添加${MAX_IMAGE_COUNT}张照片`, icon: 'none' });
      return;
    }

    this.imageChoosing = true;
    try {
      let files = [];
      this.activePrivacyAction = 'image';
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
      this.activePrivacyAction = '';
      if (!files.length) return;
      const mediaList = this.data.mediaList.concat(files
        .filter(file => file && file.tempFilePath)
        .map((file, index) => ({
          type: 'image',
          tempFilePath: file.tempFilePath,
          duration: 0,
          name: `照片 ${imageCount + index + 1}`,
          typeText: mediaTypeText('image'),
          icon: mediaTypeIcon('image'),
          durationText: '',
        })));
      this.setMediaList(mediaList);
    } catch (e) {
      this.activePrivacyAction = '';
      if (isPrivacyError(e)) {
        if (!retried) {
          const privacyOk = await this.requestPrivacy('image');
          if (privacyOk) {
            setTimeout(() => this.chooseImage(true), 100);
          } else {
            this.showPrivacyGuideModal('摄像头或相册');
          }
        } else {
          this.showPrivacyGuideModal('摄像头或相册');
        }
        return;
      }
      if (isCancelError(e)) return;
      wx.showToast({ title: '未添加照片', icon: 'none' });
    } finally {
      this.imageChoosing = false;
    }
  },

  removeMedia(e) {
    const index = Number(e.currentTarget.dataset.index);
    this.setMediaList(this.data.mediaList.filter((_, itemIndex) => itemIndex !== index));
  },

  previewMedia(e) {
    const index = Number(e.currentTarget.dataset.index);
    const item = this.data.mediaList[index];
    if (!item) return;
    if (item.type === 'image') {
      const urls = this.data.mediaList
        .filter(media => media.type === 'image')
        .map(media => media.tempFilePath);
      wx.previewImage({ current: item.tempFilePath, urls });
      return;
    }
    if (item.type === 'video') {
      wx.previewMedia({
        sources: [{ url: item.tempFilePath, type: 'video' }],
        current: 0,
      });
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
  onStoreChange(e) {
    const index = Number(e.detail.value);
    const store = this.data.stores[index];
    this.setData({
      storeIndex: index,
      currentStoreName: store ? store.name : '自动匹配',
      storeId: store ? store.id : null,
    });
  },

  async loadOptions() {
    this.setData({ optionsLoading: true, optionsFailed: false });
    try {
      const userInfo = wx.getStorageSync('userInfo') || {};
      const [stores, addresses, serviceAddresses] = await Promise.all([
        api.get('/api/v1/stores'),
        userInfo.id ? api.get('/api/v1/business/addresses', { user_id: userInfo.id }) : Promise.resolve([]),
        api.get('/api/v1/stores/addresses', { enabled: true }),
      ]);
      const activeStores = (stores || []).filter(item => item.enabled);
      const savedAddresses = (addresses || []).filter(item => item.service_address_id);
      const defaultAddress = savedAddresses.find(item => item.is_default) || savedAddresses[0];
      const selectedIndex = Math.max(0, (serviceAddresses || []).findIndex(item => item.id === (defaultAddress && defaultAddress.service_address_id)));
      const selected = (serviceAddresses || [])[selectedIndex];
      const selectedStore = selected && activeStores.find(item => item.id === selected.store_id);
      this.setData({
        stores: activeStores,
        serviceAddresses: serviceAddresses || [],
        serviceAddressIndex: selectedIndex,
        addressBookId: selected ? selected.id : 0,
        addressCode: selected ? selected.address_code : '',
        currentRegionName: selected ? `${selected.district || ''}${selected.street || ''}` : '未选择标准地址',
        currentStoreName: selectedStore ? selectedStore.name : '地址归属门店',
        regionId: selected ? selected.region_id : null,
        storeId: selected ? selected.store_id : null,
        address: selected ? selected.full_address : '',
        contactPhone: defaultAddress ? defaultAddress.contact_phone : this.data.contactPhone,
        optionsLoading: false,
        optionsFailed: !(serviceAddresses || []).length,
      });
    } catch {
      this.setData({
        regionId: 1,
        currentRegionName: '默认服务区域',
        currentStoreName: '自动匹配',
        optionsLoading: false,
        optionsFailed: true,
      });
    }
  },

  async submitOrder() {
    const { description, address, category } = this.data;
    const validationErrors = { description: '', address: '' };
    if (!description.trim() && this.data.mediaList.length === 0) {
      validationErrors.description = '填描述或加素材';
    }
    if (!this.data.addressBookId || !address.trim()) {
      validationErrors.address = '请选择平台已开通的标准地址';
    }
    if (validationErrors.description || validationErrors.address) {
      this.setData({ validationErrors });
      wx.showToast({ title: '补全信息', icon: 'none' });
      return;
    }

    this.setData({ submitting: true });
    try {
      const userInfo = wx.getStorageSync('userInfo');
      const order = await api.post('/api/v1/orders', {
        customer_id: userInfo.id,
        region_id: this.data.regionId || 1,
        store_id: this.data.storeId || undefined,
        address_book_id: this.data.addressBookId,
        category: category || 'other',
        description: description.trim() || '已上传素材',
        address: address.trim(),
        contact_phone: this.data.contactPhone || userInfo.phone,
        created_by_user_id: userInfo.id,
        customer_name_snapshot: userInfo.name,
        customer_phone_snapshot: this.data.contactPhone || userInfo.phone,
        customer_address_snapshot: address.trim(),
      });
      if (this.data.mediaList.length > 0) {
        wx.showLoading({ title: '上传素材中' });
        for (const item of this.data.mediaList) {
          await api.upload(`/api/v1/orders/${order.id}/media`, item.tempFilePath, 'file', {
            media_type: item.type,
            duration: item.duration || 0,
            name: item.name,
            uploader_id: userInfo.id,
            original_name: basename(item.tempFilePath, item.name),
          });
        }
        wx.hideLoading();
      }
      wx.showToast({ title: '已提交', icon: 'success' });
      setTimeout(() => {
        wx.redirectTo({ url: `/pages/customer/orders/orders` });
      }, 1500);
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: e.message || '提交失败', icon: 'none' });
    } finally {
      this.setData({ submitting: false });
    }
  },

  onUnload() {
    clearInterval(this.recordTimer);
    clearTimeout(this.privacyAgreeTimer);
    clearTimeout(this.privacyFailTimer);
    if (this.data.recording) recorder.stop();
    if (this.data.showPrivacyModal) this.handleRejectPrivacy();
    if (audioContext) {
      audioContext.destroy();
      audioContext = null;
    }
  },

  categoryText(category) {
    const map = {
      appliance: '家电维修', plumbing: '水路管道', electrical: '电路照明',
      door_window: '门窗维修', furniture_install: '家具安装',
      appliance_install: '家电安装', pipe_dredge: '管道疏通',
      cleaning: '清洁保养', other: '其他服务',
    };
    return map[category] || '其他服务';
  },
});
