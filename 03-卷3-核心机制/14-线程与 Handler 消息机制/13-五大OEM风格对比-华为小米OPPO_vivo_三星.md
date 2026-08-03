# 13-五大 OEM 风格对比 - 华为/小米/OPPO/vivo/三星

> 系列:Android OEM Hook 技术解析(共 15 篇 + 1 大纲 + 1 全景图 + 1 README = 17 文件)
> 本篇定位:**横切专题 - 厂商对比**(全系列唯一一次厂商横向对比)
> 版本基线:**AOSP android-14.0.0_r1** / **HarmonyOS 4.0** / **HyperOS 1.0** / **ColorOS 14** / **OriginOS 4** / **One UI 6**

---

## 本篇定位(强制开头段)

- **系列角色**:**横切专题 - 厂商对比**(全系列第一次也是唯一一次)
- **强依赖**:
  - **[01-全景图](01-OEM-Hook全景图-本质与战场.md)**
  - **[08-场景 1 隐私保护](08-场景1-隐私保护-空白通行证与假数据.md)** ~ **[12-场景 5 折叠屏适配](12-场景5-折叠屏适配-平行视界与TaskFragment.md)**:5 大场景的厂商对比基础
- **承接自**:**12-场景 5 折叠屏适配**
- **衔接去**:**[14-OEM Hook 演进 - 从运行时到编译期](14-OEM_Hook演进-从运行时到编译期.md)**
- **不重复内容**:
  - 不重复 08-12 各篇已讲的场景内容(本章做横向汇总)
  - 不重复 02-07 各篇已讲的层级原理(本章聚焦厂商差异)

---

## 角色设定

我是一名 **Android 稳定性架构师**,正在系统学习 OEM Hook 技术。本篇是系列的第 13 篇,主题是 **5 大 OEM 厂商的 Hook 风格对比**。

学完本篇后,我应该能够:
- 说出华为/小米/OPPO/vivo/三星各自的核心 Hook 风格
- 区分"底层重构派"(华为)vs"系统流畅派"(小米)vs"UI 动效派"(OPPO)vs"视觉设计派"(vivo)vs"安全合规派"(三星)
- 在做 App 兼容性适配时,知道应该优先关注哪些 OEM 的 Hook 风格

---

## 上下文

- **上一篇**:**[12-场景 5 折叠屏适配 - 平行视界与 TaskFragment](12-场景5-折叠屏适配-平行视界与TaskFragment.md)**
- **下一篇**:**[14-OEM Hook 演进 - 从运行时到编译期](14-OEM_Hook演进-从运行时到编译期.md)**
- **本系列 README** 见 Hook/README-OEM_Hook 系列.md

---

## 一、OEM 风格矩阵总览

### 1.1 5 大 OEM × 5 维度矩阵

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│                  5 大 OEM × 5 维度对比矩阵                                           │
├──────────┬────────────┬────────────┬────────────┬────────────┬────────────┤
│  维度     │  华为        │  小米        │  OPPO       │  vivo       │  三星        │
│          │ HarmonyOS   │ HyperOS     │ ColorOS     │ OriginOS    │ One UI      │
├──────────┼────────────┼────────────┼────────────┼────────────┼────────────┤
│  核心定位 │ 底层重构    │ 系统流畅    │ UI 动效     │ 视觉设计    │ 安全合规    │
│          │ + 分布式    │ + 万物互联  │ + 后台管理  │ + 内存优化  │ + 标准化    │
├──────────┼────────────┼────────────┼────────────┼────────────┼────────────┤
│  Hook    │ ★★★★      │ ★★★★     │ ★★★      │ ★★★      │ ★★        │
│  激进度  │ 深层魔改    │ 深度定制    │ 中度定制    │ 中度定制    │ 保守标准化  │
├──────────┼────────────┼────────────┼────────────┼────────────┼────────────┤
│  核心     │ 内核 +     │ Framework  │ WMS +     │ Native +   │ LSM +     │
│  Hook    │ Framework  │ + Native   │ Surface-  │ ART       │ Knox      │
│  层       │            │            │ Flinger    │            │ Framework │
├──────────┼────────────┼────────────┼────────────┼────────────┼────────────┤
│  杀手锏   │ 方舟引擎   │ 澎湃 OS    │ 量子动画   │ 原子组件   │ Knox      │
│  功能    │ 分布式软总线 │ 灵动通知   │ 潘塔纳尔   │ 内存融合   │ DeX 桌面  │
│          │ 平行视界   │ 空白通行证 │ 后台墓碑   │ 不公平调度 │ Good Lock │
├──────────┼────────────┼────────────┼────────────┼────────────┼────────────┤
│  风格    │ 自主可控    │ 流畅优先    │ 视觉极致    │ 设计驱动    │ 标准稳定   │
├──────────┼────────────┼────────────┼────────────┼────────────┼────────────┤
│  AOSP   │ 13          │ 14          │ 14          │ 14          │ 14         │
│  对应版本 │             │             │             │             │             │
└──────────┴────────────┴────────────┴────────────┴────────────┴────────────┘
```

### 1.2 OEM 风格速记

```
┌─────────────────────────────────────────────────────────────┐
│           5 大 OEM 风格速记                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  华为:重度底层 + 分布式                                     │
│    → Hook 层最深的 OEM,改内核、改 Framework、改 HAL         │
│    → 强项是"自主可控"(方舟、平行视界)                      │
│                                                             │
│  小米:重度 Framework + 万物互联                            │
│    → Framework 层最深的 OEM,改 AMS/WMS/PMS                 │
│    → 强项是"系统流畅"(澎湃 OS + 灵动通知)                  │
│                                                             │
│  OPPO:UI 动效 + 后台管理                                   │
│    → WMS + SurfaceFlinger 层最深,改渲染管线                │
│    → 强项是"视觉极致"(量子动画引擎 + 后台墓碑)             │
│                                                             │
│  vivo:视觉设计 + Native 内存                               │
│    → Native + ART 层最深,改 Bionic + 内存压缩              │
│    → 强项是"设计驱动"(原子组件 + 内存融合)                 │
│                                                             │
│  三星:标准化 + 安全                                         │
│    → LSM + Framework 层,Hook 最保守                       │
│    → 强项是"安全合规"(Knox + Good Lock + DeX)             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、华为(HarmonyOS / EMUI) - 底层重构与分布式

### 2.1 华为 Hook 风格的核心特征

```
┌─────────────────────────────────────────────────────────────┐
│           华为 Hook 风格的核心特征                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  核心定位:底层重构 + 分布式                                  │
│                                                             │
│  Hook 激进度:★★★★(最激进)                              │
│  核心 Hook 层:Kernel + Framework + HAL                     │
│  典型 Hook 数量:30-40 个                                    │
│                                                             │
│  风格关键词:                                                 │
│  ├── 自主可控(强调不被美国"卡脖子")                       │
│  ├── 全栈优化(从内核到 UI 全链路 Hook)                      │
│  ├── 分布式能力(分布式软总线、跨设备协同)                  │
│  └── 性能极致(方舟引擎、NPU 加速)                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 华为的核心 Hook 方案

| 方案 | 实现层 | 技术亮点 |
|---|---|---|
| **方舟引擎** | Kernel + ART | GPU Turbo + NPU 加速,游戏性能提升 60%+ |
| **分布式软总线** | Kernel(Binder) | 跨设备分布式通信,延迟 < 10ms |
| **EROFS 文件系统** | Kernel | 改进版只读文件系统,加载速度提升 20% |
| **平行视界** | Framework-Binder | TaskFragment 拆分,自研最早(详见 12) |
| **方舟编译器** | ART | AOT 编译优化,启动速度提升 30%+ |
| **确定性时延引擎** | Kernel | 任务调度优化,帧率抖动 < 5ms |

### 2.3 华为 HarmonyOS NEXT 的"纯血鸿蒙"演进

```
┌─────────────────────────────────────────────────────────────┐
│           华为 HarmonyOS NEXT 的演进                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  HarmonyOS(早期):基于 AOSP 的魔改                            │
│  ├── 内核:基于 Linux                                        │
│  ├── 框架:基于 AOSP                                        │
│  └── 兼容 Android App                                       │
│                                                             │
│  HarmonyOS NEXT(2024+):纯血鸿蒙                             │
│  ├── 内核:自研 HarmonyOS 内核(部分基于 Linux,部分自研)       │
│  ├── 框架:自研 HarmonyOS 框架(不再依赖 AOSP)                │
│  ├── 不兼容 Android App                                      │
│  └── 自有生态(HMS)                                          │
│                                                             │
│  Hook 视角的演进:                                           │
│  早期:在 AOSP 源码级 Hook(改 AMS/WMS/PMS)                  │
│  NOW:不再有"Hook"概念——本身就是底层,无需 Hook              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.4 华为 Hook 的典型应用

**应用 1:方舟引擎(游戏性能)**

```java
// (华为 HarmonyOS 实现,基于 AOSP 13,具体 commit 待确认)
//
// 方舟引擎:在 ART 层 Hook + Kernel 层调度干预

// ART 层:deopt 触发后,GPU Turbo 接管图形渲染
public class ArkCompilerHook {
    static void hookArkCompiler(ArtMethod* method) {
        // [OEM 拦截] 检测是否是 GPU 渲染方法
        if (isGpuRenderMethod(method)) {
            // [OEM 替换] 调用 GPU Turbo 优化版本
            gpu_turbo_render(method);
        }
    }
}

// Kernel 层:vendor hook 干预 EAS 调度器
// (参考 02-Kernel 层 Hook 第 6 节)
```

**应用 2:分布式软总线**

```c
// (华为 HarmonyOS 实现,基于 Kernel 5.10)
// 
// 分布式软总线:在 Binder 层扩展,支持跨设备通信

struct hwbinder_transaction {
    // 原始 Binder 字段
    struct binder_transaction_data transaction;
    
    // [OEM 扩展] 分布式软总线字段
    uint32_t device_id;        // 目标设备 ID
    uint32_t hop_count;        // 跳数(用于路由)
    uint64_t discovery_token;  // 设备发现 token
};
```

---

## 三、小米(HyperOS / MIUI) - 系统流畅与万物互联

### 3.1 小米 Hook 风格的核心特征

```
┌─────────────────────────────────────────────────────────────┐
│           小米 Hook 风格的核心特征                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  核心定位:系统流畅 + 万物互联                                │
│                                                             │
│  Hook 激进度:★★★★(深度定制)                              │
│  核心 Hook 层:Framework + Native                            │
│  典型 Hook 数量:25-35 个                                    │
│                                                             │
│  风格关键词:                                                 │
│  ├── 流畅度优先(动画配合调度,无感拦截)                     │
│  ├── 万物互联(澎湃 OS、智能家居、车机联动)                  │
│  ├── 隐私保护(空白通行证、隐私水印)                       │
│  └── 性价比(同硬件下提供流畅体验)                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 小米 Hook 的核心方案

| 方案 | 实现层 | 技术亮点 |
|---|---|---|
| **澎湃 OS** | Framework + Native | 底层重构,流畅度提升 30%+ |
| **动态线程调度** | Kernel + HAL | 根据场景动态调整 CPU 调度 |
| **小窗模式** | Framework-Binder(WMS) | 见 06-Framework-Binder 第 4.4 节 |
| **空白通行证** | Framework-Binder(ServiceManager) | 见 08-场景 1 第 4 节 |
| **灵动通知** | Framework-Binder(Notification) | 系统级通知管理 |
| **隐私水印** | App-UI(RRO) | 截图自动加水印 |

### 3.3 小米"无感拦截"的实现细节

详见 [06-Framework-Binder 层 Hook](06-Framework-Binder层Hook-ServiceManager代理与AMS_WMS_PMS插桩.md) 第 7 节。本节补充小米的"流畅"特色。

### 3.4 小米 Hook 的典型应用

**应用 1:澎湃 OS 底层重构**

```java
// (小米 HyperOS 实现,具体 commit 待确认)
//
// 澎湃 OS:Framework 层深度重构,提升流畅度

public class HyperOSFramework {
    // [OEM 重构] 1. Activity 启动优化
    public void optimizeActivityStart() {
        // 跳过某些预启动检查,加速启动
        if (HyperOSPolicy.shouldSkipPreCheck(callerPackage)) {
            // 直接启动,跳过冗余检查
            mActivityTaskManager.startActivity(...);
        }
    }
    
    // [OEM 重构] 2. 窗口动画优化
    public void optimizeWindowAnimation() {
        // 自定义动画曲线(配合 Skia Hook)
        WindowAnimationHooks.installQuantumCurve();
    }
    
    // [OEM 重构] 3. 渲染管线优化
    public void optimizeRenderPipeline() {
        // 优化 Skia 渲染管线
        RenderThread.optimizeQuantumAnimation();
    }
}
```

---

## 四、OPPO(ColorOS) - UI 动效与后台管理

### 4.1 OPPO Hook 风格的核心特征

```
┌─────────────────────────────────────────────────────────────┐
│           OPPO Hook 风格的核心特征                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  核心定位:UI 动效 + 后台管理                                │
│                                                             │
│  Hook 激进度:★★★(中度定制)                              │
│  核心 Hook 层:Framework-Binder(WMS) + Native(Skia)         │
│  典型 Hook 数量:20-30 个                                    │
│                                                             │
│  风格关键词:                                                 │
│  ├── 视觉极致(量子动画引擎、非线性动画)                    │
│  ├── 后台严格(ColorOS 后台墓碑)                            │
│  ├── 跨端协同(潘塔纳尔系统)                               │
│  └── 拍照优化(相机深度定制)                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 OPPO Hook 的核心方案

| 方案 | 实现层 | 技术亮点 |
|---|---|---|
| **量子动画引擎** | Native(Skia) | 非线性动画曲线,见 04-Native 第 3.4 节 |
| **潘塔纳尔跨端系统** | Framework-Binder | 手机/平板/车机无缝流转 |
| **后台墓碑机制** | Framework-Binder(AMS) | 见 09-场景 2 后台治理 |
| **隐私替身** | Framework-Binder(ServiceManager) | 见 08-场景 1 第 6 节 |
| **拍照算法** | HAL + Native | 索尼/三星相机深度调优 |

### 4.3 OPPO 量子动画的完整实现

详见 [04-Native 层 Hook](04-Native层Hook-Bionic与Skia渲染拦截.md) 第 3 节。

### 4.4 OPPO Hook 的典型应用

**应用 1:ColorOS 后台墓碑**

```java
// (OPPO ColorOS 实现,具体 commit 待确认)
//
// ColorOS 后台墓碑:App 退到后台后冻结内存和 CPU

public class ColorOSTombstone {
    // [OEM 拦截] App 进入后台
    public void onAppBackground(String packageName, int uid) {
        // [OEM 替换] 墓碑化 App
        // 1. 冻结进程
        cgroup_freezer_freeze(uid);
        
        // 2. 压缩内存(类似 vivo 内存融合)
        compressProcessMemory(uid);
        
        // 3. 记录墓碑状态
        TombstoneDb.markTombstoned(packageName, uid);
    }
    
    // [OEM 拦截] App 重新进入前台
    public void onAppForeground(String packageName, int uid) {
        if (TombstoneDb.isTombstoned(packageName, uid)) {
            // [OEM 替换] 解冻进程(秒恢复)
            cgroup_freezer_thaw(uid);
            decompressProcessMemory(uid);
            TombstoneDb.unmark(packageName);
        }
    }
}
```

---

## 五、vivo(OriginOS) - 视觉设计与内存优化

### 5.1 vivo Hook 风格的核心特征

```
┌─────────────────────────────────────────────────────────────┐
│           vivo Hook 风格的核心特征                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  核心定位:视觉设计 + 内存优化                                │
│                                                             │
│  Hook 激进度:★★★(中度定制)                              │
│  核心 Hook 层:Native(Bionic + Skia) + ART                  │
│  典型 Hook 数量:15-25 个                                    │
│                                                             │
│  风格关键词:                                                 │
│  ├── 设计驱动(原子组件、华容网格)                          │
│  ├── 内存优化(内存融合 8GB→12GB)                          │
│  ├── 不公平调度(Hook 进程优先级)                          │
│  └── 隐私空间(独立加密空间)                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 vivo Hook 的核心方案

| 方案 | 实现层 | 技术亮点 |
|---|---|---|
| **原子组件** | App-UI(RRO + View) | 见 07-App-UI 第 6.2 节 |
| **内存融合** | Native(Bionic malloc) | 见 04-Native 第 5.1 节 |
| **不公平调度** | Kernel(EAS) | 调整进程 nice 值,优先前台 App |
| **隐私空间** | Framework-Binder(PMS) | 独立加密的 App 空间 |
| **华容网格** | App-UI(Launcher) | 桌面图标网格自定义 |

### 5.3 vivo 内存融合的完整实现

详见 [04-Native 层 Hook](04-Native层Hook-Bionic与Skia渲染拦截.md) 第 5.1 节。

### 5.4 vivo Hook 的典型应用

**应用 1:OriginOS 不公平调度**

```c
// (vivo OriginOS 实现,具体 commit 待确认)
//
// 不公平调度:前台 App 优先级提升,后台 App 优先级降低

static void vivo_unfair_scheduler_tick(void *data, struct rq *rq) {
    struct task_struct *curr = rq->curr;
    
    // [OEM 拦截] 检测前台/后台
    if (is_foreground_process(curr)) {
        // [OEM 替换] 前台进程:提升优先级
        set_user_nice(curr, -10);  // 提高 nice 值
        set_cpus_allowed_ptr(curr, cpumask_of(7));  // 绑定大核
    } else {
        // 后台进程:降低优先级
        set_user_nice(curr, 10);  // 降低 nice 值
    }
}

// 注册到 scheduler_tick Vendor Hook
register_trace_android_vh_scheduler_tick(vivo_unfair_scheduler_tick, NULL);
```

---

## 六、三星(One UI) - 安全合规与标准化

### 6.1 三星 Hook 风格的核心特征

```
┌─────────────────────────────────────────────────────────────┐
│           三星 Hook 风格的核心特征                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  核心定位:安全合规 + 标准化                                  │
│                                                             │
│  Hook 激进度:★★(保守标准化)                              │
│  核心 Hook 层:LSM + Framework(标准化)                      │
│  典型 Hook 数量:10-20 个                                    │
│                                                             │
│  风格关键词:                                                 │
│  ├── 安全合规(Knox 容器、企业级安全)                        │
│  ├── 标准化(优先用官方 API,自研较少)                       │
│  ├── 折叠屏(DeX、Galaxy Z 系列)                            │
│  └── Good Lock(用户级扩展)                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 三星 Hook 的核心方案

| 方案 | 实现层 | 技术亮点 |
|---|---|---|
| **Knox 安全框架** | LSM(Kernel) + Framework | 企业级安全容器 |
| **DeX 桌面模式** | Framework-Binder(WMS) | 外接显示器,桌面级体验 |
| **Good Lock** | App-UI(RRO + Plugin) | 用户级扩展,锁屏/通知魔改 |
| **Galaxy Z Fold/Flip** | Framework-Binder + App-UI | 折叠屏适配 |

### 6.3 三星 Knox LSM Hook 的实现

详见 [02-Kernel 层 Hook](02-Kernel层Hook-Vendor_Hook与eBPF.md) 第 5.3 节。

### 6.4 三星 Hook 的典型应用

**应用 1:DeX 桌面模式**

```java
// (三星 One UI 实现,基于 AOSP 14,具体 commit 待确认)
//
// DeX:外接显示器时,Android 变桌面

public class SamsungDeXManager {
    // [OEM 拦截] 检测到 HDMI 连接
    public void onDisplayConnected(Display display) {
        if (display.type == Display.TYPE_EXTERNAL) {
            // [OEM 替换] 切换到 DeX 模式
            // 1. 创建一个虚拟 Display 作为 DeX 桌面
            VirtualDisplay dexDisplay = createVirtualDisplay(
                "DeX Desktop", 1920, 1080, 160);
            
            // 2. 启动 DeX Launcher
            mContext.startActivityAsUser(dexLauncherIntent, 
                                          UserHandle.CURRENT_OR_SYSTEM);
            
            // 3. 通知 WMS 重写窗口尺寸
            mWMS.overrideDisplayInfo(dexDisplay.getDisplayInfo());
        }
    }
}
```

---

## 七、5 大厂商的"同一问题不同解法"

### 7.1 同一个"空白通行证",5 个厂商怎么实现

| 厂商 | 实现方式 | 技术差异 |
|---|---|---|
| **华为** | ServiceManager Proxy + AppOps | 与 AppOps 深度集成 |
| **小米** | ServiceManager Proxy + 单独模块 | 与"隐私水印"功能联动 |
| **OPPO** | ServiceManager Proxy + 隐私替身 | 与"应用伪装"功能联动 |
| **vivo** | ServiceManager Proxy + 隐私空间 | 与"隐私空间"功能联动 |
| **三星** | 标准化 AppOps | 没有特殊魔改 |

### 7.2 同一个"后台冻结",5 个厂商怎么实现

| 厂商 | 冻结机制 | 触发条件 |
|---|---|---|
| **华为** | cgroup freezer + 自研墓碑 | 退到后台 5 分钟 |
| **小米** | cgroup freezer + 智能判断 | 退到后台 5-30 分钟(根据 App 类型) |
| **OPPO** | 后台墓碑(类似 cgroup) | 退到后台 5 分钟 |
| **vivo** | 退到后台 5 分钟 | 退到后台 5 分钟 |
| **三星** | Doze 模式增强 | 系统级 Doze |

### 7.3 同一个"游戏模式",5 个厂商怎么实现

| 厂商 | 调度策略 | 触控优化 |
|---|---|---|
| **iQOO(属 vivo)** | CPU/GPU 全拉满 + EAS boost | 采样率 360Hz |
| **一加(属 OPPO)** | 提前绑核 + 网络优化 | 采样率 360Hz |
| **小米** | 智能调度 + 散热优化 | 采样率 240-360Hz |
| **华为** | GPU Turbo + NPU 加速 | 采样率 240-360Hz |
| **三星** | 标准游戏中心 | 采样率 240Hz |

### 7.4 同一个"应用双开",5 个厂商怎么实现

| 厂商 | userId | 支持 App 数量 | 限制 |
|---|---|---|---|
| **华为** | 999 | ~100 | 1 个分身 |
| **小米** | 999+ | 无限 | 几乎无限制 |
| **OPPO** | 999+ | 无限 | 几乎无限制 |
| **vivo** | 999+ | 无限 | 几乎无限制 |
| **三星** | 110+ | ~50 | 最多 5 个分身 |

---

## 八、对 App 开发者的启示

### 8.1 App 兼容性矩阵

```
┌─────────────────────────────────────────────────────────────┐
│           App 兼容性需要关注的 5 个 OEM 维度                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ① 隐私保护                                                │
│     华为:纯净模式 + 隐私中心                                │
│     小米:空白通行证(返回假 IMEI/坐标)                      │
│     OPPO:隐私替身(返回假数据)                              │
│     vivo:隐私空间(独立加密)                                │
│     三星:标准化 AppOps                                     │
│     → App 必须能处理"假数据"                                │
│                                                             │
│  ② 后台治理                                                │
│     所有厂商:严格后台冻结                                   │
│     → App 必须适配"被冻结后秒恢复"                          │
│     → 推送必须用厂商推送 SDK                                │
│                                                             │
│  ③ 应用双开                                                │
│     华为:1 个分身                                          │
│     其他:无限分身                                          │
│     → App 必须能识别"分身空间"(避免被检测为多设备)          │
│                                                             │
│  ④ 游戏调度                                                │
│     所有厂商:鸡血调度 + 触控优化                           │
│     → 游戏 App 需要在 90Hz/120Hz 下测试                     │
│                                                             │
│  ⑤ 折叠屏适配                                              │
│     华为/三星/OPPO:平行视界/DeX                            │
│     → App 必须支持 TaskFragment(Android 14+)               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 App 兼容性测试建议

```
┌─────────────────────────────────────────────────────────────┐
│           App 兼容性测试矩阵(建议)                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  必备测试设备:                                                │
│  ├── 华为 Mate 60 Pro / Mate X5(鸿蒙 + 折叠屏)             │
│  ├── 小米 14 Pro / MIX Fold 4(HyperOS + 折叠屏)            │
│  ├── OPPO Find X7 / Find N5(ColorOS + 折叠屏)              │
│  ├── vivo X100 Pro / X Fold 3(OriginOS + 折叠屏)           │
│  └── 三星 Galaxy S24 / Z Fold 6(One UI + 折叠屏)           │
│                                                             │
│  必备测试场景:                                                │
│  ├── 隐私场景:开启假数据,App 是否能正常运行                 │
│  ├── 后台场景:App 退到后台 30 分钟,通知/服务是否正常        │
│  ├── 双开场景:开启双开,数据是否隔离                        │
│  ├── 游戏场景:90Hz/120Hz 屏幕下,操作是否流畅                │
│  └── 折叠屏场景:App 是否能正确适配折叠屏                    │
│                                                             │
│  兼容性测试自动化:                                            │
│  ├── 用 Appium 编写自动化测试                                │
│  ├── 覆盖 5 大 OEM × 5 大场景 = 25 个测试用例               │
│  └── 每次 OEM 系统更新都要回归                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 九、对稳定性工程师的启示

### 9.1 OEM Hook 是兼容性问题的"头号嫌疑"

```
┌─────────────────────────────────────────────────────────────┐
│       OEM Hook 兼容性问题的"5 秒定位"                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  当 App 在某 OEM 设备上出问题:                                │
│                                                             │
│  Step 1:确认是 OEM Hook 问题,还是 App 自身问题              │
│    - 关闭该 OEM 的隐私/后台等 Hook 功能                       │
│    - 如果问题消失 → 确认是 OEM Hook 问题                    │
│                                                             │
│  Step 2:定位是哪个 OEM Hook 层                                │
│    - Kernel 层 Hook → 看 dmesg / 调度器延迟                 │
│    - HAL 层 Hook → 看 /sys/.../cpufreq 等                   │
│    - Native 层 Hook → 看 malloc 性能 / Skia 渲染            │
│    - ART 层 Hook → 看方法调用栈                              │
│    - Framework-Binder → 看 logcat 中 ServiceManager 输出    │
│    - App-UI 层 → 看 RRO overlay 列表                        │
│                                                             │
│  Step 3:定位是哪个 OEM 厂商的 Hook                              │
│    - 看设备型号和系统版本                                    │
│    - 查 OEM 的"功能开关"页面                                │
│    - 关闭对应功能,看问题是否消失                            │
│                                                             │
│  Step 4:报告问题或绕过                                      │
│    - 报告给 OEM(需要详细复现步骤)                          │
│    - App 适配:用白名单绕过                                  │
│    - 用户层:提示用户关闭某项 OEM 功能                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 稳定性工程师的 OEM Hook 知识储备

```
┌─────────────────────────────────────────────────────────────┐
│      稳定性工程师必备的 OEM Hook 知识                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Level 1(基础):                                            │
│  ├── 知道"6 层 × 4 动作"框架                               │
│  ├── 能区分 Kernel/HAL/Native/ART/Framework/App-UI 层     │
│  └── 知道"假数据"vs"权限拒绝"的差异                        │
│                                                             │
│  Level 2(进阶):                                            │
│  ├── 熟悉 5 大 OEM 的核心 Hook 风格                        │
│  ├── 能定位 OEM Hook 引发的常见问题                         │
│  └── 知道 OEM 白名单机制 / cgroup freezer 概念              │
│                                                             │
│  Level 3(高级):                                            │
│  ├── 熟悉 ART Method Hook / 字段 Hook 原理                  │
│  ├── 熟悉 GKI Vendor Hook / LSM Hook 原理                  │
│  ├── 能读 OEM 修改后的 AOSP 源码                            │
│  └── 能定位 Android 大版本升级导致的 Hook 失效问题           │
│                                                             │
│  Level 4(专家):                                            │
│  ├── 熟悉 Android 14+ 的 TaskFragment / RRO / AppOps        │
│  ├── 能写 OEM 自研 Hook 兼容层                              │
│  └── 能在 Android 大版本升级时,预估 OEM Hook 失效面         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 十、风险地图

```
┌─────────────────────────────────────────────────────────────┐
│           5 大 OEM 对比风险地图                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  风险类型             触发场景              日志关键字         │
│  ─────────────────────────────────────────────────────       │
│  ① App 兼容性         同一 App 在 5 OEM    "OEM-specific  │
│     测试遗漏           上行为不同            behavior"        │
│                                                             │
│  ② 用户报告混乱       OEM 功能开关位置不同   "找不到设置"  │
│                                                             │
│  ③ 误判 Hook 厂商      看 logcat 难以区分    "wrong vendor│
│                       是哪个 OEM 的 Hook    identification" │
│                                                             │
│  ④ 升级适配成本       每个 OEM 升级都要      "5x upgrade    │
│                       单独适配                cost"          │
│                                                             │
│  ⑤ 内部文档维护       5 OEM × N 场景        "documentation│
│                       文档爆炸               explosion"      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 十一、总结 - 架构师视角的 7 条 Takeaway

1. **5 大 OEM 各有核心风格**——华为底层、小米流畅、OPPO 动效、vivo 设计、三星标准
2. **Hook 激进度差异巨大**——华为小米激进(30+ 个 Hook),OPPO/vivo 中度(15-30),三星保守(< 20)
3. **同一问题不同解法**——空白通行证 5 个厂商都做,但实现路径不同
4. **App 兼容性测试必须覆盖 5 大 OEM**——25 个用例(5 OEM × 5 场景)是基本要求
5. **OEM Hook 是兼容性问题的"头号嫌疑"**——关闭对应功能可快速定位
6. **稳定性工程师需要 OEM Hook 知识储备**——至少到 Level 2(进阶)才能应对日常问题
7. **Android 大版本升级是 OEM Hook 的"大考"**——每个 OEM 都要重新适配,工作量巨大

**5 OEM 对比速查路径**(遇到问题时):
```
线上问题(某 OEM 设备 App 异常)
   ↓
5 秒定位:是哪个 OEM?哪个 Hook 层?哪个 Hook 动作?
   ↓
查表:5 OEM × 5 场景对比表 → 看该 OEM 在该场景的实现
   ↓
修复:关闭对应 OEM Hook 功能 → 看问题是否消失
   → 报告给 OEM 厂商 / App 适配绕过
```

---

## 附录 A:核心源码路径索引(5 大 OEM 共同相关)

| 文件 | 完整路径 | 说明 |
|---|---|---|
| `ServiceManager.java` | `frameworks/base/core/java/android/os/ServiceManager.java` | 所有 OEM 都会拦截 |
| `ActivityManagerService.java` | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` | 后台治理拦截 |
| `WindowManagerService.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java` | 折叠屏/小窗拦截 |
| `PackageManagerService.java` | `frameworks/base/services/core/java/com/android/server/pm/PackageManagerService.java` | 应用双开拦截 |
| `TaskFragment.java` | `frameworks/base/services/core/java/com/android/server/wm/TaskFragment.java` | 折叠屏适配 |

---

## 附录 B:5 大 OEM 公开基线

| 厂商 | 最新系统 | 对应 AOSP | 文档 |
|---|---|---|---|
| 华为 | HarmonyOS 4.0 | AOSP 13 | 华为开发者联盟 |
| 小米 | HyperOS 1.0 | AOSP 14 | 小米开放平台 |
| OPPO | ColorOS 14 | AOSP 14 | OPPO 开放平台 |
| vivo | OriginOS 4 | AOSP 14 | vivo 开放平台 |
| 三星 | One UI 6 | AOSP 14 | 三星开发者 |

---

## 附录 C:5 大 OEM Hook 数量估算

| 厂商 | 估算 Hook 数量 | 主要分布 |
|---|---|---|
| 华为 | 30-40 | Kernel(10)+ Framework(20)+ HAL(5) |
| 小米 | 25-35 | Framework(15)+ Native(10)+ App-UI(5) |
| OPPO | 20-30 | Framework(10)+ Native(Skia)(10)+ App-UI(5) |
| vivo | 15-25 | Native(Bionic)(10)+ ART(5)+ App-UI(5) |
| 三星 | 10-20 | Framework(10)+ LSM(5) |

注:数量为公开资料估算,实际 OEM Hook 数量(含子层 Hook 点)远超此数。

---

## 附录 D:5 大 OEM 速查表(工程基线)

| OEM | Hook 风格 | 兼容重点 | 测试设备 |
|---|---|---|---|
| 华为 | 激进 + 分布式 | 鸿蒙 NEXT + 平行视界 | Mate 60 Pro / Mate X5 |
| 小米 | 流畅 + 万物互联 | 澎湃 OS + 灵动通知 | 14 Pro / MIX Fold 4 |
| OPPO | 动效 + 后台 | 量子动画 + 后台墓碑 | Find X7 / Find N5 |
| vivo | 设计 + 内存 | 原子组件 + 内存融合 | X100 Pro / X Fold 3 |
| 三星 | 标准 + 安全 | Knox + DeX | S24 / Z Fold 6 |

---

## 篇尾衔接

下一篇 **[14-OEM Hook 演进 - 从运行时到编译期](14-OEM_Hook演进-从运行时到编译期.md)** 将深入:

- Android 收紧的三大压力(Hidden API / SELinux+GKI / 兼容性反噬)
- 演进方向 1:运行时动态注入 → 编译期源码修改
- 演进方向 2:Framework → HAL/Kernel (GKI Vendor Hook 合法干预)
- 演进方向 3:OEM 自研 → 官方扩展机制(AppOps / RRO / Mainline / WindowInsets / TaskFragment)
- Android 12 → 13 → 14 → 15 关键收紧节点时间线
- 未来趋势预测(Android 16+)
- OEM 的应对策略

> 本篇完成了**横向对比**(5 大 OEM 的"现在"),下一篇进入**纵向时间线**(Android 收紧下的"未来")。
