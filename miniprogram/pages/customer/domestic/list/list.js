const api = require('../../../../utils/api');
const share = require('../../../../utils/share');

Page({
  ...share.create({ title: '立即修｜月嫂保姆服务' }),
  data: {
    serviceType: 'maternity',
    title: '月嫂服务',
    subtitle: '根据档期、经验和技能匹配合适人选',
    guest: true,
    workers: [],
    myDemands: [],
    loading: true,
    failed: false,
  },
  onLoad(options) {
    this.setType(options.type || 'maternity');
  },
  onShow() { share.enable(); },
  onPullDownRefresh() { this.loadWorkers().finally(() => wx.stopPullDownRefresh()); },
  setType(type) {
    const serviceType = type === 'nanny' ? 'nanny' : 'maternity';
    this.setData({
      serviceType,
      title: serviceType === 'maternity' ? '月嫂服务' : '保姆服务',
      subtitle: serviceType === 'maternity'
        ? '根据档期、经验和技能匹配合适人选'
        : '住家、白班、钟点和长期服务均可发布',
    });
    wx.setNavigationBarTitle({ title: serviceType === 'maternity' ? '月嫂服务' : '保姆服务' });
    this.loadWorkers();
  },
  switchType(e) { this.setType(e.currentTarget.dataset.type); },
  async loadWorkers() {
    const guest = !wx.getStorageSync('token');
    this.setData({ guest });
    if (guest) {
      this.setData({ workers: [], myDemands: [], loading: false, failed: false });
      return;
    }
    this.setData({ loading: true, failed: false });
    try {
      const user = wx.getStorageSync('userInfo') || {};
      const [list, demands] = await Promise.all([
        api.get('/api/v1/business/domestic/workers', { service_type: this.data.serviceType, active: true }),
        user.id ? api.get('/api/v1/business/domestic/demands', { customer_id: user.id, service_type: this.data.serviceType }) : Promise.resolve([]),
      ]);
      this.setData({ workers: (list || []).map(item => ({
        ...item,
        initial: String(item.name || '服').slice(0, 1),
        priceText: item.price_min || item.price_max
          ? `¥${Number(item.price_min || 0).toFixed(0)}-${Number(item.price_max || 0).toFixed(0)}`
          : '面议',
        skills: this.parseList(item.skills_json).slice(0, 3),
        verifiedCount: [item.id_verified, item.health_verified, item.training_verified].filter(Boolean).length,
      })), myDemands: (demands || []).slice(0, 3).map(item => ({ ...item, statusText: ({ submitted: '待联系', matching: '匹配中', contracted: '已签约', completed: '已完成' })[item.status] || item.status })) });
    } catch (e) {
      this.setData({ failed: true });
    } finally {
      this.setData({ loading: false });
    }
  },
  parseList(value) {
    try { const list = JSON.parse(value || '[]'); return Array.isArray(list) ? list : []; }
    catch (e) { return []; }
  },
  publishDemand() {
    wx.navigateTo({ url: `/pages/customer/domestic/demand/demand?type=${this.data.serviceType}` });
  },
  openWorker(e) {
    wx.navigateTo({
      url: `/pages/customer/domestic/detail/detail?id=${e.currentTarget.dataset.id}&type=${this.data.serviceType}`,
    });
  },
});
