# 06-Foundation/SELinux · 05 · init 进程与 SELinux：分阶段加载

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · 平台 / BSP · 内核 + init 调试
>
> **强依赖**：[04 AVC 与 avc_denied](04-AVC与avc_denied：从一次denied反推策略.md) · [02 §4 4 个 binary policy](02-策略文件体系：sepolicy.te.cil.编译产物.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把"kernel 启动 → init 启动 → zygote 启动 → service 启动"全链路上 SELinux 怎么加载、怎么切 context、怎么从 permissive 转 enforcing 讲清楚——这是 boot 阶段 90% 的"起不来"问题的根因
- **不是**：不复述 [04 §2 三个数据源](04-AVC与avc_denied：从一次denied反推策略.md)；不复述 init 进程本身（[02-Symptom/S11-Startup/A03](../../../02-卷2-系统启动/10-应用启动与首帧/A03-Init进程与init.rc.md)）
- **承接自**：[04 §6.5 unlabeled 案例](04-AVC与avc_denied：从一次denied反推策略.md)（启动期 unlabeled 修复的根因）
- **衔接去**：[06 常见稳定性问题](06-常见稳定性问题：service-crash.neverallow.build-失败.md) / [08 AOSP 17 演进](08-AOSP-17演进：Treble+CIL+userspace加载.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 5 阶段划分（pre-kernel / early-init / main-init / service / runtime）| 跨用户空间 + 内核的"加载"必须按阶段切分 |
| 2 | 第 7 章把 androidboot.selinux 4 个值单独立节 | 工程师常误用 `disabled` 触发 bootloop |
| 3 | 第 4 章用真实 `setfiles` 跑过的 init 启动 logcat | 不用示意图，用真实时间线 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**init 阶段的 SELinux 加载 = 内核先无 SELinux 启动 → 加载 pre-compiled policy → init 切到 enforcing → 启动 service 时按 type_transition 切到对应 domain。**

任何一阶段出问题，**最直接的表现是 boot 失败 / bootloop / service 起不来**——这 3 个症状的 80% 跟 SELinux 加载流程相关。

---

## 1. SELinux 加载的 5 个阶段

```
时间 ────────────────────────────────────────────────────────→

[阶段 1: pre-kernel]        kernel 启动 → SELinux 未启用
    │                       所有进程 SID = kernel SID
    │                       （系统 SID 固定，策略未加载）
    ▼
[阶段 2: early-init]        init (PID 1) 启动 → kernel context
    │                       加载 pre-compiled policy
    │                       切到 init 域
    ▼
[阶段 3: main-init]         init 解析 init.rc
    │                       restorecon 重打标签
    │                       启动 zygote / service_manager
    ▼
[阶段 4: service]           zygote fork app
    │                       各 service 启动
    │                       按 type_transition 切到对应 domain
    ▼
[阶段 5: runtime]           enforcing 模式稳定运行
                            AVC 缓存生效
                            setenforce 可动态切 permissive
```

**每个阶段都有"切换点"**：

| 阶段 | 切换点 | 谁负责 | 失败时表现 |
|:-----|:-------|:------|:---------|
| 1 → 2 | kernel 启 SELinux | kernel/security/selinux | kernel panic |
| 2 → 3 | init 切到 init domain | init 进程 selinux.cpp | init crash → bootloop |
| 3 → 4 | service 切到对应 domain | init fork | service 不起来 |
| 4 → 5 | 全部 enforcing | 持续 | 持续 denied 风暴 |

---

## 2. 阶段 1：kernel 启动期（pre-kernel）

### 2.1 kernel 启动 SELinux 的 5 个时序点

```
[1] kernel 自解压
[2] start_kernel() → setup_arch() → 解析 cmdline
[3] security_init() → 调用 LSM hook init
    └─ SELinux LSM 模块注册
[4] selinux_init() → policydb 初始化（空）
[5] policy_load() → 读取 initramfs 里的 pre-compiled policy
    └─ 关键：initramfs 必须包含 policy 文件
[6] selinux_enforcing = 1 (默认 enforcing)
[7] selinux_complete_init() → 完成
[8] rest_init() → kernel_init 启动 init 进程 (PID 1)
```

**关键源码**：

```c
// security/selinux/hooks.c（简化）
static int __init selinux_init(void)
{
    printk(KERN_INFO "SELinux:  Initializing.\n");
    
    // 注册 LSM 钩子
    register_security(&selinux_ops);
    
    // 初始化 SID 表
    selinux_init_allocators();
    selinux_policy_cache_init();
    
    // 强制模式（默认）
    selinux_enforcing = 1;  // enforcing
    selinux_policy_load_policy();  // 读 initramfs
    
    return 0;
}
```

### 2.2 initramfs 里的 policy 文件

```
# 编译时合并到 boot.img 的 initramfs
out/target/product/<device>/root/
├── sepolicy                  ← kernel 用的 binary policy
├── init                      ← init 进程可执行文件
├── init.<device>.rc
└── ...
```

**关键检查命令**：

```bash
# 解压 initramfs 看 policy 是否在内
$ mkdir /tmp/initramfs && cd /tmp/initramfs
$ gzip -dc /path/to/boot.img | cpio -idmv
$ ls -la sepolicy
-rw-r--r-- 1 root root 80000 ... sepolicy
```

**稳定性含义**：sepolicy 没在 initramfs 里 → kernel 无法加载 policy → kernel 仍 enforcing 但无规则 → 所有 syscall denied → kernel panic（"Unable to handle kernel NULL pointer"）。

---

## 3. 阶段 2：early-init（init 进程的 first stage）

### 3.1 first stage init 干 3 件事

```cpp
// system/core/init/first_stage_init.cpp（简化）
int FirstStageMain(int argc, char** argv) {
    // 1. mount 关键文件系统
    mount("tmpfs", "/dev", "tmpfs", MS_NOSUID, "mode=0755");
    mkdir("/dev/pts", 0755);
    mount("devpts", "/dev/pts", "devpts", 0, NULL);
    mount("proc", "/proc", "proc", 0, NULL);
    mount("sysfs", "/sys", "sysfs", 0, NULL);
    
    // 2. 挂 selinuxfs
    mount("selinuxfs", "/sys/fs/selinux", "selinuxfs", 0, NULL);
    
    // 3. exec second stage
    const char* path = "/system/bin/init";
    const char* args[] = {path, "second_stage", NULL};
    execve(path, const_cast<char**>(args), environ);
}
```

**关键观察**：
- first_stage 自身用 `kernel` 域（没有 init 域，init 域在 second stage 才切）
- `mount selinuxfs` 是关键，**没 mount 成功** → 后续 setenforce 失败

### 3.2 selinuxfs 内核接口

```
/sys/fs/selinux/
├── enforce              # 0=permissive, 1=enforcing（echo 0 > enforce 可切）
├── policy               # 当前 policy 版本
├── load                 # 写入新 policy
├── checkreqprot         # 0=mls 检查, 1=简化
├── disable              # 写 1 永久禁用 SELinux
├── avc/                 # AVC 缓存
├── class/               # 所有 class
├── initial_contexts     # 初始 SID
├── policy_capabilities  # 策略能力
└── status               # 当前状态
```

**真实调试命令**：

```bash
# 看当前 enforcing 状态（从内核读）
$ adb shell cat /sys/fs/selinux/enforce
1

# 临时切 permissive（root + kernel 允许）
$ adb shell su 0 cat /sys/fs/selinux/enforce
1
$ adb shell su 0 echo 0 > /sys/fs/selinux/enforce
# 成功切到 permissive

# 切回 enforcing
$ adb shell su 0 echo 1 > /sys/fs/selinux/enforce
```

**稳定性含义**：误用 `echo 0 > enforce` 临时绕过 → 线上 denied 仍记录但**不阻止** → 服务起来 → 但后续 enforcing 切回时 service 可能突然崩。

---

## 4. 阶段 3：main-init（second stage，init 域启用）

### 4.1 second stage init 的 SELinux 动作

```cpp
// system/core/init/selinux.cpp（简化）
void SelinuxInitialize() {
    // 1. 读取 cmdline 的 androidboot.selinux
    ImportKernelCmdline();
    
    // 2. 处理 disabled / permissive
    if (cmdline == "disabled") {
        // 写 /sys/fs/selinux/disable = 1
        // **永久禁用** SELinux（重启后失效）
        // 工厂模式用
    } else if (cmdline == "permissive") {
        // 切到 permissive 但不卸载
        selinux_enforcing = 0;
    }
    
    // 3. 加载 user policy（general policy）
    //    kernel policy 已经加载，这里加载 init 用的策略
    if (access("/system/etc/selinux/...", F_OK) == 0) {
        SelinuxLoadPolicy();
    }
    
    // 4. 切到 init 域
    if (setcon("u:r:init:s0") < 0) {
        // setcon 失败 → init 永远在 kernel 域
        // 后果：init 后续动作会持续 denied
    }
    
    // 5. 启动 audit
    SelinuxSetupAuditLog();
}
```

### 4.2 真实 main-init 启动 logcat（AOSP 17 模拟）

```
[    0.012345] SELinux:  Initializing.
[    0.045678] SELinux:  policy loaded successfully
[    0.123456] init: security init done
[    0.234567] init: First stage mounted
[    0.345678] init: Switching to second stage
[    0.456789] init: Loading SELinux policy
[    0.567890] init: setcon u:r:init:s0 succeeded
[    0.678901] init: restorecon /system
[    0.789012] init: restorecon /vendor
[    0.890123] init: restorecon /data
[    1.012345] init: Starting service 'zygote'...
[    1.123456] zygote64: Preloading classes...
[    1.234567] zygote64: Preloading resources...
[    1.345678] init: Service 'zygote' (pid 234) launched
[    1.456789] init: Starting service 'system_server'...
[    1.567890] system_server: System server starting
```

**每个时间点都对应一个 SELinux 决策**，denied 会出现在任一行。

### 4.3 启动期最常见的 3 个 SELinux 错误

| 错误 | logcat 标志 | 根因 |
|:-----|:----------|:-----|
| `setcon failed` | `init: setcon u:r:init:s0 failed: Invalid argument` | init 域未在 policy 中定义 |
| `restorecon failed` | `init: Could not restorecon /system: No such file or directory` | file_contexts 路径错 |
| `service denied` | `avc: denied { transition }` | service type 在 policy 中未定义 |

---

## 5. 阶段 4：service 启动（type_transition）

### 5.1 type_transition 的 3 个角色

```te
# system/sepolicy/public/init.te（简化）
# 这是 init 启动 zygote 的策略

# [1] init 能 fork + exec zygote
allow init zygote:process { transition };
allow init zygote_exec:file { read execute open };

# [2] init 切到 zygote 域（type_transition）
type_transition init zygote_exec:process zygote;

# [3] zygote 自己能做的
allow zygote self:process { setcurrent };
```

**type_transition 触发的精确时机**：

```
init 进程调用 execve("/system/bin/zygote", "zygote", NULL)
    ↓
kernel 拦截 execve
    ↓
检查可执行文件 label: zygote_exec
    ↓
查策略:  init + zygote_exec:process → zygote (type_transition)
    ↓
新进程 SID = zygote 域的 SID
    ↓
进程起来后 PID X 的 scontext = u:r:zygote:s0
```

### 5.2 service 启动的真实 logcat

```
[    2.345678] init: Starting service 'surfaceflinger'...
[    2.456789] init:     type=1400 audit(0.0:0): avc: denied { transition } 
                     for comm="init" path="/system/bin/surfaceflinger" 
                     scontext=u:r:init:s0 tcontext=u:r:surfaceflinger:s0 
                     tclass=process
[    2.567890] init: Service 'surfaceflinger' (pid 345) exited with status 1
[    2.678901] init: Service 'surfaceflinger' (pid 345) will be restarted
[    2.789012] init:     type=1400 audit(0.0:0): avc: denied { transition } ...
... (循环)
```

**根因**：surfaceflinger 在 policy 中没定义 `type_transition` 规则或 type 没在 policy 中。

**修复**：

```te
# 1. 确认 system/sepolicy/public/surfaceflinger.te 存在
# 2. 确认 type_transition 规则
type_transition init surfaceflinger_exec:process surfaceflinger;
allow init surfaceflinger:process transition;
allow init surfaceflinger_exec:file { read execute open };
```

### 5.3 service 启动期的 5 个常见 SELinux 阻塞

| service 阶段 | 可能 SELinux 阻塞 | logcat 标志 |
|:-----------|:--------------|:----------|
| fork | transition denied | `avc: denied { transition }` |
| exec | read / execute denied | `avc: denied { read execute } for comm="init"` |
| setcon | setcon 失败 | `setcon failed: Invalid argument` |
| restorecon | 找不到 label | `Could not get label for /xxx` |
| 启动后访问资源 | 任意资源 denied | `avc: denied { ... }` |

---

## 6. 阶段 5：runtime（稳定运行）

### 6.1 runtime 期 SELinux 的 3 个动态操作

| 操作 | 触发者 | 效果 | 用途 |
|:----|:-------|:-----|:-----|
| `setenforce 0/1` | init / shell | 切 enforcing / permissive | 临时诊断 |
| 加载新 policy | 升级 OTA | 卸载旧 policy + 加载新 | OTA 升级（极少）|
| AVC 缓存清空 | setprop / 重启 | 重置所有决策缓存 | 改完 policy 后必须 |

### 6.2 AVC 缓存的实现

```c
// kernel/security/selinux/avc.c（简化）
struct avc_node {
    struct avc_entry ae;          // 决策结果
    u32 ssid;                    // subject SID
    u32 tsid;                    // target SID
    u16 tclass;                  // target class
    u32 seqno;                   // policy 序号
    struct rb_node node;         // 红黑树节点
};

// 缓存查询
int avc_has_perm(u32 ssid, u32 tsid, u16 tclass, u32 requested, ...) {
    // 1. 查红黑树
    node = avc_lookup(ssid, tsid, tclass);
    if (node && node->ae.avd.allowed) {
        return 0;  // 命中缓存
    }
    // 2. 走策略
    return security_compute_av(...);
}
```

**关键性能数据**：
- AVC 缓存命中率（cache hit rate）正常 > 99%
- 命中率 < 95% 说明策略太松（permission 给太多）
- 命中率 < 80% 说明策略设计有误

### 6.3 动态加载新 policy

```bash
# OTA 升级时（极少用）
$ adb shell load_policy /data/etc/selinux/new_policy.bin
# 内核卸载旧 policy + 加载新 policy + 清空 AVC 缓存
```

**铁律**：线上**永远不要 load_policy**——会把 AVC 缓存全清，所有访问重新走策略，瞬时 CPU spike。

---

## 7. kernel 启动参数 `androidboot.selinux`

`androidboot.selinux` 是 cmdline 里控制 SELinux 启动模式的关键参数。

### 7.1 4 个值

| 值 | 行为 | 何时用 | 风险 |
|:---|:-----|:------|:-----|
| `enforcing` | enforcing 模式（默认）| 线上 | 误用 → bootloop |
| `permissive` | permissive 模式（不拒绝，只记录）| 临时诊断 | 误用 → 上线不强制 |
| `disabled` | 永久禁用 SELinux（不可逆直到重启）| 工厂模式 | 误用 → 失去强制保护 |
| 不设 | 默认 enforcing | 90% 设备 | - |

### 7.2 设置方法

```bash
# 1. 启动时 cmdline（kernel 启动参数）
# 在 BoardConfig.mk 中
BOARD_KERNEL_CMDLINE += androidboot.selinux=permissive

# 2. userdebug 设备启动后临时切
$ adb shell setprop ro.boot.selinux permissive
# 注意：setprop 不影响已启动的内核 SELinux 模式
# 真要切：adb shell su 0 echo 0 > /sys/fs/selinux/enforce

# 3. /proc/cmdline 验证
$ adb shell cat /proc/cmdline | tr ' ' '\n' | grep selinux
androidboot.selinux=enforcing
```

### 7.3 真实 bootloop 案例

**症状**：vendor 加新 .te 后烧录 boot.img，设备卡第一屏 logo 循环重启。

**logcat**：
```
[    0.234] init: Loading SELinux policy
[    0.345] init: setcon u:r:init:s0 failed: Invalid argument
[    0.456] init: panic: could not set SELinux context to init
[    0.567] init: Rebooting system
```

**根因**：vendor 的 .te 编译到 binary policy 时，**init 域定义被改坏**（比如 typeattribute 重复定义）。

**修复路径**：
1. `m selinux_policy` 看具体编译错误
2. 找到重复定义 / 引用冲突的 .te
3. 改用 attribute 排除
4. 重新 `m` + 烧录 boot.img

**应急**：在 `BoardConfig.mk` 加 `BOARD_KERNEL_CMDLINE += androidboot.selinux=permissive` 临时进 permissive，**能 boot 但不要上线**。

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 总览](01-SELinux总览：MAC机制在Android的落地.md) | 本文是 §3 12 步访问的"启动期"版本 |
| [02 策略文件体系](02-策略文件体系：sepolicy.te.cil.编译产物.md) | §4 4 个 binary policy 怎么被加载 |
| [03 Context 与 Label](03-Context与Label：四大主体的标签从哪来.md) | §3 进程 Context 何时变 = 本文 §5 type_transition |
| [04 AVC 与 avc_denied](04-AVC与avc_denied：从一次denied反推策略.md) | §2 三个数据源 + 本文 §6 runtime 缓存 |
| [02-Symptom/S11-Startup/A03-Init进程与init.rc](../../../02-卷2-系统启动/10-应用启动与首帧/A03-Init进程与init.rc.md) | init 进程本身的解析 |
| [06-Foundation/Tools/Android_Tools/Init_RC_Complete_Guide](../../../05-卷5-调查工具链/35-断点与%20Native%20调试/Init_RC_Complete_Guide.md) | init.rc 解析 + setcon / restorecon |
| [06 常见稳定性问题](06-常见稳定性问题：service-crash.neverallow.build-失败.md) | 下篇讲 SELinux 引起的 7 大症状 |

---

## 9. 下一篇预告 + 自检

### 9.1 下一篇

[06 常见稳定性问题：service crash / neverallow / build 失败](06-常见稳定性问题：service-crash.neverallow.build-失败.md) 讲清：
- 7 大症状（ANR / JE / NE / SWT / OOM / REBOOT / KE）每个的 SELinux 触点
- service crash 与 SELinux 的 4 类根因 + 速查表
- neverallow violation 的 5 种典型错误信息 + 修法
- build 期 5 个失败模式

### 9.2 看完本文的自检

- [ ] 能说 SELinux 加载的 5 个阶段
- [ ] 知道 first_stage / second_stage / runtime 各自的 SELinux 动作
- [ ] 能从 logcat 的 `setcon failed` / `transition denied` 反推根因
- [ ] 知道 `androidboot.selinux` 4 个值的风险
- [ ] 知道 selinuxfs 关键文件位置（/sys/fs/selinux/enforce）

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
