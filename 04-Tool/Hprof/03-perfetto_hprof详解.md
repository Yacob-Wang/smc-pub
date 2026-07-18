# 03-perfetto_hprof 详解

> **本篇定位**:系列第 3 篇(新机制)。读完能理解 Google 把 hprof 集成到 Perfetto 的真正动机,会配置 perfetto_hprof,理解 native heap sampling 的原理。
>
> **强依赖**:[01-hprof 原理与文件格式](01-hprof原理与文件格式.md) §4 的 ROOT 记录 + [02-hprof 解析工具链](02-hprof解析工具链.md) §3 LeakCanary
>
> **承接自**:[02](02-hprof解析工具链.md) 提到的"持续监控"需求,本篇给出 Google 的解决方案
>
> **不重复内容**:
> - hprof 文件格式 → 见 [01 §3-§5](01-hprof原理与文件格式.md)
> - 传统工具链 → 见 [02](02-hprof解析工具链.md)
> - 案例分析 → 见 [04](04-内存泄漏典型案例与排查SOP.md)
>
> **基线**:AOSP `android-14.0.0_r1` + Perfetto upstream `v43+` + Kernel `android14-5.15` GKI
> **风格**:源码密度 ~15%,重点放在架构图 + 对比表 + 视角分析
>
> **目录位置**:`Android_Framework/Hprof/`
> **上一篇**:[02-hprof 解析工具链](02-hprof解析工具链.md)
> **下一篇**:[04-内存泄漏典型案例与排查 SOP](04-内存泄漏典型案例与排查SOP.md)

---

## 目录

- [1. 背景:Google 为什么把 hprof 集成到 Perfetto](#1-背景google-为什么把-hprof-集成到-perfetto)
  - [1.1 传统 hprof 的三大痛点](#11-传统-hprof-的三大痛点)
  - [1.2 Perfetto 的"统一追踪"愿景](#12-perfetto-的统一追踪愿景)
  - [1.3 heapprofd 的设计哲学:从"快照"到"流"](#13-heapprofd-的设计哲学从快照到流)
- [2. heapprofd 守护进程架构](#2-heapprofd-守护进程架构)
  - [2.1 全景图:Producer / 中央服务 / Consumer](#21-全景图producer--中央服务--consumer)
  - [2.2 heapprofd 守护进程:为什么独立进程](#22-heapprofd-守护进程为什么独立进程)
  - [2.3 数据流时序:从 native malloc 到 Perfetto trace](#23-数据流时序从-native-malloc-到-perfetto-trace)
- [3. Native Heap Sampling 原理](#3-native-heap-sampling-原理)
  - [3.1 采样 vs 全量:为什么采样够用](#31-采样-vs-全量为什么采样够用)
  - [3.2 采样算法:基于字节数 + 调用栈](#32-采样算法基于字节数--调用栈)
  - [3.3 native malloc 拦截:从 libc 到 ART](#33-native-malloc-拦截从-libc-到-art)
- [4. Java 堆 vs Native 堆:heapprofd 双模式](#4-java-堆-vs-native-堆heapprofd-双模式)
  - [4.1 Java 模式:基于 ART Heap 遍历](#41-java-模式基于-art-heap-遍历)
  - [4.2 Native 模式:基于 libc malloc 拦截](#42-native-模式基于-libc-malloc-拦截)
  - [4.3 模式选择决策树](#43-模式选择决策树)
- [5. perfetto_hprof 配置模板详解](#5-perfetto_hprof-配置模板详解)
  - [5.1 5 分钟示例:一个最小可用配置](#51-5-分钟示例一个最小可用配置)
  - [5.2 配置项详解:mode / sampling_interval / shmem_size_bytes](#52-配置项详解mode--sampling_interval--shmem_size_bytes)
  - [5.3 实战配置模板](#53-实战配置模板)
  - [5.4 配置错误的 5 类典型症状](#54-配置错误的-5-类典型症状)
- [6. 与传统 hprof 的对比](#6-与传统-hprof-的对比)
  - [6.1 六维度对比矩阵](#61-六维度对比矩阵)
  - [6.2 实战选型 SOP:遇到 X 问题用 Y 工具](#62-实战选型-sop遇到-x-问题用-y-工具)
- [7. 实战:配置 perfetto_hprof + 在 UI 中查看](#7-实战配置-perfetto_hprof--在-ui-中查看)
  - [7.1 命令行触发](#71-命令行触发)
  - [7.2 代码触发(Application 启动时自动开启)](#72-代码触发application-启动时自动开启)
  - [7.3 Perfetto UI 中查看 native heap](#73-perfetto-ui-中查看-native-heap)
- [8. 总结:架构师视角的 5 条 Takeaway](#8-总结架构师视角的-5-条-takeaway)
- [附录 A:核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B:配置模板(`hprof_configs/perfetto_hprof.pbtxt`)](#附录-b配置模板hprof_configsperfetto_hprofpbtxt)
- [附录 C:量化数据自检表](#附录-c量化数据自检表)
- [附录 D:工程基线表](#附录-d工程基线表)
- [篇尾衔接](#篇尾衔接)

---

## 1. 背景:Google 为什么把 hprof 集成到 Perfetto

### 1.1 传统 hprof 的三大痛点

回顾 [01 §7](01-hprof原理与文件格式.md) 和 [02 §3](02-hprof解析工具链.md),传统 hprof 在生产环境有以下痛点:

| 痛点 | 影响 | 线上代价 |
|------|------|---------|
| **Stop-The-World 5-30s** | 用户卡顿 + 超时 | **直接掉 DAU** |
| **单次快照** | 看不到增长过程 | **只能事后追因** |
| **Native 盲区** | Bitmap/so/DirectByteBuffer 全看不见 | **漏掉 30% 内存问题** |

> **核心矛盾**:线上需要"持续监控",但传统 hprof 是"离线全量快照"——两者本质冲突。

### 1.2 Perfetto 的"统一追踪"愿景

Google 在 Perfetto 上做了一件事:**把所有追踪基础设施统一进一个框架**。

```
                          Perfetto("瑞士军刀")
                                 │
        ┌────────────┬───────────┼───────────┬────────────┐
        ↓            ↓           ↓           ↓            ↓
      ftrace      atrace     process_stats  heapprofd    game_intervention
     (内核事件)  (Android 事件) (进程级指标)  (堆内存采样)  (游戏性能)
        │            │           │           │            │
        └────────────┴───────────┴───────────┴────────────┘
                                 │
                          一个 trace 文件
                          (.pftrace)
                                 │
                          trace_processor
                          (SQL 分析)
```

**heapprofd** 就是其中"堆内存采样"那一支——**用 Perfetto 的统一框架解决 hprof 的三大痛点**。

### 1.3 heapprofd 的设计哲学:从"快照"到"流"

```
传统 hprof:                  heapprofd:
"dump 一次,看一个瞬间"       "持续采样,看一段过程"
    │                            │
    ▼                            ▼
[1] 全量遍历堆              [1] 后台守护进程常驻
[2] STW 5-30s              [2] 每 N ms 采样一次(默认 1ms-100ms)
[3] 写入 .hprof             [3] 写调用栈 + 大小,不开 STW
[4] 离线分析                [4] 在线 trace_processor SQL 查询
    │                            │
    └─────────→  演进方向  ←──────┘
```

**核心转变**:
- ❌ "我要看某一刻的内存" → ✅ "我要看一段时间的内存增长曲线"
- ❌ "Java 堆 + 全量" → ✅ "Java 堆采样 + Native 堆采样"
- ❌ "只能事后分析" → ✅ "实时 + 离线 双模式"

---

## 2. heapprofd 守护进程架构

### 2.1 全景图:Producer / 中央服务 / Consumer

```
┌─────────────────────────────────────────────────────────┐
│              app 进程(com.example.app)                  │
│  ┌────────────────────────────────────────────────┐     │
│  │ ART Heap                                      │     │
│  │  ↓ heapprofd client(动态注入)                 │     │
│  │  ┌──────────────────────────────────┐         │     │
│  │  │ heapprofd_client.so             │         │     │
│  │  │ - 拦截 Java 分配                │         │     │
│  │  │ - 拦截 native malloc            │         │     │
│  │  │ - 写共享内存                    │         │     │
│  │  └──────────────┬───────────────────┘         │     │
│  └─────────────────┼─────────────────────────────┘     │
└────────────────────┼────────────────────────────────────┘
                     │ 共享内存(零拷贝)
                     ↓
┌─────────────────────────────────────────────────────────┐
│     heapprofd 守护进程(system 进程)                     │
│  ┌──────────────────────────────────────────────┐      │
│  │ Producer: 读共享内存 → 转换为 trace events    │      │
│  └──────────────┬───────────────────────────────┘      │
└─────────────────┼──────────────────────────────────────┘
                  │
                  ↓ Producer / Consumer 协议
┌─────────────────────────────────────────────────────────┐
│     traced 中央服务(system 进程)                        │
│  - 接收 heapprofd producer                              │
│  - 合并多 producer 数据                                  │
│  - 响应 consumer 请求                                    │
└─────────────────┬──────────────────────────────────────┘
                  │
                  ↓ Consumer 协议
┌─────────────────────────────────────────────────────────┐
│     Consumer(perfetto cmdline / trace_processor)        │
│  - 拉取 trace 数据                                      │
│  - 输出 .pftrace 文件                                   │
│  - SQL 分析                                             │
└─────────────────────────────────────────────────────────┘
```

### 2.2 heapprofd 守护进程:为什么独立进程

**关键设计**:heapprofd 是 **system 级别的独立守护进程**,不是 app 进程内嵌。

| 优势 | 说明 |
|------|------|
| **跨进程聚合** | 一个 heapprofd 可同时监控多个 app 进程 |
| **故障隔离** | heapprofd 崩溃不影响 app |
| **权限隔离** | 采样数据先汇总到 system 进程,避免 app 直接接触 |
| **统一管控** | 通过 traced 中央服务统一开关 |

**对比传统 hprof**:
- 传统 hprof:dump 在 app 进程内 → 直接写盘 → app 卡顿
- heapprofd:拦截在 app 进程 → **共享内存** 传到 heapprofd system 进程 → 编码后给 traced → **app 几乎无感**

### 2.3 数据流时序:从 native malloc 到 Perfetto trace

```
[app 进程]                              [heapprofd 守护进程]
    │                                           │
    ├─ malloc(1MB) ─┐                           │
    │                ↓                           │
    │   [heapprofd_client.so 拦截]              │
    │   ├─ 读调用栈(unwind)                      │
    │   ├─ 算本次分配大小                        │
    │   ├─ 概率采样(默认 1/100)                  │
    │   └─ 写共享内存 ◄─────┐                    │
    │                       │ 共享内存            │
    │                       └─────→ [heapprofd 守护进程]
    │                                          │
    │                                          ├─ 读共享内存
    │                                          ├─ 编码为 Perfetto proto
    │                                          ├─ 通过 IPC 给 traced
    │                                          ↓
    │                                     [traced 中央服务]
    │                                          │
    │                                          ↓
    │                                     [Consumer / SQL]
```

**关键设计**:
- **共享内存(零拷贝)**:app 进程写到共享内存,heapprofd 直接读,**不经过 copy**
- **概率采样**:默认每 100 次 malloc 采样 1 次,开销仅 1-3%
- **调用栈 unwind**:用 frame-pointer 或 DWARF 还原调用栈

---

## 3. Native Heap Sampling 原理

### 3.1 采样 vs 全量:为什么采样够用

**全量采样**:`malloc/free` **每次**都记录。
- ❌ 开销 50%+,完全不可线上用
- ❌ 数据量爆炸(100MB/s+)

**概率采样**:每 N 次 malloc 记录 1 次(默认 N=100)。
- ✅ 开销 1-3%,可线上用
- ✅ 数据量可控(1MB/s)
- ✅ **统计上仍能反映真实分配模式**(大对象采样率高,小对象采样率低)

> **核心洞察**:Google 内部数据表明,即使是 1/1000 的采样,**也能捕获 99% 的大内存问题**(因为大对象本身就稀少,被采样命中的概率足够)。

### 3.2 采样算法:基于字节数 + 调用栈

**算法伪代码**(简化自 `external/perfetto/src/heap_profiling/...`):

```
def should_sample(allocation_size_bytes):
    # 采样概率 ∝ 分配大小
    # 1KB 分配: 1/1000 概率
    # 1MB 分配:  1/1   概率(100%)
    sample_interval = max(1, 1024 * 1024 / allocation_size_bytes)
    
    if global_sample_counter % sample_interval == 0:
        global_sample_counter = 0
        return True  # 采样
    global_sample_counter += 1
    return False
```

**关键特性**:
- **大分配 100% 捕获**(1MB+ 一定采样)
- **小分配按比例采样**(1KB 1/1000 概率)
- **统计无偏**:大对象虽然少,但每个权重高

### 3.3 native malloc 拦截:从 libc 到 ART

**拦截原理**:

```
app 调用:   void* p = malloc(1024 * 1024);
                 ↓
        [libc.so] malloc()
                 ↓
        [hook 点] heapprofd_client 拦截
                 ↓
        [原始 malloc] → 返回实际指针
                 ↓
        [hook 后处理] heapprofd_client 记录:调用栈 + 大小 + 时间
```

**两种拦截方式**:

| 方式 | 实现 | 优点 | 缺点 |
|------|------|------|------|
| **PLT/GOT hook** | 改 libc.so 的 GOT 表 | 无需重编 libc | 兼容性差(Android 7+ SELinux 限制) |
| **LD_PRELOAD** | 启动时加载 hook 库 | 简单 | 需要 root 或 debuggable |
| **perfetto_client 内嵌** | ART 集成,直接调用 hook | 兼容性好 | 仅限 Java 分配 |

**Android 14 的实际方案**:`heapprofd_client.so` 由 ART 加载,通过 **interceptor 机制**拦截 native 调用(无需 LD_PRELOAD)。

### 3.4 Java Heap 采样 vs Native Heap 采样

| 维度 | Java 堆采样 | Native 堆采样 |
|------|------------|--------------|
| **采样对象** | Java 对象分配 + native malloc | 仅 native malloc |
| **性能开销** | 5-15%(需遍历 ART heap) | **1-3%**(纯 hook) |
| **获取方式** | ART `Heap::VisitObjects` | libc malloc hook |
| **数据精度** | 全量对象图(可还原引用链) | **只有调用栈**(无引用链) |
| **典型用途** | 泄漏分析(LeakCanary 等价) | 增长归因(谁在分配 native) |

---

## 4. Java 堆 vs Native 堆:heapprofd 双模式

### 4.1 Java 模式:基于 ART Heap 遍历

**模式说明**:每 N ms 触发一次 ART heap 遍历,记录所有 Java 对象。

```
mode: "java" (或 "both")
sampling_interval_ms: 100  # 每 100ms 采样一次

内部流程:
[1] ART.SuspendAllThreads()  # 短暂 STW
[2] Heap::VisitObjects()      # 遍历所有对象
[3] 记录每个对象的 size + class + 调用栈
[4] ResumeAllThreads()        # 恢复
[5] 把数据写入共享内存
```

**注意**:即使是 Java 模式,heapprofd 也 **不会一次性 dump 全堆**(那是 hprof 的做法)。它按时间分片,**每次只记录增量对象**,避免单次大卡顿。

### 4.2 Native 模式:基于 libc malloc 拦截

**模式说明**:hook `malloc/realloc/free/calloc`,记录每次分配。

```
mode: "native"
sampling_interval_bytes: 1024  # 累计 1024 字节采样一次

内部流程:
[malloc] → 拦截
[unwind] → 还原调用栈(用 frame-pointer 或 DWARF)
[累计] → 当前累计分配字节数
[触发采样] → 累计 >= sampling_interval_bytes?
    → 是:写共享内存 + 重置累计
    → 否:继续累计
```

### 4.3 模式选择决策树

```
你的问题是:
    │
    ├─ Java 泄漏? → mode: java
    │   (Activity/Fragment/Static 不释放)
    │
    ├─ Native 增长? → mode: native
    │   (Bitmap/so/DirectByteBuffer 持续涨)
    │
    └─ 不确定? → mode: both + 低频采样
        (先摸清问题再精准配置)
```

---

## 5. perfetto_hprof 配置模板详解

### 5.1 5 分钟示例:一个最小可用配置

```protobuf
# perfetto_hprof.pbtxt(最小可用版本)
# 监控 com.example.app 进程的 native 分配
# 采样间隔:1024 字节(每分配 1KB 采样 1 次)
# 持续时间:60 秒

duration_ms: 60000

buffers: {
  size_kb: 10240
  fill_policy: RING_BUFFER
}

data_sources: {
  config: {
    name: "android.heapprofd"
    target_buffer: 0
    
    heapprofd_config: {
      sampling_interval_bytes: 1024
      
      process_dump_config: {
        process_name: "com.example.app"
        sampling_interval_bytes: 1024
      }
      
      # 也可监控其他进程
      process_dump_config: {
        process_name: "*"
        sampling_interval_bytes: 4096  # 其他进程用更低频率
      }
    }
  }
}
```

### 5.2 配置项详解:mode / sampling_interval / shmem_size_bytes

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|-------|------|
| `sampling_interval_bytes` | uint64 | 4096 | 每累计多少字节采样一次 |
| `sampling_interval_ms` | uint64 | 0(禁用) | Java 模式按时间采样 |
| `shmem_size_bytes` | uint64 | 8MB | 共享内存大小 |
| `block_client` | bool | false | 客户端阻塞模式 |
| `no_start` | bool | false | 立即启动(false)还是延迟启动 |

**采样间隔选择指南**:

```
高频监控(开发调试):   256-1024 字节
中频监控(灰度):       1024-4096 字节
低频监控(正式):       4096-16384 字节
```

### 5.3 实战配置模板

**配套资产**:完整模板见 `hprof_configs/perfetto_hprof.pbtxt`,以下是核心片段:

```protobuf
# 实战:线上 native 增长归因
duration_ms: 300000  # 5 分钟

data_sources: {
  config: {
    name: "android.heapprofd"
    heapprofd_config: {
      sampling_interval_bytes: 2048
      
      # 关键:精准定位目标进程
      process_dump_config: {
        process_name: "com.example.app"
        sampling_interval_bytes: 2048
      }
    }
  }
}

# 同时抓取其他维度做交叉分析
data_sources: {
  config: {
    name: "android.process_stats"
  }
}

data_sources: {
  config: {
    name: "linux.ftrace"
    ftrace_config: {
      atrace_categories: "memreclaim"
    }
  }
}
```

### 5.4 配置错误的 5 类典型症状

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| **`heapprofd not available on this device`** | 设备 Android 版本 < 9 | 升级到 Android 9+,或用传统 hprof |
| **`failed to inject heapprofd_client`** | SELinux 限制(用户版 ROM) | 用 userdebug ROM 或 root 设备 |
| **trace 文件 0 字节** | `process_name` 拼错 | 用 `dumpsys activity processes` 确认包名 |
| **`Sampling interval too small, overhead exceeded`** | 采样间隔太小 | 增大到 4096+ |
| **只有 Java 数据,无 native** | `mode: java` 模式 | 改为 `mode: native` 或 `both` |

---

## 6. 与传统 hprof 的对比

### 6.1 六维度对比矩阵

| 维度 | 传统 hprof | perfetto_hprof | 优势方 |
|------|-----------|---------------|--------|
| **性能开销** | ❌ 5-30s STW | ✅ 1-3% 后台 | perfetto_hprof |
| **时间维度** | ❌ 单次快照 | ✅ 持续过程 | perfetto_hprof |
| **Java 覆盖** | ✅ 全量对象图 | ⚠️ 采样对象 | 传统 hprof |
| **Native 覆盖** | ❌ 完全看不见 | ✅ malloc 采样 | perfetto_hprof |
| **分析工具** | ✅ MAT/LeakCanary | ⚠️ trace_processor SQL | 传统 hprof |
| **线上可用性** | ❌ 影响用户 | ✅ 无感 | perfetto_hprof |

### 6.2 实战选型 SOP:遇到 X 问题用 Y 工具

```
线上 OOM / 频繁被杀
    ↓
[快速定位:Java 还是 Native?]
    ↓
├── dumpsys meminfo → Java Heap > 50% → Java 模式 perfetto_hprof
│                                     ↓
│                          (5 分钟看增长曲线)
│                                     ↓
│                          定位到增长源 → 用 MAT 分析传统 hprof(深度)
│
├── dumpsys meminfo → Native > 30% → Native 模式 perfetto_hprof
│                                     ↓
│                          (看调用栈归因)
│                                     ↓
│                          定位到 native 分配热点 → 修代码
│
└── 不确定 → mode: both + 5 分钟 perfetto_hprof 摸底
```

**结论**:perfetto_hprof **不是传统 hprof 的替代**,而是 **互补**:
- **线上持续监控**:perfetto_hprof
- **线下深度分析**:传统 hprof + MAT

---

## 7. 实战:配置 perfetto_hprof + 在 UI 中查看

### 7.1 命令行触发

```bash
# 1. 把配置写到文件
cat > /data/local/tmp/perfetto_hprof.pbtxt <<'EOF'
duration_ms: 60000
buffers: { size_kb: 10240 fill_policy: RING_BUFFER }
data_sources: {
  config: {
    name: "android.heapprofd"
    heapprofd_config: {
      sampling_interval_bytes: 1024
      process_dump_config: {
        process_name: "com.example.app"
        sampling_interval_bytes: 1024
      }
    }
  }
}
EOF

# 2. 触发 perfetto
adb shell perfetto \
  --txt -c /data/local/tmp/perfetto_hprof.pbtxt \
  -o /data/misc/perfetto-traces/trace.pftrace

# 3. 拉回本地分析
adb pull /data/misc/perfetto-traces/trace.pftrace ./

# 4. 上传 Perfetto UI 分析
# 访问 https://ui.perfetto.dev,点 "Open trace file" 上传
```

### 7.2 代码触发(Application 启动时自动开启)

```java
// 仅 debug + 灰度包
public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        
        if (BuildConfig.DEBUG) {
            startHeapprofd();
        }
    }
    
    private void startHeapprofd() {
        // 用 PerfettoTraceBuilder API
        // (Android 13+ 有官方 API,之前要自己拼命令)
        // 见 https://perfetto.dev/docs/instrumentation/trace-config
    }
}
```

### 7.3 Perfetto UI 中查看 native heap

```
1. 上传 .pftrace 到 https://ui.perfetto.dev

2. 左侧菜单选 "Heap Profile" → "Native"

3. 看到 native 分配热力图:
   ┌──────────────────────────────────────┐
   │  malloc 分配热点(按调用栈聚合)        │
   │  ┌─────────────────────────────┐    │
   │  │ BitmapFactory.decodeStream  │ 60% │
   │  ├─────────────────────────────┤    │
   │  │ WebView.loadUrl            │ 20% │
   │  ├─────────────────────────────┤    │
   │  │ 其他                       │ 20% │
   │  └─────────────────────────────┘    │
   └──────────────────────────────────────┘

4. 点击某个调用栈 → 看具体分配大小 + 时间分布

5. SQL 查询(trace_processor):
   SELECT * FROM heap_profile_allocations
   WHERE callsite_id = (
     SELECT id FROM heap_profile_callsites
     WHERE name LIKE '%BitmapFactory%'
   )
   ORDER BY size DESC LIMIT 10
```

> **详细 perfetto UI 使用见 [Perfetto 系列 01-03 篇](../../Perfetto/)**。

---

## 8. 总结:架构师视角的 5 条 Takeaway

### Takeaway 1:perfetto_hprof 解决的是"持续监控",不是"深度分析"
它的核心价值是**线上 1-3% 开销持续采样**,而不是替代 MAT 做引用链分析。两者是 **互补关系**。

### Takeaway 2:heapprofd 守护进程 + 共享内存 = 零拷贝 + 故障隔离
独立 system 进程 + 共享内存传递数据,这是 Google 把 hprof 集成进 Perfetto 的**架构核心**。

### Takeaway 3:Native 采样是 perfetto_hprof 真正的杀手锏
传统 hprof **完全看不见 native**,perfetto_heapprofd 通过 **libc malloc hook** 覆盖了 bitmap/so/direct buffer。**这是它相对传统 hprof 最大的优势**。

### Takeaway 4:采样间隔决定一切
- 开发调试:256-1024 字节(高频)
- 灰度验证:1024-4096 字节(中频)
- 正式监控:4096-16384 字节(低频)
太大漏数据,太小拖累 app。

### Takeaway 5:配置精准定位目标进程
默认配置监控 `*` 所有进程开销大且数据杂,**只配 `com.example.app`** 是最佳实践。配合 `dumpsys activity processes` 验证包名拼写。

---

## 附录 A:核心源码路径索引

| 路径 | 作用 |
|------|------|
| `external/perfetto/src/heap_profiling/...` | heapprofd 核心实现 |
| `external/perfetto/src/heap_profiling/heapprofd.cc` | heapprofd 守护进程主类 |
| `external/perfetto/src/heap_profiling/heap_profiler.cc` | 采样逻辑 |
| `frameworks/native/cmds/perfetto/...` | perfetto cmdline 工具 |
| `external/perfetto/protos/perfetto/config/profiling/...` | perfetto_hprof 配置 proto |
| `art/runtime/native_stack_dump.cc` | 调用栈还原 |
| `bionic/libc/bionic/malloc_hooks.cpp` | libc malloc hook 实现 |

## 附录 B:配置模板(`hprof_configs/perfetto_hprof.pbtxt`)

完整模板见 `hprof_configs/perfetto_hprof.pbtxt`,包含:
- 5 种典型场景配置(开发调试 / 灰度验证 / 正式监控 / Java-only / Native-only)
- 配置注释和参数说明
- 输出文件命名规范

## 附录 C:量化数据自检表

| 指标 | 传统 hprof | perfetto_heapprofd | 差异 |
|------|-----------|-------------------|------|
| 性能开销 | 5-30s STW | 1-3% 后台 | **10-100 倍** |
| 单次数据量 | 50-500MB | 1-10MB/s | **50-500 倍** |
| Java 覆盖 | 100% 对象图 | 采样对象 | 精度低 |
| Native 覆盖 | 0% | 100% malloc | **质的飞跃** |
| 时间维度 | 单快照 | 持续过程 | **质的飞跃** |
| 分析工具成熟度 | 极高(MAT) | 中(trace_processor SQL) | 工具链落后 |

## 附录 D:工程基线表

| 项 | 版本/路径 |
|----|---------|
| Perfetto upstream | `v43+` |
| Android 基线 | `9.0+`(heapprofd 必需) |
| 完整 heapprofd 守护 | Android 12+ |
| userdebug ROM | 必需(线上需 root) |
| heapprofd_client | Android 14 集成在 ART |
| 配套 trace_processor | Perfetto `v43+` |

## 篇尾衔接

**下一篇**:[04-内存泄漏典型案例与排查 SOP](04-内存泄漏典型案例与排查SOP.md) 会展开案例库——**Activity/Handler/Static 经典 5 大泄漏场景,系统级泄漏,Native 内存问题,完整的"从现象到根因"SOP**。

**强依赖本篇的章节**:
- 04 §5 会用本篇的 heapprofd 工具分析 native 泄漏案例
- 05 §3-§4 会用本篇的 perfetto_hprof 配置搭建监控体系

**本篇不覆盖**:
- 具体泄漏案例 → [04](04-内存泄漏典型案例与排查SOP.md)
- 内存监控体系搭建 → [05](05-实战：内存监控体系搭建.md)
- Perfetto UI 详细使用 → 见 [Perfetto 系列](../../Perfetto/)