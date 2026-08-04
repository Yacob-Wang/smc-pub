---
书卷: 卷 2　系统启动
章: 第 6 章　Bootloader 到 Kernel
节: 本章大纲（6 节）
主旨: 讲清从硬件上电到 Linux Kernel 接管的全过程——稳定性问题的"第一公里"，所有 boot loop 调查都从这里开始
目标读者: 稳定性工程师（初级）/ OEM BSP 工程师 / 启动性能优化工程师
前置章节: 第 1 章 Android 系统全景、第 4 章 Linux Kernel 基础（Android 视角）
工程基线: AOSP 17.0.0_r1 + Linux 6.18 GKI + Qualcomm SM8550 / MTK 天玑 9200 / Pixel 7/8
源码定位:
  - bootable/bootloader/edk2/  (Android Bootloader / ABL)
  - bootable/bootloader/lk/  (Little Kernel / LK，高通早期)
  - arch/arm64/kernel/head.S  (ARM64 内核入口)
  - init/main.c  (start_kernel)
  - include/linux/init.h  (__init / __setup 宏)
  - drivers/of/fdt.c  (设备树展开)
验证方式: pstore last_kmsg + serial console log + dmesg + ramoops + ab_partition
状态: 🚧 撰写中（6.1–6.6 已落地；综合稿 A02 仍作前置素材）
字数: 已有书章正文（见 6.1–6.6）
素材: A02-Bootloader：LK体系分析与AOSP迁移.md（综合稿，勿当读者主入口）
---

# 第 6 章　Bootloader 到 Kernel

> **章定位**：启动链路第一阶段——硬件怎么移交控制权给 Kernel。本章是 boot loop 调查的"第一公里"。

## 6.1 Bootloader 类型：LK / ABL / U-Boot

**核心子问题**：
1. 三大 Bootloader 体系的演进与现状——为什么 AOSP 现在主推 ABL（基于 edk2）？
2. LK（Little Kernel）的 5 个关键特性：极小体积（~200KB）、单线程、ARM-first、 Qualcomm 历史选择
3. ABL 的 5 大组件：UEFI 协议栈 / ABL 命令处理 / AVB 校验 / 设备树加载 / Linux 启动协议
4. U-Boot 在 ARM 嵌入式市场的地位（MTK / 三星 Exynos / 瑞芯微等）
5. 同一颗 SoC 上不同阶段的 Bootloader 角色分工（PBL / XBL / ABL / Kernel）

**关键产出**：
- 三大 Bootloader 横向对比表（启动时间 / 体积 / 维护方 / 调试能力 / AVB 支持）
- 当前主流机型的 Bootloader 矩阵（Pixel / Samsung / 小米 / OPPO / vivo / 华为）

**稳定性焦点**：
- 启动失败时的 fallback 链
- AVB 校验失败 → boot loop 的根因
- Bootloader 升级失败 → 变砖的恢复路径

## 6.2 Bootloader 启动流程：PBL → ABL → Kernel

**核心子问题**：
1. PBL（Primary Boot Loader）的固化位置与不可升级性（ROM code）
2. ABL 的多阶段加载：XBL → XBL_CFG → XBL_RAMDUMP → ABL
3. ABL → Kernel 的交接协议：Linux ARM64 boot protocol（x0/x1/x2/x3 寄存器约定）
4. 设备树（DTB）的加载时机与校验
5. 启动 log 抓取路径：PBL log → ABL log → Kernel dmesg → console log → pstore

**关键产出**：
- 时序图：上电 → PBL → ABL 各阶段 → Kernel start_kernel
- 每阶段的 log 抓取命令与存放路径
- Kernel 接收的 4 个核心参数：x0=FDT 地址、x1=机器号、x2=atags、x3=0

**稳定性焦点**：
- DTB 损坏 → Kernel 启动崩溃
- cmdline 错误 → Kernel 启动后行为异常
- ABL 升级时掉电 → boot failure 的恢复

## 6.3 Kernel 启动入口：head.S / start_kernel

**核心子问题**：
1. ARM64 的 head.S 路径：`arch/arm64/kernel/head.S` → `__primary_switched` → `start_kernel`
2. start_kernel 的 30+ 调用顺序：`lockdep_init` → `boot_cpu_init` → `setup_arch` → `...` → `rest_init`
3. `setup_arch` 内部的硬件探测：CPU 特性 / 内存布局 / 设备树解析
4. `setup_command_line` 与 `parse_args`：从 DTB chosen node 提取 cmdline
5. 早期控制台：`earlycon` / `earlyprintk` 在串口上的 printk 早于 console_init

**关键产出**：
- start_kernel 关键调用栈（Mermaid 时序图）
- 5 个常见 boot hang 点：console_init / calibrate_delay / page_alloc_init / scheduler_init / irq_init
- 内核编译选项 `CONFIG_*` 决定行为的关键开关（DEBUG_KERNEL / LOCKDEP / SCHED_DEBUG）

**稳定性焦点**：
- start_kernel hang → watchdog 不复位的最早期死锁
- `calibrate_delay` 失败 → 启动卡在"Calibrating delay loop..."
- console_init 失败 → 看不到 dmesg 的盲启动

## 6.4 早期初始化：setup_arch / sched_init / page_alloc

**核心子问题**：
1. `setup_arch` → `setup_machine_fdt` → `of_flat_dt_match_machine` 的设备树匹配逻辑
2. `sched_init` 的 runqueue / task_struct 初始化（idle 进程创建）
3. `page_alloc_init` → `bootmem` → `memblock` 的内存分配早期路径
4. `trap_init` / `early_irq_init` / `init_IRQ` 的中断子系统启动
5. `time_init` / `tick_init` / `timekeeping_init` 的时间子系统

**关键产出**：
- ARM64 Linux 6.18 的 `setup_arch` 调用栈（30 个关键函数）
- `memblock` 与 `bootmem` 的差异（前者是后者的现代替代）
- early 页表建立：`__create_page_tables` 的 3 级页表配置

**稳定性焦点**：
- 内存探测失败 → Kernel panic at start_kernel（"Bad page state"）
- 中断未初始化完就响应 → early_irq 失败
- 调度器未就绪就 schedule → NULL pointer

## 6.5 Kernel cmdline 与 dtb：设备树 + 内核参数

**核心子问题**：
1. Kernel cmdline 的 4 个来源：DTB chosen node / bootloader 注入 / CONFIG_CMDLINE / atags
2. cmdline 关键参数：`androidboot.*` / `console=` / `init=` / `root=` / `androidboot.selinux=`
3. ABL 如何把 cmdline 拼装到 Kernel：x0 (FDT) + 修改 `/chosen` 节点
4. dtb 与 dtbo 的关系：设备树叠加（overlay）机制
5. 设备树节点被覆盖的优先级：bootloader > dtbo > 主 dtb

**关键产出**：
- 完整 cmdline 参数表（androidboot.* 全集 + console/init/root 关键参数）
- dtb/dto 校验流程：ABL 的 AVB 验证 vs Kernel 的 of_check
- 常见 cmdline 注入：调试开关 / perfetto 启动 / kasan / kmemleak

**稳定性焦点**：
- 错误 cmdline → 启动后 init 跑错 / SELinux 模式错 / log 抓不到
- dtb 损坏 → 设备树解析失败 → Kernel panic
- 厂商私参导致兼容性问题（如某 OEM 的 `androidboot.xx=` 未兼容）

## 6.6 启动失败案例：Kernel panic / boot loop

**核心子问题**：
1. Kernel panic 的 3 大类型：硬件探测失败 / 资源不足 / 致命异常
2. boot loop 的判定：PBL 阶段 / ABL 阶段 / Kernel early / Kernel late
3. last_kmsg 抓取机制：pstore → ramoops → /proc/last_kmsg
4. dump 抓取路径：`sysrq` → `magic sysrq` → `kexec` → `ramdump`
5. 实战案例：Pixel 7 LK 阶段 boot loop（AVB 失败）/ 高通 SM8550 Kernel panic（dtb 损坏）

**关键产出**：
- 5 类 boot failure 现场清单 + 调查 SOP
- last_kmsg 的 5 个解析步骤
- ramdump 抓取工具：`ramdump_parser.py` / QCA dump 工具链
- 实战案例库：3-5 个真实案例（脱敏）

**稳定性焦点**：
- 远程抓 last_kmsg 的方案（pstore + dropbox）
- boot loop 现场如何提权
- ramdump 的合规问题（用户数据擦除）

## 本章小结

Kernel 启动阶段出问题 = boot loop，调查工具是 last_kmsg / pstore。
启动链路最关键的不是 Kernel 本身，而是 ABL 阶段的 cmdline 注入 + DTB 校验 + AVB 验证。

稳定性工程师必须能：
1. 区分 PBL / ABL / Kernel early / Kernel late 4 个阶段的失败
2. 从 last_kmsg 倒推 Kernel hang 位置
3. 解读 ABL 输出的设备树与 cmdline
4. 抓 ramdump 分析 Kernel panic 现场

## 本章素材

- 书章正文：`6.1`–`6.6`（现行读者入口）
- 综合稿：`A02-Bootloader：LK体系分析与AOSP迁移.md`（拆章前置素材，已吸收进 6.x）
- 源码 / 文档：AOSP `bootable/bootloader/`、Qualcomm/MTK 公开文档、source.android.com bootloader 文档

## 参考资料

- AOSP 源码：`bootable/bootloader/edk2/`, `arch/arm64/kernel/head.S`, `init/main.c`
- Linux 6.18 GKI：`Documentation/admin-guide/boot-options.rst`
- AOSP 启动文档：https://source.android.com/docs/core/architecture/bootloader
- ARM64 Boot Protocol：https://www.kernel.org/doc/Documentation/arm64/booting.txt
- 内核调试：`Documentation/admin-guide/sysrq.rst`, `Documentation/admin-guide/kdump/kdump.rst`

---

**状态**：🚧 撰写中（6.1–6.6 已落地）
**生成**：build_book_skeleton.py + 第 6 章写作大纲
**更新**：2026-08-04（清理过期「0 篇章 / B 阶段迁移」元数据）
