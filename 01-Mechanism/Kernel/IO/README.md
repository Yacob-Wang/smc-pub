# Android IO 子系统深度解析系列(IO)

> **系列定位**:面向 Android 稳定性架构师,从进程 read/write 系统调用出发,沿着 VFS → Page Cache → Block → 调度器 → 设备驱动的完整链路,深度解析 IO 子系统的设计动机、跨系统耦合、稳定性风险。
>
> **源码基线**:AOSP `android-17.0.0_r1`(代号 CinnamonBun,Beta 1 2026-02-13 + 正式版 2026-05~06 推送)
>
> **内核矩阵**:`android17-6.18` GKI(主线)+ `android17-6.19`(backport);旧基线 `android14-5.10/5.15` / `android15-6.1/6.6` 作历史对照
>
> **目标读者**:Android 稳定性框架架构师
>
> **本系列 README 写于**:2026-07-22 IO v3 → v5 全量改造启动时

---

## 系列设计思路

### 1. 为什么写这个系列

Android 稳定性问题(ANR / 卡顿 / 冷启动慢 / IO hang)有相当比例根因在 IO 子系统:

- **冷启动慢**:Page Cache 缺页 + readahead 窗口不足(实测 ShopApp 冷启动 4.5s,92% 是 file-backed 缺页)
- **ANR**:D 状态进程 80%+ 是 IO 阻塞(`TASK_UNINTERRUPTIBLE` 状态)
- **卡顿**:脏页回写 + zRAM swap-out 导致主线程 IO 等待
- **闪退**:FUSE 路径上 StorageManager 异常 + sdcardfs 兼容性问题

稳定性架构师必须**能定位到具体子系统 + 理解根因机制 + 给出治理方案**——这就是本系列的目标。

### 2. 11 篇章节规划

| 阶段 | 篇 | 主题 | 在系列中的角色 | 强依赖 |
|------|-----|------|---------------|--------|
| **总览** | [01](01-IO子系统总览：从进程read、write到磁盘的完整链路.md) | IO 子系统总览:从进程 read/write 到磁盘的完整链路 | 全局观(系列首篇) | 无 |
| **核心机制** | [02](02-IO调度器与多队列架构.md) | IO 调度器与多队列架构 | 核心机制 1(调度子系统) | 01 |
| **核心机制** | [03](03-Block层核心机制：bio-request-plug-merge-throttle.md) | Block 层核心机制:bio/request/plug/merge/throttle | 核心机制 2(Block 子系统) | 01, 02 |
| **核心机制** | [04](04-IO优先级与cgroup-IO控制器.md) | IO 优先级与 cgroup IO 控制器 | 核心机制 3(资源控制) | 02, 03 |
| **横切专题** | [05](05-IO与内存的深度耦合：Page-Cache脏页回写、回收路径、swap-IO.md) | IO 与内存的深度耦合:Page Cache 脏页回写、回收路径、swap IO | 桥接 1(IO ↔ MM) | 01-04 + [Memory 系列](../Memory_Management/README.md) |
| **横切专题** | [06](06-IO与进程的深度耦合：D状态、iowait、IO-hang、进程阻塞.md) | IO 与进程的深度耦合:D 状态、iowait、IO hang、进程阻塞 | 桥接 2(IO ↔ Process) | 01-05 + [Process 系列](../Process/README.md) |
| **横切专题** | [07](07-程序加载与链接的IO路径：从execve到AOT文件mmap.md) | 程序加载与链接的 IO 路径:从 execve 到 AOT 文件 mmap | 桥接 3(IO ↔ PLE) | 01-05 + [Program_Execution 系列](../Program_Execution/README.md) |
| **Android 特色** | [08](08-Android存储栈：从FUSE、sdcardfs、StorageManager到块设备.md) | Android 存储栈:从 FUSE、sdcardfs、StorageManager 到块设备 | Android 特色 1(存储栈) | 01-03, 07 |
| **Android 特色** | [09](09-存储设备与IO性能：UFS、eMMC、NVMe命令队列与延迟特性.md) | 存储设备与 IO 性能:UFS、eMMC、NVMe 命令队列与延迟特性 | Android 特色 2(设备性能) | 02, 03 |
| **风险治理** | [10](10-IO稳定性风险全景与诊断工具链.md) | IO 稳定性风险全景与诊断工具链 | 风险地图 + 诊断 | 01-09 |
| **延伸专题** | [11](11-eBPF在IO性能分析中的实战：从bpftrace到Android落地.md) | eBPF 在 IO 性能分析中的实战:从 bpftrace 到 Android 落地 | 延伸专题(工具升级) | 10 |

### 3. 阅读建议

- **初学者**:按 01 → 11 顺序读,11 篇相互引用形成完整知识网
- **查具体问题**:直接看 10(风险全景)+ 对应主题的桥接文章(05/06/07/08)
- **写工具**:重点看 10 + 11(eBPF)
- **Android 平台工程师**:重点看 08(存储栈)+ 09(设备性能)

### 4. 跨系列引用

| 本系列主题 | 强依赖的其他系列 |
|-----------|----------------|
| 05 IO↔MM | [Memory 系列](../Memory_Management/README.md)(回收 / Page Cache / zRAM) |
| 06 IO↔Process | [Process 系列](../Process/README.md)(CFS / D 状态 / ANR) |
| 07 IO↔PLE | [Program_Execution 系列](../Program_Execution/README.md)(execve / ELF / DEX) |
| 04 IO cgroup | [Process 系列](../Process/README.md) cgroup 子系统 |
| 09 设备性能 | [Memory 系列](../Memory_Management/README.md) IO 设备内存屏障 |

### 5. v3 → v5 全量改造说明(2026-07-22 启动)

| 改造项 | v3 状态 | v5 状态 | 改造方式 |
|--------|---------|---------|---------|
| AUTHOR_ONLY marker 包裹 | 无(5 段前言直接出现在正文) | 用 `<!-- AUTHOR_ONLY:START/END -->` 包裹(5 段前言 + 自检报告) | 主线程 Edit 改造 |
| 跨篇 markdown 链接 | 全角冒号(已沿用) | 全角冒号(无需改) | 无变化 |
| 源码基线 | AOSP 14 + 5.10-6.6 | AOSP 17 + android17-6.18 主 + 5.10-6.6 历史对照 | 顶部 blockquote 升级 |
| 案例基线说明 | 无 | 加"📌 案例基线说明:本案例数据基于 A14 时代实测" | 主线程 Edit |
| 自检报告段 | 无 | 文末加 AUTHOR_ONLY 段(26 项质量清单) | 主线程 Edit |
| 反 AI 自嗨词 | 5 个词 | 20 个词 | 校准时审(部分"通常"合理保留) |
| 跨篇引用命名 | `MM_v2 09-...` | `Memory 09-...` | 跨篇引用统一到 v5 命名 |

### 6. 历史归档(如果未来需要回滚)

- **v1 → v2 归档**:`_archive/IO_v1/`
- **v2 → v3 归档**:`_archive/IO_v2/`
- **v3 现行**:本目录(11 篇)
- **v5 改造**:基于 v3 + marker 化 + 基线升级,不删 v3 内容

---

## 系列总字数

| 篇 | 行数 | 中文字符 | 改造状态 |
|----|------|---------|---------|
| 01 | 1280+ | 7864 | ✅ v5 完成(样板) |
| 02 | 1129 | 待 verify | ⏳ 待改造 |
| 03 | 1506 | 待 verify | ⏳ 待改造 |
| 04 | 1263 | 待 verify | ⏳ 待改造 |
| 05 | 1194 | 待 verify | ⏳ 待改造 |
| 06 | 1129 | 待 verify | ⏳ 待改造 |
| 07 | 1260 | 待 verify | ⏳ 待改造 |
| 08 | 1059 | 待 verify | ⏳ 待改造 |
| 09 | 1019 | 待 verify | ⏳ 待改造 |
| 10 | 1026 | 待 verify | ⏳ 待改造 |
| 11 | 1131 | 待 verify | ⏳ 待改造 |

**总进度**:1/11(9%)
**目标**:2-3 天完成全部 11 篇 v5 改造

---

**README v1 · 2026-07-22 · Mavis**
**下次更新**:v5 改造完成(预计 2026-07-24)
