# Android 文件系统架构深度解析(基于 AOSP 17 + android17-6.18)

> **视角**:架构师视角——讲"Android 怎么管理文件系统",不讲"工程师怎么排查 bug"
>
> **源码基线**:AOSP `android-17.0.0_r1`(API 37,CinnamonBun)+ Kernel `android17-6.18` GKI(主线)+ `android17-6.19`(backport);旧基线 `android14-5.10/5.15` / `android15-6.1/6.6` 作历史对照
>
> **目标读者**:Android 稳定性高级工程师 / 平台架构师 / Framework 工程师
>
> **历史版本**:旧 `FS/` 20 篇(老 v3 模板)+ `FS_Stability/` 草稿(2026-07-24)已全部删除(无备份,git 历史可追溯);本系列从零开始,严格对齐 v6 规范(单版指南,见 `E:\smc-pub\PROMPT-技术系列文章写作指南.md`)
>
> **写作规范**:v6 单版指南(顶部 2-3 行 blockquote + AUTHOR_ONLY 段 2 段 + 校准决策日志 + 反样板 §10 + 26 项质量清单 §4)

---

## 核心立场

> **本课程不是"工具手册"**——讲 `mount` / `df` / `du` / `fsck` 怎么用、`iostat` / `blktrace` 怎么读。
> **本课程是"架构指南"**——讲 Android 作为一个系统,为什么要这样设计文件系统,4 层架构怎么整体协作,20 年演进的逻辑是什么。

读完本课程,你应该能:

1. **画出一张 Android 文件系统的全景图**——5 大管理职责 × 4 层物理架构 × 6 类典型 FS 的二维矩阵
2. **解释每个子系统"为什么这么设计"**——不只知道"是什么",更知道"为什么"
3. **看懂跨层协作**——一次 `open()` 跨 4 层怎么协作,一次 FUSE 死锁跨 3 层怎么传染
4. **预判演进方向**——从 20 年演进史中看出 Google 的设计哲学,从而预判 AOSP 18/19 的 FS 方向

---

## 课程结构:6 阶段 × 25 篇

> **总览**:全景(3)→ VFS 核心机制(5)→ 具体 FS 实现(4)→ Android FS 特色(5)→ 稳定性专题(6)→ 诊断治理与未来(2)

### 阶段 1:全景与设计哲学(3 篇)—— 先建立"从上到下的全景图"

| # | 标题 | 核心问题 |
|---|------|---------|
| 01 | Android FS 分类学:5 大管理职责与全景 | Android 作为系统要做好 FS 必须做哪 5 件事(挂载/寻址/缓冲/安全/限额)?为什么不能由单一层承担? |
| 02 | 一个文件的双重视角:加载与运行的融会贯通 | 一次 `open()` / `read()` 跨 4 层怎么协作?4 层在传递什么信息? |
| 03 | Android FS 演进史:从 ext4 到 FUSE passthrough 的 20 年设计哲学 | 20 年里每个阶段为什么这么设计?演进的"驱动力"是什么?设计哲学从"直接挂载"到"用户态中转"到"内核直通"怎么演化的? |

### 阶段 2:VFS 抽象层核心机制(5 篇)

| # | 标题 | 核心问题 |
|---|------|---------|
| 04 | VFS 核心数据结构:super_block / inode / dentry / file 的设计动机 | 这 4 个结构为什么必须存在?字段为什么这样设计?生命周期怎么协作? |
| 05 | file_operations 多态分发机制(不是 hook) | 多态跟 hook 的本质区别?设置时机?VFS 怎么找到"正确的方法"? |
| 06 | 路径解析与挂载机制:path_lookup / mount namespace / overlay | `path_lookup` 怎么走?mount namespace 怎么隔离?overlay 是怎么叠层的? |
| 07 | 页缓存机制:Page Cache / address_space / 脏页回写 | Page Cache 为什么不是"缓存"那么简单?address_space 字段为什么这样设计?脏页回写的 3 个触发源? |
| 08 | 内存映射文件机制:mmap / 缺页处理 / Android 应用 | mmap 跟 read 的本质区别?缺页中断怎么处理?Android 为什么大量用 mmap(Binder / ashmem / 图形)? |

### 阶段 3:具体文件系统实现(4 篇)

| # | 标题 | 核心问题 |
|---|------|---------|
| 09 | ext4 文件系统架构:磁盘布局 / extent / journaling | ext4 的设计哲学(向后兼容)?extent 怎么替代 block map?journal 怎么保证一致性? |
| 10 | f2fs 文件系统特性:闪存友好 / 日志结构 / GC | f2fs 为什么专为 NAND 设计?日志结构怎么减少写放大?GC 怎么权衡? |
| 11 | erofs 与只读压缩:LZ4 / LZMA / Android system 分区 | erofs 为什么不用 squashfs?怎么做到"挂载即可用"?Android system 怎么选 erofs? |
| 12 | 块设备层与 FS 交互:submit_bio / IO 调度影响 | FS 怎么把请求交给 Block 层?IO 调度器怎么影响 FS 性能? |

### 阶段 4:Android FS 特色(5 篇)

| # | 标题 | 核心问题 |
|---|------|---------|
| 13 | Android 存储分区布局与动态分区:super / system / vendor / data / metadata / APEX | A/B 分区怎么工作?super 分区怎么动态切?APEX 怎么挂载?metadata 为什么独立? |
| 14 | StorageManager + Vold 守护进程链路:从 init.rc 到 Binder 跨进程 | Vold 怎么启动?StorageManager 怎么跨进程调 Vold?MountService 怎么串起来? |
| 15 | Scoped Storage 与文件访问:MediaStore / SAF / DocumentsProvider | Scoped Storage 解决什么隐私问题?3 种访问路径的设计动机? |
| 16 | FUSE 在 Android 中的应用:sdcardfs 迁移到 FUSE passthrough | sdcardfs 为什么不维护了?FUSE passthrough 怎么直通了?用户态 daemon 的角色? |
| 17 | Multi-user 存储隔离与 AppOps 配额 | Multi-user 怎么隔离存储?AppOps 怎么限制应用 IO?配额耗尽怎么治理? |

### 阶段 5:稳定性专题(6 篇)——本课程区别于纯机制课程的核心价值

| # | 标题 | 核心问题 |
|---|------|---------|
| 18 | FUSE 死锁全景:4 类锁等待链与用户态 daemon 状态机 | FUSE 为什么容易死锁?4 类锁等待(内核 / 用户态 / inode / page cache)?怎么检测? |
| 19 | Vold + MountService 跨进程故障模式 | 跨进程链路哪一段最容易断?Vold crash 怎么传播?MountService 锁死怎么治理? |
| 20 | F2FS GC 与 Checkpoint 抖动:f2fs_gc_thread 延迟源 | GC 怎么触发?background GC / foreground GC / victim GC 的差异?Checkpoint 怎么阻塞? |
| 21 | ext4 journal 满与 jbd2 阻塞:transaction 等待 | journal 满怎么触发?jbd2 transaction 怎么等待?线上 case 怎么治理? |
| 22 | FBE 文件级加密启动慢:从 init 到 first I/O 的全链路时间盒 | FBE 怎么加密?为什么启动慢?怎么量化每一段耗时? |
| 23 | 文件描述符 / inode / 配额耗尽:三大资源耗尽的诊断与治理 | 3 类资源耗尽的根因 / 现象 / 监控 / 治理 |

### 阶段 6:诊断治理与未来(2 篇)

| # | 标题 | 核心问题 |
|---|------|---------|
| 24 | FS 稳定性诊断工具链:ftrace + eBPF + drop_caches + StorageStats | 工具组合怎么用?每个工具看什么?case 怎么定位? |
| 25 | FS 治理手册与未来方向:5 件套案例库 + AOSP 18/19 路径(不臆想) | 5 件套案例库(现象 / 分析思路 / 根因 / 修复 / 监控) + 基于 Google 官方公告看未来真实可能的演进方向 |

---

## 课程地图(5 大管理职责 × 4 层物理架构)

```
                  App        FWK(Java)    Kernel(FS)    Hardware
                 ──────────────────────────────────────────────────
  挂载            ○          ★             ★             -
  寻址            ★          ★             ★             -
  缓冲            -          -             ★             ★
  安全            ★          ★             ★             -
  限额            ★          ★             ★             -
```

**矩阵解读**:
- **挂载**:Framework Vold 主导 + Kernel VFS 配合(动态分区 / FUSE)
- **寻址**:4 层协作(App API → Framework Binder → Kernel VFS → Hardware 设备)
- **缓冲**:Kernel Page Cache 主导 + Hardware 设备缓存(ufs WriteBooster)
- **安全**:4 层协作(Framework 权限 + Framework FBE 加密 + Kernel SELinux + Hardware TEE)
- **限额**:3 层协作(Framework AppOps 配额 + Kernel cgroup v2 blkio + Kernel inode 配额)

---

## 跟 IO 11 篇 / Memory 15 篇的镜像分工

| 主题 | IO 11 篇(Kernel IO 视角) | Memory 15 篇(架构师视角) | 本课程 25 篇(架构师视角) |
|------|----------|----------|----------|
| 进程 page cache | 05 IO↔MM 桥接 | 07 LRU/MGLRU 深入 | **07 Page Cache 核心机制** |
| mmap | 07 execve 路径 | 05 VMA 深入 | **08 mmap 机制** |
| ext4 | 不涉及 | 不涉及 | **09 ext4 架构** |
| f2fs | 09 设备性能 简提 | 不涉及 | **10 f2fs 特性** + **20 GC 抖动** |
| erofs | 不涉及 | 不涉及 | **11 erofs** |
| Block 层交互 | 03 Block 核心机制 | 不涉及 | **12 FS↔Block 交互** |
| FUSE 死锁 | 08 FUSE 视角 简提 | 不涉及 | **16 FUSE 机制** + **18 FUSE 死锁** |
| Vold 链路 | 不涉及 | 不涉及 | **14 Vold+StorageManager** + **19 Vold 故障** |
| FBE 加密 | 不涉及 | 不涉及 | **22 FBE 启动慢** |
| 冷启动 FS 缺页 | 07 简提 | 不涉及 | **23 三大资源耗尽** |
| 诊断工具 | 10 风险全景 + 11 eBPF | 10 内存账本 | **24 FS 工具链** |

> **判断标准**:
> - 读完想去看 `fs/` / `mm/filemap.c` / `block/` → **本课程**
> - 读完想去看 `kernel/sched/` / `fs/fuse/` / `io_uring` → **IO 系列**
> - 读完想去看 `art/runtime/gc/heap.cc` / `lmkd/` → **Memory 系列**

---

## 强依赖表(避免与 IO/Memory 重复)

| 本课程篇 | 强依赖 | 备注 |
|---------|--------|------|
| 01 FS 分类学 | 无 | 全局观首篇,独立 |
| 02 双重视角 | 无 | 独立 |
| 03 演进史 | 无 | 独立 |
| 04 VFS 数据结构 | 02 | |
| 05 file_operations 多态 | 04 | |
| 06 路径解析与挂载 | 04 | |
| 07 Page Cache | 04 + [Memory 07 LRU/MGLRU](../Memory_Management/07-内存回收子系统.md) | 不重复 LRU 算法,本篇专注 FS↔PageCache 交互 |
| 08 mmap | 04 + [Memory 05 VMA](../Memory_Management/05-进程虚拟地址子系统.md) | 不重复 VMA 设计,本篇专注 mmap 的 FS 视角 |
| 09 ext4 | 04-06 | |
| 10 f2fs | 04-06 | |
| 11 erofs | 04-06 | |
| 12 FS↔Block | 04-06 + [IO 03 Block 核心机制](../IO/03-Block层核心机制：bio-request-plug-merge-throttle.md) | 不重复 Block 内部,本篇专注 FS→Block 接口 |
| 13 动态分区 | 02 | |
| 14 Vold+StorageManager | 13 | |
| 15 Scoped Storage | 14 + 17 | |
| 16 FUSE | 04-06 + [IO 08 FUSE 视角](../IO/08-Android存储栈：从FUSE、sdcardfs、StorageManager到块设备.md) | 不重复 FUSE Kernel 模块,本篇专注 Android 演化 |
| 17 Multi-user | 14 + [Process 13 进程管理](../Process/README.md) | |
| 18 FUSE 死锁 | 16 | |
| 19 Vold 故障 | 14 | |
| 20 F2FS GC | 10 | |
| 21 ext4 journal | 09 | |
| 22 FBE | 14 | |
| 23 三大资源耗尽 | 14 + 17 + [IO 06 D 状态](../IO/06-IO与进程的深度耦合：D状态、iowait、IO-hang、进程阻塞.md) | |
| 24 工具链 | 18-23 + [IO 11 eBPF](../IO/11-eBPF在IO性能分析中的实战：从bpftrace到Android落地.md) | |
| 25 治理 + 未来 | 全部 | 收官 |

---

## 写作规范 v6 适配(本系列做法)

| 规范项 | 做法 |
|--------|------|
| 顶部 blockquote | 2-3 行(基线 + 角色 + 强依赖),不放承接自/衔接去(放 AUTHOR_ONLY 段) |
| AUTHOR_ONLY 段 | 2 段(本篇定位 3 行 + 校准决策日志 3 轮空表),~10 行 |
| 校准决策日志 | 3 轮预设(结构 / 硬伤 / 锐度),校准后回填 |
| 自检报告 | 文末独立 AUTHOR_ONLY 段(26 项质量清单 + 路径对账) |
| 反样板 | v6 §10 7 类元叙述 + §5 12 条反例必扫 |
| 公开站剥离 | mkdocs hook 用正则 `AUTHOR_ONLY:START/END` 整段剥 |
| 案例标注 | "典型模式" 或 "真实案例(来源:...)" 必标 |
| 量化 | 附录 C 量化自检表覆盖全文所有数量级,禁"通常/大约" |

---

## 跨系列引用约定

| 引用类型 | 格式 | 示例 |
|---------|------|------|
| 本系列其他篇 | `[NN-标题](NN-标题.md)` | `[07-页缓存机制](07-页缓存机制详解.md)` |
| IO 系列 | `[IO NN-标题](../IO/NN-标题.md)` + 1 句概述结论 | `[IO 03 Block 核心机制](../IO/03-Block层核心机制：bio-request-plug-merge-throttle.md)` |
| Memory 系列 | `[Memory NN-标题](../Memory_Management/NN-标题.md)` | `[Memory 07 LRU/MGLRU](../Memory_Management/07-内存回收子系统.md)` |
| Process 系列 | `[Process NN-标题](../Process/NN-标题.md)` | `[Process 13 进程管理](../Process/README.md)` |

**统一使用全角冒号(：)U+FF1A**(项目惯例)

---

## 执行计划(2026-07-27 启动)

1. **第 0 阶段**(已完成):25 篇大纲 + 跨系列引用 + 强依赖表 ✅
2. **第 1 阶段**(已完成):删除旧 `FS/` 24 文件 + 旧 `FS_Stability/` 1 文件 = 共 25 文件 ✅
3. **第 2 阶段**(本阶段):创建新 `FileSystem/` 目录 + 新 README ✅
4. **第 3 阶段**:写 01(全局观,系列首篇,无强依赖,单飞)→ 校准 → commit
5. **第 4 阶段**:写 02-03(全景续 + 演进史)
6. **第 5 阶段**:写 04-08(VFS 核心机制 5 篇)
7. **第 6 阶段**:写 09-12(具体 FS 实现 4 篇)
8. **第 7 阶段**:写 13-17(Android FS 特色 5 篇)
9. **第 8 阶段**:写 18-23(稳定性专题 6 篇)
10. **第 9 阶段**:写 24-25(诊断治理与未来 2 篇)
11. **第 10 阶段**:跑 v6 §10 grep 自检 + 公开站剥离验证 + commit + 推送

**预计工时**:25 篇 × 30-60 分钟/篇 = 12-25 小时(子线程并发 + 主线程校准);加上 README 校准与剥离验证,总计 15-30 小时(2-4 周)

---

## 系列总字数(逐步更新)

| 阶段 | 进度 | 篇数 | commit |
|------|------|------|--------|
| 阶段 0 大纲 | ✅ 完成 | - | (本次) |
| 阶段 1 删除旧篇 | ✅ 完成 | -25 文件 | (本次) |
| 阶段 2 新 README | ✅ 完成 | +1 README | (本次) |
| 阶段 3 全局观 01 | ⏳ 进行中 | +1 | - |
| 阶段 4 全景续 02-03 | ⏸ 待启动 | 2 | - |
| 阶段 5 VFS 核心机制 04-08 | ⏸ 待启动 | 5 | - |
| 阶段 6 具体 FS 09-12 | ⏸ 待启动 | 4 | - |
| 阶段 7 Android 特色 13-17 | ⏸ 待启动 | 5 | - |
| 阶段 8 稳定性专题 18-23 | ⏸ 待启动 | 6 | - |
| 阶段 9 诊断治理 24-25 | ⏸ 待启动 | 2 | - |
| 阶段 10 校准+剥离 | ⏸ 待启动 | - | - |
| **总进度** | **2/25 篇(8%)** | - | - |

---

**README v1 · 2026-07-27 · Mavis**
**下次更新**:01 写完校准后,转 v2
