# 8.4 GC × Hook 框架

> **本节回答一个根本问题**：Hook 框架（Xposed / Frida / SandHook）怎么影响 GC？为什么必须适配 ART 读屏障？
>
> **答案**：**Hook 直接修改 ArtMethod 内存，绕过 ART 读屏障 → CC GC 移动对象后 Hook 失效或崩溃**。

---

## 一、Hook 框架的工作原理

### 8.4.1 Method Hook 的本质

```
Method Hook 的本质：

1. 替换 ArtMethod.entry_point_from_quick_compiled_code_
   - 原 entrypoint 指向 AOT 编译码
   - Hook 后指向自定义 stub
   - stub 调用 Java 回调方法

2. Hook 框架的类型
   - 字节码层：Javassist / ASM（不涉及 native）
   - Native 层：Xposed / Frida（直接修改内存）

3. Hook 的风险
   - 直接修改内存，绕过 GC 屏障
   - CC GC 移动 ArtMethod 后 Hook 失效
```

### 8.4.2 主流 Hook 框架对比

| 框架 | 原理 | ART 8+ 兼容 |
|:---|:---|:---|
| Xposed | 替换 ArtMethod.entrypoint | ❌ 旧版本不兼容 |
| LSPosed | Xposed 的分支，适配 ART | ✅ |
| Frida | 动态插桩 | ✅（12.x+） |
| SandHook | Inline Hook | ✅（2.x+） |
| Epic | Method Hook | ✅（1.x+） |
| Whalebook | 字节码层 Hook | ✅ |
| YAHFA | Method Hook | ✅ |

---

## 二、Hook 与 GC 的冲突

### 8.4.3 冲突的本质

```
Hook 框架绕过 ART 的 GC 屏障：

1. ART 的 CC GC 用读屏障
   - 业务线程读 ArtMethod 时
   - 读屏障检查 ArtMethod 是否被移动
   - 如果已移动，跳转到 to-space 新地址

2. Hook 框架直接修改 ArtMethod.entrypoint
   - 修改的是 from-space 的旧 ArtMethod
   - CC GC 复制 ArtMethod 到 to-space
   - from-space 旧 ArtMethod 失效

3. 后果
   - 业务线程调用 entrypoint
   - 通过栈引用找到 ArtMethod（from-space 旧地址）
   - 读屏障触发，跳转到 to-space 新地址
   - 新地址的 entrypoint 还是原始的（没被 Hook 修改）
   - → Hook 失效

4. 更严重后果
   - from-space 旧 ArtMethod 已被覆盖
   - 旧 entrypoint 指向野内存
   - 业务线程调用 → SIGSEGV
```

### 8.4.4 Hook 框架的适配模式

```
Hook 框架适配 ART 8+ 的正确模式：

1. 用 ReadBarrier::BarrierForRoot 获取最新地址
2. 修改 entrypoint
3. 写屏障保护
4. 缓存最新地址（避免每次读屏障）

伪代码：
ArtMethod* method = ReadBarrier::BarrierForRoot(method);
method->entry_point_from_quick_compiled_code_ = new_entrypoint;
WriteBarrier::WriteField(method, ...);
```

---

## 三、Hook 框架崩溃案例

### 8.4.5 案例 1：Xposed 旧版本崩溃

```
场景：
- Android 8.0 + Xposed v90（适配 ART 7.x）
- App 启动后立即崩溃

崩溃信息：
java.lang.RuntimeException: ArtMethod entrypoint invalid

根因：
- Xposed 直接修改 ArtMethod.entrypoint
- 绕过读屏障
- CC GC 移动 ArtMethod → Xposed 修改失效
- 业务线程调用 → 崩溃
```

### 8.4.6 案例 2：Frida 11 崩溃

```
场景：
- Android 8.0 + Frida 11.0
- 注入业务方法后崩溃

崩溃信息：
SIGSEGV in artReadBarrier

根因：
- Frida 的 ART 后端直接修改 ArtMethod
- 绕过读屏障
- from-space 已被 GC 回收
- 业务线程调用 → SIGSEGV
```

### 8.4.7 案例 3：SandHook 旧版本崩溃

```
场景：
- Android 9.0 + SandHook 1.x
- 长时间运行后偶发崩溃

崩溃信息：
IllegalAccessError: Method ... was not hooked

根因：
- SandHook inline hook 直接写内存
- 绕过读屏障
- CC GC 移动 ArtMethod → hook 失效
```

---

## 四、Hook 框架的适配方案

### 8.4.8 适配方案 1：用 ReadBarrier

```cpp
// ✅ 正确：用读屏障获取最新地址
void HookMethod(JNIEnv* env, jobject method, void* new_entrypoint) {
    // 1. 获取 ArtMethod 指针
    ArtMethod* art_method = (ArtMethod*)env->FromReflectedMethod(method);
    
    // 2. 用读屏障获取最新地址
    art_method = ReadBarrier::BarrierForRoot(art_method);
    
    // 3. 修改 entrypoint
    void* old_entry = art_method->entry_point_from_quick_compiled_code_;
    art_method->entry_point_from_quick_compiled_code_ = new_entrypoint;
    
    // 4. 写屏障保护
    WriteBarrier::WriteField(art_method, 
        ArtMethod::EntryPointOffset(), 
        (mirror::Object*)new_entrypoint);
}
```

### 8.4.9 适配方案 2：缓存最新地址

```cpp
// 缓存 ArtMethod 指针 + 自愈机制
class HookedMethod {
    ArtMethod* method_;  // 缓存的 ArtMethod 指针
    
public:
    ArtMethod* GetMethod() {
        // 每次都走读屏障（自愈）
        method_ = ReadBarrier::BarrierForRoot(method_);
        return method_;
    }
};
```

### 8.4.10 适配方案 3：用 ART 公开 API

```cpp
// ART 13+ 提供公开 API
art::ArtMethod::SetEntryPointFromQuickCompiledCode(new_entrypoint);
// 内部自动处理读屏障 + 写屏障

// 或者
art::ArtMethod::SetEntryPointFromInterpreterCode(new_entrypoint);
```

---

## 五、Hook 框架的工程影响

### 8.4.11 Hook 框架对 ART 兼容性的演进

| ART 版本 | Hook 兼容性 | 推荐 Hook 框架 |
|:---|:---|:---|
| ART 5-7 | 良好 | Xposed v90 / Frida 11 |
| ART 8-9 | 旧版不兼容 | LSPosed / Frida 12+ |
| ART 10-12 | 部分兼容 | LSPosed / Frida 13+ |
| ART 13+ | 完全支持 | LSPosed / Frida 14+ |

### 8.4.12 Hook 框架的选型建议

```
Hook 框架选型建议：

1. 业务 App 集成测试
   - 用 LSPosed / Frida 14+
   - 避免用旧版本

2. 逆向 / 安全测试
   - 用 Frida
   - 持续更新版本

3. 字节码层 Hook
   - 用 Whalebook
   - 不涉及 native，兼容性好

4. 集成第三方 Hook
   - 确认 ART 版本兼容性
   - 在 ART 13+ 上测试
```

### 8.4.13 Hook 框架的工程监控

```bash
# 1. 看 Hook 框架的崩溃率
adb logcat -s "AndroidRuntime" | grep "FATAL.*Hook"

# 2. 看 ART Invariant 违反
adb logcat -s "art" | grep "Invariant"

# 3. 看 ART 调试日志
adb shell setprop dalvik.vm.image-dex2oat-flags --debug
```

---

## 六、Hook 与 GC 的源码索引

### 8.4.14 核心源码路径

```
art/runtime/read_barrier.h               # ReadBarrier
art/runtime/read_barrier.cc              # ReadBarrier 实现
art/runtime/art_method.h                # ArtMethod 类
art/runtime/entrypoints/entrypoint_utils.h  # EntryPoint 工具
external/lsposed/                        # LSPosed
external/frida/                          # Frida
external/sandhook/                       # SandHook
```

### 8.4.15 Hook 框架的源码位置

| 框架 | 路径 |
|:---|:---|
| LSPosed | `external/lsposed/` |
| Frida | `external/frida/` |
| SandHook | `external/sandhook/` |
| Epic | `external/epic/` |

---

## 七、本节小结

1. **Hook 直接修改 ArtMethod 内存**：绕过 ART 屏障
2. **CC GC 移动 ArtMethod → Hook 失效或崩溃**
3. **Hook 框架必须用 ReadBarrier::BarrierForRoot**
4. **Hook 框架版本必须适配 ART 版本**
5. **推荐用 LSPosed / Frida 14+ / Whalebook**

→ **理解 Hook 与 GC，就理解了"为什么 Android 8+ 升级时 Hook 框架要重写"**。

---

## 跨节引用

**本节被以下章节引用**：
- [8.8 实战案例](./08-实战案例.md) —— Hook 崩溃完整案例
- ART 大模块的 `08-Hook与ART` —— Hook 框架的 ART 适配

**本节引用**：
- 04 篇 4.7 实战案例 —— CC GC 下 Hook 兼容性
- 06 篇 Reference —— Cleaner 与 native 资源
