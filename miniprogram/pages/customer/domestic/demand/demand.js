const api = require('../../../../utils/api');

Page({
  data: {
    addressValue: {}, serviceType: 'maternity', title: '月嫂服务预约', userInfo: null,
    form: { contactName: '', contactPhone: '', address: '', startDate: '', budgetMin: '', budgetMax: '',
      expectedDate: '', cycleDays: '26', liveIn: true, serviceMode: '住家', familySize: '2',
      schedule: '联系确认', tasks: [], pets: false },
    cycleOptions: ['26', '42', '52'], modeOptions: ['住家', '白班', '钟点', '长期'],
    scheduleOptions: ['联系确认', '全天', '上午', '下午', '晚间'],
    taskOptions: ['做饭', '日常保洁', '衣物整理', '老人日常照护', '儿童日常照护'], submitting: false,
  },
  onLoad(options) {
    const serviceType = options.type === 'nanny' ? 'nanny' : 'maternity';
    this.preferredWorkerId = Number(options.workerId || 0);
    const userInfo = wx.getStorageSync('userInfo') || {};
    this.setData({serviceType, title:serviceType === 'maternity' ? '月嫂服务预约' : '保姆服务预约',userInfo,
      'form.contactName':userInfo.name || '', 'form.contactPhone':userInfo.phone || ''});
    wx.setNavigationBarTitle({title:this.data.title});
    this.hideSharing(); this.loadDefaults();
  },
  onShow() { this.hideSharing(); },
  hideSharing() { if (wx.hideShareMenu) wx.hideShareMenu({menus:['shareAppMessage','shareTimeline']}); },
  async loadDefaults() {
    if (!wx.getStorageSync('token')) return;
    const user = this.data.userInfo;
    try {
      const addresses=await api.get('/api/v1/business/addresses',{user_id:user.id});
      const address=(addresses || []).find(item=>item.is_default) || (addresses || [])[0];
      if(address)this.setData({addressValue:address,'form.contactName':address.contact_name || this.data.form.contactName,'form.contactPhone':address.contact_phone || this.data.form.contactPhone});
    } catch (e) {}
  },
  addressChange(e){this.setData({addressValue:e.detail,'form.address':e.detail.address});this.regionId=e.detail.region_id;},
  inputField(e) { this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value }); },
  switchField(e) { this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value }); },
  dateChange(e) { this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value }); },
  cycleChange(e) { this.setData({ 'form.cycleDays': this.data.cycleOptions[Number(e.detail.value)] }); },
  scheduleChange(e) { this.setData({ 'form.schedule': this.data.scheduleOptions[Number(e.detail.value)] }); },
  tasksChange(e) { this.setData({ 'form.tasks': e.detail.value }); },
  modeChange(e) { this.setData({ 'form.serviceMode': this.data.modeOptions[Number(e.detail.value)] }); },
  buildDetail() {
    const f = this.data.form;
    return this.data.serviceType === 'maternity'
      ? { expected_date: f.expectedDate, cycle_days: f.cycleDays, live_in: f.liveIn }
      : { service_mode: f.serviceMode, family_size: f.familySize, schedule: f.schedule, tasks: f.tasks, pets: f.pets };
  },
  async submit() {
    if(this.data.submitting)return;
    if (!wx.getStorageSync('token')) {
      wx.showModal({ title: '登录后提交预约', content: '浏览服务无需登录，提交预约时需登录以便门店联系。', confirmText: '去登录', cancelText: '继续浏览', success: (res) => { if (res.confirm) wx.navigateTo({ url: '/pages/login/login?intent=login' }); } });
      return;
    }
    const f = this.data.form;
    if (!f.contactName || !f.contactPhone || !f.address || !f.startDate) {
      wx.showToast({ title: '请完整填写联系人、地址和开始日期', icon: 'none' }); return;
    }
    if (!this.regionId || !this.data.addressValue.address_book_id) { wx.showToast({ title: '当前地区暂未开通', icon: 'none' }); return; }
    this.setData({ submitting: true });
    try {
      const demand = await api.post('/api/v1/business/domestic/demands', {
        address_book_id:this.data.addressValue.address_book_id,
        customer_id: this.data.userInfo.id,
        created_by_user_id: this.data.userInfo.id,
        store_id: this.data.addressValue.store_id,
        region_id: this.regionId,
        service_type: this.data.serviceType,
        contact_name: f.contactName,
        contact_phone: f.contactPhone,
        address: f.address,
        description: this.data.serviceType === 'maternity' ? '月嫂服务预约申请' : '保姆服务预约申请',
        detail_json: JSON.stringify(this.buildDetail()),
        budget_min: Number(f.budgetMin || 0),
        budget_max: Number(f.budgetMax || 0),
        service_start: f.startDate,
      });
      if (this.preferredWorkerId) await api.post(`/api/v1/business/domestic/demands/${demand.id}/candidates`, {
        worker_id: this.preferredWorkerId,
        proposed_by_user_id: this.data.userInfo.id,
        note: '客户从公开档案申请匹配',
      });
      wx.showToast({ title: '预约申请已提交', icon: 'success' });
      setTimeout(() => wx.redirectTo({ url: `/pages/customer/domestic/list/list?type=${this.data.serviceType}` }), 700);
    } catch (e) {
      this.setData({ submitting: false });
    }
  },
});
