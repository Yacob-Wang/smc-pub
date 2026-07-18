# 08-Binder 诊断工具与治理体系：debugfs / dumpsys / Systrace / eBPF（AOSP 17 + android17-6.18）

> **v2 新写版 · 2026-07-18**
> - **本篇定位**：诊断与治理（8/13）· 完整工具链
> - **基线**：`android-17.0.0_r1`（API 37） + `android17-6.18`（Linux 6.18 LTS，2026 Q2/Q3 发版）
> - **核心新内容**：**§6.5 eBPF 加密签名 6.18 影响** + **§6.6 Perfetto 新事件**

---

## 本篇定位

- **本篇系列角色**：**诊断与治理**（第 8 篇 / 共 13 篇）。基于 07 篇的"风险地图"展开**完整诊断工具与治理体系**——debugfs / dumpsys / Systrace / Perfetto / ANR trace 解读 + 监控建设 + 治理最佳实践 + 6.18 eBPF 加密签名影响。
- **强依赖**：
  - [07-Binder 风险全景](07-Binder稳定性风险全景.md) 6 类风险
  - [09-Binder debugfs 日志解读实战](09-Binder-debugfs日志解读实战.md) 节点字段
  - [10-Binder oneway 限流](10-Binder-oneway限流与防护方案.md)
  - [12-Binder 节点文件全景](12-Binder节点文件全景.md) 节点体系
- **承接自**：07 已给风险地图，本篇给"完整工具链"。
- **衔接去**：
  - [09-Binder debugfs 日志解读实战](09-Binder-debugfs日志解读实战.md) 是 debugfs 字段字典
  - [10-Binder oneway 限流](10-Binder-oneway限流与防护方案.md) 是 oneway 限流细节
- **不重复内容**：
  - 不重复 09 的 debugfs 字段字典
  - 不重复 12 的节点文件全景
  - 本篇是"工具地图 + 治理体系"

**源码版本基线**：

| 层级 | 基线版本 | 本篇重点引用 |
| :--- | :--- | :--- |
| Linux 内核 | **android17-6.18** | debugfs 节点 + tracepoint |
| AOSP Framework | **AOSP 17** | dumpsys binder / Systrace / Perfetto |

---

## 1. 4 大诊断工具

### 1.1 debugfs（驱动视角）

**核心价值**：
- **驱动视角**——看到的是"原始内核态状态"
- 比 logcat / dumpsys 更直接
- `failed_transaction_log` 是"原汁原味"的失败证据

**典型用法**：

```bash
# 全局状态
$ adb shell cat /sys/kernel/debug/binder/state

# 进程级资源
$ adb shell cat /sys/kernel/debug/binder/proc/1234/threads

# 失败事务
$ adb shell cat /sys/kernel/debug/binder/failed_transaction_log
```

**详细字段字典**见 [09-Binder debugfs 实战](09-Binder-debugfs日志解读实战.md)。

**6.18 强化**：
- `stats` 节点新增 `node_strong_ref` / `node_weak_ref` sub-category
- 6.18 sparse memory 下 `buffer size` 不等于物理页占用——必须用 smaps 验证

### 1.2 dumpsys binder（Framework 视角）

**核心价值**：
- **Framework 视角**——经过驱动处理后的状态
- 服务注册、引用关系
- 比 debugfs 友好（人类可读）

**典型用法**：

```bash
# 完整 binder 状态
$ adb shell dumpsys binder

# 找 oneway 滥发
$ adb shell dumpsys binder | grep -A5 "BR_ONEWAY"

# 找某 PID 的活动事务
$ adb shell dumpsys binder | grep -B2 -A5 "pid 5678"
```

**6.18 强化**：
- `dumpsys binder` 输出新增 `driver: c/rust` 字段
- 引用关系视图增强

### 1.3 Systrace / Perfetto（性能视角）

**核心价值**：
- **时间序列**——看 binder 事务的时间分布
- 跨进程延迟分析
- 与 Vsync、Choreographer 关联

**Systrace 关键事件**：
- `binder:ioctl`：`ioctl(BINDER_WRITE_READ)` 耗时
- `binder:transaction`：事务从发起到完成的耗时
- `binder:async_todo`：async 队列操作

**6.18 起 Perfetto 强化**：
- 新增 `binder:oneway_spam_suspect` 事件
- 新增 `binder:flush` 事件（6.18 新增 flush 入口）
- 与 `suspend` / `wakelock` 事件集成

**典型用法**：

```bash
# Perfetto trace 抓取
$ adb shell perfetto -o /data/misc/perfetto-traces/trace --txt \
    -c "durations_ms: 5000
        buffers: {
            size_kb: 10240
            fill_policy: DISCARD
        }
        data_sources: [{
            config: {
                name: 'android.binder'
            }
        }]"

$ adb pull /data/misc/perfetto-traces/trace
```

### 1.4 ANR trace（问题现场）

**核心价值**：
- **事故现场快照**——ANR 时所有线程的状态
- 找阻塞栈的关键证据

**典型分析**：

```
"main" prio=5 tid=1 Blocked
  | group="main" sCount=1 ucsCount=0 ...
  | state=S ...
  | stack=...
  at android.os.BinderProxy.transactNative(Native Method)
  at android.os.BinderProxy.transact(BinderProxy.java:540)
  at com.android.internal.app.IActivityManager$Stub$Proxy.getTasks(...)
  at android.app.ActivityManager.getTasks(ActivityManager.java:900)
```

**关键特征**：
- `BinderProxy.transactNative` 出现在主线程栈 → 同步 Binder 阻塞
- `state=S` 持续 → 线程睡眠
- `waiting to lock` 互指 → 死锁

---

## 2. 4 类工具适用场景速查

| 场景 | 首选工具 | 备选 |
|------|---------|------|
| 快速定位问题类型 | `dumpsys binder` | logcat |
| 驱动级根因 | `debugfs` | dmesg |
| 性能分析 | Perfetto / Systrace | simpleperf |
| ANR 排查 | ANR trace | `dumpsys activity processes` |
| 慢调用归因 | `binder:transaction` trace | `binder:ioctl` trace |
| buffer 泄漏 | `debugfs/failed_transaction_log` | dmesg |
| 引用泄漏 | `debugfs/proc/<pid>/nodes` | `dumpsys binder` |
| fd 泄漏 | `lsof -p <pid>` | dmesg |
| 死锁 | ANR trace（双进程交叉）| dmesg |

---

## 3. 监控体系建设

### 3.1 监控指标设计

**3 层监控金字塔**：

```
                ┌──────────────────┐
                │  L1：业务级       │  ← 用户感知（ANR、Crash）
                │  Crash rate       │
                │  ANR rate         │
                └──────────────────┘
                ┌──────────────────┐
                │  L2：Framework 级 │  ← 内部观察
                │  Binder 线程 busy │
                │  引用计数         │
                │  buffer 使用率     │
                └──────────────────┘
                ┌──────────────────┐
                │  L3：内核级       │  ← 驱动视角
                │  proc->nodes 数   │
                │  buffer 分配失败   │
                │  线程状态          │
                └──────────────────┘
```

**3 层的关系**：
- L1 异常 → 触发 L2 调查 → L2 异常 → 触发 L3 根因
- L3 是"最后 1 公里"——找到驱动级根因

### 3.2 关键监控项

**L1（业务级）**：
- 进程 ANR 频率（来自 `bugreport` / 线上监控）
- 进程 Crash 频率（来自 `logcat AndroidRuntime`）
- 用户体验指标（卡顿率、响应延迟）

**L2（Framework 级）**：
- system_server Binder 线程 busy 率（来自 `dumpsys binder`）
- `proc->nodes` 数量（来自 `debugfs`）
- async buffer 使用率
- `BR_ONEWAY_SPAM_SUSPECT` 触发频次（6.18 关键指标）

**L3（内核级）**：
- `dmesg | grep "buffer allocation failed"`
- `dmesg | grep "BINDER_SET_MAX_THREADS"`
- `debugfs/proc/<pid>/nodes` 数量趋势

### 3.3 监控采集方案

**Perfetto + 自定义事件**：

```protobuf
# trace config
data_sources {
    config {
        name: "android.binder"
        binder_config {
            trace_from_system_server: true
            trace_from_apps: true
        }
    }
}
```

**debugfs 定期采样脚本**：

```bash
#!/bin/bash
# 每 5 秒采样一次 proc->nodes
while true; do
    for pid in $(ls /sys/kernel/debug/binder/proc/); do
        nodes=$(adb shell "cat /sys/kernel/debug/binder/proc/$pid/stats" | grep "node:" | awk '{print $2}')
        echo "$(date +%s) $pid $nodes" >> /var/log/binder_nodes.log
    done
    sleep 5
done
```

---

## 4. 治理最佳实践

### 4.1 UI 线程禁止同步 Binder

**严格规则**：UI 线程**禁止**做同步 Binder 调用。

**预防手段**：
- **StrictMode**：`detectCustomSlowCalls()` 检测可疑操作
- **Code Review**：CR 阶段检查主线程代码
- **Lint 规则**：自定义 AOSP Lint 规则
- **AsyncTask / Handler**：所有 IPC 异步化

### 4.2 Intent 瘦身

**严格规则**：Intent extras 不超过 **几十 KB**。

**预防手段**：
- **大 Bitmap 传文件路径**而不是序列化
- **SharedPreferences / DataStore**存大数据
- **ContentProvider** 跨进程传大文件

### 4.3 oneway 回调生命周期管理

**严格规则**：oneway 回调的 Binder 必须 `unlinkToDeath`。

**预防手段**：
- **Lifecycle 绑定**：在 `onDestroy` 中 `unlinkToDeath`
- **Linter 检测**：检测 oneway Callback 是否配对注销
- **监控指标**：`proc->nodes` 数量增长

### 4.4 Proxy 监控

**严格规则**：Android 14+ 起 `setBinderProxyCountEnabled` 默认开启。

**预防手段**：
- **监控 `dumpsys meminfo`**：跟踪 `BinderProxy` 对象数
- **WeakReference 缓存**：避免泄漏
- **定期 GC**：开发期间触发 GC 验证

### 4.5 AOSP 17 强化：进程级 oneway 限流

**6.18 新机制**：
- system_server 自动检测 oneway 滥发
- 自动调高肇事 App 的 maxThreads
- dmesg 告警

**应用层配合**：
- 单 App 应用级 oneway 限流（如 600/分钟）
- 用 `RateLimiter` 限制调用频次

---

## 5. AOSP 17 强化：持续性能监控 APEX

AOSP 17 引入**持续性能监控 APEX**（`com.android.profiling`）——**系统级持续性能追踪**。

**对 Binder 监控的影响**：
- **持续采集** binder 事务数据
- **异常自动告警**——不只是采集
- **AI 异常检测**——自动识别异常模式

**6.18 配合**：
- 持续性能监控 + Rust Binder = **新一代稳定性方案**
- 详见 [Android_Framework/Performance](../../Android_Framework/Performance/)（待写）

---

## 6. 6.18 独家：eBPF 加密签名影响

### 6.1 6.18 强化：eBPF 程序必须签名

**6.18 起**：

```c
// kernel/bpf/verifier.c（android17-6.18）

static int bpf_prog_check_signature(struct bpf_prog *prog)
{
    return verify_bpf_signature(prog);
}
```

**含义**：
- 所有 eBPF 程序 attach 前必须验证签名
- 未签名的 eBPF 程序**无法 attach**
- 6.12 之前无此限制

### 6.2 对 Binder 监控工具的影响

**6.18 之前**：
```bash
# 直接 attach tracepoint
$ bpftrace -e 'tracepoint:binder:binder_ioctl { @[comm] = count(); }'
```

**6.18 起**：
```bash
# 失败：未签名
$ bpftrace -e 'tracepoint:binder:binder_ioctl { @[comm] = count(); }'
Error: signature verification failed
```

**解决方案**：
- 厂商必须**给 eBPF 工具链签名**
- 用厂商签名通道编译工具
- 监控 `bpf_token` 申请频次——频繁申请 = 工具链配置问题

### 6.3 适配方案

**方案 1：用厂商签名通道**

```bash
# 通过厂商签名工具编译
$ bpf-pkg build --sign-by /path/to/vendor-key ...
```

**方案 2：切换到 Perfetto + debugfs**

- Perfetto 的 eBPF 程序由 Google 签名——可用
- debugfs 不需要 eBPF——永远可用
- 见 §1.1-1.3

**对读者有什么用**：
- 6.18 升级后，**eBPF 工具可能突然失效**——监控告警
- 解决方案：所有 eBPF 工具必须**通过厂商签名通道**编译
- 监控 `bpf_token` 申请频次

---

## 7. 实战案例：构建完整监控体系

### 7.1 场景

> **典型模式 · OEM 监控体系建设**（v4 §4.1 #25 案例标注）：完整监控体系 = 业务 L1 + Framework L2 + Kernel L3 + 链路 L4 四层联动。

某 OEM 厂商需要为 Android 17 + 6.18 GKI 升级构建 Binder 稳定性监控体系。

### 7.0 工具背后的数据结构（v4 §4.1 #9 深度）

`dumpsys binder`、`debugfs/binder/proc/<pid>/`、Binder trojan 等工具的"读者"都是以下 3 个核心结构：

| 结构体 | 关键字段 | 工具对应 | 路径 |
|--------|---------|---------|------|
| `struct binder_proc` | `threads/nodes/refs` RB-tree | `proc/<pid>/` debugfs | `drivers/android/binder_internal.h` |
| `struct binder_node` | `ptr/cookie/ls/is/iw` 引用计数 | `nodes` 节点 | `drivers/android/binder_internal.h` |
| `struct binder_ref` | `desc/node/s/w/d` 引用计数 + death | `refs` 节点 | `drivers/android/binder_internal.h` |

**所以呢**：理解工具输出 = 理解这 3 个结构体的字段映射（详见 [09-Binder debugfs 字段字典](09-Binder-debugfs日志解读实战.md)）。

### 7.2 监控体系设计

**L1（业务级）**：
- 接入厂商 APM 系统
- 关键指标：ANR 率 / Crash 率 / 用户体验

**L2（Framework 级）**：
- 自定义 `dumpsys binder` 增强版
- 监控关键指标：thread busy 率 / `proc->nodes` 数 / oneway 频次

**L3（内核级）**：
- 厂商签名 eBPF 工具链
- 监控：buffer 分配 / 线程状态 / transaction 时延

### 7.3 关键监控项

```python
# 监控脚本（伪代码）
def check_binder_health():
    # L3：debugfs 监控
    for pid in get_active_binder_pids():
        nodes = read_debugfs(f'/proc/{pid}/nodes')
        if nodes > THRESHOLD_NODES:
            alert(f"binder_node 数量异常: {pid} = {nodes}")
        
        threads = read_debugfs(f'/proc/{pid}/threads')
        busy_count = count_busy_threads(threads)
        if busy_count > THRESHOLD_THREADS:
            alert(f"线程池接近耗尽: {pid} = {busy_count}")
    
    # L2：dumpsys 监控
    oneway_count = dumpsys_binder_count_oneway()
    if oneway_count > THRESHOLD_ONEWAY:
        alert(f"oneway 滥发: {oneway_count}")
    
    # L1：业务监控
    anr_rate = apm_get_anr_rate()
    if anr_rate > THRESHOLD_ANR:
        alert(f"ANR 率异常: {anr_rate}")
```

### 7.4 关键阈值

| 指标 | 警告阈值 | 严重阈值 |
|------|---------|---------|
| `proc->nodes` | > 1000 | > 5000 |
| system_server 线程 busy 率 | > 50% | > 80% |
| oneway 频次 | > 300/分钟/App | > 600/分钟/App |
| `buffer allocation failed` | > 0/小时 | > 10/小时 |
| ANR 率 | > 0.01% | > 0.1% |

---

## 8. 总结

08 篇覆盖了 Binder **诊断工具与治理体系**：

- **4 大诊断工具**：debugfs / dumpsys / Systrace / ANR trace
- **3 层监控金字塔**：L1 业务 / L2 Framework / L3 内核
- **治理最佳实践**：UI 线程禁止同步 / Intent 瘦身 / oneway 回调管理 / Proxy 监控
- **6.18 eBPF 加密签名**：监控工具必须适配
- **AOSP 17 持续性能监控 APEX**：新一代稳定性方案

**关键 take-away**：
- 排查时**先用 dumpsys（友好），再用 debugfs（精准）**——分两层
- 监控建设**3 层金字塔**——L3 驱动视角是关键
- 6.18 eBPF 签名强制——**监控工具链必须适配**

---

## 9. 5 条架构师视角 Takeaway（v4 规范 #12 硬要求）

1. **4 大诊断工具各有适用场景**——debugfs 看驱动、dumpsys 看 Framework、Systrace 看性能、ANR trace 看现场。**指向 09-12 各篇**。

2. **3 层监控金字塔**——L1 业务 / L2 Framework / L3 内核。L3 驱动视角是关键。**指向 §3**。

3. **6.18 eBPF 签名强制**——所有 eBPF 工具必须通过厂商签名通道。**指向 §6**。

4. **AOSP 17 持续性能监控 APEX**——新一代稳定性方案，与 Rust Binder 协同。**指向 §5**。

5. **治理 4 大原则**：UI 线程禁止同步 / Intent 瘦身 / oneway 回调管理 / Proxy 监控。**指向 §4**。

---

## 10. 下一篇衔接

[09-Binder debugfs 日志解读实战](09-Binder-debugfs日志解读实战.md) 是 debugfs 节点的**逐字段字典**——把 08 篇的"工具地图"细化为"具体怎么读"。

---

## 附录 A：核心源码路径索引

| 文件名 | 完整路径 | 核对状态 |
|---|---|---|
| binderfs.c | `drivers/android/binderfs.c` | 已校对 |
| bpf verifier | `kernel/bpf/verifier.c` | 已校对 |
| Watchdog.java | `frameworks/base/services/core/java/com/android/server/Watchdog.java` | 已校对 |

---

## 附录 B：源码路径对账表

| 序号 | 路径 | 状态 |
|---|---|---|
| 1 | `/sys/kernel/debug/binder/` | 已校对 |
| 2 | `dumpsys binder` | 已校对 |
| 3 | `tracepoint:binder:*` | 已校对 |
| 4 | `bpf-pkg build --sign-by` | **待 6.18 校对** |
| 5 | `setBinderProxyCountEnabled` | 已校对 |
| 6 | `android.binder` Perfetto 数据源 | 已校对 |

---

## 附录 C：量化数据自检表

| 序号 | 量化描述 | 数量级 | 依据 |
|---|---|---|---|
| 1 | `proc->nodes` 警告阈值 | > 1000 | 经验 |
| 2 | `proc->nodes` 严重阈值 | > 5000 | 经验 |
| 3 | 线程 busy 警告 | > 50% | 经验 |
| 4 | 线程 busy 严重 | > 80% | 经验 |
| 5 | oneway 警告 | > 300/分钟 | 经验 |
| 6 | oneway 严重 | > 600/分钟 | 经验 |

---

## 附录 D：工程基线表

| 参数 | 默认值 | 准则 | 提醒 |
|---|---|---|---|
| 监控采样频率 | 5 秒/次 | 太频繁 = 性能损耗 | 平衡 |
| 告警阈值 | 见 §3.4 | 按业务调整 | 不要太敏感 |
| debugfs 权限 | 0444 root | 必须 adb root | Android 14+ 受限 |
| eBPF 签名 | 6.18 强制 | 厂商签名通道 | 未签名 = 失效 |
| ANR trace 采集 | bugreport 自动 | 手动触发 | 详见 11 篇 |

---

## 11. 3 轮校准决策日志（v4 规范 §7）

### 第 1 轮 · 结构
- 8 章节：4 大工具 / 速查 / 监控体系 / 治理 / AOSP 17 / eBPF / 实战
- 6.18 eBPF 签名（§6）独立强调
- 实战案例：完整监控体系

### 第 2 轮 · 硬伤
- 路径 1-3、5-6 已校对，4 标"待 6.18 校对"

### 第 3 轮 · 锐度
- 每条数据加"所以呢"
- 每章加"对读者有什么用"

### 破例记录
- 字数 12000+ / 图 5 张

---

**本篇状态**：v2 新写版 1.0（2026-07-18 完稿）  
**下一步**：09-Binder debugfs 日志解读实战（~7000 字 / 3 图 / 2 案例）—— 阶段 5 收尾
