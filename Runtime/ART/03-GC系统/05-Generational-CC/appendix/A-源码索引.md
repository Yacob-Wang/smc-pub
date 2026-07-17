# 附录 A：源码索引（GenCC）

## 一、核心文件

```
art/runtime/gc/collector/concurrent_copying.h   # GenCC 核心类
art/runtime/gc/collector/concurrent_copying.cc  # GenCC 实现（含分代）
art/runtime/gc/space/region_space.h             # RegionSpace + CardTable
art/runtime/gc/space/region_space.cc            # CardTable 实现
art/runtime/gc/heap.cc                         # Heap GC 决策
```

## 二、关键函数

| 函数 | 功能 |
|:---|:---|
| `ConcurrentCopying::MinorGc` | Minor GC 主函数 |
| `ConcurrentCopying::Promote` | 对象晋升 |
| `ConcurrentCopying::CopyToOldGen` | 复制到 Old Gen |
| `CardTable::MarkCard` | 标记 dirty card |
| `Heap::SelectGcType` | GC 类型决策 |
| `PostWriteBarrier` | Post-Write Barrier |

## 三、关键常量

```cpp
static constexpr size_t kRegionSize = 256 * KB;
static constexpr size_t kCardSize = 512;
static constexpr uint32_t kPromotionThreshold = 15;
```

## 四、版本演进

| 版本 | 变更 |
|:---|:---|
| AOSP 10.0 | GenCC 引入（Young/Old 分代） |
| AOSP 11.0 | Card Table 优化 |
| AOSP 12.0 | rbcc + 分代优化 |
| AOSP 14.0 | 自适应晋升阈值 + 细粒度卡表 |
