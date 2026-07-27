# 06-Foundation/Tools/Android_Tools · 04 · Logcat 与 SELinux/avc：denied 行解读

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 看 denied 行的所有人
>
> **强依赖**：[03 Logcat 过滤与持久化](03-Logcat过滤与持久化.md) · [06-Foundation/SELinux/04-AVC与avc_denied](../../SELinux/04-AVC与avc_denied：从一次denied反推策略.md) · [06-Foundation/SELinux/07-实战](../../SELinux/07-实战：定制SELinux策略排错5例.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 logcat 中 `avc: denied` 行的 8 字段精确读法 + logcat 跟 SELinux 5 大集成场景 + 5 个真实 case 讲清楚——oncall 5 分钟从 denied 改 .te
- **不是**：不复述 [06-Foundation/SELinux/04 §1 8 字段完整版](../../SELinux/04-AVC与avc_denied：从一次denied反推策略.md)（本文是 logcat 视角的精简版）；不复述 [02 格式与 tag](02-Logcat格式与tag体系.md)
- **承接自**：[03 §2.2 denied 模板](03-Logcat过滤与持久化.md) → 本文展开"denied 怎么读 + 怎么改"
- **衔接去**：[06-Foundation/SELinux/04 完整 8 字段](../../SELinux/04-AVC与avc_denied：从一次denied反推策略.md) / [06-Foundation/SELinux/07 实战 5 例](../../SELinux/07-实战：定制SELinux策略排错5例.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章用 5 大集成场景表格 | 90% 现场就 5 类 |
| 2 | 第 2 章 8 字段精简读法 | logcat 视角的"5 秒读" |
| 3 | 第 4 章 5 case 走完反推 5 步 | oncall 实战 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**logcat 中 `avc: denied` 行 = SELinux 给出的"修法提示"——8 字段精确读 + 5 步改 .te = oncall 5 分钟闭环。**

AOSP 17 上 denied 行从 kernel audit 子系统流到 logd 再到 logcat，整条链路 5 秒理解 = 5 分钟修法。

---

## 1. logcat 与 SELinux 5 大集成场景

### 1.1 5 大场景总览

| 场景 | logcat 哪里看 | 关键字 | 何时触发 |
|:-----|:------------|:-------|:-------|
| **Kernel denied** | `-b kernel` | `avc: denied` | kernel LSM 钩子拒绝 |
| **Audit 风暴** | `-b kernel` | `audit: ... denied` | 同一 denied 多次触发 |
| **User 进程 denied** | `-b main` | `avc: denied` | native 进程被拒 |
| **Service 启动 denied** | `-b system` | `avc: denied { transition }` | init 切 domain 失败 |
| **CIL 编译错** | `-b system` | `neverallow check failed` | selinux_policy 编译失败 |

### 1.2 场景 1：Kernel denied

```bash
# 看 kernel denied（90% 现场）
$ adb logcat -d -b kernel | grep "avc: denied"
type=1400 audit(1234567890.123:67): avc: denied { write } for ...
```

**特点**：
- 在 kernel buffer（不是 main）
- `type=1400` 是 audit 固定码
- 触发源头：kernel LSM 钩子（`kernel/security/selinux/hooks.c`）

### 1.3 场景 2：Audit 风暴

```bash
# 找 audit 风暴
$ adb logcat -d -b kernel | grep "avc: denied" | wc -l
# 1234

# 意味着同一 denied 触发了 1234 次
# 修法：先 setenforce 0 临时，再修 .te
```

### 1.4 场景 3：User 进程 denied

```bash
# 找 user 进程 denied
$ adb logcat -d -b main | grep "avc: denied"
type=1400 audit(...): avc: denied { ... } for comm="surfaceflinger" ...
```

**特点**：
- 在 main buffer
- `comm="<进程名>"` 标识是哪个进程
- 触发源头：native 进程的 syscall 被 kernel LSM 钩子拒

### 1.5 场景 4：Service 启动 denied

```bash
# 找 service 启动 denied（bootloop 常见）
$ adb logcat -d -b system | grep "avc: denied"
type=1400 audit(...): avc: denied { transition } for comm="init" path="/system/bin/vendor.foo" ...
```

**特点**：
- 在 system buffer
- `{ transition }` 标志是 type transition
- 触发源头：init 切到 vendor_foo 域失败

### 1.6 场景 5：CIL 编译错

```bash
# 找 CIL 编译错（开发期）
$ adb logcat -d -b system | grep "neverallow check failed"
# neverallow check failed at /out/host/.../checkpolicy:42
```

**特点**：
- 在 system buffer（init 加载时）
- 触发源头：binary policy 加载时的 neverallow 检查
- **不是 logcat 输出，是编译期 / 加载期报错**

---

## 2. denied 行 8 字段精简读法

### 2.1 真实 denied 行

```
type=1400 audit(1719475312.345:67): avc: denied { write } for pid=2345 comm="app" 
name="data.txt" dev="dm-3" scontext=u:r:untrusted_app:s0:c123,c256 
tcontext=u:object_r:system_data_file:s0 tclass=file permissive=0
```

### 2.2 8 字段速查（5 秒读一行）

| # | 字段 | 例子 | 含义 | 5 秒读 |
|:-:|:-----|:-----|:-----|:-----|
| 1 | `type=1400` | `type=1400` | audit 事件类型 | 固定 1400 |
| 2 | `audit(时间.序号)` | `audit(1719475312.345:67)` | 时间戳 | 排序用 |
| 3 | `{ permission }` | `{ write }` | 被拒 permission | **第 1 个 allow 的 perm** |
| 4 | `scontext=...` | `u:r:untrusted_app:s0:c123,c256` | 主体 context | **第 1 个 allow 的左值** |
| 5 | `tcontext=...` | `u:object_r:system_data_file:s0` | 客体 context | **第 1 个 allow 的右值** |
| 6 | `tclass=...` | `tclass=file` | 客体 class | **第 1 个 allow 的 class** |
| 7 | `permissive=...` | `permissive=0` | 是否 permissive | 0=线上问题 |
| 8 | `comm=...` | `comm="app"` | 进程名 | 关联进程 |

### 2.3 一行转一条 allow 规则

```
denied 行的关键 4 字段 → 1 条 allow 规则

{ permission } scontext type tcontext tclass

{ write } untrusted_app system_data_file : file

↓
allow untrusted_app system_data_file:file { write };
```

### 2.4 8 字段速查（精简决策树）

```
[1] 看 { permission } + tclass
    ├─ { transition } tclass=process → domain transition 失败
    ├─ { read/write/open } tclass=file → 文件访问 denied
    ├─ { set } tclass=property_service → property denied
    ├─ { add } tclass=service_manager → service add 失败
    └─ { call } tclass=binder → binder 调用 denied

[2] 看 tcontext
    ├─ = unlabeled → file_contexts 漏写（[06-Foundation/SELinux/04 §6.5](../../SELinux/04-AVC与avc_denied：从一次denied反推策略.md)）
    ├─ 在 policy 中存在 → 继续看
    └─ 在 policy 中不存在 → type 漏定义

[3] 看 permissive
    ├─ 0 → enforcing（线上）
    └─ 1 → permissive（debug 用）

[4] 看 comm
    └─ 知道是哪个进程触发的
```

### 2.5 完整 8 字段解读（见 [06-Foundation/SELinux/04 §1.2](../../SELinux/04-AVC与avc_denied：从一次denied反推策略.md)）

---

## 3. 反推 5 步法

### 3.1 5 步流程

```
[1] 抓 denied 行（logcat -b kernel | grep "avc: denied"）
[2] 拆解 4 关键字段（permission / scontext / tcontext / tclass）
[3] 找 .te 文件（用 tcontext 查 sepolicy-analyze types）
[4] 写 allow 规则（精确 permission，不用 *）
[5] m selinux_policy + 重烧 boot.img
```

### 3.2 第 1 步：抓 denied

```bash
# 1. 标准命令
$ adb logcat -d -b kernel | grep "avc: denied"

# 2. 加时间窗
$ adb logcat -d -b kernel -t '07-27 10:30:00' | grep "avc: denied"

# 3. 加 pid
$ adb logcat -d -b kernel --pid=$(adb shell pidof com.example.app) | grep "avc: denied"

# 4. 看 audit.log（更全）
$ adb shell tail -f /data/misc/audit/audit.log | grep "avc: denied"
```

### 3.3 第 2 步：拆解 4 字段

```bash
# 1. 用 awk 提取关键 4 字段
$ adb logcat -d -b kernel | grep "avc: denied" | \
  grep -oE '\{ [a-z]+ \}' | head  # permission
$ adb logcat -d -b kernel | grep "avc: denied" | \
  grep -oE 'scontext=u:r:[^ ]+' | head  # scontext
$ adb logcat -d -b kernel | grep "avc: denied" | \
  grep -oE 'tcontext=u:[^ ]+' | head  # tcontext
$ adb logcat -d -b kernel | grep "avc: denied" | \
  grep -oE 'tclass=[a-z_]+' | head  # tclass
```

### 3.4 第 3 步：找 .te 文件

```bash
# 1. 找 tcontext 在哪定义
$ adb pull /vendor/etc/selinux/precompiled_sepolicy
$ sepolicy-analyze precompiled_sepolicy types | grep "system_data_file"
# system_data_file
# 存在 → 在 .te 找
$ grep -rn "type system_data_file" system/sepolicy/

# 2. 找 scontext 域
$ sepolicy-analyze precompiled_sepolicy types | grep "untrusted_app"
# untrusted_app
```

### 3.5 第 4 步：写 allow

```python
# 在 device/<vendor>/<device>/sepolicy/<app>.te 加：
allow untrusted_app system_data_file:file { write };
```

### 3.6 第 5 步：编译 + 烧录

```bash
# 1. 编译
$ m selinux_policy
# 检查无 ERROR

# 2. 烧录
$ fastboot flash boot out/.../boot.img
$ fastboot flash vendor out/.../vendor.img
$ fastboot reboot
```

### 3.7 5 步法总耗时

| 步骤 | 耗时 |
|:-----|:----|
| 1 抓 denied | 5 秒 |
| 2 拆解字段 | 5 秒 |
| 3 找 .te | 30 秒 |
| 4 写 allow | 1 分钟 |
| 5 编译 + 烧录 | 5-10 分钟 |
| **总** | **7-13 分钟** |

---

## 4. 5 个真实 case（精简版）

### 4.1 case 1：app 写文件 denied

```
avc: denied { write } for pid=2345 comm="app" name="data.txt" 
scontext=u:r:untrusted_app:s0:c123,c256 
tcontext=u:object_r:system_data_file:s0 tclass=file
```

**反推 4 字段**：
- permission: `write`
- scontext: `untrusted_app`
- tcontext: `system_data_file`
- tclass: `file`

**生成 allow**：
```te
# 在 system/sepolicy/public/untrusted_app.te 加
allow untrusted_app system_data_file:file { read write open getattr };
```

### 4.2 case 2：service 启动 transition denied

```
avc: denied { transition } for comm="init" path="/system/bin/vendor.foo"
scontext=u:r:init:s0 tcontext=u:r:vendor_foo:s0 tclass=process
```

**反推 4 字段**：
- permission: `transition`
- scontext: `init`
- tcontext: `vendor_foo`
- tclass: `process`

**生成 allow**：
```te
# 在 device/<vendor>/<device>/sepolicy/vendor_foo.te 加
type vendor_foo, domain;
type vendor_foo_exec, exec_type, vendor_file_type, file_type;
type_transition init vendor_foo_exec:process vendor_foo;
allow init vendor_foo:process transition;
allow init vendor_foo_exec:file { read execute open };
```

**附加**：加 file_contexts：
```
/system/bin/vendor\.foo    u:object_r:vendor_foo_exec:s0
```

### 4.3 case 3：binder call denied

```
avc: denied { call } for pid=5678 comm="com.example.app" 
scontext=u:r:untrusted_app:s0:c123,c256 
tcontext=u:object_r:my_service:s0 tclass=binder
```

**反推 4 字段**：
- permission: `call`
- scontext: `untrusted_app`
- tcontext: `my_service`
- tclass: `binder`

**生成 allow**：
```te
# app 调 service
allow untrusted_app my_service:binder { call transfer };
allow untrusted_app my_service_service:service_manager find;

# service 接收 call
allow my_service untrusted_app:binder { call transfer receive };
allow my_service untrusted_app:fd use;
```

**附加**：加 service_contexts：
```
my_service u:object_r:my_service:s0
```

### 4.4 case 4：property set denied

```
avc: denied { set } for name="ro.build.fingerprint" scontext=u:r:shell:s0
tcontext=u:object_r:fingerprint_prop:s0 tclass=property_service
```

**反推 4 字段**：
- permission: `set`
- scontext: `shell`
- tcontext: `fingerprint_prop`
- tclass: `property_service`

**正确修法**（不要 audit2allow）：
```bash
# 改用非 ro.* property
$ adb shell setprop persist.test.fingerprint "x"
```

**或**（debug 设备）：
```te
# 在 system/sepolicy/public/shell.te
allow shell fingerprint_prop:property_service set;
```

### 4.5 case 5：unlabeled 资源

```
avc: denied { open } for pid=3456 comm="init" name="init.rc" 
scontext=u:r:init:s0 tcontext=u:object_r:unlabeled:s0 tclass=file
```

**反推 4 字段**：
- permission: `open`
- scontext: `init`
- tcontext: `unlabeled` ⚠️
- tclass: `file`

**根因**：tcontext 是 unlabeled → file_contexts 漏写

**正确修法**：
```te
# 在 system/sepolicy/public/file_contexts 加
/init(\.rc)?    u:object_r:init_rc_file:s0
```

**铁律**：**看到 unlabeled 永远先修 file_contexts，不加 allow**。

---

## 5. oncall 5 分钟定位

```
[1] 30 秒抓 denied（5 秒）
$ adb logcat -d -b kernel | grep "avc: denied" | head -5
  ↓
[2] 30 秒读 4 字段（5 秒）
- permission
- scontext
- tcontext
- tclass
  ↓
[3] 30 秒看 tcontext 是不是 unlabeled（5 秒）
- unlabeled → 修 file_contexts
- 有定义 → 继续
- 无定义 → 加 type
  ↓
[4] 1 分钟找 .te 文件（30 秒）
$ grep -rn "type XXX" system/sepolicy/
  ↓
[5] 1 分钟写 allow + 改 .te（30 秒）
- 最小权限
- 不用 *
  ↓
[6] 5-10 分钟编译 + 烧录 + 验证
```

**总耗时**：5 + 5 + 30 + 30 + 5 = **75 秒**（含编译烧录约 10 分钟）

---

## 6. 5 个反模式

### 6.1 反模式 1：直接 audit2allow

```bash
# ❌ 反模式
$ adb shell dmesg | grep "avc: denied" | audit2allow
# 生成的 allow 过宽（给所有 permission）

# ✅ 正解
$ adb shell dmesg | grep "avc: denied" | audit2allow -a
# -a 显式 allow 模式
# + 人工 review
# + m selinux_policy 验证
```

### 6.2 反模式 2：注释 neverallow

```bash
# ❌ 反模式
# 在 platform 侧注释掉 neverallow
# 编译过了，但 CTS 必拒
```

### 6.3 反模式 3：用 setenforce 0 长期绕过

```bash
# ❌ 反模式
$ adb shell setenforce 0
# 长期 0 → 失去强制保护
# 只用于 debug 时临时
```

### 6.4 反模式 4：给 unlabeled 加 allow

```bash
# ❌ 反模式
allow vendor_foo unlabeled:file { open };
# 看起来编译过了，但根因没解决

# ✅ 正解
# 修 file_contexts
```

### 6.5 反模式 5：写 `allow * * * *` 过宽

```te
# ❌ 反模式
allow vendor_foo system_file:file *;

# ✅ 正解
allow vendor_foo system_data_file:file { read write open getattr };
```

---

## 7. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [02 Logcat 格式](02-Logcat格式与tag体系.md) | 基础 |
| [03 Logcat 过滤与持久化](03-Logcat过滤与持久化.md) | 过滤 |
| [06-Foundation/SELinux/04 完整 8 字段](../../SELinux/04-AVC与avc_denied：从一次denied反推策略.md) | 完整 |
| [06-Foundation/SELinux/05 init 与 SELinux](../../SELinux/05-init进程与SELinux：分阶段加载.md) | 启动期 |
| [06-Foundation/SELinux/06 常见稳定性问题](../../SELinux/06-常见稳定性问题：service-crash.neverallow.build-失败.md) | 速查表 |
| [06-Foundation/SELinux/07 实战 5 例](../../SELinux/07-实战：定制SELinux策略排错5例.md) | 实战 |

---

## 8. logcat 4 篇收官 + 自检

### 8.1 看完 logcat 4 篇的自检

- [ ] 能用 9 字段精确读一行 logcat
- [ ] 能用 5 大过滤维度组合定位
- [ ] 能用 3 种持久化方式
- [ ] 能用 5 步法处理 denied 行
- [ ] 能用 5 个真实 case 走完反推 5 步
- [ ] 能区分 5 类 SELinux 集成场景
- [ ] 知道 5 个反模式

### 8.2 logcat 4 篇引用矩阵

```
[01] Logcat_Complete_Guide
  ↓ → [02] 格式 / [03] 过滤
  ↑ ← 全部

[02] 格式与 tag 体系
  ↓ → [03] 过滤
  ↑ ← [01] [03] [04]

[03] 过滤与持久化
  ↓ → [04] SELinux 集成
  ↑ ← [02] [04]

[04] 与 SELinux/avc（你正在读）
  ↑ ← 全部 3 篇
```

### 8.3 logcat 4 篇核心 takeaway

- **5 大 buffer** = oncall 现场定位 5 秒起步
- **5 大过滤维度** = 组合 5 秒找到
- **3 种持久化** = 临时 / 一次性 / 长期
- **5 步反推法** = denied 行 5 分钟修

### 8.4 收官话

logcat 4 篇在稳定性架构师的能力模型里属于**"取证落地"层**——拿到 logcat 能 5 分钟找到 7 大症状的 SELinux 根因。

下一步推荐读：
- [06-Foundation/SELinux/04 完整 8 字段](../../SELinux/04-AVC与avc_denied：从一次denied反推策略.md) — 完整版
- [06-Foundation/SELinux/07 实战 5 例](../../SELinux/07-实战：定制SELinux策略排错5例.md) — 完整实战
- [06-Foundation/SELinux/06 常见稳定性问题](../../SELinux/06-常见稳定性问题：service-crash.neverallow.build-失败.md) — 速查表

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，logcat 4 篇收官）
