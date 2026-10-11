# 数据重置与区域架构(2026-10-07)

## 一、系统里有两套"区域",不要混

| 概念 | 表 | 作用 | 你看到的入口 |
|---|---|---|---|
| **组织架构** | `regions` + `stores` | 城市 → 区 → 门店级区域 → 门店,用来定归属和负责人 | 后台「区域」「门店」 |
| **服务区域地址库** | `service_areas` | 省/市/区/街道/社区 的**字典表**,用于地址归属与服务片区路由 | 后台「区域」页下方的「厦门地址库」 |

两者**完全独立**:`service_areas` 没有 `parent_id`,靠文本字段表达层级,不参与组织架构。

---

## 二、组织架构的三层结构

```
regions(id, name, level, parent_id, manager_id)
        │                │       └── 自引用 → 树形
        │                └── 只能是 1 / 2 / 3(API 校验 ge=1 le=3)
        └── stores.region_id 必填 → 每个门店必须挂在一个区域上

stores(id, name, region_id, manager_id, city_manager_id,
       default_second_receiver_id, status, enabled, remark)
        ├── manager_id 必填(店长)
        ├── city_manager_id 可选(城市经理)
        └── status: draft | active | suspended
```

### 建成后的样子(当前生产)

```
厦门市                level 1   parent —     ← id=1
 └ 海沧区             level 2   parent 1     ← id=2
    └ 立即修海沧未来海岸店  level 3   parent 2     ← id=3
       └ 门店:立即修海沧未来海岸店  region_id=3  manager_id=7  active
```

---

## 三、空白系统怎么从零建(以后照着做)

### 第 1 步 · 建一级(城市)

后台「区域」→ 填:

```
区域名称:厦门市
层级:    一级
上级ID:  留空
负责人ID:可留空(城市经理 id=8)
```

### 第 2 步 · 建二级(区)

```
区域名称:海沧区
层级:    二级
上级ID:  1     ← 第 1 步拿到的 ID
负责人ID:8
```

### 第 3 步 · 建三级(门店级区域)

```
区域名称:立即修海沧未来海岸店
层级:    三级
上级ID:  2     ← 第 2 步拿到的 ID
负责人ID:7
```

> **为什么要有"三级区域"和"门店"两样东西?**
> 三级区域是**行政归属**(店开在哪个片区),门店是**经营主体**(谁在管、状态如何)。
> 惯例是两者**同名**。

### 第 4 步 · 建门店

后台「门店」→ 填:

```
门店名称:立即修海沧未来海岸店
区域:    立即修海沧未来海岸店(三级区域 id=3)
店长:    演示门店店长(id=7)     ← 必填
城市经理:演示城市经理(id=8)     ← 可选
```

⚠️ **新建门店默认是 `draft` + `enabled=false`,不会生效。**
必须再点「启用」/改状态为 `active` + `enabled=true`。
否则门店相关接口会返回 404(代码判断 `not store.enabled or store.status != ACTIVE`)。

### 第 5 步 · 需要更多区/门店

重复第 2~4 步。同城市下可以挂多个区,每个区下可以挂多个门店级区域。

---

## 四、本次数据重置(2026-10-07)

用户确认"之前的测试数据都不重要",因此执行了彻底重置。

### 清空的内容

**30 张业务表,共 1163 行:**

| 表 | 行数 | 表 | 行数 |
|---|---|---|---|
| order_logs | 313 | reconciliation_logs | 244 |
| profit_shares | 157 | ledgers | 106 |
| idempotency_keys | 82 | alert_events | 45 |
| orders | 39 | service_bills | 35 |
| withdrawals | 29 | pay_orders | 28 |
| wallets | 13 | service_area_assignment_logs / assignments | 10 + 10 |
| package_schedules | 8 | warranty_certificates / wage_records / phone_verification_codes | 5 各 |
| store_staff | 4 | repairers / domestic_demands | 3 各 |
| stores / customer_packages / domestic_candidates / domestic_workers / service_packages 相关 | 2 各 | 其余 | 1 各 |

**18 个测试用户**(保留 10 个,见下):

```
1  H5Remote      13900000998      10 测试用户     13800138000
2  H5Remote      13900000997      14 微信用户     18924071446
16-23,26-28 手机号用户(9 个)        24 链路核对     13000000001
                                 25 用户1234     13700001234
```

### 保留的内容

| 项 | 数量 | 为什么保留 |
|---|---|---|
| 演示账号(白名单) | 9 个 | 小程序登录依赖 `_DEMO_ACCOUNTS` 白名单 |
| 审核账号 `审核体验账号` | 1 个 | 提审说明依赖;登录仍会恢复 100.00 余额 |
| `service_areas` 厦门地址库 | **551 条** | **真实数据**(6 个区:同安144/翔安128/思明98/集美72/湖里59/海沧50) |
| `service_packages` | 2 | 服务套餐配置 |
| `alembic_version` | 1 | 迁移版本,不能删 |

保留的 10 个用户:

```
id=3  18800000000  演示管理员        platform_admin
id=4  18800000001  演示客户          customer
id=5  18800000002  演示师傅张工       repairer
id=6  18800000003  演示二接师傅李工    second_receiver
id=7  18800000004  演示门店店长       store_manager
id=8  18800000005  演示城市经理       city_manager
id=9  18800000006  演示推广经理       promotion_manager
id=12 18800000007  演示服务保障       tech_support
id=13 18800000008  演示财务          finance
id=15 18800000999  审核体验账号       repairer
```

### 执行方式与安全措施

1. **副本试跑**:先在 `/tmp` 数据库副本上跑通,发现并修正了删除顺序(第一版有 7 张表撞外键)
2. **备份**:`shared/xiulijiu.db.bak-purge-20261007114344`
3. **停服务**再改库,避免写入竞争
4. **关外键清空** + 事后 `PRAGMA foreign_key_check` 验证 → **0 处悬空引用**
5. 重启服务 + `/health` 冒烟通过

### 副作用(已知)

- **提审演示数据没了**:订单、流水、提现记录全清空。
  - 审核账号余额仍为 **100.00**(初始余额),但**提现记录是空的**
  - 收益页「申请提现 → 看到记录」这条链路**依然可用**(提交后就有记录)
  - 参考 [wechat-review-guide.md](wechat-review-guide.md) 里"审核账户只用演示数据"的措辞仍然成立
- 小程序端的演示数据(演示客户/师傅的订单)也没了,小程序页面会是空列表状态

---

## 五、踩过的坑(重要)

### 1. 系统 `python3` 连不上数据库

```
sqlite3.DatabaseError: malformed database schema
(uq_store_addresses_canonical_key) - near "WHERE": syntax error
```

**不是数据库坏了。** 系统 `python3` 是 3.6.8,自带 SQLite 太旧,解析不了
**部分索引**(partial index):

```sql
CREATE UNIQUE INDEX uq_store_addresses_canonical_key
  ON store_addresses(canonical_key) WHERE canonical_key IS NOT NULL
```

服务用的是 `/www/wwwroot/xiulijiu_api/venv/bin/python`(3.11 + SQLite 3.53.1),正常。

> **以后直接查库必须用 venv 的 python**,不要用系统 `python3`。

### 2. 删数据不能按"表名顺序"猜

全部外键都是 `NO ACTION`(无级联删除)。一开始按直觉排的顺序撞了 7 张表:
`warranty_certificates → service_bills`、`support_tickets → orders`、
`settlement_items → orders`、`package_schedules → orders`、
`customer_packages → stores`、`service_area_assignments → repairers/stores`、
`users.promotion_manager_id → users`(自引用)。

结论:**先关外键清空,再用 `foreign_key_check` 证明干净**,比逐个试顺序可靠。

### 3. 门店建完是 draft,不生效

`POST /api/v1/stores` 固定写 `status=draft, enabled=False`。
必须再 `PATCH /api/v1/stores/{id}` 传 `{"status":"active","enabled":true}`。
