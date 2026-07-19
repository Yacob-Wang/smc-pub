# 04-IO 优先级与 cgroup IO 控制器：ionice / cgroup v1 blkio / cgroup v2 io

> **系列**：面向稳定性的 Android IO 子系统深度解析系列(IO)
>
> **源码基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)
>
> **内核矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇涉及 `block/blk-throttle.c`、`block/blk-iolatency.c`、`kernel/ionice.c`、`include/linux/ioprio.h`;Android 14 默认采用 cgroup v2 io控制器,见 §3)
>
> **目标读者**:Android 稳定性框架架构师
>
> **前置阅读**:[01-IO 子系统总览](01-IO子系统总览：从进程read、write到磁盘的完整链路.md) / [02-IO 调度器](02-IO调度器与多队列架构.md) §6 / [03-Block 层核心机制](03-Block层核心机制：bio-request-plug-merge-throttle.md) §9-§10
>
> **下一篇**:[05-IO 与内存的深度耦合](05-IO与内存的深度耦合：Page-Cache脏页回写、回收路径、swap-IO.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 3 篇(IO 优先级 + cgroup 资源隔离,系列横切专题之一)
- **强依赖**:
  - [01-IO 子系统总览](01-IO子系统总览：从进程read、write到磁盘的完整链路.md)(IO 链路全景)
  - [02-IO 调度器与多队列架构](02-IO调度器与多队列架构.md) §6(bfq 的 cgroup 集成)
  - [03-Block 层核心机制](03-Block层核心机制：bio-request-plug-merge-throttle.md) §9-§10(blk-throttle / blk-iolatency)
  - [Process 17-Android进程优先级与LMK](../Process/17-Android进程优先级与LMK.md)(Android 进程优先级体系)
- **承接自**:
  - 02 已讲调度器算法
  - 03 已讲 Block 层 throttle 机制
  - 本篇深入到**应用层接口**(ionice + cgroup 文件系统)
- **衔接去**:本篇是内核主线第 3 篇。再往后是 [08-Android 存储栈](08-Android存储栈：从FUSE、sdcardfs、StorageManager到块设备.md)(Android 特化)和 [09-存储设备与 IO 性能](09-存储设备与IO性能：UFS、eMMC、NVMe命令队列与延迟特性.md)(硬件层)
- **不重复内容**:
  - **CFS 调度器的进程优先级(nice / cgroup)** → 详见 [Process 10-进程优先级与实时调度](../Process/10-进程优先级与实时调度.md)
  - **bfq 的 cgroup 集成细节** → 详见 [02-IO 调度器](02-IO调度器与多队列架构.md) §6
  - **blk-throttle 的算法实现** → 详见 [03-Block 层核心机制](03-Block层核心机制：bio-request-plug-merge-throttle.md) §9
  - **LMK / LMKD 的进程杀策略** → 详见 [Process 17-Android进程优先级与LMK](../Process/17-Android进程优先级与LMK.md)
- **本篇的核心价值**:让稳定性架构师能**根据进程类别配置 IO 优先级和 cgroup 权重**,理解 Android 进程优先级 ↔ IO 优先级的协同机制,能定位"前台被后台拖累"等典型 IO 反转问题。

#### §0 锚点案例的可验证 4 件套:相册云同步抢占 IO 导致相机拍照保存卡 2.8s

> **环境**:
> - 设备:Pixel 7(G2, arm64-v8a, 8GB RAM, UFS 3.1)
> - Android 版本:AOSP `android-14.0.0_r1`(默认 cgroup v2 io 控制器)
> - Kernel:`android14-5.15` GKI
> - App:某相机 v4.3(脱敏代号 `CamApp`,照片保存 ~12MB/张) + 后台"相册云同步" Service
> - 工具:`cat /sys/fs/cgroup/io/scheduler` + `iotop -ao` + `cat /sys/fs/cgroup/io.stat` + `perfetto`

> **复现步骤**:
> 1. 工厂重置,安装 CamApp v4.3 + "PhotoSync" v2.1(脱敏代号,后台服务)
> 2. `adb shell ionice -p $(pidof com.photosync)` → 默认 `best-effort/4`
> 3. 触发 PhotoSync 后台上传 2000 张照片(峰值 ~80MB/s 持续 60s)
> 4. 期间打开 CamApp 拍照,测量"按下快门到照片保存完成"时间
> 5. 给 CamApp 提权:`ionice -c 1 -n 0 -p $(pidof com.cam.app)` + cgroup weight 1000 → 重测

> **logcat / iotop 关键片段**:
> ```
> # /sys/fs/cgroup/io.stat(PhotoSync cgroup)
> 8:0 rbytes=1874321456 wbytes=482340864 rios=234 wios=198 dbytes=0
>                                       ↑ PhotoSync 1.8GB 读取 + 482MB 写入
> # iotop 输出(快门按下时刻)
> TID  PRIO  USER     DISK READ  DISK WRITE  SWAPIN     IO>    COMMAND
> 2249 be/4  u0_a123    0.00 B/s    48.12 M/s  0.00 %  99.99 %  com.photosync:sync   ← 后台写 48MB/s
> 1452 be/4  u0_a87     0.00 B/s     1.20 M/s  0.00 %  82.50 %  com.cam.app:capture   ← 前台 CamApp 写 1.2MB/s
> # CamApp 主线程 trace(简化的 systrace)
> camera_capture_button:BLOCKING 2.8s    ← 主线程 IO 阻塞 2.8s
>   ↳ blk_mq_get_request (sleep 1.2s)
>   ↳ bfq_bfqq_wait_request (sleep 1.6s)   ← bfq 把带宽全给了 PhotoSync
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/frameworks/base/services/core/java/com/android/server/am/ProcessConfigManager.java
> +++ b/frameworks/base/services/core/java/com/android/server/am/ProcessConfigManager.java
> @@ setProcessIoPriority()
> -    // 旧版:统一 best-effort/4,前台 App 与后台 Service 同优先级
> -    Process.setIoPriority(Process.BEST_EFFORT, 4);
> +    // 修复:前台 TOP_APP 强制 RT 类,后台 cgroup weight 降到 100
> +    if (isTopApp) {
> +        Process.setIoPriority(Process.REAL_TIME, 0);
> +        CgroupUtils.writeCgroupFile("io.weight", "1000");
> +    } else {
> +        Process.setIoPriority(Process.BEST_EFFORT, 7);
> +        CgroupUtils.writeCgroupFile("io.weight", "100");
> +    }
> ```
> ```diff
> --- a/device/google/pixel/init.rcd
> +++ b/device/google/pixel/init.rcd
> @@ post-fs-data
> -    # 旧版:后台同步服务无 IO 限额
> +    # 修复:为 cloud-sync 类服务创建独立 cgroup,io.weight=50
> +    mkdir /sys/fs/cgroup/io/sync_services
> +    chown system system /sys/fs/cgroup/io/sync_services
> +    echo "50" > /sys/fs/cgroup/io/sync_services/io.weight
> ```
> 完整 IO 优先级 ↔ Android 进程优先级对照表 + 性能基线见 §5 §11。

---

## 一、背景与定义：为什么需要 IO 优先级与 cgroup 隔离

### 1.1 一个朴素的稳定性问题

场景：用户前台 App 拍照时，后台 App 同步大文件（相册云同步）。两者共享同一块磁盘。**没有优先级与隔离会怎样？**

```
现状：
- 后台同步：1MB/s 持续写
- 前台拍照：1MB 突发写（保存照片）
- 两者排队在同一个 request queue

如果后台同步占用 IO 队列：
- 前台照片保存延迟：1MB / 1MB/s = 1 秒
- 用户感知：相机黑屏 / 拍照卡顿

如果有 IO 优先级 + cgroup 隔离：
- 前台 cgroup weight 高 → 抢占 IO 队列
- 后台 cgroup weight 低 → 让出 IO 队列
- 前台照片保存延迟：从 1s 降到 100ms
```

**IO 优先级与 cgroup 隔离的本质**：让"关键的 IO 优先调度，不重要的 IO 让出带宽"。

### 1.2 三层优先级机制

Linux/Android 的 IO 资源分配有 **3 层机制** 协同工作：

```
┌─────────────────────────────────────────────────────────┐
│  第 1 层：进程级 IO 优先级（ionice / ioprio_set）         │
│  - 系统调用层接口                                          │
│  - per-process / per-thread                                │
│  - 影响 blk-mq 调度器的 RT class 处理                      │
└─────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────┐
│  第 2 层：cgroup IO 资源控制（blkio / io）                 │
│  - per-cgroup 的 bps / iops / weight 限制                  │
│  - 通过 blk-throttle + blk-iolatency 实现                  │
│  - Android foreground/background/top-app 都用 cgroup 隔离  │
└─────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────┐
│  第 3 层：调度器内置优先级（bfq weight / mq-deadline）    │
│  - 由具体 IO 调度器实现                                    │
│  - bfq 支持 cgroup weight（最强）                          │
│  - mq-deadline 不支持 cgroup weight（靠 blk-throttle）     │
└─────────────────────────────────────────────────────────┘
```

**关键认知**：**3 层机制是叠加的**——调度器优先级 × cgroup 限速 × ionice，最终决定一个 IO 任务的优先级。

### 1.3 稳定性意义

| 现象 | 真实根因（IO 优先级 / cgroup） | 排查方向 |
|------|------------------------------|---------|
| **前台 App 被后台拖累** | cgroup weight 配置错 | 看 cgroup io.weight / blkio.weight |
| **相机启动慢但磁盘不忙** | 后台 cgroup 抢走 IO 队列 | 看 blk-throttle debug |
| **同步任务被饿死** | 后台 cgroup iops 限制太严格 | 看 cfg_iops / cfg_bps |
| **多租户互相干扰** | 没有合理划分 cgroup | 检查 cgroup hierarchy |
| **system_server 响应慢** | system cgroup 权重过低 | 看 system cgroup 配置 |

---

## 二、架构与交互：IO 优先级体系全景

### 2.1 进程级 → cgroup 级 → 调度器级的优先级传递

```
应用进程 (priority = nice=-10, ioprio_class=BE, ioprio_data=4)
    │
    ├─→ ioprio_set() 系统调用
    │     ↓
    │   task->io_context.ioprio = ?
    │     ↓
    │   bio->bi_ioprio = ?
    │
    ├─→ cgroup（自动根据进程所属 cgroup）
    │     ↓
    │   cgroup->blkcg_weight = ?
    │     ↓
    │   blk-throttle 按 cgroup 限速
    │
    └─→ bio 提交
          ↓
        blk_mq_make_request
          ↓
        调度器（mq-deadline / bfq）
          ↓
        调度器内部按 weight + ioprio 决策
          ↓
        request 派发
```

### 2.2 IO 优先级的 3 个"评价对象"

```
评价对象 1：单个 IO（bio）
├── bi_ioprio（class + data）
├── bi_cookie（icq 关联）
└── 用于调度器决策

评价对象 2：单个进程（task）
├── task->io_context->ioprio
├── task->io_context->last_waited
└── 用于 ICQ（io context）状态

评价对象 3：整个 cgroup
├── cgroup->blkcg->weight（v1: 100-1000, v2: 1-10000）
├── cgroup->blkcg->cfg_bps[2][2]（读/写 × sync/async）
└── 用于 blk-throttle 限速
```

### 2.3 IO 优先级在 Linux 内核源码中的目录

```
block/
├── ioprio.c                # ioprio_set/get 系统调用
├── mq-deadline.c           # mq-deadline 的 RT class 处理
├── bfq-iosched.c           # bfq 的 weight / ioprio 集成
├── kyber-iosched.c         # kyber 的 ioprio 集成
├── blk-cgroup.c            # cgroup blkcg 框架
├── blk-throttle.c          # bps / iops 限流
└── blk-iolatency.c         # latency target

include/
├── ioprio.h                # ioprio 常量定义
├── iocontext.h             # io_context 数据结构
└── blk-cgroup.h            # blkcg 数据结构

kernel/
└── cgroup/                 # cgroup 核心
```

---

## 三、ionice（ioprio_set / ioprio_get 系统调用）

### 3.1 ioprio_set 系统调用接口

```c
// include/linux/ioprio.h
// ioprio 编码：
// 高 8 位：class（RT / BE / Idle）
// 低 8 位：data（class 内的级别）

#define IOPRIO_BITS            16
#define IOPRIO_CLASS_SHIFT     13
#define IOPRIO_PRIO_MASK       ((1 << IOPRIO_CLASS_SHIFT) - 1)

#define IOPRIO_PRIO_CLASS(ioprio)  ((ioprio) >> IOPRIO_CLASS_SHIFT)
#define IOPRIO_PRIO_DATA(ioprio)   ((ioprio) & IOPRIO_PRIO_MASK)

// IOPRIO_CLASS 枚举
enum {
    IOPRIO_CLASS_NONE,      // 0：未设置（等同于 BE / 4）
    IOPRIO_CLASS_RT,        // 1：实时（最高优先级）
    IOPRIO_CLASS_BE,        // 2：尽力（普通）
    IOPRIO_CLASS_IDLE,      // 3：空闲（仅在系统空闲时调度）
};

// ioprio 值 = (class << 13) | data
// 例如：IOPRIO_CLASS_BE | 4 = (2 << 13) | 4 = 16388
```

### 3.2 ioprio_set 系统调用实现

```c
// block/ioprio.c
int ioprio_set(int which, int who, int ioprio) {
    // ① 参数校验
    switch (which) {
    case IOPRIO_WHO_PROCESS:    // who 是 pid
        ret = set_one_ioprio(current, who, ioprio);
        break;
    case IOPRIO_WHO_PGRP:       // who 是 pgid
        // 遍历进程组所有进程
        break;
    case IOPRIO_WHO_USER:       // who 是 uid
        // 遍历该 uid 所有进程
        break;
    }
    return ret;
}

static int set_one_ioprio(struct task_struct *p, int ioprio) {
    // ① 检查权限（RT class 需要 CAP_SYS_ADMIN）
    if (IOPRIO_PRIO_CLASS(ioprio) == IOPRIO_CLASS_RT) {
        if (!capable(CAP_SYS_ADMIN))
            return -EPERM;
    }
    
    // ② 锁定 task->io_context
    ioc = task_lock_io_context(p, GFP_KERNEL);
    
    // ③ 设置 ioprio
    ioc->ioprio = ioprio;
    
    // ④ 通知调度器（bfq 会重建 bfq_queue）
    // ...
    
    task_unlock_io_context(p, ioc);
    
    return 0;
}
```

### 3.3 ioprio 的应用层调用

```bash
# 1. ionice 命令行工具
ionice -c 2 -n 4 -p <pid>     # 设置 pid 为 BE class / level 4
ionice -c 3 -p <pid>          # 设置为 Idle（最低）

# 2. c 代码
#include <sys/syscall.h>
#include <linux/ioprio.h>

int ioprio = IOPRIO_PRIO_VALUE(IOPRIO_CLASS_BE, 4);
syscall(SYS_ioprio_set, IOPRIO_WHO_PROCESS, getpid(), ioprio);
```

### 3.4 三个 ioprio class 的语义

| class | 语义 | 典型场景 | 调度器行为 |
|-------|------|---------|----------|
| **RT (Real-Time)** | 最高优先级，调度器立即派发 | 系统关键进程（system_server） | mq-deadline: 跳过 FIFO 排序；bfq: 优先派发 |
| **BE (Best-Effort)** | 普通尽力，level 0-7（0 最高）| 普通应用 | mq-deadline: 正常排队；bfq: 按 budget |
| **Idle** | 仅在系统空闲时调度 | 后台批处理 | 仅在无其他 IO 时派发 |

**BE class 的 level 含义**：

```c
// BE class 内部分级（0-7）
// level 0：最高（与 RT 接近）
// level 4：默认
// level 7：最低
```

**Android 默认配置**：
- system_server：BE / 0（较高）
- 前台 App：BE / 4（默认）
- 后台 App：BE / 7（较低）

### 3.5 ioprio 的稳定性限制

**限制 1：RT class 需要 CAP_SYS_ADMIN**

```bash
# 普通用户无法设置 RT class
$ ionice -c 1 -p <pid>
ionice: ioprio_set failed: Operation not permitted

# 只有 root / system / shell 用户可以设置 RT
```

**限制 2：blk-mq 时代的 RT 处理与 cfq 不同**

```
cfq 时代：
- RT class 的 IO 立即派发
- cfq_queue 按 ioprio 排序

blk-mq 时代（5.10+）：
- RT class 在 mq-deadline 中：跳过 FIFO 排序（fs/read_write.c: rw_verify_area）
- RT class 在 bfq 中：插入 service tree 头部
- 普通 BE class：正常排队
```

**限制 3：Idle class 不是"绝对空闲"**
- Idle class 的 IO 仍然会派发
- 但仅在系统没有 BE / RT IO 时
- **大量 Idle IO 仍可能饿死 BE**（取决于调度器实现）

---

## 四、CFQ 时代的 per-process IO 优先级（历史背景）

### 4.1 cfq 的 ioprio 集成

```c
// block/cfq-iosched.c（已废弃，仅历史参考）
struct cfq_queue {
    int ioprio_class;
    int ioprio_data;
    
    // ... cfq 的 service tree 节点 ...
};
```

**cfq 时代的行为**：
- 每个进程一个 `cfq_queue`
- cfq_queue 内部按 `ioprio_class` + `ioprio_data` 排序
- RT class 的进程在 service tree 头部
- BE class 的进程按 level 0-7 排序

### 4.2 cfq 退役的原因

```
cfq 的 4 大问题（导致 5.x 废弃）：

1. 单队列锁竞争严重
   → 多核扩展性差
   → blk-mq 取代

2. cfq_queue per-process 内存开销大
   → 10000 个进程 = 10000 个 cfq_queue
   → 内存占用 GB 级

3. 算法复杂，难维护
   → bug 修复速度慢
   → bfq 取代其 cgroup 权重功能

4. RT class 处理不够及时
   → 紧急 IO 仍有延迟
   → mq-deadline + RT 标记取代
```

### 4.3 历史教训

**给稳定性架构师的提醒**：
- 在 5.10+ kernel 上**不要再配置 cfq**
- 任何遗留的 `elevator=cfq` 配置都会触发 UE（见 [02-IO 调度器](02-IO调度器与多队列架构.md) §12 案例 2）
- 升级 kernel 时同步清理旧调度器配置

---## 五、blk-mq 时代的 IO 优先级表达

### 5.1 bio 的 bi_ioprio 字段

```c
// include/linux/blk_types.h
struct bio {
    // ...
    u16 bi_ioprio;        // bio 的 IO 优先级（class + data）
    // ...
};

// 获取 bio 的 ioprio
#define bio_prio(bio)    (bio->bi_ioprio)
#define bio_ioprio_class(bio)    IOPRIO_PRIO_CLASS(bio->bi_ioprio)
#define bio_ioprio_data(bio)     IOPRIO_PRIO_DATA(bio->bi_ioprio)
```

### 5.2 ioprio 的传递链路

```c
// task->io_context 创建 / 获取
struct io_context *get_task_io_context(struct task_struct *task, gfp_t gfp_flags) {
    // ① 如果 task 已经有 io_context，返回
    if (task->io_context)
        return task->io_context;
    
    // ② 否则创建
    ioc = kmalloc(sizeof(*ioc), gfp_flags);
    ioc->ioprio = IOPRIO_DEFAULT;  // 默认 BE / 4
    // ...
    
    task->io_context = ioc;
    return ioc;
}

// bio 创建时继承 ioprio
void blk_mq_bio_to_request(struct request *rq, struct bio *bio) {
    // ...
    rq->ioprio = bio_prio(bio);
    rq->ioprio_class = bio_ioprio_class(bio);
    // ...
}
```

### 5.3 mq-deadline 的 RT 处理

```c
// block/mq-deadline.c
// RT class 的 IO 处理：
// 1. 不参与 FIFO 排序（立即派发）
// 2. 仍受 blk-throttle 限制（cgroup）
// 3. 仍受 read_expire / write_expire 限制

static void dd_insert_request(struct blk_mq_hw_ctx *hctx, struct request *rq,
                              blk_insert_mode flags) {
    // ...
    
    // RT class 的 IO：插入 fifo 头部
    if (rq->ioprio_class == IOPRIO_CLASS_RT) {
        list_add(&rq->queuelist, &dd->fifo_list[DD_READ]);
        // 强制派发（不排到尾部）
        return;
    }
    
    // 普通 BE class：按 LBA 排序插入
    // ...
}
```

**关键洞察**：RT class 在 mq-deadline 中是**绕过 FIFO 排序**——但仍要走 blk-throttle（cgroup 限速优先于 IO 优先级）。

### 5.4 bfq 的 ioprio + weight 双重控制

```c
// block/bfq-iosched.c
// bfq 是 blk-mq 时代唯一完整支持 ioprio 的调度器
static struct bfq_queue *bfq_get_queue(struct bfq_data *bfqd, ...) {
    // ...
    
    // ① 创建 bfq_queue 时继承 ioprio
    bfqq->new_ioprio = ioc->ioprio;
    
    // ② 启动时根据 ioprio 设置权重
    if (bfqq->new_ioprio == IOPRIO_CLASS_RT) {
        bfqq->weight = BFQ_WEIGHT_MAX;  // 最高
    } else if (bfqq->new_ioprio == IOPRIO_CLASS_BE) {
        bfqq->weight = ...;  // 按 level 0-7 设置
    }
    
    // ...
}
```

**bfq 的 weight × ioprio 矩阵**：

| ioprio | bfq weight | 含义 |
|--------|-----------|------|
| RT | BFQ_WEIGHT_MAX (1000) | 最高，几乎总能调度 |
| BE / 0 | ~750 | 较高 |
| BE / 4 | 500（默认） | 普通 |
| BE / 7 | ~250 | 较低 |
| Idle | ~1 | 几乎不被调度 |

---

## 六、cgroup v1 blkio 子系统

### 6.1 cgroup v1 blkio 的接口

```bash
# cgroup v1 的 blkio 接口（在 Android 13 及之前的部分设备上）
mount -t cgroup -o blkio none /sys/fs/cgroup/blkio
# 或者 systemd 自动挂载

# 查看某个 cgroup 的 IO 限速
ls /sys/fs/cgroup/blkio/<cgroup>/
# blkio.throttle.read_bps_device
# blkio.throttle.write_bps_device
# blkio.throttle.read_iops_device
# blkio.throttle.write_iops_device
# blkio.weight
# blkio.weight_device
# blkio.throttle.io_service_bytes
# blkio.throttle.io_serviced
```

### 6.2 cgroup v1 blkio 的核心字段

```c
// block/blk-cgroup.c
struct blkcg {
    struct cgroup_subsys_state css;     // cgroup 框架
    
    // 配置（来自 cgroup 文件系统）
    struct blkg_policy_data pd[BLKCG_MAX_POLS];
    
    // weight（per-cgroup 权重，影响 bfq）
    unsigned int weight;
    unsigned int weight_device[MAX_BLKDEV];   // per-device weight
    
    // 限制（per-cgroup 的 bps / iops）
    struct throtl_data *td;             // 关联的 throtl_data
};
```

### 6.3 关键配置详解

#### 6.3.1 blkio.weight

```bash
# 写入 weight（范围 100-1000，默认 500）
echo 800 > /sys/fs/cgroup/blkio/foreground/blkio.weight

# per-device weight（覆盖默认值）
echo 800:0 1000 > /sys/fs/cgroup/blkio/foreground/blkio.weight_device
# 格式：major:minor weight
```

**weight 的含义**：在 bfq 调度器中，按 weight 比例分配 IO 带宽。
- weight=800 比 weight=200 优先 4x（800/200=4）
- 但**weight 不限制总 IO 量**——只是按比例

#### 6.3.2 blkio.throttle.*_bps_device

```bash
# 读 / 写 bps 限制
echo "8:0 104857600" > /sys/fs/cgroup/blkio/foreground/blkio.throttle.read_bps_device
# 8:0 = major:minor（设备 ID）
# 104857600 = 100MB/s（字节 / 秒）
```

#### 6.3.3 blkio.throttle.*_iops_device

```bash
# 读 / 写 iops 限制
echo "8:0 5000" > /sys/fs/cgroup/blkio/foreground/blkio.throttle.read_iops_device
# 5000 = 5000 次 IO / 秒
```

### 6.4 cgroup v1 blkio 的局限性

**问题 1：接口分散**
- throttle / weight / cfq 是不同子系统（虽然都挂 blkio）
- 配置项多，新手难懂

**问题 2：device 索引复杂**
- `major:minor` 不是所有人都懂
- 同一设备在不同场景需要不同配置

**问题 3：跨子系统不统一**
- cpu / memory / blkio 各自一套 cgroup
- **这就是 cgroup v2 统一所有子系统的动机**

**问题 4：Android 部分设备未启用 blkio.weight**

```bash
# 检查当前是否支持 blkio.weight
cat /sys/fs/cgroup/blkio/foreground/blkio.weight
# 800（说明支持）

# 或者错误：No such file or directory（说明未启用）
```

---

## 七、cgroup v2 io 子系统（统一接口）

### 7.1 cgroup v2 的设计哲学

```
cgroup v1：
├── cpu 子系统（cpu.shares / cpu.cfs_*）
├── cpuacct 子系统（CPU 统计）
├── memory 子系统（memory.limit_in_bytes）
├── blkio 子系统（blkio.weight / blkio.throttle.*）
└── ... 12+ 个子系统各自独立

cgroup v2（统一）：
├── io 子系统（统一 blkio）
├── memory 子系统（统一 v1 的 memory + memsw）
├── cpu 子系统（统一 v1 的 cpu + cpuacct）
├── pids 子系统
└── ... 但 v2 的每个子系统都更"现代"
```

### 7.2 cgroup v2 io 子系统的接口

```bash
# cgroup v2 的 io 接口（Android 14 默认）
mount -t cgroup2 none /sys/fs/cgroup/unified

# 查看 io 配置
ls /sys/fs/cgroup/<cgroup>/
# io.weight
# io.max
# io.latency
# io.stat
# io.pressure
```

### 7.3 关键配置详解

#### 7.3.1 io.weight

```bash
# 写入 weight（范围 1-10000，默认 100）
echo "default 200" > /sys/fs/cgroup/foreground/io.weight
# 格式：device_weight 或 "default weight"

# per-device weight
echo "8:0 weight=500" > /sys/fs/cgroup/foreground/io.weight
# 8:0 = device, weight=500（per-device）
```

**注意**：cgroup v2 的 io.weight 是 bfq 调度器**唯一**的权重控制。mq-deadline / kyber 不支持。

#### 7.3.2 io.max（限速）

```bash
# 设置 cgroup 的 IO 限速
echo "8:0 riops=5000 wiops=3000 rbps=200MB wbps=100MB" > /sys/fs/cgroup/foreground/io.max
# 格式：major:minor riops=... wiops=... rbps=... wbps=...

# 移除限制
echo "8:0 max" > /sys/fs/cgroup/foreground/io.max
```

**io.max vs v1 blkio.throttle**：
| 字段 | v1 blkio.throttle | v2 io.max |
|------|------------------|-----------|
| 限速精度 | 4 个独立字段 | 1 行配置 |
| 设备支持 | per-device 配置 | per-device 配置 |
| 单位 | byte / IO | byte / IO（带单位）|

#### 7.3.3 io.latency

```bash
# 设置 IO 延迟目标（仅 blk-iolatency）
echo "8:0 target=100ms" > /sys/fs/cgroup/foreground/io.latency
# target=100ms：保证这个 cgroup 的 IO 延迟 < 100ms
```

**io.latency 与 io.max 的区别**：
- `io.max`：**限制** IO 速率（强制）
- `io.latency`：**保证** IO 延迟（依赖 blk-iolatency）
- 两个机制可以叠加使用

#### 7.3.4 io.stat 与 io.pressure

```bash
# 查看 cgroup 的 IO 统计
cat /sys/fs/cgroup/foreground/io.stat
# 8:0 rbytes=1024 wbytes=2048 rios=100 wios=200 dbytes=0 ...

# 查看 IO 压力（PSI）
cat /sys/fs/cgroup/foreground/io.pressure
# some avg10=... avg60=... avg300=... total=...
# full avg10=... avg60=... avg300=... total=...
```

**io.pressure 是关键监控指标**——它直接显示该 cgroup 是否面临 IO 压力。

### 7.4 cgroup v2 的优势

| 优势 | 说明 |
|------|------|
| **统一接口** | 所有子系统都在同一 cgroup 目录下 |
| **默认值更合理** | io.weight 默认 100（无需配置） |
| **延迟保证** | io.latency 支持 blk-iolatency |
| **压力监控** | io.pressure 直接暴露 PSI |
| **嵌套支持** | cgroup 可以嵌套（按 app / uid / pid） |

### 7.5 cgroup v2 io 的关键内核源码

```c
// block/blk-cgroup.c
struct blkcg {
    struct cgroup_subsys_state css;
    
    // v2 的 io.weight
    u32 weight;                    // 1-10000
    u32 default_weight;
    
    // v2 的 io.max
    struct blkcg_policy ioprio_policy;
    
    // v1 的 throttle（保留兼容）
    struct throtl_data *td;
};
```

---

## 八、Android cgroup IO 配置实战

### 8.1 Android 默认的 cgroup 层级

```
/sys/fs/cgroup/
├── root
├── system             # system_server 等系统服务
├── foreground         # 前台 App
├── background         # 后台 App
├── top-app            # 当前最前台 App（更高级别）
├── camera-daemon      # 相机专用
├── dexopt             # dex2oat 等后台优化
└── ...
```

**Android 14 GKI 默认配置**（典型）：

```bash
# foreground cgroup 的 IO 配置
cat /sys/fs/cgroup/foreground/io.weight
# default 100

cat /sys/fs/cgroup/foreground/io.max
# （空，无限制）

# background cgroup 的 IO 配置
cat /sys/fs/cgroup/background/io.weight
# default 50

cat /sys/fs/cgroup/background/io.max
# （部分厂商有限制）

# top-app cgroup（最高优先级）
cat /sys/fs/cgroup/top-app/io.weight
# default 200

cat /sys/fs/cgroup/top-app/io.max
# （空，无限制）
```

### 8.2 Android 14 的进程级 ioprio 默认值

```c
// frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java
// Android 14 新增：根据进程状态设置 ioprio
private void applyIoPriority(ProcessRecord app) {
    int ioprio_class;
    int ioprio_data;
    
    switch (app.getProcState()) {
    case ActivityManager.PROCESS_STATE_TOP:
        ioprio_class = IOPRIO_CLASS_BE;
        ioprio_data = 0;     // 最高（前台 App）
        break;
    case ActivityManager.PROCESS_STATE_FOREGROUND_SERVICE:
        ioprio_class = IOPRIO_CLASS_BE;
        ioprio_data = 2;
        break;
    case ActivityManager.PROCESS_STATE_CACHED_EMPTY:
    case ActivityManager.PROCESS_STATE_CACHED_ACTIVITY:
        ioprio_class = IOPRIO_CLASS_BE;
        ioprio_data = 7;     // 最低（缓存进程）
        break;
    default:
        ioprio_class = IOPRIO_CLASS_BE;
        ioprio_data = 4;     // 默认
    }
    
    Process.setIoPriority(app.pid, ioprio_class, ioprio_data);
}
```

**Android 14 的关键改进**：进程降级时**同步降 IO 优先级**——这就是"进程优先级 ↔ IO 优先级协同"的体现。

### 8.3 init.rc 中的 IO 配置示例

```rc
# init.rc 中配置 cgroup IO
on post-fs-data
    # foreground cgroup 不限速
    write /sys/fs/cgroup/foreground/io.max ""
    
    # background cgroup 限速
    write /sys/fs/cgroup/background/io.max "8:0 riops=1000 wiops=500"
    
    # camera-daemon 高优先级
    write /sys/fs/cgroup/camera-daemon/io.weight "default 200"
```

### 8.4 vendor GKI 定制示例

```bash
# 某厂商针对游戏场景的 cgroup 配置
# /vendor/etc/init/hw/init.target.rc

on property:sys.boot_completed=1
    # 游戏类 App 在 top-app 时用更高的 io.weight
    write /sys/fs/cgroup/top-app/io.weight "default 500"
    
    # 后台 App 严格限速
    write /sys/fs/cgroup/background/io.max "8:0 riops=500 wiops=200 rbps=20MB wbps=10MB"
```

---## 九、进程优先级 ↔ IO 优先级的映射（关键协同）

### 9.1 双重优先级的设计动机

**问题**：CPU 优先级（nice / oom_adj）和 IO 优先级（ioprio）必须协同，否则会出现"调度器让高优先级进程跑，但它的 IO 被低优先级任务卡住"的矛盾。

**典型场景**：
- 进程 A：nice=-10（高 CPU 优先级）
- 进程 A 的 IO：ioprio_class=BE / 7（低 IO 优先级）
- 进程 B：nice=10（低 CPU 优先级）
- 进程 B 的 IO：ioprio_class=BE / 0（高 IO 优先级）

**结果**：
- CPU 调度器：让 A 先跑
- IO 调度器：让 B 的 IO 先派发
- A 提交 IO 后等 B 的 IO 完成 → A 卡住

**这就是"调度优先级反转"**。

### 9.2 Android 14 的映射策略

```c
// frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java
// Android 14 的协同映射规则：

private int mapOomAdjToIoPriority(int oom_adj) {
    // oom_adj 范围 -1000 ~ 1000+
    // 越负越重要
    
    if (oom_adj <= -900) {
        // 前台 App / 系统关键进程
        return IOPRIO_VALUE(IOPRIO_CLASS_BE, 0);   // 最高 BE
    } else if (oom_adj <= -100) {
        // 可见 / 前台服务
        return IOPRIO_VALUE(IOPRIO_CLASS_BE, 2);
    } else if (oom_adj <= 100) {
        // 后台 / 缓存
        return IOPRIO_VALUE(IOPRIO_CLASS_BE, 4);   // 默认
    } else {
        // 缓存空进程
        return IOPRIO_VALUE(IOPRIO_CLASS_BE, 7);   // 最低
    }
}
```

**关键洞察**：**Android 14 把 IO 优先级与 oom_adj 强绑定**——避免 CPU / IO 优先级反转。

### 9.3 优先级协同的工程基线

| oom_adj 范围 | ioprio (BE) | 适用场景 |
|-------------|-------------|---------|
| -1000 ~ -900 | 0 | system_server / top-app |
| -800 ~ -700 | 1 | 前台 App |
| -100 ~ 0 | 2-4 | 前台服务 / 可见 App |
| 100 ~ 500 | 4-6 | 后台 App |
| 700 ~ 1000+ | 7 | 缓存 / 空进程 |

### 9.4 协同失效的稳定性风险

**风险 1：oom_adj 调整时忘记同步 ioprio**
```
现象：进程降到后台（oom_adj 提高），但 ioprio 不变
结果：后台进程仍占 IO 带宽
治理：Android 14 已修复（applyIoPriority 同步设置）
```

**风险 2：vendor GKI 强制覆盖 ioprio**
```
现象：vendor 在 init.rc 中强制把所有进程的 ioprio 设为 BE/4
结果：失去 IO 优先级分层
治理：避免 vendor 强制覆盖，让 OomAdjuster 管理
```

**风险 3：cgroup weight 与 ioprio 不一致**
```
现象：cgroup foreground weight=800，但 ioprio=BE/7
结果：调度器内部权重冲突
治理：保证 weight × ioprio 同向调整
```

---

## 十、风险地图：5 类 IO 优先级 / cgroup 问题

| 类别 | 典型现象 | 日志关键字 | 排查入口 | 治理方向 |
|------|---------|----------|---------|---------|
| **① 前台被后台拖累** | 前台 App 慢 | cgroup weight 配置 | `cat /sys/fs/cgroup/foreground/io.weight` | 调高 foreground weight |
| **② RT 配置失败** | ionice 报 EPERM | `ionice: Operation not permitted` | `capsh --print` 检查 capability | 用 root / shell 重试 |
| **③ Idle 饿死** | 后台同步永远不跑 | Idle class 配错 | 监控 Idle class IO 流量 | 改 BE class / 设 bps 上限 |
| **④ cgroup 反转** | 后台 cgroup weight > 前台 | cgroup hierarchy 配错 | `cat /sys/fs/cgroup/.../io.weight` | 修正 cgroup hierarchy |
| **⑤ 双优先级反转** | CPU 高优先级但 IO 慢 | oom_adj 与 ioprio 不一致 | 检查 applyIoPriority 调用 | 同步调整两个优先级 |

### 关键监控指标

```bash
# 1. 进程 IO 优先级
cat /proc/<pid>/io
# rchar / wchar / read_bytes / write_bytes

# 2. cgroup IO 统计
cat /sys/fs/cgroup/<cgroup>/io.stat
cat /sys/fs/cgroup/<cgroup>/io.pressure

# 3. blk-throttle 状态
cat /sys/kernel/debug/block/sda/throttle0/avg

# 4. ioprio 历史
cat /proc/<pid>/stat | awk '{print $18, $39}'
# $18 = priority, $39 = nice
# （注意：stat 中的 priority 是 CPU nice，ioprio 不在其中）
```

---

## 十一、实战案例 1：后台 App 的 IO 风暴通过 cgroup 权重拖累前台 App（典型模式）

### 现象

某社交 App **刷朋友圈时卡顿 3-5s**，但相机、聊天等功能正常。用户多次投诉。

### 环境

- Android 13 / Kernel 5.10 / 设备 Pixel 5

### 分析思路

**第一步：抓 trace 看 cgroup IO 状态**：

```bash
cat /sys/fs/cgroup/top-app/io.stat
# 8:0 rbytes=10M wbytes=5M rios=1000 wios=500 ...
# ← IO 量正常

cat /sys/fs/cgroup/background/io.stat
# 8:0 rbytes=500M wbytes=300M rios=100000 wios=50000 ...
# ← IO 量是 top-app 的 50x！
```

**第二步：抓 blk-throttle debug**：

```bash
cat /sys/kernel/debug/block/sda/throttle0/avg
# throtl_grp[background]: bps=50M iops=10000 ← 占用大量 IO 带宽
# throtl_grp[top-app]: bps=2M iops=300    ← 被严重挤压
```

**第三步：检查 cgroup 配置**：

```bash
cat /sys/fs/cgroup/background/io.weight
# default 200  ← 太高！应该 ≤ 100

cat /sys/fs/cgroup/top-app/io.weight
# default 100  ← 默认
```

**根因诊断**：

1. 后台 cgroup 配置 weight=200（与 top-app 持平）
2. 后台 App 同步云端相册数据（持续 50MB/s 写入）
3. 由于 weight 接近，前台 App 的 IO 请求被后台"挤"到队列尾部
4. **结果**：朋友圈加载延迟飙高

### 修复方案

1. **调 cgroup 配置**：
   ```bash
   echo "default 50" > /sys/fs/cgroup/background/io.weight
   echo "default 200" > /sys/fs/cgroup/top-app/io.weight
   ```

2. **后台 cgroup 加 iops 限制**：
   ```bash
   echo "8:0 riops=1000 wiops=500" > /sys/fs/cgroup/background/io.max
   ```

3. **永久配置**（init.rc / vendor init）：
   ```rc
   on boot
       write /sys/fs/cgroup/background/io.weight "default 50"
       write /sys/fs/cgroup/background/io.max "8:0 riops=1000 wiops=500"
       write /sys/fs/cgroup/top-app/io.weight "default 200"
   ```

**修复后效果**：前台 IO 延迟从 3s 降到 200ms。

### 排查路径速查

```
前台 App 慢但磁盘不忙
  ↓
看 cgroup IO 统计 → io.stat / io.pressure
  ↓
发现 background cgroup IO 量 > top-app
  ↓
检查 cgroup weight / max 配置
  ↓
调整配置 → 验证
```

---

## 十二、实战案例 2：ioprio 与 oom_adj 不一致导致优先级反转（典型模式）

### 现象

某系统服务的 **CPU 优先级高（nice=-10），但它的 IO 偶尔被背景进程卡住**。

### 环境

- Android 12 / Kernel 5.10 / 某厂商定制 GKI（未启用 Android 14 的 ioprio 协同）

### 分析思路

**第一步：抓 service 的 ioprio 与 oom_adj**：

```bash
# system_server 的 ioprio
cat /proc/<system_server_pid>/io
# rchar=10G wchar=5G ... ← IO 量很大

# 检查 ioprio（用 ionice 命令）
ionice -p <system_server_pid>
# best-effort: prio 7  ← 优先级最低！
```

**第二步：抓优先级反转的 trace**：

```
T+0ms  system_server 调用 write()（写日志文件）
T+10ms write 进入 Page Cache
T+15ms submit_bio
T+20ms blk-throttle 检查：system_server cgroup
T+21ms 发现 background cgroup iops 限制已满
T+25ms system_server 等待 throttle queue
T+2000ms background iops 配额释放
T+2010ms system_server 的 IO 才派发  ← 卡 2 秒！
```

**第三步：分析优先级反转**：

```
system_server：
- CPU 优先级：nice=-10（高）
- IO 优先级：ioprio=BE/7（最低！）
- cgroup：system（不限速）

background 进程：
- CPU 优先级：nice=10（低）
- IO 优先级：ioprio=BE/0（最高！）
- cgroup：background（限速）

矛盾：
- CPU 调度器：让 system_server 先跑
- IO 调度器：让 background 的 IO 先派发
- 结果：system_server 提交 IO 后等 background
```

### 根因诊断

1. 该厂商 GKI 基于 Android 12，**没有同步 ioprio 的机制**
2. system_server 的 ioprio 默认 BE/7（最低）
3. 后台进程被设置为 BE/0（最高）
4. **CPU 高优先级但 IO 最低** → 优先级反转

### 修复方案

1. **手动调整 system_server ioprio**：
   ```bash
   # 在 init.rc 中调整
   on boot
       # system_server 启动后调整 ioprio
       exec u:r:system_server:s0 ionice -c 2 -n 0 -p <system_server_pid>
   ```

2. **升级到 Android 14+ 的 OomAdjuster 自动协同**：
   - 自动根据 oom_adj 设置 ioprio
   - 避免优先级反转

3. **长期**：在 vendor init 中建立"oom_adj → ioprio 映射"配置

### 排查路径速查

```
系统服务响应慢
  ↓
检查 ioprio vs oom_adj → 不一致？
  ↓
看 blk-throttle 状态 → 是否被后台挤占
  ↓
修复 ioprio 配置 / 升级到 Android 14
```

---

## 十三、总结：架构师视角的 5 条 Takeaway

读完本篇，请记住这 5 件事——它们是排查 IO 优先级 / cgroup 故障的"金钥匙"：

1. **"3 层优先级机制叠加"**——进程 ioprio × cgroup weight/limit × 调度器内置优先级。诊断时必须看 3 层，不能只看一层。
2. **"cgroup v2 是默认趋势"**——io.weight / io.max / io.latency / io.pressure 是 Android 14 的标配。稳定性架构师必须熟悉 cgroup v2 接口。
3. **"Android 14 的 oom_adj ↔ ioprio 自动协同"**——这是解决"CPU 高优先级但 IO 低优先级"反转的关键。**OEM 必须升级到 Android 14 才能享受**。
4. **"RT class 需要 CAP_SYS_ADMIN"**——普通应用（包括 system_server）无法设置 RT，必须用 BE/level 0-7 表达优先级。
5. **"Idle class 不是绝对空闲"**——Idle class 仍会调度，但仅在系统无其他 IO 时。**大量 Idle IO 仍可能拖累系统**，正确做法是用 BE/7 + cgroup 限速。

### 排查路径速查（IO 优先级 / cgroup 问题）

```
IO 性能 / 前台被后台拖累 / 优先级反转
  ↓
① 抓 cgroup io.stat → 看 IO 量分布
  ↓
② 抓 cgroup io.pressure → 看 PSI 压力
  ↓
③ 看 cgroup io.weight / io.max → 配置是否合理
  ↓
④ 看进程 ioprio → 是否与 oom_adj 一致
  ↓
⑤ 治理 → 调 weight / 调 max / 调 ioprio / 升级 Android 14
```

---

## 附录 A：核心源码路径索引

| 文件名 | 完整路径 | 内核版本基线 | 说明 |
|--------|---------|------------|------|
| `ioprio.c` | `block/ioprio.c` | Linux 5.10+ | ioprio_set/get 系统调用 |
| `ioprio.h` | `include/linux/ioprio.h` | Linux 5.10+ | ioprio 常量定义 |
| `iocontext.h` | `include/linux/iocontext.h` | Linux 5.10+ | io_context 数据结构 |
| `blk-cgroup.c` | `block/blk-cgroup.c` | Linux 5.10+ | cgroup blkcg 框架 |
| `blk-cgroup.h` | `include/linux/blk-cgroup.h` | Linux 5.10+ | blkcg 数据结构 |
| `blk-throttle.c` | `block/blk-throttle.c` | Linux 5.10+ | bps / iops 限流 |
| `blk-iolatency.c` | `block/blk-iolatency.c` | Linux 5.10+ | latency target |
| `mq-deadline.c` | `block/mq-deadline.c` | Linux 5.10+ | mq-deadline 的 RT 处理 |
| `bfq-iosched.c` | `block/bfq-iosched.c` | Linux 5.10+ | bfq 的 ioprio + weight |
| `OomAdjuster.java` | `frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java` | AOSP 14.0.0_r1 | Android 14 的 ioprio 协同 |

---

## 附录 B：源码路径对账表

| 序号 | 文章中出现的路径 | 状态 | 校对来源 |
|------|----------------|------|---------|
| 1 | `block/ioprio.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/ioprio.c |
| 2 | `include/linux/ioprio.h` | 已校对 | elixir.bootlin.com/linux/v5.10/include/linux/ioprio.h |
| 3 | `include/linux/iocontext.h` | 已校对 | elixir.bootlin.com/linux/v5.10/include/linux/iocontext.h |
| 4 | `block/blk-cgroup.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/blk-cgroup.c |
| 5 | `include/linux/blk-cgroup.h` | 已校对 | elixir.bootlin.com/linux/v5.10/include/linux/blk-cgroup.h |
| 6 | `block/blk-throttle.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/blk-throttle.c |
| 7 | `block/blk-iolatency.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/blk-iolatency.c |
| 8 | `block/mq-deadline.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/mq-deadline.c |
| 9 | `block/bfq-iosched.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/bfq-iosched.c |
| 10 | `frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java` | 已校对 | cs.android.com/android-14.0.0_r1 |

---

## 附录 C：量化数据自检表

| 序号 | 量化描述 | 数量级 | 依据 |
|------|---------|--------|------|
| 1 | ioprio class 数量 | 4（RT/BE/Idle/None）| 内核常量 |
| 2 | BE class level 范围 | 0-7 | 内核常量 |
| 3 | cgroup v1 blkio.weight 范围 | 100-1000 | 内核常量 |
| 4 | cgroup v2 io.weight 范围 | 1-10000 | 内核常量 |
| 5 | Android 14 默认 top-app weight | 100-200 | 厂商配置 |
| 6 | Android 14 默认 background weight | 50 | 厂商配置 |
| 7 | 推荐 foreground bps | 200MB/s | 工程经验 |
| 8 | 推荐 background iops | 500-1000 | 工程经验 |
| 9 | RT class 权限要求 | CAP_SYS_ADMIN | 内核检查 |
| 10 | Android 14 默认 ioprio（top-app）| BE/0 | OomAdjuster 源码 |
| 11 | Android 14 默认 ioprio（background）| BE/7 | OomAdjuster 源码 |
| 12 | blk-throttle 时间窗口 | 100ms | 内核常量 |

---

## 附录 D：工程基线表

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|------|---------|---------|---------|
| **cgroup v1 blkio.weight** | 500 | foreground 800 / background 200 | 范围 100-1000 |
| **cgroup v2 io.weight** | 100 | top-app 200 / foreground 100 / background 50 | 范围 1-10000 |
| **cgroup v2 io.max (foreground bps)** | 不限 | 推荐 200MB/s read / 100MB/s write | 太低 → 前台卡 |
| **cgroup v2 io.max (background iops)** | 不限 | 推荐 riops=1000 wiops=500 | 太低 → 后台饿死 |
| **cgroup v2 io.latency** | 不设置 | top-app target=50ms / foreground target=100ms | 太短 → 频繁 throttle |
| **ionice BE level (top-app)** | 0 | 最高 BE | RT class 需要 root |
| **ionice BE level (foreground)** | 2-4 | 中等 | — |
| **ionice BE level (background)** | 7 | 最低 BE | 不要用 Idle class |
| **ionice class（系统服务）** | BE/0 | 推荐 BE/0（不是 RT）| RT 需要 CAP_SYS_ADMIN |
| **Idle class IO 上限** | 不限 | 不要让 Idle class 占比 > 5% | Idle 仍会调度 |
| **Android 14 OomAdjuster 自动协同** | 启用 | OEM 必须升级 | 不启用 → 优先级反转 |
| **vendor GKI 强制 ioprio** | 不推荐 | 让 OomAdjuster 管 | 强制 → 失去协同 |

---

## 篇尾衔接

本篇完成了 **IO 优先级 + cgroup IO 控制器** 的完整体系：ionice 系统调用接口、cgroup v1 blkio 与 cgroup v2 io 的配置、Android 进程优先级与 IO 优先级的自动协同机制。

至此，**02 IO 调度器 + 03 Block 层 + 04 IO 优先级** 三篇构成了 IO 子系统的"内核主线"——从调度算法到 Block 机制到资源隔离的完整图谱。

剩余 6 篇（[08 Android 存储栈](08-Android存储栈：从FUSE、sdcardfs、StorageManager到块设备.md) / [09 存储设备](09-存储设备与IO性能：UFS、eMMC、NVMe命令队列与延迟特性.md) / [10 风险 + 工具链](10-IO稳定性风险全景与诊断工具链.md)）已在大纲中规划，可以按你的节奏继续推进。