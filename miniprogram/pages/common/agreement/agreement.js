const TABS = ['terms', 'privacy'];

Page({
  data: {
    activeTab: 'terms',
  },

  onLoad(options) {
    const tab = options && options.tab;
    if (TABS.indexOf(tab) !== -1) {
      this.setData({ activeTab: tab });
    }
    wx.setNavigationBarTitle({
      title: this.data.activeTab === 'privacy' ? '隐私保护指引' : '用户协议',
    });
  },

  switchTab(e) {
    const tab = e.currentTarget.dataset.tab;
    if (TABS.indexOf(tab) === -1 || tab === this.data.activeTab) return;
    this.setData({ activeTab: tab });
    wx.setNavigationBarTitle({
      title: tab === 'privacy' ? '隐私保护指引' : '用户协议',
    });
  },
});
