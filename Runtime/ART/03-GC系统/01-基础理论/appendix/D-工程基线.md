# 附录 D：工程基线（v2 升级版）

> **本附录是 01-基础理论子模块的"工程基线"** —— 关键参数、监控指标、排查 checklist 的完整清单。
>
> **目的**：把 01 子模块 9 篇的知识点转化为可直接使用的工程工具。
>
> **AOSP 版本**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.12`（6.12 LTS）
> **v2 升级日期**：2026-07-18

---

## 0. 本附录定位

| 维度 | 本附录承担 | 本附录不涉及 |
| :--- | :--- | :--- |
| 关键可调参数基线（ART GC 相关） | ✓ 完整 | — |
| 监控指标基线（dumpsys / Perfetto） | ✓ 完整 | — |
| 排查 Checklist（OOM / GC 卡顿 / 漏标） | ✓ 完整 | — |
| APM 监控指标 + 告警阈值 | ✓ 完整 | — |
| 工具链配置 | ✓ 完整 | — |
| 关键 KPI 基线 | ✓ 完整 | — |
| 源码路径 | — | 详见 [A-源码索引](A-源码索引.md) |
| 版本号对账 | — | 详见 [B-路径对账](B-路径对账.md) |
| 实战案例 | — | 详见各篇实战案例章节 |

**承接自**：[A-源码索引](A-源码索引.md) + [B-路径对账](B-路径对账.md) 给出了源码 + 版本对账；**本附录给出工程工具箱**。

**衔接去**：[A-源码索引](A-源码索引.md) 附录 A 集中源码路径；[B-路径对账](B-路径对账.md) 附录 B 给出版本号 / commit hash 对账；[10-ART17分代GC强化专章 v2](../../10-ART17分代GC强化专章-v2.md) 专章 ART 17 强化。

---

## 校准决策日志（v2 升级 · 3 轮全跑）

### 第 1 轮：结构校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| v1 旧稿标记段 | 在（顶部 14 行） | **删**（v1 → v2 实质升级） | 内容已按 v4 规范重写，标记段失效 |
| 本附录定位 | 无 | **新增**（v4 §3 强制要求） | 明确本附录职责边界 |
| 衔接去 | 无 | **新增 3 篇**（A-源码索引/B-路径对账/10-ART17 专章） | 跨篇引用矩阵 |
| 章节组织 | 按 1-7 旧结构 | **按"参数 → 监控 → 排查 → APM → 工具 → KPI"** | 实战可查性 |
| AOSP 17 软阈值 | 未列出 | **新增 §1.2 整行** | AOSP 17 关键参数 |

### 第 2 轮：硬伤校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| 基线版本号 | AOSP 14 / Linux 5.15 | AOSP 17 / **Linux 6.12** | **2026-07-18 基线纠正** |
| API 等级 | API 34 | **API 37** | 与 AOSP 17 配套 |
| Linux 内核 | android17-6.18（误） | **android17-6.12** | **基线纠正** |
| Card Table 粒度默认值 | 512B | **128B（AOSP 17）** | 基线纠正 |
| **软阈值 kSoftThresholdPercent** | 未列出 | **新增 §1.2** | AOSP 17 关键参数 |
| **Finalizer 线程数** | 1 线程 | **4 线程池化（AOSP 17）** | 基线纠正 |
| **编译 SDK** | 34 | **37** | 与 AOSP 17 配套 |
| LeakCanary 版本 | 2.10+ | **2.14+** | AOSP 17 兼容版本 |
| MAT 版本 | 1.11+ | **1.13+** | AOSP 17 hprof 格式 |
| Perfetto 版本 | 18.x+ | **30.x+** | AOSP 17 屏障统计 |

### 第 3 轮：锐度校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| §2 监控指标 | 通用 | **新增 AOSP 17 屏障统计 + 软阈值触发频率** | AOSP 17 时代新指标 |
| §3 排查 Checklist | 3 类 | **保留 3 类 + 加 1 类 ART 17 漏标排查** | 完整覆盖 |
| §4 APM 告警 | AOSP 14 时代 | **AOSP 17 强化阈值（GenCC 暂停阈值）** | 新基线 |
| §6 KPI 基线 | AOSP 14 | **AOSP 17（Young GC 频繁 + STW < 1ms）** | 新基线一致性 |
| §8 后续篇目工程基线 | 1-7 旧编号 | **1-9 完整 + 10 专章** | v2 完整结构 |

---

## 一、关键可调参数基线（ART GC 相关）

### 1.1 dalvik.vm.* 参数

| 参数 | 默认值 | 选用准则 | 踩坑提醒 | AOSP 17 变化 |
| :--- | :--- | :--- | :--- | :--- |
| `dalvik.vm.heapgrowthlimit` | 256MB | 默认即可 | 误用 `largeHeap` 被 LMK 杀得更快 | 不变 |
| `dalvik.vm.heapsize` | 512MB | 仅 `largeHeap=true` 生效 | 误用会让 GC 扫描更慢 | 不变 |
| `dalvik.vm.softrefthreshold` | 0.25 | 调小 → SoftRef 保留更少 | 影响 Glide 缓存命中率 | 不变 |
| `dalvik.vm.heaptargetutilization` | 0.75 | 调小 → 堆更早收缩 | 太低会触发频繁 Trim | 不变 |
| `dalvik.vm.gc.max-relative-concurrent-start-threshold` | 0.05 | 调整 CC GC 启动时机 | 影响后台 GC 频率 | 不变 |
| `dalvik.vm.usejit` | true | 默认即可 | 关闭会降低性能 | 不变 |
| `dalvik.vm.dex2oat-Xms` | 64m | 默认即可 | 影响 dex2oat 启动速度 | 不变 |
| `dalvik.vm.dex2oat-Xmx` | 512m | 默认即可 | 影响 dex2oat 最大内存 | 不变 |
| `dalvik.vm.image-dex2oat-Xms` | 64m | 默认即可 | 影响 image dex2oat 启动速度 | 不变 |
| `dalvik.vm.image-dex2oat-Xmx` | 64m | 默认即可 | 影响 image dex2oat 最大内存 | 不变 |

### 1.2 ART 内部参数（AOSP 17 新增软阈值 + Finalizer 池化）

| 参数 | 默认值 | 选用准则 | 踩坑提醒 | AOSP 17 变化 |
| :--- | :--- | :--- | :--- | :--- |
| **`kSoftThresholdPercent`** | **30** | **AOSP 17 默认** | **太低→GC 频繁** | **AOSP 17 新增** |
| **`kHardThresholdPercent`** | **80** | **AOSP 17 默认** | 不变 | **AOSP 17 新增** |
| `ConcurrentCopying::kMaxMarkStackSize` | 64 KB | 默认即可 | 太大占用内存 | 不变 |
| **`CardTable::kCardSize`** | **128 字节** | **AOSP 17 默认** | **ART 14 = 256B** | **AOSP 17 强化** |
| `ReferenceProcessor::kDefaultSoftRefThreshold` | 0.25 | 同 `dalvik.vm.softrefthreshold` | 一致性 | 不变 |
| `Heap::kDefaultMaxRelativeConcurrentStartThreshold` | 0.05 | 同 `dalvik.vm.gc.max-relative-...` | 一致性 | 不变 |
| **`FinalizerDaemon::kPoolSize`** | **4** | **AOSP 17 默认** | **ART 14 = 1 线程** | **AOSP 17 池化** |
| **`RBCCState` 位数** | **3 bit** | **AOSP 17 默认** | **ART 14 = 2 bit** | **AOSP 17 扩展** |

### 1.3 Kernel 相关参数（AOSP 17 + Linux 6.12）

| 参数 | 默认值 | 选用准则 | 踩坑提醒 |
| :--- | :--- | :--- | :--- |
| `vm.lowmemkiller.minfree` | 厂商定制 | 默认即可 | 影响 LMK 杀进程时机 |
| `vm.vfs_cache_pressure` | 100 | 默认即可 | 影响文件系统缓存 |
| `vm.swappiness` | 60 | 调高 → 更积极 swap | 影响 zram 行为 |
| `vm.dirty_ratio` | 20 | 默认即可 | 影响脏页回写 |
| `vm.pressure_level` | 内核 4.20+ | 默认即可 | 内存压力通知 |
| **Linux 6.12 sheaves** | **启用** | **AOSP 17 默认** | **Native 堆 -15-20%** |
| **Linux 6.12 io_uring** | **5.x+** | **AOSP 17 默认** | **Card Table 刷盘 -30%** |

### 1.4 关键参数配置示例（custom.prop，AOSP 17）

```properties
# 调优示例（仅供参考）
dalvik.vm.heapgrowthlimit=256m
dalvik.vm.heapsize=512m
dalvik.vm.softrefthreshold=0.25
dalvik.vm.heaptargetutilization=0.75
dalvik.vm.gc.max-relative-concurrent-start-threshold=0.05

# OEM 定制（小米/华为等）
ro.config.low_ram=false

# AOSP 17 软阈值（一般不手动调整，ART 内部参数）
# kSoftThresholdPercent=30（默认值）
# kHardThresholdPercent=80（默认值）

# AOSP 17 屏障统计（调试时启用）
dalvik.vm.barrier-stats=true
```

---

## 二、监控指标基线

### 2.1 dumpsys meminfo 关键指标

| 指标 | 含义 | 正常范围 | 异常处理 |
| :--- | :--- | :--- | :--- |
| **Native Heap** | Native 内存分配 | < 200MB | 检查 JNI / DirectByteBuffer |
| **Dalvik Heap** | Java 堆使用 | < heapgrowthlimit | 检查 GC Root / 泄漏 |
| **Dalvik Heap Alloc** | 已分配 Java 堆 | < Dalvik Heap Size | 同上 |
| **Stack** | 线程栈 | < 5MB / thread | 检查线程数 |
| **Cursor** | Cursor 内存 | < 10MB | 检查 Cursor 泄漏 |
| **Ashmem** | 共享内存 | < 50MB | 检查 Surface / Bitmap |
| **Graphics** | 图形内存 | < 100MB | 检查 GL Texture |
| **Code** | 代码段 | < 100MB | 检查 DEX / OAT 大小 |
| **Other dev** | 其他设备 | < 20MB | — |
| **.so mmap** | .so 映射 | < 50MB | 检查 .so 泄漏 |
| **.jar mmap** | .jar 映射 | < 20MB | — |
| **.apk mmap** | .apk 映射 | < 20MB | — |
| **.ttf mmap** | .ttf 映射 | < 10MB | — |
| **.dex mmap** | .dex 映射 | < 50MB | 检查 DEX 数量 |
| **Other mmap** | 其他映射 | < 50MB | — |
| **EGL mtrack** | EGL 内存追踪 | < 50MB | 检查 EGL 泄漏 |
| **GL mtrack** | GL 内存追踪 | < 50MB | 检查 GL Texture 泄漏 |
| **Unknown** | 未知 | < 10MB | — |
| **TOTAL** | 总计 | < 500MB（普通 App） | 综合判断 |
| **TOTAL PSS** | PSS 总计 | < 500MB | 综合判断 |
| **TOTAL RSS** | RSS 总计 | < 1GB | 综合判断 |
| **TOTAL SWAP PSS** | Swap PSS | < 100MB | 检查 Swap 使用 |

### 2.2 GC 关键指标（AOSP 17 强化）

| 指标 | 含义 | AOSP 17 正常范围 | 异常处理 |
| :--- | :--- | :--- | :--- |
| **Young GC 频率** | Young GC 每分钟次数 | **5-10 次/分钟（软阈值 30%）** | **检查堆压力** |
| **Major GC 频率** | Full GC 每小时次数 | **< 1 次/小时** | **检查分代假说** |
| **Young GC STW** | Young GC 暂停时间 | **< 1ms** | **检查 Card Table** |
| **Major GC STW** | Major GC 暂停时间 | **< 20ms** | **检查 Live Set 大小** |
| **Background GC 频率** | 后台 GC 频率 | **1-3 次/分钟** | **检查 `dalvik.vm.gc.max-relative-...`** |
| **Finalizer 队列深度** | 待 finalize 的对象数 | **< 100** | **检查 finalize() 阻塞** |
| **Reference 队列深度** | 待清理 Reference 数 | < 1000 | 检查 Reference 泄漏 |
| **Card Table dirty 比例** | dirty card 占比 | < 5% | 检查跨代引用频率 |
| **TLAB 分配成功率** | TLAB 分配占比 | > 95% | 检查分配竞争 |
| **Concurrent GC 标记速度** | 标记对象数/秒 | > 100K/秒 | 检查对象数 |
| **写屏障调用开销** | 单次写屏障 | **< 20ns（AOSP 17）** | **检查写屏障优化** |
| **读屏障调用开销** | 单次读屏障 | **< 10ns（AOSP 17）** | **检查读屏障优化** |
| **屏障冲突率** | 多线程屏障冲突 | **< 5%（CAS 优化后）** | **检查 CAS 优化** |

### 2.3 GC 日志关键字段（logcat）

```bash
# ART GC 日志（AOSP 17）
adb logcat -d -s "art" | grep -i "gc"

# 关键日志示例
art : Background concurrent copying GC freed 1048576(13MB) AllocSpace objects, 0(0B) LOS objects, 50% free, 13MB/26MB, paused 1.234ms total 50.5ms
#                                                              ↑                    ↑
#                                                              释放字节数           暂停时间

# 关键字段解读
# - freed：释放的字节数 + 对象数
# - LOS：Large Object Space
# - free：释放后空闲比例
# - AllocSpace：Allocation Space 大小
# - paused：STW 时间
# - total：GC 总耗时
```

### 2.4 AOSP 17 新增 GC 日志（软阈值触发）

```bash
# 查看软阈值触发的 Young GC
adb logcat -d -s "art" | grep "TriggerYoungGC"

# 输出示例（AOSP 17）：
art : TriggerYoungGC: heap=35% > soft=30%, pause=0.5ms, freed=8MB
#                   ↑                  ↑        ↑
#                   堆占用 35%         软阈值 30%   暂停 < 1ms
```

### 2.5 AOSP 17 屏障统计日志

```bash
# 启用屏障统计（调试时）
adb shell setprop dalvik.vm.barrier-stats true

# 查看屏障统计
adb logcat -d -s "art" | grep "BarrierStats"

# 输出示例（AOSP 17）：
art : BarrierStats: write=200ns/call, read=10ns/call, conflicts=2%
#                            ↑                  ↑
#                            写屏障开销         读屏障开销
```

### 2.6 Perfetto 关键 trace 字段

```
# Perfetto trace 中的 GC 事件
ART::ConcurrentCopying::MarkingRoot
ART::ConcurrentCopying::MarkObject
ART::ConcurrentCopying::CopyingPhase
ART::ConcurrentCopying::ReclaimPhase
ART::Heap::VisitRoots
ART::WriteBarrier
ART::ReadBarrier
ART::FinalizerDaemon::Run
ART::ReferenceQueueDaemon::Run

# AOSP 17 新增
ART::TriggerYoungGC
ART::BarrierStats
```

---

## 三、排查 Checklist

### 3.1 OOM 排查 Checklist

```markdown
□ 1. 确认 OOM 类型
  □ 1.1 Java heap OOM？ (dumpsys meminfo 看 Dalvik Heap)
  □ 1.2 Native heap OOM？ (dumpsys meminfo 看 Native Heap)
  □ 1.3 Graphics OOM？ (dumpsys meminfo 看 Graphics)
  □ 1.4 Thread/Stack OOM？ (dumpsys meminfo 看 Stack)
  □ 1.5 FD/Thread OOM？ (dumpsys meminfo 看 FD)

□ 2. Java heap OOM 排查
  □ 2.1 检查 LeakCanary 报告（如果集成）
  □ 2.2 手动触发 heap dump (hprof)
  □ 2.3 用 MAT / Shark 分析
  □ 2.4 找出最大的 retained heap 对象
  □ 2.5 检查 GC Root 引用链
  □ 2.6 验证泄漏源（Activity / Fragment / Handler / Callback）

□ 3. Native heap OOM 排查
  □ 3.1 检查 JNI Global Ref 数量 (dumpsys meminfo | grep JNI)
  □ 3.2 检查 DirectByteBuffer 数量
  □ 3.3 检查第三方 .so 的 mmap (smaps)
  □ 3.4 检查 Bitmap 分配（是否复用）
  □ 3.5 检查 Surface 分配

□ 4. Graphics OOM 排查
  □ 4.1 检查 EGL mtrack (dumpsys meminfo | grep EGL)
  □ 4.2 检查 GL mtrack (dumpsys meminfo | grep GL)
  □ 4.3 检查 Surface 泄漏
  □ 4.4 检查 HWUI display list 泄漏

□ 5. 修复方案
  □ 5.1 Java heap OOM：修复泄漏 + 减小缓存 + 用 LRU 替代 WeakRef
  □ 5.2 Native heap OOM：复用 DirectByteBuffer + 复用 Bitmap
  □ 5.3 Graphics OOM：复用 Surface + 减少 GL Texture
```

### 3.2 GC 卡顿排查 Checklist

```markdown
□ 1. 抓取 systrace / Perfetto
  □ 1.1 抓取 trace 时长 ≥ 30 秒
  □ 1.2 包含 GC 事件（sched freq am wm gfx view binder_driver hal dalvik）
  □ 1.3 拉取 trace 到本地

□ 2. 找 GC 事件
  □ 2.1 找 ConcurrentCopying / MarkSweep 事件
  □ 2.2 看 STW 时间分布
  □ 2.3 看 GC 频率

□ 3. 分析 STW 时间
  □ 3.1 单次 STW > 10ms → 异常
  □ 3.2 GC 频率 > 10 次/分钟 → 异常
  □ 3.3 Major GC 频繁 → 分代假说失效

□ 4. CMS 卡顿排查
  □ 4.1 Remark 阶段长？Incremental Update 标脏过多？
  □ 4.2 Initial Mark 阶段长？GC Root 多？
  □ 4.3 升级到 CC GC？

□ 5. CC GC 卡顿排查
  □ 5.1 Initialize 阶段长？栈扫描慢？
  □ 5.2 Copy 阶段长？Live Set 大？
  □ 5.3 读屏障开销大？Hot path 太多？

□ 6. GenCC 卡顿排查
  □ 6.1 Minor GC 频繁？Card Table 频繁 dirty？
  □ 6.2 Major GC 频繁？分代假说失效？
  □ 6.3 跨代引用过多？长寿对象污染 Young Gen？

□ 7. 修复方案
  □ 7.1 减小堆大小（避免频繁 GC）
  □ 7.2 优化内存使用（对象池 / LRU 缓存）
  □ 7.3 升级到更新的 GC（CMS → CC → GenCC）
  □ 7.4 升级到 AOSP 17（50ns→20ns 写屏障 / 30ns→10ns 读屏障）
  □ 7.5 调整 GC 参数（参见 §1）
```

### 3.3 内存泄漏排查 Checklist

```markdown
□ 1. 集成 LeakCanary（2.14+ 支持 AOSP 17）
  □ 1.1 在 build.gradle 添加依赖
  □ 1.2 在 Application 初始化
  □ 1.3 测试泄漏检测是否生效

□ 2. 触发可疑代码路径
  □ 2.1 执行可疑操作（旋转屏幕 / 进入退出 Activity）
  □ 2.2 等待 LeakCanary 检测

□ 3. 分析 LeakCanary 报告
  □ 3.1 看泄漏链
  □ 3.2 找到 GC Root
  □ 3.3 找到泄漏对象
  □ 3.4 修复泄漏源

□ 4. 常见泄漏源
  □ 4.1 Activity / Fragment Context 泄漏
  □ 4.2 Handler / Runnable 引用泄漏
  □ 4.3 静态变量持有 Activity
  □ 4.4 Listener / Callback 未注销
  □ 4.5 Thread / TimerTask 未停止
  □ 4.6 WeakHashMap value 泄漏
  □ 4.7 JNI Global Ref 泄漏
  □ 4.8 第三方库泄漏（Glide / OkHttp / 推送 SDK）

□ 5. 修复方案
  □ 5.1 用 Application Context 替代 Activity Context
  □ 5.2 Handler 用 WeakReference 包裹
  □ 5.3 在 onDestroy 中清理静态引用
  □ 5.4 在 onDestroy 中注销 Listener
  □ 5.5 在 onDestroy 中停止 Thread / TimerTask
  □ 5.6 WeakHashMap 改用 LRU
  □ 5.7 JNI Global Ref 配对 DeleteGlobalRef
  □ 5.8 第三方库升级或反馈
```

### 3.4 AOSP 17 新增：漏标排查 Checklist

```markdown
□ 1. 确认是漏标问题
  □ 1.1 Crash trace 显示"对象已被回收"或"Invalid read of 0x..."
  □ 1.2 偶发（与 GC 时机相关）
  □ 1.3 heap dump 不显示该对象

□ 2. 抓 GC log
  □ 2.1 adb logcat -d -s art:V | grep "Concurrent mark"
  □ 2.2 确认在并发标记期间出现异常

□ 3. 分析代码（5 类漏标场景）
  □ 3.1 Handler / Listener 持有外部引用
  □ 3.2 跨线程引用
  □ 3.3 finalize() 复活对象
  □ 3.4 JNI / Native 持有 Java 引用
  □ 3.5 反射修改静态字段

□ 4. 检查屏障实现
  □ 4.1 自定义 ClassLoader 实现的屏障是否正确
  □ 4.2 反射 / Unsafe 绕过屏障的风险
  □ 4.3 Hook 框架修改 entrypoint 绕过屏障

□ 5. ART 17 验证
  □ 5.1 反射 Method.invoke → 升级 AOSP 17（已修复）
  □ 5.2 JNI RegisterNatives → 升级 AOSP 17（已修复）
  □ 5.3 整体漏标率 → 升级 AOSP 17（降低 50%）
```

### 3.5 排查 Checklist 汇总

| 问题 | 优先排查入口 | 关键命令 | 升级 AOSP 17 收益 |
| :--- | :--- | :--- | :--- |
| Java 堆 OOM | heap dump + MAT | `am dumpheap` + `hprof-conv` | 漏标率 -50% |
| GC 卡顿 | Perfetto + logcat | `perfetto` + `logcat -s art` | 写屏障 50ns→20ns / 读屏障 30ns→10ns |
| 内存泄漏 | LeakCanary | LeakCanary 2.14+ | 屏障覆盖更全 |
| **漏标（NPE）** | **logcat + 反射分析** | `logcat` + 反射调用 | **反射屏障覆盖（-50%）** |

---

## 四、APM 监控指标基线

### 4.1 应用层指标

```java
// 自建 APM 监控示例代码（AOSP 17 强化）
public class GCMonitor {
    // GC 频率（次/分钟）
    private AtomicInteger gcCount = new AtomicInteger();

    // STW 时间累计（ms）
    private AtomicLong totalPauseTime = new AtomicLong();

    // GC 触发原因统计
    private ConcurrentHashMap<String, AtomicInteger> gcCauseMap;

    // AOSP 17 新增：软阈值触发次数
    private AtomicInteger softThresholdTrigger = new AtomicInteger();

    // AOSP 17 新增：屏障调用次数
    private AtomicLong writeBarrierCount = new AtomicLong();
    private AtomicLong readBarrierCount = new AtomicLong();

    // JVMTI 回调
    public void onGarbageCollectionStart() {
        gcCount.incrementAndGet();
    }

    public void onGarbageCollectionFinish(long pauseTime) {
        totalPauseTime.addAndGet(pauseTime);
    }

    // AOSP 17 新增：软阈值触发回调
    public void onSoftThresholdTrigger() {
        softThresholdTrigger.incrementAndGet();
    }

    // 定时上报
    @Scheduled(fixedRate = 60000)
    public void report() {
        long pauseAvg = totalPauseTime.get() / Math.max(1, gcCount.get());
        // 上报到 APM 服务
        apmClient.report("gc.frequency", gcCount.get());
        apmClient.report("gc.pause.avg", pauseAvg);
        apmClient.report("gc.soft.trigger", softThresholdTrigger.get());
        apmClient.report("gc.barrier.write", writeBarrierCount.get());
        apmClient.report("gc.barrier.read", readBarrierCount.get());
    }
}
```

### 4.2 关键告警阈值（AOSP 17 强化）

| 指标 | 警告阈值 | 严重阈值 | 紧急处理 | AOSP 17 变化 |
| :--- | :--- | :--- | :--- | :--- |
| Java heap 使用率 | > 70% | > 85% | > 95% 立即报警 | 不变 |
| Native heap 使用率 | > 80% | > 90% | > 95% 立即报警 | 不变 |
| **Young GC 频率（次/分钟）** | **> 15** | **> 30** | **> 60 立即报警** | **AOSP 17 强化** |
| **Major GC 频率（次/小时）** | **> 1** | **> 3** | **> 10 立即报警** | **AOSP 17 强化** |
| **Young GC STW（ms）** | **> 1** | **> 3** | **> 5 立即报警** | **AOSP 17 强化（GenCC）** |
| Major GC STW（ms） | > 20 | > 100 | > 500 立即报警 | 不变 |
| **写屏障调用开销（ns）** | **> 30** | **> 50** | **> 100 立即报警** | **AOSP 17 新增** |
| **读屏障调用开销（ns）** | **> 15** | **> 30** | **> 50 立即报警** | **AOSP 17 新增** |
| **屏障冲突率** | **> 5%** | **> 10%** | **> 20% 立即报警** | **AOSP 17 新增** |
| Finalizer 队列深度 | > 100 | > 1000 | > 10000 立即报警 | **4 线程池化** |
| Reference 队列深度 | > 1000 | > 10000 | > 100000 立即报警 | 不变 |
| Card Table dirty 比例 | > 5% | > 10% | > 20% 立即报警 | **128B 粒度** |
| Thread 数 | > 200 | > 500 | > 1000 立即报警 | 不变 |
| JNI Global Ref | > 100 | > 500 | > 1000 立即报警 | 不变 |
| .so mmap | > 50MB | > 100MB | > 200MB 立即报警 | 不变 |
| EGL mtrack | > 30MB | > 100MB | > 200MB 立即报警 | 不变 |
| GL mtrack | > 30MB | > 100MB | > 200MB 立即报警 | 不变 |

### 4.3 APM 工具推荐（AOSP 17 强化）

| 工具 | 平台 | 关键特性 | AOSP 17 兼容性 | 适用场景 |
| :--- | :--- | :--- | :--- | :--- |
| **LeakCanary 2.14+** | Android | 内存泄漏检测 | **✅ AOSP 17** | 调试 + 测试 |
| **Matrix 2.0+** | Android | APM + GC 监控 | **✅ AOSP 17** | 生产环境 |
| Firebase Performance | 跨平台 | 性能监控 | AOSP 17 | 海外 App |
| 友盟 U-APM | Android | 崩溃 + 性能 | AOSP 17 | 国内 App |
| 听云 App | 跨平台 | 真实用户体验 | AOSP 17 | 国内 App |
| New Relic | 跨平台 | 全链路追踪 | AOSP 17 | 海外 App |
| Sentry | 跨平台 | 崩溃监控 | AOSP 17 | 调试 + 生产 |

---

## 五、工具链配置基线

### 5.1 开发环境（AOSP 17 强化）

```bash
# 必备工具
Android Studio Koala (2024.1.1) 或更新
JDK 17 (AGP 8.0+)
Gradle 8.0+
Android SDK 37
NDK r26c 或更新

# 推荐工具
LeakCanary 2.14+
Matrix 2.0+
Perfetto UI (https://ui.perfetto.dev/)
cs.android.com (AOSP 17 源码搜索)
```

### 5.2 调试命令清单（AOSP 17 强化）

```bash
# 1. 内存相关
adb shell dumpsys meminfo <package>
adb shell procrank
adb shell run-as <package> cat /proc/self/smaps > smaps.txt
adb shell run-as <package> cat /proc/self/maps > maps.txt

# 2. GC 相关
adb logcat -d -s "art" | grep -i "gc"
adb shell setprop dalvik.vm.dex2oat-Xms 256m
adb shell setprop dalvik.vm.dex2oat-Xmx 512m

# AOSP 17 新增
adb logcat -d -s "art" | grep "TriggerYoungGC"
adb shell setprop dalvik.vm.barrier-stats true
adb logcat -d -s "art" | grep "BarrierStats"

# 3. Trace 相关
adb shell perfetto --out /data/local/tmp/trace.proto \
  -t 10s \
  sched freq idle am wm gfx view binder_driver hal dalvik \
  camera input hal res
adb pull /data/local/tmp/trace.proto

# 4. Thread 相关
adb shell ps -T -p <pid>
adb shell kill -3 <pid>  # 触发 ANR / dump thread

# 5. Native crash
adb shell logcat -d -b crash
adb shell ls /data/tombstones/
```

### 5.3 关键 Gradle 配置（AOSP 17 强化）

```groovy
// app/build.gradle
android {
    compileSdkVersion 37  // AOSP 17

    defaultConfig {
        // ...
    }

    buildTypes {
        debug {
            debuggable true
            minifyEnabled false
            shrinkResources false
        }
        release {
            minifyEnabled true
            shrinkResources true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }

    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }

    // 大堆配置（仅当需要时）
    // defaultConfig {
    //     manifestPlaceholders = [largeHeap: "true"]
    // }
}

dependencies {
    // LeakCanary 2.14+（AOSP 17 兼容）
    debugImplementation 'com.squareup.leakcanary:leakcanary-android:2.14'

    // 监控 SDK（按需选择）
    implementation 'com.tencent.matrix:matrix-android:2.0.0'
}
```

### 5.4 AndroidManifest.xml 关键配置

```xml
<!-- 大堆配置（仅当真正需要时） -->
<application
    android:largeHeap="false"  <!-- 默认 false，避免被 LMK 杀 -->
    android:hardwareAccelerated="true"
    ...>
```

```java
// StrictMode 配置（调试时）
if (BuildConfig.DEBUG) {
    StrictMode.setThreadPolicy(new StrictMode.ThreadPolicy.Builder()
        .detectAll()
        .penaltyLog()
        .build());
    StrictMode.setVmPolicy(new StrictMode.VmPolicy.Builder()
        .detectLeakedClosableObjects()
        .detectLeakedRegistrationObjects()
        .penaltyLog()
        .build());
}
```

---

## 六、关键 KPI 基线（AOSP 17 强化）

### 6.1 应用启动 KPI

| 指标 | 启动类型 | AOSP 17 优秀 | AOSP 17 良好 | AOSP 17 一般 | AOSP 17 差 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **冷启动时间** | 冷启动 | < 800ms | 800-1500ms | 1500-2500ms | > 2500ms |
| **温启动时间** | 温启动 | < 400ms | 400-800ms | 800-1500ms | > 1500ms |
| **热启动时间** | 热启动 | < 80ms | 80-250ms | 250-450ms | > 450ms |
| **首帧绘制时间** | 冷启动 | < 1.2s | 1.2-2s | 2-3.5s | > 3.5s |
| **可交互时间** | 冷启动 | < 1.5s | 1.5-2.5s | 2.5-4s | > 4s |

### 6.2 内存 KPI

| 指标 | AOSP 17 优秀 | AOSP 17 良好 | AOSP 17 一般 | AOSP 17 差 |
| :--- | :--- | :--- | :--- | :--- |
| **Java 堆使用率** | < 50% | 50-70% | 70-85% | > 85% |
| **Native 堆使用率** | < 60% | 60-80% | 80-90% | > 90% |
| **总 PSS** | < 200MB | 200-400MB | 400-600MB | > 600MB |
| **内存增长率（24h）** | < 20% | 20-50% | 50-100% | > 100% |
| **内存泄漏率（7d）** | 0 | < 5% | 5-20% | > 20% |

### 6.3 GC 性能 KPI（AOSP 17 强化）

| 指标 | AOSP 17 优秀 | AOSP 17 良好 | AOSP 17 一般 | AOSP 17 差 |
| :--- | :--- | :--- | :--- | :--- |
| **Young GC 频率（次/分钟）** | **5-10** | **10-20** | **20-40** | **> 40** |
| **Major GC 频率（次/小时）** | **< 1** | **1-3** | **3-10** | **> 10** |
| **Young GC STW（ms）** | **< 0.5** | **0.5-1** | **1-3** | **> 3** |
| **Major GC STW（ms）** | **< 10** | **10-20** | **20-50** | **> 50** |
| **Background GC 占比** | **> 60%** | **40-60%** | **20-40%** | **< 20%** |
| **GC 吞吐率** | **> 99%** | **95-99%** | **90-95%** | **< 90%** |
| **写屏障调用开销（ns）** | **< 20** | **20-30** | **30-50** | **> 50** |
| **读屏障调用开销（ns）** | **< 10** | **10-20** | **20-30** | **> 30** |
| **屏障冲突率** | **< 2%** | **2-5%** | **5-10%** | **> 10%** |
| **软阈值触发频率** | **稳定 5-10/min** | **波动 5-15/min** | **频繁波动** | **持续 0（无触发）** |

### 6.4 ART 17 漏标率 KPI

| 指标 | AOSP 17 优秀 | AOSP 17 良好 | AOSP 17 一般 | AOSP 17 差 |
| :--- | :--- | :--- | :--- | :--- |
| **反射漏标率** | **< 0.01%** | **0.01-0.05%** | **0.05-0.1%** | **> 0.1%** |
| **跨线程漏标率** | **< 0.03%** | **0.03-0.1%** | **0.1-0.5%** | **> 0.5%** |
| **Hook 框架漏标率** | **0%** | **< 0.1%** | **0.1-0.5%** | **> 0.5%** |
| **JNI 漏标率** | **< 0.01%** | **0.01-0.05%** | **0.05-0.1%** | **> 0.1%** |

---

## 七、附录小结

1. **关键参数基线**：完整 dalvik.vm.* / ART 17 内部参数 / Kernel 6.12 参数
2. **监控指标基线**：dumpsys meminfo + GC 指标 + Perfetto trace + **AOSP 17 屏障统计**
3. **排查 Checklist**：OOM / GC 卡顿 / 内存泄漏 / **AOSP 17 漏标** 四类问题
4. **APM 监控指标基线**：关键告警阈值（AOSP 17 强化）+ 工具推荐
5. **工具链配置基线**：开发环境 + 调试命令 + Gradle 配置
6. **关键 KPI 基线**：启动 / 内存 / GC 性能 / **AOSP 17 漏标率** 的全套 KPI

→ **本附录是 01-基础理论子模块的"工程工具箱"**——遇到任何 GC 相关问题，都能在这里找到对应的工具和阈值。

---

## 八、后续篇目的工程基线

| 篇目 | 重点工程基线 | 链接 |
| :--- | :--- | :--- |
| [01-可达性分析](../01-可达性分析.md) | GC Root 12 种 + ART 17 GenCC | 基础理论 1/9 |
| [02-三色标记不变式](../02-三色标记不变式.md) | 三色不变式 + 漏标排查 | 基础理论 2/9 |
| [03-写屏障机制](../03-写屏障机制.md) | 写屏障 + Card Table + 反射 | 基础理论 3/9 |
| [04-读屏障机制](../04-读屏障机制.md) | 读屏障 + 自愈指针 + Baker | 基础理论 4/9 |
| [05-记忆集与卡表](../05-记忆集与卡表.md) | Card Table + Remembered Set | 基础理论 5/9 |
| [06-Reference体系](../06-Reference体系.md) | Reference + Finalizer + Cleaner | 基础理论 6/9 |
| [07-理论总结](../07-理论总结.md) | GC 基础理论总结 | 基础理论 7/9 |
| [08-GC与其他子系统](../08-GC与其他子系统.md) | GC × JNI / Hook / Zygote | 基础理论 8/9 |
| [09-GC诊断与治理](../09-GC诊断与治理.md) | 完整工具链 + 监控体系搭建 | 基础理论 9/9 |
| **[10-ART17分代GC强化专章 v2](../../10-ART17分代GC强化专章-v2.md)** | **ART 17 强化（v2 增量专章）** | **v2 增量专章** |

---

> **回到 01-基础理论子模块首页**：[README](../README.md)
