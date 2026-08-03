# 06-Foundation/SELinux · 03 · Context 与 Label：四大主体的标签从哪来

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · 平台 / BSP · 设备维护
>
> **强依赖**：[01 总览](01-SELinux总览：MAC机制在Android的落地.md) · [02 策略文件体系](02-策略文件体系：sepolicy.te.cil.编译产物.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把"进程标签、文件标签、property 标签、service 标签"这 4 大主体的 SELinux Context 讲清楚——它们从哪个文件来、什么时机被赋值、怎么调试改值
- **不是**：不复述 [02 §3.1 file_contexts 的正则语法](02-策略文件体系：sepolicy.te.cil.编译产物.md)；不复述策略决策本身（[04 AVC](04-AVC与avc_denied：从一次denied反推策略.md)）
- **承接自**：[02 §3.1 .fc 文件](02-策略文件体系：sepolicy.te.cil.编译产物.md)（本文讲 .fc 怎么被使用）
- **衔接去**：[04 AVC 与 avc_denied](04-AVC与avc_denied：从一次denied反推策略.md) / [05 init 与 SELinux 分阶段加载](05-init进程与SELinux：分阶段加载.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章把 context 4 段字段单独列表 | 90% 的 denied 行问题在 4 段字段没读对 |
| 2 | 第 5 章 service_contexts 单独立节 | service_manager 的 SELinux 标签被忽略导致 50% 的 service 启动失败 |
| 3 | 第 7 章真实命令都用 `-Z` 输出格式 | 架构师要能直接对 logcat 输出做匹配 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**Context（安全上下文）= SELinux 用来标识"谁是谁"的字符串，由 4 段字段组成；标签（Label）= 同一个东西的另一个名字。**

AOSP 17 上 4 大主体（进程 / 文件 / property / service）都有自己独立的 context 体系——理解 4 大 context 的来源和赋值时机，是"看 denied 行能定位到具体哪个文件 / 哪个 service"的关键。

---

## 1. SELinux Context 的 4 段字段

```
u:object_r:init_exec:s0
│   │      │        │
│   │      │        └── sensitivity（MLS/MCS level，AOSP 17 几乎固定 s0）
│   │      └─────────── type（核心！DENY 决策只看 type）
│   └────────────────── role（role-based access，AOSP 17 几乎固定 object_r 或 system_r）
└────────────────────── user（SELinux user，区别于 Linux UID）
```

### 1.1 4 段字段的稳定性含义

| 字段 | 是什么 | 决策影响 | 调试时关注度 |
|:-----|:------|:---------|:----------|
| **user** | SELinux user（不是 Linux UID）| 决定 role 范围 | 低（Android 几乎只有 `u` 一种）|
| **role** | SELinux role | 决定能进哪些 type | 低（Android 几乎只有 `object_r` 和 `system_r`）|
| **type** | 主体 / 客体 的类型 | **DENY 决策只看这个** | **极高** |
| **sensitivity** | MLS level（multi-level security）| 决定跨级别访问 | 低（Android 几乎固定 `s0`）|

**关键事实**：**Android SELinux 决策只看 type 字段**。前面 `u:object_r:` 和后面 `:s0` 是历史兼容性，几乎不影响决策。

### 1.2 MCS categories（多类别安全）

AOSP 14+ 引入了 MCS categories，常见于：
- 多人多 app 隔离
- 工作区 / 个人区隔离
- 多用户

```
u:object_r:system_data_file:s0:c123,c256
                                    └────┘
                                    MCS categories
```

**MCS 触点**：
- 同一 type 的不同 instance 可以用 MCS category 隔离
- 例如同一 `system_data_file` type，多个 app 各自有 `c123` / `c256`
- 决策时**同 type 但不同 category 仍可访问**（除非显式 deny MCS）

**调试命令**：
```bash
# 看进程 MCS category
$ adb shell ps -Z | grep system_server
u:r:system_server:s0       system    1234  1  ... /system/bin/system_server
                           └── level s0（无 MCS categories）

# 看文件 MCS category
$ adb shell ls -Z /data/data/com.example.app
u:object_r:app_data_file:s0:c123,c256  user  user  ... /data/data/com.example.app
                                         └── MCS categories c123 + c256
```

### 1.3 5 种特殊 Context

| Context | 含义 | 触点 |
|:--------|:-----|:-----|
| `u:r:kernel:s0` | 内核自身 | 看 `ps -eZ` 第一行 |
| `u:r:unlabeled:s0` | 没打标签的资源 | 文件系统异常 / 启动期 |
| `u:r:init:s0` | init 进程（PID 1）| 看 `ps -eZ \| grep init` |
| `u:r:zygote:s0` | zygote 进程 | app_process 启动后 |
| `u:r:su:s0` | root shell（userdebug）| debug 模式才有 |

`unlabeled` 是稳定性触点——**如果线上看到大量 `unlabeled` 资源，说明 file_contexts 配错或 `restorecon` 没跑**。

---

## 2. 进程 Context 从哪来

### 2.1 进程 Context 的存储位置

进程 Context 不存文件里，存 **task_struct** 的 cred 子结构：

```c
// kernel/security/selinux/include/objsec.h（简化）
struct task_security_struct {
    u32 osid;           // subject ID（进程的 type SID）
    u32 sid;            // current SID
    u32 exec_sid;       // exec 时的新 SID
    u32 create_sid;     // fork 时的新 SID
    u32 keycreate_sid;
    u32 sockcreate_sid;
};

// 进程切换/创建时
// task_struct->cred->security = task_security_struct
```

**OSID 怎么决定**：
- 进程由 `exec()` 启动时，内核从可执行文件的 SID 找新进程的 SID
- 父进程 SID 通过 `transition` 规则传给子进程（除非 type_transition 显式指定新 type）
- **这是 `domain_auto_trans` interface 的核心机制**（见 [02 §3.2](02-策略文件体系：sepolicy.te.cil.编译产物.md)）

### 2.2 进程 Context 调试 5 条命令

```bash
# 1. 看自己（当前 shell）
$ adb shell id -Z
u:r:shell:s0

# 2. 看所有进程
$ adb shell ps -eZ
LABEL                          USER  PID  PPID  ...
u:r:kernel:s0                  root     1     0  /init
u:r:init:s0                    root   123     1  /system/bin/init
u:r:zygote:s0                  root   234     1  zygote64
u:r:system_server:s0           system 456   234  system_server
u:r:surfaceflinger:s0          system 567   234  /system/bin/surfaceflinger
u:r:untrusted_app:s0:c123,c256 u0_a45 6789 234  com.example.app
...

# 3. 看单进程
$ adb shell ps -A -Z | grep init
u:r:init:s0                    root   123     1  /system/bin/init

# 4. 看某 PID 的所有 thread（system_server 这种多线程）
$ adb shell ps -T -p 456 -Z
u:r:system_server:s0 system  456  456  ... 1  system_server
u:r:system_server:s0 system  456  457  ... 1  Signal Catcher
u:r:system_server:s0 system  456  458  ... 1  JDWP
...

# 5. 看某 PID 的内核栈
$ adb shell cat /proc/456/attr/current
u:r:system_server:s0
```

### 2.3 进程 Context 变化的 3 个时机

```
进程 Context 何时会变？

[1] exec() 调用
    └─ 内核从可执行文件 label 找新 SID
       └─ 走 type_transition / domain_auto_trans 规则

[2] 主动 setcon() 调用
    └─ 极少见（只有 init / 服务启动时用）
       └─ 对应 setcon / setexeccon 系统调用

[3] 进程被强制改写（理论上不可，AOSP 17 未实现）
    └─ 早期 SELinux 实验功能，未进入生产
```

**关键事实**：**进程 Context 几乎只在 exec() 时变**。一个进程的 SID 在它的整个生命周期不变（除非 `exec()` 重新装入）。

---

## 3. 文件 Context 从哪来

文件 Context（label）**存在文件系统扩展属性（xattr）**里：

```
$ adb shell getfattr -d -m security /system/bin/init
# file: system/bin/init
security.selinux="u:object_r:init_exec:s0\0"
```

### 3.1 3 个赋值时机

| 时机 | 谁赋值 | 怎么赋 | 何时生效 |
|:-----|:------|:-------|:--------|
| **编译时** | build 阶段 `setfiles` | 写 `security.selinux` xattr | 镜像烧录后即生效 |
| **启动时** | init 进程 `restorecon` | 重新打标签 | 启动期关键路径 |
| **运行时** | app / service 主动 `setfilecon` | 写新 xattr | 罕见（仅 init / installd 偶尔用）|

**`restorecon` 触发的稳定性问题**：
- 启动期 `restorecon` 跑失败 → 文件 `unlabeled` → 后续访问全部 denied
- `restorecon` 跑得太久 → 启动变慢
- 经常被 `setprop` 控制：`setprop selinux.restorecon_immutable true`

### 3.2 file_contexts 匹配规则

```bash
# 1. 看某文件实际标签
$ adb shell ls -Z /system/bin/zygote
u:object_r:zygote_exec:s0  root  shell  ...  /system/bin/zygote

# 2. 看 file_contexts 怎么定义这个标签
$ grep zygote system/sepolicy/public/file_contexts
/system/bin/zygote          u:object_r:zygote_exec:s0
/system/bin/app_process     u:object_r:zygote_exec:s0
/system/bin/app_process32   u:object_r:zygote_exec:s0

# 3. 检查 file_contexts 是否有遗漏
$ checkfc -p /system system/sepolicy/public/file_contexts
# 输出会列出所有"file_contexts 写了但实际文件不存在"或"实际文件存在但 file_contexts 没写"
```

### 3.3 实际打标签的代码路径

```
/system/bin/setfiles -r /system /system/etc/selinux/plat_file_contexts /system
└── external/selinux/libsemanage/src/store.c
    └── 读 file_contexts + 正则匹配
    └── setxattr(path, "security.selinux", label, XATTR_CREATE)
        └── VFS 写 xattr
            └── kernel/security/selinux/hooks.c:selinux_inode_setxattr
                └── 验证允许 setxattr → 写入 inode->i_security
```

**关键源码锚点**（[01 §3 提过](01-SELinux总览：MAC机制在Android的落地.md)）：
- `kernel/security/selinux/hooks.c:selinux_inode_setxattr`（LSM 钩子）
- `external/selinux/libsemanage/src/store.c:setfiles_set_label`（用户空间工具）

### 3.4 restorecon 启动期链

```bash
# init.rc 里
on early-init
    setcon u:r:init:s0
    restorecon --recursive --force /system

on post-fs-data
    restorecon --recursive --force /data

# restorecon 实现：external/selinux/libselinux/src/restorecon.c
```

**稳定性含义**：restorecon 失败 → data 分区所有文件 unlabeled → app 启动时 denied 风暴。

---

## 4. Property Context

Property Context 不存 xattr，**存在 system property 数据库的内存数据结构里**，由 `property_service` 在 `__set_property` 时查询并强制。

### 4.1 property_contexts 真实例子

```te
# system/sepolicy/public/property_contexts（简化）
# 格式：property_name  →  context

# 普通 property
ro.*                u:object_r:system_prop:s0
sys.*               u:object_r:system_prop:s0
service.*           u:object_r:system_prop:s0
persist.*           u:object_r:system_prop:s0

# 特定 property（更细）
ro.build.fingerprint u:object_r:fingerprint_prop:s0
ro.serialno         u:object_r:system_prop:s0
ro.boot.serialno    u:object_r:system_prop:s0
ro.debuggable       u:object_r:debug_prop:s0

# SELinux 自身
selinux.*           u:object_r:selinux_prop:s0

# ctl.* 是 service control，不走 property SELinux
# 但 ctl.start / ctl.stop 受 init context 限制
```

### 4.2 property_contexts 的 3 个匹配模式

| 模式 | 例子 | 含义 |
|:-----|:-----|:-----|
| **精确匹配** | `ro.build.fingerprint` | 只匹配这个完整名 |
| **前缀匹配** | `ro.*` | 匹配 `ro.` 开头的所有 property |
| **类型匹配** | `ctl.start` | service control，单独处理 |

**稳定性含义**：
- `setprop ro.debuggable 1` → 检查调用者是否有 `debug_prop:property_service { set }`
- 如果没有，setprop 失败（看起来"系统没反应"）
- **线上常见 denied**：`avc: denied { set } for scontext=u:r:shell:s0 tcontext=u:object_r:system_prop:s0 tclass=property_service`

### 4.3 调试 property denied

```bash
# 1. 看某 property 要求的 context
$ adb shell getprop -T ro.debuggable
u:object_r:debug_prop:s0

# 2. 看自己能不能 set
$ adb shell setprop ro.debuggable 1
# 失败 + logcat:
# avc: denied { set } for name="ro.debuggable" scontext=u:r:shell:s0
#        tcontext=u:object_r:debug_prop:s0 tclass=property_service

# 3. 解决：要么换非 ro.* property，要么给 shell 域加 allow
```

---

## 5. Service Context

Service Context 决定 **service_manager 维护的服务列表里，每个服务名对应的 SELinux type**。

### 5.1 service_contexts 真实例子

```te
# system/sepolicy/public/service_contexts（简化）
# 格式：service_name  →  context

activity            u:object_r:activity_service:s0
package             u:object_r:package_service:s0
window              u:object_r:window_service:s0
input               u:object_r:input_service:s0
audio               u:object_r:audio_service:s0

# vendor 自己的 service（需要 platform 在 public/ 暴露 type）
vendor.foo.bar      u:object_r:vendor_foo_service:s0
```

### 5.2 服务添加的稳定性触点

```java
// frameworks/base/services/core/java/com/android/server/SystemService.java
public abstract class SystemService {
    public final void publishBinderService(String name, IBinder service) {
        // 走 service_manager.addService()
        // 内核在 binder transaction 时检查 scontext 是否允许
        // → allow  scontext  service_manager_type:service_manager { add }
    }
}
```

**addService 的 SELinux 检查流程**：
```
[1] app/system_service 调用 ServiceManager.addService("my_svc", binder)
[2] → ServiceManagerNative.addService（system_server 进程内）
[3] → service_manager.c:add_service（system_server 内）
[4] → 查 service_contexts，把 "my_svc" 转成 SELinux type
[5] → 检查调用者 type 是否有 allow 写 service_manager 的 add
[6] → 检查 type 是否被 platform public/ 暴露（vendor 新增时关键）
```

**线上常见 50% 启动失败**：
- vendor 加新 service → service_contexts 漏写 → type 是 `unlabeled` → addService denied
- vendor 加新 service → type 没在 platform public/ 暴露 → 编译期 neverallow 失败

### 5.3 调试 service denied

```bash
# 看 service 列表 + 各自 context
$ adb shell service list | head -10
# 格式：service_name 类型
# 但 SELinux context 要单独查：
$ adb shell cmd service_manager list | head -20

# 直接看 service_contexts 文件
$ adb shell cat /system/etc/selinux/plat_service_contexts | grep "activity"
activity          u:object_r:activity_service:s0
```

---

## 6. 4 大 Context 关系图

```
                            ┌────────────────────────┐
                            │   SELinux Policy        │
                            │   (binary policy.bin)   │
                            └──────────┬──────────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            │                          │                          │
            ▼                          ▼                          ▼
   ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
   │ task_security   │       │ inode_security  │       │ service_context │
   │ (进程 cred 里)   │       │ (文件 xattr)     │       │ (内存表)         │
   └────────┬────────┘       └────────┬────────┘       └────────┬────────┘
            │                         │                         │
   ┌────────▼────────┐      ┌─────────▼────────┐      ┌────────▼────────┐
   │ ps -eZ 输出     │      │ ls -Z / getfattr │      │ service list    │
   │ 进程 Context    │      │ 文件 Context      │      │ service Context │
   └─────────────────┘      └──────────────────┘      └─────────────────┘

   赋值来源:
   ┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
   │ exec() 时       │      │ setfiles /       │      │ property_service│
   │ 从可执行文件     │      │ restorecon /     │      │ addService 时   │
   │ label 查表      │      │ setfilecon        │      │ 查 service_ctx  │
   └─────────────────┘      └──────────────────┘      └─────────────────┘
```

### 6.1 4 大 Context 的对照

| 主体 | 存储位置 | 何时赋值 | 调试命令 |
|:-----|:--------|:---------|:--------|
| **进程** | `task_struct->cred->security`（内核内存）| `exec()` 时 | `ps -Z` / `id -Z` |
| **文件** | ext4 inode `security.selinux` xattr | `setfiles` / `restorecon` / `setfilecon` | `ls -Z` / `getfattr` |
| **property** | property_service 内存表 | `setprop` 时查 `property_contexts` | `getprop -T` |
| **service** | service_manager 内存表 | `addService` 时查 `service_contexts` | `service list` + `cmd service_manager` |

**调试铁律**：看到 denied 行的第一时间，确定是哪一类主体的 context 有问题——99% 的稳定性问题在 5 分钟内能定位到。

---

## 7. 真实调试场景：从 denied 行反推 context 出处

### 7.1 场景：app 写文件 denied

```
$ adb logcat -d | grep "avc: denied"
avc: denied { write } for name="data.txt" dev="dm-3" scontext=u:r:untrusted_app:s0:c123,c256
        tcontext=u:object_r:system_data_file:s0 tclass=file
        permissive=0
```

**反推 5 步**：
1. **scontext** `u:r:untrusted_app:s0:c123,c256` → 进程是 untrusted_app，category c123,c256
2. **tcontext** `u:object_r:system_data_file:s0` → 目标文件 type 是 system_data_file
3. **tclass** `file` → 客体是文件
4. **{write}** → 想写
5. **permissive=0** → enforcing 模式

**根因（90% 概率）**：app 写到 `/data/data/com.example.app/files/data.txt` 期望 type 是 `app_data_file`，但**实际 type 是 `system_data_file`**（因为 file_contexts 写错 / 父目录 label 不对）。

### 7.2 场景：service 启动 denied

```
avc: denied { add } for scontext=u:r:system_server:s0 tcontext=u:object_r:unlabeled:s0
        tclass=service_manager
```

**反推**：
1. **scontext** `system_server` → 发起者是 system_server
2. **tcontext** `unlabeled` → 目标服务 type 未定义（service_contexts 漏写！）
3. **tclass** `service_manager` → service_manager 操作
4. **{add}** → addService

**根因**：新加 service 忘写 service_contexts，type 落到 `unlabeled`。**5 分钟修复**：
```te
# 加到 system/sepolicy/public/service_contexts 或 device/<vendor>/<device>/sepolicy/service_contexts
my_new_service      u:object_r:my_new_service_type:s0
```

### 7.3 场景：property 设置 denied

```
avc: denied { set } for name="ro.build.fingerprint" scontext=u:r:shell:s0
        tcontext=u:object_r:fingerprint_prop:s0 tclass=property_service
```

**反推**：
1. **scontext** `shell` → 发起者是 adb shell
2. **tcontext** `fingerprint_prop` → 目标 property type
3. **tclass** `property_service` → property 操作
4. **{set}** → 写 property

**根因**：adb shell 没有 `allow shell fingerprint_prop:property_service { set }`。**修复**：
- 改用 `setprop persist.xxx` (持久化的 type 要求不同)
- 或 vendor 适配层给 shell 加 allow

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 总览](01-SELinux总览：MAC机制在Android的落地.md) | 本文 4 大 Context 串起 §2-§5 |
| [02 策略文件体系](02-策略文件体系：sepolicy.te.cil.编译产物.md) | .fc / property_contexts / service_contexts 的语法 |
| [04 AVC 与 avc_denied](04-AVC与avc_denied：从一次denied反推策略.md) | 下篇讲 denied 行怎么改 .te |
| [05 init 与 SELinux](05-init进程与SELinux：分阶段加载.md) | init 阶段怎么给关键目录打 label |
| [01-Mechanism/Framework/Service](../../01-Mechanism/Framework/Service/) | service_manager 服务注册流程 |
| [06-Foundation/Tools/Android_Tools/Logcat_Complete_Guide](../../../05-卷5-调查工具链/35-断点与%20Native%20调试/Logcat_Complete_Guide.md) | denied 行怎么从 kernel 走到 logcat |
| [04-Tool/AmCommand/01-am命令全景与Activity触发](../../../../05-卷5-调查工具链/33-Dumpsys · Bugreport · DropBox/01-am命令全景与Activity触发.md) | `am` 命令运行需要 service context |

---

## 9. 下一篇预告 + 自检

### 9.1 下一篇

[04 AVC 与 avc_denied：从一次 denied 反推策略](04-AVC与avc_denied：从一次denied反推策略.md) 讲清：
- `avc: denied` 行的 8 个字段精确解读
- 怎么从一行 denied 反推 `.te` 应该加什么
- 怎么用 `audit2allow` 安全生成最小 allow 规则
- 怎么用 `sepolicy-analyze` 验证修复
- 5 个真实 denied 案例逐行解读

### 9.2 看完本文的自检

- [ ] 能说 SELinux Context 4 段字段分别是什么、各自决策权重
- [ ] 能用 `ps -Z` / `ls -Z` / `getprop -T` / `service list` 看 4 大 context
- [ ] 能解释 4 大 context 的存储位置和赋值时机
- [ ] 能从 1 行 denied 反推是哪类主体出问题
- [ ] 知道 MCS categories 出现时表示什么

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
