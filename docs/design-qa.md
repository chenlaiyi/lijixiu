**Comparison Target**

- Source visual truth: `D:\app\xiulijiu\design\reference-option-1.png`
- Implementation screenshot: see supplemental evidence below
- Viewport: 390 x 844
- State: customer home, logged-in customer with an active order

**Full-View Comparison Evidence**

- The selected source visual was opened and reviewed before implementation.
- WeChat CI compiled every registered JS, JSON, WXML, and WXSS file successfully and uploaded version `1.0.211`.
- A rendered miniprogram screenshot could not be captured initially. The newly installed WeChat Developer Tools requires an interactive WeChat login before project automation is available, and the Windows capture attempt returned `SetIsBorderRequired failed: unsupported interface (0x80004002)`.

**Supplemental Evidence (2026-08-09, 9 roles, 57 screenshots)**

H5 工作台实现截图(同源 390x844):

- 工具脚本:`scripts/screenshot_h5.js`(用 Edge 远程调试 + Playwright `connectOverCDP` 注入登录态)
- 截图目录:`design/screenshots/<role>/tab-*.png` + `manifest.json`
- 涵盖角色:admin / customer / repairer / second_receiver / store_manager / city_manager / promotion_manager / tech_support / finance
- 状态:9/9 角色 OK,所有 tab 渲染正常,数据来自线上 demo 种子
- 限制:H5 布局与小程序不同,只能作为"功能已实现"的视觉证据,不能 1:1 替代小程序对位

**Focused Region Comparison Evidence**

- H5 实现截图已就位 — 关键视图(`customer/home`、`repairer/earnings`)已完成截图
- 小程序对位 — 仍需微信开发者工具登录后逐页面截图

**Findings**

- [P0] 小程序对位视觉验证仍受限于微信开发者工具扫码登录
  Location: customer home and role workbenches
  Impact: 小程序端的 spacing / 文本截行 / 图标渲染 / 胶囊避让仍无法在模拟器确认
  Fix: 打开微信开发者工具扫码登录 → 手动截图 30 个页面 → 归档到 `design/miniprogram-screens/`
- [P1] H5 实现可作为辅助证据 — 9 角色 57 截图已落盘

**Implementation Checklist**

- [x] H5 实现批量截图(9 角色,57 张)
- [ ] 微信开发者工具登录,补 30 个小程序页面截图
- [ ] 对照 `design/reference-option-1.png` 与小程序首页截图
- [ ] 修复任何 P0/P1/P2 不匹配
- [ ] 复检后更新本 QA 报告

**Follow-up Polish**

- Validate long Chinese descriptions and four-item staff tab bars on a narrow Android viewport.

last verified: H5 部分 2026-08-09;小程序部分待扫码登录后补全
