/**
 * 立即修 - API 封装
 * 统一处理 Token、错误、baseURL
 */
const DEFAULT_BASE_URL = 'https://x.iddg.cn';

function getBaseURL() {
  try {
    const app = getApp();
    return (app && app.globalData && app.globalData.baseURL) || DEFAULT_BASE_URL;
  } catch (e) {
    return DEFAULT_BASE_URL;
  }
}

const request = (url, method = 'GET', data = {}) => {
  return new Promise((resolve, reject) => {
    const token = wx.getStorageSync('token');
    const header = { 'Content-Type': 'application/json' };
    if (token) header['Authorization'] = `Bearer ${token}`;

    wx.request({
      url: `${getBaseURL()}${url}`,
      method,
      header,
      data,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else if (res.statusCode === 401) {
          wx.removeStorageSync('token');
          wx.showToast({ title: '登录已过期，请重新登录', icon: 'none' });
          wx.reLaunch({ url: '/pages/login/login' });
          reject(new Error('登录已过期'));
        } else {
          const msg = (res.data && res.data.detail) || `请求失败(${res.statusCode})`;
          wx.showToast({ title: msg, icon: 'none' });
          reject(new Error(msg));
        }
      },
      fail(err) {
        wx.showToast({ title: '网络异常', icon: 'none' });
        reject(err);
      }
    });
  });
};

const upload = (url, filePath, name = 'file', formData = {}) => {
  return new Promise((resolve, reject) => {
    const token = wx.getStorageSync('token');
    const header = {};
    if (token) header['Authorization'] = `Bearer ${token}`;

    wx.uploadFile({
      url: `${getBaseURL()}${url}`,
      filePath,
      name,
      formData,
      header,
      success(res) {
        let data = res.data;
        try {
          data = JSON.parse(res.data);
        } catch (e) {
          // keep raw response
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(data);
        } else {
          const msg = (data && data.detail) || `上传失败(${res.statusCode})`;
          wx.showToast({ title: msg, icon: 'none' });
          reject(new Error(msg));
        }
      },
      fail(err) {
        wx.showToast({ title: '上传异常', icon: 'none' });
        reject(err);
      },
    });
  });
};

module.exports = {
  get: (url, data) => request(url, 'GET', data),
  post: (url, data) => request(url, 'POST', data),
  patch: (url, data) => request(url, 'PATCH', data),
  upload,
  resolveURL: (url) => (/^https?:\/\//.test(url || '') ? url : `${getBaseURL()}${url}`),
  setToken: (token) => { /* token 由 app.js 管理 */ },
};
