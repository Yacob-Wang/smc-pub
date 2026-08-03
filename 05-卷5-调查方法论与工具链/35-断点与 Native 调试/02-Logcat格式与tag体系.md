# 06-Foundation/Tools/Android_Tools · 02 · Logcat 格式与 tag 体系

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 自定义 log
>
> **强依赖**：[Logcat_Complete_Guide](./Logcat_Complete_Guide.md) · [06-Foundation/SELinux/04-AVC与avc_denied](../../SELinux/04-AVC与avc_denied：从一次denied反推策略.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 logcat 行的完整格式 + 5 大 buffer + tag 体系 + level 体系 + 自定义 tag 5 大块讲清楚——oncall 5 秒从一行 logcat 读到完整信息
- **不是**：不复述 [Logcat_Complete_Guide](./Logcat_Complete_Guide.md) 基础命令（本文是它的体系化扩展）
- **承接自**：[Logcat_Complete_Guide §1 基础命令](./Logcat_Complete_Guide.md)（本文讲"行格式 + 体系"）
- **衔接去**：[03 Logcat 过滤与持久化](03-Logcat过滤与持久化.md) / [04 Logcat 与 SELinux/avc](04-Logcat与SELinux-avc-denied行解读.md) / [06-Foundation/SELinux/04-AVC与avc_denied](../../SELinux/04-AVC与avc_denied：从一次denied反推策略.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章拆 9 字段精确含义 | oncall 5 秒看一行 |
| 2 | 第 2 章 5 大 buffer 深度 | bugreport 取证用 |
| 3 | 第 5 章自定义 tag 实战 | vendor 适配必用 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**logcat 行 = 7 段元数据 + 1 段消息——5 秒读懂一行。**

AOSP 17 logcat 行格式 `MM-DD HH:MM:SS.mmm  PID  TID PRIORITY/TAG: MESSAGE`，每个字段都有精确含义。理解字段 = 5 秒从海量 logcat 提取关键信息。

---

## 1. logcat 行格式详解（AOSP 17 threadtime 模式）

### 1.1 真实 logcat 行

```
07-27 10:30:45.123  1234  1234 I MyTag    : Hello World
07-27 10:30:45.456  1234  1235 W ExampleTag: Warning: foo
07-27 10:30:45.789  1234  1236 E AndroidRuntime: FATAL EXCEPTION: ...
```

### 1.2 9 字段精确含义

| # | 字段 | 例子 | 含义 |
|:-:|:-----|:-----|:-----|
| 1 | 日期 | `07-27` | 月-日（注意：不是年）|
| 2 | 时间 | `10:30:45.123` | 时:分:秒.毫秒 |
| 3 | PID | `1234` | 进程 ID |
| 4 | TID | `1234` / `1235` | 线程 ID（不同线程不同 TID）|
| 5 | Priority | `I` / `W` / `E` | 优先级（V/D/I/W/E/F/S）|
| 6 | Tag | `MyTag` | 标签（通常是类名 / 模块名）|
| 7 | `:` | `:` | 分隔符 |
| 8 | Message | `Hello World` | 实际消息（可含换行）|
| 9 | 续行 | 续行有空格开头 | 长消息自动换行 |

### 1.3 4 种输出模式

| 模式 | 例子 | 用途 |
|:-----|:-----|:-----|
| `brief` | `I/MyTag( 1234): Hello` | 紧凑 |
| `process` | `I (1234) Hello World` | 按 process |
| `tag` | `I/MyTag: Hello` | 按 tag |
| `threadtime` | `07-27 10:30:45.123  1234  1234 I MyTag: Hello` | 完整时间线（AOSP 17 默认）|
| `time` | `07-27 10:30:45.123 I/MyTag: Hello` | 带时间但无 PID/TID |

**AOSP 17 默认 `threadtime`**——oncall 5 秒定位时这个最有用。

### 1.4 6 大 Priority 详解

```
V - Verbose (最低)   ⬇
D - Debug
I - Info (默认)
W - Warning
E - Error
F - Fatal
S - Silent (最高,不输出)
```

| 字符 | 名称 | 颜色 | 用途 |
|:-----|:-----|:-----|:-----|
| V | Verbose | 灰 | 调试级（默认不输出）|
| D | Debug | 蓝 | 调试信息 |
| I | Info | 绿 | 正常运行信息 |
| W | Warning | 黄 | 警告（需关注）|
| E | Error | 红 | 错误（需处理）|
| F | Fatal | 红 | 致命（系统级）|
| S | Silent | - | 不输出（用于屏蔽）|

### 1.5 切换 Priority

```bash
# 1. 全部输出（含 V/D）
$ adb logcat -v threadtime

# 2. 只输出 I/W/E
$ adb logcat *:I

# 3. 特定 tag 某个 level
$ adb logcat MyTag:W *:S
# MyTag 输出 W 及以上，其他 tag Silent

# 4. 全部 silent（清屏）
$ adb logcat -c
```

---

## 2. 5 大 buffer 详解

### 2.1 5 大 buffer 总览

| buffer | 用途 | 大小（AOSP 17 默认）| 取证关注度 |
|:-------|:-----|:------------------|:--------|
| `main` | app + system（默认）| 4MB | ⭐⭐⭐ |
| `system` | system 进程（init / system_server）| 256KB | ⭐⭐⭐ |
| `events` | 二进制 events（systrace 用）| 4MB | ⭐ |
| `crash` | crash 触发 | 256KB | ⭐⭐⭐ |
| `kernel` | kernel log | 1MB | ⭐⭐⭐ |

### 2.2 main buffer

**内容**：
- 90% 的应用层 log
- 包含 system_server 的 log（也写 system）
- AOSP 17 默认

```bash
# 1. 看 main buffer
$ adb logcat -d -b main | head

# 2. 看 buffer 大小
$ adb logcat -g -b main
# main: ring buffer is 4.0MB (1 used of 4MB)

# 3. 清 main
$ adb logcat -c
```

### 2.3 system buffer

**内容**：
- init 进程（PID 1）
- system_server
- service_manager
- vold / surfaceflinger / netd 等系统服务

```bash
# 1. 看 system buffer
$ adb logcat -d -b system | head

# 2. 看 init log
$ adb logcat -d -b system | grep "init:"

# 3. 看 system_server
$ adb logcat -d -b system | grep "SystemServer"
```

### 2.4 events buffer

**内容**：
- 二进制 events（systrace 用）
- 包含 am_pss / am_proc_start / am_proc_died 等

```bash
# 1. 看 events
$ adb logcat -d -b events | head

# 2. events 是二进制，文本模式看不懂
# 用 systrace 解析
$ systrace -o /tmp/trace.html

# 3. 用 logcat -v events 解析
$ adb logcat -d -b events -v threadtime | head
```

### 2.5 crash buffer

**内容**：
- 触发 crash 的 log
- 包含 FATAL EXCEPTION 完整栈
- 通常 256KB 环形

```bash
# 1. 看 crash buffer
$ adb logcat -d -b crash | head

# 2. 找 FATAL
$ adb logcat -d -b crash | grep "FATAL"

# 3. bugreport 自动收集 crash
```

### 2.6 kernel buffer

**内容**：
- kernel log（dmesg）
- SELinux denied
- kernel panic
- kernel module load

```bash
# 1. 看 kernel buffer
$ adb logcat -d -b kernel | head

# 2. 找 SELinux denied
$ adb logcat -d -b kernel | grep "avc: denied"

# 3. 找 kernel panic
$ adb logcat -d -b kernel | grep -E "panic|oops"

# 4. kernel buffer 跟 dmesg 是同一份
$ adb shell dmesg | head
# 等价
```

### 2.7 5 大 buffer 速查

| 现场 | 看哪个 buffer | 命令 |
|:-----|:------------|:-----|
| **ANR** | system + main | `adb logcat -b system,main` |
| **NE** | crash + main + kernel | `adb logcat -b crash,main,kernel` |
| **OOM** | main | `adb logcat -b main -d | grep -E "lowmemory|killer"` |
| **KE** | kernel | `adb logcat -b kernel -d | grep panic` |
| **bootloop** | system + kernel | `adb logcat -b system,kernel -d` |
| **SELinux denied** | kernel | `adb logcat -b kernel -d | grep "avc: denied"` |
| **性能** | events | `adb logcat -b events -d` |

---

## 3. tag 体系

### 3.1 tag 的本质

**tag = log 的"分类标签"**——通常是：
- 类名（`MyActivity`、`MyService`）
- 模块名（`MyDaemon`）
- 功能名（`NetworkHelper`、`DatabaseHelper`）
- 系统名（`ActivityManager`、`WindowManager`）

### 3.2 系统 tag 分类

| 类别 | tag 例子 |
|:-----|:--------|
| **AMS** | `ActivityManager`、`ActivityTaskManager`、`ActivityStartController` |
| **WMS** | `WindowManager`、`InputManager`、`WindowOnBackDispatcher` |
| **PMS** | `PackageManager`、`PackageManagerService`、`PackageInstaller` |
| **PWR** | `PowerManager`、`BatteryStatsService`、`WakeLock` |
| **SYS** | `SystemServer`、`SystemService`、`init` |
| **NET** | `NetworkSecurityConfig`、`ConnectivityService`、`Netd` |
| **ART** | `art`、`art-method-trace`、`art-jit` |
| **KERN** | `kernel`（实际是 kernel buffer）|
| **BIND** | `Binder`（实际是 system buffer）|
| **DEBUG** | `StrictMode`、`Choreographer`、`Looper` |

### 3.3 tag 命令

```bash
# 1. 单 tag 过滤
$ adb logcat MyTag:V *:S
# MyTag: 全部 + 其他: Silent

# 2. 多 tag 过滤（用逗号）
$ adb logcat MyTag:V OtherTag:W *:S

# 3. tag 通配符
$ adb logcat "MyTag*":V *:S
# 所有 MyTag 开头的 tag

# 4. 多个 priority
$ adb logcat "MyTag:V MyOtherTag:W" *:S
```

### 3.4 真实 tag 取证案例

```bash
# 1. 找 Activity 启动慢
$ adb logcat -d | grep "ActivityTaskManager" | grep "Displayed"

# 2. 找 window 卡顿
$ adb logcat -d | grep "Choreographer.*Skipped"

# 3. 找 service 死
$ adb logcat -d | grep "ActivityManager.*died"

# 4. 找 power 异常
$ adb logcat -d | grep -E "PowerManager|BatteryStats"
```

### 3.5 tag 截断（AOSP 17 限制）

**tag 最大长度 32 字符**（含 null 结尾）

```java
// 源码（frameworks/base/core/java/android/util/Log.java）
public static final int LOG_TAG_MAX_LENGTH = 32;
```

**实战影响**：

```java
// 错误：tag 太长（被截断）
private static final String TAG = "MyCompanyName.MyProduct.MyModule.MyClass";
// 实际输出：MyCompanyName.MyProduct.MyModul

// 正确：tag 简短
private static final String TAG = "MyClass";
// 或
private static final String TAG = "MyApp";
```

---

## 4. level 体系详解

### 4.1 level 与过滤的对应

```
Priority 字符 = Log.x() 调用
─────────────────────────────────
V → Log.v()  最低（verbose）
D → Log.d()  调试（debug）
I → Log.i()  信息（info）
W → Log.w()  警告（warning）
E → Log.e()  错误（error）
A → Log.wtf() 严重（what a terrible failure）
F → Log.wtf() (AOSP 17 同 A)
S → Silent  不输出
```

### 4.2 5 大 Log 方法

```java
import android.util.Log;

Log.v("MyTag", "Verbose: " + msg);  // 调试详细
Log.d("MyTag", "Debug: " + msg);    // 调试信息
Log.i("MyTag", "Info: " + msg);     // 正常运行
Log.w("MyTag", "Warn: " + msg);     // 警告
Log.e("MyTag", "Error: " + msg, throwable);  // 错误 + 异常
```

### 4.3 level 过滤规则

```
默认输出：I 及以上
logcat *:V → 输出 V/D/I/W/E（全部）
logcat *:D → 输出 D/I/W/E
logcat *:I → 输出 I/W/E（默认）
logcat *:W → 输出 W/E
logcat *:E → 输出 E
logcat *:F → 输出 F
logcat *:S → 不输出（silent）
```

### 4.4 实战过滤组合

```bash
# 1. 只看 Error（最常用，安静）
$ adb logcat *:E

# 2. 看 Error + Warning
$ adb logcat *:W

# 3. 特定 tag 全部 + 其他 Silent
$ adb logcat MyTag:V *:S

# 4. 多个 tag 多个 level
$ adb logcat MyTag:V OtherTag:W *:S
```

### 4.5 编译期 log 控制

```java
// 1. 全部 disable（生产 release）
if (BuildConfig.DEBUG) {
    Log.d(TAG, "debug info");
}

// 2. 全部 strip（更彻底）
// 在 proguard.cfg 加：
-assumenosideeffects class android.util.Log {
    public static int v(...);
    public static int d(...);
}
```

**注意**：strip 后 debug 版本也没有 log，不利调试

---

## 5. 自定义 tag 实战

### 5.1 Java 自定义 tag

```java
// 1. 类顶部定义
private static final String TAG = "MyApp";

// 2. Log 调用
Log.i(TAG, "User clicked: " + buttonName);

// 3. 输出
// I MyApp   : User clicked: Confirm
```

### 5.2 C/C++ 自定义 tag

```cpp
// 1. include log 头文件
#include <android/log.h>

#define LOG_TAG "MyNative"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

// 2. 调用
LOGI("Init complete, version=%d", version);

// 3. 输出
// I MyNative: Init complete, version=1
```

### 5.3 自定义 tag 命名规范

| 规范 | 例子 | 原因 |
|:-----|:-----|:-----|
| **简短** | `MyApp` | 不被截断（< 32 字符）|
| **大小写区分** | `MyApp` | 易 grep |
| **不用空格** | `MyApp` | 易 filter |
| **模块化** | `MyApp.Network`、`MyApp.DB` | 分类清晰 |
| **避免通用** | `MyApp` 而非 `App` | 跟系统 tag 区分 |
| **避免空** | 不能为空 | logcat 报 invalid tag |

### 5.4 5 个反模式

```java
// 1. tag 太长（被截断）
private static final String TAG = "com.example.myapp.MyActivity";
// ❌ 截断

// 2. tag 太通用（难 filter）
private static final String TAG = "App";
// ❌ 跟系统混淆

// 3. tag 含空格（split 出错）
private static final String TAG = "My App";
// ❌ logcat 解析错

// 4. tag 跟类名（重复）
// MyActivity.java 里
private static final String TAG = "MyActivity";
// ❌ 重复（但用短类名还行）

// 5. tag 动态拼接（难 filter）
Log.i("MyApp" + threadId, "...");
// ❌ 无法 filter
```

---

## 6. 实战：5 个真实 logcat 案例

### 6.1 案例 1：app 启动慢

```bash
# 1. 抓启动 logcat
$ adb logcat -c
$ adb shell am start -n com.example.app/.MainActivity
$ sleep 5
$ adb logcat -d | grep "ActivityTaskManager" | head

# 2. 找到 "Displayed" 行
$ adb logcat -d | grep "ActivityTaskManager: Displayed"
07-27 10:30:00.123 1234 1234 I ActivityTaskManager: Displayed com.example.app/.MainActivity for user 0: 8500ms

# 3. 解读 9 字段
# 07-27 10:30:00.123   - 时间
# 1234                    - PID（system_server）
# 1234                    - TID（main）
# I                       - Info
# ActivityTaskManager     - tag
# "Displayed ... 8500ms"  - message
```

### 6.2 案例 2：service died

```bash
# 1. 找 service died
$ adb logcat -d | grep "service died"
07-27 10:30:00.456 1234 1234 I ActivityManager: Process com.example.app has died
07-27 10:30:00.789 1234 1234 W ActivityManager: Service crashed 2 times, stopping: com.example.app/.MyService

# 2. 看 crash 原因（5 秒前）
$ adb logcat -d -b crash | head -50
```

### 6.3 案例 3：SELinux denied

```bash
# 1. 找 denied
$ adb logcat -d -b kernel | grep "avc: denied"
07-27 10:30:00.123 0 0 I type=1400 audit(...): avc: denied { write } for ...

# 2. 8 字段解读（见 [06-Foundation/SELinux/04 §1.2](../../SELinux/04-AVC与avc_denied：从一次denied反推策略.md)）
```

### 6.4 案例 4：Jank 帧

```bash
# 1. 找 jank
$ adb logcat -d | grep "Choreographer.*Skipped"
07-27 10:30:00.123 1234 1234 I Choreographer: Skipped 32 frames!  The application may be doing too much work on its main thread.

# 2. 找具体代码
$ adb logcat -d | grep "Choreographer" | grep "frames" | tail
```

### 6.5 案例 5：ANR 触发

```bash
# 1. 找 ANR
$ adb logcat -d | grep "ANR in"
07-27 10:30:00.123 1234 1234 I ActivityManager: ANR in com.example.app, Reason: Input dispatching timed out

# 2. 看 system_server 行为
$ adb logcat -d -b system | grep "ANR" | head
```

---

## 7. 实战命令集（20+ 速查）

```bash
# 1. 看完整（threadtime）
$ adb logcat -v threadtime

# 2. 看指定 tag
$ adb logcat MyTag:V *:S

# 3. 看指定 buffer
$ adb logcat -b system

# 4. 多 buffer 组合
$ adb logcat -b main,system,kernel

# 5. 实时 + 后台
$ adb logcat | tee /tmp/logcat.txt &

# 6. 时间过滤
$ adb logcat -d -t '07-27 10:30:00.000'

# 7. 行数限制
$ adb logcat -d -T 100

# 8. grep 特定关键字
$ adb logcat -d | grep "ANR"

# 9. grep + 上下文
$ adb logcat -d -v threadtime | grep -B5 -A20 "FATAL"

# 10. 反向 grep（排除）
$ adb logcat -d | grep -v "debug"

# 11. 实时写入文件
$ adb logcat -v threadtime > /tmp/logcat.txt &

# 12. 实时过滤
$ adb logcat -v threadtime | grep "FATAL\|ANR"

# 13. 解析 binary event
$ adb logcat -b events -v threadtime

# 14. crash buffer
$ adb logcat -b crash

# 15. kernel buffer
$ adb logcat -b kernel

# 16. 看 buffer 状态
$ adb logcat -g

# 17. 多个 tag + 多个 level
$ adb logcat MyTag:V OtherTag:W *:S

# 18. 通配符
$ adb logcat "MyTag*":V *:S

# 19. 时间戳
$ adb logcat -v time

# 20. 显示 PID + TID
$ adb logcat -v threadtime
```

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [Logcat_Complete_Guide](./Logcat_Complete_Guide.md) | 基础命令 |
| [03 Logcat 过滤与持久化](03-Logcat过滤与持久化.md) | 下篇 |
| [04 Logcat 与 SELinux/avc](04-Logcat与SELinux-avc-denied行解读.md) | SELinux 集成 |
| [06-Foundation/SELinux/04-AVC与avc_denied](../../SELinux/04-AVC与avc_denied：从一次denied反推策略.md) | avc: denied 完整解读 |
| [03-Forensics/Bugreport/02 §4 logcat/ 详解](../../../../05-卷5-调查方法论与工具链/33-Dumpsys · Bugreport · DropBox/02-Bugreport-目录结构全梳理.md) | bugreport 中 logcat 文件 |
| [06-Foundation/Tools/Tracing/20-Trace抓取方法全面指南](../Tracing/20-Trace抓取方法全面指南：ftrace-atrace-systrace-perfetto.md) | trace 对应 logcat |

---

## 9. 下一篇预告 + 自检

### 9.1 下一篇

[03 Logcat 过滤与持久化](03-Logcat过滤与持久化.md) 讲清：
- 5 类过滤组合（按 tag / level / buffer / 时间 / 内容）
- 3 种持久化方式（tee / logcat 转储 / properties）
- 持久 logcat 在生产环境配置
- 真实 case：5 分钟找某 app 全部 log

### 9.2 看完本文的自检

- [ ] 能用 9 字段精确读一行 logcat
- [ ] 能用 4 种输出模式
- [ ] 能选对 5 大 buffer
- [ ] 能用 6 大 Priority 过滤
- [ ] 能用 20+ 实战命令
- [ ] 能写自定义 tag（Java / C++）
- [ ] 知道 5 个反模式

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
