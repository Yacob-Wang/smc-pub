<#
.SYNOPSIS
    OOM 日志解析脚本(Windows PowerShell)

.DESCRIPTION
    解析 logcat 中的 OOM 异常、LMKD 杀进程等内存相关事件

.PARAMETER LogFile
    logcat 文件路径,或 "-" 表示从管道读取

.PARAMETER OutputDir
    输出目录(默认: oom_analysis_<timestamp>)

.EXAMPLE
    .\oom_log_analyzer.ps1 -LogFile logcat.txt
    .\oom_log_analyzer.ps1 -LogFile logcat.txt -OutputDir custom_out
    adb logcat -d | .\oom_log_analyzer.ps1 -LogFile -

.NOTES
    配套文档:Android_Framework_Layer/Hprof/05-实战：内存监控体系搭建.md §4.4
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$LogFile,
    
    [string]$OutputDir = ""
)

# ====== 颜色输出 ======
function Write-Success { param($msg) Write-Host $msg -ForegroundColor Green }
function Write-Error { param($msg) Write-Host $msg -ForegroundColor Red }
function Write-Warning { param($msg) Write-Host $msg -ForegroundColor Yellow }

# ====== 参数处理 ======
if (-not $OutputDir) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputDir = "oom_analysis_$timestamp"
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

# 处理管道输入
$tempFile = $null
if ($LogFile -eq "-") {
    $tempFile = [System.IO.Path]::GetTempFileName()
    $input | Out-File -FilePath $tempFile -Encoding UTF8
    $LogFile = $tempFile
}

if (-not (Test-Path $LogFile)) {
    Write-Error "✗ 文件不存在: $LogFile"
    exit 1
}

Write-Host "=== OOM 日志分析器 ===" -ForegroundColor Green
Write-Host "输入: $LogFile"
Write-Host "输出: $OutputDir"
Write-Host ""

# ====== 1. OOM 异常 ======
Write-Host -NoNewline "[1/6] 提取 OOM 异常 ... "
$oomeFile = Join-Path $OutputDir "oome_exceptions.txt"
Select-String -Path $LogFile -Pattern "OutOfMemoryError|Failed to allocate" | 
    ForEach-Object { $_.Line } | Out-File -FilePath $oomeFile -Encoding UTF8
$oomCount = (Get-Content $oomeFile | Measure-Object -Line).Lines
Write-Success "✓ ($oomCount 条)"

# ====== 2. OOM kill ======
Write-Host -NoNewline "[2/6] 提取 OOM kill ... "
$killFile = Join-Path $OutputDir "oom_kills.txt"
Select-String -Path $LogFile -Pattern "Process.*has died.*OOM|has died \(OOM\)|kill.*oom_score" |
    ForEach-Object { $_.Line } | Out-File -FilePath $killFile -Encoding UTF8
$killCount = (Get-Content $killFile | Measure-Object -Line).Lines
Write-Success "✓ ($killCount 条)"

# ====== 3. LMKD 事件 ======
Write-Host -NoNewline "[3/6] 提取 LMKD 事件 ... "
$lmkdFile = Join-Path $OutputDir "lmkd_events.txt"
Select-String -Path $LogFile -Pattern "lowmemorykiller|lmkd|low memory" -CaseSensitive:$false |
    ForEach-Object { $_.Line } | Out-File -FilePath $lmkdFile -Encoding UTF8
$lmkdCount = (Get-Content $lmkdFile | Measure-Object -Line).Lines
Write-Success "✓ ($lmkdCount 条)"

# ====== 4. onTrimMemory ======
Write-Host -NoNewline "[4/6] 提取 onTrimMemory 回调 ... "
$trimFile = Join-Path $OutputDir "trim_memory.txt"
Select-String -Path $LogFile -Pattern "onTrimMemory|onLowMemory" |
    ForEach-Object { $_.Line } | Out-File -FilePath $trimFile -Encoding UTF8
$trimCount = (Get-Content $trimFile | Measure-Object -Line).Lines
Write-Success "✓ ($trimCount 条)"

# ====== 5. ANR 事件 ======
Write-Host -NoNewline "[5/6] 提取 ANR 事件 ... "
$anrFile = Join-Path $OutputDir "anr_events.txt"
Select-String -Path $LogFile -Pattern "ANR in|Application Not Responding|input dispatching timed out" |
    ForEach-Object { $_.Line } | Out-File -FilePath $anrFile -Encoding UTF8
$anrCount = (Get-Content $anrFile | Measure-Object -Line).Lines
Write-Success "✓ ($anrCount 条)"

# ====== 6. GC 信息 ======
Write-Host -NoNewline "[6/6] 提取 GC 信息 ... "
$gcFile = Join-Path $OutputDir "gc_events.txt"
Select-String -Path $LogFile -Pattern "GC freed|concurrent copying|Background concurrent|art.*Grow" |
    ForEach-Object { $_.Line } | Out-File -FilePath $gcFile -Encoding UTF8
$gcCount = (Get-Content $gcFile | Measure-Object -Line).Lines
Write-Success "✓ ($gcCount 条)"

# ====== 汇总 ======
Write-Host ""
Write-Host "=== 统计汇总 ===" -ForegroundColor Green
Write-Host "OOM 异常:     $oomCount 条"
Write-Host "OOM kill:     $killCount 条"
Write-Host "LMKD 事件:    $lmkdCount 条"
Write-Host "onTrimMemory: $trimCount 条"
Write-Host "ANR 事件:     $anrCount 条"
Write-Host "GC 事件:      $gcCount 条"
Write-Host ""

# ====== TOP 10 统计 ======
Write-Host "=== TOP 10 OOM 异常类型 ===" -ForegroundColor Green
if ($oomCount -gt 0) {
    Get-Content $oomeFile | 
        Select-String -Pattern "OutOfMemoryError[^:]*" -AllMatches |
        ForEach-Object { $_.Matches[0].Value } |
        Group-Object | Sort-Object Count -Descending | Select-Object -First 10 |
        ForEach-Object { "{0,5} {1}" -f $_.Count, $_.Name }
} else {
    Write-Host "(无)"
}
Write-Host ""

Write-Host "=== TOP 10 OOM kill 进程 ===" -ForegroundColor Green
if ($killCount -gt 0) {
    Get-Content $killFile |
        Select-String -Pattern "Process [a-zA-Z0-9._]+ has died" -AllMatches |
        ForEach-Object { $_.Matches[0].Value } |
        Group-Object | Sort-Object Count -Descending | Select-Object -First 10 |
        ForEach-Object { "{0,5} {1}" -f $_.Count, $_.Name }
} else {
    Write-Host "(无)"
}
Write-Host ""

# ====== 建议 ======
Write-Host "=== 分析建议 ===" -ForegroundColor Green

if ($oomCount -gt 0) {
    Write-Warning "⚠ 检测到 $oomCount 个 OOM 异常"
    Write-Host "  建议:用 perfetto_heapprofd 配置模板(perfetto_hprof.pbtxt)抓 native trace"
    Write-Host "  或用 LeakCanary 灰度包捕获 hprof"
}

if ($killCount -gt 10) {
    Write-Warning "⚠ OOM kill 次数过多($killCount 次)"
    Write-Host "  建议:检查 dumpsys meminfo,定位内存大头(Java/Native/Graphics)"
}

if ($lmkdCount -gt 50) {
    Write-Warning "⚠ LMKD 杀进程频繁($lmkdCount 次)"
    Write-Host "  建议:优化 onTrimMemory 回调,主动释放内存"
}

Write-Host ""
Write-Success "✓ 分析完成,结果在: $OutputDir"

# 清理临时文件
if ($tempFile) {
    Remove-Item $tempFile -Force
}