param(
  [string]$HostName = "8.134.99.53",
  [string]$User = "root",
  [string]$ServiceName = "xiulijiu-api.service",
  [string]$EnvFile = "/www/wwwroot/xiulijiu_api/shared/.env",
  [string]$WechatAppSecret = $env:WECHAT_APP_SECRET,
  [switch]$PromptAppSecret
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

if ($PromptAppSecret -or [string]::IsNullOrEmpty($WechatAppSecret)) {
  $WechatAppSecret = Convert-SecureStringToPlainText (Read-Host "WECHAT_APP_SECRET" -AsSecureString)
}

if ([string]::IsNullOrWhiteSpace($WechatAppSecret)) {
  throw "WECHAT_APP_SECRET is required."
}

$SecretB64 = To-Base64Utf8 $WechatAppSecret

$RemoteScript = @'
set -euo pipefail
ENV_FILE="${1:?env file required}"
SERVICE_NAME="${2:?service name required}"
SECRET_B64="${3:?secret required}"

mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE" || true

SECRET="$(printf "%s" "$SECRET_B64" | base64 -d)"
TMP="$(mktemp)"
grep -v "^WECHAT_APP_SECRET=" "$ENV_FILE" > "$TMP" 2>/dev/null || true
printf "WECHAT_APP_SECRET=%s\n" "$SECRET" >> "$TMP"
cat "$TMP" > "$ENV_FILE"
rm -f "$TMP"
chown www:www "$ENV_FILE" 2>/dev/null || true

systemctl restart "$SERVICE_NAME"
sleep 2
systemctl is-active "$SERVICE_NAME"
curl -fsS http://127.0.0.1:8112/api/v1/payment/wechat/config-status
echo
'@

$EncodedScript = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($RemoteScript))
$RemoteCommand = "python3 - <<'PY'
import base64
import subprocess
script = base64.b64decode('$EncodedScript').decode('utf-8')
subprocess.run(['bash', '-s', '$EnvFile', '$ServiceName', '$SecretB64'], input=script, text=True, check=True)
PY"

ssh "${User}@${HostName}" $RemoteCommand
