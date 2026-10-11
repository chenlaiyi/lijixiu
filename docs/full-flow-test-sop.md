# 立即修 · 全流程测试 SOP

> 用法:每行是一条**可执行链路**,箭头读作「然后」。方括号 `[按钮]` = 界面上的原文案。
> 角色顺序已按「数据依赖」排好,**从上往下跑就是一条完整业务**。
> 对应源码:小程序 `miniprogram/pages/*` · H5 `h5/` · 后台 `admin-web/` · 后端 `app/`。

- 版本:v1(2026-10-07)
- 建议耗时:单轮全流程 ≈ 90 分钟(不含家政与保修支线)
- 自动化对照:`scripts/test_platform_flows.py`(6 套件)/ `scripts/review_audit.js`(13 项)

---

## 0. 开测前准备(5 步)

```
1 起后端   → uvicorn app.main:app --reload --port 8000
2 开关.env → PAYMENT_ALLOW_MOCK=true · ALLOW_SMS_DEBUG_ENDPOINT=true · SMS_DEBUG_CODE=246810 · WECHAT_WITHDRAW_AUTO_TRANSFER=false
3 造数据   → python scripts/seed_demo_data.py http://127.0.0.1:8000
4 起前端   → http://localhost:8000/h5/  ·  http://localhost:8000/admin/  ·  微信开发者工具打开 miniprogram/
5 健康检查 → GET /health  ·  GET /metrics  ·  GET /docs
```

> `PAYMENT_ALLOW_MOCK=false` 时支付页会直接报「微信支付暂不可用」——本地测支付必须改 true。
> Admin 后台首屏要粘贴**平台管理员 token**,`/admin/` 的 basic auth 只管静态资源。

### 账号与入口对照

| 角色 | 手机号 | 登录后落地页 | 一句话职责 |
|---|---|---|---|
| 平台总管理 | 18800000000 | `admin/dashboard` | 建店 / 建人 / 兜底受理 / 计薪 / 提现审核 / 对账 |
| 客户 | 18800000001 | `customer/home` | 报修 / 支付 / 保修 / 家政 |
| 师傅 | 18800000002 | `repairer/jobs` | 接单 / 服务 / 服务单 / 提现 |
| 二接师傅 | 18800000003 | `second/dashboard` | 兜底接单 |
| 店长 | 18800000004 | `store/dashboard` | 受理 / 派单 / 确认服务单 / 计薪 / 工资单 |
| 城市经理 | 18800000005 | `city/dashboard` | 只读监控区域门店与工单 |
| 推广经理 | 18800000006 | `promotion/dashboard` | 只读客户与佣金;代下单 |
| 服务保障(客服) | 18800000007 | `support/dashboard` | 只读售后工单与家政队列 |
| 财务 | 18800000008 | `finance/dashboard` | 只读资金三表 + 运行对账 |
| 审核体验号 | 18800000999 | `repairer/earnings` | 微信提审路径(体验余额 100 元) |

小程序登录页底部有 **9 个「演示角色快速登录」磁贴**(客户/师傅/兜底/店长/城市/推广/保障/财务/平台),点一下即登录,不用短信。
H5 同一套 token 可切角色工作台;Admin 用 `/admin/`。

### 主播状态机(所有验收都对着它)

```
created → store_pending → store_accepted → dispatched → repairer_accepted
        → servicing → bill_submitted → wait_payment → paid
        → paid_pending_review → store_reviewed → completed → [refunding → refunded]
```

---

## 1. 主干一图流

```
新增门店开始
  建区域 → 建门店 → 启用门店 → 分配服务区 → 建标准地址 → 门店就绪
→ 建师傅档案 → 绑门店 → 客户下单 → 店长受理 → 指派师傅
→ 师傅接单 → 开始服务 → 提交服务单 → 店长确认服务单 → 客户支付
→ 店长计薪审核 → 分润落账 → 财务对账 → 师傅/店长提现 → 平台通过 → 完结 + 出保修凭证
```

---

## 2. 逐角色流程

### R0 平台总管理 `18800000000` · 起点

```
[新增门店开始] —— 走 Admin 后台 http://localhost:8000/admin/(粘管理员 token)
  区域 → [新增区域] → 填 name / level / 城市经理ID → 保存
  门店 → [新增门店] → 填 名称 / 区域ID / 负责人ID / 城市经理ID / 默认师傅ID → 保存
       → 列表 [启用] → 门店 enabled=true
  区域 → 服务区筛选(区/街道) → 勾选 → [批量分配] → dry_run 预览弹窗 → 确认执行
       → 分配日志出现 operator = 管理员
  门店 → [新增标准地址](或 API) → 小区/栋/单元/室 → 得 ADDR-xxxxxx
    ★ 验收:未挂标准地址的门店,客户下单会被拒(400 请选择地址库中的标准上门地址)

小程序 · pages/admin/dashboard/dashboard(平台工作台)
  登录 → 平台工作台 → 快捷导航[工单 n][提现 n][门店 n][告警 n]
  待受理单 → [受理工单] → 选师傅 → [指派师傅]        (或 [我来服务] 自己接)
  师傅提交服务单 → [确认服务单]
  客户已支付 → 计薪方式[按单/月薪] → 快捷比例[50%|60%|70%] 或填[师傅工资]
            → [记录工资]/[完成审核] → 订单 store_reviewed → completed
  提现区 → pending 行 [通过] → 提现 status=approved
  [对账] → 弹「异常 n 条」 → 告警区人工关注
  旁支:[代下单] / [看素材] / [退出]
```

**验收**:`store_pending → store_accepted → dispatched → … → completed` 全链无 4xx;`GET /metrics` 的 `orders_completed` 与页面一致。

---

### R1 城市经理 `18800000005` · 城市工作台(只读)

```
登录 → 城市工作台(门店和工单) → 看 4 卡[门店][待跟进][服务单][支付]
     → 门店区核对 店长#ID / 门店#ID 与自己名下的店一致
     → 工单区核对下一步文案:受理工单 → 安排上门人员 → 跟进接单 → 服务中 → 确认服务单 → 客户支付 → 确认计薪 → 已审核
     → [代下单](本页唯一写操作) → 跳 staff/proxy-order
```

**验收**:门店数 = `stores.city_manager_id == 自己` 的数量;`金额 ¥` 随订单完成增长;**本页不应出现任何受理/派单/审核按钮**。

---

### R2 店长 `18800000004` · 门店工作台(核心枢纽)

```
登录 → 门店工作台(店名)
  待受理单 → [受理工单] → 选师傅 → [指派师傅] → 已派单
  或 → [我来服务] → 自己接单 → 跳 repairer/detail
  师傅完成 → [确认服务单](bill_submitted) → 客户可支付
  客户支付 → 计薪方式[按单|月薪] → 填[本单工资] → [完成审核]
  旁支:[代下单] → proxy-order  ·  [看素材] → repairer/detail  ·  [服务单] → repairer/detail

月薪线: [工资] → 月薪工资单 → 选月份 → 看 本月记录工作量 → 填[月薪] → [生成工资单]
        → 工资周期 → [发放工资] → 已发放
```

**验收**:`确认服务单`(bill_submitted)与`完成审核`(paid/paid_pending_review)不同屏;月薪提交时 `technician_wage_amount` 必须为 0,否则报 `Monthly employees cannot receive a per-order wage`;WageRecord 状态按单 `pending_settlement → paid`、月薪 `approved`。

---

### R3 师傅 `18800000002` · 工单/服务单/收益

```
登录 → 工单 → 待接工单 → 订单卡 → [接单]
     → 跳 repairer/detail → [开始服务](servicing)
     → 服务明细:[新增明细]/(≥2 项时)[删除] → 填数量/单价
     → 保修期(默认 30 天) + 客户确认[现场口头/电话/微信/其他]
     → [保存草稿] 或 [提交服务单] → bill_submitted
     → 等门店确认 → 等客户支付
收益线: 收益 → 可提现余额/冻结/累计 → 填金额 或 [全部] → [申请提现]
        → 弹「申请编号 N,财务审核中」 → 提现记录出现 pending
旁支:[代下单]
```

**验收**:服务单校验(项目名称/数量>0/单价>0/保修天数为非负数);提现 ≤ 可用余额;体验号单次 ≤ ¥5。

---

### R4 二接师傅 `18800000003` · 兜底工单

```
登录 → 兜底工单 → 兜底卡(store_pending,来自 default_second_receiver_id 指向的门店)
     → [兜底接单]  ← 一条龙:store-accept → assign(自己) → transition(repairer_accepted)
     → 跳 detail → [开始服务] → [提交服务单] → 回落店长确认
或 → [接单](assigned/dispatched)  ·  [看详情](恒有)  ·  [工单] → repairer/jobs
```

**验收**:门店 `default_second_receiver_id` 未配置时,兜底列表为空;二接必须已有 `repairers` 档案,否则页头显示「绑定师傅档案」。

---

### R5 推广经理 `18800000006` · 推广工作台(只读)

```
登录 → 推广工作台(客户和佣金) → 看 4 卡[客户][待结算][累计¥][可提现¥]
     → 客户区核对 客户#ID / 手机号 / 下一步 等待首单
     → 佣金区核对 订单#ID → 待结算 → 已结算 → 已打款
     → [代下单](本页唯一写操作)
```

**验收**:客户数 = `users.promotion_manager_id == 自己`;订单完成后佣金由 `待结算` 转 `已结算` 且余额同步;**提现动作不在本页**。

---

### R6 员工代客(店长/城市/推广/平台/师傅均可进) · 代下单

```
任意角色 → 顶部[代下单] → staff/proxy-order
  ① 类型 picker(9 类)  ② 客户手机号(11 位,自动查/建客户)
  ③ 标准地址 picker(必选平台已开通地址)
  ④ 描述 或 [语音][照片][视频] 素材(二选一)
  ⑤ [提交订单] → proxy-result
proxy-result: 生成二维码(按订单状态自动 claim / payment)
  → [转发二维码入口] 发给客户/家属/代付人   ·  [刷新订单状态]  ·  [返回工作台]
```

**验收**:订单带 `is_proxy_order=true / proxy_creator_id / proxy_reason`;手机号不在库时自动建客户;无标准地址选不了、提交报「请选择平台已开通的标准地址」。

---

### R7 客户 `18800000001` · 报修→支付→保修

```
登录 → 首页 → 选分类(家电维修/水路管道/电路照明/门窗维修/家具安装/家电安装/管道疏通/清洁保养/其他)
     → [预约上门维修] → 下单页
     → 描述 或 加素材(语音/照片/视频) 二选一
     → 选[标准上门地址](必选,否则报「请选择平台已开通的标准地址」)
     → [提交] → 跳订单列表(created / store_pending)
[等门店受理 + 派单 + 师傅做完单]
订单列表 → 状态「待确认」→ [确认并支付] → 支付页
支付页 → 核对服务单明细/合计/保修期 → [微信支付] → wx.requestPayment
       → 支付成功 → 回订单列表(paid)
成单后 → 保修凭证页 → 条目 → [提交保修申请] → 选问题类型 + 描述(≥5 字) → 提交 → 工单生成
旁支:地址簿[新增]/[设为默认]  ·  家政月嫂保姆  ·  我的→设置/个人信息
```

**验收**:`canPay` 只在 `bill_submitted / wait_payment` 且 `max(price, bill.amount) > paid_amount` 时出现;支付页先查 `/payment/wechat/config-status`,未 ready 直接报「微信支付暂不可用」;第三方代付显示「不会改变订单和保修归属」。

---

### R8 家政支线(客户 + 店长 + 客服)

```
客户 → 首页[月嫂服务]/[保姆服务] → 列表 → 人员档案 → [申请匹配] → 发布需求
     → 填 联系人/电话/地址/开始日期(必填) + 预算/周期/服务方式 → [提交需求]
店长 → 家政服务 → [新增人员](年月/经验/价格/三项核验) → 需求匹配 → 定候选
     → 建合同(服务费/代收/分期计划) → 查看分期
客户/代付人 → 分期支付(逐期 mock/微信) → 回调
店长 → 合同 [开始] → [完成] → 分润按总额落账
客服 → 服务保障 → 家政服务跟踪 → 核对状态(待联系/匹配中/已签约/已完成/投诉)
```

**验收**:分期逐期支付后合同才能 start;完成后 `total_distributed` = 服务费 + 代收。

---

### R9 服务保障/客服 `18800000007` · 只读看板

```
登录 → 服务保障(资料核验、投诉和售后跟进)
     → 3 卡[待处理工单(排除已关闭/已取消)][家政需求][投诉服务]
     → 售后工单区核对 #ID/标题/状态
     → 家政服务跟踪区核对状态
     → 下拉刷新  ·  [退出]
```

**验收**:客户提交的保修 ticket 出现在列表且状态 `待处理`;本页无核验/派单/关闭/回复按钮——处置动作走接口或后台。

---

### R10 财务 `18800000008` · 资金核对

```
登录 → 财务工作台(支付、退款、工资和对账)
     → 3 卡[支付到账¥][成功退款¥][已发工资¥]
     → 最近支付区核对 支付单#ID / 订单#ID / 金额 / 付款人#ID / 状态
     → [运行对账] → 弹「对账完成 正常 n,异常 m」
     → [退出登录]
```

**验收**:三组数分别与 `payment(status=paid/partially_refunded)`、`refund(status=success)`、`wage(status=paid)` 求和一致。

---

### R11 代理/扫码人(扫码进入) · 认领或付款

```
微信扫码 → proxy/access?token=xxx
  purpose=claim   → [确认是我的订单] → 未登录先去登录 → 认领成功 → [查看订单进度]
  purpose=payment → [核对明细并付款] → 跳支付页(代付提示) → 微信支付
  两者都可 [转发给家人]
```

**验收**:二维码时效——`proxy-result` 刷新后旧 token 失效;付款人 ≠ 客户时订单归属与保修不变。

---

## 3. 推荐执行顺序(照着跑)

```
R0 建店建人 → R2 店长看板已就绪 → R7 客户下单 → R2 受理派单 → R3 师傅接单服务
→ R2 确认服务单 → R7 客户端支付 → R2/R0 计薪审核 → R5 推广看佣金 → R10 财务对账
→ R3 提现 → R0 通过 → R9 客服保修 → R4 二接兜底 → R6+R11 代客二维码
→ R1 城市复核 → R8 家政支线
```

---

## 4. 验收断言清单

| # | 检查点 | 期望 |
|---|---|---|
| 1 | 未挂标准地址下单 | 400「请选择地址库中的标准上门地址」 |
| 2 | 重复建同小区/栋/单元/室 | 400 |
| 3 | 订单服务区路由 | `store_id` / `address_code_snapshot` / `channel_manager_id_snapshot` 快照正确 |
| 4 | 状态机非法跳转 | 400 `Illegal status transition` |
| 5 | 月薪 + 非 0 工资 | 400 `Monthly employees cannot receive a per-order wage` |
| 6 | 无 repairer 的订单计薪 | 400 `Order has no repairer for wage review` |
| 7 | 分润合计 = 订单实付 | `total_distributed` ≈ 支付额;含 `platform_retained` / `channel_manager_commission` |
| 8 | 保修凭证 | 成单后生成;过期后从「保修凭证」页消失,`include_expired=true` 仍可查 |
| 9 | 未登录访问敏感接口 | 401 |
| 10 | 客户访问管理接口/他人数据 | 403 |
| 11 | 客户自改 business_role | 403 |
| 12 | `PAYMENT_ALLOW_MOCK=false` 走 mock | 400「模拟支付已关闭」 |
| 13 | 审核号登录 | 自动发 100 元体验余额 + 历史提现置 rejected |
| 14 | 非白名单手机号 wechat-login | 403 |
| 15 | `/metrics` 口径 | 与页面订单数一致(枚举大小写已修) |

---

## 5. 异常与安全回归(必跑)

```
未登录扫 30 个敏感接口 → 全 401
带 token 正常流程(5 类角色)→ 全 200
越权:客户 → 管理接口 / 他人订单 / 他人钱包 → 全 403
提权:客户 PATCH 自己 business_role=platform_admin → 403
短信闸门:ALLOW_SMS_DEBUG_ENDPOINT=false → /auth/sms/request 503 且无 debug_code
代付:payer ≠ customer → 订单与保修归属不变
二维码失效:刷新后旧 token GET /business/access/{token} → 失败
```

---

## 6. 结果记录表

| # | 角色 | 链路 | 结果 | 备注 |
|---|---|---|---|---|
| 1 | 平台 | 新增区域→门店→启用→分配服务区→标准地址 | ☐ | |
| 2 | 平台 | 师傅档案 → 绑门店 → 默认二接 | ☐ | |
| 3 | 客户 | 下单 → 提交 → 订单列表可见 | ☐ | |
| 4 | 店长 | 受理 → 指派 → 确认服务单 | ☐ | |
| 5 | 师傅 | 接单 → 开始服务 → 提交服务单 | ☐ | |
| 6 | 客户 | 确认并支付 → paid | ☐ | |
| 7 | 店长/平台 | 计薪审核 → store_reviewed → completed | ☐ | |
| 8 | 推广 | 佣金 待结算→已结算 | ☐ | |
| 9 | 财务 | 三表 + 对账 正常/异常 | ☐ | |
| 10 | 师傅 | 提现申请 → 平台通过 | ☐ | |
| 11 | 客服 | 保修 ticket 出现 | ☐ | |
| 12 | 二接 | 兜底接单 一条龙 | ☐ | |
| 13 | 员工/代理 | 代下单 → 二维码 → 扫码认领/付款 | ☐ | |
| 14 | 平台 | 家政 需求→候选→合同→分期→完成 | ☐ | |
| 15 | 城市 | 门店/工单 数与金额正确 | ☐ | |

---

## 7. 自动化对照

```powershell
python scripts/test_platform_flows.py        # 6 套件:鉴权/审核号/服务区路由/报修支付保修/计薪/家政
python scripts/run_platform_flow_tests.ps1   # 同上,带环境包装
node scripts/review_audit.js                 # 提审前 13 项核对
node scripts/security_audit.js               # 安全头基线
python scripts/validate_env.py --strict      # 部署前 env 校验
```

> 手工 SOP 跑完一轮后,再用上面脚本回归一次;两边结果不一致时以脚本输出为准(手工易漏状态前置条件)。

---

## 8. 测试坑位(容易测错的地方)

```
① 服务单确认有 4 个入口:客户订单列表 / 客户订单详情 / 客户支付页 / 平台工作台
   ★ 客户「支付页」进页会自动 service-bill/confirm
   → 测「店长确认服务单」时要抢在客户端之前,否则单子已跳到 wait_payment

② 订单不能被跨状态找按钮
   确认服务单 = bill_submitted 专属 · 完成审核 = paid/paid_pending_review 专属 → 永不同屏

③ 只读页面别安排写操作
   城市经理 / 推广经理 / 客服 / 财务 = 看板;唯一例外:财务[运行对账]、其余三页[代下单]

④ 兜底接单的前置
   门店必须配 default_second_receiver_id,二接必须已有 repairers 档案,否则兜底列表恒空

⑤ 店长两个按钮的隐式行为
   [指派师傅] 对 store_pending 会先隐式 store-accept
   [我来服务] 会隐式给自己建 repairers 档案(skills 门店综合服务)

⑥ 支付前置
   /payment/wechat/config-status 不 ready → 支付页直接报「微信支付暂不可用」
   本地必须 PAYMENT_ALLOW_MOCK=true 才能走 mock 通道

⑦ 二维码时效
   proxy-result [刷新订单状态] 会让旧 token 失效,已发出的二维码扫不开

⑧ 计薪字段红线
   technician_wage_amount 与 wage_mode 必须匹配:月薪必须传 0
   订单没有 repairer_id / assigned_repairer_id 时计薪直接 400

⑨ 保修
   凭证过期后从客户「保修凭证」页消失;未关闭 ticket 时按钮变「售后处理中」不可重复提交
```
