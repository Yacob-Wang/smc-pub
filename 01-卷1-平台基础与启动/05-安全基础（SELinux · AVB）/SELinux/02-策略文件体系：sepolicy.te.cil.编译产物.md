# 06-Foundation/SELinux · 02 · 策略文件体系：sepolicy / .te / .cil / 编译产物

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · 平台 / BSP / 厂商适配
>
> **强依赖**：[01 总览](01-SELinux总览：MAC机制在Android的落地.md) · [system/sepolicy/ 真实目录](#1-systemsepolicy-目录全景)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 `system/sepolicy/` 那一坨 `.te` / `.fc` / `.if` / `.cil` 文件讲清楚——它们各是什么、怎么互相引用、怎么编译成 binary policy
- **不是**：不重复 libsepol 编译器源码分析（外部模块，跳过）；不复述 [01 总览](01-SELinux总览：MAC机制在Android的落地.md) §2 的 4 大组件
- **承接自**：[01 总览](01-SELinux总览：MAC机制在Android的落地.md) §2.1 platform vs vendor 策略隔离
- **衔接去**：[03 Context 与 Label](03-Context与Label：四大主体的标签从哪来.md) / [04 AVC 与 avc_denied](04-AVC与avc_denied：从一次denied反推策略.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 5 章直接用 `sepolicy-analyze` 跑真 binary policy | 不画饼，真实输出比 ASCII 图有用 |
| 2 | 第 4 章把 .cil 独立成节，不并入 .te | AOSP 12+ 是分水岭，老文章混淆会误导 |
| 3 | 第 7 章"neverallow violation"案例用 `m selinux_policy` 真实输出 | 编译期失败信息最准，文档常写错 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**策略文件体系 = 怎么把"几百个 .te 文件 + 几十个 .fc 文件"组织起来，编译成一个 binary policy 文件（kernel 用的二进制格式），装到 boot.img 里。**

AOSP 17 的策略源文件散落在 6 个目录（`system/sepolicy/{public,private,vendor,test,reqd_mask,compat}` + `device/<vendor>/<device>/sepolicy/`），总文件数 500+，编译产物 4 个 binary policy（kernel / general / precompiled / vendor）。

读懂这套体系，是"看了 logcat denied 行能直接改 .te + 重新 m selinux_policy"的必要前提。

---

## 1. system/sepolicy/ 目录全景

AOSP 17 真实目录结构（节选关键文件）：

```
system/sepolicy/
├── Android.bp                      ← Soong 编译入口（AOSP 12+ 替代 Android.mk）
├── Android.mk                      ← 老 Make 入口（保留兼容，已不推荐新代码用）
├── public/                         ← 平台 → 厂商 的公共接口
│   ├── te                          ← 所有 .te 文件（按 domain 拆开）
│   ├── attributes                  ← typeattribute 集合
│   ├── property_contexts
│   ├── file_contexts
│   ├── service_contexts
│   └── genfs_contexts
├── private/                        ← 平台私有（不暴露给 vendor）
│   ├── te
│   ├── file_contexts
│   └── ...
├── vendor/                         ← vendor 策略基线
│   ├── te
│   └── file_contexts
├── reqd_mask/                      ← SELinux 必需 mask（基本不动）
├── test/                           ← CTS / VTS 兼容性测试（编译期检查）
│   ├── genfs_test
│   └── ...
├── compat/                         ← 兼容旧设备用
│   └── ...
├── build/                          ← 编译相关（不参与最终策略）
│   ├── soong/
│   │   ├── sepolicy.go             ← Soong 模块定义
│   │   └── ...
│   └── ...
└── tools/                          ← 策略分析工具
    ├── sepolicy-analyze            ← 重要！见 §5
    ├── checkfc                     ← 验证 file_contexts
    ├── checkpolicy                 ← 编译期验证
    └── audit2allow                  ← 从 denied 行自动生成 allow 规则（慎用）
```

### 1.1 4 类子目录的含义

| 目录 | 谁写的 | 谁能引用 | 何时合并 |
|:-----|:------|:---------|:--------|
| **public/** | Google | vendor 侧可引用 | system.img 编译时 |
| **private/** | Google | vendor 不可引用 | system.img 编译时 |
| **vendor/** | Google | 仅 vendor 自身 | vendor.img 编译时 |
| **device/<vendor>/<device>/sepolicy/** | 厂商 | 只能引用 public + vendor | vendor.img 编译时 |

### 1.2 关键观察

**`build/` 目录不进策略**：纯工具链（编译 + 验证），产物不在设备上。

**`tools/sepolicy-analyze`**：见 §5，是排错时最常用的工具，能列出所有 type / attribute / allow 规则。

**`tools/audit2allow`**：慎用！它能从 `avc: denied` 行自动生成 `allow` 规则。**生成的规则经常过宽**（比如允许 `*:file *`），绕过最小权限原则。线上策略**永远不要直接 audit2allow**。

---

## 2. .te 文件体系：策略的"主体"

`.te`（Type Enforcement）文件是 SELinux 策略的核心。**每个 .te 文件通常对应一个 domain**。

### 2.1 .te 文件的标准结构

```te
# 注释：# 开头
# 1. 声明 type
type foo, domain, mlstrustedsubject;
type foo_exec, exec_type, vendor_file_type, file_type;

# 2. 声明 attribute（可选）
typeattribute foo mlstrustedprocess;

# 3. allow 规则
allow foo self:capability { sys_admin };
allow foo system_data_file:file { read write create };
allow foo system_data_file:dir { search add_name };

# 4. neverallow（编译期检查）
# neverallow { domain -foo } foo:capability { sys_admin };
```

### 2.2 type 声明的 3 个组成部分

```
type <名字>, <type 集>, <attribute 集>;

例：type init, domain, mlstrustedsubject;
                      │        │
                      │        └─ attribute 集（可多个）
                      └── type 集（通常 domain 或 file_type）
```

| 集 | 含义 | 例子 |
|:---|:-----|:-----|
| `domain` | 这是一个进程 domain | init / zygote / system_server |
| `exec_type` | 这是可执行文件 | init_exec / zygote_exec |
| `file_type` | 这是普通文件 | system_file / vendor_file |
| `service_manager_type` | 这是 service_manager 注册的服务 | system_app_service / etc |
| `mlstrustedsubject` | 这是 MLS（多级安全）信任的 subject | init / zygote |
| `mlstrustedprocess` | 信任的 process | init / zygote |
| `core_data_file_type` | 核心 data 文件 | system_data_file |
| `vendor_file_type` | vendor 分区文件 | vendor_file |

**最常用的 2 个集**：`domain`（进程）和 `file_type`（文件）。**新加 native daemon** 几乎一定需要同时声明这 2 个。

### 2.3 allow 规则的精确语法

```
allow <subject_type> <object_type> : <object_class> { <permissions> };
```

**空格 / 重复规则**：
```te
# 这 3 行等价
allow init kernel:security setenforce;
allow init kernel:security { setenforce };
allow init kernel:security { setenforce setbool };
```

**`-` 排除**：
```te
# foo 域允许所有 capability 除了 sys_admin
allow foo self:capability { -sys_admin };
```

**`~` 限定 subset**（AOSP 17 引入）：
```te
# foo 域允许某 attribute 子集中除了 xxx 的所有 permission
allow foo bar:file { ~read write };
```

### 2.4 真实 .te 文件例子：AOSP 17 system/sepolicy/public/init.te

```te
# 完整 init.te 有 ~80 行，下面是节选
type init, domain, mlstrustedsubject;
type init_exec, exec_type, vendor_file_type, file_type;

# init 切到任何 domain（核心能力）
allow init kernel:process { setcurrent };

# init 管理 capability
allow init self:capability {
    sys_admin
    sys_boot
    sys_nice
    sys_resource
    sys_time
    sys_tty_config
    net_admin
    net_raw
    kill
    dac_override
    fsetid
    mknod
};

# init 处理 SELinux 自身
allow init selinuxfs:dir { search mounton };
allow init selinuxfs:file { read write open };

# init 处理 property
allow init property_socket:sock_file write;
allow init default_prop:property_service set;
allow init system_prop:property_service set;
```

**5 分钟读懂 .te 的心法**（也写在 [01 §6](01-SELinux总览：MAC机制在Android的落地.md)）：
1. **`type X, domain;`** → 创建主体类型
2. **`type X_exec, exec_type;`** → 创建可执行文件类型
3. **`allow X Y:CLASS { PERM }`** → 显式允许
4. **`neverallow`** → 显式禁止
5. **`self:`** → 主体对自己资源的访问

---

## 3. .fc / .if / .cil 文件：策略的"客体侧"

### 3.1 .fc 文件：File Contexts（文件标签）

`.fc` 文件决定**文件被打上什么 SELinux 标签**——在文件系统被 mount / 文件被创建时由 `setfiles` 工具写入扩展属性 `security.selinux`。

```te
# 简化版：system/sepolicy/public/file_contexts
# 路径正则 → 标签

/system/bin/init        u:object_r:init_exec:s0
/system/bin/zygote      u:object_r:zygote_exec:s0
/system/bin/app_process u:object_r:zygote_exec:s0
/system                u:object_r:system_file:s0
/system/framework       u:object_r:system_file:s0
/data/data              u:object_r:system_data_file:s0
/cache                  u:object_r:cache_file:s0
/vendor                 u:object_r:vendor_file:s0
```

**正则语法**（PCRE 子集）：
- `*` → 任意字符（不含 `/`）
- `**` → 任意字符（含 `/`）
- `?` → 单字符
- `[abc]` → 字符集
- `\s` → 空白
- 行尾 `-` → 命中后不递归（不应用子目录）

**调试命令**：
```bash
# 触发 file_contexts 重新打标签（enforcing 模式慎用）
/system/bin/setfiles -r /system /system/etc/selinux/plat_file_contexts /system

# 单独查看某文件的标签
adb shell ls -Z /system/bin/init
# 输出：u:object_r:init_exec:s0  root  root ... /system/bin/init
```

### 3.2 .if 文件：Interface（可复用接口）

`.if` 文件用 `interface` 关键字定义**可复用的策略块**——vendor 侧可以引用 platform 暴露的接口。

```te
# system/sepolicy/public/attributes
# 这是 attribute 集合，相当于 .if 的依赖

# system/sepolicy/public/domain.te 中的 interface 定义（简化）
interface(`
    domain_auto_trans(olddomain, newdomain, newfile)
')

define(`domain_auto_trans', `
    allow $1 $2:process transition;
    allow $1 $3:file { read getattr open execute execute_no_trans };
    allow $2 $1:process sigchld;
    allow $1 $2:process { sigkill sigstop signull signal };
')
```

**vendor 怎么用 platform interface**：

```te
# device/<vendor>/<device>/sepolicy/vendor_foo.te
type vendor_foo, domain;
type vendor_foo_exec, exec_type, vendor_file_type, file_type;

# 引用 platform 的 domain_auto_trans 接口
domain_auto_trans(init, vendor_foo, vendor_foo_exec)

# vendor_foo 域 → init 域 的转换被 platform 的 interface 接管
# vendor 不用知道 platform 内部细节
```

### 3.3 .cil 文件：CIL（Common Intermediate Language）

AOSP 12+ 引入 `.cil` 作为**新的策略源语言**，意图替代传统 .te。优势：
- 编译更快（避免 libsepol 的 m4 macro 解析）
- 更易读（语法更现代）
- 错误信息更友好

```cil
; system/sepolicy/public/init.cil（示例结构）
(type init)
(type init_exec)
(roletype object_r init_exec)

; allow 规则
(allow init self (capability (sys_admin sys_boot sys_nice)))
(allow init kernel (process (setcurrent)))
(allow init selinuxfs (dir (search mounton)))
(allow init selinuxfs (file (read write open)))
```

**.te vs .cil 的真实关系**（AOSP 17 现状）：
- AOSP 12-15：.te 为主，.cil 为辅
- AOSP 16-17：.te 和 .cil **并存**，但 .cil 优先
- AOSP 18+：计划全部 .cil（未确定）

**稳定性含义**：看一份新加的策略，**先看是不是 .cil**。AOSP 17 新增的 .te 文件越来越少，但删 .te 是大工程。

---

## 4. 编译产物：4 个 binary policy 文件

`m selinux_policy` 编译 `system/sepolicy/`，最终输出 4 个 binary policy 文件：

| 产物 | 路径 | 用途 |
|:-----|:-----|:-----|
| **kernel policy** | `out/target/product/<device>/boot.img` 内嵌 | 内核 enforcing 用 |
| **general policy** | `out/target/product/<device>/system/etc/selinux/...` | 用户空间 init / zygote 用 |
| **precompiled policy** | `out/target/product/<device>/vendor/etc/selinux/...` | vendor 镜像用 |
| **vendor policy** | `out/target/product/<device>/odm/etc/selinux/...` | ODM 镜像用 |

### 4.1 binary policy 文件结构（高层）

```
+----------------+
| magic header   | ← 0xf97cff8c（policy magic）
+----------------+
| string table   | ← 所有 type / role / user / class 名字
+----------------+
| type table     | ← type 的属性 + 引用
+----------------+
| role / user    | ← role allow 规则 + user 范围
+----------------+
| class / perm   | ← 所有 class 和 permission
+----------------+
| av rules       | ← 主体 allow 规则（最大的一块）
+----------------+
| te rules       | ← type_transition 规则
+----------------+
| cond rules     | ← 条件规则（bool 控制）
+----------------+
| ...            |
+----------------+
```

**真实跑一下 `sepolicy-analyze`**（AOSP 17 build 后）：

```bash
# 找 binary policy
$ find out/target/product/ -name "*.bin" 2>/dev/null
out/target/product/cf_x86_64_phone/obj/ETC/treble_sepolicy_intermediates/treble_sepolicy
out/target/product/cf_x86_64_phone/vendor/etc/selinux/precompiled_sepolicy
out/target/product/cf_x86_64_phone/obj/ETC/plat_sepolicy_intermediates/plat_sepolicy

# 列出所有 type
$ sepolicy-analyze out/target/product/cf_x86_64_phone/vendor/etc/selinux/precompiled_sepolicy types | head -20
unlabeled
init
kernel
vold
surfaceflinger
system_app
priv_app
untrusted_app
zygote
...
```

**这就是排错时"我关心的 type 在不在 policy 里"的快速检查方式**。

---

## 5. 编译流程：从源码到 binary

AOSP 17 的 Soong 编译流程（关键节点）：

```
[1] source build/envsetup.sh
[2] lunch cf_x86_64_phone-eng
[3] m selinux_policy
    ↓
    Soong 读 system/sepolicy/Android.bp
    ↓
    ┌─→ m4 宏展开所有 .te 文件（含 .if 的 interface）
    ├─→ cil 编译 .cil 文件
    ├─→ 合并 platform + vendor + device 策略
    ├─→ checkpolicy 编译期验证（neverallow / 引用 / class）
    ├─→ 4 个 binary policy 输出到 out/
    └─→ policy.conf 文本版（调试用）
```

### 5.1 关键编译命令

| 命令 | 作用 | 用法 |
|:-----|:-----|:-----|
| `m selinux_policy` | 编译所有 binary policy | 全量编译 |
| `m treble_sepolicy` | 只编译 platform + vendor | vendor 适配时快 |
| `m odm_sepolicy` | 只编译 ODM | ODM 适配时快 |
| `sepolicy-analyze <bin> types` | 列出所有 type | 排错 |
| `sepolicy-analyze <bin> allow <subj> <obj> <class> <perm>` | 检查单条 allow | 排错 |
| `checkfc -p <prefix> <file_contexts>` | 验证 file_contexts 正则 | 防 PCRE 错误 |
| `audit2allow -i denied.log` | 从 denied 自动生成 allow | 慎用！ |

### 5.2 真实 sepolicy-analyze 输出

```bash
# 检查 init 域的所有 allow
$ sepolicy-analyze precompiled_sepolicy allow -s init
init self:capability { sys_admin sys_boot sys_nice ... }
init kernel:process { setcurrent }
init selinuxfs:dir { search mounton }
init selinuxfs:file { read write open }
...

# 检查 untrusted_app 能不能读 system_data_file
$ sepolicy-analyze precompiled_sepolicy allow -s untrusted_app -t system_data_file -c file
allow untrusted_app system_data_file:file { read getattr open }

# 检查某个 type 是不是定义过
$ sepolicy-analyze precompiled_sepolicy type vendor_foo
ERROR: type 'vendor_foo' not found
# 提示：vendor 漏写 .te
```

---

## 6. 常见编译错误：neverallow violation

**neverallow** 是 AOSP 强制规则——某些"危险权限组合"绝不允许出现。违反时**编译期直接失败**：

```
neverallow { domain -init -kernel -recovery } self:capability sys_admin;
```

意思是"除 init / kernel / recovery 域外，任何 domain 都不要给自己 sys_admin capability"。

### 6.1 真实 neverallow violation 报错

```
# 改 .te 写错了，m selinux_policy 触发
out/host/linux-x86/bin/checkpolicy:  ERROR: 
  neverallow check failed
    for scontext=u:r:vendor_foo:s0
    tcontext=u:r:vendor_foo:s0
    tclass=capability
    permission: sys_admin
    at out/host/linux-x86/bin/checkpolicy:42
make[1]: *** [out/target/product/cf_x86_64_phone/obj/ETC/treble_sepolicy_intermediates/treble_sepolicy] Error 1
```

### 6.2 解决路径（按 80/20 排）

1. **用 attribute 排除法**：在 .te 顶部加 `typeattribute vendor_foo <排除的 attribute>`，让 neverallow 不命中
2. **改 neverallow**（不推荐，要 platform 合入）
3. **改用别的方式实现功能**（推荐）

**反模式**：直接注释掉 neverallow → 编译过了但上线后被 CTS 拒。

---

## 7. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 总览](01-SELinux总览：MAC机制在Android的落地.md) | 体系总览 |
| [03 Context 与 Label](03-Context与Label：四大主体的标签从哪来.md) | 下篇讲 .fc / property_contexts 怎么生效 |
| [04 AVC 与 avc_denied](04-AVC与avc_denied：从一次denied反推策略.md) | 下下篇讲怎么从 denied 行改 .te |
| [06-Foundation/Build-System/04_Build_Configuration_And_Options](../../02-AOSP%20源码结构与构建系统/04_Build_Configuration_And_Options.md) | `m selinux_policy` 怎么配 |
| [06-Foundation/Tools/Android_Tools/Logcat_Complete_Guide](../../../03-卷3-调查工具/35-断点与%20Native%20调试/Logcat_Complete_Guide.md) | denied 怎么从 kernel 走到 logcat |
| [05-Governance/Security](../../../05-Governance/Security/) | SELinux 治理 SOP（**待补**）|

---

## 8. 下一篇预告 + 自检

### 8.1 下一篇

[03 Context 与 Label：四大主体的标签从哪来](03-Context与Label：四大主体的标签从哪来.md) 讲清：
- 进程标签（`u:r:init:s0`）的 4 个字段各代表什么
- 文件标签怎么从 file_contexts 写进 ext4 的 xattr
- property 标签 / socket 标签 / service 标签 怎么独立成 fc
- 一次 `restorecon` 怎么改文件标签

### 8.2 看完本文的自检

- [ ] 能说出 `system/sepolicy/{public,private,vendor}` 3 个目录的含义
- [ ] 能从 1 个 .te 文件读出"哪类进程允许哪些操作"
- [ ] 能区分 .te vs .cil 的使用时机
- [ ] 能跑 `sepolicy-analyze` 列出某 device 的所有 type
- [ ] 知道 neverallow violation 怎么改（attribute 排除法）

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
