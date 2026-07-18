#!/usr/bin/env pwsh
# dumpheap_and_analyze.ps1
# ============================================================
# 端到端 am dumpheap 自动化脚本(Windows PowerShell)
# 流程:触发 dump → pull → hprof-conv 转换 → 准备 MAT
#
# 用法:
#   .\dumpheap_and_analyze.ps1 -Package com.example.app
#   .\dumpheap_and_analyze.ps1 -Package com.example.app -OutputDir .\dumps
#   .\dumpheap_and_analyze.ps1 -Package com.example.app -OutputDir .\dumps -UserId 0
#
# 依赖:
#   - adb 已配 PATH
#   - $env:ANDROID_HOME 已设(指向 SDK 根)
#   - hprof-conv.exe 在 $env:ANDROID_HOME\platform-tools\
#
# 基线:AOSP 14 + adb platform-tools 34.0.0+
# ============================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Package,
    [string]$OutputDir = ".\heap_dumps",
    [string]$UserId = ""
)

$ErrorActionPreference = "Stop"

# ---- 帮助 ----
if (-not $Package) {
    @"
用法: .\dumpheap_and_analyze.ps1 -Package <package> [-OutputDir <dir>] [-UserId <id>]

参数:
  -Package    目标 app 包名(必填)
  -OutputDir  输出目录(可选,默认 .\heap_dumps)
  -UserId     Android user id(可选,默认空 = 当前)

示例:
  .\dumpheap_and_analyze.ps1 -Package com.example.app
  .\dumpheap_and_analyze.ps1 -Package com.example.app -OutputDir .\dumps -UserId 0
"@
    exit 1
}

# ---- 环境检查 ----
if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: adb 不在 PATH" -ForegroundColor Red
    exit 1
}

if (-not $env:ANDROID_HOME) {
    Write-Host "ERROR: `$env:ANDROID_HOME 未设置" -ForegroundColor Red
    Write-Host "  `$env:ANDROID_HOME = 'C:\path\to\Android\Sdk'"
    exit 1
}

$hprofConv = Join-Path $env:ANDROID_HOME "platform-tools\hprof-conv.exe"
if (-not (Test-Path $hprofConv)) {
    Write-Host "ERROR: hprof-conv 不在 $hprofConv" -ForegroundColor Red
    exit 1
}

# 检查 adb 设备
$adbState = adb get-state 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: 没有连接 adb 设备" -ForegroundColor Red
    exit 1
}

# ---- 创建输出目录 ----
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$heapFile = "/data/local/tmp/heap_$ts.hprof"
$localFile = Join-Path $OutputDir "heap_$ts.hprof"
$converted = Join-Path $OutputDir "heap_$ts_mat.hprof"

# ---- Step 1: 找 PID ----
Write-Host "=== [1/5] 查找目标进程 $Package ===" -ForegroundColor Cyan

$pidofCmd = if ($UserId) { "pidof $Package" } else { "pidof $Package" }
$pidRaw = adb shell $pidofCmd
$pid = ($pidRaw | Out-String).Trim()

if ([string]::IsNullOrEmpty($pid)) {
    Write-Host "ERROR: 进程 $Package 未运行" -ForegroundColor Red
    Write-Host "  当前进程列表(前 20):" -ForegroundColor Yellow
    adb shell "ps -A" | Select-Object -First 20
    exit 1
}
Write-Host "  PID: $pid" -ForegroundColor Green

# 显示进程信息
Write-Host "  进程信息:" -ForegroundColor Gray
$psOutput = adb shell "ps -A | grep $Package" 2>&1
$psOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }

# ---- Step 2: 触发 dump ----
Write-Host ""
Write-Host "=== [2/5] 触发 am dumpheap ===" -ForegroundColor Cyan
Write-Host "  目标: $heapFile"
Write-Host "  警告:app 会卡顿 5-30 秒(dump 期间 ANR 告警属正常)" -ForegroundColor Yellow

$dumpCmd = if ($UserId) { "am dumpheap -n $UserId $pid $heapFile" } else { "am dumpheap $pid $heapFile" }

$startTime = Get-Date
try {
    $dumpResult = adb shell $dumpCmd
    Write-Host "  命令输出: $dumpResult"
} catch {
    Write-Host "ERROR: am dumpheap 执行失败" -ForegroundColor Red
    Write-Host "  常见原因:" -ForegroundColor Yellow
    Write-Host "    1) 权限不足:需要 DUMP 权限" -ForegroundColor Yellow
    Write-Host "    2) 进程已死:重新 pidof 拿最新 pid" -ForegroundColor Yellow
    Write-Host "    3) SELinux 拒绝:adb shell setenforce 0" -ForegroundColor Yellow
    exit 1
}
$endTime = Get-Date
$duration = [math]::Round(($endTime - $startTime).TotalSeconds, 1)
Write-Host "  完成,耗时: $duration s" -ForegroundColor Green

# ---- Step 3: pull 文件 ----
Write-Host ""
Write-Host "=== [3/5] 拉取文件到本地 ===" -ForegroundColor Cyan
Start-Sleep -Seconds 1  # 等文件系统刷盘

$remoteInfo = adb shell "ls -l $heapFile" 2>&1
$remoteSize = 0
if ($remoteInfo -match "(\d+)\s+\S+\s+\S+\s+(\d+)") {
    $remoteSize = [int]$Matches[2]
}
if ($remoteSize -eq 0) {
    Write-Host "ERROR: 远程文件 $heapFile 不存在或大小为 0" -ForegroundColor Red
    Write-Host "  可能 dump 提前失败,查看 logcat:" -ForegroundColor Yellow
    Write-Host "    adb logcat -d | Select-String 'art|debug'" -ForegroundColor Yellow
    exit 1
}
$remoteSizeMB = [math]::Round($remoteSize / 1MB, 2)
Write-Host "  远程文件大小: $remoteSizeMB MB" -ForegroundColor Green

try {
    adb pull $heapFile $localFile | Out-Null
} catch {
    Write-Host "ERROR: 拉取失败" -ForegroundColor Red
    exit 1
}
$localSizeMB = [math]::Round((Get-Item $localFile).Length / 1MB, 2)
Write-Host "  本地路径: $localFile" -ForegroundColor Green
Write-Host "  本地大小: $localSizeMB MB" -ForegroundColor Green

# ---- Step 4: hprof-conv 转换 ----
Write-Host ""
Write-Host "=== [4/5] hprof-conv 转换 ===" -ForegroundColor Cyan
try {
    & $hprofConv $localFile $converted | Out-Null
} catch {
    Write-Host "ERROR: hprof-conv 转换失败" -ForegroundColor Red
    Write-Host "  可能原因:文件截断(被信号中断)" -ForegroundColor Yellow
    exit 1
}
$convertedSizeMB = [math]::Round((Get-Item $converted).Length / 1MB, 2)
Write-Host "  转换后: $converted" -ForegroundColor Green
Write-Host "  大小: $convertedSizeMB MB" -ForegroundColor Green

# ---- Step 5: 清理 + 报告 ----
Write-Host ""
Write-Host "=== [5/5] 清理设备文件 + 输出报告 ===" -ForegroundColor Cyan
adb shell "rm -f $heapFile" | Out-Null

# 写 OQL 模板
$oqlFile = Join-Path $OutputDir "oom_queries_$ts.txt"
@"
// MAT OQL 模板
// 在 MAT 的 OQL 面板粘贴以下查询

// 1. 找所有 Activity(可能泄漏)
SELECT * FROM android.app.Activity

// 2. 找所有 Bitmap(可能 Native OOM)
SELECT * FROM android.graphics.Bitmap

// 3. 找所有 Handler(可能消息堆积)
SELECT * FROM android.os.Handler

// 4. 找 static 字段持有的对象(经典泄漏模式)
SELECT classof(c.value) AS cls, c.value
FROM java.lang.Class `$cls
WHERE `$cls.name LIKE "com.example.app.%"
   , `$cls.classLoader != null
   , c = classof(`$cls).staticField
   , c.@reference != null

// 5. 找所有 Fragment
SELECT * FROM androidx.fragment.app.Fragment
"@ | Out-File -FilePath $oqlFile -Encoding UTF8

@"

========================================
  Dump 完成!
========================================
原始文件:  $localFile
MAT 文件:  $converted  ← 用 MAT 打开这个
OQL 模板:  $oqlFile
dump 耗时:  $duration s
目标 PID:  $pid
用户 ID:   $(if ($UserId) { $UserId } else { "default(0)" })

下一步:
  1. 用 MAT(Eclipse Memory Analyzer)打开 $converted
     - Leak Suspects Report(自动疑似泄漏)
     - Dominator Tree(看谁占内存最多)
     - Histogram(按类看实例数)
  2. 把 $oqlFile 里的 OQL 复制到 MAT 的 OQL 面板
  3. 对比多次 dump 的差集,看哪些对象在累积

参考本系列:
  - 04 §9 案例库
  - Hprof 系列 02(hprof 工具链)
  - Hprof 系列 04(内存泄漏 SOP)

========================================
"@ -ForegroundColor Green
