# 一个账号多角色(2026-10-07)

## 1. 需求与场景

一个手机号可能同时是 **店长 + 师傅 + 业务**。例:18060936373。

改造前:权限只认 `users.business_role` 这一个字符串,多角色只能三选一,
后台想给一个号叠加角色就得覆盖掉它原来的身份。

改造后:

* 后台可以给一个账号**多选**关联角色(如 店长 / 师傅 / 业务 全勾);
* 小程序「我的」页把「客户」这个固定标签换成**真实角色标签**,
  并在拥有 2 个以上角色时提供**切换当前身份**入口;
* 切换是**全局身份**:首页、底部导航、工作台入口、可见数据都按当前身份走;
* 接口鉴权按**角色并集**:拥有任一所需角色即放行,不会因为"当前选中了师傅"
  就丢掉店长的权限。

## 2. 数据模型

| 字段 | 含义 |
| --- | --- |
| `users.business_roles` (JSON 数组) | 该账号**拥有**的全部业务角色 —— 权限的唯一真相 |
| `users.active_business_role` | 用户在小程序里**当前选中**的身份(必须是上者之一) |
| `users.business_role` (旧列) | 兼容字段,始终等于 `business_roles[0]` |
| `users.role` (旧列) | 兼容的粗粒度身份,由角色集合推导(见下) |
| `users.is_promotion_manager` | 兼容开关,等于"是否含 `promotion_manager`" |
| `user_role_grants` (新表) | 角色变更审计:谁、什么时候、给谁加了/收回了哪个角色 |

业务角色取值(`BusinessRole`):
`customer` / `repairer` / `store_manager` / `second_receiver` /
`promotion_manager` / `city_manager` / `tech_support` / `finance` / `platform_admin`。

`users.role` 的推导规则(`app/models/user.py: required_user_role`),
按 `ALL_BUSINESS_ROLES` 的声明顺序取第一个命中的:

| 拥有的角色里最先出现的 | `users.role` |
| --- | --- |
| `platform_admin` / `store_manager` / `city_manager` / `tech_support` / `finance` | `admin` |
| `repairer` / `second_receiver` | `repairer` |
| `promotion_manager` / `customer` | `customer` |

> `users.role` **不参与鉴权**(历史遗留,仅登录 token payload 与旧列表用),
> 所以"店长+师傅"推到 `admin` 不会降低权限,也不会误给客户权限。

## 3. 鉴权口径(并集)

判断逻辑集中在 `app/services/role.py`,`app/core/auth.py` 只做 HTTP 包装:

```python
role_service.resolve_roles(user)   # -> ["store_manager", "repairer", "promotion_manager"]
role_service.active_role(user)     # -> "store_manager"
role_service.has_role(user, "finance", "repairer")  # 任一命中即 True
role_service.is_staff(user) / is_admin(user)
```

* `resolve_roles` 有兜底:老数据没有 `business_roles` 时退回 `business_role`,
  再退回 `role`,最后退回 `customer`。所以升级过程中不会出现"谁都进不去"。
* `active_role` 只在**展示与入口**上生效(决定进哪个工作台、tabbar 用哪套),
  **不参与**放行判断。
* `require_admin` / `require_staff` / `require_roles(...)` 全部改成并集判断。

## 4. 接口

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/users/roles/options` | 登录即可 | 角色字典(`value/label/staff/workbench`),前端不要硬编码 |
| `GET` | `/api/v1/users/{id}/roles` | 本人或内部角色 | 拥有的角色、当前身份、标签、`can_switch`、变更历史(仅内部角色可见) |
| `PATCH` | `/api/v1/users/{id}/roles` | **仅平台管理员** | 整体替换角色集合 + 写审计;可同时指定 `active_business_role` |
| `POST` | `/api/v1/users/{id}/switch-active-role` | 本人或内部角色 | 切换当前身份,只能选自己**拥有**的角色,否则 403 |
| `PATCH` | `/api/v1/users/{id}` | 本人或内部角色 | 旧接口。`business_role` / `is_promotion_manager` 改为**只增不减** |

`/api/v1/auth/me`、登录响应(4 个登录端点)在原有 `business_role` 之外新增:

```json
{
  "business_roles": ["store_manager", "repairer", "promotion_manager"],
  "active_business_role": "store_manager"
}
```

### 防提权 / 防自锁

* 客户 `PATCH` 自己的 `business_roles` → 403;客户 `PATCH` 别人的角色 → 403;
* 非平台管理员(含店长)`PATCH /users/{id}/roles` → 403;
* 切换到自己没有的角色 → 403;
* 平台管理员不能把自己最后一个 `platform_admin` 摘掉 → 400;
* 空 `business_roles` → 422。

## 5. 小程序

* `miniprogram/utils/role.js` 是唯一取值来源:
  `getBusinessRoles` / `getBusinessRole`(当前身份)/ `hasBusinessRole`
  / `canSwitchRole` / `roleOptions` / `roleText` / `getEntryPathForRole`;
  老缓存(只有 `business_role`)与 `null` 入参都能安全处理。
* 「我的」页(`pages/customer/profile`):
  * 角色标签显示全部角色(`店长 · 师傅 · 业务`);
  * 有 2 个以上角色时出现 **切换身份（N）** 按钮,以及列表里的「切换身份」项;
  * 切换走 `POST /users/{id}/switch-active-role`,成功后写回 `storage.userInfo`,
    再 `redirectTo` 新身份的工作台入口(`role.getEntryPathForRole`)。
* 个人信息页显示全部角色与「当前身份」,也支持在那里切换。
* 自定义 tabbar (`components/role-tabbar`) 与 `app.js` 的 `globalData.role`
  都改为读 `active_business_role`,所以切换后导航条跟着变。
* 钱包入口只对 `repairer` / `second_receiver` 角色显示。

## 6. 管理后台

「用户」视图:

* 列表新增 **业务角色** 列(`店长 / 师傅 / 业务`,`＊` 标记当前身份)与 **当前身份** 列;
* 每行新增 **配置角色** 按钮:勾选多个角色 + 选择当前身份 + 填写变更备注;
* 角色字典来自 `/api/v1/users/roles/options`,后端加角色时后台不需要改代码。

## 7. 迁移与上线

启动时会自动完成(`app/core/database.py: init_db`):

1. `create_all` 建出 `user_role_grants` 等新表;
2. 轻量迁移补列:`users.business_roles`(JSON)、`users.active_business_role`,
   以及历史只存在于 alembic 里的 6 个用户列
   (`agreed_terms_version` / `agreed_privacy_version` / `agreed_at` /
   `deletion_requested_at` / `deletion_scheduled_at` / `last_login_at`)
   —— 生产库历史上从未跑过 alembic,这一步是必需的;
3. **回填**:
   * `active_business_role` ← `business_role`
   * `business_roles` ← `["<business_role>"]`(写成合法 JSON 数组)

回填条件是"空值才写",且只发生在启动时,因此**可反复执行**、不会覆盖后台配好的多角色。
老账号升级后第一次打开小程序仍落在原来的工作台(不会掉回客户)。

容器启动命令里的 `alembic upgrade head` 保持原样(失败也继续启动),真正的兼容由上面的
轻量迁移保证。

### 配置示例账号(店长 + 师傅 + 业务)

```bash
# 本地 / 服务器上,在工程根目录执行(读 .env 的 DATABASE_URL)
python scripts/seed_multi_role_demo.py 18060936373 --dry-run   # 先看会改什么
python scripts/seed_multi_role_demo.py 18060936373             # 建号 + 补齐三个角色
```

* 幂等:再跑一次只会显示"无需变更";
* 默认**只补齐不删除**已有角色,要整体替换加 `--replace`;
* 走的和后台按钮同一条代码路径(`services/role.set_roles`),会写 `user_role_grants`;
* 部署环境也可以直接用后台「用户 → 配置角色」多选,或调
  `PATCH /api/v1/users/{id}/roles`。

登录:该手机号已加入 `_DEMO_ACCOUNTS`(演示身份=店长),可用
`POST /api/v1/auth/wechat-login` 的演示通道登录;登录**只会补齐**店长角色,
不会清掉后台配的师傅/业务。

### 回滚

* 代码回滚到旧版本即可:旧代码只读 `business_role`,而它始终等于
  `business_roles[0]`,不会因为多了新列而报错。
* 新列可保留(不参与旧逻辑);`user_role_grants` 表可保留作为审计。

## 8. 测试

```bash
# 后端
python tests/test_multi_role.py             # 37 项:接口 / 并集鉴权 / 切换 / 越权防护
python tests/test_multi_role_migration.py   # 29 项:老库迁移回填 + 幂等 + 越权边界
python tests/test_auth_admin.py             # 回归
python tests/test_role_boundaries.py        # 回归(并集不能误伤也不能放水)
python tests/test_order_authz.py            # 回归

# 小程序
node tests/test_multi_role_miniprogram.js   # 12 项:角色取值 / 入口 / 老缓存兼容
```

> 在 DSH 沙箱里跑 pytest 类脚本时,`TemporaryDirectory` 可能因沙箱限制失败,
> 需要用可写目录(CI 上不受影响)。`test_multi_role*.py` 已改成用工程内
> `.tmp-test-*` 目录,沙箱内可直接运行。
