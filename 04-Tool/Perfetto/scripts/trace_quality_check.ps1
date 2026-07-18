# 文件路径:Android_Framework_Layer/Perfetto/scripts/trace_quality_check.ps1
# 场景:trace 完整性 + 关键事件验证(Windows 兼容版)
# 用法:.\trace_quality_check.ps1 -TraceFile "anr_031723.pftrace"

param(
    [Parameter(Mandatory=$true)]
    [string]$TraceFile
)

Write-Host "=== Perfetto Trace 质量检查 ==="
Write-Host "文件: $TraceFile"
Write-Host ""

# 1. 文件存在性
if (-not (Test-Path $TraceFile)) {
    Write-Error "trace 文件不存在: $TraceFile"
    exit 1
}
Write-Host "OK 文件存在"

# 2. 文件大小
$size = (Get-Item $TraceFile).Length
$sizeMB = [math]::Round($size / 1MB, 2)
Write-Host "大小: $sizeMB MB"

if ($size -lt 1MB) {
    Write-Warning "文件过小(< 1MB),可能数据源没匹配"
}
if ($size -gt 100MB) {
    Write-Warning "文件过大(> 100MB),可能 buffer 配置过大"
}

# 3. trace_processor 检查
$tp = (Get-Command trace_processor -ErrorAction SilentlyContinue)
if (-not $tp) {
    Write-Host ""
    Write-Warning "trace_processor 未安装,跳过详细检查"
    Write-Host "    安装:https://perfetto.dev/docs/quickstart/trace-processor"
    Write-Host ""
    Write-Host "=== 检查完成 ==="
    exit 0
}

Write-Host ""
Write-Host "关键事件统计:"
$query = @"
SELECT
  (SELECT COUNT(*) FROM slice WHERE name LIKE '%binder%') AS binder_events,
  (SELECT COUNT(*) FROM slice WHERE name LIKE '%AMS%' OR name LIKE '%am%') AS ams_events,
  (SELECT COUNT(*) FROM slice WHERE name LIKE '%WMS%' OR name LIKE '%wm%') AS wms_events,
  (SELECT COUNT(*) FROM slice WHERE name LIKE '%input%') AS input_events,
  (SELECT COUNT(*) FROM ftrace_events WHERE name = 'sched_switch') AS sched_events,
  (SELECT COUNT(*) FROM ftrace_events WHERE name LIKE 'block_%') AS block_events,
  (SELECT COUNT(*) FROM process WHERE name != '') AS process_count
"@
$result = & trace_processor --query-file $query $TraceFile 2>&1
Write-Host "  $result"

Write-Host ""
Write-Host "数据源完整性:"
$query2 = @"
SELECT
  (SELECT COUNT(*) > 0 FROM ftrace_events) AS has_ftrace,
  (SELECT COUNT(*) > 0 FROM slice WHERE name LIKE 'atrace%' OR depth > 0) AS has_atrace,
  (SELECT COUNT(*) > 0 FROM process_stats) AS has_process_stats,
  (SELECT COUNT(*) > 0 FROM sched WHERE ts > 0) AS has_sched
"@
$result2 = & trace_processor --query-file $query2 $TraceFile 2>&1
Write-Host "  $result2"

Write-Host ""
Write-Host "=== 检查完成 ==="
Write-Host ""
Write-Host "排查建议:"
Write-Host "  - binder_events = 0 -> 没启用 atrace(binder)"
Write-Host "  - ams_events = 0 -> 没启用 atrace(am)"
Write-Host "  - sched_events < 100 -> 数据源被覆盖或时长太短"
Write-Host "  - has_ftrace = 0 -> ftrace 数据源配置错误"
Write-Host "  - has_atrace = 0 -> atrace 类目没启用"
