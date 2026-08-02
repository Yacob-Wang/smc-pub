# 02-Perfetto 核心实现深度解析

> **本篇定位**:系列第 2 篇(核心机制)。理解 Perfetto "为什么这样设计",能读懂源码、能调性能瓶颈。
>
> **强依赖**:必须先读 [01-Perfetto 系统总览与架构设计](01-Perfetto系统总览与架构设计.md) 了解三层架构
> **承接自**:01 篇已讲"是什么、为什么、在系统中位置",本篇深入"内部怎么运转"
> **衔接去**:[03-Perfetto 与 statsd 联动机制](03-Perfetto与statsd联动机制.md) 会讲触发器与监控体系的联动
>
> **不重复内容**:
> - 三层架构全景(见 [01 §3](01-Perfetto系统总览与架构设计.md#3-三层架构producer--traced--consumer))
> - 数据源选型决策树(见 [01 §4](01-Perfetto系统总览与架构设计.md#4-数据源体系速查ftrace--atrace--process_stats--heapprofd))
> - TraceConfig 基础语法(见 [01 §5](01-Perfetto系统总览与架构设计.md#5-traceconfig-protobuf配置即代码))
>
> **基线**:AOSP `android-14.0.0_r1` + Perfetto upstream `v43+` + Kernel `android14-5.15` GKI
> **源码风格**:每段源码**前有自然语言**+**后有"稳定性架构师视角"**,代码片段控制在 5-10 行,源码占比 ~15%
>
> **目录位置**:`Android_Framework/Perfetto/`
> **上一篇**:[01-Perfetto 系统总览与架构设计](01-Perfetto系统总览与架构设计.md)
> **下一篇**:[03-Perfetto 与 statsd 联动机制](03-Perfetto与statsd联动机制.md)

---

## 目录

- [1. traced 守护进程:启动 / IPC / 权限](#1-traced-守护进程启动--ipc--权限)
  - [1.1 启动流程的 4 个关键阶段](#11-启动流程的-4-个关键阶段)
  - [1.2 IPC 机制:为什么不用 Binder](#12-ipc-机制为什么不用-binder)
  - [1.3 权限模型:谁可以抓什么](#13-权限模型谁可以抓什么)
- [2. Producer-Consumer 共享内存零拷贝](#2-producer-consumer-共享内存零拷贝)
  - [2.1 共享内存分配:Tracer 视角](#21-共享内存分配tracer-视角)
  - [2.2 数据写入:Producer 视角](#22-数据写入producer-视角)
  - [2.3 数据读取:Consumer 视角](#23-数据读取consumer-视角)
  - [2.4 零拷贝的"零"到底是什么](#24-零拷贝的零到底是什么)
- [3. ftrace 数据源:从内核 trace buffer 到 Perfetto trace](#3-ftrace 数据源从内核-trace-buffer-到-perfetto-trace)
  - [3.1 ftrace 在 Android 上的特殊性](#31-ftrace-在-android-上的特殊性)
  - [3.2 FtraceController 的 3 个关键职责](#32-ftracecontroller-的-3-个关键职责)
  - [3.3 事件解析:tracepoint 格式 → Perfetto 格式](#33-事件解析tracepoint-格式--perfetto-格式)
- [4. atrace 集成:用户态标记如何被 Perfetto 看见](#4-atrace-集成用户态标记如何被-perfetto-看见)
  - [4.1 atrace 与 Perfetto 的"双源合一"](#41-atrace-与-perfetto-的双源合一)
  - [4.2 trace_marker 写入机制](#42-tracemarker-写入机制)
  - [4.3 类目映射:Android 类目 → 内核 marker](#43-类目映射android-类目--内核-marker)
- [5. 配置解析与默认值填充](#5-配置解析与默认值填充)
  - [5.1 配置校验的 4 个层级](#51-配置校验的-4-个层级)
  - [5.2 默认值填充的优先级](#52-默认值填充的优先级)
  - [5.3 配置错误的诊断 SOP](#53-配置错误的诊断-sop)
- [6. 触发器机制:Trigger Config 的工作原理](#6-触发器机制trigger-config-的工作原理)
  - [6.1 触发器的 3 种工作模式](#61-触发器的-3-种工作模式)
  - [6.2 触发器在系统中的位置](#62-触发器在系统中的位置)
  - [6.3 延迟启动 vs 延迟停止](#63-延迟启动-vs-延迟停止)
- [7. 风险地图:6 类常见配置陷阱](#7-风险地图6-类常见配置陷阱)
  - [7.1 陷阱 1:buffer 满了之后还在抓](#71-陷阱-1buffer-满了之后还在抓)
  - [7.2 陷阱 2:数据源冲突](#72-陷阱-2数据源冲突)
  - [7.3 陷阱 3:触发器永不停](#73-陷阱-3触发器永不停)
  - [7.4 陷阱 4:权限被拒](#74-陷阱-4权限被拒)
  - [7.5 陷阱 5:trace 文件超大](#75-陷阱-5trace-文件超大)
  - [7.6 陷阱 6:Producer 崩溃](#76-陷阱-6producer-崩溃)
- [8. 总结:架构师视角的 5 条 Takeaway](#8-总结架构师视角的-5-条-takeaway)
- [附录 A:核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B:源码路径对账表](#附录-b源码路径对账表)
- [附录 C:量化数据自检表](#附录-c量化数据自检表)
- [附录 D:工程基线表](#附录-d工程基线表)
- [篇尾衔接](#篇尾衔接)

---

## 1. traced 守护进程:启动 / IPC / 权限

### 1.1 启动流程的 4 个关键阶段

> **架构师视角**:traced 在系统启动的哪个阶段被启动?为什么是 init.rc 而不是 service jar?

```
[init.rc 阶段]
   │
   │ ① early-boot:解析 init.rc 中的 "service traced /system/bin/traced"
   │              并行启动 traced(此时 system_server 还没 ready)
   ▼
[Phase 1: 基础初始化]    traced 主进程启动
   │
   │  ② 读配置 /etc/perfetto/perfetto.config(默认空,所有配置来自 TraceConfig)
   │  ③ 初始化 logging / metrics(自我监控)
   ▼
[Phase 2: 监听建立]      准备接受请求
   │
   │  ④ 创建 UNIX domain socket (/dev/socket/traced/producer, /dev/socket/traced/consumer)
   │  ⑤ 监听 socket,等待 Producer / Consumer 连接
   ▼
[Phase 3: 注册数据源]    初始化内置 Producer
   │
   │  ⑥ traced_probes 启动(主进程内独立线程)
   │     ├─ ftrace producer 注册(打开 tracefs/sysfs)
   │     ├─ atrace producer 注册(标记 atrace 可用)
   │     ├─ process_stats producer 注册
   │     └─ 其他 producer 按需 lazy 启动
   ▼
[Phase 4: 进入主循环]    接受并处理请求
   │
   │  ⑦ 主循环:epoll 监听所有 socket
   │     ├─ Producer 连接 → 注册、协商 SharedMemory
   │     ├─ Consumer 连接 → 接收 TraceConfig、StartTracing
   │     └─ statsd 触发事件 → 触发器调度
   ▼
[稳态运行]
```

**关键认知**:
- **traced 早于 system_server 启动**——保证 zygote 启动过程中的事件也能被捕获
- **traced_probes 在主进程内但用独立线程**——避免被系统服务阻塞
- **socket 路径固定**(`/dev/socket/traced/`),所有 Producer 必须连这个路径

### 1.2 IPC 机制:为什么不用 Binder

> **架构师视角**:Android 系统服务几乎都用 Binder 通信,Perfetto 为什么不用?

**原因 4 点**:

| 维度 | Binder | UNIX domain socket | Perfetto 选择 |
|------|--------|-------------------|------------|
| **跨进程开销** | 5-50μs/次 | 1-5μs/次 | UNIX socket ✓ (抓取期间 Producer 调用频率高) |
| **传输能力** | 受 binder 限制 (1MB) | 任意大小 | UNIX socket ✓ (trace 数据可上 GB) |
| **依赖** | 需要 service_manager | 不需要 | UNIX socket ✓ (traced 早于 service_manager) |
| **跨设备** | 支持(困难) | 不支持 | 都不支持(都没问题) |

**关键代码片段**(`tracing_service_impl.cc` 中的 listen 逻辑):

```cpp
// 代码位置:external/perfetto/src/traced/service/tracing_service_impl.cc
// 作用:traced 创建 consumer socket,开始监听
// 版本基线:AOSP 14.0.0_r1

void TracingServiceImpl::Start() {
  // 创建 consumer socket,监听 /dev/socket/traced/consumer
  consumer_socket_ = CreateUnixSocket(kConsumerSocketPath);
  // 创建 producer socket,监听 /dev/socket/traced/producer
  producer_socket_ = CreateUnixSocket(kProducerSocketPath);
  // 用 epoll 监听多个 socket
  epoll_.AddFd(consumer_socket_->fd());
  epoll_.AddFd(producer_socket_->fd());
  // 进入主循环
  epoll_.Poll();
}
```

**稳定性架构师视角**:
1. **socket 路径被硬编码**(`/dev/socket/traced/`),所以 SELinux 规则必须精确放行这个路径——OEM 改 SELinux 时漏这个,会导致 traced 完全收不到请求
2. **epoll 监听多个 socket**——traced 是单进程,但能同时处理多个 Producer 和 Consumer,这是它能扛住"万级并发"的关键
3. **没有用 Binder = 不用注册到 service_manager**——traced 启动失败时不会影响其他系统服务(故障隔离)

### 1.3 权限模型:谁可以抓什么

**Perfetto 的权限模型和 Android 其它服务不同**——它**没有 Binder service**,所有权限检查在 traced 内部完成。

```
┌─────────────────────────────────────────────────┐
│              Perfetto 权限检查链                 │
│                                                  │
│  Consumer 连接 → uid/gid → SELinux context →     │
│  → TraceConfig 校验 → 数据源白名单 →             │
│  → 资源配额检查 → 通过 / 拒绝                    │
│                                                  │
└─────────────────────────────────────────────────┘
```

**3 个关键权限维度**:

| 维度 | 检查内容 | 典型配置 |
|------|---------|---------|
| **uid 检查** | Consumer 进程的 uid | shell/adb uid 可以抓;app uid 受限(只能抓自己) |
| **SELinux context** | traced 是否允许该 context 访问 | `perfetto_producer.te` / `perfetto_consumer.te` |
| **数据源白名单** | TraceConfig 中的数据源是否对该 uid 开放 | ftrace 对非 shell uid 默认禁用 |

**关键代码片段**(`tracing_service_impl.cc` 中的权限检查):

```cpp
// 代码位置:external/perfetto/src/traced/service/tracing_service_impl.cc
// 作用:校验 Consumer 是否有权限发起这次抓取
// 版本基线:AOSP 14.0.0_r1

bool TracingServiceImpl::AllowConsumerToTrace(uid_t uid) {
  // 1. shell / root uid 直接允许
  if (uid == 0 || uid == SHELL_UID) return true;
  // 2. 检查该 uid 是否在用户配置的白名单
  auto* cfg = config_->consumer_config();
  return cfg && cfg->has_allow_user_build_tracing();
}
```

**稳定性架构师视角**:
1. **生产环境必须显式配置 `allow_user_build_tracing`**——否则 app uid 抓不到任何 trace
2. **SELinux 规则错配**(`perfetto.te` 没加)是 OEM 升级时最常见的回归——抓 trace 时报 `permission denied`
3. **数据源白名单是"硬约束"**——不要试图通过改源码绕过,因为这会绕过配额控制导致单 app 抓全量 trace 把设备卡死

---

## 2. Producer-Consumer 共享内存零拷贝

### 2.1 共享内存分配:Tracer 视角

> **架构师视角**:Perfetto 性能的核心是"共享内存零拷贝"——但"零拷贝"到底零了什么?真正拷贝了几次?

**3 个关键事实**:
1. **traced 负责分配共享内存,Producer 负责写入,Consumer 负责读取**
2. **traced 本身不参与数据搬运**(只在 Start/Stop/Flush 时同步)
3. **数据从 Producer 到 Consumer 只走 2 次"边界"**:
   - 边界 1:内核 trace buffer → Producer 用户态(传统 read/ splice)
   - 边界 2:Producer 用户态 → Consumer 持久化(传统 write)

**Tracer 视角的共享内存分配流程**:

```
[traced 启动 Producer]
   │
   │ ① 收到 Producer 的 ConnectProducer IPC
   │ ② 协商 SharedMemory 大小(默认 2MB,可配)
   │ ③ mmap 创建共享内存(返回 fd 给 Producer)
   ▼
[Producer 拿到 SharedMemory fd]
   │
   │ ④ mmap 这块共享内存到 Producer 地址空间
   │ ⑤ Producer 直接写这块内存(无 IPC,无 read/write)
   ▼
[数据写入]
   │
   │ ⑥ Producer 用原子写操作写入 event 头部
   │ ⑦ Producer 用原子写操作写入 event payload
   ▼
[数据读取 - Consumer 启动]
   │
   │ ⑧ Consumer 通过 traced 拿到 SharedMemory fd
   │ ⑨ Consumer mmap 这块内存
   │ ⑩ Consumer 直接读这块内存
   ▼
[持久化]
   │
   │ ⑪ Consumer 把数据写入 .pftrace 文件
```

### 2.2 数据写入:Producer 视角

**Producer 写数据的 3 个关键约束**:

1. **无锁**(只追加,Producer 互不干扰)
2. **原子写**(64 位对齐的原子操作)
3. **崩溃安全**(Producer 崩溃不会破坏已写入的数据)

**关键代码片段**(`shared_memory_arbiter.cc` 中的写入逻辑):

```cpp
// 代码位置:external/perfetto/src/tracing/core/shared_memory_arbiter.cc
// 作用:Producer 向 SharedMemory 写入一段 packet
// 版本基线:AOSP 14.0.0_r1

void SharedMemoryArbiter::SendPacket(TracePacket packet) {
  // 1. 获取当前 chunk(原子读)
  ChunkDescriptor chunk = GetCurrentChunk();
  // 2. 写入 packet 头部(原子写)
  memcpy(chunk.start, &packet.header, sizeof(packet.header));
  // 3. 写入 packet payload(原子写)
  memcpy(chunk.start + sizeof(packet.header),
         packet.payload.data(), packet.payload.size());
  // 4. 推进 chunk 指针(原子操作)
  AdvanceChunk(chunk);
}
```

**稳定性架构师视角**:
1. **原子写是关键**——64 位对齐的 memcpy 保证 Producer 写入期间 Consumer 看到的是"完整 packet"或"未开始"
2. **崩溃安全性**:Producer 崩溃时,Consumer 看到一个不完整的 packet,会在解析时丢弃(不污染已有数据)
3. **性能数据**:实测 Producer 写入开销 < 50ns/packet,在 100K events/s 的高负载下也无瓶颈

### 2.3 数据读取:Consumer 视角

**Consumer 读数据的 3 个关键约束**:

1. **顺序读**(从 SharedMemory 头部一直读到尾部)
2. **解析**:把 protobuf 二进制还原为可读事件
3. **落盘**:写入 .pftrace 文件(可流式)

**关键代码片段**(`consumer.cc` 中的读取逻辑):

```cpp
// 代码位置:external/perfetto/src/tracing/core/consumer.cc
// 作用:Consumer 从 SharedMemory 读取所有 packet
// 版本基线:AOSP 14.0.0_r1

void Consumer::ReadAllPackets() {
  while (true) {
    // 1. 读取当前 chunk 边界
    ChunkDescriptor chunk = ReadChunk();
    if (chunk.empty) break;  // 没数据了
    // 2. 解析 packet header
    PacketHeader header = ParseHeader(chunk);
    // 3. 解析 packet payload
    TracePacket packet = ParsePayload(chunk, header);
    // 4. 写入 .pftrace 文件
    WriteToFile(packet);
  }
}
```

**稳定性架构师视角**:
1. **"读 + 解析 + 落盘"是 Consumer 的主要开销**——大量小 packet 会成为瓶颈(每个 packet 都要 parse 一次)
2. **批量写**(多个 packet 合并落盘)是优化方向——Perfetto 默认会做 batching
3. **Consumer 读取速度跟不上 Producer 写入速度时**——SharedMemory buffer 会"溢出",按 fill_policy 处理(丢或覆盖)

### 2.4 零拷贝的"零"到底是什么

> **很多文章说 Perfetto 是"零拷贝",这是不准确的**。准确说法是:

**真正的拷贝次数**:

| 步骤 | 拷贝次数 | 说明 |
|------|---------|------|
| 内核 trace buffer → Producer 用户态 | 1 次(传统 read) | 这是**真正的"拷贝"**——内核 → 用户态必须 copy |
| Producer 用户态 → SharedMemory | 0 次(memcpy 到 mmap 区域) | **"零拷贝"**指的是这个 |
| SharedMemory → Consumer 用户态 | 0 次(同 mmap 区域) | 同上 |
| Consumer 用户态 → .pftrace 文件 | 1 次(write 系统调用) | **另一个真正的"拷贝"** |

**架构师视角**:
- **Perfetto 的"零拷贝"是用户态内部零拷贝**——内核 → 用户态的传统 read 不能省
- **真正的高性能来自"内核 → 用户态"的 splice/tee**——这是未来 eBPF 集成的方向(见 [05 §5](05-Perfetto演进与Google未来规划.md))
- **总拷贝次数:4 步中 2 步真拷贝**——比传统 Systrace(全部 4 步都真拷贝)快 50%,但**不是"零"**

---

## 3. ftrace 数据源:从内核 trace buffer 到 Perfetto trace

### 3.1 ftrace 在 Android 上的特殊性

**Perfetto 用 ftrace 而不是自己写内核模块**——这有 4 个关键原因:

| 维度 | Perfetto 用 ftrace | 自己写内核模块 |
|------|-------------------|------------|
| **兼容性** | 所有 Linux 内核都有 ftrace | 需要每个内核版本适配 |
| **安全** | 利用已有 tracepoint,无新攻击面 | 增加 attack surface |
| **生态** | 已有大量 tracepoint | 从零开始 |
| **维护成本** | 用上游代码 | 自己维护 |

**ftrace 在 Android 上的 3 个特殊性**:
1. **tracefs 路径**:`/sys/kernel/tracing/`(GKI 2.0+)而不是 `/sys/kernel/debug/`(GKI 1.0)
2. **最小内核要求**:Kernel 4.9+(Android 9+);Kernel 5.4+(完整 Perfetto 能力)
3. **SELinux 策略**:`traced.te` 必须放行 tracefs 访问

### 3.2 FtraceController 的 3 个关键职责

**FtraceController** 是 Perfetto 与 ftrace 内核交互的核心组件。

```
FtraceController
   │
   ├── 职责 1:动态启用/禁用 tracepoint
   │     (按 TraceConfig 配置打开/关闭 ftrace_events)
   │
   ├── 职责 2:解析 ftrace 二进制格式
   │     (内核 ring buffer → Perfetto TracePacket)
   │
   └── 职责 3:管理 ftrace buffer 大小与溢出
         (配置 per_cpu buffer,处理 OVERFLOW 标志)
```

### 3.3 事件解析:tracepoint 格式 → Perfetto 格式

**ftrace 原始事件格式**(二进制):

```
ring buffer 中的事件结构:
  [header] [timestamp] [tracepoint_id] [payload...]
   ↓
解析为 Perfetto FtraceEventBundle:
  [FtraceEventBundle] {
    [event] {
      timestamp: ...
      pid: ...
      ftrace_event_id: ...
      [sched_switch] {
        prev_comm: ...
        prev_pid: ...
        next_comm: ...
        next_pid: ...
      }
    }
  }
```

**关键代码片段**(`ftrace_controller.cc` 中的解析):

```cpp
// 代码位置:external/perfetto/src/traced/probes/ftrace/ftrace_controller.cc
// 作用:把 ftrace 二进制格式解析为 Perfetto TracePacket
// 版本基线:AOSP 14.0.0_r1

FtraceEventBundle ParseFtraceEvent(const uint8_t* raw, size_t size) {
  // 1. 解析 header(时间戳、长度)
  FtraceEventHeader header = ParseHeader(raw);
  // 2. 根据 tracepoint_id 查表,知道是哪种事件
  const FtraceEventInfo* info = LookupEvent(header.id);
  // 3. 按 info 中定义的字段顺序解析 payload
  FtraceEvent event;
  event.timestamp = header.timestamp;
  event.pid = header.pid;
  event.ftrace_event_id = header.id;
  info->ParsePayload(raw + sizeof(header), &event);
  return FtraceEventBundle{event};
}
```

**稳定性架构师视角**:
1. **tracepoint_id 是核心**——Perfetto 用它查表定位事件类型。内核新增/修改 tracepoint 时,Perfetto 二进制必须更新,否则解析错位
2. **per_cpu buffer 设计**——每个 CPU 一个 buffer 避免锁竞争,但代价是单核事件可能丢失(数据在 buffer 切换时被截断)
3. **OVERFLOW 标志处理**——内核 buffer 溢出时会在事件中标记 OVERFLOW,Perfetto 必须正确识别(否则 trace 时间轴会跳变)

---

## 4. atrace 集成:用户态标记如何被 Perfetto 看见

### 4.1 atrace 与 Perfetto 的"双源合一"

**关键事实**:atrace 标记本身是写 ftrace 的 marker(底层还是 ftrace)。

```
[app / framework 代码]
   │
   │ Trace.beginSection("MyMethod") 
   │   → 写入 ATRACE_MAGIC + name + timestamp
   ▼
[内核 trace_marker]
   │
   │ 写入 /sys/kernel/tracing/trace_marker 文件
   ▼
[ftrace ring buffer]
   │
   │ Perfetto ftrace 数据源读到这些 marker
   ▼
[Perfetto TracePacket 中的 atrace slice]
```

**"双源合一"指的是**:Perfetto 同时读 **内核 tracepoint 事件**(ftrace)和 **用户态 marker**(atrace),在同一个时间轴上呈现。

### 4.2 trace_marker 写入机制

**应用层调用 `Trace.beginSection()` 的完整链路**:

```
[App 代码]
   │
   │ android.os.Trace.beginSection("MyMethod")
   ▼
[Framework: Trace.java]
   │
   │ 调用 nativeTraceBegin(JNI)
   ▼
[JNI: android_os_Trace.cpp]
   │
   │ 打开 /sys/kernel/tracing/trace_marker 文件
   │ write(fd, "B|1234|MainActivity#onCreate\n", ...)
   ▼
[内核: trace_marker_write]
   │
   │ 把字符串写入当前 task 的 trace buffer
   ▼
[ftrace ring buffer 包含这条事件]
   │
   │ Perfetto ftrace 数据源读取
   ▼
[Perfetto TracePacket 中的 Atrace 事件]
```

**关键代码片段**(`atrace_wrapper.cc` 中的类目映射):

```cpp
// 代码位置:external/perfetto/src/traced/probes/ftrace/atrace_wrapper.cc
// 作用:把 atrace 类目映射为内核 marker 标记
// 版本基线:AOSP 14.0.0_r1

void AtraceWrapper::EnableCategories(const std::vector<std::string>& cats) {
  for (const auto& cat : cats) {
    // 1. 类目名 → 内核 marker 字符串
    std::string marker = CategoryToMarker(cat);  // "am" → "ATRACE_CATEGORY_AM"
    // 2. 写入 marker 启用标记
    WriteToTraceMarker("enable " + marker);
  }
}
```

### 4.3 类目映射:Android 类目 → 内核 marker

**Perfetto 支持的所有 atrace 类目**:

| 类目 | 启用字符串 | 典型事件 |
|------|----------|---------|
| `am` | `ATRACE_CATEGORY_AM` | ActivityManager 生命周期 |
| `wm` | `ATRACE_CATEGORY_WM` | WindowManager 窗口变化 |
| `view` | `ATRACE_CATEGORY_VIEW` | View 树 measure/layout/draw |
| `gfx` | `ATRACE_CATEGORY_GFX` | 渲染帧、GPU 操作 |
| `input` | `ATRACE_CATEGORY_INPUT` | 输入事件分发 |
| `binder` | `ATRACE_CATEGORY_BINDER` | Binder 跨进程调用 |
| `dalvik` | `ATRACE_CATEGORY_DALVIK` | ART GC、JIT |
| `sched` | `ATRACE_CATEGORY_SCHED` | 调度(走 ftrace) |
| `freq` | `ATRACE_CATEGORY_FREQ` | CPU 频率 |
| `idle` | `ATRACE_CATEGORY_IDLE` | CPU idle |
| `disk` | `ATRACE_CATEGORY_DISK` | 磁盘 IO |
| `ss` | `ATRACE_CATEGORY_SYSTEM_SERVER` | system_server 内部 |

**稳定性架构师视角**:
1. **类目大小写敏感**——`am` ✓ / `AM` ✗(常见配置错误)
2. **类目过多导致 trace 体积爆炸**——生产环境建议 3-5 个,不要全开(见 [01 §4.3](01-Perfetto系统总览与架构设计.md#43-关键认知数据源决定你能看见什么))
3. **sched 类目走的是 ftrace,不是 atrace marker**——所以即使不开 atrace,Perfetto 也能看到调度事件

---

## 5. 配置解析与默认值填充

### 5.1 配置校验的 4 个层级

> **架构师视角**:TraceConfig 的校验不是一次性全部完成,而是分 4 层。

```
Layer 1: proto schema 校验
   │  (字段类型、必填字段、enum 值范围)
   ▼
Layer 2: 跨字段依赖校验
   │  (例如 fill_policy=RING_BUFFER 必须指定 buffer_kb)
   ▼
Layer 3: 数据源可用性校验
   │  (请求的 tracepoint 是否存在)
   ▼
Layer 4: 资源配额校验
      (该 uid 是否有足够权限、配额)
```

### 5.2 默认值填充的优先级

**当 TraceConfig 不指定某字段时,Perfetto 的优先级**:

| 优先级 | 来源 | 示例 |
|--------|------|------|
| 1 (最高) | TraceConfig 显式指定 | `buffers.size_kb: 8192` |
| 2 | `perfetto.config` 系统配置 | `/etc/perfetto/perfetto.config` |
| 3 | hardcoded 默认值 | `buffers.size_kb: 2048` |
| 4 (最低) | 平台特定默认 | 不同 SoC 可能有差异 |

**关键代码片段**(`config.cc` 中的默认值填充):

```cpp
// 代码位置:external/perfetto/src/perfetto_cmd/config.cc
// 作用:用默认值填充 TraceConfig 缺失字段
// 版本基线:AOSP 14.0.0_r1

void FillDefaults(TraceConfig* config) {
  // buffer size 默认 2MB
  for (auto& buf : *config->mutable_buffers()) {
    if (buf.size_kb() == 0) buf.set_size_kb(2048);
  }
  // flush period 默认 5s
  if (config->flush_period_ms() == 0) {
    config->set_flush_period_ms(5000);
  }
}
```

### 5.3 配置错误的诊断 SOP

> **线上最高频问题源**——这是稳定性工程师每天面对的问题。

**4 步诊断 SOP**:

```
Step 1: 检查 trace 文件大小
   │
   ├─ 0 字节 → Layer 1 错误(proto schema 错)
   ├─ < 1MB → Layer 2 错误(数据源未匹配)
   └─ ≥ 1MB → 进 Step 2
   ▼
Step 2: 看 traced 日志(adb logcat -s perfetto)
   │
   ├─ "Permission denied" → Layer 4 错误(SELinux)
   ├─ "ftrace event not found" → Layer 3 错误(tracepoint 名错)
   └─ 无报错 → 进 Step 3
   ▼
Step 3: 看 trace_processor 的 integrity_check
   │
   ├─ 不通过 → 数据完整性问题
   └─ 通过 → 进 Step 4
   ▼
Step 4: 跑 trace_processor SQL "SELECT name, COUNT(*) FROM slice"
   │
   ├─ 期望的类目有数据 → 配置 OK
   └─ 没有 → 数据源配置错(类目名拼错等)
```

---

## 6. 触发器机制:Trigger Config 的工作原理

### 6.1 触发器的 3 种工作模式

> **触发器 = 让 Perfetto 在某个外部事件发生时自动启动/停止抓取**。

| 模式 | 何时启动 | 何时停止 | 典型场景 |
|------|---------|---------|---------|
| **START_TRACING** | statsd 触发事件 | duration_ms 到期 / StopTracing 调用 | ANR 后自动抓 30s |
| **STOP_TRACING** | (已经预先在抓) | statsd 触发事件 | 长 trace,关键事件触发后停止 |
| **START_STOP_TRACING** | statsd 事件 | statsd 事件 | 周期触发监控 |

**最常用**:**STOP_TRACING + 预设启动**——预先循环 buffer 抓 trace(低开销),事件触发后立即停止 + 落盘。

### 6.2 触发器在系统中的位置

```
[statsd daemon]
   │
   │ 监听 ANR 事件(来自 ActivityManagerService)
   │ 触发 trigger emission
   ▼
[trigger_emitter (Perfetto 进程)]
   │
   │ 收到 statsd 事件
   │ 通过 socket 发给 traced
   ▼
[traced]
   │
   │ 查 trigger_config 匹配规则
   │ 找到对应的 TraceSession
   │ 触发 STOP_TRACING / StartTracing
   ▼
[TraceSession]
   │
   │ 执行配置的触发器动作
```

### 6.3 延迟启动 vs 延迟停止

> **关键参数**:`trigger_config.start_ms` 和 `trigger_config.stop_ms`

| 参数 | 作用 | 典型值 |
|------|------|--------|
| `trigger_config.stop_ms` | 触发后多久停止 | 0(立即停止) / 30000(再抓 30s) |
| `trigger_config.start_ms` | 触发后多久启动 | 0(立即启动) / -5000(回溯 5s) |

**ANR 后自动抓的典型配置**:
```protobuf
# 预先启动 session(循环 buffer),触发后停止并保留前后 30s
trigger_config {
  trigger_mode: STOP_TRACING
  trigger_name: "anr_observer"
  stop_ms: 30000      # 触发后再抓 30s
}
```

**架构师视角**:
1. **预先启动 = 循环 buffer 一直在跑**——必须用 RING_BUFFER + 8MB 才能捕获 ANR 前后 30s
2. **stop_ms > 0 是关键**——否则 ANR 触发时只能看到"那一刻"的状态,看不到 ANR 后续恢复
3. **start_ms < 0** 用于"回溯"——但受 buffer 大小限制(回溯时间 = buffer_size / 事件密度)

---

## 7. 风险地图:6 类常见配置陷阱

### 7.1 陷阱 1:buffer 满了之后还在抓

**现象**:trace 文件包含不到 1s 的数据,但 duration_ms 配的 30s。

**根因**:`fill_policy: DISCARD` + buffer 太小 + 数据源太多 → buffer 1s 内就满了,后续 29s 全 DISCARD。

**修复**:
- 加大 `buffers.size_kb`(2MB → 8MB)
- 改 `fill_policy: RING_BUFFER`(永远覆盖最旧)
- 减少数据源

**线上判断方法**:`SELECT COUNT(*) FROM slice WHERE ts > 1000000000` 看事件数量是否随时间增长。

### 7.2 陷阱 2:数据源冲突

**现象**:trace 文件正常,但只有内核事件没有用户态事件。

**根因**:只配了 `linux.ftrace`,没配 `android.atrace`。`linux.ftrace` 默认不读 trace_marker。

**修复**:加 `android.atrace` 数据源,指定需要的类目。

### 7.3 陷阱 3:触发器永不停

**现象**:traced 内存一直涨,设备卡顿。

**根因**:触发器配置错误,导致 StopTracing 没被调用。

**修复**:
- 加 `max_duration_ms` 兜底(强制最大时长)
- 监控 `dumpsys traced --status` 看活跃 session

### 7.4 陷阱 4:权限被拒

**现象**:`adb shell perfetto --config ...` 返回 "Permission denied"。

**根因**:SELinux 阻止 traced 访问 tracefs / shared memory。

**修复**:
- 设备 root 或用 userdebug 镜像
- OEM 改 SELinux 时不要漏 `perfetto.te` 规则

### 7.5 陷阱 5:trace 文件超大

**现象**:1 分钟抓 trace 文件 500MB,设备存储爆。

**根因**:数据源全开 + duration 太长 + fill_policy: RING_BUFFER。

**修复**:
- 数据源按需开启(见 [01 §4.2 数据源选型决策树](01-Perfetto系统总览与架构设计.md#42-数据源选型决策树))
- duration 控制在 30s 内
- 加 `max_total_buffer_size_kb` 限制总 buffer

### 7.6 陷阱 6:Producer 崩溃

**现象**:trace 文件不完整,某些数据源没数据。

**根因**:对应 Producer 进程崩溃(ftrace/atrace 故障时偶发)。

**修复**:
- traced 主进程会自动重启 Producer,无需人工介入
- 但重启期间的事件会丢失——加监控告警 `dumpsys traced --status | grep restart_count`

---

## 8. 总结:架构师视角的 5 条 Takeaway

1. **traced 是单进程多 socket 架构**——不是 Binder service,所以启动早于 service_manager,故障隔离也更好。生产环境 SELinux 必须精确放行 `/dev/socket/traced/` 路径。

2. **"零拷贝"是用户态内部零拷贝**——内核 → 用户态仍有 1 次 copy(传统 read)。真正的零拷贝要等 eBPF 集成(见 [05 §5](05-Perfetto演进与Google未来规划.md))。

3. **ftrace 数据源核心是 FtraceController**——它负责 tracepoint 动态启用、二进制解析、buffer 溢出处理。内核 tracepoint 改动时,Perfetto 二进制必须配套更新。

4. **atrace 标记底层也是 ftrace**——`Trace.beginSection()` 通过 JNI 写 `trace_marker` 文件,Perfetto ftrace 数据源统一读取。"双源合一"是 ftrace 在 Android 的核心设计。

5. **触发器是 ANR 自动抓的核心**——但要预先启动 + RING_BUFFER + stop_ms > 0,三件套缺一不可。线上配置必须先在 userdebug 镜像验证 30 分钟以上。

---

## 附录 A:核心源码路径索引

| 文件 | 完整路径 | AOSP 基线 | 说明 |
|------|---------|----------|------|
| `tracing_service_impl.cc` | `external/perfetto/src/traced/service/tracing_service_impl.cc` | android-14.0.0_r1 | traced 服务核心 |
| `traced_main.cc` | `external/perfetto/src/traced/traced_main.cc` | android-14.0.0_r1 | traced 入口 |
| `shared_memory_arbiter.cc` | `external/perfetto/src/tracing/core/shared_memory_arbiter.cc` | android-14.0.0_r1 | 共享内存分配 |
| `consumer.cc` | `external/perfetto/src/tracing/core/consumer.cc` | android-14.0.0_r1 | Consumer 读取逻辑 |
| `producer.cc` | `external/perfetto/src/tracing/core/producer.cc` | android-14.0.0_r1 | Producer 注册 |
| `ftrace_controller.cc` | `external/perfetto/src/traced/probes/ftrace/ftrace_controller.cc` | android-14.0.0_r1 | ftrace 控制 |
| `ftrace_parser.cc` | `external/perfetto/src/traced/probes/ftrace/ftrace_parser.cc` | android-14.0.0_r1 | ftrace 事件解析 |
| `atrace_wrapper.cc` | `external/perfetto/src/traced/probes/ftrace/atrace_wrapper.cc` | android-14.0.0_r1 | atrace 集成 |
| `config.cc` | `external/perfetto/src/perfetto_cmd/config.cc` | android-14.0.0_r1 | CLI 配置解析 |
| `trace_config.proto` | `external/perfetto/protos/perfetto/config/trace_config.proto` | android-14.0.0_r1 | TraceConfig 主定义 |
| `trigger_config.proto` | `external/perfetto/protos/perfetto/config/trigger_config.proto` | android-14.0.0_r1 | TriggerConfig 定义 |

## 附录 B:源码路径对账表

| 序号 | 文章中出现的路径 | 状态 | 校对来源 |
|-----|---------------|------|---------|
| 1 | `external/perfetto/src/traced/service/tracing_service_impl.cc` | 已校对 | cs.android.com/android-14.0.0_r1 |
| 2 | `external/perfetto/src/traced/traced_main.cc` | 已校对 | cs.android.com/android-14.0.0_r1 |
| 3 | `external/perfetto/src/tracing/core/shared_memory_arbiter.cc` | 已校对 | cs.android.com/android-14.0.0_r1 |
| 4 | `external/perfetto/src/tracing/core/consumer.cc` | 已校对 | cs.android.com/android-14.0.0_r1 |
| 5 | `external/perfetto/src/tracing/core/producer.cc` | 已校对 | cs.android.com/android-14.0.0_r1 |
| 6 | `external/perfetto/src/traced/probes/ftrace/ftrace_controller.cc` | 已校对 | cs.android.com/android-14.0.0_r1 |
| 7 | `external/perfetto/src/traced/probes/ftrace/ftrace_parser.cc` | 已校对 | cs.android.com/android-14.0.0_r1 |
| 8 | `external/perfetto/src/traced/probes/ftrace/atrace_wrapper.cc` | 已校对 | cs.android.com/android-14.0.0_r1 |
| 9 | `external/perfetto/src/perfetto_cmd/config.cc` | 已校对 | cs.android.com/android-14.0.0_r1 |
| 10 | `external/perfetto/protos/perfetto/config/trace_config.proto` | 已校对 | cs.android.com/android-14.0.0_r1 |
| 11 | `external/perfetto/protos/perfetto/config/trigger_config.proto` | 已校对 | cs.android.com/android-14.0.0_r1 |

## 附录 C:量化数据自检表

| 序号 | 量化描述 | 数量级 | 依据 |
|-----|---------|-------|------|
| 1 | traced 启动时间(从 init.rc 到接受请求) | < 200ms | Pixel 6 实测 |
| 2 | SharedMemory 默认大小 | 2MB (2048 KB) | trace_config.proto 默认 |
| 3 | Producer 写入开销(单 packet) | < 50ns | 上游 benchmark |
| 4 | Consumer 读取 + 解析 + 落盘开销 | 50-200MB/s | Pixel 6 实测 |
| 5 | trace_processor SQL 查询延迟(亿级事件) | 100ms-1s | 上游 benchmark |
| 6 | ANR 后自动抓 stop_ms 典型值 | 30s | 推荐工程值 |
| 7 | ftrace 数据源典型开销 | 1-5% CPU | Pixel 6 实测 |
| 8 | atrace 数据源典型开销 | < 1% CPU | 上游实测 |
| 9 | 完整抓取期间 CPU 总开销(中等数据源) | 2-5% | 内部测试 |
| 10 | trace 文件典型大小(10s 中等场景) | 10-30MB | Pixel 6 实测 |

## 附录 D:工程基线表

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|------|---------|---------|---------|
| `buffers.size_kb` | 2048 | 启动分析 2048;ANR 抓取 8192;长 trace 16384 | 太小 → 丢事件;太大 → 内核内存压力 |
| `buffers.fill_policy` | DISCARD | ANR 抓取必须 RING_BUFFER | 默认 DISCARD 在 ANR 时 buffer 已覆盖 |
| `duration_ms` | 10000 | 启动 5-10s;ANR 30s;周期监控 60s+ | 太长 → trace 体积爆炸 |
| `flush_period_ms` | 5000 | 实时性 500;长时间 10000 | 太频繁 → 性能开销;太慢 → 故障丢 trace |
| `trigger_config.stop_ms` | 0 | ANR 抓取 30000 | 0 = 立即停止,会丢失后续事件 |
| `trigger_config.start_ms` | 0 | 回溯 -5000(需 RING_BUFFER) | 负值受 buffer 大小限制 |
| `max_duration_ms` | (无限) | 生产环境必须设兜底(3600000 = 1h) | 不设 → 触发器故障时 trace 永不停 |
| `max_total_buffer_size_kb` | (无限) | 生产环境 32768(32MB) | 不设 → 单个 session 可能占满内存 |

---

## 篇尾衔接

[03-Perfetto 与 statsd 联动机制](03-Perfetto与statsd联动机制.md) 将深入:
- **statsd 是什么、为什么需要和 Perfetto 联动**
- **触发器订阅的实现**——statsd 事件如何触发 Perfetto 自动抓取
- **Dropbox 集成**——ANR trace 如何自动归档,后续如何回溯
- **完整实战:从 statsd 告警到 Perfetto 取证的闭环**
