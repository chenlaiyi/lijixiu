const DEFAULT_TITLE = '立即修｜上门维修服务平台';
const DEFAULT_IMAGE = '/assets/logo-mark.png';

function encodeQuery(params) {
  const pairs = [];
  Object.keys(params || {}).forEach((key) => {
    const value = params[key];
    if (value === undefined || value === null || value === '') return;
    pairs.push(`${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
  });
  return pairs.join('&');
}

function getPageOptions(page) {
  return (page && page.options) || {};
}

function getCurrentPath(page) {
  const route = page && page.route ? page.route : 'pages/login/login';
  const query = encodeQuery({
    ...getPageOptions(page),
    from: 'share',
  });
  return `/${route}${query ? `?${query}` : ''}`;
}

function resolveValue(value, page, fallback) {
  if (typeof value === 'function') return value.call(page);
  return value || fallback;
}

function enable() {
  if (!wx.showShareMenu) return;
  wx.showShareMenu({
    withShareTicket: true,
    menus: ['shareAppMessage', 'shareTimeline'],
  });
}

function create(config = {}) {
  return {
    onShareAppMessage() {
      return {
        title: resolveValue(config.title, this, DEFAULT_TITLE),
        path: resolveValue(config.path, this, getCurrentPath(this)),
        imageUrl: resolveValue(config.imageUrl, this, DEFAULT_IMAGE),
      };
    },

    onShareTimeline() {
      return {
        title: resolveValue(config.timelineTitle || config.title, this, DEFAULT_TITLE),
        query: encodeQuery({
          ...getPageOptions(this),
          from: 'timeline',
        }),
        imageUrl: resolveValue(config.imageUrl, this, DEFAULT_IMAGE),
      };
    },
  };
}

module.exports = {
  enable,
  create,
};
