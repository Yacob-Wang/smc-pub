# 面向稳定性的 Window 系统深度解析系列

## 为什么要写这个系列

Window 系统是 Android UI 的"骨架"。**屏幕上的每一个像素，都必须经过 WindowManagerService 的布局计算与 SurfaceFlinger 的合成渲染，才能最终呈现在用户眼前。** 从 Activity 的第一帧到 Dialog 的弹出，从状态栏到导航栏，一切可见的界面元素都是 Window。

对于稳定性架构师来说，Window 系统的重要性在于：

- **高频崩溃的重灾区**：`BadTokenException`、`WindowLeaked` 是线上 App 最常见的崩溃类型之一。理解 WindowToken 验证机制和 Window 生命周期，是根治这类 Crash 的基础。
- **system_server Watchdog 的头号嫌疑人**：WMS 的全局锁 `mGlobalLock` 竞争是导致 system_server 被 Watchdog 杀死的首要原因之一。锁持有时间过长会级联阻塞 AMS、IMS 等核心服务。
- **Input ANR 的幕后推手**：WMS 负责为 InputDispatcher 管理焦点窗口——焦点设置不及时或焦点丢失，是造成 60% 以上 Input ANR 的根本原因。
- **启动速度的关键路径**：TTID（Time To Initial Display）和 TTFD（Time To Full Display）直接决定用户感知的启动速度。窗口的创建、布局、首帧绘制每一步都在启动关键路径上，也是 ANR 风险的高发区。

本系列的目标：**让你理解从 `addView` 到屏幕显示的完整链路，能从 `dumpsys window` / `dumpsys SurfaceFlinger` / Systrace / winscope 中快速定位 Window 相关问题的根因，并建立有效的窗口稳定性监控与治理体系。**

## 系列设计思路

```
Window 系统是什么？为什么 Android 需要 WMS 这样一个复杂的系统服务？（定位）
    ↓
一个 Window 从创建到显示到销毁，经历了哪些环节？（边界与交互）
    ↓
WMS 如何管理窗口层级？布局？Surface？动画？（核心机制）
    ↓
WMS 如何管理焦点？焦点切换如何影响 Input ANR？（跨模块交互）
    ↓
TTID/TTFD 衡量什么？如何优化？（显示性能）
    ↓
黑屏、Crash、焦点丢失、WMS 锁死各是什么原因？（风险地图）
    ↓
dumpsys window / SurfaceFlinger / Systrace / winscope 怎么用？（诊断与治理）
```

---

## 第一篇章：建立全局观（1 篇）

> 核心问题：Window 系统是什么？一个窗口从创建到显示经历了哪些环节？为什么 Android 需要 WMS 这样一个复杂的系统服务？

### [01-Window 系统总览：从 addView 到屏幕显示的全链路](01-Window系统总览.md)


| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. Window 系统是什么** | 一切可见 UI 的承载容器；Activity、Dialog、Toast、状态栏都是 Window | — | "一切界面皆 Window" |
| **2. 为什么需要 WMS** | 多窗口仲裁、Z-order 管理、安全隔离、焦点管理四大设计驱动力 | — | 架构决定了问题排查的层次 |
| **3. WMS 架构全景图** | App → ViewRootImpl → WMS → SurfaceFlinger 四层协作模型 | `frameworks/base/services/core/java/com/android/server/wm/` | 出问题时定位在哪一层 |
| **4. Window 完整生命周期** | addView → relayout → draw → remove 的全链路概要 | 多个目录 | 建立端到端的心智模型 |
| **5. 进程与线程模型** | App 主线程 / system_server WMS 线程（含 `mGlobalLock`）/ SurfaceFlinger 主线程的分工 | `WindowManagerService.java` | 线程阻塞 → 界面卡顿或 Watchdog |
| **6. 与其他模块的交互全景** | IMS（焦点与输入）、AMS（Activity 生命周期）、SurfaceFlinger（合成显示）、Choreographer（VSync） | 多个目录 | Window 是系统模块的"连接枢纽" |
| **7. 核心源码目录导航** | `server/wm/`、`view/`、`SurfaceControl`、`SurfaceFlinger` 等目录速查 | 多个目录 | 排查问题时的"导航地图" |


---

## 第二篇章：核心机制深潜（6 篇）

> 核心问题：Window 如何创建与添加？层级如何组织？布局如何计算？Surface 如何管理？动画如何运作？焦点如何影响 Input？

### [02-Window 的创建与添加：从 addView 到 Surface 诞生](02-Window的创建与添加.md)


| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. App 端发起 addView** | WindowManager.addView → ViewRootImpl.setView → Session.addToDisplayAsUser | `ViewRootImpl.java`、`WindowManagerGlobal.java` | addView 时机不对 → BadTokenException |
| **2. WMS 端 addWindow 流程** | 权限检查 → 窗口类型验证 → 创建 WindowState → 插入窗口层级树 | `WindowManagerService.java` | addWindow 失败 → 窗口无法显示 |
| **3. WindowToken 验证** | AppWindowToken / WindowToken 的创建与校验；Token 不匹配的场景分析 | `WindowToken.java`、`ActivityRecord.java` | Token 无效 → BadTokenException |
| **4. Surface 创建** | WindowState → SurfaceSession → SurfaceControl.Builder → 分配 Layer | `WindowStateAnimator.java`、`SurfaceControl.java` | Surface 创建失败 → 黑屏 |
| **5. InputChannel 注册与焦点初始化** | openInputChannel → 注册到 InputDispatcher → 初始焦点计算 | `WindowState.java`、`InputMonitor.java` | InputChannel 未注册 → 触摸无响应 |


### [03-WindowContainer 层级体系与窗口组织](03-WindowContainer层级体系与窗口组织.md)


| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. WindowContainer 层级模型** | RootWindowContainer → DisplayContent → TaskDisplayArea → Task → ActivityRecord → WindowState 的树形结构 | `WindowContainer.java` | 层级理解是排查窗口问题的基础 |
| **2. DisplayContent** | 屏幕抽象；管理 DisplayArea 层级；多屏场景的窗口隔离 | `DisplayContent.java` | 多屏异常 → 窗口显示在错误屏幕 |
| **3. Task 与 ActivityRecord** | Task 栈管理；ActivityRecord 与 WindowState 的关联；Activity 切换时的窗口操作 | `Task.java`、`ActivityRecord.java` | Task 状态异常 → Activity 无法显示 |
| **4. WindowState** | 窗口的核心数据结构；属性、Frame、Surface 引用、输入通道 | `WindowState.java` | 理解 WindowState 是理解 WMS 的关键 |
| **5. Z-order 与 assignLayer** | assignLayer 机制；窗口类型优先级；动态 Z-order 调整 | `WindowContainer.java`、`DisplayArea.java` | Z-order 错误 → 窗口遮挡异常 |


### [04-窗口布局与 Insets 计算](04-窗口布局与Insets计算.md)


| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. performSurfacePlacement** | WMS 布局总入口；遍历窗口树计算每个窗口的位置和大小 | `WindowSurfacePlacer.java` | 布局耗时过长 → 界面卡顿 |
| **2. DisplayPolicy 与 Frame 计算** | 系统窗口（状态栏、导航栏）的策略；窗口 Frame 的计算流程 | `DisplayPolicy.java` | Frame 计算错误 → 窗口位置偏移 |
| **3. WindowInsets 体系** | InsetsState / InsetsController / InsetsSource 的协作；刘海屏与圆角适配 | `InsetsState.java`、`InsetsController.java` | Insets 异常 → 内容被遮挡或布局错乱 |
| **4. relayoutWindow** | App 请求重新布局；WMS 重新计算 Frame 并返回；Surface 大小调整 | `WindowManagerService.java` | relayout 频繁 → 性能问题 |
| **5. 配置变更与窗口重建** | 旋转、分屏、折叠屏变化触发的窗口销毁重建流程 | `DisplayContent.java`、`ActivityRecord.java` | 配置变更处理不当 → Crash 或状态丢失 |


### [05-Surface 管理与 SurfaceFlinger 交互](05-Surface管理与SurfaceFlinger交互.md)


| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. SurfaceControl** | WMS 侧的 Surface 句柄；层级关系映射；属性设置 | `SurfaceControl.java` | SurfaceControl 泄漏 → Native 内存泄漏 |
| **2. Transaction 机制** | SurfaceControl.Transaction 批量提交；原子性保证；apply 时机 | `SurfaceControl.java`、`Transaction.java` | Transaction 未提交 → 界面不刷新 |
| **3. Buffer 与 BufferQueue** | GraphicBuffer 的生产者-消费者模型；dequeueBuffer / queueBuffer 流程 | `BufferQueueProducer.cpp`、`BufferQueueConsumer.cpp` | Buffer 不足 → 掉帧或卡顿 |
| **4. SurfaceFlinger 合成** | Layer 树构建；HWC 与 GPU 合成选择；VSync 信号与帧提交 | `SurfaceFlinger.cpp`、`Layer.cpp` | 合成超时 → 丢帧 |
| **5. Surface 生命周期管理** | Surface 的创建、复用、销毁时机；与窗口生命周期的对应关系 | `WindowStateAnimator.java` | Surface 提前销毁 → 黑屏或 Crash |


### [06-窗口动画与转场](06-窗口动画与转场.md)


| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. 窗口动画体系概述** | 窗口动画 vs Activity 转场动画 vs 共享元素动画的分层 | `WindowAnimator.java` | 动画卡顿直接影响用户体验 |
| **2. AppTransition** | Activity 切换动画的状态机；TRANSIT 类型与动画选择逻辑 | `AppTransition.java`、`AppTransitionController.java` | 转场超时 → 黑屏或闪烁 |
| **3. RemoteAnimation** | Launcher/SystemUI 自定义转场动画；RemoteAnimationAdapter 机制 | `RemoteAnimationController.java` | 远程动画回调超时 → 转场卡死 |
| **4. 窗口内动画与 Choreographer** | Choreographer 调度 VSync 回调；动画帧率与掉帧检测 | `Choreographer.java`、`WindowAnimator.java` | 动画掉帧 → 用户感知卡顿 |


### [07-WMS 与 Input 焦点管理](07-WMS与Input焦点管理.md)　　*← 桥梁文章：连接 Window 系列与 Input 系列*


| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. FocusedApplication vs FocusedWindow** | 两个焦点概念的区别与协作；InputDispatcher 如何使用它们 | `InputMonitor.java`、`InputDispatcher.cpp` | 概念混淆 → 无法准确排查焦点 ANR |
| **2. FocusedApplication 设置与切换** | AMS/WMS 何时设置 FocusedApplication；Activity 启动/切换/销毁时的更新时序 | `ActivityRecord.java`、`InputMonitor.java` | 设置延迟 → InputDispatcher 找不到目标 Application |
| **3. FocusedWindow 计算与更新** | WMS 遍历窗口树计算焦点窗口；`updateFocusedWindowLocked` 的触发时机 | `DisplayContent.java`、`WindowManagerService.java` | 焦点窗口计算延迟 → Input ANR |
| **4. InputMonitor 详解** | WMS 与 IMS 的桥梁；`updateInputWindowsLw` 将窗口列表同步给 InputDispatcher | `InputMonitor.java` | 窗口列表同步延迟 → 事件发送到错误窗口 |
| **5. Activity 切换焦点时序** | 从 Activity A 到 Activity B 的焦点切换完整时序图；关键时间窗口分析 | 多个目录 | 时间窗口内焦点为空 → 事件无处可发 |
| **6. 焦点异常四种场景** | 焦点为空 / 焦点不匹配 / 焦点切换过慢 / 焦点被抢占——原因与排查方法 | — | 每种场景对应一类 Input ANR |


---

## 第三篇章：性能与稳定性专题（2 篇）

> 核心问题：窗口显示性能如何衡量与优化？Window 系统有哪些典型的稳定性风险？

### [08-窗口显示性能：TTID、TTFD 与启动优化](08-窗口显示性能TTID与TTFD.md)


| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. 从窗口视角看启动** | 冷启动全链路中窗口相关的关键阶段：Window 创建 → 首帧绘制 → 内容就绪 | 多个目录 | 窗口环节耗时直接拉长启动时间 |
| **2. TTID（Time To Initial Display）** | 定义与测量方法；`Displayed` 日志的含义；从 Activity 启动到首帧上屏的关键路径 | `ActivityRecord.java`、`WindowState.java` | TTID 过长 → 用户感知白屏/黑屏 |
| **3. TTFD（Time To Full Display）** | 定义与 `reportFullyDrawn` 的使用；与 TTID 的关系 | `ActivityRecord.java` | TTFD 过长 → 用户看到骨架屏时间过久 |
| **4. TTID 与 TTFD 对比** | 测量口径、触发条件、优化侧重点的对比表 | — | 明确两个指标的各自价值 |
| **5. Starting Window（Splash Screen）** | 启动窗口的创建时机与作用；Android 12+ SplashScreen API | `StartingSurfaceController.java` | Starting Window 延迟 → 用户看到黑屏 |
| **6. 优化最佳实践** | 减少首帧视图复杂度、异步初始化、预加载、合理使用 Starting Window | — | 从窗口角度优化启动速度 |


### [09-Window 稳定性风险全景](09-Window稳定性风险全景.md)


| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. BadTokenException** | 五种典型触发场景：Activity 已销毁弹 Dialog、非 Activity Context 加窗口、Token 过期等 | `WindowManagerService.java` | 线上高频 Crash 类型 |
| **2. WindowLeaked** | Activity 销毁时 Window 未移除；检测机制与修复方案 | `WindowManagerGlobal.java` | 内存泄漏 + 日志污染 |
| **3. 黑屏分类** | 首帧黑屏（Surface 未就绪）/ 中途黑屏（Surface 意外销毁）/ 切换黑屏（转场动画异常）| 多个目录 | 用户感知最强烈的体验问题 |
| **4. 窗口焦点丢失与 ANR** | 焦点为空导致 Input ANR 的完整因果链；与 07 篇焦点管理的呼应 | `InputMonitor.java`、`InputDispatcher.cpp` | Input ANR 中最难排查的类型 |
| **5. 模式识别速查表** | 问题类型 / 日志特征 / dumpsys 特征 / 排查方向 速查表 | — | 5 分钟内定位问题类型 |


---

## 第四篇章：系统级稳定性与诊断治理（2 篇）

> 核心问题：WMS 锁竞争为什么会导致 Watchdog？Window 问题怎么查？怎么建监控体系？

### [10-WMS 锁竞争与 Watchdog](10-WMS锁竞争与Watchdog.md)


| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. mGlobalLock 本质** | WMS 全局锁的设计意图；保护的核心数据结构；与 AMS 锁的关系 | `WindowManagerService.java` | 理解锁范围是排查锁竞争的基础 |
| **2. 竞争者图谱** | 哪些操作会持有 mGlobalLock：addWindow / relayout / performLayout / removeWindow 等；各自持锁时长分析 | `WindowManagerService.java` | 识别高频竞争者 → 针对性优化 |
| **3. 级联效应** | WMS 锁阻塞 → AMS 等待 WMS → IMS 等待 AMS → 多服务级联卡死 | 多个目录 | 一把锁导致整个 system_server 瘫痪 |
| **4. Watchdog 与 WMS** | Watchdog 检测 system_server 主线程和关键锁；超时 → 杀 system_server → 重启 | `Watchdog.java` | system_server 重启 → 用户体验灾难 |
| **5. 死锁场景** | WMS 锁与 AMS 锁交叉持有；Binder 调用导致的锁反转 | 多个目录 | 死锁 → 必然触发 Watchdog |
| **6. 实战案例** | 典型锁竞争与 Watchdog 问题的排查过程：日志分析 → 锁链还原 → 根因定位 | — | 从案例中学习排查方法论 |


### [11-Window 诊断工具与治理体系](11-Window诊断工具与治理体系.md)


| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. dumpsys window** | 窗口列表 / 焦点窗口 / 窗口属性 / Policy 状态 的解读方法 | — | Window 问题排查的第一工具 |
| **2. dumpsys SurfaceFlinger** | Layer 树 / Buffer 状态 / 合成方式 / 帧统计 的解读方法 | — | Surface 和合成问题的核心工具 |
| **3. dumpsys input 窗口信息** | InputDispatcher 中的窗口列表、焦点窗口、InputChannel 状态 | — | 验证 WMS 同步给 IMS 的窗口信息是否正确 |
| **4. Systrace / Perfetto** | WMS 相关 trace tag；窗口布局、动画、Surface 操作的可视化分析 | — | 性能分析与时序问题排查的主力工具 |
| **5. winscope** | 窗口层级可视化；逐帧回放窗口状态变化；与 Systrace 的配合使用 | — | 最直观的窗口调试工具 |
| **6. 监控与治理最佳实践** | BadTokenException 防御 / WindowLeaked 检测 / WMS 锁耗时监控 / 启动窗口性能埋点 | — | 从"能查"到"能治"到"能防" |


---

## 与 Input 系列的交叉引用

Window 系统与 Input 系统深度耦合，以下是两个系列的关键交叉点：

| 交叉点 | Window 系列相关文章 | Input 系列相关文章 | 说明 |
| --- | --- | --- | --- |
| **焦点管理** | [07-WMS 与 Input 焦点管理](07-WMS与Input焦点管理.md) | [03-InputDispatcher](../Input/03-InputDispatcher.md) | WMS 计算焦点窗口 → InputDispatcher 使用焦点窗口分发按键事件 |
| **InputChannel 注册** | [02-Window 的创建与添加](02-Window的创建与添加.md) | [04-InputChannel 与跨进程投递](../Input/04-InputChannel与跨进程投递.md) | addWindow 时创建 InputChannel → 注册到 InputDispatcher |
| **窗口焦点丢失导致 ANR** | [09-Window 稳定性风险全景](09-Window稳定性风险全景.md) | [06-Input ANR](../Input/06-InputANR.md) | 焦点窗口为空 → InputDispatcher 等待超时 → ANR |
| **窗口列表同步** | [07-WMS 与 Input 焦点管理](07-WMS与Input焦点管理.md) | [03-InputDispatcher](../Input/03-InputDispatcher.md) | InputMonitor 将窗口信息同步给 InputDispatcher 用于触摸命中测试 |
| **WMS 锁阻塞 Input** | [10-WMS 锁竞争与 Watchdog](10-WMS锁竞争与Watchdog.md) | [06-Input ANR](../Input/06-InputANR.md) | WMS 锁竞争导致焦点更新延迟 → 级联引发 Input ANR |

---

## 阅读建议

**如果你时间有限，优先阅读：**

1. **01 总览** — 建立全局观，理解 WMS 架构和窗口完整生命周期。
2. **07 焦点管理** — 桥梁文章，理解焦点管理机制及其对 Input ANR 的影响。
3. **08 TTID/TTFD** — 实战价值最高，从窗口视角理解启动性能优化。
4. **10 WMS 锁竞争** — 理解 system_server 级稳定性风险的核心篇章。

**如果你要系统学习，按顺序阅读 01 → 11。** 每篇文章的设计逻辑是：

```
背景与定义（是什么、为什么需要它）
    → 架构与交互（在系统中的位置、上下游关系）
        → 核心机制与源码（关键数据结构、核心流程）
            → 稳定性风险点（会在哪里出问题）
                → 实战案例（线上真实问题的排查过程）
```
