# 06-Foundation/SELinux · 07 · 实战：定制 SELinux 策略排错 5 例

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · 厂商适配 · oncall 工程师
>
> **强依赖**：[04 AVC 与 avc_denied](04-AVC与avc_denied：从一次denied反推策略.md) · [05 init 与 SELinux](05-init进程与SELinux：分阶段加载.md) · [06 常见稳定性问题](06-常见稳定性问题：service-crash.neverallow.build-失败.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：用 5 个**真实可重现**的 SELinux 排错案例，把"症状 → logcat → 根因 → 修复"全流程跑一遍，让架构师 5 分钟学会、5 分钟复用
- **不是**：不复述 [06 §5 速查表](06-常见稳定性问题：service-crash.neverallow.build-失败.md)；不复述 [04 §6 5 个案例](04-AVC与avc_denied：从一次denied反推策略.md)（本文是它的"完整排错版"）
- **承接自**：[06 §2 service crash 4 类根因](06-常见稳定性问题：service-crash.neverallow.build-失败.md)（5 个案例是 4 类根因的真实落地）
- **衔接去**：[08 AOSP 17 演进](08-AOSP-17演进：Treble+CIL+userspace加载.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 5 案例覆盖 §2 的 4 类根因（多 1 个）| 4 类根因全可重现 + 1 个综合 case |
| 2 | 每案例用"时间戳 logcat"模拟真实现场 | 截图级时间戳便于在 bug report 中匹配 |
| 3 | 第 6 章给"通用修复流程"6 步 | 5 案例抽公共步骤 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**5 个真实可重现的 SELinux 排错案例，分布在 vendor 适配 / 启动期 / app 通信 / property / file_contexts 5 个最常见触点。**

每个案例都按"症状 → logcat 关键行 → 反推 → 修复 → 验证"5 步走，耗时控制在 5-15 分钟。**学完本文 = 把 [01]-[06] 所有方法论过一遍实战**。

---

## 1. 案例 1：vendor 加新 daemon 起不来（典型 vendor 适配）

### 1.1 场景

vendor 在 `device/<vendor>/<device>/sepolicy/` 加了 `vendor.foo`，准备开机自启。但**漏写 .te 策略**。

### 1.2 完整时间线 logcat

```
[ 0.000000] Linux version 6.18.0-android17-xxx (builder@xxx)
[ 0.123456] SELinux:  Initializing.
[ 0.234567] SELinux:  policy loaded successfully
[ 1.345678] init: First stage mounted
[ 1.456789] init: Switching to second stage
[ 1.567890] init: Loading SELinux policy
[ 1.678901] init: setcon u:r:init:s0 succeeded
[ 2.000000] init: Processing /init.rc
[ 2.123456] init: Processing /init.<device>.rc
[ 2.234567] init: Starting service 'vendor.foo'...
[ 2.345678] type=1400 audit(0.5:7): avc: denied { transition } for
            comm="init" path="/system/bin/vendor.foo"
            scontext=u:r:init:s0
            tcontext=u:r:vendor_foo:s0 tclass=process
[ 2.456789] init: Service 'vendor.foo' (pid 1234) exited with status 1
[ 2.567890] init:     type=1400 audit(0.5:7): avc: denied { transition } ...
[ 2.678901] init: Service 'vendor.foo' will be restarted in 1s
[ 2.789012] init: Service 'vendor.foo' (pid 1235) exited with status 1
... (循环 5 次)
[ 8.000000] init: Service 'vendor.foo' has been restarted 5 times in 5s
[ 8.000001] init: Service 'vendor.foo' failed to start, blocking forever
[ 8.000002] init: Rebooting system  ← bootloop 触发
```

### 1.3 反推 3 步

**Step 1**：找 `avc: denied` 第一行（关键）
```
[ 2.345678] type=1400 audit(0.5:7): avc: denied { transition } ...
```
- `comm="init"` → 发起者 init
- `scontext=u:r:init:s0` → init 域
- `tcontext=u:r:vendor_foo:s0` → 想切到 vendor_foo 域
- `tclass=process` → process class
- `{ transition }` → 想 transition 到 vendor_fo

**Step 2**：检查 vendor_fo type 是否存在
```bash
# 烧录后的 binary policy
$ adb pull /vendor/etc/selinux/precompiled_sepolicy
$ sepolicy-analyze precompiled_sepolicy types | grep vendor_fo
# 期望：vendor_fo
# 实际：（无输出）→ type 未定义
```

**Step 3**：检查 .te 文件
```bash
$ find device/<vendor>/ -name "vendor_fo.te"
# 期望：device/<vendor>/<device>/sepolicy/vendor_fo.te
# 实际：不存在 → vendor 漏写
```

### 1.4 根因

**vendor 漏写 .te 文件**——4 类根因中的根因 1（type 未定义）。

### 1.5 修复（4 个文件 + 1 个命令）

**文件 1**：`device/<vendor>/<device>/sepolicy/vendor_fo.te`

```te
type vendor_fo, domain;
type vendor_fo_exec, exec_type, vendor_file_type, file_type;

# init 切到 vendor_fo 域
type_transition init vendor_fo_exec:process vendor_fo;
allow init vendor_fo:process transition;
allow init vendor_fo_exec:file { read execute open };

# vendor_fo 自身基础能力
allow vendor_fo self:capability { sys_nice dac_override };
allow vendor_fo self:process { setcurrent };
```

**文件 2**：`device/<vendor>/<device>/sepolicy/file_contexts`（追加）

```
/system/bin/vendor_fo     u:object_r:vendor_fo_exec:s0
```

**文件 3**：`device/<vendor>/<device>/<init>.<device>.rc`（追加）

```
service vendor_fo /system/bin/vendor_fo
    class core
    user root
    group root
    seclabel u:r:vendor_fo:s0   # 显式声明
```

**文件 4**：`device/<vendor>/<device>/BoardConfig.mk`（如果用了 selinux 编译选项）

```
# 让 device sepolicy 加入编译
BOARD_SEPOLICY_DIRS += device/<vendor>/<device>/sepolicy
```

**命令 1**：

```bash
$ m selinux_policy
# 检查输出：无 ERROR

# 重新烧录 boot.img + vendor.img
$ fastboot flash boot out/.../boot.img
$ fastboot flash vendor out/.../vendor.img
$ fastboot reboot
```

### 1.6 验证 5 步

```bash
# 1. 启动后看 service 是否成功
$ adb logcat -d | grep "vendor_fo"
# 期望：Service 'vendor_fo' (pid X) launched
# 不应再有 "exited with status 1"

# 2. 进程 context
$ adb shell ps -Z | grep vendor_fo
u:r:vendor_fo:s0        root  ...  /system/bin/vendor_fo

# 3. 进程可执行文件 context
$ adb shell ls -Z /system/bin/vendor_fo
u:object_r:vendor_fo_exec:s0  root  ...  /system/bin/vendor_fo

# 4. 找 denied 行（应该没有）
$ adb logcat -d | grep "avc: denied" | grep vendor_fo
# 期望：无输出

# 5. sepolicy-analyze 验证
$ sepolicy-analyze precompiled_sepolicy types | grep vendor_fo
vendor_fo
$ sepolicy-analyze precompiled_sepolicy transition -s init -t vendor_fo_exec
init → vendor_fo
```

**总耗时**：5 分钟（4 文件 + 1 命令 + 5 步验证）。

---

## 2. 案例 2：init 启动期 bootloop

### 2.1 场景

vendor 改 `init.te` 加了一条 `allow init self:capability sys_admin;`，触发 AOSP 17 强制 neverallow，编译过了但运行时 init 立刻 setcon 失败。

### 2.2 完整时间线 logcat

```
[ 0.123456] SELinux:  Initializing.
[ 0.234567] SELinux:  policy loaded successfully
[ 1.345678] init: First stage mounted
[ 1.456789] init: Switching to second stage
[ 1.567890] init: Loading SELinux policy
[ 1.678901] type=1400 audit(1.5:8): avc: denied { set } for
            comm="init" scontext=u:r:kernel:s0
            tcontext=u:r:init:s0 tclass=process
[ 1.789012] init: setcon u:r:init:s0 failed: Permission denied
[ 1.890123] init: Cannot set SELinux context to init
[ 2.000000] init: Rebooting system
... (循环 10 次)
[ 30.000000] init: panic: could not set SELinux context to init
[ 30.000001] Kernel panic - not syncing: Attempted to kill init!
```

### 2.3 反推 3 步

**Step 1**：找第一行 denied
```
type=1400 audit(1.5:8): avc: denied { set } for comm="init"
```
- `scontext=u:r:kernel:s0` → init 还在 kernel 域（**first stage 用 kernel 域**）
- `tcontext=u:r:init:s0` → 想切到 init 域
- `{ set }` → 想 set 自己的 process context

**Step 2**：检查 init 域是否在 policy
```bash
$ sepolicy-analyze precompiled_sepolicy types | grep -E "^init$"
init
```
（init 域存在）

**Step 3**：检查 init 域规则
```bash
$ sepolicy-analyze precompiled_sepolicy allow -s init | head
# 期望看到 init 的 allow 规则
# 实际：（setcon 需要的 set capability 缺失）
```

### 2.4 根因

**init 域的 capability 不全**——可能 vendor 改 init.te 时不小心删了某行。

### 2.5 修复 3 步

**Step 1**：用 BoardConfig.mk 临时进 permissive 进系统
```
BOARD_KERNEL_CMDLINE += androidboot.selinux=permissive
```

**Step 2**：进系统后查 init 域的 allow
```bash
$ adb shell su 0 setenforce 0  # 切 permissive（如果已经 permissive，跳过）
$ sepolicy-analyze /vendor/etc/selinux/precompiled_sepolicy allow -s init
```

**Step 3**：找到缺失的 allow，加回 init.te
```te
# system/sepolicy/public/init.te 补回缺失的 allow
# 例如：
allow init self:capability { sys_admin sys_boot sys_nice ... };
# 或
allow init kernel:process setcurrent;
```

**重新编译 + 烧录**（不要忘记去掉 cmdline 的 permissive）。

### 2.6 验证 4 步

```bash
# 1. 启动成功
$ adb logcat -d | grep "setcon u:r:init:s0 succeeded"

# 2. 没有 panic
$ adb logcat -d | grep "panic" | wc -l
# 期望：0

# 3. init 进程 context
$ adb shell ps -eZ | grep -E "init$"
u:r:init:s0  root  1  0  /init

# 4. cmdline 已清掉 permissive
$ adb shell cat /proc/cmdline | grep selinux
# 期望：androidboot.selinux=enforcing
# 实际（修复中可能）：androidboot.selinux=permissive
```

---

## 3. 案例 3：app 跨 app binder 调用 denied

### 3.1 场景

AOSP 自带 `MyService`（type=`my_service`）想被 `com.example.app`（type=`untrusted_app`）调用，但 vendor 漏给 app 域加 binder call 权限。

### 3.2 完整时间线 logcat

```
[10.000000] untrusted_app: ServiceConnection leaked
[10.123456] com.example.app: java.lang.SecurityException:
            Binder invocation to an incorrect interface
[10.234567] type=1400 audit(10.0:15): avc: denied { call } for
            comm="com.example.app"
            scontext=u:r:untrusted_app:s0:c123,c256
            tcontext=u:object_r:my_service:s0
            tclass=binder permissive=0
[10.345678] ActivityManager: Process com.example.app has died
[10.456789] WindowManager: Force removing ActivityRecord{...}
```

### 3.3 反推 3 步

**Step 1**：定位 denied 行
```
avc: denied { call } ... tcontext=u:object_r:my_service:s0 tclass=binder
```
- `tclass=binder` → binder 调用
- `{ call }` → 想 call
- `tcontext=my_service` → 目标 service

**Step 2**：检查 my_service type 和 service_contexts
```bash
# type 存在
$ sepolicy-analyze precompiled_sepolicy types | grep my_service
my_service

# service_contexts 暴露
$ adb shell cat /system/etc/selinux/plat_service_contexts | grep my_service
my_service u:object_r:my_service:s0
```

**Step 3**：检查 my_service 域的 allow
```bash
# 验证反向：untrusted_app 能不能 call my_service
$ sepolicy-analyze precompiled_sepolicy allow -s untrusted_app -t my_service -c binder
# 期望：allow untrusted_app my_service:binder { call transfer };
# 实际：（无输出）→ 缺失
```

### 3.4 根因

**untrusted_app 域的 binder call 权限缺失**。

### 3.5 修复 3 步

**文件 1**：`system/sepolicy/public/untrusted_app.te`（追加）

```te
# 让 untrusted_app 能 call my_service
allow untrusted_app my_service:binder { call transfer };
allow untrusted_app my_service_service:service_manager find;
```

**文件 2**：`system/sepolicy/public/service_contexts`（已存在）

```te
my_service u:object_r:my_service:s0
```

**文件 3**：`system/sepolicy/public/my_service.te`（追加）

```te
# 让 my_service 能接收 untrusted_app 的 call
allow my_service untrusted_app:binder { call transfer receive };
allow my_service untrusted_app:fd use;
```

**重新编译 + 烧录 system.img**。

### 3.6 验证 5 步

```bash
# 1. service_contexts 正确
$ adb shell cmd service_manager list | grep my_service
my_service    u:object_r:my_service:s0

# 2. 反向 allow 正确
$ sepolicy-analyze precompiled_sepolicy allow -s untrusted_app -t my_service -c binder
allow untrusted_app my_service:binder { call transfer }

# 3. 应用启动
$ adb shell am start -n com.example.app/.MainActivity
# 期望：成功，不 crash

# 4. 没有 denied
$ adb logcat -d | grep "avc: denied" | grep my_service
# 期望：无输出

# 5. service 调用成功
$ adb logcat -d | grep "MyService"
# 期望：MyService onBind called
```

---

## 4. 案例 4：property 写入 denied

### 4.1 场景

shell 想 `setprop ro.build.fingerprint`，但被 SELinux 拒绝。

### 4.2 完整时间线

```bash
$ adb shell setprop ro.build.fingerprint "test"
# 输出：（无，但 setprop 实际失败）

$ adb logcat -d | grep "avc: denied"
type=1400 audit(0.0:0): avc: denied { set } for
    name="ro.build.fingerprint"
    scontext=u:r:shell:s0
    tcontext=u:object_r:fingerprint_prop:s0
    tclass=property_service permissive=0
```

### 4.3 反推 3 步

**Step 1**：定位 denied
```
denied { set } ... tcontext=fingerprint_prop ... tclass=property_service
```

**Step 2**：检查 property_contexts
```bash
$ adb shell cat /system/etc/selinux/plat_property_contexts | grep fingerprint
ro.build.fingerprint u:object_r:fingerprint_prop:s0
```

**Step 3**：检查 shell 域的 allow
```bash
$ sepolicy-analyze precompiled_sepolicy allow -s shell -t fingerprint_prop -c property_service
# 期望：allow shell fingerprint_prop:property_service { set };
# 实际：（无输出）→ shell 没有 set 权限
```

### 4.4 根因

**shell 域的 fingerprint_prop set 权限缺失**。**这是 AOSP 17 默认设计**——shell 不该改 ro.build.fingerprint（防伪）。

### 4.5 修复方案

**方案 1（推荐）：换非 ro.* property**

```bash
$ adb shell setprop persist.test.fingerprint "x"
# persist.test.fingerprint 不在 property_contexts 中，走 default_prop
# default_prop:property_service set 是 shell 默认 allow
```

**方案 2（仅 debug 设备）：改 shell 域**

```te
# system/sepolicy/public/shell.te
allow shell fingerprint_prop:property_service set;
```

**方案 3（绝不推荐）：audit2allow 自动加**

```bash
# ❌ 会加未审计的 allow
$ audit2allow -a -i audit.log
```

### 4.6 验证 2 步

```bash
# 1. 持久 property 写入成功
$ adb shell setprop persist.test.fingerprint "x"
$ adb shell getprop persist.test.fingerprint
x

# 2. ro.* property 仍然不能改（AOSP 17 设计）
$ adb shell setprop ro.build.fingerprint "test"
# 失败 + denied 行（应该）
```

---

## 5. 案例 5：file_contexts 漏写导致 service 静默死

### 5.1 场景

vendor 加新 binary `vendor.bin`，但**忘了在 file_contexts 里打 label**。init 启动它时静默死，不报错。

### 5.2 完整时间线 logcat

```
[ 5.000000] init: Starting service 'vendor_service'...
[ 5.123456] init:     type=1400 audit(5.0:5): avc: denied { read } for
                comm="init" name="vendor.bin"
                scontext=u:r:init:s0
                tcontext=u:object_r:unlabeled:s0
                tclass=file permissive=0
[ 5.234567] init: Service 'vendor_service' (pid 1234) exited with status 1
... (循环 5 次)
[ 10.000000] init: Service 'vendor_service' has been restarted 5 times in 5s
[ 10.000001] init: Service 'vendor_service' failed to start
```

**特征**：denied 但**没有 transition denied**——这是文件 label 错（unlabeled）的标志。

### 5.3 反推 3 步

**Step 1**：定位 denied
```
denied { read } ... tcontext=u:object_r:unlabeled:s0 tclass=file
```

**Step 2**：检查文件实际 label
```bash
$ adb shell ls -Z /system/bin/vendor.bin
u:object_r:unlabeled:s0  root  ...  /system/bin/vendor.bin
# 关键：unlabeled
```

**Step 3**：检查 file_contexts 是否定义
```bash
$ adb shell cat /system/etc/selinux/plat_file_contexts | grep vendor.bin
# 期望：/system/bin/vendor.bin ... vendor_bin_exec:s0
# 实际：（无输出）→ 漏写
```

### 5.4 根因

**file_contexts 漏写**——4 类根因中的根因 4。

### 5.5 修复 3 步

**Step 1**：加 file_contexts
```te
# device/<vendor>/<device>/sepolicy/file_contexts
/system/bin/vendor\.bin   u:object_r:vendor_bin_exec:s0
```

**Step 2**：验证正则（**注意转义**）
```bash
$ checkfc -p /system device/<vendor>/<device>/sepolicy/file_contexts
# 期望：no error
```

**Step 3**：重新编译 + 烧录
```bash
$ m selinux_policy
$ fastboot flash system out/.../system.img
$ fastboot reboot
```

**不要用 restorecon 临时绕过**——只对运行时文件有效，**新加 binary 必须在 file_contexts 里**。

### 5.6 验证 4 步

```bash
# 1. 文件 label 正确
$ adb shell ls -Z /system/bin/vendor.bin
u:object_r:vendor_bin_exec:s0  root  ...  /system/bin/vendor.bin

# 2. service 起来
$ adb logcat -d | grep "vendor_service"
# 期望：Service 'vendor_service' (pid X) launched

# 3. 没有 denied
$ adb logcat -d | grep "avc: denied" | grep vendor.bin
# 期望：无输出

# 4. 进程 context
$ adb shell ps -Z | grep vendor_service
u:r:vendor_service:s0  root  ...  /system/bin/vendor.bin
```

---

## 6. 5 个案例的"通用修复流程"

### 6.1 6 步通用流程

```
[1] 抓现象（logcat / dmesg / ps -Z / ls -Z）
    ↓
[2] 定位 denied 行（grep "avc: denied"）
    ↓
[3] 拆解 8 字段（[04 §1.2](04-AVC与avc_denied：从一次denied反推策略.md)）
    ↓
[4] 反推类型（root cause 是 4 类中的哪一类）
    ↓
[5] 加 .te / .fc / service_contexts（4 文件之一）
    ↓
[6] m selinux_policy + 重烧 + 验证（5 步验证）
```

### 6.2 4 类根因的 5 分钟定位表

| 根因 | logcat 标志 | 第一检查 | 修法文件 |
|:-----|:----------|:---------|:--------|
| **1. type 未定义** | `setcon failed: Invalid argument` | `sepolicy-analyze types` | device sepolicy .te |
| **2. transition 缺失** | `avc: denied { transition }` | `sepolicy-analyze transition` | device sepolicy .te |
| **3. allow 漏写** | `avc: denied { read/write }` | `audit2allow -a` | 缺哪个 allow 加哪 |
| **4. file_contexts 漏** | `tcontext=unlabeled` | `ls -Z` 看实际 label | file_contexts |

### 6.3 4 类根因的"反模式"

| 反模式 | 后果 |
|:-------|:-----|
| `audit2allow -M` 自动写盘 | 生成的 allow 过宽 |
| 注释 neverallow | CTS 拒，永久 fail |
| 改用 `setenforce 0` 长期 | 失去强制保护，线上事故 |
| 只跑 restorecon 不改 file_contexts | OTA 后失效 |

---

## 7. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [04 §6 5 个案例](04-AVC与avc_denied：从一次denied反推策略.md) | 简短版案例 |
| [06 §2 4 类根因](06-常见稳定性问题：service-crash.neverallow.build-失败.md) | 4 类根因的诊断流程 |
| [06 §5 速查表](06-常见稳定性问题：service-crash.neverallow.build-失败.md) | 30 症状映射 |
| [08 AOSP 17 演进](08-AOSP-17演进：Treble+CIL+userspace加载.md) | 下篇讲 AOSP 17 的新变化 |
| [05-Governance/Security](../../../05-Governance/Security/) | SELinux 治理 SOP（**待补**）|
| [01-Mechanism/App/Hook/02-Kernel层Hook-Vendor_Hook与eBPF](../../../01-Mechanism/App/Hook/02-Kernel层Hook-Vendor_Hook与eBPF.md) | vendor hook 与 SELinux 互动 |

---

## 8. 下一篇预告 + 自检

### 8.1 下一篇

[08 AOSP 17 演进：Treble + CIL + userspace 加载](08-AOSP-17演进：Treble+CIL+userspace加载.md) 讲清：
- Treble 引入的 SELinux 隔离（AOSP 8 起）
- CIL 策略语言（AOSP 12+ 引入，AOSP 17 已成主流）
- userspace 加载机制（`load_policy` 演进）
- AOSP 17 相对 AOSP 14 的 3 个硬变化
- 迁移路径：从 AOSP 14 升到 AOSP 17 要改什么

### 8.2 看完本文的自检

- [ ] 能用 6 步通用流程定位 4 类根因
- [ ] 能完成 vendor daemon 从 0 到上线的全流程（案例 1）
- [ ] 能修复 init 启动期 bootloop（案例 2）
- [ ] 能修复 app 跨 app binder 调用（案例 3）
- [ ] 能区分 ro.* / persist.* property 的 set 权限（案例 4）
- [ ] 能修复 file_contexts 漏写（案例 5）

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
