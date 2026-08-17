#!/usr/bin/env pwsh
# H5 体验版同步脚本 - 把本地改动的 H5 文件 SCP 到生产/预发布服务器
#
# 用法:
#   # 1) 交互式:会让你填 HOST / USER / REMOTE_PATH
#   pwsh scripts/upload_h5.ps1
#
#   # 2) 环境变量模式:适合 CI / 计划任务
#   $env:H5_SSH_HOST = "8.134.99.53"
#   $env:H5_SSH_USER = "root"
#   $env:H5_SSH_PORT = "22"
#   $env:H5_REMOTE_DIR = "/opt/xiulijiu/website/h5"
#   pwsh scripts/upload_h5.ps1
#
#   # 3) dry-run
#   pwsh scripts/upload_h5.ps1 -DryRun
#
# 前置:本机已安装 OpenSSH 客户端 (Windows 10/11 / Server 2019+ 默认带)
# 兼容:PowerShell 5.1 (Windows) 与 PowerShell 7+ (pwsh)

[CmdletBinding()]
param([switch]$DryRun)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$H5Dir = Join-Path $ProjectRoot "h5"

# ---------- 读配置 ----------
$Host_ = $env:H5_SSH_HOST
$User = $env:H5_SSH_USER
$Port = $env:H5_SSH_PORT
if (-not $Port) { $Port = "22" }
$Remote = $env:H5_REMOTE_DIR
$KeyPath = $env:H5_SSH_KEY

if (-not $Host_)   { $Host_   = Read-Host "Server IP/host" }
if (-not $User)    { $User    = Read-Host "SSH user" }
if (-not $Remote)  { $Remote  = Read-Host "Remote h5 dir (e.g. /opt/xiulijiu/website/h5)" }

# ---------- 检查文件 ----------
$Files = @("index.html", "app.js", "styles.css")
foreach ($f in $Files) {
  if (-not (Test-Path (Join-Path $H5Dir $f))) {
    Write-Host ("[ERR] missing local file: h5/" + $f) -ForegroundColor Red
    exit 1
  }
}

# ---------- 组装 scp 选项 ----------
$sshOpts = @("-P", $Port)
if ($KeyPath) {
  $sshOpts = $sshOpts + @("-i", $KeyPath)
}

Write-Host ""
Write-Host ("==> Uploading " + $Files.Count + " files to " + $User + "@" + $Host_ + ":" + $Remote) -ForegroundColor Cyan
Write-Host ""

# ---------- 上传循环 ----------
$failed = $false
foreach ($f in $Files) {
  $local  = Join-Path $H5Dir $f
  $target = $User + "@" + $Host_ + ":" + $Remote + "/" + $f

  if ($DryRun) {
    $preview = "scp " + ($sshOpts -join " ") + " " + $local + " " + $target
    Write-Host ("[DRY-RUN] " + $preview)
    continue
  }

  Write-Host ("  -> " + $f + " ...") -NoNewline
  try {
    $argList = $sshOpts + @($local, $target)
    & scp @argList 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "scp exit " + $LASTEXITCODE
    }
    Write-Host " OK" -ForegroundColor Green
  } catch {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host ("    " + $_.Exception.Message) -ForegroundColor Red
    $failed = $true
  }
}

# ---------- dry-run 提前退出 ----------
if ($DryRun) {
  Write-Host ""
  Write-Host "Dry-run done. Remove -DryRun to actually upload." -ForegroundColor Yellow
  exit 0
}

# ---------- 上传失败退出 ----------
if ($failed) {
  Write-Host ""
  Write-Host "[ERR] Some files failed to upload, see above." -ForegroundColor Red
  exit 1
}

# ---------- 验证远端 ----------
Write-Host ""
Write-Host "==> Verifying remote files" -ForegroundColor Cyan
$urls = @(
  "https://x.iddg.cn/h5/index.html",
  "https://x.iddg.cn/h5/app.js",
  "https://x.iddg.cn/h5/styles.css"
)
foreach ($u in $urls) {
  try {
    $r = Invoke-WebRequest -Uri $u -UseBasicParsing -Method Head -TimeoutSec 8
    $line = "  OK  " + $u + "  " + $r.StatusCode + "  " + $r.Headers["Content-Length"]
    Write-Host $line -ForegroundColor Green
  } catch {
    $line = "  ??  " + $u + "  " + $_.Exception.Message
    Write-Host $line -ForegroundColor Yellow
  }
}

# ---------- 完成提示 ----------
Write-Host ""
Write-Host "==> Done!" -ForegroundColor Green
Write-Host "  Preview URL: https://x.iddg.cn/h5/"
$stamp = Get-Date -Format "yyyyMMddHHmm"
Write-Host ("  Tip: hard-refresh or add ?v=" + $stamp + " to bypass cache")
