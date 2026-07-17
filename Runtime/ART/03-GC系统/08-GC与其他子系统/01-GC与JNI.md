# 8.1 GC × JNI：Critical 区的阻塞问题

> **本节回答一个根本问题**：JNI Critical 区（如 GetPrimitiveArrayCritical）为什么阻塞 GC？业务代码应该怎么避免？
>
> **答案**：**Critical 区的指针不能移动（可能正在被 native 使用）→ GC 必须等待 Critical 区释放**。

---

## 一、JNI Critical 区的定义

### 8.1.1 Critical 区 API

```cpp
// art/runtime/jni/jni_internal.cc
// 关键 API
void* GetPrimitiveArrayCritical(JNIEnv* env, jarray array, jboolean* is_copy);
void ReleasePrimitiveArrayCritical(JNIEnv* env, jarray array, void* carray, jmode mode);

// 还有相关 API
void* GetStringCritical(JNIEnv* env, jstring string, jboolean* is_copy);
void ReleaseStringCritical(JNIEnv* env, jstring string, const void* cstring);
```

### 8.1.2 Critical 区的特殊性

```
Critical 区的特殊性：

1. 直接返回 native 内存指针
   - 不经过 JNI 引用管理
   - native 代码直接读写 array 内存

2. 必须 pin 内存
   - GC 不能移动 array 的内容
   - 否则 native 代码访问错误地址

3. 阻塞 GC
   - CC GC 想移动 array 时
   - 必须等待 Critical 区释放
   - 否则会破坏 native 内存
```

### 8.1.3 Critical 区与 GC 的冲突

```
业务线程在 Critical 区读 array
  ↓
CC GC 触发，想移动 array 到 to-space
  ↓
但 array 被 pin，GC 无法移动
  ↓
GC 必须等待 Critical 区释放
  ↓
业务线程长时间占用 Critical 区
  ↓
GC 等待时间 → 用户感知卡顿
```

---

## 二、Critical 区的实现

### 8.1.4 ART 的 Critical 实现

```cpp
// art/runtime/jni/jni_internal.cc 的 GetPrimitiveArrayCritical
void* GetPrimitiveArrayCritical(JNIEnv* env, jarray array, jboolean* is_copy) {
    // 1. 获取 array 的 native 指针
    void* carray = GetArrayData(array);
    
    // 2. 通知 GC：array 被 pin
    //    pin 的 array 不能移动
    heap_->IncrementDisableMovingGC(self);
    
    // 3. 设置 Critical 区计数
    critical_section_count_++;
    
    // 4. 返回 native 指针
    return carray;
}
```

### 8.1.5 ReleasePrimitiveArrayCritical

```cpp
void ReleasePrimitiveArrayCritical(JNIEnv* env, jarray array, void* carray, jmode mode) {
    // 1. 减少 Critical 区计数
    critical_section_count_--;
    
    // 2. 通知 GC：array 不再被 pin
    if (critical_section_count_ == 0) {
        heap_->DecrementDisableMovingGC(self);
    }
    
    // 3. 如果有修改且需要回写
    if (mode == 0 && carray != nullptr) {
        // 写回 Java 堆
        memcpy(GetArrayData(array), carray, ...);
    }
}
```

### 8.1.6 Heap 的 pin 计数

```cpp
// art/runtime/gc/heap.cc
void Heap::IncrementDisableMovingGC(Thread* self) {
    // 增加 pin 计数
    // GC 在 CC 阶段会检查这个计数
    // 如果 > 0，array 不能移动
    disable_moving_gc_count_++;
}

void Heap::DecrementDisableMovingGC(Thread* self) {
    // 减少 pin 计数
    disable_moving_gc_count_--;
}
```

---

## 三、CC GC 与 Critical 区的交互

### 8.1.7 CC GC 检查 pin 计数

```cpp
// art/runtime/gc/collector/concurrent_copying.cc
bool ConcurrentCopying::IsMovable(mirror::Object* obj) {
    // 1. 检查 pin 计数
    if (heap_->disable_moving_gc_count_ > 0) {
        // 有 Critical 区，不能移动任何对象
        // （简化逻辑，实际更复杂）
        return false;
    }
    
    // 2. 检查对象是否被 pin
    if (obj->IsPinned()) {
        return false;
    }
    
    // 3. 可以移动
    return true;
}
```

### 8.1.8 Critical 区阻塞 GC 的场景

```
Critical 区阻塞 GC 的具体场景：

1. 业务线程 1 在 Critical 区
2. 业务线程 2 申请分配，触发 GC
3. GC 线程想要移动对象
4. 但有 Critical 区 → 等待
5. 业务线程 1 长时间占用 Critical 区（例如 100ms）
6. GC 等待 100ms
7. 业务线程 2 卡 100ms（GC_FOR_ALLOC）
8. 用户感知卡顿
```

### 8.1.9 Critical 区的卡顿影响

```
Critical 区对卡顿的影响：

场景 1：Critical 区 100ms
  → GC 等待 100ms
  → 用户感知：明显卡顿（100ms = 6 帧）

场景 2：Critical 区 10ms
  → GC 等待 10ms
  → 用户感知：轻微卡顿

场景 3：Critical 区 < 1ms
  → GC 不等待
  → 用户感知：无
```

---

## 四、Critical 区的工程最佳实践

### 8.1.10 原则 1：Critical 区尽可能短

```cpp
// ❌ 错误：Critical 区长
void bad_use(JNIEnv* env, jbyteArray array) {
    jbyte* bytes = (jbyte*)env->GetPrimitiveArrayCritical(array, nullptr);
    
    // 长时间处理
    complexProcessing(bytes, length);  // 假设耗时 100ms
    
    env->ReleasePrimitiveArrayCritical(array, bytes, 0);
    // ↑ Critical 区共 100ms → 阻塞 GC
}

// ✅ 正确：Critical 区短
void good_use(JNIEnv* env, jbyteArray array) {
    jbyte* bytes = (jbyte*)env->GetPrimitiveArrayCritical(array, nullptr);
    
    // 仅必要的内存读写
    memcpy(local_buffer, bytes, length);
    
    env->ReleasePrimitiveArrayCritical(array, bytes, JNI_ABORT);
    // ↑ Critical 区极短
    
    // 长时间处理（在 Java 堆外）
    complexProcessing(local_buffer, length);
}
```

### 8.1.11 原则 2：避免在 Critical 区内分配对象

```cpp
// ❌ 错误：在 Critical 区内分配
void bad_use(JNIEnv* env, jbyteArray array) {
    jbyte* bytes = (jbyte*)env->GetPrimitiveArrayCritical(array, nullptr);
    
    // 在 Critical 区分配 Java 对象 → 触发 GC → 死锁
    jobject new_obj = env->NewObject(cls, ...);  // ❌ 触发 GC
    
    env->ReleasePrimitiveArrayCritical(array, bytes, 0);
}

// ✅ 正确：在 Critical 区外分配
void good_use(JNIEnv* env, jbyteArray array) {
    // 先分配 Java 对象（在 Critical 区外）
    jobject new_obj = env->NewObject(cls, ...);
    
    // 再进入 Critical 区
    jbyte* bytes = (jbyte*)env->GetPrimitiveArrayCritical(array, nullptr);
    // 仅内存读写，不分配
    memcpy(bytes, ..., length);
    env->ReleasePrimitiveArrayCritical(array, bytes, 0);
}
```

### 8.1.12 原则 3：用 Critical 替代方案

```cpp
// 替代方案 1：用 GetXxxArrayElements + Release
void alternative1(JNIEnv* env, jbyteArray array) {
    jbyte* bytes = env->GetByteArrayElements(array, nullptr);
    // GetByteArrayElements 不强制 pin，可以拷贝
    process(bytes, length);
    env->ReleaseByteArrayElements(array, bytes, 0);
}

// 替代方案 2：用 SetXxxArrayRegion
void alternative2(JNIEnv* env, jbyteArray array) {
    // 直接设置区域，不需要 native 指针
    env->SetByteArrayRegion(array, 0, length, local_buffer);
}
```

---

## 五、Critical 区的监控

### 8.1.13 监控 Critical 区时长

```bash
# 1. ART 调试日志
adb shell setprop dalvik.vm.image-dex2oat-flags --debug
adb logcat -s "art" | grep "Critical"

# 2. Perfetto trace
adb shell perfetto --out /data/local/tmp/trace.proto \
  -t 30s sched freq idle am wm gfx view binder_driver hal dalvik
# 在 Perfetto UI 中搜索 Critical section
```

### 8.1.14 Critical 区异常的诊断

| 现象 | 根因 | 修复 |
|:---|:---|:---|
| GC 等待时间 > 50ms | Critical 区占用长 | 缩短 Critical 区 |
| Critical 区 100ms+ | 业务代码错误 | 用替代方案 |
| GC 频繁卡顿 | 多次 Critical 区 | 合并 Critical 区 |

---

## 六、Critical 区的源码索引

### 8.1.15 核心源码路径

```
art/runtime/jni/jni_internal.cc          # JNI Critical 实现
art/runtime/gc/heap.h                   # Heap 类（含 disable_moving_gc_count_）
art/runtime/gc/heap.cc                  # Heap 实现
art/runtime/gc/collector/concurrent_copying.cc # CC GC 检查 pin
```

### 8.1.16 关键函数

| 函数 | 功能 |
|:---|:---|
| `GetPrimitiveArrayCritical` | 进入 Critical 区 |
| `ReleasePrimitiveArrayCritical` | 释放 Critical 区 |
| `Heap::IncrementDisableMovingGC` | 增加 pin 计数 |
| `Heap::DecrementDisableMovingGC` | 减少 pin 计数 |
| `ConcurrentCopying::IsMovable` | 检查对象是否可移动 |

---

## 七、本节小结

1. **Critical 区 pin array 内存**：GC 不能移动
2. **Critical 区阻塞 GC**：长时间占用 → 卡顿
3. **Critical 区工程原则**：尽可能短 / 不在区内分配 / 用替代方案
4. **替代方案**：GetXxxArrayElements / SetXxxArrayRegion
5. **监控**：Critical 区时长 + GC 卡顿

→ **理解 Critical 区与 GC，就理解了"为什么 JNI 调用要小心"**。

---

## 跨节引用

**本节被以下章节引用**：
- [8.2 JNI Global Ref](./02-GC与JNI-GlobalRef.md) —— JNI 全局引用
- [8.8 实战案例](./08-实战案例.md) —— Critical 区实战

**本节引用**：
- 04 篇 CC GC —— 移动对象机制
- ART 大模块的 `04-JNI` —— JNI 完整机制
