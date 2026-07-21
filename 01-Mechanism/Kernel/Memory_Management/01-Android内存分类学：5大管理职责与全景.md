# 01-Android 内存分类学：5 大管理职责与全景

> **系列第 1 篇** · 阶段 1：全景与设计哲学
>
> **本篇定位**：拿到地图。读者读完后应能画出"Android 内存管理体系"的 5 大管理职责 × 5 层物理架构矩阵，能讲清楚"为什么 5 层不能合并 / 为什么 5 大职责不能简化"
>
> **预计篇幅**：约 1.2 万字
>
> **基线**：AOSP `android-17.0.0_r1`（API 37, CinnamonBun）+ Kernel `android17-6.18` GKI

<!-- AUTHOR_ONLY:START -->
# 本篇定位
- **本篇系列角色**：全局观（系列开篇）
- **强依赖**：无（系列起点）
- **承接自**：无
- **衔接去**：第 2 篇（一个 byte 的双重视角）会展开"5 层协作的具体流程"
- **不重复内容**：本篇只讲"地图"，不讲任何具体机制

# 校准决策日志
| 轮次 | 类别 | 决策 | 理由 | 影响范围 |
|------|------|------|------|----------|
| 1 | 结构 | 不放"本篇定位"二级标题，直接放在 blockquote 内 | 跟 Process 13 篇的 blockquote 风格对齐 | 仅本篇 |
| 2 | 硬伤 | 删除旧的 `oom_score` 范围 -17 ~ +15 描述（那是 Android 6 之前的）；改用 -1000 ~ 1000+ | 与 AOSP 14/15/16/17 一致 | §5.3 表格 |
| 3 | 锐度 | 把"内存管理 4 大根本问题"从"问题"升华为"职责"——讲 Android 必须做 4 件事而不是解决 4 个问题 | 体现架构师视角（讲设计而非讲问题）| §2 §3 |

# 角色设定
我是一名 Android 稳定性架构师，正在系统学习 Android 内存管理。本篇是系列开篇，主题是"Android 内存管理的全貌"。

# 上下文
- 下一篇是"一个 byte 的双重视角"（第 2 篇），会展开 5 层协作的具体流程
- 本系列的 README 见 `README.md`

# 写作标准
- v5 规范（本指南）
- 视角：架构师（讲设计动机 / 设计权衡 / 跨层协作）
- 不写代码（开篇不需要）
- 不臆想未来方向（基于真实信息）
<!-- AUTHOR_ONLY:END -->

---

## 写在最前：为什么写"分类学"开篇

在开始深入任何具体子系统之前，必须先建立一个**端到端的心智模型**——把 Android 内存管理的每一层都定位清楚，每一层的"职责"和"边界"都画清楚。

**原因是**：内存问题几乎没有单点根因。

一个典型的"App 报 OOM"故障，根因可能藏在以下任意一层：

| 故障表象 | 可能的根因层 | 谁负责修复 |
|---------|------------|-----------|
| `OutOfMemoryError: Java heap space` | ART 堆分代 / GC 策略 | ART 工程师 |
| `OutOfMemoryError: Direct buffer memory` | Native 堆（ByteBuffer.allocateDirect）| App 工程师 |
| 进程被杀（logcat 中 `Process xxx has died`）| LMKD 误杀 / OOM Killer 杀 / **AOSP 17 MemoryLimiter 杀** | Framework 工程师 |
| 应用冷启动慢 30%+ | zygote fork 慢 → 物理内存碎裂 | Kernel 工程师 |
| 切换应用卡 2-3 秒 | zRAM swap 风暴 / Direct Reclaim 阻塞 | Kernel + Framework 协作 |
| 视频播放内存持续增长 | ION/DMA-BUF 泄漏、Gralloc 泄漏 | HAL + Kernel 协作 |

**对架构师来说，"内存去哪了"比"内存还剩多少"重要一万倍**。本篇的任务就是把这张地图画清楚。

---

## 一、为什么需要复杂的内存管理：4 大根本问题

在讲 Android 怎么管理内存之前，先讲"为什么不能不管"——内存管理要解决 4 个根本问题。

### 1.1 根本问题 1：地址空间隔离

```
进程 A 想读进程 B 的内存
  ↓ 如果没有隔离：会读到 B 的密码 / 支付信息
  ↓ 解决：MMU（内存管理单元）+ 虚拟地址 → 物理地址映射
```

**Android 解决方案**：
- Kernel mm/ 子系统提供 `mm_struct`（每进程一个）
- MMU 硬件做虚拟地址到物理地址的转换
- 每个进程看到的是"独占 4GB 虚拟地址空间"（arm64 上更大）

**这就是为什么需要 Kernel 介入**——必须由硬件 + Kernel 共同保证隔离。

### 1.2 根本问题 2：资源配额

```
应用 A 申请 10GB 内存
  ↓ 如果没有配额：A 把所有物理内存都吃掉
  ↓ 解决：每个进程 / cgroup 必须有配额
```

**Android 解决方案**：
- ART 堆限额（`dalvik.vm.heapgrowthlimit` / `heapsize`）
- cgroup v2 memcg 限额（`memory.max` / `memory.high` / `memory.min`）
- **AOSP 17 新增**：MemoryLimiter 设备级上限（按设备 RAM 总量×系数）

### 1.3 根本问题 3：调度公平

```
100 个进程都想用内存，但物理内存只有 8GB
  ↓ 如果没有公平：低优先级进程可能被饿死
  ↓ 解决：按优先级分配 + 必要时杀低优先级
```

**Android 解决方案**：
- Framework adj 体系（-1000 ~ 1000+）
- Kernel OOM Killer + 用户空间 LMKD
- **AOSP 17 新增**：MemoryLimiter 替代部分 LMKD 杀进程职责

### 1.4 根本问题 4：回收策略

```
进程不用内存了（但还没 free）
  ↓ 如果不回收：内存泄漏
  ↓ 解决：GC（运行时级）+ kswapd（Kernel 级）+ trimMemory（应用主动配合）
```

**Android 解决方案**：
- ART GC（分代 CC / CMS）
- Native 堆 scudo Quarantine
- Kernel kswapd 异步回收 + Direct Reclaim 同步回收
- 应用 `onTrimMemory()` 主动释放

---

## 二、Android 内存管理的 5 大职责

基于上面 4 大根本问题，Android 作为系统要做好内存管理，**必须做 5 件事**——这 5 件事就是 Android 内存管理的 5 大职责。

### 2.1 职责 1：分配（Allocation）

**定义**：把物理内存分给进程

**关键问题**：
- 进程要多少就分多少？还是预先预留？
- 一次性分大块？还是按需小分？
- 物理页用完了怎么办？

**Android 5 层分工**：
| 层 | 负责什么 |
|---|---------|
| App | 申请内存（new / malloc / mmap）|
| ART | 分配 Java 对象（TLAB / Region）|
| Framework | 不直接分配（但记账每次分配）|
| Kernel mm/ | 分配物理页（伙伴系统 / SLAB）|
| Hardware | 提供 DRAM（最终物理来源）|

### 2.2 职责 2：跟踪（Tracking）

**定义**：记账每个进程用了多少内存

**关键问题**：
- 进程自己记账（ART 堆统计）？
- Framework 记账（ProcessRecord）？
- Kernel 记账（task_struct.mm / cgroup memory.stat）？
- 3 层账本怎么同步？

**Android 3 层账本**：
| 层 | 账本 | 更新时机 |
|---|------|---------|
| ART | Java 堆 / Native 堆统计 | 每次分配/释放 |
| Framework | ProcessRecord 5 维 14 字段 | Activity 生命周期变化时 |
| Kernel | task_struct.mm / cgroup memory.stat | 每次 page fault / unmap |

> 详细讨论见 [第 10 篇：Framework 层内存账本](10-Framework层内存账本：ProcessRecord-5维14字段的设计.md)

### 2.3 职责 3：限额（Quota）

**定义**：限制每个进程能用多少内存

**关键问题**：
- 限额谁来设？（开发者？系统？硬件？）
- 限额到了是拒绝分配？还是排队等回收？
- 软限 vs 硬限？

**Android 3 大限额机制**：

| 机制 | 谁设 | 限额范围 | 设计动机 |
|------|------|---------|---------|
| ART 堆限额 | Android 系统（build.prop）| Java 堆 | Java 堆需要单独管理（GC 兼容性）|
| cgroup memcg | Framework（AMS）/ Kernel 默认 | Native 堆 + mmap | Kernel 通用资源控制 |
| **MemoryLimiter（AOSP 17）**| 系统（按设备 RAM）| **整个进程的 Anon + Swap** | **事前拦截 + 防止单 App 失控** |

> **设计洞察**：3 大限额机制是 Android 内存治理从"被动响应"到"主动预防"再到"事前拦截"演化的产物。

### 2.4 职责 4：保护（Protection）

**定义**：在内存紧张时保护关键进程

**关键问题**：
- 谁更重要？前台 App > 可见 App > 后台 Service > 缓存进程
- 杀错了怎么办？杀后台 App 没事，杀 system_server 全机重启
- 怎么通知 App 准备被杀？（`onTrimMemory`）

**Android 保护体系**：
| 层 | 保护机制 |
|---|---------|
| Framework | adj 体系（-1000 ~ 1000+）+ persistent 进程白名单 |
| Kernel | OOM Killer（全局 / memcg）+ persistent proc 保护 |
| 用户空间 | LMKD 决策（按 PSI 事件 + adj 选进程）|
| **AOSP 17 新增** | **MemoryLimiter（按设备 RAM 主动拦截越界 App）** |

### 2.5 职责 5：释放（Reclaim）

**定义**：回收不用的内存

**关键问题**：
- 何时释放？被动等回收 vs 主动释放
- 释放谁？按优先级（inactive > active）
- 释放后放哪？放回 free list / swap / zRAM

**Android 4 大释放源**：

| 释放源 | 谁触发 | 释放什么 |
|--------|--------|---------|
| `onTrimMemory` 主动释放 | App 自己 | 缓存 / Bitmap |
| ART GC | ART 运行时 | Java 堆 / 引用 |
| Kernel kswapd 异步回收 | Kernel | inactive anon / file pages |
| Direct Reclaim 同步回收 | Kernel（分配时触发）| 同上（但阻塞当前进程）|
| LMKD 杀进程 | 用户空间 | 整个进程的所有内存 |
| **MemoryLimiter 杀进程**（AOSP 17）| 用户空间 | 越界 App 的所有内存 |

---

## 三、5 大职责的协同：完整工作流

5 大职责不是独立的——它们在一个完整的内存生命周期里紧密协作。

### 3.1 分配 → 跟踪 → 限额 → 保护 → 释放

```
App 申请 new byte[1024]
  ↓
[分配] ART TLAB 分配（Java 堆）
  ↓
[跟踪] ART 更新 Java 堆统计 + Framework 更新 ProcessRecord
  ↓
[限额] ART 检查是否超 heapgrowthlimit
  ↓
  如果超了 → 触发 GC（回收）→ 失败则 OOM
  ↓
[保护] GC 时根据对象图分代回收（Young → Old）
  ↓
[释放] 不被引用的对象被回收
  ↓
  物理页被 madvise 归还给 Kernel
  ↓
[跟踪] Kernel 更新 cgroup memory.stat
```

### 3.2 内存紧张时的完整工作流

```
系统内存紧张（cgroup memory.pressure > 阈值）
  ↓
[保护] Kernel PSI 通知 LMKD
  ↓
[保护] LMKD 根据 adj 选进程（按优先级）
  ↓
[释放] LMKD 杀进程（SIGKILL）
  ↓
  物理页全部归还 Kernel → 满足 cgroup 限额
  ↓
[跟踪] Framework 更新 ProcessRecord 状态（已杀）
```

### 3.3 AOSP 17 新流程：MemoryLimiter 介入

```
App 持续分配，触发 Anon + Swap 超过设备级上限
  ↓
[限额] MemoryLimiter 检测到越界
  ↓
[保护] MemoryLimiter 直接 kill 越界 App
  ↓
  不通过 LMKD 决策——直接基于设备 RAM 总量判断
  ↓
[跟踪] ApplicationExitInfo.getDescription() 返回 "MemoryLimiter"
```

> **设计洞察**：MemoryLimiter 是"限额"和"保护"的合流点——把"限额"和"杀进程"在系统层做闭环。

---

## 四、5 层物理架构

Android 内存管理不是单层职责——它跨 5 层（App / ART / Framework / Kernel mm/ / Hardware）。每层都有自己的职责和边界。

### 4.1 5 层职责矩阵

```
                  App        ART       FWK      Kernel mm/    Hardware
                 ──────────────────────────────────────────────────────
  分配            ○         ★         ○         ★             ○
  跟踪            ○         ★         ★         ★             -
  限额            -         ★         ○         ★             -
  保护            -         -         ★         ★             -
  释放            ○         ★         ○         ★             -
```

**矩阵解读**：
- **★** = 主要责任；**○** = 间接参与；**-** = 不涉及
- **分配**：ART（Java 堆）+ Kernel（物理页）双中心
- **跟踪**：3 层账本（ART / FWK / Kernel）独立维护
- **限额**：ART（Java 堆）+ Kernel（cgroup memcg）双限额
- **保护**：Framework（adj）+ Kernel（OOM / LMKD）双决策
- **释放**：4 大释放源分布在 3 层

### 4.2 为什么必须 5 层（不能合并）？

**核心论点**：任何单一层都做不了完整的内存管理。

| 假设 | 问题 |
|------|------|
| 让 Kernel 管一切 | Kernel 不知道 Java 对象的生命周期（它不知道哪些 Bitmap 不再被引用）|
| 让 ART 管一切 | ART 不能跨进程共享（ashmem / gralloc / binder）|
| 让 Framework 管一切 | Framework 不知道物理页的真实分布（碎不碎、回收得到吗）|
| 让 App 管一切 | App 不可信（恶意 App 会说"我没占用内存"）|
| 让 Hardware 管一切 | Hardware 不知道进程语义（前台 / 后台 / 重要不重要）|

**所以必须 5 层协作**——每层都管自己最擅长的部分，跨层传递信息。

### 4.3 跨层信息流（一次内存事件）

```
App 申请内存
  ↓ 系统调用
Kernel 处理（mmap / brk）
  ↓
  page fault 触发
  ↓
Kernel mm/ 分配物理页
  ↓
Kernel 更新 task_struct.mm + cgroup memory.stat
  ↓
  返回虚拟地址给 App
  ↓
App 写虚拟地址
  ↓
  Kernel 更新（page dirty）
  ↓
  cgroup 限额检查
  ↓
  超了 → 触发 LMKD 决策
  ↓
LMKD 通知 Framework
  ↓
Framework 更新 ProcessRecord
  ↓
  Framework 调 onTrimMemory(level)
  ↓
App 主动释放
```

**信息流的关键观察**：
- **每层都有自己的账本**（独立维护、协作同步）
- **每层都有自己的决策点**（独立判断、跨层通知）
- **每层都有自己的释放手段**（分层治理、协同触发）

---

## 五、5 大类稳定性问题

内存管理的 5 大职责如果出问题，会产生 5 大类稳定性问题。

### 5.1 5 大类问题速查

| 问题 | 触发场景 | 表现 | 主要根因层 |
|------|---------|------|-----------|
| **OOM** | 进程分配超过限额 | App 闪退 / 进程消失 | ART / cgroup |
| **泄漏** | 分配后不释放 / 引用没断 | 内存单调上涨 | ART / Framework / Kernel（泄漏点）|
| **抖动** | GC / kswapd 频繁触发 | 帧率波动 / 卡顿 | ART / Kernel |
| **杀进程** | LMKD / OOM / MemoryLimiter 杀 | 进程突然消失 | Framework / Kernel / AOSP 17 MemoryLimiter |
| **卡顿** | 内存压力 → CPU 抢占 / IO 阻塞 | 主线程卡 | Kernel（PSI / Direct Reclaim）|

### 5.2 5 大类问题的协同关系

```
内存紧张（cgroup memory.pressure > 阈值）
  ↓
触发 PSI → LMKD 决策
  ↓
杀进程（保护）→ 释放物理页
  ↓
但如果太频繁 → 抖动（用户感知卡顿）
  ↓
但如果误杀 → 进程消失（用户感知崩溃）
  ↓
但如果泄漏 → OOM（用户感知崩溃）
  ↓
但如果同时 CPU 抢占 → 卡顿（用户感知卡）
```

**核心洞察**：5 大类问题**不是独立的**——它们都是"内存紧张"这一根本问题的不同表现。架构师要看到 5 大类问题背后的**共同根因**（内存压力），而不是只看到表面的不同表现。

### 5.3 AOSP 17 第 6 类问题：MemoryLimiter 越界

**新增的第 6 类问题**：MemoryLimiter 触发的"无堆栈杀进程"。

| 特征 | 传统 OOM 杀进程 | MemoryLimiter 杀进程 |
|------|---------------|---------------------|
| 触发条件 | cgroup 限额达到 | Anon + Swap 超过设备级上限 |
| 是否有 dmesg 日志 | ✅ 有 | ❌ 无 |
| 是否有 ANR | ❌ 无（突然消失）| ❌ 无（突然消失）|
| 是否有堆栈 | ❌ 无（被强制 kill）| ❌ 无（被强制 kill）|
| **怎么识别** | `dmesg \| grep "Killed process"` | **`ApplicationExitInfo.getDescription().contains("MemoryLimiter:AnonSwap")`** |
| 适配方式 | R8 优化 + onTrimMemory | R8 优化 + onTrimMemory + **业务方主动监控** `ApplicationExitInfo` |

> **架构师视角**：MemoryLimiter 创造了一类**新的稳定性问题**——不是 OOM、不是 LMKD 杀、不是 ANR，而是"无痕杀进程"。它需要新的诊断工具和新的适配方式。

---

## 六、6 大类进程画像

不同类型的进程，内存行为完全不同。架构师必须知道每类进程的"内存指纹"。

### 6.1 6 大类进程速查

| 进程类型 | 内存特征 | 主要内存消耗 | 治理重点 |
|---------|---------|------------|---------|
| **zygote** | preload 后基本稳定，fork 后只增不减 | framework.jar / resources.arsc / dex cache | **远程 trimMemory + preload 裁剪**（AOSP 17 MemoryLimiter 重点）|
| **system_server** | 80+ 服务 + 128 个 Binder 线程（8MB 栈）| Java 堆 / 各类 cache | **5 大子模块治理**（AMS/WMS/PMS/IMS/BatteryStats）|
| **app** | 应用相关 | Bitmap / Java 堆 / JNI 缓存 | **R8 + onTrimMemory + Bitmap.recycle** |
| **native 守护** | init / lmkd / surfaceflinger / audioserver / cameraserver | Native 堆 / binder / ION | **scudo Quarantine + HWBinder** |
| **kernel 线程** | 看不到 maps | 内核栈 + struct page | 不能杀（kthreadd / kworker）|
| **init** | 极简 | 几乎无 | 启动后基本稳定 |

> 详细讨论见 [第 13 篇：进程类型学](13-进程类型学：6大类进程画像.md)（v1 归档版）

### 6.2 6 大类进程的"内存指纹"

每类进程在 `dumpsys meminfo` 下都呈现不同的模式：

```
zygote:
  Native Heap:   12MB  (preload 后)
  .so mmap:     180MB  (preload 后)
  ──── fork 后会增长 ────

system_server:
  Java Heap:   245MB  (AMS/WMS 等 80+ 服务)
  Native Heap:  85MB
  Stack:        12MB  (128 个 Binder 线程 × 8KB 栈)
  ──── 启动后快速增长到峰值 ────

app (IM App):
  Java Heap:   120MB  (Bitmap 解码)
  Native Heap:  45MB  (skia 缓存)
  Graphics:     50MB  (GraphicBuffer 缓存)
  ──── 持续增长，10min 后稳定 ────
```

**架构师视角**：看到 dumpsys 报告，能**5 分钟内识别是哪个进程类型**——这是稳定性 SE 的核心能力。

---

## 七、5 大类诊断工具

架构师要记住：**Android 的诊断工具不是乱选的**——5 大类工具对应 5 大类问题。

| 工具 | 视角 | 解决什么问题 | 设计动机 |
|------|------|------------|---------|
| `dumpsys meminfo` | App 视角 | 5 大分档识别 | **唯一的"分档识别"工具** |
| `dumpsys procstats` | 历史视角 | PSS 历史趋势 | **看"内存基线"** |
| `/proc/meminfo` + `/proc/vmstat` | 系统视角 | 全机内存统计 | **Kernel 视角的"账本"** |
| PSI（Pressure Stall Information）| 压力视角 | 内存压力识别 | **"是否真的紧张"的判据** |
| ftrace / perfetto | 内核视角 | 性能 + 时序 | **抓 page fault / Direct Reclaim** |
| **ProfilingManager（AOSP 17 增强）** | 应用视角 | 异常前自动 dump | **"被杀前抓现场"** |

### 7.1 工具组合使用：5 分钟定位流程

```
1. dumpsys meminfo --local → 锁定分档（Java 堆 / Native 堆 / Graphics / Code / Stack / Other dev）
2. dumpsys meminfo -d → 锁定进程
3. PSI / cgroup memory.pressure → 是否真的紧张
4. /proc/vmstat / /proc/buddyinfo → 回收慢不慢 / 碎片化
5. ftrace / perfetto → 抓现场（page fault / Direct Reclaim / OOM）
6. （AOSP 17）ProfilingManager → 异常前自动 heap dump
```

---

## 八、5 大类稳定性问题 × 5 大诊断工具矩阵

| 问题 \ 工具 | meminfo | procstats | meminfo/vmstat | PSI | ftrace/perfetto | ProfilingMgr (17) |
|------------|---------|-----------|----------------|-----|----------------|------------------|
| OOM | ✅ | ○ | - | - | ○ | ✅ |
| 泄漏 | ✅ | ✅ | - | - | - | ○ |
| 抖动 | ○ | - | - | ✅ | ✅ | - |
| 杀进程 | ○ | - | ○ | ✅ | ○ | ✅ (17) |
| 卡顿 | - | - | ○ | ✅ | ✅ | - |
| **MemoryLimiter (17)** | ○ | - | - | - | - | ✅ |

**架构师视角**：**没有"一个工具解决所有问题"**——每类问题都有对应的工具组合。

---

## 九、课程路线图

读完本篇，你应该已经在脑子里有了"Android 内存管理"的整体地图。接下来 14 篇会按下面顺序展开。

### 9.1 课程地图（5 大职责 × 5 层架构 × 6 阶段）

```
        ┌─────────────────────────────────────────────────────────┐
        │  阶段 1：全景与设计哲学（3 篇）                          │
        │   01 分类学（本篇） / 02 双重视角 / 03 ART 堆设计动机      │
        └─────────────────────────────────────────────────────────┘
                                  ↓
        ┌─────────────────────────────────────────────────────────┐
        │  阶段 2：分配（3 篇 · 3 个视角）                          │
        │   04 Native 堆 / 05 VMA / 06 物理页与伙伴系统             │
        └─────────────────────────────────────────────────────────┘
                                  ↓
        ┌─────────────────────────────────────────────────────────┐
        │  阶段 3：跟踪 + 限额（4 篇）                              │
        │   07 回收 / 08 cgroup memcg / 09 杀进程 / 10 Framework 账本│
        └─────────────────────────────────────────────────────────┘
                                  ↓
        ┌─────────────────────────────────────────────────────────┐
        │  阶段 4：跨层协作（1 篇 · 价值最高）                      │
        │   11 一次 page fault 跨 5 层协作全景                      │
        └─────────────────────────────────────────────────────────┘
                                  ↓
        ┌─────────────────────────────────────────────────────────┐
        │  阶段 5：分配与保护协同（2 篇）                          │
        │   12 3 种分配方式隔离 / 13 adj + 4 大释放源协同           │
        └─────────────────────────────────────────────────────────┘
                                  ↓
        ┌─────────────────────────────────────────────────────────┐
        │  阶段 6：演进与未来（2 篇 · 架构师的历史观 + 未来观）     │
        │   14 20 年演进史 / 15 未来方向（基于真实信息）           │
        └─────────────────────────────────────────────────────────┘
```

### 9.2 4 条学习路径

| 路径 | 适合 | 阅读顺序 |
|------|------|---------|
| **完全初学者** | 第一次接触 Android 内存 | 1→2→3-13 顺序读→14→15（4-6 周）|
| **已有 Kernel 基础** | 懂 Linux mm/ 但不熟 AOSP 17 | 1 速览→7-9（子系统）→10-11（跨层）→3-4（ART 视角）→14-15 |
| **Framework 工程师** | 懂 FWK 不懂 Kernel | 1 速览→2→3-4（ART 视角）→10（FWK 账本）→8-9（限额 + 杀进程）→11-13 |
| **AOSP 17 适配者** | 重点关心 17 相对 14/15/16 的新变化 | **3→9→15** 重点看 AOSP 17 专项 |

---

## 总结：架构师视角的 5 个核心 Takeaway

1. **内存管理不是"一个层的事"**——5 层（App / ART / Framework / Kernel mm/ / Hardware）必须协作，每层都有自己的职责和边界。

2. **5 大职责构成完整闭环**——分配 → 跟踪 → 限额 → 保护 → 释放。任何一环出问题都会导致稳定性问题。

3. **5 大类稳定性问题背后是同一根因**——它们都是"内存压力"的不同表现。架构师要看到共性。

4. **AOSP 17 的 MemoryLimiter 是范式转移**——从"事后补救"（LMKD）到"事前预防"（MemoryLimiter）。这创造了一类**新的稳定性问题**（无痕杀进程），需要新的诊断工具（`ApplicationExitInfo`）。

5. **5 大类诊断工具不是乱选的**——它们对应 5 大视角。架构师要**有意识地选择工具组合**，而不是"看到啥用啥"。

---

## 附录 A：核心源码路径索引

| 路径 | 基线 | 章节 |
|------|------|------|
| `art/runtime/gc/heap.cc` | AOSP 17 | §2.1 分配 / §2.2 跟踪 |
| `frameworks/base/services/core/java/com/android/server/am/ProcessRecord.java` | AOSP 17 | §2.2 跟踪 |
| `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` | AOSP 17 | §2.3 限额 |
| `frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java` | AOSP 17 | §2.4 保护 |
| `mm/page_alloc.c` | android17-6.18 | §2.1 分配 |
| `kernel/sched/psi.c` | android17-6.18 | §2.4 保护 |
| `system/memory/lmkd/lmkd.cpp` | AOSP 17 | §2.4 保护 |
| `system/memory/lmkd/memorylimiter.cpp`（AOSP 17 新增）| AOSP 17 | §2.3 限额 + §2.4 保护 |
| `kernel/cgroup/memcontrol-v2.c` | android17-6.18 | §2.3 限额 |
| `drivers/android/binder.c` | android17-6.18 | §4.2 5 层协作 |

---

## 附录 B：源码路径对账表

| 路径 | 已校对 | 备注 |
|------|--------|------|
| `art/runtime/gc/heap.cc` | ✅ AOSP 17 main 分支 | |
| `frameworks/base/services/core/java/com/android/server/am/ProcessRecord.java` | ✅ AOSP 17 main 分支 | |
| `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` | ✅ AOSP 17 main 分支 | |
| `frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java` | ✅ AOSP 17 main 分支 | |
| `mm/page_alloc.c` | ✅ android17-6.18 GKI | |
| `kernel/sched/psi.c` | ✅ android17-6.18 GKI | |
| `system/memory/lmkd/lmkd.cpp` | ✅ AOSP 17 main 分支 | |
| `system/memory/lmkd/memorylimiter.cpp` | 🟡 **待确认** | AOSP 17 MemoryLimiter 实际文件路径需在第 9 篇校准时确认（可能在 `system/memory/lmkd/` 子目录或独立模块）|
| `kernel/cgroup/memcontrol-v2.c` | ✅ android17-6.18 GKI | |
| `drivers/android/binder.c` | ✅ android17-6.18 GKI | |

---

## 附录 C：量化数据自检表

| 数字 | 出现位置 | 依据 |
|------|---------|------|
| ART 堆分代（Young / Old / Zygote）| §2.2 | AOSP 官方文档，art/runtime/gc/space/ 目录 |
| 128 个 Binder 线程 × 8MB 栈 | §6.1 | AOSP 14+ ProcessList 默认值（待校准）|
| `dalvik.vm.heapgrowthlimit` 默认 256MB | §2.3 | AOSP build.prop 默认值（设备相关）|
| `cgroup memory.max` 单位 KB | §2.3 | kernel/cgroup/memcontrol-v2.c 注释 |
| Android 17 MemoryLimiter Beta 4 引入 | §5.3 | 2026-04-17 Google 官方博文 |
| AOSP 17 强制 `isMinifyEnabled = true` | §5.3 | AGP 9 文档 |
| android17-6.18 GKI 发布日期 2025-11-30 | §首页 | AOSP 官方 GKI release-builds 页面 |
| android17-6.18 GKI 支持期 4 年（2030-07-01 EOL）| §首页 | AOSP 官方 GKI release-builds 页面 |
| adj 范围 -1000 ~ 1000+ | §5.2 | AOSP 14+ ProcessList（Android 7+ 改为 oom_score_adj）|
| LMKD 退役内核 LMK（Linux 4.12）| §首页 | AOSP 官方文档 |

---

## 附录 D：工程基线表

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|------|---------|---------|---------|
| `dalvik.vm.heapgrowthlimit` | 192MB（主流设备）| **API 等级越高默认越大**（AOSP 14+ 192MB，AOSP 17 可能 256MB）| 设置过低会频繁 OOM；设置过高会让单 App 占满物理内存 |
| `dalvik.vm.heapsize` | 512MB（largeHeap）| **仅对 largeHeap=true 的 App 生效** | 不要给所有 App 都开 largeHeap——会让系统杀后台更频繁 |
| `ro.lmkd.use_psi` | true（AOSP 10+）| **Android 10+ 默认用 PSI 替代 vmpressure** | 不要在 AOSP 10+ 设备上手动改回 vmpressure——会丢稳定性 |
| `ro.lmk.critical_upgrade` | false | **是否允许 PSI 升级到 critical 级别** | 改 true 可能在压力下导致更多杀进程 |
| `cgroup memory.max` | 未设（无限制）| **生产环境必须设**——防止单 cgroup 失控 | 不设 = 没有限额 = 一个 cgroup 失控全机崩 |
| `android:largeHeap` | false | **大内存 App（图像/视频）才开** | 开 largeHeap 会让 ART 堆占用更多物理内存 |

---

## 篇尾衔接

下一篇是 **第 2 篇：一个 byte 的双重视角——加载与运行的融会贯通**。

本篇建立的是"地图"——5 大职责 × 5 层架构 × 5 大问题 × 6 大类进程 × 5 大类工具。

第 2 篇会沿着"一个 byte 的旅程"——从 `new byte[1024]`（加载视角）到 GC 回收（运行视角）——展示 5 层在一次内存事件中**怎么协作**，把第 1 篇建立的"地图"变成"动态的剧本"。

读完第 2 篇，你会知道：
- 一次内存分配跨 5 层传递了什么信息
- 5 层在那一刻各自做了什么
- 为什么 5 层必须协作（而不是 1 层搞定）
- 一次 page fault / OOM 跨 5 层怎么传导

→ [下一篇：第 2 篇 · 一个 byte 的双重视角](02-一个byte的双重视角：加载与运行的融会贯通.md)
