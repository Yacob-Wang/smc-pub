# PSI内存压力与kswapd活跃度异常分析

## 问题描述

在ANR日志中观察到以下矛盾现象：
- **内存PSI压力较低**：`some avg10=6.33%`, `full avg10=4.59%`
- **kswapd异常活跃**：占用42% CPU
- **IO压力极高**：`some avg10=78.08%`, `full avg10=52.78%`
- **iowait很高**：21% (第一个时间段), 12% (第二个时间段)

## 日志关键信息

### PSI压力指标
```
/proc/pressure/memory:
  some avg10=6.33% avg60=6.32% avg300=5.83%
  full avg10=4.59% avg60=4.50% avg300=4.06%

/proc/pressure/io:
  some avg10=78.08% avg60=72.73% avg300=35.96%
  full avg10=52.78% avg60=49.30% avg300=21.79%
```

### CPU使用情况
```
42% 103/kswapd0: 0% user + 42% kernel
87% TOTAL: 29% user + 33% kernel + 21% iowait + 2% irq + 1.1% softirq
```

### 大量IO相关worker线程
```
多个kworker/u17:* -blk_crypto_wq线程活跃
```

## 根本原因分析

### 1. PSI内存统计的局限性

PSI (Pressure Stall Information) 的 `some` 和 `full` 指标反映的是**任务因等待内存而阻塞的时间比例**，而不是内存使用率或swap频率。

**关键理解**：
- `some`: 至少一个任务因内存等待而阻塞的时间比例
- `full`: 所有任务都因内存等待而阻塞的时间比例

**为什么PSI内存压力看起来不高？**

1. **异步swap机制**：kswapd是后台线程，它的swap操作是异步的，不会直接阻塞前台任务
2. **页面回收策略**：系统可能优先回收文件缓存、inactive页面，这些操作对用户任务影响较小
3. **统计窗口问题**：PSI统计的是10秒窗口，如果内存压力是突发性的，可能被平均化

### 2. kswapd活跃的真实原因

#### 2.1 IO瓶颈导致的连锁反应

```
IO压力极高 (78.08% some, 52.78% full)
↓
kswapd需要将页面写入swap分区/文件
↓
IO队列阻塞，kswapd等待IO完成
↓
kswapd持续运行，CPU占用高
↓
但前台任务可能没有直接等待内存，所以PSI内存压力不高
```

#### 2.2 内存碎片化

即使总内存压力不大，如果存在：
- **内存碎片化**：大量小页面需要swap out
- **文件系统缓存压力**：需要回收大量文件缓存
- **ZRAM压缩**：如果使用ZRAM，压缩操作本身消耗CPU

#### 2.3 加密IO瓶颈

日志中大量 `blk_crypto_wq` worker线程，说明：
- 存储加密导致IO性能下降
- swap操作需要加密/解密，进一步加重IO负担
- kswapd在等待加密IO完成时持续占用CPU

### 3. iowait高的原因

```
21% iowait + 大量kworker线程
```

**iowait表示CPU空闲但等待IO完成的时间**，这里高iowait说明：
1. **IO队列深度大**：大量IO请求排队
2. **存储性能瓶颈**：可能是eMMC/UFS性能不足，或加密开销大
3. **swap IO密集**：kswapd频繁进行swap out操作

## PSI算法是否真的有问题？

### PSI内存统计的设计逻辑

PSI内存压力统计的是**任务因等待内存分配而阻塞的时间**，而不是swap频率或内存使用率。

**正常情况下的逻辑**：
- 如果内存充足，任务直接分配内存，不阻塞 → PSI低
- 如果内存不足，任务等待内存分配 → PSI高

**但在这个案例中**：
- kswapd在后台异步回收内存
- 前台任务可能通过以下方式避免阻塞：
  - 使用已有的内存（不触发新分配）
  - 等待时间在PSI统计窗口外
  - 通过其他机制（如cgroup限制）间接等待

### PSI的潜在问题

1. **异步操作不统计**：kswapd的swap操作是异步的，不直接贡献到PSI
2. **间接阻塞不统计**：如果任务因为IO慢而间接受影响，可能不会计入内存PSI
3. **统计延迟**：PSI是滑动窗口平均，可能无法及时反映突发压力

## 诊断建议

### 1. 检查swap使用情况
```bash
# 检查swap使用
cat /proc/meminfo | grep -i swap
cat /proc/swaps

# 检查swap IO
iostat -x 1 | grep -i swap
```

### 2. 检查IO性能
```bash
# 检查IO延迟
iostat -x 1
# 关注await, svctm等指标

# 检查IO队列深度
cat /sys/block/*/queue/nr_requests
```

### 3. 检查内存碎片
```bash
# 检查内存碎片
cat /proc/buddyinfo
cat /proc/pagetypeinfo
```

### 4. 检查ZRAM（如果使用）
```bash
# 检查ZRAM使用和压缩率
cat /sys/block/zram0/mm_stat
cat /sys/block/zram0/comp_algorithm
```

### 5. 更详细的内存压力指标
```bash
# 检查内存回收统计
cat /proc/vmstat | grep -E "pgmajfault|pgpgin|pgpgout|pswpin|pswpout"

# 检查kswapd活动
cat /proc/vmstat | grep kswapd
```

## 解决方案建议

### 1. 优化IO性能
- **减少加密开销**：评估是否所有数据都需要加密
- **优化存储驱动**：检查是否有IO调度器优化空间
- **增加IO队列深度**：如果硬件支持

### 2. 优化内存管理
- **调整swappiness**：如果swap过于频繁，降低swappiness
- **优化内存回收策略**：调整vfs_cache_pressure等参数
- **减少内存碎片**：考虑使用CMA或调整内存分配策略

### 3. 监控改进
- **结合多个指标**：不要只看PSI，要结合swap使用、IO延迟等
- **实时监控**：使用更细粒度的监控（如1秒间隔）
- **关注IO PSI**：在这个案例中，IO PSI更能反映问题

## 结论

**PSI内存统计算法本身没有问题**，但它统计的是**任务阻塞时间**，而不是**系统资源消耗**。

在这个案例中：
- **真正的问题是IO瓶颈**，不是内存压力
- **kswapd活跃是因为IO慢**，导致swap操作堆积
- **PSI内存压力低是因为任务没有直接等待内存分配**
- **应该关注IO PSI**（78.08%），这才是真正的瓶颈

**建议**：在ANR分析中，应该综合多个指标：
1. PSI（内存、CPU、IO）
2. swap使用率
3. IO延迟和队列深度
4. kswapd CPU占用
5. iowait比例

单一指标可能误导，需要全局视角。
