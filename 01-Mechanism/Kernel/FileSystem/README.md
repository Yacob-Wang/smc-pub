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

1. **画出一张 Android 文件系统的全景图**——12 类 FS × 4 层物理架构 × 5 大管理职责的三维矩阵
2. **看懂 Android 设备每个分区为什么用这种 FS**——erofs 在 /system、f2fs 在 /data、FUSE 在 /storage,**不是**单纯的"用 ext4"
3. **知道 Android 文件树每个挂载点的 FS 类型**——`/proc` 是 procfs、`/sys` 是 sysfs、`/dev/ashmem` 是 ashmem
4. **解释每个子系统"为什么这么设计"**——不只知道"是什么",更知道"为什么"
5. **看懂跨层协作**——一次 `open()` 跨 4 层怎么协作,一次 FUSE 死锁跨 3 层怎么传染
6. **预判演进方向**——从 20 年演进史中看出 Google 的设计哲学,从而预判 AOSP 18/19 的 FS 方向

---

## 课程结构:7 阶段 × 25 篇

> **总览**:事实基础(4)→ 机制全景(2)→ VFS 核心机制(5)→ 具体 FS 实现(4)→ Android FS 特色(4)→ 稳定性专题(5)→ 诊断治理与未来(1)

### 阶段 1:事实基础(4 篇)—— 先回答"FS 是什么 / Android 用哪些 / 文件树长啥样"

| # | 标题 | 核心问题 |
|---|------|---------|
| 01 | [文件系统是什么 + 12 类类型](01-文件系统是什么+12%20类类型.md) | FS 是什么抽象?Linux/Android 涉及 12 类 FS,分别是哪些?为什么需要这么多? |
| 02 | [Android 设备分区与 FS 选型](02-Android%20设备分区与%20FS%20选型.md) | /system 用 erofs、/data 用 f2fs、/storage 用 FUSE——为什么这么选?选错会怎样? |
| 03 | [Android 文件树全貌:从 / 到 /storage 的完整挂载点表](03-Android%20文件树全貌：从%20%20到%20storage%20的完整挂载点表.md) | Android 文件树长啥样?每个挂载点用什么 FS?每个目录是做什么的? |
| 04 | [5 大管理职责 × 4 层物理架构矩阵](04-5%20大管理职责%20×%204%20层物理架构矩阵.md) | 挂载/寻址/缓冲/安全/限额 5 大职责在 4 层之间怎么分工? |

### 阶段 2:机制全景(2 篇)

| # | 标题 | 核心问题 |
|---|------|---------|
| 05 | [一个文件的双重视角:open/read 时序走查](05-一个文件的双重视角：open,read%20时序走查.md) | 一次 `open()` / `read()` 跨 4 层怎么协作?4 层在传递什么信息? |
| 06 | [Android FS 演进史:从 ext4 到 FUSE passthrough 的 20 年设计哲学](06-Android%20FS%20演进史：从%20ext4%20到%20FUSE%20passthrough%20的%2020%20年设计哲学.md) | 20 年里每个阶段为什么这么设计?演进的"驱动力"是什么? |

### 阶段 3:VFS 抽象层核心机制(5 篇)

| # | 标题 | 核心问题 |
|---|------|---------|
| 07 | VFS 核心数据结构:super_block / inode / dentry / file 的设计动机 | 这 4 个结构为什么必须存在?字段为什么这样设计?生命周期怎么协作? |
| 08 | file_operations 多态分发机制(不是 hook) | 多态跟 hook 的本质区别?设置时机?VFS 怎么找到"正确的方法"? |
| 09 | 路径解析与挂载机制:path_lookup / mount namespace / overlay | `path_lookup` 怎么走?mount namespace 怎么隔离?overlay 是怎么叠层的? |
| 10 | 页缓存机制:Page Cache / address_space / 脏页回写 | Page Cache 为什么不是"缓存"那么简单?address_space 字段为什么这样设计?脏页回写的 3 个触发源? |
| 11 | 内存映射文件机制:mmap / 缺页处理 / Android 应用 | mmap 跟 read 的本质区别?缺页中断怎么处理?Android 为什么大量用 mmap(Binder / ashmem / 图形)? |

### 阶段 4:具体文件系统实现(4 篇)

| # | 标题 | 核心问题 |
|---|------|---------|
| 12 | ext4 文件系统架构:磁盘布局 / extent / journaling | ext4 的设计哲学(向后兼容)?extent 怎么替代 block map?journal 怎么保证一致性? |
| 13 | f2fs 文件系统特性:闪存友好 / 日志结构 / GC | f2fs 为什么专为 NAND 设计?日志结构怎么减少写放大?GC 怎么权衡? |
| 14 | erofs 与只读压缩:LZ4 / LZMA / Android system 分区 | erofs 为什么不用 squashfs?怎么做到"挂载即可用"?Android system 怎么选 erofs? |
| 15 | 块设备层与 FS 交互:submit_bio / IO 调度影响 | FS 怎么把请求交给 Block 层?IO 调度器怎么影响 FS 性能? |

### 阶段 5:Android FS 特色(4 篇)

| # | 标题 | 核心问题 |
|---|------|---------|
| 16 | 动态分区 / APEX / metadata:super 分区与可热升级 | A/B 分区怎么工作?super 分区怎么动态切?APEX 怎么挂载?metadata 为什么独立? |
| 17 | StorageManager + Vold 守护进程链路:从 init.rc 到 Binder 跨进程 | Vold 怎么启动?StorageManager 怎么跨进程调 Vold?MountService 怎么串起来? |
| 18 | Scoped Storage 与文件访问:MediaStore / SAF / DocumentsProvider | Scoped Storage 解决什么隐私问题?3 种访问路径的设计动机? |
| 19 | FUSE 在 Android 中的应用:sdcardfs 迁移到 FUSE passthrough | sdcardfs 为什么不维护了?FUSE passthrough 怎么直通了?用户态 daemon 的角色? |

### 阶段 6:稳定性专题(5 篇)——本课程区别于纯机制课程的核心价值

| # | 标题 | 核心问题 |
|---|------|---------|
| 20 | FUSE 死锁全景:4 类锁等待链与用户态 daemon 状态机 | FUSE 为什么容易死锁?4 类锁等待(内核 / 用户态 / inode / page cache)?怎么检测? |
| 21 | Vold + MountService 跨进程故障模式 | 跨进程链路哪一段最容易断?Vold crash 怎么传播?MountService 锁死怎么治理? |
| 22 | F2FS GC 与 Checkpoint 抖动:f2fs_gc_thread 延迟源 | GC 怎么触发?background GC / foreground GC / victim GC 的差异?Checkpoint 怎么阻塞? |
| 23 | ext4 journal 满与 jbd2 阻塞:transaction 等待 | journal 满怎么触发?jbd2 transaction 怎么等待?线上 case 怎么治理? |
| 24 | FBE 加密启动慢 + 三大资源耗尽(FD/inode/配额) | FBE 怎么加密?为什么启动慢?fd/inode/配额耗尽怎么诊断与治理? |

### 阶段 7:诊断治理与未来(1 篇)——收官

| # | 标题 | 核心问题 |
|---|------|---------|
| 25 | FS 稳定性诊断工具链 + 5 件套案例库 + AOSP 18/19 路径(不臆想) | 工具组合怎么用?5 件套案例库(现象/分析思路/根因/修复/监控) + 基于 Google 官方公告看未来真实可能的演进方向 |

---

## 课程地图(12 类 FS × 4 层物理架构)

```
              App        FWK(Java)    Kernel(FS)    Hardware
             ──────────────────────────────────────────────────
  块 FS       -          -             ★(ext4/f2fs/erofs)  ★
  虚拟 FS     -          ○             ★(proc/sys/tmp/dev)  -
  用户态 FS   ○          ★             ★(FUSE 内核)        -
  设备 FS     -          -             ★(ashmem/binder)    -
  控制 FS     -          -             ★(cgroup/configfs)  -
  容器 FS     -          ★             ★(APEX)             -
```

**矩阵解读**:
- **块 FS**:Kernel VFS 主导,直接落 Hardware 块设备
- **虚拟 FS**:Kernel 提供,Framework 部分使用(/config 等)
- **用户态 FS**:Framework 主导(daemon)+ Kernel FUSE 内核模块
- **设备 FS**:Kernel 字符设备(ashmem/binder),不是真正 FS
- **控制 FS**:Kernel 资源控制(cgroup v2)
- **容器 FS**:Framework APEX 主导 + Kernel 支持

---

## 跟 IO 11 篇 / Memory 15 篇的镜像分工

| 主题 | IO 11 篇 | Memory 15 篇 | 本课程 25 篇 |
|------|----------|----------|----------|
| 进程 page cache | 05 IO↔MM | 07 LRU/MGLRU | **10 Page Cache** |
| mmap | 07 execve | 05 VMA | **11 mmap 机制** |
| ext4 | 不涉及 | 不涉及 | **12 ext4 架构** |
| f2fs | 09 简提 | 不涉及 | **13 f2fs 特性** + **22 GC 抖动** |
| erofs | 不涉及 | 不涉及 | **14 erofs** |
| Block 层交互 | 03 Block | 不涉及 | **15 FS↔Block** |
| FUSE 死锁 | 08 简提 | 不涉及 | **19 FUSE** + **20 FUSE 死锁** |
| Vold 链路 | 不涉及 | 不涉及 | **17 Vold** + **21 Vold 故障** |
| FBE 加密 | 不涉及 | 不涉及 | **24 FBE 启动慢** |
| 诊断工具 | 10/11 eBPF | 10 内存账本 | **25 FS 工具链** |

> **判断标准**:
> - 读完想去看 `fs/` / `mm/filemap.c` / `block/` → **本课程**
> - 读完想去看 `kernel/sched/` / `fs/fuse/` / `io_uring` → **IO 系列**
> - 读完想去看 `art/runtime/gc/heap.cc` / `lmkd/` → **Memory 系列**

---

## 强依赖表(避免与 IO/Memory 重复)

| 本课程篇 | 强依赖 | 备注 |
|---------|--------|------|
| 01 FS 概念 + 12 类 | 无 | 全局观首篇,独立 |
| 02 Android 选型 | 01 | |
| 03 Android 文件树 | 02 | |
| 04 5 大职责 × 4 层 | 01-03 | |
| 05 双重视角 | 04 | |
| 06 演进史 | 04 | |
| 07 VFS 数据结构 | 04 | |
| 08 file_operations 多态 | 07 | |
| 09 路径解析与挂载 | 07 | |
| 10 Page Cache | 07 + [Memory 07 LRU/MGLRU](../Memory_Management/07-内存回收子系统.md) | 不重复 LRU 算法,本篇专注 FS↔PageCache 交互 |
| 11 mmap | 07 + [Memory 05 VMA](../Memory_Management/05-进程虚拟地址子系统.md) | 不重复 VMA 设计,本篇专注 mmap 的 FS 视角 |
| 12 ext4 | 07-09 | |
| 13 f2fs | 07-09 | |
| 14 erofs | 07-09 | |
| 15 FS↔Block | 07-09 + [IO 03 Block 核心机制](../IO/03-Block层核心机制：bio-request-plug-merge-throttle.md) | |
| 16 动态分区 | 02 + 03 | |
| 17 Vold+StorageManager | 16 | |
| 18 Scoped Storage | 17 | |
| 19 FUSE | 09 + [IO 08 FUSE 视角](../IO/08-Android存储栈：从FUSE、sdcardfs、StorageManager到块设备.md) | |
| 20 FUSE 死锁 | 19 | |
| 21 Vold 故障 | 17 | |
| 22 F2FS GC | 13 | |
| 23 ext4 journal | 12 | |
| 24 FBE + 资源耗尽 | 17 + [IO 06 D 状态](../IO/06-IO与进程的深度耦合：D状态、iowait、IO-hang、进程阻塞.md) | |
| 25 工具链 + 治理 | 全部 + [IO 11 eBPF](../IO/11-eBPF在IO性能分析中的实战：从bpftrace到Android落地.md) | 收官 |

---

## 写作规范 v6 适配

| 规范项 | 做法 |
|--------|------|
| 顶部 blockquote | 2-3 行(基线 + 角色 + 强依赖) |
| AUTHOR_ONLY 段 | 2 段(本篇定位 + 校准决策日志),~10 行 |
| 校准决策日志 | 3 轮预设(结构 / 硬伤 / 锐度),校准后回填 |
| 自检报告 | 文末独立 AUTHOR_ONLY 段(26 项质量清单 + 路径对账) |
| 反样板 | v6 §10 7 类元叙述 + §5 12 条反例必扫 |
| 公开站剥离 | mkdocs hook 用正则 `AUTHOR_ONLY:START/END` 整段剥 |
| 案例标注 | "典型模式" 或 "真实案例(来源:...)" 必标 |
| 量化 | 附录 C 量化自检表覆盖全文所有数量级,禁"通常/大约" |

---

## 跨系列引用约定

| 引用类型 | 格式 |
|---------|------|
| 本系列其他篇 | `[NN-标题](NN-标题.md)` |
| IO 系列 | `[IO NN-标题](../IO/NN-标题.md)` |
| Memory 系列 | `[Memory NN-标题](../Memory_Management/NN-标题.md)` |
| Process 系列 | `[Process NN-标题](../Process/NN-标题.md)` |

**统一使用全角冒号(：)U+FF1A**(项目惯例)

---

## 执行计划(2026-07-27 启动 · v2 重设计)

1. **第 0 阶段**(已完成):25 篇大纲 v2 审核通过 ✅
2. **第 1 阶段**(已完成):删除旧 `FS/` 24 文件 + 旧 `FS_Stability/` 1 文件 ✅
3. **第 2 阶段**(已完成):创建新 `FileSystem/` 目录 + 新 README v1 ✅
4. **第 3 阶段**:写 01(FS 是什么 + 12 类类型)→ 校准 → commit
5. **第 4 阶段**:写 02-04(Android 选型 + 文件树 + 5 大职责)
6. **第 5 阶段**:写 05-06(双重视角 + 演进史)
7. **第 6 阶段**:写 07-11(VFS 核心机制 5 篇)
8. **第 7 阶段**:写 12-15(具体 FS 实现 4 篇)
9. **第 8 阶段**:写 16-19(Android FS 特色 4 篇)
10. **第 9 阶段**:写 20-24(稳定性专题 5 篇)
11. **第 10 阶段**:写 25(诊断治理与未来 1 篇)
12. **第 11 阶段**:跑 v6 §10 grep 自检 + 公开站剥离验证 + commit + 推送

**预计工时**:25 篇 × 30-60 分钟/篇 = 12-25 小时(子线程并发 + 主线程校准);加上 README 校准与剥离验证,总计 15-30 小时(2-4 周)

---

## 系列总字数(逐步更新)

| 阶段 | 进度 | 篇数 | commit |
|------|------|------|--------|
| 阶段 0 大纲 v2 | ✅ 完成 | - | (本次) |
| 阶段 1 删除旧篇 | ✅ 完成 | -25 文件 | `5b69160` |
| 阶段 2 新 README v1 | ✅ 完成 | +1 README | `9056b0a` |
| 阶段 2.5 README v2 重设计 | ✅ 完成 | README 改 | (本次) |
| 阶段 3 全局观 01(FS 概念) | ⏳ 进行中 | +1 | - |
| 阶段 4 事实续 02-04 | ⏸ 待启动 | 3 | - |
| 阶段 5 机制全景 05-06 | ⏸ 待启动 | 2 | - |
| 阶段 6 VFS 07-11 | ⏸ 待启动 | 5 | - |
| 阶段 7 具体 FS 12-15 | ⏸ 待启动 | 4 | - |
| 阶段 8 Android 特色 16-19 | ⏸ 待启动 | 4 | - |
| 阶段 9 稳定性 20-24 | ⏸ 待启动 | 5 | - |
| 阶段 10 收官 25 | ⏸ 待启动 | 1 | - |
| 阶段 11 校准+剥离 | ⏸ 待启动 | - | - |
| **总进度** | **0/25 篇(0%)** | - | - |

---

**README v2 · 2026-07-27 · Mavis**
**关键变化(v1 → v2)**:阶段 1 从 3 篇扩为 4 篇事实基础(加 FS 概念 + Android 选型 + 文件树全貌);总规模 25 不变;原 01(5 大职责)推到 04
**下次更新**:01 写完校准后,转 v3
