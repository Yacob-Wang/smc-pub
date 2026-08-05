# 06-Foundation/SELinux · 06 · 常见稳定性问题：service crash / neverallow / build 失败

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 厂商适配
>
> **强依赖**：[04 AVC 与 avc_denied](04-AVC与avc_denied：从一次denied反推策略.md) · [05 init 与 SELinux](05-init进程与SELinux：分阶段加载.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 SELinux 引起的 7 大症状的触点、service crash 的 4 类根因、neverallow violation 的 5 种错误信息、build 期的 5 个失败模式全部串成"症状 → 排查路径"速查
- **不是**：不复述 [01 §5 7 大症状对应](01-SELinux总览：MAC机制在Android的落地.md)；不复述 [05 §4 main-init 启动 logcat](05-init进程与SELinux：分阶段加载.md)
- **承接自**：[05 §7 androidboot.selinux 误用](05-init进程与SELinux：分阶段加载.md)（bootloop 案例）
- **衔接去**：[07 实战 5 例](07-实战：定制SELinux策略排错5例.md) / [08 AOSP 17 演进](08-AOSP-17演进：Treble+CIL+userspace加载.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章 7 大症状按 oncall 出现频率排序（SWT > ANR > NE > OOM > KE > JE > REBOOT）| 不按字母排，按"你今晚要处理的可能"排 |
| 2 | 第 5 章给 30+ 个症状映射一张速查表 | oncall 工程师 5 分钟决策工具 |
| 3 | 第 2 章"4 类根因"是 service crash 的统一模型 | vendor 90% 的"service 不起来"在这 4 类里 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**线上 80% 的"service crash / bootloop / 启动失败"在 SELinux 这一层都有迹可循——本文给"症状 → 排查路径"的速查表，让 5 分钟内定位到 SELinux 是不是根因。**

不是所有"service crash"都是 SELinux 引起的——但所有"service crash"**首先**要排除 SELinux 影响，再去查代码层。

---

## 1. 7 大症状的 SELinux 触点（按 oncall 频率排）

### 1.1 SWT（System Watchdog Timeout，5 大症状之首）

**触点**：init 启动的 service 起不来 → 触发 watchdog → 看门狗超时杀进程。

**真实 logcat**：

```
[  10.234] init: Starting service 'vendor.foo'...
[  10.345] init: Service 'vendor.foo' (pid 1234) exited with status 1
[  10.456] init:     type=1400 audit(1234.5:6): avc: denied { transition } 
              for comm="init" path="/system/bin/vendor.foo" 
              scontext=u:r:init:s0 tcontext=u:r:vendor_foo:s0 tclass=process
[  10.567] init: Service 'vendor.foo' will be restarted in 1s
[  10.678] init: Service 'vendor.foo' (pid 1235) exited with status 1
... (循环)
[  20.000] init: Service 'vendor.foo' has been restarted 5 times in 10s
[  20.001] init: Service 'vendor.foo' (pid 1240) killed by signal 9
[  25.000] init: Service 'vendor.foo' failed to start, blocking forever
```

**根因（90% 概率）**：`type_transition` 缺失 + vendor 漏写 .te

**修复**：

```te
# device/<vendor>/<device>/sepolicy/vendor_foo.te
type vendor_foo, domain;
type vendor_foo_exec, exec_type, vendor_file_type, file_type;
type_transition init vendor_foo_exec:process vendor_foo;
allow init vendor_foo:process transition;
allow init vendor_foo_exec:file { read execute open };
allow vendor_foo self:capability { sys_nice };
```

**修复后必须**：
- `m selinux_policy`
- 重烧 boot.img + vendor.img
- 不刷只重启无效

### 1.2 ANR（Application Not Responding，5 大症状之二）

**触点**：service 起不来阻塞主线程 → ANR 倒计时 5 秒触发。

**真实 logcat**：

```
[  30.123] system_server: ANR in com.example.app (input dispatching timed out)
[  30.234] ActivityManager: ANR in com.example.app, Reason: Input dispatching timed out
[  30.345] am_anr: pid 5678, com.example.app, ANR for 5003ms
[  30.456] type=1400 audit(0.0:0): avc: denied { read } for ...
```

**根因**：app 启动期等待 service_manager.addService() 阻塞，但 addService 因 SELinux denied 阻塞。

**修复**：先看 service 启动期的 SELinux denied，service 起来后 ANR 自然消失。

### 1.3 NE（Native Crash，5 大症状之三）

**触点**：native 进程 denied 后 crash（如 surfaceflinger 写文件被拒）。

**真实 logcat + tombstone**：

```
# logcat
[  40.123] type=1400 audit(0.0:0): avc: denied { write } for 
            comm="surfaceflinger" name="hwc.cfg" 
            scontext=u:r:surfaceflinger:s0 
            tcontext=u:object_r:vendor_file:s0 tclass=file
[  40.234] surfaceflinger: surface flinger died, signal 11 (SIGSEGV)

# tombstone (从 /data/tombstones/tombstone_01 拉)
backtrace:
  #00 pc 0x0000abcd in vendor::hwc::Config::Write() at hwc.cpp:42
  #01 pc 0x00001234 in main at main.cpp:18
signal: 11 (SIGSEGV)
cause: null pointer dereference
```

**根因**：surfaceflinger 写 hwc.cfg 时 SELinux denied → 函数返回 nullptr → 下次访问 nullptr → SIGSEGV。

**修复**：加 allow 规则 OR 把 hwc.cfg 改成正确的 file label。

### 1.4 OOM（Out of Memory）

**触点**：denied 风暴刷屏 logcat → logcat 满了 → 真正 OOM 信号被淹没。

**真实现象**：

```bash
# logcat 容量检查
$ adb shell logcat -g -b all
main: ring buffer is 4.0MB (1 used of 4MB)  # 异常：1MB used 意味着被刷爆过
system: ring buffer is 256KB (256 used of 256KB)  # 满了
```

**根因**：服务起不来 → 启动期 1000+ denied/秒 → logcat 满。

**修复**：先用 `setenforce 0` 临时绕过 → 修 .te → 重新刷。

### 1.5 KE（Kernel Exception）

**触点**：极少——SELinux 内核模块自身 bug。

**真实现象**：

```bash
# dmesg
[   5.123] BUG: unable to handle kernel NULL pointer dereference at 0000000000000000
[   5.234] PGD 0 P4D 0
[   5.345] Oops: 0010 [#1] SMP NOPTI
[   5.456] CPU: 0 PID: 1234 Comm: init Tainted: G W
[   5.567] Hardware name: ...
[   5.678] RIP: 0010:selinux_inode_permission+0x12/0x80
```

**根因**：SELinux 内核模块 bug（极罕见，AOSP 17 修复了大量）；或 vendor 改 kernel 改坏。

**修复**：抓 ramoops + 提 vendor 改 kernel。

### 1.6 JE（Java Exception）

**触点**：间接——SELinux 不直接导致 JE，但 neverallow violation 会被 audit 误报。

**真实现象**：

```bash
# audit.log 大量 neverallow 警告
# 误以为是 Java 异常，实则 SELinux
```

**根因**：从不直接，JE 总有 Java 根因，SELinux 引起"看起来像 JE"通常都是 NE。

### 1.7 REBOOT（重启）

**触点**：init 自身策略错误 → kernel panic 或 init restart 循环。

**真实 logcat**：

```
# init 持续重启
[   0.123] init: Loading SELinux policy
[   0.234] init: setcon u:r:init:s0 failed: Invalid argument
[   0.345] init: Cannot set SELinux context to init
[   0.456] init: Rebooting system
```

**修复**：见 [05 §7.3 bootloop 案例](05-init进程与SELinux：分阶段加载.md)。

---

## 2. service crash 与 SELinux 的 4 类根因

### 2.1 4 类根因总览

```
service crash 根因
├── 1. type 未定义（30%）        ← .te 漏写
├── 2. type_transition 缺失（40%） ← 启动 transition 没允许
├── 3. 资源访问 denied（25%）     ← .te allow 漏写
└── 4. file_contexts 漏写（5%）    ← .fc 漏写
```

### 2.2 根因 1：type 未定义（30%）

**症状**：service 启动后立刻 `setcon failed: Invalid argument` 或 `avc: denied { set }`。

**真实 logcat**：

```
[   5.123] init: Starting service 'myapp_daemon'...
[   5.234] type=1400 audit(0.0:0): avc: denied { set } for 
            comm="init" scontext=u:r:init:s0 
            tcontext=u:r:myapp_daemon:s0 tclass=process
[   5.345] init: Service 'myapp_daemon' (pid 1234) exited with status 1
```

**根因**：`myapp_daemon` 这个 type 在 policy 中根本不存在 → setcon 失败。

**诊断命令**：

```bash
# 1. 检查 type 是否定义
$ sepolicy-analyze precompiled_sepolicy types | grep myapp_daemon
# 期望：myapp_daemon
# 实际：（无输出）→ type 未定义

# 2. 检查 .te 文件
$ find device/<vendor>/ -name "myapp_daemon.te"
# 期望：device/<vendor>/<device>/sepolicy/myapp_daemon.te
# 实际：不存在 → 漏写
```

**修复**：

```te
# device/<vendor>/<device>/sepolicy/myapp_daemon.te
type myapp_daemon, domain;
type myapp_daemon_exec, exec_type, vendor_file_type, file_type;
```

### 2.3 根因 2：type_transition 缺失（40%）

**症状**：type 已定义，但 init 仍 denied transition。

**诊断命令**：

```bash
# 检查 type_transition 规则
$ sepolicy-analyze precompiled_sepolicy transition -s init -t myapp_daemon_exec
# 期望：init → myapp_daemon
# 实际：（无输出）→ 缺失
```

**修复**：

```te
type_transition init myapp_daemon_exec:process myapp_daemon;
allow init myapp_daemon:process transition;
allow init myapp_daemon_exec:file { read execute open };
```

### 2.4 根因 3：资源访问 denied（25%）

**症状**：service 起来后一段时间 crash。

**修复**：按 [04 §3 反推 5 步法](04-AVC与avc_denied：从一次denied反推策略.md) 加 allow。

### 2.5 根因 4：file_contexts 漏写（5%）

**症状**：logcat 出现 `tcontext=unlabeled`。

**修复**：见 [04 §6.5 unlabeled 案例](04-AVC与avc_denied：从一次denied反推策略.md)。

---

## 3. neverallow violation 的 5 种典型错误

### 3.1 5 种错误信息

```bash
# 错误 1：sys_admin 自给
neverallow check failed
  for scontext=u:r:vendor_foo:s0
  tcontext=u:r:vendor_foo:s0
  tclass=capability
  permission: sys_admin
# 原因：除 init/kernel/recovery 外禁止自给 sys_admin

# 错误 2：跨域 transition
neverallow check failed
  for scontext=u:r:vendor_foo:s0
  tcontext=u:r:init:s0
  tclass=process
  permission: transition
# 原因：vendor 不能 transition 到 platform 域

# 错误 3：私域访问
neverallow check failed
  for scontext=u:r:vendor_foo:s0
  tcontext=u:r:priv_app:s0
  tclass=binder
  permission: call
# 原因：vendor 不能调用 private 域 service

# 错误 4：访问 kernel parameters
neverallow check failed
  for scontext=u:r:vendor_foo:s0
  tcontext=u:object_r:kernel:s0
  tclass=security
  permission: load_policy
# 原因：vendor 不能 load_policy

# 5 错误：写 system 分区
neverallow check failed
  for scontext=u:r:vendor_foo:s0
  tcontext=u:object_r:system_file:s0
  tclass=file
  permission: write
# 原因：vendor 不可写 system 分区
```

### 3.2 修法 4 种（按推荐顺序）

| 修法 | 用法 | 风险 |
|:-----|:-----|:-----|
| **1. attribute 排除** | `typeattribute vendor_foo mlstrustedsubject;` | 低 |
| **2. 改用别的方式** | 换 capability / 换域 | 中 |
| **3. 改 neverallow** | 直接注释 / 删除 | **高**（CTS 拒） |
| **4. 加 platform 合入** | 让 Google 改 platform 策略 | 时间长 |

**反模式**：**永远不要注释 neverallow**。CTS 必拒。

---

## 4. build 期 5 个失败模式

### 4.1 失败 1：type 重复定义

```
libsepol.report_failure: neverallow check failed
libsepol.report_failure: conflicting definitions:
  type vendor_foo defined in /.../platform/vendor_foo.te:10
  type vendor_foo defined in /.../device/vendor_foo.te:8
```

**根因**：type 在 platform 和 device 两侧都定义。**修法**：删 device 侧的定义。

### 4.2 失败 2：typeattribute 冲突

```
libsepol.report_failure: typeattribute mlstrustedsubject:
  conflicting attribute sets for type vendor_foo
  in /.../platform/vendor_foo.te:12
  in /.../device/vendor_foo.te:15
```

**根因**：vendor_foo 在两侧都属于不同 attribute 集。**修法**：用 `typeattribute` 显式指定。

### 4.3 失败 3：neverallow 违反

（见 §3）

### 4.4 失败 4：file_contexts 路径无效

```
checkfc: invalid regex at /.../file_contexts:42
        pattern: /system/[**/]foo
```

**根因**：file_contexts PCRE 语法错。**修法**：用 `checkfc -p` 验证。

### 4.5 失败 5：sepolicy 编译 OOM

```
out/host/linux-x86/bin/checkpolicy: out of memory
```

**根因**：策略文件太大（>50MB）。**修法**：
- 删除未使用的 .te
- 减少 macro 展开
- 升级编译机器

### 4.6 自动化检查脚本

```bash
#!/bin/bash
# selinux_build_check.sh
# 用法：在 m selinux_policy 前跑

set -e

# 1. file_contexts 语法检查
echo "[1/3] checkfc ..."
checkfc -p /system system/sepolicy/public/file_contexts

# 2. sepolicy-analyze 验证 binary policy
echo "[2/3] sepolicy-analyze ..."
POLICY=out/target/product/cf_x86_64_phone/vendor/etc/selinux/precompiled_sepolicy
if [ -f "$POLICY" ]; then
  sepolicy-analyze $POLICY types | wc -l  # 至少 200 个 type
fi

# 3. neverallow 路径检查
echo "[3/3] audit2why ..."
adb shell dmesg | grep "avc: denied" | audit2why 2>&1 | head -20
```

---

## 5. 速查表：症状 → 排查路径（30+ 映射）

| 症状 | 第一检查 | 第二检查 | 第三检查 |
|:-----|:--------|:--------|:--------|
| **bootloop** | logcat `setcon failed` | `cat /proc/cmdline \| grep selinux` | BoardConfig.mk `androidboot.selinux=` |
| **service 一直重启** | logcat `transition denied` | `sepolicy-analyze transition` | device sepolicy .te 文件 |
| **service 启动后 crash** | logcat `denied { ... } for comm=<svc>` | `audit2allow -a` | 检查 file_contexts |
| **ANR** | logcat denied 在 ANR 前 5 秒 | 找 service 启动期 denied | 检查 service_manager 调用 |
| **NE** | tombstone + 紧前 logcat denied | 看进程 context 是否正确 | 检查 .te allow 完整 |
| **OEM_Hook 引起 denied** | `audit2allow -a` 输出 | 用 attribute 收敛 | 与 hook 文档交叉验证 |
| **property set 失败** | logcat `denied { set } for name=` | property_contexts 查 type | 改用正确 type 的 property |
| **service addService 失败** | logcat `denied { add }` | service_contexts 查 type | 检查 public 暴露 |
| **写文件被拒** | logcat `denied { write }` | ls -Z 看文件 type | 检查 file_contexts |
| **driver ioctl 被拒** | logcat `denied { ioctl }` | chr_file class 查 type | 检查 .te 的 chr_file allow |
| **sepolicy 编译失败** | `m selinux_policy` 看 ERROR 行 | `checkpolicy` 详细输出 | 比对 .te 行号 |
| **CTS 失败 SELinux 测试** | cts-tradefed 查 fail 测试 | `cts/tests/security/selinux` | 看 platform public 暴露 |
| **VTS 失败** | vts-tradefed 查 fail | `vts/testcases/security/selinux` | 跑 `vts_kernel_selinux_test` |
| **neverallow violation** | `m selinux_policy` 看 ERROR | 用 attribute 排除 | 改用别的方式实现 |
| **unlabeled 资源** | `ls -Z` 看 tcontext=unlabeled | `restorecon` 跑 | 改 file_contexts |
| **/system 不可写** | logcat `denied { write }` tclass=file tcontext=system_file | 检查 vendor 策略 | vendor 不应写 system |
| **/vendor 不可写** | logcat `denied { write }` tcontext=vendor_file | platform 也不应写 vendor | 检查 type allow 方向 |
| **systrace 抓不到** | cmdtrace 是否 denied | perfetto 数据目录权限 | 检查 trace_data_file type |
| **dropbox 不能写** | logcat `denied { write }` tcontext=dropbox_data_file | dropbox 域 allow | 检查 dropbox.te |
| **binder 调用被拒** | logcat `denied { call }` tclass=binder | service type 是否在 policy | 检查 service 域 allow |

### 5.1 oncall 5 分钟决策树

```
[问题] service 起不来 / crash
  ↓
[1] logcat 找 "avc: denied" 行（5 秒）
  ├─ 有 → [2]
  └─ 无 → 不是 SELinux，去查代码层
  ↓
[2] 看 { permission } + tclass（5 秒）
  ├─ { transition } → §2.3 根因 2
  ├─ { write/read/open } tclass=file → §2.4 根因 3
  └─ { set } tclass=process → §2.2 根因 1
  ↓
[3] 看 scontext / tcontext（5 秒）
  ├─ tcontext=unlabeled → §2.5 根因 4
  ├─ type 在 device 侧定义 → 走 vendor 适配流程
  └─ type 在 platform 侧 → 走 platform 合入
  ↓
[4] 按根因加 .te + 重新 m + 重刷 boot.img（5-10 分钟）
  ↓
[5] 验证：sepolicy-analyze 确认新规则存在（5 秒）
```

**总耗时**：5 + 10 = **15 分钟**（含重刷时间）。

---

## 6. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 §5 7 大症状对应](01-SELinux总览：MAC机制在Android的落地.md) | 详细展开 |
| [04 AVC 与 avc_denied](04-AVC与avc_denied：从一次denied反推策略.md) | §3 反推 5 步法 + 本文 §2 4 类根因 |
| [05 init 与 SELinux](05-init进程与SELinux：分阶段加载.md) | §7 bootloop 案例 + 本文 §1.1 SWT |
| [07 实战 5 例](07-实战：定制SELinux策略排错5例.md) | 下篇用 5 个真实案例展示 |
| [02-Symptom/S01-ANR](../../../../02-Symptom/S01-ANR/) | ANR 视角的 SELinux 触点 |
| [02-Symptom/S04-SWT](../../../../02-Symptom/S04-SWT/) | SWT 视角 |
| [04-Tool/Watchdog/02-多层Watchdog架构](../../../../04-卷4-诊断方法论与稳定性症状/27-系统无响应（SWT · Watchdog）/02-多层Watchdog架构.md) | watchdog 杀进程链路 |
| [03-Forensics/F04-NE](../../../../../04-卷4-诊断方法论与稳定性症状/25-Native 异常/01-取证机制.md) | NE 取证视角 |
| [05-Governance/Security](../../../05-Governance/Security/) | SELinux 治理 SOP（**待补**）|

---

## 7. 下一篇预告 + 自检

### 7.1 下一篇

[07 实战：定制 SELinux 策略排错 5 例](07-实战：定制SELinux策略排错5例.md) 讲 5 个真实场景的完整排错流程：
1. vendor 加新 daemon 起不来
2. init 启动期 bootloop
3. app 跨 app binder 调用 denied
4. property 写入 denied
5. file_contexts 漏写导致 service 静默死

### 7.2 看完本文的自检

- [ ] 能从"service crash"反推是 4 类根因中的哪一类
- [ ] 能识别 neverallow violation 的 5 种错误信息
- [ ] 知道 build 期 5 个失败模式 + 修法
- [ ] 能在 5 分钟内用"症状 → 排查路径"速查表定位
- [ ] 知道 vendor 加 service 的 5 步完整流程（.te + .fc + service_contexts + 编译 + 烧录）

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
