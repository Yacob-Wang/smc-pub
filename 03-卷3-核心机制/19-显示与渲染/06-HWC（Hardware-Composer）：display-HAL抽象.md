# 06-Foundation/Graphics · 06 · HWC（Hardware Composer）：display HAL 抽象

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 显示 / 屏幕异常
>
> **强依赖**：[01 图形栈总览](01-图形栈总览：app-WindowManager-SurfaceFlinger-HWC-Display.md) · [02 SurfaceFlinger 内部](02-SurfaceFlinger内部：合成-VSync-Layer树.md) · [03 BufferQueue](03-BufferQueue：跨进程图形缓冲机制.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 HWC（Hardware Composer）HAL 这个 display 抽象层讲清楚——oncall 5 秒定位"显示异常是 HWC 错 / 合成错 / 驱动错"
- **不是**：不复述 [02 §4 GLES vs HWC 合成](02-SurfaceFlinger内部：合成-VSync-Layer树.md)（本文深入 HWC HAL 细节）；不复述 [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md)（综合实战）
- **承接自**：[02 §4.1 合成决策](02-SurfaceFlinger内部：合成-VSync-Layer树.md) → 本文展开 HWC HAL
- **衔接去**：[07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md) / [01-Mechanism/Kernel/Memory_Management](../../../01-Mechanism/Kernel/Memory_Management/) / [06-Foundation/Network/05](../Network/05-netd-NetworkManagementService：网络策略.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章 HWC 是什么 + 关键源码 | 必备 |
| 2 | 第 3 章 4 大 HAL 接口 | 核心 |
| 3 | 第 5 章 5 大实战 case | oncall 用 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**HWC = 屏幕硬件的 HAL 抽象层——SF 通过 HWC HAL 让 vendor 决定哪些 layer 走 GPU 合成 / 哪些硬件直送——5 类显示异常，oncall 5 秒定位"是不是 HWC 驱动错"。**

AOSP 17 上 HWC 跑在 HIDL/AIDL HAL 服务。理解 HWC = 5 秒定位"显示问题是不是 vendor 驱动"。

---

## 1. HWC 是什么

### 1.1 一句话定义

**HWC（Hardware Composer）= Display 硬件的 HAL 抽象层——让 vendor 实现合成逻辑，决定哪些 layer 走硬件 / 哪些走 GPU。**

### 1.2 4 大特性

| 特性 | 含义 | 性能影响 |
|:-----|:-----|:--------|
| **HAL 抽象** | vendor 实现合成 | 灵活 |
| **硬件决策** | 哪些走硬件 | 性能 |
| **vsync 同步** | 硬件 vsync | 流畅 |
| **多 Display** | 多屏支持 | 笔记本 / 折叠屏 |

### 1.3 关键源码

```
hardware/interfaces/graphics/composer/
├── 2.1/                          ← HWC 2.1（HIDL）
│   ├── IComposer.hal             ← Composer 接口
│   ├── IComposerClient.hal        ← Client 接口
│   └── ...
├── 2.2/                          ← HWC 2.2（HIDL）
├── 2.3/                          ← HWC 2.3（HIDL）
├── 2.4/                          ← HWC 2.4（HIDL）
└── AIDL/                         ← HWC 3.0（AOSP 15+）
    ├── IComposer.aidl
    └── ...

frameworks/native/services/surfaceflinger/
└── Hwc2/
    ├── Hwc2Composer.cpp           ← HWC 2.x 适配
    └── Hwc2ComposerHal.cpp         ← HAL 调用

hardware/qcom/display/composer/     ← Qualcomm 实现
hardware/mediatek/display/composer/  ← MediaTek 实现
hardware/google/display/composer/    ← Google 实现
```

### 1.4 AOSP 17 HWC 关键变化

```
AOSP 8  → HWC 2.0（HIDL 化）
AOSP 11 → HWC 2.4 稳定
AOSP 12 → Multi-display 增强
AOSP 14 → HWC 2.4 完整
AOSP 15 → HWC 3.0（AIDL 替代 HIDL）
AOSP 16 → HWC 3.0 增强
AOSP 17 → HWC 3.0 默认（AIDL）
```

---

## 2. HWC 架构

### 2.1 4 层架构

```
[SurfaceFlinger]
    │
    │ Hwc2::Composer
    ▼
[HWC HAL Client]
    │
    │ HIDL/AIDL
    ▼
[HWC HAL Server (vendor)]
    │
    │ vendor API
    ▼
[Kernel / Driver]
    │
    │ vendor HAL
    ▼
[Display Hardware]
```

### 2.2 4 大组件

| 组件 | 角色 |
|:-----|:-----|
| **IComposer** | HAL Server（vendor 实现）|
| **IComposerClient** | HAL Client（SF 调）|
| **ComposerHal** | 适配层 |
| **Vendor Driver** | vendor 实现（高通 / 联发科）|

### 2.3 4 大 HWC capability

| Capability | 含义 | 性能影响 |
|:----------|:-----|:--------|
| **LAYER_TYPE** | 支持 layer 类型 | 灵活 |
| **GEOMETRY** | 几何变换 | 性能 |
| **BLENDING** | 混合模式 | 透明合成 |
| **DISPLAY** | 显示器控制 | 屏幕 |

---

## 3. 4 大 HAL 接口

### 3.1 IComposer（vendor 实现）

```hal
// IComposer.hal（AOSP 17 简化）
interface IComposer {
    // 初始化
    init() generates (Error err);
    
    // 创建 virtual display
    createVirtualDisplay(...) generates (...);
    
    // 销毁 display
    destroyVirtualDisplay(...);
    
    // 4 大 capability
    getCapabilities() generates (...);
};
```

### 3.2 IComposerClient（SF 调）

```hal
// IComposerClient.hal（AOSP 17 简化）
interface IComposerClient {
    // 注册回调
    registerCallback(IComposerCallback callback);
    
    // vsync
    onVsync(...) generates (...);
    
    // hotplug
    onHotplug(...) generates (...);
    
    // refresh
    onRefresh(...) generates (...);
    
    // vsync period 变化
    onVsyncPeriodTimingChanged(...) generates (...);
};
```

### 3.3 4 大回调

| 回调 | 触发时机 | SF 动作 |
|:-----|:--------|:--------|
| **onVsync** | VSync 信号 | 启动下一帧 |
| **onHotplug** | 屏幕插拔 | 重建 display |
| **onRefresh** | refresh request | 重新合成 |
| **onVsyncPeriodTimingChanged** | vsync 频率变化 | 调整调度 |

### 3.4 5 大错误码

```hal
// 4 大 error
enum Error : int32_t {
    NONE              = 0,
    BAD_CONFIG        = 1,
    BAD_DISPLAY       = 2,
    BAD_LAYER         = 3,
    BAD_PARAMETER     = 4,
    NO_RESOURCES      = 5,
    UNAUTHORIZED      = 6,
    ...
};
```

---

## 4. HWC 合成决策

### 4.1 5 大合成类型

| 类型 | 性能 | 何时用 | 限制 |
|:-----|:-----|:----|:----|
| **HWC 直接送显** | 优 | 简单 ColorLayer | 不支持旋转/alpha |
| **HWC transform** | 优 | 旋转 / 镜像 | Vendor 实现 |
| **GLES 合成** | 中 | 复杂合成 | CPU / GPU |
| **Vulkan 合成** | 优 | 大块合成 | Vulkan |
| **Client 合成** | 差 | 兜底 | 不用 |

### 4.2 HWC 合成决策流程

```
[1] SF 收到所有 buffer ready
[2] 对每个 Layer:
    a. 问 HWC：能硬件合成吗？
    b. HWC 返回 capability
    c. SF 决定走 HWC 还是 GLES
[3] HWC 合成（hardware）
[4] GLES 合成（software fallback）
[5] HWC 提交到 Display
```

### 4.3 4 大决策参数

| 参数 | 含义 | 影响 |
|:-----|:-----|:----|
| **format** | buffer 格式 | HWC 是否支持 |
| **transform** | 旋转 / 缩放 | HWC 能力 |
| **alpha** | 透明度 | 透明合成 |
| **blend** | 混合模式 | 视觉 |

### 4.4 5 大合成异常

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **HWC 不接受** | capability 不够 | `dumpsys SurfaceFlinger \| grep HWC` |
| **fallback 太多** | HWC 限制 | `dumpsys SurfaceFlinger \| grep Fallback` |
| **GPU 高** | 走 GLES | `dumpsys gpu` |
| **错位** | transform 错 | `dumpsys SurfaceFlinger` |
| **撕裂** | vsync 错 | `dumpsys SurfaceFlinger \| grep VSync` |

---

## 5. 5 大实战 case

### 5.1 Case 1：屏幕花屏 HWC 错

```
[症状] 屏幕花屏

[Step 1] 看 HWC 状态
$ adb shell dumpsys SurfaceFlinger | head -30
# 看 HWC version

[Step 2] 看 logcat
$ adb logcat -d | grep -i "HWC\|composer"
# 关键："Composer: HAL fail"

[Step 3] 重启 SF
$ adb shell stop surfaceflinger
$ adb shell start surfaceflinger

[Step 4] 看是否恢复
# 大概率恢复了

[Step 5] 修法
- 重启 SF
- 重启设备
- vendor 升级 HWC driver
```

### 5.2 Case 2：屏幕黑屏 HWC 驱动死

```
[症状] 黑屏

[Step 1] 看 HWC 进程
$ adb shell pidof android.hardware.graphics.composer
# 或
$ adb shell service list | grep composer
# 期望存在

[Step 2] 看 logcat
$ adb logcat -d -b system | grep "composer"
# 关键："composer died"

[Step 3] 重启 HWC
$ adb shell stop
$ adb shell start
# vendor HWC 进程

[Step 4] 看是否恢复

[Step 5] 修法
- vendor HWC 升级
- 检查 kernel driver
```

### 5.3 Case 3：屏幕亮度调不动

```
[症状] 屏幕亮度调不动

[Step 1] 看 brightness
$ adb shell settings get system screen_brightness
# 0-255

[Step 2] 调亮度
$ adb shell settings put system screen_brightness 128

[Step 3] 看 HWC 状态
$ adb shell dumpsys SurfaceFlinger | grep -i "brightness"
# 看 HWC 是否接受 brightness

[Step 4] 看 Display HAL
$ adb shell dumpsys display | grep -i "brightness"

[Step 5] 修法
- 调 mode (manual / automatic)
- 检查 Display HAL capability
```

### 5.4 Case 4：foldable 屏切换失败

```
[症状] 折叠屏切换不工作

[Step 1] 看 display
$ adb shell dumpsys display
# 多个 display
# 0: 内屏
# 1: 外屏

[Step 2] 看 HWC 多 display
$ adb shell dumpsys SurfaceFlinger | grep "Display"
# 多个 display

[Step 3] 看 hotplug
$ adb logcat -d -b system | grep "hotplug"

[Step 4] 触发切换
$ adb shell input keyevent FOLD

[Step 5] 修法
- 检查 hotplug 实现
- 检查 Display HAL
- vendor 升级
```

### 5.5 Case 5：HDR 显示异常

```
[症状] HDR 不工作

[Step 1] 看 HDR capability
$ adb shell dumpsys SurfaceFlinger | grep "HDR"
# "HDR Capabilities: HDR10, HLG"

[Step 2] 看 display
$ adb shell dumpsys display | grep "hdr"

[Step 3] 看 HWC layer
# hdr layer 用 RGBA_1010102

[Step 4] 触发 HDR
# 播放 HDR 视频

[Step 5] 修法
- 启用 HDR
- 调 HWC layer config
- 检查 Display HAL
```

---

## 6. 5 大调优 case

### 6.1 Case 1：禁用 HWC

```bash
# 强制 GLES 合成（debug）
$ adb shell setprop debug.sf.disable_hwc 1
# 强制 SF 走 GLES

# 恢复 HWC
$ adb shell setprop debug.sf.disable_hwc 0
```

### 6.2 Case 2：启用严格 mode

```bash
# HWC 严格模式
$ adb shell setprop debug.hwc.strict_mode 1
# 严格检查 capability
```

### 6.3 Case 3：强制 60Hz

```bash
# 强制 60Hz
$ adb shell wm density 320
$ adb shell wm size 1080x1920
```

### 6.4 Case 4：禁用 GPU 合成

```bash
# 强制 HWC 合成
$ adb shell setprop debug.sf.disable_glcomposition 1
```

### 6.5 Case 5：HWC 调优参数

```bash
# HWC 调优
$ adb shell setprop debug.hwc.nodx 1
# 禁用 direct cross-display (foldable)

$ adb shell setprop debug.hwc.always_on 1
# 强制 HWC always on
```

---

## 7. oncall 5 分钟决策

```
[问题] HWC / Display 相关
  ↓
[1] 30 秒判断（5 秒）
  ├─ "黑屏" → 重启 SF
  ├─ "花屏" → dumpsys SurfaceFlinger
  ├─ "亮度错" → dumpsys display
  ├─ "foldable 错" → logcat hotplug
  └─ "HDR 错" → HWC HDR capability
  ↓
[2] 抓现场（30-60 秒）
  ├─ dumpsys SurfaceFlinger
  ├─ dumpsys display
  ├─ logcat -b system | grep HWC
  └─ 重启 SF / HWC
  ↓
[3] 5 分钟定位
  ├─ HWC 错 → vendor 升级
  ├─ Display HAL 错 → AOSP 升级
  ├─ 驱动错 → kernel / vendor 升级
  └─ 配置错 → 改 HWC config
  ↓
[4] 出报告（5 分钟）
```

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 图形栈总览](01-图形栈总览：app-WindowManager-SurfaceFlinger-HWC-Display.md) | 上篇 |
| [02 SurfaceFlinger 内部](02-SurfaceFlinger内部：合成-VSync-Layer树.md) | 上篇 |
| [03 BufferQueue](03-BufferQueue：跨进程图形缓冲机制.md) | 上篇 |
| [04 HWUI / RenderThread](04-HWUI-RenderThread：硬件加速渲染.md) | 上篇 |
| [05 Choreographer / VSync](05-Choreographer-VSync：UI节奏协调.md) | 上篇 |
| [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md) | 续篇 |
| [01-Mechanism/Kernel/Memory_Management](../../../01-Mechanism/Kernel/Memory_Management/) | kernel 层 |

---

## 9. 收官 + 自检

### 9.1 看完本文的自检

- [ ] 能说 HWC 4 大特性
- [ ] 能说 HWC 4 层架构
- [ ] 能说 4 大 HAL 接口
- [ ] 能说 4 大 HWC capability
- [ ] 能说 5 大合成类型 + 决策流程
- [ ] 知道 5 大实战 case 修法
- [ ] 知道 5 大调优 case

### 9.2 收官话

HWC 在图形栈里属于**"硬件抽象层"**——Display 硬件的 vendor 实现。

下一步推荐读：
- [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md) — 综合实战
- [04 HWUI / RenderThread](04-HWUI-RenderThread：硬件加速渲染.md) — 渲染回看
- [02 SurfaceFlinger 内部](02-SurfaceFlinger内部：合成-VSync-Layer树.md) — SF 回看

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
