# 4.4 Invariant：不变量与正确性

> **本节回答一个根本问题**：CC GC 怎么保证并发移动对象的正确性？什么是不变量（Invariant）？
>
> **答案**：**弱三色不变式 + GrayStatusImmuneWord + 读屏障** —— 保证并发场景下不会漏标。
>
> **理解本节，就理解了 CC GC 的"正确性数学基础"** —— 是 ART 8.0+ 稳定运行的保证。

---

## 一、不变量（Invariant）的定义

### 4.4.1 不变量 = GC 正确性的数学表达

**不变量（Invariant）**是 GC 标记过程中必须维护的不变条件。如果不变量被破坏，GC 可能漏标（漏活对象）。

CC GC 维护 **弱三色不变式**（Weak Tri-Color Invariant）。

### 4.4.2 弱三色不变式的形式化

```
Weak Tri-Color Invariant：
  黑色对象可以引用白色对象，
  但白色对象必须被某个灰色对象可达（"被保护可达"）。

形式化：
  ∀ white obj:
    ∃ gray obj G:
      G reaches obj (直接引用或间接引用)
```

### 4.4.3 弱三色不变式的含义

```
允许的状态：
  Black → White（黑色直接引用白色）
  但 White 必须被某个 Gray 可达

不允许的状态：
  White 完全孤立（没有任何 Gray 引用它）
```

### 4.4.4 弱三色不变式的形式化证明

**命题**：维护弱三色不变式，CC GC 不会漏标。

**证明**（反证法）：
1. 假设漏标：白色对象 C 被回收
2. 弱三色不变式要求：C 被某个灰色对象 G 可达
3. C 在 GC 结束时仍是白色 → G 染黑时未扫描 C 的引用
4. 矛盾：除非业务线程在 G 染黑前执行 `G.field = null`（删除引用）
5. 但读屏障保证：业务线程读 C 时，C 已被移动到 to-space → C 不再是白色
6. 矛盾 → 漏标不可能

---

## 二、CC GC 的不变量实现

### 4.4.5 CC GC 的不变式维护

CC GC 通过 **读屏障** + **对象头标记** + **Mark Bitmap** 共同维护弱三色不变式：

```cpp
// art/runtime/gc/collector/concurrent_copying.h
class ConcurrentCopying {
 private:
    // 1. 弱三色不变式
    //    黑色对象允许引用白色对象
    //    但白色对象必须被灰色对象可达
    
    // 2. 通过读屏障维护：
    //    - 业务线程读 from-space 对象时，读屏障更新指针
    //    - 业务线程读 to-space 对象时，无需处理
    
    // 3. 通过对象头标记追踪对象状态：
    //    - gray: 灰色（待处理）
    //    - black: 黑色（已处理）
    //    - white: 白色（未处理）
};
```

### 4.4.6 GrayStatusImmuneWord 详解

**GrayStatusImmuneWord** 是 ART 中实现不变式的关键常量：

```cpp
// art/runtime/gc/collector/concurrent_copying.h
static constexpr uint32_t kGrayStatusImmuneWord = 0xFEEDDEAD;

// 含义：
// - Gray 状态的对象免疫读屏障检查
// - 当对象被标记为 Gray 时，其 mark word 设置为 kGrayStatusImmuneWord
// - 读屏障检查到 mark word = kGrayStatusImmuneWord 时，直接返回（无需处理）
```

### 4.4.7 对象头标记的状态机

```
对象状态转换：

白色（White）
  │
  │ 标记（Mark）
  ▼
灰色（Gray）← 标记 mark word = kGrayStatusImmuneWord
  │
  │ 扫描完成
  ▼
黑色（Black）← mark word 包含 forwarding address

---

详细状态机：

White
  - 初始状态
  - mark word = 普通值
  - 还未被 GC 访问

Gray
  - mark word = kGrayStatusImmuneWord
  - 已被 GC 访问，待扫描其引用
  - 业务线程读 Gray 对象时，读屏障"免疫"（直接返回）

Black
  - mark word 包含 forwarding address（如果被移动到 to-space）
  - 已被 GC 完整扫描

Self-Healed
  - 在 to-space 中
  - mark word 已更新为新地址
  - 读屏障快速路径
```

### 4.4.8 Mark Bitmap 与不变式

CC GC 用 Mark Bitmap 记录对象是否被标记：

```cpp
// art/runtime/gc/collector/concurrent_copying.h
class ConcurrentCopying {
 private:
    // Mark Bitmap（与 CMS 共用一套基础设施）
    std::unique_ptr<accounting::ContinuousSpaceBitmap> mark_bitmap_;
    
    // 标记对象为 Gray
    void MarkObject(mirror::Object* obj) {
        if (!mark_bitmap_->Set(obj)) {
            return;  // 已被标记
        }
        
        // 设置 mark word 为 Gray 状态
        obj->SetMarkWord(kGrayStatusImmuneWord);
        
        // 加入 mark stack
        mark_stack_->Push(obj);
    }
    
    // 扫描 Gray 对象后标记为 Black
    void ScanAndMarkBlack(mirror::Object* obj) {
        // 扫描 obj 的引用
        obj->VisitReferences([this](mirror::Object* ref) {
            if (ref != nullptr) {
                MarkObject(ref);  // 标记引用的对象
            }
        });
        
        // 复制 obj 到 to-space
        CopyObject(obj);
        
        // obj 变为 Black（在 to-space）
    }
};
```

---

## 三、不变式的形式化验证

### 4.4.9 不变式的形式化定义

```cpp
// art/runtime/gc/collector/concurrent_copying.h
// 不变式的代码表达

class ConcurrentCopying {
 public:
    // 不变式检查（用于 ART 调试模式）
    bool VerifyInvariant() {
        // 1. 所有 GC Root 引用的对象都已标记
        for (mirror::Object* root : GetRoots()) {
            if (!IsMarked(root)) {
                LOG(FATAL) << "Invariant violated: root not marked";
                return false;
            }
        }
        
        // 2. 所有 Mark Bitmap 标记的对象都已正确处理
        // ...
        
        // 3. 所有 from-space 对象都有 forwarding address 或被回收
        // ...
        
        return true;
    }
};
```

### 4.4.10 不变式的实时检查

ART 14+ 引入了 **invariant checking** 模式：

```bash
# 启用不变式检查（仅调试）
adb shell setprop dalvik.vm.image-dex2oat-flags --debug

# 看不变式违反日志
adb logcat -s "art" | grep "Invariant"
# 输出示例：
# art : Invariant verified after Copying phase
# art : FATAL: Invariant violated at line 12345
```

### 4.4.11 不变式违反的修复

**不变式违反的常见原因**：
1. **Hook 框架绕过读屏障**（详见 4.7）
2. **JNI 直接修改对象字段**
3. **Unsafe 操作**
4. **第三方库的 bug**

**不变式违反的后果**：
- 漏标（漏活对象）
- 业务线程访问已回收对象
- 崩溃 / 内存错误

**修复策略**：
1. 升级到 ART 13+（有 JIT 代码校验）
2. 禁用绕过读屏障的代码
3. 用 ART 调试模式定位违规点

---

## 四、不变式与 CMS 的对比

### 4.4.12 不变式类型对比

| GC | 不变式 | 屏障 | 性能 |
|:---|:---|:---|:---|
| **CMS** | 强三色不变式 | 写屏障 | STW 50ms+ |
| **CC GC** | 弱三色不变式 | 读屏障 | STW < 5ms |

### 4.4.13 强三色 vs 弱三色

```
强三色不变式（CMS）：
  黑色对象不许引用白色对象
  → 每次黑色对象断开引用，写屏障要重新染灰
  → STW 阶段（Remark）要重新扫描所有 dirty 对象

弱三色不变式（CC）：
  黑色对象可引用白色对象，但白色必须被灰色保护
  → 读屏障 + 自愈指针处理对象移动
  → STW 阶段（Initialize + Reclaim）只扫描栈 + 切换空间
```

### 4.4.14 不变式的工程权衡

| 维度 | 强三色不变式 | 弱三色不变式 |
|:---|:---|:---|
| **屏障开销** | 写屏障（少） | 读屏障（多） |
| **STW 时间** | 长（50ms+） | 短（< 5ms） |
| **内存开销** | 小 | 中（双空间） |
| **碎片化** | 高 | 无 |
| **实现复杂度** | 中 | 高 |

→ **CC GC 选择弱三色不变式：牺牲运行时换 STW 时间**。

---

## 五、Invariant 与并发安全

### 4.4.15 多线程并发的不变式

CC GC 是多线程并发标记 + 复制，不变式必须在多线程下维护：

```cpp
// 多线程并发标记
class ConcurrentCopying {
    void ConcurrentMarkingPhase() {
        // 多线程并行扫描 mark stack
        for (int i = 0; i < num_gc_threads_; i++) {
            gc_threads_[i] = std::thread(this {
                while (!mark_stack_->IsEmpty()) {
                    mirror::Object* obj = mark_stack_->Pop();  // 线程安全
                    
                    // 复制 + 扫描
                    mirror::Object* new_obj = CopyObject(obj);
                    new_obj->VisitReferences([this](mirror::Object* ref) {
                        if (ref != nullptr) {
                            MarkObject(ref);  // 线程安全（CAS）
                        }
                    });
                }
            });
        }
    }
};
```

### 4.4.16 CAS 在不变式维护中的作用

```cpp
// 标记对象的 CAS 实现
bool MarkObject(mirror::Object* obj) {
    // 1. CAS 检查 + 设置 mark bit
    if (mark_bitmap_->TestAndSet(obj)) {
        return false;  // 已被标记
    }
    
    // 2. 设置 mark word 为 Gray 状态
    uint32_t old_mark_word = obj->GetMarkWord();
    uint32_t new_mark_word = kGrayStatusImmuneWord;
    
    // 3. CAS 设置 mark word
    while (!CAS(&obj->mark_word_, old_mark_word, new_mark_word)) {
        old_mark_word = obj->GetMarkWord();
        // 重试
    }
    
    // 4. 加入 mark stack
    mark_stack_->Push(obj);
    
    return true;
}
```

### 4.4.17 业务线程与 GC 线程的协作

```
业务线程 T1                          GC 线程
  │                                    │
  │ 读 obj.field                       │
  │ → 触发读屏障                       │
  │ → 检查 mark word                   │
  │                                    │ 复制 obj 到 to-space
  │                                    │ 设置 forwarding address
  │ 读屏障发现已移动                   │
  │ → 更新指针到新地址（自愈）          │
  │                                    │
  │ 后续访问 obj.field                 │
  │ → 已自愈 → 快速路径                │
```

---

## 六、不变式的工程价值

### 4.4.18 不变式的意义

**数学意义**：不变式是 GC 正确性的形式化保证。

**工程意义**：维护不变式需要权衡屏障开销和 STW 时间。

**ART 选择**：
- Android 5-7：CMS（强三色 + 写屏障）
- Android 8-9：CC GC（弱三色 + 读屏障）
- Android 10+：GenCC（CC + 分代优化）

### 4.4.19 不变式违反的真实案例

**案例 1**：Android 8.0 + Frida 早期版本

```
场景：Frida 注入 native 代码修改 ArtMethod
症状：ART 崩溃 "Invariant violated"
根因：Frida 绕过了读屏障，ArtMethod 被错误回收
修复：Frida 升级到 12.x（支持 ART 8+ 读屏障）
```

**案例 2**：Xposed 旧版本

```
场景：Xposed 框架在 ART 8.0 上崩溃
症状：app 启动后立即崩溃
根因：Xposed 直接修改 ArtMethod.entrypoint，绕过读屏障
修复：升级到 LSPosed（适配 ART 8+ 读屏障）
```

**案例 3**：第三方 Native 库

```
场景：第三方 .so 通过 JNI 直接修改对象字段
症状：偶发性崩溃
根因：JNI 代码绕过读屏障，间接导致不变式违反
修复：用 JNI 接口替代直接内存访问
```

---

## 七、不变式的源码索引

### 4.4.20 核心源码路径

```
art/runtime/gc/collector/concurrent_copying.h   # ConcurrentCopying 类
art/runtime/gc/collector/concurrent_copying.cc  # CC GC 实现
art/runtime/gc/collector/concurrent_copying.h   # kGrayStatusImmuneWord
art/runtime/read_barrier.h                      # 读屏障实现不变式
art/runtime/gc/accounting/space_bitmap.h        # Mark Bitmap
```

### 4.4.21 关键常量

```cpp
// art/runtime/gc/collector/concurrent_copying.h
static constexpr uint32_t kGrayStatusImmuneWord = 0xFEEDDEAD;

// 含义：Gray 状态的对象免疫读屏障检查
// 这是 ART 故意选择的特殊值，便于快速判断
```

---

## 八、本节小结

1. **CC GC 维护弱三色不变式**：黑色可引用白色，但白色必须被灰色保护
2. **读屏障 + GrayStatusImmuneWord + Mark Bitmap** 共同维护不变式
3. **不变式是 CC GC 正确性的数学基础**
4. **Hook / JNI / Unsafe 可能破坏不变式**
5. **ART 14+ 引入不变式实时检查**

→ **理解不变式，就理解了 CC GC 为什么能正确地并发移动对象**。

---

## 跨节引用

**本节被以下章节引用**：
- [4.7 实战案例](./07-实战案例.md) —— Hook 框架破坏不变式的案例
- 08 篇横切 —— GC × Hook
- [01 篇 1.2 三色不变式](../01-基础理论/02-三色标记不变式.md) —— 不变式理论

**本节引用**：
- [4.1 核心思想](./01-CC核心思想.md) —— 弱三色不变式
- [4.3 读屏障机制](./03-读屏障机制.md) —— 读屏障维护不变式
