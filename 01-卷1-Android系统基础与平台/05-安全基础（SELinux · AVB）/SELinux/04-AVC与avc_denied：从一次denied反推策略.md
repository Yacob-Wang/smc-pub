# 06-Foundation/SELinux · 04 · AVC 与 avc_denied：从一次 denied 反推策略

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 厂商适配
>
> **强依赖**：[01 总览](01-SELinux总览：MAC机制在Android的落地.md) · [02 策略文件体系](02-策略文件体系：sepolicy.te.cil.编译产物.md) · [03 Context 与 Label](03-Context与Label：四大主体的标签从哪来.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 logcat 里那一行 `avc: denied` 精确解读成"该改 .te 加哪条 allow"——这是稳定性架构师每天要做的核心动作
- **不是**：不复述 [01 §3 12 步访问](01-SELinux总览：MAC机制在Android的落地.md)；不复述 [02 §2.3 .te 语法](02-策略文件体系：sepolicy.te.cil.编译产物.md)
- **承接自**：[03 §7 真实调试场景](03-Context与Label：四大主体的标签从哪来.md)（本文展开那 3 个场景的"反推"细节）
- **衔接去**：[06 常见稳定性问题](06-常见稳定性问题：service-crash.neverallow.build-失败.md) / [07 实战 5 例](07-实战：定制SELinux策略排错5例.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章精确拆解 audit 行 8 个字段 | 90% 的人只读"avc: denied"5 个字，漏看 permissve / dev / pid |
| 2 | 第 4 章讲 `audit2allow` 三个危险陷阱 | AOSP 安全指南明确不推荐，但 90% 团队在用 |
| 3 | 第 6 章用 5 个真实案例（含 vendor 适配场景）| 教科书例子无法对应"现场 5 分钟决策" |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**`avc: denied` 行不是"错误日志"，是"内核在告诉你应该加哪条 allow 规则"——一行字精确映射一条 .te 策略。**

AOSP 17 上 denied 行的输出格式严格遵循 Linux audit 规范，**8 个字段全部可解析**。读懂这 8 个字段 = 直接生成正确的 allow 规则。**5 分钟定位、10 分钟修复** 是 oncall 工程师的硬指标。

---

## 1. `avc: denied` 行的 8 个字段精确解读

### 1.1 真实 audit 行（AOSP 17 + 6.18 LTS kernel）

```
type=1400 audit(1719475312.345:67): avc: denied { write } for pid=2345 comm="app" 
name="data.txt" dev="dm-3" scontext=u:r:untrusted_app:s0:c123,c256 
tcontext=u:object_r:system_data_file:s0 tclass=file permissive=0
```

### 1.2 字段精确含义

| 字段 | 含义 | 例子 | 怎么用 |
|:-----|:-----|:-----|:------|
| `type=1400` | audit 事件类型（固定 1400 = AVC）| `type=1400` | 过滤用：logcat `grep "type=1400"` |
| `audit(时间.序号)` | 时间戳 + 当前序号 | `audit(1719475312.345:67)` | 排序 / 关联其他事件 |
| `avc: denied { permission }` | 被拒绝的 permission | `{ write }` | **第一条 allow 要加的 perm** |
| `pid=2345` | 发起访问的进程 PID | `pid=2345` | 关联 `ps -p 2345` |
| `comm="app"` | 进程名（截断 15 字符）| `comm="app"` | 关联 `ps -eZ \| grep app` |
| `name="data.txt"` | 目标文件名（可选）| `name="data.txt"` | 看是哪个文件 |
| `dev="dm-3"` | 设备号 | `dev="dm-3"` | 关联 `/dev/block/...` |
| `scontext=u:r:untrusted_app:s0:c123,c256` | 主体 context | subject | **第二条 allow 的左值** |
| `tcontext=u:object_r:system_data_file:s0` | 客体 context | target | **第二条 allow 的右值** |
| `tclass=file` | 客体 class | `file` / `dir` / `socket` / `process` / `binder` | **第二条 allow 的 class** |
| `permissive=0` | 是否 permissive 模式 | `0` = enforcing，`1` = permissive | 决定修复紧迫性 |

### 1.3 模板：denied 行 → allow 规则

```
{ permission } scontext tcontext : tclass { permission }

例：
{ write } u:r:untrusted_app:s0:c123,c256  u:object_r:system_data_file:s0 : file
                              ↓                            ↓                       ↓        ↓
                         subject                       object                  class   permission
```

**生成的 .te 行**：

```te
allow untrusted_app system_data_file:file { write };
```

### 1.4 3 个常被忽略的关键字段

| 字段 | 为什么关键 | 漏看的后果 |
|:-----|:----------|:---------|
| `permissive=0` | 表示 enforcing 真的拒绝了，**线上问题** | 误以为是 permissive 测试环境（其实线上） |
| `pid=2345` | 找发起者进程 | 修复 .te 时加错 subject |
| `dev="dm-3"` | 找设备 | 容器 / chroot 场景下设备名错乱 |

---

## 2. 3 个数据源：哪里能抓到 denied 行

| 数据源 | 完整度 | 实时性 | 用法 |
|:------|:------|:------|:----|
| **logcat** | 部分（kernel 转发到 logd 才有）| 实时 | `adb logcat -d \| grep "avc: denied"` |
| **dmesg** | 完整 | 实时（重启前）| `adb shell dmesg \| grep "avc: denied"` |
| **/data/misc/audit/audit.log** | 完整 | 持久化 | `adb pull /data/misc/audit/audit.log` |

### 2.1 logcat vs dmesg 的区别

```
kernel audit 触发
    ↓
kernel audit 子系统 (kernel/audit/audit.c)
    ↓
    ├─→ netlink multicast → auditd 用户空间 → 写 /data/misc/audit/audit.log
    │
    └─→ printk → logd 转发 → logcat 缓存
```

**logcat 可能漏 denied**：
- logd 默认 ringbuffer 4MB（main）+ 256KB（system）
- 高频 denied 时，logcat 满了会覆盖
- **dmesg 完整但重启后丢**（除非 `pstore` 持久化）

### 2.2 实时抓 denied 5 个技巧

```bash
# 1. logcat 实时过滤（最常用）
$ adb logcat -d -b all | grep "avc: denied" | tail -50

# 2. dmesg 实时（kernel 重启前）
$ adb shell dmesg -w | grep "avc: denied"

# 3. audit.log 实时（最完整，userdebug 默认开启）
$ adb shell tail -f /data/misc/audit/audit.log | grep "avc: denied"

# 4. 触发后再抓（按时间戳过滤）
$ adb logcat -d -t '07-22 14:30:00.000' -b all | grep "avc: denied"

# 5. 拉全量日志后离线分析
$ adb shell bugreport > bugreport.zip
$ unzip -p bugreport.zip fs/data/misc/audit/audit.log | grep "avc: denied"
```

### 2.3 真实场景：denied 风暴的高效抓取

**线上 50% 场景**：服务起不来，重启后 logcat 被刷爆，普通 grep 找不到根因。

```bash
# 用 4 步法抓"第一次出现"的 denied（根因被淹没时）
$ adb shell dmesg -c  # 清空 dmesg（注意：清的是 ringbuffer）
$ adb shell setprop ctl.start my_failing_service
# 失败后
$ adb shell dmesg | grep "avc: denied" | head -3
# 第一次出现的就是根因
```

---

## 3. 反推 5 步法：从 denied 到 .te

### 3.1 5 步流程

```
[1] 抓 denied 行（logcat / dmesg / audit.log）
    ↓
[2] 拆解 8 字段（用 §1.2 表格）
    ↓
[3] 确定在哪个 .te 文件加
    - subject 域 → 找 system/sepolicy/public/<subject>.te
    - object type → 找 public/<type>.te 或 vendor/ 侧
    ↓
[4] 写 allow 规则
    - 最小权限（精确 permission，不用 *）
    - 检查 neverallow（可能编译失败）
    ↓
[5] m selinux_policy + 重新刷 boot.img
    - 跑完 m selinux_policy 才有 binary policy
    - 重新烧录 boot.img 才会生效
```

### 3.2 第 3 步：定位 .te 文件的 3 条路径

| subject / object | .te 文件位置 | 例子 |
|:----------------|:------------|:-----|
| `init` | `system/sepolicy/public/init.te` | `init` 域策略 |
| `system_server` | `system/sepolicy/private/system_server.te` | system_server 内部 |
| `surfaceflinger` | `system/sepolicy/public/surfaceflinger.te` | surfaceflinger 域 |
| `untrusted_app` | `system/sepolicy/public/te_macros`（app 通用）| 普通 app |
| vendor 自定义 `vendor_foo` | `device/<vendor>/<device>/sepolicy/vendor_foo.te` | vendor 适配 |

**找不到时**：
```bash
# 在 system/sepolicy 下递归 grep
$ grep -rn "type vendor_foo" system/sepolicy/
# 输出会指向定义 vendor_foo 的 .te
```

### 3.3 第 4 步：写 allow 规则的 3 个原则

1. **最小权限**：只给被 denied 的 permission，**不要给 class 上所有 permission**
2. **不用 `*`**：禁止 `allow X Y:file *;`（违反最小权限）
3. **attribute 复用**：如能归属到现有 attribute，写 attribute 而非具体 type

**反例**（90% 团队犯的错）：

```te
# 反例 1：给所有 permission（危险）
allow vendor_foo system_file:file *;

# 反例 2：给所有 type（更危险）
allow vendor_foo { system_file vendor_file system_data_file ... }:file { read write };
```

**正例**：

```te
# 正例 1：只给具体 permission
allow vendor_foo system_data_file:file { read write open getattr };

# 正例 2：用 attribute 收敛（如果已经定义）
typeattribute vendor_foo data_file_type;
# 然后用 data_file_type
allow vendor_foo data_file_type:file { read write open getattr };
```

---

## 4. audit2allow 的 3 个危险陷阱

`audit2allow` 是把 denied 行自动转成 allow 规则的"懒人工具"。**官方建议是"用但必须审"**——但 90% 团队"用但不审"。

### 4.1 audit2allow 真实用法

```bash
# 从 audit.log 生成
$ audit2allow -i /data/misc/audit/audit.log
# 输出：
#============= vendor_foo ==============
allow vendor_foo system_data_file:file { read write getattr open };

# 从 stdin 生成
$ adb shell dmesg | grep "avc: denied" | audit2allow
```

### 4.2 陷阱 1：默认给 class 上所有 permission

```bash
# 真实输出（看似只给 read）
#============= vendor_foo ==============
allow vendor_foo system_data_file:file { read };

# 但实际编译时会合并其他规则：
# audit2allow --restore 模式会丢失最小权限
# 真实最终产物（不知不觉变成 read + write + create + ...）
allow vendor_foo system_data_file:file { read write create unlink append ... };
```

**防御**：
```bash
# 永远用 -a 显式限定（-a = allow 模式，不合并）
$ audit2allow -a -i audit.log
# 输出 1 条 allow 精确对应 1 条 denied
```

### 4.3 陷阱 2：把 unlabeled 当成真 type

```bash
# audit.log 含一行：
avc: denied { write } ... scontext=u:r:vendor_foo:s0 
        tcontext=u:object_r:unlabeled:s0 tclass=file

# audit2allow 生成的"看似正确"规则：
allow vendor_foo unlabeled:file { write };

# 实际：unlabeled 是异常，**正确做法是修 file_contexts**，不是给 unlabeled 加 allow
```

**防御**：见到 `tcontext=...:unlabeled:s0` 时，**不要直接 audit2allow**，先查 file_contexts。

### 4.4 陷阱 3：忽略 neverallow

```bash
# audit2allow 生成的 allow
allow vendor_foo init:process transition;
# 但 AOSP 17 有 neverallow 规则禁止这种 transition
# → m selinux_policy 编译失败
# → 团队改成"先 commit 再说" → 编译绕过 → 上线被 CTS 拒
```

**防御**：audit2allow 后**必须** `m selinux_policy` 验证编译期通过。

### 4.5 audit2allow 安全使用流程

```
[1] audit2allow -a -i audit.log  # 显式 allow 模式
[2] 人工 review 生成的每条规则
[3] 手工编辑 .te（不用 audit2allow 写盘）
[4] m selinux_policy 验证
[5] 跑 CTS / VTS 验证
[6] 提交 + review
```

**反模式**：`audit2allow -M my_module`（自动写 .te 文件 + 编译），**永远不要在 vendor 适配用**。

---

## 5. sepolicy-analyze 验证：5 条命令

修复后必须用 `sepolicy-analyze` 验证 binary policy 真的包含新规则：

```bash
# 1. 列出所有 type（确认新 type 存在）
$ sepolicy-analyze precompiled_sepolicy types | grep vendor_foo
vendor_foo

# 2. 列出 vendor_foo 域所有 allow（确认新 allow 存在）
$ sepolicy-analyze precompiled_sepolicy allow -s vendor_foo
vendor_foo system_data_file:file { read write getattr open }

# 3. 验证反向：vendor_foo 不能越权
$ sepolicy-analyze precompiled_sepolicy allow -s vendor_foo -t init
# 期望：无输出（验证最小权限）

# 4. 列出所有 attribute
$ sepolicy-analyze precompiled_sepolicy attributes | head -10
domain
file_type
exec_type
service_manager_type
...

# 5. 检查 type 是不是被某个 attribute 包含
$ sepolicy-analyze precompiled_sepolicy type -a vendor_foo
# 期望：vendor_foo 有哪些 attribute 集
```

### 5.1 自动化验证脚本

```bash
#!/bin/bash
# verify_sepolicy_fix.sh
# 用法：./verify_sepolicy_fix.sh <device> <type>

DEVICE=$1
TYPE=$2
POLICY=out/target/product/${DEVICE}/vendor/etc/selinux/precompiled_sepolicy

echo "=== 1. type ${TYPE} 存在 ==="
sepolicy-analyze $POLICY types | grep -w $TYPE || { echo "FAIL"; exit 1; }

echo "=== 2. ${TYPE} 域所有 allow ==="
sepolicy-analyze $POLICY allow -s $TYPE

echo "=== 3. ${TYPE} 反向 allow（验证最小权限）==="
sepolicy-analyze $POLICY allow -t $TYPE
```

---

## 6. 5 个真实案例逐行解读

### 6.1 案例 1：vendor daemon 写 system_data_file denied

```
avc: denied { write } for pid=1234 comm="vendor.foo" name="state.db" 
dev="dm-3" scontext=u:r:vendor_foo:s0 
tcontext=u:object_r:system_data_file:s0 tclass=file permissive=0
```

**反推**：
- subject: `vendor_foo` (process)
- object: `system_data_file` (file)
- class: `file`
- permission: `write`

**修复**（加到 `device/<vendor>/<device>/sepolicy/vendor_foo.te`）：

```te
allow vendor_foo system_data_file:file { read write open getattr };
```

### 6.2 案例 2：app 通过 Binder 调用 service denied

```
avc: denied { call } for pid=5678 comm="com.example.app" 
scontext=u:r:untrusted_app:s0:c123,c256 
tcontext=u:object_r:my_custom_service:s0 tclass=binder permissive=0
```

**反推**：
- subject: `untrusted_app`
- object: `my_custom_service` (binder service type)
- class: `binder`
- permission: `call`

**修复**：

```te
# app 调用 service 的 SELinux 规则（两边都要）
# app 侧：untrusted_app 调用 service 的 binder
allow untrusted_app my_custom_service:binder { call transfer };

# service 侧：service_manager 暴露 service
allow my_custom_service_service my_custom_service:service_manager add;
# 实际写 service_contexts
```

**额外步骤**（常被漏）：
- `service_contexts` 加 `my_custom_service u:object_r:my_custom_service:s0`
- 否则 tcontext 可能是 `unlabeled`

### 6.3 案例 3：service 启动期属性设置 denied

```
avc: denied { set } for pid=234 comm="init" 
name="ctl.start" scontext=u:r:init:s0 
tcontext=u:object_r:ctl_default_prop:s0 tclass=property_service permissive=0
```

**反推**：
- subject: `init`
- object: `ctl_default_prop` (default ctl start/stop property)
- class: `property_service`
- permission: `set`

**根因**：init 想 `setprop ctl.start myservice` 但 default ctl type 受限。

**修复（不推荐 audit2allow）**：

```te
# 给 init 加对所有 ctl.* 的 allow
allow init ctl_default_prop:property_service set;
allow init ctl_start_prop:property_service set;
```

**或更好**：用 `setprop` 替换 `ctl.start`（`setprop ctl.start` 是反模式，正解是 `start <service>`）。

### 6.4 案例 4：neverallow 编译失败

```
neverallow check failed
  for scontext=u:r:vendor_foo:s0
  tcontext=u:r:vendor_foo:s0
  tclass=capability
  permission: sys_admin
  at out/host/linux-x86/bin/checkpolicy:42
make[1]: *** [out/.../treble_sepolicy] Error 1
```

**反推**：
- vendor_foo 域给了自己 `sys_admin` capability
- AOSP 17 neverallow 规则禁止任何非 init/kernel/recovery 域给 `self:capability sys_admin`

**修复**：
```te
# 反方案 1：用 attribute 排除（推荐）
typeattribute vendor_foo sys_admin_capable;  # 自己定义 attribute
# 改 neverallow 时不用 vendor_foo 域

# 反方案 2：找替代能力（不推荐改 neverallow）
allow vendor_foo self:capability { net_admin dac_override };  # 用其他 capability
```

### 6.5 案例 5：unlabeled 资源访问（陷阱）

```
avc: denied { open } for pid=3456 comm="init" name="init.rc" 
dev="dm-0" scontext=u:r:init:s0 
tcontext=u:object_r:unlabeled:s0 tclass=file permissive=0
```

**反推**：
- subject: `init`
- object: `unlabeled`（异常！）
- class: `file`
- permission: `open`

**根因**：**`init.rc` 文件本身没打 SELinux 标签**（file_contexts 漏写 / restorecon 没跑）。

**错误修复**（audit2allow 直接出）：
```te
# 这样写编译会过，但**根因没解决**
allow init unlabeled:file { open read getattr };
```

**正确修复**：
```te
# 加 file_contexts（不是 .te）
# system/sepolicy/public/file_contexts
/init(\.rc)?    u:object_r:init_rc_file:s0

# 跑 restorecon 重新打标签
$ adb shell restorecon -v /init.rc
```

**铁律**：看到 `unlabeled` 永远先查 file_contexts，不加 allow。

---

## 7. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 总览](01-SELinux总览：MAC机制在Android的落地.md) | §1.1 denied 行的位置 |
| [02 策略文件体系](02-策略文件体系：sepolicy.te.cil.编译产物.md) | .te 语法 + binary policy 编译 |
| [03 Context 与 Label](03-Context与Label：四大主体的标签从哪来.md) | §7 三个真实场景的展开 |
| [06 常见稳定性问题](06-常见稳定性问题：service-crash.neverallow.build-失败.md) | 下篇讲 SELinux 引起的 7 大症状 |
| [04-Tool/Perfetto/01-Perfetto系统总览与架构设计](../../../../05-卷5-调查工具链/31-Perfetto 全栈使用/01-Perfetto系统总览与架构设计.md) | Perfetto trace 怎么结合 SELinux denied 看 |
| [05-Governance/Security](../../../05-Governance/Security/) | 治理：denied 怎么门禁 / 审批 |
| [06-Foundation/Tools/Android_Tools/Logcat_Complete_Guide](../../../05-卷5-调查工具链/35-断点与%20Native%20调试/Logcat_Complete_Guide.md) | logcat 过滤 denied 的 5 条命令 |

---

## 8. 下一篇预告 + 自检

### 8.1 下一篇

[05 init 进程与 SELinux：分阶段加载](05-init进程与SELinux：分阶段加载.md) 讲清：
- kernel → init → vendor 三阶段 SELinux 加载时序
- init 进程怎么用 SELinux context 切到对应 domain
- early-boot / late-boot / vendor-boot 三段策略的边界
- kernel 启动参数 `androidboot.selinux=` 的 4 个取值

### 8.2 看完本文的自检

- [ ] 能拆解 `avc: denied` 行的 8 个字段
- [ ] 能从 1 行 denied 反推出 1 条 .te allow 规则
- [ ] 能区分 logcat / dmesg / audit.log 3 个数据源的差异
- [ ] 知道 `audit2allow` 的 3 个危险陷阱 + 安全使用流程
- [ ] 知道 `unlabeled` 不该用 audit2allow 修复，要修 file_contexts

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
