# am profile 参数速查表

> **基线**:AOSP `android-14.0.0_r1` + adb `platform-tools 34+`
>
> **位置**:`Android_Framework/AmCommand/am_command_configs/am_profile_params.md`

---

## 1. 子命令总览

| 子命令 | 语法 | 作用 | Android 版本 |
|--------|------|------|------------|
| `start` | `am profile start <proc> <file>` | 启动 Method Trace | 7.0+ |
| `stop` | `am profile stop <proc>` | 停止并自动 pull 文件 | 7.0+ |
| `dumpheap` | `am profile dumpheap <proc> <file>` | profile 期间触发堆 dump | 7.0+ |

---

## 2. start 参数详解

### 2.1 完整语法

```
am profile start [--user <userId>] [--sampling | --instrumented] <PROCESS> <FILE>
```

### 2.2 参数矩阵

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `<PROCESS>` | string | ✅ | - | 包名(`com.example.app`)或 PID(`12345`) |
| `<FILE>` | path | ✅ | - | 设备上的输出路径,**必须 `/data/local/tmp/` 开头** |
| `--user <userId>` | int | ❌ | 0 | 多用户设备,普通用户 0,Work Profile 通常 10 |
| `--sampling` | flag | ❌ | ✅ 默认 | 采样式采样,2-5% CPU 开销 |
| `--instrumented` | flag | ❌ | ❌ | 插桩式采样,20-50% CPU 开销,严禁线上 |
| `--wall-clock` | flag | ❌ | ❌ | 时钟源(几乎不用) |
| `--cpu-clock` | flag | ❌ | ✅ 默认 | CPU 时钟 |

### 2.3 进程标识选择

| 标识 | 用法 | 适用场景 |
|------|------|---------|
| **包名** | `com.example.app` | 单一进程 app(90% 场景) |
| **PID** | `12345` | 多进程 app 精确到子进程 |
| **包名 + 后缀** | `com.example.app:push` | 部分 Android 版本支持 |

### 2.4 文件路径约束

| 路径前缀 | 是否可用 | 说明 |
|---------|---------|------|
| `/data/local/tmp/` | ✅ | **唯一推荐**——Android 14 SELinux 放行 |
| `/sdcard/` | ❌ | SELinux 拒绝(Android 9+) |
| `/data/data/<pkg>/` | ❌ | 普通 app 无写权限 |
| `/data/local/` | ⚠️ | 部分版本可用,但不如 `/local/tmp/` |

---

## 3. stop 参数详解

### 3.1 完整语法

```
am profile stop [--user <userId>] <PROCESS>
```

### 3.2 行为

1. 通知目标进程停止采样
2. ART 把内存中的采样数据 flush 到 `<FILE>`
3. **adb 自动把 `<FILE>` pull 到主机当前目录**
4. 设备上的 `<FILE>` 被删除

### 3.3 关键注意

| 项 | 说明 |
|----|------|
| 主机文件路径 | `pwd` 所在目录(执行 adb 的当前路径) |
| 文件名 | 与设备上同名(如 `trace.trace`) |
| 自动清理 | pull 后设备上文件被删除 |
| 失败回退 | pull 失败时,可手动 `adb pull <设备路径> <主机路径>` |

---

## 4. dumpheap 参数详解

### 4.1 完整语法

```
am profile dumpheap [--user <userId>] <PROCESS> <FILE>
```

### 4.2 用途

**profile 期间**同步触发 Java 堆 dump,产出的 hprof 文件可与 trace 做时间对齐分析。

### 4.3 与直接 `am dumpheap` 的差异

| 项 | `am profile dumpheap` | `am dumpheap` |
|----|---------------------|--------------|
| 触发时机 | profile 已启动期间 | 任意时刻 |
| 上下文关联 | ✅ 与 profile 时间对齐 | ❌ 独立 |
| 自动 pull | ❌(需手动) | ❌(需手动) |
| 推荐度 | ⭐⭐⭐⭐⭐(联动现场保留) | ⭐⭐⭐⭐(单独使用) |

---

## 5. Android 版本差异矩阵

### 5.1 各版本支持情况

| Android 版本 | API | sampling | instrumented | 默认模式 |
|------------|-----|----------|--------------|---------|
| 7.0 (Nougat) | 24 | ✅ | ❌ | sampling |
| 8.0 (Oreo) | 26 | ✅ | ❌ | sampling |
| 9.0 (Pie) | 28 | ✅ | ✅ | sampling |
| 10 (Q) | 29 | ✅ | ✅ | sampling |
| 11 (R) | 30 | ✅ | ✅ | sampling |
| 12 (S) | 31 | ✅ | ✅ | sampling |
| 13 (T) | 33 | ✅ | ✅ | sampling |
| 14 (U) | 34 | ✅ | ✅ | sampling |

### 5.2 各版本默认采样率

| Android 版本 | 默认采样间隔 | 备注 |
|------------|------------|------|
| 7.0-9.0 | 10ms | 性能保守 |
| 10-13 | 1ms(可调到 10ms) | 默认高精度 |
| 14 | 1ms | 与 13 一致 |

### 5.3 调整采样率

```bash
# Android 10+ 调整(需要 root 或 userdebug)
adb shell setprop dalvik.vm.profiler.sampling-interval 10  # 低开销

# 还原
adb shell setprop dalvik.vm.profiler.sampling-interval 1   # 默认
```

---

## 6. 采样开销实测参考

### 6.1 不同采样率的开销

| 采样间隔 | CPU 开销 | 内存开销(/10s 采样) | 适用场景 |
|---------|---------|---------------------|---------|
| 1ms(默认) | 3-5% | 8-12MB | 短时精确定位 |
| 5ms | 2-3% | 4-6MB | 平衡场景 |
| 10ms | 1-2% | 2-3MB | 长期后台采样 |
| 100ms | < 1% | < 1MB | 极低开销采样 |

### 6.2 不同 trace 时长的文件大小

| 时长 | 方法数 ~1k | 方法数 ~10k | 方法数 ~50k |
|------|-----------|------------|------------|
| 10s | 1-3MB | 5-10MB | 10-20MB |
| 60s | 5-15MB | 30-60MB | 80-150MB |
| 300s | 25-70MB | 150-300MB | 400-700MB |
| 1800s | 150-400MB | 800-1500MB | 2-4GB(危险) |

> **建议**:单次 trace 不超过 5 分钟,文件控制在 100MB 以内,便于 Studio 打开。

---

## 7. 联动用法速查

### 7.1 profile + dumpheap(性能 + 内存)

```bash
PID=12345
adb shell am profile start $PID /data/local/tmp/trace.trace
sleep 30   # 场景中段
adb shell am profile dumpheap $PID /data/local/tmp/heap.hprof
sleep 30
adb shell am profile stop $PID   # 自动 pull trace
adb pull /data/local/tmp/heap.hprof ./  # 手动 pull heap
```

### 7.2 profile + hang(ANR 期间采 trace)

```bash
PID=12345
adb shell am profile start $PID /data/local/tmp/long_trace.trace
sleep 30
adb shell am hang $PID
sleep 10
adb shell am profile stop $PID
```

### 7.3 profile + monitor(后台监控)

```bash
PID=12345
adb shell am monitor &
MONITOR_PID=$!

adb shell am profile start $PID /data/local/tmp/trace.trace
sleep 60
adb shell am profile stop $PID

kill $MONITOR_PID
```

---

## 8. trace 文件解析命令速查

### 8.1 traceview(命令行)

```bash
# SDK tools 路径
traceview trace.trace

# 限制输出 top N
traceview --limit 20 trace.trace

# 输出 HTML 报告
traceview --html trace.trace > trace_report.html
```

### 8.2 hprof-conv(转码,profile 不产出 hprof 但 dumpheap 联动时会用)

```bash
$ANDROID_HOME/platform-tools/hprof-conv heap.hprof heap_mat.hprof
```

### 8.3 Studio Profiler(GUI)

1. Studio → Profiler → 顶栏 → Sampled (Java/Kotlin Method Trace)
2. → `...` → Load from file → 选 `trace.trace`

---

## 9. 决策树:profile 还是其他工具?

```
想看什么?
├─ Java 方法栈热点
│  ├─ 单进程采样 → am profile ✅
│  ├─ 多进程对比 → am profile <pid>
│  └─ 实验室精确耗时 → am profile --instrumented
├─ Native 函数 CPU
│  └─ simpleperf ✅
├─ 系统调用 / Kernel 事件
│  └─ Perfetto + atrace ✅
├─ 渲染 / 帧率
│  └─ dumpsys gfxinfo / Perfetto
├─ 内存分配对象
│  └─ am dumpheap / Studio Memory Profiler
└─ 进程整体 CPU 占用
   └─ dumpsys cpuinfo / top -p <pid>
```

---

## 10. 实战 5 分钟模板

```bash
# === 1. 找 PID ===
PID=$(adb shell pidof com.example.app | tr -d '\r\n ')

# === 2. 启动 profile ===
adb shell am profile start $PID /data/local/tmp/trace.trace

# === 3. 执行场景(手动 / monkey / UI Automator) ===
adb shell am start -n com.example.app/.MainActivity
sleep 5

# === 4. 停止 profile ===
cd /tmp   # 确保 pull 路径
adb shell am profile stop $PID

# === 5. 查看文件 ===
ls -lh /tmp/trace.trace

# === 6. Studio 打开 / traceview 解析 ===
traceview /tmp/trace.trace
```

---

## 11. 错误码与诊断

| 错误输出 | 根因 | 解决 |
|---------|------|------|
| `Profiling failed: Can't profile this process` | app 未 debuggable 或系统 app 权限不足 | 检查 `dumpsys package` 的 flags,确认 DEBUGGABLE |
| `Profiling failed: File path invalid` | 路径不在 `/data/local/tmp/` | 改为 `/data/local/tmp/trace.trace` |
| `Profiling failed: Process not found` | PID 错误 | `pidof <pkg>` 重新拿 |
| `Profiling already active` | 同进程已有 profile | 先 `am profile stop` |
| pull 后文件空(几 KB) | 采样时间太短 / 进程已死 | 加长采样时间,确认进程存活 |
| pull 失败 | 当前目录无写权限 / 设备空间满 | 切到 `/tmp` 后重试,清理设备空间 |

---

## 12. 相关命令速查

| 命令 | 用途 | 详见 |
|------|------|------|
| `am dumpheap` | 触发 Java 堆 dump | [04-堆内存转储-dumpheap 详解](../04-堆内存转储-dumpheap详解.md) |
| `am hang` | 触发 ANR | [05-诊断与监控](../05-诊断与监控-hang-monitor.md) |
| `am monitor` | 监控 GC / Crash 事件 | [05-诊断与监控](../05-诊断与监控-hang-monitor.md) |
| `am kill` | 模拟 LMKD 杀进程 | [02-进程管理三件套](../02-进程管理三件套-kill-crash-restart.md) |
| `simpleperf record` | Native 函数 CPU 采样 | SimplePerf 系列 |
| `perfetto -o` | 系统级 trace | Perfetto 系列 |

---

**返回**:[03-性能分析入口-profile 命令](../03-性能分析入口-profile命令.md)