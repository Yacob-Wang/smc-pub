#!/bin/bash
# monitor_logcat.sh
# ============================================================
# am monitor 的 logcat 替代方案(脚本化)
# 把 ActivityManager 事件流重定向到文件,适合压测期间后台观察
#
# 用法:
#   ./monitor_logcat.sh <package> [output_file] [duration_seconds]
#   ./monitor_logcat.sh com.example.app ./monitor.log 60
#   ./monitor_logcat.sh com.example.app  # 默认 ./monitor_<ts>.log,无限时长
#
# 基线:AOSP 14 + adb platform-tools 34.0.0+
# ============================================================

set -e

# ---- 工具函数:打印统计 ----
print_stats() {
    local file="$1"
    if [ ! -f "$file" ]; then
        return
    fi
    local gc_count=$(grep -c "GC:" "$file" 2>/dev/null || echo "0")
    local anr_count=$(grep -c "ANR in $PKG" "$file" 2>/dev/null || echo "0")
    local crash_count=$(grep -c "FATAL EXCEPTION" "$file" 2>/dev/null || echo "0")
    local lmk_count=$(grep -c "Low on memory" "$file" 2>/dev/null || echo "0")
    local died_count=$(grep -c "has died" "$file" 2>/dev/null || echo "0")

    echo "========================================"
    echo "  监控统计"
    echo "========================================"
    echo "  GC 次数:    $gc_count"
    echo "  ANR 次数:   $anr_count"
    echo "  Crash 次数: $crash_count"
    echo "  LMK 次数:   $lmk_count"
    echo "  进程死亡:   $died_count"
    echo "========================================"
    echo "  输出文件: $file"
    echo "========================================"
}

# ---- 参数解析 ----
PKG="$1"
OUT_FILE="${2:-./monitor_$(date +%Y%m%d_%H%M%S).log}"
DURATION="${3:-0}"  # 0 = 无限

# ---- 帮助 ----
if [ -z "$PKG" ]; then
    cat <<EOF
用法: $0 <package> [output_file] [duration_seconds]

参数:
  package          目标 app 包名(必填)
  output_file      输出文件(可选,默认 ./monitor_TIMESTAMP.log)
  duration_seconds 监控时长(可选,默认 0=无限,直到 Ctrl+C)

示例:
  $0 com.example.app
  $0 com.example.app ./monitor.log 60

事件类型:
  - GC  (ActivityManager: GC: ...)
  - ANR (ANR in <pkg>)
  - Crash (FATAL EXCEPTION / signal 11)
  - LMK  (Low on memory)
  - Process died (Process ... has died)

EOF
    exit 1
fi

# ---- 环境检查 ----
if ! command -v adb &> /dev/null; then
    echo "ERROR: adb 不在 PATH" >&2
    exit 1
fi

# ---- 清空 logcat ----
adb logcat -c

# ---- 启动 monitor(后台) ----
echo "=== 启动 monitor ==="
echo "  包名: $PKG"
echo "  输出: $OUT_FILE"
echo "  时长: ${DURATION}s(0=无限)"
echo ""
echo "事件类型: GC / ANR / Crash / LMK / Process died"
echo "按 Ctrl+C 停止"
echo ""

# 后台 logcat 到文件
adb logcat -v time -s ActivityManager:I AndroidRuntime:E libc:E DEBUG:E "*:S" > "$OUT_FILE" 2>&1 &
LOG_PID=$!

# 清理函数
cleanup() {
    kill $LOG_PID 2>/dev/null || true
    echo ""
    echo "=== 监控停止 ==="
    print_stats "$OUT_FILE"
}

# 监控时长
if [ "$DURATION" -gt 0 ]; then
    trap cleanup EXIT INT TERM
    sleep "$DURATION"
else
    # 无限模式
    trap cleanup INT TERM
    wait $LOG_PID
fi
