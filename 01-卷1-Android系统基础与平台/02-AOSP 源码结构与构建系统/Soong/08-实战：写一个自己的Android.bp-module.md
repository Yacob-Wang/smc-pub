# 06-Foundation/Build-System/Soong · 08 · 实战：写一个自己的 Android.bp module

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · BSP · 改源码工程师
>
> **强依赖**：[01]-[07] 全部前篇

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：从 0 到 1 写一个完整可上线的 cc_library native daemon——含 Android.bp + C++ 源码 + init.rc 集成 + SELinux 策略 + file_contexts 集成 + 编译验证 + 上线验证
- **不是**：不复述 [01]-[07] 任一篇语法（实战用）
- **承接自**：[07 §6 速查表](07-常见编译错误速查.md) → 本文用真实案例走完 5 大类
- **衔接去**：[06-Foundation/SELinux/07](../../05-安全基础（SELinux%20·%20AVB）/SELinux/07-实战：定制SELinux策略排错5例.md)（SELinux 集成实战）

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章给真实可编译的 vendor daemon | 不用 toy example |
| 2 | 第 5-8 章按 5 步流程（写→编→验→集成→上线）| 实战 5 步走 |
| 3 | 第 9 章给完整文件树 + 集成 checklist | 上线前 checklist |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**从 0 到 1 写一个完整可上线的 vendor daemon = Android.bp + C++ + init.rc + SELinux + file_contexts 5 个文件，5 步走完。**

本文以"vendor 想要一个系统级 daemon `vendor.example.daemon`"为真实场景，**所有文件都可直接 copy-paste 编入 AOSP 17**。

---

## 1. 实战目标

### 1.1 需求

**vendor.example.daemon** 是什么：

- 一个系统级 native daemon
- 启动后常驻
- 读一个配置 `/vendor/etc/foo.conf`
- 周期性往 `/data/vendor/foo/state.txt` 写一行 timestamp
- 接受 `SIGTERM` / `SIGINT` 优雅退出
- logcat 输出 "I vendor.example.daemon: state updated"

### 1.2 5 个产出文件

| 文件 | 路径 | 角色 |
|:-----|:-----|:-----|
| `Android.bp` | `vendor/example/daemon/Android.bp` | Soong module 定义 |
| `main.cpp` | `vendor/example/daemon/src/main.cpp` | 源码 |
| `init.rc` | `vendor/example/daemon/daemon.rc` | init 启动配置 |
| `*.te` | `vendor/example/sepolicy/vendor.example.daemon.te` | SELinux 策略 |
| `file_contexts` | `vendor/example/sepolicy/file_contexts` | 文件标签 |

### 1.3 完整文件树

```
vendor/example/
├── daemon/
│   ├── Android.bp
│   ├── src/
│   │   └── main.cpp
│   └── daemon.rc
└── sepolicy/
    ├── vendor.example.daemon.te
    └── file_contexts
```

---

## 2. 步骤 1：写 Android.bp

```python
# vendor/example/daemon/Android.bp
cc_binary {
    name: "vendor.example.daemon",
    srcs: ["src/main.cpp"],

    shared_libs: [
        "liblog",       // logcat
        "libbase",      // android::base
        "libutils",     // 工具
    ],

    cflags: [
        "-Wall",
        "-Werror",
        "-Wno-unused-parameter",
    ],

    // init.rc 自动生成
    init_rc: ["daemon.rc"],

    // vendor 分区可用
    vendor: true,

    // selinux 标签
    stem: "vendor.example.daemon",

    // 默认在哪个分区
    install_in: "vendor",
}
```

**关键属性说明**：
- `init_rc: ["daemon.rc"]` → 自动拷贝到 `out/.../vendor/etc/init/`
- `vendor: true` → 进 vendor 分区
- `install_in: "vendor"` → 同上
- `stem` → 二进制名字（不用 platform 默认的"daemon"）

---

## 3. 步骤 2：写 main.cpp

```cpp
// vendor/example/daemon/src/main.cpp
#include <android-base/logging.h>
#include <signal.h>
#include <fstream>
#include <chrono>
#include <ctime>
#include <string>
#include <thread>

// 全局退出标志
volatile sig_atomic_t g_should_exit = 0;

// 信号处理
void signal_handler(int sig) {
    LOG(INFO) << "Received signal " << sig << ", exiting";
    g_should_exit = 1;
}

// 读配置
std::string read_config() {
    std::ifstream f("/vendor/etc/foo.conf");
    if (!f.is_open()) {
        return "default";
    }
    std::string line;
    std::getline(f, line);
    return line.empty() ? "default" : line;
}

// 写状态
void write_state() {
    std::ofstream f("/data/vendor/foo/state.txt");
    if (!f.is_open()) {
        LOG(WARNING) << "Cannot open state file";
        return;
    }
    auto now = std::chrono::system_clock::now();
    auto t = std::chrono::system_clock::to_time_t(now);
    f << "state updated at " << std::ctime(&t);
}

int main(int /*argc*/, char* /*argv*/[]) {
    // 1. 初始化 log
    android::base::InitLogging(nullptr, 
        android::base::LogdLogger(android::base::SYSTEM));
    LOG(INFO) << "vendor.example.daemon starting";

    // 2. 注册信号
    signal(SIGTERM, signal_handler);
    signal(SIGINT, signal_handler);

    // 3. 读配置
    auto config = read_config();
    LOG(INFO) << "config: " << config;

    // 4. 主循环
    while (!g_should_exit) {
        write_state();
        LOG(INFO) << "state updated";
        // 60s 一次
        for (int i = 0; i < 60 && !g_should_exit; i++) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    }

    LOG(INFO) << "vendor.example.daemon exiting";
    return 0;
}
```

---

## 4. 步骤 3：写 init.rc

```rc
# vendor/example/daemon/daemon.rc
service vendor.example.daemon /vendor/bin/vendor.example.daemon
    class core
    user root
    group root system
    seclabel u:r:vendor_example_daemon:s0

on boot
    # 启动 daemon
    start vendor.example.daemon

on property:vendor.example.daemon.restart=1
    stop vendor.example.daemon
    start vendor.example.daemon
```

**关键配置**：
- `class core` → 启动时机早（init 后立即）
- `seclabel u:r:vendor_example_daemon:s0` → SELinux 标签
- 启动后用 `start vendor.example.daemon` 手动触发
- 提供 `setprop vendor.example.daemon.restart 1` 优雅重启

---

## 5. 步骤 4：写 SELinux 策略

```te
# vendor/example/sepolicy/vendor.example.daemon.te
type vendor_example_daemon, domain;
type vendor_example_daemon_exec, exec_type, vendor_file_type, file_type;

# 启动时切到 vendor_example_daemon 域
type_transition init vendor_example_daemon_exec:process vendor_example_daemon;
allow init vendor_example_daemon:process transition;
allow init vendor_example_daemon_exec:file { read execute open };

# daemon 自身能力
allow vendor_example_daemon self:capability { sys_nice dac_override };
allow vendor_example_daemon self:process { setcurrent };

# 读 /vendor/etc/foo.conf
allow vendor_example_daemon vendor_file:file { read open getattr };
allow vendor_example_daemon vendor_file:dir { search };

# 写 /data/vendor/foo/state.txt
type vendor_example_daemon_data_file, file_type, data_file_type;
allow vendor_example_daemon vendor_example_daemon_data_file:file { read write create open getattr };
allow vendor_example_daemon vendor_example_daemon_data_file:dir { search add_name };

# logcat
allow vendor_example_daemon logd:unix_stream_socket connectto;
allow vendor_example_daemon logdr_socket:sock_file write;
```

**注意**：简化版策略，**实际生产要更细的权限**（见 [06-Foundation/SELinux/02](../../05-安全基础（SELinux%20·%20AVB）/SELinux/02-策略文件体系：sepolicy.te.cil.编译产物.md)）。

---

## 6. 步骤 4.5：写 file_contexts

```te
# vendor/example/sepolicy/file_contexts
/vendor/bin/vendor\.example\.daemon    u:object_r:vendor_example_daemon_exec:s0
/data/vendor/foo(/.*)?                u:object_r:vendor_example_daemon_data_file:s0
/vendor/etc/foo\.conf                 u:object_r:vendor_file:s0
```

**注意转义**：点号 `.` 必须 `\.`，否则匹配任意字符。

---

## 7. 步骤 5：集成到 BoardConfig.mk

```makefile
# device/<vendor>/<device>/BoardConfig.mk
# 1. 启用 device sepolicy
BOARD_SEPOLICY_DIRS += \
    device/<vendor>/<device>/sepolicy \
    vendor/example/sepolicy

# 2. 启用 SELinux enforcing
BOARD_KERNEL_CMDLINE += androidboot.selinux=enforcing
```

**关键**：
- `BOARD_SEPOLICY_DIRS` 让 Soong 编译时合并 vendor 的策略
- 不加 → 策略不会进 binary policy

---

## 8. 步骤 6：编译 + 验证

### 8.1 编译

```bash
# 1. 加载环境
$ source build/envsetup.sh
$ lunch <device>-userdebug

# 2. 编译 daemon
$ m vendor.example.daemon
# 期望：编译成功

# 3. 编译 selinux_policy
$ m selinux_policy
# 期望：无 neverallow 错误

# 4. 编译 system.img（让 daemon 进 vendor.img）
$ m vendor
```

### 8.2 验证产物

```bash
# 1. 找 daemon 二进制
$ find out/target/product -name "vendor.example.daemon" 2>/dev/null
out/target/product/cf_x86_64_phone/vendor/bin/vendor.example.daemon
out/target/product/cf_x86_64_phone/obj/EXECUTABLES/vendor.example.daemon_intermediates/vendor.example.daemon

# 2. 找 init.rc
$ find out/target/product -name "daemon.rc" 2>/dev/null
out/target/product/cf_x86_64_phone/vendor/etc/init/daemon.rc

# 3. 找 binary policy
$ find out/target/product -name "precompiled_sepolicy*" 2>/dev/null
out/target/product/cf_x86_64_phone/vendor/etc/selinux/precompiled_sepolicy

# 4. 验证 binary policy 包含新 type
$ sepolicy-analyze out/target/product/cf_x86_64_phone/vendor/etc/selinux/precompiled_sepolicy types | grep vendor_example_daemon
vendor_example_daemon
```

### 8.3 验证 init.rc

```bash
# 1. 验证 init.rc 被打包到 vendor.img
$ cat out/target/product/cf_x86_64_phone/vendor/etc/init/daemon.rc
service vendor.example.daemon /vendor/bin/vendor.example.daemon
    class core
    user root
    group root system
    seclabel u:r:vendor_example_daemon:s0
    ...

# 2. 验证 service 名
$ grep -r "vendor.example.daemon" out/target/product/cf_x86_64_phone/vendor/etc/init/
out/target/product/cf_x86_64_phone/vendor/etc/init/daemon.rc:service vendor.example.daemon /vendor/bin/vendor.example.daemon
```

### 8.4 验证 SELinux policy

```bash
# 1. 验证 type 已注册
$ sepolicy-analyze out/target/product/cf_x86_64_phone/vendor/etc/selinux/precompiled_sepolicy types | grep vendor_example_daemon
vendor_example_daemon
vendor_example_daemon_exec
vendor_example_daemon_data_file

# 2. 验证 transition 规则
$ sepolicy-analyze out/target/product/cf_x86_64_phone/vendor/etc/selinux/precompiled_sepolicy transition -s init -t vendor_example_daemon_exec
init → vendor_example_daemon

# 3. 验证 allow 规则
$ sepolicy-analyze out/target/product/cf_x86_64_phone/vendor/etc/selinux/precompiled_sepolicy allow -s vendor_example_daemon
vendor_example_daemon self:capability { sys_nice dac_override }
vendor_example_daemon vendor_file:file { read open getattr }
vendor_example_daemon logd:unix_stream_socket connectto
...
```

---

## 9. 步骤 7：烧录 + 上线验证

### 9.1 烧录

```bash
# 1. 烧录 boot.img（含 init 二进制）
$ fastboot flash boot out/target/product/cf_x86_64_phone/boot.img

# 2. 烧录 vendor.img（含 daemon + init.rc + policy）
$ fastboot flash vendor out/target/product/cf_x86_64_phone/vendor.img

# 3. 重启
$ fastboot reboot
```

### 9.2 上线验证 5 步

```bash
# 1. 启动后看 init 启动 service
$ adb logcat -d | grep "vendor.example.daemon"
[   5.123] init: Starting service 'vendor.example.daemon'...
[   5.234] init: Service 'vendor.example.daemon' (pid 1234) launched
[   5.345] vendor.example.daemon: config: default
[   5.456] vendor.example.daemon: state updated

# 2. 进程 context 正确
$ adb shell ps -Z | grep vendor.example.daemon
u:r:vendor_example_daemon:s0  root  1234  1  /vendor/bin/vendor.example.daemon

# 3. 进程能写 state 文件
$ adb shell cat /data/vendor/foo/state.txt
state updated at Mon Jul 27 10:00:00 2026
[+60s]
$ adb shell cat /data/vendor/foo/state.txt
state updated at Mon Jul 27 10:01:00 2026

# 4. 没有 denied 行
$ adb logcat -d | grep "avc: denied" | grep vendor_example_daemon
# 期望：无输出

# 5. 优雅退出
$ adb shell setprop ctl.stop vendor.example.daemon
[  10.234] vendor.example.daemon: Received signal 15, exiting
[  10.345] vendor.example.daemon: vendor.example.daemon exiting
$ adb shell ps -A | grep vendor.example.daemon
# 期望：无输出（已退出）
```

---

## 10. 集成 Checklist（上线前必过）

### 10.1 编译期 Checklist

- [ ] `m vendor.example.daemon` 编译成功
- [ ] `m selinux_policy` 无 neverallow 错误
- [ ] `sepolicy-analyze types` 含 3 个新 type
- [ ] `sepolicy-analyze transition` 含 init → daemon
- [ ] `sepolicy-analyze allow -s daemon` 含必要 allow
- [ ] 产物路径正确（vendor/bin/ + vendor/etc/init/）
- [ ] `m vendor` 编译 vendor.img 成功

### 10.2 上线期 Checklist

- [ ] 启动后进程 context 正确（`ps -Z`）
- [ ] 启动后没有 denied 风暴
- [ ] logcat 输出符合预期
- [ ] 数据文件正确写入
- [ ] `setprop ctl.stop` 优雅退出
- [ ] `setprop ctl.start` 重启正常
- [ ] 多次重启无内存泄漏（`dumpsys meminfo`）

### 10.3 性能 Checklist

- [ ] 启动时间 < 1 秒
- [ ] 内存占用 < 20MB
- [ ] CPU 占用空闲 < 1%
- [ ] 不在主线程做 I/O

---

## 11. 完整文件树 + 集成路径

```
完整集成后的工程树
═══════════════════════════════════════════════════════════════

aosp/
├── vendor/example/
│   ├── daemon/
│   │   ├── Android.bp           ← Soong module 定义
│   │   ├── src/
│   │   │   └── main.cpp         ← 源码
│   │   └── daemon.rc            ← init 启动配置
│   └── sepolicy/
│       ├── vendor.example.daemon.te   ← SELinux 策略
│       └── file_contexts              ← 文件标签
│
├── device/<vendor>/<device>/
│   ├── BoardConfig.mk           ← 启用 sepolicy 目录
│   └── sepolicy/                ← device 侧 SELinux（可选）
│
└── out/target/product/<device>/
    ├── vendor/
    │   ├── bin/
    │   │   └── vendor.example.daemon   ← 编译产物
    │   ├── etc/
    │   │   ├── init/
    │   │   │   └── daemon.rc
    │   │   ├── selinux/
    │   │   │   └── precompiled_sepolicy   ← binary policy
    │   │   └── foo.conf                   ← 配置
    │   └── lib/                            ← 依赖的 .so
    │
    └── vendor.img                          ← 烧录镜像
```

---

## 12. 8 篇 Soong 系列收官引用矩阵

```
┌────────────────────────────────────────────────────────────┐
│  Soong 8 篇全引用矩阵                                       │
└────────────────────────────────────────────────────────────┘

[01] 演进史
  ↓ 引用 → [02] 语法 / [04] 架构
  ↑ 引用 ← 全部

[02] Android.bp 语法
  ↓ 引用 → [03] 解析 / [07] 错误
  ↑ 引用 ← 全部

[03] Blueprint
  ↓ 引用 → [04] Soong 怎么用
  ↑ 引用 ← [02] [04] [07]

[04] Soong 架构
  ↓ 引用 → [05] Ninja / [06] 产物
  ↑ 引用 ← [01] [03] [08]

[05] Ninja
  ↓ 引用 → [06] 产物 / [07] 错误
  ↑ 引用 ← [04] [07] [08]

[06] out/ 目录
  ↓ 引用 → [07] 错误 / [08] 实战
  ↑ 引用 ← [05] [08]

[07] 编译错误速查
  ↓ 引用 → [08] 实战排错
  ↑ 引用 ← [02] [03] [05] [08]

[08] 实战（你正在读）
  ↑ 引用 ← 全部 7 篇
```

---

## 13. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01]-[07] 全部前篇 | 实战用到所有语法 |
| [06-Foundation/SELinux/02](../../05-安全基础（SELinux%20·%20AVB）/SELinux/02-策略文件体系：sepolicy.te.cil.编译产物.md) | SELinux 编译 |
| [06-Foundation/SELinux/04](../../05-安全基础（SELinux%20·%20AVB）/SELinux/04-AVC与avc_denied：从一次denied反推策略.md) | 实战排 denied |
| [06-Foundation/SELinux/07](../../05-安全基础（SELinux%20·%20AVB）/SELinux/07-实战：定制SELinux策略排错5例.md) | vendor daemon 案例同本文 |
| [06-Foundation/Tools/Android_Tools/Init_RC_Complete_Guide](../../../05-卷5-调查工具链/35-断点与%20Native%20调试/Init_RC_Complete_Guide.md) | init.rc 完整语法 |
| [Build-System/04_Build_Configuration_And_Options](../04_Build_Configuration_And_Options.md) | BoardConfig.mk |
| [02-Symptom/S11-Startup/A03-Init进程与init.rc](../../../02-卷2-系统启动/10-应用启动与首帧/A03-Init进程与init.rc.md) | init 进程 |

---

## 14. 自检 + 收官

### 14.1 看完 Soong 8 篇全系列的自检

- [ ] 能说 Soong 30 年演进的 4 阶段
- [ ] 能用 9 大 module 类型 + 6 大属性 + 3 特殊语法写 Android.bp
- [ ] 能说 Android.bp → token → AST → module 的 4 阶段解析
- [ ] 能说 Soong 4 大核心概念（module / variant / provider / mutator）
- [ ] 能从 build.ninja 手工调 ninja 增量构建
- [ ] 能用 6 大常见产物路径速查 5 秒找文件
- [ ] 能用 30 错误速查表 5 分钟定位编译问题
- [ ] 能从 0 到 1 写一个完整可上线的 native daemon

### 14.2 收官话

Soong 这条线在稳定性架构师的能力模型里属于**"改源码" + "机制理解"两层交集**——读得懂 Android.bp 能 5 秒加 module，看得懂 build.ninja 能手工增量构建。

下一步推荐读：
- [03-Forensics/Bugreport/01-总览与生成/解析](../../../../05-卷5-调查工具链/33-Dumpsys · Bugreport · DropBox/01-Bugreport-总览与生成解析.md) — 编译产物上线后怎么取证（下一条 M4-B1 系列）
- [06-Foundation/SELinux/08](../../05-安全基础（SELinux%20·%20AVB）/SELinux/08-AOSP-17演进：Treble+CIL+userspace加载.md) — AOSP 17 跨版本迁移
- [02-Symptom/S08-AOSP17-K618](../../../../../01-卷1-Android系统基础与平台/01-Android 系统全景与 AOSP 17/01-症状机制.md) — AOSP 17 全局演进

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，Soong 8 篇收官）
