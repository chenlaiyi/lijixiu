/**
 * 立即修 - 登录/认证工具
 * 封装 wx.login → 后端换取 token 的完整流程
 */
const api = require('./api');

/**
 * 执行登录
 * @param {string} code - 开发模式: 'phone:name:role'，如 '13800138000:张三:customer'
 */
async function login(code, extra = {}) {
  // wx.login 获取 code（开发模式直接传自定义 code）
  if (!code) {
    return new Promise((resolve, reject) => {
      wx.login({
        success: async (res) => {
          try {
            const result = await _doLogin(res.code, extra);
            resolve(result);
          } catch (e) { reject(e); }
        },
        fail: reject
      });
    });
  }
  return _doLogin(code, extra);
}

async function _doLogin(code, extra = {}) {
  const res = await api.post('/api/v1/auth/wechat-login', { code, ...extra });
  return persistLogin(res);
}

async function loginWithPhoneCode(phoneCode, extra = {}) {
  const res = await api.post('/api/v1/auth/wechat-phone-login', {
    phone_code: phoneCode,
    ...extra,
  });
  return persistLogin(res);
}

async function requestSmsCode(phone) {
  return api.post('/api/v1/auth/sms/request', { phone });
}

async function loginWithSms(phone, code, extra = {}) {
  const res = await api.post('/api/v1/auth/sms/login', { phone, code, ...extra });
  return persistLogin(res);
}

async function loginForReview(account, password, extra = {}) {
  const res = await api.post('/api/v1/auth/review-login', {
    account,
    password,
    ...extra,
  });
  return persistLogin(res);
}

function persistLogin(res) {
  // 保存登录态
  wx.setStorageSync('token', res.token);
  wx.setStorageSync('userInfo', res.user);
  wx.removeStorageSync('reviewExperience');
  return res.user;
}

/** 检查登录态是否有效 */
async function checkLogin() {
  try {
    const user = await api.get('/api/v1/auth/me');
    return user;
  } catch {
    return null;
  }
}

/** 退出登录 */
function logout() {
  wx.removeStorageSync('token');
  wx.removeStorageSync('userInfo');
  wx.removeStorageSync('reviewExperience');
  wx.reLaunch({ url: '/pages/customer/home/home' });
}

module.exports = {
  login,
  loginWithPhoneCode,
  requestSmsCode,
  loginWithSms,
  loginForReview,
  checkLogin,
  logout,
};
