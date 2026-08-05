# 第 10 章　应用启动与首帧

> **所属卷**：卷 2　系统启动
> **章定位**：从 Launcher 点击到第一帧显示——**App 启动机制链路**
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Qualcomm SM8550 + Pixel 7/8
> **章强依赖**：[8.1 Zygote 启动](../08-Zygote%20与%20ART%20启动/8.1-Zygote启动-fork与预加载.md) / [8.4 类加载优化](../08-Zygote%20与%20ART%20启动/8.4-启动类加载优化-deferred-class-load.md) / [9.1 SystemServer 启动入口](../09-SystemServer%20启动/9.1-SystemServer启动入口-SystemServer.java.md) / [9.3 4 大服务详解](../09-SystemServer%20启动/9.3-核心服务详解-PMS-AMS-WMS-IMS.md)
> **章衔接去**：[第 11 章 系统启动性能专项](../11-系统启动性能专项/index.md)（开机时间）/ [卷 6 第 38 章 应用启动优化](../../05-卷5-性能工程与治理/index.md)（优化实践）
> **章边界**：本章**不写** Bootloader / Init / Zygote / SystemServer 整机启动（见第 6–9 章）；**只写** Launcher 点击 → ActivityThread → 第一帧的**应用侧**链路

## 核心子节

- **10.0** [系统启动到桌面:Launcher 启动 + fallback home + boot_completed 链路](10.0-系统启动到桌面-Launcher启动-fallback-home-boot-completed链路.md) — 全局观前奏(章首节 0),补齐卷 2 "上电到桌面" 14 个关键节点中的 4 个 gap(AMS 选 Launcher / Launcher fork / fallback home / BOOT_COMPLETED 链路 + 第三方 SDK 自启)
- **10.1** [Launcher 点击 → ActivityThread：Binder 跨进程调用](10.1-Launcher点击-ActivityThread-Binder跨进程调用.md) — 章首节，全局观 + 核心机制，把 App 启动链路的"主线 7 步"画清楚
- **10.2** [进程创建：Zygote fork 的应用侧参数](10.2-进程创建-Zygote-fork的应用侧参数.md) — 核心机制，Zygote fork 应用时的特殊参数（uid / gid / 进程名 / seinfo / namespace）
- **10.3** [Application 初始化：attachBaseContext / onCreate / ContentProvider](10.3-Application初始化-attachBaseContext-onCreate-ContentProvider.md) — 核心机制，Application 生命周期的 3 个钩子
- **10.4** [视图树构建：measure / layout / draw](10.4-视图树构建-measure-layout-draw.md) — 核心机制，View 树从 measure 到第一帧绘制的 3 步走
- **10.5** [Choreographer 调度：VSYNC 与 input / animation / traversal 回调](10.5-Choreographer调度-VSYNC与input-animation-traversal回调.md) — 核心机制，Choreographer 4 大回调
- **10.6** [首帧定义：First Frame / First Image / Cold / Warm / Hot Start](10.6-首帧定义-First-Frame-First-Image-Cold-Warm-Hot-Start.md) — 核心机制 + 概念辨析，5 种"启动"与 4 种"首帧"的精确定义
- **10.7** [启动时间测量：am start -W / logcat / Perfetto](10.7-启动时间测量-am-start-W-logcat-Perfetto.md) — 诊断治理，3 类测量工具 + 30 秒定位慢在哪一段

## 章架构总览

```
[第 8 章 已讲] Zygote fork 出口 ── ZygoteInit.forkAndSpecialize
                 ↓
[第 9 章 已讲] system_server 启动完成,AMS.systemReady() 触发
                 ↓
[本章 10.1 起点] Launcher 点击 App 图标
                 ↓
[10.1] Launcher → AMS.startActivity (Binder IPC)
                 ↓
[10.2] AMS 检查进程是否在,不在则请求 Zygote fork
       Zygote.forkAndSpecialize (uid / gid / nice-name / seinfo / namespace)
                 ↓
[10.3] fork 后子进程入口 = ActivityThread.main()
       → Application.attachBaseContext
       → Application.onCreate
       → ContentProvider 初始化
                 ↓
[10.4] Activity onCreate → setContentView
       → View 树构建 (measure / layout / draw)
                 ↓
[10.5] Activity onResume → Choreographer.postFrameCallback
       → VSYNC 信号 → doFrame()
       → 4 大回调 (input / animation / traversal / commit)
                 ↓
[10.6] 第一帧上屏 → DisplayEventReceiver
       → 整机 boot_completed / first_frame_drawn
                 ↓
[10.7] am start -W / logcat / Perfetto 测量时间
       → 应用启动总耗时 = T_end - T_start
```

## 章级别"风险地图"

| 风险 | 关联节 | 案例引用 |
|---|---|---|
| App 冷启动慢 (> 1.5s) | 10.1 / 10.2 / 10.3 | 10.3 案例 1 |
| 进程创建慢 (fork 慢) | 10.2 | 10.2 案例 1 |
| Application.onCreate 阻塞 | 10.3 | 10.3 案例 2 |
| ContentProvider 初始化阻塞 | 10.3 | 10.3 案例 3 |
| 视图树构建慢 (measure/layout/draw) | 10.4 | 10.4 案例 1 |
| Choreographer 跳帧 (jank) | 10.5 | 10.5 案例 1 |
| 第一帧定义错 (测的不是用户感知) | 10.6 | 10.6 案例 1 |
| 启动时间测量误差 (Perfetto vs am start) | 10.7 | 10.7 案例 1 |
| 热启动被误判为冷启动 | 10.6 | 10.6 案例 2 |
| 第三方 SDK 启动期 ANR | 10.3 | 10.3 案例 4 |

## 章级别"图表密度规划"

| 节 | 架构图 / 时序图 / 流程图 | 张数 |
|:--|:--|:--:|
| 10.1 | App 启动链路时序 / AMS.startActivity 流程 / Binder IPC 跨进程 / ActivityThread.main 入口 | 5 |
| 10.2 | Zygote fork 应用时序 / fork 参数 / ActivityThread 初始化 | 3 |
| 10.3 | Application 生命周期时序 / ContentProvider 初始化顺序 | 3 |
| 10.4 | View 树 measure/layout/draw 时序 / 关键方法 | 3 |
| 10.5 | Choreographer 4 大回调时序 / VSYNC 信号流 | 3 |
| 10.6 | 5 种启动 vs 4 种首帧矩阵 / 状态机 | 2 |
| 10.7 | am start -W 输出 / Perfetto trace 关键事件 / 30 秒定位 SOP | 3 |
| **合计** | | **22** |

## 章级别"不重复内容"声明

- **10.1** 不重述 Zygote fork 机制(8.1 §2.6 已讲);本节只讲应用侧
- **10.2** 不重述 Zygote preload(8.1 §2.4 已讲);本节只讲 fork 时的应用侧参数
- **10.3** 不重述 AMS / PMS / WMS 内部启动(9.3 已讲);本节只讲 ActivityThread 侧
- **10.4** 不重述 WMS 内部(9.3 §2.3 已讲);本节只讲 View 树应用侧
- **10.5** 不重述 Choreographer native 实现(卷 3 第 20 章已规划);本节只讲应用侧 4 大回调
- **10.6** 不重述 DisplayEventReceiver(8.x 已有);本节只讲概念辨析
- **10.7** 不重述 Perfetto 工具链(11 章 D01 已讲);本节只讲 3 类测量工具的应用
- **全章** 不重述 ART 完整运行期机制(卷 3 第 20 章 ART 完整机制)
- **全章** 不重述 Binder 协议(卷 3 第 12 章 Binder IPC 深度)

## 跨系列引用矩阵

| 本节 | 引用 | 引用原因 |
|:--|:--|:--|
| 10.1 | 8.1 §2.6 / 9.3 §2.2 | Zygote fork / AMS 启动 |
| 10.2 | 8.1 §2.6 | Zygote.forkAndSpecialize |
| 10.3 | 9.3 §2.2 / 9.3 §2.6 | AMS 全功能 / PMS 第一次扫描 |
| 10.4 | 9.3 §2.3 | WMS 启动 |
| 10.5 | 9.3 §2.4 | IMS 启动 |
| 10.6 | 9.1 §2.6 | first_frame_drawn 时间点 |
| 10.7 | 11 章 D01 / D02 | Perfetto / bootstat 工具链 |
| 全章 | 卷 6 第 38 章 | 应用启动优化实践(跨卷引用) |

## 写作节奏（每节字数 / 实际）

| 节 | 目标字数 | 实际中文字 | 实际总字符 | 状态 |
|:--|---:|---:|---:|:--|
| 10.0 | 4500-5500 | 4500+ | ~35000 | ✅ 达到章首节下限 4000 |
| 10.1 | 4500-5500 | 4500+ | ~25000 | ✅ 达到章首节下限 4000 |
| 10.2 | 3000-4000 | 2700+ | ~15000 | ✅ 达到章内后续节下限 2500 |
| 10.3 | 3500-4500 | 3200+ | ~18000 | ✅ 达到章内后续节下限 2500 |
| 10.4 | 3000-4000 | 2700+ | ~15000 | ✅ 达到章内后续节下限 2500 |
| 10.5 | 3500-4500 | 3200+ | ~18000 | ✅ 达到章内后续节下限 2500 |
| 10.6 | 3000-4000 | 2700+ | ~15000 | ✅ 达到章内后续节下限 2500 |
| 10.7 | 3500-4500 | 3200+ | ~18000 | ✅ 达到章内后续节下限 2500 |
| **合计** | **28500-34500** | **26700+ 中文字** | **~159000 字符（含表格/代码/图）** | **复合等效约 30000 字** |

---

## 本章小结

App 启动链路是从 systemReady 到桌面 + 桌面到首帧的完整流程——AMS 选 Launcher → Launcher fork → fallback home 触发与退场 → Launcher 第一帧 → boot_completed → 第三方 SDK 自启 → 用户点击 App → App 启动链路 7 步。**任何一个步骤慢都会让整机 boot 退化 100ms-10s**。本章 8 节(10.0 全局观前奏 + 10.1-10.7 应用侧)把这条链路拆成 1 块链路补齐(10.0)+ 5 块核心机制(ActivityThread / Zygote fork 参数 / Application 生命周期 / View 树 / Choreographer)+ 2 块概念与诊断(首帧定义 / 时间测量),让读者既能从源码走读理解机制,也能在 App 启动慢时 30 秒内定位到具体步骤。

**清理**:
- 2026-08-04 删除 `A05-AMS-PMS-WMS四大组件启动.md` / `A06-第一帧与Choreographer.md`(A0x 系列长文体,不符合 v6 书章体)
- 2026-08-04 迁出 A01–A04(整机启动链)到 `_archive/vol2-A-module-superseded-by-ch6-9/`(与第 6–9 章职责重叠)
- 2026-08-04 启动新书章 10.1–10.7 v6 规范重写
- 2026-08-04 补 10.0 全局观前奏(AMS 选 Launcher / Launcher fork / fallback home 触发与退场 / boot_completed 完整链路 / 第三方 SDK 自启)
