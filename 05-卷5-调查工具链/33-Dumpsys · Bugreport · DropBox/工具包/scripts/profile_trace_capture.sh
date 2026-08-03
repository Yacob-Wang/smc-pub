#!/usr/bin/env bash
# ==============================================================================
# profile_trace_capture.sh
#   自动触发 am profile 采样 + 自动归档 + 元信息记录
#
# 适用:Android 7.0+,adb 可用,目标 app debuggable 或 system app
#
# 用法:
#   ./profile_trace_capture.sh -p com.example.app -d 60 -s "cold_start_test"
#   ./profile_trace_capture.sh -p com.example.app -d 30 -a -s "stress_30s"   # 同时 dumpheap
#
# 参数:
#   -p  包名或 PID(必填)
#   -d  采样时长(秒,默认 30)
#   -s  场景描述(默认 "manual")
#   -a  同步触发 dumpheap(联动现场保留,默认 false)
#   -u  userId(多用户设备,默认 0)
#   -o  输出目录(默认 ./traces/)
#
# 产出:
#   traces/<时间戳>/<场景名>/
#     ├── trace.trace             am profile trace 文件
#     ├── heap.hprof              (若 -a 触发)Java 堆 dump
#     ├── meta.json               元信息(设备/包名/采样时长等)
#     └── README.md               本次采样说明
# ==============================================================================

set -euo pipefail

# ---------- 默认值 ----------
PKG=""
DURATION=30
SCENE="manual"
WITH_DUMPHEAP=0
USER_ID=0
OUTPUT_DIR="./traces"

# ---------- 参数解析 ----------
while getopts "p:d:s:au:o:h" opt; do
    case $opt in
        p) PKG="$OPTARG" ;;
        d) DURATION="$OPTARG" ;;
        s) SCENE="$OPTARG" ;;
        a) WITH_DUMPHEAP=1 ;;
        u) USER_ID="$OPTARG" ;;
        o) OUTPUT_DIR="$OPTARG" ;;
        h) cat <<EOF
Usage: $0 -p <pkg|pid> [-d duration_sec] [-s scene] [-a dumpheap] [-u userId] [-o output]

  -p  包名或 PID(必填)
  -d  采样时长(秒,默认 30)
  -s  场景描述(归档用,默认 manual)
  -a  同步触发 dumpheap(联动现场保留)
  -u  userId(默认 0)
  -o  输出目录(默认 ./traces/)
EOF
            exit 0 ;;
        *) echo "Unknown option: -$OPTARG"; exit 1 ;;
    esac
done

if [[ -z "$PKG" ]]; then
    echo "ERROR: 必须指定 -p <包名或 PID>" >&2
    exit 1
fi

# ---------- 前置检查 ----------
if ! command -v adb >/dev/null 2>&1; then
    echo "ERROR: adb 命令未找到,请配置 ANDROID_HOME/platform-tools 到 PATH" >&2
    exit 1
fi

# 检查设备连接
if ! adb devices | grep -q "device$"; then
    echo "ERROR: 没有连接的 adb 设备" >&2
    exit 1
fi

# ---------- 解析 PID ----------
PID="$PKG"
if [[ "$PKG" =~ ^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+$ ]]; then
    # 是包名格式,找 PID
    PID=$(adb shell pidof "$PKG" | tr -d '\r\n ')
    if [[ -z "$PID" ]]; then
        echo "ERROR: 找不到进程 $PKG 的 PID(可能 app 未启动)" >&2
        echo "提示: 先 adb shell am start -n $PKG/... 启动 app" >&2
        exit 1
    fi
    echo "[INFO] $PKG 的 PID = $PID"
fi

# ---------- 设备信息采集 ----------
DEVICE_MODEL=$(adb shell getprop ro.product.model | tr -d '\r\n')
ANDROID_VERSION=$(adb shell getprop ro.build.version.release | tr -d '\r\n')
SDK_INT=$(adb shell getprop ro.build.version.sdk | tr -d '\r\n')
KERNEL=$(adb shell uname -r | tr -d '\r\n')

# ---------- 输出目录 ----------
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SCENE_DIR="${OUTPUT_DIR}/${TIMESTAMP}/${SCENE}"
mkdir -p "$SCENE_DIR"

echo "==============================================="
echo "  am profile 自动化采集"
echo "==============================================="
echo "  目标进程   : $PKG (PID=$PID)"
echo "  采样时长   : ${DURATION}s"
echo "  场景描述   : $SCENE"
echo "  联动 dump  : $([ $WITH_DUMPHEAP -eq 1 ] && echo 'YES' || echo 'NO')"
echo "  设备       : $DEVICE_MODEL (Android $ANDROID_VERSION, SDK $SDK_INT)"
echo "  输出目录   : $SCENE_DIR"
echo "==============================================="

# ---------- 记录基准时间 ----------
BASE_TIME=$(adb shell date +%s.%N | tr -d '\r\n')
echo "[$(date +%H:%M:%S)] Profile start time: $BASE_TIME (device uptime ref)"

# ---------- 启动 profile ----------
adb shell am profile start --user "$USER_ID" "$PID" /data/local/tmp/trace.trace 2>&1 | tee "$SCENE_DIR/profile_start.log"
if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
    echo "ERROR: am profile start 失败" >&2
    exit 1
fi

# ---------- (可选)联动 dumpheap ----------
DUMP_TIME=""
if [[ $WITH_DUMPHEAP -eq 1 ]]; then
    # 在采样到一半时触发 dumpheap
    DUMP_DELAY=$((DURATION / 2))
    echo "[$(date +%H:%M:%S)] 等待 ${DUMP_DELAY}s 后触发 dumpheap..."
    sleep "$DUMP_DELAY"
    DUMP_TIME=$(adb shell date +%s.%N | tr -d '\r\n')
    echo "[$(date +%H:%M:%S)] Dump time: $DUMP_TIME"
    adb shell am dumpheap --user "$USER_ID" "$PID" /data/local/tmp/heap.hprof 2>&1 | tee "$SCENE_DIR/dumpheap.log"
    DUMP_WAIT=$((DURATION - DUMP_DELAY))
    echo "[$(date +%H:%M:%S)] 等剩余 ${DUMP_WAIT}s..."
    sleep "$DUMP_WAIT"
else
    sleep "$DURATION"
fi

# ---------- 停止 profile(自动 pull)----------
STOP_TIME=$(adb shell date +%s.%N | tr -d '\r\n')
echo "[$(date +%H:%M:%S)] Profile stop time: $STOP_TIME"
# am profile stop 会自动 pull trace.trace 到 adb 执行目录
# 我们切到 SCENE_DIR 再执行,确保归档位置正确
(cd "$SCENE_DIR" && adb shell am profile stop --user "$USER_ID" "$PID")
# 等待 pull 完成
sleep 2

# ---------- 拉 dumpheap 文件(若有)----------
if [[ $WITH_DUMPHEAP -eq 1 ]]; then
    if [[ -f "$SCENE_DIR/heap.hprof" ]]; then
        echo "[INFO] heap.hprof 已就绪: $(du -h "$SCENE_DIR/heap.hprof" | cut -f1)"
    else
        # am dumpheap 不会自动 pull,手动拉
        adb pull /data/local/tmp/heap.hprof "$SCENE_DIR/heap.hprof" 2>&1 | tee -a "$SCENE_DIR/dumpheap.log"
    fi
fi

# ---------- 重命名 trace 文件 ----------
if [[ -f "$SCENE_DIR/trace.trace" ]]; then
    TRACE_SIZE=$(du -h "$SCENE_DIR/trace.trace" | cut -f1)
    echo "[INFO] trace.trace: $TRACE_SIZE"
else
    echo "WARN: trace.trace 没生成!可能是采样时间太短或进程已死" >&2
    echo "      常见原因: 采样时间 < 5s,目标进程被杀,profile 路径错误" >&2
fi

# ---------- 写元信息 ----------
cat > "$SCENE_DIR/meta.json" <<EOF
{
  "scene": "$SCENE",
  "package": "$PKG",
  "pid": "$PID",
  "user_id": $USER_ID,
  "duration_sec": $DURATION,
  "with_dumpheap": $([ $WITH_DUMPHEAP -eq 1 ] && echo "true" || echo "false"),
  "device": {
    "model": "$DEVICE_MODEL",
    "android_version": "$ANDROID_VERSION",
    "sdk_int": $SDK_INT,
    "kernel": "$KERNEL"
  },
  "time_alignment": {
    "profile_start_device_time": "$BASE_TIME",
    "dumpheap_time": "$DUMP_TIME",
    "profile_stop_device_time": "$STOP_TIME",
    "host_collect_time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  },
  "files": {
    "trace": "$([ -f "$SCENE_DIR/trace.trace" ] && echo "trace.trace" || echo null)",
    "heap": "$([ -f "$SCENE_DIR/heap.hprof" ] && echo "heap.hprof" || echo null)"
  }
}
EOF

# ---------- 写 README ----------
cat > "$SCENE_DIR/README.md" <<EOF
# am profile 采集 - $SCENE

## 概述

| 项 | 值 |
|----|---|
| 场景 | $SCENE |
| 包名 | $PKG |
| PID | $PID |
| 采样时长 | ${DURATION}s |
| 联动 dumpheap | $([ $WITH_DUMPHEAP -eq 1 ] && echo 'YES' || echo 'NO') |
| 设备 | $DEVICE_MODEL (Android $ANDROID_VERSION, SDK $SDK_INT) |

## 时间对齐基准

| 事件 | 设备时间 |
|------|---------|
| profile start | $BASE_TIME |
| dumpheap | $DUMP_TIME |
| profile stop | $STOP_TIME |

## 文件清单

- \`trace.trace\`: ART sampling trace(可用 Android Studio Profiler 打开)
- \`heap.hprof\`: Java 堆 dump(若 -a 触发,需要 hprof-conv 转换才能用 MAT 打开)
- \`meta.json\`: 元信息
- \`*.log\`: 执行日志

## 怎么分析

1. **trace 分析**:
   - Android Studio → Profiler → Load trace
   - 或 \`traceview trace.trace\`

2. **heap 分析**(若有):
   - \`hprof-conv heap.hprof heap_mat.hprof\`
   - 用 MAT 打开 heap_mat.hprof

3. **时间对齐**(关键):
   - 配合 \`meta.json\` 的时间基准,做 CPU 热点 + 内存对象关联分析
EOF

echo "==============================================="
echo "  ✅ 完成"
echo "==============================================="
echo "  输出目录: $SCENE_DIR"
echo "  文件清单:"
ls -lh "$SCENE_DIR" | tail -n +2 | awk '{print "    " $NF " (" $5 ")"}'
echo "==============================================="