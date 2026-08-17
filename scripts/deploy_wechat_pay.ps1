param(
  [string]$HostName = "8.134.99.53",
  [string]$User = "root",
  [string]$RemoteDir = "/www/wwwroot/xiulijiu_api/current",
  [string]$ServiceName = "xiulijiu-api.service",
  [string]$WechatPayApiV3Key = $env:WECHAT_PAY_API_V3_KEY,
  [string]$WechatAppSecret = $env:WECHAT_APP_SECRET,
  [switch]$PromptWechatSecrets
)

$ErrorActionPreference = "Stop"

function Require-Command($Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Missing required command: $Name"
  }
}

Require-Command "ssh"
Require-Command "scp"
Require-Command "tar"

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

if ($PromptWechatSecrets) {
  if ([string]::IsNullOrEmpty($WechatPayApiV3Key)) {
    $WechatPayApiV3Key = Convert-SecureStringToPlainText (Read-Host "WECHAT_PAY_API_V3_KEY" -AsSecureString)
  }
  if ([string]::IsNullOrEmpty($WechatAppSecret)) {
    $WechatAppSecret = Convert-SecureStringToPlainText (Read-Host "WECHAT_APP_SECRET" -AsSecureString)
  }
}

$WechatPayApiV3KeyB64 = To-Base64Utf8 $WechatPayApiV3Key
$WechatAppSecretB64 = To-Base64Utf8 $WechatAppSecret

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Stamp = Get-Date -Format "yyyyMMddHHmmss"
$Archive = Join-Path $env:TEMP "xiulijiu-wechat-pay-$Stamp.tgz"
$RemoteArchive = "/tmp/xiulijiu-wechat-pay-$Stamp.tgz"
$RemoteScript = "/tmp/xiulijiu-wechat-pay-deploy-$Stamp.sh"
$LocalRemoteScript = Join-Path $env:TEMP "xiulijiu-wechat-pay-deploy-$Stamp.sh"

$Include = @(
  "app",
  "admin-web",
  "h5",
  "cert",
  "requirements.txt",
  ".env.example",
  "scripts/check_wechat_pay.py",
  "scripts/set_wechat_runtime_config.ps1",
  "scripts/set_wechat_app_secret.ps1"
)

Push-Location $Root
try {
  tar -czf $Archive @Include
} finally {
  Pop-Location
}

@'
#!/usr/bin/env bash
set -euo pipefail

REMOTE_DIR="${1:?remote dir required}"
SERVICE_NAME="${2:?service name required}"
ARCHIVE="${3:?archive required}"
STAMP="$(date +%Y%m%d%H%M%S)"
BACKUP_ROOT="/www/backup/xiulijiu_api"
BACKUP_FILE="$BACKUP_ROOT/current-pay-before-$STAMP.tgz"

mkdir -p "$REMOTE_DIR" "$BACKUP_ROOT"

if [ -d "$REMOTE_DIR/app" ]; then
  tar -czf "$BACKUP_FILE" -C "$REMOTE_DIR" \
    app admin-web h5 cert requirements.txt .env .env.example scripts/check_wechat_pay.py \
    2>/dev/null || true
  echo "backup: $BACKUP_FILE"
fi

tar -xzf "$ARCHIVE" -C "$REMOTE_DIR"
cd "$REMOTE_DIR"

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp ".env.example" ".env"
fi
touch ".env"
chmod 600 ".env" || true
chown www:www ".env" 2>/dev/null || true

ensure_env() {
  local key="$1"
  local value="$2"
  if ! grep -q "^${key}=" ".env"; then
    printf "%s=%s\n" "$key" "$value" >> ".env"
  fi
}

ensure_env "PUBLIC_BASE_URL" "https://x.iddg.cn"
ensure_env "WECHAT_PAY_APPID" "wx2273201e59e280bc"
ensure_env "WECHAT_PAY_MCH_ID" "1481119632"
ensure_env "WECHAT_PAY_CERT_PATH" "cert/apiclient_cert.pem"
ensure_env "WECHAT_PAY_KEY_PATH" "cert/apiclient_key.pem"
ensure_env "WECHAT_PAY_CERT_SERIAL_NO" "4591395BB783609366C47474379A9B2B5611FEF0"
ensure_env "WECHAT_PAY_NOTIFY_URL" "https://x.iddg.cn/api/v1/payment/wechat/notify"
ensure_env "WECHAT_REFUND_NOTIFY_URL" "https://x.iddg.cn/api/v1/payment/wechat/refund-notify"
ensure_env "WECHAT_WITHDRAW_AUTO_TRANSFER" "false"
ensure_env "WECHAT_TRANSFER_SCENE_ID" ""
ensure_env "WECHAT_TRANSFER_NOTIFY_URL" "https://x.iddg.cn/api/v1/wallet/wechat/transfer-notify"
ensure_env "WECHAT_TRANSFER_REMARK" "withdrawal"
ensure_env "WECHAT_TRANSFER_USER_RECV_PERCEPTION" "withdrawal"

upsert_env() {
  local key="$1"
  local value="$2"
  local tmp
  tmp="$(mktemp)"
  grep -v "^${key}=" ".env" > "$tmp" 2>/dev/null || true
  printf "%s=%s\n" "$key" "$value" >> "$tmp"
  cat "$tmp" > ".env"
  rm -f "$tmp"
}

decode_b64() {
  printf "%s" "$1" | base64 -d
}

if [ -n "${DEPLOY_WECHAT_PAY_API_V3_KEY_B64:-}" ]; then
  upsert_env "WECHAT_PAY_API_V3_KEY" "$(decode_b64 "$DEPLOY_WECHAT_PAY_API_V3_KEY_B64")"
fi
if [ -n "${DEPLOY_WECHAT_APP_SECRET_B64:-}" ]; then
  upsert_env "WECHAT_APP_SECRET" "$(decode_b64 "$DEPLOY_WECHAT_APP_SECRET_B64")"
fi
chmod 600 ".env" || true
chown www:www ".env" 2>/dev/null || true

if [ -x ".venv/bin/python" ]; then
  PY_BIN=".venv/bin/python"
else
  PY_BIN="$(command -v python3 || command -v python)"
  if [ ! -d ".venv" ]; then
    "$PY_BIN" -m venv .venv || true
  fi
  if [ -x ".venv/bin/python" ]; then
    PY_BIN=".venv/bin/python"
  fi
fi

"$PY_BIN" -m pip install -r requirements.txt

if ! grep -q "^WECHAT_PAY_API_V3_KEY=.\+" ".env"; then
  echo "missing: set WECHAT_PAY_API_V3_KEY in $REMOTE_DIR/.env"
fi
if ! grep -q "^WECHAT_APP_SECRET=.\+" ".env"; then
  echo "missing: set WECHAT_APP_SECRET in $REMOTE_DIR/.env"
fi
if ! grep -q "^WECHAT_TRANSFER_SCENE_ID=.\+" ".env"; then
  echo "optional missing: set WECHAT_TRANSFER_SCENE_ID to enable WeChat merchant transfers"
fi

systemctl restart "$SERVICE_NAME"
systemctl --no-pager --full status "$SERVICE_NAME" | sed -n '1,12p'

curl -fsS http://127.0.0.1:8112/health || true
echo
"$PY_BIN" scripts/check_wechat_pay.py
'@ | Set-Content -Encoding utf8 -NoNewline $LocalRemoteScript

try {
  scp $Archive "${User}@${HostName}:$RemoteArchive"
  scp $LocalRemoteScript "${User}@${HostName}:$RemoteScript"
  $RemoteCommand = "DEPLOY_WECHAT_PAY_API_V3_KEY_B64='$WechatPayApiV3KeyB64' DEPLOY_WECHAT_APP_SECRET_B64='$WechatAppSecretB64' bash '$RemoteScript' '$RemoteDir' '$ServiceName' '$RemoteArchive'"
  ssh "${User}@${HostName}" $RemoteCommand
} finally {
  Remove-Item -LiteralPath $Archive -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $LocalRemoteScript -Force -ErrorAction SilentlyContinue
}
