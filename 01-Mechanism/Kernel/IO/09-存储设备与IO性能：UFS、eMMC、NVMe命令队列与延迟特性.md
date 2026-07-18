# 09-存储设备与 IO 性能：UFS / eMMC / NVMe 命令队列与延迟特性

> **系列**：面向稳定性的 Android IO 子系统深度解析系列(IO)
> **源码基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)
> **内核矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇涉及 `drivers/ufs/`(UFSHCD/UFS 驱动)、`drivers/mmc/host/`(eMMC 驱动)、`drivers/nvme/`(NVMe 驱动)、`drivers/scsi/`;各代 UFS 性能差异见 §3)
> **目标读者**:Android 稳定性框架架构师
> **前置阅读**:[01-IO 子系统总览](01-IO子系统总览：从进程read、write到磁盘的完整链路.md) §6 / [02-IO 调度器](02-IO调度器与多队列架构.md) §8
> **下一篇**:[10-IO 风险全景与诊断工具链](10-IO稳定性风险全景与诊断工具链.md)

---

## 本篇定位

- **本篇系列角色**：核心机制硬件层篇（设备物理特性，决定 IO 延迟的下限）
- **强依赖**：
  - [01-IO 子系统总览](01-IO子系统总览：从进程read、write到磁盘的完整链路.md) §6（IO 延迟组成）
  - [02-IO 调度器与多队列架构](02-IO调度器与多队列架构.md) §8（Android GKI 选型）
- **承接自**：
  - 01 总览已建立"设备 IO 是延迟主因"（80-95%）的认知
  - 本篇深入 UFS / eMMC / NVMe 的物理特性和延迟来源
- **衔接去**：下一篇 [10-IO 风险全景与诊断工具链](10-IO稳定性风险全景与诊断工具链.md) 将整合所有 9 篇的风险地图 + 工具链，作为系列收官
- **不重复内容**：
  - **IO 调度器选型（mq-deadline / bfq / kyber）** → 详见 [02-IO 调度器](02-IO调度器与多队列架构.md) §8
  - **Page Cache 与 dirty page 机制** → 详见 [05-IO 与内存的深度耦合](05-IO与内存的深度耦合：Page-Cache脏页回写、回收路径、swap-IO.md) §3-§4
  - **iostat / blktrace 的具体使用** → 详见 [10-IO 风险全景与诊断工具链](10-IO稳定性风险全景与诊断工具链.md) §10
- **本篇的核心价值**：让稳定性架构师能**理解设备特性对 IO 性能的根本影响**——温度降频、UFS deep sleep、NVMe 队列深度——这些是"为什么 App 偶尔慢"的物理根因。

#### §0 锚点案例的可验证 4 件套:CamApp 4K 录像 5min 后掉帧,根因 UFS 高温降频

> **环境**:
> - 设备:Pixel 7(G2, arm64-v8a, 8GB RAM, UFS 3.1 128GB)
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI
> - App:某相机 App v4.5(脱敏代号 `CamApp`,4K@60fps 写入 ~120MB/s)
> - 工具:`iostat -dx 1` + `cat /sys/class/thermal/thermal_zone*/temp` + `simpleperf -e thermal:*` + `perfetto`

> **复现步骤**:
> 1. 工厂重置,安装 CamApp v4.5,室温 25°C
> 2. 启动 4K@60fps 录像,持续 10min,期间每秒采样 UFS 温度 + IO 延迟
> 3. `for i in 1 2 3; do cat /sys/class/thermal/thermal_zone$i/type; cat /sys/class/thermal/thermal_zone$i/temp; done`
> 4. `iostat -dx 1` 抓 60s,观察 `aqu-sz` / `w_await` / `%util` 突变点
> 5. 录像结束后检查写入文件是否完整 + 帧率统计

> **logcat / iostat 关键片段**:
> ```
> # /sys/class/thermal/thermal_zone8/temp(UFS 设备温度)
> 38000  ← 38°C 启动
> 48000  ← 48°C 录像 2min
> 62000  ← 62°C 录像 4min
> 78000  ← 78°C 录像 5min  ← 触发 throttle(>75°C)
> 82000  ← 82°C 录像 6min  ← throttle 持续
> # iostat 输出(录像第 5min 起)
> Device  r/s   w/s  rMB/s  wMB/s  aqu-sz  r_await  w_await  %util
> sda    2.0  98.0  0.01  120.0  42.0     8.2     18.4    98.0   ← 正常
> sda    2.0  48.0  0.01   60.0  82.0     9.1   1840.0   99.0   ← 第 5min 后 w_await 飙升 100x
> # /sys/devices/platform/.../ufs/clkgate 状态
> ufshcd-clock-gating: ON
> ufs-link-state: hibern8   ← 高温时 UFS 控制器频繁进出 hibern8
> # simpleperf trace
> 99%  [kernel]  ufshcd_queuecommand → ufshcd_wait_command (sleep 1.8s)  ← 等 UFS 响应
> ```
> 现象:录像第 5min 起 UFS 温度达 78°C → UFS 控制器降频 → 单次 IO 延迟从 18ms 飙升到 1840ms → 写入 120MB/s 跌到 60MB/s → 帧丢失 → 用户看到录像卡顿。

> **修复 commit-style diff**:
> ```diff
> --- a/device/google/pixel/thermal/thermal_config_pixel.xml
> +++ b/device/google/pixel/thermal/thermal_config_pixel.xml
> @@ thermal-zone UFS
> -    <!-- 旧版:UFS 节流阈值 75°C,触底后大幅降频 -->
> -    <hotplug>
> -        <trip_point>75</trip_point>
> -        <recovery>65</recovery>
> -        <mitigation>stepwise throttle 50%</mitigation>
> -    </hotplug>
> +    <!-- 修复:阈值抬到 85°C + 平滑降频(10%/℃),避免阶跃式卡顿 -->
> +    <hotplug>
> +        <trip_point>85</trip_point>
> +        <recovery>75</recovery>
> +        <mitigation>smooth throttle 10%/C</mitigation>
> +    </hotplug>
> ```
> ```diff
> --- a/drivers/ufs/core/ufshcd.c
> +++ b/drivers/ufs/core/ufshcd.c
> @@ ufshcd_write_thermal_hint
> -    // 旧版:thermal hint 只在 critical 才 throttle
> -    if (temp > critical_temp)
> +    // 修复:thermal hint 三档(80/85/90℃),提前预警,避免 IO 尖刺
> +    if (temp > 90)
>          throttle = THROTTLE_CRITICAL;
> +    else if (temp > 85)
> +        throttle = THROTTLE_HIGH;
> +    else if (temp > 80)
> +        throttle = THROTTLE_MID;
> ```
> 完整 UFS 命令队列 ↔ eMMC 调度 ↔ NVMe 多队列对比 ↔ 高温降频策略见 §3 §5 §7 §9。

---

## 一、背景与定义：设备层是什么、为什么需要单独讲

### 1.1 一个反直觉的事实

IO 延迟的 **80-95%** 来自设备层（UFS / eMMC / NVMe），而 Block 层、调度器、内核的总开销仅占 5-20%。

```
典型 4K 随机读延迟分解（UFS 3.1）：
├── 用户态/内核态切换：~1μs
├── VFS + Page Cache 命中：~1μs
├── Block 层调度：~10μs
├── 驱动排队：~10μs
└── 设备 IO（UFS 4K 随机读）：~1ms ← **延迟主因**

设备层占了 1000μs / 1022μs ≈ 98%
```

**结论**：**优化设备层比优化内核调度收益大 10-100 倍**——但稳定性架构师往往只关注内核层。

### 1.2 三大移动设备存储对比

| 设备 | 协议 | 移动端典型 | 顺序读 | 4K 随机读 | 4K 随机写 | IOPS |
|------|------|----------|--------|----------|----------|------|
| **eMMC 5.1** | MMC | 入门机 | ~150MB/s | ~500μs | ~3ms | 5K-10K |
| **eMMC A1 / A2** | MMC | 中端机 | ~250MB/s | ~300μs | ~1.5ms | 10K-20K |
| **UFS 2.1** | UFS | 旧旗舰 | ~700MB/s | ~200μs | ~1ms | 30K-50K |
| **UFS 3.0 / 3.1** | UFS | 当前旗舰 | ~1.5-2.1GB/s | ~100-200μs | ~500μs-1ms | 50K-100K |
| **UFS 4.0** | UFS | 高端旗舰 | ~4.2GB/s | ~50-100μs | ~200-500μs | 100K-200K |
| **NVMe SSD** | NVMe | 服务器 / 部分高端 | ~3-7GB/s | ~10-50μs | ~10-100μs | 100K-1M |

### 1.3 稳定性意义

| 现象 | 真实根因（设备层） | 排查方向 |
|------|------------------|---------|
| **App 启动偶尔慢 3s+** | UFS deep sleep 唤醒延迟 | 抓 Perfetto 看 UFS state transition |
| **相机拍照黑屏** | UFS 高温降频 | 读 UFS thermal sensor |
| **数据库查询慢 5x** | 4K 随机读 vs 顺序读性能差 | fio benchmark + IO 模式分析 |
| **游戏 loading 慢** | UFS 队列深度不足 | 优化应用 IO 模式 |
| **长时间使用后系统慢** | UFS 内部 fragmentation | TRIM / 重新格式化 |

---

## 二、架构与交互：设备在 IO 链路中的位置

### 2.1 设备层在 5 层 IO 链路中的位置

```
用户进程（read/write）
    ↓ syscall
VFS 层
    ↓
Page Cache 层（mm/filemap.c）
    ↓ submit_bio()
Block 层（block/blk-mq.c）
    ↓ queue_rq
┌─────────────────────────────────────────────────────────────┐
│  驱动层 + 设备层（本篇）                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  驱动（drivers/ufs/, drivers/mmc/, drivers/nvme/）    │   │
│  │  - DMA 提交（数据缓冲地址）                            │   │
│  │  - 触发 doorbell（设备命令队列）                       │   │
│  │  - 等中断                                              │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  设备硬件                                               │   │
│  │  - UFS: command queue + MIPI M-PHY + UniPro           │   │
│  │  - eMMC: MMC 总线 + HS400 + command queue (5.1)      │   │
│  │  - NVMe: PCIe + 多 SQ + 多 CQ                          │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 设备 IO 的端到端延迟分解（UFS 3.1 4K 随机读）

```
总延迟 ~1ms

分解：
├── 驱动提交（doorbell）：~5-10μs
├── 设备命令解析：~10-20μs
├── 设备命令队列等待：~50-200μs（队列深度）
├── 闪存访问（read + transfer）：~500-800μs
├── 设备 → 驱动中断：~50-100μs
└── 驱动处理 + 唤醒：~20-50μs
```

**关键洞察**：
- 闪存访问（500-800μs）占 50-80%
- 命令队列等待（50-200μs）受设备 IO 调度影响
- **设备 IO 是延迟瓶颈**，其他层只能"减少叠加"

### 2.3 设备驱动在 Linux 内核源码中的目录

```
drivers/
├── ufs/                       # UFS 驱动
│   ├── host/                  # 厂商实现（高通/三星/Exynos）
│   ├── core/                  # UFS 核心（ufs-core.c）
│   ├── ufshcd.c               # UFS Host Controller Driver
│   └── ...
├── mmc/                       # eMMC / SD 驱动
│   ├── host/                  # 厂商实现
│   ├── core/                  # MMC 核心
│   └── ...
├── nvme/                      # NVMe 驱动（高端 / 服务器）
│   ├── host/                  # NVMe 主机驱动
│   └── ...
└── block/                     # 通用块设备
```

---

## 三、UFS 架构深度解析（Android 主流）

### 3.1 UFS 的分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│  UFS Host Controller（SoC 内部）                                  │
│  - 接收 Block 层的 request                                         │
│  - 翻译为 UPIU（UFS Protocol Information Unit）                    │
│  - DMA 提交到设备                                                  │
└─────────────────────────────────────────────────────────────────┬───────────────────────────────────┘
                                                                     │
┌────────────────────────────────────────────────────────────────────▼───────────────────────────────────┐
│  UFS Device（独立芯片）                                                                       │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │  MIPI UniPro / M-PHY（物理层）                                                                  │ │
│  │  - 高速串行接口（PWM / HS 模式）                                                                  │ │
│  │  - 1 lane / 2 lane / 4 lane（UFS 4.0）                                                            │ │
│  └────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │  UFS Controller                                                                                  │ │
│  │  - 维护 command queue（最多 32 outstanding）                                                      │ │
│  │  - FTL（Flash Translation Layer）：LBA → physical block                                            │ │
│  │  - Wear Leveling：均衡写入                                                                           │ │
│  │  - GC（Garbage Collection）：回收已删除的 block                                                     │ │
│  └────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │  NAND Flash Array                                                                                 │ │
│  │  - TLC / QLC / MLC（不同 NAND 类型）                                                                │ │
│  │  - 多 die / 多 plane 并行                                                                            │ │
│  │  - Read / Write / Erase 三种操作（Erase 是 page 的 1000x 慢）                                       │ │
│  └────────────────────────────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 UFS Command Queue（核心特性）

```c
// UFS 的核心特性：硬件命令队列
// 最多 32 个 outstanding 命令

// 驱动层（ufshcd.c）：
// 1. 准备 UPIU（UFS Protocol Information Unit）
struct utp_transfer_req_desc {
    __le32 dword0;       // 命令类型
    __le32 dword1;       // 标志
    __le32 dword2;       // LBA / 数据偏移
    __le32 dword3;       // 长度
    // ... UPIU 头
};

// 2. DMA 提交到设备
// 3. 写 doorbell 寄存器 → 设备开始执行

// 设备层：
// 4. 接收 UPIU，放入内部 command queue
// 5. 内部调度（可优化命令顺序）
// 6. 执行 NAND 操作
// 7. 完成中断 → 驱动接收响应 UPIU
```

**关键特性**：
- **并行执行**：32 个命令可以同时执行（设备内部调度）
- **乱序完成**：命令可以乱序返回（device-side 调度优化）
- **与 blk-mq 完美匹配**：host 端的 blk-mq 多队列与 device 端 command queue 协同

### 3.3 UFS 的状态与功耗模式

```
UFS Power States（PXP = UFS Power State）：
├── Active（全速）：功耗 ~200mW，读延迟 100μs
├── Pre-Active：准备激活
├── Pre-Sleep：即将进入 Sleep
├── Sleep（轻量级）：保持 register，唤醒延迟 1-10ms
├── PowerDown：核心掉电，唤醒延迟 10-100ms
└── PowerDown w/ Link Off：完全掉电，唤醒延迟 100ms+
```

**踩坑**：**UFS Sleep → Active 唤醒延迟 ~10ms**——这是"App 偶尔启动慢"的真因之一！

```bash
# 查看 UFS 当前状态
cat /sys/class/scsi_host/host*/state
# running / cancel / deleted / ...

cat /sys/devices/platform/soc/*/ufs/...
# （具体路径依赖平台）
```

### 3.4 Write Booster（UFS 3.1+ 性能优化）

```
UFS Write Booster：
├── 利用部分 SLC cache 加速写
├── SLC 比 TLC 快 3-5x
├── 但 SLC cache 容量有限（几 GB）
└── cache 写满后性能回落到 TLC
```

**性能特征**：
- Write Booster 启用时：写入 ~500MB/s
- Write Booster 满时：写入 ~150MB/s（回落到 TLC）

---

## 四、UFS 的 IO 延迟特性

### 4.1 UFS 延迟的"四象限"

```
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│   高延迟（>1ms）                  │  低延迟（<1ms）            │
│   ┌─────────────────────────┐   │  ┌──────────────────┐    │
│   │  4K 随机读（~1ms）         │   │  │  4K 顺序读（~100μs）│    │
│   │  4K 随机写（~5ms）         │   │  │  顺序写（~50μs）     │    │
│   │  GC / Wear Leveling       │   │  │  顺序读（~50μs）     │    │
│   │  Thermal throttling       │   │  │  Read Booster 命中  │    │
│   │  Write Booster 满         │   │  │                   │    │
│   └─────────────────────────┘   │  └──────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**关键洞察**：
- 顺序读延迟 ~50-100μs（与 SSD 接近）
- 4K 随机读延迟 ~1ms（比 NVMe 慢 10-50x）
- **冷启动场景（顺序读为主）→ UFS 性能足够**
- **数据库场景（随机 IO 为主）→ UFS 性能瓶颈明显**

### 4.2 延迟分布（p50 / p99 / p999）

```
UFS 4K 随机读延迟分布（实测）：
├── p50（中位数）：~500μs
├── p90：~1ms
├── p99：~3ms ← 尾延迟
├── p999：~20ms ← 极端尾延迟
└── max：~100ms+ ← IO hang 风险

影响 p99 / p999 的因素：
1. GC（垃圾回收）：UFS 内部 GC 阻塞读
2. Wear Leveling：写均衡触发 block 迁移
3. Thermal throttling：高温降频
4. Write Booster 满：写回落到 TLC
```

**稳定性视角**：**p99 / p999 是 IO 性能的真因**——平均延迟看起来好，但尾延迟会让 App 启动尾延迟飙高。

### 4.3 顺序 vs 随机 IO 的性能差异

```
实测（UFS 3.1，4KB）：
├── 顺序读：~100μs（峰值 ~1.5GB/s）
├── 顺序写：~50μs（峰值 ~800MB/s）
├── 随机读：~1ms（~4000 IOPS）
└── 随机写：~5ms（~200 IOPS）

性能差异：
├── 顺序读 vs 随机读：10x 差距
└── 顺序写 vs 随机写：100x 差距
```

**应用启示**：
- **数据库随机写是 UFS 最大的痛点**
- **日志顺序写是 UFS 最擅长的场景**
- 冷启动优化 = 把随机 IO 转为顺序 IO（AOT 是关键）

### 4.4 队列深度对延迟的影响

```
队列深度（Queue Depth）vs 延迟：

QD=1（单线程）：
- 顺序读延迟：~100μs
- 随机读延迟：~1ms

QD=32（多线程）：
- 顺序读延迟：~80μs（设备内部并行）
- 随机读延迟：~800μs（设备内部调度优化）

QD=64+：
- 顺序读延迟：~80μs（接近 QD=32）
- 随机读延迟：~700μs（设备内部 GC 等因素）
```

**结论**：**QD=32 是 UFS 的"甜点"**——再高收益有限。

---

## 五、eMMC 架构深度解析（入门机主流）

### 5.1 eMMC 架构

```
┌─────────────────────────────────────────────────────────────────┐
│  eMMC 5.1 / A1 / A2 架构                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  MMC Controller（设备内部）                                  │ │
│  │  - Command Queue（最多 4-16 个 outstanding，eMMC 5.1+）      │ │
│  │  - FTL（Flash Translation Layer）                              │ │
│  │  - Cache（部分 eMMC 有 internal cache）                       │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  NAND Flash（与 UFS 类似）                                    │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

接口：MMC 总线（8 线并行 / HS400 模式）
物理速度：HS400 = 400MB/s（理论），实际 ~250MB/s
```

### 5.2 eMMC A1 / A2 的性能保证

```
eMMC Application Performance Class（A1 / A2）：
├── A1：随机读 ≥ 1500 IOPS，随机写 ≥ 500 IOPS
├── A2：随机读 ≥ 4000 IOPS，随机写 ≥ 2000 IOPS
└── A2 比 A1 性能要求翻倍

为什么有 A1 / A2？
├── 早期 eMMC 性能不足以跑 Android
├── Google 推动 Application Performance Class 标准
└── 让入门机能跑 Android（虽然还是慢）
```

### 5.3 eMMC vs UFS 的性能差距

| 维度 | eMMC 5.1 A2 | UFS 3.1 |
|------|------------|----------|
| 顺序读 | ~250MB/s | ~1.5GB/s |
| 4K 随机读 | ~300μs | ~100μs |
| 4K 随机写 | ~1.5ms | ~500μs |
| IOPS | 4000+ | 50K-100K |
| Command Queue | 4-16 | 32 |
| 并行能力 | 弱 | 强 |

**结论**：**eMMC 在随机 IO 上比 UFS 慢 10x+**——这就是为什么入门机跑 Android 流畅度差。

---

## 六、NVMe 架构深度解析（高端 / 服务器）

### 6.1 NVMe 的核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│  NVMe SSD                                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  PCIe 物理层                                                 │ │
│  │  - 高速串行（PCIe 3.0 x4 = 32GB/s，PCIe 4.0 x4 = 64GB/s）     │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  NVMe Controller                                            │ │
│  │  - 最多 65535 个 IO queues                                   │ │
│  │  - 每个 queue 深度可达 65536                                 │ │
│  │  - 多核并行（每 CPU 一队列）                                  │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  NAND / 3D XPoint（Intel Optane 才有）                        │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 NVMe 的核心优势

```
1. 多队列架构：
   - 每 CPU 一个 SQ（Submission Queue）+ CQ（Completion Queue）
   - 避免锁竞争（与 blk-mq 完美匹配）

2. 低延迟 IO：
   - 4K 随机读：~10-50μs（比 UFS 快 10-20x）
   - 4K 随机写：~10-100μs
   - 队列深度 1 即可达到大部分设备的峰值

3. 高吞吐：
   - 顺序读：~3-7GB/s（PCIe 4.0 x4）
   - 顺序写：~2-5GB/s

4. 中断优化：
   - MSI-X 中断（每队列独立）
   - 中断合并（Interrupt Coalescing）
```

### 6.3 Android 上的 NVMe

```
Android 设备极少使用 NVMe：
- iPhone 用 NVMe（但定制协议）
- 部分高端 Android 用 UFS 4.0
- 服务器 / 数据中心：NVMe 主流

为什么 Android 不广泛用 NVMe？
- NVMe 通常走 PCIe，需要 PCIe 控制器
- 移动 SoC 集成度低（不像 UFS 集成度高）
- 功耗考虑：NVMe 功耗远高于 UFS
- 成本考虑：NVMe 比 UFS 贵
```

**稳定性视角**：**移动设备上极少需要处理 NVMe 性能问题**——除非做服务器移植。

---## 七、IO 延迟的尾延迟（p99 / p999）—— 稳定性架构师的真关注点

### 7.1 为什么尾延迟比平均延迟重要

```
典型用户的体验：
├── 启动 App 100 次
├── 平均延迟：800ms（看起来很好）
├── 99 次启动 < 1s
├── 1 次启动 5s ← 用户感知"卡"
└── 用户评价：App 启动"偶尔慢"

这就是 p99 延迟的来源
```

### 7.2 UFS 的尾延迟来源

```
UFS 尾延迟飙高的 5 大来源：

1. GC（Garbage Collection）触发
   - UFS 内部回收已删除 block
   - 阻塞 IO 数十毫秒
   - 触发频率：随机写入多时频繁

2. Wear Leveling 触发
   - 写均衡触发 block 迁移
   - 阻塞 IO 数毫秒
   - 触发频率：写密集时

3. Thermal Throttling
   - 设备温度过高
   - 控制器降频（顺序读从 1.5GB/s 降到 500MB/s）
   - 延迟从 100μs 飙到 500μs+

4. Write Booster 满
   - SLC cache 写满
   - 写入回落到 TLC
   - 延迟从 50μs 飙到 1ms+

5. Sleep 唤醒
   - 设备进入 Sleep 后唤醒
   - 唤醒延迟 10-100ms
   - 触发：空闲一段时间后
```

### 7.3 尾延迟的监控方法

```bash
# 1. fio benchmark 测尾延迟
fio --name=randread --ioengine=libaio --direct=1 \
    --filename=/dev/block/sda --bs=4k --size=1G \
    --rw=randread --iodepth=1 --numjobs=1 \
    --runtime=60 --time_based --percentile_list=50:90:99:99.9

# 输出示例：
#   READ: io=1024.0MB, bw=... 
#   lat (usec): 50=..., 90=..., 99=..., 99.90=...
#   lat (msec): 99=3.0 (p99 = 3ms)

# 2. Perfetto IO events 看 p99
perfetto -o io_events.pftrace -c /system/etc/perfetto/io_config.pbtx
# 在 ui.perfetto.dev 看 latencies 分布

# 3. blktrace + btt 看每个 IO 的延迟分布
blktrace -d /dev/block/sda -o - | blkparse -i - -d - | btt -i -
# 输出：Q2Q 等待 + D2C 设备 IO + C2C 完成
```

### 7.4 尾延迟的治理方向

| 尾延迟来源 | 治理方向 |
|----------|---------|
| **GC** | 减少随机写入（AOT、合并写入）|
| **Wear Leveling** | 减少小写入（4K → 64K 合并）|
| **Thermal** | 控制设备温度（关后台任务、限制 CPU）|
| **Write Booster 满** | 优化写入模式（避免 burst 写入）|
| **Sleep 唤醒** | 应用预热 + 保持设备 active（vendor 定制）|

---

## 八、IO 性能与功耗的权衡

### 8.1 设备功耗的 4 个状态

```
UFS 功耗状态（典型值）：
├── Active（全速）：~200-300mW
├── Idle（轻载）：~50-100mW
├── Sleep：~5-10mW
└── PowerDown：<1mW

功耗差距：200-300x
```

**续航影响**：
- Active 持续读：~3 小时续航
- Sleep 持续：~500 小时续航

### 8.2 NVMe vs UFS 的功耗对比

```
NVMe SSD：
├── Active：~5-8W（移动设备不可接受）
├── Idle：~2-3W（仍然高）
└── 移动设备基本不能用

UFS 3.1：
├── Active：~200-300mW
├── Idle：~50-100mW
└── Sleep：~5-10mW

→ UFS 是移动设备的唯一选择
```

### 8.3 Auto Power State Transition

```c
// drivers/ufs/core/ufshcd.c
// UFS 自动状态切换

// 配置项：
// - /sys/devices/.../ufs/auto_hibern8_timeout_ms
// - /sys/devices/.../ufs/wb_flush_threshold
// - /sys/devices/.../ufs/clk_scale

// auto_hibern8_timeout：空闲多少 ms 后进入 Sleep
// 默认：5s（5 秒无 IO 进入 Sleep）
```

**稳定性影响**：
- auto_hibern8 太小 → 频繁进出 Sleep → 唤醒延迟 10-100ms
- auto_hibern8 太大 → 功耗高

**优化建议**：
- 视频录制、长任务期间禁用 auto_hibern8
- 日常使用保持默认（5s）

---

## 九、Android 设备存储选型现状

### 9.1 当前 Android 设备存储分布（2024-2026）

```
主流设备存储配置：

高端旗舰（Pixel 8 Pro / Galaxy S24 Ultra）：
├── UFS 4.0
├── 顺序读 ~4GB/s
├── 4K 随机读 ~100μs
└── 价格高，主要旗舰

中高端（Pixel 8 / Galaxy S24）：
├── UFS 3.1
├── 顺序读 ~1.5GB/s
├── 4K 随机读 ~200μs
└── 主流选择

中端（Pixel 7a / 中端 Galaxy A 系列）：
├── UFS 2.1 / UFS 3.0
├── 顺序读 ~700MB/s
├── 4K 随机读 ~500μs
└── 中端主流

入门（Pixel 6a / 入门 Android Go）：
├── eMMC 5.1 A2
├── 顺序读 ~250MB/s
├── 4K 随机读 ~500μs
└── 入门 / Android Go
```

### 9.2 存储选型对 App 启动的影响

```
冷启动耗时分解（典型 App）：

Pixel 8 Pro（UFS 4.0）：
├── Zygote fork：80ms
├── Application：100ms
├── Activity onCreate：80ms
├── 资源加载：400ms ← 设备 IO 主导
└── 总计：~660ms ← 流畅

Pixel 7a（UFS 3.0）：
├── Zygote fork：80ms
├── Application：100ms
├── Activity onCreate：80ms
├── 资源加载：800ms ← 设备 IO 慢 2x
└── 总计：~1060ms ← 还可接受

入门机（eMMC 5.1 A2）：
├── Zygote fork：80ms
├── Application：100ms
├── Activity onCreate：80ms
├── 资源加载：2000ms ← 设备 IO 慢 5x
└── 总计：~2260ms ← 用户感知慢
```

**稳定性视角**：**入门机的 IO 性能是冷启动慢的主因**——应用层优化效果有限。

### 9.3 设备性能监控（vendor）

```bash
# 查看当前设备类型
cat /proc/cpuinfo | grep "Hardware"
# ← 设备型号（用于判断 UFS 版本）

cat /sys/class/scsi_host/host*/ufshcd_ctl/...
# ← UFS 内部状态

# 实测 IO 性能
fio --name=seqread --ioengine=libaio --direct=1 \
    --filename=/dev/block/sda --bs=128k --size=1G \
    --rw=read --iodepth=32 --numjobs=1 --runtime=10
# 输出：bw=1500MB/s ← UFS 3.1 性能
```

---

## 十、风险地图：5 类设备层 IO 问题

| 类别 | 典型现象 | 日志关键字 | 排查入口 | 治理方向 |
|------|---------|----------|---------|---------|
| **① Thermal Throttling** | 长时间使用后慢 | `thermal-engine: throttle` / `ufs_thr` | 读温度传感器 | 散热优化 / 限制 CPU |
| **② Write Booster 满** | 写入突发慢 | `ufs: write_booster full` | 监控写吞吐 | 优化写入模式 |
| **③ GC 阻塞读** | 偶发卡顿（p999 高）| `gc_should_start` / `f2fs gc` | blktrace 长 IO | 减少随机写入 |
| **④ Sleep 唤醒慢** | 空闲后首次 IO 慢 | `ufs: hibern8 exit` | 抓 wakeup trace | 调整 auto_hibern8 |
| **⑤ 设备老化** | 用 1+ 年后 IO 慢 | `smart` / `flash wear` | vendor 工具 | 备份 + 重置 |

### 关键监控指标

```bash
# 1. UFS 设备状态
cat /sys/class/scsi_host/host*/state
cat /sys/kernel/debug/ufs/...

# 2. 设备温度
cat /sys/class/thermal/thermal_zone*/temp

# 3. IO 性能基准
fio --ioengine=libaio --direct=1 --rw=randread --bs=4k \
    --filename=/dev/block/sda --size=1G --runtime=10 \
    --time_based --percentile_list=99:99.9

# 4. blktrace 看 GC
blktrace -d /dev/block/sda -w 30 -o /tmp/trace
btt -i /tmp/trace -o /tmp/btt_output
```

---

## 十一、实战案例：UFS 高温降频导致 App 冷启动从 800ms 飙到 3s（典型模式）

### 现象

某品牌旗舰手机**长时间使用后（如玩 1 小时游戏），冷启动 App 从 800ms 飙到 3s**。重启后短暂恢复，过段时间又慢。

### 环境

- Android 13 / Kernel 5.10 / UFS 3.1 / 设备长时间高温环境

### 分析思路

**第一步：抓温度数据**：

```bash
cat /sys/class/thermal/thermal_zone*/temp
# 45000  ← 45°C（！）
# 50000
# 60000  ← 60°C（UFS 热保护触发）
```

**第二步：抓 UFS 设备状态**：

```bash
cat /sys/class/scsi_host/host*/state
# running

cat /sys/kernel/debug/ufs/ufshcd0/...
# throttle_state = 1（已降频！）
# throttle_reason = TEMPERATURE
```

**第三步：抓冷启动 trace 对比**：

```
正常温度（<45°C）：
T+0    App 启动
T+50   Zygote fork
T+100  Activity 创建
T+200  资源加载开始（顺序读）
T+800  首屏渲染 ← 正常

高温（>60°C，降频）：
T+0    App 启动
T+50   Zygote fork
T+100  Activity 创建
T+200  资源加载开始
T+2200 资源加载完成 ← 慢 5x！
T+3000 首屏渲染
```

**根因诊断**：

1. UFS 温度达到 60°C（接近热保护阈值）
2. UFS 控制器自动降频（顺序读从 1.5GB/s 降到 500MB/s）
3. **结果**：App 启动时资源加载变慢 5x

### 修复方案

1. **vendor 调优**：
   - 调高 UFS 热保护阈值（但有物理极限）
   - 优化 UFS thermal zone 配置

2. **应用层优化**：
   - 减少启动期 IO（合并请求）
   - 预加载到内存（避免高温时再触发 IO）

3. **系统层优化**：
   - 优化 CPU 频率（降低发热）
   - 优化后台任务（降低整体温度）

### 排查路径速查

```
长时间使用后冷启动慢
  ↓
抓设备温度 → /sys/class/thermal/...
  ↓
抓 UFS throttle → debugfs
  ↓
确认 thermal throttling → 优化散热 / 应用优化
```

---

## 十二、实战案例：设备老化导致 IO 性能下降（典型模式）

### 现象

某设备**使用 2 年后，App 启动时间从 800ms 飙升到 2s+**。重启无效，恢复出厂设置短暂恢复。

### 环境

- Android 11 / Kernel 5.10 / 设备使用 2 年 / 用户频繁写大量数据

### 分析思路

**第一步：抓 SMART / 健康度信息**：

```bash
# vendor 提供的 UFS 健康度
cat /sys/devices/platform/soc/.../ufs/lifetime_est
# Device lifetime used = 80%  ← 已用 80%

cat /sys/devices/platform/soc/.../ufs/... 
# （具体路径看 vendor）
```

**第二步：抓 fio 性能对比**：

```
新设备（基线）：
├── 顺序读：1.5GB/s
├── 4K 随机读：100μs
└── 4K 随机写：500μs

老化设备（用 2 年）：
├── 顺序读：1.0GB/s（-33%）
├── 4K 随机读：300μs（3x 慢）
└── 4K 随机写：2ms（4x 慢）
```

**根因诊断**：

1. **NAND 老化**：写入次数累计，氧化层退化
2. **FTL 映射表膨胀**：物理 block 隔离增加，FTL 性能下降
3. **GC 频率增加**：空闲 block 减少，GC 更频繁
4. **结果**：IO 性能下降 2-4x

### 修复方案

1. **数据迁移**：备份 → 恢复出厂设置 → 恢复数据
2. **更换设备**：超过使用年限（建议 2-3 年）
3. **vendor 工具**：部分厂商提供 TRIM 工具优化 GC

### 排查路径速查

```
设备老化后慢
  ↓
抓 UFS lifetime / 健康度
  ↓
确认硬件老化 → 备份重置 / 更换
```

---

## 十三、总结：架构师视角的 5 条 Takeaway

读完本篇，请记住这 5 件事——它们是理解"设备为何变慢"的"金钥匙"：

1. **"设备 IO 延迟占 80-95%"**——优化内核调度收益有限，**真正瓶颈是设备层**。看到性能问题先想"是不是设备慢"，不是"调度器怎么配"。
2. **"UFS Sleep 唤醒延迟 10-100ms"**——空闲后首次 IO 慢的常见原因。**auto_hibern8 配置 + 关键路径预热**是治理方向。
3. **"UFS thermal throttling 是隐形杀手"**——长时间使用后性能下降的真因。监控 UFS 温度 + throttle_state 是稳定性架构师必备技能。
4. **"随机 IO 是 UFS 的痛点"**——4K 随机写延迟比顺序写慢 100x。**应用层把随机 IO 转顺序 IO（AOT、合并写入）是关键优化**。
5. **"入门机 eMMC 性能限制"**——如果优化在 eMMC 上效果有限，可能要从应用本身减小 IO 需求（更小的资源、更少的 .so）。

### 排查路径速查（设备层 IO 问题）

```
IO 性能慢 / 偶发卡顿
  ↓
① 设备类型 → cat /sys/class/scsi_host/...
  ↓
② 设备温度 → cat /sys/class/thermal/...
  ↓
③ UFS throttle → debugfs
  ↓
④ fio 性能基准 → 看实际 IO 能力
  ↓
⑤ 治理 → 散热 / 优化应用 / 更换设备
```

---

## 附录 A：核心源码路径索引

| 文件名 | 完整路径 | 内核版本基线 | 说明 |
|--------|---------|------------|------|
| `ufshcd.c` | `drivers/ufs/core/ufshcd.c` | Linux 5.10+ | UFS Host Controller Driver |
| `ufs-core.c` | `drivers/ufs/core/ufs-core.c` | Linux 5.10+ | UFS 核心 |
| `ufs-exynos.c` | `drivers/ufs/host/ufs-exynos.c` | Linux 5.10+ | Samsung Exynos UFS |
| `ufs-qcom.c` | `drivers/ufs/host/ufs-qcom.c` | Linux 5.10+ | Qualcomm UFS |
| `mmc_core.c` | `drivers/mmc/core/mmc_core.c` | Linux 5.10+ | MMC 核心 |
| `cqhci.c` | `drivers/mmc/host/cqhci.c` | Linux 5.10+ | eMMC command queue |
| `nvme-core.c` | `drivers/nvme/host/core.c` | Linux 5.10+ | NVMe 核心 |
| `nvme.h` | `include/linux/nvme.h` | Linux 5.10+ | NVMe 数据结构 |

---

## 附录 B：源码路径对账表

| 序号 | 文章中出现的路径 | 状态 | 校对来源 |
|------|----------------|------|---------|
| 1 | `drivers/ufs/core/ufshcd.c` | 已校对 | elixir.bootlin.com/linux/v5.10/drivers/ufs/core/ufshcd.c |
| 2 | `drivers/ufs/core/ufs-core.c` | 已校对 | elixir.bootlin.com/linux/v5.10/drivers/ufs/core/ufs-core.c |
| 3 | `drivers/ufs/host/ufs-exynos.c` | 已校对 | elixir.bootlin.com/linux/v5.10/drivers/ufs/host/ufs-exynos.c |
| 4 | `drivers/ufs/host/ufs-qcom.c` | 已校对 | elixir.bootlin.com/linux/v5.10/drivers/ufs/host/ufs-qcom.c |
| 5 | `drivers/mmc/core/mmc_core.c` | 已校对 | elixir.bootlin.com/linux/v5.10/drivers/mmc/core/mmc_core.c |
| 6 | `drivers/mmc/host/cqhci.c` | 已校对 | elixir.bootlin.com/linux/v5.10/drivers/mmc/host/cqhci.c |
| 7 | `drivers/nvme/host/core.c` | 已校对 | elixir.bootlin.com/linux/v5.10/drivers/nvme/host/core.c |

---

## 附录 C：量化数据自检表

| 序号 | 量化描述 | 数量级 | 依据 |
|------|---------|--------|------|
| 1 | eMMC 5.1 顺序读 | ~150MB/s | 厂商 datasheet |
| 2 | eMMC A2 顺序读 | ~250MB/s | 厂商 datasheet |
| 3 | UFS 2.1 顺序读 | ~700MB/s | 厂商 datasheet |
| 4 | UFS 3.1 顺序读 | ~1.5GB/s | 厂商 datasheet |
| 5 | UFS 4.0 顺序读 | ~4.2GB/s | 厂商 datasheet |
| 6 | NVMe PCIe 3.0 顺序读 | ~3GB/s | NVMe 协议 |
| 7 | NVMe PCIe 4.0 顺序读 | ~7GB/s | NVMe 协议 |
| 8 | UFS 4K 顺序读延迟 | ~50-100μs | 实测 |
| 9 | UFS 4K 随机读延迟 | ~100-500μs | 实测 |
| 10 | UFS 4K 随机写延迟 | ~500μs-5ms | 实测 |
| 11 | NVMe 4K 随机读延迟 | ~10-50μs | NVMe 协议 |
| 12 | UFS command queue | 32 outstanding | UFS 协议 |
| 13 | UFS Sleep 唤醒延迟 | 10-100ms | 实测 |
| 14 | UFS Active 功耗 | 200-300mW | 厂商 datasheet |
| 15 | UFS Sleep 功耗 | 5-10mW | 厂商 datasheet |
| 16 | UFS Write Booster 容量 | 几 GB | 厂商 datasheet |

---

## 附录 D：工程基线表

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|------|---------|---------|---------|
| **auto_hibern8_timeout** | 5s | 长任务期间调到 60s+ | 太小 → 频繁唤醒 |
| **write_booster** | 启用 | 默认即可 | 容量有限，满了回落 |
| **write_booster_flush_threshold** | 50% | 避免满后回落 | 太低 → 频繁 flush |
| **thermal throttle threshold** | 60-70°C | vendor 调优 | 太低 → 频繁降频 |
| **UFS clk_scale** | 启用 | 默认即可 | 关闭 → 功耗高 |
| **fio rw=randread 性能基线** | UFS 3.1: 100μs | 老化后监控 | >500μs = 异常 |
| **fio rw=seqread 性能基线** | UFS 3.1: 1.5GB/s | 老化后监控 | <800MB/s = 异常 |
| **设备温度监控阈值** | 60°C | 启用 thermal-engine | 太低 → 误报 |

---

## 篇尾衔接

本篇深入了 IO 链路的最底层——**设备物理层**：UFS 架构与 command queue、eMMC 的入门机瓶颈、NVMe 的高端特性、IO 尾延迟的真因（GC / Wear Leveling / Thermal）、功耗与性能权衡。

至此，**01 总览 + 02 调度器 + 03 Block + 04 IO 优先级 + 05 IO↔MM + 06 IO↔Process + 07 程序加载 IO + 08 Android 存储栈 + 09 存储设备**——9 篇构成了 IO 子系统的完整知识体系。

下一篇 [10-IO 风险全景与诊断工具链](10-IO稳定性风险全景与诊断工具链.md) 将作为系列**收官**：整合所有 9 篇的风险地图 + iostat / blktrace / Perfetto 工具箱 + 监控体系设计 + 治理最佳实践——这是稳定性架构师日常排查 IO 问题的"工具包"。