# 03-Forensics/Bugreport · 04 · Bugreport 实战 5 类典型案例

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 现场取证
>
> **强依赖**：[03 关键文件速查](03-Bugreport-关键文件速查.md) · [02 目录结构全梳理](02-Bugreport-目录结构全梳理.md) · [06-Foundation/SELinux/04-AVC与avc_denied](../../../01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/SELinux/04-AVC与avc_denied：从一次denied反推策略.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：用 5 个真实可重现的 bugreport 取证案例（ANR / NE / OOM / KE / bootloop），把 [03 §6 30 grep 命令](03-Bugreport-关键文件速查.md) 和 [03 §7 7 大症状路径](03-Bugreport-关键文件速查.md) 跑一遍实战
- **不是**：不复述 [01] [02] [03] 任一篇；不复述 [04-Tool/Dumpsys/12-dumpsys实战SOP](../../../../05-卷5-调查方法论与工具链/33-Dumpsys · Bugreport · DropBox/12-dumpsys实战SOP.md)
- **承接自**：[03 §6 30 grep 命令](03-Bugreport-关键文件速查.md) → 本文用真实 case 走完
- **衔接去**：[05 vs perfetto](05-Bugreport-vs-perfetto-trace.md) / [06-Case/Cases-Extended/](../../../06-Case/Cases-Extended/) / [04-Tool/Dumpsys/12-dumpsys实战SOP](../../../../05-卷5-调查方法论与工具链/33-Dumpsys · Bugreport · DropBox/12-dumpsys实战SOP.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 5 案例覆盖 7 大症状中的 5 个高频 | ANR / NE / OOM / KE / bootloop |
| 2 | 每案例按 5 步：症状 → 抓现场 → 5 命令 → 5 分钟定位 → 报告 | 实战模板 |
| 3 | 第 6 章 5 案例交叉总结 | 给"通用取证清单" |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**5 个真实可重现的 bugreport 取证案例 = oncall 现场 5 分钟定位模板。**

每个案例都按"症状描述 → 抓现场命令 → 5 个关键 grep → 5 分钟定位 → 报告模板"5 步走，耗时 5-15 分钟。**学完 = 把 [01]-[03] 所有方法论过一遍实战**。

---

## 1. 案例 1：ANR 现场（5 分钟）

### 1.1 场景

`com.example.app` 启动时主线程卡死 6 秒，触发 ANR。

### 1.2 完整 5 步取证

**Step 1：抓现场**

```bash
$ adb bugreport /tmp/anr_bugreport.zip
# 等 30-60 秒
$ unzip anr_bugreport.zip -d /tmp/br
```

**Step 2：5 个关键 grep**

```bash
# 1. 找 ANR 触发
$ grep "ANR in" /tmp/br/logcat/logcat_main.txt | head
07-27 10:30:00.123  1234  1234 I ActivityManager: ANR in com.example.app, 
                    Reason: Input dispatching timed out

# 2. 看主线程栈
$ grep -A 30 '"main"' /tmp/br/FS/data/anr/traces.txt
"main" prio=5 tid=7 Blocked
  | group="main" sCount=1 ...
  at java.lang.Object.wait(Native method)
  at com.example.app.FooClass.barMethod(FooClass.java:42)
  - waiting on <0x12345> (a java.lang.Object)

# 3. 找持锁线程
$ grep "held by" /tmp/br/FS/data/anr/traces.txt
  - held by thread tid=12 ("Worker-1")

# 4. 看 Worker-1 在做什么
$ grep -A 30 '"Worker-1"' /tmp/br/FS/data/anr/traces.txt
"Worker-1" prio=5 tid=12 Native
  at android.os.BinderProxy.transactNative(Native method)
  at com.example.app.NetworkHelper.fetchData(NetworkHelper.java:88)

# 5. 看 input 状态
$ grep "Input dispatching" /tmp/br/logcat/logcat_system.txt
07-27 10:30:00.456 Input dispatching timed out waiting because there 
                    are no focused windows
```

**Step 3：5 分钟定位**

```
根因：主线程在等待对象锁（FooClass.barMethod 同步块），
     持锁线程 Worker-1 在做网络请求（Binder 卡住），
     5 秒没回来 → 主线程 ANR
```

**Step 4：fix 方向**

1. **短期**：把 `barMethod` 改成异步，不在主线程同步
2. **中期**：加网络超时（connectTimeout 5s + readTimeout 5s）
3. **长期**：监控 Worker-1 网络调用，避免单次 > 5s

**Step 5：报告模板**

```markdown
# ANR 案例 - com.example.app

## 现场
- 时间：2026-07-27 10:30
- 设备：Pixel 8 (Android 17)
- 触发：用户启动 app
- 现场：bugreport.anr_2026-07-27_10-30.zip (180MB)

## 根因
主线程在 FooClass.barMethod:42 等待 Worker-1 持锁；
Worker-1 在 NetworkHelper.fetchData:88 等待网络 Binder 调用；
网络请求 > 6s，触发 ANR (Input dispatching timed out)。

## 修复
- com.example.app/FooClass.java:42 改异步
- NetworkHelper.java:88 加 5s 超时
- 加 Worker-1 网络调用监控

## 预防
- 主线程不允许有锁等待
- 所有网络调用强制超时
```

---

## 2. 案例 2：NE 现场（5 分钟）

### 2.1 场景

`vendor.hwcomposer` daemon NE 段错误，system 重启一次。

### 2.2 完整 5 步取证

**Step 1：抓现场**

```bash
$ adb bugreport /tmp/ne_bugreport.zip
# 等 30-60 秒
$ unzip ne_bugreport.zip -d /tmp/br
```

**Step 2：5 个关键 grep**

```bash
# 1. 找 FATAL / tombstone
$ grep -E "FATAL|tombstone" /tmp/br/logcat/logcat_crash.txt | head
07-27 14:20:00.123 1234 1234 I vendor.hwcomposer: 
    sending signal 11 to vendor.hwcomposer (pid 1234)

# 2. 看 tombstone 完整
$ cat /tmp/br/FS/data/tombstones/tombstone_00
# 看 signal: 11 (SIGSEGV) fault addr 0x000000000000
# 看 backtrace:
#  #00 pc 0x0000abcd in vendor::hwc::Config::Write() at hwc.cpp:42
#  #01 pc 0x00001234 in main at main.cpp:18

# 3. 看 register + memory map
$ grep "memory map" -A 50 /tmp/br/FS/data/tombstones/tombstone_00 | head
# 找到出错地址属于哪个 .so

# 4. 看 dropbox
$ grep "vendor.hwcomposer" /tmp/br/dumpsys/dumpsys_dropbox.txt | head
# 看到 dropbox 已有这条记录

# 5. 看前后 30 秒
$ grep "vendor.hwcomposer" /tmp/br/logcat/logcat_main.txt | head -50
# 看到 14:19:55 之前 daemon 正常
# 14:19:56 有一次 "Config reload" 触发
# 14:20:00 NE
```

**Step 3：5 分钟定位**

```
根因：vendor.hwcomposer 14:19:56 收到 Config reload 信号，
     Config::Write 函数访问了空指针（fault addr 0x0），
     SIGSEGV 触发 NE，tombstone 在 data/tombstones/tombstone_00
```

**Step 4：fix 方向**

1. **短期**：`Config::Write` 加 nullptr check
2. **中期**：看 Config::Write 拿什么指针空，加 verbose log
3. **长期**：config reload 时 mutex 保护

**Step 5：报告模板**

```markdown
# NE 案例 - vendor.hwcomposer

## 现场
- 时间：2026-07-27 14:20
- 设备：Pixel 8 (Android 17)
- 触发：Config reload 信号
- 现场：bugreport.ne_2026-07-27_14-20.zip (190MB)

## 根因
Config::Write 访问空指针（fault addr 0x0），SIGSEGV 触发 NE。
Tombstone 在 FS/data/tombstones/tombstone_00:backtrace 第 00 帧。

## 修复
- vendor/hwcomposer/hwc.cpp:42 加 nullptr check
- config reload 加 mutex

## 预防
- 所有 native 函数加 nullptr check
- config reload 加 verbose log
```

---

## 3. 案例 3：OOM 现场（5 分钟）

### 3.1 场景

App 后台被 OOM 杀，但 LMKD 没记录为何杀。

### 3.2 完整 5 步取证

**Step 1：抓现场**

```bash
$ adb bugreport /tmp/oom_bugreport.zip
$ unzip oom_bugreport.zip -d /tmp/br
```

**Step 2：5 个关键 grep**

```bash
# 1. 看 PSI 早期信号
$ cat /tmp/br/proc/pressure/memory
some avg10=42.31 avg60=38.92 avg300=22.15 total=...
full avg10=15.23 avg60=10.45 avg300=5.12 total=...
# some avg10 > 20% → 内存压力高
# full avg10 > 0 → 有任务饿死

# 2. 看 MemAvailable
$ grep "MemAvailable" /tmp/br/proc/meminfo
MemAvailable:    123456 kB  # < 200MB → 风险

# 3. 找大进程（PSS 排序）
$ grep -A 5 "Pss Total" /tmp/br/dumpsys/dumpsys_meminfo.txt | head
# 找到 PSS 最大的 5 个进程

# 4. 看 native heap
$ grep -A 2 "Native Heap" /tmp/br/dumpsys/dumpsys_meminfo.txt
# Native Heap 占用情况

# 5. 看 kernel slab（内核泄漏）
$ head -10 /tmp/br/proc/slabinfo
# 找异常大的 slab（dentry / inode 泄漏）
```

**Step 3：5 分钟定位**

```
根因：MemAvailable < 200MB，PSI some avg10 > 40%，
     最大 PSS 进程是 com.example.app（1.2GB），
     Native Heap 600MB（Bitmap 缓存），
     触发 LMKD 杀进程
```

**Step 4：fix 方向**

1. **短期**：app 减少 Bitmap 缓存（LruCache size 200MB）
2. **中期**：Bitmap 用 RGB_565 代替 ARGB_8888（节省 50% 内存）
3. **长期**：监控 Native Heap，超过 500MB 报警

**Step 5：报告模板**

```markdown
# OOM 案例 - com.example.app

## 现场
- 时间：2026-07-27 16:30
- 设备：Pixel 8 (Android 17, 8GB RAM)
- 触发：LMKD 杀进程
- 现场：bugreport.oom_2026-07-27_16-30.zip (200MB)

## 根因
com.example.app Native Heap 占用 600MB（Bitmap 缓存），
MemAvailable < 200MB，PSI some avg10 > 40%，
触发 LMKD 杀进程。

## 修复
- app LruCache size 减半
- Bitmap 改 RGB_565

## 预防
- Native Heap > 500MB 报警
- Bitmap 缓存强制 size 上限
```

---

## 4. 案例 4：KE 现场（5 分钟）

### 4.1 场景

设备突然重启，怀疑 kernel panic。

### 4.2 完整 5 步取证

**Step 1：抓现场**

```bash
$ adb bugreport /tmp/ke_bugreport.zip
$ unzip ke_bugreport.zip -d /tmp/br
```

**Step 2：5 个关键 grep**

```bash
# 1. 看 dmesg 找 panic
$ grep -E "panic|oops|BUG" /tmp/br/kernel/dmesg.txt | head
[12345.678] Kernel panic - not syncing: ...

# 2. 看 last_kmsg（这是上次 boot 的 log）
$ head -100 /tmp/br/kernel/last_kmsg.txt
[    0.000000] Linux version 6.18.0
[  123.456] Unable to handle kernel NULL pointer dereference at 0000000000000000
[  123.457] PGD 0 P4D 0
[  123.458] Oops: 0010 [#1] SMP NOPTI
[  123.459] CPU: 0 PID: 1234 Comm: kworker/0:1
[  123.460] Hardware name: ...
[  123.461] RIP: 0010:vendor_driver_func+0x12/0x80
[  123.462] Call Trace:
[  123.463]  ? __schedule+0x10/0x20
[  123.464]  schedule+0x1f/0x40
[  123.465]  process_one_work+0x123/0x280
[  123.466]  worker_thread+0x45/0x3c0

# 3. 看 pmsg-ramoops
$ cat /tmp/br/FS/data/vendor/ramoops/pmsg-ramoops-0 | tail -50
# 看 panic 前 printk 输出

# 4. 看 tainted（kernel 警告位）
$ cat /tmp/br/proc/sys/kernel/tainted
# 数字 > 0 → KE 现场

# 5. 用 kallsyms 反查 RIP 地址
$ grep "vendor_driver_func" /tmp/br/kernel/kallsyms | head
# 找到 vendor_driver_func 的具体实现位置
```

**Step 3：5 分钟定位**

```
根因：vendor_driver_func（vendor 驱动）kworker 线程
     访问 NULL 指针（fault addr 0x0），
     内核 Oops → panic → 重启。
     RIP 寄存器指向 vendor_driver_func+0x12。
```

**Step 4：fix 方向**

1. **短期**：vendor 驱动加 NULL check
2. **中期**：找 vendor 拿到 fault addr 的具体变量
3. **长期**：vendor 驱动加 stress test

**Step 5：报告模板**

```markdown
# KE 案例 - vendor_driver

## 现场
- 时间：2026-07-27 18:30
- 设备：Pixel 8 (Android 17)
- 触发：kworker 线程
- 现场：bugreport.ke_2026-07-27_18-30.zip (220MB)

## 根因
vendor_driver_func (kworker/0:1) 访问 NULL 指针，
RIP = vendor_driver_func+0x12，Oops → panic → 重启。

## 修复
- vendor_driver_func 加 NULL check
- 找 vendor 拿 RIP 处的反汇编

## 预防
- vendor 驱动加 stress test
- 加 tainted 监控
```

---

## 5. 案例 5：bootloop 现场（5 分钟）

### 5.1 场景

设备开机卡第一屏 logo，重启循环。

### 5.2 完整 5 步取证

**Step 1：抓现场**

```bash
$ adb bugreport /tmp/bootloop_bugreport.zip
# 注意：可能需要 fastboot mode 才能抓
$ unzip bootloop_bugreport.zip -d /tmp/br
```

**Step 2：5 个关键 grep**

```bash
# 1. 看 last_kmsg（上次 boot 的 kernel log）
$ head -100 /tmp/br/kernel/last_kmsg.txt
# 找 panic 或 restart 触发点

# 2. 看 init 启动 log（system buffer）
$ grep "init:" /tmp/br/logcat/logcat_system.txt | head -50
[    5.123] init: Loading SELinux policy
[    5.234] init: setcon u:r:init:s0 failed: Invalid argument
[    5.345] init: Cannot set SELinux context to init
[    5.456] init: Rebooting system

# 3. 看 SELinux denied
$ grep "avc: denied" /tmp/br/logcat/logcat_kernel.txt | head -20
# 大量 denied → SELinux 问题

# 4. 看 service 重启
$ grep "restarted" /tmp/br/logcat/logcat_system.txt | head
# vendor.foo restarted 5 times in 5s

# 5. 看 selinux mode
$ cat /tmp/br/proc/cmdline | tr '\0' '\n' | grep selinux
androidboot.selinux=permissive
# 注意：这里已经是 permissive，说明 vendor 加过
```

**Step 3：5 分钟定位**

```
根因：init 启动期 setcon 失败（SELinux 上下文错），
     触发 init 重启循环。
     cmdline 显示 selinux=permissive，
     说明 vendor 用 permissive 临时绕过但没修根因。
```

**Step 4：fix 方向**

1. **短期**：revert vendor 改的 .te（找回 git history）
2. **中期**：`m selinux_policy` 看具体 neverallow violation
3. **长期**：改完 .te 后，**必须重烧 boot.img**，不能只靠 selinux=permissive

**Step 5：报告模板**

```markdown
# bootloop 案例 - init 启动

## 现场
- 时间：2026-07-27 20:30
- 设备：Pixel 8 (Android 17)
- 触发：烧录新 boot.img
- 现场：bugreport.bootloop_2026-07-27_20-30.zip (150MB)

## 根因
vendor.foo .te 文件改坏 init 域，
init 启动 setcon 失败，触发 init 重启循环。
临时用 selinux=permissive 绕过但根因没修。

## 修复
- revert vendor.foo.te
- 重新 m selinux_policy
- 重烧 boot.img（必须）

## 预防
- 加 lint 检查 .te
- 禁止用 selinux=permissive 上线
```

---

## 6. 5 案例交叉总结：通用取证清单

### 6.1 通用取证 5 步法

```
[1] 抓现场
    - adb bugreport /tmp/case.zip
    - 30-60 秒后拿到

[2] 5 个 grep 命令
    - 触发证据（logcat / traces / tombstone）
    - 详细栈（traces.txt / tombstone）
    - 持锁 / 关联线程
    - 进程 / service 状态
    - 错误数据（PSI / MemAvailable / selinux mode）

[3] 5 分钟定位
    - 触发点 + 阻塞点 + 根因

[4] fix 方向
    - 短期：hotfix 立即缓解
    - 中期：加超时 / 监控
    - 长期：重构 / 加 lint

[5] 报告 + 提交
    - 5 行报告：现场 / 根因 / 修复 / 预防 / 复盘
    - git commit 修复
    - 加监控 / 门禁
```

### 6.2 5 案例速查表

| 案例 | 现场类型 | 第 1 文件 | 第 2 文件 | 第 3 文件 | fix 方向 |
|:-----|:---------|:---------|:---------|:---------|:--------|
| 1 ANR | 主线程卡死 | traces.txt | logcat_system | activity dumpsys | 异步 + 超时 |
| 2 NE | tombstone | tombstone_00 | logcat_crash | dropbox | nullptr check |
| 3 OOM | LMKD 杀进程 | meminfo | PSI | meminfo dumpsys | 减小缓存 |
| 4 KE | 内核 panic | last_kmsg | dmesg | ramoops | NULL check |
| 5 bootloop | init 重启 | last_kmsg | logcat_system | SELinux denied | revert .te |

### 6.3 oncall 通用清单

```markdown
# oncall 现场取证清单

## 抓现场（30-60 秒）
[ ] adb bugreport /tmp/<date>_<symptom>.zip
[ ] unzip <zip> -d /tmp/br
[ ] 看 version.txt 确认时间
[ ] 看 proc/cmdline 确认 selinux mode

## 定位（5-10 分钟）
[ ] grep 触发证据（症状关键词）
[ ] grep 主现场（traces / tombstone / dmesg / meminfo）
[ ] grep 关联数据（持锁 / 进程状态 / PSI）
[ ] grep 历史（dropbox / 之前的 bugreport）

## 出报告（5 分钟）
[ ] 5 行：现场 / 根因 / 修复 / 预防 / 复盘
[ ] 保存 bugreport 原始 zip
[ ] git commit 修复
[ ] 加监控 / 门禁 / 测试
```

### 6.4 oncall 5 大反模式

```
❌ 1. 不抓现场只看 logcat（80% 案例无法定位）
❌ 2. 抓现场后不 unzip（zip 里没直接看）
❌ 3. 只看一个文件（要交叉看 logcat + dumpsys + proc）
❌ 4. 不保存原始 zip（再要就丢了）
❌ 5. 出报告太慢（5 分钟出初版比 1 小时出完整更重要）
```

---

## 7. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 Bugreport 总览](01-Bugreport-总览与生成解析.md) | 工具 |
| [02 目录结构全梳理](02-Bugreport-目录结构全梳理.md) | 结构 |
| [03 关键文件速查](03-Bugreport-关键文件速查.md) | 30 命令 |
| [05 vs perfetto](05-Bugreport-vs-perfetto-trace.md) | 工具边界 |
| [04-Tool/Dumpsys/12-dumpsys实战SOP](../../../../05-卷5-调查方法论与工具链/33-Dumpsys · Bugreport · DropBox/12-dumpsys实战SOP.md) | dumpsys 实战 |
| [06-Foundation/SELinux/07-实战：定制SELinux策略排错5例](../../../01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/SELinux/07-实战：定制SELinux策略排错5例.md) | SELinux 实战 |
| [04-Tool/Perfetto/01-Perfetto系统总览与架构设计](../../../../05-卷5-调查方法论与工具链/31-Perfetto 全栈使用/01-Perfetto系统总览与架构设计.md) | perfetto |
| [06-Case/Cases-Extended/](../../../06-Case/Cases-Extended/) | 完整案例 |
| [02-Symptom/S00-S09 7 大症状](../../02-Symptom/) | 7 大症状 |
| [03-Forensics/F00-F07 7 大取证](../../03-Forensics/) | 取证总览 |

---

## 8. 下一篇预告 + 自检

### 8.1 下一篇

[05 Bugreport vs perfetto trace](05-Bugreport-vs-perfetto-trace.md) 讲清：
- bugreport vs perfetto 各自定位
- 5 类事故下"用 bugreport / perfetto / 都要用"
- 工具边界速查
- 何时用哪个的 5 条铁律

### 8.2 看完本文的自检

- [ ] 能用 5 步法处理 5 类现场
- [ ] 能用 §6 通用取证清单
- [ ] 能用 §6.2 速查表秒级定位
- [ ] 能用 §6.3 oncall 清单避免漏步
- [ ] 知道 §6.4 5 大反模式

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
