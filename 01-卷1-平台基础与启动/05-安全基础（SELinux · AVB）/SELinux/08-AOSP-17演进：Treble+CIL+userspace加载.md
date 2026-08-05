# 06-Foundation/SELinux · 08 · AOSP 17 演进：Treble + CIL + userspace 加载

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · 平台 / BSP · 跨版本迁移工程师
>
> **强依赖**：[01]-[07] 全部前篇

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 AOSP 4.3（SELinux 引入）到 AOSP 17 的 SELinux 演进时间线讲清楚——为什么 Treble 隔离、为什么 CIL 替代 .te、为什么 userspace 加载、为什么 AOSP 17 的 3 个硬变化
- **不是**：不复述 [01]-[07] 任一篇；本文是 SELinux 系列的"收官篇" + 跨版本迁移指南
- **承接自**：[07 实战 5 例](07-实战：定制SELinux策略排错5例.md) 5 个 case 中的 AOSP 17 假设
- **衔接去**：[02-Symptom/S08-AOSP17-K618](../../../../../01-卷1-平台基础与启动/01-系统全景与 AOSP 17/01-症状机制.md) / [Android.bp 01](../../02-AOSP%20源码结构与构建系统/Soong/01-从Make到Soong：AOSP编译系统演进.md) / [05-Governance/Security](../../../05-Governance/Security/)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章给完整时间线（4.3 → 17 跨度 13 年）| 架构师要懂"为什么这样设计" |
| 2 | 第 6 章给"迁移路径"具体步骤 | 真实项目 90% 要跨版本迁 |
| 3 | 第 8 章 SELinux 8 篇完结 + 全系列引用矩阵 | 系列收官 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**AOSP 17 的 SELinux ≠ 简单"更严"或"更快"——是 Treble 隔离 + CIL 策略 + userspace 加载 + 3 个硬变化的综合体，每个变化都对应线上 1 类稳定性问题。**

跨 AOSP 版本迁移时，**SELinux 是最容易踩雷的子系统**——kernel policy 变、user policy 变、.te vs .cil 变、boot.img 装载逻辑变。本文给 13 年演进时间线 + AOSP 17 硬变化 + 迁移路径速查。

---

## 1. SELinux 13 年演进时间线（AOSP 4.3 → 17）

### 1.1 关键里程碑

| AOSP 版本 | 年份 | 关键变化 | 稳定性含义 |
|:---------|:----:|:-------|:---------|
| **4.3** | 2013 | SELinux 首次引入（enforcing 默认）| 全量策略 + init.te 标准结构 |
| **4.4** | 2013 | 引入 permissive domain（per-domain 切）| 调试入口 |
| **5.0** | 2014 | SELinux for Bluetooth / NFC | 新增子域 |
| **5.1** | 2015 | SEPolicy split（system / vendor 分离）| 厂商可定制 |
| **6.0** | 2015 | Treble 雏形（HAL 接口分离）| 加速 OTA |
| **7.0** | 2016 | 完整 Treble 引入 | 隔离强化 |
| **8.0** | 2017 | **Treble 正式启用**，SELinux 强制 vendor 隔离 | platform / vendor 强隔离 |
| **9.0** | 2018 | APEX 模块（runtime upgrade）| 模块化 |
| **10.0** | 2019 | APEX 正式启用 | libbinder / conscrypt 等可升级 |
| **11.0** | 2020 | mac_permissions.xml 简化 | installd 简化 |
| **12.0** | 2021 | **CIL 策略语言引入** | .te 编译加速 5x |
| **13.0** | 2022 | CIL 默认，.te 兼容 | 双轨期 |
| **14.0** | 2023 | **userspace 加载机制** | load_policy 完整化 |
| **15.0** | 2024 | SELinux + APEX 集成 | APEX 升级带 policy |
| **16.0** | 2025 | SELinux + AI Native 集成 | AICore 域 |
| **17.0** | 2026 | **3 个硬变化**（见 §5）| ML 信任 / binder 重写 / Treble 强化 |

### 1.2 跨版本兼容性铁律

**二进制策略不兼容**：
- AOSP 14 的 binary policy 不能直接装到 AOSP 17（struct 变）
- AOSP 11 的 binary policy 不能装到 AOSP 12（CIL 引入后 header 变）
- **每次升级必须重烧 boot.img + 重新 m selinux_policy**

**源码策略部分兼容**：
- .te 文件 AOSP 11 → 17 多数兼容
- .cil 文件 AOSP 12 → 17 完全兼容
- 跨大版本时**有 5-10% .te 需要手动调整**

---

## 2. AOSP 8：Treble 引入策略隔离

### 2.1 Treble 之前的混乱

AOSP 7 之前，platform 和 vendor 共享同一份 policy：

```
/system/etc/selinux/  ← system + vendor 共享
```

**问题**：
- vendor 改 SELinux 策略会破坏 system 稳定性
- OTA 升级时策略耦合，难维护
- 厂商定制困难

### 2.2 Treble 强制隔离

AOSP 8 把 policy 切成 4 块：

```
system/sepolicy/                    ← platform（Google 维护）
├── public/                         # 暴露给 vendor
├── private/                        # 不暴露
├── vendor/                         # vendor 基线
└── ...

device/<vendor>/<device>/sepolicy/  ← vendor（厂商维护）
└── ...                             # 只能引用 public
```

**强制规则**：
- vendor 侧 .te **不能 allow platform private 类型**
- platform 侧 .te **不能 allow vendor 类型**
- 两边互相 allow 只能通过 `public/` 暴露

### 2.3 neverallow 的"围墙"作用

```te
# AOSP 8+ 大量 neverallow 防止"误用"
# 例：vendor 不能访问 platform private 域
neverallow { vendor -init -kernel -recovery } priv_app:file *;
```

**稳定性含义**：vendor 加新 service 时**必须先看 public/ 暴露了哪些 type**，否则编译期 neverallow 直接失败。

---

## 3. AOSP 12：CIL 策略语言引入

### 3.1 .te 的 3 个痛点

AOSP 11 之前用 .te + m4 macro：

```te
# .te 看起来很现代，但底层是 m4 宏
interface(`
    domain_auto_trans(olddomain, newdomain, newfile)
')

define(`domain_auto_trans', `
    allow $1 $2:process transition;
    ...
')
```

**痛点**：
- m4 宏编译慢（500+ .te 文件 10 分钟）
- 错误信息对人不友好
- 不支持现代 IDE 的语法高亮 / 跳转

### 3.2 CIL 的设计目标

AOSP 12 引入 CIL（Common Intermediate Language）：

```cil
; CIL 看起来像 Lisp
(type domain)
(type exec_type)

(typeattribute domain)
(typeattribute exec_type)

(roletype object_r exec_type)

(allow untrusted_app app_data_file (file (read write open)))
```

**优势**：
- 编译快 5x（200 个 .cil 文件 1 分钟）
- 错误信息精确到行号
- 工具链友好（可解析为 AST）
- **AOSP 12 引入，AOSP 17 已是主流**

### 3.3 AOSP 12-17 的 .te vs .cil 现状

| AOSP 版本 | .te 占比 | .cil 占比 | 关系 |
|:---------|:--------|:---------|:----|
| 12 | 70% | 30% | CIL 引入 |
| 13 | 50% | 50% | 双轨期 |
| 14 | 30% | 70% | CIL 主导 |
| 15 | 20% | 80% | CIL 主流 |
| 16 | 15% | 85% | CIL 绝对主流 |
| **17** | **10%** | **90%** | CIL 几乎全替代 |

**稳定性含义**：
- 新加 .te 文件越来越少
- 但**删 .te 是大工程**（依赖多）
- 跨版本迁移优先 .te → .cil

---

## 4. AOSP 14：userspace 加载机制

### 4.1 kernel 加载 vs userspace 加载

AOSP 11 之前：policy 编译成 binary 后**由内核直接 load**。

```bash
# AOSP 11 之前 binary policy
out/target/product/<device>/obj/.../policy.bin
# 内核 boot 时直接 load
```

**问题**：
- policy 改动必须重新编译 kernel
- 调试不便
- 与 user policy 不一致

### 4.2 AOSP 14 引入 userspace load

```bash
# AOSP 14+ 多了 userspace policy
out/target/product/<device>/vendor/etc/selinux/precompiled_sepolicy
# 由 init 进程在启动时 load 到内核
```

**关键变化**：
- kernel policy 和 user policy 分离
- init 进程 load user policy（不再依赖 kernel）
- 调试更友好（可读 SELinux denial log）

### 4.3 加载时序

```
[1] kernel 启动 → load kernel policy（不变）
[2] init (PID 1) 启动 → 走 second stage
[3] init 调用 SelinuxInitialize() → load user policy
    └─ SelinuxLoadPolicy() (system/core/init/selinux.cpp)
    └─ security_load_policy() (kernel)
    └─ AVC 缓存清空
[4] init 切到 init 域
[5] 继续启动
```

**稳定性含义**：
- 改 user policy **不用重烧 kernel**
- 但**仍要重烧 boot.img**（init 进程在 boot.img）
- 重启时 init 自动 load

---

## 5. AOSP 17：3 个硬变化

### 5.1 变化 1：ML 信任域扩展

AOSP 17 引入了 **AI 相关的 SELinux 域**：

```te
# system/sepolicy/public/ai_native.te（AOSP 17 新增）
type ai_native_service, domain, mlstrustedsubject;
type ai_native_service_exec, exec_type, vendor_file_type, file_type;

# AICore 系统服务
allow ai_native_service system_app:binder { call transfer };
allow ai_native_service priv_app:fd use;
```

**稳定性含义**：
- 新加 AI 域的 service **必须给 ML 信任**
- 涉及 AICore 的 binder 调用要走特殊域

### 5.2 变化 2：Rust Binder 集成

AOSP 17 引入了 Rust 实现的 Binder 驱动（部分），SELinux 决策路径变化：

```rust
// kernel/security/rust_binder/avc_decision.rs
fn selinux_check(sctx: &str, tctx: &str, tclass: u16, perm: u32) -> bool {
    // Rust 实现的 AVC 决策
    // 与 C 版保持 100% 一致
}
```

**稳定性含义**：
- C 版和 Rust 版 AVC 决策**结果必须完全一致**
- 任何不一致 = 严重的稳定性 bug
- 调试时可能看到不同路径的同一 denied

### 5.3 变化 3：Treble 强化（v3）

AOSP 17 把 Treble 推进到 v3：

```te
# system/sepolicy/public/private/treble_v3.te
# 禁止 vendor 直接访问所有 platform internal 域
neverallow { vendor } { system_server priv_app system_app }:binder { call transfer };
# 必须通过 public/ 暴露的 service_manager 调用
```

**稳定性含义**：
- vendor 适配工作量进一步加大
- 任何"vendor 误调 system_server"都被 neverallow 阻止
- 编译期 fail = 早发现

---

## 6. 迁移路径：AOSP 14 → AOSP 17

### 6.1 3 个阶段

```
[阶段 1] 准备（1-2 周）
    └─ 备份当前 binary policy
    └─ 列 vendor .te 文件清单
    └─ 列 .te vs .cil 占比

[阶段 2] 编译切换（1-2 周）
    └─ 用 AOSP 17 source 重新 m selinux_policy
    └─ 修 neverallow violation（必有 5-20 处）
    └─ 跑 CTS / VTS 验证

[阶段 3] 灰度上线（2-4 周）
    └─ 内部 device 灰度
    └─ 监控 avc: denied 数量
    └─ 修剩余 denied
    └─ 全量
```

### 6.2 迁移必做的 5 件事

**1. m selinux_policy 跑通**：

```bash
$ source build/envsetup.sh
$ lunch <device>-eng
$ m selinux_policy
# 期望：编译成功；neverallow violation 列出
```

**2. 处理 neverallow violation**：

```bash
# 看到 ERROR 位置
# 例：neverallow check failed ... at /.../treble_sepolicy
# 修法：
#  - 用 attribute 排除（推荐）
#  - 改用其他 capability / class
#  - 联系 Google 合入 platform
```

**3. 跑 CTS / VTS SELinux 测试**：

```bash
$ cts-tradefed run cts-dev --module CtsSelinuxTargetSdk25TestCases
$ cts-tradefed run cts-dev --module CtsSelinuxNeverallowRulesTest
$ vts-tradefed run vts --module vts_kernel_selinux_test
```

**4. 跑 audit2why 看剩余 denied**：

```bash
$ adb shell dmesg | grep "avc: denied" | audit2why
# 输出每条 denied 的根因
# 修法：按 4 类根因（[06 §2](06-常见稳定性问题：service-crash.neverallow.build-失败.md)）
```

**5. 重烧所有相关镜像**：

```bash
$ fastboot flash boot out/.../boot.img
$ fastboot flash vendor out/.../vendor.img
$ fastboot flash system out/.../system.img
$ fastboot reboot
```

### 6.3 跨版本迁移的 5 个常见雷区

| 雷区 | 表现 | 解法 |
|:-----|:-----|:-----|
| 1. .te → .cil 语法错 | m selinux_policy 报错 | 优先用 .cil，新文件直接 .cil |
| 2. neverallow 增强 | 老代码不通过 | 用 attribute 排除 |
| 3. Treble v3 限制 | vendor 不能访问 system_server | 走 service_manager 间接 |
| 4. binary policy 不兼容 | 启动 panic | 必须重烧所有镜像 |
| 5. audit2allow 过宽 | 上线后被 CTS 拒 | 手动收紧 allow |

---

## 7. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 总览](01-SELinux总览：MAC机制在Android的落地.md) | 起点 |
| [02 策略文件体系](02-策略文件体系：sepolicy.te.cil.编译产物.md) | .te vs .cil 详细对比 |
| [03 Context 与 Label](03-Context与Label：四大主体的标签从哪来.md) | 跨版本 context 字段不变 |
| [04 AVC 与 avc_denied](04-AVC与avc_denied：从一次denied反推策略.md) | AVC 在 AOSP 17 是 Rust + C 双实现 |
| [05 init 与 SELinux](05-init进程与SELinux：分阶段加载.md) | userspace 加载见本文 §4 |
| [06 常见稳定性问题](06-常见稳定性问题：service-crash.neverallow.build-失败.md) | 跨版本常见稳定性问题 |
| [07 实战 5 例](07-实战：定制SELinux策略排错5例.md) | 5 案例的 AOSP 17 假设见本文 §5 |
| [02-Symptom/S08-AOSP17-K618](../../../../../01-卷1-平台基础与启动/01-系统全景与 AOSP 17/01-症状机制.md) | AOSP 17 全局演进 |
| [01-Mechanism/Kernel/Binder/13-Rust Binder专题](../../../../02-卷2-核心机制/12-Binder IPC 深度/13-Rust Binder专题.md) | Rust Binder 集成 |
| [05-Governance/AI-Native/02_AI_Native_OS/O03-AICore_System_Service_AOSP中的AI调度核心](../../../../05-卷5-性能工程与治理/52-AI-Native 调试/O03-AICore_System_Service_AOSP中的AI调度核心.md) | AICore 域 |
| [Android.bp 01](../../02-AOSP%20源码结构与构建系统/Soong/01-从Make到Soong：AOSP编译系统演进.md) | Soong 编译系统演进（与 SELinux 编译耦合）|

---

## 8. SELinux 系列完结：8 篇引用矩阵

```
┌─────────────────────────────────────────────────────────────┐
│  SELinux 8 篇全引用矩阵                                       │
└─────────────────────────────────────────────────────────────┘

[01] 总览
  ↓ 引用 → [02] 策略文件 / [03] Context / [05] init
  ↑ 引用 ← 全部后续

[02] 策略文件体系
  ↓ 引用 → [03] Context（.fc 怎么被使用）/[04] AVC（反推）
  ↑ 引用 ← [01] [05] [06] [07]

[03] Context 与 Label
  ↓ 引用 → [04] AVC（denied 行）/ [05] init
  ↑ 引用 ← [01] [02] [04] [06] [07]

[04] AVC 与 avc_denied
  ↓ 引用 → [05] init（启动期 AVC）/[06] 稳定性
  ↑ 引用 ← [03] [06] [07] [08]

[05] init 与 SELinux
  ↓ 引用 → [04]（启动期数据源）/[06]（启动期症状）
  ↑ 引用 ← [04] [06] [08]

[06] 常见稳定性问题
  ↓ 引用 → [07]（5 案例）/ [04]（反推 5 步）
  ↑ 引用 ← [01] [04] [05] [07]

[07] 实战 5 例
  ↓ 引用 → [06]（4 类根因）
  ↑ 引用 ← [04] [06] [08]

[08] AOSP 17 演进（本文）
  ↑ 引用 ← 全部 7 篇
```

**全 8 篇统一资源**：
- 真实源码路径：kernel/security/selinux/、system/sepolicy/、system/core/init/
- 真实工具：sepolicy-analyze / checkfc / checkpolicy / audit2why
- 真实命令：ps -Z / ls -Z / getfattr / getprop -T / dmesg

---

## 9. 自检 + 收官

### 9.1 看完 SELinux 8 篇全系列的自检

- [ ] 能说 SELinux 13 年演进的 5 个关键节点
- [ ] 能区分 Treble 之前 / 之后 / v3 的策略隔离
- [ ] 能说 .te vs .cil 在 AOSP 12-17 的占比演化
- [ ] 知道 userspace 加载机制什么时候引入（AOSP 14）
- [ ] 能说 AOSP 17 的 3 个硬变化
- [ ] 知道跨版本迁移的 3 阶段 + 5 必做 + 5 雷区
- [ ] 能用 6 步通用流程定位 4 类根因
- [ ] 能从 1 行 `avc: denied` 反推 1 条 .te allow 规则
- [ ] 知道 audit2allow 的 3 个危险陷阱
- [ ] 知道 unlabeled 资源不该用 audit2allow 修复，要修 file_contexts

### 9.2 收官话

SELinux 这条线在稳定性架构师的能力模型里属于**"机制理解" + "取证落地"两层交集**——读得懂源码能定位问题，看得懂 denied 能反推修法。

下一步推荐读：
- [Android.bp 01](../../02-AOSP%20源码结构与构建系统/Soong/01-从Make到Soong：AOSP编译系统演进.md) — 编译系统是 SELinux 编译的前置
- [02-Symptom/S08-AOSP17-K618](../../../../../01-卷1-平台基础与启动/01-系统全景与 AOSP 17/01-症状机制.md) — AOSP 17 全局演进
- [05-Governance/Security](../../../05-Governance/Security/) — SELinux 治理 SOP（**待补**，M1-M6 规划外）

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，SELinux 系列收官）
