# am_command_configs/am_start_params.md

> **配套文章**:[01-am命令全景与Activity触发 §4.2 五大参数矩阵](../01-am命令全景与Activity触发.md#42-五大参数矩阵)
> **基线**:AOSP `android-14.0.0_r1`

`am start-activity` 参数速查表,按"日常用得多"排序。

---

## 1. 常用组合模板

### 1.1 启动 launcher 主页面

```bash
adb shell am start-activity \
  -a android.intent.action.MAIN \
  -c android.intent.category.LAUNCHER \
  -n com.example.app/.ui.MainActivity
```

### 1.2 直达深链路页面(带参数)

```bash
adb shell am start-activity \
  -n com.example.app/.ui.detail.OrderDetailActivity \
  --es orderId "ORDER_20240622_001" \
  --ei fromPush 1 \
  --ez isVip true \
  -f 0x14000000 \
  -W
```

### 1.3 启动 + 测冷启动耗时

```bash
adb shell am start-activity -W -n com.example.app/.ui.MainActivity
# 输出 TotalTime: <ms>
```

### 1.4 重启 app(模拟冷启动)

```bash
adb shell am force-stop com.example.app
sleep 1
adb shell am start-activity -W -n com.example.app/.ui.MainActivity
```

### 1.5 触发 trim memory(模拟低内存)

```bash
# 触发 TRIM_MEMORY_RUNNING_LOW
adb shell am send-trim-memory <pid> RUNNING_LOW

# 触发 TRIM_MEMORY_BACKGROUND
adb shell am send-trim-memory <pid> BACKGROUND

# 触发 TRIM_MEMORY_COMPLETE
adb shell am send-trim-memory <pid> COMPLETE
```

### 1.6 隐式 Intent 启动浏览器

```bash
adb shell am start-activity \
  -a android.intent.action.VIEW \
  -d "https://example.com" \
  -t "text/html"
```

### 1.7 模拟来电(测试 in-call UI)

```bash
adb shell am start-activity \
  -a android.intent.action.DIAL \
  -d "tel:10086"
```

---

## 2. Extras 类型速查

| 参数 | 类型 | Java 端读取 |
|------|------|------------|
| `--es <key> <value>` | String | `getStringExtra(key)` |
| `--esn <key>` | null String | `getStringExtra(key) == null` |
| `--ei <key> <value>` | int | `getIntExtra(key, 0)` |
| `--el <key> <value>` | long | `getLongExtra(key, 0L)` |
| `--ef <key> <value>` | float | `getFloatExtra(key, 0f)` |
| `--ed <key> <value>` | double | `getDoubleExtra(key, 0d)` |
| `--ez <key> <bool>` | boolean | `getBooleanExtra(key, false)` |
| `--eu <key> <uri>` | Uri | `getParcelableExtra(key) as Uri` |
| `--ecn <key> <comp>` | ComponentName | `getParcelableExtra(key) as ComponentName` |
| `--eia <key> v1,v2,v3` | int[] | `getIntArrayExtra(key)` |
| `--esa <key> v1,v2,v3` | String[] | `getStringArrayExtra(key)` |
| `--ela <key> v1,v2,v3` | long[] | `getLongArrayExtra(key)` |
| `--eia <key> v1,v2,v3` | int[] | `getIntArrayExtra(key)` |
| `--grant-read-uri-permission` | grant flag | URI 读权限 |
| `--grant-write-uri-permission` | grant flag | URI 写权限 |
| `--el <key> <value>` | long | `getLongExtra(key, 0L)` |

**Java 端读取模板**:

```java
@Override
protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    Intent intent = getIntent();
    String orderId = intent.getStringExtra("orderId");      // --es
    int fromPush = intent.getIntExtra("fromPush", 0);        // --ei
    boolean isVip = intent.getBooleanExtra("isVip", false); // --ez
}
```

---

## 3. Intent Flags 速查(常用)

| Hex | Flag | 用途 |
|-----|------|------|
| `0x10000000` | `FLAG_ACTIVITY_NEW_TASK` | 新 task(必须,否则非 Activity 上下文会崩) |
| `0x04000000` | `FLAG_ACTIVITY_CLEAR_TOP` | 清掉目标之上页面 |
| `0x20000000` | `FLAG_ACTIVITY_SINGLE_TOP` | 等同 singleTop |
| `0x00100000` | `FLAG_ACTIVITY_NO_HISTORY` | 不进历史栈 |
| `0x02000000` | `FLAG_ACTIVITY_TASK_ON_HOME` | task 置 home 之上 |

**组合常用**:`-f 0x14000000` = NEW_TASK + CLEAR_TOP

---

## 4. 启动延迟测量 -W

```bash
$ adb shell am start-activity -W -n com.example.app/.ui.MainActivity
Starting: Intent { cmp=com.example.app/.ui.MainActivity }
Status: ok
LaunchState: COLD
Activity: com.example.app/.ui.MainActivity
TotalTime: 847
ThisTime: 723
WaitTime: 891
```

| 字段 | 含义 | 稳定性 KPI |
|------|------|----------|
| `Status` | 成功 / 失败 | 失败看 logcat |
| `LaunchState` | 冷 / 温 / 热 | 冷启是硬指标 |
| `TotalTime` | am 发出到首帧绘制 | **核心 KPI** |
| `ThisTime` | Activity onCreate 到 onResume | 应用自己耗时 |
| `WaitTime` | am 发出到系统调度完成 | 系统调度开销 |

**冷启动合格线**:
- P50 ≤ 1500ms:合格
- P50 ≤ 1000ms:优秀
- P99 > 2500ms:需优化

---

## 5. Android 11+ 必须显式 component

```bash
# ❌ 错误(Android 11+ 报错)
adb shell am start com.example.app/.ui.MainActivity

# ✅ 正确(必须 -n)
adb shell am start-activity -n com.example.app/.ui.MainActivity
```

详见 [01 §6.1 坑位](../01-am命令全景与Activity触发.md#61-权限不足android-11-强制使用--n)。

---

## 6. 多用户设备

```bash
# 指定 user(默认 0)
adb shell am start-activity -n 0 com.example.app/.MainActivity   # 旧写法
adb shell am start-activity --user 0 -n com.example.app/.MainActivity  # 推荐

# 跨 user 操作
adb shell am start-activity --user 10 -n com.example.app/.MainActivity
```
