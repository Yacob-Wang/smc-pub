# 03-Hook 框架与 ART 的兼容性：CC GC 读屏障对 Hook 的影响

> **本子模块**：08-对比与演进（横切对比 · 8/9）
> **本篇定位**：**横切对比 3/4**——Hook 框架（Epic / SandHook / Pine）实现原理 + ART CC GC 读屏障对 Hook 的影响 + ART Hook 三种流派

---

## 1. 背景与定义：Hook 框架在 Android 上的挑战

### 1.1 一句话定义

**Android Hook 框架是允许 App 在运行时修改 Java / Native 方法行为的工具集**（如 Epic / SandHook / Pine / Xposed / Frida）。Android 8.0+ 的 ART CC GC 引入读屏障（Read Barrier）后，Hook 框架必须绕过读屏障才能正确处理对象引用，否则会引发崩溃或数据不一致。

### 1.2 为什么稳定性架构师需要懂 Hook 框架

**Hook 框架的稳定性风险**：

```
┌────────────────────────────────────────────────────────────────┐
│ Hook 框架的 5 大稳定性风险                                       │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. CC GC 读屏障冲突                                            │
│    └─ 触发时机：Android 8.0+ ART CC GC 默认读屏障                 │
│    └─ 现象：Hook 替换的方法访问对象时崩溃                          │
│                                                                │
│  2. ART 编译路径绕过                                              │
│    └─ JIT/AOT 编译后 Hook 代码被跳过                              │
│    └─ 现象：Hook 不生效                                          │
│                                                                │
│  3. Native ABI 兼容性                                            │
│    └─ Android 升级 + ART 升级 → Hook 框架不兼容                    │
│                                                                │
│  4. ANR / Crash 风险                                              │
│    └─ Hook 框架本身有 bug → 主线程 ANR / Crash                    │
│                                                                │
│  5. SELinux / 安全限制                                            │
│    └─ Android 9+ SELinux 收紧 → 部分 Hook 失效                    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 2. Hook 框架实现流派

### 2.1 三大流派

```
┌────────────────────────────────────────────────────────────────┐
│ ART Hook 三大流派                                                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  流派 1：Java 层 Hook（ART Method Hook）                          │
│    └─ 直接替换 ArtMethod 的 entry_point_from_quick_compiled_*    │
│    └─ 代表：Xposed / Epic / SandHook                              │
│                                                                │
│  流派 2：Native 层 Hook（PLT / GOT Hook）                        │
│    └─ 修改 ELF 的 PLT / GOT 表                                   │
│    └─ 代表：Frida / PLT Hook                                     │
│                                                                │
│  流派 3：字节码插桩（Instrumentation）                            │
│    └─ 利用 JVMTI / ART instrumentation                            │
│    └─ 代表：ART instrumentation / Frida Stalker                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 流派 1：ART Method Hook（Java 层）

**ART Method Hook 原理**：

```cpp
// art/runtime/art_method.cc
void ArtMethod::SetEntryPointFromQuickCompiledCode(const void* entry_point) {
    // 直接修改 ArtMethod 的 entry_point 字段
    SetEntryPoint(entry_point);
}
```

**Hook 步骤**：
1. 找到目标 ArtMethod（通过反射 / ClassLinker）
2. 保存原始 entry_point
3. 替换 entry_point 为 Hook 函数
4. Hook 函数调用原始方法（invoke original）

### 2.3 流派 2：PLT / GOT Hook（Native 层）

**PLT Hook 原理**：

```
应用代码：call func@plt
    ↓
PLT 表：func@plt → resolver → 真实地址
    ↓
修改 PLT 表：func@plt → hook_func
    ↓
下次调用：直接跳到 hook_func
```

**代表**：
- **Frida**：动态二进制插桩
- **xHook**：PLT Hook 库
- **Inline Hook**：直接修改函数入口字节码

### 2.4 流派 3：Instrumentation

**ART instrumentation 原理**：

```cpp
// art/runtime/instrumentation.cc
void Instrumentation::MethodEnterEvent(Thread* thread, ArtMethod* method) {
    if (!HasMethodEntryListeners()) return;
    
    for (auto listener : method_entry_listeners_) {
        listener->MethodEnter(thread, method);
    }
}
```

**使用 instrumentation 的工具**：
- **Frida Stalker**：动态跟踪
- **ART JVMTI**：部分功能（事件回调）
- **App 自研 APM**：埋点统计

---

## 3. CC GC 读屏障对 Hook 的影响

### 3.1 CC GC 读屏障原理

```cpp
// art/runtime/gc/collector/concurrent_copying.cc
mirror::Object* ConcurrentCopying::Mark(mirror::Object* from) {
    // 1. 把 from 原子地复制到 to-space
    mirror::Object* to = Copy(from);
    
    // 2. 把 from 标记为 forwarding pointer
    from->SetForwardAddress(to);
    
    return to;
}
```

**读屏障触发点**：每次访问对象引用时（如 `obj.field = otherObj`），需要先调用 `Mark(obj)`。

### 3.2 Hook 框架的绕过方法

**方法 1：使用 ReadBarrier 黑名单**

```cpp
// art/runtime/gc/collector/concurrent_copying.cc
bool ConcurrentCopying::IsInterestingField(mirror::ArtField* field) {
    // Hook 框架标记特定 ArtField 为不感兴趣
    if (hook_blacklist_.find(field) != hook_blacklist_.end()) {
        return false;
    }
    return true;
}
```

**方法 2：使用 ReadBarrier 关闭标记**

```cpp
// 临时关闭读屏障
mirror::Object* HookFunc(ArtMethod* method, Thread* thread, mirror::Object** args) {
    ScopedGCCriticalSection gcs(thread, ...);  // 关闭读屏障
    // ... Hook 逻辑
    mirror::Object* result = InvokeOriginal(method, args);
    return result;
}
```

### 3.3 常见崩溃场景

**场景 1：Hook 函数访问已 GC 移动的对象**

```
GC 触发 → 对象被复制到 to-space
    ↓
Hook 函数访问原对象引用（已是 forwarding pointer）
    ↓
解引用 → 崩溃（访问错误地址）
```

**场景 2：Hook 替换的方法引用错误的对象**

```
Hook 替换目标方法
    ↓
方法返回值是对象引用
    ↓
但 Hook 函数返回的是错误对象（未经过 GC 标记）
    ↓
调用方访问 → 崩溃
```

---

## 4. 代表性 Hook 框架

### 4.1 Epic

**Epic**（https://github.com/tiann/epic）是基于 ART Method Hook 的开源框架。

**特点**：
- 支持 Android 5.0 - 14
- 兼容 CC GC（AOSP 12+ 启用读屏障）
- 支持 inline hook
- 性能损耗小

### 4.2 SandHook

**SandHook**（https://github.com/ganyao114/SandHook）是另一个 ART Method Hook 框架。

**特点**：
- 支持 Android 5.0 - 14
- 支持 JVM / ART 双平台
- 兼容 ART CC GC

### 4.3 Frida

**Frida**（https://frida.re）是动态二进制插桩工具。

**特点**：
- 支持 Java / Native Hook
- 支持 iOS / Android / Windows / Linux
- 基于 PLT / GOT Hook + Inline Hook
- 强大的脚本引擎（JavaScript）

### 4.4 框架对比

| 框架 | 类型 | CC GC 兼容 | 性能损耗 | 学习成本 |
| :--- | :--- | :--- | :--- | :--- |
| **Epic** | Java Method | ✅ | < 5% | 中 |
| **SandHook** | Java Method | ✅ | < 5% | 中 |
| **Frida** | Native + Java | ✅ | 10-30% | 高 |
| **Xposed** | Java Method | ⚠️ 部分 | 5-10% | 低 |
| **Pine** | Java Method | ✅ | < 5% | 中 |

---

## 5. Hook 框架的稳定性影响

### 5.1 ART 升级 → Hook 框架不兼容

| ART 版本 | Hook 框架兼容性 |
| :--- | :--- |
| ART 5.x (Android 5) | Epic / SandHook / Xposed 支持 |
| ART 7.x (Android 7) | 大部分框架支持 |
| ART CC GC (Android 8+) | Epic / SandHook 支持 |
| ART GenCC (Android 12+) | Epic / SandHook 支持（需更新版本） |
| ART APEX (Android 11+) | 部分框架需重新适配 |

### 5.2 Hook 框架崩溃常见原因

| 原因 | 现象 | 排查 |
| :--- | :--- | :--- |
| **CC GC 读屏障冲突** | 随机崩溃 | 关闭读屏障 / 使用白名单 |
| **Native ABI 不匹配** | 启动崩溃 | 重新编译 Native 库 |
| **ART API 变化** | Method 替换失败 | 更新 Hook 框架版本 |
| **SELinux 限制** | 部分 Hook 失效 | 关闭 SELinux（需 root） |
| **内存泄漏** | 进程 OOM | 检查 Hook 框架自身内存 |

---

## 6. 实战案例：某 App 接入 Hook 框架后频繁崩溃

**现象**：某 App 接入 Epic Hook 后，Android 12+ 设备上随机崩溃。

**环境**：Android 14 / ART Generational CC / Epic v0.11.0。

### 步骤 1：抓取崩溃堆栈

```
java.lang.NullPointerException: Attempt to read from null array
  at com.example.hook.EpicHook.invoke(EpicHook.java:42)
  at java.lang.reflect.Method.invoke(Native method)
```

### 步骤 2：定位根因

Epic Hook 函数访问了已被 GC 移动的对象（CC GC 读屏障触发）。

### 步骤 3：修复

```java
// 修复前（错误）
public Object invoke(Object obj, Object[] args) {
    Object result = originalMethod.invoke(obj, args);  // 可能 GC
    return postProcess(result);  // 访问 result 可能崩溃
}

// 修复后（正确）
public Object invoke(Object obj, Object[] args) {
    // 1. 在 GC Critical Section 内执行（关闭读屏障）
    Object result;
    synchronized (gcLock) {  // Hook 框架提供的锁
        result = originalMethod.invoke(obj, args);
    }
    
    // 2. 跨 GC 边界前对 result 做快照
    Object snapshot = copyIfNeeded(result);
    
    return snapshot;
}
```

### 步骤 4：验证

| 指标 | 修复前 | 修复后 |
| :--- | :--- | :--- |
| 崩溃率 | 5% | 0% |
| 性能损耗 | < 5% | < 5% |

---

## 7. 总结（架构师视角的 5 条 Takeaway）

1. **CC GC 读屏障是 Hook 框架的最大挑战**——Android 8.0+ ART 默认启用 CC GC，所有 Hook 框架必须正确处理读屏障。**这是 Hook 框架崩溃的头号原因**。
2. **三大流派各有优势**——Java Method Hook（性能优）/ Native Hook（兼容性强）/ Instrumentation（功能强）。**选型需考虑 ART 版本和性能要求**。
3. **Epic / SandHook / Frida 是当前主流**——Epic / SandHook 是 Java Hook 主流，Frida 是 Native Hook 主流。**稳定性工程师必须熟悉至少一种**。
4. **ART APEX 升级可能破坏 Hook 框架**——每个 ART 版本都可能引入新的 GC 行为或 API 变化。**Hook 框架需要持续适配**。
5. **Hook 框架不是"银弹"**——Hook 会引入性能损耗 + 兼容性风险 + 安全隐患。**生产环境慎用**。

---

## 附录 A：代表性框架

| 框架 | 仓库 | 类型 |
| :--- | :--- | :--- |
| **Epic** | github.com/tiann/epic | Java Method Hook |
| **SandHook** | github.com/ganyao114/SandHook | Java Method Hook |
| **Pine** | github.com/canyie/pine | Java Method Hook |
| **Xposed** | github.com/rovo89/Xposed | Java Method Hook |
| **Frida** | frida.re | Native + Java Hook |

---

## 附录 B：Hook 框架兼容性矩阵

| ART 版本 | Epic | SandHook | Frida | Xposed |
| :--- | :--- | :--- | :--- | :--- |
| **Android 14 (ART APEX v3)** | ✅ v0.12+ | ✅ v1.0+ | ✅ | ⚠️ 部分 |
| **Android 12 (ART APEX v2)** | ✅ | ✅ | ✅ | ⚠️ |
| **Android 10 (ART v2)** | ✅ | ✅ | ✅ | ✅ |
| **Android 8 (ART CC GC)** | ✅ | ✅ | ✅ | ⚠️ |
| **Android 7 (JIT + AOT)** | ✅ | ✅ | ✅ | ✅ |

---

## 8. 进阶实战：Hook 框架适配 ART 升级的 5 步法

### 步骤 1：版本对齐

```bash
# 检查 ART 版本
adb shell getprop ro.apex.com.android.runtime.version
adb shell getprop ro.build.version.sdk

# 检查 Hook 框架版本（以 Epic 为例）
grep -r "ART_VERSION" /data/data/com.example.app/files/epic/
```

### 步骤 2：兼容性测试矩阵

| ART 版本 | 测试设备 | 验证项 |
| :--- | :--- | :--- |
| **Android 14 ART APEX v4** | Pixel 6 | Hook 正常 |
| **Android 13 ART APEX v3** | Pixel 5 | Hook 正常 |
| **Android 12 ART APEX v2** | Pixel 4 | Hook 正常 |
| **Android 10 ART v2** | Pixel 3 | Hook 正常 |
| **Android 8 ART CC GC** | Pixel 1 | Hook 可能不兼容 |

### 步骤 3：CC GC 读屏障验证

```bash
# 启用 ART 详细 GC 日志
adb shell setprop dalvik.vm.dex2oat-Xms 256m
adb shell setprop dalvik.vm.usejit true
adb shell setprop debug.allocTracker.enabled true

# 跑稳定性测试 1 小时
./run_stress_test.sh

# 检查 GC 事件
adb logcat -d -s "art:*" | grep "ReadBarrier"
```

### 步骤 4：崩溃捕获与堆栈分析

```bash
# 启用 ART tombstone
adb shell setprop dalvik.vm.lib.2.org 1

# 跑 Hook 触发场景
./trigger_hook_scenario.sh

# 拉 tombstone
adb pull /data/tombstones/
```

### 步骤 5：Hook 框架升级

```groovy
// build.gradle
dependencies {
    implementation 'me.weishu:epic:0.12.0'  // 最新支持 Android 14
    // implementation 'me.weishu:epic:0.11.0'  // Android 13
}
```

---

## 9. ART Hook 风险全景图

```
┌────────────────────────────────────────────────────────────────┐
│ ART Hook 风险全景                                                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  CC GC 读屏障 ──────────────────────────────────────────────┐  │
│    ↓                                                      │  │
│  ART 编译路径 ──────────────────────────────────────────┐  │  │
│    ↓                                                    │  │  │
│  Native ABI ──────────────────────────────────────┐     │  │  │
│    ↓                                              │     │  │  │
│  ART API 变化 ────────────────────────────┐       │     │  │  │
│    ↓                                      │       │     │  │  │
│  SELinux / 安全 ──────────────────┐       │       │     │  │  │
│    ↓                              │       │       │     │  │  │
│  Hook 框架稳定性 ────────┐       │       │       │     │  │  │
│    ↓                      │       │       │       │     │  │  │
│  内存 / 性能 ─────┐       │       │       │       │     │  │  │
│    ↓              │       │       │       │       │     │  │  │
│  最终风险 = 7 维综合 (Hook 可能崩溃 / 性能下降 / 安全风险)   │  │  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 10. 总结（架构师视角的 5 条 Takeaway）

1. **CC GC 读屏障是 Hook 框架的最大挑战**——Android 8.0+ ART 默认启用 CC GC，所有 Hook 框架必须正确处理读屏障。**这是 Hook 框架崩溃的头号原因**。
2. **三大流派各有优势**——Java Method Hook（性能优）/ Native Hook（兼容性强）/ Instrumentation（功能强）。**选型需考虑 ART 版本和性能要求**。
3. **Epic / SandHook / Frida 是当前主流**——Epic / SandHook 是 Java Hook 主流，Frida 是 Native Hook 主流。**稳定性工程师必须熟悉至少一种**。
4. **ART APEX 升级可能破坏 Hook 框架**——每个 ART 版本都可能引入新的 GC 行为或 API 变化。**Hook 框架需要持续适配**。
5. **Hook 框架不是"银弹"**——Hook 会引入性能损耗 + 兼容性风险 + 安全隐患。**生产环境慎用**。

---

## 附录 C：量化自检表

| # | 量化描述 | 数量级 |
| :-- | :--- | :--- |
| 1 | Method Hook 性能损耗 | 5-10% |
| 2 | Native Hook 性能损耗 | 10-30% |
| 3 | 字节码插桩损耗 | < 5% |
| 4 | JVMTI Method Entry 损耗 | 10-50% |
| 5 | Frida 启动耗时 | +200-500ms |
| 6 | Epic Android 14 兼容性 | ✅ v0.12+ |
| 7 | SandHook Android 14 兼容性 | ✅ v1.0+ |
| 8 | Hook 框架内存开销 | 5-20MB |
| 9 | Hook 失败率（适配良好） | < 0.1% |
| 10 | Hook 失败率（未适配） | 5-20% |

---

## 附录 D：工程基线表

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
| :--- | :--- | :--- | :--- |
| Java Method Hook 库 | Epic / SandHook | — | 适配 ART CC GC |
| Native Hook 库 | Frida / xHook | — | 性能损耗大 |
| 字节码插桩 | Redex / ASM | — | APM SDK 主流 |
| JVMTI 使用 | < 1% 关键方法 | — | 全量埋点性能崩溃 |
| Hook 线程 | 后台线程 | — | 主线程 Hook 卡顿 |
| Hook 失败回滚 | 是 | — | 必须支持 |
| CC GC 兼容性 | 必备 | — | 不兼容随机崩溃 |
| ART 升级适配 | 每个版本测试 | — | 跳过可能崩 |
| SELinux 检查 | 必须 | — | root 才能绕 |
| 内存监控 | 是 | — | Hook 框架泄漏 |

---

## 附录 E：Hook 框架关键源码路径

| 路径 | 角色 |
| :--- | :--- |
| `art/runtime/art_method.cc` | ART Method Hook 入口 |
| `art/runtime/instrumentation.cc` | ART instrumentation 实现 |
| `art/runtime/gc/collector/concurrent_copying.cc` | CC GC 读屏障 |
| `art/runtime/gc/collector/concurrent_copying-inl.h` | CC GC inline 实现 |
| `art/runtime/thread.cc` | SuspendAll / SafePoint |
| `external/skia/` | Frida / 字节码插桩底层 |

---

> **下一篇**：[04-监控与诊断基础设施](04-监控与诊断基础设施.md) 将深入 ART 监控工具链——JVMTI / Perfetto / systrace / Simpleperf / 字节码插桩 / 启动期监控 与诊断基础设施。