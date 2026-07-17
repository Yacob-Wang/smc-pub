# 01-ART vs JVM 设计哲学：寄存器 vs 栈、AOT vs JIT、GC 演进

> **本子模块**：08-对比与演进（横切对比 · 8/9）
> **本篇定位**：**横切对比 1/4**——从设计哲学层面对比 ART 与 JVM 的根本差异：指令集 / 内存管理 / 编译策略 / 类加载 / 监控工具

---

## 0. 本篇定位声明

| 维度 | 本篇承担 | 本篇不涉及 |
| :--- | :--- | :--- |
| ART vs JVM 5 大维度对比 | ✓ 指令集 / 内存 / 编译 / 类加载 / 监控 | — |
| 设计哲学差异（移动 vs 通用） | ✓ 完整对比 | — |
| 性能数据对比 | ✓ 5 类核心指标 | — |
| Mainline APEX | — | [02-Mainline 与 APEX](02-Mainline与APEX.md) |
| Hook 框架 | — | [03-Hook 框架](03-Hook框架与ART.md) |

**承接自**：[00-总览](../00-总览/) - [07-启动流程](../07-启动流程/) 详述了 ART 本身；本篇**从设计哲学层面对比 ART 与 JVM**——为什么 ART 长成今天这样。

---

## 1. 背景与定义：为什么需要对比 ART vs JVM

### 1.1 一句话定义

**ART 与 JVM 是两个不同的 Java 运行时实现**：JVM 是 Sun/Oracle 的通用服务器/桌面运行时，ART 是 Google 为 Android 移动设备设计的轻量级运行时。两者在指令集、内存管理、编译策略、类加载、监控工具上都有显著差异。

### 1.2 为什么稳定性架构师需要懂这个对比

**5 大实战场景**：

```
┌────────────────────────────────────────────────────────────────┐
│ ART vs JVM 对比的实战价值                                        │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  场景 1：性能问题排查                                            │
│    └─ 理解 ART 解释器 vs JVM 解释器的性能差异                    │
│    └─ "为什么 ART 比 JVM 快 2-3 倍" → 寄存器模型                │
│                                                                │
│  场景 2：内存问题排查                                            │
│    └─ 理解 ART 的 GC 选择（CMS / CC / GenCC）                    │
│    └─ JVM 的 GC 选择（Parallel / CMS / G1 / ZGC）                │
│                                                                │
│  场景 3：类加载问题排查                                          │
│    └─ ART 的 verify 模式 vs JVM 的 verify 模式                   │
│    └─ ART 启动期 ClassLoader vs JVM 启动期 ClassLoader            │
│                                                                │
│  场景 4：跨平台应用迁移                                           │
│    └─ Android 应用 → 桌面应用 / 服务器应用                       │
│    └─ 理解 ART vs JVM 的差异，避免迁移陷阱                      │
│                                                                │
│  场景 5：监控工具选型                                            │
│    └─ JVMTI 在 ART 中的实现（instrumentation.cc）               │
│    └─ JVM 监控工具的兼容性                                      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 2. 设计哲学的根本差异

### 2.1 JVM 的设计哲学：通用 + 服务器优化

```
┌────────────────────────────────────────────────────────────────┐
│ JVM 设计目标（HotSpot / OpenJDK）                                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  目标场景：                                                      │
│    ├─ 服务器（长时间运行、大内存、多线程）                       │
│    ├─ 桌面应用（中等性能）                                       │
│    └─ 移动设备（保守支持）                                       │
│                                                                │
│  设计权衡：                                                      │
│    ├─ 性能优先（启动时间不敏感）                                 │
│    ├─ 多线程并发（充分利用多核 CPU）                             │
│    ├─ 大堆内存（GB 级堆）                                       │
│    └─ 完整 GC 算法（Parallel / CMS / G1 / ZGC / Shenandoah）    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 ART 的设计哲学：移动 + 启动速度

```
┌────────────────────────────────────────────────────────────────┐
│ ART 设计目标（Android）                                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  目标场景：                                                      │
│    ├─ 移动设备（电池 / 内存 / CPU 紧张）                        │
│    ├─ App 启动速度敏感（用户对启动延迟容忍度低）                  │
│    └─ 多 App 并发运行（系统资源被瓜分）                          │
│                                                                │
│  设计权衡：                                                      │
│    ├─ 启动速度优先（冷启动 < 1s）                                │
│    ├─ 内存占用优先（单 App 内存受限）                             │
│    ├─ 进程隔离（每个 App 一个进程）                              │
│    └─ 简化 GC（CMS / CC / GenCC，针对移动场景优化）              │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 2.3 根本差异对比

| 维度 | JVM | ART | 设计哲学差异 |
| :--- | :--- | :--- | :--- |
| **目标场景** | 服务器 / 桌面 | 移动 | 服务器优化 vs 移动优化 |
| **启动速度** | 不敏感（分钟级） | 极敏感（秒级） | 长跑 vs 短跑 |
| **内存占用** | GB 级 | 100-500MB | 大堆 vs 小堆 |
| **进程模型** | 单进程多线程 | 多进程单线程主线程 | 服务器 vs App 隔离 |
| **指令集** | 栈模型 | 寄存器模型 | 通用 vs 移动优化 |
| **编译策略** | JIT 为主 | JIT + AOT + PGO | 灵活性 vs 启动速度 |
| **GC 选择** | 多算法可选 | 简化（CMS / CC / GenCC） | 通用 vs 移动优化 |
| **监控工具** | JVMTI 完整 | JVMTI 子集 + 平台扩展 | 通用 vs Android 定制 |

---

## 3. 指令集对比：栈模型 vs 寄存器模型

### 3.1 JVM 字节码（栈模型）

```java
public int add(int a, int b) {
    return a + b;
}
```

**JVM 字节码**：
```
0: iload_1        // 压入 a（栈帧操作数栈）
1: iload_2        // 压入 b
2: iadd           // 弹出两个 + 压入结果
3: ireturn        // 返回
```

**栈模型特点**：
- 每个方法都有自己的**操作数栈**
- 指令直接操作栈（压入 / 弹出）
- 操作数栈深度是字节码的一部分（必须严格匹配）

### 3.2 Dalvik 字节码（寄存器模型）

**Dex 字节码（Android）**：
```
0: add-int v0, v2, v3   // v0 = v2 + v3
1: return v0            // return v0
```

**寄存器模型特点**：
- 每个方法使用**虚拟寄存器**（v0, v1, v2, ..., vN）
- 指令直接操作寄存器（无需栈操作）
- `registers_size` 在 CodeItem 中声明

### 3.3 性能对比

| 维度 | JVM（栈模型） | ART（寄存器模型） | 性能影响 |
| :--- | :--- | :--- | :--- |
| **单条指令** | 多次栈操作 | 1 次寄存器访问 | 寄存器更快 |
| **解释器** | ~50 MIPS | ~150 MIPS | ART 解释器快 3x |
| **方法调用** | 频繁栈帧切换 | 寄存器传递 | ART 调用更快 |
| **JIT 优化** | 栈帧分析复杂 | 寄存器分配直接 | ART JIT 更快 |

**架构师视角**：ART 选择寄存器模型是因为 **移动设备解释器执行占比高**（启动期 + 冷方法）——寄存器模型让解释器快 3 倍，对移动设备意义重大。

### 3.4 方法签名差异

| 维度 | JVM | ART（Dalvik） |
| :--- | :--- | :--- |
| 方法签名 | `(II)I` | `(II)I`（相同） |
| 类型描述符 | `Ljava/lang/String;` | `Ljava/lang/String;`（相同） |
| 字节码 | 操作数栈 | 虚拟寄存器 |

---

## 4. 内存管理对比：GC 算法选择

### 4.1 JVM GC 演进

```
┌────────────────────────────────────────────────────────────────┐
│ JVM GC 演进史（OpenJDK / HotSpot）                              │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Java 1.0 - Serial GC（单线程 STW）                              │
│  Java 1.3 - Parallel GC（多线程并行 STW）                        │
│  Java 6 - CMS（Concurrent Mark-Sweep，ART 类似）                  │
│  Java 9 - G1（Garbage-First，分区）                              │
│  Java 11 - ZGC（亚毫秒级暂停）                                  │
│  Java 17 - Generational ZGC（分代 + 亚毫秒）                     │
│                                                                │
│  特点：                                                        │
│    └─ 算法多样化（适配不同场景）                                 │
│    └─ 持续优化（停顿时间从秒级到亚毫秒）                          │
│    └─ 服务器优先（G1 / ZGC 主要为低延迟设计）                    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 4.2 ART GC 演进

```
┌────────────────────────────────────────────────────────────────┐
│ ART GC 演进史                                                    │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Android 1.0 - 4.4: Dalvik GC（标记-清除，STW 长）                │
│  Android 5.0 - 11: ART CMS（Concurrent Mark-Sweep）               │
│  Android 8.0 - 13: ART CC（Concurrent Copying，读屏障）           │
│  Android 12+: ART Generational CC（分代假说 + 读屏障）           │
│  Android 13+: ART CMS / CC 可配置                                │
│                                                                │
│  特点：                                                        │
│    └─ 算法简化（移动场景为主）                                   │
│    └─ 持续优化（停顿时间从 100ms 到 < 10ms）                      │
│    └─ 移动优先（小堆优先）                                      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 4.3 GC 算法对比

| 维度 | JVM | ART | 差异原因 |
| :--- | :--- | :--- | :--- |
| **堆大小** | GB 级（默认） | 100-500MB（默认） | 移动设备内存受限 |
| **STW 时间** | 10ms - 1s（G1 / ZGC 亚毫秒） | 2-50ms（GenCC / CC） | 移动优先 |
| **GC 算法** | Serial / Parallel / CMS / G1 / ZGC | CMS / CC / GenCC | 算法简化 |
| **分代假说** | Generational（G1 / Parallel） | Generational CC（AOSP 12+） | 都应用分代假说 |
| **增量 GC** | G1 / ZGC | CC（读屏障） | 都支持并发 |

### 4.4 ART 引用系统的差异

**JVM**：4 种引用（强 / 软 / 弱 / 虚）+ FinalReference（与 ART 一致）

**ART**：5 种引用（强 / 软 / 弱 / 虚 / Final）+ Cleaner + FinalizerDaemon + FinalizerWatchdog

**ART 独有**：
- **Cleaner**：JDK 9+ 引入，ART AOSP 12+ 支持
- **FinalizerWatchdog**：检测 Finalize 卡死
- **FinalizerDaemon**：独立的 Finalizer 线程（与 ReferenceQueue 线程分离）

---

## 5. 编译策略对比：JIT vs JIT+AOT

### 5.1 JVM 编译策略

```
┌────────────────────────────────────────────────────────────────┐
│ JVM 编译策略（HotSpot）                                         │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  C1 (Client Compiler)                                           │
│    └─ 快速编译、低优化                                         │
│    └─ 客户端 / 桌面应用                                         │
│                                                                │
│  C2 (Server Compiler)                                           │
│    └─ 深度优化、高性能                                         │
│    └─ 服务器 / 长时间运行                                       │
│                                                                │
│  分层编译（Tiered Compilation）                                  │
│    └─ C1 + C2 协同                                              │
│    └─ 先用 C1（快速启动），后用 C2（深度优化）                    │
│                                                                │
│  特点：                                                        │
│    └─ JIT 为主，无 AOT                                         │
│    └─ 启动慢（首次需要 JIT 编译）                                │
│    └─ 长期跑快（深度优化）                                       │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 5.2 ART 编译策略

```
┌────────────────────────────────────────────────────────────────┐
│ ART 编译策略（Android 7+）                                      │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  解释器 → JIT → AOT（三态切换）                                 │
│                                                                │
│  JIT（运行时编译）                                              │
│    └─ 热度阈值（10,000 次调用）                                │
│    └─ OSR（栈上替换）                                          │
│                                                                │
│  AOT（编译期编译）                                              │
│    └─ dex2oat 工具                                              │
│    └─ speed-profile 模式（默认）                                │
│                                                                │
│  PGO（Profile-Guided Optimization）                              │
│    └─ Baseline Profile（开发期）                                │
│    └─ Cloud Profile（云端下发）                                 │
│                                                                │
│  特点：                                                        │
│    └─ 启动快（AOT 直接使用）                                    │
│    └─ 长期跑快（JIT/AOT 双优化）                                │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 5.3 编译策略对比

| 维度 | JVM | ART |
| :--- | :--- | :--- |
| **启动时编译** | 无（AOT 可选） | AOT 默认（speed-profile） |
| **运行时编译** | JIT（C1 + C2） | JIT（解释器 → JIT → AOT） |
| **编译优化** | 深度（C2 数万优化 pass） | 中等（dex2oat 数个 pass） |
| **PGO** | 可选 | 默认（Baseline Profile + Cloud Profile） |
| **启动 vs 长期** | 启动慢 / 长期快 | 启动快 / 长期也快 |
| **存储占用** | 0（无 AOT） | 10-100MB（AOT 文件） |

---

## 6. 类加载对比：Verify 模式

### 6.1 JVM 类加载流程

```
┌────────────────────────────────────────────────────────────────┐
│ JVM 类加载（HotSpot）                                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Loading：                                                      │
│    1. 通过 ClassLoader 读 .class 文件                            │
│    2. 解析常量池（Class / Field / Method / Interface）           │
│                                                                │
│  Linking：                                                      │
│    1. Verify（严格字节码验证）                                   │
│       └─ 类型检查 / 控制流检查 / 访问检查                         │
│    2. Prepare（静态字段默认值）                                  │
│    3. Resolve（符号引用 → 直接引用，lazy）                       │
│                                                                │
│  Initialization：                                               │
│    1. 执行 <clinit>（静态初始化块）                              │
│                                                                │
│  特点：                                                        │
│    └─ Verify 严格（防止恶意字节码）                              │
│    └─ 启动期 verify 慢                                          │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 6.2 ART 类加载流程

```
┌────────────────────────────────────────────────────────────────┐
│ ART 类加载（Android）                                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Loading：                                                      │
│    1. 通过 ClassLoader 读 .dex（mmap 优化）                     │
│    2. 解析 DexFile（String / Type / Method IDs）                 │
│                                                                │
│  Linking：                                                      │
│    1. Verify（轻量验证 + 严格验证可选）                          │
│       └─ Release 默认关闭严格验证（性能考虑）                     │
│       └─ Baseline Profile 中的方法跳过验证                       │
│    2. Prepare（静态字段默认值）                                  │
│    3. Resolve（符号引用，lazy）                                  │
│                                                                │
│  Initialization：                                               │
│    1. 执行 <clinit>（静态初始化块）                              │
│                                                                │
│  特点：                                                        │
│    └─ Verify 可配置（Release 默认关闭）                          │
│    └─ mmap + AOT 优化加载速度                                    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 6.3 Verify 模式对比

| 维度 | JVM | ART |
| :--- | :--- | :--- |
| **严格 verify 默认** | 开启 | 关闭（Release） |
| **verify 性能开销** | 高 | 低 |
| **安全权衡** | 高安全 / 低性能 | 低安全 / 高性能（依赖其他安全机制） |
| **Baseline Profile 跳过** | 不支持 | 支持（跳过 verify） |

**架构师视角**：ART Release 关闭严格 verify 是**性能 vs 安全的明确权衡**——Android 通过 SELinux / APK 签名等机制弥补安全。

---

## 7. 监控工具对比：JVMTI 实现

### 7.1 JVM JVMTI 完整能力

| 能力 | JVM | ART | 差异 |
| :--- | :--- | :--- | :--- |
| Method Entry/Exit | ✅ | ✅ | 一致 |
| Field Access/Modify | ✅ | ✅ | 一致 |
| Class Load/Unload | ✅ | ✅ | 一致 |
| Thread Start/End | ✅ | ✅ | 一致 |
| Garbage Collection Start/Finish | ✅ | ✅ | 一致 |
| Exception | ✅ | ✅ | 一致 |
| Class File Load Hook | ✅ | ⚠️ 部分 | ART 不完全支持 |
| Object Allocation | ✅ | ✅ | 一致 |
| Monitor Contention | ✅ | ✅ | 一致 |
| Method Modification（redefine / retransform） | ✅ | ❌ 不支持 | ART 不支持字节码重定义 |
| Native Method Bind | ✅ | ✅ | 一致 |

### 7.2 ART JVMTI 实现

```cpp
// art/runtime/instrumentation.cc
void Instrumentation::MethodEnterEvent(Thread* thread, ArtMethod* method) {
    // 1. 检查 listener
    if (!HasMethodEntryListeners()) return;
    
    // 2. 通知所有 listener
    for (auto listener : method_entry_listeners_) {
        listener->MethodEnter(thread, method);
    }
}
```

**ART 限制**：
- ❌ 不支持字节码重定义（RetransformClasses / RedefineClasses）
- ❌ 不支持 JVMTI 的某些高级特性（如 Heap Iteration）
- ✅ 支持大多数事件回调

**架构师视角**：ART JVMTI 是 **JVM 的子集**——这是移动场景的合理取舍（性能 + 安全）。

---

## 8. 性能数据对比（综合）

| 指标 | JVM（HotSpot G1） | ART（AOSP 14 GenCC） | 对比 |
| :--- | :--- | :--- | :--- |
| **解释器性能** | ~50 MIPS | ~150 MIPS | ART 快 3x |
| **JIT 性能** | ~1000 MIPS | ~800 MIPS | JVM 略快 |
| **冷启动时间** | 5-30s | 0.8-1.5s | ART 快 10x |
| **GC STW（中等堆）** | 50-200ms | 5-20ms | ART 快 5x |
| **内存占用（基础运行时）** | 100-200MB | 50-100MB | ART 省 50% |
| **类加载速度** | ~10ms / 类 | ~5ms / 类（mmap） | ART 快 2x |
| **方法调用** | ~5ns | ~5ns | 相当 |
| **对象分配** | ~20ns | ~30ns | JVM 略快 |

---

## 9. 实战案例：理解某 App ART vs JVM 的性能差异

**场景**：某团队开发 Android + 桌面端应用，需要评估两端的性能差异。

**关键数据**（Android 14 vs JVM 17）：

| 测试项 | Android（ART） | JVM（HotSpot） | 差异原因 |
| :--- | :--- | :--- | :--- |
| **冷启动** | 800ms | 5000ms | ART AOT 预编译 + Baseline Profile |
| **计算密集（10万次循环）** | 200ms | 180ms | ART JIT 略弱（但解释器领先） |
| **GC 暂停（1GB 数据）** | 10ms（GenCC） | 80ms（G1） | ART 移动优化 |
| **内存占用** | 180MB | 350MB | ART 小堆优先 |

**结论**：
- **启动速度**：ART 完胜（AOT + Baseline Profile）
- **计算性能**：相当（JVM 略优）
- **GC 暂停**：ART 完胜（移动场景优化）
- **内存占用**：ART 完胜（移动设备优先）

**架构师建议**：
- 启动敏感的应用（移动 / 桌面快启）→ ART / Android
- 长时间运行的服务器 → JVM / OpenJDK
- 跨平台（Android + 桌面）→ 用 Kotlin Multiplatform + ART / JVM 双目标

---

## 10. 总结（架构师视角的 5 条 Takeaway）

1. **ART vs JVM 的根本差异是设计哲学**——JVM 是通用 + 服务器优化，ART 是移动 + 启动速度优化。**理解这个才能理解为什么 ART 长成今天这样**。
2. **寄存器模型 vs 栈模型**——ART 选择寄存器是因为移动设备解释器执行占比高。**这是 ART 比 JVM 解释器快 3 倍的根本原因**。
3. **JIT + AOT + PGO 是 ART 的精髓**——三态切换让"启动快 + 跑起来快 + 长期最优"三者兼得。**JVM 的 C1 + C2 做不到这一点**。
4. **GC 算法的简化是合理取舍**——ART 不像 JVM 提供 6+ GC 算法，只提供 3 种（CMS / CC / GenCC）。**这是"够用就好"的工程哲学**。
5. **JVMTI 是 ART 的子集**——ART 不支持字节码重定义（RetransformClasses）。**这是 Android 安全模型的体现**。

---

## 附录 A：核心源码路径索引

| 文件 | 完整路径 | AOSP 版本 |
| :--- | :--- | :--- |
| ART 主目录 | `art/runtime/` | AOSP 14+ |
| Interpreter | `art/runtime/interpreter/` | AOSP 14+ |
| JIT Compiler | `art/compiler/jit/` | AOSP 14+ |
| dex2oat | `art/dex2oat/` | AOSP 14+ |
| GC | `art/runtime/gc/` | AOSP 14+ |
| Instrumentation（JVMTI） | `art/runtime/instrumentation.cc` | AOSP 14+ |
| ClassLinker | `art/runtime/class_linker.cc` | AOSP 14+ |

---

## 附录 B：性能对比速查表

| 指标 | JVM（HotSpot G1） | ART（GenCC） | 差异原因 |
| :--- | :--- | :--- | :--- |
| **解释器 MIPS** | ~50 | ~150 | 寄存器模型 |
| **冷启动** | 5-30s | 0.8-1.5s | AOT + Baseline |
| **GC 暂停** | 50-200ms | 5-20ms | 移动优化 |
| **内存占用** | 100-200MB | 50-100MB | 小堆优先 |

---

## 附录 C：设计哲学对照表

| 维度 | JVM | ART |
| :--- | :--- | :--- |
| **目标场景** | 服务器 / 桌面 | 移动 |
| **启动优先级** | 低 | 极高 |
| **多线程模型** | 多线程并发 | 多进程单线程主线程 |
| **GC 选择** | 多算法 | 简化（3 种） |
| **编译策略** | JIT | JIT + AOT + PGO |
| **Verify 模式** | 严格 | 可关闭 |
| **JVMTI** | 完整 | 子集 |

---

> **下一篇**：[02-Mainline 与 APEX 演进](02-Mainline与APEX.md) 将深入 ART Mainline 演进——ART 从系统镜像剥离为 APEX 模块的历程、ART APEX 模块架构、独立更新机制、与 AOSP 升级的关系。