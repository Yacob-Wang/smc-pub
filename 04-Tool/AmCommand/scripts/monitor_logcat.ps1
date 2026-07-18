#!/usr/bin/env pwsh
# monitor_logcat.ps1
# ============================================================
# am monitor 的 logcat 替代方案(Windows PowerShell 版)
#
# 用法:
#   .\monitor_logcat.ps1 -Package com.example.app
#   .\monitor_logcat.ps1 -Package com.example.app -OutputFile .\monitor.log -DurationSeconds 60
#
# 基线:AOSP 14 + adb platform-tools 34.0.0+
# ============================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Package,
    [string]$OutputFile = "",
    [int]$DurationSeconds = 0
)

$ErrorActionPreference = "Stop"

# ---- 工具函数:打印统计 ----
function Print-Stats {
    param([string]$File, [string]$Pkg)
    if (-not (Test-Path $File)) { return }

    $gc = (Select-String -Path $File -Pattern "GC:" -ErrorAction SilentlyContinue).Count
    $anr = (Select-String -Path $File -Pattern "ANR in $Pkg" -ErrorAction SilentlyContinue).Count
    $crash = (Select-String -Path $File -Pattern "FATAL EXCEPTION" -ErrorAction SilentlyContinue).Count
    $lmk = (Select-String -Path $File -Pattern "Low on memory" -ErrorAction SilentlyContinue).Count
    $died = (Select-String -Path $File -Pattern "has died" -ErrorAction SilentlyContinue).Count

    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  监控统计" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  GC 次数:    $gc" -ForegroundColor Green
    Write-Host "  ANR 次数:   $anr" -ForegroundColor Green
    Write-Host "  Crash 次数: $crash" -ForegroundColor Green
    Write-Host "  LMK 次数:   $lmk" -ForegroundColor Green
    Write-Host "  进程死亡:   $died" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  输出文件: $File" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

# ---- 参数默认值 ----
if ([string]::IsNullOrEmpty($OutputFile)) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputFile = ".\monitor_$timestamp.log"
}

# ---- 环境检查 ----
if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: adb 不在 PATH" -ForegroundColor Red
    exit 1
}

# ---- 清空 logcat ----
adb logcat -c | Out-Null

# ---- 启动 monitor ----
Write-Host "=== 启动 monitor ===" -ForegroundColor Cyan
Write-Host "  包名: $Package" -ForegroundColor Green
Write-Host "  输出: $OutputFile" -ForegroundColor Green
Write-Host "  时长: $DurationSeconds s(0=无限)" -ForegroundColor Green
Write-Host ""
Write-Host "事件类型: GC / ANR / Crash / LMK / Process died" -ForegroundColor Yellow
Write-Host "按 Ctrl+C 停止" -ForegroundColor Yellow
Write-Host ""

# 后台 logcat 任务
$logcatJob = Start-Job -ScriptBlock {
    param($file)
    adb logcat -v time -s ActivityManager:I AndroidRuntime:E libc:E DEBUG:E "*:S" 2>&1 | Out-File -FilePath $file -Encoding UTF8
} -ArgumentList $OutputFile

# 监控时长
if ($DurationSeconds -gt 0) {
    Start-Sleep -Seconds $DurationSeconds
    Stop-Job $logcatJob
    Remove-Job $logcatJob
    Write-Host ""
    Write-Host "=== 监控结束 ===" -ForegroundColor Cyan
    Print-Stats -File $OutputFile -Pkg $Package
} else {
    Write-Host "无限模式:按 Ctrl+C 停止..." -ForegroundColor Yellow
    # 等待 Ctrl+C
    while ($true) {
        Start-Sleep -Seconds 1
        if ($Host.UI.RawUI.KeyAvailable) {
            $key = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyUp,IncludeKeyDown")
            if ($key.Character -eq [char]3) {  # Ctrl+C
                break
            }
        }
    }
    Stop-Job $logcatJob
    Remove-Job $logcatJob
    Write-Host ""
    Write-Host "=== 监控停止 ===" -ForegroundColor Cyan
    Print-Stats -File $OutputFile -Pkg $Package
}
