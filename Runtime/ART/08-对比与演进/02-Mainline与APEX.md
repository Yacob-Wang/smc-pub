# 02-Mainline 与 APEX 演进：ART 从系统镜像到独立模块

> **本子模块**：08-对比与演进（横切对比 · 8/9）
> **本篇定位**：**横切对比 2/4**——ART Mainline 演进史、ART APEX 模块架构、独立更新机制、与 AOSP 升级的协同

---

## 1. 背景与定义：什么是 Mainline / APEX

### 1.1 一句话定义

**Mainline 是 Google 推出的 AOSP 模块化升级机制，把核心组件（ART / Conscrypt / DNS resolver 等）从系统镜像（system.img / vendor.img）剥离为独立可升级的 APEX 模块，让 Google 通过 Google Play Store / Play System Updates 推送模块更新，无需完整 OTA。**

### 1.2 为什么 ART 需要 Mainline

**传统 ART 部署的问题**：

```
┌────────────────────────────────────────────────────────────────┐
│ ART 在 Mainline 之前的部署方式                                    │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ART 集成在 system.img / vendor.img 中                            │
│    ↓                                                           │
│  ART 更新需要完整 OTA（system.img 升级）                          │
│    ↓                                                           │
│  OTA 推送周期：月度 / 季度（厂商决定）                            │
│    ↓                                                           │
│  ART 漏洞修复 / 性能优化 → 等 OTA 推送                            │
│    ↓                                                           │
│  平均延迟：30-90 天                                              │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**问题**：
- ART 性能优化（如 Generational CC GC）无法快速推送给用户
- ART 漏洞修复（如 JIT 编译器漏洞）延迟大
- 厂商定制 ART → 与 AOSP ART 分裂严重

**Mainline 解决方案**：

```
┌────────────────────────────────────────────────────────────────┐
│ Mainline ART 部署方式                                            │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ART 剥离为 com.android.runtime APEX 模块                          │
│    ↓                                                           │
│  APEX 模块独立存储（/apex/com.android.runtime/）                  │
│    ↓                                                           │
│  通过 Google Play System Updates 推送                              │
│    ↓                                                           │
│  推送周期：月度（Google 控制）                                    │
│    ↓                                                           │
│  ART 漏洞修复 / 性能优化 → 自动推送                               │
│    ↓                                                           │
│  平均延迟：7-30 天                                               │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 2. ART Mainline 演进史

### 2.1 关键时间节点

| 时间 | Android 版本 | Mainline 进展 |
| :--- | :--- | :--- |
| **2018** | Android 9 Pie | Project Treble + 模块化雏形 |
| **2019** | Android 10 Q | Mainline 模块化正式启动（首批 11 个模块） |
| **2020** | Android 11 R | ART 正式加入 Mainline（com.android.runtime APEX） |
| **2021** | Android 12 S | Generational CC GC 推送（通过 ART APEX） |
| **2022** | Android 13 T | ART 进一步模块化（拆分为 runtime + tzdata） |
| **2023** | Android 14 U | ART 持续迭代（性能优化 / 漏洞修复） |

### 2.2 ART Mainline 前的关键里程碑

- **Android 5.0（ART 替代 Dalvik）**
- **Android 7.0（JIT + AOT 混合模式）**
- **Android 9.0（Cloud Profile）**

### 2.3 ART Mainline 后的关键里程碑

- **Android 11（ART APEX 启动）**
- **Android 12（Generational CC GC）**
- **Android 14（持续优化）**

---

## 3. ART APEX 模块架构

### 3.1 ART APEX 文件结构

```
/apex/com.android.runtime/
├── apex_manifest.json                 ← APEX 元数据
├── payload/
│   ├── art/                           ← ART 核心
│   │   ├── oatexec                    ← dex2oat 工具
│   │   └── ...
│   ├── lib/                           ← Native 库
│   │   ├── libart.so
│   │   ├── libartbase.so
│   │   └── ...
│   └── ...
├── etc/                                ← 配置
└── ...
```

### 3.2 ART APEX 模块组成

| 模块 | 路径 | 角色 |
| :--- | :--- | :--- |
| **com.android.runtime** | `/apex/com.android.runtime/` | ART 运行时（libart.so 等） |
| **com.android.runtime.tzdata** | `/apex/com.android.tzdata/` | 时区数据 |

### 3.3 ART 在 APEX 中的关键变化

**Mainline 之前**：
```
/system/lib64/libart.so       ← ART 核心库
/system/framework/boot.art   ← 启动 Image
/system/framework/core-oj.jar ← Java 标准库
```

**Mainline 之后**：
```
/apex/com.android.runtime/lib64/libart.so  ← ART 核心库（移到 APEX）
/system/framework/core-oj.jar               ← Java 标准库（部分依赖 APEX）
/apex/com.android.runtime/javalib/core-oj.jar ← Java 标准库（APEX 中）
```

**关键设计**：
- **libart.so 移到 APEX** → ART 运行时独立更新
- **Java 标准库移到 APEX** → ART API 独立更新
- **Image 文件保留在 /system/** → 兼容性考虑（system.img 启动 Image）

---

## 4. ART APEX 启动流程

### 4.1 APEX 挂载流程

```
┌────────────────────────────────────────────────────────────────┐
│ ART APEX 启动挂载流程                                            │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  系统启动 init 阶段                                              │
│    ↓                                                           │
│  init 解析 /apex/com.android.runtime/apex_manifest.json          │
│    ↓                                                           │
│  apexd 守护进程挂载 APEX                                        │
│    ├─ loop 设备映射 /apex/com.android.runtime/                   │
│    ├─ bind mount 子目录（lib / javalib / etc）                   │
│    └─ 设置 LD_LIBRARY_PATH / BOOTCLASSPATH                      │
│    ↓                                                           │
│  Zygote 启动                                                     │
│    ↓                                                           │
│  app_process 加载 APEX 中的 libart.so                            │
│    ↓                                                           │
│  ART Runtime 初始化（同 [07-启动流程](../07-启动流程/)）          │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 4.2 ART 类加载路径（APEX 后）

```cpp
// frameworks/base/core/java/com/android/internal/os/ZygoteInit.java
private static void preloadClasses() {
    // Java 标准库路径（来自 APEX）
    String bootClasspath = System.getProperty("java.boot.class.path");
    // /apex/com.android.runtime/javalib/core-oj.jar
    // /apex/com.android.runtime/javalib/core-libart.jar
    // /apex/com.android.runtime/javalib/okhttp.jar
    // ...
    
    // 从这些路径加载类
}
```

---

## 5. Mainline 更新机制

### 5.1 Play System Updates 推送

```
┌────────────────────────────────────────────────────────────────┐
│ Play System Updates 推送 ART APEX                                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Google 内部                                                    │
│    ↓                                                           │
│  构建新 ART APEX（含新 GC / 性能优化）                            │
│    ↓                                                           │
│  上传到 Google Play                                              │
│    ↓                                                           │
│  Play System Updates 检测更新                                    │
│    ↓                                                           │
│  后台下载 ART APEX（~50MB）                                      │
│    ↓                                                           │
│  下次重启时验证 + 切换                                          │
│    ↓                                                           │
│  Zygote 重新启动（使用新 ART APEX）                               │
│    ↓                                                           │
│  App 进程重新 fork（继承新 ART）                                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 5.2 ART APEX 升级风险

**5 大升级风险**：

| 风险 | 影响 | 缓解 |
| :--- | :--- | :--- |
| **API 不兼容** | App 调用新 API 但旧 ART 没有 → 崩溃 | Google 通过 `@UnsupportedAppUsage` 标注 |
| **GC 行为变化** | 老 GC 调优参数失效 → OOM / 性能下降 | ART 兼容老 GC 配置 |
| **启动 Image 失效** | boot.art 与新 ART 不匹配 → 启动失败 | ART 自动重建 Image |
| **Native 库不兼容** | 旧 Native 库链接新 ART 符号 → 崩溃 | Google 控制 Native ABI |
| **回滚困难** | ART APEX 升级失败 → 需 OTA 回滚 | Play System 支持回滚 |

---

## 6. ART Mainline 对厂商 / 开发者的影响

### 6.1 对厂商的影响

**Mainline 前**：
- 厂商可以深度定制 ART（如 MTK / 三星的 ART 优化）
- ART 升级依赖厂商 OTA 推送

**Mainline 后**：
- ART 升级由 Google 控制，厂商定制空间减少
- 厂商必须适配 Google Mainline ART（不能深度 fork）

### 6.2 对 App 开发者的影响

**App 开发者现在依赖的 ART 能力**：
- ✅ ART API（@UnsupportedAppUsage 之外的 API）
- ✅ GC 行为（暂停时间）
- ✅ ART 性能（冷启动、JIT 等）
- ⚠️ Native ABI（必须兼容 Google Mainline ART 的符号）

### 6.3 对稳定性工程师的影响

**稳定性工程师必须关注**：
- **ART APEX 版本**：通过 `adb shell getprop ro.apex.com.android.runtime.version`
- **ART 行为变化**：每个 Android 版本 ART 行为可能变化（如 GC 选择）
- **兼容性测试**：App 必须在新版 ART 上测试

---

## 7. 实战案例：ART APEX 升级引发 OOM

**现象**：某 App 在 Android 13（ART Mainline v3）上 OOM，但在 Android 12（ART v2）上正常。

**根因**：
- ART v3 默认启用 Generational CC GC
- Generational CC GC 的 young gen 大小与 v2 不同
- App 在 v3 上 young gen 频繁 GC，但触发老年代晋升

**修复**：
- 适配 v3 的 GC 行为，调整年轻代对象创建策略
- 使用 `dumpsys meminfo` 对比两个版本的内存使用

---

## 8. 总结（架构师视角的 5 条 Takeaway）

1. **Mainline 是 ART 模块化的里程碑**——从 system.img 剥离为独立 APEX，Google 可独立更新 ART。**这是 Android 架构演进的重大变化**。
2. **ART APEX 升级延迟从 30-90 天缩短到 7-30 天**——漏洞修复 / 性能优化可以快速推送给用户。**移动场景的合理优化**。
3. **APEX 模块挂载需要 apexd 守护进程**——系统启动阶段必须正确挂载 ART APEX，否则所有 App 启动失败。
4. **Mainline 限制了厂商定制空间**——厂商不能再深度 fork ART。**这是 Google 收紧 Android 生态的举措**。
5. **稳定性工程师必须关注 ART APEX 版本**——不同 ART 版本行为可能差异巨大（如 GC 选择）。

---

## 附录 A：关键路径索引

| 路径 | 角色 |
| :--- | :--- |
| `/apex/com.android.runtime/` | ART APEX 模块路径 |
| `system/apex/com.android.runtime/` | ART APEX 源码路径 |
| `frameworks/base/core/java/com/android/internal/os/ZygoteInit.java` | Zygote 启动（APEX 后） |
| `system/core/apexd/` | apexd 守护进程 |

---

## 附录 B：Mainline 关键时间线

| 时间 | 事件 |
| :--- | :--- |
| 2018 | Treble 模块化启动 |
| 2019 | Mainline 11 个模块首发 |
| 2020 | ART 加入 Mainline |
| 2021 | Generational CC GC 推送 |
| 2024 | 持续迭代 |

---

## 9. 进阶实战：ART APEX 升级引发兼容性问题的 5 大场景

### 场景 1：Native 库 ABI 变化

**现象**：某 App 的 Native 库在 ART APEX 升级后崩溃。

**根因**：ART 升级时，可能引入新的 Native ABI（如新的 symbol）。Native 库链接旧 ABI，但运行时找不到对应符号。

**修复**：
- Native 库必须与 ART APEX 版本匹配
- 上线前在新 ART APEX 版本上跑完整测试

### 场景 2：GC 行为变化导致 OOM

**现象**：某 App 在 Android 13 升级 ART APEX 后 OOM 率上升。

**根因**：ART APEX v3 引入 Generational CC GC，年轻代划分变化。App 创建大量短期对象 → 频繁触发 minor GC → 老年代对象堆积 → OOM。

**修复**：
- 适配 Generational CC GC 的内存模型
- 减少短期对象创建，使用对象池
- 监控 GC 频率，调整年轻代大小（通过 `art -XX:GrowthLimit` 等）

### 场景 3：启动 Image 重建失败

**现象**：App 启动时卡死，logcat 显示 "Failed to load image"。

**根因**：ART APEX 升级后，boot.art 与新 ART 不匹配，但 ART 自动重建 Image 失败（磁盘空间不足 / OOM）。

**修复**：
- 清理磁盘空间
- 增加启动期内存（修改 dalvik.vm.heapsize）
- 强制重新 dexopt

### 场景 4：API 行为变化（新增弃用）

**现象**：App 调用 ART 内部 API，升级 ART APEX 后 API 被弃用。

**修复**：
- 避免使用 ART 内部 API（用 @UnsupportedAppUsage 标注）
- 升级 App 用标准 ART API

### 场景 5：ART APEX 升级失败回滚

**现象**：ART APEX 升级失败，设备卡在 boot 阶段。

**应急**：
- 进入 recovery 模式
- 卸载 ART APEX：`pm uninstall-system-updates com.android.runtime`
- 重启系统

---

## 10. ART APEX 版本兼容性矩阵

| ART APEX 版本 | Android 版本 | 主要变化 | 兼容性风险 |
| :--- | :--- | :--- | :--- |
| **v1** | Android 11 | 初始 ART APEX | 厂商适配 |
| **v2** | Android 12 | Generational CC GC | GC 行为变化 |
| **v3** | Android 13 | 进一步优化 | Native ABI 变化 |
| **v4** | Android 14 | 持续优化 | 持续适配 |

---

## 11. 总结（架构师视角的 5 条 Takeaway）

1. **Mainline 是 ART 模块化的里程碑**——从 system.img 剥离为独立 APEX，Google 可独立更新 ART。**这是 Android 架构演进的重大变化**。
2. **ART APEX 升级延迟从 30-90 天缩短到 7-30 天**——漏洞修复 / 性能优化可以快速推送给用户。**移动场景的合理优化**。
3. **APEX 模块挂载需要 apexd 守护进程**——系统启动阶段必须正确挂载 ART APEX，否则所有 App 启动失败。
4. **Mainline 限制了厂商定制空间**——厂商不能再深度 fork ART。**这是 Google 收紧 Android 生态的举措**。
5. **稳定性工程师必须关注 ART APEX 版本**——不同 ART 版本行为可能差异巨大（如 GC 选择）。

---

## 附录 C：量化自检表

| # | 量化描述 | 数量级 |
| :-- | :--- | :--- |
| 1 | ART APEX 模块大小 | ~50MB |
| 2 | 升级延迟（Mainline 前） | 30-90 天 |
| 3 | 升级延迟（Mainline 后） | 7-30 天 |
| 4 | APEX 挂载耗时 | ~200ms |
| 5 | Boot Image 重建耗时 | 30s-5min |
| 6 | Generational CC GC 暂停 | < 2ms（99th） |
| 7 | Android 14 ART APEX 版本 | v4 |
| 8 | Android 12 ART APEX 版本 | v2 |

---

## 附录 D：工程基线表

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
| :--- | :--- | :--- | :--- |
| ART APEX 版本 | 跟随 AOSP | — | 厂商深度定制失效 |
| 升级策略 | 自动 Play System Updates | — | 必须 OTA 才行 |
| 升级失败回滚 | 系统自动 | — | recovery 模式可手动回滚 |
| Native ABI | 与 ART 同步 | — | ABI 不匹配会崩溃 |
| GC 类型 | Generational CC (Android 12+) | — | 老 App 可能行为变化 |
| Boot Image | /system/framework/ | — | ART 升级后重建 |
| boot.art 路径 | /system/framework/boot.art | — | 与 ART APEX 版本匹配 |

---

## 附录 E：Mainline 模块化全景

| 模块名 | 大小 | 用途 |
| :--- | :--- | :--- |
| **com.android.runtime** | ~50MB | ART 运行时 |
| **com.android.runtime.tzdata** | ~1MB | 时区数据 |
| **com.android.adbd** | ~5MB | adb 守护进程 |
| **com.android.art** | 集成在 runtime | ART 内部组件（部分） |
| **com.android.conscrypt** | ~3MB | TLS 实现 |
| **com.android.dnsresolver** | ~2MB | DNS 解析 |
| **com.android.documentsui** | ~5MB | 文档 UI |
| **com.android.media** | ~10MB | 多媒体 |
| **com.android.media.swcodec** | ~5MB | 软件编解码 |
| **com.android.networkstack** | ~10MB | 网络栈 |
| **com.android.permission** | ~3MB | 权限控制 |
| **com.android.sdkext** | ~2MB | SDK 扩展 |
| **com.android.tzdata** | ~1MB | 时区数据（旧） |

> ART APEX（com.android.runtime）是最大的 Mainline 模块。

---

## 附录 F：稳定性架构师视角的 Mainline 影响

### F.1 正面影响

1. **更快修复 ART 漏洞**——ART 0-day 漏洞可通过 Play System Updates 快速推送修复，无需等 OTA
2. **更快推送 ART 性能优化**——Generational CC GC、新 JIT 优化可快速下发
3. **更一致的行为**——所有厂商设备使用相同的 ART 行为，App 兼容性测试覆盖更完整

### F.2 负面影响

1. **厂商定制空间减少**——厂商不能再深度 fork ART（如 MTK 的 ART 优化）
2. **App 测试覆盖要更广**——多个 ART APEX 版本需测试
3. **Native ABI 风险**——ART 升级可能引入 Native ABI 变化

### F.3 稳定性架构师行动清单

- [ ] 监控 ART APEX 版本（`getprop ro.apex.com.android.runtime.version`）
- [ ] 在新 ART APEX 版本上跑兼容性测试
- [ ] 关注 ART 升级 changelog（`cs.android.com`）
- [ ] Native 库与 ART 同步升级
- [ ] 不要深度依赖 ART 内部 API（用 @UnsupportedAppUsage 标注的）

### F.4 ART APEX vs 系统镜像：核心差异对比

| 维度 | 系统镜像（system.img） | ART APEX |
| :--- | :--- | :--- |
| **存储位置** | /system/lib64/libart.so | /apex/com.android.runtime/lib64/libart.so |
| **升级路径** | OTA 推送 | Play System Updates |
| **升级延迟** | 30-90 天 | 7-30 天 |
| **厂商可控** | ✅ 深度定制 | ❌ Google 控制 |
| **挂载时机** | 系统启动自动 | apexd 守护进程 |
| **ABI 一致性** | 系统镜像版本绑定 | ART APEX 版本绑定 |
| **回滚支持** | OTA 回滚 | 自动回滚 + recovery |
| **App 感知** | 几乎无感 | 通过 getprop 查询 |

### F.5 ART APEX 升级检查清单

```
ART APEX 升级前必查项：
1. ART 版本（ro.apex.com.android.runtime.version）
2. Native ABI（adb shell getprop ro.product.cpu.abi）
3. 厂商是否支持（部分厂商屏蔽 Play System Updates）
4. 设备剩余空间（ART APEX 升级需要 ~100MB 临时空间）
5. ART Profile 是否需要更新（profile_expiry 时间）
6. App 兼容性测试结果（新 ART APEX 跑回归测试）

ART APEX 升级后必查项：
1. App 启动时间（am start -W）
2. App 内存使用（dumpsys meminfo）
3. App 崩溃率（Crashlytics）
4. ART GC 行为（Perfetto）
5. ART 性能（JIT / AOT 命中情况）
```

---

## 附录 G：稳定性工程师视角的 ART APEX 升级 SOP

### SOP 1：ART APEX 版本查询

```bash
# 方式 1：通过 getprop
adb shell getprop ro.apex.com.android.runtime.version

# 方式 2：通过 cmd package
adb shell cmd package list packages -f com.android.runtime

# 方式 3：通过 dumpsys
adb shell dumpsys package com.android.runtime | grep -i version
```

### SOP 2：ART APEX 升级强制触发

```bash
# 强制检查 ART APEX 更新
adb shell cmd package check-update com.android.runtime

# 强制下载 ART APEX
adb shell cmd package download com.android.runtime

# 强制安装 ART APEX（需要重启）
adb shell cmd package install com.android.runtime
```

### SOP 3：ART APEX 回滚

```bash
# 进入 recovery 模式
adb reboot recovery

# 卸载 ART APEX（恢复 system.img 中的旧版本）
adb shell pm uninstall-system-updates com.android.runtime

# 重启
adb reboot
```

### SOP 4：ART APEX 日志收集

```bash
# 启用 APEX 详细日志
adb shell setprop log.tag.APEXD VERBOSE

# 抓取 ART APEX 升级日志
adb logcat -d -s "APEXD:*" "art:*" > apex_upgrade.log
```

---

> **下一篇**：[03-Hook 框架与 ART 的兼容性](03-Hook框架与ART.md) 将深入 Hook 框架（Epic / SandHook / Pine）实现原理 + ART CC GC 读屏障对 Hook 的影响 + ART Hook 三种流派 + 稳定性影响。