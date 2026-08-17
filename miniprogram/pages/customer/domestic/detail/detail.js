const api = require('../../../../utils/api');
const share = require('../../../../utils/share');

Page({
  ...share.create({ title: '立即修｜服务人员档案' }),
  data: { worker: null, skills: [], loading: true, errorText: '', serviceType: 'maternity' },
  onLoad(options) {
    this.workerId = Number(options.id);
    this.setData({ serviceType: options.type === 'nanny' ? 'nanny' : 'maternity' });
    this.loadWorker();
  },
  onShow() { share.enable(); },
  async loadWorker() {
    this.setData({ loading: true, errorText: '' });
    try {
      const worker = await api.get(`/api/v1/business/domestic/workers/${this.workerId}`);
      if (!worker) {
        this.setData({ loading: false, worker: null });
        return;
      }
      let skills = [];
      try { skills = JSON.parse(worker.skills_json || '[]'); } catch (e) {}
      this.setData({ worker, skills: Array.isArray(skills) ? skills : [] });
      wx.setNavigationBarTitle({ title: `${worker.name}的档案` });
    } catch (e) {
      this.setData({ errorText: e.message || '档案加载失败，请稍后再试' });
    } finally {
      this.setData({ loading: false });
    }
  },
  publishDemand() {
    wx.navigateTo({
      url: `/pages/customer/domestic/demand/demand?type=${this.data.serviceType}&workerId=${this.workerId}`,
    });
  },
});
