# profile_trace_capture.ps1
#   自动触发 am profile 采样 + 自动归档 + 元信息记录
#
# 适用:Android 7.0+,adb 可用,Windows PowerShell 5.1+
#
# 用法:
#   .\profile_trace_capture.ps1 -Package com.example.app -DurationSec 60 -Scene "cold_start_test"
#   .\profile_trace_capture.ps1 -Package com.example.app -DurationSec 30 -WithDumpheap -Scene "stress_30s"

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Package,

    [int]$DurationSec = 30,

    [string]$Scene = "manual",

    [switch]$WithDumpheap,

    [int]$UserId = 0,

    [string]$OutputDir = "./traces"
)

$ErrorActionPreference = "Stop"

# ---------- 前置检查 ----------
if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
    Write-Error "ERROR: adb 命令未找到,请配置 ANDROID_HOME/platform-tools 到 PATH"
    exit 1
}

$devices = & adb devices
if (-not ($devices -match "device$")) {
    Write-Error "ERROR: 没有连接的 adb 设备"
    exit 1
}

# ---------- 解析 PID ----------
$Pid = $Package
if ($Package -match "^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+$") {
    $pidof = & adb shell pidof $Package
    $Pid = ($pidof -replace "\r|\n| ", "").Trim()
    if ([string]::IsNullOrEmpty($Pid)) {
        Write-Error "ERROR: 找不到进程 $Package 的 PID"
        Write-Host "提示: 先 adb shell am start -n $Package/... 启动 app"
        exit 1
    }
    Write-Host "[INFO] $Package 的 PID = $Pid"
}

# ---------- 设备信息 ----------
$DeviceModel = (& adb shell getprop ro.product.model) -replace "\r|\n", ""
$AndroidVer = (& adb shell getprop ro.build.version.release) -replace "\r|\n", ""
$SdkInt = (& adb shell getprop ro.build.version.sdk) -replace "\r|\n", ""

# ---------- 输出目录 ----------
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$SceneDir = Join-Path $OutputDir "$Timestamp/$Scene"
New-Item -ItemType Directory -Path $SceneDir -Force | Out-Null

Write-Host "==============================================="
Write-Host "  am profile 自动化采集"
Write-Host "==============================================="
Write-Host "  目标进程   : $Package (PID=$Pid)"
Write-Host "  采样时长   : ${DurationSec}s"
Write-Host "  场景描述   : $Scene"
Write-Host "  联动 dump  : $(if ($WithDumpheap) { 'YES' } else { 'NO' })"
Write-Host "  设备       : $DeviceModel (Android $AndroidVer, SDK $SdkInt)"
Write-Host "  输出目录   : $SceneDir"
Write-Host "==============================================="

# ---------- 基准时间 ----------
$BaseTime = (& adb shell date +%s.%N) -replace "\r|\n", ""
Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Profile start time: $BaseTime"

# ---------- 启动 profile ----------
& adb shell am profile start --user $UserId $Pid /data/local/tmp/trace.trace 2>&1 | Tee-Object -FilePath "$SceneDir/profile_start.log"

# ---------- (可选)联动 dumpheap ----------
$DumpTime = ""
if ($WithDumpheap) {
    $DumpDelay = [Math]::Floor($DurationSec / 2)
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 等待 ${DumpDelay}s 后触发 dumpheap..."
    Start-Sleep -Seconds $DumpDelay
    $DumpTime = (& adb shell date +%s.%N) -replace "\r|\n", ""
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Dump time: $DumpTime"
    & adb shell am dumpheap --user $UserId $Pid /data/local/tmp/heap.hprof 2>&1 | Tee-Object -FilePath "$SceneDir/dumpheap.log" -Append
    $DumpWait = $DurationSec - $DumpDelay
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 等剩余 ${DumpWait}s..."
    Start-Sleep -Seconds $DumpWait
} else {
    Start-Sleep -Seconds $DurationSec
}

# ---------- 停止 profile ----------
$StopTime = (& adb shell date +%s.%N) -replace "\r|\n", ""
Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Profile stop time: $StopTime"
Push-Location $SceneDir
try {
    & adb shell am profile stop --user $UserId $Pid
} finally {
    Pop-Location
}
Start-Sleep -Seconds 2

# ---------- 拉 dumpheap ----------
if ($WithDumpheap) {
    $heapFile = Join-Path $SceneDir "heap.hprof"
    if (-not (Test-Path $heapFile)) {
        & adb pull /data/local/tmp/heap.hprof $heapFile 2>&1 | Tee-Object -FilePath "$SceneDir/dumpheap.log" -Append
    } else {
        Write-Host "[INFO] heap.hprof 已就绪: $((Get-Item $heapFile).Length / 1MB)MB"
    }
}

# ---------- trace 文件状态 ----------
$traceFile = Join-Path $SceneDir "trace.trace"
if (Test-Path $traceFile) {
    $traceSize = "{0:N1}MB" -f ((Get-Item $traceFile).Length / 1MB)
    Write-Host "[INFO] trace.trace: $traceSize"
} else {
    Write-Warning "trace.trace 没生成!可能是采样时间太短或进程已死"
}

# ---------- 写元信息 ----------
$meta = @{
    scene = $Scene
    package = $Package
    pid = $Pid
    user_id = $UserId
    duration_sec = $DurationSec
    with_dumpheap = [bool]$WithDumpheap
    device = @{
        model = $DeviceModel
        android_version = $AndroidVer
        sdk_int = [int]$SdkInt
    }
    time_alignment = @{
        profile_start_device_time = $BaseTime
        dumpheap_time = $DumpTime
        profile_stop_device_time = $StopTime
        host_collect_time = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    }
    files = @{
        trace = if (Test-Path $traceFile) { "trace.trace" } else { $null }
        heap  = if (Test-Path $heapFile) { "heap.hprof" } else { $null }
    }
} | ConvertTo-Json -Depth 5

$meta | Out-File -FilePath "$SceneDir/meta.json" -Encoding utf8

# ---------- 写 README ----------
@"
# am profile 采集 - $Scene

## 概述

| 项 | 值 |
|----|---|
| 场景 | $Scene |
| 包名 | $Package |
| PID | $Pid |
| 采样时长 | ${DurationSec}s |
| 联动 dumpheap | $(if ($WithDumpheap) { 'YES' } else { 'NO' }) |
| 设备 | $DeviceModel (Android $AndroidVer, SDK $SdkInt) |

## 时间对齐基准

| 事件 | 设备时间 |
|------|---------|
| profile start | $BaseTime |
| dumpheap | $DumpTime |
| profile stop | $StopTime |

## 文件清单

- `trace.trace`: ART sampling trace(用 Android Studio Profiler 打开)
- `heap.hprof`: Java 堆 dump(若触发,需要 hprof-conv 转换)
- `meta.json`: 元信息
- `*.log`: 执行日志

## 怎么分析

1. trace 分析: Android Studio → Profiler → Load trace
2. heap 分析: hprof-conv heap.hprof heap_mat.hprof → MAT 打开
3. 时间对齐: 配合 meta.json 的时间基准
"@ | Out-File -FilePath "$SceneDir/README.md" -Encoding utf8

Write-Host "==============================================="
Write-Host "  完成"
Write-Host "==============================================="
Write-Host "  输出目录: $SceneDir"
Write-Host "  文件清单:"
Get-ChildItem $SceneDir | ForEach-Object { Write-Host "    $($_.Name) ($([math]::Round($_.Length/1KB, 1))KB)" }
Write-Host "==============================================="