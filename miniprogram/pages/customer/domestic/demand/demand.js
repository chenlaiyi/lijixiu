const api = require('../../../../utils/api');
const share = require('../../../../utils/share');

const recorder = wx.getRecorderManager();

Page({
  ...share.create({ title: '立即修｜发布家政需求' }),
  data: {
    serviceType: 'maternity',
    title: '发布月嫂需求',
    userInfo: null,
    form: {
      contactName: '', contactPhone: '', address: '', description: '', startDate: '',
      budgetMin: '', budgetMax: '', expectedDate: '', cycleDays: '26', liveIn: true,
      serviceMode: '住家', familySize: '2', schedule: '', tasks: '', pets: false,
    },
    cycleOptions: ['26', '42', '52', '自定义'],
    modeOptions: ['住家', '白班', '钟点', '长期'],
    localMedia: [],
    recording: false,
    recordSeconds: 0,
    showPrivacyModal: false,
    submitting: false,
  },
  onLoad(options) {
    const serviceType = options.type === 'nanny' ? 'nanny' : 'maternity';
    this.preferredWorkerId = Number(options.workerId || 0);
    const userInfo = wx.getStorageSync('userInfo') || {};
    this.setData({
      serviceType,
      title: serviceType === 'maternity' ? '发布月嫂需求' : '发布保姆需求',
      userInfo,
      'form.contactName': userInfo.name || '',
      'form.contactPhone': userInfo.phone || '',
    });
    wx.setNavigationBarTitle({ title: this.data.title });
    this.setupPrivacy();
    this.setupRecorder();
    this.loadDefaults();
  },
  onShow() { share.enable(); },
  async loadDefaults() {
    const user = this.data.userInfo;
    try {
      const [addresses, stores, regions] = await Promise.all([
        api.get('/api/v1/business/addresses', { user_id: user.id }),
        api.get('/api/v1/stores'),
        api.get('/api/v1/regions'),
      ]);
      const address = (addresses || []).find(item => item.is_default) || (addresses || [])[0];
      this.store = (stores || []).find(item => item.enabled) || (stores || [])[0];
      this.regionId = (this.store && this.store.region_id) || ((regions || [])[0] && regions[0].id);
      if (address) this.setData({
        'form.address': address.address,
        'form.contactName': address.contact_name || this.data.form.contactName,
        'form.contactPhone': address.contact_phone || this.data.form.contactPhone,
      });
    } catch (e) {}
  },
  inputField(e) { this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value }); },
  switchField(e) { this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value }); },
  dateChange(e) { this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value }); },
  cycleChange(e) { this.setData({ 'form.cycleDays': this.data.cycleOptions[Number(e.detail.value)] }); },
  modeChange(e) { this.setData({ 'form.serviceMode': this.data.modeOptions[Number(e.detail.value)] }); },
  setupPrivacy() {
    if (!wx.onNeedPrivacyAuthorization) return;
    wx.onNeedPrivacyAuthorization((resolve) => {
      this.privacyResolve = resolve;
      this.setData({ showPrivacyModal: true });
    });
  },
  requestPrivacy() {
    if (!wx.requirePrivacyAuthorize) return Promise.resolve(true);
    return new Promise((resolve) => {
      this.privacyRequestResolve = resolve;
      wx.requirePrivacyAuthorize({
        success: () => this.finishPrivacy(true),
        fail: () => setTimeout(() => {
          if (!this.data.showPrivacyModal) this.finishPrivacy(false);
        }, 1000),
      });
    });
  },
  finishPrivacy(ok) {
    const resolve = this.privacyRequestResolve;
    this.privacyRequestResolve = null;
    this.privacyResolve = null;
    this.setData({ showPrivacyModal: false });
    if (resolve) resolve(ok);
  },
  agreePrivacy() {
    if (this.privacyResolve) this.privacyResolve({ buttonId: 'domestic-agree', event: 'agree' });
    this.finishPrivacy(true);
  },
  rejectPrivacy() {
    if (this.privacyResolve) this.privacyResolve({ event: 'disagree' });
    this.finishPrivacy(false);
  },
  openPrivacyContract() { if (wx.openPrivacyContract) wx.openPrivacyContract(); },
  setupRecorder() {
    recorder.onStart(() => {
      this.startedAt = Date.now();
      this.setData({ recording: true, recordSeconds: 0 });
      this.recordTimer = setInterval(() => this.setData({
        recordSeconds: Math.min(120, Math.floor((Date.now() - this.startedAt) / 1000)),
      }), 1000);
    });
    recorder.onStop(res => {
      clearInterval(this.recordTimer);
      const item = { type: 'audio', path: res.tempFilePath, duration: Math.round((res.duration || 0) / 1000) };
      this.setData({ recording: false, localMedia: this.data.localMedia.concat(item).slice(-6) });
    });
    recorder.onError(() => {
      clearInterval(this.recordTimer);
      this.setData({ recording: false });
      wx.showToast({ title: '录音失败，请检查麦克风权限', icon: 'none' });
    });
  },
  async toggleRecord() {
    if (this.data.recording) { recorder.stop(); return; }
    if (!(await this.requestPrivacy())) return;
    try {
      await new Promise((resolve, reject) => wx.authorize({ scope: 'scope.record', success: resolve, fail: reject }));
      recorder.start({ duration: 120000, format: 'mp3' });
    } catch (e) {
      wx.showModal({ title: '需要麦克风权限', content: '请在设置中开启麦克风权限后重试', success: r => r.confirm && wx.openSetting() });
    }
  },
  async chooseImages() {
    if (!(await this.requestPrivacy())) return;
    try {
      const result = await new Promise((resolve, reject) => wx.chooseMedia({
        count: Math.max(1, 6 - this.data.localMedia.length),
        mediaType: ['image'],
        sourceType: ['album', 'camera'],
        success: resolve,
        fail: reject,
      }));
      const items = (result.tempFiles || []).map(item => ({ type: 'image', path: item.tempFilePath, duration: 0 }));
      this.setData({ localMedia: this.data.localMedia.concat(items).slice(0, 6) });
    } catch (e) {
      if (!isCancelError(e)) wx.showToast({ title: e.message || '图片选择失败', icon: 'none' });
    }
  },
  removeMedia(e) {
    const index = Number(e.currentTarget.dataset.index);
    this.setData({ localMedia: this.data.localMedia.filter((_, i) => i !== index) });
  },
  buildDetail() {
    const f = this.data.form;
    return this.data.serviceType === 'maternity'
      ? { expected_date: f.expectedDate, cycle_days: f.cycleDays, live_in: f.liveIn }
      : { service_mode: f.serviceMode, family_size: f.familySize, schedule: f.schedule, tasks: f.tasks, pets: f.pets };
  },
  async submit() {
    const f = this.data.form;
    if (!f.contactName || !f.contactPhone || !f.address || !f.startDate) {
      wx.showToast({ title: '请完整填写联系人、地址和开始日期', icon: 'none' }); return;
    }
    if (!this.regionId) { wx.showToast({ title: '当前地区暂未开通', icon: 'none' }); return; }
    this.setData({ submitting: true });
    try {
      const demand = await api.post('/api/v1/business/domestic/demands', {
        customer_id: this.data.userInfo.id,
        created_by_user_id: this.data.userInfo.id,
        store_id: this.store && this.store.id,
        region_id: this.regionId,
        service_type: this.data.serviceType,
        contact_name: f.contactName,
        contact_phone: f.contactPhone,
        address: f.address,
        description: f.description || (this.data.serviceType === 'maternity' ? '月嫂服务需求' : '保姆服务需求'),
        detail_json: JSON.stringify(this.buildDetail()),
        budget_min: Number(f.budgetMin || 0),
        budget_max: Number(f.budgetMax || 0),
        service_start: f.startDate,
      });
      for (const item of this.data.localMedia) {
        await api.upload(`/api/v1/business/domestic/demands/${demand.id}/media`, item.path, 'file', {
          media_type: item.type, duration: item.duration || 0,
        });
      }
      if (this.preferredWorkerId) await api.post(`/api/v1/business/domestic/demands/${demand.id}/candidates`, {
        worker_id: this.preferredWorkerId,
        proposed_by_user_id: this.data.userInfo.id,
        note: '客户从公开档案申请匹配',
      });
      wx.showToast({ title: '需求已提交', icon: 'success' });
      setTimeout(() => wx.redirectTo({ url: `/pages/customer/domestic/list/list?type=${this.data.serviceType}` }), 700);
    } catch (e) {
      this.setData({ submitting: false });
    }
  },
  onUnload() { clearInterval(this.recordTimer); if (this.data.recording) recorder.stop(); },
});
