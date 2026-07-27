# 06-Foundation/Tools/Android_Tools · 05 · dropbox / crash buffer 机制

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · crash 历史取证
>
> **强依赖**：[03-Forensics/Bugreport/02 §2.4 dropbox](../../../03-Forensics/Bugreport/02-Bugreport-目录结构全梳理.md) · [01-Mechanism/Framework/Service](../../../01-Mechanism/Framework/Service/) · [03-Forensics/Bugreport/04 实战 5 案例](../../../03-Forensics/Bugreport/04-Bugreport-实战5类典型案例.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 dropbox（system_server 提供的 crash 历史持久化服务）讲清楚——怎么工作、4 大组件、数据格式、调试命令、跟 bugreport / logcat 的关系
- **不是**：不复述 [03-Forensics/Bugreport/02 §2.4 dropbox 简介](../../../03-Forensics/Bugreport/02-Bugreport-目录结构全梳理.md)；不复述 [01-Mechanism/Framework/Service](../../../../01-Mechanism/Framework/Service/) 通用 service 机制
- **承接自**：[Bugreport/02 §2.4 dropbox 简介](../../../03-Forensics/Bugreport/02-Bugreport-目录结构全梳理.md) → 本文讲"为什么 / 怎么 / 怎么用"
- **衔接去**：[04-Tool/Dumpsys/12-dumpsys实战SOP](../../../04-Tool/Dumpsys/12-dumpsys实战SOP.md) · [03-Forensics/Bugreport/04 §2 案例 2 NE](../../../03-Forensics/Bugreport/04-Bugreport-实战5类典型案例.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 2 章 4 大组件表 | 理解 dropbox 怎么工作 |
| 2 | 第 3 章数据格式 + tag 分类 | 取证用 |
| 3 | 第 5 章实战案例 | 5 分钟上手 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**dropbox = system_server 的"crash 历史"服务——把 crash 信息持久化到 /data/system/dropbox/，oncall 5 秒拉历史 crash。**

理解 dropbox = 理解"为什么 NE 后 tombstone 还在 / data/system/dropbox/ 也有一份" = 现场取证多 1 个数据源。

---

## 1. dropbox 是什么

### 1.1 一句话定位

```
dropbox = system_server 内置的 crash buffer
├─ 输入：app / service 死亡事件（system_server 监听）
├─ 输出：/data/system/dropbox/<tag>@<timestamp>.txt 文件
├─ 容量：默认 5MB（每个 tag）
├─ 持久：重启不丢
└─ 目的：oncall 拉历史 crash（不只是看当前 crash）
```

### 1.2 跟 tombstone 的区别

| 维度 | tombstone | dropbox |
|:-----|:----------|:--------|
| **触发** | NE 进程自己写 | system_server 监听 + 写 |
| **位置** | `/data/tombstones/` | `/data/system/dropbox/` |
| **内容** | 详细 backtrace + signal + maps | 摘要 + 触发原因 |
| **大小** | 几 MB / 个 | 几 KB / 个 |
| **保留时间** | 30+ 个（循环）| 5MB / tag（循环）|
| **看哪个** | 看完整 NE 现场 | 看 crash 历史 |

### 1.3 跟 logcat crash buffer 的区别

| 维度 | logcat crash | dropbox |
|:-----|:------------|:--------|
| **触发** | logd 监听 | system_server 监听 |
| **位置** | ringbuffer（重启丢）| 文件（持久）|
| **内容** | 完整 logcat | 摘要 + logcat 摘录 |
| **看哪个** | 当前 crash | 历史 crash |

### 1.4 4 大用途

| 用途 | 何时用 |
|:-----|:------|
| **crash 历史** | "昨天 3 点 NE 了几次" |
| **现场摘要** | 没抓 bugreport，但 dropbox 还在 |
| **按 tag 过滤** | 只看 `system_app_crash@...` |
| **自动持久化** | 不要人工保存（自动）|

---

## 2. dropbox 4 大组件

### 2.1 组件总览

```
[A] DropBoxManager（API 层）
    └─ frameworks/base/core/java/android/os/DropBoxManager.java
    └─ 暴露给 app / service 调用
    
[B] DropBoxManagerService（系统服务）
    └─ frameworks/base/services/core/java/com/android/server/DropBoxManagerService.java
    └─ 在 system_server 进程
    └─ 监听 / 写文件 / 维护容量
    
[C] tag + 文件格式
    └─ <tag>@<timestamp>.<age>.txt
    └─ /data/system/dropbox/
    
[D] 容量管理
    └─ 每个 tag 默认 5MB
    └─ 超容量自动 trim（删最老的）
```

### 2.2 DropBoxManager（API 层）

```java
// frameworks/base/core/java/android/os/DropBoxManager.java
public class DropBoxManager {
    public static final String TAG_CRASH = "system_app_crash";
    public static final String TAG_ANR = "system_app_anr";
    public static final String TAG_TOMBSTONE = "SYSTEM_TOMBSTONE";
    public static final String TAG_NATIVE_CRASH = "native_crash";
    
    public void addText(String tag, String data) {
        // 添加文本到 dropbox
    }
    
    public void addFile(String tag, File file, int flags) {
        // 添加文件（如 tombstone）
    }
    
    public void addData(String tag, byte[] data, int flags) {
        // 添加 binary data
    }
    
    public InputStreamEntry getNextEntry(String tag, long millis) {
        // 取下一个 entry
    }
}
```

### 2.3 DropBoxManagerService（核心服务）

```java
// frameworks/base/services/core/java/com/android/server/DropBoxManagerService.java
public class DropBoxManagerService extends SystemService {
    // 数据目录
    private File mDropBoxDir = new File("/data/system/dropbox");
    
    // 每个 tag 的容量（默认 5MB）
    private static final int DEFAULT_AGE_SECONDS = 3 * 24 * 60 * 60;  // 3 天
    private static final int DEFAULT_MAX_FILES = 1000;
    private static final int DEFAULT_MAX_BYTES_LOWRAM = 5 * 1024 * 1024;  // 5MB
    private static final int DEFAULT_MAX_BYTES = 20 * 1024 * 1024;  // 20MB
    
    // 关键方法
    public void addText(String tag, String text) {
        // 1. 写文件
        File f = new File(mDropBoxDir, tag + "@" + timestamp + ".txt");
        // 2. 检查容量
        // 3. 超出 → trim 旧文件
    }
    
    public void onStart() {
        // 服务启动时 trim 旧 entry
    }
}
```

### 2.4 tag 分类（AOSP 17）

| tag | 含义 | 何时触发 |
|:---|:-----|:-------|
| `system_app_crash` | app 进程 NE | app NE 时 |
| `system_app_anr` | app ANR | app ANR 时 |
| `system_app_wtf` | app WTF（严重错）| app Log.wtf 时 |
| `system_server_crash` | system_server NE | system_server NE 时 |
| `system_server_anr` | system_server ANR | system_server ANR 时 |
| `SYSTEM_TOMBSTONE` | native NE 摘要 | native 进程 NE 时 |
| `SYSTEM_RECOVERY_LOG` | recovery 模式 log | 进 recovery 时 |
| `BATTERY_DISCHARGE_INFO` | 电池放电信息 | 关机 / 重启时 |
| `SYSTEM_BOOT` | 系统启动信息 | 启动时 |
| `KERNEL_PANIC` | kernel panic 摘要 | kernel panic 时 |
| `KERNEL_WAKEUP_*` | kernel 唤醒源 | kernel 唤醒时 |
| `native_crash` | native 进程 NE | native 进程 NE 时 |
| `anr` | ANR（老 tag）| app ANR 时（v <= 7）|
| `crash` | crash（老 tag）| app crash 时（v <= 7）|

### 2.5 文件名格式

```
/data/system/dropbox/
├── system_app_crash@1719475312345.txt
├── system_app_crash@1719475400000.txt
├── system_app_anr@1719475500000.txt
├── SYSTEM_TOMBSTONE@1719475600000.txt
├── KERNEL_PANIC@1719475700000.txt
└── ...
```

**格式**：`@<timestamp>.<age>.txt`
- `timestamp` = ms since epoch
- `age` = 文件保留时长（毫秒）
- `.txt` = 扩展名

---

## 3. dropbox 数据格式

### 3.1 真实 dropbox 文件内容

```
# system_app_crash@1719475312345.txt
Process: com.example.app
Build: Pixel 8
Time: 1719475312
Duration: 8500
ANR in com.example.app, Reason: Input dispatching timed out
Subject: Input dispatching timed out

Cmd line: com.example.app
PID: 1234
UID: 10001
Cold start: false
Launched since boot: 4523

----- pid 1234 at 2026-07-27 10:30:00 +0800 -----
Cmd line: com.example.app
ABI: arm64
Build type: optimized
systrace: false

"main" prio=5 tid=7 Blocked
  | group="main" sCount=1 ...
  at java.lang.Object.wait(Native method)
  at com.example.app.FooClass.barMethod(FooClass.java:42)
  ...
```

### 3.2 4 大内容块

| 块 | 内容 | 用途 |
|:---|:-----|:-----|
| **元信息** | Process / Build / Time / PID / UID | 5 秒定位 |
| **触发原因** | ANR in ... / FATAL EXCEPTION: ... | 1 秒看类型 |
| **线程栈** | main / worker thread 栈 | 定位代码 |
| **内存 / 调度** | malloc info / io 状态 | 辅助分析 |

### 3.3 SYSTEM_TOMBSTONE 格式

```
# SYSTEM_TOMBSTONE@1719475600000.txt
Process: vendor.foo
Build: Pixel 8
Time: 1719475600
Signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x000000000000
ABI: arm64
Instruction aborted: 0x000000000000

backtrace:
  #00 pc 0x0000abcd in vendor::hwc::Config::Write() at hwc.cpp:42
  #01 pc 0x00001234 in main at main.cpp:18

memory map:
  0x000000001234-0x000000005678 r-xp  /system/lib64/libfoo.so
  ...
```

### 3.4 KERNEL_PANIC 格式

```
# KERNEL_PANIC@1719475700000.txt
Process: <none>
Build: Pixel 8
Time: 1719475700
Kernel panic - not syncing: Unable to handle kernel NULL pointer
Tainted: G W
Hardware name: ...
RIP: 0010:vendor_driver_func+0x12/0x80
```

---

## 4. dropbox 调试命令

### 4.1 dumpsys dropbox（最全）

```bash
# 1. 完整 dropbox 状态
$ adb shell dumpsys dropbox
# 输出：
# Drop box: /data/system/dropbox
#   tags: system_app_crash, system_app_anr, ...
#   ...
#   tag: system_app_crash
#     2026-07-27 10:30:00 age 1d file 1234 bytes
#     2026-07-26 08:15:30 age 1d file 567 bytes
#     ...
#   tag: system_app_anr
#     2026-07-27 09:00:00 age 1d file 8901 bytes
#   ...

# 2. 完整 dropbox 列表
$ adb shell dumpsys dropbox --print
# 输出每个 entry 的完整内容
```

### 4.2 直接列文件

```bash
# 1. 列所有 dropbox
$ adb shell ls -la /data/system/dropbox/
# 5 个 tag 共 100+ 文件

# 2. 列某 tag 的文件
$ adb shell ls -la /data/system/dropbox/ | grep "system_app_crash"
# 最近的 crash

# 3. 按时间倒序
$ adb shell ls -lt /data/system/dropbox/

# 4. 看 size
$ adb shell du -sh /data/system/dropbox/
# 8M
```

### 4.3 拉取

```bash
# 1. 拉单个文件
$ adb pull /data/system/dropbox/system_app_crash@1719475312345.txt

# 2. 拉整个 dropbox
$ adb pull /data/system/dropbox/ /tmp/dropbox/

# 3. 远程 adb pull
$ adb shell cat /data/system/dropbox/system_app_crash@1719475312345.txt
```

### 4.4 按 tag 拉历史

```bash
# 1. 拉所有 system_app_crash
$ adb shell ls /data/system/dropbox/ | grep "system_app_crash" | \
  while read f; do
    adb pull "/data/system/dropbox/$f" /tmp/dropbox/
  done

# 2. 拉所有 KERNEL_PANIC
$ adb shell ls /data/system/dropbox/ | grep "KERNEL_PANIC" | \
  while read f; do
    adb pull "/data/system/dropbox/$f" /tmp/dropbox/
  done
```

### 4.5 dumpsys dropbox --print（完整内容）

```bash
# 完整内容（可能很大）
$ adb shell dumpsys dropbox --print

# 指定 tag
$ adb shell dumpsys dropbox --print --tag system_app_crash

# 指定时间
$ adb shell dumpsys dropbox --print --tag system_app_crash --since 1719475312
```

### 4.6 6 大调试场景速查

| 场景 | 命令 |
|:-----|:-----|
| 看 dropbox 状态 | `dumpsys dropbox` |
| 看完整内容 | `dumpsys dropbox --print` |
| 拉文件 | `adb pull /data/system/dropbox/` |
| 找某 tag | `dumpsys dropbox --print --tag XXX` |
| 列文件 | `ls -lt /data/system/dropbox/` |
| 看 size | `du -sh /data/system/dropbox/` |

---

## 5. dropbox 实战案例

### 5.1 案例 1：app 频繁 NE 调查

```bash
# 1. 看 dropbox 摘要
$ adb shell dumpsys dropbox
# tag: system_app_crash
#   5 个 entry（最近 1 天）

# 2. 拉所有
$ adb shell ls /data/system/dropbox/ | grep "system_app_crash" | \
  while read f; do
    adb pull "/data/system/dropbox/$f" /tmp/crashes/
  done

# 3. 看 trigger 原因
$ grep "Process:\|FATAL EXCEPTION" /tmp/crashes/*.txt | head

# 4. 看 SIGSEGV / SIGABRT
$ grep "signal\|Reason" /tmp/crashes/*.txt | sort | uniq -c
# 输出：
#   5 Reason: Input dispatching timed out
#   2 FATAL EXCEPTION: main
#   1 signal 11 (SIGSEGV)
```

**结论**：5 次 ANR + 2 次 JE + 1 次 NE → 主线程卡死是主因

### 5.2 案例 2：系统服务重启调查

```bash
# 1. 找 system_server crash
$ adb shell ls /data/system/dropbox/ | grep "system_server"

# 2. 拉
$ adb pull /data/system/dropbox/system_server_crash@xxx.txt

# 3. 看死亡原因
$ head -50 system_server_crash@xxx.txt
```

### 5.3 案例 3：kernel panic 调查

```bash
# 1. 找 KERNEL_PANIC
$ adb shell ls /data/system/dropbox/ | grep "KERNEL_PANIC"

# 2. 拉
$ adb pull /data/system/dropbox/KERNEL_PANIC@xxx.txt

# 3. 看 RIP
$ grep "RIP\|Tainted" KERNEL_PANIC@xxx.txt

# 4. 对照 kallsyms
$ adb pull /proc/kallsyms
$ grep "<vendor_func>" kallsyms
```

### 5.4 案例 4：自动监控 dropbox 增长

```bash
# 1. 看容量
$ adb shell du -sh /data/system/dropbox/
# 8M

# 2. 看每个 tag 占用
$ adb shell "for t in system_app_crash system_app_anr KERNEL_PANIC; do
  du -sh /data/system/dropbox/ 2>/dev/null | grep \$t
done"

# 3. 监控（每秒）
$ watch -n 1 "adb shell du -sh /data/system/dropbox/"
```

### 5.5 案例 5：清空 dropbox（debug 时）

```bash
# ⚠️ 危险：会丢历史 crash
# 1. 清空整个 dropbox
$ adb shell rm -rf /data/system/dropbox/
$ adb shell mkdir -p /data/system/dropbox/
$ adb shell chown system:system /data/system/dropbox/

# 2. 清特定 tag
$ adb shell rm /data/system/dropbox/system_app_crash@*

# 注意：清空后 oncall 历史 crash 不可见
```

---

## 6. dropbox 与 bugreport

### 6.1 关系

```
crash 发生
    ↓
DropBoxManagerService 写 dropbox（持久化）
    ↓
bugreport 抓现场时收集 dropbox
    ↓
FS/data/system/dropbox/  在 bugreport.zip 里
```

**关键洞察**：
- dropbox 在 system_server（重启丢 system_server 时 dropbox 也丢）
- bugreport 抓取时会同步收集 dropbox
- 双重保险：tombstone + dropbox + logcat crash buffer

### 6.2 在 bugreport 中的位置

```
bugreport.zip/
└── FS/
    └── data/
        └── system/
            └── dropbox/                   ← 这里
                ├── system_app_crash@1719475312345.txt
                ├── system_app_anr@1719475500000.txt
                ├── SYSTEM_TOMBSTONE@1719475600000.txt
                └── ...
```

### 6.3 bugreport 之外的 dropbox 抓取

```bash
# 1. 直接 dumpsys
$ adb shell dumpsys dropbox --print > /tmp/dropbox.txt

# 2. 拉文件
$ adb pull /data/system/dropbox/ /tmp/dropbox/

# 3. 按 tag 过滤
$ adb shell dumpsys dropbox --print --tag system_app_crash > /tmp/crash_history.txt
```

### 6.4 5 类 crash 的 dropbox 触发表

| crash 类型 | dropbox tag | 何时写 |
|:----------|:-----------|:------|
| **app NE** | `system_app_crash` | system_server 监听到 process died |
| **app ANR** | `system_app_anr` | system_server 监听到 ANR |
| **app WTF** | `system_app_wtf` | app 主动调 Log.wtf |
| **system_server NE** | `system_server_crash` | system_server 死 |
| **system_server ANR** | `system_server_anr` | system_server 卡死 |
| **native NE** | `SYSTEM_TOMBSTONE` | native 进程死（从 tombstone 复制）|
| **kernel panic** | `KERNEL_PANIC` | init 监听到 kernel panic |
| **recovery 进** | `SYSTEM_RECOVERY_LOG` | 进 recovery 时 |

### 6.5 dropbox 是 bugreport 的"补充"

| 数据源 | 持久 | 完整 | 易访问 |
|:-------|:----|:-----|:------|
| **tombstone** | ✅ 30+ 个循环 | ✅ 完整 NE | 单独 pull |
| **dropbox** | ✅ 5MB/tag 循环 | 🟡 摘要 | dumpsys 5 秒 |
| **logcat crash** | ❌ 重启丢 | ✅ 完整 | logcat -d |

**oncall 5 分钟决策**：
1. 先看 dropbox 摘要（5 秒）
2. 再看 logcat crash 详细（10 秒）
3. 最后看 tombstone 完整（30 秒）

---

## 7. dropbox 调优

### 7.1 4 大调优 property

```bash
# 1. 调整容量（低 RAM 设备）
$ adb shell setprop persist.logd.dropbox.lowram 1
# → 5MB per tag

# 2. 调整容量（正常设备）
$ adb shell setprop persist.logd.dropbox.max_bytes 20971520
# → 20MB per tag

# 3. 调整保留时间
$ adb shell setprop persist.logd.dropbox.max_files 1000

# 4. 关闭某 tag
$ adb shell setprop persist.logd.dropbox.tag.<TAG>.enable 0
# e.g. setprop persist.logd.dropbox.tag.system_app_wtf.enable 0
```

### 7.2 5 个反模式

```
❌ 1. 永久清空 dropbox（丢历史）
❌ 2. 不看 dropbox 直接看 logcat（漏摘要）
❌ 3. 删某 tag 全部文件（破坏 oncall 数据）
❌ 4. 长期禁用某 tag（错失 crash 信号）
❌ 5. 不监控 dropbox 容量（满后丢数据）
```

### 7.3 5 大调优原则

```
✅ 1. 留够容量（默认 5MB 太小时调大）
✅ 2. 定期清（每月 1 次，但保留 1 周内）
✅ 3. 监控 dropbox 增长（发现 crash 趋势）
✅ 4. 集成 bugreport（自动持久）
✅ 5. 启用 logpersistd（logcat 长期收集）
```

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [03-Forensics/Bugreport/02 §2.4 dropbox 简介](../../../03-Forensics/Bugreport/02-Bugreport-目录结构全梳理.md) | 简介 |
| [03-Forensics/Bugreport/04 §2 案例 2 NE](../../../03-Forensics/Bugreport/04-Bugreport-实战5类典型案例.md) | 实战 |
| [03-Forensics/Bugreport/05 §2 工具选择](../../../03-Forensics/Bugreport/05-Bugreport-vs-perfetto-trace.md) | 工具边界 |
| [01-Mechanism/Framework/Service](../../../../01-Mechanism/Framework/Service/) | service 机制 |
| [01-Mechanism/Runtime/Native_Crash/04-debuggerd与Tombstone](../../../../01-Mechanism/Runtime/Native_Crash/04-debuggerd与Tombstone.md) | tombstone 机制 |
| [06-Foundation/SELinux/07 实战 5 例](../../SELinux/07-实战：定制SELinux策略排错5例.md) | NE 排错 |
| [04-Tool/Dumpsys/12-dumpsys实战SOP](../../../04-Tool/Dumpsys/12-dumpsys实战SOP.md) | dumpsys 完整 |

---

## 9. 收官 + 自检

### 9.1 看完本文的自检

- [ ] 能说 dropbox 4 大组件（API / Service / 格式 / 容量）
- [ ] 知道 dropbox 跟 tombstone / logcat crash buffer 的差异
- [ ] 能用 `dumpsys dropbox` 看完整状态
- [ ] 能用 `dumpsys dropbox --print` 看完整内容
- [ ] 能用 `adb pull /data/system/dropbox/` 拉文件
- [ ] 知道 6 大调试命令
- [ ] 能用 5 步法分析 crash 历史
- [ ] 知道 dropbox 在 bugreport 里的位置
- [ ] 知道 4 大调优 property + 5 大反模式

### 9.2 5 类 crash 的 dropbox tag 速查

| crash 类型 | dropbox tag | 看什么命令 |
|:----------|:-----------|:--------|
| app NE | `system_app_crash` | `dumpsys dropbox --print --tag system_app_crash` |
| app ANR | `system_app_anr` | `dumpsys dropbox --print --tag system_app_anr` |
| system_server NE | `system_server_crash` | `dumpsys dropbox --print --tag system_server_crash` |
| native NE | `SYSTEM_TOMBSTONE` | `dumpsys dropbox --print --tag SYSTEM_TOMBSTONE` |
| kernel panic | `KERNEL_PANIC` | `dumpsys dropbox --print --tag KERNEL_PANIC` |

### 9.3 oncall 5 分钟定位模板

```
[1] 抓现场
$ adb shell dumpsys dropbox > /tmp/dropbox.txt
$ adb shell bugreport
[2] 看 dropbox 摘要（5 秒）
$ grep "tag:" /tmp/dropbox.txt
[3] 找某 tag 详细（10 秒）
$ adb shell dumpsys dropbox --print --tag <TAG> | less
[4] 拉所有相关文件（30 秒）
$ adb pull /data/system/dropbox/ /tmp/
[5] 关联 bugreport（5 秒）
$ unzip -p bugreport.zip FS/data/system/dropbox/ > /tmp/dropbox_bugreport/
```

### 9.4 收官话

dropbox 在稳定性架构师的能力模型里属于**"取证落地"层**——能 5 秒拉 crash 历史，5 分钟定位多次 crash 的根因。

下一步推荐读：
- [03-Forensics/Bugreport/01-总览与生成解析](../../../03-Forensics/Bugreport/01-Bugreport-总览与生成解析.md) — bugreport 完整
- [04-Tool/Dumpsys/12-dumpsys实战SOP](../../../04-Tool/Dumpsys/12-dumpsys实战SOP.md) — dumpsys 完整
- [01-Mechanism/Framework/Service](../../../../01-Mechanism/Framework/Service/) — system_server 机制

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，dropbox 收官）
