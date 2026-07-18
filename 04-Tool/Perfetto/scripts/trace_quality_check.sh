#!/bin/bash
# 文件路径:Android_Framework_Layer/Perfetto/scripts/trace_quality_check.sh
# 场景:trace 完整性 + 关键事件验证
# 用法:./trace_quality_check.sh <trace.pftrace>

set -e

if [ -z "$1" ]; then
    echo "用法: $0 <trace.pftrace>"
    echo "示例: $0 /tmp/anr_031723.pftrace"
    exit 1
fi

TRACE_FILE="$1"

echo "=== Perfetto Trace 质量检查 ==="
echo "文件: $TRACE_FILE"
echo

# 1. 文件存在性
if [ ! -f "$TRACE_FILE" ]; then
    echo "❌ trace 文件不存在"
    exit 1
fi
echo "✅ 文件存在"

# 2. 文件大小
SIZE=$(stat -c %s "$TRACE_FILE" 2>/dev/null || stat -f %z "$TRACE_FILE")
SIZE_MB=$(echo "scale=2; $SIZE/1024/1024" | bc)
echo "大小: ${SIZE_MB} MB"

if [ "$SIZE" -lt 1048576 ]; then
    echo "⚠️  文件过小(< 1MB),可能数据源没匹配"
fi
if [ "$SIZE" -gt 104857600 ]; then
    echo "⚠️  文件过大(> 100MB),可能 buffer 配置过大"
fi

# 3. trace_processor 关键事件统计
TP=$(which trace_processor 2>/dev/null || echo "")
if [ -z "$TP" ]; then
    echo
    echo "⚠️  trace_processor 未安装,跳过详细检查"
    echo "    安装:https://perfetto.dev/docs/quickstart/trace-processor"
    echo
    echo "=== 检查完成 ==="
    exit 0
fi

echo
echo "关键事件统计:"
"${TP}" --query-file "
SELECT
  (SELECT COUNT(*) FROM slice WHERE name LIKE '%binder%') AS binder_events,
  (SELECT COUNT(*) FROM slice WHERE name LIKE '%AMS%' OR name LIKE '%am%') AS ams_events,
  (SELECT COUNT(*) FROM slice WHERE name LIKE '%WMS%' OR name LIKE '%wm%') AS wms_events,
  (SELECT COUNT(*) FROM slice WHERE name LIKE '%input%') AS input_events,
  (SELECT COUNT(*) FROM ftrace_events WHERE name = 'sched_switch') AS sched_events,
  (SELECT COUNT(*) FROM ftrace_events WHERE name LIKE 'block_%') AS block_events,
  (SELECT COUNT(*) FROM process WHERE name != '') AS process_count
" "$TRACE_FILE" 2>&1 || echo "  (trace_processor 执行失败,可能 trace 格式问题)"

echo
echo "数据源完整性检查:"
"${TP}" --query-file "
SELECT
  (SELECT COUNT(*) > 0 FROM ftrace_events) AS has_ftrace,
  (SELECT COUNT(*) > 0 FROM slice WHERE name LIKE 'atrace%' OR depth > 0) AS has_atrace,
  (SELECT COUNT(*) > 0 FROM process_stats) AS has_process_stats,
  (SELECT COUNT(*) > 0 FROM sched WHERE ts > 0) AS has_sched
" "$TRACE_FILE" 2>&1 || echo "  (执行失败)"

echo
echo "=== 检查完成 ==="
echo
echo "排查建议:"
echo "  - binder_events = 0 → 没启用 atrace(binder) 或 android.atrace 数据源"
echo "  - ams_events = 0 → 没启用 atrace(am)"
echo "  - sched_events < 100 → 数据源被覆盖或时长太短"
echo "  - has_ftrace = 0 → ftrace 数据源配置错误"
echo "  - has_atrace = 0 → atrace 类目没启用或拼写错误"
