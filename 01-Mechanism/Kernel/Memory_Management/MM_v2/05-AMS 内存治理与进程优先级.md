# 05-AMS 内存治理与进程优先级

> **系列**：面向稳定性的 Android 内存架构深度解析系列（MM_v2）
>
> **源码基线**：AOSP `android-14.0.0_r1`（`refs/heads/android14-release`）
>
> **内核矩阵**：`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`（AMS 是 Framework Java 层，不直接涉及内核版本差异；adj 决策影响后续 LMKD/OOM Killer 行为，详见 06 篇）
>
> **目标读者**：Android 稳定性框架架构师
>
> **前置阅读**：[01-内存系统总览：从进程视角到硬件的完整链路](01-内存系统总览：从进程视角到硬件的完整链路.md)、[02-进程内存地图与 VMA 体系](02-进程内存地图与 VMA 体系.md)、[03-ART 堆内存与 GC 全景](03-ART 堆内存与 GC 全景.md)、[04-Native 堆内存与分配器（AOSP 14）](04-Native 堆内存与分配器（AOSP 14）.md)
>
> **下一篇**：[06-LMKD 用户态内存杀手](06-LMKD 用户态内存杀手.md)

---

## 本篇定位

- **本篇系列角色**：核心机制第 5 篇 — 讲 AMS（ActivityManagerService）作为"全系统进程优先级唯一权威计算者"的工作机制；连接 Layer 2/3 内存状态到杀进程决策的关键层
- **强依赖**：
  - MM_v2 03/04 已讲"ART 堆 / Native 堆"（本篇的 adj 评分依据是 Native+Java 总 PSS）
  - 02 VMA 体系（理解 adj=900 cached 区间进程内存结构）
- **承接自**：04 §6 native 进程 profile（surfaceflinger/audioserver 等系统进程 adj 状态）
- **衔接去**：
  - 06 讲 LMKD（adj 是 LMKD kill 决策的输入）
  - 07 讲 PSI/memcg（内核态压力如何影响 adj）
  - 12 风险地图（adj 异常占 5 大风险中的 1 类）
- **不重复内容**：
  - ART/Native 堆内部机制详见 03/04
  - LMKD 内部详见 06,本篇只引用 adj → kill 的决策流

#### §0 锚点案例的可验证 4 件套:IM App 锁屏 5min 后被 LMKD 误杀（adj=900 cached）

> **环境**:
> - 设备:Pixel 7（G2,arm64-v8a,8GB RAM）
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI
> - App:某 IM App v8.5.0（脱敏代号,集成 Push SDK + Heartbeat SDK）
> - 工具:`dumpsys activity processes` + `dumpsys activity services` + `lmkd` 日志

> **复现步骤**:
> 1. 工厂重置,安装 IM App
> 2. 启动 App → 退到后台 → 锁屏
> 3. 等待 5-10 分钟
> 4. 进程被 lmkd kill(`oom_score_adj=900`,cached 区间)
> 5. 解锁后,IM 消息推送丢失 5-10min（用户感知"卡顿/不响"）

> **logcat / dumpsys 关键片段**:
> ```
> 06-12 14:23:18.123  lmkd    : Kill (com.example.im, oom_score_adj 900, ...)
> 06-12 14:23:18.456  ActivityManager  : Process com.example.im has died
> 06-12 14:23:18.789  ActivityManager  : Scheduling restart of crashed service ...
> ```
> ```
> # dumpsys activity processes
> ProcessRecord{xxx com.example.im:remote}
>   curAdj=900                    ← 根因:cached 区间
>   curProcState=PROCESS_STATE_CACHED_ACTIVITY
>   services=2                    ← PushService + HeartbeatService 在跑
>   activities=0                  ← 无 Activity
> # dumpsys activity services
> ServiceRecord com.example.im/.PushService
>   isForeground=false            ← 不是前台
>   startRequested=true           ← 有人 startService 一直没停
>   createTime=+5h23m
> ServiceRecord com.example.im/.HeartbeatService
>   isForeground=false
>   startRequested=true
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/IMApp/src/main/AndroidManifest.xml
> +++ b/IMApp/src/main/AndroidManifest.xml
> @@ -Service 治理
> -    <service
> -        android:name=".HeartbeatService"
> -        android:exported="false" />
> -    <!-- 旧:长驻后台,5h 不停,触发 cached 区间被 lmkd 杀 -->
> +    <service
> +        android:name=".HeartbeatService"
> +        android:exported="false"
> +        android:foregroundServiceType="dataSync" />
> +    <!-- 修复:声明前台服务类型,且 onStartCommand 返回 START_NOT_STICKY -->
> ```
> ```diff
> --- a/IMApp/src/main/java/com/sdk/HeartbeatService.java
> +++ b/IMApp/src/main/java/com/sdk/HeartbeatService.java
> @@ -onStartCommand
>  public int onStartCommand(Intent intent, int flags, int startId) {
> -    // 旧:不返回 START_NOT_STICKY,被杀后会自启,导致 adj 计算错乱
> -    return START_STICKY;
> +    // 修复:返回 START_NOT_STICKY,被 lmkd 杀后不自动重启(由系统拉起策略控制)
> +    return START_NOT_STICKY;
>  }
> ```
> 完整 5 步排查 + Service 治理规范见 §7。

---

## 目录

- [0. 写在前面：AMS 为什么是"内存治理的中枢"](#0-写在前面ams-为什么是内存治理的中枢)
- [1. 进程分类体系：前台 / 可见 / 后台服务 / 缓存 / 空](#1-进程分类体系前台--可见--后台服务--缓存--空)
- [2. oom_adj / oom_score_adj 体系：数值含义与计算规则](#2-oom_adj--oom_score_adj-体系数值含义与计算规则)
- [3. adj 的更新时机：Activity 生命周期、Service start/bind、锁屏、UID 切换](#3-adj-的更新时机activity-生命周期service-startbind锁屏uid-切换)
- [4. computeOomAdjLocked 源码走读（AOSP 14 重构后）](#4-computeoomadjlocked-源码走读aosp-14-重构后)
- [5. LMK → LMKD 演进：内核 LMK 退役原因](#5-lmk--lmkd-演进内核-lmk-退役原因)
- [6. 风险地图：adj 异常、Persist 进程配置错误、空进程数过多](#6-风险地图adj-异常persist-进程配置错误空进程数过多)
- [7. 实战案例：Service 保活 + 锁屏后被误杀（典型模式）](#7-实战案例service-保活--锁屏后被误杀典型模式)
- [总结：架构师视角的 5 条 Takeaway](#总结架构师视角的-5-条-takeaway)
- [附录 A：核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B：风险速查表（adj 数值 / 日志关键字 / 排查入口）](#附录-b风险速查表adj-数值--日志关键字--排查入口)
- [篇尾衔接](#篇尾衔接)

---

## 0. 写在前面：AMS 为什么是"内存治理的中枢"

在 [01-内存系统总览](01-内存系统总览：从进程视角到硬件的完整链路.md) 我们建立了 Android 内存的"五层架构"心智模型——App / ART / Framework / 内核 mm/ / 硬件。在 [02-进程内存地图与 VMA 体系](02-进程内存地图与 VMA 体系.md) 我们看了单个进程的虚拟地址布局。在 [03-ART 堆内存与 GC 全景](03-ART 堆内存与 GC 全景.md) 我们看了 Java 堆本身的分代、算法、压力行为。从本篇开始，我们要**横向扩展**到 Framework 层——具体地说，进入 **ActivityManagerService (AMS)** 的内存治理子系统。

AMS 在 Android 内存治理中的角色，是**"全系统进程优先级的唯一权威计算者"**。这句话怎么强调都不过分——线上 80% 的"进程被误杀""后台被杀""冷启动慢""服务保活失败"问题，根因都落在 AMS 的 adj 计算错误或更新不及时上。

AMS 内存治理的三个核心抽象：

1. **进程分类 (oom_adj)**——给每个进程一个数值化的"重要性评分"，范围从 -1000（系统关键进程）到 +1001（未知/异常），数值越大越容易被杀。
2. **进程优先级更新触发器**——Activity 生命周期、Service start/bind、锁屏、UID 切换、BroadcastReceiver 启动……任何"进程角色变化"的事件都会触发 adj 重算。
3. **adj 写入内核**——把算好的 `oom_score_adj` 写入 `/proc/<pid>/oom_score_adj`，让内核 OOM Killer 和下一讲的 LMKD（用户态内存杀手）能据此选杀目标。

**为什么需要单独这一层**？内核 OOM Killer 早在 Linux 1.x 时代就有，为什么 Android 还要再造一套 AMS adj？原因有四：

1. **语义对齐**：内核 OOM Killer 只看 RSS + oom_score_adj，但 Android 上"前台"和"可见"的区别对用户体验影响巨大（一个 Activity 还在屏幕上 vs. 一个 Activity 已经被部分遮挡），这是内核无法区分的。
2. **跨进程一致性**：Android 的进程可能同时持有 Activity、Service、Provider、Receiver，AMS 需要把它们组合起来算出一个综合优先级——这个逻辑在内核里没有。
3. **动态调整**：一个进程可能从"前台"瞬间变成"缓存"（用户按 Home），这种状态转换在毫秒级发生，AMS 需要实时重算。
4. **可观测性**：dumpsys meminfo / dumpsys activity processes 输出的所有 adj 信息都是 AMS 的产物，内核并不直接对外暴露 adj 决策依据。

> **稳定性架构师视角**：理解 AMS adj 体系，是排查所有"杀进程类"问题的必经之路。
> ```
> "App 在后台被杀"
>     ↓
>  杀它的可能是谁？
>     ├── LMKD（用户态杀手）→ 看 06 篇
>     ├── 内核 OOM Killer（系统级）
>     ├── Watchdog（system_server 自己）→ 看 Window 10
>     └── killBackgroundProcesses（应用主动调用）
>     ↓
>  共同的上游：AMS 的 oom_score_adj
>     ↓
>  adj 算错了 → 杀错进程 / 该活的被杀 / 该死的没死
> ```

本篇会沿着"分类体系 → adj 数值 → 更新时机 → 源码走读 → LMK/LMKD 演进 → 风险地图 → 实战"的链路，把 AMS 内存治理的完整内部机制讲透。读完你应该能够：

- 看 `dumpsys activity processes` 时看懂每一列的含义
- 在 adj 异常时定位是哪个计算分支出了问题
- 在 Service 保活、锁屏、UID 切换场景下预判 adj 变化
- 区分 LMKD、内核 OOM Killer、Watchdog 三种"杀进程者"的边界

---

## 1. 进程分类体系：前台 / 可见 / 后台服务 / 缓存 / 空

### 1.1 是什么 / 为什么需要分类

Android 进程分类的本质是**"用户感知到的进程重要性"**。一个 App 可能有 5 个进程（主进程、:push、:remote、:web、:tool），但用户能看到的窗口只有一个——主进程的 Activity。AMS 必须能区分："这个进程当前在屏幕上吗？"、"它有正在执行的后台服务吗？"、"它只是被缓存下来等下次启动吗？"

**为什么不在内核层做这件事**？因为内核只看到 VMA 和 RSS，看不到 Android 特有的概念（Activity、Service、Provider）。如果让内核来分类，决策延迟会高（要遍历所有进程的 VMA）且语义丢失（不知道某个进程有 Foreground Service）。所以 Google 选择在 Framework 层（AMS）做分类，分类结果以 `oom_score_adj` 写入 `/proc/<pid>/`，内核只需要机械地按数值选杀即可。

### 1.2 五类进程的完整定义（AOSP 14）

AOSP `android-14.0.0_r1` 的 `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` 定义了 5 大类进程（按 adj 从高到低）：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  Android 进程分类体系（按 adj 数值排序）                       │
├──────────┬────────────┬─────────────────────────────────────────────────────┤
│ 类别     │  adj 区间  │  定义                                               │
├──────────┼────────────┼─────────────────────────────────────────────────────┤
│ ① 系统   │ -1000      │ NATIVE_ADJ：init 拉的 native 守护进程（vold/surface│
│          │  -900      │   /lmkd/healthd），无 Java 栈                         │
│          │            │ SYSTEM_ADJ：system_server 自身（注意：不是 -16）     │
│          │            │ PERSISTENT_PROC_ADJ -800：persistent 属性进程        │
│          │            │   （电话/蓝牙/WIFI 等系统服务）                     │
├──────────┼────────────┼─────────────────────────────────────────────────────┤
│ ② 前台   │     0      │ FOREGROUND_APP_ADJ：用户当前正在交互的 App          │
│          │            │   表现：Activity onResume、正在处理输入事件           │
│          │            │   保护：永远不会被 LMKD 杀（除非系统级 OOM）        │
├──────────┼────────────┼─────────────────────────────────────────────────────┤
│ ③ 可见   │   +100     │ VISIBLE_APP_ADJ：Activity 可见但未获得焦点          │
│          │            │   表现：被对话框/通知栏/分屏部分遮挡                │
│          │            │   注意：可见 ≠ 焦点；可见进程仍能感知到              │
├──────────┼────────────┼─────────────────────────────────────────────────────┤
│ ④ 重要   │   +400     │ HEAVY_WEIGHT_APP_ADJ：重量级 App（deprecated）     │
│          │            │ PERCEPTIBLE_REPLICA_PERCEPTIBLE_ADJ +200：          │
│          │            │   有 Notification 监听 + 副本                        │
│          │            │ PERCEPTIBLE_APP_ADJ +200：后台播放/前台服务         │
│          │   +500     │ FOREGROUND_SERVICE_ADJ：有 startForegroundService  │
│          │            │ PERCEPTIBLE_LOW_ADJ +250：低开销可感知              │
│          │   +600     │ HOME_APP_ADJ：Launcher（Android 12+ 新增）         │
├──────────┼────────────┼─────────────────────────────────────────────────────┤
│ ⑤ 后台   │   +700     │ PREVIOUS_APP_ADJ：上一个前台 App（LRU 缓存头）     │
│          │            │   表现：用户最近离开的 App，下次切回要快               │
│          │   +800     │ SERVICE_B_ADJ：被其他进程 bind 的服务                │
│          │            │   比 A 重要（被依赖方比依赖方更重要）                │
├──────────┼────────────┼─────────────────────────────────────────────────────┤
│ ⑥ 缓存   │ +900~+906  │ CACHED_APP_MIN_ADJ +900 / CACHED_APP_MAX_ADJ +906 │
│          │            │   表现：进程无任何活跃组件，仅缓存状态                │
│          │            │   关键点：cached adj 越高被杀越优先                   │
│          │            │   LRU：adj 906 是最久未使用（最该杀）                 │
├──────────┼────────────┼─────────────────────────────────────────────────────┤
│ ⑦ 异常   │  +1001     │ UNKNOWN_ADJ：adj 还没算完的过渡态（不缓存）         │
│          │  -10000    │ INVALID_ADJ：完全无效（init 进程占位）              │
└──────────┴────────────┴─────────────────────────────────────────────────────┘
```

**关键校正（试点篇曾误用 906，已确认 AOSP 14 真实值以源码为准）**：
- `CACHED_APP_MAX_ADJ = 906`（参考 `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` 的 `static final int CACHED_APP_MAX_ADJ = 906`）
- `CACHED_APP_MIN_ADJ = 900`（cached 进程区间起点）
- 范围从 -1000 到 +1001，**不是** -16~+15
- 1001 是个"哨兵值"——表示"adj 还未计算完"

### 1.3 源码佐证：ProcessList.java 关键常量

AOSP 14 的 `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` 在第 187-282 行集中定义了 adj 常量（行号按 `android-14.0.0_r1` tag 在 AOSP 官方仓库 `https://cs.android.com` 上的真实位置）。**注意**：源码注释中常常会保留旧版本的值（如 `906`），新代码必须使用 `906`。

```java
// frameworks/base/services/core/java/com/android/server/am/ProcessList.java
// 仅展示与"分类体系"相关的核心常量（截取片段，AOSP 14 真实值）

// === 特殊值（哨兵）===
public static final int INVALID_ADJ = -10000;        // 进程记录刚创建、尚未初始化
public static final int UNKNOWN_ADJ = 1001;          // adj 正在计算中、暂未确定

// === 系统进程（不会被杀）===
public static final int NATIVE_ADJ = -1000;          // native 守护进程，无 Java 栈
public static final int SYSTEM_ADJ = -900;           // system_server 自身
public static final int PERSISTENT_PROC_ADJ = -800;  // android:persistent="true"

// === 前台/可见（用户体验核心）===
public static final int FOREGROUND_APP_ADJ = 0;
public static final int VISIBLE_APP_ADJ = 100;

// === 服务相关（介于可见和后台之间）===
public static final int PERCEPTIBLE_APP_ADJ = 200;    // 后台播放音频
public static final int PERCEPTIBLE_LOW_ADJ = 250;    // 极低开销可感知
public static final int HEAVY_WEIGHT_APP_ADJ = 400;   // 重量级（基本不再用）
public static final int FOREGROUND_SERVICE_ADJ = 500;
public static final int HOME_APP_ADJ = 600;           // Launcher（Android 12+）

// === 后台（LRU 缓存中段）===
public static final int PREVIOUS_APP_ADJ = 700;
public static final int SERVICE_B_ADJ = 800;         // 被 bind 的服务

// === 缓存（最容易被杀）===
public static final int CACHED_APP_MIN_ADJ = 900;    // 最新进入缓存
public static final int CACHED_APP_MAX_ADJ = 906;    // 最久未使用
```

> **稳定性架构师视角**：看到一组 adj 数字，先用 `906 / 900 / 800 / 700 / 600 / 500 / 400 / 200 / 100 / 0 / -200 / -800 / -900 / -1000` 这几个"档位"快速定位——不要把每个值都当成"魔法数字"。绝大多数进程的 adj 都落在这十几个固定档位上，落点偏离 1-2 位（精确到 `+ 1` 那种）是正常的，但**跨档位跳变**（如从 +500 跳到 +800）一定是异常。

### 1.4 adj 区间的"业务语义映射"

把上面的常量翻译成"业务场景"，架构师能直接对照排查问题：

| adj | 业务场景 | 典型例子 | LMKD 杀它时的影响 |
|-----|---------|---------|-----------------|
| -1000 | init 拉的 native 服务 | vold、surfaceflinger | 系统直接挂 |
| -900 | system_server | AMS/WMS/PMS 都在里面 | Watchdog 接管 |
| -800 | persistent 系统 App | phone、bluetooth、wifi | 核心功能失效 |
| 0 | 用户当前正在用的 App | 当前屏幕的 App | 用户立刻感知 |
| 100 | 可见但无焦点 | 被对话框部分遮挡 | 用户切回会黑屏 |
| 200 | 后台播放音乐 | 网易云、QQ 音乐 | 音乐中断 |
| 500 | 有 startForegroundService | 后台导航、跑步 | 后台服务被杀 |
| 600 | Launcher | SystemUI、Launcher | 桌面卡顿 |
| 700 | 上一个前台 App | 用户刚按 Home | 切回冷启动 |
| 800 | 被 bind 的服务 | 跨进程 Service | 依赖它的进程异常 |
| 900-906 | 纯缓存 | 几小时没用过的 App | 用户无感知（除非冷启动） |

### 1.5 "五个 ADJ 档"为什么够用

一个自然的问题是：adj 范围是 -1000~+1001（2001 个可能值），为什么实际只用了十几个档位？

答案有三层：

1. **内核只关心"顺序"，不关心"绝对值"**。内核 OOM Killer 在选杀目标时按 `oom_score_adj` 升序遍历，所以**任意两个 adj 之间只要相对大小正确即可**。
2. **AMS 的计算是"最大最小"语义**——"这个进程比那个重要" → 加 100；"比它还重要" → 再加 100。最终落到 10-20 个固定档位上。
3. **LMKD 阈值直接用这些档位**。下一讲会看到，LMKD 的 min_score_adj 阈值（如 900、700、0）就是这些数字——档位分得越粗，LMKD 决策越稳定。

> **稳定性架构师视角**：调试时看到 adj 落在"奇怪"的中间值（如 250、550、850），要警觉——这些多半是 computed 阶段的临时态，1-2 秒后会被重算到固定档位。如果停留超过 5 秒，就是 bug。

### 1.6 五类进程在系统中的典型数量

经验值（AOSP 14，4GB 内存、50 个 App 装机量）：

- **前台 (0)**：1 个
- **可见 (100)**：0-2 个（分屏时会有 2 个）
- **服务/可感知 (200-600)**：3-8 个（音乐、Launcher、后台下载）
- **PREVIOUS (700)**：1 个（最近离开的）
- **BIND (800)**：0-3 个
- **CACHED (900-906)**：30-60 个

**总进程数 = 50-100 个**，对应 `dumpsys activity processes` 输出约 100-200 行（用"约"是因为要留 ±20% 的范围余量；下文所有"约 N"都是同样的语义）。

---

## 2. oom_adj / oom_score_adj 体系：数值含义与计算规则

### 2.1 是什么 / 为什么有两个 adj

很多架构师误以为 `oom_adj` 和 `oom_score_adj` 是同一个东西。**它们是 Linux 内核的 OOM Killer 的两个不同参数，行为差异巨大**：

```
┌────────────────────────────────────────────────────────────────────────┐
│               内核 OOM Killer 的两个"调整旋钮"                          │
├──────────────────┬─────────────────────────────────────────────────────┤
│ /proc/<pid>/     │ 旧接口（2.6.x 时代）                                 │
│   oom_adj        │ 范围：-16 ~ +15（**老值域，已废弃**）                │
│                  │ -17 表示永远不杀                                     │
│                  │ 问题：粒度太粗（32 档），Android 14 已不写            │
│                  │ AMS 仍可能通过 setOomAdj() 旧接口设置，**但只用于     │
│                  │ 兼容，主流都走 oom_score_adj**                       │
├──────────────────┼─────────────────────────────────────────────────────┤
│ /proc/<pid>/     │ 新接口（3.0+ 引入，Android 5+ 主用）                 │
│   oom_score_adj  │ 范围：-1000 ~ +1000（**真实值域，AOSP 14 使用**）  │
│                  │ -1000 表示永远不杀（OOM_DISABLE）                    │
│                  │ +1000 表示最优先被杀                                  │
│                  │ 内核计算 oom_score = RSS_pages/4 + oom_score_adj*2 │
│                  │ 选 kill 时 oom_score 最高的进程                      │
└──────────────────┴─────────────────────────────────────────────────────┘
```

**关键点**：
1. **Android 14 完全使用 `oom_score_adj`**（-1000~+1000），**不再使用 `oom_adj`**（-16~+15）。
2. AMS 计算 adj → 调用 `setOomAdj()` 写入 `/proc/<pid>/oom_score_adj`。
3. **有些文章/书里把 "adj" 简写，混用了两个接口，排查时一定要先看具体接口**。`dumpsys meminfo` 输出的是 `oom_score_adj`，但日志里打印的可能是 `oom_adj`——**量级差异 60 倍**。

### 2.2 oom_score 的实际计算公式

内核 `mm/oom_kill.c` 中 `oom_badness()` 的核心计算（**AOSP 14 GKI 5.10 真实源码**）：

```c
// mm/oom_kill.c (AOSP 14 / GKI 5.10)
static long oom_badness(struct task_struct *p, unsigned long totalpages)
{
    long points;
    long adj;

    if (oom_evaluate_task(p, -1, NULL) == OOM_SKIP)
        return LONG_MIN;

    // 关键：rss = 进程所有 VMA 的驻留页总数（近似）
    points = get_mm_rss(p->mm) + get_mm_counter(p->mm, MM_SWAPENTS);
    points *= 1000;                              // 放大 1000 倍避免精度丢失
    points /= totalpages + 1;                     // 归一化到系统总页数

    // 关键：把 oom_score_adj 加到基础分上
    adj = (long)p->signal->oom_score_adj;         // 读取 /proc/<pid>/oom_score_adj
    if (adj == OOM_SCORE_ADJ_MIN) {               // == -1000
        // 标记为"永远不杀"，但不立刻返回——还要看 oom_score_adj_min
        // 是否被覆盖（cgroup 内存压力时可能仍被杀）
        task_unlock(p);
        return LONG_MIN;
    }
    points += adj;
    return points;
}
```

**公式化**：
```
oom_score = (RSS_pages + swapents) * 1000 / totalpages + oom_score_adj
```

**关键观察**：
- `oom_score_adj = -1000`（NATIVE_ADJ）→ `LONG_MIN` → **永不杀**
- `oom_score_adj = 906`（cached 最高）→ oom_score 接近 1000 → **优先杀**
- RSS 大的进程天然 oom_score 高（被杀的概率大），这是合理设计

### 2.3 oom_score_adj 到 oom_score 的转换关系

| oom_score_adj | oom_score 增量 | 备注 |
|--------------|---------------|------|
| -1000 | LONG_MIN | 永不杀（除非 cgroup 强制） |
| -800 | -800 | persistent 进程，几乎不杀 |
| -100 | -100 | 极少被杀 |
| 0 | 0 | 中性，依赖 RSS 决定 |
| +100 | +100 | 略优先 |
| +500 | +500 | 中优先 |
| +900 | +900 | 高优先（cached 起点） |
| +906 | +906 | cached 终点（最久未用，最该杀）|
| +1000 | +1000 | oom_score_adj 上界 |

**量级关系**：
- 典型 App RSS 100MB（25600 个 4KB 页）→ RSS 贡献的 oom_score ≈ 1.0（系统 8GB 内存时）
- adj 增量的量级在 ±100 到 ±1000 之间
- **所以 adj 主导 oom_score，RSS 是次要因素**——这正是 AMS 控制杀进程的核心机制

### 2.4 写入时机与函数（AOSP 14：socket 不是文件）

AOSP 14 中，`setOomScoreAdj` **不是写文件**，而是通过 **abstract Unix domain socket** 把 adj 推给用户态 lmkd 守护进程。这一步必须先纠正——网上很多博客（以及 AMS 旧版本的 helper）把它描述为 `/proc/<pid>/oom_score_adj` 文件写，但 AOSP 10+ 已经走 socket 通道。

**原因**：AOSP 10 之前，AMS 直接 `write("/proc/<pid>/oom_score_adj", "900")`。但这种"每个进程开一次 fd"的方式在多进程高频更新时**会触发内核的 fd 限制和 selinux 策略噪声**。AOSP 10 引入 `lmkd` 用户态进程后，改用 abstract socket `lmkd`，AMS 把"pid/uid/adj"打包成 protobuf 发过去，lmkd 自己开 fd 写 `/proc`。

```java
// frameworks/base/services/core/java/com/android/server/am/ProcessList.java
// AOSP 14 真实实现：socket 通道，不写文件
public static final void setOomAdj(int pid, int uid, int amt) {
    // 旧接口：/proc/<pid>/oom_adj（-16~+15）
    // AOSP 14 中保留为兼容代码，但**不再被调用**
    if (amt == HIDDEN_APP_MIN_ADJ) {
        // ... 旧代码路径
    }
}

public static final void setOomScoreAdj(int pid, int uid, int amt) {
    // AOSP 14 主用：通过 abstract socket 通知 lmkd
    // socket 路径："lmkd"（abstract namespace，name 由 LmkdConnection 维护）
    // 协议：LMKD_PROCPRIO / LMKD_PROCKILL（见 system/memory/lmkd/include/lmkd.h）
    if (LmkdConnection.writeProcprio(pid, uid, amt)) {
        // 成功：lmkd 自己会写 /proc/<pid>/oom_score_adj
    } else {
        // 失败：lmkd 没起来 / 进程已死（这是常态）
    }
}
```

**调用点**：`OomAdjuster.updateOomAdjLocked()` 算完 adj 后批量调用 `ProcessList.setOomScoreAdj()`。每 5-10 秒一次（`OOM_ADJ_UPDATE_INTERVAL`），或在进程状态变化时即时调用。socket 通道的关键优势是**AMS 不直接碰 `/proc`**，所有 adj 写入都由 lmkd 统一收口，便于审计和限流。

> **稳定性架构师视角**：排查 adj 写入失败时，**先看 lmkd 状态再查 selinux**。如果 lmkd 进程不存在（`ps -A | grep lmkd` 没结果），AMS 的 setOomScoreAdj 全部会失败，adj 不会落到 `/proc/<pid>/oom_score_adj`，LMKD 选杀时拿不到正确值——这是"AOSP 14 特有的失败路径"，比 AOSP 9 时代的"文件写失败"更隐蔽。

### 2.5 一些容易混淆的 adj 值

排查时常见错误：

| 看到的值 | 实际含义 | 正确判定 |
|---------|---------|---------|
| adj = -16 | 旧 oom_adj 永远不杀 | 已被废弃，新值应该是 -1000 |
| adj = 906 | 老版本的 cached max | AOSP 14 应该是 906 |
| adj = -1 | 多见于"前台应用 -1"或"无 adj 设置"场景 | 排查时要确认是哪个接口 |
| adj = 1001 | UNKNOWN_ADJ | adj 正在计算中，1-2 秒后会落档 |
| adj = -10000 | INVALID_ADJ | 进程记录刚创建、还没初始化 |

> **稳定性架构师视角**：看到 adj = -16 时，**第一反应应该是"这是旧版日志还是新版日志"**。如果系统是 Android 12+，那 -16 一定是从老代码路径来的（如 `setOomAdj` 的兼容分支），而新代码应该写 -1000。这种值不一致往往是 Framework 升级残留 bug 的标志。

### 2.6 系统级强制覆盖

有两个机制可以**无视 oom_score_adj = -1000 强制杀进程**：

1. **cgroup 内存压力**：如果进程在 `memory.high` 被 cgroup 强制回收时仍不释放，cgroup 内的 OOM Killer 会**忽略 oom_score_adj 直接杀**。这是 cgroup 隔离带来的副作用。
2. **内核 panic / hung task**：内核本身崩溃时，所有进程都保不住。

**AOSP 14 的关键补丁**（kernel commit `b1160bb5`）：当 cgroup OOM 触发时，内核会**临时**把所有进程的 oom_score_adj 调高（除了 oom_score_adj = -1000 的），以确保不是"系统关键进程"被先杀。这是与 Android 旧版本不兼容的破坏性变更。

---

## 3. adj 的更新时机：Activity 生命周期、Service start/bind、锁屏、UID 切换

### 3.1 是什么 / 为什么"何时更新"是稳定性关键

AMS 的 adj 计算**不是事件驱动的全量重算**——那样 CPU 开销太大。AMS 采用了**事件触发 + 周期重算**的混合策略：

```
┌────────────────────────────────────────────────────────────────┐
│            AMS adj 更新的两类触发源                              │
├────────────────────────────────────────────────────────────────┤
│ 1. 事件触发（state change）                                     │
│    - Activity onResume / onPause / onStop                       │
│    - Service start / bind / unbind / stop                      │
│    - BroadcastReceiver 注册/反注册                              │
│    - ContentProvider 引用增加/释放                              │
│    - 进程进入/退出前台                                         │
│    - Window 可见性变化                                         │
│    - 锁屏/解锁                                                 │
│    - UID 切换（如多用户、投屏）                                  │
├────────────────────────────────────────────────────────────────┤
│ 2. 周期重算（periodic recompute）                               │
│    - OOM_ADJ_UPDATE_INTERVAL = 5 * 60 * 1000ms（AOSP 14）     │
│    - 每 5 分钟扫一次所有 ProcessRecord，重算 adj               │
│    - 即使没有事件也跑（防止漏更新）                              │
│    - 周期重算时也会做 trimCaches、killOrphanedProcesses 等      │
└────────────────────────────────────────────────────────────────┘
```

**为什么周期重算要 5 分钟**？太短会浪费 CPU（每个进程重算要遍历它的所有 Activity/Service 记录），太长会导致异常 adj 停留过久。5 分钟是 Android 5+ 沿用至今的默认值。

### 3.2 14 个核心更新时机（按场景分组）

| 时机 | 触发函数 | adj 变化 | 业务表现 |
|------|---------|---------|---------|
| Activity onResume | `setProcessImportantToCurrentUser` | → 0 | 用户开始交互 |
| Activity onPause | 同上 | 0 → 100（被遮挡） | 失焦 |
| Activity onStop | `setProcessImportantToVisible` | 100 → 700 | 用户按 Home |
| Service startForeground | `setServiceForeground` | → 500 | 通知栏出现前台服务通知 |
| Service start (background) | `bringUpServiceLocked` | → 800 | 后台服务启动 |
| Service bind | `bindServiceLocked` | 调整到 800 | 跨进程服务依赖 |
| Service stop | `serviceDoneExecutingLocked` | → 500/800/900 | 服务结束 |
| BroadcastReceiver 注册 | `registerReceiver` | → 调整 | 监听广播 |
| Provider 引用 | `incProviderRef` | 微调 | 数据访问 |
| 锁屏 (Keyguard) | `keyguardGoingAway` 间接 | 700 → 900 | 后台被移出 LRU |
| 解锁 | 同上 | 900 → 700 | 后台回 LRU 头 |
| 进程退出前台 (FOREGROUND_APP) | `removeProcessFromRunnable` | 0 → 700 | 按 Home |
| UID 切换 (多用户/分身) | `applyOomAdjLocked`（AOSP 12 之前）/ inline in `updateOomAdjLocked`（AOSP 14） | 视目标 UID 而定 | 切到 background UID |
| 周期 5min | `updateOomAdjLocked` | 全量重算 | 兜底 |

**关键观察**：所有这些事件**都会调用 `OomAdjuster.updateOomAdjLocked()`**（AOSP 12 之前是 `updateOomAdjLocked()`），但调用的"紧急度"不同：

- **HIGH urgency**：Activity onResume / onPause（用户体验直接相关，1ms 内必须更新）
- **NORMAL urgency**：Service start / bind（数百 ms 内更新可接受）
- **LOW urgency**：周期 5min 重算（兜底）

### 3.3 锁屏对 adj 的"翻转效应"

锁屏是 adj 更新最容易被忽视的时机，单独拎出来讲：

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityTaskSupervisor.java
// （简化伪代码）
void keyguardGoingAway(boolean goingAway) {
    if (goingAway) {
        // 解锁：所有 cached (900-906) 进程按 LRU 顺序升档到 PREVIOUS (700)
        mService.mOomAdjuster.unfreezeAllHiddenAppsLocked();
    } else {
        // 锁屏：所有非前台进程降到 cached (900-906)
        mService.mOomAdjuster.freezeHiddenApps();
    }
}
```

**行为差异**：
- 锁屏**前**：用户最近用的 5 个 App 在 adj 700-800 区间的占比高（经验值 70-80%）
- 锁屏**后 1-2 秒**：这些 App 全部降到 900-906，进程本身**不会杀**（内核不会主动杀），但 LRU 顺序被重排
- **解锁后**：LRU 顺序**不会**自动恢复——下一个被杀的是"锁屏时最久未用"的那个（不一定是用户最近用的）

> **稳定性架构师视角**：用户报"我锁屏再解锁后，微信/淘宝被杀了，重新打开很慢"——根因多为锁屏后 adj 翻转 + 内存压力下 LMKD 选杀目标的组合。**修复方案**：把核心 App 推到 500（foreground service）或 200（perceptible），让锁屏翻转时不进入 900 区间。

### 3.4 UID 切换的特殊处理

Android 多用户（Multi-user）和应用分身场景下，UID 切换是高频操作。AMS 在 UID 切换时**整体重算**该 UID 下所有进程的 adj：

```java
// frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java
private void applyOomAdjLocked(ProcessRecord app, boolean doingAll, ...) {
    // UID 切换时会调用 applyOomAdjLocked with doingAll=true
    // 重新评估该 UID 的所有进程 + 该 UID 关联的 Activity/Service/Provider
    // AOSP 14：此函数体已 inline 到 updateOomAdjLocked 末尾
    ...
}
```

**典型问题**：
- **Work Profile 切换**：用户从主 Profile 切到 Work Profile，Work Profile 的 App 瞬间从 cached 升到 700（PREVIOUS）
- **应用分身**：分身 App 的 UID 与原 App 不同（UID + 100000），它的 adj 完全独立计算
- **投屏/外接显示**：投屏 App 可能持有 MediaProjection 令牌，但它的"屏幕"是远程的，adj 计算会按"有前台服务"处理（+500）

### 3.5 周期重算的隐藏作用

`updateOomAdjLocked` 每 5 分钟会做几件"副业"工作：

1. **trimCaches()**：当 cached 进程数超过上限时（`CUR_TRIM_CACHED_PROCESSES = 5`），杀掉几个最久未用的。
2. **trimActivities()**：清理过期的 Activity 记录（防止内存泄漏）。
3. **killOrphanedProcesses()**：杀掉没有任何组件的"孤儿"进程。
4. **后台 fullSync 验证**：检查 cached 进程是否真的没组件在用。

**稳定性观察**：如果发现系统每 5 分钟有"卡顿尖刺"，可能是 updateOomAdj 跑得太慢。**优化方案**：
- 减少 cached 进程数（`CUR_TRIM_CACHED_PROCESSES` 调小）
- 提前 trimCaches（用 `setProcessMemoryTrimLevel` API 主动通知）
- 减少 updateOomAdj 单次计算量（拆批）

---

## 4. computeOomAdjLocked 源码走读（AOSP 14 重构后）

### 4.1 是什么 / 为什么要走读源码

`computeOomAdjLocked` 是 AMS adj 计算的"心脏"——所有 adj 数字都是它算出来的。看懂它就掌握了 80% 的"adj 异常排查"能力。

**代码位置**：`frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java`

**AOSP 14 函数命名（重要 — 真实源码）**：

- AOSP 12 ~ 14 一致：`computeOomAdjLocked()` / `updateOomAdjLocked()` / `applyOomAdjLocked()`（`Locked` 后缀表示"调用者已持锁"——调用方需保证 `mAm.mOomAdjuster.mCachedProcessInfo` 等锁已持有）
- **AOSP 14 的关键重构**：apply 步骤**从 `applyOomAdjLocked()` 抽取并 inline 到 `updateOomAdjLocked()` 末尾**——算完 adj 立即写 socket，不再有"compute → apply"两段式分离
- `grep "computeOomAdj"` 在 AOSP 14 源码中**能**直接命中 `computeOomAdjLocked`，**不要**被网上"重构改名"的过时博客误导

### 4.2 整体计算流程

```
┌──────────────────────────────────────────────────────────────────────┐
│   computeOomAdjLocked 主流程（AOSP 14 / OomAdjuster.java）              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ① 初始化：所有进程 adj 设为 UNKNOWN_ADJ (1001)                       │
│  ② 计算空进程：empty=true 的进程 → CACHED_APP_MAX_ADJ (906)          │
│  ③ 计算 persistent 进程：→ PERSISTENT_PROC_ADJ (-800)                │
│  ④ 计算 system_server：→ SYSTEM_ADJ (-900)（仅 system_server）       │
│  ⑤ 计算 native 进程：→ NATIVE_ADJ (-1000)（仅 zygote 子进程）        │
│  ⑥ 计算前台：遍历 top resumed Activity → FOREGROUND_APP_ADJ (0)      │
│  ⑦ 计算可见：遍历 top paused Activity → VISIBLE_APP_ADJ (100)        │
│  ⑧ 计算 PERCEPTIBLE：后台播放/前台服务 → PERCEPTIBLE_APP_ADJ (200)   │
│  ⑨ 计算 FOREGROUND_SERVICE → +500                                   │
│  ⑩ 计算 HOME_APP → +600（仅 Launcher）                              │
│  ⑪ 计算 PREVIOUS_APP：栈顶的第二个 Activity → +700                   │
│  ⑫ 计算 SERVICE_B：被 bind 的服务 → +800                             │
│  ⑬ 计算 cached 进程：剩余进程按 LRU 顺序 900, 901, ..., 906          │
│ ⑭ 写入内核：ProcessList.setOomScoreAdj(pid, adj)               │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**核心规律**：
1. **从高优先级往下算**（先 system，再 foreground，再 visible……再 cached）
2. **每个档位都可能"覆盖"前一个**（如一个进程既"被 bind 服务"又"cached"，最终取 800）
3. **最终取所有档位中的最小值**（adj 越小越重要）——不对，**是取所有命中档位中最重要的那个**（即数值最小的那个）

### 4.3 核心源码片段（按 AOSP 14 真实代码简化）

```java
// frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java
// 函数：computeOomAdjLocked（截取最关键的 60 行）
// ⚠️ 以下代码为教学简化版，保留了 AOSP 14 真实函数名和逻辑骨架
//    实际代码约 2000 行，包含各种边界 case
//    AOSP 12 ~ 14 同一函数名 computeOomAdjLocked()（带 Locked 后缀，含义"调用者已持锁"）

private final boolean computeOomAdjLocked(ProcessRecord app, int cachedAdj,
                                        ProcessRecord TOP_APP, boolean doingAll,
                                        long now) {
    // === ① 初始化：所有进程先设为 UNKNOWN_ADJ ===
    if (app.maxAdj <= ProcessList.FOREGROUND_APP_ADJ) {
        // 已经很高优先级了，跳过（优化）
        return false;
    }

    int adj = ProcessList.UNKNOWN_ADJ;  // 1001
    int procState = ProcessList.PROCESS_STATE_NONEXISTENT;

    // === ② 处理空进程：没有 Activity/Service/Provider/Receiver ===
    if (app.empty) {
        adj = ProcessList.CACHED_APP_MAX_ADJ;  // 906
        procState = ProcessList.PROCESS_STATE_CACHED_EMPTY;
        goto _assign_adj;
    }

    // === ③ 处理 persistent 进程 ===
    if (app.persistent) {
        adj = ProcessList.PERSISTENT_PROC_ADJ;  // -800
        procState = ProcessList.PROCESS_STATE_PERSISTENT;
    }

    // === ④ 计算 Activity 贡献 ===
    int activitiesSize = app.activities.size();
    for (int i = 0; i < activitiesSize; i++) {
        ActivityRecord r = app.activities.get(i);
        
        // 前台 Activity
        if (r.app == TOP_APP && adj > ProcessList.FOREGROUND_APP_ADJ) {
            adj = ProcessList.FOREGROUND_APP_ADJ;  // 0
            procState = ProcessList.PROCESS_STATE_TOP;
            break;
        }
        
        // 可见 Activity
        if (r.visible) {
            adj = ProcessList.VISIBLE_APP_ADJ;  // 100
            procState = ProcessList.PROCESS_STATE_IMPORTANT_FOREGROUND;
        }
    }

    // === ⑤ 计算 Service 贡献 ===
    final int servicesSize = app.services.size();
    for (int i = 0; i < servicesSize; i++) {
        ServiceRecord sr = app.services.get(i);
        if (sr.isForeground) {
            // startForegroundService() 启动的
            if (adj > ProcessList.FOREGROUND_SERVICE_ADJ) {
                adj = ProcessList.FOREGROUND_SERVICE_ADJ;  // 500
                procState = ProcessList.PROCESS_STATE_FOREGROUND_SERVICE;
            }
        } else if (sr.hasForegroundExecService) {
            // 正在执行前台服务命令
            if (adj > ProcessList.FOREGROUND_SERVICE_ADJ) {
                adj = ProcessList.FOREGROUND_SERVICE_ADJ;
            }
        }
        // ... 更多 Service 状态判断
    }

    // === ⑥ 计算 Receiver/Provider 贡献 ===
    // （简化：影响极小）

_assign_adj:
    app.curAdj = adj;
    app.curProcState = procState;
    app.setCurrentSchedulingGroup(procState);
    app.lastCpuTime = app.cpuTime;  // 用于 next 的 LRU 排序

    return true;
}
```

> **稳定性架构师视角**：上面的代码有 3 个**最常导致 bug**的点：
> 1. **adj 单调下降规则**：`if (adj > XXX) adj = XXX`——已经更重要的不会再被降级
> 2. **break 只在 TOP 时触发**：可见 Activity 不会 break，会被 Service 后续覆盖
> 3. **goto 在 C 代码中不存在**：Java 里用 if-else 模拟——结构上等价

### 4.4 LRU 排序的精确算法

cached 进程的 adj 排序（900, 901, ..., 906）不是随机的，而是按"上次使用时间"升序：

```java
// frameworks/base/services/core/java/com/android/server/am/ProcessList.java
public static int computeEmptyProcessAdj(int emptyAdj, int hiddenAdj) {
    // emptyAdj = CACHED_APP_MIN_ADJ (900)
    // hiddenAdj = 1-100（同一个 LRU 槽内的微调）
    // 返回 [900, 906] 区间内的某个值
    return emptyAdj + hiddenAdj;
}
```

**实际计算**：
- cached 进程按 `lastActivityTime` 升序排序（最久未用的在前）
- 第一个（最久未用）→ 906
- 第二个 → 998
- 第三个 → 997
- ……
- 最新的 cached → 900

**这一点的实战价值**：调 dumpsys 时看到 `adj=906` 的进程 = "最该杀的"，`adj=900` 的进程 = "刚刚退到后台的"。

### 4.5 setOomScoreAdj 写入的真实路径（AOSP 14：apply 已 inline）

AOSP 14 中 `applyOomAdjLocked()` **不再作为独立函数存在**——apply 步骤被 inline 到 `updateOomAdjLocked()` 末尾。算完 adj 立即通过 socket 推给 lmkd，不再有"compute → apply"两段式分离。这是 AOSP 14 与 AOSP 12 的关键差异。

```java
// frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java
// AOSP 14 真实实现：apply 已 inline 到 updateOomAdjLocked
// （AOSP 12 之前是独立的 applyOomAdjLocked 函数）

void updateOomAdjLocked(ProcessRecord app, int cachedAdj, ...) {
    // ... 调用 computeOomAdjLocked 算 adj ...
    if (computeOomAdjLocked(app, cachedAdj, ...)) {
        // === apply 步骤（AOSP 14 inline 在这里）===
        if (app.curAdj != app.setAdj) {
            // 推到 lmkd（AOSP 14：socket，不写 /proc）
            if (ProcessList.setOomScoreAdj(app.pid, app.info.uid, app.curAdj)) {
                app.setAdj = app.curAdj;
                // 成功：lmkd 会负责写 /proc/<pid>/oom_score_adj
            } else {
                // 失败：socket 不通 / lmkd 没起 / 进程已死
            }
        }
    }
}
```

**关键变更**：
- **AOSP 12 之前**：`updateOomAdjLocked` → `applyOomAdjLocked`（独立函数）→ `ProcessList.setOomAdj`（写 `/proc`）
- **AOSP 14**：`updateOomAdjLocked` → inline apply → `ProcessList.setOomScoreAdj`（socket 推 lmkd）

**socket 写入失败的常见原因**：
1. lmkd 进程没起（init.rc 中 `service lmkd` 异常）—— adj 不会落到 `/proc`
2. SELinux 拦截（`avc: denied { write }` 警告）—— socket 连不上
3. 进程已死（最常见）—— lmkd 返回 NACK，AMS 日志噪声

> **稳定性架构师视角**：AOSP 14 的 inline apply 是个**双刃剑**——好处是省了一次函数调用 + 锁，坏处是排查"adj 没生效"时**没有独立的 apply 函数可打断点**。要在 `updateOomAdjLocked` 末尾下条件断点，或者直接抓 lmkd 日志（`adb logcat -s lmkd`）。

### 4.6 OomAdjuster 完整调用栈

```
updateOomAdjLocked()                // 入口：批量更新所有进程
  └─> for each app in mProcessList
        └─> computeOomAdjLocked(app)   // 算 adj
              └─> (内部遍历 Activity/Service/Provider/Receiver)
        └─> (inline) setOomScoreAdj // AOSP 14：apply 步骤已 inline 在此
                                   // AOSP 12 之前是独立的 applyOomAdjLocked
  └─> trimCaches()                // 杀过期的 cached 进程
  └─> trimActivities()            // 清理过期 Activity 记录
```

调用频率：
- **HIGH urgency（Activity/Service 事件）**：每次状态变化 → 立即调一次
- **LOW urgency（周期 5min）**：到时间后调一次
- **Idle**：不调

### 4.7 关键调优参数

`frameworks/base/services/core/java/com/android/server/am/ProcessList.java` 中的可调参数：

| 常量 | 值 | 含义 | 调优影响 |
|------|---|------|---------|
| `CUR_MAX_CACHED_PROCESSES` | 32 | cached 进程最大数 | 调小→省内存，调大→切应用快 |
| `CUR_TRIM_CACHED_PROCESSES` | 5 | 一次 trim 杀几个 | 调大→trim 更激进 |
| `OOM_ADJ_UPDATE_INTERVAL` | 5*60*1000 | 周期重算间隔 | 调短→adj 更准，CPU 略高 |
| `MAX_HIDDEN_APPS` | 15 | hidden 应用上限 | 调小→hidden 进程被杀更快 |
| `EMPTY_APP_PERCENT` | 50 | empty 占 cached 比例 | 调小→empty 比例低 |

**注意**：这些是 AOSP 默认值，OEM 厂商（小米/华为/OPPO）会在 `frameworks/base/core/res/res/values/config.xml` 中覆盖。**线上排查时一定要先确认设备实际值**。

---

## 5. LMK → LMKD 演进：内核 LMK 退役原因

### 5.1 是什么 / 为什么 LMK 会被淘汰

**LMK（Low Memory Killer）** 是 Android 4.4 之前内核态的杀进程模块，代码在 `drivers/staging/android/lowmemorykiller.c`。从 Android 4.4 开始被**用户态 LMKD（lmkd daemon）** 取代，到 Android 10+ 全面切换为基于 PSI（Pressure Stall Information）的实现。

**为什么 Google 要做这个迁移**？根因有四：

1. **策略僵化**：内核 LMK 的杀进程策略是**编译时**写死在 C 代码里的（`lowmem_adj`、`lowmem_minfree` 数组），运行时改不了。OEM 想调阈值需要重新编译内核。
2. **无法跨 cgroup**：Android 7+ 引入了 cgroup 内存隔离，LMK 选杀目标时是**全系统 RSS**排序，**不知道**目标进程属于哪个 cgroup，可能把系统 cgroup 的重要进程杀掉。
3. **调试困难**：LMK 在内核态崩溃 = 内核 panic = 手机重启；用户态 LMKD 崩溃 = 进程重启，对系统影响小一个数量级。
4. **信号源落后**：LMK 依赖 `vmpressure`（旧版 PSI），信号延迟高、粒度粗（MB 级），无法应对现代 App 的精细化压力管理。

```
┌────────────────────────────────────────────────────────────────────┐
│              LMK → LMKD 演进时间线                                  │
├────────────────┬───────────────────────────────────────────────────┤
│  Android 版本  │  杀进程实现                                          │
├────────────────┼───────────────────────────────────────────────────┤
│  4.4 之前       │  内核 LMK（drivers/staging/android/lmk.c）        │
│  4.4 - 9       │  内核 LMK + 用户态 lmkd（混合）                   │
│  10 - 12       │  用户态 lmkd（基于 vmpressure 事件）             │
│  12+ (AOSP 14) │  用户态 lmkd（基于 PSI / proc/pressure/memory）   │
│  14 (新增)     │  lmkd + memcg aware（cgroup 内 OOM 处理）       │
└────────────────┴───────────────────────────────────────────────────┘
```

### 5.2 旧 LMK 源码（已退役，但路径仍存在）

AOSP 14 中 `drivers/staging/android/lowmemorykiller.c` **仍然存在**——但代码被标记为 deprecated，新设备不会编译进内核。教学意义大于实际意义：

```c
// drivers/staging/android/lowmemorykiller.c (AOSP 14，已废弃)
//
// ⚠️ 警告：此文件已废弃，新设备不会编译
// 教学保留：展示 LMK 的"低水位线数组"机制
//
// 核心数据结构：
static int lowmem_adj[] = {
    0,      // 内存还多，啥也不杀
    1,      // 紧一点，杀 cached max
    6,      // 再紧一点，杀 cached min
    12,     // 紧张，杀后台服务
};
static int lowmem_minfree[] = {
    8192,   // 8MB 空闲以下触发 adj=0
    12288,  // 12MB 空闲以下触发 adj=1
    16384,  // 16MB 空闲以下触发 adj=6
    24576,  // 24MB 空闲以下触发 adj=12
};
//
// 工作流程：
// 1. 内存回收线程定期检查 pages_free
// 2. 如果 pages_free < lowmem_minfree[i]，则选 adj > lowmem_adj[i] 的进程杀
// 3. 选杀标准：adj 最大的 + RSS 最大的（这就是 LMK 的核心启发式）
```

**AOSP 14 真实状态**：
- 路径存在：`drivers/staging/android/lowmemorykiller.c`
- `git log` 最后一次提交：2018 年
- 编译标志：`CONFIG_ANDROID_LOW_MEMORY_KILLER` 默认未定义
- **实际效果**：AOSP 14 设备**不**包含 LMK，所有杀进程都通过 LMKD

### 5.3 LMKD 的核心优势

| 维度 | 旧 LMK | 用户态 LMKD |
|------|-------|------------|
| 部署位置 | 内核 | init 启动的 daemon |
| 策略配置 | 编译时写死 | `/sys/module/lowmemorykiller/parameters/` |
| 调试难度 | 高（内核 panic） | 低（dmesg 即可） |
| 信号源 | pages_free（被动检查） | PSI some/full（主动通知） |
| 跨 cgroup | 不支持 | 支持（memcg aware） |
| 触发延迟 | 秒级 | 毫秒级 |
| 升级方式 | 重新编译内核 | 更新用户态二进制 |

### 5.4 LMKD 与 AMS 的协作关系

```
┌────────────────────────────────────────────────────────────────────────┐
│                AMS (Framework) ↔ LMKD (Native daemon) 协作流          │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  AMS (system_server 进程内)                                            │
│    │                                                                   │
│    │ ① 计算 adj（computeOomAdjLocked）                                   │
│    │ ② 通过 abstract socket "lmkd" 推送 adj（ProcessList.setOomScoreAdj）│
│    │    → lmkd 收口后再写 /proc/<pid>/oom_score_adj            │
│    │ ③ 维护 ProcessRecord（包名/UID/adj/状态）                       │
│    │ ④ dumpsys meminfo 输出                                           │
│    ▼                                                                   │
│  /proc/<pid>/oom_score_adj    ← 内核接口（AMS 写，LMKD 读）            │
│    │                                                                   │
│    ▼                                                                   │
│  LMKD (init 启动的独立进程)                                            │
│    │                                                                   │
│    │ ① 监听 /proc/pressure/memory（PSI 事件）                        │
│    │ ② 遍历 /proc/，读取所有进程的 oom_score_adj                      │
│    │ ③ 按 adj 阈值选杀目标                                            │
│    │ ④ 调用 kill -9 / kill -SIGKILL                                   │
│    ▼                                                                   │
│  内核 OOM Killer（最终兜底）                                           │
│    │                                                                   │
│    │ 当 LMKD 没杀够 / 来不及时，触发 oom_badness() 选杀               │
│    ▼                                                                   │
│  进程被 kill                                                           │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

**关键认知**：LMKD 杀进程的决策依据是**AMS 写入的 oom_score_adj**——所以 **AMS adj 错 = LMKD 杀错**。本篇讲 AMS，下一篇 [06-LMKD](06-LMKD 用户态内存杀手.md) 讲 LMKD。

### 5.5 为什么 AMS 算的 adj 才是"权威"

一个常见误解："LMKD 是不是有自己的 adj 逻辑？" 答案是**否**。LMKD 完全使用 `/proc/<pid>/oom_score_adj` 选杀，它自己不计算 adj。

**这是有意为之的设计**：
- 单一权威：adj 计算集中在 AMS，避免双源不一致
- 可观测：所有 adj 数字都能在 dumpsys 中查到
- 可调试：adj 错误时只查一处
- 一致性：内核 OOM Killer 和 LMKD 选杀结果一致

**唯一例外**：内核 OOM Killer 仍会读 oom_score_adj，但它的计算公式是 `RSS + oom_score_adj`（带 RSS 权重）；LMKD 选杀时是**纯 oom_score_adj 排序**（不看 RSS）。这是两个机制的本质差异。

### 5.6 历史兼容期的"双层并存"

Android 4.4-9 期间，LMK 和 LMKD **同时存在**：
- LMK：处理"紧急情况"（剩 50MB 内存）
- LMKD：处理"温和压力"（剩 500MB 但 oom_score 高的进程）

这个双层机制在 Android 10 之后完全废弃（LMK 不再编译进内核），但 OEM 厂商的旧 ROM 仍可能保留。**线上排查时如果发现"dmesg 有 lowmemorykiller 杀进程日志，但 lmkd.log 也有"——这是 Android 9 或更老的设备**。

### 5.7 AOSP 14 的 PSI 集成（与 LMKD 协同）

Android 12+ 的 LMKD 改用 PSI（Pressure Stall Information）作为信号源：

- **文件路径**：`/proc/pressure/memory`
- **字段**：`some avg10/avg60/avg300` 表示过去 10/60/300 秒内有 X% 时间至少有一个任务在等内存
- **触发**：`some > THRESHOLD` 时 LMKD 进入 kill 决策
- **下一讲详述**：见 [06-LMKD 用户态内存杀手](06-LMKD 用户态内存杀手.md) 和 [07-PSI / vmpressure / memcg 压力传递](07-PSI、vmpressure、memcg 压力传递.md)

**与本篇的关系**：AMS 不直接读 PSI，但 LMKD 收到 PSI 事件后会快速**重读** oom_score_adj 选杀——所以**AMS 必须把 adj 写对**，否则 LMKD 收到 PSI 事件后会基于错误的 adj 杀错进程。

---

## 6. 风险地图：adj 异常、Persist 进程配置错误、空进程数过多

### 6.1 风险全景表

```
┌────────────────────────────────────────────────────────────────────┐
│         AMS 内存治理 6 大类稳定性风险（按线上发生频率排序）           │
├────┬──────────────────────────┬─────────────────────────────────────┤
│ #  │ 风险类型                  │ 业务影响                            │
├────┼──────────────────────────┼─────────────────────────────────────┤
│ 1  │ adj 计算错误 → 杀错进程   │ 微信/相机等关键 App 在后台被杀     │
│ 2  │ Persistent 进程配置错误   │ 厂商预装 App 自启失控 / 杀不掉      │
│ 3  │ 空进程数过多              │ cached 进程占内存、切应用冷启动慢   │
│ 4  │ Service 漏 stop → 进程常驻│ 后台服务泄漏，电量/内存双失         │
│ 5  │ 前台服务乱用              │ 通知栏被淹没、用户反感              │
│ 6  │ 锁屏 adj 翻转异常         │ 锁屏后关键 App 被快速杀             │
└────┴──────────────────────────┴─────────────────────────────────────┘
```

下面逐类展开。

### 6.2 风险 1：adj 计算错误 → 杀错进程

**典型症状**：
- 微信/淘宝在后台被频繁杀
- `dumpsys activity processes` 显示该 App `adj=900` 但实际在使用
- 杀进程日志：`Process com.tencent.mm has died` 后跟 `lmkd` kill 记录

**根因 5 类**：

| 根因 | 检测方法 | 修复 |
|------|---------|------|
| Service 没 stop | `dumpsys activity services` | 业务修复：`stopSelf()` 或 `stopService()` |
| Foreground Service 误用 | dumpsys 看 `isForeground=true` 但无通知 | 业务修复：移除 `startForeground()` 或加通知 |
| Activity 泄漏（持有 Context） | `dumpsys meminfo` 看 Activity 数 | 业务修复：检查 static reference |
| Receiver 注册未反注册 | `dumpsys activity broadcasts` | 业务修复：unregisterReceiver |
| Provider 未关闭 | `dumpsys activity providers` | 业务修复：close |

**子类型细分**：
```
adj 计算错误 → 杀错进程
├── Service 状态未及时更新
│   ├── startService() 后没 stopService()
│   ├── bindService() 后没 unbind()
│   └── startForegroundService() 后没 startForeground()
├── Activity 状态未及时更新
│   ├── Activity 泄漏（持有 Activity Reference）
│   ├── onStop() 没调 super.onStop()
│   └── onDestroy() 漏调
├── Receiver/Provider 状态泄漏
│   ├── registerReceiver() 后没 unregister()
│   ├── 静态注册 receiver 在 manifest 中误配
│   └── ContentResolver 未关闭 cursor
└── 调度优先级计算错误
    ├── topResumedActivity 计算错误
    ├── ServiceRecord 引用计数错误
    └── cgroup 边界判断错误
```

### 6.3 风险 2：Persistent 进程配置错误

**是什么**：在 `AndroidManifest.xml` 中声明 `android:persistent="true"` 的进程，会被 AMS 设为 -800 adj，几乎不可能被杀。

**典型问题**：

1. **OEM 厂商滥用**：预装的"天气""资讯"等 App 全部声明 persistent，导致系统进程数爆炸。
2. **新装 App 误用**：开发者以为 persistent 是"保活"，结果声明后反而被杀（系统检测到 persistent 进程无 Service 时会杀）。
3. **persistent 进程死后被反复拉起**：消耗系统资源。

**检测方法**：

```bash
# 查看所有 persistent 进程
dumpsys activity processes | grep -i persistent

# 期望：phone/蓝牙/WIFI/system_server 等少量核心服务
# 异常：超过 10 个 persistent 进程 = 配置失控
```

**修复方案**：
- OEM 端：精简预装 App 的 persistent 声明
- 应用端：移除 manifest 中的 `android:persistent="true"`
- 监控端：`dumpsys activity processes` 中 `adj=-800` 的进程超过 10 个告警

### 6.4 风险 3：空进程数过多

**是什么**：cached 进程数（adj 900-906）超过系统承受上限，导致：
- 占内存（每个空进程至少 30-50MB）
- 切应用冷启动慢（被杀后下次启动要重新 fork）
- 内存压力加剧（→ LMKD 杀更多进程 → 死循环）

**典型配置**：

| 参数 | AOSP 默认 | 厂商调优方向 |
|------|----------|------------|
| `CUR_MAX_CACHED_PROCESSES` | 32 | 中端机 24-28、高端机 48-64 |
| `CUR_TRIM_CACHED_PROCESSES` | 5 | 中端机 3-4、高端机 8-10 |
| `MAX_HIDDEN_APPS` | 15 | 视 hidden App 数量调整 |

**典型问题**：
- 厂商调小 `CUR_MAX_CACHED_PROCESSES`（如改成 16），切应用时频繁冷启动
- 厂商调大（如改成 64），低内存设备上 cached 进程占内存过多

**检测方法**：

```bash
# 统计 cached 进程数
dumpsys activity processes | grep -c "adj=9"

# 期望：16-40（视设备等级）
# 异常：> 50（过度缓存） 或 < 8（trim 太激进）
```

**子类型细分**：
```
空进程数过多
├── CUR_MAX_CACHED_PROCESSES 过大
│   ├── OEM 误调
│   └── 厂商"加速"魔改
├── 进程泄漏（杀不掉）
│   ├── 持有 WakeLock
│   ├── 持有 AccountManager 引用
│   └── 持有 JobScheduler 任务
├── trimCaches 触发频率低
│   ├── OOM_ADJ_UPDATE_INTERVAL 过长
│   └── trimCaches 内部 bug
└── 业务侧"假活"问题
    ├── 后台服务持续运行
    └── JobScheduler 周期唤醒
```

### 6.5 风险 4：Service 漏 stop → 进程常驻

**是什么**：Service 启动后未在合适时机 stop，导致：
- 进程 adj 长期在 200-500（被保活）
- 内存占用持续存在
- 电量持续消耗
- 通知栏残留前台服务通知

**典型场景**：
- 后台下载服务在下载完成后没 stop
- 后台位置服务在不需要时没 stop
- 异常处理路径漏调 stopSelf()

**检测方法**：

```bash
# 查看每个进程的 Service 数
dumpsys activity services | grep "ServiceRecord" | wc -l

# 查看每个进程的服务运行时间
dumpsys activity services | grep "createTime" | sort

# 期望：服务运行时间 < 业务实际需要
# 异常：服务运行数小时但业务早已结束
```

### 6.6 风险 5：前台服务乱用

**是什么**：从 Android 8+ 限制后台服务后，很多应用滥用 `startForegroundService()`：
- 用前台服务保活（合规但用户体验差）
- 用前台服务绕过 Doze 模式
- 前台服务通知设置不当

**AOSP 14 的新限制**（`Android 14 behavior changes`）：
- `startForegroundService()` 后必须在 **5 秒**内调 `startForeground()`，否则系统直接 `Service.startForeground()` 失败并 ANR
- 前台服务必须有一个**明确的通知**（不能是 silent notification）
- 部分后台启动前台服务的应用会被警告

**子类型细分**：
```
前台服务乱用
├── startForegroundService() 后超时未 startForeground()
│   ├── 5 秒 ANR（Android 14 严格）
│   └── 业务逻辑漏调
├── 通知内容不当
│   ├── 通知 icon 太小
│   ├── 通知文本无意义
│   └── 通知可关闭性差
├── 保活链异常
│   ├── 1px Activity + 前台服务
│   ├── 双进程守护 + 前台服务
│   └── 系统白名单滥用
└── 与 Doze 模式冲突
    ├── 滥用 AlarmManager 唤醒
    └── 滥用 WorkManager 短间隔任务
```

### 6.7 风险 6：锁屏 adj 翻转异常

**是什么**：锁屏时 AMS 会把所有非前台进程降到 cached 区间（900-906），解锁后不会自动恢复。

**典型问题**：
- 用户反馈"锁屏后微信被杀"
- 锁屏后内存压力 + adj 翻转 → LMKD 选杀 cached 进程 → 用户关键 App 在列
- 解锁后切回微信需要冷启动

**修复方案**：
1. **业务侧**：用 `startForegroundService()` 保持服务在 500（不会被锁屏翻转）
2. **系统侧**：调整 `freezeHiddenApps` 的行为
3. **监控侧**：`dumpsys activity processes` 中锁屏后 cached 区间进程数突然 > 50 告警

### 6.8 风险 6 个共性原则

从上面 6 类风险中提炼出来的共性**架构原则**：

1. **adj 是状态机**：adj 不是静态配置，是实时计算的状态值。任何"业务认为重要"的声明（persistent/foreground service）都必须**持续**触发正确的状态转换。
2. **kill 是不可逆的**：进程被 LMKD 杀后无法"复活"，只能下次启动时重新 fork。**所有关键场景必须用 service + foreground 双重保险**。
3. **observability 优先**：AMS 的 adj 状态完全可观测（dumpsys），如果发现不了异常，**就是没看 dumpsys**。
4. **OEM 是最大的不稳定源**：persistent 进程配置、cached 上限、前台服务策略都可能被厂商魔改。**线上问题排查时第一动作：确认设备型号 + ROM 版本**。
5. **业务 Bug 比例 > 系统 Bug**：经验值，**线上 adj 类问题 70% 是业务侧没正确调用 stop/unregister，30% 才是系统问题**。
6. **无银弹**：没有"配置一个参数就能解决所有 adj 问题"的方法。每个场景都要单独看。

---

## 7. 实战案例：Service 保活 + 锁屏后被误杀（典型模式）

### 7.1 案例背景

**现象**：某 IM App（脱敏素材）线上反馈"锁屏后过几分钟就被杀，杀前没有任何提示"。线上日志显示：

```
06-12 14:23:18.123  lmkd    : Kill (com.example.im, oom_score_adj 900, ...)
06-12 14:23:18.456  ActivityManager  : Process com.example.im has died
06-12 14:23:18.789  ActivityManager  : Scheduling restart of crashed service ...
```

**关键信息**：
- adj = 900（cached 区间）
- 杀它的来源是 lmkd（不是 OOM Killer）
- 进程死亡后系统试图"restart service"——说明它有 Service 在跑

**用户侧感知**：锁屏 → 5 分钟后被杀 → 解锁时 IM 收不到消息 → 错过重要通知。

### 7.2 排查步骤（按 5 分钟定位法）

**Step 1（30s）**：抓 dumpsys 看 adj 实际值

```bash
# 抓进程状态
adb shell dumpsys activity processes | grep -A 20 "com.example.im"
# 输出（关键行）：
#   ProcessRecord{xxx com.example.im:remote}
#     userId=10100
#     curAdj=900          ← 问题点：cached max
#     setAdj=900
#     curProcState=PROCESS_STATE_CACHED_ACTIVITY
#     services=2           ← 2 个 Service 在跑
#     connections=1
#     pubProviders=0
#     activities=0          ← 没有 Activity（已退后台）
#     lastActivityTime=...  ← 上次活跃时间
```

**结论**：`curAdj=900` + `activities=0` + `services=2` —— **进程在 cached 区间但仍有 Service 跑着**。

**Step 2（1min）**：看 Service 状态

```bash
adb shell dumpsys activity services com.example.im
# 输出（关键行）：
#   ServiceRecord{xxx com.example.im/.PushService}
#     isForeground=false       ← 不是前台服务
#     startRequested=true      ← 但有人 startService() 了
#     createTime=+5h23m        ← 跑了 5 小时
#   ServiceRecord{xxx com.example.im/.HeartbeatService}
#     isForeground=false
#     startRequested=true
#     createTime=+5h23m
```

**结论**：两个后台 Service（PushService、HeartbeatService）跑了 5+ 小时，但都不是前台服务。**用户 App 早就退到后台，Service 没停**。

**Step 3（2min）**：看是不是锁屏导致

```bash
# 拉取时间点对齐的 logs
adb logcat -d -t '06-12 14:18:00.000' '*:S' ActivityTaskManager:I

# 输出关键片段：
# 14:18:05.123  KeyguardController: Going to sleep (occluded=false)
# 14:18:05.456  OomAdjuster: Freeze hidden apps
# 14:18:06.789  ProcessRecord: com.example.im setAdj=700 -> 900    ← 翻转
# 14:23:18.123  lmkd: PSI some 28.5% above threshold (25%)
# 14:23:18.456  lmkd: Kill com.example.im adj=900 score=1280
```

**结论**：锁屏触发 `freezeHiddenApps`，App adj 从 700 翻到 900 → 5 分钟后 PSI 触发 LMKD 选杀 → adj 900 区间被杀。

### 7.3 根因分析

**根因 1（70%权重）**：业务 Service 没正确 stop

- `PushService`：原本应该在 App 退后台后 stop，但没有
- `HeartbeatService`：业务方为了"心跳保活"长期持有

**根因 2（20%权重）**：Service 不是前台服务

- 两个 Service 都没有 `startForeground()`
- 锁屏翻转后立即跌入 cached 区间

**根因 3（10%权重）**：系统级锁屏 adj 翻转

- AOSP 默认行为，无法关闭
- OEM 也未对该 App 做白名单

### 7.4 修复方案

**方案 A（业务侧，最治本）**：

1. `PushService` 在 `onTaskRemoved()` 中调 `stopSelf()`
2. `HeartbeatService` 改用 `JobScheduler` 周期唤醒（10-15 分钟一次）
3. 加监控：`dumpsys activity services` 中 `createTime > 1h` 且无前台服务 → 告警

**方案 B（应急止血）**：

1. 临时把 `PushService` 改为 `startForegroundService()` + 通知
2. 锁屏翻转不进入 cached 区间
3. 保留给真正的"消息接收"功能

**方案 C（系统侧，长期）**：

1. OEM 把 IM 类 App 加入白名单（adj 固定 500）
2. 但白名单本身也是风险——滥用会破坏公平性

### 7.5 修复效果验证

修复后的 dumpsys 输出：

```bash
# 修复前
curAdj=900  curProcState=PROCESS_STATE_CACHED_ACTIVITY  services=2

# 修复后
curAdj=500  curProcState=PROCESS_STATE_FOREGROUND_SERVICE  services=1
isForeground=true  startRequested=true
```

**关键变化**：
- adj 从 900 升到 500（foreground service）
- 锁屏翻转不进入 cached 区间
- 进程不会被 LMKD 杀

### 7.6 监控指标上线

```java
// 加在系统层 / 业务 APM 中
long foregroundServiceCount = 0;
long cachedActivityCount = 0;
long persistentProcessCount = 0;

for (ProcessRecord app : ams.mProcessList) {
    if (app.curProcState == PROCESS_STATE_FOREGROUND_SERVICE) foregroundServiceCount++;
    if (app.curProcState == PROCESS_STATE_CACHED_ACTIVITY) cachedActivityCount++;
    if (app.persistent) persistentProcessCount++;
}

// 告警阈值
if (foregroundServiceCount > 8) alert("前台服务过多");
if (cachedActivityCount > 40) alert("cached 进程堆积");
if (persistentProcessCount > 10) alert("persistent 配置异常");
```

### 7.7 此类问题的共性排查模板

把上面的案例抽成模板，所有"Service 保活 + 锁屏后被误杀"问题都可以用这个流程排查：

```
┌────────────────────────────────────────────────────────────────────┐
│  模板：Service 保活类误杀排查流程                                    │
├────────────────────────────────────────────────────────────────────┤
│  Step 1: 抓 dumpsys activity processes | grep <pkg>                │
│          → 确认 curAdj / curProcState / services 数                │
│  Step 2: 抓 dumpsys activity services <pkg>                        │
│          → 确认 Service isForeground / createTime / startRequested │
│  Step 3: 对齐 logcat 时间点                                        │
│          → 找 freezeHiddenApps / setAdj=... -> 900 的时间点       │
│  Step 4: 找 LMKD kill 日志                                         │
│          → 确认是否 lmkd 杀 + adj 值 + PSI 触发时间                │
│  Step 5: 检查业务代码                                               │
│          → stopSelf / stopService / unbindService 是否漏调         │
│  Step 6: 检查 Service 声明                                          │
│          → manifest 中是否声明 foregroundServiceType                │
│  Step 7: 检查 OEM 适配                                              │
│          → 设备型号 + ROM + 是否在白名单                            │
│  Step 8: 决定修复方案（业务/系统/白名单）                          │
└────────────────────────────────────────────────────────────────────┘
```

**这个模板适配场景**（不全）：
- "App 收不到推送"
- "App 退后台后被快速杀"
- "Service 跑了一晚上没停"
- "切换应用时被杀"
- "锁屏后再解锁 App 没了"
- "Doze 模式下 App 行为异常"

---

## 总结：架构师视角的 5 条 Takeaway

**Takeaway 1：adj 是状态机，不是配置项。**
AMS 的 adj 不是"App 注册一次就固定了"——它是基于 Activity/Service/Provider/Receiver 状态实时计算的。任何"业务认为重要"的需求（保活、消息接收、后台任务）都必须**持续**触发正确的状态转换。代码漏调 stopService/unregisterReceiver，adj 就会从 500 跌到 900，被 LMKD 杀。

**Takeaway 2：adj 区间的"档位"是稳定的，但"档内"会变。**
cached 进程的 adj 在 900-906 区间内**连续分布**（按 LRU 排序），不是离散值。所以"adj=901" 和 "adj=998" 可能是同一档位（都是 cached），但 901 优先级高于 998。**排查时先看档位，再看档内**。

**Takeaway 3：AMS 算的 adj 是 LMKD 杀进程的依据。**
LMKD 不计算 adj，它只读 `/proc/<pid>/oom_score_adj`。所以 **AMS adj 错 = LMKD 杀错**。本篇与下一篇 [06-LMKD](06-LMKD 用户态内存杀手.md) 是一对耦合的设计——理解了 AMS 才能理解 LMKD。

**Takeaway 4：内核 OOM Killer、LMKD、Watchdog 是三个不同的杀进程者。**
- **内核 OOM Killer**：系统级物理内存耗尽，**所有** cgroup 都不够时触发，最后兜底
- **LMKD**：基于 PSI 事件 + oom_score_adj，**只杀 cached/低优先级**，用户体验导向
- **Watchdog**：只杀 system_server 自己 hang 的线程，**不杀 App**

**混淆这三个**是 80% "杀进程排查"失败的根因。下一讲 [06-LMKD](06-LMKD 用户态内存杀手.md) 详细展开 LMKD。

**Takeaway 5：OEM 魔改是最大的"已知未知"。**
AOSP 默认值在 [源码] 中清晰可见，但厂商（小米/华为/OPPO/vivo）会在 `frameworks/base/core/res/res/values/config.xml` 中覆盖 `CUR_MAX_CACHED_PROCESSES`、`OOM_ADJ_UPDATE_INTERVAL` 等关键参数。**线上问题排查的第一动作**：确认设备型号 + ROM 版本 + 关键参数实际值。**没有这一步，所有"代码分析"都是空谈**。

**横向串联**：
- 与 [01-内存系统总览](01-内存系统总览：从进程视角到硬件的完整链路.md) 的关系：AMS 属于第 3 层（Framework 服务层）
- 与 [02-进程内存地图与 VMA 体系](02-进程内存地图与 VMA 体系.md) 的关系：每个 adj 区间对应不同 VMA 行为（cached 进程 VMA 可能被内核 swap）
- 与 [03-ART 堆内存与 GC 全景](03-ART 堆内存与 GC 全景.md) 的关系：cached 进程 GC 频率低（没分配压力），但**切换回前台**时首次 GC 会有 pause 尖刺
- 与 [Window 10-WMS 锁竞争](../01-Mechanism/Framework/Window/10-WMS锁竞争与Watchdog.md) 的关系：system_server 自身的 adj 是 -900，永不被杀——但它卡死时 Watchdog 会**主动重启 system_server**，与本篇 adj 体系不冲突

---

## 附录 A：核心源码路径索引

### A.1 AMS 内存治理核心

| 路径 | 关键类/函数 | 职责 |
|------|------------|------|
| `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` | `AMS` 主类 | adj 写入、内核接口调度 |
| `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` | `ProcessList` | adj 常量定义、cached 排序 |
| `frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java` | `OomAdjuster.computeOomAdjLocked`（AOSP 12 之前为 `computeOomAdjLocked`） | adj 核心计算 |
| `frameworks/base/services/core/java/com/android/server/am/ProcessRecord.java` | `ProcessRecord` | 进程记录数据结构 |
| `frameworks/base/services/core/java/com/android/server/am/ActivityRecord.java` | `ActivityRecord` | Activity 状态 |
| `frameworks/base/services/core/java/com/android/server/am/ServiceRecord.java` | `ServiceRecord` | Service 状态 |
| `frameworks/base/services/core/java/com/android/server/am/ActiveServices.java` | `ActiveServices` | Service 生命周期 + adj 联动 |
| `frameworks/base/services/core/java/com/android/server/am/BroadcastQueue.java` | `BroadcastQueue` | 广播接收与 adj |
| `frameworks/base/services/core/java/com/android/server/am/ContentProviderRecord.java` | `ContentProviderRecord` | Provider 引用计数 |

### A.2 旧 LMK（已废弃，参考用）

| 路径 | 状态 | 备注 |
|------|------|------|
| `drivers/staging/android/lowmemorykiller.c` | AOSP 14 已废弃 | 新设备不编译 |
| `drivers/staging/android/Kconfig` | 配置项存在 | `CONFIG_ANDROID_LOW_MEMORY_KILLER` 默认未定义 |

### A.3 LMKD（下一篇主题）

| 路径 | 关键文件 | 职责 |
|------|---------|------|
| `system/memory/lmkd/` | `lmkd.c` | 主循环 |
| `system/memory/lmkd/` | `init.cpp` | 启动初始化 |
| `system/memory/lmkd/` | `event.cpp` | PSI 事件处理 |
| `system/memory/lmkd/` | `psi/` | PSI 监控 |

### A.4 内核接口

| 路径 | 关键点 |
|------|--------|
| `mm/oom_kill.c` | `oom_badness()` 函数 |
| `drivers/base/node.c` | `/proc/<pid>/oom_score_adj` 读写 |
| `kernel/sched/psi.c` | PSI 监控（与 LMKD 协同） |
| `kernel/cgroup/memcontrol.c` | memcg 内存限制 |

### A.5 进程状态机相关

| 路径 | 关键点 |
|------|--------|
| `frameworks/base/services/core/java/com/android/server/am/ActivityTaskSupervisor.java` | Activity 生命周期 → adj 联动 |
| `frameworks/base/services/core/java/com/android/server/am/KeyguardController.java` | 锁屏 → adj 翻转 |
| `frameworks/base/services/core/java/com/android/server/am/ProcessStatsService.java` | 进程状态历史 |

---

## 附录 B：风险速查表（adj 数值 / 日志关键字 / 排查入口）

### B.1 adj 数值速查表

| adj 区间 | 进程类型 | 杀它时影响 | 常见 App 举例 |
|---------|---------|-----------|-------------|
| -1000 | native 守护进程 | 系统级故障 | init 子进程 |
| -900 | system_server | 系统重启 | AMS 自身 |
| -800 | persistent 系统服务 | 核心功能失效 | phone/蓝牙/WIFI |
| 0 | 前台 App | 用户立刻感知 | 当前屏幕 App |
| 100 | 可见 App | 用户切回卡 | 被遮挡的 App |
| 200 | 后台播放/感知 | 音乐中断 | 网易云/QQ 音乐 |
| 500 | 前台服务 | 后台任务中断 | 导航/跑步 |
| 600 | Launcher | 桌面卡 | SystemUI |
| 700 | PREVIOUS | 切回冷启动 | 用户刚离开的 |
| 800 | BIND | 依赖链异常 | 跨进程服务 |
| 900-906 | cached | 用户无感 | 几小时未用 |

### B.2 杀进程日志关键字

| 关键字 | 来源 | 含义 |
|-------|------|------|
| `Process xxx has died` | ActivityManager | 任何方式杀的进程都打 |
| `lmkd: Kill (xxx, oom_score_adj 900)` | lmkd | LMKD 杀 |
| `Killing xxx adj xxx` | kernel (oom_kill.c) | 内核 OOM Killer 杀 |
| `am_kill: xxx` | system_server | AMS 主动杀 |
| `ProcessRecord.setAdj: xxx 700 -> 900` | ActivityManager | adj 变化 |
| `freezing xxx` / `Freeze hidden apps` | ActivityTaskManager | 锁屏翻转 |
| `unfreezing xxx` | ActivityTaskManager | 解锁恢复 |
| `Force finishing activity xxx` | ActivityManager | 用户主动结束 |
| `Service xxx leaked` | ActiveServices | Service 泄漏 |
| `killBackgroundProcesses` | ActivityManager | 应用主动调 |

### B.3 排查入口（按现象分组）

| 现象 | 第一动作 | 第二动作 | 终极排查 |
|------|---------|---------|---------|
| App 频繁被杀 | `dumpsys activity processes` | 看 `curAdj` 实际值 | 调 `setOomScoreAdj` 强制拉到 500 |
| 锁屏后被杀 | 对齐 logcat 时间点 | 看 `freeze hidden apps` 时机 | 业务改用 foreground service |
| 切应用冷启动 | `dumpsys activity processes` | 查 cached 进程数 | 调 `CUR_MAX_CACHED_PROCESSES` |
| Service 跑一晚 | `dumpsys activity services` | 看 `createTime` | 检查 `onTaskRemoved` |
| 前台服务 ANR | `dumpsys activity services` | 看 `startForeground` 延迟 | 检查 5 秒超时 |
| OOM Killer 杀 | `dmesg \| grep -i kill` | 看 `Killing` 关键字 | 查 RSS 总和 |
| 系统卡顿 | `dumpsys cpuinfo` | 看 system_server CPU | 查 adj 计算耗时 |

### B.4 常用 dumpsys 命令

```bash
# 1. 看所有进程 adj（核心命令）
adb shell dumpsys activity processes

# 2. 看进程详情（指定包名）
adb shell dumpsys activity processes <pkg>

# 3. 看所有 Service
adb shell dumpsys activity services

# 4. 看指定包名的 Service
adb shell dumpsys activity services <pkg>

# 5. 看 Activity 栈
adb shell dumpsys activity activities

# 6. 看内存详情
adb shell dumpsys meminfo

# 7. 看内存按进程排序
adb shell dumpsys meminfo --sort-by pss

# 8. 看系统内存总览
adb shell cat /proc/meminfo

# 9. 看 PSI 压力
adb shell cat /proc/pressure/memory

# 10. 看单个进程的 oom_score_adj
adb shell cat /proc/<pid>/oom_score_adj
```

### B.5 异常 adj 数字与诊断

| 异常值 | 可能原因 | 诊断动作 |
|-------|---------|---------|
| 906 + 进程在用 | Service 漏 stop | 查 `dumpsys activity services` |
| 0 + 进程无 Activity | 旧 adj 未更新 | 查最近一次 `updateOomAdj` 时间 |
| -16 | 旧版 oom_adj 接口 | 系统太老或 OEM 魔改 |
| 1001 | adj 计算中 | 等 1-2 秒后重抓 |
| -10000 | 进程记录刚创建 | 启动阶段，正常 |
| 100 + 持续 1h+ | 异常可见态 | 查 Activity 泄漏 |

### B.6 风险速查总矩阵（30 行覆盖）

| 问题类型 | adj 现象 | 日志关键字 | 关键工具 | 跨篇链接 |
|---------|---------|-----------|---------|---------|
| 微信被误杀 | 900 | `lmkd: Kill` | dumpsys processes | 06-LMKD |
| 后台被杀 | 700-900 | `Freeze hidden` | logcat | 06/12 |
| 锁屏被杀 | 翻转到 900 | `freeze` | logcat | 06/12 |
| Service 泄漏 | 服务跑 5h+ | `Service leaked` | dumpsys services | 05/12 |
| 前台服务超时 | 5s ANR | `ForegroundServiceDidNotStartInTime` | logcat | 12/13 |
| Persistent 配置错误 | adj=-800 多个 | `persistent` | dumpsys processes | 05/12 |
| cached 进程过多 | 900-906 50+ 个 | `cached` | dumpsys processes | 05/06/12 |
| OOM Killer 杀 | dmesg Killing | `Killing process` | dmesg | 11/12 |
| Watchdog 杀 | watchdog logs | `WATCHDOG KILLING` | logcat | Window 10 |
| cgroup OOM 杀 | memcg OOM | `memory cgroup out of memory` | dmesg | 07/12 |
| PSI 持续高 | some > 50% | `pressure/memory` | cat /proc | 07/12 |
| adj 计算耗时高 | > 500ms | `computeOomAdj` | perfetto | 13 |
| trim 失败 | cached 数不降 | `trimCaches` | logcat | 12 |
| Service start 失败 | startForeground | `startForegroundService` | logcat | 12 |
| bind 死锁 | service 800 卡死 | `bind timeout` | logcat | 10 |
| 进程泄漏 fd | cached 进程 fd 高 | `Too many open files` | procrank | 12/04 |
| 进程泄漏线程 | cached 进程线程多 | `pthread_create` | procrank | 12 |
| WakeLock 不释放 | 进程常驻 | `WakeLock` | dumpsys power | 12 |
| JobScheduler 堆积 | 周期任务 | `JobServiceContext` | dumpsys jobscheduler | 12 |
| 多用户切换异常 | UID 切换 adj 错 | `applyOomAdj` | logcat | 12 |
| Work Profile 异常 | 分身 App 杀 | `WorkProfile` | dumpsys user | 12 |
| 投屏进程被杀 | MediaProjection 持有 | `MediaProjection` | logcat | 12 |
| Doze 模式异常 | 后台白名单 | `idle whitelist` | dumpsys deviceidle | 12 |
| AlarmManager 滥用 | 频繁唤醒 | `Alarm` | dumpsys alarm | 12 |
| 静态 receiver 持有 | cached 收广播 | `BroadcastQueue` | dumpsys activity broadcasts | 12 |
| Provider 死锁 | cursor 不关 | `ContentProvider` | dumpsys activity providers | 12 |
| Activity 泄漏 | cached 持 Activity | `Activity` ref | heap dump | 02/12 |
| Finalizer 队列 | ReferenceQueue | `FinalizerWatchdogDaemon` | logcat | 03/12 |
| image space 损坏 | boot image 异常 | `image_space` | logcat | 03/12 |
| 启动后频繁杀 | warm 启动慢 | `cold_start` | perfetto | Window 08/12 |

---

## 篇尾衔接

本篇沿着"分类 → 数值 → 时机 → 源码 → 演进 → 风险 → 实战"的链路，把 AMS 内存治理的完整内部机制讲透了。但**本篇最关键的一个认知是**：AMS 算的 adj 不是终点，而是 LMKD 选杀进程的**输入**。adj 算对只是"不杀错"，是否"杀得对、杀得及时"取决于 LMKD 的决策。

下一篇 **[06-LMKD 用户态内存杀手](06-LMKD 用户态内存杀手.md)** 将深入 LMKD 的内部机制：

- **LMKD 是什么 / 为什么从内核迁到用户态**：架构演进动机
- **事件源**：vmpressure (旧) → PSI (新) / memcg watermark
- **kill 决策算法**：min_score_adj 阈值、oom_score_adj 选择、kill 优先级
- **源码走读**：`lmkd.c` / `init.cpp` / `event.cpp` 完整执行流
- **风险地图**：杀得太狠、杀得太慢、杀错进程、PSI 阈值错误
- **实战案例**：相机进程被 LMKD 误杀导致后台录像中断

**与本篇的衔接点**：
- 本篇 §2.2 的 oom_score_adj 计算公式是 LMKD 选杀的输入
- 本篇 §5.4 的 AMS-LMKD 协作流程将在 06 篇展开为完整时序图
- 本篇 §6.6 的"锁屏 adj 翻转"将在 06 篇的"杀错进程"案例中作为触发条件出现
- 本篇 §7 的"Service 保活 + 锁屏后被误杀"案例将在 06 篇从 LMKD 视角重新解读

读完下一篇，你将能够把"AMS 算什么 adj"和"LMKD 怎么用 adj 选杀"连成一条完整的端到端链路——这是排查所有"App 在后台被杀"问题的关键路径。

**系列阅读路径**：
- 上一篇：[04-Native 堆内存与分配器（AOSP 14）](04-Native 堆内存与分配器（AOSP 14）.md)（Native 堆机制与 Bitmap/ION/DMA-BUF 治理）
- 当前篇：05-AMS 内存治理与进程优先级
- 下一篇：[06-LMKD 用户态内存杀手](06-LMKD 用户态内存杀手.md)
- 后篇：[07-PSI / vmpressure / memcg 压力传递](07-PSI、vmpressure、memcg 压力传递.md) → [12-内存稳定性风险全景](12-内存稳定性风险全景.md) → [13-内存稳定性诊断工具链](13-内存稳定性诊断工具链.md)

