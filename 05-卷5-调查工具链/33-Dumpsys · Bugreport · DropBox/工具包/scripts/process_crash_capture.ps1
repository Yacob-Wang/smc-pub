#!/usr/bin/env pwsh
# process_crash_capture.ps1
# ============================================================
# 主动触发 crash 并采集完整现场(Windows PowerShell 版)
#
# 用法:
#   .\process_crash_capture.ps1 -Package com.example.app
#   .\process_crash_capture.ps1 -Package com.example.app -OutputDir .\crash_2024
#
# 基线:AOSP 14 + adb platform-tools 34.0.0+
# ============================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Package,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

# ---- 帮助 ----
if (-not $Package) {
    @"
用法: .\process_crash_capture.ps1 -Package <package> [-OutputDir <dir>]

参数:
  -Package    目标 app 包名(必填)
  -OutputDir  输出目录(可选,默认 .\crash_capture_TIMESTAMP)
"@
    exit 1
}

# ---- 环境检查 ----
if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: adb 不在 PATH" -ForegroundColor Red
    exit 1
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: 没有连接 adb 设备" -ForegroundColor Red
    exit 1
}

# ---- 创建输出目录 ----
if ([string]::IsNullOrEmpty($OutputDir)) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputDir = ".\crash_capture_$timestamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
New-Item -ItemType Directory -Force -Path "$OutputDir\tombstones" | Out-Null
New-Item -ItemType Directory -Force -Path "$OutputDir\anr" | Out-Null
Write-Host "=== 现场输出目录: $OutputDir ===" -ForegroundColor Cyan

# ---- Step 1: 清空 logcat ----
Write-Host "[1/6] 准备 logcat..." -ForegroundColor Cyan
adb logcat -c
$startTime = Get-Date

# ---- Step 2: 触发 crash ----
Write-Host "[2/6] 触发 am crash $Package ..." -ForegroundColor Cyan
try {
    $crashResult = adb shell am crash $Package 2>&1
    Write-Host "  输出: $crashResult"
} catch {
    Write-Host "  ERROR: am crash 执行失败" -ForegroundColor Red
    exit 1
}
Start-Sleep -Seconds 3

# ---- Step 3: 拉 logcat ----
Write-Host "[3/6] 拉 crash 后 logcat..." -ForegroundColor Cyan
adb logcat -d -b all > "$OutputDir\logcat_after.log"
$logcatLines = (Get-Content "$OutputDir\logcat_after.log").Count
Write-Host "  logcat 行数: $logcatLines" -ForegroundColor Green

# ---- Step 4: 拉 dropbox ----
Write-Host "[4/6] 拉 dropbox..." -ForegroundColor Cyan
try {
    adb shell dumpsys dropbox --print > "$OutputDir\dropbox.log" 2>&1
    if ((Get-Item "$OutputDir\dropbox.log").Length -gt 0) {
        $dropboxLines = (Get-Content "$OutputDir\dropbox.log").Count
        Write-Host "  dropbox 行数: $dropboxLines" -ForegroundColor Green
        # 提取和目标包相关的事件
        Select-String -Path "$OutputDir\dropbox.log" -Pattern $Package -Context 0, 5 | Out-File "$OutputDir\dropbox_$Package.log" -Encoding UTF8
    } else {
        Write-Host "  (dropbox 输出为空)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  (dropbox 需要 root 或 debug 包)" -ForegroundColor Yellow
}

# ---- Step 5: 拉 tombstone / anr ----
Write-Host "[5/6] 拉 tombstone / anr..." -ForegroundColor Cyan
try {
    adb pull /data/tombstones/ "$OutputDir\tombstones\" 2>&1 | Out-Null
    $tombCount = (Get-ChildItem "$OutputDir\tombstones" -ErrorAction SilentlyContinue).Count
    Write-Host "  tombstone 数量: $tombCount" -ForegroundColor Green
} catch {
    Write-Host "  (tombstone 需要 root,或本次未触发 native crash)" -ForegroundColor Yellow
}

try {
    adb pull /data/anr/ "$OutputDir\anr\" 2>&1 | Out-Null
    $anrCount = (Get-ChildItem "$OutputDir\anr" -ErrorAction SilentlyContinue).Count
    Write-Host "  ANR 数量: $anrCount" -ForegroundColor Green
} catch {
    Write-Host "  (本次未触发 ANR 或 anr 不可读)" -ForegroundColor Yellow
}

# ---- Step 6: 拉 dumpsys 快照 ----
Write-Host "[6/6] 拉 dumpsys 快照..." -ForegroundColor Cyan
adb shell dumpsys activity processes > "$OutputDir\dumpsys_processes.log" 2>&1
adb shell dumpsys meminfo $Package > "$OutputDir\dumpsys_meminfo.log" 2>&1
adb shell dumpsys activity activities > "$OutputDir\dumpsys_activities.log" 2>&1

# ---- 生成报告 ----
$endTime = Get-Date
$duration = [math]::Round(($endTime - $startTime).TotalSeconds, 1)

$logcatSize = "{0:N2} KB" -f ((Get-Item "$OutputDir\logcat_after.log").Length / 1KB)
$dropboxSize = if (Test-Path "$OutputDir\dropbox.log") { "{0:N2} KB" -f ((Get-Item "$OutputDir\dropbox.log").Length / 1KB) } else { "0 KB" }

$report = @"
# Crash 现场报告

- 包名: $Package
- 触发时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
- 触发耗时: $duration s
- 触发命令: am crash $Package

## 关键文件

| 文件 | 用途 |
|------|------|
| `logcat_after.log` | crash 后的全 buffer logcat(关键) |
| `dropbox.log` | dropbox 事件(am_proc_died, system_app_crash 等) |
| `dropbox_$Package.log` | 仅和 $Package 相关的 dropbox 事件 |
| `tombstones\` | native crash 现场(若有) |
| `anr\` | ANR 现场(若有) |
| `dumpsys_*.log` | 系统状态快照 |

## 快速分析步骤

### Step 1: 确认死亡原因
\`\`\`powershell
Select-String -Path logcat_after.log -Pattern 'FATAL|AndroidRuntime|am_proc_died'
\`\`\`

### Step 2: 定位 Java 栈
\`\`\`powershell
\$content = Get-Content logcat_after.log -Raw
\$content | Select-String 'FATAL EXCEPTION' -Context 0, 30
\`\`\`

### Step 3: 看 dropbox 上下文
\`\`\`powershell
Get-Content dropbox_$Package.log
\`\`\`

### Step 4: 看 native 栈(若有)
\`\`\`powershell
Get-ChildItem tombstones\
Get-Content tombstones\tombstone_00 -TotalCount 20
\`\`\`

## 关键统计

- 触发耗时: $duration s
- logcat 大小: $logcatSize
- dropbox 大小: $dropboxSize
"@

$report | Out-File "$OutputDir\REPORT.md" -Encoding UTF8

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Crash 现场已采集到: $OutputDir" -ForegroundColor Green
Write-Host "看 REPORT.md 了解快速分析步骤" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
