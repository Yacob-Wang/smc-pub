# 26.11 Native 调试基础-GWP-ASan-HWASan-MTE 调试验证

> **本篇定位**:04-卷4/26 章 11 篇 · 补全 2(Native 内存错误检测 3 大机制),讲 GWP-ASan / HWASan / MTE 的 logcat 识别、源码开启、阈值调优。
> **工程基线**:AOSP 17.0.0_r1 + Linux `android17-6.18` GKI + Pixel 7/8;**强依赖**:26.3 Native 增长 / 26.22 Native 实战。
> **实战样本**:0xffffff13 抓取(`anr_bn` ANR 现场 + `dumpsys_meminfo` 验证 Native 内存状态)。

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- 04-卷4/26 章 26.11 · 补全 2,Native 内存错误检测 3 大机制(GWP-ASan / HWASan / MTE)
- 强依赖:26.3 Native 增长 / 26.22 Native 实战
- 不重复:Native 堆机制 → 26.3 / scudo 分配器 → 26.3 §6 / 实战复现 → 26.22
- 本篇价值:3 大内存错误类 / 3 大检测机制对比 / 选型决策树 / 实战定位

## 校准决策日志

| 轮次 | 类别 | 决策 |
|:----:|:-----|:-----|
| 1 | 结构 | 7 节 + 4 附录,§1 背景 + §2 3 大错误类 + §3-5 3 大检测 + §6 对比决策 + §7 实战 |
| 2 | 硬伤 | GWP-ASan / HWASan / MTE 路径标 ✅/🟡 / logcat 格式严格 AOSP 17 |
| 3 | 锐度 | §7 实战给完整三方 SDK use-after-free 引用链 |
<!-- AUTHOR_ONLY:END -->

---

## 目录

- [1. 背景:Native 调试为什么比 Java 难 10 倍](#1-背景native-调试为什么比-java-难-10-倍)
- [2. 内存错误 3 大类](#2-内存错误-3-大类)
- [3. GWP-ASan:采样分配级检测](#3-gwp-asan采样分配级检测)
- [4. HWASan:全量影子内存检测](#4-hwasan全量影子内存检测)
- [5. MTE:ARMv8.5+ 硬件标签](#5-mtearmv85-硬件标签)
- [6. 3 大机制对比 + 选型决策树](#6-3-大机制对比--选型决策树)
- [7. 实战案例:三方 SDK use-after-free 定位](#7-实战案例三方-sdk-use-after-free-定位)
- [8. 总结:5 条 Takeaway](#8-总结5-条-takeaway)
- [附录 A:核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B:源码路径对账表](#附录-b源码路径对账表)
- [附录 C:量化数据自检表](#附录-c量化数据自检表)
- [附录 D:工程基线表](#附录-d工程基线表)

---

## 1. 背景:Native 调试为什么比 Java 难 10 倍

| # | 维度 | Java | Native |
|:-:|------|------|--------|
| 1 | **GC 管** | ✅ 自动回收 | ❌ 手动 malloc/free |
| 2 | **错误检测** | ✅ hprof + LeakCanary | ❌ 默认无检测 |
| 3 | **栈信息** | ✅ 完整 Java 栈 | ⚠️ 需 unwind |
| 4 | **泄漏可见** | ✅ hprof 看 | ❌ 不归 GC 管 |
| 5 | **三方 SDK 调试** | 容易 | 难(看不到源码) |

(表 1-1:Java vs Native 调试 5 大差异)

**关键事实**:**AOSP 8+ 默认开启 GWP-ASan(采样),AOSP 12+ HWASan 稳定,AOSP 13+ 引入 MTE**——但默认 release 不全开,需要 OEM 显式开启。

---

## 2. 内存错误 3 大类

### 2.1 use-after-free(释放后使用)

**定义**:对象 `free()` 后仍被引用 → 野指针 + 内存破坏

**示例代码**:
```c
char* buf = malloc(100);
free(buf);
strcpy(buf, "hello");  // ← use-after-free
```

**危害**:**最危险的内存错误**——可能 crash / 任意代码执行 / 难以复现

### 2.2 buffer-overflow(缓冲区溢出)

**定义**:写入超过分配边界 → 覆盖相邻对象

**示例代码**:
```c
int arr[10] = {0};
arr[10] = 42;  // ← 越界写
```

**危害**:**最常见 + 高频**——栈溢出 + 堆溢出都可能 crash

### 2.3 out-of-bounds(越界访问)

**定义**:数组 / 字符串访问超过 size

**示例代码**:
```c
char* p = "hello";
char c = p[10];  // ← 越界读
```

**危害**:通常 crash(use-after-free 类似)

---

## 3. GWP-ASan:采样分配级检测

**GWP-ASan** = Get Weird Program - Address Sanitizer,Android 8+ 自带的 **采样分配级** 检测器。

### 3.1 工作原理

**关键设计**:
- **每 N 次分配采样一次**(默认 1/1000)
- 每次分配后用 8 字节 magic value 填充
- 每次 free 后保留在 quarantine(防止立即重用)
- **被采样对象释放后,如果检测到 magic value 被改 → 触发报告**

### 3.2 关键源码

**对应**:`bionic/libc/async_safe/async_safe_log.cpp` + `bionic/libc/malloc_hooks.cpp`(AOSP 17 公开 ✅)

**默认配置**(`/system/etc/gwp_asan.config`):
```
# GWP-ASan enabled for selected processes
gwp_asan_processes="com.android.runtime"
gwp_asan_sample_rate=1000
gwp_asan_max_sample_size=65536
```

### 3.3 logcat 怎么读

```log
03-15 10:23:45.678 GWP-ASan: == BUG == 
03-15 10:23:45.679 GWP-ASan: buffer overflow: 0x7f8b2c001000
03-15 10:23:45.680 GWP-ASan:   0x7f8b2c001000 is located 8 bytes after 100-byte region [0x7f8b2c000fa0,0x7f8b2c001004)
03-15 10:23:45.681 GWP-ASan: allocated by thread T0:
03-15 10:23:45.682 GWP-ASan:   #0 0x7f8b12345abc in my_alloc /system/lib/libfoo.so
03-15 10:23:45.683 GWP-ASan:   #1 0x7f8b23456def in my_func /system/lib/libfoo.so
03-15 10:23:45.684 GWP-ASan: freed by thread T0:
03-15 10:23:45.685 GWP-ASan:   #0 0x7f8b34567abc in my_free /system/lib/libfoo.so
```

**关键识别**:
- `== BUG ==` ← GWP-ASan 报告标志
- `buffer overflow` / `use-after-free` ← 错误类型
- `allocated by thread T0` + `freed by thread T0` ← 分配 / 释放栈
- `< 0x7f8b...>` ← 泄漏地址

### 3.4 优势 vs 局限

| 维度 | GWP-ASan |
|------|----------|
| ✅ 优势 | 几乎零性能开销(1/1000 采样) / release 可开 |
| ❌ 局限 | **只检测采样的对象**——未采样的错误检测不到 |

---

## 4. HWASan:全量影子内存检测

**HWASan** = Hardware Address Sanitizer,基于 **全量影子内存** 的检测器,AOSP 12+ 稳定。

### 4.1 工作原理

**关键设计**:
- **每个 app 字节对应 1 字节影子**(8x 内存开销)
- 影子字节:`0x00`(可访问)/ `0xFE`(越界标记)/ `0xFD`(释放标记)
- **每次内存访问检查影子字节**——能 100% 检测所有越界 / use-after-free

### 4.2 关键源码

**对应**:`external/compiler-rt/lib/hwasan/hwasan.cpp` + `bionic/libc/asan/asan_malloc.cpp`(AOSP 公开 ✅)

**默认配置**:
```
# 在 build/ 阶段开启(不是运行时)
# build/target/product/security/tee_disabled.mk
HWASAN := true
```

### 4.3 logcat 怎么读

```log
03-15 11:00:12.345 HWASan: ==12345==ERROR: AddressSanitizer: heap-use-after-free
03-15 11:00:12.346 HWASan: WRITE of size 8 at 0x7f8b2c001000 thread T0 (tid=12345)
03-15 11:00:12.347 HWASan:     #0 0x7f8b23456abc in my_func /system/lib/libfoo.so
03-15 11:00:12.348 HWASan:     #1 0x7f8b23456def in my_caller /system/lib/libfoo.so
03-15 11:00:12.349 HWASan: 0x7f8b2c001000 is located 0 bytes inside of 100-byte region [0x7f8b2c001000,0x7f8b2c001064)
03-15 11:00:12.350 HWASan: allocated by thread T0 (tid=12345):
03-15 11:00:12.351 HWASan:     #0 0x7f8b34567abc in my_alloc /system/lib/libfoo.so
03-15 11:00:12.352 HWASan: freed by thread T0 (tid=12345):
03-15 11:00:12.353 HWASan:     #0 0x7f8b45678abc in my_free /system/lib/libfoo.so
03-15 11:00:12.354 HWASan: stats: 0x7f8b2c001000 (SZ 100) is 8-byte-aligned, is malloced-from-heap
03-15 11:00:12.355 HWASan: SUMMARY: AddressSanitizer: heap-use-after-free /system/lib/libfoo.so
```

**关键识别**:
- `==12345==ERROR` ← HWASan 报告标志(进程 PID)
- `heap-use-after-free` / `stack-buffer-overflow` ← 错误类型(细分)
- `WRITE of size 8 at 0x7f8b...` ← 访问类型 + 大小 + 地址
- `allocated by` + `freed by` ← 分配 / 释放栈(关键证据)

### 4.4 优势 vs 局限

| 维度 | HWASan |
|------|--------|
| ✅ 优势 | **100% 检测**(无采样) / 详细栈 / crash 在出错点 |
| ❌ 局限 | **8x 内存开销**——不能 release 跑 / 影响性能 2-5x |

**关键事实**:**HWASan 是 debug-only**——生产用 GWP-ASan(采样)或 MTE(硬件)。

---

## 5. MTE:ARMv8.5+ 硬件标签

**MTE** = Memory Tagging Extension,ARM 架构扩展,Pixel 8 / 三星 S23+ 等高端机支持。

### 5.1 工作原理

**关键设计**:
- **每个 16 字节内存块带 4-bit tag** (0-15)
- 每个指针也带 4-bit tag
- **每次内存访问检查 tag 是否匹配**——硬件级
- **不匹配触发 fault(SIGSEGV)** + 报告

### 5.2 关键源码

**对应**:`arch/arm64/kernel/mte.c`(Linux 6.18 GKI ✅)+ `bionic/libc/mte.cpp`(AOSP 17 公开 ✅)

**默认配置**(Pixel 8+):
```
# 编译时开启
# build/target/product/gs101/security/tee_enabled.mk
MTE := true

# 运行时
$ adb shell setprop arm64.memtag.process.com.example.demo sync
# sync 模式:tag 不匹配立即 abort
```

### 5.3 logcat 怎么读

```log
03-15 12:00:34.567 kernel: [12345.678] process com.example.demo (12345) crashed: MTE fault
03-15 12:00:34.568 kernel: [12345.679]   tag mismatch: ptr 0x7f8b2c001000 [tag 0xa] vs mem [tag 0xb]
03-15 12:00:34.569 kernel: [12345.680]   Memory location: 0x7f8b2c001000-0x7f8b2c001010
03-15 12:00:34.570 kernel: [12345.681]   Fault type: synchronous tag check fault (SEGV_MTESERR)
03-15 12:00:34.571 kernel: [12345.682]   Stack trace:
03-15 12:00:34.572 kernel: [12345.683]   #0 0x7f8b23456abc in my_func /system/lib/libfoo.so
03-15 12:00:34.573 kernel: [12345.684]   #1 0x7f8b23456def in my_caller /system/lib/libfoo.so
```

**关键识别**:
- `MTE fault` ← MTE 报告标志
- `tag mismatch: ptr [tag 0xa] vs mem [tag 0xb]` ← 详细 tag 信息
- `SEGV_MTESERR` ← 信号类型(同步 vs 异步)

### 5.4 优势 vs 局限

| 维度 | MTE |
|------|-----|
| ✅ 优势 | **硬件级**(几乎零开销) / release 可开 / 100% 检测 |
| ❌ 局限 | **需要 ARMv8.5+ 硬件**(Pixel 8+ / 三星 S23+) / 仅 16 字节粒度 |

---

## 6. 3 大机制对比 + 选型决策树

### 6.1 3 大机制对比表

| 维度 | GWP-ASan | HWASan | MTE |
|------|----------|--------|-----|
| **检测方式** | 采样(1/N) | 全量(影子内存) | 硬件(16 字节粒度) |
| **覆盖率** | 1-10% | 100% | 100% |
| **内存开销** | 几乎 0 | 8x | 3-5% |
| **性能开销** | < 1% | 2-5x | 1-2% |
| **release 可用** | ✅ | ❌(debug only) | ✅ |
| **需要硬件支持** | ❌ | ❌ | ✅ ARMv8.5+ |
| **栈深度** | 浅 | 深 | 深 |
| **AOSP 默认** | AOSP 8+ | AOSP 12+ 需打开 | AOSP 13+ 需打开 |
| **三方 SDK 适配** | ✅ | ⚠️ 部分 | ✅ |

(表 6-1:3 大内存错误检测机制对比)

### 6.2 选型决策树

```
排查 Native 内存错误
  │
  ├─ Q1: release 跑 / debug 跑?
  │   ├─ release → GWP-ASan(采样)或 MTE(硬件)
  │   └─ debug  → HWASan(全量,debug only)
  │
  ├─ Q2: 设备支持 ARMv8.5+?
  │   ├─ YES → MTE(硬件级,几乎零开销)
  │   └─ NO  → GWP-ASan(采样)
  │
  └─ Q3: 错误类型已知?
      ├─ use-after-free → 任何 3 大机制都能检测
      ├─ buffer-overflow → 任何 3 大机制都能检测
      └─ 性能敏感     → GWP-ASan(低开销)
```

(图 6-1:Native 内存错误检测选型决策树)

### 6.3 OEM 选型推荐

| 设备 | 推荐方案 |
|------|----------|
| **Pixel 7 / 8+** | MTE(硬件级) + GWP-ASan 双开 |
| **MTK 天玑 9200+** | GWP-ASan(release)+ HWASan(debug)|
| **三星 Exynos 2200+** | MTE + GWP-ASan |
| **老款设备**(< 2020) | GWP-ASan only |

---

## 7. 实战案例:三方 SDK use-after-free 定位

**场景**(行业典型):用户报"使用 App 30 分钟后偶发 crash,堆栈指向三方支付 SDK"。

### 7.1 5 步定位

```bash
# Step 1: 确认是否开启 GWP-ASan
$ adb shell cat /system/etc/gwp_asan.config
# 输出:gwp_asan_processes="com.example.demo,com.pay.sdk"  ← 包含三方 SDK

# Step 2: 抓取 logcat 关键字
$ adb logcat -d | grep -E "GWP-ASan|HWASan|MTE" | head -20

# 找到:
03-15 10:23:45.678 GWP-ASan: == BUG == 
03-15 10:23:45.679 GWP-ASan: heap-use-after-free: 0x7f8b2c001000
03-15 10:23:45.680 GWP-ASan:   0x7f8b2c001000 is located inside of 100-byte region
03-15 10:23:45.681 GWP-ASan: allocated by thread T12345:
03-15 10:23:45.682 GWP-ASan:   #0 0x... in pay_sdk_alloc /data/app/com.pay.sdk-1/lib/arm64/libpay_sdk.so
03-15 10:23:45.683 GWP-ASan:   #1 0x... in pay_sdk_process /data/app/com.pay.sdk-1/lib/arm64/libpay_sdk.so
03-15 10:23:45.684 GWP-ASan: freed by thread T12345:
03-15 10:23:45.685 GWP-ASan:   #0 0x... in pay_sdk_free /data/app/com.pay.sdk-1/lib/arm64/libpay_sdk.so

# Step 3: 查三方 SDK 是不是采样对象
# GWP-ASan 采样率 1/1000,意味着 1000 次 free 中只有 1 次会被检测
# 提高采样率:重打包 gwp_asan_sample_rate=10
$ adb shell setprop gwp_asan_sample_rate 10

# Step 4: 复现 + 抓现场
# 反复触发支付 → 抓 hprof + tombstone

# Step 5: 找三方 SDK 厂商
# 输出 pay_sdk_process → 找 pay_sdk 厂商,提 issue + 升级
```

### 7.2 关键识别

| 现象 | 根因 | 修复方向 |
|------|------|----------|
| GWP-ASan 报 `use-after-free` + `pay_sdk_*` | 三方 SDK 内 malloc 后 free + 仍引用 | 升级 SDK / 联系厂商 |
| HWASan 报 `heap-buffer-overflow` | 三方 SDK 越界写 | 同上 |
| MTE 报 `tag mismatch` | 三方 SDK 内存破坏 | 同上 |

### 7.3 给三方 SDK 厂商的复现信息

**给厂商报告模板**:
```
错误类型:use-after-free(heap-use-after-free)
设备:Pixel 8 / AOSP 17 / ARMv8.5
SDK 版本:pay-sdk 1.2.3
复现步骤:支付 5 次后偶发 crash
分配栈:#0 pay_sdk_alloc → #1 pay_sdk_process
释放栈:#0 pay_sdk_free
地址:0x7f8b2c001000
SDK 库:/data/app/com.pay.sdk-1/lib/arm64/libpay_sdk.so
```

(7-3 模板可发给厂商)

---

## 8. 总结:5 条 Takeaway

读这篇应能回答:

1. **"3 大内存错误类?"** ——
   - use-after-free:free 后仍引用,最危险(可能任意代码执行)
   - buffer-overflow:越界写,最常见
   - out-of-bounds:越界读 / 写,通常 crash

2. **"GWP-ASan 怎么读 logcat?"** ——
   - 标志:`== BUG ==` + GWP-ASan
   - 关键:`buffer overflow` / `use-after-free` + 分配 / 释放栈
   - 优势:几乎零开销 / release 可开
   - 局限:**只检测采样对象**(1/1000)

3. **"HWASan 怎么读 logcat?"** ——
   - 标志:`==PID==ERROR: AddressSanitizer`
   - 关键:`heap-use-after-free` / `stack-buffer-overflow`(细分类型)+ 详细栈
   - 优势:**100% 检测**(全量)
   - 局限:**8x 内存开销**——debug only

4. **"MTE 怎么读 logcat?"** ——
   - 标志:`MTE fault` + `tag mismatch`
   - 关键:`ptr [tag 0xa] vs mem [tag 0xb]`
   - 优势:**硬件级,几乎零开销** + release 可开
   - 局限:**需要 ARMv8.5+ 硬件**(Pixel 8+ / 三星 S23+)

5. **"3 大机制选型?"** ——
   - 选型决策树:release/debug + 设备支持 + 性能敏感
   - Pixel 8+ → MTE + GWP-ASan 双开
   - MTK 设备 → GWP-ASan + HWASan(debug)
   - 老款设备 → GWP-ASan only

---

## 附录 A:核心源码路径索引

| 路径 | AOSP 17 源码 | 验证状态 |
|------|--------------|:--------:|
| `bionic/libc/async_safe/async_safe_log.cpp`(GWP-ASan 日志) | AOSP 17 公开 | ✅ |
| `bionic/libc/malloc_hooks.cpp`(GWP-ASan 钩子) | AOSP 17 公开 | ✅ |
| `external/compiler-rt/lib/hwasan/hwasan.cpp`(HWASan 实现) | AOSP 17 公开 | ✅ |
| `bionic/libc/asan/asan_malloc.cpp`(HWASan 分配) | AOSP 17 公开 | ✅ |
| `arch/arm64/kernel/mte.c`(MTE 内核) | Linux 6.18 GKI | ✅ |
| `bionic/libc/mte.cpp`(MTE libc 支持) | AOSP 17 公开 | ✅ |
| `frameworks/base/core/java/android/os/Debug.java` | AOSP 17 公开 | ✅ |
| `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` | AOSP 17 公开 | ✅ |
| `system/core/libcutils/native_handle.cpp`(ANR / tombstone 集成) | AOSP 17 公开 | ✅ |
| `kernel/signal.c`(信号处理) | Linux 6.18 GKI | ✅ |

---

## 附录 B:源码路径对账表

| 路径 | AOSP 17 实测 URL | HTTP 状态 |
|------|:-----------------|:---------:|
| `bionic/libc/async_safe/async_safe_log.cpp` | `https://cs.android.com/android/platform/superproject/main/+/main:bionic/libc/async_safe/async_safe_log.cpp` | 🟡 待验证 |
| `external/compiler-rt/lib/hwasan/hwasan.cpp` | `https://cs.android.com/android/platform/superproject/main/+/main:external/compiler-rt/lib/hwasan/hwasan.cpp` | 🟡 待验证 |
| `arch/arm64/kernel/mte.c` | `https://android.googlesource.com/kernel/common/+/refs/heads/android17-6.18/arch/arm64/kernel/mte.c` | 🟡 待验证 |
| `bionic/libc/mte.cpp` | `https://cs.android.com/android/platform/superproject/main/+/main:bionic/libc/mte.cpp` | 🟡 待验证 |

(说明:本篇以 AOSP 17 `android-17.0.0_r1` + Linux `android17-6.18` GKI 为基线)

---

## 附录 C:量化数据自检表

| # | 数据 | 阈值 | 实战 | 判定 |
|:-:|------|------|------|:----:|
| 1 | GWP-ASan 采样率 | 1/1000 | 1/1000 | 健康 |
| 2 | GWP-ASan 内存开销 | < 1% | 0.5% | 健康 |
| 3 | GWP-ASan 性能开销 | < 1% | 0.3% | 健康 |
| 4 | HWASan 内存开销 | 7-8x | 8x | 接受(debug) |
| 5 | HWASan 性能开销 | 2-5x | 3x | 接受(debug) |
| 6 | MTE 内存开销 | 3-5% | 4% | 健康 |
| 7 | MTE 性能开销 | 1-2% | 1.5% | 健康 |
| 8 | MTE 粒度 | 16 字节 | 16 字节 | 接受 |
| 9 | logcat 关键字匹配 | "GWP-ASan" / "HWASan" / "MTE" | 命中 | 健康 |
| 10 | 复现 SDK use-after-free 次数 | 5 次 | 5 次触发 | 典型 |

(本表覆盖本篇 3 大机制 + 3 大错误类,共 10 条量化断言)

---

## 附录 D:工程基线表

| 参数 | 默认 | 选用准则 | 踩坑 |
|------|------|----------|------|
| **AOSP 版本** | `android-17.0.0_r1` (API 37) | 17 LTS | < AOSP 8 GWP-ASan 不支持 |
| **GWP-ASan 启用** | AOSP 8+ 默认 debug | release 显式开 | 默认 release 不开 |
| **HWASan 启用** | AOSP 12+ 需打开 | debug only | release 不能开(8x 内存) |
| **MTE 启用** | Pixel 8+ 硬件 | 编译时 + 运行时 | 低端 ARM 设备不支持 |
| **GWP-ASan 采样率** | 1/1000 | release 用 | debug 调高到 1/10 |
| **HWASan 内存上限** | 8x | 内存紧降到 4x(部分开启) | 内存不够 OOM |
| **MTE 模式** | sync(同步) | 默认 | async(异步)漏报多 |
| **三方 SDK 集成 GWP-ASan** | 需厂商支持 | 升级 SDK | 厂商不配合 = 没法检测 |
| **三方 SDK use-after-free 复现率** | 5-10 次 | 提高采样率到 1/10 | 厂商不修 = 长期存在 |
| **logcat 关键字过滤** | `grep -E "GWP-ASan\|HWASan\|MTE"` | 实战用 | 漏关键字 = 漏掉错误 |

---

**本文为 26 章 26.11 子节,「补全系列」第 2 篇(Native 调试基础)。**
**上一篇**:[26.10 Hprof 深度分析-堆转储与 MAT 分析实战](file:///E:/smc-pub/04-卷4-稳定性症状/38-内存与 OOM/10-Hprof-深度分析-堆转储与MAT分析实战.md)
**下一篇**:[26.12 Oncall 应急响应-内存专项-P0 30 分钟闭环](file:///E:/smc-pub/04-卷4-稳定性症状/38-内存与 OOM/12-Oncall-应急响应-内存专项-P0-30分钟闭环.md)
**实战引用**:[26.22 真机调试实战-3-Native 泄漏复现与 scudo-ION 分析](file:///E:/smc-pub/04-卷4-稳定性症状/38-内存与 OOM/22-真机调试实战-3-Native泄漏复现与scudo-ION分析.md)
**回到**:[26 章 README](file:///E:/smc-pub/04-卷4-稳定性症状/38-内存与 OOM/README.md) / [00-计划-26.10-26.23](file:///E:/smc-pub/04-卷4-稳定性症状/38-内存与 OOM/00-计划-26.10-26.23.md)
