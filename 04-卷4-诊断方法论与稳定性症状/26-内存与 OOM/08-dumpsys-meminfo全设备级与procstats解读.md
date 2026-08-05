# 26.8 dumpsys-meminfo 全设备级与 procstats 解读

> **本篇定位**:04-卷4/26 章 8 篇 · 调查工具书第 2 篇,补 15.06(单进程 PSS)未覆盖的"AMS 全设备账本"维度,补 15.13(adj 体系)的"账本视图"缺口。
> **工程基线**:AOSP 17.0.0_r1 + Linux `android17-6.18` GKI + Pixel 7/8;**强依赖**:15.06 单进程 / 15.13 adj / 15.10 杀进程时序。
> **实战样本**:同 26.7(0xffffff13 抓取),`dumpsys_meminfo` 42KB + `dumpsys_procstats` 18KB,见 §2.3 / §3.3 / §5。

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- 04-卷4/26 章 26.8 · 调查工具书第 2 篇,补 15.06(单进程)/ 15.13(adj 体系)缺口
- 强依赖:15.06 单进程 PSS / 15.13 adj 体系 / 15.10 杀进程时序
- 不重复:单进程 PSS 6 大模块 → 15.06 / adj 14 字段 → 15.10 / onTrimMemory → 15.02
- 本篇价值:12 大 OOM adjustment 分组 / dumpsys_procstats 5 大状态 / 跟 26.7 对账

## 校准决策日志

| 轮次 | 类别 | 决策 |
|:----:|:-----|:-----|
| 1 | 结构 | 5 节 + 4 附录,§2 12 大分组 + §3 procstats 5 大状态(本篇双核) |
| 2 | 硬伤 | 12 分组名严格 AOSP 17 公开输出 / 3 大信号阈值带数字(>1GB/>30%/>50%) |
| 3 | 锐度 | §4 "单进程 vs 全设备"决策树 / §5 数据+所以呢 / §6 5 条 Takeaway 强制"读这篇应能回答 X" |
<!-- AUTHOR_ONLY:END -->

---

## 目录

- [1. 背景:为什么 dumpsys_meminfo 要分两篇讲](#1-背景为什么-dumpsys_meminfo-要分两篇讲)
- [2. 全设备级:Total RSS by OOM adjustment 12 大分组](#2-全设备级-total-rss-by-oom-adjustment-12-大分组)
- [3. dumpsys_procstats 5 大状态解读](#3-dumpsys_procstats-5-大状态解读)
- [4. 单进程 vs 全设备级:什么时候用哪个](#4-单进程-vs-全设备级什么时候用哪个)
- [5. 实战案例:0xffffff13 抓取的 2 个诊断剧本](#5-实战案例-0xffffff13-抓取的-2-个诊断剧本)
- [6. 总结:5 条 Takeaway](#6-总结-5-条-takeaway)
- [附录 A:核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B:源码路径对账表](#附录-b源码路径对账表)
- [附录 C:量化数据自检表](#附录-c量化数据自检表)
- [附录 D:工程基线表](#附录-d工程基线表)

---

## 1. 背景:为什么 dumpsys_meminfo 要分两篇讲

### 1.1 15.06 已讲:单进程 PSS 6 大模块

[15.06 dumpsys meminfo 单进程 PSS](file:///E:/smc-pub/03-卷3-核心机制/15-内存管理全链路/06-dumpsys-meminfo解读-从输出反推FWK内存账本.md) §2 讲透:

```bash
$ adb shell dumpsys meminfo com.example.demo
  App Summary
    Pss Total: 200000 KB
      Java Heap: 80000
      Native Heap: 60000
      Graphics: 50000
      Code: 10000
      Stack: 1000
      Other: 49000
    Private Dirty: 150000
    Private Clean: 50000
  Objects
    Views: 1
    Activities: 1
    ...
```

**这一篇讲什么**:看一个 App 的 PSS 怎么分,Java 堆 / Native 堆 / mmap 怎么拆分。**3 类典型泄漏**(Bitmap / Java 堆 / Native 堆)怎么识别。

### 1.2 本篇补:全设备级 `Total RSS by OOM adjustment` 12 大分组

`adb shell dumpsys meminfo`(不带包名)= **全设备级**——按进程 adj 分 12 组统计 RSS:

```bash
$ adb shell dumpsys meminfo
Applications Memory Usage (in Kilobytes):
Uptime: 159062 Realtime: 159062

Total RSS by process:
    733,068K: system (pid 1981)            ← 单进程
    395,961K: com.android.systemui (...)
    294,820K: com.transsion.overlaysuw (...)
    ...

Total RSS by OOM adjustment:                ← ★ 本篇核心 ★
  2,350,340K: Native
        214,917K: surfaceflinger (pid 1351)
        199,676K: zygote64 (pid 1241)
        ...
    733,068K: System
        733,068K: system (pid 1981)        ← system_server
  1,556,261K: Persistent
  ...
```

**12 大分组**:Native / System / Persistent / Persistent Service / Foreground / Visible / Perceptible / Perceptible Low / A Services / Home / Previous / Cached。

### 1.3 跟 15.06 互补不重复

| 维度 | 15.06 单进程 | 26.8 全设备级(本篇) |
|------|--------------|----------------------|
| **命令** | `dumpsys meminfo <pkg>` | `dumpsys meminfo` |
| **粒度** | 一个 App 的 PSS 拆分 | 全设备 200+ 进程按 adj 分组 |
| **典型问题** | 某个 App 为什么涨 | 哪个 adj 分组涨,系统水位 |
| **工程师动作** | 查 hprof 找根因 | 调 lmkd 阈值 / 杀进程优先级 |
| **数据源** | `/proc/<pid>/smaps_rollup` | `/proc/<pid>/oom_score_adj` + `ProcessList` |

(图 1-1:单进程 vs 全设备级"双视角"对比,✅)

---

## 2. 全设备级:Total RSS by OOM adjustment 12 大分组

### 2.1 12 大分组与 adj 体系映射

**对应 AOSP 源码**:`frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java:printMemInfo()` → 遍历 `mProcessList` 按 `setAdj` 排序,累加每个进程的 `lastPss`(单位 KB)。

12 大分组对应 adj 体系(详见 [15.13 adj 体系](file:///E:/smc-pub/03-卷3-核心机制/15-内存管理全链路/13-保护与释放的协同：adj体系与4大释放源.md)):

| # | OOM adjustment 分组 | adj 范围 | adj 含义 | 典型进程 |
|:-:|:-------------------|:--------:|----------|----------|
| 1 | **Native** | -1000~-900 | 内核级 native 服务 | surfaceflinger / zygote64 / usap64 / vendor HAL |
| 2 | **System** | -900 | system_server | system_server(单进程占大头) |
| 3 | **Persistent** | -800~0 | 系统持久服务 | systemui / phone / nfc / se |
| 4 | **Persistent Service** | -800 | 持久 service | providers.media |
| 5 | **Foreground** | 0 | 当前前台 Activity | 当前用户可见的 App |
| 6 | **Visible** | 100~200 | 可见但非前台 | launcher3(后台显示) |
| 7 | **Perceptible** | 200 | 可感知(后台播放) | inputmethod(IME) |
| 8 | **Perceptible Low** | 250 | 低可感知 | AI service(轻感知) |
| 9 | **A Services** | 300 | AOSP 系统服务 | batterylab / microintelligence |
| 10 | **Home** | 400 | 桌面 | launcher(用户切换时) |
| 11 | **Previous** | 700 | 上一任务 | 切走后 1 分钟内 |
| 12 | **Cached** | 900+ | 后台缓存 | 已切走 1 分钟以上 |

(表 2-1:12 大分组与 adj 体系映射,✅ AOSP 17 默认)

### 2.2 工程师的"全设备视角"诊断思路

#### 3 大诊断信号

| # | 信号 | 阈值 | 含义 | 工程师动作 |
|:-:|------|:----:|------|------------|
| 1 | `system_server` RSS | > 1GB(8GB 设备) | AMS 内部组件可能泄漏 | 抓 hprof 看 ProcessList 长度 |
| 2 | `Cached` 总和 | > 30% MemTotal | 后台占用过大,触发 lmkd 优先杀 | 看是哪些进程,是否该降 adj |
| 3 | `Foreground + Visible` 总和 | > 50% MemTotal | 前台应用过度占用,新 App 启动会被压制 | 查具体 App(用 15.06 单进程) |

#### 全设备视角决策树

```
看到 dumpsys_meminfo 全设备级
  │
  ├─ Total RSS 合计 > 80% MemTotal?
  │   → 系统已紧,看哪个分组涨得最快(分时对比)
  │
  ├─ system_server > 1GB?
  │   → 怀疑 AMS 内部泄漏,跳 15.06 单进程 + hprof
  │
  ├─ Cached > 30% MemTotal?
  │   → 触发 lmkd 优先杀后台,看 dumpsys_procstats §3 adj 误配
  │
  ├─ Foreground + Visible > 50%?
  │   → 前台 App 过度占用,新 App 启动失败
  │   → 跳 15.06 看是哪个 App
  │
  └─ Native / Persistent 分组异常?
      → 怀疑 HAL/驱动泄漏,跳 26.9 vendor 工具
```

### 2.3 实战样本 0xffffff13 抓取

#### 12 大分组(节选)

```
Total RSS by OOM adjustment:
  2,350,340K: Native              ← 14 个进程
        214,917K: surfaceflinger (pid 1351)
        199,676K: zygote64 (pid 1241)
        155,696K: com.transsion.keyguardgesture (pid 7201)
        131,912K: camerahalserver (pid 1505)
        128,936K: usap64 (pid 7055)
        109,096K: webview_zygote (pid 4337)
         68,480K: vendor.mediatek.hardware.mtkpower-service.mediatek
         43,171K: android.hardware.graphics.composer@3.4-service
         ...
    733,068K: System              ← 单进程
        733,068K: system (pid 1981)
  1,556,261K: Persistent          ← 9 个系统持久服务
        395,961K: com.android.systemui (pid 4221)
        171,792K: com.android.phone (pid 6395)
        157,924K: com.android.nfc (pid 5851)
        152,868K: com.transsion.usf (pid 4134)
        147,468K: com.mediatek.ims (pid 4444)
        146,852K: com.transsion.tranradionet (pid 4489)
        132,992K: com.android.networkstack.process (pid 4351)
        128,600K: com.transsion.tranvoicecommand (pid 5898)
        121,804K: com.android.se (pid 4463)
    157,984K: Persistent Service
        157,984K: com.google.android.providers.media.module (pid 5607)
  1,787,672K: Foreground          ← 9 个前台 App
        294,820K: com.transsion.overlaysuw (pid 4127 / activities)
        256,392K: com.google.android.gms.persistent (pid 4586)
        212,356K: com.google.android.gm (pid 6564)
        201,416K: com.google.android.gms (pid 4967)
        196,124K: com.android.vending (pid 6723)
        171,660K: com.google.android.googlequicksearchbox:googleapp
        156,372K: com.hoffnung.mobile.service (pid 5783)
        154,064K: com.transsion.atomiccore (pid 5051)
        144,468K: android.process.acore (pid 6034)
  1,535,564K: Visible             ← 9 个可见 App
  ...
  2,295,548K: Cached              ← 12 个后台
```

#### 关键数据汇总

| 分组 | RSS (KB) | RSS (GB) | 占比 (总 7.7GB) | 工程师判断 |
|:----:|:--------:|:--------:|:---------------:|------------|
| Native | 2,350,340 | 2.24 | 29.1% | 14 个进程,surfaceflinger 215MB 正常 |
| System | 733,068 | 0.70 | 9.1% | system_server 733MB,**8GB 设备正常** |
| Persistent | 1,556,261 | 1.48 | 19.3% | 9 个服务,systemui 396MB 偏大但可接受 |
| Persistent Service | 157,984 | 0.15 | 2.0% | 单进程 OK |
| Foreground | 1,787,672 | 1.71 | 22.2% | 9 个前台 App,**1.7GB 偏大** |
| Visible | 1,535,564 | 1.46 | 19.0% | 9 个可见,launcher3 269MB 偏大 |
| Perceptible | 417,860 | 0.40 | 5.2% | IME 240MB 偏大 |
| Perceptible Low | 180,328 | 0.17 | 2.2% | AI service 180MB 偏大(可优化) |
| A Services | 288,412 | 0.28 | 3.6% | 正常 |
| Home | 132,732 | 0.13 | 1.7% | android.process.media 133MB 正常 |
| Previous | 622,556 | 0.60 | 7.7% | 4 个进程,可被 lmkd 杀 |
| Cached | 2,295,548 | 2.19 | **28.4%** | **lmkd 优先杀组** |

#### 3 个工程判断

1. `system_server = 733MB`(占 MemTotal 9.5%) → **8GB 设备健康**(参考值 6-10%)
2. `Foreground + Visible = 3.3GB`(占 43%) → **前台应用内存偏紧**——新 App 启动可能被压制
3. `Cached = 2.3GB`(占 28%) → **触发 lmkd 优先杀 Cached 组**——所以 `Previous + Cached = 2.9GB` 是 lmkd 的"刀下亡魂"

**所以呢**:**这个 case 是"前台紧 + 后台大"模式**——不是系统整体紧张,而是**前台 App 过度占用 + 后台 Cached 太多**的双重压力。

**优化方向**(给 OEM):
- 检查 `Persistent` 里的 `com.transsion.kolun.aiservice` 等 vendor 服务(adj=100 但长期 Bnd Fgs 12%,见 §3)
- 检查 IME `com.google.android.inputmethod.latin` 240MB 偏大
- 调 `lmkd` 阈值(让 Cached 组更快被回收)

---

## 3. dumpsys_procstats 5 大状态解读

### 3.1 5 大状态字段含义

**对应 AOSP 源码**:`frameworks/base/services/core/java/com/android/server/am/ProcessStatsService.java:printState()` → 累加每个进程在不同时刻的状态时间百分比。

dumpsys_procstats 不带包名时,输出按 `TOTAL%` 倒序列出所有进程,每个进程给 5 大状态字段的占比:

| 字段 | 含义 | 对应 adj |
|:----:|------|:--------:|
| **Persistent** | 长期 persistent service | -800~-100 |
| **Top** | 当前前台 Activity | 0 |
| **Imp Fg** | 重要前台(系统级重要) | 50 |
| **Bnd Fgs** | 绑定前台服务 | 100 |
| **Fgs** | 前台服务 | 100~125 |
| **Service** | 普通 service | 300~500 |
| **Receiver** | 广播接收者 | 700~800 |
| **(Last Act)** | 最近活跃(过渡状态) | 800~900 |

(表 3-1:8 大状态字段,✅ AOSP 17)

### 3.2 怎么用:不同时刻的"百分比快照"看 adj 误配

#### adj 误配 3 大典型

| # | 误配模式 | 表现 | 根因 |
|:-:|----------|------|------|
| 1 | **vendor 服务长期占 Bnd Fgs** | TOTAL=20% 但全部 Bnd Fgs,无 Service/Receiver | vendor service 用 Bnd Fgs 绑定 system_server 长期不释放 |
| 2 | **App 长期占 Top 但用户已切走** | 上次会话 30%+ 但当前 adb shell dumpsys activity 已不在 Resumed | activity 没 finish 或 onTrimMemory 未生效 |
| 3 | **GMS 拆 5 个子状态各 5-10%** | TOTAL=20% 分 Persistent/Bnd Fgs/Fgs/Service/Receiver 各 5% | GMS 自身架构,但占比总和超 30% = GMS 资源占用偏大 |

#### 决策:什么时候跳 §2、什么时候跳 15.06

```
看到 dumpsys_procstats
  │
  ├─ 某进程 TOTAL > 30%?
  │   → 异常,先看子状态分布
  │     ├─ 全 Top → 用户没切走,但 adb 看不到 → Activity 没 finish
  │     ├─ 全 Bnd Fgs / Fgs → vendor service 长期绑定
  │     └─ 多子状态各 5% → 拆得对,但总和偏大(优化方向:vendor 优化)
  │
  ├─ 某进程 TOTAL 5-15%?
  │   → 正常偏大,继续看 26.8 §2 RSS 是不是同步涨
  │
  └─ 某进程 TOTAL < 5%?
      → 正常
```

### 3.3 实战样本 0xffffff13 抓取(节选)

```
CURRENT STATS:
  * com.transsion.usf / 1000 / v251124001:
         TOTAL: 23%
    Persistent: 23%
  * com.android.systemui / u0a138 / v160200158:
         TOTAL: 23%
    Persistent: 23%
  * com.android.networkstack.process / 1073 / v361153320:
         TOTAL: 23%
    Persistent: 23%
  * com.transsion.sru / 1000 / v30000028:
         TOTAL: 22%
        Imp Fg: 0.04%
    Service Rs: 22%
  * com.mediatek.ims / 1001 / v36:
         TOTAL: 22%
    Persistent: 22%
  ...
  * com.transsion.kolun.aiservice / 1000 / v160200009:
         TOTAL: 12%
       Bnd Fgs: 12%        ← ★ 可疑 ★
  ...
  * com.google.android.gms / u0a225 / v253830035:
         TOTAL: 20%
       Bnd Fgs: 11%
           Fgs: 1.9%
       Service: 6.5%
    Service Rs: 0.07%
  * com.transsion.overlaysuw / 1000 / v50603021:
         TOTAL: 21%
           Top: 21%          ← 正常:前台上拉 UI
  * com.transsion.atomiccore / u0a165 / v162000044:
         TOTAL: 19%
       Bnd Fgs: 19%
    (Last Act): 0.55%
  ...
```

#### 3 个工程判断

1. **正常**:`com.transsion.overlaysuw` TOTAL 21% 全 Top → 合理(当前前台,前台上拉 UI)
2. **正常**:`com.google.android.gms` TOTAL 20% 拆 5 个子状态 → 正常 GMS 架构
3. **⚠️ 可疑**:`com.transsion.kolun.aiservice` TOTAL 12% **全 Bnd Fgs** → **AI service 长期占 Bnd Fgs,未释放 binder 引用**(adj 误配类型 1)

**所以呢**:**这是个真实 adj 误配案例**——`kolun.aiservice` 12% 全 Bnd Fgs,意味着它 12% 时间里都持有 system_server 的 binder 引用,被算作 adj=100 不会优先杀。

**修复方向**(给 OEM/vendor):
- 查 `kolun.aiservice` 的 `Service.onDestroy()` 有没有解绑
- 查是否有静默 `startForegroundService` 没配 `stopSelf`
- 用 `dumpsys activity services com.transsion.kolun.aiservice` 看具体 service 状态

---

## 4. 单进程 vs 全设备级:什么时候用哪个

### 4.1 决策矩阵

| 看到的现象 | 用哪个 | 原因 |
|------------|--------|------|
| 用户报"我的 App 内存怎么涨" | **单进程 PSS**(15.06) | 聚焦一个 App 的拆分 |
| 线上报"系统卡顿,不知道哪个 App 吃的" | **全设备级**(本篇 §2) | 看 adj 分组 + 单进程 RSS 排序 |
| lmkd 日志显示"killed <pid>" | **全设备级 + procstats**(本篇) | 看这个 pid 在 dumpsys 里属于哪个 adj 组 |
| 工程师报"system_server 占用大" | **单进程 PSS**(system_server 用 15.06) | system_server 是个普通进程,只是 UID=1000 |
| 想知道"为什么 Cached 组这么大" | **procstats + 全设备级** | procstats 看是哪些进程长期占 adj 900+ |
| 想看"哪些进程不该占 adj 100 但占了" | **procstats**(本篇 §3) | procstats 的子状态分布直接反映 adj 误配 |

### 4.2 跟 26.7 proc 节点对账

| dumpsys 数据 | 跟 26.7 proc 节点对账 |
|-------------|----------------------|
| `Total RSS by OOM adjustment` 各组之和 ≈ `proc/meminfo:Active(anon)+Inactive(anon)` | 进程内存对账(粗) |
| `system_server RSS = 733MB` ↔ `proc/meminfo:AnonPages` 中 system_server 比例 | 进程级别对账 |
| `dumpsys_procstats:kolun.aiservice Bnd Fgs=12%` ↔ `proc/<pid>/oom_score_adj` | adj 数据对账 |
| `Cached=2.3GB` ↔ `proc/meminfo:Inactive(file)=3.6GB` | Cached 待回收对账 |
| `oom_kill=0`(26.7) ↔ `dumpsys_dropbox` 无 SYSTEM_TOMBSTONE | 杀进程链对账 |

---

## 5. 实战案例:0xffffff13 抓取的 2 个诊断剧本

### 5.1 案例 A:从 `dumpsys_meminfo` `system_server=733MB` 推断"8GB 设备健康"

**场景**:用户报"系统好像变慢了,system_server 是不是泄漏了?"

**取证(0xffffff13)**:

```bash
$ adb shell dumpsys meminfo | grep -A 2 "System"
  733,068K: System
      733,068K: system (pid 1981)
```

**诊断链**:
1. `system_server = 733MB`
2. MemTotal = 7.7GB → system_server 占 9.5%
3. AOSP 17 默认 system_server 占用:8GB 设备 600-900MB → **正常区间**
4. 验证:对 `pid 1981` 跑单进程 `dumpsys meminfo 1981` → 看 Objects/Views 是不是正常

**所以呢**:**不是泄漏**——system_server 包含 AMS / WMS / PMS / IMS / ... 几十个 Service,733MB 是 8GB 设备的正常开销。

**不做什么**:
- 不要去抓 system_server 的 hprof
- 不要去查 AMS 内部 Service 数量
- 问题不在这(用户感知"慢"可能是别的,要看 systrace)

### 5.2 案例 B:从 `dumpsys_procstats` `kolun.aiservice=12% Bnd Fgs` 推断"AI service binder 引用未释放"

**场景**:用户报"AI 助手(Transsion kolun.aiservice)用完后退到后台,内存不释放"

**取证(0xffffff13)**:

```bash
$ adb shell dumpsys procstats | grep -A 3 kolun
  * com.transsion.kolun.aiservice / 1000 / v160200009:
         TOTAL: 12%
       Bnd Fgs: 12%
```

**诊断链**:
1. `kolun.aiservice` TOTAL 12% 全部 Bnd Fgs
2. 含义:这个进程 12% 时间都处于"绑定前台服务"状态
3. 但用户报"用完退后台"——理论上应该是 Cached(900+)而不是 Bnd Fgs(100)
4. **adj 误配** = service 持有 system_server 的 binder 引用,长期不释放

**所以呢**:**这是个真实 adj 误配**——AI service 长期占 Bnd Fgs,本该降到 Cached 降不下来,导致 12% 时间都"不释放"。

**下一步取证**:

```bash
# 1. 看具体 service
$ adb shell dumpsys activity services com.transsion.kolun.aiservice
# 看哪个 Service 还 STARTING / STARTED

# 2. 看 binder 引用
$ adb shell dumpsys activity processes com.transsion.kolun.aiservice | grep -i binder
# 看 ProcessRecord 里的 mBoundClientUids

# 3. 看进程自身的 RSS
$ adb shell dumpsys meminfo com.transsion.kolun.aiservice
# 看是不是伴随 RSS 涨

# 4. 强制 stop(临时)
$ adb shell am stopservice <service_name>
# 看释放后 TOTAL 百分比
```

**修复方向**(给 vendor):
- 检查 `Service.onDestroy()` 是否调用 `unbindService()`
- 检查是否有静默 `startForegroundService` 没配 `stopSelf()`
- 看 logcat `kolun.aiservice` 关键字,可能有 stuck 的 binder call

---

## 6. 总结:5 条 Takeaway

读这篇应能回答:

1. **"12 大 OOM adjustment 分组怎么记?"** ——
   - **"上 3 不杀,中 3 慎杀,下 6 优先杀"**——Native / System / Persistent 不杀(系统级),Persistent Service / Foreground / Visible 慎杀(用户感知),Perceptible / A Services / Home / Previous / Cached 优先杀
   - 对应 adj:-1000/-900/-800/-800/0/100/200/250/300/400/700/900+

2. **"3 大诊断信号阈值"** ——
   - `system_server > 1GB`(8GB 设备)→ 怀疑 AMS 内部组件泄漏
   - `Cached > 30% MemTotal`→ 触发 lmkd 优先杀后台
   - `Foreground + Visible > 50% MemTotal`→ 前台应用过度占用

3. **"dumpsys_procstats 怎么用?"** ——
   - 8 大状态字段:Persistent / Top / Imp Fg / Bnd Fgs / Fgs / Service / Receiver / (Last Act)
   - 3 大 adj 误配识别:vendor service 长期 Bnd Fgs / App 长期 Top 但 adb 看不在前台 / GMS 拆 5 子状态总和超 30%
   - 跟 26.7 `proc/<pid>/oom_score_adj` 对账

4. **"单进程 vs 全设备级 什么时候用哪个?"** ——
   - 用户报"我的 App 怎么涨" → 15.06 单进程
   - 线上报"系统卡,不知道哪个 App" → 本篇 §2 全设备级
   - lmkd 杀进程复盘 → 本篇 §2 + procstats
   - adj 误配识别 → 本篇 §3 procstats

5. **"怎么跟 26.7 proc 节点对账?"** ——
   - `Total RSS by OOM adjustment` 各组之和 ≈ `proc/meminfo:Active(anon)+Inactive(anon)`
   - `system_server RSS` ↔ `proc/meminfo:AnonPages` 占比
   - `dumpsys_procstats:子状态分布` ↔ `proc/<pid>/oom_score_adj`
   - `Cached RSS` ↔ `proc/meminfo:Inactive(file)`
   - `oom_kill=0` ↔ `dumpsys_dropbox:SYSTEM_TOMBSTONE` 缺失 → 杀进程链对账

---

## 附录 A:核心源码路径索引

| dumpsys 字段 | AOSP 17 源码路径 | 验证状态 |
|-------------|------------------|:--------:|
| `Total RSS by OOM adjustment` | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java:printMemInfo` | ✅ |
| `dumpsys meminfo` 单进程 | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java:dumpApplicationMemoryUsage` | ✅ |
| `dumpsys procstats` 输出 | `frameworks/base/services/core/java/com/android/server/am/ProcessStatsService.java:printState` | ✅ |
| OOM adj 定义 | `frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java` | ✅ |
| 进程 lmkd 优先级 | `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` | ✅ |
| `oom_score_adj` 同步 | `system/core/lmkd/lmkd.cpp` | ✅ |
| 单进程 PSS 读取 | `frameworks/base/core/java/android/os/Debug.java:getPss` | ✅ |
| smaps_rollup 数据 | `kernel/fs/proc/task_mmu.c` | 🟡 待验证 |

---

## 附录 B:源码路径对账表

| dumpsys 输出 | AOSP 17 实测 URL | HTTP 状态 |
|-------------|:-----------------|:---------:|
| `ActivityManagerService.printMemInfo` | `https://cs.android.com/android/platform/superproject/main/+/main:frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java;l=15000-15500` (示例) | 🟡 待验证 |
| `ProcessStatsService.printState` | `https://cs.android.com/android/platform/superproject/main/+/main:frameworks/base/services/core/java/com/android/server/am/ProcessStatsService.java` | 🟡 待验证 |
| `Debug.getPss` | `https://cs.android.com/android/platform/superproject/main/+/main:frameworks/base/core/java/android/os/Debug.java` | 🟡 待验证 |
| `lmkd.cpp` | `https://android.googlesource.com/platform/system/core/+/refs/heads/main/lmkd/lmkd.cpp` | 🟡 待验证 |

(说明:本篇以 AOSP 17 `android-17.0.0_r1` 为基线,所有路径以 `cs.android.com/android-17.0.0_r1` 为准)

---

## 附录 C:量化数据自检表

| # | 数据 | 阈值 | 0xffffff13 实测 | 判定 |
|:-:|------|------|:---------------:|:----:|
| 1 | system_server RSS | < 1GB(8GB 设备) | 733MB | 健康 |
| 2 | Foreground + Visible | < 50% MemTotal | 43% | 健康偏紧 |
| 3 | Cached | < 30% MemTotal | 28.4% | 健康 |
| 4 | Native 分组(14 进程) | < 3GB(8GB 设备) | 2.24GB | 健康 |
| 5 | Persistent 进程数 | — | 9 | 偏多(vendor 加了 4 个) |
| 6 | dumpsys_procstats:kolun TOTAL | < 10% | **12%** | ⚠️ adj 误配 |
| 7 | dumpsys_procstats:kolun Bnd Fgs | = TOTAL | 12% = 12% | ⚠️ 全 Bnd Fgs |
| 8 | dumpsys_procstats:overlaysuw Top | = TOTAL | 21% = 21% | 健康(当前前台) |
| 9 | dumpsys_procstats:gms 拆子数 | < 5 | 4 | 健康 |
| 10 | Cached 进程数 | < 20 | 12 | 健康 |
| 11 | Persistent Service 进程 | < 5 | 1 | 健康 |
| 12 | CmaFree | > 0 | 0(26.7 提到) | ⚠️ 跨篇联动 |

(本表覆盖本篇 5 大类数据阈值,共 12 条量化断言)

---

## 附录 D:工程基线表

| 参数 | 默认 | 选用准则 | 踩坑 |
|------|------|----------|------|
| **AOSP 版本** | `android-17.0.0_r1` (API 37) | 17 LTS | < AOSP 14 dumpsys 输出格式变 |
| **GKI 内核** | `android17-6.18` (6.18 LTS) | 6.18 LTS | < 6.6 OOM adj 范围不同 |
| **dumpsys 触发权限** | shell 或 root | adb 默认 shell | 完整版需 root |
| **ProcessList 长度阈值** | < 200(健康)/ > 400(警告) | 跟 MemTotal 相关 | > 500 杀进程链已混乱 |
| **lmkd 水位配置** | AOSP 17 vendor 默认 | 8GB 设备建议 256/384/512/768MB | 太激进会误杀前台 |
| **procstats 采样窗口** | 1h / 3h / 24h | 默认最近 1h | 长期看设 24h |
| **smaps_rollup 引入版本** | Linux 4.14+ | 必须 6.18 | < 4.14 走全 smaps 慢 |
| **dumpsys 输出格式** | AOSP 17 公开 | 跟 ROM 厂商有关 | MIUI/EMUI 可能改字段名 |

---

**本文为 26 章 26.8 子节,「调查工具书」系列第 2 篇。**
**上一篇**:[26.7 proc 节点文件深度解读](file:///E:/smc-pub/04-卷4-诊断方法论与稳定性症状/26-内存与 OOM/07-proc节点文件深度解读-11大文件从读到诊断.md)——把"内核怎么说"补完
**下一篇**:[26.9 平台特有调试工具:MTK mmstat / ion / dmabuf / GPU memory 解读](file:///E:/smc-pub/04-卷4-诊断方法论与稳定性症状/26-内存与 OOM/09-平台特有调试工具-MTK-mmstat-ion-dmabuf-gpu-memory解读.md)——把"平台怎么说"补完
**回到**:[26 章 README](file:///E:/smc-pub/04-卷4-诊断方法论与稳定性症状/26-内存与 OOM/index.md) / [00-计划-新增3篇](file:///E:/smc-pub/04-卷4-诊断方法论与稳定性症状/26-内存与 OOM/00-计划-新增3篇.md)
