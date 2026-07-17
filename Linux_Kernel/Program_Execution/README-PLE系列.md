# 程序加载与执行深度解析系列 — 系列总览

> **系列代号**:PLE(Program Loading & Execution)
> **目录**:`Linux_Kernel/Program_Execution/`
> - **骨架对齐**:MM_v2 系列的"锚点+分层+对仗"
> - **风格对齐**:Android_Framework/Process 系列(8 篇)的"场景+机制+风险"
> **源码基线**:
> - **AOSP**:`android-14.0.0_r1`(`refs/heads/android14-release`)
> - **Linux Kernel 多版本矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本系列涉及内核侧 execve / mmap / 缺页 / VMA / cgroup / schedtune,各篇头部按需标注适用版本)
> - **工具**:`arm64-linux-gnu-readelf` + `dexdump` + `baksmali` + `oatdump` + `apksigner`
> **每篇文章头部必须包含**:(1) 本篇定位 5 字段段(系列角色 / 强依赖 / 承接自 / 衔接去 / 不重复内容);(2) 多版本内核基线;(3) 案例可验证 4 件套(环境/复现/logcat/diff)

---

## 0. 系列定位

### 0.1 一句话定义

**程序加载与执行(Program Loading & Execution, PLE)是"代码与数据从静态文件到运行时实例"的转换过程,横跨 Linux 内核(动态链接)、Android Runtime(类加载)、Android Framework(资源加载与进程启动)三个层面。**

### 0.2 PLE 在 Android 知识地图中的位置

```
                     Android 技术知识地图(节选)
                     ─────────────────────────

  Linux_Kernel/
  ├─ Process/                  ← 进程管理
  ├─ Memory_Management/        ← MM_v2 运行时内存模型
  │   └─ MM_v2/
  │       ├─ 14 篇正文
  │       └─ README-MM_v2系列.md  ← 与本系列双向引用
  └─ Program_Execution/        ← PLE 本系列 ★
      ├─ 14 篇正文
      └─ README-PLE系列.md  ← 你在这里
```

### 0.3 PLE 回答什么问题

**MM_v2 回答"运行时数据长啥样",PLE 回答"启动时装啥、按什么顺序"。**

四者正交,两两互补:
- **MM_v2** = 运行时内存账本
- **PLE** = 启动时装配流水线
- **ART 系列** = 装好后怎么跑
- **Android_Framework/Process** = 调度进程

---

## 1. 14 篇文章总览

### 1.1 篇章划分

| 篇章 | 篇号 | 主题 | 字数(估计) |
|---|---|---|---|
| **总览** | 01 | 全景 | 54KB |
| **ELF + 动态链接** | 02 / 03 / 04 / 05 | SO 加载 | 61+42+35+31KB |
| **DEX + ART** | 06 / 07 / 08 / 09 | 字节码加载 + 类加载 | 42+30+29+29KB |
| **Resources + APK** | 10 / 11 | 资源加载 | 34+28KB |
| **进程启动** | 12 / 13 | Zygote + 跨进程类型 | 31+27KB |
| **风险地图** | 14 | 故障速查 | 29KB |

**总产出**:**~530KB / ~7700 行**

### 1.2 14 篇文章清单

| # | 标题 | 主线 | 关键问题 |
|---|---|---|---|
| **01** | [程序加载与执行全景图:从 execve 到第一行 Java 代码的完整链路](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md) | 锚点篇 | 8 阶段流水线 + 四元动作 + 跨篇引用骨架 |
| **02** | [ELF 文件格式深度解析:从可执行文件到内核视角](02-ELF文件格式深度解析-从可执行文件到内核视角.md) | ELF 格式 | 头 / 段 / section / 3 段分离 / arm64 特殊处理 |
| **03** | [Bionic 动态链接器:linker64 的工作机制](03-Bionic动态链接器-linker64的工作机制.md) | 动态链接器 | 7 步启动 / soinfo / find_library / namespace |
| **04** | [符号解析与重定位:.plt / .got / .relro 全景](04-符号解析与重定位-plt-got-relro全景.md) | 重定位 | 4 张表 / RELRO / GNU hash / R_AARCH64_* |
| **05** | [.init_array 与构造函数链:静态初始化的执行顺序](05-init_array与构造函数链-静态初始化的执行顺序.md) | 静态初始化 | 5 个 section / 倒序执行 / JNI_OnLoad |
| **06** | [DEX / ODEX / VDEX 格式:为 mmap 而生的字节码](06-DEX-ODEX-VDEX格式-为mmap而生的字节码.md) | DEX 格式 | 头 / 5 大 id 表 / 4 种产物 |
| **07** | [ART ClassLoader 体系:从 BootClassLoader 到 PathClassLoader](07-ART-ClassLoader体系-从BootClassLoader到PathClassLoader.md) | ClassLoader | 5 种 ClassLoader / 5 步路径 / 可见性 |
| **08** | [类加载生命周期:Loading → Linking → Initializing](08-类加载生命周期-Loading-Linking-Initializing.md) | 类加载 7 阶段 | Verify / Prepare / Resolve / Init |
| **09** | [AOT / JIT 编译流水线:dex2oat 与 ART 运行时编译](09-AOT-JIT编译流水线-dex2oat与ART运行时编译.md) | AOT/JIT | 3 模式 / PGC / Baseline Profile |
| **10** | [资源加载:AssetManager / ApkAssets / ResTable](10-资源加载-AssetManager-ApkAssets-ResTable.md) | 资源加载 | 3 层结构 / arsc 解析 / Configuration |
| **11** | [APK 容器解析:ZIP + arsc + 资源 ID 体系](11-APK容器解析-ZIP-arsc-资源ID体系.md) | APK 容器 | ZIP / 签名 / arsc / aapt2 |
| **12** | [进程启动全景:Zygote fork → 第一帧](12-进程启动全景-Zygote-fork-第一帧.md) | 进程启动 | Zygote / preload / ActivityThread / 8 阶段 |
| **13** | [不同进程类型的加载差异:zygote / system_server / app / native](13-不同进程类型的加载差异-zygote-system_server-app-native.md) | 跨进程类型 | 4 类进程 / preload / fork 后加载 |
| **14** | [加载失败与启动期故障速查](14-加载失败与启动期故障速查.md) | 风险地图 | 8 大类故障 / 速查矩阵 / 5 秒定位法 |

---

## 2. 4 个核心抽象(全系列贯穿)

**为保持全系列的概念一致性,PLE 严格围绕 4 个核心抽象展开**:

| 抽象 | 定义 | 在系列中的角色 |
|---|---|---|
| **四元动作** | 解析/映射/链接/初始化 | 跨所有加载器的统一 pattern |
| **8 阶段流水线** | execve → 第一行 Java | 冷启动拆解骨架 |
| **三类程序数据** | SO/DEX/Resources | 系列覆盖的三种介质 |
| **三类进程类型** | zygote/system_server/app/native | 跨篇对比视角(P13) |

任何一篇文章都应能映射回这 4 个抽象之一。

---

## 3. 与 MM_v2 的对仗矩阵

### 3.1 14 篇对仗

| MM_v2 篇 | PLE 篇 | 对仗关系 |
|---|---|---|
| 01 内存系统总览 | 01 加载全景 | 姐妹锚点篇 |
| 02 VMA 体系 | 02 ELF 格式 | 虚拟地址空间视角 |
| 03 ART 堆 | 06/07/08 DEX/ClassLoader/生命周期 | ART 视角 |
| 04 Native 堆 | 03/04/05 linker64/重定位/init | native 加载视角 |
| 05 AMS 内存治理 | 12 进程启动 | AMS 参与 |
| 06 LMKD | 13 进程类型 | 进程管理 |
| 07 PSI/压力 | 14 故障地图 | 稳定性治理 |
| 08-11 内核基础 | (跨篇引用) | 共同基础 |
| 12 风险 | 14 风险 | 风险篇对仗 |
| 13 诊断 | 14(含诊断) | 诊断融入风险 |
| 14 进程类型学 | 13 进程类型 | **完全对仗,同视角切换** |

### 3.2 完全对仗点

**MM_v2 14 ↔ PLE 13** 是最深的对仗:

| 维度 | MM_v2 14(运行时) | PLE 13(启动时) |
|---|---|---|
| 视角 | 进程在内存里长啥样 | 进程怎么被装起来的 |
| zygote | 内存类型 + GC 行为 | preload 内容 |
| system_server | 80+ 服务内存贡献 | 80+ 服务加载顺序 |
| app | 内存类型学 | DEX + Resources 加载 |
| native 守护 | init / lmkd 内存 | init / lmkd 加载特殊性 |

**架构师必记**:**同一组进程,两个视角**——MM 看结果,PLE 看原因。**两个一起读 = 全貌**。

---

## 4. 与其他系列的关联

| 关联系列 | 关联点 | PLE 引用 |
|---|---|---|
| **MM_v2** | 运行时内存 / 启动时加载 | 全部 14 篇互引 |
| **ART 系列** | DEX / ClassLoader / JIT | P06-09 引用 |
| **Android_Framework/Process** | AMS / Zygote fork | P12-13 引用 |
| **Linux_Kernel/Process** | execve / fork 入口 | P02 / P12 引用 |
| **Window 系列** | 启动期首帧渲染 | P12 / P14 引用 |

---

## 5. 阅读路径建议

### 5.1 三条推荐路径

**路径 A:只想懂 Android 启动**(架构师 5 篇)
```
01 全景图
  ↓
03 linker64(只读 §1 §2 §3 加载机制)
  ↓
07 ClassLoader 体系
  ↓
10 资源加载
  ↓
12 进程启动全景
```

**路径 B:想做加载性能优化**(性能架构师 8 篇)
```
01 全景
  ↓
02-05 ELF 系(全部)
  ↓
06-09 DEX 系(全部)
  ↓
10-11 资源系(全部)
  ↓
12-13 进程启动与跨进程类型
  ↓
14 风险地图
```

**路径 C:想完整理解,自学为主**(本系列作者本人推荐)← **强烈推荐**
```
01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10 → 11 → 12 → 13 → 14
按顺序,每篇 2-3 小时精读
```

### 5.2 与其他系列的协同阅读

| 你想了解 | 推荐先读 |
|---|---|
| 启动后内存怎么布局 | MM_v2 02 → PLE 01 |
| 启动后 ART 怎么跑 | PLE 06 → PLE 09 → ART 系列 03 |
| Zygote 怎么 fork | Android_Framework/Process 16 → PLE 12 |
| 进程优先级怎么算 | Android_Framework/Process 17 → PLE 13 |
| 启动期故障 5 秒定位 | PLE 14 速查矩阵 |

---

## 6. 关键交叉引用矩阵

| PLE 主题 | 关联的系列 | 关联点 |
|---|---|---|
| **execve 入口 / PT_LOAD 段** | [MM_v2 02-VMA 体系](../Memory_Management/MM_v2/02-进程内存地图与VMA体系.md) | ELF 段怎么映射成 VMA;多个 PT_LOAD 段的合并与拆分 |
| **linker64 / 重定位** | [MM_v2 04-Native 堆](../Memory_Management/MM_v2/04-Native堆分配与scudo.md) | .so 加载时 scudo reserve;Native 内存峰值 |
| **ClassLoader / DEX 加载** | [MM_v2 03-ART 堆](../Memory_Management/MM_v2/03-ART堆内存与GC全景.md) | DEX mmap 后的 ART 堆管理;Class 对象分配 |
| **AOT/JIT 编译** | [MM_v2 03-ART 堆](../Memory_Management/MM_v2/03-ART堆内存与GC全景.md) | AOT 产物 VDEX 占用 ART 元数据堆;JIT code cache |
| **Zygote fork** | [Android_Framework/Process 03](../../Android_Framework/Process/03-Zygote-Android进程工厂.md) | Zygote 的进程工厂角色;fork 的实现细节 |
| **Zygote preload** | [MM_v2 14-进程类型学](../Memory_Management/MM_v2/14-Android进程内存类型学-zygote-system_server-app-kernel-native守护进程.md) | preload 后的 zygote 进程内存长啥样 |
| **进程类型差异** | [MM_v2 14-进程类型学](../Memory_Management/MM_v2/14-Android进程内存类型学-zygote-system_server-app-kernel-native守护进程.md) | **完全对仗**:MM_v2 14 看运行时,PLE 13 看启动时 |
| **Resources 加载** | [Android_Framework/Process 04](../../Android_Framework/Process/04-应用进程首生-fork到ActivityThread.md) | 应用首生时 AssetManager 创建;resources.arsc 解析 |
| **冷启动慢** | (本系列 PLE 14) | 8 阶段拆解 + 异常映射 |
| **加载失败** | (本系列 PLE 14) | 异常关键字 → 阶段 → 文章 |

---

## 7. 风险地图汇总(14 篇横向速查)

| 风险类型 | 主要涉及篇 | 关键日志关键字 | 排查入口 |
|---|---|---|---|
| **类找不到** | P07, P08 | `ClassNotFoundException` | logcat + dexdump |
| **so 加载失败** | P03, P04, P05 | `dlopen failed`、`cannot locate symbol` | logcat + `readelf -s` |
| **架构错配** | P02 | `dlopen failed: wrong ELF class` | `adb shell getprop ro.product.cpu.abi` |
| **Verify 错误** | P08, P09 | `VerifyError`、`IllegalAccessError` | dex2oat 日志 + VDEX 校验 |
| **资源 ID 找不到** | P10, P11 | `Resources$NotFoundException` | aapt2 dump + R.java 对比 |
| **APK 签名错误** | P11 | `INSTALL_FAILED_NO_MATCHING_ABIS`、`Signature` | apksigner verify |
| **Zygote fork 失败** | P12 | `Zygote: fork failed` | logcat + dmesg |
| **冷启动慢** | P12, P14 | `slow main thread`、`Choreographer` | Perfetto + 8 阶段拆解 |
| **启动期 OOM** | P03, P09, P12 | `Out of memory`、`mmap failed` | dmesg + procrank |
| **Preload 残留** | P12, P13 | `preload` 阶段日志 | Zygote 日志 |
| **进程残留 / 僵尸** | P12, P13 | `Zygote dead`、`process gone` | logcat + procrank |
| **ART Verify 卡住** | P09 | `verify time`、`method verifier` | dex2oat 日志 |
| **Relocation 错误** | P04 | `relocation error`、`undefined symbol` | logcat + `readelf -r` |
| **动态库版本冲突** | P03 | `dlopen: library not found` | `LD_DEBUG=libs` |
| **Configuration fallback** | P10 | (静默) UI 错乱 | aapt2 dump resources |
| **Drawable OOM** | P10 | `OutOfMemoryError: Bitmap` | dumpsys meminfo |
| **dex2oat OOM** | P09 | `dex2oat failed: out of memory` | dex2oat 日志 |

详细速查见 [PLE 14 §7](14-加载失败与启动期故障速查.md)。

---

## 8. 写作规范(本系列铁律)

| 维度 | 约束 | 原因 |
|---|---|---|
| 场景驱动 | 每章 1-2 个真实场景开篇 | 不堆概念,先建立直觉 |
| 代码克制 | 单片段 ≤ 20 行,全章 ≤ 8 处 | 保留架构视角,避免陷入源码 |
| 层次递进 | 概念→机制→决策→风险 四层 | 架构师需要的递进式理解 |
| 跨篇引用 | 关键术语首次出现时标注系列内位置 | 14 篇互为索引,不重复 |
| 架构师视角 | 每章末段固定一段"架构师视角"小节 | 把机制映射到稳定性/性能/风险 |
| 故障落地 | 14 篇末尾专章给故障速查表 | 排查时有抓手 |
| 与 MM_v2 对仗 | 关键概念显式交叉引用 | 拼成完整 Android 内存图 |

---

## 9. 进度

全系列 14 篇正文已完成（含 README）。

---

## 10. 14 篇的"对仗设计"完整图

```
MM_v2 篇                PLE 篇                    对仗关系
─────────              ─────                    ────────
01 内存总览       ↔    01 加载全景          ←  姐妹锚点篇
02 VMA 体系       ↔    02 ELF 格式         ←  虚拟地址空间
03 ART 堆         ↔    06/07/08 DEX/Class  ←  ART 视角
04 Native 堆      ↔    03/04/05 linker64   ←  native 加载
05 AMS 内存       ↔    12 进程启动         ←  AMS 参与
06 LMKD           ↔    13 进程类型         ←  进程管理
07 PSI/压力       ↔    14 故障地图         ←  稳定性治理
08-11 内核        ↔    (跨篇引用)         ←  共同基础
12 风险           ↔    14 风险            ←  风险对仗
13 诊断           ↔    14(含诊断)         ←  诊断融入
14 进程类型学     ↔    13 进程类型        ←  完全对仗 ★

                  ─────
                  9-11 资源/进程/启动   ← PLE 独有(启动时)
                  04 scudo             ← MM 独有(运行时分配)
```

**关键洞察**:
- **MM_v2 关注"运行时"**(内存长啥样)
- **PLE 关注"启动时"**(怎么装起来)
- **两者交集在 14/13 进程类型篇**——同一组进程,两个视角

---

## 11. 8 阶段流水线(全系列贯穿图)

```
┌─────────────────────────────────────────────────────────────┐
│  阶段 0: execve 入口(内核)                                    │
│    └─ 解析 ELF / mmap PT_LOAD / 跳到 linker64                 │
│    PLE 02 详述                                                │
├─────────────────────────────────────────────────────────────┤
│  阶段 1: linker64 加载 .so                                    │
│    └─ 7 步流程: _start / 自举 / 解析可执行文件 / NEEDED 树     │
│        / 重定位 / .init_array / 跳入口                       │
│    PLE 03-05 详述                                             │
├─────────────────────────────────────────────────────────────┤
│  阶段 2: JNI_OnLoad 启动 ART                                  │
│    └─ libart.so 触发 / Runtime::Create / GC 线程              │
│    PLE 05 §4 详述                                             │
├─────────────────────────────────────────────────────────────┤
│  阶段 3: Zygote fork                                          │
│    └─ Zygote 进程接收 fork 请求 / 子进程继承                  │
│    PLE 12 §3 详述                                             │
├─────────────────────────────────────────────────────────────┤
│  阶段 4: ActivityThread.main()                                │
│    └─ 子进程反射调用 / 启动主线程 Looper                      │
│    PLE 12 §4 详述                                             │
├─────────────────────────────────────────────────────────────┤
│  阶段 5: ClassLoader + DEX 加载                               │
│    └─ PathClassLoader / mmap DEX / Verify / Init              │
│    PLE 06-09 详述                                             │
├─────────────────────────────────────────────────────────────┤
│  阶段 6: Resources 加载                                        │
│    └─ AssetManager / ApkAssets / arsc 解析 / ResTable         │
│    PLE 10-11 详述                                             │
├─────────────────────────────────────────────────────────────┤
│  阶段 7: 第一行 Java 代码执行                                 │
│    └─ Activity 启动 / 布局 inflate / 第一帧渲染              │
│    (本系列外)                                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 12. 给读者的建议

### 12.1 如果你只想解决眼前问题

**直接读 [PLE 14 §7 速查矩阵](14-加载失败与启动期故障速查.md)**——5 秒定位 + 5-30 分钟修复。

### 12.2 如果你想系统理解

按 01 → 02-05（ELF/动态链接）→ 06-09（DEX/ART）→ 10-13（资源/进程）→ 14（风险）通读。

### 12.3 如果你想做加载性能优化

优先读 03/04/05（linker / 重定位 / 构造函数）与 09（AOT/JIT），再对照 MM_v2 内存账本。

### 12.4 如果你想理解 PLE 与 MM_v2 的关系

**先读 [MM_v2 README](../Memory_Management/MM_v2/README-MM_v2系列.md)**,再读 [PLE 01](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md) 和 [PLE 13](13-不同进程类型的加载差异-zygote-system_server-app-native.md)。

---

## 13. 反馈与改进

本系列为自学导向,完全开放给读者反馈:

- **错误指出**:任何技术错误、代码错误、引用错误——指出必改
- **章节补充**:任何概念讲得不够透——可加补充章节
- **实战案例**:任何"线上真实案例"想分享——欢迎投稿
- **新文章建议**:任何本系列没覆盖但应该覆盖的——可提议新文章

---

## 附录 A:本系列的关键源码路径

**AOSP 路径**(以 AOSP `android-14.0.0_r1` 为准):

| 主题 | 路径 |
|---|---|
| ELF 解析 | `fs/binfmt_elf.c` |
| 动态链接器 | `bionic/linker/` |
| linker 主流程 | `bionic/linker/linker.cpp` |
| namespace | `bionic/linker/android_namespace.cpp` |
| DEX 格式 | `art/libdexfile/dex/dex_file.h` |
| ClassLoader | `libcore/ojluni/src/main/java/java/lang/ClassLoader.java` |
| 类加载 | `art/runtime/class_linker.cc` |
| Verify | `art/runtime/verifier/method_verifier.cc` |
| dex2oat | `art/dex2oat/dex2oat.cc` |
| AssetManager | `frameworks/base/libs/androidfw/AssetManager.cpp` |
| ApkAssets | `frameworks/base/libs/androidfw/ApkAssets.cpp` |
| ResTable | `frameworks/base/libs/androidfw/ResourceTypes.cpp` |
| ZIP 解析 | `system/core/libziparchive/` |
| aapt2 | `frameworks/base/tools/aapt2/` |
| ZygoteInit | `frameworks/base/core/java/com/android/internal/os/ZygoteInit.java` |
| ZygoteServer | `frameworks/base/core/java/com/android/internal/os/ZygoteServer.java` |
| ActivityThread | `frameworks/base/core/java/android/app/ActivityThread.java` |
| SystemServer | `frameworks/base/services/java/com/android/server/SystemServer.java` |
| ProcessList | `frameworks/base/core/java/com/android/server/am/ProcessList.java` |

## 附录 B:本系列的关键工具

| 工具 | 用途 | 关键命令 |
|---|---|---|
| `readelf` | ELF 信息查看 | `-h` 头 / `-l` 段 / `-S` section / `-s` 符号 / `-d` 动态 / `-r` 重定位 |
| `objdump` | 反汇编 | `-d` 反汇编 / `-t` 符号表 |
| `nm` | 符号表 | `-D` 动态符号 / `-a` 所有 |
| `dexdump` | DEX 信息 | `-h` 头 / `-d` 反汇编 / `-i` id 表 |
| `baksmali` | DEX → smali | `disassemble app.apk -o smali/` |
| `oatdump` | OAT 反汇编 | `--header` / `--dump-classes` / `--method` |
| `aapt2` | 资源 + APK | `dump resources` / `dump xmltree` / `optimize` |
| `apksigner` | APK 签名 | `verify` / `sign` / `verify --print-certs` |
| `dex2oat` | DEX → ODEX | `--dex-input` / `--compiler-filter=speed-profile` |
| `unzip` / `zipinfo` | ZIP 解析 | `unzip -l` / `unzip -t` |
| `strace` | 系统调用 | `-e openat` |
| `simpleperf` | perf 分析 | `record -e cpu-cycles` / `report` |
| `perfetto` | trace | `perfetto -t 30s` |
| `R8` | DEX 优化 | `r8.jar --release` |

## 附录 C:本系列的所有异常关键字速查

见 [PLE 14 §7.1](14-加载失败与启动期故障速查.md) 完整速查矩阵。

## 附录 D:本系列与 MM_v2 的双向引用

### D.1 PLE → MM_v2 引用

| PLE 篇 | 引用 MM_v2 篇 |
|---|---|
| 01 加载全景 | 02 VMA 体系 |
| 02 ELF 格式 | 02 VMA 体系 |
| 03 linker64 | 04 Native 堆 |
| 04 重定位 | 04 Native 堆 |
| 05 .init_array | 14 进程类型学 |
| 06 DEX 格式 | 03 ART 堆 |
| 07 ClassLoader | 03 ART 堆 |
| 08 类生命周期 | 03 ART 堆 |
| 09 AOT/JIT | 03 ART 堆 |
| 10 资源加载 | 02 VMA 体系(部分) |
| 12 进程启动 | 14 进程类型学 |
| 13 进程类型 | 14 进程类型学(**对仗**) |
| 14 故障地图 | 12 风险 + 13 诊断 |

### D.2 MM_v2 → PLE 引用(在 MM_v2 README 中)

(MM_v2 README 14 中应包含 PLE 13 的对仗引用)

### D.3 完全对仗

**MM_v2 14 ↔ PLE 13**:同一组进程,运行时 vs 启动时。**两者一起读 = Android 进程的完整图景**。

---

> **本系列 14 篇 + 1 大纲 + 1 README = 16 个文件 / ~570KB / ~8200 行**。
> **从"execve 入口"到"加载失败速查"——我们走完了"程序加载与执行"的全景。**
> **记住 8 阶段流水线、四元动作、4 类进程类型、5 秒定位法,你的加载视角就立住了。**
