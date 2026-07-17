# 8.2 GC × JNI：Global Reference 的 GC 责任

> **本节回答一个根本问题**：JNI Global Reference 是什么？为什么它是 GC Root？Global Ref 泄漏 = Java 堆泄漏？
>
> **答案**：**JNI Global Ref 是 GC Root，持有 Global Ref 的对象不会被 GC 回收**——泄漏即永久。

---

## 一、JNI Global Reference 的定义

### 8.2.1 Global Ref 的 API

```cpp
// art/runtime/jni/jni_internal.cc
jobject NewGlobalRef(JNIEnv* env, jobject obj);
void DeleteGlobalRef(JNIEnv* env, jobject globalRef);

jweak NewWeakGlobalRef(JNIEnv* env, jobject obj);
void DeleteWeakGlobalRef(JNIEnv* env, jweak obj);
```

### 8.2.2 Global Ref 的特点

```
Global Ref 的特点：

1. 跨 JNI 调用保持有效
   - Local Ref 在 native 函数返回时失效
   - Global Ref 一直有效，直到 DeleteGlobalRef

2. 是 GC Root
   - Global Ref 持有对象不会被 GC 回收
   - 必须显式 DeleteGlobalRef 释放

3. 占用 JNI 引用表
   - 每个 Global Ref 占一个 slot
   - 默认上限 51200 个 Global Ref
```

### 8.2.3 Global Ref 与 Local Ref 的对比

| 维度 | Local Ref | Global Ref |
|:---|:---|:---|
| **生命周期** | native 函数返回失效 | 直到 DeleteGlobalRef |
| **GC Root** | 否 | 是 |
| **跨线程** | 否 | 是 |
| **容量限制** | 512 个（默认） | 51200 个（默认） |
| **典型用途** | 函数参数 / 临时对象 | 缓存 / 回调 |

---

## 二、Global Ref 的实现

### 8.2.4 Global Ref 的存储

```cpp
// art/runtime/jni/indirect_reference_table.h
class IndirectReferenceTable {
public:
    // Global Ref 存储在 table_ 中
    struct IndirectRef {
        uint32_t serial_;       // 序列号
        mirror::Object* referent_;  // 引用的对象
    };
    
    IndirectRef Get(size_t idx) const {
        return table_[idx];
    }
    
    void Add(mirror::Object* obj) {
        table_[next_].serial_ = serial_counter_++;
        table_[next_].referent_ = obj;
    }
    
    size_t GetCapacity() const {
        return table_.size();
    }
};

// IndirectReferenceTable 用于 Global Ref
class GlobalRefTable : public IndirectReferenceTable {
    // 默认 51200 个 slot
    static constexpr size_t kDefaultGlobalCapacity = 51200;
};
```

### 8.2.5 NewGlobalRef 实现

```cpp
// art/runtime/jni/jni_internal.cc 的 NewGlobalRef
jobject NewGlobalRef(JNIEnv* env, jobject obj) {
    // 1. 检查 obj 是否为 null
    if (obj == nullptr) return nullptr;
    
    // 2. 加锁（避免并发问题）
    std::lock_guard<std::mutex> lock(global_ref_table_lock_);
    
    // 3. 把 obj 加入 Global Ref 表
    IndirectRef iref = global_ref_table_->Add(obj);
    
    // 4. 返回 IndirectRef（指向对象的指针）
    return reinterpret_cast<jobject>(iref);
}
```

### 8.2.6 DeleteGlobalRef 实现

```cpp
void DeleteGlobalRef(JNIEnv* env, jobject globalRef) {
    // 1. 检查 globalRef 是否为 null
    if (globalRef == nullptr) return;
    
    // 2. 加锁
    std::lock_guard<std::mutex> lock(global_ref_table_lock_);
    
    // 3. 把 globalRef 从表中移除
    global_ref_table_->Remove(globalRef);
}
```

---

## 三、Global Ref 与 GC 的交互

### 8.3.7 Global Ref 是 GC Root

```cpp
// art/runtime/gc/root_visitor.h
enum RootType {
    // ...
    kRootJniGlobal,  // ← Global Ref
    kRootJniLocal,
    // ...
};

// GC 扫描时
VisitRoots([this](mirror::Object* obj) {
    // 1. 扫描 JNI Global Ref
    jni_globals->VisitRoots(visitor);
});
```

### 8.3.8 Global Ref 泄漏 = Java 堆泄漏

```
Global Ref 泄漏的后果：

1. Global Ref 是 GC Root
2. Global Ref 引用的对象不会被 GC 回收
3. 多次 NewGlobalRef 但忘记 DeleteGlobalRef
4. → 全局表持续增长
5. → 引用的对象持续占用 Java 堆
6. → Java 堆使用率持续增长
7. → 频繁 GC
8. → 最终 OOM
```

### 8.3.9 Global Ref 泄漏的诊断

```bash
# 1. dumpsys meminfo 看 JNI 引用数
adb shell dumpsys meminfo <package> | grep -i "JNI"
# 输出示例：
#   JNI:    1234     1000      234      0      1234
#         ↑↑↑↑↑↑↑↑↑↑↑
#         Global Ref 数量

# 2. 对比多次 dumpsys
# 如果 Global Ref 数量持续增长且不收敛 → 泄漏
```

### 8.3.10 Global Ref 监控

```java
public class GlobalRefMonitor {
    @Scheduled(fixedRate = 60000)
    public void monitor() {
        // 1. 读取 JNI Global Ref 数量
        int globalRefCount = Debug.getJniGlobalRefCount();
        
        // 2. 上报到 APM
        apmClient.report("jni.globalref.count", globalRefCount);
        
        // 3. 告警
        if (globalRefCount > 1000) {
            apmClient.alert("jni.globalref.high", "JNI Global Ref > 1000");
        }
        
        // 4. 检查是否持续增长
        // （需要历史数据）
    }
}
```

---

## 四、Global Ref 的工程最佳实践

### 8.4.11 原则 1：NewGlobalRef 必配对 DeleteGlobalRef

```cpp
// ❌ 错误：忘记 DeleteGlobalRef
void bad_use(JNIEnv* env, jobject obj) {
    g_obj = env->NewGlobalRef(obj);  // 创建 Global Ref
    // ❌ 忘记 DeleteGlobalRef → 泄漏
}

// ✅ 正确：成对使用
void good_use(JNIEnv* env, jobject obj) {
    g_obj = env->NewGlobalRef(obj);
    // ...
    if (g_obj != nullptr) {
        env->DeleteGlobalRef(g_obj);  // 显式释放
        g_obj = nullptr;
    }
}
```

### 8.4.12 原则 2：用 Smart Pointer 管理 Global Ref

```cpp
// 用智能指针（自定义）
class GlobalRefHolder {
public:
    GlobalRefHolder(JNIEnv* env, jobject obj) : env_(env), ref_(nullptr) {
        if (obj != nullptr) {
            ref_ = env->NewGlobalRef(obj);
        }
    }
    
    ~GlobalRefHolder() {
        if (ref_ != nullptr) {
            env_->DeleteGlobalRef(ref_);
        }
    }
    
    jobject Get() const { return ref_; }
    
private:
    JNIEnv* env_;
    jobject ref_;
};

// 使用
void good_use() {
    GlobalRefHolder holder(env, obj);
    // 使用 holder.Get()
    // 自动释放
}
```

### 8.4.13 原则 3：避免不必要的 Global Ref

```cpp
// ❌ 错误：用 Global Ref 持有 Activity Context
static jobject g_activity;  // 永远不释放

// ✅ 正确：用 Application Context
static jobject g_application_context;  // 通常单例，安全

// ✅ 更好：避免 native 持有 Java 对象
// 让 Java 端管理，native 只通过 callback 访问
```

### 8.4.14 原则 4：定期清理未使用的 Global Ref

```cpp
// 定期清理策略
class GlobalRefCache {
public:
    void Cleanup() {
        // 清理不再使用的 Global Ref
        for (auto& pair : cache_) {
            if (!IsStillUsed(pair.first)) {
                env_->DeleteGlobalRef(pair.second);
                cache_.erase(pair.first);
            }
        }
    }
    
private:
    std::unordered_map<Key, jobject> cache_;
};
```

---

## 五、Global Ref 与 Weak Global Ref

### 8.5.15 Weak Global Ref 的特点

```
Weak Global Ref 的特点：

1. 不阻止 GC 回收
   - 如果引用的对象只被 Weak Ref 指向
   - GC 回收后，Weak Ref 自动失效
   - IsSameObject 检查会返回 false

2. 适用场景
   - 缓存（不强制对象存活）
   - 观察者模式
```

### 8.5.16 Weak Global Ref 的使用

```cpp
// 使用 Weak Global Ref 做缓存
class Cache {
public:
    void Put(JNIEnv* env, jobject obj) {
        // 用 Weak Global Ref 缓存
        jweak weak_ref = env->NewWeakGlobalRef(obj);
        cache_[key_] = weak_ref;
    }
    
    jobject Get(JNIEnv* env, const std::string& key) {
        jweak weak_ref = cache_[key_];
        if (weak_ref == nullptr) return nullptr;
        
        // 检查对象是否还存活
        jobject obj = env->NewLocalRef(weak_ref);
        if (env->IsSameObject(obj, nullptr)) {
            // 对象已被 GC
            cache_.erase(key);
            return nullptr;
        }
        return obj;
    }
};
```

---

## 六、Global Ref 的工程监控

### 8.6.17 dumpsys meminfo 中的 JNI 信息

```bash
$ adb shell dumpsys meminfo <package>

# 关键输出
                       Pss    Private   Private   SwapPss      Rss
                     Total    Dirty    Clean    Dirty    Total
  Native Heap      12345     6789     1234      100    15000
  Dalvik Heap      45678    40000     5678      200    51234
   ...
   ...
   JNI:    1234     1000      234      0      1234
          ↑↑↑↑
          JNI Global Ref 数量
```

### 8.6.18 异常的诊断

| JNI Ref 数量 | 状态 | 根因 | 修复 |
|:---|:---|:---|:---|
| < 100 | 正常 | — | — |
| 100-1000 | 警告 | 可能有泄漏 | 排查代码 |
| > 1000 | 严重 | 明显泄漏 | 紧急修复 |
| 持续增长 | 紧急 | 大量 NewGlobalRef 无 Delete | 紧急修复 |

---

## 七、本节小结

1. **Global Ref 是 GC Root**：持有对象不会被回收
2. **Global Ref 泄漏 = Java 堆泄漏**：永久
3. **NewGlobalRef 必配对 DeleteGlobalRef**
4. **用 Weak Global Ref 做缓存**：避免强制对象存活
5. **监控 JNI Ref 数量**：超过 1000 警告

→ **理解 Global Ref 与 GC，就理解了"为什么 JNI Global Ref 泄漏 = Java 堆泄漏"**。

---

## 跨节引用

**本节被以下章节引用**：
- [8.8 实战案例](./08-实战案例.md) —— Global Ref 泄漏实战
- 09 篇诊断 —— JNI Ref 监控

**本节引用**：
- [8.1 JNI Critical](./01-GC与JNI.md) —— JNI Critical
- 01 篇 1.1 可达性分析 —— GC Root 来源
