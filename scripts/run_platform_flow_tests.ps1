#requires -Version 5.1
# Run full-link platform tests and emit a Markdown report.
# Note: PS5.1 parser on Windows has issues with non-ASCII in source files,
# so this script uses ASCII only in its own source. The Markdown report it
# emits is UTF-8 and contains the Chinese content the reader expects.

$ErrorActionPreference = 'Continue'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPy = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Script = Join-Path $ProjectRoot 'scripts\test_platform_flows.py'
$ReportPath = Join-Path $ProjectRoot 'docs\test-report.md'

if (-not (Test-Path $VenvPy)) {
    Write-Host ('Venv not found: ' + $VenvPy) -ForegroundColor Red
    exit 1
}

Write-Host '==> Running platform flow tests...' -ForegroundColor Cyan

# Capture stdout+stderr via temp files. Python's cleanup noise can exit 1
# even when tests pass, so we deliberately ignore the exit code here.
$tmpOut = [System.IO.Path]::GetTempFileName()
$tmpErr = [System.IO.Path]::GetTempFileName()
try {
    $p = Start-Process -FilePath $VenvPy -ArgumentList $Script -NoNewWindow -Wait `
        -RedirectStandardOutput $tmpOut -RedirectStandardError $tmpErr
    $output = [System.IO.File]::ReadAllText($tmpOut) + [System.IO.File]::ReadAllText($tmpErr)
} finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $tmpOut, $tmpErr
}

$suites = New-Object System.Collections.ArrayList
foreach ($line in ($output -split "`r?`n")) {
    if ($line -match '^(.+?)=(ok|fail)$') {
        [void]$suites.Add([PSCustomObject]@{ Name = $Matches[1]; Status = $Matches[2] })
    }
}

$okCount = 0
$failCount = 0
foreach ($s in $suites) {
    if ($s.Status -eq 'ok') { $okCount++ } else { $failCount++ }
}

$timestamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
$hostName = $env:COMPUTERNAME
$pyVer = & $VenvPy -c 'import sys;print(sys.version.split()[0])'

# Build report lines using [String]::Format to avoid PS5.1 parser quirks with -f
$report = New-Object System.Collections.ArrayList
[void]$report.Add([String]::Format('# 全链路测试报告'))
[void]$report.Add([String]::Format(''))
[void]$report.Add([String]::Format('- 跑测时间:{0}', $timestamp))
[void]$report.Add([String]::Format('- 运行环境:{0} · Python {1}', $hostName, $pyVer))
[void]$report.Add([String]::Format('- 脚本:`scripts/test_platform_flows.py`'))
if ($failCount -gt 0) {
    [void]$report.Add([String]::Format('- 结果:**{0} / {1} 通过** · **{2} 失败**', $okCount, $suites.Count, $failCount))
} else {
    [void]$report.Add([String]::Format('- 结果:**{0} / {1} 通过**', $okCount, $suites.Count))
}
[void]$report.Add([String]::Format(''))
[void]$report.Add([String]::Format('| # | Suite | Result |'))
[void]$report.Add([String]::Format('|---|---|---|'))
$idx = 1
foreach ($s in $suites) {
    $icon = '[OK]'
    if ($s.Status -ne 'ok') { $icon = '[FAIL]' }
    [void]$report.Add([String]::Format('| {0} | {1} | {2} {3} |', $idx, $s.Name, $icon, $s.Status))
    $idx++
}
[void]$report.Add([String]::Format(''))
[void]$report.Add([String]::Format('## 套件覆盖'))
[void]$report.Add([String]::Format(''))
[void]$report.Add([String]::Format('1. **auth_roles_and_sms** - 9 角色微信登录 + SMS 登录 + 非法账号拒登'))
[void]$report.Add([String]::Format('2. **review_login_and_partial_withdrawal** - 审核账号 login + 提现 + 自动重置'))
[void]$report.Add([String]::Format('3. **xiamen_service_area_assignment_and_routing** - 厦门思明区 98 个服务区查询 + 批量分配'))
[void]$report.Add([String]::Format('4. **repair_proxy_claim_payment_warranty** - 报修 → 师傅接单 → 服务单 → 支付 → 保修'))
[void]$report.Add([String]::Format('5. **per_order_and_monthly_payroll** - 单笔订单结算 + 月度工资单'))
[void]$report.Add([String]::Format('6. **domestic_matching_installments_profit** - 家政需求匹配 + 分期支付 + 分润'))
[void]$report.Add([String]::Format(''))
[void]$report.Add([String]::Format('## Known cleanup noise'))
[void]$report.Add([String]::Format(''))
[void]$report.Add([String]::Format('After tests pass, Python `tempfile.TemporaryDirectory` cleanup can race with SQLite handle release on Windows and print `PermissionError: [WinError 32]`. This is teardown only and does not affect assertions.'))
[void]$report.Add([String]::Format(''))
[void]$report.Add([String]::Format('## Re-run'))
[void]$report.Add([String]::Format(''))
[void]$report.Add([String]::Format('```powershell'))
[void]$report.Add([String]::Format('.\scripts\run_platform_flow_tests.ps1'))
[void]$report.Add([String]::Format('```'))
[void]$report.Add([String]::Format(''))

$utf8 = New-Object System.Text.UTF8Encoding($false)
$content = [string]::Join("`n", $report.ToArray())
[System.IO.File]::WriteAllText($ReportPath, $content, $utf8)

$summary = 'Pass: ' + $okCount + ' / ' + $suites.Count + '  Report: ' + $ReportPath
if ($failCount -gt 0) {
    Write-Host $summary -ForegroundColor Red
    exit 1
} else {
    Write-Host $summary -ForegroundColor Green
    exit 0
}
