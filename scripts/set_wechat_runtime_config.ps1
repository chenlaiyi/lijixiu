param(
  [string]$HostName = "8.134.99.53",
  [string]$User = "root",
  [string]$ServiceName = "xiulijiu-api.service",
  [string]$EnvFile = "/www/wwwroot/xiulijiu_api/shared/.env",
  [string]$WechatAppSecret = $env:WECHAT_APP_SECRET,
  [string]$WechatTransferSceneId = $env:WECHAT_TRANSFER_SCENE_ID,
  [ValidateSet("true", "false")]
  [string]$WechatWithdrawAutoTransfer = "false",
  [switch]$Prompt
)

$ErrorActionPreference = "Stop"

function Convert-SecureStringToPlainText([securestring]$Value) {
  if (-not $Value) { return "" }
  $Ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
  try {
    return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Ptr)
  } finally {
    if ($Ptr -ne [IntPtr]::Zero) {
      [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Ptr)
    }
  }
}

function To-Base64Utf8([string]$Value) {
  if ([string]::IsNullOrEmpty($Value)) { return "" }
  return [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Value))
}

if ($Prompt -or [string]::IsNullOrWhiteSpace($WechatAppSecret)) {
  $WechatAppSecret = Convert-SecureStringToPlainText (Read-Host "WECHAT_APP_SECRET" -AsSecureString)
}

if ($Prompt -and [string]::IsNullOrWhiteSpace($WechatTransferSceneId)) {
  $WechatTransferSceneId = Read-Host "WECHAT_TRANSFER_SCENE_ID (optional, press Enter to skip)"
}

if ([string]::IsNullOrWhiteSpace($WechatAppSecret)) {
  throw "WECHAT_APP_SECRET is required for miniprogram payment openid exchange."
}

$SecretB64 = To-Base64Utf8 $WechatAppSecret
$SceneB64 = To-Base64Utf8 $WechatTransferSceneId

$RemoteScript = @'
set -euo pipefail
ENV_FILE="${1:?env file required}"
SERVICE_NAME="${2:?service name required}"
SECRET_B64="${3:?secret required}"
SCENE_B64="${4:-}"
AUTO_TRANSFER="${5:-false}"

mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE" || true

SECRET="$(printf "%s" "$SECRET_B64" | base64 -d)"
SCENE_ID=""
if [ -n "$SCENE_B64" ]; then
  SCENE_ID="$(printf "%s" "$SCENE_B64" | base64 -d)"
fi

upsert_env() {
  local key="$1"
  local value="$2"
  local tmp
  tmp="$(mktemp)"
  grep -v "^${key}=" "$ENV_FILE" > "$tmp" 2>/dev/null || true
  printf "%s=%s\n" "$key" "$value" >> "$tmp"
  cat "$tmp" > "$ENV_FILE"
  rm -f "$tmp"
}

upsert_env "PUBLIC_BASE_URL" "https://x.iddg.cn"
upsert_env "WECHAT_PAY_NOTIFY_URL" "https://x.iddg.cn/api/v1/payment/wechat/notify"
upsert_env "WECHAT_REFUND_NOTIFY_URL" "https://x.iddg.cn/api/v1/payment/wechat/refund-notify"
upsert_env "WECHAT_TRANSFER_NOTIFY_URL" "https://x.iddg.cn/api/v1/wallet/wechat/transfer-notify"
upsert_env "WECHAT_APP_SECRET" "$SECRET"
upsert_env "WECHAT_WITHDRAW_AUTO_TRANSFER" "$AUTO_TRANSFER"
if [ -n "$SCENE_ID" ]; then
  upsert_env "WECHAT_TRANSFER_SCENE_ID" "$SCENE_ID"
fi
if ! grep -q "^WECHAT_TRANSFER_REMARK=" "$ENV_FILE"; then
  printf "WECHAT_TRANSFER_REMARK=withdrawal\n" >> "$ENV_FILE"
fi
if ! grep -q "^WECHAT_TRANSFER_USER_RECV_PERCEPTION=" "$ENV_FILE"; then
  printf "WECHAT_TRANSFER_USER_RECV_PERCEPTION=withdrawal\n" >> "$ENV_FILE"
fi

chown www:www "$ENV_FILE" 2>/dev/null || true

systemctl restart "$SERVICE_NAME"
sleep 2
systemctl is-active "$SERVICE_NAME"
curl -fsS http://127.0.0.1:8112/api/v1/payment/wechat/config-status
echo
curl -fsS http://127.0.0.1:8112/api/v1/wallet/wechat-transfer/config-status
echo
'@

$EncodedScript = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($RemoteScript))
$RemoteCommand = "python3 - <<'PY'
import base64
import subprocess
script = base64.b64decode('$EncodedScript').decode('utf-8')
subprocess.run(['bash', '-s', '$EnvFile', '$ServiceName', '$SecretB64', '$SceneB64', '$WechatWithdrawAutoTransfer'], input=script, text=True, check=True)
PY"

ssh "${User}@${HostName}" $RemoteCommand
