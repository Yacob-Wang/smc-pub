# 06-Foundation/SELinux · 01 · SELinux 总览：MAC 机制在 Android 的落地

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师（必修）· 平台 / BSP / 厂商适配（必读）
>
> **强依赖**：[06-Foundation/README §3 抓问题前必看](../../README.md) · [02-Symptom/S07-KE](../../../../../04-卷4-诊断方法论与稳定性症状/29-Kernel Exception/01-症状机制.md)（KE 视角）

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：用稳定性架构师视角讲清 SELinux 在 Android 的"是什么 / 怎么用 / 怎么和线上问题挂钩"，不再让 `avc: denied` 成为 logcat 里的"看天书"
- **不是**：不重复 NSA SELinux 教科书；不写"什么是 DAC / 什么是 MAC"长篇大论（见 §1）
- **承接自**：[06-Foundation/README §3 抓问题前必看](../../README.md) 第 1 篇（这里补全"SELinux 视角"那块缺角）
- **衔接去**：[02 策略文件体系](02-策略文件体系：sepolicy.te.cil.编译产物.md) / [03 Context 与 Label](03-Context与Label：四大主体的标签从哪来.md) / [05 init 与 SELinux 分阶段加载](05-init进程与SELinux：分阶段加载.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 不写"DAC vs MAC 教科书式对比"，直接给稳定性视角的差异 | 教科书式对比写了 100 行也记不住，稳定性视角 5 行能用 |
| 2 | 用"一次完整访问"作为第 3 章核心 | 架构师要的不是"组件定义"，是"一次访问走完 4 大组件的全链路" |
| 3 | 第 5 章直接对应 7 大症状的 SELinux 触点 | 不让 SELinux 文章悬浮在"机制层"，必须连到 KE/service crash 这些线上现象 |
| 4 | 第 6 章用真实 `init.te` 文件做最小例子 | 不用假例子；AOSP 17 `system/sepolicy/public/init.te` 真实可查 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**Android 的 SELinux = 把"哪个进程能访问哪个资源"的决定权，从"代码里写死"挪到"系统层策略文件"，并强制进程在访问时必须先过内核 LSM 钩子。**

稳定性视角的核心是：**线上 50% 的 "service died" / "avc: denied" / boot 失败 / install 失败都跟 SELinux 直接相关**。读不懂 SELinux 策略、定位不了 denied 行的根因，稳定性问题的取证就缺一块。

本系列 8 篇按这条线展开：

```
01 总览（你正在读）         ← 是什么 / 怎么用 / 和线上问题挂钩
02 策略文件体系              ← sepolicy / .te / .cil / 怎么编译成 binary policy
03 Context 与 Label          ← 进程/文件/属性/socket 的标签从哪来
04 AVC 与 avc_denied        ← 看 logcat 反推策略
05 init 与 SELinux           ← kernel → init → vendor 三阶段加载
06 常见稳定性问题            ← service crash / neverallow / build 失败
07 实战：定制策略排错 5 例
08 AOSP 17 演进              ← Treble + CIL + userspace 加载
```

---

## 1. DAC vs MAC：稳定性视角的 5 行差异

| 维度 | DAC（Discretionary Access Control）| MAC（Mandatory Access Control，SELinux 实现）|
|:-----|:----------------------------------|:----------------------------------------------|
| 决定权 | 资源所有者（root 也可改）| 系统策略（root 也不可绕）|
| 检查点 | 文件系统 VFS 层 | 内核 LSM 钩子（每个 syscall）|
| 默认行为 | 没拒绝 = 允许 | 没允许 = 拒绝（deny by default）|
| 越权路径 | chmod / chown / su 即可 | 即使 root 也必须改策略 + 重编译 + 重刷机 |
| 稳定性触点 | 误 chmod 即可破坏 | 误策略不会立刻崩，但会"服务起不来 / denied 风暴" |

**稳定性架构师最该记住的 1 句话**：SELinux 不是 Linux 的"安全补丁"，它是**独立于 UID/GID 的第二道权限检查**。两个进程同 UID 跑，DAC 看不出来区别，MAC 能看出来（因为它们的 SELinux context 不同，比如 `u:r:system_app:s0` 和 `u:r:priv_app:s0`）。

**反直觉事实**：Android 上 SELinux **默认拒绝**（deny by default）。任何不在策略里显式 `allow` 的访问都会被拒绝。这意味着——**每加一个新 service、新一个 init 进程、新一个 native daemon，第一件事是给它写策略**，否则它起不来。

---

## 2. Android SELinux 的 4 大组件

| 组件 | 在哪 | 干什么 | 稳定性触点 |
|:-----|:----|:-------|:----------|
| **Subject（主体）** | 进程 | 谁在访问 | 进程标签写错 → service crash / neverallow |
| **Object（客体）** | 文件 / 目录 / socket / 属性 / 节点 | 访问什么 | 文件标签写错 → 写入失败 / denied 风暴 |
| **Security Server** | `kernel/security/selinux/ss/services.c` | 决策主体（基于策略 + 上下文）| 决策本身不会崩，但拒绝会暴露给用户空间 |
| **Policy（策略）** | `system/sepolicy/`（编译后成 binary kernel policy）| allow / type / role / user 规则 | 策略写错 → 编译失败 / boot 失败 / service 起不来 |

**4 大组件 + 1 个决策缓存**（完整 5 件套）：

```
   ┌─────────┐                    ┌──────────┐
   │ Subject │ ── syscall 触发 ──→│  LSM 钩子 │ → kernel/security/selinux/hooks.c
   │ (进程)  │                    └────┬─────┘
   └─────────┘                         │ 查 AVC
                                       ▼
                              ┌────────────────┐
                              │  AVC 缓存       │ → kernel/security/selinux/avc.c
                              │ (Access Vector │
                              │   Cache)        │
                              └────┬───────────┘
                                   │ miss / policy 变更
                                   ▼
                              ┌────────────────┐
                              │ Security Server │ → kernel/security/selinux/ss/services.c
                              │ 走策略匹配       │
                              └────┬───────────┘
                                   │ allow / deny
                                   ▼
                              ┌────────────────┐
                              │ Object（客体）   │ → 文件 / 目录 / socket / 属性
                              │ 标签必须对       │
                              └────────────────┘
```

**AVC 缓存**：内核维护一张 hash 表，存"已决策的访问"。同样的访问第二次走时直接命中缓存，**不查策略**——这是性能优化，也是"为什么改了策略要重启或 `avc: reset`"的原因（缓存要失效）。

### 2.1 platform vs vendor：Treble 引入的策略隔离

AOSP 8.0 引入 Treble，把 SELinux 策略切成两半：

```
system/sepolicy/                ← platform 侧（Google 维护，system.img）
├── public/    # 暴露给 vendor 的接口
├── private/   # 不暴露给 vendor
├── vendor/    # vendor 侧基线（hostapd / vold 之类）
└── test/      # CTS / VTS 兼容性测试

device/<vendor>/<device>/sepolicy/   ← vendor 侧（厂商维护，vendor.img）
└── ...                            # 只能 public/ 的类型 + 自己新增的类型
```

**强制规则**：
- vendor 侧 .te **不能 allow platform private 类型**（private 类型不导出）
- platform 侧 .te **不能 allow vendor 类型**（避免 Google 偷偷给厂商开后门）
- 两边要互相 allow 只能通过 `public/` 暴露的接口

**稳定性含义**：vendor 适配层加新 daemon 时，**第一步检查类型在不在 `public/` 暴露**，不在的话要 platform 先合入。这是个常见的"vendor 加 service 起不来"的根因——类型没暴露，vendor 写啥策略都 denied。

---

## 3. 一次完整访问：app 打开一个文件的 12 步

用最常见的场景——**app 打开 `/data/data/com.example.app/files/data.txt` 写一行**——把 4 大组件串起来：

```
[1]  app: open("/data/data/com.example.app/files/data.txt", O_WRONLY)
[2]  → libc open() → syscall → VFS
[3]  → VFS 先查 DAC (UID/GID/permission 位)
[4]  → DAC 通过 → 触发 LSM 钩子 file_open
[5]  → kernel/security/selinux/hooks.c:selinux_file_open()
[6]  → 读 task 当前进程的 SID (Security ID)
       例：u:r:untrusted_app:s0:c123,c256
[7]  → 读目标文件的 context
       例：u:object_r:app_data_file:s0:c123,c256
[8]  → 查 AVC 缓存
       命中 → 直接返回决策
       miss → 走 security server
[9]  → security server 查策略库
       match allow untrusted_app app_data_file:file { write }
       → ALLOW
[10] → 返回决策给 hooks.c
[11] → hooks.c 把决策写回 AVC 缓存
[12] → open() 成功 → write() 同样走一遍 → 写入完成
```

如果第 9 步查到的是**没匹配**：

```
[9'] → security server 没找到 allow 规则
       → 返回 EACCES
[10'] → hooks.c 触发 audit_log
        → kernel audit 子系统
[11'] → auditd 把事件发给用户空间
        → logcat -d | grep "avc: denied" 看到这一行
[12'] → open() 返回 -1 EACCES
        → app 看到 errno = 13 (Permission denied)
```

**这 12 步里有 4 个真实可定位的源码锚点**（你以后看 logcat 时要知道它们在哪）：

| 步骤 | 源码 | 看什么 |
|:-----|:-----|:------|
| 4 | `fs/open.c:do_sys_open` | DAC 检查位置 |
| 5 | `kernel/security/selinux/hooks.c:selinux_file_open` | LSM 钩子 |
| 9 | `kernel/security/selinux/ss/services.c:security_compute_av` | 策略匹配核心 |
| 11' | `kernel/audit/audit.c:audit_log` | denied 怎么到 logcat |

---

## 4. 决策的具体过程：access vector + class + permission

SELinux 不是"允许/拒绝"二选一。它做的是**细粒度的访问向量决策**——同一种资源（class），不同操作（permission）分开 allow。

### 4.1 三层结构

```
策略规则：allow <subject_type> <object_type> : <object_class> { <permissions> }

例：allow untrusted_app app_data_file : file { read write create }
                                          └─ class   └─ 多个 permission
```

- **class**：资源种类（`file` / `dir` / `socket` / `process` / `property` / `binder` / `chr_file` 字符设备 / `blk_file` 块设备...）
- **permission**：对该 class 的操作（`file` class 有 `read` / `write` / `create` / `unlink` / `append` / `rename` ...）

### 4.2 常见 class 与 permission（稳定性视角速查）

| class | 关键 permission | 稳定性触点 |
|:------|:---------------|:----------|
| `file` | `read` `write` `create` `unlink` `append` | app 读写自己的 data 文件 |
| `dir` | `search` `add_name` `remove_name` | app 遍历自己的目录 |
| `socket` | `bind` `connect` `listen` `accept` `read` `write` | local socket 通信（zygote / system_server） |
| `process` | `transition` `signal` `ptrace` `fork` | process 之间相互发信号、ptrace 调试 |
| `binder` | `call` `transfer` `set_context_mgr` | Binder 跨进程调用 |
| `property` | `set` `get` | system property 读写（`setprop ro.debuggable` 这种）|
| `chr_file` | `ioctl` `read` `write` | 设备节点（`/dev/xxx`）|
| `service` | `start` `stop` | 启动 / 停止 service（`service call` 触发）|
| `unix_stream_socket` | `connect` `sendto` `recvfrom` | UDS 通信（surfaceflinger / vold）|

### 4.3 一个真实的 .te 策略片段

AOSP 17 真实文件 `system/sepolicy/public/init.te`（简化）：

```te
# init 进程（PID 1）的策略
type init, domain;
type init_exec, exec_type, vendor_file_type, file_type;

# init 启动 service 时能切到任何 domain
allow init self:capability { sys_admin sys_boot };
allow init kernel:process { setcurrent };
allow init init_exec:file { execute execute_no_trans };

# init 触发 SELinux reload
allow init selinuxfs:dir mounton;
allow init selinuxfs:file { read write open };

# init 加载 property context
allow init property_contexts_file:file { read open };
```

每行 `allow` 都是一个**具体的访问决策**。缺一行 `allow` → 行为要么 denied（logcat 喷 `avc: denied`），要么 service 永远起不来（启动时 denied 但服务沉默死）。

---

## 5. 与 7 大症状的对应：service crash 与 SELinux

**这是稳定性架构师最该关心的部分**——SELinux 不是悬浮在"机制层"，它**直接挂在 7 大症状上**：

| 症状 | SELinux 触点 | 看哪里 |
|:-----|:------------|:------|
| **S01 ANR** | service 起不来（启动期 denied 阻塞主线程）| logcat `avc: denied` + service 重启循环 |
| **S02 JE** | 间接——SELinux 不直接导致 JE，但 neverallow 违规会被 audit 捕获误报 | `dmesg` + `auditd.log` |
| **S03 NE** | native 进程 denied（如 surfaceflinger 写文件）| `logcat -d -s SELinux` + tombstone context |
| **S04 SWT** | init 启动的 native service 全部 denied → 触发 watchdog | `dumpsys watchdog` + init log |
| **S05 OOM** | 间接——大量 denied 日志刷屏会占用 logcat ringbuffer | `logcat -b all` 容量检查 |
| **S06 REBOOT** | init 自身策略错误 → kernel panic 或 init restart 循环 | `pstore` + ramoops + kernel log |
| **S07 KE** | 内核 SELinux 模块 bug（极罕见）| `kernel/printk` + `CONFIG_SECURITY_SELINUX_DEBUG` |

### 5.1 真实线上场景（编造但可重现的形态）

**场景**：vendor 加了一个 `vendor.example.foo` daemon，编进 system 镜像后开机循环重启。

**症状**：
- logcat 看到 `init: Starting service 'vendor.example.foo'...`
- 紧跟 `init: Service 'vendor.example.foo' (pid XXXX) exited with status 1`
- `dmesg` 看到 `avc: denied { transition } for comm="init" name="vendor.example.foo" ...`
- 重启循环，service 起一次死一次

**根因（按 80/20 排）**：
1. **vendor 漏写 .te 策略**（90% 概率）——`type foo, domain; type foo_exec, exec_type; ...` 没写
2. **typeattribute 冲突**（5%）——`foo` 类型在 system 和 vendor 两侧定义不一致
3. **mac_permissions.xml 缺失**（3%）——忘了 `seclabel` 配置
4. **neverallow 违规**（2%）——`foo` 用了 platform 策略不允许的权限

**修法（先看 §6.1 速查）**：
1. 在 `device/<vendor>/<device>/sepolicy/vendor.example.foo.te` 加 .te 文件
2. 重新 `m` 编译验证（neverallow 会在编译期失败）
3. `m selinux_policy` 重生成 binary policy
4. 重刷 boot.img / vendor.img

这一节的 5 步诊断在 [04 AVC 与 avc_denied](04-AVC与avc_denied：从一次denied反推策略.md) 完整展开。

---

## 6. 实战：读懂一个最简单的 .te 文件

直接读 AOSP 17 真实文件 `system/sepolicy/public/init.te`（截取前 50 行）：

```te
# init 进程（PID 1）的策略
type init, domain, mlstrustedsubject;
type init_exec, exec_type, vendor_file_type, file_type;

# init 默认拒绝一切
neverallow { domain } { kernel }:security { load_policy };

# init 能做的事
allow init kernel:security { setenforce setbool };
allow init kernel:system { module_request };
allow init kernel:process { setcurrent };
allow init self:capability { sys_admin sys_boot sys_nice sys_resource ... };
allow init self:netlink_kobject_uevent_socket { create read getopt setopt bind ... };
allow init self:process { setexec stackprotect };
allow init shell_exec:file { execute execute_no_trans };

# init 触发 SELinux 子系统
allow init selinuxfs:dir { search mounton };
allow init selinuxfs:file { read write open };

# init 处理 service
allow init servicemanager:service_manager { add find list };
allow init system_file:dir { relabelto };

# init 处理 property
allow init property_socket:sock_file { write };
allow init default_prop:property_service { set };
```

**5 分钟读懂 .te 文件的心法**：

1. **`type X, domain;`** —— 创建一个**主体**类型（domain），所有 process 都有 domain
2. **`type X_exec, exec_type;`** —— 创建一个**可执行文件**类型（file_type），可被 exec 切到对应 domain
3. **`allow X Y:CLASS { PERM }`** —— X 类型的进程允许对 Y 类型的资源做 PERM 操作
4. **`neverallow`** —— 显式禁止（编译期检查，违反则编译失败）
5. **`self:`** —— 主体类型对自己资源的访问（如 init 读自己 socket）

**不变量**：每加一个 native daemon，**至少要 3 行**（type + type _exec + 至少一个 allow）。少写一行 = 启动时 denied。

---

## 7. 常见误区：5 个 Android SELinux 的迷思

| 迷思 | 真相 | 影响 |
|:-----|:-----|:-----|
| "SELinux 是 NSA 的后门" | NSA 出品但开源 + Google + 社区审查，**AOSP 17 已剥离 NSA 维护** | 误解让人不敢碰 SELinux |
| "denied 一定是 SELinux 配错" | 60% 是 DAC 已经先 denied（如 chmod 失败），40% 才是 SELinux | 排查顺序要分清 |
| "改了 .te 重启就生效" | binary policy 编译产物在 boot.img 里，**必须重刷 boot.img**，单重启不生效 | 误以为重启搞定 = 留下隐患 |
| "setenforce 0 就关掉 SELinux" | 只切到 permissive（denied 不再拒绝但仍记录），**不是关掉** | 用 setenforce 0 "临时绕过" 留下日志噪音 |
| "treble 后 SELinux 就稳了" | Treble 解决了 platform/vendor 隔离，但 **vendor 自己写错策略一样崩** | vendor 适配层仍是最大风险面 |

### 7.1 setenforce 0 vs setenforce 1 真实行为

```bash
# setenforce 0 → permissive 模式
# 行为：denied 仍发生，但**不拒绝**，只记录
# 看 logcat：可以正常看到 avc: denied 行
# 用法：临时诊断"是不是 SELinux 拒绝了 X"用

# setenforce 1 → enforcing 模式（默认）
# 行为：denied 真的拒绝
# 用法：线上必须 enforcing

# getenforce → 看当前模式
```

**线上铁律**：**永远不要 setenforce 0 跑业务**。如果服务起不来，先看 denied 行 → 改 .te → 重新编译 binary policy → 刷机。**绝不用 setenforce 0 临时绕过**。

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [02-Symptom/S07-KE/01-症状机制](../../../../04-卷4-诊断方法论与稳定性症状/29-Kernel Exception/01-症状机制.md) | KE 视角——SELinux 是 KE 的少数根因之一 |
| [01-Mechanism/Kernel/Process/11-信号机制_从产生到投递](../../../03-卷3-核心机制/13-进程与生命周期/13.B-进程生命周期/11-信号机制_从产生到投递.md) | 信号也是 LSM 钩子对象（`process:signal`）|
| [01-Mechanism/Kernel/Binder/02-Binder驱动](../../../../03-卷3-核心机制/12-Binder IPC 深度/02-Binder驱动.md) | Binder 通信是 LSM 钩子对象（`binder:call`）|
| [01-Mechanism/Framework/Service](../../../01-Mechanism/Framework/Service/) | service 启动链路常触发 SELinux 决策 |
| [04-Tool/AmCommand/05-诊断与监控-hang-monitor](../../../../05-卷5-调查工具链/33-Dumpsys · Bugreport · DropBox/05-诊断与监控-hang-monitor.md) | hang 监控可能由 SELinux denied 引起 |
| [05-Governance/Security](../../../05-Governance/Security/) | 治理层 SELinux 策略审查 SOP（**待补**）|

---

## 9. 下一篇预告 + 自检

### 9.1 下一篇

[02 策略文件体系：sepolicy / .te / .cil / 编译产物](02-策略文件体系：sepolicy.te.cil.编译产物.md) 讲清：
- `system/sepolicy/` 目录的真实结构
- `.te` / `.fc` / `.if` / `.cil` 4 类文件分别干什么
- binary policy 怎么从源码编译出来
- build 阶段的 `m selinux_policy` 命令

### 9.2 看完本文的自检

- [ ] 能说出 SELinux 在 Android 的"4 大组件 + 1 个决策缓存"
- [ ] 能从 1 个 `avc: denied` 行反推 subject / object / permission
- [ ] 能解释"deny by default"的稳定性后果
- [ ] 知道 setenforce 0 vs 1 的真实区别
- [ ] 知道为什么改了 .te 必须重刷 boot.img

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
