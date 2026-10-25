const auth = require('../../utils/auth');
const share = require('../../utils/share');
const role = require('../../utils/role');

function callWx(method, options = {}) {
  return new Promise((resolve, reject) => {
    if (!wx[method]) {
      reject(new Error(`${method} is not supported`));
      return;
    }
    wx[method]({ ...options, success: resolve, fail: reject });
  });
}

function normalizeErrMsg(value = '') {
  return String(value || '').toLowerCase();
}

function resolvePhoneAuthFailure(detail = {}) {
  const errMsg = normalizeErrMsg(detail.errMsg);
  const manualFallback = {
    tip: '请填写手机号继续登录。',
    toast: '',
    tone: '',
    showManual: true,
  };
  if (errMsg.includes('no quota') || errMsg.includes('quota')) {
    return {
      tip: '手机号快捷登录暂不可用，请填写手机号继续。',
      toast: '',
      tone: 'warning',
      showManual: true,
    };
  }
  if (
    errMsg.includes('no permission')
    || errMsg.includes('unauthorized')
    || errMsg.includes('api scope')
    || errMsg.includes('jsapi has no permission')
  ) {
    return {
      tip: '手机号快捷登录暂不可用，请填写手机号继续。',
      toast: '',
      tone: 'warning',
      showManual: true,
    };
  }
  if (
    errMsg.includes('cancel')
    || errMsg.includes('deny')
    || errMsg.includes('auth deny')
    || errMsg.includes('user deny')
    || errMsg.includes('user reject')
  ) {
    return manualFallback;
  }
  if (detail.encryptedData && detail.iv) {
    return {
      tip: '当前版本不支持手机号快捷登录，请填写手机号继续。',
      toast: '',
      tone: 'warning',
      showManual: true,
    };
  }
  return manualFallback;
}

Page({
  ...share.create({ title: '立即修｜上门维修' }),

  data: {
    agreementAccepted: false,
    phone: '',
    smsCode: '',
    smsSending: false,
    smsCountdown: 0,
    debugSmsCode: '',
    name: '',
    loading: false,
    phoneAuthReady: false,
    phoneAuthPreparing: false,
    phoneInputFocus: false,
    focusField: '',
    validationErrors: { phone: '' },
    heroPaddingTop: 72,
    capsuleRightReserve: 108,
    showPrivacyModal: false,
    privacyLoading: false,
    privacyMode: 'local',
    privacyContractName: '用户隐私保护指引',
    quickLoginTip: '',
    quickLoginTipTone: '',
    // v2:登录方式 tab(wechat 微信登录 / phone 手机号 / account 账号密码)
    loginMode: 'wechat',
    showAccountLogin: false,
    reviewAccount: '',
    reviewPassword: '',
    accountLoginError: '',
    showDemoAccounts: false,
    demos: [
      { phone: '18800000001', name: '演示客户', label: '客户' },
      { phone: '18800000002', name: '演示师傅', label: '师傅' },
      { phone: '18800000003', name: '演示兜底', label: '兜底' },
      { phone: '18800000004', name: '演示店长', label: '店长' },
      { phone: '18800000005', name: '演示城市经理', label: '城市' },
      { phone: '18800000006', name: '演示推广经理', label: '推广' },
      { phone: '18800000007', name: '演示服务保障', label: '保障' },
      { phone: '18800000008', name: '演示财务', label: '财务' },
      { phone: '18800000000', name: '演示平台', label: '平台' },
    ],
  },

  onLoad() {
    share.enable();
    this._applyNavSafeArea();
    this.initPrivacy();
    if (wx.getStorageSync('token')) this._redirectByRole();
  },

  onAgreementChange(e) {
    this.setData({ agreementAccepted: (e.detail.value || []).includes('accept') });
  },

  requireAgreement() {
    if (this.data.agreementAccepted) return true;
    wx.showToast({ title: '请阅读并自主勾选协议', icon: 'none' });
    return false;
  },

  openTerms() { wx.navigateTo({ url: '/pages/common/agreement/agreement?tab=terms' }); },
  openPolicy() { wx.navigateTo({ url: '/pages/common/agreement/agreement?tab=privacy' }); },
  browseServices() { wx.reLaunch({ url: '/pages/customer/home/home' }); },

  onPhoneInput(e) {
    const phone = e.detail.value;
    const validationErrors = { ...this.data.validationErrors };
    if (phone.length === 11) validationErrors.phone = '';
    this.setData({ phone, validationErrors });
  },

  onNameInput(e) {
    this.setData({ name: e.detail.value });
  },

  onSmsCodeInput(e) { this.setData({ smsCode: e.detail.value }); },

  onReviewAccountInput(e) {
    this.setData({ reviewAccount: e.detail.value, accountLoginError: '' });
  },

  onReviewPasswordInput(e) {
    this.setData({ reviewPassword: e.detail.value, accountLoginError: '' });
  },

  async sendSmsCode() {
    if (!this.requireAgreement()) return;
    const phone = this.data.phone;
    if (!phone || phone.length !== 11) {
      this.setData({ validationErrors: { phone: '请输入 11 位手机号' }, phoneInputFocus: true });
      return;
    }
    this.setData({ smsSending: true, debugSmsCode: '' });
    try {
      const result = await auth.requestSmsCode(phone);
      this.setData({ smsCountdown: 60, debugSmsCode: result.debug_code || '' });
      clearInterval(this.smsTimer);
      this.smsTimer = setInterval(() => {
        const next = this.data.smsCountdown - 1;
        this.setData({ smsCountdown: Math.max(0, next) });
        if (next <= 0) clearInterval(this.smsTimer);
      }, 1000);
      wx.showToast({ title: '验证码已发送', icon: 'success' });
    } catch (e) {
      wx.showToast({ title: e.message || '验证码发送失败', icon: 'none' });
    } finally { this.setData({ smsSending: false }); }
  },

  onFieldFocus(e) {
    this.setData({ focusField: e.currentTarget.dataset.field || '' });
  },

  onFieldBlur() {
    this.setData({ focusField: '', phoneInputFocus: false });
  },

  toggleDemoAccounts() {
    if (this.data.loading) return;
    this.setData({ showDemoAccounts: !this.data.showDemoAccounts });
  },

  // v2:tab 切换(wechat / phone / account)
  switchLoginMode(e) {
    if (this.data.loading) return;
    const mode = e.currentTarget.dataset.mode;
    if (!mode || mode === this.data.loginMode) return;
    this.setData({
      loginMode: mode,
      accountLoginError: '',
      quickLoginTip: '',
      quickLoginTipTone: '',
      validationErrors: { phone: '' },
      phoneInputFocus: mode === 'phone',
      focusField: mode === 'account' ? 'reviewAccount' : '',
    });
  },

  // v2:从微信 tab 切到手机号 tab(兼容旧链接)
  toggleManualLogin() {
    this.switchLoginMode({ currentTarget: { dataset: { mode: 'phone' } } });
  },

  toggleAccountLogin() {
    this.switchLoginMode({ currentTarget: { dataset: { mode: 'account' } } });
  },

  async handleAccountLogin() {
    if (!this.requireAgreement()) return;
    if (this.data.loading) return;
    const account = String(this.data.reviewAccount || '').trim();
    const password = String(this.data.reviewPassword || '');
    if (!account || !password) {
      this.setData({ accountLoginError: '请输入账号和密码' });
      return;
    }
    this.setData({ loading: true, accountLoginError: '' });
    try {
      const wxLogin = await callWx('login').catch(() => ({}));
      await auth.loginForReview(account, password, { wx_code: wxLogin.code || undefined });
      wx.setStorageSync('reviewExperience', true);
      wx.showToast({ title: '登录成功', icon: 'success' });
      wx.redirectTo({ url: '/pages/repairer/earnings/earnings' });
    } catch (e) {
      this.setData({ accountLoginError: '账号或密码不正确' });
    } finally {
      this.setData({ loading: false });
    }
  },

  showManualFallback(tip = '', tone = '') {
    this.setData({
      loginMode: 'phone',
      quickLoginTip: tip,
      quickLoginTipTone: tone,
      validationErrors: { phone: '' },
      phoneInputFocus: true,
    });
  },

  handleWechatPhoneTap() {
    if (!this.requireAgreement()) return;
    if (this.data.loading || this.data.phoneAuthPreparing) return;
    this.setData({
      quickLoginTip: '',
      quickLoginTipTone: '',
      validationErrors: { phone: '' },
      phoneInputFocus: false,
    });
    if (!this.data.phoneAuthReady) this.prepareWechatPhoneLogin();
  },

  initPrivacy() {
    this.privacyRequestPromise = null;
    this.privacyRequestResolve = null;
    this.privacyResolve = null;
    this.privacyRequireFailed = false;

    if (wx.onNeedPrivacyAuthorization) {
      wx.onNeedPrivacyAuthorization((resolve, eventInfo) => {
        this.privacyResolve = resolve;
        this.privacyEventInfo = eventInfo || {};
        this.setData({ showPrivacyModal: true, privacyLoading: false, privacyMode: 'wechat' });
      });
    }

    this.refreshPrivacySetting().then((setting) => {
      this.setData({ phoneAuthReady: !setting.needAuthorization });
    });
  },

  async refreshPrivacySetting() {
    if (!wx.getPrivacySetting) return { needAuthorization: false };
    const setting = await callWx('getPrivacySetting').catch(() => ({ needAuthorization: false }));
    this.setData({ privacyContractName: setting.privacyContractName || '用户隐私保护指引' });
    return setting;
  },

  finishPrivacyRequest(ok) {
    clearTimeout(this.privacyAgreeTimer);
    clearTimeout(this.privacyFailTimer);
    this.privacyAgreeTimer = null;
    this.privacyFailTimer = null;
    const resolve = this.privacyRequestResolve;
    this.privacyRequestResolve = null;
    this.privacyRequestPromise = null;
    this.privacyResolve = null;
    this.privacyRequireFailed = false;
    this.setData({
      showPrivacyModal: false,
      privacyLoading: false,
      phoneAuthReady: !!ok || this.data.phoneAuthReady,
    });
    if (ok) wx.setStorageSync('privacyAcceptedAt', Date.now());
    if (typeof resolve === 'function') resolve(ok);
  },

  async requestPrivacy(force = false) {
    const setting = await this.refreshPrivacySetting();
    if (!setting.needAuthorization) {
      this.setData({ phoneAuthReady: true });
      return true;
    }
    if (this.privacyRequestPromise) return this.privacyRequestPromise;

    this.privacyRequestPromise = new Promise((resolve) => {
      this.privacyRequestResolve = resolve;

      if (!wx.requirePrivacyAuthorize || !setting.needAuthorization) {
        this.setData({ showPrivacyModal: true, privacyLoading: false, privacyMode: 'local' });
        return;
      }

      this.setData({ showPrivacyModal: true, privacyLoading: false, privacyMode: 'wechat' });
      wx.requirePrivacyAuthorize({
        success: () => this.finishPrivacyRequest(true),
        fail: () => {
          this.privacyRequireFailed = true;
          clearTimeout(this.privacyFailTimer);
          this.privacyFailTimer = setTimeout(() => {
            if (!this.privacyRequestPromise) return;
            if (this.privacyResolve) return;
            this.setData({ showPrivacyModal: true, privacyLoading: false, privacyMode: 'local' });
          }, 1500);
        },
      });
    });

    return this.privacyRequestPromise;
  },

  async prepareWechatPhoneLogin() {
    if (!this.requireAgreement()) return;
    if (this.data.loading || this.data.phoneAuthPreparing) return;
    this.setData({
      phoneAuthPreparing: true,
      quickLoginTip: '请先完成隐私授权。',
      quickLoginTipTone: '',
      validationErrors: { phone: '' },
      phoneInputFocus: false,
    });
    try {
      const ok = await this.requestPrivacy(true);
      if (ok) {
        this.setData({
          phoneAuthReady: true,
          quickLoginTip: '已完成隐私授权，请再次点击手机号快捷登录。',
          quickLoginTipTone: 'success',
        });
      } else {
        this.showManualFallback('请填写手机号继续登录。');
      }
    } catch (err) {
      this.showManualFallback('请填写手机号继续登录。');
    } finally {
      this.setData({ phoneAuthPreparing: false });
    }
  },

  openPrivacyContract() {
    if (!wx.openPrivacyContract) {
      wx.showToast({ title: '当前版本不支持查看', icon: 'none' });
      return;
    }
    wx.openPrivacyContract({
      fail: () => wx.showToast({ title: '隐私指引打开失败', icon: 'none' }),
    });
  },

  handleAgreePrivacyAuthorization(e) {
    const detail = (e && e.detail) || {};
    if (detail.errMsg && detail.errMsg.indexOf('fail') !== -1) {
      wx.showToast({ title: '隐私授权未完成，请再试一次', icon: 'none' });
      return;
    }

    this.setData({ privacyLoading: true });
    if (typeof this.privacyResolve === 'function') {
      this.privacyResolve({ buttonId: 'login-agree-btn', event: 'agree' });
      clearTimeout(this.privacyAgreeTimer);
      this.privacyAgreeTimer = setTimeout(() => {
        if (!this.privacyRequestPromise) return;
        this.finishPrivacyRequest(true);
      }, 300);
      return;
    }
    this.finishPrivacyRequest(true);
  },

  handleAgreeLocalPrivacy() {
    if (this.data.privacyLoading) return;
    this.setData({ privacyLoading: true });
    this.finishPrivacyRequest(true);
  },

  handleRejectPrivacy() {
    if (this.data.privacyLoading) return;
    if (typeof this.privacyResolve === 'function') {
      this.privacyResolve({ event: 'disagree' });
    }
    this.finishPrivacyRequest(false);
    wx.showToast({ title: '同意后才能使用语音、照片和视频', icon: 'none' });
  },

  _applyNavSafeArea() {
    const app = getApp();
    const metrics = app.getNavMetrics ? app.getNavMetrics() : null;
    if (!metrics) return;
    this.setData({
      heroPaddingTop: metrics.customPageTop,
      capsuleRightReserve: metrics.capsuleRightReserve,
    });
  },

  async enterFullExperience() {
    if (!this.requireAgreement()) return;
    if (this.data.loading) return;
    const item = { phone: '18800000999', name: '审核功能体验' };
    this.setData({ loading: true, accountLoginError: '' });
    try {
      const backendRole = role.getBackendRole(item.phone);
      const wxLogin = await callWx('login').catch(() => ({}));
      await auth.login(`${item.phone}:${item.name}:${backendRole}`, {
        phone: item.phone,
        name: item.name,
        role: backendRole,
        wx_code: wxLogin.code || undefined,
      });
      wx.setStorageSync('reviewExperience', true);
      wx.showToast({ title: '进入成功', icon: 'success' });
      wx.redirectTo({ url: '/pages/repairer/earnings/earnings' });
    } catch (e) {
      wx.showToast({ title: e.message || '暂时无法进入', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  useDemo(e) {
    if (this.data.loading) return;
    const item = this.data.demos[e.currentTarget.dataset.index];
    this.setData({
      phone: item.phone,
      name: item.name,
      showDemoAccounts: false,
      validationErrors: { phone: '' },
    }, () => {
      this.handleDemoLogin(item);
    });
  },

  async handleDemoLogin(item) {
    if (!this.requireAgreement()) return;
    this.setData({ loading: true });
    try {
      const backendRole = role.getBackendRole(item.phone);
      const wxLogin = await callWx('login').catch(() => ({}));
      const user = await auth.login(`${item.phone}:${item.name}:${backendRole}`, {
        phone: item.phone,
        name: item.name,
        role: backendRole,
        wx_code: wxLogin.code || undefined,
      });
      wx.showToast({ title: '登录成功', icon: 'success' });
      this._redirectByRole(user);
    } catch (e) {
      wx.showToast({ title: e.message || '登录失败', icon: 'none' });
    } finally { this.setData({ loading: false }); }
  },

  async handleWechatPhoneLogin(e) {
    if (!this.requireAgreement()) return;
    if (this.data.loading) return;
    const detail = (e && e.detail) || {};
    if (!detail.code) {
      const failure = resolvePhoneAuthFailure(detail);
      console.warn('getPhoneNumber did not return code', detail);
      if (failure.showManual) {
        this.showManualFallback(failure.tip, failure.tone);
      } else {
        this.setData({
          quickLoginTip: failure.tip,
          quickLoginTipTone: failure.tone,
          phoneInputFocus: false,
        });
      }
      if (failure.toast) wx.showToast({ title: failure.toast, icon: 'none' });
      return;
    }

    this.setData({
      loading: true,
      quickLoginTip: '',
      quickLoginTipTone: '',
      validationErrors: { phone: '' },
    });
    try {
      const wxLogin = await callWx('login').catch(() => ({}));
      const user = await auth.loginWithPhoneCode(detail.code, {
        wx_code: wxLogin.code || undefined,
        name: '手机号用户',
        role: 'customer',
      });
      wx.showToast({ title: '登录成功', icon: 'success' });
      this._redirectByRole(user);
    } catch (err) {
      const message = (err && err.message) || '';
      console.warn('wechat phone login failed', err);
      this.showManualFallback('手机号快捷登录暂不可用，请填写手机号继续。', 'warning');
      if (message.includes('404')) {
        wx.showToast({ title: '快捷登录未配置', icon: 'none' });
      } else {
        wx.showToast({ title: message || '快捷登录暂不可用', icon: 'none' });
      }
    } finally {
      this.setData({ loading: false });
    }
  },

  async handleLogin() {
    if (!this.requireAgreement()) return;
    if (this.data.loading) return;
    const { phone, name, smsCode } = this.data;
    if (!phone || phone.length < 11) {
      this.setData({
        loginMode: 'phone',
        validationErrors: { phone: '请输入 11 位手机号' },
        phoneInputFocus: true,
      });
      wx.showToast({ title: '请输入正确的手机号', icon: 'none' });
      return;
    }
    if (!smsCode || smsCode.length < 4) {
      wx.showToast({ title: '请输入短信验证码', icon: 'none' });
      return;
    }

    this.setData({ loading: true });
    try {
      const displayName = name || `用户${phone.slice(-4)}`;
      const wxLogin = await callWx('login').catch(() => ({}));
      const user = await auth.loginWithSms(phone, smsCode, {
        name: displayName,
        wx_code: wxLogin.code || undefined,
      });
      wx.showToast({ title: '登录成功', icon: 'success' });
      this._redirectByRole(user);
    } catch (e) {
      wx.showToast({ title: e.message || '登录失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  _redirectByRole(user) {
    const userInfo = wx.getStorageSync('userInfo');
    const pendingAccessToken = wx.getStorageSync('pendingAccessToken');
    if (pendingAccessToken) {
      wx.redirectTo({
        url: `/pages/proxy/access/access?token=${encodeURIComponent(pendingAccessToken)}`,
      });
      return;
    }
    wx.redirectTo({ url: role.getEntryPath(user || userInfo) });
  },

  onUnload() {
    clearTimeout(this.privacyAgreeTimer);
    clearTimeout(this.privacyFailTimer);
    clearInterval(this.smsTimer);
  },
});
