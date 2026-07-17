# 8.5 GC × APEX 模块

> **本节回答一个根本问题**：Android Mainline（APEX）模块怎么影响 GC？com.android.art 模块升级后 GC 行为变化是什么？
>
> **答案**：**com.android.art 模块通过 APEX 升级，包含 ART 运行时 + GC 行为**——App 进程 fork 自新版本 Zygote。

---

## 一、Android Mainline 概述

### 8.5.1 Android Mainline 的定义

```
Android Mainline：

- Android 10+ 引入
- 把系统组件模块化（APEX 格式）
- 通过 Google Play 系统更新升级
- 不需要完整 OTA

主要 Mainline 模块：
- com.android.art（ART 运行时）
- com.android.conscrypt（TLS）
- com.android.tzdata（时区）
- com.android.adbd（ADB）
- ...
```

### 8.5.2 com.android.art 模块

```
com.android.art 模块：

- 包含 ART 运行时（libart.so）
- 包含 GC 算法实现
- 包含 Zygote 和 dex2oat
- 通过 Google Play 系统更新升级
- App 进程 fork 自最新版本
```

### 8.5.3 APEX 模块的工程价值

```
APEX 模块的优势：

1. 独立升级
   - 修复 ART bug 不需要 OTA
   - 通过 Google Play 推送
   - 用户无感知

2. A/B 测试
   - 新版本可以小范围测试
   - 验证后再推送

3. 灰度发布
   - 按地区 / 设备类型灰度
   - 监控后全量推送
```

---

## 二、com.android.art 模块的 GC 行为

### 8.5.4 ART 模块的版本演进

| 模块版本 | ART 版本 | 关键 GC 变更 |
|:---|:---|:---|
| com.android.art 1.0 | ART 10 | GenCC 引入 |
| com.android.art 1.1 | ART 11 | Card Table 优化 |
| com.android.art 1.2 | ART 12 | rbcc 优化 |
| com.android.art 1.3 | ART 13 | JIT 代码校验 |
| com.android.art 1.4 | ART 14 | 细粒度卡表 |

### 8.5.5 模块升级对 GC 的影响

```
com.android.art 模块升级对 GC 的影响：

1. STW 时间
   - 新版本可能优化 STW
   - 也可能引入新 bug

2. 堆大小
   - 模块升级后默认参数可能变
   - 例如 heaptargetutilization 默认值

3. GC 算法
   - 新版本可能改用新算法
   - 例如从 GenCC 升级到 rbcc 增强

4. 行为兼容
   - App 应该用 ART 公开 API
   - 避免依赖内部实现
```

### 8.5.6 模块升级的兼容性问题

```
模块升级的兼容性问题：

1. ART 内部 API 变更
   - ART 13+ 移除了一些内部 API
   - Hook 框架需要适配

2. GC 默认参数变更
   - ART 12+ 默认启用 rbcc
   - App 可能出现新的兼容性问题

3. 模块加载顺序
   - com.android.art 与 App 的 dex2oat 结果可能不匹配
   - 需要重新编译
```

---

## 三、APEX 模块的工程影响

### 8.5.7 App 的适配

```xml
<!-- AndroidManifest.xml 声明 ART 模块依赖 -->
<uses-feature android:name="android.hardware.ram.normal"/>

<!-- 适配 APEX 模块 -->
<application
    android:largeHeap="false"
    android:hardwareAccelerated="true">
    <!-- App 应在 APEX 模块更新后验证 -->
</application>
```

### 8.5.8 App 测试策略

```
App 在 APEX 模块更新后的测试策略：

1. 兼容性测试
   - 在最新 ART 版本上测试
   - 验证 GC 行为
   - 验证性能

2. 回归测试
   - 关键场景（启动 / 滑动 / 切后台）
   - 内存使用
   - 卡顿率

3. 灰度发布
   - 1% 用户
   - 监控 APM 指标
   - 异常立即回滚
```

### 8.5.9 ART 模块升级的监控

```bash
# 1. 查看 ART 模块版本
adb shell dumpsys package com.android.art | grep versionName

# 2. 查看 ART 版本
adb shell getprop ro.build.version.sdk

# 3. 查看 GC 算法
adb shell getprop dalvik.vm.gctype
```

### 8.5.10 APM 监控 ART 模块升级

```java
public class ArtModuleMonitor {
    @Scheduled(fixedRate = 3600000)  // 1 小时
    public void monitor() {
        // 1. 获取 ART 模块版本
        String artVersion = getArtModuleVersion();
        apmClient.report("art.module.version", artVersion);
        
        // 2. 与之前版本对比
        if (!artVersion.equals(lastArtVersion_)) {
            // 3. ART 模块升级，触发监控
            apmClient.alert("art.module.upgraded", "ART upgraded to " + artVersion);
            lastArtVersion_ = artVersion;
            
            // 4. 监控 GC 行为变化
            monitorGcBehaviorAfterUpgrade();
        }
    }
}
```

---

## 四、ART 模块升级的工程实践

### 8.5.11 ART 升级前的准备

```
ART 升级前的准备：

1. 阅读 ART Release Notes
   - 关注 GC 相关变更
   - 关注行为兼容性

2. 测试 ART 公开 API
   - 用 ART 公开 API（不是 internal）
   - 避免依赖未公开的内部行为

3. 准备灰度方案
   - 1% → 10% → 50% → 100%
   - 监控关键指标
```

### 8.5.12 ART 升级后的监控

```
ART 升级后的监控：

1. 监控 GC 频率
   - kGcCauseForAlloc 频率
   - 后台 GC 频率

2. 监控 STW 时间
   - Minor GC STW
   - Major GC STW

3. 监控内存使用
   - Native Heap / Dalvik Heap
   - JNI Ref 数量

4. 监控崩溃率
   - 整体崩溃率
   - GC 相关崩溃
```

### 8.5.13 ART 升级的回滚

```
ART 升级的回滚策略：

1. 自动回滚
   - ART 模块升级后监控异常
   - 崩溃率 > 阈值 → 自动回滚

2. 手动回滚
   - 关键场景卡顿
   - 内存泄漏
   - 性能下降

3. 回滚到哪个版本
   - 上一稳定版本
   - 上一个 LTS 版本
```

---

## 五、APEX 模块的源码索引

### 8.5.14 核心源码路径

```
system/core/libartpalette/             # ART 模块配置
system/apex/com.android.art/         # com.android.art 模块
frameworks/base/core/java/android/app/Application.java # App 适配
```

### 8.5.15 ART 模块的相关命令

```bash
# 1. 查看 APEX 模块
adb shell cmd apd list

# 2. 查看 ART 模块版本
adb shell dumpsys package com.android.art

# 3. 查看 ART 详细信息
adb shell cmd art --help
```

---

## 六、本节小结

1. **com.android.art 是 Android Mainline 模块**：通过 Google Play 系统更新
2. **ART 模块升级影响 GC 行为**：算法 / 参数 / 行为
3. **App 应使用 ART 公开 API**：避免依赖内部行为
4. **ART 模块升级后需要测试**：兼容性 + 性能
5. **APM 监控 ART 模块版本**：异常告警

→ **理解 ART 模块升级，就理解了"为什么 ART 升级可能影响 App GC 行为"**。

---

## 跨节引用

**本节被以下章节引用**：
- 09 篇诊断 —— ART 版本与 GC 行为

**本节引用**：
- 04/05 篇 —— ART GC 算法
- Android_Framework 的相关模块
