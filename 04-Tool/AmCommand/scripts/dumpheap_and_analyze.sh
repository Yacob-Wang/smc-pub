#!/bin/bash
# dumpheap_and_analyze.sh
# ============================================================
# 端到端 am dumpheap 自动化脚本
# 流程:触发 dump → pull → hprof-conv 转换 → 准备 MAT
#
# 用法:
#   ./dumpheap_and_analyze.sh <package> [output_dir] [userId]
#   ./dumpheap_and_analyze.sh com.example.app
#   ./dumpheap_and_analyze.sh com.example.app ./heap_dumps
#   ./dumpheap_and_analyze.sh com.example.app ./heap_dumps 0
#
# 依赖:
#   - adb 已配 PATH
#   - ANDROID_HOME 环境变量已设(指向 SDK 根)
#   - hprof-conv 在 $ANDROID_HOME/platform-tools/
#
# 基线:AOSP 14 + adb platform-tools 34.0.0+
# ============================================================

set -e

# ---- 参数解析 ----
PKG="$1"
OUT_DIR="${2:-./heap_dumps}"
USER_ID="${3:-}"

if [ -z "$PKG" ]; then
    cat <<EOF
用法: $0 <package> [output_dir] [userId]

参数:
  package    目标 app 包名(必填)
  output_dir 输出目录(可选,默认 ./heap_dumps)
  userId     Android user id(可选,默认空 = 当前)

示例:
  $0 com.example.app
  $0 com.example.app ./dumps 0

环境要求:
  ANDROID_HOME=/path/to/Android/Sdk
EOF
    exit 1
fi

# ---- 环境检查 ----
if ! command -v adb &> /dev/null; then
    echo "ERROR: adb 不在 PATH"
    exit 1
fi

if [ -z "$ANDROID_HOME" ]; then
    echo "ERROR: ANDROID_HOME 未设置"
    echo "  export ANDROID_HOME=/path/to/Android/Sdk"
    exit 1
fi

HPROF_CONV="$ANDROID_HOME/platform-tools/hprof-conv"
if [ ! -x "$HPROF_CONV" ]; then
    echo "ERROR: hprof-conv 不在 $HPROF_CONV"
    echo "  请安装 Android SDK platform-tools"
    exit 1
fi

# 检查设备
if ! adb get-state &> /dev/null; then
    echo "ERROR: 没有连接 adb 设备"
    exit 1
fi

# ---- 创建输出目录 ----
mkdir -p "$OUT_DIR"
TS=$(date +%Y%m%d_%H%M%S)
HEAP_FILE="/data/local/tmp/heap_${TS}.hprof"
LOCAL_FILE="$OUT_DIR/heap_${TS}.hprof"
CONVERTED="$OUT_DIR/heap_${TS}_mat.hprof"

# ---- Step 1: 找 PID ----
echo "=== [1/5] 查找目标进程 $PKG ==="
if [ -n "$USER_ID" ]; then
    PID=$(adb shell "pidof $PKG" --user "$USER_ID" 2>/dev/null | tr -d '\r\n')
else
    PID=$(adb shell "pidof $PKG" | tr -d '\r\n')
fi

if [ -z "$PID" ]; then
    echo "ERROR: 进程 $PKG 未运行"
    echo "  当前进程列表:"
    adb shell ps -A | head -20
    exit 1
fi
echo "  PID: $PID"

# 显示进程状态
echo "  进程信息:"
adb shell ps -A | grep "$PKG" | head -3

# ---- Step 2: 触发 dump ----
echo ""
echo "=== [2/5] 触发 am dumpheap ==="
echo "  目标: $HEAP_FILE"
echo "  警告:app 会卡顿 5-30 秒(dump 期间 ANR 告警属正常)"

# 拼装命令(支持 -n userId)
if [ -n "$USER_ID" ]; then
    DUMP_CMD="am dumpheap -n $USER_ID $PID $HEAP_FILE"
else
    DUMP_CMD="am dumpheap $PID $HEAP_FILE"
fi

START_TIME=$(date +%s)
if ! adb shell "$DUMP_CMD"; then
    echo "ERROR: am dumpheap 执行失败"
    echo "  常见原因:"
    echo "    1) 权限不足:需要 DUMP 权限(adb shell 默认有)"
    echo "    2) 进程已死:重新 pidof 拿最新 pid"
    echo "    3) SELinux 拒绝:adb shell setenforce 0"
    exit 1
fi
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo "  完成,耗时: ${DURATION}s"

# ---- Step 3: pull 文件 ----
echo ""
echo "=== [3/5] 拉取文件到本地 ==="
# 等文件系统刷盘
sleep 1

REMOTE_SIZE=$(adb shell "ls -l $HEAP_FILE" 2>/dev/null | awk '{print $4}' | tr -d '\r\n')
if [ -z "$REMOTE_SIZE" ] || [ "$REMOTE_SIZE" = "0" ]; then
    echo "ERROR: 远程文件 $HEAP_FILE 不存在或大小为 0"
    echo "  可能 dump 提前失败,查看 logcat:"
    echo "    adb logcat -d | grep -E 'art|debug'"
    exit 1
fi
echo "  远程文件大小: $((REMOTE_SIZE / 1024 / 1024)) MB"

if ! adb pull "$HEAP_FILE" "$LOCAL_FILE"; then
    echo "ERROR: 拉取失败"
    exit 1
fi
echo "  本地路径: $LOCAL_FILE"
echo "  本地大小: $(ls -lh "$LOCAL_FILE" | awk '{print $5}')"

# ---- Step 4: hprof-conv 转换 ----
echo ""
echo "=== [4/5] hprof-conv 转换 ==="
if ! "$HPROF_CONV" "$LOCAL_FILE" "$CONVERTED"; then
    echo "ERROR: hprof-conv 转换失败"
    echo "  可能原因:文件截断(被信号中断)"
    exit 1
fi
echo "  转换后: $CONVERTED"
echo "  大小: $(ls -lh "$CONVERTED" | awk '{print $5}')"

# ---- Step 5: 清理 + 报告 ----
echo ""
echo "=== [5/5] 清理设备文件 + 输出报告 ==="
adb shell rm -f "$HEAP_FILE"

# 提取 OQL 模板到文件
OQL_FILE="$OUT_DIR/oom_queries_${TS}.txt"
cat > "$OQL_FILE" <<'EOF'
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
FROM java.lang.Class $cls
WHERE $cls.name LIKE "com.example.app.%"
   , $cls.classLoader != null
   , c = classof($cls).staticField
   , c.@reference != null

// 5. 找所有 Fragment
SELECT * FROM androidx.fragment.app.Fragment
EOF

cat <<EOF

========================================
  Dump 完成!
========================================
原始文件:  $LOCAL_FILE
MAT 文件:  $CONVERTED  ← 用 MAT 打开这个
OQL 模板:  $OQL_FILE
dump 耗时:  ${DURATION}s
目标 PID:  $PID
用户 ID:   ${USER_ID:-default(0)}

下一步:
  1. 用 MAT(Eclipse Memory Analyzer)打开 $CONVERTED
     - Leak Suspects Report(自动疑似泄漏)
     - Dominator Tree(看谁占内存最多)
     - Histogram(按类看实例数)
  2. 把 $OQL_FILE 里的 OQL 复制到 MAT 的 OQL 面板
  3. 对比多次 dump 的差集,看哪些对象在累积

参考本系列:
  - 04 §9 案例库
  - Hprof 系列 02(hprof 工具链)
  - Hprof 系列 04(内存泄漏 SOP)

========================================
EOF
