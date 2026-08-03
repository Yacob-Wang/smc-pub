# 第 7 章 Init 进程与 init.rc - 写作准备

> **生成时间**：2026-08-02
> **章节状态**：🚧 0 篇章
> **总目标字数**：~30000 字（6 节 × 4000-6000）
> **预估工时**：10-14h
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI

---

## 章定位

第一个用户态进程——整个 Android 系统的"启动管家"。

**为什么重要**：
- init 阶段慢 = 整机启动慢的 N 倍影响（gating 后续所有服务）
- init 失败 = 整个系统起不来（bootloop、brick）
- init 启动的 Service 数量 = 200+（zygote, surfaceflinger, servicemanager, vold, netd, ...）

---

## 6 节大纲（精细化）

### 7.1 Init 进程启动流程（system/core/init）

**核心子问题**（8 个）：
1. PID 1 为什么必须是 init？kernel 如何保证？
2. main() → FirstStageMain / SecondStageMain 的分阶段原因？
3. ueventd / watchdogd / logd 怎么从 init fork 出来？
4. signal handler：处理 SIGCHLD / SIGTERM / SIGUSR1 的逻辑
5. epoll + timerfd 事件循环怎么实现？
6. init 启动时序图（从 kernel_init 到 SystemServer 启动前的所有步骤）
7. AOSP 17 vs AOSP 14 init 启动链路差异
8. Pixel 7 实测 init 启动耗时数据（来源：tracing 数据）

**AOSP 17 源码路径**（AOSP 17.0.0_r1 锁定）：
- `system/core/init/main.cpp` — FirstStageMain / SecondStageMain
- `system/core/init/init.cpp` — Init 核心类（构造函数 + 启动流程）
- `system/core/init/signal_handler.cpp` — 信号处理
- `system/core/init/init.h` — 类定义
- `system/core/init/ueventd.cpp` — ueventd 实现

**字数目标**：5000-6000
**写作要点**：
- 启动流程用 mermaid 时序图
- 信号处理部分贴真实代码片段（init.cpp HandleSignal）
- 对比 AOSP 14 突出 AOSP 17 的 reinit / bootstat 改造

---

### 7.2 init.rc 语法：service / action / import / on

**核心子问题**（8 个）：
1. init.rc 文件分哪几类？（init.rc / init.<hardware>.rc / init.<product>.rc / vendor init）
2. Action / Service / Command / Import / On 五大原语
3. 解析器如何处理 trigger 语法（on early / on boot / on property:xxx=yyy）？
4. Service 关键字：class / user / group / capability / seclabel / oneshot / disabled
5. Service 启动策略：class_start / class_stop / class_reset
6. import 递归：如何保证不重复 import？循环引用检测？
7. 解析错误处理：rc 文件语法错的 fallback 策略
8. AOSP 17 init.rc 新增指令（vs AOSP 14）

**AOSP 17 源码路径**：
- `system/core/init/parser.cpp` — Tokenizer / Parser 实现
- `system/core/init/builtins.cpp` — 内建命令（class_start 等）
- `system/core/init/service.cpp` — Service 类
- `system/core/init/action.cpp` — Action 类
- `system/core/init/import_parser.cpp` — Import 解析

**字数目标**：5000-6000
**写作要点**：
- 解析器流程图（lex → parse → AST → execute）
- Service 配置实战示例（surfaceflinger.rc 完整解释）
- class 启动顺序：core / main / late_start

---

### 7.3 启动阶段：early / init / late-start / post-fs / post-fs-data

**核心子问题**（8 个）：
1. 6 个启动阶段分别在什么时候触发？
2. early-init：挂载 /dev / /proc / /sys 等基础文件系统
3. init：初始化属性 / 加载 SELinux policy
4. late-init：启动 core class 关键服务
5. post-fs-data：挂载 /data 分区
6. property trigger：ro.build.* / ro.product.* 触发的 action
7. 阶段间依赖：哪些阶段必须按顺序？
8. AOSP 17 新增阶段（vs AOSP 14）

**AOSP 17 源码路径**：
- `system/core/init/init.cpp` — ActionQueue 执行
- `system/core/init/bootchart.cpp` — bootchart 集成
- `system/core/rootdir/init.rc` — 核心 init.rc
- `system/core/rootdir/init.zygote64.rc` — zygote 启动配置

**字数目标**：4000-5000
**写作要点**：
- 6 阶段时间线（时序图）
- 关键 Service 启动顺序表（class core / class main / class late_start）
- 阶段失败时的 kernel panic 行为

---

### 7.4 属性服务（Property Service）：跨进程配置传递

**核心子问题**（8 个）：
1. Property Service 架构：init 主进程 + ashmem + socket
2. 5 类 Property：system / vendor / persist / ctl / socket
3. property_set / property_get 客户端实现
4. 跨进程同步：init socket 协议 / 锁 / dirty 区
5. 持久化：persist.* 写入 /data/property/persist.properties
6. ctl.* 服务控制：ctl.start / ctl.stop / ctl.restart
7. ro.* 只读保护：AOSP 14/15/16/17 的强化演进
8. 性能数据：setprop 调用延迟、Property Service 锁竞争案例

**AOSP 17 源码路径**：
- `system/core/init/property_service.cpp` — 服务端
- `system/core/libcutils/properties.cpp` — 客户端
- `system/core/init/builtins.cpp` — setprop / getprop 命令
- `bionic/libc/include/sys/_system_properties.h` — 客户端 API

**字数目标**：5000-6000
**写作要点**：
- ashmem + socket 通信流程图
- ctl.* 实战：am restart / stop / start
- 性能案例：Property Service 锁竞争导致 boot 慢 1.2s

---

### 7.5 SELinux 上下文加载与策略执行

**核心子问题**（7 个）：
1. SELinux 在 init 阶段的启动顺序
2. policy 加载路径：/vendor/etc/selinux + /system/etc/selinux
3. init 进程 SELinux 上下文：kernel 域
4. 动态上下文加载：setcon / restorecon
5. SELinux 拒绝日志：avc denied → dmesg / logcat
6. Permissive 模式：调试期临时降级
7. AOSP 17 SELinux 演进：userfaultfd 限制 / io_uring 限制

**AOSP 17 源码路径**：
- `system/core/init/selinux.cpp` — 策略加载
- `external/selinux/libselinux/src/avc.c` — AVC 拒绝处理
- `system/sepolicy/` — 策略定义

**字数目标**：4000-5000
**写作要点**：
- SELinux 启动时序图
- avc denied 实战案例（init 启动某 Service 失败）
- 永久 vs 临时 Permissive 模式切换

---

### 7.6 init 启动慢的常见原因（实战案例）

**核心子问题**（6 个）：
1. 性能基线：Pixel 7 init 阶段耗时数据（来源：atrace / bootchart）
2. 关键 Service 启动超时：zygote 启动慢 / surfaceflinger 启动慢
3. wait_for_property 阻塞：等属性超时
4. fs 挂载慢：post-fs-data /data 挂载延迟
5. init.rc 启动顺序优化：并行启动 + class_start 合并
6. 性能工具：bootchart / atrace init / perfetto init trace

**AOSP 17 源码路径**：
- `system/core/init/bootchart.cpp` — bootchart 实现
- `frameworks/native/cmds/atrace/` — atrace init 支持
- `external/perfetto/` — perfetto init trace

**字数目标**：4000-5000
**写作要点**：
- 性能数据表（Pixel 7 / Pixel 8 / 模拟器对比）
- 实战案例：某 Service 启动慢导致整机 boot 多 2.3s 的完整定位过程
- 优化 SOP：5 步快速定位 init 启动慢

---

## 总字数与工时估算

| 节 | 字数 | 估时 | 关键依赖 |
|---|---:|---:|---|
| 7.1 Init 启动流程 | 6000 | 2-3h | 无 |
| 7.2 init.rc 语法 | 6000 | 2-3h | 7.1 |
| 7.3 启动阶段 | 5000 | 1.5-2h | 7.1, 7.2 |
| 7.4 Property Service | 6000 | 2-3h | 7.1 |
| 7.5 SELinux | 5000 | 1.5-2h | 7.1 |
| 7.6 启动慢实战 | 5000 | 1.5-2h | 7.1-7.5 |
| **合计** | **~33000** | **10-14h** | |

---

## 写作顺序建议

**Phase 1 (4-5h)**：7.1 + 7.3（建立 init 启动时间线基础）
**Phase 2 (4-5h)**：7.2 + 7.4（init.rc 语法 + Property）
**Phase 3 (2-3h)**：7.5 + 7.6（SELinux + 实战收尾）

---

## 与前后章的链接

- **前置章节**：第 6 章 Bootloader 到 Kernel（init 之前 = kernel 阶段）
- **后继章节**：第 8 章 Zygote 与 ART 启动（init 启动 zygote）
- **跨卷引用**：
  - 卷 3 第 13 章 进程与生命周期（init 是所有进程的祖先）
  - 卷 3 第 18 章 SELinux（详细 SELinux 机制）
  - 卷 5 第 31 章 Perfetto（init 启动性能分析工具）

---

## AOSP 17 关键变化（vs AOSP 14/16）

| 变化 | AOSP 14 | AOSP 17 | 影响 |
|---|---|---|---|
| init 启动并行度 | 顺序 class_start | 部分 Service 并行 | 启动快 0.3-0.5s |
| Property Service 锁优化 | 全局锁 | 读 / 写分离 | 启动快 0.1-0.2s |
| SELinux 强制模式 | 部分 Permissive | 全部 Enforcing | 启动期 + 0.1-0.3s |
| init 重构（reinit） | 无 | reinit 子系统 | 支持 OTA 后快速 init |
| 启动 tracing | bootchart | bootchart + atrace + perfetto | 可观测性增强 |

---

**下一步**：commit 完 3 个（拆分 + E 级 + 00-Meta）后，按 Phase 1 → 2 → 3 顺序写 7.1-7.6 节正文。
