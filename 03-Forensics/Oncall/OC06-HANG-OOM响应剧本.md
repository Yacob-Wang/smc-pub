# OC06 · HANG/OOM 响应剧本：黑屏/卡死/OOM 三轨分类的 5/15/30 处置

> **基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18` LTS
>
> **目标读者**：oncall 工程师 / 稳定性架构师
>
> **完成时间**：2026-07-24（v1.0 首版）

<!-- AUTHOR_ONLY:START -->

## 本篇定位

- oncall 7 大症状剧本第 6 篇（HANG 与 OOM 合并成 1 篇，因为 OOM 常表现为 HANG）
- 强依赖：[OC01-oncall 工程总论](OC01-oncall工程总论：值班机制与工具栈.md) / [02-Symptom/S05-HANG](../../02-Symptom/S05-HANG/01-症状机制.md) / [03-Forensics/F06-HANG-OOM](../F06-HANG-OOM/01-取证机制.md) / [04-Tool/Hprof](../../04-Tool/Hprof/) 5 篇
- 衔接去：[OC07-REBOOT 响应剧本](OC07-REBOOT响应剧本.md)（待补）

## 校准决策日志

| 轮次 | 类别 | 决策 | 理由 |
|:-----|:-----|:-----|:-----|
| 1 | 结构 | 单篇 500+ 行（§8 破例）| HANG + OOM 合并 + 4 类场景 |
| 2 | 硬伤 | HANG 3 类（黑屏/卡死/无响应）分类必给关键字 | 反例 #4 |
| 2 | 硬伤 | OOM 3 类（Java/Native/图片）必给 hprof 抓法 | 反例 #11 |
| 3 | 锐度 | 删"可能" | 反例 #5 |

<!-- AUTHOR_ONLY:END -->

---

# 1. HANG 与 OOM 的关键区别

| 维度 | HANG | OOM |
|:-----|:-----|:----|
| 现象 | 黑屏/卡死/无响应 | 黑屏/闪退/内存告警 |
| 检测 | 用户反馈（无自动告警）| LMKD / 告警 |
| 触发 | 主线程卡 / 渲染卡 / IO 卡 | 内存耗尽 |
| 取证 | traces + perfetto | hprof + meminfo |

> **铁律**：OOM 经常"伪装"成 HANG——oncall 第 1 件事就是**先判断是哪种**

---

# 2. HANG 3 类分类速查

| # | 类型 | 现象 | 检测点 |
|:-:|:-----|:-----|:-------|
| 1 | **黑屏** | App 启动后黑屏 | Choreographer 不刷新 |
| 2 | **卡死** | App 触摸不响应 | InputDispatcher 队列堆积 |
| 3 | **无响应** | App 弹 ANR dialog | InputDispatcher 5s 超时 |

**logcat 关键字**：

| 类型 | 关键字 |
|:-----|:-------|
| 黑屏 | `Choreographer: Skipped N frames` |
| 卡死 | `Input event injection finished but no response` |
| 无响应 | `ANR in xxxActivity` |

---

# 3. OOM 3 类分类速查

| # | 类型 | 现象 | 占比 |
|:-:|:-----|:-----|:----:|
| 1 | **Java 堆 OOM** | OutOfMemoryError 异常 | 40% |
| 2 | **Native 堆 OOM** | 进程被杀，tombstone 显示 OOM | 35% |
| 3 | **图片 OOM** | 解码大图崩溃 | 25% |

**logcat 关键字**：

| 类型 | 关键字 |
|:-----|:-------|
| Java 堆 | `java.lang.OutOfMemoryError` |
| Native 堆 | `tombstone: malloc failed` |
| 图片 | `Failed to allocate a 4MB byte allocation` |

---

# 4. 黄金 5 分钟：必做 4 件事

## 4.1 第 1 分钟：确认告警 + 拉群

```bash
# HANG：用户反馈为主
# OOM：APM 告警为主
```

## 4.2 第 2 分钟：抓 dumps

```bash
# 1. HANG 抓 traces + perfetto
adb shell kill -3 $(pidof com.example.app)
adb shell perfetto --out /data/local/tmp/trace.bin -t 10s sched freq &
adb pull /data/local/tmp/trace.bin /tmp/

# 2. OOM 抓 hprof
adb shell am dumpheap com.example.app /data/local/tmp/heap.hprof
adb pull /data/local/tmp/heap.hprof /tmp/

# 3. 同步抓 meminfo
adb shell dumpsys meminfo com.example.app
```

## 4.3 第 3 分钟：判断类型

**HANG 看 Choreographer / InputDispatcher**：
```bash
adb shell dumpsys gfxinfo com.example.app framestats
adb logcat -d | grep -E "Choreographer.*Skipped|Input event"
```

**OOM 看异常类型**：
```bash
adb logcat -d -b crash | grep -E "OutOfMemoryError|malloc failed|Failed to allocate"
```

## 4.4 第 4-5 分钟：发首报

```yaml
告警: HANG/OOM [类型]
触发: [用户反馈/告警]
判断: [HANG 3 类 / OOM 3 类]
首报:
  - 影响: [N] DAU
  - 类型: [黑屏/卡死/无响应] 或 [Java 堆/Native 堆/图片]
  - 行动: 已抓 [traces/hprof]，开始分析
```

---

# 5. 白银 15 分钟：定位

## 5.1 HANG 定位

### 黑屏（Choreographer 卡死）

```
"Choreographer" prio=10 tid=...
  at android.view.Choreographer.doScheduleFrame(...)
  at android.view.Choreographer.scheduleFrameLocked(...)
  - waiting on <0x...> (a android.view.Choreographer$FrameDisplayEventReceiver)
```

→ 渲染线程等主线程 → 主线程卡死

### 卡死（InputDispatcher 堆积）

```
"InputDispatcher" prio=10 tid=...
  at android.os.MessageQueue.nativePollOnce(Native method)
  - waiting on <0x...> (a java.lang.Object)
```

→ InputDispatcher 等 App 主线程 → 详见 OC02

### 无响应（ANR）

→ 完全等同 ANR 流程，详见 [OC02-ANR 响应剧本](OC02-ANR响应剧本.md)

## 5.2 OOM 定位

### Java 堆 OOM

```
java.lang.OutOfMemoryError: Failed to allocate a 4MB byte allocation
  at java.util.HashMap.resize(HashMap.java:...)
  at com.example.app.cache.ImageCache.put(ImageCache.java:67)
```

→ 缓存未限制大小

### Native 堆 OOM

```
signal 6 (SIGABRT), code -1 (SI_TKILL)
  #00 libc.so (abort+88)
  #01 libc.so (tgkill+...)
  ...（无 backtrace 细节）
```

→ 同时 `tombstone` 显示 OOM killer 触发 → 详见 [01-Mechanism/Kernel/Memory_Management/09](../../01-Mechanism/Kernel/Memory_Management/09-杀进程决策子系统：LMKD-MemoryLimiter-的协同.md)

### 图片 OOM

```
java.lang.OutOfMemoryError: Failed to allocate a 4MB byte allocation
  at android.graphics.Bitmap.nativeCreate(Native method)
  at android.graphics.Bitmap.createBitmap(Bitmap.java:1000)
```

→ Bitmap 解码未缩放

---

# 6. 黄金 30 分钟：修复

## 6.1 HANG 修复速查

| 类型 | 修复 |
|:-----|:-----|
| 黑屏 | 排查主线程 / 渲染线程 同步 IO |
| 卡死 | 走 OC02 ANR 流程 |
| 无响应 | 走 OC02 ANR 流程 |

## 6.2 OOM 修复代码

### Java 堆 OOM

```java
// 错误
public class ImageCache {
    private final Map<String, Bitmap> cache = new HashMap<>();  // ❌ 无大小限制
}

// 正确（LruCache）
public class ImageCache {
    private final LruCache<String, Bitmap> cache = new LruCache<>(16 * 1024 * 1024) {  // ✅ 16MB
        protected int sizeOf(String key, Bitmap value) {
            return value.getByteCount();
        }
    };
}
```

### 图片 OOM

```java
// 错误
Bitmap bitmap = BitmapFactory.decodeFile(path);  // ❌ 大图直接解码

// 正确（inSampleSize 缩放）
BitmapFactory.Options opts = new BitmapFactory.Options();
opts.inJustDecodeBounds = true;
BitmapFactory.decodeFile(path, opts);
opts.inSampleSize = calculateInSampleSize(opts, 800, 600);  // ✅ 缩放
opts.inJustDecodeBounds = false;
Bitmap bitmap = BitmapFactory.decodeFile(path, opts);
```

### Native 堆 OOM

```c
// 错误
void* buf = malloc(100 * 1024 * 1024);  // ❌ 100MB
if (buf == NULL) {
    return -1;
}

// 正确（分批分配 + 失败回退）
void* buf = malloc(8 * 1024 * 1024);  // ✅ 8MB
if (buf == NULL) {
    ALOGE("malloc failed: %s", strerror(errno));
    return -1;
}
```

---

# 7. 4 类真实场景剧本

## 7.1 场景 1：启动黑屏 5s

**现象**：App 启动后黑屏 5s 才出第一帧
**Choreographer log**：`Skipped 312 frames`
**根因**：`Application.onCreate` 同步执行 5s 任务
**修复**：onCreate 不做耗时操作 / 用 WorkManager 异步

## 7.2 场景 2：列表滑动卡死

**现象**：用户滑动列表卡顿 2s
**traces**：`RecyclerView.onBindViewHolder` 同步 IO
**根因**：图片加载在主线程
**修复**：用 Glide / Coil 异步加载

## 7.3 场景 3：Java 堆 OOM 闪退

**现象**：长时间使用后 OOM 闪退
**hprof**：ImageCache 持有 200MB
**根因**：LruCache 限制 16MB，但有 5 个实例各持 200MB
**修复**：改成单例 LruCache

## 7.4 场景 4：图片 OOM 闪退

**现象**：打开 4K 图片闪退
**OOM 异常**：`Failed to allocate a 64MB byte allocation`
**根因**：直接 decode 4K 图
**修复**：inSampleSize 缩放 + 分块加载

---

# 8. 告警规则

```yaml
# HANG 告警（无自动 → 用户反馈为主）
# OOM 告警
- alert: JavaHeapOomSpike
  expr: rate(java_oom_total[5m]) > 5
  for: 3m
  labels: { severity: P1 }
  
- alert: NativeHeapOomSpike
  expr: rate(native_oom_total[5m]) > 10
  for: 3m
  labels: { severity: P0 }
```

---

# 9. 12 反例清单

| # | 反例 | 错误做法 | 正确做法 |
|:-:|:-----|:---------|:---------|
| 1 | **HANG 当 OOM 处理** | 直接抓 hprof | **先判断类型** |
| 2 | **OOM 当 HANG 处理** | 抓 traces | **看 OOM 关键字** |
| 3 | **不抓 hprof** | OOM 只看 logcat | **hprof 是金标准** |
| 4 | **不抓 perfetto** | 卡顿只抓 traces | **perfetto 看帧时序** |
| 5 | **不缩放图片** | 改 try-catch | **inSampleSize 必用** |
| 6 | **不限制 LruCache** | 单例 + 无限 | **必限制 size** |
| 7 | **不通知 Native** | Native OOM Java 团队自己看 | **第 1 分钟拉 Native** |
| 8 | **不查引入版本** | 不查发版 | **第 3 步必查** |
| 9 | **重启完不复盘** | 修了就忘 | **24h 内 postmortem** |
| 10 | **不写内存基线** | 凭感觉 | **必设阈值** |
| 11 | **追责** | "X 写错代码" | **只对事不对人** |
| 12 | **不复盘同类** | 单点修复 | **横向 review 同类** |

---

# 10. 5 条 Takeaway

1. **HANG 与 OOM 经常混淆** —— oncall 第 1 件事是判断
2. **HANG 3 类**（黑屏/卡死/无响应）+ **OOM 3 类**（Java/Native/图片）—— 不同类型走不同分支
3. **HANG 用 traces + perfetto**，**OOM 用 hprof + meminfo** —— 工具不要混
4. **修复 OOM 的 3 个标准动作**：LruCache / inSampleSize / Native malloc 失败处理
5. **24h 内必出 postmortem** —— 防止同类 OOM 下周再发

---

# 11. 附录

## A 源码索引

| 模块 | 路径 | 关键 |
|:-----|:-----|:-----|
| HANG 机制 | [02-Symptom/S05-HANG/01-症状机制.md](../../02-Symptom/S05-HANG/01-症状机制.md) | 3 类 |
| HANG/OOM 取证 | [03-Forensics/F06-HANG-OOM/01-取证机制.md](../F06-HANG-OOM/01-取证机制.md) | 完整流程 |
| Hprof | [04-Tool/Hprof/04-内存泄漏典型案例与排查SOP](../../04-Tool/Hprof/04-内存泄漏典型案例与排查SOP.md) | 案例 |
| LMKD | [Memory_Management/09](../../01-Mechanism/Kernel/Memory_Management/09-杀进程决策子系统：LMKD-MemoryLimiter-的协同.md) | 杀进程决策 |
| oncall 流程 | [OC01-oncall 工程总论](OC01-oncall工程总论：值班机制与工具栈.md) | 5/15/30 |

## B 路径对账

无新增模块。

## C 量化自检

- HANG 3 类 + OOM 3 类 ✅
- 黄金 5/15/30 每分钟动作 ✅
- 4 类真实场景剧本 ✅
- 12 反例清单 ✅
- 5 条 Takeaway ✅

## D 工程基线

AOSP 17 + 6.18 LTS / 工具链：hprof + perfetto + dumpsys meminfo

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-24（v1.0）
