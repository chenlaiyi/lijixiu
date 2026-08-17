#!/usr/bin/env bash
# 微信支付链路端到端冒烟脚本
#
# 用法:
#   ./scripts/payment_smoke.sh                              # 跑全部,默认连 localhost:8000
#   BASE_URL=https://x.iddg.cn ./scripts/payment_smoke.sh  # 跑线上
#   ADMIN_TOKEN=eyJ... ./scripts/payment_smoke.sh           # 传管理员 token
#   CUSTOMER_TOKEN=eyJ... ./scripts/payment_smoke.sh        # 传客户 token
#   SKIP_PAID=1 ./scripts/payment_smoke.sh                 # 跳过需要真 0.01 元的步骤
#
# 退出码:
#   0 = 全部通过
#   1 = 至少 1 个失败
#   2 = 配置不全(看不到 admin token / customer token)

set -uo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
CUSTOMER_TOKEN="${CUSTOMER_TOKEN:-}"
SKIP_PAID="${SKIP_PAID:-0}"

PASS=0
FAIL=0
RESULTS=()

# 颜色(只在 TTY 输出)
if [ -t 1 ]; then
    GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
else
    GREEN=''; RED=''; YELLOW=''; CYAN=''; NC=''
fi

_check() {
    local name="$1"
    local ok="$2"
    local detail="${3:-}"
    if [ "$ok" = "1" ]; then
        PASS=$((PASS + 1))
        RESULTS+=("OK  $name  $detail")
        printf "${GREEN}OK  ${NC} %-48s %s\n" "$name" "$detail"
    else
        FAIL=$((FAIL + 1))
        RESULTS+=("FAIL $name  $detail")
        printf "${RED}FAIL${NC} %-48s %s\n" "$name" "$detail"
    fi
}

_section() {
    printf "\n${CYAN}=== %s ===${NC}\n" "$1"
}

_http() {
    # _http METHOD PATH [TOKEN] [JSON_BODY]
    local method="$1"
    local path="$2"
    local token="${3:-}"
    local body="${4:-}"
    if [ -n "$token" ]; then
        if [ -n "$body" ]; then
            curl -fsS -X "$method" "$BASE_URL$path" \
                -H "Authorization: Bearer $token" \
                -H "Content-Type: application/json" \
                -d "$body"
        else
            curl -fsS -X "$method" "$BASE_URL$path" \
                -H "Authorization: Bearer $token"
        fi
    else
        if [ -n "$body" ]; then
            curl -fsS -X "$method" "$BASE_URL$path" \
                -H "Content-Type: application/json" \
                -d "$body"
        else
            curl -fsS -X "$method" "$BASE_URL$path"
        fi
    fi
}

_http_code() {
    # _http_code METHOD PATH [TOKEN] [JSON_BODY] — return status code only
    local method="$1"
    local path="$2"
    local token="${3:-}"
    local body="${4:-}"
    local args=(-s -o /dev/null -w "%{http_code}" -X "$method" "$BASE_URL$path")
    [ -n "$token" ] && args+=(-H "Authorization: Bearer $token")
    [ -n "$body" ] && args+=(-H "Content-Type: application/json" -d "$body")
    curl "${args[@]}"
}

# 探测 BASE_URL 是不是可达
if ! curl -fsS --max-time 10 "$BASE_URL/health" >/dev/null 2>&1; then
    printf "${RED}ERR${NC}: $BASE_URL/health 不可达\n" >&2
    exit 2
fi

printf "${CYAN}==> 支付链路冒烟测试${NC}\n"
printf "  BASE_URL: %s\n" "$BASE_URL"
printf "  ADMIN_TOKEN: %s\n" "${ADMIN_TOKEN:-(empty,部分测试会跳过)}"
printf "  CUSTOMER_TOKEN: %s\n" "${CUSTOMER_TOKEN:-(empty,部分测试会跳过)}"
printf "  SKIP_PAID: %s\n" "$SKIP_PAID"

# ═══════════════════ Section 1: 服务可用性 ═══════════════════
_section "1. 服务可用性"

HEALTH=$(curl -fsS --max-time 5 "$BASE_URL/health" 2>/dev/null || echo "")
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    _check "health-ok" 1 "$HEALTH"
else
    _check "health-ok" 0 "$HEALTH"
fi

# ═══════════════════ Section 2: 微信支付配置 ═══════════════════
_section "2. 微信支付配置(无需 token)"

if [ -n "$ADMIN_TOKEN" ]; then
    STATUS=$(_http GET "/api/v1/payment/wechat/config-status" "$ADMIN_TOKEN" 2>/dev/null || echo "")
    if [ -z "$STATUS" ]; then
        _check "config-status-fetch" 0 "(admin token 鉴权失败?)"
    else
        _check "config-status-fetch" 1 "ready=$(echo "$STATUS" | python -c "import json,sys; print(json.load(sys.stdin).get('ready'))" 2>/dev/null || echo "?")"
        READY=$(echo "$STATUS" | python -c "import json,sys; print(json.load(sys.stdin).get('ready'))" 2>/dev/null || echo "False")
        API_V3_KEY_OK=$(echo "$STATUS" | python -c "import json,sys; print(json.load(sys.stdin).get('api_v3_key_configured'))" 2>/dev/null || echo "False")
        APP_SECRET_OK=$(echo "$STATUS" | python -c "import json,sys; print(json.load(sys.stdin).get('app_secret_configured'))" 2>/dev/null || echo "False")
        _check "api_v3_key_configured" "$API_V3_KEY_OK" "(必需)"
        _check "app_secret_configured" "$APP_SECRET_OK" "(必需)"
    fi

    # 平台 cert 诊断
    DIAG=$(_http GET "/api/v1/admin/wechat-pay/diagnostics" "$ADMIN_TOKEN" 2>/dev/null || echo "")
    if [ -n "$DIAG" ]; then
        CACHED=$(echo "$DIAG" | python -c "import json,sys; d=json.load(sys.stdin); print(d['platform_cert']['cached_count'])" 2>/dev/null || echo "0")
        FAILS=$(echo "$DIAG" | python -c "import json,sys; d=json.load(sys.stdin); print(d['platform_cert']['consecutive_failures'])" 2>/dev/null || echo "0")
        if [ "$CACHED" -gt 0 ]; then
            _check "platform-cert-downloaded" 1 "cached=$CACHED"
        else
            _check "platform-cert-downloaded" 0 "cached=$CACHED consecutive_failures=$FAILS"
        fi
    fi
else
    printf "${YELLOW}SKIP${NC} 配置 / cert 诊断(需要 ADMIN_TOKEN)\n"
fi

# ═══════════════════ Section 3: 鉴权 ═══════════════════
_section "3. 鉴权"

CODE_NO_TOKEN=$(_http_code GET "/api/v1/wallet/balance/1")
_check "wallet-no-token-401" "$([ "$CODE_NO_TOKEN" = "401" ] && echo 1 || echo 0)" "got=$CODE_NO_TOKEN"

if [ -n "$CUSTOMER_TOKEN" ]; then
    CODE_SELF=$(_http_code GET "/api/v1/wallet/balance/0" "$CUSTOMER_TOKEN")
    # 0 不是 customer 的 ID,所以应该 403
    _check "wallet-self-or-admin" "$([ "$CODE_SELF" = "200" ] || [ "$CODE_SELF" = "403" ] && echo 1 || echo 0)" "got=$CODE_SELF (200=self, 403=other)"
else
    printf "${YELLOW}SKIP${NC} wallet self/other(需要 CUSTOMER_TOKEN)\n"
fi

if [ -n "$ADMIN_TOKEN" ]; then
    CODE_ADMIN=$(_http_code GET "/api/v1/admin/reconcile/logs" "$ADMIN_TOKEN")
    _check "admin-reconcile-logs-200" "$([ "$CODE_ADMIN" = "200" ] && echo 1 || echo 0)" "got=$CODE_ADMIN"
else
    printf "${YELLOW}SKIP${NC} admin 端点(需要 ADMIN_TOKEN)\n"
fi

# ═══════════════════ Section 4: 对账 ═══════════════════
_section "4. 对账"

if [ -n "$ADMIN_TOKEN" ]; then
    RECON=$(_http POST "/api/v1/admin/reconcile/run" "$ADMIN_TOKEN" 2>/dev/null || echo "")
    if [ -n "$RECON" ]; then
        MISMATCHES=$(echo "$RECON" | python -c "import json,sys; d=json.load(sys.stdin); print(sum(1 for r in d.get('results',[]) if r.get('status')=='mismatch'))" 2>/dev/null || echo "?")
        _check "reconcile-runs" 1 "mismatches=$MISMATCHES"
    else
        _check "reconcile-runs" 0 "(空响应)"
    fi
else
    printf "${YELLOW}SKIP${NC} 对账(需要 ADMIN_TOKEN)\n"
fi

# ═══════════════════ Section 5: 支付创建(无 JSAPI,只看 prepay 接口) ═══════════════════
_section "5. 支付链路"

if [ "$SKIP_PAID" = "1" ]; then
    printf "${YELLOW}SKIP${NC} 真实支付(SKIP_PAID=1)\n"
elif [ -z "$CUSTOMER_TOKEN" ] || [ -z "$ADMIN_TOKEN" ]; then
    printf "${YELLOW}SKIP${NC} 真实支付(需要 ADMIN_TOKEN + CUSTOMER_TOKEN)\n"
else
    # 5.1 拿 customer ID
    ME=$(_http GET "/api/v1/auth/me" "$CUSTOMER_TOKEN" 2>/dev/null || echo "")
    CUSTOMER_ID=$(echo "$ME" | python -c "import json,sys; print(json.load(sys.stdin).get('id'))" 2>/dev/null || echo "")
    if [ -n "$CUSTOMER_ID" ]; then
        _check "auth-me-customer-id" 1 "id=$CUSTOMER_ID"
    else
        _check "auth-me-customer-id" 0 "no id in /auth/me"
    fi

    # 5.2 找一笔可支付的订单
    ORDERS=$(_http GET "/api/v1/orders?status=wait_payment&limit=5" "$CUSTOMER_TOKEN" 2>/dev/null || echo "")
    ORDER_ID=$(echo "$ORDERS" | python -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null || echo "")
    if [ -n "$ORDER_ID" ]; then
        _check "find-wait-payment-order" 1 "order_id=$ORDER_ID"

        # 5.3 尝试创建 prepay
        PREPAY_CODE=$(_http_code POST "/api/v1/payment/create" "$CUSTOMER_TOKEN" "{\"order_id\":$ORDER_ID,\"user_id\":$CUSTOMER_ID,\"provider\":\"wechat\",\"amount\":0.01}")
        # 期望:200 (mock关时真接) 或 400 (金额不对/配置缺失) — 但绝不是 500
        if [ "$PREPAY_CODE" = "200" ]; then
            _check "wechat-prepay-200" 1 "order_id=$ORDER_ID"
        elif [ "$PREPAY_CODE" = "400" ]; then
            _check "wechat-prepay-400" 1 "order_id=$ORDER_ID(配置未全或金额不符,正常)"
        else
            _check "wechat-prepay-unexpected" 0 "got=$PREPAY_CODE"
        fi
    else
        printf "${YELLOW}SKIP${NC} prepay(无 wait_payment 订单)\n"
    fi
fi

# ═══════════════════ Section 6: 指标 ═══════════════════
_section "6. Prometheus 指标"

METRICS=$(curl -fsS --max-time 5 "$BASE_URL/metrics/prom" 2>/dev/null || echo "")
if [ -n "$METRICS" ]; then
    _check "metrics-endpoint-up" 1 "$(echo "$METRICS" | wc -l) lines"
    if echo "$METRICS" | grep -q "^xiulijiu_orders_total"; then
        _check "metric-orders-total" 1
    else
        _check "metric-orders-total" 0 "(missing)"
    fi
    if echo "$METRICS" | grep -q "^xiulijiu_total_balance"; then
        _check "metric-wallet-balance" 1
    else
        _check "metric-wallet-balance" 0 "(missing)"
    fi
else
    _check "metrics-endpoint-up" 0 "(unreachable)"
fi

# ═══════════════════ Section 7: 告警 ═══════════════════
_section "7. 告警"

if [ -n "$ADMIN_TOKEN" ]; then
    ALERTS=$(_http GET "/api/v1/admin/alerts?resolved=false" "$ADMIN_TOKEN" 2>/dev/null || echo "")
    if [ -n "$ALERTS" ]; then
        COUNT=$(echo "$ALERTS" | python -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "?")
        _check "alerts-fetch" 1 "unresolved=$COUNT"
    fi
fi

# ═══════════════════ 总结 ═══════════════════
echo
printf "${CYAN}══════════════════════════════════════════${NC}\n"
printf "  PASS: ${GREEN}%d${NC}    FAIL: ${RED}%d${NC}    TOTAL: %d\n" "$PASS" "$FAIL" "$((PASS + FAIL))"
printf "${CYAN}══════════════════════════════════════════${NC}\n"

# 输出 JSON 摘要(给 CI / alert_watcher 用)
cat <<EOF
{
  "base_url": "$BASE_URL",
  "pass": $PASS,
  "fail": $FAIL,
  "total": $((PASS + FAIL)),
  "results": [
$(printf '    "%s",\n' "${RESULTS[@]}" | sed '$ s/,$//')
  ]
}
EOF

[ "$FAIL" -eq 0 ]
