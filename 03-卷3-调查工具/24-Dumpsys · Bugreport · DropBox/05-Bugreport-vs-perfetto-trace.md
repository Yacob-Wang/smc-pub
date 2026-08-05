# 03-Forensics/Bugreport · 05 · Bugreport vs perfetto trace：工具边界

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 取证工具选择
>
> **强依赖**：[04 实战 5 类典型案例](04-Bugreport-实战5类典型案例.md) · [04-Tool/Perfetto/01-Perfetto系统总览与架构设计](../../../../03-卷3-调查工具/22-Perfetto 全栈使用/01-Perfetto系统总览与架构设计.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 bugreport 和 perfetto trace 各自的"擅长什么 / 不擅长什么"讲清楚，5 类事故下"用哪个 / 都要用 / 都不用"
- **不是**：不复述 [04-Tool/Perfetto/01](../../../../03-卷3-调查工具/22-Perfetto 全栈使用/01-Perfetto系统总览与架构设计.md) Perfetto 架构；不复述 [01]-[04] Bugreport 已有内容
- **承接自**：[04 §6 通用取证清单](04-Bugreport-实战5类典型案例.md) → 本文给"工具选择"维度
- **衔接去**：[Bugreport 系列收官](05-Bugreport-vs-perfetto-trace.md)（本文是收官篇） / [04-Tool/Perfetto/04-Perfetto定制化实战](../../../../03-卷3-调查工具/22-Perfetto 全栈使用/04-Perfetto定制化实战：ANR后自动抓取trace.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章给"本质差异"对照表 | 5 类事故用错工具的根因 |
| 2 | 第 2 章 5 类事故对应表 | oncall 5 秒选对 |
| 3 | 第 7 章 Bugreport 5 篇引用矩阵 | 系列收官 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**bugreport = 静态快照（"设备现在是什么状态"），perfetto trace = 时间线（"这段时间内发生了什么"）——oncall 现场两者组合，5 类事故各取所长。**

理解两者的本质差异 = 现场 5 秒选对工具，不浪费时间在错的工具上。

---

## 1. 两个工具的本质差异

### 1.1 本质对照表

| 维度 | bugreport | perfetto trace |
|:-----|:----------|:---------------|
| **本质** | 静态快照 | 时间线 |
| **回答的问题** | "设备现在什么状态" | "这段时间内发生了什么" |
| **覆盖范围** | 全设备（300+ 文件）| 单一进程 / 资源（深）|
| **时间维度** | 当前时刻 | 几秒 ~ 几分钟 |
| **数据量** | 100-300MB | 1-100MB |
| **生成耗时** | 30-120 秒 | 几秒 ~ 几十秒 |
| **分析工具** | unzip + grep | ui.perfetto.dev |
| **AOSP 17 状态** | 默认 | 默认（替代 systrace）|
| **核心信息** | dumpsys + logcat + tombstones | ftrace events + 性能计数 |

### 1.2 真实场景对比

**场景：app 启动慢 8 秒**

| 用 bugreport | 用 perfetto |
|:-----------|:-----------|
| 看 meminfo（8GB 充足）| 看 zygote fork 时间（200ms）|
| 看 PSI 压力（some avg10 < 5%）| 看 class load 时间（4.5s，慢在 ART）|
| 看 logcat（无 NE / ANR）| 看 dex2oat 时间（1.5s，systrace 看到）|
| 看 dropsys（无 dropbox）| 看 view inflate（500ms）|
| **结论：内存 OK、CPU OK、logcat OK**| **结论：class load + dex2oat 是慢的根因**|
| **能找到慢但定位不到具体代码**| **精确定位到 dex2oat 在 PackageManager.loadClassLoader** |

**关键洞察**：
- bugreport = 静态概览（"什么慢"）
- perfetto = 动态细节（"哪里慢"）
- oncall 现场 90% 是先 bugreport 看到"什么慢" → 再 perfetto 找"哪里慢"

### 1.3 4 大本质区别

| 区别 | bugreport | perfetto |
|:-----|:----------|:---------|
| **维度** | 静态（当前状态）| 动态（时间线）|
| **粒度** | 粗（系统级）| 细（函数级）|
| **触发** | 任何时候 | 抓现场时 |
| **存储** | 文件 dump | 事件流 |

---

## 2. 5 类事故的对应工具

### 2.1 ANR 现场

| 工具 | 用 | 不用 |
|:-----|:---|:-----|
| **bugreport** | ⭐ **必用**：看 traces.txt 主线程栈、dumpsys_activity 列表、logcat ANR 触发 | - |
| **perfetto** | 🟡 **可选**：看 main thread 卡在哪一秒、blocked on 哪个锁、CPU 调度 | 简单 ANR 不必 |

**结论**：**bugreport 必用，perfetto 选用**（90% 的 ANR 用 bugreport 就够）

### 2.2 NE 现场

| 工具 | 用 | 不用 |
|:-----|:---|:-----|
| **bugreport** | ⭐ **必用**：看 tombstone backtrace / signal / maps、logcat crash 触发 | - |
| **perfetto** | ❌ **不用**：NE 现场在 crash，trace 抓不到 | - |

**结论**：**只用 bugreport**（perfetto 抓不到 NE 现场）

### 2.3 OOM 现场

| 工具 | 用 | 不用 |
|:-----|:---|:-----|
| **bugreport** | ⭐ **必用**：看 meminfo / PSI / dumpsys_meminfo / proc/slabinfo | - |
| **perfetto** | 🟡 **可选**：看哪个 native heap 在涨、mmap 频率、GC 频率 | 简单 OOM 不必 |

**结论**：**bugreport 必用，perfetto 选看 native heap 增长曲线**

### 2.4 KE 现场

| 工具 | 用 | 不用 |
|:-----|:---|:-----|
| **bugreport** | ⭐ **必用**：看 last_kmsg / dmesg / ramoops / kallsyms | - |
| **perfetto** | ❌ **不用**：KE 在 kernel 层，trace 抓不到 | - |

**结论**：**只用 bugreport**（perfetto 在 user space）

### 2.5 性能 / 卡顿

| 工具 | 用 | 不用 |
|:-----|:---|:-----|
| **bugreport** | 🟡 **有限**：看 gfxinfo / procstats 概览 | 深度分析不够 |
| **perfetto** | ⭐ **必用**：看 frame time / CPU 调度 / IO 等待 / binder call | - |

**结论**：**perfetto 必用，bugreport 看概览**（性能问题 80% 靠 trace）

### 2.6 bootloop 现场

| 工具 | 用 | 不用 |
|:-----|:---|:-----|
| **bugreport** | ⭐ **必用**：看 last_kmsg / init log / SELinux denied | - |
| **perfetto** | ❌ **不用**：boot 期间抓不到（system 没起来）| - |

**结论**：**只用 bugreport**

### 2.7 5 类事故工具速查

| 事故 | bugreport | perfetto | 最佳组合 |
|:-----|:----------|:---------|:--------|
| ANR | ⭐ 必用 | 🟡 选看 | bugreport → perfetto 选看 |
| NE | ⭐ 必用 | ❌ 不用 | bugreport 单独 |
| OOM | ⭐ 必用 | 🟡 选看 | bugreport → perfetto 选看 native |
| KE | ⭐ 必用 | ❌ 不用 | bugreport 单独 |
| 性能/卡顿 | 🟡 概览 | ⭐ 必用 | perfetto → bugreport 看大图 |
| bootloop | ⭐ 必用 | ❌ 不用 | bugreport 单独 |

---

## 3. 何时用哪个的 5 条铁律

### 3.1 铁律 1：5 类症状级事故 → bugreport 必用

```
ANR / NE / OOM / KE / bootloop 5 类"事故"：
→ bugreport 必用（一次性拿到全状态）
→ perfetto 选用（只特定场景）
```

### 3.2 铁律 2：性能级问题 → perfetto 必用

```
启动慢 / 卡顿 / 高 CPU / 帧 jank 4 类"性能"问题：
→ perfetto 必用（时间线分析）
→ bugreport 选看（看 meminfo / PSI / gfxinfo 概览）
```

### 3.3 铁律 3：组合拳 = bugreport 先 + perfetto 后

```
步骤 1：bugreport 拿到全状态
       → 5 分钟看出"什么慢 / 哪里死"
步骤 2：perfetto 抓目标进程 / 资源
       → 5 分钟看出"具体哪个函数慢 / 哪一行死"
步骤 3：交叉验证（logcat 时间戳对齐）
```

### 3.4 铁律 4：现场时间窗口 = perfetto 决定

```
[1-10 秒] 短现场（ANR / 启动）→ perfetto 5-10 秒 trace
[10-60 秒] 中现场（卡顿）→ perfetto 30-60 秒 trace
[> 1 分钟] 长现场（内存泄漏）→ bugreport 看长期趋势
[持续] bootloop → bugreport 必然（perfetto 抓不到）
```

### 3.5 铁律 5：用户层 vs kernel 层

```
用户层（app / framework / native daemon）：
→ bugreport + perfetto 都可用
kernel 层（kernel panic / 驱动）：
→ 只用 bugreport（perfetto 不在 kernel）
```

---

## 4. 工具组合拳：3 个实战场景

### 4.1 场景 1：app 启动慢 8 秒（5 分钟定位 + 5 分钟找代码）

**Step 1：bugreport 看到大图（2 分钟）**

```bash
$ adb bugreport /tmp/start_slow.zip
$ unzip /tmp/start_slow.zip -d /tmp/br
$ grep "MemAvailable" /tmp/br/proc/meminfo
# 4.2GB（充足）
$ grep "ANR\|FATAL" /tmp/br/logcat/logcat_main.txt
# 无
$ grep "Slow operation" /tmp/br/logcat/logcat_main.txt
# 找到 app 启动 8s
```

**Step 2：perfetto 抓启动 trace（30 秒 + 2 分钟）**

```bash
$ adb shell perfetto -o /data/misc/perfetto-traces/boot.perfetto-trace \
    -t 30s -b 64mb sched freq idle am wm gfx view binder_driver hal input
$ adb pull /data/misc/perfetto-traces/boot.perfetto-trace
$ open https://ui.perfetto.dev  # 上传看
```

**Step 3：ui.perfetto.dev 看 4 个时间点（3 分钟）**

```
[0-500ms] zygote fork（正常 200ms）
[500-3000ms] PackageManager.loadClassLoader（2500ms）→ 慢！ART dex2oat
[3000-5000ms] app 启动（2000ms）→ 正常
[5000-8000ms] splash screen → main activity（3000ms）→ 慢！view inflate
```

**Step 4：根因 + fix（2 分钟）**

```
根因 1：PackageManager.loadClassLoader 慢 2.5s（dex2oat 卡）
根因 2：main activity view inflate 慢 3s（嵌套深）

fix：
- 启用 Profile-guided dexopt（启动前 pre-compile）
- main activity 改用 viewstub 延迟加载
```

### 4.2 场景 2：app 偶发卡顿 1 秒（5 分钟定位 + 5 分钟找代码）

**Step 1：bugreport 看 PSI 和 meminfo（2 分钟）**

```bash
$ grep "some avg10" /tmp/br/proc/pressure/cpu
# some avg10=8.5 → CPU 有压力但不大
$ grep "MemAvailable\|Committed_AS" /tmp/br/proc/meminfo
# 充足
```

**Step 2：perfetto 持续抓 1 分钟（30 秒 + 2 分钟）**

```bash
$ adb shell perfetto -o /data/misc/perfetto-traces/jank.perfetto-trace \
    -t 60s -b 64mb sched freq idle am wm gfx view binder_driver hal input
```

**Step 3：ui.perfetto.dev 看 5 个慢帧（3 分钟）**

```
[10.5s] frame 1 卡 1100ms → 看 main thread blocked on lock at FooActivity.java:88
[25.3s] frame 2 卡 850ms → 同样位置
[40.1s] frame 3 卡 1200ms → 同样位置
```

**Step 4：根因 + fix（2 分钟）**

```
根因：FooActivity.onCreate:88 同步等待网络回调（@Worker-1 持锁）
fix：网络回调用 LiveData / Flow 异步
```

### 4.3 场景 3：后台进程被 OOM 杀（5 分钟定位）

**Step 1：bugreport 看 meminfo（2 分钟）**

```bash
$ grep "MemAvailable" /tmp/br/proc/meminfo
# 80MB → 风险
$ grep "Pressure" /tmp/br/proc/pressure/memory
# some avg10=45 → 内存压力高
```

**Step 2：perfetto 选看（不是必用）**

```bash
# 看哪个 native heap 在涨
$ adb shell perfetto -o /data/misc/perfetto-traces/native_grow.perfetto-trace \
    -t 30s -b 32mb process
```

**Step 3：bugreport dumpsys 找大进程（1 分钟）**

```bash
$ grep -A 5 "Pss Total" /tmp/br/dumpsys/dumpsys_meminfo.txt | sort -k3 -n -r | head
# 找到 com.example.app 1.2GB（最大）
# Native Heap 600MB（Bitmap 缓存）
```

**Step 4：fix**

```
根因：app native heap 600MB（Bitmap 缓存）
fix：LruCache 减半 + 改 RGB_565
```

---

## 5. 性能对比（AOSP 17 实测）

### 5.1 抓取耗时

| 操作 | bugreport | perfetto |
|:-----|:----------|:---------|
| 启动抓取 | 30-120 秒 | < 1 秒（perfetto 启动）|
| 抓 30 秒 | 30-120 秒 | 30 秒（实际 30 秒）|
| 抓 5 分钟 | 30-120 秒 | 300 秒（5 分钟）|
| 后台抓 | 30-120 秒 | 任意长（rodata 上限）|

### 5.2 数据量

| 操作 | bugreport | perfetto |
|:-----|:----------|:---------|
| 1 个 trace | 100-300 MB | 1-10 MB（小）|
| 长 trace | 不变（100-300 MB）| 100 MB+（看时间）|
| 5 分钟 trace | - | 100-500 MB |

### 5.3 分析耗时

| 操作 | bugreport | perfetto |
|:-----|:----------|:---------|
| 5 分钟定位 | 5-15 分钟（grep）| 5-10 分钟（UI）|
| 10 分钟深度 | 15-30 分钟 | 15-20 分钟 |
| 30 分钟完整 | 30-60 分钟 | 30-60 分钟 |

---

## 6. oncall 5 分钟决策

```
[问题] 收到事故
  ↓
[1] 30 秒判断事故类型（5 秒）
  ├─ "事故"（ANR / NE / OOM / KE / bootloop）→ bugreport
  ├─ "性能"（卡顿 / 启动慢 / 高 CPU）→ perfetto
  └─ 模糊 → 两者都用
  ↓
[2] 抓现场
  ├─ bugreport：30-120 秒
  └─ perfetto：30-300 秒（看现场长度）
  ↓
[3] 5 分钟定位
  ├─ bugreport：grep 关键文件（见 [03 §6 30 命令]）
  └─ perfetto：ui.perfetto.dev 看时间线
  ↓
[4] 交叉验证
  - bugreport logcat 时间戳 + perfetto 事件时间对齐
  ↓
[5] 出报告（5 分钟）
```

**总耗时**：5 + 5 + 5 = **15 分钟**（不含抓现场）

---

## 7. Bugreport 5 篇引用矩阵（收官）

```
┌────────────────────────────────────────────────────────────┐
│  Bugreport 5 篇全引用矩阵                                  │
└────────────────────────────────────────────────────────────┘

[01] 总览与生成/解析
  ↓ 引用 → [02] 结构 / [03] 速查
  ↑ 引用 ← 全部

[02] 目录结构全梳理
  ↓ 引用 → [03] 速查 / [04] 实战
  ↑ 引用 ← [01] [03] [04] [05]

[03] 关键文件速查
  ↓ 引用 → [04] 实战 / [05] 工具边界
  ↑ 引用 ← [02] [04]

[04] 实战 5 类典型案例
  ↓ 引用 → [05] 工具边界
  ↑ 引用 ← [02] [03] [05]

[05] vs perfetto（你正在读）
  ↑ 引用 ← 全部 4 篇
```

### 7.1 5 篇统一资源

- **真实工具**：`adb bugreport` / `perfetto` / `ui.perfetto.dev`
- **真实命令**：`unzip` + `grep` + 30 个取证命令
- **真实场景**：ANR / NE / OOM / KE / bootloop 5 类
- **真实数据**：bugreport 100-300MB / perfetto 1-100MB
- **真实耗时**：5 类事故 5-15 分钟定位

### 7.2 5 篇核心 takeaway

- **5 类症状级事故** → bugreport 必用
- **性能问题** → perfetto 必用
- **组合拳** = bugreport 先 + perfetto 后
- **oncall 现场** 5 分钟决策（事故 / 性能 / 模糊）

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [04-Tool/Perfetto/01-Perfetto系统总览与架构设计](../../../../03-卷3-调查工具/22-Perfetto 全栈使用/01-Perfetto系统总览与架构设计.md) | perfetto 完整 |
| [04-Tool/Perfetto/03-Perfetto与statsd联动机制](../../../../03-卷3-调查工具/22-Perfetto 全栈使用/03-Perfetto与statsd联动机制.md) | perfetto + statsd |
| [04-Tool/Perfetto/04-Perfetto定制化实战：ANR后自动抓取trace](../../../../03-卷3-调查工具/22-Perfetto 全栈使用/04-Perfetto定制化实战：ANR后自动抓取trace.md) | perfetto 自动抓 |
| [06-Foundation/Tools/Tracing/20-Trace抓取方法全面指南](../../../03-卷3-调查工具/26-断点与 Native 调试/20-Trace抓取方法全面指南：ftrace-atrace-systrace-perfetto.md) | 4 大 trace 对比 |
| [04-Tool/Dumpsys/12-dumpsys实战SOP](../../../../03-卷3-调查工具/24-Dumpsys · Bugreport · DropBox/12-dumpsys实战SOP.md) | dumpsys 完整 |
| [06-Foundation/Tools/Android_Tools/Logcat_Complete_Guide](../../../03-卷3-调查工具/26-断点与 Native 调试/Logcat_Complete_Guide.md) | logcat 完整 |
| [02-Symptom/S00-S09 7 大症状](../../02-Symptom/) | 7 大症状 |
| [03-Forensics/F00-F07 7 大取证](../../03-Forensics/) | 取证总览 |
| [06-Case/Cases-Extended/](../../../06-Case/Cases-Extended/) | 实战案例 |

---

## 9. Bugreport 系列 5 篇完结 + 自检

### 9.1 看完 Bugreport 5 篇全系列的自检

- [ ] 能说 5 类 bugreport 工具的差异
- [ ] 能说 AOSP 17 bugreport.zip 6 大子目录
- [ ] 能用 30 grep 命令直接取证
- [ ] 能用 7 大症状完整路径
- [ ] 能用 5 步法处理 ANR / NE / OOM / KE / bootloop
- [ ] 能用 5 分钟决策判断用 bugreport 还是 perfetto
- [ ] 能用组合拳（bugreport 先 + perfetto 后）
- [ ] 知道何时只用 bugreport（NE/KE/bootloop）
- [ ] 知道何时只用 perfetto（性能）
- [ ] 知道何时都要用（模糊事故）

### 9.2 收官话

Bugreport 这条线在稳定性架构师的能力模型里属于**"取证落地"层**——拿到 bugreport 能 5 分钟定位 7 大症状的根因。

下一步推荐读：
- [04-Tool/Perfetto/01-Perfetto系统总览与架构设计](../../../../03-卷3-调查工具/22-Perfetto 全栈使用/01-Perfetto系统总览与架构设计.md) — perfetto 深入
- [04-Tool/Dumpsys/12-dumpsys实战SOP](../../../../03-卷3-调查工具/24-Dumpsys · Bugreport · DropBox/12-dumpsys实战SOP.md) — dumpsys 深入
- [06-Case/Cases-Extended/](../../../06-Case/Cases-Extended/) — 实战案例（待补）

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，Bugreport 5 篇收官）
