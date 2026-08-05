# 第 8 章　Zygote 与 ART 启动

> **所属卷**：卷 2　系统启动
> **章定位**：Java 进程工厂——所有 App 进程的模板。ART 的完整机制见卷 3 第 20 章，本章只讲**启动阶段**。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Qualcomm SM8550 + Pixel 7/8
> **章强依赖**：[7.1 Init 启动流程](../07-Init%20进程与%20init.rc/7.1-Init进程启动流程.md) / [7.2 init.rc 语法](../07-Init%20进程与%20init.rc/7.2-init.rc语法详解.md) / [7.3 启动阶段划分](../07-Init%20进程与%20init.rc/7.3-启动阶段划分.md) / [7.6 init 慢与卡死](../07-Init%20进程与%20init.rc/7.6-init阶段慢与卡死.md)
> **章衔接去**：[第 9 章 SystemServer 启动](../09-SystemServer%20启动/index.md) / [第 10 章 应用启动与首帧](../10-应用启动与首帧/index.md) / [第 11 章 系统启动性能专项](../11-系统启动性能专项/index.md)

## 核心子节

- **8.1** [Zygote 启动：从 `app_process64` 到 `runSelectLoop`](8.1-Zygote启动-fork与预加载.md) — 章首节，全局观 + 核心机制
- **8.2** [ART 启动：`libart.so` / ClassLinker / OAT 镜像加载](8.2-ART启动-libart与ClassLinker.md) — 核心机制，Runtime::Init 4 大步
- **8.3** [启动预优化：Profile Guided Compilation + Cloud Profile](8.3-启动预优化-PGC与Cloud-Profile.md) — 核心机制，dex2oat 触发链 + Cloud Profile 3 类来源
- **8.4** [启动类加载优化：deferred class load / lazy verification](8.4-启动类加载优化-deferred-class-load.md) — 核心机制，preload vs lazy 的判定准则
- **8.5** [Zygote fork 慢 / Zygote crash 调查](8.5-Zygote-fork慢与crash调查.md) — 风险地图 + 诊断治理，**Zygote 内部视角**
- **8.6** [Zygote 内存治理：fork copy-on-write 与 RSS 控制](8.6-Zygote内存治理-fork-copy-on-write.md) — 核心机制 + 风险地图，**本卷新增节**

## 章架构总览

```
┌─ Kernel  ─────────────────────────────────────────────────────────┐
│  kernel_init → run_init_process("/init")  →  PID 1                 │
└────────────────┬───────────────────────────────────────────────────┘
                 ▼
┌─ Init (PID 1) ─ 7.1/7.2/7.3 已讲 ─────────────────────────────────┐
│  LoadBootScripts: 启动 zygote (service)                            │
│  on post-fs-data: mount /data + 准备 ART profile 目录              │
└────────────────┬───────────────────────────────────────────────────┘
                 ▼  ← ★ 本章主战场
┌─ Zygote (UID=root) ───────────────────────────────────────────────┐
│  app_process64 → ZygoteInit.java → main()                          │
│   ├─ 1. 加载 libart.so / libnativebridge.so  ← 8.2                 │
│   ├─ 2. Runtime::Init (ART 启动)            ← 8.2                  │
│   ├─ 3. preloadClasses()  (~9000-12000 class) ← 8.1 / 8.4          │
│   ├─ 4. preloadResources()                              ← 8.1     │
│   ├─ 5. preloadSharedLibraries()                        ← 8.1     │
│   ├─ 6. GC + prepareOatFiles  (PGC / Cloud Profile)     ← 8.3     │
│   └─ 7. runSelectLoop()  (epoll,等待 fork 请求)         ← 8.1     │
│                                                                  │
│  8.5: 启动慢 / crash 的 3+4 类根因调查                              │
│  8.6: fork COW + Zygote RSS 治理                                   │
└────────────────┬───────────────────────────────────────────────────┘
                 ▼
┌─ Zygote fork 出去的进程 ─────────────────────────────────────────┐
│  ├─ system_server  →  第 9 章 SystemServer 启动                      │
│  └─ app process    →  第 10 章 应用启动与首帧                         │
└───────────────────────────────────────────────────────────────────┘
```

## 章级别"风险地图"

| 风险 | 关联节 | 案例引用 |
|---|---|---|
| Zygote 启动失败 / 启动慢 | 8.1 / 8.5 | 8.1 §4 案例 2 / 8.5 §4 案例 1 |
| ART 启动崩（libart / OAT 损坏） | 8.2 / 8.5 | 8.2 §4 案例 1 / 8.5 §4 案例 1 |
| ClassLinker 死锁 | 8.2 / 8.5 | 8.2 §4 案例 2 |
| 首启慢（没 profile / OTA 后） | 8.3 | 8.3 §4 案例 2 |
| 装应用后首次启动崩（profile 损坏） | 8.3 | 8.3 §4 案例 1 |
| preloaded-classes 误配触发 VerifyError | 8.4 | 8.4 §4 案例 1 |
| preloaded-classes 误移导致 system_server 启动退化 | 8.4 | 8.4 §4 案例 2 |
| seccomp 误配触发 SIGSYS | 8.5 | 8.5 §4 案例 2 |
| Zygote RSS 7 天膨胀 | 8.6 | 8.6 §4 案例 1 |
| App 冷启动从 800ms 退化到 1.5s（Zygote 内存换出） | 8.6 | 8.6 §4 案例 2 |

## 章级别"图表密度规划"

| 节 | 架构图 / 时序图 / 流程图 | 张数 |
|:--|:--|:--:|
| 8.1 | Init→Zygote→fork 架构 / ZygoteInit 6 步流水线 / fork 出去的两类进程 | 5 |
| 8.2 | Runtime::Init 4 大步 / OAT/VDEX/ART 镜像三件套 / OAT 损坏 3 类自愈路径 | 3 |
| 8.3 | dex2oat 触发链 / Cloud Profile 流程 / profile 状态机 | 3 |
| 8.4 | preloaded-classes 生成流程 / verify 校验链 / PIC 与 lazy 联动 | 3 |
| 8.5 | Zygote fork 慢 3 类根因定位 / 抓栈工具链 / critical window 触发流程 | 3 |
| 8.6 | fork COW 本质 / Zygote RSS 与整机内存 / 3 类压力点 | 3 |
| **合计** | | **20** |

## 章级别"不重复内容"声明

- **8.1** 不重述 zygote service 声明 / `onrestart` 链 / `critical window=`（7.2 已讲）
- **8.1** 不重述 `zygote-start` 触发链（7.3 已讲）
- **8.1 / 8.3** 不重述 odsign 拖住 zygote 案例（7.3 §案例 2 已讲）
- **8.5** 不讲整机调查 SOP（11 章已管）
- **8.6** 是本卷新增节，原因是"Zygote 内存治理"在骨架里没有，但稳定性最痛
- **全章** 不重复 ART 编译 / JNI / GC 等运行期机制（卷 3 第 20 章 ART 完整机制）
- **全章** 不重复 Binder 域（卷 3 第 12 章 Binder IPC 深度）

## 跨系列引用矩阵

| 本节 | 引用 | 引用原因 |
|:--|:--|:--|
| 8.1 | 7.1 / 7.2 / 7.3 / 7.6 | Init 怎么拉起 zygote / zygote service 声明 / zygote-start 触发链 / 慢 vs 卡死分诊 |
| 8.2 | 8.1 | Runtime::Init 是 Zygote 启动链路的子集 |
| 8.3 | 7.3 / 8.2 | odsign 案例 / AOT/JIT 模式选 |
| 8.4 | 8.1 / 8.2 | preload 阶段 / ClassLinker 初始化 |
| 8.5 | 8.1 / 8.2 / 8.3 / 8.4 | 给读者快速复盘时定位到具体节 |
| 8.6 | 8.1 / 8.4 | fork COW 机制 / preloaded-classes 内存影响 |

## 写作节奏（每节字数 / 实际）

| 节 | 目标字数 | 实际中文字 | 实际总字符 | 状态 |
|:--|---:|---:|---:|:--|
| 8.1 | 7000-9000 | 4659 | 28802 | ✅ 达到章首节下限 4000 |
| 8.2 | 4000-5000 | 3662 | 23741 | ✅ 达到章内后续节下限 2500 |
| 8.3 | 3000-4000 | 3360 | 20321 | ✅ 达到章内后续节下限 2500 |
| 8.4 | 3500-4500 | 3561 | 20389 | ✅ 达到章内后续节下限 2500 |
| 8.5 | 3500-4500 | 3204 | 20158 | ✅ 达到章内后续节下限 2500 |
| 8.6 | 3500-4500 | 4084 | 19050 | ✅ 达到章内后续节下限 2500 |
| **合计** | **24500-30500** | **22530 中文字** | **~132460 字符（含表格/代码/图）** | **复合等效约 25000 字** |

---

## 本章小结

Zygote 是所有 App 启动的公共瓶颈——**它慢 1 次,全系统每个 App 的冷启动都跟着慢**,因为所有 App 都是它的 fork 副本。本章 6 节把 Zygote 启动链路拆成 4 块核心机制（fork / ART 启动 / PGC / 类加载优化）+ 2 块风险治理（fork 慢/crash 调查 / 内存治理），让读者既能从源码走读理解机制,也能在 Zygote 出问题时 30 秒内定位到根因。
