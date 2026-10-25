const role = require('../../utils/role');
const share = require('../../utils/share');

// 给用户 1.2 秒看到品牌区, 不再像之前 280ms 那样一闪而过
const ENTRY_DELAY_MS = 1200;
// 重试次数上限, 防止死循环
const MAX_AUTO_RETRY = 2;

Page({
  ...share.create({ title: '立即修｜上门维修' }),

  data: {
    statusText: '进入中',
    showRetry: false,
    errorHint: '',
  },

  onLoad() {
    share.enable();
    this.enter();
  },

  onUnload() {
    this._clearTimers();
  },

  _clearTimers() {
    if (this.enterTimer) {
      clearTimeout(this.enterTimer);
      this.enterTimer = null;
    }
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
  },

  enter() {
    this._clearTimers();
    this.setData({
      statusText: '进入中',
      showRetry: false,
      errorHint: '',
    });
    this.enterTimer = setTimeout(() => this._attemptEntry('redirect', 0), ENTRY_DELAY_MS);
  },

  _attemptEntry(method, attempt) {
    const target = wx.getStorageSync('token') ? role.getEntryPath(wx.getStorageSync('userInfo')) : '/pages/customer/home/home';
    const navigate = method === 'relaunch' ? wx.reLaunch : wx.redirectTo;
    navigate({
      url: target,
      success: () => {
        // 跳转成功, 后续逻辑交给 login 页处理
      },
      fail: (err) => {
        // redirectTo 失败时降级到 reLaunch, 最多再尝试一次
        if (method === 'redirect' && attempt < MAX_AUTO_RETRY) {
          this._attemptEntry('relaunch', attempt + 1);
          return;
        }
        // reLaunch 也失败, 或已达上限, 落到重试面板
        const reason = this._classifyError(err);
        this.setData({
          statusText: '进入失败',
          showRetry: true,
          errorHint: reason,
        });
      },
    });
  },

  _classifyError(err) {
    const msg = String((err && (err.errMsg || err.message)) || err || '').toLowerCase();
    if (!msg) return '网络异常,请检查后重试';
    if (msg.includes('timeout')) return '网络超时,请检查后重试';
    if (msg.includes('navigate') || msg.includes('url not in')) return '页面路径不可用,请重试';
    return '进入失败,请稍后重试';
  },

  onContact() {
    // 微信内置客服会话入口, 失败时给个非阻塞提示
    // open-type="contact" 触发, 这里做兜底
  },
});
