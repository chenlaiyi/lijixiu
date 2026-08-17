const api = require('../../../utils/api');
const share = require('../../../utils/share');

Page({
  ...share.create({ title: '立即修｜我的地址簿' }),
  data: {
    list: [], serviceAddresses: [], loading: true, errorText: '', editingId: 0, showForm: false, saving: false,
    form: { contactName: '', contactPhone: '', serviceAddressId: 0, serviceAddressIndex: 0, address: '', isDefault: false },
  },
  onShow() { share.enable(); this.load(); },
  async load() {
    const user = wx.getStorageSync('userInfo');
    if (!user) return;
    this.setData({ errorText: '' });
    try {
      const [list, serviceAddresses] = await Promise.all([
        api.get('/api/v1/business/addresses', { user_id: user.id }),
        api.get('/api/v1/stores/addresses', { enabled: true }),
      ]);
      this.setData({
        list: (list || []).filter(item => item.service_address_id),
        serviceAddresses: serviceAddresses || [],
        errorText: '',
      });
    } catch (e) {
      this.setData({ errorText: e.message || '地址加载失败，请稍后再试' });
    } finally {
      this.setData({ loading: false });
    }
  },
  openAdd() {
    const user = wx.getStorageSync('userInfo') || {};
    const selected = this.data.serviceAddresses[0] || {};
    this.setData({ showForm: true, editingId: 0, form: { contactName: user.name || '', contactPhone: user.phone || '', serviceAddressId: selected.id || 0, serviceAddressIndex: 0, address: selected.full_address || '', isDefault: this.data.list.length === 0 } });
  },
  openEdit(e) {
    const item = this.data.list.find(row => row.id === Number(e.currentTarget.dataset.id));
    if (!item) return;
    const index = Math.max(0, this.data.serviceAddresses.findIndex(row => row.id === item.service_address_id));
    this.setData({ showForm: true, editingId: item.id, form: { contactName: item.contact_name, contactPhone: item.contact_phone, serviceAddressId: item.service_address_id || 0, serviceAddressIndex: index, address: item.address, isDefault: item.is_default } });
  },
  closeForm() { this.setData({ showForm: false }); },
  noop() {},
  input(e) { this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value }); },
  selectServiceAddress(e) {
    const index = Number(e.detail.value);
    const selected = this.data.serviceAddresses[index];
    if (!selected) return;
    this.setData({
      'form.serviceAddressIndex': index,
      'form.serviceAddressId': selected.id,
      'form.address': selected.full_address,
    });
  },
  switchDefault(e) { this.setData({ 'form.isDefault': e.detail.value }); },
  async save() {
    const f = this.data.form;
    if (!f.contactName || !f.contactPhone || !f.serviceAddressId) { wx.showToast({ title: '请选择已开通的标准地址', icon: 'none' }); return; }
    const user = wx.getStorageSync('userInfo');
    this.setData({ saving: true });
    try {
      const body = { contact_name: f.contactName, contact_phone: f.contactPhone, is_default: f.isDefault };
      if (this.data.editingId) await api.patch(`/api/v1/business/addresses/${this.data.editingId}`, body);
      else await api.post('/api/v1/business/addresses', { ...body, user_id: user.id, service_address_id: f.serviceAddressId });
      this.setData({ showForm: false });
      await this.load();
    } catch (e) {
      wx.showToast({ title: e.message || '保存失败', icon: 'none' });
    } finally { this.setData({ saving: false }); }
  },
});
