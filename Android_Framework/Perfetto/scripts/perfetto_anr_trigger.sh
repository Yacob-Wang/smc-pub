# 文件路径:Android_Framework_Layer/Perfetto/scripts/perfetto_anr_trigger.sh
# 场景:手动触发 Perfetto ANR 抓取(测试用)
# 用法:./perfetto_anr_trigger.sh [trigger_name]

set -e

TRIGGER_NAME="${1:-anr_input_observer}"

echo "=== 手动触发 Perfetto ANR 抓取 ==="
echo "Trigger: $TRIGGER_NAME"
echo

# 检查设备
if ! adb devices | grep -q "device$"; then
    echo "❌ 没有连接的设备"
    exit 1
fi

# 检查 trigger 是否存在
echo "Step 1: 检查 trigger 配置..."
TRACED_STATUS=$(adb shell dumpsys traced 2>/dev/null || echo "")
if echo "$TRACED_STATUS" | grep -q "$TRIGGER_NAME"; then
    echo "✅ trigger '$TRIGGER_NAME' 已注册"
else
    echo "⚠️  trigger '$TRIGGER_NAME' 未注册"
    echo "    请先部署 trigger 配置(参考 04 篇 §8.2)"
fi
echo

# 触发
echo "Step 2: 触发 Perfetto 抓取..."
adb shell perfetto --trigger "$TRIGGER_NAME"
echo "✅ trigger 已发送"
echo

# 等待 trace 完成(根据 stop_ms)
echo "Step 3: 等待 trace 落盘..."
WAIT_TIME=35  # 默认 30s stop_ms + 5s 余量
echo "    等待 ${WAIT_TIME}s..."
sleep $WAIT_TIME
echo

# 拉取 trace
echo "Step 4: 拉取最新 trace..."
LATEST_TRACE=$(adb shell ls -t /data/misc/perfetto-traces/ | head -1 | tr -d '\r')
if [ -n "$LATEST_TRACE" ]; then
    adb pull "/data/misc/perfetto-traces/$LATEST_TRACE" /tmp/
    echo "✅ trace 已拉取:/tmp/$LATEST_TRACE"
    echo
    echo "Step 5: 质量检查..."
    ./trace_quality_check.sh "/tmp/$LATEST_TRACE"
else
    echo "❌ 未找到 trace 文件"
    exit 1
fi

echo
echo "=== 完成 ==="
