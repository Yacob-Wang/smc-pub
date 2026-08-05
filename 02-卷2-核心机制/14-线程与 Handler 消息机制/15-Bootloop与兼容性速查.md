# 15-Bootloop 与兼容性速查

> 系列:Android OEM Hook 技术解析(共 15 篇 + 1 大纲 + 1 全景图 + 1 README = 17 文件)
> 本篇定位:**诊断治理**(系列收尾篇)
> 版本基线:**AOSP android-14.0.0_r1** / **Kernel android14-5.10**

---

## 本篇定位(强制开头段)

- **系列角色**:**诊断治理**(全系列收尾篇)
- **强依赖**:
  - **[01-全景图](01-OEM-Hook全景图-本质与战场.md)**
  - **[02-Kernel 层 Hook](02-Kernel层Hook-Vendor_Hook与eBPF.md)** ~ **[14-OEM Hook 演进](14-OEM_Hook演进-从运行时到编译期.md)**:所有已讲内容
- **承接自**:**14-OEM Hook 演进**
- **衔接去**:**无**(系列完结)
- **不重复内容**:
  - 不重复 02-14 各篇已讲的单个风险点(本章做汇总速查)
  - 专注"5 秒定位 + 30 分钟根因"的实战能力

---

## 角色设定

我是一名 **Android 稳定性架构师**,正在系统学习 OEM Hook 技术。本篇是系列的第 15 篇(也是最后 1 篇),主题是 **Bootloop 与兼容性速查**。

学完本篇后,我应该能够:
- 在 5 秒内把任何 OEM Hook 故障定位到正确的层级和场景
- 在 30 分钟内通过 dump/logcat/systrace 抓到根因
- 给出源码级修复 / 配置文件 / 白名单的修复策略

---

## 上下文

- **上一篇**:**[14-OEM Hook 演进 - 从运行时到编译期](14-OEM_Hook演进-从运行时到编译期.md)**
- **本系列完结**

---

## 一、速查矩阵总览

### 1.1 5 大类故障 × 6 层 Hook 矩阵

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│               5 大类故障 × 6 层 Hook 速查矩阵                                      │
├──────────────────┬─────────┬─────────┬─────────┬─────────┬─────────┬─────────┤
│   故障类型        │ Kernel  │  HAL    │ Native  │  ART    │Framework│ App-UI  │
├──────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ ① Bootloop       │ ★★★★ │   ★    │   ★★  │   ★★  │ ★★★★★ │   ★    │
│   循环重启        │ 调度死锁│  HAL挂掉│ malloc │ ART挂掉 │ AMS拦死│ RRO冲突│
├──────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ ② App 闪退       │   -    │   -    │   ★★  │ ★★★★│   ★★  │   ★★  │
│   App启动崩溃    │        │        │ 库错误│ ART校验│ 假数据│ RRO   │
├──────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ ③ 功能失效       │  ★★    │ ★★★★ │ ★★★★ │ ★★★★│ ★★★★★ │ ★★★★ │
│   抢不到红包等    │ 调度    │ PowerHAL│ Skia   │ 方法挂 │ 后台拦 │ 资源   │
├──────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ ④ 性能问题       │ ★★★★ │ ★★★★ │ ★★★★ │   ★★  │   ★★  │   ★    │
│   发热/卡顿      │ 调度    │ 调频   │ 渲染   │ 解释器 │ Proxy  │ 主题   │
├──────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ ⑤ 兼容性问题     │  ★★    │ ★★★   │   ★★  │ ★★★★│ ★★★★ │ ★★★★ │
│   App闪退/布局错乱│        │        │        │ 三同步漏│ 拦截漏 │ TaskFrag│
└──────────────────┴─────────┴─────────┴─────────┴─────────┴─────────┴─────────┘

注:★ 越多表示该层 Hook 在该类故障中越常出现
```

### 1.2 故障现象 → 怀疑 Hook 层级 速查

| 故障现象 | 怀疑 Hook 层级 | 排查方向 |
|---|---|---|
| **系统循环重启** | Framework-Binder(AMS)或 Kernel | Bootloop 类(详见第 2 节) |
| **App 启动崩溃** | ART 或 App-UI | 案例 1(详见第 3 节) |
| **抢不到红包** | Framework-Binder(后台拦截)或 Kernel(cgroup) | 案例 2(详见第 3 节) |
| **闹钟失灵** | Framework-Binder(Alarm) | 详见 [09-场景 2](09-场景2-后台治理-cgroup_freezer与启动拦截.md) |
| **折叠屏 UI 错乱** | Framework-Binder(WMS/ATMS) | 详见 [12-场景 5](12-场景5-折叠屏适配-平行视界与TaskFragment.md) |
| **发热严重** | HAL(PowerHAL)或 Kernel(EAS) | 详见 [03-HAL](03-HAL层Hook-PowerHAL与触控优化.md) |
| **银行 App 拒绝运行** | Framework-Binder(假数据被检测) | 详见 [08-场景 1](08-场景1-隐私保护-空白通行证与假数据.md) |
| **微信被踢下线** | Framework-Binder(双开被检测) | 详见 [10-场景 3](10-场景3-应用双开-UserHandle多用户魔改.md) |
| **界面闪烁** | App-UI(RRO)或 Native(Skia) | 详见 [07-App-UI](07-App-UI层Hook-RRO与Instrumentation替换.md) |
| **游戏掉帧** | Kernel(EAS)或 HAL(PowerHAL) | 详见 [11-场景 4](11-场景4-游戏调度-Vendor_Hook与PowerHAL.md) |

---

## 二、Bootloop 类故障 - 系统循环重启

### 2.1 Bootloop 的本质

```
┌─────────────────────────────────────────────────────────────┐
│           Bootloop 的本质                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Bootloop = 启动过程中 system_server 反复崩溃                 │
│  → Zygote 检测到崩溃 → 重启 → 再崩 → 重启                  │
│  → 用户看到"开机动画 → 启动崩溃 → 再次开机动画"循环          │
│                                                             │
│  90%+ 的 Bootloop 是 OEM Hook 引发的:                        │
│  ├── Hook 拦截了 system_server 自身依赖的方法               │
│  ├── Hook 死锁导致 system_server 阻塞                      │
│  ├── Hook 抛出异常但没被捕获                               │
│  └── Hook 引发了 watchdog timeout                           │
│                                                             │
│  修复策略:                                                  │
│  ├── 临时:进入 recovery 模式,清除 OEM 分区                 │
│  └── 永久:修复 Hook 代码,加边界检查和降级逻辑               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Bootloop 排查速查

```
┌─────────────────────────────────────────────────────────────┐
│           Bootloop 排查速查                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Step 1:抓取崩溃日志                                         │
│    adb logcat -b crash -d > crash.log                        │
│    adb pull /sys/fs/pstore/ ./                               │
│                                                             │
│  Step 2:找 system_server 崩溃栈                             │
│    关键字:"AndroidRuntime: FATAL EXCEPTION"                │
│    → 找到崩溃的类和方法                                     │
│                                                             │
│  Step 3:判断是否是 OEM Hook 问题                            │
│    - 崩溃栈里是否有 MiuiXxx / HarmonyXxx / ColorXxx 等      │
│    - 崩溃方法是否在 AMS/WMS/PMS 等 Framework 服务           │
│                                                             │
│  Step 4:定位到具体 OEM Hook                                  │
│    找到崩溃栈顶部的 OEM 类                                  │
│    → 进入该 OEM Hook 的实现代码                             │
│                                                             │
│  Step 5:修复                                                  │
│    - 加边界检查                                             │
│    - 加异常处理(不能让 Hook 自身抛出未捕获异常)            │
│    - 加降级逻辑(失败时走原 AOSP 流程)                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 实战案例 1:启动期 Hook 引发 Bootloop

**现象**:
某 OEM 在 Android 13 升级时,把 AMS 的 `startActivity` 入口加了一个 `if-else`,导致部分设备开机后 30 秒内反复重启。

**关键 logcat 片段**:
```
E AndroidRuntime: FATAL EXCEPTION: main
E AndroidRuntime: Process: com.android.server, PID: 1234
E AndroidRuntime: java.lang.NullPointerException
E AndroidRuntime:   at com.oem.miui.server.am.MiuiBgPolicy.allowStartActivity(MiuiBgPolicy.java:42)
E AndroidRuntime:   at com.android.server.am.ActivityManagerService.startActivityAsUser(ActivityManagerService.java:4500)
E AndroidRuntime:   at com.android.server.am.ActivityManagerService.startActivity(ActivityManagerService.java:4200)
```

**根因分析**:
崩溃栈定位到 `MiuiBgPolicy.allowStartActivity` 第 42 行,空指针异常:

```java
// 错误的 OEM Hook(第 42 行)
public boolean allowStartActivity(String callerPackage, Intent intent, ...) {
    if (callerPackage.equals("com.android.systemui")) {  // ← 这里 NPE
        return true;
    }
    // ...
}
```

启动期 `callerPackage` 可能为 `null`(system_server 自己启动时调用),`null.equals(...)` 抛 NPE → `startActivity` 抛异常 → system_server 崩溃 → Zygote 重启。

**修复**:
加 null 检查:

```java
// 修复:加 null 检查
public boolean allowStartActivity(String callerPackage, Intent intent, ...) {
    if (callerPackage == null || callerPackage.equals("com.android.systemui")) {
        return true;
    }
    // ...
}
```

**环境**:AOSP 13 / 设备 Pixel 7 Pro / 复现:启动时概率触发。

**稳定性架构师视角**:**启动期的 Hook 必须做 null/边界检查**——这是 OEM Hook 引发 Bootloop 的头号原因。

### 2.4 实战案例 2:Service Manager Proxy 死锁引发 Bootloop

**现象**:
某 OEM 上线 ServiceManager Proxy 后,系统无法进入桌面,反复重启。

**关键 logcat 片段**:
```
W ActivityManager: Slow operation: ActivityManagerService.startActivityAsUser took 30s
W Watchdog: AM Service dumped state: held lock=ActivityManager
E AndroidRuntime: java.lang.RuntimeException: Deadlock!
```

**根因分析**:
OEM Proxy 持锁状态下调用原服务,导致死锁:

```java
// 错误的 OEM Proxy
public int startActivity(...) {
    synchronized (mPolicyLock) {  // 持锁
        // 错误:在持锁状态下调用原 AMS 方法
        // AMS 在等 mPolicyLock,这里又调 AMS → 死锁
        return mOriginal.startActivity(...);
    }
}
```

**修复**:
不在持锁状态下调用原服务:

```java
// 修复:先在锁内做决策,锁外调原服务
public int startActivity(...) {
    int decision;
    synchronized (mPolicyLock) {
        decision = mPolicyEngine.decide(...);
    }
    
    // 锁外调用原服务
    if (decision == ALLOW) {
        return mOriginal.startActivity(...);
    } else {
        return ActivityManager.START_INTENT_NOT_RESOLVED;
    }
}
```

**环境**:AOSP 13 / 设备 小米 12 Pro / 复现:每次开机必触发。

**稳定性架构师视角**:**OEM Proxy 头号坑:持锁调原服务**——任何 OEM Proxy 实现都必须在锁外调原服务。

### 2.5 实战案例 3:Vendor Hook 调度死锁

**现象**:
某 OEM 在 GKI 5.10 上加 Vendor Hook 后,部分设备启动后立刻死机。

**关键 logcat 片段**:
```
[   12.345] BUG: scheduling while atomic: kworker/u8:1/234/0x00000002
[   12.345] Modules linked in: oem_vendor_hook vendor_hook
[   12.345] CPU: 7 PID: 234 Comm: kworker/u8:1 Tainted: G        W        5.10.xxx
[   12.345] Call trace:
[   12.345]  schedule_timeout+0x1c/0x100
[   12.345]  iqoo_game_boost_tick+0x48/0xc0 [vendor_hook]
[   12.345]  android_vh_scheduler_tick+0x30/0x50
```

**根因分析**:
Vendor Hook 持锁状态下调用调度器 API:

```c
// 错误的 Vendor Hook 实现
static void iqoo_game_boost_tick(void *data, struct rq *rq) {
    spin_lock(&game_lock);  // 持锁
    
    // 错误:在持锁状态下调用调度器 API
    set_cpus_allowed_ptr(rq->curr, cpumask_of(7));
    
    spin_unlock(&game_lock);
}
```

`scheduling while atomic` 是 Kernel 的硬性错误,直接 panic。

**修复**:
不在持锁状态调调度器 API:

```c
// 修复
static void iqoo_game_boost_tick(void *data, struct rq *rq) {
    struct task_struct *target = NULL;
    
    // 1. 在锁内判断是否需要 boost
    if (should_boost(rq->curr)) {
        target = rq->curr;
        get_task_struct(target);
    }
    
    // 2. 在锁外调用调度器 API
    if (target) {
        set_cpus_allowed_ptr(target, cpumask_of(7));
        put_task_struct(target);
    }
}
```

**环境**:Kernel 5.10 / 设备 iQOO 11 / 复现:开机时触发。

**稳定性架构师视角**:**Vendor Hook 中不能持锁调调度器 API**——这是 Kernel 开发的铁律。

---

## 三、App 兼容性故障

### 3.1 微信/银行 App 闪退

详见 [08-场景 1](08-场景1-隐私保护-空白通行证与假数据.md) 第 9 节实战案例。

### 3.2 抢红包被冻结

详见 [09-场景 2](09-场景2-后台治理-cgroup_freezer与启动拦截.md) 第 7.1 节实战案例。

### 3.3 实战案例 4:微信双开被检测为多设备

详见 [10-场景 3](10-场景3-应用双开-UserHandle多用户魔改.md) 第 8.1 节实战案例。

### 3.4 实战案例 5:折叠屏 App 启动错乱

详见 [12-场景 5](12-场景5-折叠屏适配-平行视界与TaskFragment.md) 第 8.1 节实战案例。

---

## 四、5 秒定位速查表

### 4.1 速查流程

```
┌─────────────────────────────────────────────────────────────┐
│           5 秒定位速查流程                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Step 1:看故障现象(2 秒)                                    │
│    ├─ Bootloop → 跳到第 2 节                                │
│    ├─ App 闪退 → 跳到第 3 节                                │
│    ├─ 功能失效 → 跳到第 4 节                                │
│    └─ 性能问题 → 跳到第 5 节                                │
│                                                             │
│  Step 2:看 OEM 厂商(1 秒)                                    │
│    查 [13-五大 OEM 对比](13-五大OEM风格对比-华为小米OPPO_vivo_三星.md)│
│    → 锁定是哪个 OEM 的 Hook                                 │
│                                                             │
│  Step 3:看 OEM 的功能开关(1 秒)                             │
│    打开 OEM 设置 → 找到"隐私/后台/游戏"等开关                │
│    → 关闭对应功能,看问题是否消失                            │
│                                                             │
│  Step 4:看 OEM 文档(1 秒)                                   │
│    查 OEM 开发者文档/Hook 文档                              │
│    → 锁定具体 Hook 点                                       │
│                                                             │
│  合计:5 秒定位                                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 速查表(故障现象 → OEM Hook 层级)

| 故障现象 | 第一怀疑 | 第二怀疑 | 排查入口 |
|---|---|---|---|
| 系统循环重启 | AMS Hook(NPE) | ServiceManager Proxy(死锁) | logcat crash 日志 |
| App 启动崩溃 | ART Hook 字段错误 | RRO 冲突 | App logcat |
| 抢不到红包 | AMS startActivity 拦截 | cgroup freezer | dumpsys activity |
| 闹钟失灵 | Alarm Hook | 后台冻结 | dumpsys alarm |
| 微信被踢 | Build.FINGERPRINT 未区分 | UID 计算错误 | dumpsys package |
| 折叠屏错乱 | WMS Hook | TaskFragment 拆分 | dumpsys window |
| 发热严重 | PowerHAL 鸡血调度 | EAS Vendor Hook | dumpsys thermalservice |
| 银行 App 拒绝 | IMEI 全 0 被检测 | 假数据格式错误 | App 日志 |
| 界面闪烁 | RRO 切换冲突 | SurfaceFlinger | dumpsys SurfaceFlinger |
| 游戏掉帧 | EAS 调度失败 | PowerHAL 没拉频 | systrace / Perfetto |

---

## 五、30 分钟根因模板

### 5.1 抓取清单

```
┌─────────────────────────────────────────────────────────────┐
│           30 分钟根因抓取清单                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  0-2 分钟:快速抓取                                          │
│  ├─ adb logcat -d -b crash > crash.log                       │
│  ├─ adb logcat -d -b main > main.log                        │
│  ├─ adb pull /sys/fs/pstore/ ./                            │
│  └─ adb shell dumpsys > dumpsys.log                          │
│                                                             │
│  2-5 分钟:针对性抓取(根据故障现象)                          │
│  ├─ AMS 相关:adb shell dumpsys activity                     │
│  ├─ WMS 相关:adb shell dumpsys window                       │
│  ├─ PMS 相关:adb shell dumpsys package                      │
│  ├─ PowerHAL:adb shell dumpsys power                        │
│  ├─ Alarm:adb shell dumpsys alarm                           │
│  ├─ 通知:adb shell dumpsys notification                    │
│  └─ SurfaceFlinger:adb shell dumpsys SurfaceFlinger         │
│                                                             │
│  5-10 分钟:性能抓取(如需要)                                │
│  ├─ systrace -t 10 -o trace.html                            │
│  ├─ Perfetto record -c 30s -o trace.perfetto               │
│  ├─ simpleperf record -g -o perf.data 30                    │
│  └─ atrace --async_start -c -t 30                          │
│                                                             │
│  10-15 分钟:OEM 特定抓取                                    │
│  ├─ 关闭该 OEM 的 Hook 功能,看问题是否消失                 │
│  ├─ 用 OEM 提供的诊断工具(如有)                            │
│  └─ 切换到安全模式(部分 OEM 提供)                          │
│                                                             │
│  15-30 分钟:分析                                            │
│  ├─ 用 grep/awk 分析日志                                    │
│  ├─ 用 Perfetto UI 看 systrace                             │
│  └─ 用 crash 日志定位崩溃栈                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 关键命令速查

```bash
# ========== 1. 日志抓取 ==========
adb logcat -d -b crash       # 崩溃日志
adb logcat -d -b main        # 主日志
adb logcat -d -b system      # 系统日志

# ========== 2. dumpsys 速查 ==========
adb shell dumpsys activity   # AMS 信息
adb shell dumpsys window     # WMS 信息
adb shell dumpsys package    # PMS 信息
adb shell dumpsys power      # PowerHAL 信息
adb shell dumpsys alarm      # 闹钟信息
adb shell dumpsys notification  # 通知信息
adb shell dumpsys cpuinfo    # CPU 调度信息

# ========== 3. 系统状态 ==========
adb shell top -m 10 -n 1     # CPU 占用 Top 10
adb shell cat /proc/cgroups  # cgroup 信息
adb shell ls /sys/fs/cgroup/ # cgroup freezer
adb shell cat /proc/uid_cputime/show_uid_stat  # UID CPU 时间

# ========== 4. ART Hook 状态 ==========
adb shell dumpsys meminfo    # 内存状态
adb shell setprop dalvik.vm.dex2oat-throttle 0  # 关闭 AOT 节流
adb shell getprop dalvik.vm.dex2oat-Xms  # dex2oat 内存

# ========== 5. OEM 特定 ==========
adb shell cmd miui settings get privacy_blacklist  # MIUI 隐私黑名单
adb shell cmd coloros settings get task_freeze_config  # OPPO 后台冻结
adb shell cmd harmony settings get permission  # 华为权限

# ========== 6. trace 工具 ==========
adb shell atrace --async_start -c -t 30 sched freq view
adb shell atrace --async_dump
adb shell simpleperf record -g -o /data/local/tmp/perf.data 30
```

### 5.3 OEM Hook 状态查询速查

```bash
# ========== 1. 检查 ART Hook ==========
# 找出 OEM 改过的方法
adb shell dumpsys package com.example.app | grep -i oem

# ========== 2. 检查 RRO overlay ==========
adb shell cmd overlay list
adb shell cmd overlay enable com.oem.theme
adb shell cmd overlay disable com.oem.theme

# ========== 3. 检查 cgroup 状态 ==========
adb shell ls /sys/fs/cgroup/frozen/
adb shell cat /sys/fs/cgroup/frozen/app_<uid>/cgroup.freeze
# FROZEN → 进程被冻结
# THAWED → 进程正常运行

# ========== 4. 检查 Vendor Hook ==========
adb shell cat /proc/vendor_hook
# (部分 OEM 提供此接口)

# ========== 5. 检查 PowerHAL ==========
adb shell dumpsys power | grep -i profile
adb shell cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
adb shell cat /sys/class/devfreq/gpu/governor
```

---

## 六、修复策略汇总

### 6.1 3 大修复策略

```
┌─────────────────────────────────────────────────────────────┐
│           OEM Hook 兼容性问题的 3 大修复策略                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  策略 1:源码级修复(根本)                                    │
│    直接修复 OEM Hook 代码                                    │
│    ├── 加边界检查                                           │
│    ├── 加异常处理                                           │
│    ├── 加降级逻辑                                           │
│    └── 加超时回滚                                           │
│                                                             │
│    适用:严重问题,影响所有用户                               │
│    成本:高(需要重新编译、ROM 升级)                        │
│                                                             │
│  策略 2:配置文件调整(中)                                    │
│    修改 OEM 的配置(白名单、黑名单、阈值)                    │
│    ├── 加入白名单                                           │
│    ├── 调整阈值                                             │
│    ├── 修改 cloud config                                    │
│    └── 推送 OTA 配置文件                                   │
│                                                             │
│    适用:中等问题,影响部分用户                               │
│    成本:中(OTA 推送即可)                                   │
│                                                             │
│  策略 3:App 层适配(最低)                                    │
│    App 适配 OEM Hook 的行为                                 │
│    ├── 检测是否是分身空间                                   │
│    ├── 检测是否是隐私模式                                   │
│    ├── 使用厂商推送 SDK                                     │
│    └── 适配折叠屏布局                                       │
│                                                             │
│    适用:轻度问题,App 兼容性问题                            │
│    成本:低(App 团队适配即可)                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 按故障类型的修复策略选择

| 故障类型 | 推荐策略 | 实施难度 |
|---|---|---|
| Bootloop | 源码级修复(必须) | ★★★★★ |
| App 闪退 | App 适配 + OEM 配置 | ★★★ |
| 抢不到红包 | OEM 配置(白名单) | ★★ |
| 闹钟失灵 | OEM 配置(白名单) | ★★ |
| 微信被踢 | App 适配 | ★★★ |
| 折叠屏错乱 | 源码级修复 + App 适配 | ★★★★ |
| 发热严重 | OEM 配置 + 源码级 | ★★★ |
| 银行 App 拒绝 | App 适配 + 用户关闭 | ★★ |
| 界面闪烁 | 源码级修复 | ★★★★ |
| 游戏掉帧 | OEM 配置(降低鸡血) | ★★★ |

---

## 七、速查工具集

### 7.1 在线资源

```
┌─────────────────────────────────────────────────────────────┐
│           OEM Hook 速查在线资源                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  AOSP 源码:                                                 │
│  ├── cs.android.com/android-14.0.0_r1                      │
│  └── android.googlesource.com                               │
│                                                             │
│  Kernel 源码:                                                │
│  ├── elixir.bootlin.com/linux/v5.10                        │
│  └── android.googlesource.com/kernel/common                │
│                                                             │
│  OEM 开发者文档:                                            │
│  ├── 华为:HarmonyOS Developer                              │
│  ├── 小米:HyperOS 开发者文档                                │
│  ├── OPPO:ColorOS 开放平台                                 │
│  ├── vivo:OriginOS 开放平台                                 │
│  └── 三星:Samsung Developers                                │
│                                                             │
│  ART Hook 开源框架:                                          │
│  ├── github.com/topjohnwu(YAHFA / LSPosed)                 │
│  ├── github.com/ElderDrivers/Epic(Xposed)                   │
│  └── github.com/aspect-build/aspectj(Java AOP)             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 本系列内部速查

```
┌─────────────────────────────────────────────────────────────┐
│           本系列 15 篇的内部速查                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  全景图 → [01-全景图](01-OEM-Hook全景图-本质与战场.md)      │
│  6 层基础设施 → [02-07](02-Kernel层Hook-Vendor_Hook与eBPF.md)|
│  5 大场景 → [08-12](08-场景1-隐私保护-空白通行证与假数据.md) │
│  厂商对比 → [13-OEM 对比](13-五大OEM风格对比-华为小米OPPO_vivo_三星.md)│
│  演进趋势 → [14-演进](14-OEM_Hook演进-从运行时到编译期.md)  │
│  实战速查 → [本篇 15](15-Bootloop与兼容性速查.md)            │
│                                                             │
│  跨系列引用:                                                 │
│  ├── PLE 系列:程序加载(对应 Hook 的"载体")                │
│  ├── ART 系列:ART 运行时(对应 05-ART Hook)                 │
│  ├── MM_v2 系列:内存治理(对应 09-后台治理的 cgroup)        │
│  ├── Input 系列:输入子系统(对应 03-HAL 触控)               │
│  └── Binder 系列:Binder 通信(对应 06-Framework)             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 八、实战案例汇总(本系列所有案例速查)

### 8.1 15 篇中的 20+ 个实战案例

| 篇 | 案例 | 故障类型 | 修复策略 |
|---|---|---|---|
| 02-Kernel | 1. Vendor Hook 调度死锁 | Bootloop | 源码级修复 |
| 02-Kernel | 2. eBPF 程序过大被拒 | 性能问题 | 拆分程序 |
| 03-HAL | 1. HAL 服务挂掉 | Bootloop | 加边界检查 |
| 03-HAL | 2. 鸡血模式未恢复 | 性能问题 | 加状态回滚 |
| 03-HAL | 3. TouchHAL 高采样率不兼容 | 兼容性 | 平台能力探测 |
| 04-Native | 1. malloc hook 递归死锁 | 性能/Bootloop | 异步化 |
| 04-Native | 2. Skia 升级导致 hook 失效 | 兼容性 | 重新定位虚函数表 |
| 04-Native | 3. InputDispatcher Hook 导致 ANR | 性能 | 异步化日志 |
| 05-ART | 1. 三同步漏掉 | Hook 失效 | 补齐三同步 |
| 05-ART | 2. ART 升级导致全部失效 | 兼容性 | 动态检测偏移 |
| 05-ART | 3. Verifier 拒绝 | App 闪退 | 用反射找偏移 |
| 06-Framework | 1. ServiceManager Proxy 死锁 | Bootloop | 锁外调原服务 |
| 06-Framework | 2. AMS 拦截导致闹钟失灵 | 功能失效 | 补齐白名单 |
| 06-Framework | 3. WMS 折叠屏拆分导致 App 闪退 | 兼容性 | App 兼容性检查 |
| 07-App-UI | 1. RRO 优先级冲突 | 功能失效 | 明确优先级 |
| 07-App-UI | 2. Instrumentation 启动慢 | 性能 | 异步化日志 |
| 07-App-UI | 3. ClassLoader 类冲突 | App 闪退 | OEM 类命名规范 |
| 08-场景1 | 银行 App 检测权限欺骗 | 兼容性 | 假数据逼真化 |
| 09-场景2 | 微信抢红包被杀 | 功能失效 | 补齐白名单 |
| 09-场景2 | 闹钟 App 被冻结 | 功能失效 | 扩展白名单 |
| 09-场景2 | cgroup freezer 与 Service 冲突 | ANR | 协调生命周期 |
| 10-场景3 | 微信双开被检测 | 兼容性 | 设备标识区分 userId |
| 10-场景3 | 双开存储占用过大 | 性能 | 共享 APK |
| 10-场景3 | 双开 QQ 与主 QQ 推送冲突 | 兼容性 | 通知 key 加 userId |
| 11-场景4 | 游戏掉帧(温控触发) | 性能 | 放宽温控阈值 |
| 11-场景4 | 游戏退出后未恢复 | 性能 | 配套退出逻辑 |
| 12-场景5 | 折叠屏 App 启动错乱 | 兼容性 | 分离强制横屏/平行视界 |
| 12-场景5 | TaskFragment 拆分导致返回键异常 | 兼容性 | TaskFragment 栈管理 |

---

## 九、风险地图

```
┌─────────────────────────────────────────────────────────────┐
│           OEM Hook 兼容性风险地图(汇总)                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  故障类型       频率    严重度    修复成本    修复速度        │
│  ─────────────────────────────────────────────────────       │
│  Bootloop      低      极高     高         慢(ROM升级)    │
│  App 闪退      中      中       中         中(OTA)        │
│  功能失效      高      低       低         快(白名单)      │
│  性能问题      中      中       中         中              │
│  兼容性问题    高      中       高         慢(App适配)    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 十、总结 - 架构师视角的 7 条 Takeaway

1. **5 秒定位 + 30 分钟根因是 OEM Hook 排障的黄金标准**
2. **90% 的 Bootloop 都是 OEM Hook 引发的**(启动期边界检查缺失)
3. **App 兼容性问题的头号嫌疑是 OEM Hook**(关闭功能可快速定位)
4. **白名单机制是 OEM 后台治理的"必选项"**(误杀关键 App 是兼容性大忌)
5. **持锁调原服务是 OEM Proxy 头号坑**(任何 Proxy 实现都必须在锁外调)
6. **设备的设备标识必须区分 userId**(避免被 App 检测为"多设备登录")
7. **OEM Hook 维护成本与 Android 版本号同步增长**(必须有专门团队)

**OEM Hook 兼容性速查路径**(终极):
```
线上问题(任何 OEM Hook 引起的故障)
   ↓
5 秒定位:
   ├── Bootloop → logcat crash 日志
   ├── App 闪退 → App logcat + ART 校验错误
   ├── 功能失效 → dumpsys activity / window / alarm
   └── 性能问题 → Perfetto / systrace / dumpsys power
   ↓
30 分钟根因:
   ├── 抓取关键 log
   ├── 关闭 OEM 功能看是否消失
   ├── 定位崩溃栈或异常点
   └── 找到 OEM Hook 的具体代码位置
   ↓
修复:
   ├── Bootloop → 源码级修复
   ├── App 闪退 → App 适配 + OEM 配置
   ├── 功能失效 → 白名单/黑名单调整
   └── 性能问题 → HAL 配置 + Kernel 调参
```

---

## 附录 A:核心源码路径索引

| 文件 | 完整路径 | 说明 |
|---|---|---|
| `logcat` | `/system/bin/logcat` | 日志抓取工具 |
| `dumpsys` | `/system/bin/dumpsys` | 系统服务状态 |
| `atrace` | `/system/bin/atrace` | systrace 抓取 |
| `simpleperf` | `/system/bin/simpleperf` | CPU profile |
| `cmd overlay` | `/system/bin/cmd overlay` | RRO overlay 管理 |
| `cmd miui` | `/system/bin/cmd miui` | MIUI 特定命令 |
| `cmd coloros` | `/system/bin/cmd coloros` | ColorOS 特定命令 |

---

## 附录 B:故障类型速查表

| 故障类型 | 5 大 OEM 各自高发 | 通用修复 |
|---|---|---|
| Bootloop | 华为、小米 | 加边界检查 |
| App 闪退 | OPPO、vivo | App 适配 |
| 功能失效 | 小米、华为 | 白名单/配置 |
| 性能问题 | iQOO、一加 | HAL 配置 |
| 兼容性问题 | 所有厂商 | App 适配 |

---

## 附录 C:30 分钟抓取清单速查

| 时间 | 工具 | 输出 |
|---|---|---|
| 0-2 分钟 | logcat -b crash | 崩溃栈 |
| 0-2 分钟 | logcat -b main | 主日志 |
| 2-5 分钟 | dumpsys | 系统服务状态 |
| 5-10 分钟 | systrace / Perfetto | trace 文件 |
| 10-15 分钟 | OEM 关闭功能 | 验证假设 |
| 15-30 分钟 | 分析 | 根因定位 |

---

## 附录 D:工程基线表(OEM Hook 故障应急)

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|---|---|---|---|
| **Bootloop 应急响应时间** | < 30 分钟 | OEM 团队必修 | recovery 模式必备 |
| **App 兼容性测试覆盖** | Top 5000 App | 必须覆盖 | Top 200 必须 |
| **白名单更新频率** | 每周 | 新 App 上线快 | 必须云端同步 |
| **Hook 兼容性测试** | 自动化 | 必须 CI 集成 | 每次 Hook 修改必测 |
| **5 秒定位覆盖率** | > 80% | 不断完善 | 维护速查表 |
| **30 分钟根因覆盖率** | > 60% | 持续训练 | 必须实战演练 |
| **OTA 推送时效** | < 24 小时 | 紧急问题必须 | OTA 通道必须稳定 |
| **Hook 代码审查** | 必须 | 每次 Hook 修改 | 防止 Bootloop |

---

## 篇尾 - 系列完结

```
┌─────────────────────────────────────────────────────────────┐
│           Android OEM Hook 技术解析 系列完结                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  完成 17 个文件:                                            │
│ ├── 
│  ├── 01-全景图                                              │
│  ├── 02-Kernel 层 Hook                                      │
│  ├── 03-HAL 层 Hook                                        │
│  ├── 04-Native 层 Hook                                     │
│  ├── 05-ART 层 Hook                                        │
│  ├── 06-Framework-Binder 层 Hook                            │
│  ├── 07-App-UI 层 Hook                                     │
│  ├── 08-场景 1 隐私保护                                     │
│  ├── 09-场景 2 后台治理                                     │
│  ├── 10-场景 3 应用双开                                     │
│  ├── 11-场景 4 游戏调度                                     │
│  ├── 12-场景 5 折叠屏适配                                   │
│  ├── 13-五大 OEM 风格对比                                   │
│  ├── 14-OEM Hook 演进                                     │
│  ├── 15-Bootloop 与兼容性速查                              │
│  └── README-OEM_Hook 系列(批 6 输出)                       │
│                                                             │
│  总产出:~700KB / ~13000 行                                  │
│                                                             │
│  核心价值:                                                  │
│  ├── 5 秒定位 OEM Hook 故障                                 │
│  ├── 30 分钟抓到根因                                        │
│  └── 5 秒阅读 Hook 源码                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

> **本篇是系列的最后一篇(15),也是实战速查的"压轴"。**
> 
> 下一步:撰写 **README-OEM_Hook 系列.md**(批 6 收尾),作为整个系列的总入口。
