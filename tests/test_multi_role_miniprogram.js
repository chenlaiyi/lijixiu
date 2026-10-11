/**
 * 多角色工具回归测试(2026-10-07)
 *
 * 运行:node tests/test_multi_role_miniprogram.js
 *
 * 覆盖「我的」页依赖的取值逻辑:
 *  - 多角色账号读全部角色 + 当前身份
 *  - 老缓存(只有 business_role)仍能正常工作
 *  - 当前身份必须在拥有的角色里,否则退回工作台角色
 *  - 切换入口只在 2 个以上角色时出现
 */
const assert = require("assert");
const path = require("path");

const role = require(path.join(__dirname, "..", "miniprogram", "utils", "role.js"));

let passed = 0;
let failed = 0;

function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`  OK   ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`  FAIL ${name} — ${error.message}`);
  }
}

// 目标场景:18060936373 同时是 店长 + 师傅 + 业务
const multiUser = {
  id: 42,
  phone: "18060936373",
  business_roles: ["store_manager", "repairer", "promotion_manager"],
  active_business_role: "store_manager",
  business_role: "store_manager",
  role: "admin",
};

check("多角色:读出全部角色", () => {
  assert.deepStrictEqual(role.getBusinessRoles(multiUser), [
    "store_manager",
    "repairer",
    "promotion_manager",
  ]);
});

check("多角色:当前身份取 active_business_role", () => {
  assert.strictEqual(role.getBusinessRole(multiUser), "store_manager");
});

check("多角色:切换后当前身份跟着变", () => {
  const switched = { ...multiUser, active_business_role: "promotion_manager" };
  assert.strictEqual(role.getBusinessRole(switched), "promotion_manager");
});

check("多角色:入口页按当前身份", () => {
  assert.strictEqual(role.getEntryPath(multiUser), "/pages/store/dashboard/dashboard");
  assert.strictEqual(
    role.getEntryPath({ ...multiUser, active_business_role: "repairer" }),
    "/pages/repairer/jobs/jobs"
  );
  assert.strictEqual(
    role.getEntryPathForRole("promotion_manager"),
    "/pages/promotion/dashboard/dashboard"
  );
});

check("多角色:并集判断(拥有即算)", () => {
  assert.strictEqual(role.hasBusinessRole(multiUser, "repairer"), true);
  assert.strictEqual(role.hasBusinessRole(multiUser, "finance"), false);
  assert.strictEqual(role.hasAnyBusinessRole(multiUser, ["finance", "promotion_manager"]), true);
  assert.strictEqual(role.hasAnyBusinessRole(multiUser, ["finance", "customer"]), false);
});

check("多角色:可切换 + 标签串", () => {
  assert.strictEqual(role.canSwitchRole(multiUser), true);
  assert.strictEqual(role.roleText(multiUser), "店长 · 师傅 · 业务");
});

check("多角色:角色选项带 active 标记", () => {
  const options = role.roleOptions(multiUser);
  assert.strictEqual(options.length, 3);
  assert.strictEqual(options[0].value, "store_manager");
  assert.strictEqual(options[0].active, true);
  assert.strictEqual(options[1].active, false);
});

check("老缓存:只有 business_role 也能正确取值", () => {
  const legacy = { id: 7, phone: "19933330005", business_role: "store_manager", role: "admin" };
  assert.deepStrictEqual(role.getBusinessRoles(legacy), ["store_manager"]);
  assert.strictEqual(role.getBusinessRole(legacy), "store_manager");
  assert.strictEqual(role.canSwitchRole(legacy), false);
});

check("老缓存:当前身份不在拥有列表时退回工作台角色", () => {
  const broken = {
    business_roles: ["customer", "repairer"],
    active_business_role: "platform_admin",
  };
  assert.strictEqual(role.getBusinessRole(broken), "repairer");
});

check("纯客户账号:入口是用户首页,不能切换", () => {
  const customer = { business_role: "customer", role: "customer" };
  assert.strictEqual(role.getBusinessRole(customer), "customer");
  assert.strictEqual(role.canSwitchRole(customer), false);
  assert.strictEqual(role.getEntryPath(customer), "/pages/customer/home/home");
  assert.strictEqual(role.roleText(customer), "客户");
});

check("空账号不崩", () => {
  assert.deepStrictEqual(role.getBusinessRoles({}), ["customer"]);
  assert.strictEqual(role.getBusinessRole(undefined), "customer");
  assert.strictEqual(role.getEntryPath(null), "/pages/customer/home/home");
});

check("角色工作台名", () => {
  assert.strictEqual(role.workbenchLabel("store_manager"), "门店工作台");
  assert.strictEqual(role.workbenchLabel("promotion_manager"), "推广工作台");
  assert.strictEqual(role.workbenchLabel("unknown"), "工作台");
});

console.log("---");
console.log(`${passed}/${passed + failed} passed`);
process.exit(failed === 0 ? 0 : 1);
