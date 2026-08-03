#!/bin/bash
# OOM 日志解析脚本(Linux/Mac)
# 解析 logcat 中的 OOM 异常、LMKD 杀进程等内存相关事件
#
# 用法:
#   ./oom_log_analyzer.sh logcat.txt
#   ./oom_log_analyzer.sh logcat.txt -o output_dir
#   adb logcat -d | ./oom_log_analyzer.sh -
#
# 依赖:grep / awk / sort(Linux/Mac 标准工具)
#
# 配套文档:Android_Framework_Layer/Hprof/05-实战：内存监控体系搭建.md §4.4

set -e

# ====== 参数解析 ======
LOG_FILE="${1:-}"
OUTPUT_DIR="${2:-oom_analysis_$(date +%Y%m%d_%H%M%S)}"

if [ -z "$LOG_FILE" ]; then
    echo "用法: $0 <logcat_file> [output_dir]"
    echo "  或: adb logcat -d | $0 -"
    exit 1
fi

if [ "$LOG_FILE" != "-" ] && [ ! -f "$LOG_FILE" ]; then
    echo "✗ 文件不存在: $LOG_FILE"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

# ====== 颜色输出 ======
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== OOM 日志分析器 ===${NC}"
echo "输入: $LOG_FILE"
echo "输出: $OUTPUT_DIR"
echo ""

# ====== 1. 提取 OOM 异常 ======
echo -n "[1/6] 提取 OOM 异常 ... "
grep -E "OutOfMemoryError|Failed to allocate" "$LOG_FILE" > "$OUTPUT_DIR/oome_exceptions.txt" 2>/dev/null || true
OOM_COUNT=$(wc -l < "$OUTPUT_DIR/oome_exceptions.txt" 2>/dev/null || echo 0)
echo -e "${GREEN}✓${NC} ($OOM_COUNT 条)"

# ====== 2. 提取 OOM kill 事件 ======
echo -n "[2/6] 提取 OOM kill ... "
grep -E "Process.*has died.*OOM|has died (OOM)|kill.*oom_score" "$LOG_FILE" > "$OUTPUT_DIR/oom_kills.txt" 2>/dev/null || true
KILL_COUNT=$(wc -l < "$OUTPUT_DIR/oom_kills.txt" 2>/dev/null || echo 0)
echo -e "${GREEN}✓${NC} ($KILL_COUNT 条)"

# ====== 3. 提取 LMKD 事件 ======
echo -n "[3/6] 提取 LMKD 事件 ... "
grep -iE "lowmemorykiller|lmkd|low memory" "$LOG_FILE" > "$OUTPUT_DIR/lmkd_events.txt" 2>/dev/null || true
LMKD_COUNT=$(wc -l < "$OUTPUT_DIR/lmkd_events.txt" 2>/dev/null || echo 0)
echo -e "${GREEN}✓${NC} ($LMKD_COUNT 条)"

# ====== 4. 提取 onTrimMemory / onLowMemory ======
echo -n "[4/6] 提取 onTrimMemory 回调 ... "
grep -E "onTrimMemory|onLowMemory" "$LOG_FILE" > "$OUTPUT_DIR/trim_memory.txt" 2>/dev/null || true
TRIM_COUNT=$(wc -l < "$OUTPUT_DIR/trim_memory.txt" 2>/dev/null || echo 0)
echo -e "${GREEN}✓${NC} ($TRIM_COUNT 条)"

# ====== 5. 提取 ANR 事件 ======
echo -n "[5/6] 提取 ANR 事件 ... "
grep -E "ANR in|Application Not Responding|input dispatching timed out" "$LOG_FILE" > "$OUTPUT_DIR/anr_events.txt" 2>/dev/null || true
ANR_COUNT=$(wc -l < "$OUTPUT_DIR/anr_events.txt" 2>/dev/null || echo 0)
echo -e "${GREEN}✓${NC} ($ANR_COUNT 条)"

# ====== 6. 提取 GC 信息 ======
echo -n "[6/6] 提取 GC 信息 ... "
grep -E "GC freed|concurrent copying|Background concurrent|art.*Grow" "$LOG_FILE" > "$OUTPUT_DIR/gc_events.txt" 2>/dev/null || true
GC_COUNT=$(wc -l < "$OUTPUT_DIR/gc_events.txt" 2>/dev/null || echo 0)
echo -e "${GREEN}✓${NC} ($GC_COUNT 条)"

# ====== 统计汇总 ======
echo ""
echo -e "${GREEN}=== 统计汇总 ===${NC}"
echo "OOM 异常:    $OOM_COUNT 条"
echo "OOM kill:    $KILL_COUNT 条"
echo "LMKD 事件:   $LMKD_COUNT 条"
echo "onTrimMemory: $TRIM_COUNT 条"
echo "ANR 事件:    $ANR_COUNT 条"
echo "GC 事件:     $GC_COUNT 条"
echo ""

# ====== TOP 10 统计 ======
echo -e "${GREEN}=== TOP 10 OOM 异常类型 ===${NC}"
if [ $OOM_COUNT -gt 0 ]; then
    grep -oE "OutOfMemoryError[^:]*" "$LOG_FILE" 2>/dev/null | sort | uniq -c | sort -rn | head -10
else
    echo "(无)"
fi
echo ""

echo -e "${GREEN}=== TOP 10 OOM kill 进程 ===${NC}"
if [ $KILL_COUNT -gt 0 ]; then
    grep -oE "Process [a-zA-Z0-9._]+ has died" "$LOG_FILE" 2>/dev/null | sort | uniq -c | sort -rn | head -10
else
    echo "(无)"
fi
echo ""

echo -e "${GREEN}=== TOP 10 ANR 进程 ===${NC}"
if [ $ANR_COUNT -gt 0 ]; then
    grep -oE "ANR in [a-zA-Z0-9._]+" "$LOG_FILE" 2>/dev/null | sort | uniq -c | sort -rn | head -10
else
    echo "(无)"
fi
echo ""

# ====== 时间分布(可选) ======
echo -e "${GREEN}=== OOM 时间分布(按小时) ===${NC}"
if [ $OOM_COUNT -gt 0 ]; then
    grep -E "OutOfMemoryError" "$LOG_FILE" 2>/dev/null | grep -oE "[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}" | cut -d' ' -f2 | cut -d':' -f1 | sort | uniq -c
else
    echo "(无)"
fi
echo ""

# ====== 总结建议 ======
echo -e "${GREEN}=== 分析建议 ===${NC}"

if [ $OOM_COUNT -gt 0 ]; then
    echo -e "${YELLOW}⚠ 检测到 $OOM_COUNT 个 OOM 异常${NC}"
    echo "  建议:用 perfetto_heapprofd 配置模板(perfetto_hprof.pbtxt)抓 native trace"
    echo "  或用 LeakCanary 灰度包捕获 hprof"
fi

if [ $KILL_COUNT -gt 10 ]; then
    echo -e "${YELLOW}⚠ OOM kill 次数过多($KILL_COUNT 次)${NC}"
    echo "  建议:检查 dumpsys meminfo,定位内存大头(Java/Native/Graphics)"
fi

if [ $LMKD_COUNT -gt 50 ]; then
    echo -e "${YELLOW}⚠ LMKD 杀进程频繁($LMKD_COUNT 次)${NC}"
    echo "  建议:优化 onTrimMemory 回调,主动释放内存"
fi

echo ""
echo -e "${GREEN}=== 输出文件 ===${NC}"
ls -la "$OUTPUT_DIR"/ | tail -n +2

echo ""
echo -e "${GREEN}✓ 分析完成${NC}"