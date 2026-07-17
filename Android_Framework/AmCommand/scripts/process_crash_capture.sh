#!/bin/bash
# process_crash_capture.sh
# ============================================================
# 主动触发 crash 并采集完整现场
# 流程:拉 logcat → 触发 crash → 拉 dropsbox → 拉 tombstone → 拉 ANR
#
# 用法:
#   ./process_crash_capture.sh <package> [output_dir]
#   ./process_crash_capture.sh com.example.app
#   ./process_crash_capture.sh com.example.app ./crash_2024
#
# 基线:AOSP 14 + adb platform-tools 34.0.0+
# ============================================================

set -e

PKG="$1"
OUT_DIR="${2:-./crash_capture_$(date +%Y%m%d_%H%M%S)}"

# ---- 参数检查 ----
if [ -z "$PKG" ]; then
    cat <<EOF
用法: $0 <package> [output_dir]

参数:
  package    目标 app 包名(必填)
  output_dir 输出目录(可选,默认 ./crash_capture_TIMESTAMP)

示例:
  $0 com.example.app
  $0 com.example.app ./crash_2024
EOF
    exit 1
fi

# ---- 环境检查 ----
if ! command -v adb &> /dev/null; then
    echo "ERROR: adb 不在 PATH" >&2
    exit 1
fi

if ! adb get-state &> /dev/null; then
    echo "ERROR: 没有连接 adb 设备" >&2
    exit 1
fi

# ---- 创建输出目录 ----
mkdir -p "$OUT_DIR/tombstones" "$OUT_DIR/anr"
echo "=== 现场输出目录: $OUT_DIR ===" | tee "$OUT_DIR/SUMMARY.log"

# ---- Step 1: 拉当前 logcat(触发前) ----
echo "[1/6] 拉当前 logcat..." | tee -a "$OUT_DIR/SUMMARY.log"
adb logcat -c  # 清空 buffer
# 注意:此处不立即拉,先触发,再拉(避免 logcat 截断)
START_TIME=$(date +%s)
echo "  开始时间: $START_TIME" | tee -a "$OUT_DIR/SUMMARY.log"

# ---- Step 2: 触发 crash ----
echo "[2/6] 触发 am crash $PKG ..." | tee -a "$OUT_DIR/SUMMARY.log"
if ! adb shell am crash "$PKG"; then
    echo "  ERROR: am crash 执行失败" | tee -a "$OUT_DIR/SUMMARY.log"
    exit 1
fi
sleep 3  # 等 dropbox / traces 写入

# ---- Step 3: 拉 crash 后 logcat ----
echo "[3/6] 拉 crash 后 logcat..." | tee -a "$OUT_DIR/SUMMARY.log"
adb logcat -d -b all > "$OUT_DIR/logcat_after.log"
echo "  logcat 行数: $(wc -l < "$OUT_DIR/logcat_after.log")" | tee -a "$OUT_DIR/SUMMARY.log"

# ---- Step 4: 拉 dropbox ----
echo "[4/6] 拉 dropbox..." | tee -a "$OUT_DIR/SUMMARY.log"
if adb shell dumpsys dropbox --print > "$OUT_DIR/dropbox.log" 2>&1; then
    if [ -s "$OUT_DIR/dropbox.log" ]; then
        echo "  dropbox 行数: $(wc -l < "$OUT_DIR/dropbox.log")" | tee -a "$OUT_DIR/SUMMARY.log"
        # 提取和目标包相关的事件
        grep -A 5 "$PKG" "$OUT_DIR/dropbox.log" > "$OUT_DIR/dropbox_$PKG.log" 2>/dev/null || true
    else
        echo "  (dropbox 输出为空,可能需要 root)" | tee -a "$OUT_DIR/SUMMARY.log"
    fi
else
    echo "  (dropbox 需要 root 或 debug 包)" | tee -a "$OUT_DIR/SUMMARY.log"
fi

# ---- Step 5: 拉 tombstone / anr ----
echo "[5/6] 拉 tombstone / anr..." | tee -a "$OUT_DIR/SUMMARY.log"
if adb pull /data/tombstones/ "$OUT_DIR/tombstones/" 2>/dev/null; then
    TOMB_COUNT=$(ls "$OUT_DIR/tombstones/" 2>/dev/null | wc -l)
    echo "  tombstone 数量: $TOMB_COUNT" | tee -a "$OUT_DIR/SUMMARY.log"
else
    echo "  (tombstone 需要 root,或本次未触发 native crash)" | tee -a "$OUT_DIR/SUMMARY.log"
fi

if adb pull /data/anr/ "$OUT_DIR/anr/" 2>/dev/null; then
    ANR_COUNT=$(ls "$OUT_DIR/anr/" 2>/dev/null | wc -l)
    echo "  ANR 数量: $ANR_COUNT" | tee -a "$OUT_DIR/SUMMARY.log"
else
    echo "  (本次未触发 ANR 或 anr 不可读)" | tee -a "$OUT_DIR/SUMMARY.log"
fi

# ---- Step 6: 拉 dumpsys 快照 ----
echo "[6/6] 拉 dumpsys 快照..." | tee -a "$OUT_DIR/SUMMARY.log"
adb shell dumpsys activity processes > "$OUT_DIR/dumpsys_processes.log" 2>&1 || true
adb shell dumpsys meminfo "$PKG" > "$OUT_DIR/dumpsys_meminfo.log" 2>&1 || true
adb shell dumpsys activity activities > "$OUT_DIR/dumpsys_activities.log" 2>&1 || true

# ---- 生成报告 ----
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

cat > "$OUT_DIR/REPORT.md" <<EOF
# Crash 现场报告

- 包名: $PKG
- 触发时间: $(date -d @$START_TIME '+%Y-%m-%d %H:%M:%S')
- 触发耗时: ${DURATION}s
- 触发命令: am crash $PKG

## 关键文件

| 文件 | 用途 |
|------|------|
| \`logcat_after.log\` | crash 后的全 buffer logcat(关键) |
| \`dropbox.log\` | dropbox 事件(am_proc_died, system_app_crash 等) |
| \`dropbox_$PKG.log\` | 仅和 $PKG 相关的 dropbox 事件 |
| \`tombstones/\` | native crash 现场(若有) |
| \`anr/\` | ANR 现场(若有) |
| \`dumpsys_*.log\` | 系统状态快照 |

## 快速分析步骤

### Step 1: 确认死亡原因
\`\`\`bash
grep -E "FATAL|AndroidRuntime|am_proc_died" logcat_after.log
\`\`\`

### Step 2: 定位 Java 栈
\`\`\`bash
grep -A 30 "FATAL EXCEPTION" logcat_after.log
\`\`\`

### Step 3: 看 dropbox 上下文
\`\`\`bash
cat dropbox_$PKG.log
\`\`\`

### Step 4: 看 native 栈(若有)
\`\`\`bash
ls tombstones/
head -20 tombstones/tombstone_00
\`\`\`

### Step 5: 看 ANR(若有)
\`\`\`bash
ls anr/
head -50 anr/anr_*
\`\`\`

## 关键统计

- 触发耗时: ${DURATION}s
- logcat 大小: $(du -h "$OUT_DIR/logcat_after.log" | awk '{print $1}')
- dropbox 大小: $(du -h "$OUT_DIR/dropbox.log" 2>/dev/null | awk '{print $1}')

EOF

echo "" | tee -a "$OUT_DIR/SUMMARY.log"
echo "========================================" | tee -a "$OUT_DIR/SUMMARY.log"
echo "Crash 现场已采集到: $OUT_DIR" | tee -a "$OUT_DIR/SUMMARY.log"
echo "看 REPORT.md 了解快速分析步骤" | tee -a "$OUT_DIR/SUMMARY.log"
echo "========================================" | tee -a "$OUT_DIR/SUMMARY.log"
