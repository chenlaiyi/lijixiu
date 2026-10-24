const api = require('../../../utils/api');
const share = require('../../../utils/share');
Page({
  ...share.create({ title: '立即修｜我的地址簿' }),
  data: { list: [], loading: true, errorText: '', editingId: 0, showForm: false, saving: false,
    addressValue: {}, form: { contactName: '', contactPhone: '', isDefault: false } },
  onShow() { share.enable(); this.load(); },
  async load() {
    const user = wx.getStorageSync('userInfo');
    if (!user) return;
    try {
      const list = await api.get('/api/v1/business/addresses', { user_id: user.id });
      this.setData({ list, errorText: '' });
    } catch (e) { this.setData({ errorText: e.message || '地址加载失败' }); }
    finally { this.setData({ loading: false }); }
  },
  openAdd() {
    const user = wx.getStorageSync('userInfo') || {};
    this.setData({ showForm: true, editingId: 0, addressValue: {},
      form: { contactName: user.name || '', contactPhone: user.phone || '', isDefault: !this.data.list.length } });
  },
  openEdit(e) {
    const item = this.data.list.find(row => row.id === Number(e.currentTarget.dataset.id));
    if (!item) return;
    this.setData({ showForm: true, editingId: item.id, addressValue: item,
      form: { contactName: item.contact_name, contactPhone: item.contact_phone, isDefault: item.is_default } });
  },
  addressChange(e) { this.setData({ addressValue: e.detail }); },
  closeForm() { this.setData({ showForm: false }); },
  noop() {},
  input(e) { this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value }); },
  switchDefault(e) { this.setData({ 'form.isDefault': e.detail.value }); },
  async save() {
    const f = this.data.form, v = this.data.addressValue;
    if (!f.contactName || !f.contactPhone || !v.service_area_id || !v.estate || !v.door_number) {
      wx.showToast({ title: '请补全联系人、小区和门牌号', icon: 'none' }); return;
    }
    const user = wx.getStorageSync('userInfo');
    this.setData({ saving: true });
    try {
      const body = { contact_name: f.contactName, contact_phone: f.contactPhone, is_default: f.isDefault,
        service_area_id: v.service_area_id, estate: v.estate, door_number: v.door_number };
      if (this.data.editingId) await api.patch(`/api/v1/business/addresses/${this.data.editingId}`, body);
      else await api.post('/api/v1/business/addresses', { ...body, user_id: user.id });
      this.setData({ showForm: false }); await this.load();
    } catch (e) { wx.showToast({ title: e.message || '保存失败', icon: 'none' }); }
    finally { this.setData({ saving: false }); }
  },
});
