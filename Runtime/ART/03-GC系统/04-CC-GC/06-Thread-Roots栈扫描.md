# 4.6 Thread Roots 与栈扫描

> **本节回答一个根本问题**：CC GC 怎么在 STW 期间冻结线程？怎么扫描栈帧？怎么处理 Thread 对象？
>
> **答案**：**SuspendAllThreads + 遍历栈帧 + 扫描局部变量表 + 扫描 Thread 对象字段**。
>
> **理解本节，就理解了"STW 时如何冻结线程"的 ART 答案**。

---

## 一、STW 时的线程冻结机制

### 4.6.1 SuspendAllThreads 的实现

```cpp
// art/runtime/thread_list.cc 的 ThreadList::SuspendAll
void ThreadList::SuspendAll() {
    // 1. 设置全局暂停标志
    suspend_all_count_++;
    
    // 2. 等待所有线程到达安全点
    for (Thread* thread : list_) {
        thread->WaitForSuspend();  // 等待线程暂停
    }
    
    // 3. 所有线程暂停完成
    //    进入 STW 状态
}
```

### 4.6.2 线程暂停的机制

```
业务线程 T1（运行中）              GC 线程
    │                                 │
    │ 执行 Java 代码                  │ 调用 SuspendAllThreads
    │                                 │ 设置暂停标志
    │ ←────── 信号中断 ←─────────────│ 发送 SIGUSR1 信号
    │                                 │
    │ 处理信号：                      │
    │ 1. 保存现场                     │
    │ 2. 设置挂起状态                 │
    │ 3. 等待恢复信号                 │
    │                                 │
    │ ◄────── 等待 ◄─────────────────│ 等待所有线程挂起
    │                                 │
    │                                 │ 全部挂起 → GC 开始
    │                                 │
    │                                 │ GC 完成
    │                                 │
    │ ◄────── 恢复 ◄─────────────────│ 发送恢复信号
    │ 恢复现场                        │
    │ 继续执行                        │
```

### 4.6.3 线程状态

```cpp
// art/runtime/thread.h 的 ThreadState
enum ThreadState {
    kRunnable,           // 可运行
    kSuspended,          // 暂停（STW）
    kWaiting,            // 等待
    kTimedWaiting,       // 限时等待
    kSleeping,           // 睡眠
    kBlocked,            // 阻塞
    kNative,             // 执行 native 代码
    kTerminated,         // 已终止
};
```

---

## 二、栈扫描的完整流程

### 4.6.4 Thread::VisitRoots 实现

```cpp
// art/runtime/thread.cc 的 Thread::VisitRoots
void Thread::VisitRoots(RootVisitor* visitor) {
    // 1. 扫描 Java 栈
    for (StackFrame<mirror::Object>* frame = stack_; 
         frame != nullptr; 
         frame = frame->next_) {
        frame->VisitRoots(visitor);
    }
    
    // 2. 扫描 Native 栈（如果有对象引用）
    if (has_method_handles_) {
        VisitMethodHandles(visitor);
    }
    
    // 3. 扫描 Thread 对象本身
    VisitObjectReferences(visitor, this, &thread_obj_);
    
    // 4. 扫描 Thread 局部变量（JNI）
    if (jni_env_ != nullptr) {
        jni_env_->VisitRoots(visitor);
    }
}
```

### 4.6.5 StackFrame::VisitRoots

```cpp
// art/runtime/stack.cc 的 StackFrame::VisitRoots
void StackFrame::VisitRoots(RootVisitor* visitor) {
    // 1. 扫描方法参数 + 局部变量
    for (size_t i = 0; i < GetNumberOfVRegs(); i++) {
        mirror::Object* ref = GetVReg(i);
        if (ref != nullptr) {
            visitor(ref);  // 标记
        }
    }
    
    // 2. 扫描操作数栈（如果有对象引用）
    if (HasReferenceOperands()) {
        // 扫描操作数栈
    }
    
    // 3. 扫描 dex 寄存器映射（用于解释器栈帧）
    VisitDexRegisters(visitor);
}
```

### 4.6.6 栈扫描的优化：Stack Map

AOT/JIT 编译器生成的代码包含 **Stack Map**（栈映射表），记录栈帧每个 slot 的类型：

```
┌──────────────────────────────────────────┐
│              Stack Frame                   │
├──────────────────────────────────────────┤
│  PC  |  vreg[0] | vreg[1] | vreg[2] | ... │
├──────────────────────────────────────────┤
│  0x100 |  Ref   |  int   |  Ref   | ...  │
│  0x200 |  Ref   |  null  |  int   | ...  │
│  0x300 |  null  |  Ref   |  Ref   | ...  │
└──────────────────────────────────────────┘

Stack Map 告诉 GC：
- 在 PC = 0x100 时，vreg[0] 是对象引用，vreg[1] 是 int，vreg[2] 是对象引用
- 在 PC = 0x200 时，vreg[0] 是对象引用，vreg[1] 是 null，vreg[2] 是 int
```

**优势**：GC 扫描时无需逐 slot 试探类型，直接读取 Stack Map 即可。

---

## 三、解释器栈 vs 编译码栈

### 4.6.7 解释器栈的处理

解释器栈是软件模拟的栈帧，扫描较慢：

```cpp
// art/runtime/interpreter/interpreter.cc
void Interpreter::VisitRoots(RootVisitor* visitor) {
    // 1. 解释器栈帧是软件模拟的
    ShadowFrame* frame = top_frame_;
    while (frame != nullptr) {
        // 2. 遍历 shadow frame 的 vregs
        for (size_t i = 0; i < frame->NumberOfVRegs(); i++) {
            mirror::Object* ref = frame->GetVReg(i);
            if (ref != nullptr) {
                visitor(ref);
            }
        }
        frame = frame->GetLink();  // 下一个 frame
    }
}
```

### 4.6.8 编译码栈的处理

AOT/JIT 编译码栈是真实的机器栈，扫描依赖 Stack Map：

```cpp
// art/runtime/arch/arm64/quick_entrypoints_arm64.S
// ARM64 上栈扫描的快速路径
art_quick_stack_visitor:
    ; 1. 获取当前 fp（frame pointer）
    mov x9, fp
    
    ; 2. 遍历栈帧（fp 链）
.Lloop:
    cbz x9, .Lend                ; fp == null → 结束
    
    ; 3. 读取 Stack Map（由 AOT 编译器生成）
    ldr x10, [x9, #stack_map_offset]
    
    ; 4. 按 Stack Map 扫描
    bl artVisitStackMap
    
    ; 5. 移动到下一个 fp
    ldr x9, [x9, #prev_fp_offset]
    b .Lloop
```

### 4.6.9 解释器栈 vs 编译码栈的扫描速度

| 类型 | 数量级 | 扫描耗时 |
|:---|:---|:---|
| **解释器栈** | ~10-50 frames × ~10 vregs | ~2ms |
| **编译码栈** | ~10-50 frames × ~16 vregs | ~1ms |

→ **编译码栈扫描更快**（依赖 Stack Map）。

---

## 四、Thread 对象的字段扫描

### 4.6.10 Thread 对象包含的 Root

```cpp
// art/runtime/thread.cc 的 Thread 对象字段
class Thread {
    // 关键 Root 字段
    mirror::Object* peer_;           // Thread peer
    mirror::Object* name_;            // Thread name
    jobject jni_env_;                 // JNI environment
    
    // 栈相关
    StackFrame<mirror::Object>* stack_;  // Java 栈
    std::vector<mirror::Object*> jni_local_refs_;  // JNI Local Refs
    
    // Thread 状态
    ThreadState state_;
};
```

### 4.6.11 Thread 对象的字段扫描

```cpp
void Thread::VisitObjectReferences(RootVisitor* visitor, void* obj, ...) {
    Thread* thread = reinterpret_cast<Thread*>(obj);
    
    // 1. peer_（Thread peer）
    visitor(&thread->peer_);
    
    // 2. name_（Thread name）
    if (thread->name_ != nullptr) {
        visitor(&thread->name_);
    }
    
    // 3. jni_env_（JNI environment）
    if (thread->jni_env_ != nullptr) {
        thread->jni_env_->VisitRoots(visitor);
    }
}
```

---

## 五、CC GC 的栈扫描策略

### 4.1.12 CC GC 的栈扫描时间

CC GC 的栈扫描时间分析：

| 线程数 | 栈深度 | vreg 数 | 总 slot 数 | 扫描耗时 |
|:---|:---|:---|:---|:---|
| 10 | 50 | 16 | 8000 | ~1ms |
| 100 | 50 | 16 | 80000 | ~5ms |
| 1000 | 50 | 16 | 800000 | ~50ms |

**注意**：线程数过多时栈扫描会很慢！

### 4.1.13 CC GC 的栈扫描优化

**优化 1：Stack Map**

```cpp
// AOT/JIT 编译时生成 Stack Map
// GC 扫描时直接读取，避免类型判断
```

**优化 2：并发栈扫描（部分）**

```cpp
// 某些 ART 版本实现部分并发栈扫描
// 把栈扫描分为多个阶段，分摊到 GC 的不同时间
```

**优化 3：避免深度栈**

```java
// 业务代码优化：避免过深的调用栈
public void doWork() {
    // 避免：递归深度过大
    recursiveMethod(depth);  // ❌ 深栈
    
    // 推荐：循环代替递归
    iterativeMethod(depth);  // ✅ 浅栈
}
```

### 4.1.14 STW 时的线程冻结开销

```
STW 总耗时 = 线程冻结时间 + 栈扫描时间 + GC 工作时间 + 线程恢复时间

线程冻结：~10ms（发送信号 + 等待所有线程）
栈扫描：~2ms
GC 工作：~1ms（Initialize 阶段）
线程恢复：~5ms
─────────────────
总计：~18ms（理论最坏）

实际 ART 优化后：~2-5ms
```

---

## 六、Thread Roots 的工程影响

### 4.1.15 栈扫描与多线程

**问题**：线程数过多导致栈扫描慢。

**修复**：
```java
// 减少线程数
ExecutorService executor = Executors.newFixedThreadPool(8);  // 限制线程池大小
// ❌ 避免：每次请求都 new Thread
```

### 4.1.16 栈扫描与 JNI

**JNI Local Ref 也要扫描**：
```cpp
// JNI 函数中创建的 Local Ref 是 Thread 的 Root
void JNI方法(JNIEnv* env) {
    jstring str = env->NewStringUTF("hello");  // Local Ref
    // str 在 Thread.jni_local_refs_ 中
    // GC 扫描时会标记它
}
```

### 4.1.17 栈扫描与 Native 代码

**Native 代码的对象引用**：

```cpp
// Native 代码中保存 Java 对象引用
static jobject g_cached_obj = nullptr;  // 静态引用

// 必须用 Global Ref 或 Weak Global Ref
// 否则 GC 不识别这个引用，错误回收
```

---

## 七、Thread Roots 的源码索引

### 4.1.18 核心源码路径

```
art/runtime/thread_list.cc                  # ThreadList::SuspendAll
art/runtime/thread.cc                       # Thread::VisitRoots
art/runtime/thread.h                        # Thread 类
art/runtime/stack.cc                        # StackFrame::VisitRoots
art/runtime/interpreter/interpreter.cc      # 解释器栈扫描
art/runtime/arch/arm64/quick_entrypoints_arm64.S  # AArch64 栈扫描机器码
art/runtime/gc/collector/concurrent_copying.cc  # CC GC 的栈扫描
```

### 4.1.19 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `ThreadList::SuspendAll` | `thread_list.cc` | 暂停所有线程（STW） |
| `ThreadList::ResumeAll` | `thread_list.cc` | 恢复所有线程 |
| `Thread::VisitRoots` | `thread.cc` | 扫描 Thread |
| `StackFrame::VisitRoots` | `stack.cc` | 扫描栈帧 |
| `Interpreter::VisitRoots` | `interpreter.cc` | 扫描解释器栈 |
| `QuickStackVisitor` | `arch/*/quick_entrypoints_*.S` | 编译码栈扫描 |

### 4.1.20 STW 关键路径

```
ThreadList::SuspendAll
    │
    ├── 增加 suspend_all_count_
    │
    ├── 遍历所有 Thread
    │   │
    │   └── thread->WaitForSuspend()
    │       │
    │       └── 等待线程到达安全点
    │
    └── 所有线程暂停 → STW 开始

[GC 执行栈扫描 + GC 工作]

ThreadList::ResumeAll
    │
    ├── 恢复所有 Thread
    │
    └── STW 结束
```

---

## 八、本节小结

1. **STW 通过 SIGUSR1 信号暂停线程** + 等待所有线程到达安全点
2. **栈扫描 = 遍历栈帧 + 扫描 vreg + 扫描 Thread 对象字段**
3. **Stack Map 让编译码栈扫描极快**（无需类型判断）
4. **解释器栈扫描较慢**（软件模拟）
5. **线程数过多导致栈扫描慢** —— 业务应限制线程数

→ **理解 Thread Roots 与栈扫描，就理解了 STW 时 GC 如何冻结线程**。

---

## 跨节引用

**本节被以下章节引用**：
- [4.2 3 阶段详解](./02-3阶段详解.md) —— Initialize 阶段的栈扫描
- 09 篇诊断 —— STW 时间监控
- [01 篇 1.1 可达性分析](../01-基础理论/01-可达性分析.md) —— Thread 作为 GC Root

**本节引用**：
- [4.1 核心思想](./01-CC核心思想.md) —— CC GC 与 STW 的关系
- [4.2 3 阶段详解](./02-3阶段详解.md) —— Initialize 阶段的栈扫描
