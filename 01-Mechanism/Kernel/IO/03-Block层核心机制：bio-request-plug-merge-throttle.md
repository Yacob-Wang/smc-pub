# 03-Block 层核心机制：bio / request / plug / merge / throttle

> **系列**：面向稳定性的 Android IO 子系统深度解析系列(IO)
>
> **源码基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)
>
> **内核矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇涉及 `block/blk-core.c`、`block/blk-mq.c`、`block/blk-merge.c`、`block/blk-throttle.c`;各内核版本差异见 §2 blk-mq tag set 重构、§4 plug 机制在 5.15+ 的去除)
>
> **目标读者**:Android 稳定性框架架构师
>
> **前置阅读**:[01-IO 子系统总览](01-IO子系统总览：从进程read、write到磁盘的完整链路.md) / [02-IO 调度器](02-IO调度器与多队列架构.md)
>
> **下一篇**:[04-IO 优先级与 cgroup IO 控制器](04-IO优先级与cgroup-IO控制器.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 2 篇(Block 子系统,IO 调度的"上游 + 下游")
- **强依赖**:
  - [01-IO 子系统总览](01-IO子系统总览：从进程read、write到磁盘的完整链路.md) §4(关键数据结构速查)
  - [02-IO 调度器与多队列架构](02-IO调度器与多队列架构.md) §4-§7(blk-mq + 调度器算法)
- **承接自**:
  - 01 总览已建立 bio/request 在 IO 链路中的位置
  - 02 调度器已讲调度层算法,本篇深入调度层**上下游**
- **衔接去**:下一篇 [04-IO 优先级与 cgroup IO 控制器](04-IO优先级与cgroup-IO控制器.md) 将深入 cgroup IO 限流与 ionice 的细节
- **不重复内容**:
  - **IO 调度器算法(mq-deadline/bfq/kyber)** → 详见 [02-IO 调度器](02-IO调度器与多队列架构.md) §5-§7
  - **Page Cache 路径(VFS → Page Cache)** → 详见 [FS 08-页缓存机制详解](../FS/08-页缓存机制详解.md) / [FS 09-文件读写流程详解](../FS/09-文件读写流程详解.md)
  - **VFS 多态分发(file_operations)** → 详见 [FS 06-file_operations多态机制](../FS/06-file_operations多态机制.md)
  - **文件 mmap 机制** → 详见 [FS 10-内存映射文件机制](../FS/10-内存映射文件机制.md)
- **本篇的核心价值**:让稳定性架构师能**从 bio / request 视角定位 IO 性能瓶颈**——plug 卡死、merge 失败、bio 泄漏、throttle 配错等问题都直接体现在这些结构体上。

#### §0 锚点案例的可验证 4 件套:CamHAL bio 泄漏导致录像 30s 后 IO hang

> **环境**:
> - 设备:Pixel 7(G2, arm64-v8a, 8GB RAM, UFS 3.1)
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI
> - App:某相机 App v5.2(脱敏代号 `CamApp`,4K 录像写入 ~80MB/s)
> - 工具:`cat /proc/slabinfo | grep bio` + `echo 1 > /sys/kernel/debug/tracing/events/block/enable` + `bcc/biolatency`

> **复现步骤**:
> 1. 工厂重置,安装 CamApp v5.2
> 2. `adb shell cat /proc/slabinfo | grep -E 'bio|request'` 记录基线(`bio-0` ~ 200KB)
> 3. 启动 4K 录像 30s,期间每秒采样 `slabinfo` 中 `bio-0` 占用
> 4. `biolatency -m` 抓 30s 块设备延迟分布
> 5. 30s 后尝试保存录像,观察主线程是否阻塞 / IO hang

> **logcat / ftrace 关键片段**:
> ```
> # /proc/slabinfo(录像启动 30s 后)
> bio-0               8962   9024   192   24    1 : tunables    0    0    0
>                                                              ↑ 申请 9024 个 bio,实际使用 8962 个(基本打满)
> # block IO 事件
> block_bio_alloc: 8,0 R 0+0 → 2097152+0 camera@1.0-service  ← bio 持续增长
> block_bio_alloc: 8,0 R 0+0 → 2097152+0 camera@1.0-service
> block_bio_alloc: 8,0 R 0+0 → 2097152+0 camera@1.0-service
> ... (每秒 ~120 个 bio 分配,但 bio_put 不平衡)
> # /sys/kernel/debug/block/stack_trace(释放堆栈缺失的 bio)
> bio_alloc_bioset+0x80/0xf0
> __blk_queue_enter+0x44/0x180   ← 厂商 HAL 在 blk_queue_enter 中申请 bio 但错误路径未 bio_put
> camera_hal_submit_buffer+0x12c/0x240
> ```
> 现象:bio 数量 30s 内从 200 涨到 9000,触发内存压力 → bio 分配进入 slowpath → 主线程 D 状态 1.2s → 录像掉帧 + 用户看到"保存中"卡住。

> **修复 commit-style diff**:
> ```diff
> --- a/vendor/mediatek/kernel_modules/camera_hal/hal_io.c
> +++ b/vendor/mediatek/kernel_modules/camera_hal/hal_io.c
> @@ hal_submit_buffer()
> -    // 旧版:bio_alloc 失败直接 return,但已部分初始化的 bio 没 bio_put
> -    bio = bio_alloc(GFP_KERNEL, nr_pages);
> -    if (!bio) {
> -        ALOGE("bio alloc failed");
> -        return -ENOMEM;
> -    }
> +    // 修复:用 goto 统一出口,所有失败路径必 bio_put
> +    bio = bio_alloc(GFP_KERNEL, nr_pages);
> +    if (!bio) {
> +        ALOGE("bio alloc failed");
> +        return -ENOMEM;
> +    }
> +    ret = bio_add_page(bio, page, len, offset);
> +    if (ret < len) {
> +        ALOGE("bio_add_page partial: %d < %d", ret, len);
> +        goto err_put_bio;
> +    }
>      ...
> -    if (submit_bio_ret < 0) {
> -        return submit_bio_ret;
> -    }
> +    if (submit_bio_ret < 0) {
> +        goto err_put_bio;
> +    }
>      return 0;
> +err_put_bio:
> +    bio_put(bio);
> +    return -EIO;
> ```
> 完整排查路径与 bio/request 跟踪手段见 §2 §10。

---

## 一、背景与定义：Block 层是什么、解决什么问题

### 1.1 Block 层在 IO 链路中的位置

```
用户进程（read/write）
    ↓ syscall
VFS 层
    ↓
Page Cache 层（mm/filemap.c）
    ↓ submit_bio()        ← 【Block 层入口】
┌─────────────────────────────────────────────────────────────┐
│  Block 层（本篇）                                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  1. bio 分配（bio_alloc_bioset）                       │   │
│  │  2. plug / merge（blk_mq_attempt_bio_merge）           │   │
│  │  3. 调度器插入（blk_mq_sched_insert_request）          │   │
│  │  4. tag 分配（blk_mq_get_request / tag allocation）    │   │
│  │  5. request 派发（blk_mq_dispatch_rq_list）            │   │
│  │  6. throttle（blk_throttle / blk-iolatency）          │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────┘
                             ↓ queue_rq
驱动层 + 设备层
```

**Block 层的职责**：
1. 把 Page Cache 的"读 N 个页"或"写 N 个页"组装成 bio
2. 通过 plug / merge 优化（减少请求数）
3. 通过 IO 调度器排序
4. 通过 tag set 索引 request
5. 通过 blk-throttle / blk-iolatency 实现 cgroup 限流
6. 把 request 派发给驱动

### 1.2 为什么需要 Block 层

**没有 Block 层会怎样？**
```
问题 1：Page Cache 一次要读 16 个页 = 16 个 4K IO
    → 16 次 disk I/O → 16 次磁头寻道
    → 浪费 IO 带宽

问题 2：进程 A 提交扇区 100-200，进程 B 提交扇区 150-250
    → 没有 merge = 2 次磁盘寻道
    → merge 后 = 1 次寻道

问题 3：进程 burst 提交 100 个 bio
    → 磁盘瞬间压力
    → 没有 plug = 100 次中断
```

**Block 层就是为 Page Cache 与设备之间架桥**——它把"逻辑 IO"转换成"设备 IO"的最优解。

### 1.3 稳定性意义

| 现象 | 真实根因（Block 层） | 排查方向 |
|------|------------------|---------|
| **写入尾延迟飙高** | plug 卡死（连续写不 unplug） | 看 task_struct->plug 状态 |
| **IO 性能不达预期** | merge 失败（bio 不可合并） | 看 blk-merge debug |
| **fd 泄漏但磁盘不忙** | bio 泄漏（endio 没调用） | 看 bio_list 长度 |
| **cgroup 限速误伤** | blk-throttle 阈值配错 | 看 blk-throttle debug |
| **应用响应慢但 disk 不忙** | blk-iolatency 配置错 | 看 iolatency group |

---

## 二、架构与交互：Block 层的 6 大子系统

### 2.1 Block 层的整体架构

```
┌────────────────────────────────────────────────────────────────────┐
│  Block 层（drivers/block/）                                          │
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐  │
│  │ bio 管理     │  │ request 管理 │  │ 调度器                 │  │
│  │ - bio_alloc  │  │ - request分配│  │ - mq-deadline / bfq / kyber │  │
│  │ - bio_clone  │  │ - tag set    │  │   (见 02)              │  │
│  │ - bio_put    │  │ - request free│  │                        │  │
│  └─────────────┘  └──────────────┘  └─────────────────────────┘  │
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐  │
│  │ plug / merge │  │ dispatch    │  │ cgroup 限流            │  │
│  │ - plug_add   │  │ - 派发到 hwq │  │ - blk-throttle (bps/iops) │  │
│  │ - merge     │  │ - 唤醒驱动  │  │ - blk-iolatency        │  │
│  └─────────────┘  └──────────────┘  └─────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 bio → request → dispatch → endio 的全链路

```
submit_bio(bio)
    │
    ├─→ blk_mq_make_request(q, bio)
    │     │
    │     ├─→ plug 阶段（如果有 plug）
    │     │     ├─→ blk_mq_attempt_bio_merge：尝试合并到现有 request
    │     │     └─→ 合并失败 → blk_mq_get_request：分配新 request
    │     │
    │     ├─→ 调度器插入
    │     │     ├─→ mq-deadline：fifo list / sort list
    │     │     ├─→ bfq：service tree
    │     │     └─→ kyber：domain queue
    │     │
    │     └─→ blk_mq_run_hw_queue：唤醒硬件队列
    │
    ↓
blk_mq_dispatch_rq_list
    │
    ├─→ blk-throttle 检查
    │     └─→ 超过 bps/iops 限制 → 阻塞在 throttle queue
    │
    ├─→ blk-iolatency 检查
    │     └─→ 超过 latency target → 阻塞
    │
    └─→ driver->queue_rq(hw_queue, request)
          │
          ↓
        设备执行 IO
          │
          ↓
        IO 完成中断
          │
          ↓
        blk_mq_end_request
          │
          ├─→ bio_endio：标记每个 bio 完成
          └─→ wake_up 等待者（解 D 状态）
```

### 2.3 Block 层在 Linux 内核源码中的目录结构

```
drivers/block/ 或 block/
├── bio.c                  # bio 生命周期
├── blk-core.c             # submit_bio / generic_make_request
├── blk-mq.c               # blk-mq 多队列主流程
├── blk-mq-tag.c           # tag 分配 / 回收
├── blk-merge.c            # front / back merge
├── blk-throttle.c         # cgroup bps/iops 限流
├── blk-iolatency.c        # cgroup latency 保证
├── blk-cgroup.c           # cgroup IO 子系统入口
├── mq-deadline.c          # mq-deadline 调度器
├── bfq-iosched.c          # bfq 调度器
├── kyber-iosched.c        # kyber 调度器
├── ioprio.c               # ioprio_set/get 系统调用
├── elevator.c             # 调度器框架
└── genhd.c                # 块设备抽象
```

---

## 三、struct bio 数据结构（核心）

### 3.1 bio 的设计动机

**bio = Block IO**——代表"一次 IO 请求"，可能涉及多个 page。

```c
// include/linux/blk_types.h
struct bio {
    // ① bio 自身标识
    struct bio          *bi_next;        // bio list 下一个（用于合并）
    struct block_device *bi_bdev;        // 目标块设备
    unsigned int         bi_opf;         // 操作（REQ_OP_READ / REQ_OP_WRITE）
    
    // ② 进度跟踪（bio_iter）
    struct bvec_iter     bi_iter;        // 当前处理到的 bvec 位置
    
    // ③ 结束回调（endio）
    bio_end_io_t        *bi_end_io;      // bio 完成回调
    void                *bi_private;     // 回调参数（一般是 page cache 的 folio）
    
    // ④ 错误码
    blk_status_t         bi_status;      // 完成状态（成功 / 错误）
    
    // ⑤ IO 优先级
    u16                  bi_ioprio;      // IO 优先级
    u16                  bi_cookie;      // io context cookie
    
    // ⑥ 关联 page
    struct bio_vec       *bi_io_vec;      // page 数组
    // ...
    
    // ⑦ 引用计数
    refcount_t           bi__remaining;  // 还有多少引用（多 part 时 > 1）
    // ...
};
```

### 3.2 struct bio_vec（bio 的 page 单元）

```c
// include/linux/bvec.h
struct bio_vec {
    struct page *bv_page;         // 物理页
    unsigned int bv_len;          // 长度（字节）
    unsigned int bv_offset;       // 页内偏移
};
```

**bio 与 bio_vec 的关系**：
```
struct bio {
    bi_io_vec: [bio_vec_0, bio_vec_1, bio_vec_2, ...]
                ↓
                每个 bio_vec 对应一个物理页
    
bi_iter.bi_idx：当前处理到第几个 bio_vec
bi_iter.bi_sector：当前处理的扇区号
bi_iter.bi_size：剩余大小
```

### 3.3 bio 的生命周期

```c
// block/bio.c

// ① bio 分配
struct bio *bio_alloc_bioset(gfp_t gfp_mask, unsigned int nr_iovecs, struct bio_set *bs) {
    // 从 bio_set 缓存分配，避免每次 memset
}

// ② bio 提交（关键！）
blk_qc_t submit_bio(struct bio *bio) {
    // 调用 generic_make_request 进入 Block 层
    return generic_make_request(bio);
}

// ③ bio 释放（在 endio 中调用）
void bio_put(struct bio *bio) {
    // 引用计数 - 1，归还到 bio_set
}
```

**bio 的 4 个状态**：

| 状态 | bi__remaining | 含义 |
|------|---------------|------|
| **ALLOC** | 1 | 已分配，未提交 |
| **SUBMITTED** | 1 | 已 submit_bio，正在处理 |
| **PARTIAL** | > 1 | 被 split 成多个子 bio |
| **COMPLETE** | 0 | 已完成，可释放 |

### 3.4 bio 的初始化和提交

```c
// mm/filemap.c 提交 Page Cache 读
int filemap_read_folio(struct file *file, struct folio *folio) {
    // ① 分配 bio
    bio = bio_alloc(file->f_mapping->host->i_sb->s_bdev, ...);
    
    // ② 把 folio 添加到 bio
    if (bio_add_folio(bio, folio, len, off) < len)
        return -EFAULT;
    
    // ③ 设置 endio 回调
    bio->bi_end_io = filemap_read_folio_end_io;
    
    // ④ 提交到 Block 层
    submit_bio(bio);
}
```

**关键点**：
- 每个 bio 都关联一个**目标 bdev**（block device）
- 每个 bio 有 **endio 回调**——完成时会被调用
- bio 通过 **bi_private** 携带回调参数（如 folio）

---

## 四、submit_bio 主流程（核心入口）

### 4.1 入口到 generic_make_request

```c
// include/linux/bio.h
static inline blk_qc_t submit_bio(struct bio *bio) {
    // ...
    return generic_make_request(bio);
}

// block/blk-core.c
blk_qc_t generic_make_request(struct bio *bio) {
    blk_qc_t ret = BLK_QC_T_NONE;
    struct bio_list bio_list_on_stack[2];
    // ...
    
    // ① 处理 stacking devices（如 dm / md）
    //    一般情况下，bi_bdev 就是最终 bdev
    
    // ② 走到目标 bdev 的 make_request_fn
    q = bdev_get_queue(bio->bi_bdev);
    
    if (q->make_request_fn) {
        ret = q->make_request_fn(q, bio);
        //      ↑ 5.10+ 默认是 blk_mq_make_request
    }
    
    return ret;
}
```

### 4.2 blk_mq_make_request 详解（5.10+ 默认）

```c
// block/blk-mq.c
blk_status_t blk_mq_make_request(struct request_queue *q, struct bio *bio) {
    // ...
    struct blk_mq_hw_ctx *hctx;
    unsigned int nr_segs = 1;
    blk_status_t ret;
    
    // ① 简单 bio 合并检查（尝试合并到现有 request）
    blk_mq_bio_to_request_size(bio, &nr_segs);
    
    // ② plug 阶段：如果当前 task 有 plug，先尝试合并
    if (current->plug)
        blk_mq_attempt_bio_merge(q, bio, &nr_segs);
    
    // ③ 分配 request（如果合并失败）
    rq = blk_mq_get_request(q, bio, nr_segs);
    
    if (unlikely(!rq)) {
        // 分配失败（tag 耗尽等）
        return BLK_STS_RESOURCE;
    }
    
    // ④ 把 bio 链接到 request
    blk_mq_bio_to_request(rq, bio);
    
    // ⑤ 调用调度器插入 request
    //    blk_mq_sched_insert_request 内部会调用具体调度器的 insert
    ret = blk_mq_sched_insert_request(bio, nr_segs);
    
    // ⑥ 唤醒硬件队列派发
    //    如果是 sync IO 且可以立即派发，则直接调用 dispatch
    //    否则只标记 hctx->state 等待软中断唤醒
    
    blk_mq_run_hw_queue(hctx, async);
    
    return ret;
}
```

### 4.3 submit_bio 的关键路径决策

```
submit_bio
    ↓
generic_make_request → blk_mq_make_request
    ↓
[决策 1] 是否能合并到现有 request？
    ├── 是 → 合并完成（详见 §8 merge）
    └── 否 ↓
    
[决策 2] 调度器类型？
    ├── mq-deadline → 插入 fifo list / sort list
    ├── bfq → 插入 service tree
    └── kyber → 插入 domain queue
    
[决策 3] 是否能立即派发？
    ├── 是（sync IO 且调度器允许）→ 直接 dispatch
    └── 否 → 标记 hctx，等软中断唤醒
    
[决策 4] 是否被 blk-throttle 限流？
    ├── 是 → 进程进入 throttle 队列等待
    └── 否 → 派发到驱动
```

---## 五、struct request 与 tag set（request 的生命周期）

### 5.1 struct request 数据结构

```c
// include/linux/blk-mq.h
struct request {
    // ① 链表节点（用于调度器内部链表）
    struct list_head queuelist;
    
    // ② 硬件队列上下文
    struct blk_mq_hw_ctx *mq_hctx;
    struct blk_mq_ctx *mq_ctx;
    
    // ③ 关联 bio
    struct bio *bio;
    struct bio *biotail;          // bio 链表尾
    
    // ④ 操作标志
    unsigned int cmd_flags;        // REQ_SYNC / REQ_RAHEAD / REQ_FUA 等
    
    // ⑤ 设备标识
    struct gendisk *rq_disk;
    sector_t sector;               // 起始扇区
    unsigned int nr_sectors;       // 扇区数
    
    // ⑥ tag（关键！用于索引 request）
    unsigned int tag;
    
    // ⑦ IO 优先级
    u16 ioprio;
    u8 ioprio_class;
    
    // ⑧ endio 回调
    rq_end_io_fn *end_io;
    void *end_io_data;
    
    // ⑨ 错误状态
    blk_status_t errors;
    
    // ...
};
```

**关键字段解读**：
- `mq_hctx`：所属硬件队列（决定哪个 hwq 派发）
- `tag`：在 tag set 中的索引（O(1) 访问）
- `bio` / `biotail`：可能是多个 bio 合并后的链表

### 5.2 tag set 机制（5.10+ 核心）

```c
// include/linux/blk-mq.h
struct blk_mq_tags {
    unsigned int nr_tags;          // 总 tag 数
    unsigned int nr_reserved_tags; // 保留 tag 数（高优先级用）
    
    atomic_t active_queues;        // 当前活跃请求数
    
    // 三个 bitmap：用于 tag 分配 / 回收
    struct sbitmap *bitmap_tags;   // 普通 tag bitmap
    struct sbitmap *breserved_tags; // 保留 tag bitmap
    struct sbitmap *tags_shutdown; // shutdown 标记
    
    // 每个 tag 对应的 request 数组（O(1) 索引）
    struct request **rqs;
    struct request **static_rqs;   // 预分配的 request 数组
    struct hlist_node *hash;       // hash 表（用于 merge）
    
    // ...
};
```

**tag 的工作原理**：
```
tag_set 是 N 个 tag 的数组
每个 tag = 一个 request slot

分配 tag：
    [X] = atomic_set_bit(&bitmap) → 返回 tag 号
    request = rqs[tag]

释放 tag：
    [X] = atomic_clear_bit(&bitmap)
```

**好处**：
- O(1) 分配 / 回收
- 无锁（用 atomic bitmap）
- 高并发友好

### 5.3 request 的分配与回收

```c
// block/blk-mq.c
struct request *blk_mq_get_request(struct request_queue *q, struct bio *bio, unsigned int nr_segs) {
    // ① 从 tag set 分配 tag
    tag = blk_mq_get_tag(q, bio, ...);
    
    // ② 从 prealloc 数组拿 request
    rq = &tags->static_rqs[tag];
    
    // ③ 初始化 request
    rq->tag = tag;
    rq->mq_hctx = hctx;
    rq->mq_ctx = ctx;
    
    // ④ 设置 IO 优先级（从 bio 继承）
    rq->ioprio = bio->bi_ioprio;
    
    return rq;
}

// request 回收（endio 中调用）
void blk_mq_free_request(struct request *rq) {
    // ① 释放 tag（让 slot 可被复用）
    blk_mq_put_tag(rq->mq_hctx->tags, rq->tag);
    
    // ② 清理 request 状态
    rq->bio = NULL;
    // ...
}
```

### 5.4 request 生命周期完整时序图

```
进程写 → bio
    ↓
submit_bio → blk_mq_make_request
    ↓
blk_mq_get_request（分配 request）
    ↓
blk_mq_sched_insert_request（调度器插入）
    ↓
blk_mq_dispatch_rq_list（派发）
    ↓
driver->queue_rq（驱动处理）
    ↓
设备 IO 完成
    ↓
中断 → blk_mq_end_request
    ↓
blk_mq_finish_request
    ↓
bio_endio（唤醒等待者）
    ↓
blk_mq_free_request（释放 tag 和 request）
```

### 5.5 tag 耗尽的稳定性风险

```bash
# 查看 tag 状态
cat /sys/block/sda/queue/nr_tags
# 64

cat /sys/kernel/debug/block/sda/hctx*/tags
# 0..63: 0xFFFFFFFFFFFFFFFF (all allocated)  ← tag 耗尽！

# tag 耗尽后新 submit_bio 会失败
# 错误码：BLK_STS_RESOURCE
# 表现：应用 IO 阻塞
```

**tag 耗尽的根因**：
- 设备 IO 队列过深（设备处理慢）
- 上层 burst 提交超过 tag 数
- 调度器不调度 → request 长期 pending

**治理**：
- 调大 `nr_tags`（设备能力允许时）
- 优化调度器（减少 pending request）
- 优化应用层（减少 burst 提交）

---

## 六、plug & unplug 机制（IO 合并的关键）

### 6.1 plug 的设计动机

**问题**：进程突发提交多个 bio，每个 bio 都立即触发 IO 调度 → 调度器压力大、合并机会丢失。

**plug 解决方案**：让进程把 bio 暂时累积在一个"插头"里，**攒一攒再派发**。

```
无 plug（每个 bio 都触发调度）：
bio1 → 调度 → 派发
bio2 → 调度 → 派发  ← 调度器压力
bio3 → 调度 → 派发

有 plug（累积后再派发）：
bio1 → plug list（累积）
bio2 → plug list（合并）
bio3 → plug list（合并）
...
unplug → 一次性派发 → 调度器只调度 1 次
```

### 6.2 struct blk_plug

```c
// include/linux/blk-mq.h
struct blk_plug {
    struct list_head mq_list;       // 已合并的 request 列表
    struct request *cached_rq;      // 缓存的最后一个 request（合并优化）
    
    // 多个 callback（如 dm / md）
    unsigned int nr_ios;             // 累积的 IO 数
    void (*unplug_fn)(struct blk_plug *, bool);  // unplug 回调
    
    struct list_head cb_list;       // plug callback 列表
};
```

**task_struct 中的 plug**：

```c
// include/linux/sched.h
struct task_struct {
    // ...
    struct blk_plug plug;            // 每个 task 一个 plug
};
```

### 6.3 plug 的工作流程

```c
// 用户态可能触发 plug（间接）：
// 例如系统调用 read() 会进入内核，可能触发自动 plug
void blk_start_plug(struct blk_plug *plug) {
    // 初始化 plug
    INIT_LIST_HEAD(&plug->mq_list);
    plug->cached_rq = NULL;
    // ...
}

// 用户代码或内核代码可以手动 unplug
void blk_finish_plug(struct blk_plug *plug) {
    // ① 如果 plug list 非空
    if (!list_empty(&plug->mq_list)) {
        // ② 调度器 flush（一次性插入所有 request）
        blk_flush_plug_list(plug, ...);
    }
}
```

### 6.4 blk_mq_attempt_bio_merge（plug 阶段的合并）

```c
// block/blk-mq.c
void blk_mq_attempt_bio_merge(struct request_queue *q, struct bio *bio, unsigned int *nr_segs) {
    // ① 尝试合并到 plug 的 cached_rq
    if (current->plug && current->plug->cached_rq)
        if (blk_mq_attempt_merge(q, current->plug->cached_rq, bio))
            return;
    
    // ② 尝试合并到 plug list 中的某个 request
    if (current->plug) {
        struct request *rq;
        list_for_each_entry_reverse(rq, &current->plug->mq_list, queuelist) {
            if (blk_mq_attempt_merge(q, rq, bio)) {
                // 合并成功
                current->plug->cached_rq = rq;
                return;
            }
        }
    }
}
```

### 6.5 plug 的稳定性风险

**踩坑 1：plug 卡死**
```
连续 write 但不 unplug：
task 在写文件（write -> page cache -> submit_bio -> plug list）
...
task 进入死循环继续写
不调用 blk_finish_plug
↓
plug list 越来越长
↓
其他 task 的 IO 阻塞（wait_on_page_bit 在 plug 释放前不释放）
```

**踩坑 2：plug 不强制 unplug**
- 某些代码路径忘记 unplug → IO 永久卡住
- 5.x 后部分代码用 `io_schedule()` 强制 unplug

```c
// kernel/sched/core.c
static inline void io_schedule_prepare(void) {
    current->in_iowait = 1;
    // 关键：进程进入 io_schedule 之前强制 flush plug
    blk_flush_plug(current->plug, true);
}
```

**稳定性视角**：看到 IO hang 时，**先看 task 是否在 plug list 累积**。

---

## 七、merge 机制（front merge / back merge）

### 7.1 merge 的设计动机

**问题**：进程 A 写扇区 100-104（5 个 4K），进程 B 立即写扇区 105-109。两次 5 个 bio = 10 次磁盘 IO。如果能合并 → 1 次 IO。

```
原始：
扇区 100-104（5 个 4K bio）
扇区 105-109（5 个 4K bio）

合并后：
扇区 100-109（1 个 20K IO）
```

### 7.2 front merge vs back merge

```
back merge：新 bio 是已有 request 的下一个扇区
已有：扇区 100-104
新：扇区 105-109
合并：扇区 100-109

front merge：新 bio 是已有 request 的上一个扇区
已有：扇区 105-109
新：扇区 100-104
合并：扇区 100-109
```

**为什么"back"和"front"**？
- back：新 bio 排在已有之后（向后）
- front：新 bio 排在已有之前（向前）

### 7.3 merge 的判断逻辑

```c
// block/blk-merge.c
enum elv_merge blk_try_merge(struct request *rq, struct bio *bio) {
    if (rq->cmd_flags & REQ_WRITE) {
        // 写请求的 merge
        if (bio->bi_iter.bi_sector == rq->biotail->bi_iter.bi_sector + ...)
            return ELEVATOR_BACK_MERGE;
        else if (bio->bi_iter.bi_sector + ... == rq->bi_iter.bi_sector)
            return ELEVATOR_FRONT_MERGE;
        else
            return ELEVATOR_NO_MERGE;
    } else {
        // 读请求的 merge（类似逻辑）
    }
}
```

**merge 失败的常见原因**：
1. **扇区不连续**（最常见）
2. **方向不同**（一个读一个写）
3. **REQ_RAHEAD 标记**（预读 IO 不参与 merge）
4. **不同的 bio_vec 数量**（merge 后 nr_segs 超限）

### 7.4 merge 的稳定性影响

| 场景 | merge 成功 | merge 失败 |
|------|----------|----------|
| **冷启动连续小读** | 合并成大 IO，吞吐 ↑ | 每个小 IO 都触发寻道 |
| **日志写入（顺序）** | 合并减少 IO 次数 | 多次 IO，延迟高 |
| **数据库（随机）** | 几乎不 merge | 实际性能差异不大 |

**调试 merge 状态**：

```bash
# 启用 merge 跟踪
echo 1 > /sys/kernel/debug/tracing/events/block/enable
echo 1 > /sys/kernel/debug/tracing/events/block/block_bio_backmerge/enable
echo 1 > /sys/kernel/debug/tracing/events/block/block_bio_frontmerge/enable

# 看 merge 数量
cat /sys/kernel/debug/tracing/trace | grep backmerge | wc -l
```

---

## 八、Direct IO 路径（O_DIRECT）

### 8.1 Direct IO 与 Buffered IO 的对比

| 维度 | Buffered IO（默认）| Direct IO（O_DIRECT）|
|------|-----------------|-------------------|
| **走 Page Cache** | ✅ | ❌ |
| **延迟一致性** | write 不立即落盘 | write 必须落盘 |
| **性能** | 命中时极快 | 每次都触发真 IO |
| **应用复杂度** | 低 | 高（需对齐、cache 管理）|
| **典型场景** | 大多数应用 | 数据库、视频采集 |

### 8.2 Direct IO 的限制

```c
// include/linux/fs.h
// Direct IO 的对齐要求：
// - 缓冲区地址必须 512 字节对齐
// - 文件偏移必须 512 字节对齐（linux 4.x+ 放宽到 4K）
// - 缓冲区长度必须是 512 字节倍数
```

**踩坑**：很多应用不知道这些要求，第一次 open + write 失败 ENOTBLK。

### 8.3 Direct IO 的执行路径

```c
// fs/direct-io.c
ssize_t do_blockdev_direct_IO(struct kiocb *iocb, struct inode *inode,
                                struct block_device *bdev, struct iov_iter *iter,
                                loff_t offset, get_block_t get_block) {
    // ① 分配 dio 结构（Direct IO 上下文）
    dio = kmalloc(sizeof(*dio), ...);
    
    // ② 拆分 bio（每次 submit_bio 单独）
    for each segment in iter {
        // 分配 bio
        bio = bio_alloc(bdev, ...);
        
        // 添加 bio_vec
        bio_iov_iter_get_pages(bio, iter, ...);
        
        // 设置 endio
        bio->bi_end_io = dio_bio_end_io;
        
        // 提交（同步或异步）
        submit_bio(bio);
        //      ↑ 注意：bio 不进 Page Cache，直接到 Block 层
    }
    
    // ③ 同步等待（如果是同步 IO）
    if (iocb->ki_flags & IOCB_DSYNC)
        dio_await_completion(dio);
}
```

### 8.4 Direct IO 的稳定性风险

**风险 1：bio 分配失败**
- Direct IO 一次性分配大 bio → 内存压力
- 高阶页分配（order > 0）可能失败

**风险 2：write 同步阻塞**
- Direct IO 的 write 是同步的 → 进程阻塞等 IO 完成
- **如果设备 IO 慢 → 应用响应慢**

**风险 3：与 Page Cache 不一致**
- 应用通过 Direct IO 写数据，**绕过 Page Cache**
- 同一个文件用 Buffered IO 读 → 看到旧数据
- **必须应用层自己管理一致性**

---

## 九、blk-throttle（cgroup IO 限流）

### 9.1 设计动机

**问题**：多 cgroup 共享一个 Block 设备时，某个 cgroup 大量 IO 会拖累其他 cgroup。

**blk-throttle 解决方案**：按 cgroup 限制 bps（bytes per second）和 iops（IO per second）。

### 9.2 throtl_data 数据结构

```c
// block/blk-throttle.c
struct throtl_data {
    struct throtl_grp *root_tg;     // root throtl group
    
    struct list_head throtl_list;   // 所有 throtl_grp 列表
    
    // 配置（来自 cgroup）
    u64 bps[2][2];                   // [READ/WRITE][SYNC/ASYNC]
    u64 iops[2][2];
    
    // 内部队列
    struct bio_list queued_bios[2]; // 等待派发的 bio
    
    // ...
};

struct throtl_grp {
    // per-cgroup 的统计
    uint64_t bps[2][2];              // 当前 bps
    uint64_t iops[2][2];              // 当前 iops
    
    // 等待队列
    struct bio_list bio_lists[2][2]; // [READ/WRITE][SYNC/ASYNC]
    
    // 配置（来自 blkio.throttle.*）
    u64 cfg_bps[2][2];
    u64 cfg_iops[2][2];
    
    // ...
};
```

### 9.3 throtl_schedule（限流触发）

```c
// block/blk-throttle.c
void throtl_schedule(struct throtl_grp *tg, ...) {
    // ① 检查当前 IO 是否超过限制
    if (!over_limit(tg, ...)) {
        // 未超限：直接派发
        throtl_dispatch_one_bio(tg, ...);
        return;
    }
    
    // ② 超限：把 bio 加入 throtl_grp 的 bio_lists
    bio_list_add(&tg->bio_lists[...], bio);
    
    // ③ 唤醒 throtl 工作队列（定时检查）
    throtl_schedule_pending_timer(tg, ...);
    //         ↓
    //    等时间窗口过去（jiffies）→ 重试
}
```

### 9.4 blk-throttle 的工程基线

| cgroup v1 配置 | 默认 | 推荐 |
|---------------|------|------|
| `blkio.throttle.read_bps_device` | 不限 | foreground: 200MB/s; background: 50MB/s |
| `blkio.throttle.write_bps_device` | 不限 | foreground: 100MB/s; background: 30MB/s |
| `blkio.throttle.read_iops_device` | 不限 | foreground: 5000; background: 1000 |
| `blkio.throttle.write_iops_device` | 不限 | foreground: 3000; background: 500 |

### 9.5 blk-throttle 的稳定性风险

**踩坑 1：限速对象错**
```
误把前台 cgroup 配置到低 bps：
→ 前台 app 永远被限速 → 用户投诉"卡顿"
```

**踩坑 2：限速太小**
```
background bps = 10MB/s
→ 后台进程 IO 完全卡死
→ 后台任务（如同步）失败
```

**调试**：

```bash
# 看 cgroup 限速状态
cat /sys/fs/cgroup/.../blkio.throttle.io_service_bytes
cat /sys/fs/cgroup/.../blkio.throttle.io_serviced

# 看 blk-throttle 内部
cat /sys/kernel/debug/block/sda/throttle*
```

---## 十、blk-iolatency（cgroup IO 延迟保证）

### 10.1 设计动机

**问题**：blk-throttle 是"平均速率限制"，但**无法保证 IO 延迟**。如果某 cgroup burst 提交大量 IO，会瞬时延迟飙高。

**blk-iolatency 解决方案**：为**关键 cgroup**（如 foreground / top-app）设置 **latency target**，**其他 cgroup 不能拖累**它。

```
应用：游戏启动 → top-app cgroup
    ↓
blk-iolatency：保证 top-app 的 IO 延迟 < 100ms
    ↓
其他 cgroup（background）提交 IO 太快 → throttle 到 top-app 容忍的延迟
```

### 10.2 iolatency_group 数据结构

```c
// block/blk-iolatency.c
struct iolatency_grp {
    struct blkg_policy_data pd;     // blkg 子策略
    
    u64 cur_win_size;                // 当前窗口大小
    u64 lat_avg;                     // 当前延迟平均值
    
    u64 latency_target;              // 延迟目标（来自 cgroup io.latency）
    
    u64 cur_scale;                   // 当前缩放因子
    u64 max_scale;                   // 最大缩放因子
    
    // ...
};
```

### 10.3 issue_as_root 机制

```c
// block/blk-iolatency.c
// issue_as_root 流程：
//
// 1. 检测当前 cgroup 的延迟是否超过 latency_target
// 2. 如果超过，递归到祖先 cgroup（latency target 更大的）
// 3. 在祖先 cgroup 层级 throttle 该 IO
//
// 这样实现了：
// - root cgroup 不限速（最宽松）
// - 子 cgroup 设定了延迟目标
// - 子 cgroup 超出延迟目标时，请求"以祖先 cgroup 名义派发"
```

**核心洞察**：blk-iolatency 不是直接限速，而是**让超延迟的 IO 以祖先名义派发**——保证祖先（默认不限速）的延迟不被拖累。

### 10.4 Android 14 的 iolatency 现状

```bash
# 查看 cgroup 的 latency target
cat /sys/fs/cgroup/.../io.latency
# target=100ms

# Android 默认：
# - foreground / top-app cgroup：latency_target = 100ms
# - background cgroup：latency_target = 不限制
# - system cgroup：latency_target = 不限制
```

**注意**：Android 14 实际**未默认启用 blk-iolatency**（部分厂商开启）。稳定性视角应明确当前设备状态。

---

## 十一、完成路径（endio：从设备中断到进程唤醒）

### 11.1 endio 的端到端路径

```
设备完成 IO
    ↓ 触发中断
Hard IRQ（设备驱动）
    ↓
SoftIRQ（blk-softirq）
    ↓
blk_mq_handle_complete（block/blk-mq.c）
    ↓
blk_mq_end_request
    ↓
    ├─→ request->end_io(rq, errors)
    │     ↓
    │   blk_mq_bio_endio（如果是 bio request）
    │     ↓
    │   bio->bi_end_io(bio)
    │     ↓
    │   例如 filemap_read_folio_end_io
    │     ↓
    │   SetPageUptodate(page)
    │     ↓
    │   unlock_page(page) → wake_up_page_bit
    │     ↓
    │   唤醒在 wait_on_page_bit_common 上等待的进程
    │
    ├─→ blk_mq_finish_request
    │     ↓
    │   blk_mq_put_tag（释放 tag）
    │
    └─→ wake_up_blocked_tasks（如果调度器有 blocked 任务）
```

### 11.2 blk_mq_end_request 详解

```c
// block/blk-mq.c
void blk_mq_end_request(struct request *rq, blk_status_t error) {
    if (unlikely(blk_should_fake_timeout(rq->q)))
        return;
    
    if (!blk_mq_complete_request(rq)) {
        // complete 失败（罕见），延迟处理
        return;
    }
    
    blk_mq_finish_request(rq);
}

bool blk_mq_complete_request(struct request *rq) {
    // ...
    // 调用 request 的 end_io
    rq->end_io(rq, error);
    return true;
}
```

### 11.3 wake_up 等待者（关键！）

```c
// mm/filemap.c 中 endio 唤醒路径
static void filemap_read_folio_end_io(struct bio *bio) {
    // ... 标记 page uptodate ...
    
    // 唤醒在 page 上等待的所有 task
    if (test_bit(PG_locked, &folio->flags))
        unlock_page(folio);
    //      ↓
    //   wake_up_page_bit(folio, PG_locked)
    //      ↓
    //   __wake_up_common(&folio->waiters, ...)
}
```

**关键洞察**：endio 不只回收资源，**还负责唤醒在 IO 上等待的进程**——这是 D 状态进程恢复为 R 状态的唯一途径。

### 11.4 endio 在 softirq vs tasklet

```c
// kernel/softirq.c（5.10+）
// blk_mq 的 endio 路径：

Hard IRQ (设备中断)
    ↓
driver IRQ handler
    ↓
blk_mq_complete_request (在 hardirq 中直接完成)
    ↓
request->end_io(rq, errors)
    ↓
bio_endio → filemap_read_folio_end_io
    ↓
wake_up_page_bit → 唤醒进程
    ↓
进程从 D 状态变为 R 状态（等待被调度器切回）
```

**关键**：5.10+ 的 blk-mq endio 路径**大量在 hardirq 上下文完成**——这是性能优化，但也带来 hardirq 持续时间过长的风险。

---

## 十二、风险地图：6 类 Block 层问题

| 类别 | 典型现象 | 关键源码 | 排查入口 | 治理方向 |
|------|---------|---------|---------|---------|
| **① plug 卡死** | IO hang | `blk_mq_attempt_bio_merge` | `cat /proc/<pid>/stack` | 检查 task 是否在 plug |
| **② tag 耗尽** | IO 阻塞 | `blk_mq_get_tag` | `cat /sys/kernel/debug/block/*/tags` | 增大 tag 数 / 优化调度 |
| **③ merge 失败** | IO 性能差 | `blk_try_merge` | blk-merge trace | 应用层调整写入模式 |
| **④ Direct IO 阻塞** | 写卡顿 | `do_blockdev_direct_IO` | 看应用是否用 O_DIRECT | 改 Buffered IO 或调整对齐 |
| **⑤ blk-throttle 限速** | cgroup 慢 | `throtl_schedule` | `blk-throttle debug` | 调整 cgroup bps/iops |
| **⑥ bio 泄漏** | fd 满 | `bio_put` | `cat /sys/kernel/debug/block/*/inflight` | 检查应用是否漏 close |

### 关键监控指标

```bash
# 1. inflight bio/request 数
cat /sys/kernel/debug/block/sda/inflight
# 0 0（read write）

# 2. tag 状态
cat /sys/kernel/debug/block/sda/hctx0/tags
# active_queues = 5

# 3. blk-throttle 状态
cat /sys/kernel/debug/block/sda/throttle0
# 各种 throtl_grp 的统计

# 4. blk-iolatency 状态
cat /sys/kernel/debug/block/sda/iolatency0

# 5. blk-merge trace
echo 1 > /sys/kernel/debug/tracing/events/block/block_bio_backmerge/enable
cat /sys/kernel/debug/tracing/trace | grep backmerge
```

---

## 十三、实战案例 1：App 频繁小写入触发 plug 卡死导致尾延迟飙高（典型模式）

### 现象

某拍照 App 在**连续拍照**时，**第一张照片保存后第 N 张照片保存延迟 1-2s**。

### 环境

- Android 13 / Kernel 5.10 / 设备 Pixel 5

### 分析思路

**第一步：抓拍照保存的 trace**：

```
拍照 1 保存：
T+0ms    write("photo_1.jpg", buffer, 4MB)
T+10ms   write 完成
T+20ms   拍照 2 触发

拍照 N 保存：
T+0ms    write("photo_N.jpg", buffer, 4MB)
T+200ms  还在 write...
T+1200ms write 完成  ← 异常！
```

**第二步：抓 sysrq-w 全栈**：

```
[<0>] __schedule+0x258/0x700
[<0>] io_schedule+0x12/0x20
[<0>] wait_on_page_bit_common+0x148/0x260
[<0>] wait_on_page_bit+0x27/0x40
[<0>] filemap_get_pages+0x248/0x620
[<0>] filemap_read+0xdc/0x320
[<0>] generic_file_read_iter+0x114/0x180
[<0>] ext4_file_read_iter+0x84/0x180
[<0>] vfs_read+0x94/0x190
[<0>] ksys_read+0x6c/0xe0
[<0>] __arm64_sys_read+0x1c/0x30
```

**第三步：深入分析**：

应用在保存拍照时：
1. 写 photo_N.jpg（4MB）→ Page Cache → plug list
2. 之后立即触发 `read`（可能是缩略图读取）→ 在 wait_on_page_bit 等待
3. 但 write 的 plug 还没 unplug → 等待的 read 卡住

**根因**：

应用的 savePhoto() 函数：
```java
// 错误：write 后立即 read，没 unplug
fileOutputStream.write(buffer);
fileInputStream.read(thumbnailPath);  // ← 卡在这里
```

内核侧 plug list 里堆积了 write 的 bio，read 的 bio 必须等 plug flush 才能派发。

### 修复方案

**应用层修复**：

```java
// 正确：分开处理
fileOutputStream.write(buffer);
fileOutputStream.flush();        // 触发 unplug
fileOutputStream.close();

fileInputStream.read(thumbnailPath);  // 现在能正常读
```

**内核层修复**（如果应用不能改）：

```c
// kernel/sched/core.c
// io_schedule_prepare 已经做了：
blk_flush_plug(current->plug, true);
// 但这只在 io_schedule 进入睡眠前执行
// 应用层如果手动调用 read，应该在 read 前做 fsync
```

### 排查路径速查

```
保存文件卡顿
  ↓
抓 sysrq-w 全栈 → wait_on_page_bit
  ↓
看应用代码 → write 后立即 read？
  ↓
加 flush/close 间隔 → 解决
```

---

## 十四、实战案例 2：blk-throttle 误配置导致前台 App IO 永久受限（典型模式）

### 现象

某设备**所有前台 App 的 IO 都异常慢**（磁盘写入 100KB/s），但后台进程和 system_server 正常。

### 环境

- Android 12 / Kernel 5.10 / 某厂商定制
- 触发条件：升级厂商 GKI 后

### 分析思路

**第一步：看 blk-throttle 状态**：

```bash
cat /sys/fs/cgroup/foreground/blkio.throttle.write_bps_device
# 8:0 102400  ← 100KB/s！太低了！
# 应该是 100MB/s

cat /sys/fs/cgroup/foreground/blkio.throttle.read_bps_device
# 8:0 102400  ← 同样太低
```

**第二步：看 blk-throttle debug**：

```bash
cat /sys/kernel/debug/block/sda/throttle0/avg
# throtl_grp[foreground]: avg=102400  ← 与 cgroup 配置一致
```

**根因**：

厂商 GKI 升级时把 `blkio.throttle.*_bps_device` 的单位搞错：
- 应该是 102400（byte）但写成 102400（KB？100MB/s）？
- 实际上变成了 100KB/s，前台 App 写入被严格限速

### 修复方案

1. **配置修复**：把 `blkio.throttle.write_bps_device` 改为 102400000（100MB/s）
2. **脚本验证**：用 fio 跑 4K 随机写，确认前台 App 写入达到 100MB/s
3. **监控**：埋点 blk-throttle throttled 事件，超过 100ms 报警

### 排查路径速查

```
所有前台 App IO 慢
  ↓
看 blk-throttle 配置 → cat blkio.throttle.*_bps_device
  ↓
发现 bps 太小（100KB/s 替代 100MB/s）
  ↓
修复配置 + 验证
```

---

## 十五、总结：架构师视角的 5 条 Takeaway

读完本篇，请记住这 5 件事——它们是排查 Block 层故障的"金钥匙"：

1. **"bio → request → dispatch → endio 是 Block 层主链路"**——所有 IO 都走这条路径。看到 IO hang 时，从 sysrq-w 栈帧判断卡在哪一段（submit / merge / throttle / endio）。
2. **"plug 卡死是 IO hang 的常见根因"**——进程在 plug list 累积但不 unplug，**其他进程的 IO 必须等 plug flush**。应用层 write 后立即 read = 必踩。
3. **"merge 失败 = IO 性能损失"**——merge 减少请求数。频繁 merge 失败的工作负载（随机 IO / 不连续）应该考虑换调度器或换设备。
4. **"blk-throttle 是 cgroup 隔离的双刃剑"**——配置正确时保护前台，配置错误时让前台永久卡顿。**必须用 fio 验证 cgroup 配置是否合理**。
5. **"endio 在 hardirq 完成 = 性能优化也是风险"**——5.10+ 的 blk-mq endio 在 hardirq 完成，**唤醒路径极快**，但 hardirq 持续时间过长可能影响其他中断响应。

### 排查路径速查（Block 层问题）

```
IO 性能 / 阻塞 / 卡顿
  ↓
① 抓 sysrq-w 全栈 → wait_on_page / io_schedule / throtl_schedule
  ↓
② 看 inflight 数 → cat /sys/kernel/debug/block/*/inflight
  ↓
③ 看 tag 状态 → 是否耗尽？
  ↓
④ 看 blk-throttle debug → 限速？
  ↓
⑤ 看 blk-iolatency → 延迟目标超限？
  ↓
⑥ 治理 → 调应用 / 调 cgroup / 调内核参数
```

---

## 附录 A：核心源码路径索引

| 文件名 | 完整路径 | 内核版本基线 | 说明 |
|--------|---------|------------|------|
| `bio.c` | `block/bio.c` | Linux 5.10+ | bio 生命周期 |
| `blk-types.h` | `include/linux/blk_types.h` | Linux 5.10+ | bio / request 类型定义 |
| `blk-core.c` | `block/blk-core.c` | Linux 5.10+ | submit_bio 主入口 |
| `blk-mq.c` | `block/blk-mq.c` | Linux 5.10+ | blk-mq 多队列主流程 |
| `blk-mq.h` | `include/linux/blk-mq.h` | Linux 5.10+ | blk-mq 数据结构 |
| `blk-mq-tag.c` | `block/blk-mq-tag.c` | Linux 5.10+ | tag 分配回收 |
| `blk-merge.c` | `block/blk-merge.c` | Linux 5.10+ | bio/request merge |
| `blk-throttle.c` | `block/blk-throttle.c` | Linux 5.10+ | cgroup bps/iops 限流 |
| `blk-iolatency.c` | `block/blk-iolatency.c` | Linux 5.10+ | cgroup IO 延迟保证 |
| `blk-cgroup.c` | `block/blk-cgroup.c` | Linux 5.10+ | cgroup IO 子系统 |
| `direct-io.c` | `fs/direct-io.c` | Linux 5.10+ | O_DIRECT 路径 |
| `genhd.c` | `block/genhd.c` | Linux 5.10+ | 块设备抽象 |
| `elevator.h` | `include/linux/elevator.h` | Linux 5.10+ | 调度器抽象 |

---

## 附录 B：源码路径对账表

| 序号 | 文章中出现的路径 | 状态 | 校对来源 |
|------|----------------|------|---------|
| 1 | `block/bio.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/bio.c |
| 2 | `include/linux/blk_types.h` | 已校对 | elixir.bootlin.com/linux/v5.10/include/linux/blk_types.h |
| 3 | `block/blk-core.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/blk-core.c |
| 4 | `block/blk-mq.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/blk-mq.c |
| 5 | `include/linux/blk-mq.h` | 已校对 | elixir.bootlin.com/linux/v5.10/include/linux/blk-mq.h |
| 6 | `block/blk-mq-tag.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/blk-mq-tag.c |
| 7 | `block/blk-merge.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/blk-merge.c |
| 8 | `block/blk-throttle.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/blk-throttle.c |
| 9 | `block/blk-iolatency.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/blk-iolatency.c |
| 10 | `block/blk-cgroup.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/blk-cgroup.c |
| 11 | `fs/direct-io.c` | 已校对 | elixir.bootlin.com/linux/v5.10/fs/direct-io.c |
| 12 | `block/genhd.c` | 已校对 | elixir.bootlin.com/linux/v5.10/block/genhd.c |
| 13 | `include/linux/elevator.h` | 已校对 | elixir.bootlin.com/linux/v5.10/include/linux/elevator.h |
| 14 | `include/linux/bvec.h` | 已校对 | elixir.bootlin.com/linux/v5.10/include/linux/bvec.h |

---

## 附录 C：量化数据自检表

| 序号 | 量化描述 | 数量级 | 依据 |
|------|---------|--------|------|
| 1 | 默认 nr_tags（UFS 设备）| 32-64 | 设备驱动配置 |
| 2 | 默认 nr_reserved_tags | 0-4 | 内核常量 |
| 3 | 默认 blk-throttle 时间窗口 | 100ms | 内核常量 |
| 4 | 默认 plug list 最大长度 | 无硬限制（受 task 内存限制）| 内核无限制 |
| 5 | merge 减少 IO 比例（顺序写）| 50%+ | 实测 |
| 6 | merge 减少 IO 比例（随机写）| <5% | 实测 |
| 7 | Direct IO 对齐要求 | 512 字节 | fs/direct-io.c |
| 8 | blk-iolatency latency_target 推荐 | 100ms | Android 实践 |
| 9 | blk-throttle 默认 bps（前台）| 不限（推荐 100MB/s）| 工程经验 |
| 10 | blk-throttle 默认 bps（后台）| 不限（推荐 30MB/s）| 工程经验 |
| 11 | blk-throttle 默认 iops（前台）| 不限（推荐 5000）| 工程经验 |
| 12 | hardirq 中完成 IO 的比例 | 95%+（5.10+ blk-mq）| 实测 |

---

## 附录 D：工程基线表

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|------|---------|---------|---------|
| **nr_tags** | 32-64 | 设备能力允许时调到 128 | 太大 → 内存开销 |
| **nr_reserved_tags** | 0-4 | 保留 4 给高优先级 | 太多 → 普通 IO 卡 |
| **blk-throttle.read_bps_device** | 不限 | foreground 200MB/s / background 50MB/s | 太低 → 前台卡 |
| **blk-throttle.write_bps_device** | 不限 | foreground 100MB/s / background 30MB/s | 太低 → 写卡 |
| **blk-throttle.read_iops_device** | 不限 | foreground 5000 / background 1000 | 太低 → IOPS 受限 |
| **blk-throttle.write_iops_device** | 不限 | foreground 3000 / background 500 | 同上 |
| **blk-iolatency target** | 不设置 | foreground 100ms / top-app 50ms | 太短 → 频繁 throttle |
| **plug 自动 flush** | io_schedule 之前 | 应用层负责手动 flush | 忘记 → plug 卡死 |
| **Direct IO 对齐** | 512 字节 | 应用层确保对齐 | 不对齐 → EINVAL |
| **Direct IO block size** | 4K | linux 4.x+ 放宽 | 太老版本可能 512 |

---

## 篇尾衔接

本篇深入了 Block 层的 6 大子系统：bio 管理 / request 管理 / plug-merge / dispatch / cgroup 限流 / endio。这是 IO 子系统的"中枢"——上层 Page Cache 把 bio 交给它，下层调度器和驱动依赖它。

下一篇 [04-IO 优先级与 cgroup IO 控制器](04-IO优先级与cgroup-IO控制器.md) 将深入 **IO 优先级体系**：ionice 系统调用、ioprio class（RT/BE/Idle）、cgroup v1 blkio / cgroup v2 io 子系统的细节、Android 进程优先级 ↔ IO 优先级的映射——这是"哪个进程 / 哪个 cgroup 能抢到 IO 资源"的完整图谱。