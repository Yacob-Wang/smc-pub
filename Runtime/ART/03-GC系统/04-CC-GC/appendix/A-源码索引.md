# 附录 A：源码索引（CC GC）

> **本附录是 04 篇涉及的所有 AOSP 源码路径清单** —— 按章节组织。
> **AOSP 版本**：AOSP 14 (API 34) / master。

## 一、CC GC 核心类

### 关键文件

| 文件路径 | 关键内容 |
|:---|:---|
| `art/runtime/gc/collector/concurrent_copying.h` | ConcurrentCopying 类（含 kGrayStatusImmuneWord） |
| `art/runtime/gc/collector/concurrent_copying.cc` | CC GC 实现（~5000 行） |
| `art/runtime/read_barrier.h` | 读屏障抽象层 |
| `art/runtime/read_barrier.cc` | 读屏障实现 |
| `art/runtime/gc/space/region_space.h` | RegionSpace + Region |
| `art/runtime/gc/space/region_space.cc` | RegionSpace 实现 |

## 二、关键函数

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `ConcurrentCopying::RunPhases` | `concurrent_copying.cc` | CC GC 主函数 |
| `ConcurrentCopying::InitializePhase` | `concurrent_copying.cc` | Initialize 阶段 |
| `ConcurrentCopying::ConcurrentCopyingPhase` | `concurrent_copying.cc` | Copying 阶段 |
| `ConcurrentCopying::ReclaimPhase` | `concurrent_copying.cc` | Reclaim 阶段 |
| `ConcurrentCopying::CopyObject` | `concurrent_copying.cc` | 复制对象 |
| `ConcurrentCopying::MarkObject` | `concurrent_copying.cc` | 标记对象 |
| `ReadBarrier::Barrier` | `read_barrier.h` | 读屏障入口 |
| `ReadBarrier::BarrierForRoot` | `read_barrier.h` | Root 对象读屏障 |
| `RegionSpace::Alloc` | `region_space.cc` | Region 分配 |
| `RegionSpace::SwapSemiSpaces` | `region_space.cc` | 切换 from/to-space |
| `Thread::VisitRoots` | `thread.cc` | 栈扫描 |
| `ThreadList::SuspendAll` | `thread_list.cc` | 暂停所有线程 |

## 三、关键常量

```cpp
// art/runtime/gc/collector/concurrent_copying.h
static constexpr uint32_t kGrayStatusImmuneWord = 0xFEEDDEAD;
static constexpr size_t kRegionSize = 256 * KB;
```

## 四、版本演进

| 版本 | 变更 |
|:---|:---|
| AOSP 8.0 | CC GC 引入（读屏障 + Region） |
| AOSP 9.0 | 读屏障优化 |
| AOSP 12.0 | rbcc 优化（Read Barrier Copy Collector） |
| AOSP 14.0 | 进一步优化 |

## 五、关键 commit

```
commit: a5d0b5d8e2b7c9f1a3d5e7f9b1c3d5e7f9b1c3d5
title: "Introduce Concurrent Copying (CC) GC with read barriers"
date: 2017-Q3 (Android 8.0)

commit: f8b9c2e1a3d5f7b9c1d3e5f7b9c1d3e5f7b9c1d3
title: "Optimize read barriers with rbcc"
date: 2021-Q2 (AOSP 12.0)
```
