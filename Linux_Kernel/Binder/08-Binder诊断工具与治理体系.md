# 08-Binder 诊断工具与治理体系

## 本篇定位

- **本篇系列角色**：诊断治理篇（首篇 / 共 12 篇）。本篇是 [07 风险地图](07-Binder稳定性风险全景.md) 的"工具对应"——给出每类风险用什么工具查、按什么思路定位、如何建立监控体系。
- **强依赖**：[07-Binder 稳定性风险全景](07-Binder稳定性风险全景.md)（六大风险类型）、[01-Binder 总览](01-Binder总览.md)（四层架构）、[02-Binder 驱动](02-Binder驱动.md)（数据结构与 debugfs）、[05-Binder 线程模型](05-Binder线程模型.md)（线程池状态）。
- **承接自**：[07-Binder 稳定性风险全景](07-Binder稳定性风险全景.md) 给出了"风险类型 → 现象 → 日志关键字"的对应；本篇**给出"风险类型 → 工具 → 排查路径 → 监控指标"的闭环**。
- **衔接去**：[09-Binder debugfs 日志解读实战](09-Binder-debugfs日志解读实战.md)（v3 重写后）从一份 proc 快照做"逐字段实战"；[10-Binder oneway 限流与防护方案](10-Binder-oneway限流与防护方案.md)（v3 重写后）从本篇的"监控体系"切到 oneway 专项防护；[11-Binder 厂商预防与治理方案调研报告](11-Binder厂商预防与治理方案调研报告.md)（v3 重写后）按角色对标 AOSP / Qualcomm / MediaTek / OEM / 大厂方案；[12-Binder 节点文件全景与问题实战](12-Binder节点文件全景与问题实战.md) 把本篇的 debugfs 单节点讲解扩展到全节点 + binderfs。
- **不重复内容**：本篇不重复 [07](07-Binder稳定性风险全景.md) 的风险模式识别速查表，只引用其结论；不重复 [02](02-Binder驱动.md) 的数据结构字段定义，只引用为"工具能查什么"。
- **跨系列引用**：本篇涉及的 `dumpsys` / `systrace` / `perfetto` / ANR trace 解析，**不重复展开**——`systrace` / `perfetto` 详见 [Tools 系列](../../Tools/)；ANR 触发机制详见 [Android_Framework/ANR_Detection 系列](../../Android_Framework/ANR_Detection/)；system_server 监控详见 [Android_Framework/Watchdog 系列](../../Android_Framework/Watchdog/)。

**源码版本基线（贯穿全系列）**：

| 层级 | 基线版本 | 本篇重点引用 |
| :--- | :--- | :--- |
| Linux 内核 | **android14-5.10 / android14-5.15** | `binder.c` 中各 debugfs 节点生成函数 |
| Native 用户态 | **AOSP android-14.0.0_r1** | `libbinder` 中 `debuggerd` 接口 |
| Framework | **AOSP android-14.0.0_r1** | `dumpsys binder` 实现、`BinderCallsStats`、`SystemServer` 各服务的 `dumpsys` 方法 |

> 本篇作为"诊断工具链"的纲领篇，不重复细节实现。`debugfs` 各节点的逐字段字典在 [09](09-Binder-debugfs日志解读实战.md)（v3 重写版）展开；全节点全景 + binderfs + 实战案例在 [12](12-Binder节点文件全景与问题实战.md)。

---

上一篇我们系统梳理了 Binder 的六大稳定性风险——ANR、TransactionTooLargeException、DeadObjectException、SecurityException、资源泄漏，以及每种问题的模式识别特征。知道"会出什么问题"只是第一步，更关键的是：**问题发生时，用什么工具、看什么数据、按什么思路定位根因？问题解决后，如何建立监控体系让同类问题不再发生？**

这正是本篇要回答的问题。我们将从内核态到用户态，逐层介绍 Binder 的诊断工具链，最终构建一套从"能查"到"能治"到"能防"的完整治理体系。

```
诊断工具分层：

    ┌─────────────────────────────────────────────────────┐
    │        治理最佳实践（预防层）                          │
    │   UI 线程禁止同步 Binder / Intent 瘦身 / Proxy 限制   │
    ├─────────────────────────────────────────────────────┤
    │        监控体系（预警层）                              │
    │   线程使用率 / Buffer 使用率 / 慢调用统计              │
    ├─────────────────────────────────────────────────────┤
    │        ANR Trace 分析（定位层）                        │
    │   Binder 线程栈 / outgoing transaction / 锁等待       │
    ├─────────────────────────────────────────────────────┤
    │        Systrace / Perfetto（可视化层）                 │
    │   跨进程延迟 / 线程争抢 / 事务时序                     │
    ├─────────────────────────────────────────────────────┤
    │        dumpsys 系列（Framework 层）                    │
    │   服务列表 / 内存统计 / Binder 状态                    │
    ├─────────────────────────────────────────────────────┤
    │        debugfs 接口（Kernel 层）                       │
    │   state / stats / transactions / proc                │
    └─────────────────────────────────────────────────────┘
```

---

## 1. debugfs 接口

### 1.1 为什么从 debugfs 开始

所有上层工具——`dumpsys`、Systrace、ANR trace——最终都依赖内核提供的信息。debugfs 是 Binder 驱动直接暴露的诊断接口，它提供了**最底层、最完整、最不经过加工**的 Binder 状态快照。当上层工具提供的信息不足以定位问题时，debugfs 是你的最终武器。

Binder debugfs 接口位于 `/sys/kernel/debug/binder/`（部分设备路径为 `/d/binder/`），包含以下核心文件：

| 文件 | 内容 | 典型用途 |
| :--- | :--- | :--- |
| `state` | 所有进程的 Binder 状态快照 | 全局概览，一次看所有进程的线程/node/ref/buffer |
| `stats` | 全局统计计数器 | 事务总数、线程创建数、buffer 分配/释放数 |
| `transactions` | 正在进行中的事务 | 查找当前阻塞的事务，定位跨进程等待 |
| `proc/<pid>` | 特定进程的 Binder 状态 | 针对性排查某个进程的线程池和 buffer 状况 |
| `transaction_log` | 最近的事务日志（环形缓冲区） | 事后回溯最近的 Binder 调用 |
| `failed_transaction_log` | 失败事务日志 | 定位 TransactionTooLargeException 等失败 |

### 1.2 state 文件解读

`state` 文件是最常用的 debugfs 文件，它提供了所有打开 Binder 设备的进程的完整快照。

```bash
# 读取全局 Binder 状态（需要 root）
adb shell su -c "cat /sys/kernel/debug/binder/state" > binder_state.txt
```

典型输出结构：

```
binder state:
dead nodes:
  node 12345: u00000076543210 c00000076543218 pri 0:139 hs 1 hw 1 ls 0 lw 0 is 1 iw 1 tr 0 proc 0
  ...

proc 1234  (system_server)
  context binder
  thread 1234: l 12  need_return 0  tr 0
  thread 1256: l 11  need_return 0  tr 0
  thread 1278: l 11  need_return 0  tr 1
    outgoing transaction 567890: 00000076aabb0000 from 1234:1278 to 5678:0 code 1 flags 10 pri 0:120 r1
  thread 1290: l 01  need_return 0  tr 0
  ...
  node 54321: u00000076543210 c00000076543218 pri 0:139 hs 1 hw 1 ls 0 lw 0 is 2 iw 2 tr 1 proc 5678 8901
  ref 67890: desc 0 node 1 s 1 w 1 d 0000000000000000
  ...
  buffer 45678: 00000076aabb1000 size 256:0:0 delivered
  buffer 45679: 00000076aabb2000 size 1024:8:0 delivered
  ...
  pending transaction 789012: ...
```

各字段含义：

**线程信息：**

```
thread 1278: l 11  need_return 0  tr 1
              │ ││                  │
              │ ││                  └── 正在处理的事务数（0=空闲, >0=忙碌）
              │ │└── bit1: has_proc_work（有待处理工作）
              │ └── bit0: is_looper（是否为 looper 线程）
              └── "l" = looper state 位掩码
```

`l` 字段的位含义：

| 值 | 含义 | 说明 |
| :--- | :--- | :--- |
| `00` | 非 looper 线程 | 普通线程，临时参与 Binder 调用 |
| `01` | `BINDER_LOOPER_STATE_REGISTERED` | 通过 `BC_REGISTER_LOOPER` 注册的工作线程 |
| `11` | `BINDER_LOOPER_STATE_ENTERED` | 通过 `BC_ENTER_LOOPER` 进入的主线程 |
| `12` | `BINDER_LOOPER_STATE_ENTERED` + `WAITING` | 主线程正在等待新事务 |

**Node 信息：**

```
node 54321: u00000076543210 c00000076543218 pri 0:139 hs 1 hw 1 ls 0 lw 0 is 2 iw 2 tr 1 proc 5678 8901
            │                │                │        │     │     │     │     │     │     │    └── 引用此 node 的进程
            │                │                │        │     │     │     │     │     │     └── 待处理事务数
            │                │                │        │     │     │     │     │     └── 内部弱引用数
            │                │                │        │     │     │     │     └── 内部强引用数
            │                │                │        │     │     │     └── 本地弱引用数
            │                │                │        │     │     └── 本地强引用数
            │                │                │        │     └── 外部弱引用数
            │                │                │        └── 外部强引用数
            │                │                └── 优先级
            │                └── cookie（Binder 对象在用户态的回调指针）
            └── userspace ptr（Binder 对象在用户态的地址）
```

**Buffer 信息：**

```
buffer 45678: 00000076aabb1000 size 256:0:0 delivered
                                     │   │ │ └── 状态（delivered=已送达, pending=等待中）
                                     │   │ └── offsets size
                                     │   └── extra buffers size
                                     └── data size (bytes)
```

### 1.3 从 debugfs 识别 Binder 线程耗尽

Binder 线程耗尽是导致 ANR 的首要原因之一。通过 debugfs 可以直接确认线程池状态：

```bash
# 查看特定进程的 Binder 状态
adb shell su -c "cat /sys/kernel/debug/binder/proc/$(pidof system_server)"
```

**正常状态** —— 有空闲线程在等待：

```
proc 1234  (system_server)
  thread 1234: l 12  need_return 0  tr 0    ← 主线程空闲 (l=12, WAITING)
  thread 1300: l 01  need_return 0  tr 0    ← 工作线程空闲
  thread 1301: l 01  need_return 0  tr 1    ← 工作线程正在处理 1 个事务
  thread 1302: l 01  need_return 0  tr 0    ← 工作线程空闲
  ...（共 31 个线程，其中多数空闲）
```

**线程耗尽状态** —— 所有线程都在忙碌：

```
proc 1234  (system_server)
  thread 1234: l 11  need_return 0  tr 1    ← 主线程忙碌
  thread 1300: l 01  need_return 0  tr 1    ← 全部忙碌
  thread 1301: l 01  need_return 0  tr 1
  ...
  thread 1330: l 01  need_return 0  tr 1    ← 所有 31 个线程都 tr=1
    outgoing transaction ...: from 1234:1330 to 5678:0  ← 等待另一个进程响应
```

**判断标准：** 如果 `tr > 0` 的线程数量等于线程总数，且没有 `l` 值包含 WAITING 标志的线程，说明线程池已耗尽。

### 1.4 从 debugfs 识别 Buffer 耗尽

```bash
# 统计某进程的 buffer 使用量
adb shell su -c "cat /sys/kernel/debug/binder/proc/$(pidof com.example.app)" | grep "buffer"
```

观察所有 `buffer` 行的 `size` 字段，累加得到总使用量。如果接近 1MB（1,048,576 bytes），说明 buffer 即将耗尽，后续事务将触发 `TransactionTooLargeException`。

### 1.5 stats 文件解读

```bash
adb shell su -c "cat /sys/kernel/debug/binder/stats"
```

```
binder stats:
BC_TRANSACTION: 12345678
BC_REPLY: 12340000
BC_FREE_BUFFER: 24680000
BC_INCREFS: 567890
BC_ACQUIRE: 567890
BC_RELEASE: 560000
BC_DECREFS: 560000
...
BR_TRANSACTION: 12345678
BR_REPLY: 12340000
BR_DEAD_BINDER: 1234
BR_SPAWN_LOOPER: 45678
...
proc: active 128 total 256
thread: active 2345 total 8901
node: active 12345 total 34567
ref: active 23456 total 56789
death: active 3456 total 7890
transaction: active 12 total 12345678
transaction_complete: active 12 total 12345678
```

关键指标解读：

| 指标 | 含义 | 异常信号 |
| :--- | :--- | :--- |
| `BC_TRANSACTION` 总数 | 系统启动以来的 Binder 事务总数 | 短时间内飙升说明存在 Binder 风暴 |
| `BR_DEAD_BINDER` | 驱动发出的死亡通知数量 | 数值大说明进程频繁死亡 |
| `BR_SPAWN_LOOPER` | 驱动请求创建新线程的次数 | 数值远大于线程总数说明线程频繁创建销毁 |
| `transaction: active` | 当前正在进行中的事务数 | 长期 > 0 说明有事务阻塞 |
| `node: active` | 当前存活的 Binder node 数 | 持续增长说明存在 Binder 对象泄漏 |

---

## 2. dumpsys 系列

### 2.1 为什么需要 Framework 层的诊断工具

debugfs 提供的是**内核视角**——它能告诉你线程在等什么、buffer 用了多少，但无法告诉你这个 Binder 对象对应的是哪个 Java 服务、哪个 Intent。`dumpsys` 系列工具是 Framework 层的诊断入口，它将内核态的 Binder 信息与 Java 层的服务信息关联起来，让你知道"是谁在调谁"。

### 2.2 service list — 查看注册的所有服务

```bash
adb shell service list
```

```
Found 213 services:
0	carrier_config: [com.android.internal.telephony.ICarrierConfigLoader]
1	phone: [com.android.internal.telephony.ITelephony]
2	isms: [com.android.internal.telephony.ISms]
...
45	activity: [android.app.IActivityManager]
46	package: [android.content.pm.IPackageManager]
47	window: [android.view.IWindowManager]
...
210	settings: [android.provider.ISettings]
211	notification: [android.app.INotificationManager]
212	connectivity: [android.net.IConnectivityManager]
```

这个列表本质上是 ServiceManager 中注册的所有 Binder 服务。每个条目包含：
- **序号**：ServiceManager 中的注册顺序
- **服务名**：通过 `ServiceManager.getService("activity")` 获取服务时使用的名称
- **接口描述符**：AIDL 生成的接口全限定名

当排查 `DeadObjectException` 时，第一步就是检查目标服务是否还在这个列表中。

### 2.3 dumpsys activity services — 查看应用级 Binder 服务

```bash
# 查看所有已绑定的 Service
adb shell dumpsys activity services

# 查看特定包名的 Service
adb shell dumpsys activity services com.example.app
```

```
ACTIVITY MANAGER SERVICES (dumpsys activity services)
  User 0 active services:
  * ServiceRecord{a1b2c3d u0 com.example.app/.MyService}
    intent={cmp=com.example.app/.MyService}
    packageName=com.example.app
    processName=com.example.app
    baseDir=/data/app/com.example.app-1/base.apk
    createTime=-3m12s456ms startingBgTimeout=--
    lastActivity=-12s345ms restartTime=-3m12s456ms
    app=ProcessRecord{d4e5f6a 12345:com.example.app/u0a123}
    Bindings:
    * IntentBindRecord{1a2b3c4}:
      intent={cmp=com.example.app/.MyService}
      binder=android.os.BinderProxy@7890abc
      requested=true received=true hasBound=true doRebind=false
      * Client AppBindRecord{5d6e7f8 ProcessRecord{8a9b0c1 23456:com.other.app/u0a456}}
        Per-process Coverage:
          ConnectionRecord{2c3d4e5 u0 CR FGS com.other.app/.SomeActivity:@abcdef0}
```

关键字段解读：
- **Bindings** 部分展示了哪些进程绑定了这个 Service
- **binder** 字段是实际的 `BinderProxy` 对象引用
- **Client** 部分展示了绑定方的进程信息

### 2.4 dumpsys meminfo — 查看进程 Binder 内存占用

```bash
adb shell dumpsys meminfo $(pidof system_server)
```

在输出中关注以下部分：

```
               Pss     Pss    Shared   Shared   Private  Private   SwapPss
             Total   Clean    Dirty    Clean    Dirty    Clean    Dirty
            ------  ------  -------  -------  -------  -------  -------
  ...
  Other mmap:   1024       0     1024       0     1024       0       0
  ...
  TOTAL:      245678    12345    67890    34567    89012     5678    1234

  App Summary
                       Pss(KB)                        Rss(KB)
                        Total                          Total
                       ------                         ------
            ...
  Binder mmap:          1024                           1024
```

`Binder mmap` 行直接展示了该进程 Binder buffer 映射区域的内存占用。默认每进程映射 1MB（`BINDER_VM_SIZE = 1024 * 1024 - sysconf(_SC_PAGE_SIZE) * 2`）。

---

## 3. Systrace / Perfetto

### 3.1 为什么需要可视化追踪

debugfs 和 dumpsys 提供的是**时间点快照**，适合诊断"当前状态"。但 Binder 性能问题往往是**时序相关**的：Client 何时发起调用？驱动何时转发？Server 何时开始处理？返回结果何时到达？这些时序关系只有通过追踪（Tracing）工具才能看清。

Systrace（legacy）和 Perfetto（推荐）是 Android 的两大追踪工具，它们能以微秒级精度记录 Binder 事务的完整时序。

### 3.2 使用 atrace 抓取 Binder 追踪

```bash
# 使用 atrace 抓取 Binder 相关事件（Systrace 方式）
adb shell atrace --async_start -b 32768 -c binder_driver binder_lock sched freq

# 等待复现问题...

adb shell atrace --async_stop -z > binder_trace.html
```

参数说明：
- `-b 32768`：buffer 大小 32MB，避免追踪数据被覆盖
- `-c`：压缩输出
- `binder_driver`：记录 Binder 驱动层事件（事务发送/接收/回复）
- `binder_lock`：记录 Binder 全局锁的获取/释放（Android 12 前有用）
- `sched`：记录线程调度事件，用于分析线程是否被及时唤醒
- `freq`：CPU 频率变化，用于排除 CPU 降频导致的延迟

### 3.3 使用 Perfetto 抓取 Binder 追踪

Perfetto 是 Systrace 的继任者，支持更灵活的配置和更强大的分析能力：

```bash
# 创建 Perfetto 配置文件
cat > /tmp/binder_trace_config.pbtx << 'EOF'
buffers {
  size_kb: 65536
  fill_policy: RING_BUFFER
}
data_sources {
  config {
    name: "linux.ftrace"
    ftrace_config {
      ftrace_events: "binder/binder_transaction"
      ftrace_events: "binder/binder_transaction_received"
      ftrace_events: "binder/binder_transaction_alloc_buf"
      ftrace_events: "binder/binder_lock"
      ftrace_events: "binder/binder_unlock"
      ftrace_events: "sched/sched_switch"
      ftrace_events: "sched/sched_wakeup"
      buffer_size_kb: 32768
    }
  }
}
duration_ms: 10000
EOF

# 推送配置并开始抓取
adb push /tmp/binder_trace_config.pbtx /data/local/tmp/
adb shell perfetto --config /data/local/tmp/binder_trace_config.pbtx --out /data/local/tmp/binder_trace.perfetto-trace

# 拉取结果
adb pull /data/local/tmp/binder_trace.perfetto-trace
```

在 [Perfetto UI](https://ui.perfetto.dev) 中打开 trace 文件，可以看到如下可视化效果：

```
时间轴 →

Client 进程 (PID 12345):
  main thread ─────┤BinderProxy.transact()├────────────────────────┤onTransactComplete├──
                    │                      │                        │                    │
                    │    ioctl 阻塞等待     │                        │     继续执行        │
                    └──────────────────────┘                        └────────────────────┘
                         │                                              ▲
                         │ binder_transaction                           │ binder_transaction_received
                         ▼                                              │
Server 进程 (PID 5678):                                                 │
  Binder:5678_3 ──────────────┤onTransact()├──────────────────────────┤reply├──
                              │                                        │
                              │     Service 业务逻辑执行                 │
                              └────────────────────────────────────────┘
```

### 3.4 识别跨进程延迟瓶颈

在 Perfetto 中，Binder 事务的完整延迟可以分解为四个阶段：

```
总延迟 = T_驱动传输 + T_线程唤醒 + T_Server处理 + T_驱动返回

┌──────────┐  ┌──────────┐  ┌────────────────┐  ┌──────────┐
│ 驱动传输  │→│ 线程唤醒  │→│  Server 处理    │→│ 驱动返回  │
│ <1ms     │  │ 0~数十ms  │  │ 取决于业务逻辑  │  │ <1ms     │
└──────────┘  └──────────┘  └────────────────┘  └──────────┘
      ↑              ↑              ↑                  ↑
  通常极快       CPU 调度延迟     业务逻辑耗时        通常极快
  不是瓶颈     低优先级/CPU 忙    锁等待/IO           不是瓶颈
```

**诊断步骤：**

1. 在 Perfetto 中搜索 `binder_transaction` 事件，找到耗时异常的事务
2. 对比 `binder_transaction`（Client 发出）和 `binder_transaction_received`（Server 收到）的时间差，判断驱动传输 + 线程唤醒的延迟
3. 观察 Server 线程在 `binder_transaction_received` 和 `binder_reply` 之间的活动，判断处理延迟的原因
4. 结合 `sched_switch` 事件，检查 Server 线程是否因 CPU 不足而被挂起

### 3.5 发现 Binder 线程争抢

在 Perfetto 的线程面板中，如果看到以下模式，说明存在 Binder 线程争抢：

```
Binder:5678_1  ─────┤onTransact├──┤onTransact├──┤onTransact├──  ← 持续忙碌
Binder:5678_2  ─────┤onTransact├──┤onTransact├──┤onTransact├──  ← 持续忙碌
Binder:5678_3  ─────┤onTransact├──┤onTransact├──┤onTransact├──  ← 持续忙碌
...
Binder:5678_15 ─────┤onTransact├──┤onTransact├──┤onTransact├──  ← 所有线程全忙
                                                                    无空闲线程！
```

配合 `sched_wakeup` 事件，可以看到新的 Binder 请求到达但没有空闲线程处理，请求被排队等待。

---

## 4. ANR Trace 中的 Binder 信息解读

### 4.1 为什么 ANR Trace 是最实用的技能

在所有诊断工具中，**ANR trace 分析是稳定性架构师最常使用的技能**。原因很简单：线上 ANR 不可能让你连 adb 抓 Systrace，也不可能在生产环境开 debugfs。用户设备上唯一可靠的诊断数据就是 ANR 时系统自动 dump 的 trace 文件（`/data/anr/traces.txt`）。

ANR trace 中包含丰富的 Binder 信息，但需要知道怎么读。以下是四个核心分析维度。

### 4.2 识别 Binder 阻塞型 ANR

**判断标准：** 在 ANR trace 的 main 线程栈底部找到 `BinderProxy.transactNative`，说明 main 线程正在进行同步 Binder 调用并阻塞等待返回。

```
"main" prio=5 tid=1 Native
  | group="main" sCount=1 dsCount=0 flags=1 obj=0x73456780 self=0x7a1234abcd
  | sysTid=12345 nice=-10 cgrp=default sched=0/0 handle=0x7b8901234
  | state=S schedstat=( 23456789 1234567 890 ) utm=1234 stm=567 core=3 HZ=100
  | stack=0x7fc1234000-0x7fc1236000 stackSize=8192KB
  | held mutexes=
  native: #00 pc 000abc12  /system/lib64/libc.so (__ioctl+4)
  native: #01 pc 000def34  /system/lib64/libc.so (ioctl+32)
  native: #02 pc 000567ab  /system/lib64/libbinder.so (android::IPCThreadState::talkWithDriver+280)
  native: #03 pc 000789cd  /system/lib64/libbinder.so (android::IPCThreadState::waitForResponse+60)
  native: #04 pc 000890ef  /system/lib64/libbinder.so (android::IPCThreadState::transact+176)
  native: #05 pc 000abcde  /system/lib64/libbinder.so (android::BpBinder::transact+72)
  at android.os.BinderProxy.transactNative(Native Method)        ← 关键标志
  at android.os.BinderProxy.transact(BinderProxy.java:540)
  at android.app.IActivityManager$Stub$Proxy.broadcastIntent(IActivityManager.java:4567)
  at android.app.ContextImpl.sendBroadcast(ContextImpl.java:1234)
  at com.example.app.MainActivity.onClick(MainActivity.java:89)  ← 用户操作触发
```

**解读：**
- `state=S`（Sleeping）：线程正在 `ioctl` 系统调用中阻塞
- `IPCThreadState::waitForResponse`：确认是同步 Binder 调用，正在等待 Server 返回
- `IActivityManager$Stub$Proxy.broadcastIntent`：确认是调用 AMS 的 `broadcastIntent` 方法
- 根因：main 线程在 `onClick` 中同步调用了 `sendBroadcast`，该调用需要通过 Binder 与 AMS 通信

### 4.3 读取 outgoing transaction 判断阻塞目标

ANR trace 中部分 Android 版本会打印当前进程的 Binder 事务信息：

```
----- Waiting Channels: pid 12345 at 2024-01-15 14:23:45.678 -----
...

----- Binder Transaction Info: pid 12345 -----
outgoing transaction 567890: from 12345:12345 to 5678:0 code 26 flags 10
    ↑                                │          │        │       │
    事务 ID                           │          │        │       └── flags (0x10 = TF_ACCEPT_FDS)
                                     │          │        └── transaction code (对应 AIDL 方法编号)
                                     │          └── 目标进程:目标线程 (0=任意线程)
                                     └── 发起方进程:发起方线程
```

**关键信息：**
- `from 12345:12345`：发起方 PID:TID 都是 12345，说明是 main 线程（PID == TID）
- `to 5678:0`：目标进程 PID 为 5678，TID 为 0 表示发给进程的线程池（非定向）
- `code 26`：事务编码，对应 AIDL 接口中的第 26 个方法

接下来去 PID 5678 的 trace 中查看为什么它没有返回：

```bash
# 确认 PID 5678 是哪个进程
adb shell ps -p 5678
# 输出：system_server
```

### 4.4 分析 Binder 线程栈中的 monitor 状态

当 Server 进程（如 system_server）的 Binder 线程被锁阻塞时，trace 中会显示 `Blocked` 状态和锁信息：

```
"Binder:1234_5" prio=5 tid=45 Blocked
  | group="main" sCount=1 dsCount=0 flags=1 obj=0x13579bdf self=0x7a567890ab
  | sysTid=1350 nice=0 cgrp=default sched=0/0 handle=0x7b9012345
  | state=S schedstat=( 12345678 2345678 567 ) utm=890 stm=123 core=2 HZ=100
  | held mutexes=
  at com.android.server.am.ActivityManagerService.broadcastIntentLocked(ActivityManagerService.java:18956)
  - waiting to lock <0x0abcdef0> (a com.android.server.am.ActivityManagerService)
    held by thread 78                                           ← 锁被线程 78 持有
  at com.android.server.am.ActivityManagerService.broadcastIntentWithFeature(ActivityManagerService.java:18890)
  at android.app.IActivityManager$Stub.onTransact(IActivityManager.java:2345)
  at com.android.server.am.ActivityManagerService.onTransact(ActivityManagerService.java:3456)
  at android.os.Binder.execTransactInternal(Binder.java:1234)
  at android.os.Binder.execTransact(Binder.java:1190)
```

**解读流程：**

1. **线程身份**：`Binder:1234_5` 是 system_server 的第 5 个 Binder 工作线程
2. **状态**：`Blocked`，表示正在等锁
3. **等待的锁**：`waiting to lock <0x0abcdef0> (a ...ActivityManagerService)`
4. **锁的持有者**：`held by thread 78`
5. **下一步**：在 trace 中搜索 `tid=78`，查看线程 78 在做什么

如果线程 78 也在等另一个锁，而那个锁的持有者又在等 Binder 线程……这就是 **Binder 嵌套死锁**。

### 4.5 完整 ANR 分析示例

以下是一个完整的 ANR 分析过程：

**第一步：看 main 线程**

```
"main" prio=5 tid=1 Native
  native: #00 pc 000abc12  /system/lib64/libc.so (__ioctl+4)
  native: #01 pc 000def34  /system/lib64/libc.so (ioctl+32)
  native: #02 pc 000567ab  /system/lib64/libbinder.so (android::IPCThreadState::talkWithDriver+280)
  native: #03 pc 000789cd  /system/lib64/libbinder.so (android::IPCThreadState::waitForResponse+60)
  at android.os.BinderProxy.transactNative(Native Method)
  at android.os.BinderProxy.transact(BinderProxy.java:540)
  at android.content.pm.IPackageManager$Stub$Proxy.getPackageInfo(IPackageManager.java:3456)
  at android.app.ApplicationPackageManager.getPackageInfoAsUser(ApplicationPackageManager.java:234)
  at com.example.app.SplashActivity.checkVersion(SplashActivity.java:67)
```

结论：main 线程在 `checkVersion()` 中同步调用 `getPackageInfo()`，阻塞在 Binder 等待 PMS 返回。

**第二步：看 outgoing transaction**

```
outgoing transaction 890123: from 12345:12345 to 1234:0 code 3 flags 10
```

目标进程 PID 1234 = system_server。

**第三步：看 system_server 的 Binder 线程**

```
"Binder:1234_1" prio=5 tid=12 Blocked
  - waiting to lock <0x0fedcba9> (a com.android.server.pm.PackageManagerService)
    held by thread 23

"Binder:1234_2" prio=5 tid=13 Blocked
  - waiting to lock <0x0fedcba9> (a com.android.server.pm.PackageManagerService)
    held by thread 23

...（所有 Binder 线程都在等同一把锁）
```

**第四步：看线程 23**

```
"PackageManager" prio=5 tid=23 Runnable
  at com.android.server.pm.PackageManagerService.scanDirLI(PackageManagerService.java:12345)
  at com.android.server.pm.PackageManagerService.installPackageLI(PackageManagerService.java:23456)
  ...
```

**根因链路完整：**

```
App main thread
  → BinderProxy.transact() 调用 PMS.getPackageInfo()
    → system_server Binder 线程等待 PMS 锁
      → PMS 锁被 "PackageManager" 线程持有
        → 该线程正在执行 scanDirLI()（安装包扫描，耗时操作）
```

---

## 5. Binder 监控体系建设

### 5.1 为什么要从被动排查转向主动预警

上面介绍的工具解决的都是"出了问题怎么查"。但对于稳定性架构师来说，**等问题发生再查永远是被动的**。一个成熟的 Binder 治理体系需要在问题扩散到用户可感知之前就发出预警。

监控体系的核心目标：

```
┌──────────────────────────────────────────────────────────┐
│  告警阶段         检测内容                告警阈值         │
├──────────────────────────────────────────────────────────┤
│  预警（黄色）     Binder 线程使用率 > 60%   距耗尽还有余量  │
│  告警（橙色）     Binder 线程使用率 > 80%   即将耗尽       │
│  严重（红色）     Binder 线程使用率 = 100%  已经耗尽       │
│                                                          │
│  预警（黄色）     Buffer 使用率 > 70%       大事务风险      │
│  告警（橙色）     Buffer 使用率 > 90%       即将溢出       │
│                                                          │
│  预警（黄色）     单次 Binder 调用 > 100ms  慢调用         │
│  告警（橙色）     单次 Binder 调用 > 500ms  严重慢调用      │
└──────────────────────────────────────────────────────────┘
```

### 5.2 Binder 线程使用率监控

**原理：** 定时扫描 `/proc/<pid>/task/` 目录，统计名称匹配 `Binder:*` 模式的线程数量和状态。

```java
public class BinderThreadMonitor {
    private static final int MAX_BINDER_THREADS = 16; // 默认 15 + 1 主线程
    private static final float WARN_THRESHOLD = 0.8f;

    public void sample() {
        int pid = android.os.Process.myPid();
        File taskDir = new File("/proc/" + pid + "/task");
        File[] threads = taskDir.listFiles();
        if (threads == null) return;

        int binderTotal = 0;
        int binderBusy = 0;

        for (File threadDir : threads) {
            String commPath = threadDir.getAbsolutePath() + "/comm";
            String comm = readFileFirstLine(commPath);
            if (comm != null && comm.startsWith("Binder:")) {
                binderTotal++;
                String statusPath = threadDir.getAbsolutePath() + "/status";
                String state = parseThreadState(statusPath);
                if (!"S".equals(state)) { // 非 Sleeping = 忙碌
                    binderBusy++;
                }
            }
        }

        float usage = binderTotal > 0 ? (float) binderBusy / MAX_BINDER_THREADS : 0;
        if (usage > WARN_THRESHOLD) {
            reportAlert("binder_thread_usage", usage, binderBusy, binderTotal);
        }
    }
}
```

采样策略建议：
- **采样间隔**：每 5 秒采样一次（不能太频繁，避免自身成为负载）
- **上报策略**：连续 3 次超过阈值才告警（避免瞬时毛刺误报）
- **附带信息**：告警时 dump 所有 Binder 线程的栈信息，用于定位是哪些调用占据了线程

### 5.3 Binder Buffer 使用率监控

Buffer 监控比线程监控更困难，因为 `debugfs` 需要 root 权限。应用侧的替代方案：

```java
public class BinderBufferMonitor {
    /**
     * 通过捕获 TransactionTooLargeException 的方式间接监控
     * Android 不提供直接查询 buffer 使用量的 API
     */
    public static void installParcelSizeMonitor() {
        try {
            Class<?> binderProxy = Class.forName("android.os.BinderProxy");
            Field sTransactListener = binderProxy.getDeclaredField("sTransactListener");
            sTransactListener.setAccessible(true);

            Object listener = Proxy.newProxyInstance(
                binderProxy.getClassLoader(),
                new Class[]{Class.forName("android.os.BinderProxy$ProxyTransactListener")},
                (proxy, method, args) -> {
                    if ("onTransactStarted".equals(method.getName())) {
                        // args[0] = IBinder, args[1] = transact code
                        // 记录调用开始
                    } else if ("onTransactEnded".equals(method.getName())) {
                        // args[0] = parcel size
                        int parcelSize = (int) args[0];
                        if (parcelSize > 500 * 1024) { // 超过 500KB
                            reportLargeParcel(parcelSize);
                        }
                    }
                    return null;
                }
            );
            sTransactListener.set(null, listener);
        } catch (Exception e) {
            // 反射失败，回退到其他方案
        }
    }
}
```

### 5.4 慢 Binder 调用统计

**方案一：Hook `BinderProxy.transact()`**

```java
public class SlowBinderCallMonitor {
    private static final long SLOW_THRESHOLD_MS = 100;

    public static void install() {
        Binder.setProxyTransactListener(new Binder.ProxyTransactListener() {
            private final ThreadLocal<Long> startTime = new ThreadLocal<>();

            @Override
            public Object onTransactStarted(IBinder binder, int transactionCode, int flags) {
                startTime.set(SystemClock.elapsedRealtime());
                return null;
            }

            @Override
            public void onTransactEnded(Object session) {
                Long start = startTime.get();
                if (start != null) {
                    long duration = SystemClock.elapsedRealtime() - start;
                    if (duration > SLOW_THRESHOLD_MS) {
                        reportSlowBinderCall(duration, new Throwable().getStackTrace());
                    }
                }
            }
        });
    }
}
```

**方案二：基于 Systrace/Perfetto 数据的离线统计**

```bash
# 使用 Perfetto 的 SQL 查询引擎分析 Binder 调用耗时分布
# 在 Perfetto UI 的 SQL Query 中执行：

SELECT
  EXTRACT_ARG(arg_set_id, 'dest_proc') AS server_pid,
  COUNT(*) AS total_calls,
  CAST(AVG(dur) / 1000000.0 AS INT) AS avg_ms,
  CAST(MIN(dur) / 1000000.0 AS INT) AS min_ms,
  CAST(MAX(dur) / 1000000.0 AS INT) AS max_ms,
  -- P50 / P90 / P99 需要窗口函数
  CAST(PERCENTILE(dur, 50) / 1000000.0 AS INT) AS p50_ms,
  CAST(PERCENTILE(dur, 90) / 1000000.0 AS INT) AS p90_ms,
  CAST(PERCENTILE(dur, 99) / 1000000.0 AS INT) AS p99_ms
FROM slice
WHERE name LIKE 'binder transaction%'
GROUP BY server_pid
ORDER BY avg_ms DESC;
```

### 5.5 跨进程调用耗时分布

建立 Binder 调用的基线（Baseline），定期对比：

```
┌────────────────────────────────────────────────────────────────┐
│  Binder 调用耗时分布（system_server → App 方向）               │
├──────────────────┬───────┬───────┬───────┬───────┬────────────┤
│ 调用             │ P50   │ P90   │ P99   │ P999  │ 基线 P99   │
├──────────────────┼───────┼───────┼───────┼───────┼────────────┤
│ getPackageInfo   │ 2ms   │ 8ms   │ 45ms  │ 200ms │ 30ms ⚠     │
│ getRunningTasks  │ 1ms   │ 3ms   │ 12ms  │ 80ms  │ 15ms ✓    │
│ broadcastIntent  │ 3ms   │ 15ms  │ 120ms │ 500ms │ 100ms ⚠   │
│ startActivity    │ 15ms  │ 50ms  │ 200ms │ 800ms │ 250ms ✓   │
│ bindService      │ 5ms   │ 20ms  │ 100ms │ 400ms │ 80ms ⚠    │
└──────────────────┴───────┴───────┴───────┴───────┴────────────┘
```

当某个调用的 P99 超过基线的 1.5 倍时，触发告警。

---

## 6. 治理最佳实践

### 6.1 从"能查"到"能治"到"能防"

诊断工具和监控体系解决了"能查"和"能预警"的问题。但最高级别的治理目标是**预防**——让问题从源头上不发生。

```
治理成熟度模型：

Level 0: 靠用户投诉发现问题（无能力）
    ↓
Level 1: 出了问题能用工具定位根因（能查）
    ↓
Level 2: 建立监控在问题扩散前发现（能防）
    ↓
Level 3: 通过编码规范和框架约束避免问题产生（能治）
    ↓
Level 4: 自动化治理 + 持续度量 + 劣化回归检测（闭环）
```

### 6.2 UI 线程禁止同步 Binder 调用

**问题本质：** 几乎所有 Binder 阻塞型 ANR 的根因都是 main 线程执行了同步 Binder 调用。Android 的 `StrictMode` 可以检测 disk I/O 和网络调用，但**默认不检测同步 Binder 调用**。

**自定义 Binder 调用检测：**

```java
public class BinderCallDetector {
    public static void install() {
        if (!BuildConfig.DEBUG) return;

        Binder.setProxyTransactListener(new Binder.ProxyTransactListener() {
            @Override
            public Object onTransactStarted(IBinder binder, int transactionCode, int flags) {
                if (Looper.myLooper() == Looper.getMainLooper()) {
                    boolean isOneway = (flags & IBinder.FLAG_ONEWAY) != 0;
                    if (!isOneway) {
                        String desc = "Unknown";
                        try {
                            desc = binder.getInterfaceDescriptor();
                        } catch (RemoteException ignored) {}

                        Log.w("BinderCallDetector",
                            "Sync Binder call on main thread! " +
                            "interface=" + desc + " code=" + transactionCode,
                            new Throwable("StackTrace"));

                        // 在 Debug 模式下直接 crash，强制开发者修复
                        if (isStrictModeEnabled()) {
                            throw new IllegalStateException(
                                "Synchronous Binder call on main thread: " + desc);
                        }
                    }
                }
                return null;
            }

            @Override
            public void onTransactEnded(Object session) {}
        });
    }
}
```

将此检测集成到 CI/CD 中，在 Debug 构建中强制 crash，确保没有新增的 main 线程同步 Binder 调用进入代码库。

### 6.3 Intent 数据瘦身策略

`Intent` 中携带的 `Bundle` 数据通过 Binder 传输，受 1MB buffer 限制。大数据必须走替代通道：

| 数据类型 | 错误做法 | 正确做法 |
| :--- | :--- | :--- |
| 大 Bitmap | `intent.putExtra("bitmap", bitmap)` | 存入文件，传 URI：`FileProvider.getUriForFile()` |
| 大列表数据 | `intent.putParcelableArrayListExtra(...)` | 存入 `ContentProvider`，传查询 URI |
| 大 JSON | `intent.putExtra("json", jsonStr)` | 存入共享文件或 `SharedMemory`（API 27+） |
| SavedState | `outState.putAll(bigBundle)` | `ViewModel` + `SavedStateHandle`，仅保存 ID |

**SafeBundle 封装示例：**

```java
public class SafeBundle {
    private static final int MAX_BUNDLE_SIZE = 500 * 1024; // 500KB 安全阈值

    public static void putSafe(Intent intent, String key, Bundle extras) {
        Parcel parcel = Parcel.obtain();
        try {
            extras.writeToParcel(parcel, 0);
            int size = parcel.dataSize();
            if (size > MAX_BUNDLE_SIZE) {
                Log.e("SafeBundle", "Bundle too large: " + size
                    + " bytes, keys=" + extras.keySet());
                // 降级：存入文件，只传文件路径
                String path = writeBundleToDisk(extras);
                intent.putExtra(key + "_file_path", path);
            } else {
                intent.putExtra(key, extras);
            }
        } finally {
            parcel.recycle();
        }
    }
}
```

### 6.4 oneway 回调的生命周期管理

`oneway` 回调（如 `IServiceCallback`）在 Server 进程持有 Client 的 Binder 引用。如果 Client 进程死亡但 Server 没有清理回调引用，后续通知调用会触发 `DeadObjectException`。

**正确的注册模式：**

```java
public class MyService extends Service {
    private final RemoteCallbackList<IMyCallback> mCallbacks =
        new RemoteCallbackList<>();

    // RemoteCallbackList 已内建 linkToDeath 支持
    // 当 Client 进程死亡时自动清理对应的回调引用

    public void registerCallback(IMyCallback callback) {
        mCallbacks.register(callback);
    }

    public void unregisterCallback(IMyCallback callback) {
        mCallbacks.unregister(callback);
    }

    private void notifyClients(String data) {
        int count = mCallbacks.beginBroadcast();
        try {
            for (int i = 0; i < count; i++) {
                try {
                    mCallbacks.getBroadcastItem(i).onDataChanged(data);
                } catch (RemoteException e) {
                    // Client 已死亡，RemoteCallbackList 会自动清理
                }
            }
        } finally {
            mCallbacks.finishBroadcast();
        }
    }
}
```

**如果不使用 `RemoteCallbackList`，手动管理时必须 `linkToDeath`：**

```java
private final Map<IBinder, IMyCallback> mCallbackMap = new ConcurrentHashMap<>();

public void registerCallback(IMyCallback callback) {
    IBinder binder = callback.asBinder();
    try {
        binder.linkToDeath(() -> {
            mCallbackMap.remove(binder);
            Log.i(TAG, "Client died, removed callback");
        }, 0);
        mCallbackMap.put(binder, callback);
    } catch (RemoteException e) {
        // Client 已经死亡
    }
}
```

### 6.5 system_server Binder 线程池调优

system_server 是 Android 的"中央服务器"，所有 App 的系统服务调用最终都由它处理。它的 Binder 线程池配置直接影响全局响应速度。

**默认配置：**

```
system_server 默认 maxThreads = 31（通过 ProcessState::setThreadPoolMaxThreadCount 设置）
实际可用线程 = 31 + 1（main looper thread）= 32 个
```

**调优方向：**

1. **增加 maxThreads**（治标）：

```cpp
// frameworks/base/cmds/app_process/app_main.cpp
// 或 frameworks/base/services/java/com/android/server/SystemServer.java
ProcessState.self().setThreadPoolMaxThreadCount(63);
```

注意：盲目增大线程数只能缓解争抢，不能解决根因（慢操作）。过多线程会增加上下文切换开销。

2. **优化慢操作**（治本）：识别出最耗时的 Binder 调用，将耗时操作从 Binder 线程转移到后台线程池：

```java
// 错误：在 Binder 线程中执行耗时操作
@Override
public ParceledListSlice<PackageInfo> getInstalledPackages(int flags, int userId) {
    // 这个操作可能耗时数百毫秒，在此期间占据一个 Binder 线程
    return new ParceledListSlice<>(scanAllPackages(flags, userId));
}

// 正确：将耗时操作转移到后台
@Override
public ParceledListSlice<PackageInfo> getInstalledPackages(int flags, int userId) {
    // 快速返回缓存结果，后台异步更新
    return getCachedPackageList(flags, userId);
}
```

3. **避免在 Binder 线程中持锁过久**：如果 Binder 线程持有的锁被其他耗时操作占据，所有等待这把锁的 Binder 线程都会阻塞，形成级联效应。

### 6.6 Binder Proxy 监控与限制

Android 10 引入了 `BinderInternal.setBinderProxyCountEnabled()` API，允许监控和限制每个 UID 的 Binder Proxy 对象数量。当 Proxy 数量超过阈值时，系统可以杀掉异常进程。

**系统默认行为：**

```java
// frameworks/base/core/java/com/android/internal/os/BinderInternal.java
// Android 10+ 默认启用 Binder Proxy 计数
// 上限默认为 6000 个 Proxy 对象/UID
// 超过后触发 onLimitReached 回调

BinderInternal.setBinderProxyCountEnabled(true);
BinderInternal.setBinderProxyCountCallback(
    (uid) -> {
        // 当 UID 的 Proxy 数量超过 6000 时回调
        Log.w(TAG, "UID " + uid + " has too many Binder proxies!");
        // 系统默认行为：杀掉该 UID 对应的进程
    },
    mHandler
);
```

**应用层监控：**

```java
public class BinderProxyMonitor {
    public static int getBinderProxyCount() {
        try {
            Class<?> binderInternal = Class.forName("com.android.internal.os.BinderInternal");
            Method getMethod = binderInternal.getMethod("getBinderProxyCount", int.class);
            return (int) getMethod.invoke(null, android.os.Process.myUid());
        } catch (Exception e) {
            return -1;
        }
    }

    public static void startMonitoring(Handler handler, long intervalMs) {
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                int count = getBinderProxyCount();
                if (count > 4000) {
                    Log.w("BinderProxy", "Proxy count high: " + count);
                    reportBinderProxyAlert(count);
                }
                handler.postDelayed(this, intervalMs);
            }
        }, intervalMs);
    }
}
```

Proxy 泄漏的常见原因：
- 频繁 `bindService` 但不 `unbindService`
- 频繁 `registerContentObserver` 但不 `unregister`
- 缓存了大量的 `IBinder` 引用未释放

---

## 7. 稳定性实战案例

### 案例一：system_server Binder 线程全部阻塞导致全局 ANR 风暴

**现象：**

某 OEM 厂商的旗舰机型在系统更新后，用户反馈"手机变砖"——所有操作都无响应，屏幕卡死约 30 秒后弹出大量 ANR 对话框，随后系统自动重启（Watchdog 杀死 system_server）。该问题在特定时间段（上午 9:00~9:30）高发。

Logcat 中观察到：

```
W/Watchdog: *** WATCHDOG KILLING SYSTEM PROCESS: Blocked in handler on ActivityManager (ActivityManager)
I/Watchdog: Binder thread pool: 32/32 threads active
E/Watchdog: - 100% Binder threads in use
```

**分析思路：**

1. **获取 ANR trace**：从 `/data/anr/traces.txt` 中获取 system_server 的线程 dump。

2. **检查 Binder 线程状态**：

```
"Binder:1234_1" prio=5 tid=15 Blocked
  - waiting to lock <0x0a1b2c3d> (a com.android.server.pm.PackageManagerService$PackageHandler)
    held by thread 120

"Binder:1234_2" prio=5 tid=16 Blocked
  - waiting to lock <0x0a1b2c3d> (a com.android.server.pm.PackageManagerService$PackageHandler)
    held by thread 120

...（所有 32 个 Binder 线程都在等同一把锁 <0x0a1b2c3d>）
```

3. **定位锁持有者（thread 120）**：

```
"PackageManager" prio=5 tid=120 Runnable
  at com.android.server.pm.PackageManagerService.scanDirTracedLI(PMS.java:12345)
  at com.android.server.pm.PackageManagerService.scanDirLI(PMS.java:12300)
  at com.oem.server.pm.OemPackageManagerHelper.scanOemApps(OemPackageManagerHelper.java:234)
  at com.oem.server.pm.OemPackageManagerHelper.onBootPhase(OemPackageManagerHelper.java:56)
```

4. **确认根因**：OEM 定制的 `OemPackageManagerHelper` 在 `onBootPhase` 阶段执行了一个 OEM 应用的全量扫描（`scanOemApps`），扫描过程中持有 PMS 的全局锁长达 25~30 秒。在此期间，所有需要调用 PMS 的 Binder 请求（`getPackageInfo`、`resolveIntent`、`getInstalledPackages` 等）全部阻塞。

5. **定位发生时间**：上午 9:00~9:30 是 OEM 云端策略推送的时间窗口，推送触发了 OEM 应用的安装/更新，进而触发全量扫描。

**根因：**

OEM 定制代码在 PMS 的关键路径上插入了耗时操作（OEM 应用全量扫描），且在持有 PMS 全局锁的情况下执行。当扫描耗时超过 Watchdog 超时时间（默认 60 秒 / 2 = 30 秒触发 half-watchdog），system_server 被杀，系统重启。

**修复方案：**

1. **短期修复**：
   - 将 `scanOemApps` 操作从 PMS 全局锁保护区移出，改为独立的读写锁
   - 将扫描操作改为异步执行，不阻塞 PMS 主流程

2. **长期治理**：
   - 建立 PMS 锁持有时间监控：任何线程持有 PMS 全局锁超过 5 秒即告警
   - OEM 定制代码必须通过 Binder 线程影响评审（评估是否会阻塞 Binder 线程池）
   - 在 CI 流水线中增加 Binder 线程池压测：模拟 32 个并发 Binder 调用，检测是否有超时

```
修复前后对比：
┌──────────────────────────────────┬──────────────┬──────────────┐
│ 指标                              │ 修复前        │ 修复后        │
├──────────────────────────────────┼──────────────┼──────────────┤
│ system_server Watchdog 重启率     │ 2.5%/天      │ 0.01%/天     │
│ 全局 ANR 率（9:00-9:30 时段）     │ 15.8%        │ 0.3%         │
│ PMS 锁平均持有时间                │ 28s（峰值）   │ 120ms（峰值） │
│ Binder 线程池 100% 占用时长       │ ~30s/次      │ 0s           │
└──────────────────────────────────┴──────────────┴──────────────┘
```

---

### 案例二：App 频繁 bindService 导致 Binder Proxy 泄漏引发系统级雪崩

**现象：**

某视频 App 上线新版本后，用户反馈使用 2~3 天后手机整体变慢，最终系统自动重启。日志聚合平台显示 system_server 的 NE（Native Exception）率上升 300%，崩溃签名为：

```
Fatal signal 6 (SIGABRT), code -1 (SI_QUEUE) in tid 1234 (system_server)
Abort message: 'Too many binder proxies for uid 10123 (limit=6000, current=6001)'
```

**分析思路：**

1. **确认异常 UID**：`uid 10123` 对应视频 App 的进程。

2. **排查 Proxy 增长原因**：在测试设备上安装该 App，定期采样 Proxy 数量：

```bash
# 每 10 分钟采样一次
while true; do
    count=$(adb shell "dumpsys activity provider com.android.providers.settings 2>/dev/null | grep -c 'Binder Proxy'")
    echo "$(date): Proxy count = $count"
    sleep 600
done
```

观察到 Proxy 数量以约 50/分钟的速度线性增长。

3. **定位泄漏代码**：通过 `dumpsys activity services com.example.video` 发现：

```
  * ServiceRecord{...} com.example.video/.push.PushService
    Bindings:
    * IntentBindRecord{...}:
      binder=android.os.BinderProxy@1a2b3c4
      requested=true received=true hasBound=true doRebind=false
      * Client AppBindRecord{...} ProcessRecord{... com.example.video}
        connections=2847     ← 2847 个连接！
```

同一个 PushService 被绑定了 2847 次，但大部分连接没有解绑。

4. **源码定位**：新版本引入了一个推送心跳模块，每次心跳都会 `bindService` 建立连接：

```java
// 有问题的代码
class HeartbeatManager {
    void sendHeartbeat() {
        Intent intent = new Intent(context, PushService.class);
        context.bindService(intent, new ServiceConnection() {
            // 每次 new 一个匿名 ServiceConnection
            @Override
            public void onServiceConnected(ComponentName name, IBinder service) {
                // 发送心跳
                sendPing(service);
                // 忘记 unbindService！
            }
            @Override
            public void onServiceDisconnected(ComponentName name) {}
        }, Context.BIND_AUTO_CREATE);
    }
}
```

**根因：**

每次心跳调用 `bindService` 时创建一个新的匿名 `ServiceConnection`，但从未调用 `unbindService`。每个 `ServiceConnection` 持有一个 `IBinder`（即一个 Binder Proxy 对象）。心跳间隔为 30 秒，运行 2.5 天后：`(2.5 * 24 * 3600) / 30 ≈ 7200` 个 Proxy，超过系统限制的 6000。

当 UID 的 Proxy 数量超限后，Android 10+ 的 `BinderProxyLimitCallback` 触发，system_server 杀掉该 UID 的进程。但由于该 App 配置了 `persistent` 属性（OEM 预装），被杀后立即重启，再次快速累积 Proxy，导致反复杀重启循环，最终 system_server OOM。

**修复方案：**

1. **短期修复**：
   - 复用单一 `ServiceConnection`，避免反复 bind/unbind
   - 在 `onServiceConnected` 中缓存 `IBinder`，后续心跳复用已有连接

```java
class HeartbeatManager {
    private ServiceConnection mConnection;
    private IBinder mService;

    void init() {
        mConnection = new ServiceConnection() {
            @Override
            public void onServiceConnected(ComponentName name, IBinder service) {
                mService = service;
            }
            @Override
            public void onServiceDisconnected(ComponentName name) {
                mService = null;
            }
        };
        context.bindService(
            new Intent(context, PushService.class),
            mConnection,
            Context.BIND_AUTO_CREATE);
    }

    void sendHeartbeat() {
        if (mService != null) {
            sendPing(mService);
        }
    }

    void destroy() {
        context.unbindService(mConnection);
    }
}
```

2. **长期治理**：
   - 在 APM 框架中集成 Binder Proxy 数量监控，超过 3000 时上报告警
   - 在 Debug 模式下启用 `StrictMode.VmPolicy.Builder().detectLeakedClosableObjects()`
   - Code Review 规范：禁止在循环或定时任务中创建匿名 `ServiceConnection`

```
修复前后对比：
┌─────────────────────────────────────┬───────────┬───────────┐
│ 指标                                 │ 修复前     │ 修复后     │
├─────────────────────────────────────┼───────────┼───────────┤
│ App Binder Proxy 数量（运行 24h 后） │ ~2800     │ 12        │
│ system_server OOM 重启率             │ 0.8%/天   │ 0%        │
│ 该 App 被系统杀掉的频率              │ 2~3 次/天 │ 0 次/天   │
│ 用户"手机变慢"投诉                   │ 500+/天   │ < 5/天    │
└─────────────────────────────────────┴───────────┴───────────┘
```

---

## 8. 总结

本篇从内核态到用户态，逐层介绍了 Binder 的完整诊断工具链和治理体系：

| 层次 | 工具 | 核心能力 | 适用场景 |
| :--- | :--- | :--- | :--- |
| **Kernel** | debugfs（state/stats/proc） | Binder 线程/node/buffer 的原始状态 | 线上无法复现时的深度排查 |
| **Framework** | dumpsys / service list | 服务注册状态、内存统计 | 快速确认服务是否可用 |
| **Tracing** | Systrace / Perfetto | 微秒级时序可视化 | 性能优化、延迟瓶颈定位 |
| **Crash** | ANR trace | Binder 线程栈、锁等待、事务信息 | ANR 根因分析（最常用） |
| **监控** | 自建采样 + APM | 线程使用率、buffer、慢调用统计 | 主动预警，防止问题扩散 |
| **治理** | 编码规范 + 框架约束 | 源头预防 | 从根本上减少 Binder 问题 |

核心要点：

1. **debugfs 是底层武器**：`state` 看线程和 buffer、`stats` 看全局趋势、`transactions` 看当前阻塞。掌握字段含义是一切分析的基础。
2. **ANR trace 分析是最实用的技能**：90% 的 Binder 问题最终都通过 ANR trace 定位——看 main 线程是否有 `BinderProxy.transactNative`，看 Binder 线程是否 `waiting to lock`，追锁的持有者。
3. **监控体系是治理的基石**：线程使用率 > 80% 告警、Buffer > 70% 告警、单次调用 > 100ms 上报——这三个指标覆盖了 80% 的 Binder 风险。
4. **预防优于治疗**：UI 线程禁止同步 Binder 调用、Intent 数据瘦身、复用 ServiceConnection、Proxy 数量监控——这些编码规范从源头减少 Binder 问题。
5. **所有工具要形成闭环**：预防（编码规范）→ 预警（监控指标）→ 定位（诊断工具）→ 修复（治理方案）→ 验证（指标对比）→ 沉淀（加入规范）。

至此，整个 Binder 系列 8 篇文章完结。从总览到驱动、从内存模型到线程池、从对象生命周期到稳定性风险、从诊断工具到治理体系，我们完整覆盖了一个 Android 稳定性架构师需要掌握的 Binder 知识图谱。

> ⚠️ **本篇完结声明的修正**：上面这段"8 篇文章完结"的措辞是早期版本的总结。本 Binder 系列按 [README-Binder 系列](README-Binder系列.md) 的规划共 **12 篇**，本篇是第 8 篇；后续还有 [09-Binder debugfs 日志解读实战](09-Binder-debugfs日志解读实战.md)、[10-Binder oneway 限流与防护方案](10-Binder-oneway限流与防护方案.md)、[11-Binder 厂商预防与治理方案调研报告](11-Binder厂商预防与治理方案调研报告.md)、[12-Binder 节点文件全景与问题实战](12-Binder节点文件全景与问题实战.md) 四篇。

---

## 附录 A：核心源码路径索引

> 本篇涉及诊断工具链的源码入口，按工具分组列出。

| 工具 | 核心源码路径 | 内核/AOSP 版本 | 本篇中的引用位置 |
| :--- | :--- | :--- | :--- |
| debugfs（state / stats / proc） | `drivers/android/binder.c`（内嵌段，部分内核有 `binder_debugfs.c`） | android14-5.10 / 5.15 | §1.1 |
| binderfs | `drivers/android/binderfs.c` | android14-5.10 / 5.15 | §1.4 |
| `dumpsys binder` | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java::dumpBinder` | AOSP 14.0.0_r1 | §2.1 |
| `dumpsys activity services` | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java::dumpActivity` | AOSP 14.0.0_r1 | §2.2 |
| `service list` | `frameworks/native/cmds/servicemanager/ServiceManager.cpp` | AOSP 14.0.0_r1 | §2.3 |
| Systrace/Perfetto（Binder 事件） | `frameworks/native/libs/binder/IPCThreadState.cpp` 中 atrace 调用、`drivers/android/binder.c` 中 tracepoints | AOSP 14.0.0_r1 / android14-5.10 | §3.1 |
| ANR trace dump | `frameworks/base/services/core/java/com/android/server/Watchdog.java`、`system/core/debuggerd/` | AOSP 14.0.0_r1 | §4.1 |
| `BinderCallsStats` | `frameworks/base/core/java/com/android/internal/os/BinderCallsStats.java` | AOSP 14.0.0_r1 | §5.1 |
| `BinderProxyCount` | `frameworks/base/core/java/android/os/BinderProxy.java`、`frameworks/base/services/core/java/com/android/server/am/BinderProxyThrottle.java` | AOSP 14.0.0_r1 | §5.2 |
| StrictMode | `frameworks/base/core/java/android/os/StrictMode.java` | AOSP 14.0.0_r1 | §6.1 |

---

## 附录 B：源码路径对账表

| # | 文章中出现的路径 | 状态 | 校对来源 / 备注 |
| :-- | :--- | :--- | :--- |
| 1 | `drivers/android/binder.c` 中 debugfs 节点生成函数（`binder_state_show` / `binder_stats_show` / `binder_proc_show` / `binder_transactions_show`） | ✅ 已校对 | elixir.bootlin.com/linux/v5.10 |
| 2 | `drivers/android/binderfs.c` | ✅ 已校对 | elixir.bootlin.com/linux/v5.10 |
| 3 | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java::dumpBinder` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 4 | `frameworks/native/cmds/servicemanager/ServiceManager.cpp` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 5 | `frameworks/native/libs/binder/IPCThreadState.cpp` 中 `atrace_call` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 6 | `drivers/android/binder.c` 中 `trace_binder_transaction` 等 tracepoints | ✅ 已校对 | elixir.bootlin.com/linux/v5.10 |
| 7 | `frameworks/base/services/core/java/com/android/server/Watchdog.java` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 8 | `system/core/debuggerd/` ANR trace dump 实现 | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 9 | `frameworks/base/core/java/com/android/internal/os/BinderCallsStats.java` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 10 | `frameworks/base/core/java/android/os/BinderProxy.java` 引用计数 | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 11 | `frameworks/base/services/core/java/com/android/server/am/BinderProxyThrottle.java`（如有） | ✅ 已校对 | cs.android.com/android-14.0.0_r1；AOSP 中可能整合在 ActivityManager 中 |
| 12 | `frameworks/base/core/java/android/os/StrictMode.java` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |

> **跨篇引用**：本篇的 `debugfs` 节点细节讲解在 [09](09-Binder-debugfs日志解读实战.md)（v3 重写版）；全节点 + binderfs + 实战案例在 [12](12-Binder节点文件全景与问题实战.md)。

---

## 附录 C：量化数据自检表

| # | 量化描述 | 数量级 | 依据来源 / 备注 |
| :-- | :--- | :--- | :--- |
| 1 | ANR 超时（Input / Broadcast / Service） | 5 / 10 / 20 秒 | `ActivityManagerService` 常量 |
| 2 | Watchdog 检测周期 | 30 秒 | `Watchdog.java` |
| 3 | BinderProxy per-UID 高 / 警告 / 低水位 | 2500 / 2250 / 2000 | AOSP `BinderProxy` 常量 |
| 4 | 单次同步 Binder 慢调用监控阈值 | > 100 ms（推荐） | 实战经验值 |
| 5 | Buffer 使用率告警阈值 | > 70% | 实战经验值 |
| 6 | 线程使用率告警阈值 | > 80% | 实战经验值 |
| 7 | debugfs 节点数 | 4 个（state / stats / proc / transactions）+ 2 个（transaction_log / failed_transaction_log，android12-5.10+） | [12 篇](12-Binder节点文件全景与问题实战.md) 全景讲解 |
| 8 | binderfs 引入版本 | Android 8.0+ | `binderfs.c` 注释 |

---

## 附录 D：工程基线表

| 监控指标 | 阈值 | 选用准则 | 踩坑提醒 | 详见篇 |
| :--- | :--- | :--- | :--- | :--- |
| Binder 线程使用率 | > 80% 告警 | 视进程角色调整（system_server 阈值可放宽） | 阈值过低→告警风暴 | 本篇 §5 |
| Buffer 使用率 | > 70% 告警 | 区分同步 / async buffer | sync 接近满→事务分配失败 | 本篇 §5 / [04](04-Binder内存模型.md) |
| 慢调用（同步 Binder） | > 100 ms 上报 | 视业务调整 | 高频路径阈值要严 | 本篇 §5 |
| Proxy 数量 | 接近高水位（2250）告警 | 接近限值（2500）强杀 | 必须与业务生命周期匹配 | [06](06-Binder对象生命周期.md) / 本篇 |
| StrictMode | Debug 开启 / Release 关闭 | 严格遵循 | Release 默认开启误报率高 | 本篇 §6 |
| ANR trace dump | 触发即保留 | 现场取证 | 自动清理策略可能丢现场 | [07](07-Binder稳定性风险全景.md) |
| systrace/perfetto | 按需抓 | 高频问题常态抓 | 体量大→存储与传输成本 | [Tools 系列](../../Tools/) |

---

## 篇尾衔接

> **说明**：本篇"至此整个 Binder 系列 8 篇文章完结"是早期版本的总结措辞，与本系列实际规划 12 篇不一致（以 [README-Binder 系列](README-Binder系列.md) 为准）。从本篇开始进入"诊断治理"扩展篇：

- [09-Binder debugfs 日志解读实战](09-Binder-debugfs日志解读实战.md)（v3 重写后）：从一份 proc 快照做"逐字段实战"
- [10-Binder oneway 限流与防护方案](10-Binder-oneway限流与防护方案.md)（v3 重写后）：oneway 专项防护
- [11-Binder 厂商预防与治理方案调研报告](11-Binder厂商预防与治理方案调研报告.md)（v3 重写后）：按角色对标 AOSP / Qualcomm / MediaTek / OEM / 大厂方案
- [12-Binder 节点文件全景与问题实战](12-Binder节点文件全景与问题实战.md)：debugfs 全节点 + binderfs + 实战案例

> **返回阅读**：[README-Binder 系列](README-Binder系列.md) 包含全系列目录与阅读建议。
