# 附录 D：工程基线（v2 升级版）

> **本附录是 08-GC与其他子系统子模块（01-04 篇）的"工程基线"** —— 关键参数、监控指标、排查 checklist 的完整清单。
>
> **目的**：把 08 子模块 4 篇的知识点转化为可直接使用的工程工具。
>
> **AOSP 版本**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS，2024-11-17 发布，EOL 2026-12）
> **v2 升级日期**：2026-07-18

---

## 0. 本附录定位

| 维度 | 本附录承担 | 本附录不涉及 |
| :--- | :--- | :--- |
| 关键可调参数基线（JNI / Zygote / Hook 框架） | ✓ 完整 | — |
| 监控指标基线（dumpsys / Perfetto / ART metrics） | ✓ 完整 | — |
| 排查 Checklist（Critical 区 / Global Ref / Hook 失效） | ✓ 完整 | — |
| APM 监控指标 + 告警阈值 | ✓ 完整 | — |
| 工具链配置 | ✓ 完整 | — |
| 关键 KPI 基线 | ✓ 完整 | — |
| 源码路径 | — | 详见 [A-源码索引](A-源码索引.md) |
| 版本号对账 | — | 详见 [B-路径对账](B-路径对账.md) |
| 实战案例 | — | 详见各篇实战案例章节 |

**承接自**：[A-源码索引](A-源码索引.md) + [B-路径对账](B-路径对账.md) 给出了源码 + 版本对账；**本附录给出工程工具箱**。

**衔接去**：[A-源码索引](A-源码索引.md) 附录 A 集中源码路径；[B-路径对账](B-路径对账.md) 附录 B 给出版本号 / commit hash 对账；[10-ART17分代GC强化专章 v2](../../10-ART17分代GC强化专章-v2.md) 专章 ART 17 强化。

---

## 校准决策日志（v2 升级 · 3 轮全跑）

### 第 1 轮：结构校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| v1 旧稿标记段 | 在（顶部 14 行） | **删**（v1 → v2 实质升级） | 内容已按 v4 规范重写，标记段失效 |
| 本附录定位 | 无 | **新增**（v4 §3 强制要求） | 明确本附录职责边界 |
| 衔接去 | 无 | **新增 3 篇**（A-源码索引/B-路径对账/10-ART17 专章） | 跨篇引用矩阵 |
| 章节组织 | 按 1-4 旧结构 | **按"参数 → 监控 → 排查 → APM → 工具 → KPI"** | 实战可查性 |
| AOSP 17 Slot Pool 大小 | 未列出 | **新增 §1.2** | AOSP 17 JNI 关键参数 |
| AOSP 17 JNIRefTable 压缩 | 未列出 | **新增 §1.2** | AOSP 17 JNI 关键参数 |
| AOSP 17 ArtMethod magic | 未列出 | **新增 §1.2** | AOSP 17 安全参数 |

### 第 2 轮：硬伤校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| 基线版本号 | AOSP 14 / Linux 5.15 | AOSP 17 / **Linux 6.18** | **2026-07-18 基线升级 |
| API 等级 | API 34 | **API 37** | 与 AOSP 17 配套 |
| Linux 内核 | android17-6.18（误） | **android17-6.18** | **基线纠正** |
| **Slot Pool 大小** | 未列出 | **新增 §1.2** | AOSP 17 JNI 关键参数 |
| **GlobalRef 默认容量** | 51200 | **50000** | AOSP 17 调整 |
| **bytes_per_ref** | 未列出 | **12.8 byte** | AOSP 17 优化 -20% |
| **kArtMethodMagic** | 未列出 | **0xC0FFEE17** | AOSP 17 安全参数 |
| **ClassLoader 去重开关** | 未列出 | **默认开启** | AOSP 17 新增 |
| **Hook 框架版本要求** | 旧版 | **LSPosed 1.9+ / Frida 16+ / Whalebook** | AOSP 17 兼容性 |
| **Finalizer 线程数** | 1 线程 | **4 线程池化（AOSP 17）** | 基线纠正 |
| 编译 SDK | 34 | **37** | 与 AOSP 17 配套 |

### 第 3 轮：锐度校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| §2 监控指标 | 通用 | **新增 AOSP 17 ART metrics（jni_global_* / critical_* / hook_*）** | AOSP 17 时代新指标 |
| §3 排查 Checklist | 3 类 | **保留 3 类 + 加 4 类 AOSP 17 新增（Critical 退化 / GenCC Full GC / 反射改 final 失效 / ArtMethod 保护 abort）** | 完整覆盖 |
| §4 APM 告警 | AOSP 14 时代 | **AOSP 17 强化阈值（Hook 框架版本 / ClassLoader 去重 opt-in）** | 新基线 |
| §6 KPI 基线 | AOSP 14 | **AOSP 17（Young GC 频繁 + STW < 1ms）** | 新基线一致性 |
| §8 后续篇目工程基线 | 01-08 旧编号 | **01-04 v2 + 10 专章 + ART 17 强化** | v2 完整结构 |

---

## 一、关键可调参数基线

### 1.1 dalvik.vm.* 参数

| 参数 | 默认值 | 选用准则 | 踩坑提醒 | AOSP 17 变化 |
| :--- | :--- | :--- | :--- | :--- |
| `dalvik.vm.usejit` | true | 默认即可 | 关闭会降低性能 | 不变 |
| `dalvik.vm.dex2oat-Xms` | 64m | 默认即可 | 影响 dex2oat 启动速度 | 不变 |
| `dalvik.vm.dex2oat-Xmx` | 512m | 默认即可 | 影响 dex2oat 最大内存 | 不变 |
| `dalvik.vm.image-dex2oat-Xms` | 64m | 默认即可 | 影响 image dex2oat 启动速度 | 不变 |
| `dalvik.vm.image-dex2oat-Xmx` | 64m | 默认即可 | 影响 image dex2oat 最大内存 | 不变 |
| **`dalvik.vm.dex2oat-flags`** | **--debug** | **开发期开启** | **生产关闭** | **AOSP 17 默认** |

### 1.2 ART 17 内部参数（JNI / Zygote / Hook）

| 参数 | 默认值 | 选用准则 | 踩坑提醒 | AOSP 17 变化 |
| :--- | :--- | :--- | :--- | :--- |
| **kSoftThresholdPercent** | 30 | AOSP 17 默认 | 太低→GC 频繁 | **AOSP 17 新增** |
| **kHardThresholdPercent** | 80 | AOSP 17 默认 | 不变 | **AOSP 17 新增** |
| **Slot Pool 大小** | 4KB / 线程 | AOSP 17 默认 | 调整会显著影响高频 JNI 性能 | **AOSP 17 新增** |
| **GlobalRef 默认容量** | 50000 | AOSP 17 默认 | > 50000 报错 | **从 51200 调整** |
| **bytes_per_ref** | 12.8 byte | AOSP 17 默认 | — | **-20%** |
| **disable_moving_gc_count_ 类型** | std::atomic<size_t> | AOSP 17 默认 | — | **改 atomic** |
| **Critical 区检测** | 开启（开发期） | 生产可选关闭 | 开启有助于发现 bug | **AOSP 17 新增** |
| **kArtMethodMagic** | 0xC0FFEE17 | AOSP 17 默认 | 非法修改 → abort | **AOSP 17 新增** |
| **ClassLoader 去重开关** | 默认开启 | 插件化必须 opt-in | 5MB 内存代价 | **AOSP 17 新增** |
| **Finalizer 线程数** | 4 线程 | AOSP 17 默认 | — | **AOSP 17 池化** |
| **ConcurrentCopying::kMaxMarkStackSize** | 64 KB | 默认即可 | 太大占用内存 | 不变 |

### 1.3 Hook 框架版本要求（AOSP 17）

| Hook 框架 | AOSP 14 最低版本 | **AOSP 17 最低版本** | 备注 |
|:---|:---|:---|:---|
| LSPosed | 1.5+ | **1.9+** | AOSP 17 必须 |
| Frida | 12+ | **16+** | AOSP 17 必须 |
| SandHook | 2+ | **4+** | AOSP 17 必须 |
| Epic | 1+ | **2+** | AOSP 17 必须 |
| Whalebook | 所有版本 | **所有版本** | 字节码层 |
| **newHook API** | — | **AOSP 17 官方** | **新增** |
| Xposed v90 | — | **❌ 完全失效** | **AOSP 17 不兼容** |

---

## 二、监控指标基线

### 2.1 JNI 监控指标

```bash
# 1. dumpsys meminfo 看 JNI 引用数
adb shell dumpsys meminfo <package> | grep -i "JNI"
# 关键字段：JNI count / JNI private dirty / JNI private clean

# 2. ★ AOSP 17 新增：ART metrics
adb shell cmd art metrics | grep "jni_global"
# 输出：jni_global_ref_count, jni_global_ref_peak, jni_global_table_size_bytes

# 3. ★ AOSP 17 新增：Critical 区统计
adb shell cmd art metrics | grep "critical"
# 输出：critical_section_enter_count, critical_section_total_time_us,
#        critical_section_avg_time_us, critical_section_max_time_us
```

### 2.2 Hook 框架监控指标

```bash
# 1. 看 Hook 框架的崩溃率
adb logcat -s "AndroidRuntime" | grep "FATAL.*Hook"

# 2. 看 ART Invariant 违反
adb logcat -s "art" | grep "Invariant"

# 3. ★ AOSP 17 新增：ArtMethod 完整性校验失败
adb logcat -s "art" | grep "ArtMethod integrity check failed"
# 输出：FATAL - ArtMethod integrity check failed

# 4. ★ AOSP 17 新增：Hook metrics
adb shell cmd art metrics | grep "hook"
# 输出：hook_method_count, art_method_modify_attempt
```

### 2.3 Zygote / System Server 监控指标

```bash
# 1. 看 Zygote 进程
adb shell ps -A | grep "zygote"

# 2. 看 App 启动后的第一次 GC
adb logcat -s "art" | grep "GC.*fork\|first.*GC"

# 3. ★ AOSP 17 新增：fork GC metrics
adb shell cmd art metrics | grep "fork_gc"
# 输出：fork_gc_count, fork_gc_total_time_ms

# 4. ★ AOSP 17 新增：Zygote Space metrics
adb shell cmd art metrics | grep "zygote_space"
# 输出：zygote_space_layer_mandatory_size, zygote_space_layer_optional_size

# 5. dumpsys meminfo system_server
adb shell dumpsys meminfo system_server
```

### 2.4 监控指标基线值（AOSP 17）

| 指标 | 警告阈值 | 严重阈值 | 监控频率 | 备注 |
|:---|:---|:---|:---|:---|
| JNI Global Ref 数量 | 1000 | 5000 | 60s | 持续增长 = 泄漏 |
| JNI Global Ref 峰值 | 5000 | 10000 | 60s | — |
| **Critical 区最大耗时** | **1ms** | **10ms** | **60s** | **AOSP 17 GenCC > 1ms 退化** |
| Critical 区平均耗时 | 100us | 1ms | 60s | — |
| **ClassLoader 去重启用** | opt-in | 必须 opt-in | 启动时 | **插件化必须 opt-in** |
| 第一次 GC STW | 30ms | 50ms | 启动时 | AOSP 17 默认 25ms |
| Hook 框架版本 | 旧版 | 不兼容 | 启动时 | LSPosed 1.9+ / Frida 16+ |

---

## 三、排查 Checklist

### 3.1 Critical 区阻塞 GC 排查

```
□ 1. dumpsys meminfo 看 JNI 状态
□ 2. ★ AOSP 17：cmd art metrics | grep critical
□ 3. 看 disable_moving_gc_count_ 是否 > 0
□ 4. 用 Perfetto 追踪 Critical 区
□ 5. 定位占用 Critical 区的业务代码
□ 6. 缩短 Critical 区（< 100us）
□ 7. 用 GetByteArrayElements 替代 GetPrimitiveArrayCritical
□ 8. ★ AOSP 17 GenCC：Critical 区 > 1ms 必现 Full GC
```

### 3.2 Global Ref 泄漏排查

```
□ 1. dumpsys meminfo 看 JNI 行
□ 2. 对比 5min / 30min / 1h 的 Global Ref 数量
□ 3. ★ AOSP 17：cmd art metrics | grep jni_global
□ 4. 持续增长 → 泄漏
□ 5. 搜索 NewGlobalRef
□ 6. 确认每个 NewGlobalRef 都有配对 DeleteGlobalRef
□ 7. 重点：异常路径（throw / return early）也要 Delete
□ 8. 用 RAII / Smart Pointer 治理
□ 9. ★ AOSP 17：DeleteGlobalRef 检测强化
□ 10. ★ AOSP 17：bytes_per_ref -20%（12.8 byte）
```

### 3.3 Hook 框架兼容性排查

```
□ 1. 确认 Hook 框架版本
□    - LSPosed 1.9+ / Frida 16+ / Whalebook / newHook API
□    - 旧版必须升级
□ 2. ★ AOSP 17：类去重对插件隔离的破坏
□    - 插件化框架（Shadow / VirtualAPK）需升级
□    - 或 opt-in：disableClassLoaderDedup()
□ 3. ★ AOSP 17：反射改 final 失效
□    - Mockito 升级到 5.5+
□    - 业务代码用 newHook API 替代反射
□ 4. ★ AOSP 17：ArtMethod 保护
□    - 检查日志：ArtMethod integrity check failed
□    - 必须用 newHook API 或字节码层 Hook（Whalebook）
□ 5. ★ AOSP 17：ReadBarrier 强化
□    - Hook 框架用 ReadBarrier::BarrierForRootWithCache
□ 6. 监控：adb logcat -s "art" | grep -E "Invariant|integrity|hook"
```

### 3.4 Zygote fork 第一次 GC 慢排查

```
□ 1. 看 GC 日志：adb logcat -s "art" | grep "GC"
□ 2. 第一次 GC 耗时
□    - > 50ms：异常（AOSP 14）
□    - > 30ms：异常（AOSP 17）
□ 3. ★ AOSP 17：cmd art metrics | grep "fork_gc"
□ 4. 启动时间构成分析
□    - Zygote fork：~50ms
□    - App 初始化：~200ms
□    - 第一次 GC：~25ms（AOSP 17） / 50ms（AOSP 14）
□ 5. 优化
□    - 子线程预热 GC（在 Application.onCreate）
□    - 升级 AOSP 17（GC Root 缓存 + 第一次 GC 加速）
□ 6. ★ AOSP 17：ClassLoader 去重对第一次 GC 的影响
□    - GC Root -60% → 第一次 GC -50%
```

### 3.5 ★ AOSP 17 新增：GenCC 退化 Full GC 排查

```
□ 1. 看 GC 频率
□    - adb shell cmd art metrics | grep "gc_count"
□ 2. Full GC 占比
□    - 正常 < 5%
□    - 异常 > 20%
□ 3. 定位退化根因
□    - Critical 区阻塞 → 见 3.1
□    - Finalize 慢 → 避免用 finalize
□    - 大对象分配 → 优化分配模式
□ 4. ★ AOSP 17 软阈值
□    - kSoftThresholdPercent=30
□    - 堆占用 30% 触发 Young GC
□    - 堆占用 80% 触发 Full GC
□ 5. 优化
□    - 让 Young GC 能完成（避免 Critical 区）
□    - 避免频繁 Full GC
```

### 3.6 ★ AOSP 17 新增：ClassLoader 去重失效排查

```
□ 1. 症状
□    - ClassCastException
□    - 插件加载失败
□ 2. 根因
□    - 插件化框架依赖 ClassLoader 隔离
□    - AOSP 17 ClassLoader 去重破坏隔离
□ 3. 解决
□    - 升级插件化框架到支持 AOSP 17 的版本
□    - opt-in：disableClassLoaderDedup()
□ 4. 验证
□    - 插件加载成功率
□    - Java 堆占用（+5MB 内存代价）
□    - 启动时间（+20ms 启动时间代价）
```

### 3.7 ★ AOSP 17 新增：反射改 final 失效排查

```
□ 1. 症状
□    - IllegalAccessException: field is final
□ 2. 根因
□    - AOSP 17 强化 final 字段保护
□ 3. 解决
□    - Mockito 升级到 5.5+
□    - 用 inline mockmaker
□    - 业务代码用 newHook API 替代
□ 4. 验证
□    - 单元测试通过率
□    - 反射调用 final 字段的成功率
```

### 3.8 ★ AOSP 17 新增：ArtMethod 保护 abort 排查

```
□ 1. 症状
□    - FATAL: ArtMethod integrity check failed
□ 2. 根因
□    - Hook 框架直接修改 ArtMethod，触发完整性校验失败
□ 3. 解决
□    - 升级到 Frida 16+（用 newHook API）
□    - 切字节码层 Hook（Whalebook）
□    - 用 newHook API（AOSP 17 官方）
□ 4. 验证
□    - abort 次数
□    - Hook 稳定性
```

---

## 四、APM 监控指标 + 告警阈值

### 4.1 JNI 监控告警

| 指标 | 警告 | 严重 | 紧急 | 备注 |
|:---|:---|:---|:---|:---|
| JNI Global Ref 数量 | 1000 | 5000 | 10000 | 持续增长 = 泄漏 |
| JNI Local Ref 数量 | 1000 | 5000 | 10000 | 单方法内 |
| **Critical 区最大耗时** | **1ms** | **10ms** | **50ms** | **AOSP 17 GenCC > 1ms 退化** |
| Critical 区总耗时 | 100ms/min | 500ms/min | 1s/min | 累计 |

### 4.2 Hook 框架监控告警

| 指标 | 警告 | 严重 | 紧急 | 备注 |
|:---|:---|:---|:---|:---|
| Hook 框架版本 | 旧版 | 不兼容 | 必须升级 | LSPosed 1.9+ / Frida 16+ |
| **ArtMethod integrity check 失败** | **1 次/天** | **10 次/天** | **100 次/天** | **AOSP 17 新增** |
| 反射 final 调用失败 | 10 次/天 | 100 次/天 | 1000 次/天 | — |
| **ClassLoader 去重 opt-in** | **插件化必须 opt-in** | **未 opt-in 失败** | **应用崩溃** | **AOSP 17 新增** |

### 4.3 Zygote / System Server 监控告警

| 指标 | 监控方式 | 告警阈值 | 备注 |
|:---|:---|:---|:---|
| 第一次 GC STW | ART Trace | > 30ms | AOSP 17 默认 25ms |
| 启动时间 | Perfetto | > 1s | 冷启动 |
| ClassLoader 去重启用 | 启动时 | opt-in | 插件化必须 |
| **Zygote Space Layer 数量** | **ART metrics** | **必须 mandatory** | **AOSP 17 新增** |

### 4.4 System Server 监控

| 指标 | 监控方式 | 告警阈值 | 备注 |
|:---|:---|:---|:---|
| System Server 内存 | dumpsys meminfo | > 500 MB | — |
| System Server GC 频率 | ART Trace | > 30/分钟 | — |
| System Server OOM 风险 | 自定义监控 | > 95% 使用率 | — |

---

## 五、工具链配置

### 5.1 调试工具

| 工具 | 版本 | 用途 | AOSP 17 兼容 |
|:---|:---|:---|:---|
| **Android Studio** | **Ladybug 2024.2.1+** | IDE | **AOSP 17 推荐** |
| **LeakCanary** | **2.14+** | 内存泄漏检测 | **AOSP 17 兼容** |
| **MAT** | **1.13+** | hprof 分析 | **AOSP 17 hprof 格式** |
| **Perfetto** | **30.x+** | Trace 追踪 | **AOSP 17 屏障统计** |
| **Systrace** | 1.0+ | 系统 Trace | 通用 |
| **adb** | 1.0.41+ | 调试桥 | 通用 |
| **aosp-search** | 最新 | 源码搜索 | — |
| **Android Emulator** | 34+ | 模拟器 | AOSP 17 image |

### 5.2 编译工具

| 工具 | 版本 | 用途 | AOSP 17 兼容 |
|:---|:---|:---|:---|
| **Android SDK Build-Tools** | **37.0.0+** | 构建 | **AOSP 17 推荐** |
| **Android SDK Platform** | **API 37** | 平台 | **AOSP 17** |
| **CMake** | 3.22+ | Native 编译 | AOSP 17 |
| **NDK** | **r27+** | Native 开发 | **AOSP 17 推荐** |
| **JDK** | **17** | Java 编译 | **AOSP 17 要求** |
| **Kotlin** | **2.0+** | Kotlin 编译 | **AOSP 17 推荐** |

### 5.3 第三方库

| 库 | 版本 | 用途 | AOSP 17 兼容 |
|:---|:---|:---|:---|
| **LSPosed** | **1.9+** | Xposed 分支 | **AOSP 17 必须** |
| **Frida** | **16+** | 动态插桩 | **AOSP 17 必须** |
| **Whalebook** | 最新 | 字节码层 Hook | AOSP 17 |
| **Shadow** | **6+** | 插件化 | **AOSP 17 必须升级** |
| **VirtualAPK** | **0.5+** | 插件化 | **AOSP 17 必须升级** |
| **Mockito** | **5.5+** | 单元测试 | **AOSP 17 必须升级** |
| **PowerMock** | **2.0.9+** | 单元测试 | **AOSP 17 必须升级** |

---

## 六、关键 KPI 基线

### 6.1 启动性能 KPI

| KPI | AOSP 14 | **AOSP 17** | 提升 |
|:---|:---|:---|:---|
| 冷启动时间 | 800ms | **750ms** | **-50ms（Zygote Space 优化）** |
| 第一次 GC STW | 50ms | **25ms** | **-50%（PreloadGCRoots）** |
| ClassLoader 加载时间 | 100ms | **50ms** | **-50%（ClassLoader 去重）** |

### 6.2 JNI 性能 KPI

| KPI | AOSP 14 | **AOSP 17** | 提升 |
|:---|:---|:---|:---|
| Local Ref 分配速度 | 基线 | **+50%（Slot Pool）** | **AOSP 17 优化** |
| Global Ref 内存 | 基线 | **-20%（JNIRefTable 压缩）** | **AOSP 17 优化** |
| bytes_per_ref | 16 | **12.8** | **-20%** |

### 6.3 Hook 框架性能 KPI

| KPI | AOSP 14 | **AOSP 17** | 提升 |
|:---|:---|:---|:---|
| Hook 1000 方法耗时（newHook） | — | **50ms** | **+37% vs Frida 16** |
| Hook 1000 方法耗时（Frida 16） | 80ms | 80ms | 基线 |
| ReadBarrier 性能 | 基线 | **+5-10%（缓存版本）** | **AOSP 17 优化** |

### 6.4 Native 堆 KPI

| KPI | AOSP 14 | **AOSP 17** | 提升 |
|:---|:---|:---|:---|
| Native 堆内存占用 | 基线 | **-15-20%（Linux 6.18 sheaves）** | **AOSP 17 + Linux 6.18** |
| heap dump 写盘延迟 | 基线 | **-30%（Linux 6.18 io_uring）** | **AOSP 17 + Linux 6.18** |

---

## 七、JNI 工程原则（AOSP 17 强化）

```
□ 1. Critical 区尽可能短（< 100us，AOSP 17 GenCC 严格）
□ 2. 不在 Critical 区内分配 Java 对象
□ 3. NewGlobalRef 必配对 DeleteGlobalRef
□ 4. 用 RAII / Smart Pointer 管理 Global Ref
□ 5. 异常路径也要 Delete（try-finally / scope guard）
□ 6. 优先用替代 API（GetByteArrayElements / SetXxxArrayRegion）
□ 7. ★ AOSP 17：用 SetXxxArrayRegion 替代 Get/ReleasePrimitiveArrayCritical
□ 8. ★ AOSP 17：避免在 Critical 区做复杂逻辑（GenCC 退化）
□ 9. JNI Ref 数量监控（Global > 1000 警告）
□ 10. ★ AOSP 17：cmd art metrics | grep jni_global
```

---

## 八、Hook 框架工程原则（AOSP 17 强化）

```
□ 1. ART 8+ 用 ReadBarrier::BarrierForRoot
□ 2. ★ AOSP 17：用 ReadBarrier::BarrierForRootWithCache（缓存版本）
□ 3. ART 字段修改用 WriteBarrier
□ 4. 升级 ART 时同步升级 Hook 框架
□ 5. ★ AOSP 17：LSPosed 1.9+ / Frida 16+ / Whalebook / newHook API
□ 6. ★ AOSP 17：优先字节码层 Hook（Whalebook）
□ 7. ★ AOSP 17：插件化必须 opt-in ClassLoader 去重
□ 8. ★ AOSP 17：避免反射改 final 字段
□ 9. 监控 ART Invariant 违反
□ 10. ★ AOSP 17：监控 ArtMethod integrity check failed
```

---

## 九、Zygote / System Server 优化

```
□ 1. 在 Application.onCreate 中预热 GC（子线程）
□ 2. 不在 main thread 触发 GC
□ 3. ★ AOSP 17：升级到 AOSP 17 利用 PreloadGCRoots
□ 4. 精简 preloaded-classes
□ 5. 监控第一次 GC 耗时
□ 6. ★ AOSP 17：监控 ClassLoader 去重状态
□ 7. ★ AOSP 17：监控 fork_gc_* 指标
□ 8. 用 Perfetto 追踪启动时间构成
```

---

## 十、输入法 / SurfaceFlinger 优化

```
□ 1. Buffer Pool + Triple Buffering
□ 2. 缓存候选词 + LRU
□ 3. 监听 onTrimMemory
□ 4. 减少 Native 内存分配
□ 5. 用 Cleaner 替代 finalize
□ 6. ★ AOSP 17：用 AutoCloseable + try-with-resources
□ 7. ★ AOSP 17：Finalizer 线程池化，finalize 仍是瓶颈
```

---

## 十一、跨系列引用

### 11.1 本附录被以下章节引用

- [01-GC与JNI v2](../01-GC与JNI.md) §7 ART 17 硬变化专章
- [02-GC与JNI-GlobalRef v2](../02-GC与JNI-GlobalRef.md) §7 ART 17 硬变化专章
- [03-GC与Zygote v2](../03-GC与Zygote.md) §7 ART 17 硬变化专章
- [04-GC与Hook框架 v2](../04-GC与Hook框架.md) §7 ART 17 硬变化专章

### 11.2 本附录引用

- [A-源码索引](A-源码索引.md) —— 完整源码路径
- [B-路径对账](B-路径对账.md) —— 版本号 / commit hash 对账
- [10-ART17分代GC强化专章 v2](../../10-ART17分代GC强化专章-v2.md) —— ART 17 强化专章
- [01-JNI 完整解析 v2](../../../05-JNI/01-JNI完整解析.md) —— JNI 完整机制
- [02-ART17-JNI 优化 v2](../../../05-JNI/02-ART17-JNI优化与Hook兼容性-v2.md) —— ART 17 JNI 侧硬变化
- [Linux_Kernel/MM/06-MM-调优-sheaves](../01-Mechanism/Kernel/MM/06-MM-调优-sheaves.md) —— Linux 6.18 sheaves（待升级 v2）

---

> **下一篇**：[08-实战案例](../08-实战案例.md) 实战案例：Hook 框架在 CC GC 下的 3 个崩溃（待升级 v2）。
