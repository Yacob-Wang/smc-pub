# 06-Foundation/Tools/Android_Tools · 03 · Logcat 过滤与持久化

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 长期 log 收集
>
> **强依赖**：[02 Logcat 格式与 tag 体系](02-Logcat格式与tag体系.md) · [Logcat_Complete_Guide](./Logcat_Complete_Guide.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 logcat 5 大过滤维度（tag / level / buffer / 时间 / 内容）+ 3 种持久化方式（tee / logcatd / properties）讲清楚——oncall 5 分钟精确定位 + 长期 log 收集
- **不是**：不复述 [02 §3 tag 体系](02-Logcat格式与tag体系.md) 和 [02 §4 level 体系](02-Logcat格式与tag体系.md)；不复述 [Logcat_Complete_Guide](./Logcat_Complete_Guide.md) 基础命令
- **承接自**：[02 §1-7](02-Logcat格式与tag体系.md) → 本文讲"组合过滤 + 持久化"
- **衔接去**：[04 Logcat 与 SELinux/avc](04-Logcat与SELinux-avc-denied行解读.md) / [06-Foundation/Tools/Tracing/20-Trace抓取方法全面指南](../Tracing/20-Trace抓取方法全面指南：ftrace-atrace-systrace-perfetto.md) / [04-Tool/AmCommand/05-诊断与监控-hang-monitor](../../../../05-卷5-调查工具链/33-Dumpsys · Bugreport · DropBox/05-诊断与监控-hang-monitor.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 5 大过滤维度独立成节 | 90% oncall 用这 5 类过滤 |
| 2 | 第 3 章 3 种持久化对比 | 长期 log 收集选型 |
| 3 | 第 4 章 properties 配置实战 | 厂商适配必用 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**logcat 过滤 = 5 维度组合（tag / level / buffer / 时间 / 内容）= oncall 5 秒定位。**

AOSP 17 默认 logcat 输出噪声大（4MB 缓冲 + 1MB kernel），5 维度组合过滤 = 90% 的事故定位提速 10x。

---

## 1. 5 大过滤维度

### 1.1 维度总览

| 维度 | 关键字 | 例子 | 5 秒选择 |
|:-----|:------|:-----|:--------|
| **tag** | `TAG:V` | `MyTag:V` | 已知 tag |
| **level** | `*:W` | `*:E` | 已知 level |
| **buffer** | `-b` | `-b system` | 已知 buffer |
| **时间** | `-t` | `-t '07-27 10:30:00'` | 已知时间窗口 |
| **内容** | `grep` | `grep "FATAL"` | 已知关键字 |

### 1.2 维度 1：tag 过滤

```bash
# 1. 单 tag + level
$ adb logcat MyTag:V *:S
# MyTag 全 level + 其他 Silent

# 2. 多 tag 不同 level
$ adb logcat MyTag:V OtherTag:W *:S

# 3. 通配符
$ adb logcat "MyApp*":V *:S
# 所有 MyApp 开头的 tag

# 4. 全部 tag 某 level
$ adb logcat *:E
# 所有 Error

# 5. 全部 tag 全部 level
$ adb logcat *:V
```

### 1.3 维度 2：level 过滤

```bash
# 1. Error 及以上
$ adb logcat *:E

# 2. Warning 及以上
$ adb logcat *:W

# 3. Info 及以上（默认）
$ adb logcat *:I

# 4. Debug 及以上（开发期）
$ adb logcat *:D

# 5. Verbose 及以上（最详细）
$ adb logcat *:V
```

### 1.4 维度 3：buffer 过滤

```bash
# 1. 单 buffer
$ adb logcat -b main
$ adb logcat -b system
$ adb logcat -b kernel
$ adb logcat -b crash
$ adb logcat -b events

# 2. 多 buffer
$ adb logcat -b main,system

# 3. all buffer
$ adb logcat -b all

# 4. buffer 容量
$ adb logcat -g -b main
# main: ring buffer is 4.0MB (1 used of 4MB)
```

### 1.5 维度 4：时间过滤

```bash
# 1. 最后 N 行
$ adb logcat -d -T 100
# 最后 100 行

# 2. 起始时间（自此往后）
$ adb logcat -d -t '07-27 10:30:00.000'
# 从 10:30:00 开始

# 3. 起始时间（多 buffer）
$ adb logcat -d -b all -t '07-27 10:30:00.000'

# 4. 完整时间线
$ adb logcat -v threadtime -d
```

### 1.6 维度 5：内容过滤（grep）

```bash
# 1. 简单 grep
$ adb logcat -d | grep "FATAL"

# 2. 多关键字
$ adb logcat -d | grep -E "FATAL|ANR|service died"

# 3. 反向（排除）
$ adb logcat -d | grep -v "debug"

# 4. 上下文
$ adb logcat -d | grep -B5 -A20 "FATAL"

# 5. 大小写不敏感
$ adb logcat -d | grep -i "fatal"

# 6. case sensitive（默认）
$ adb logcat -d | grep "FATAL"
```

---

## 2. 过滤组合实战

### 2.1 6 大组合模式

#### 模式 1：单 tag 全 level

```bash
$ adb logcat MyApp:V *:S
```

#### 模式 2：多 tag 不同 level

```bash
$ adb logcat MyApp:V Network:W *:S
```

#### 模式 3：单 buffer + 关键字

```bash
$ adb logcat -b system | grep "init:"
```

#### 模式 4：多 buffer + 关键字

```bash
$ adb logcat -b main,system | grep "FATAL"
```

#### 模式 5：时间窗口 + tag

```bash
$ adb logcat -b main -t '07-27 10:30:00.000' MyApp:V *:S
```

#### 模式 6：grep + 上下文

```bash
$ adb logcat -d -b system -v threadtime | grep -B5 -A20 "init:" 
```

### 2.2 5 大事故的过滤模板

#### ANR 模板

```bash
# 1. 找 ANR 触发
$ adb logcat -d -b system | grep "ANR in"

# 2. 看主线程栈
$ adb logcat -d -b system | grep -A 50 "ANR in" | head -100

# 3. 看 Input dispatching
$ adb logcat -d -b system | grep "Input dispatching"
```

#### NE 模板

```bash
# 1. 找 FATAL
$ adb logcat -d -b crash | grep "FATAL"

# 2. 看完整栈
$ adb logcat -d -b crash | grep -A 50 "FATAL"

# 3. 找 tombstone 触发
$ adb logcat -d -b main | grep "tombstone"
```

#### OOM 模板

```bash
# 1. 找 lowmemory / killer
$ adb logcat -d | grep -E "lowmemory|killer|am_kill"

# 2. 看 process dies
$ adb logcat -d | grep "Process.*died" | tail

# 3. 看 meminfo dumpsys（不是 logcat，但 5 秒定位）
$ adb shell dumpsys meminfo | head
```

#### KE 模板

```bash
# 1. 找 kernel panic
$ adb logcat -d -b kernel | grep -E "panic|oops"

# 2. 看 BUG
$ adb logcat -d -b kernel | grep "BUG:"

# 3. 看 last_kmsg（持久化）
$ adb shell cat /proc/last_kmsg | head
```

#### bootloop 模板

```bash
# 1. 找 init 启动
$ adb logcat -d -b system | grep "init:" | head -50

# 2. 找 service 重启
$ adb logcat -d -b system | grep "restarted"

# 3. 看 SELinux denied
$ adb logcat -d -b kernel | grep "avc: denied" | head
```

### 2.3 复杂 case：组合 5 维度

```bash
# 案例：com.example.app 在 07-27 10:30 出现 ANR
# 5 维度组合：

# 1. 只看 system + main buffer
# 2. 只看 com.example.app 进程
# 3. 只看 ANR / FATAL / die 关键字
# 4. 时间窗：10:30 前后
# 5. level：W 及以上

$ adb logcat -d -b system,main -v threadtime \
  --pid=$(adb shell pidof com.example.app) \
  | grep -E "FATAL|ANR|died" \
  | grep -E "07-27 10:3"
```

---

## 3. 3 种持久化方式

### 3.1 方式 1：实时 tee（开发者本地）

```bash
# 1. 简单 tee
$ adb logcat -v threadtime | tee /tmp/logcat.txt &

# 2. tee + grep
$ adb logcat -v threadtime | tee /tmp/all.txt | grep "MyApp" &

# 3. 限制大小（防止无限增长）
$ adb logcat -v threadtime | tee -a /tmp/logcat.txt & 
# 用 logrotate 定期切
```

**特点**：
- 即时看到
- adb 断 → log 丢
- 仅本地存

### 3.2 方式 2：logcat -d 后转储（一次性抓）

```bash
# 1. 抓全部 main buffer
$ adb logcat -d -b main -v threadtime > /tmp/logcat_main.txt

# 2. 抓多 buffer
$ adb logcat -d -b all -v threadtime > /tmp/logcat_all.txt

# 3. 抓最近 N 行
$ adb logcat -d -T 1000 -v threadtime > /tmp/logcat_1k.txt

# 4. 抓特定时间
$ adb logcat -d -b all -t '07-27 10:30:00.000' -v threadtime > /tmp/logcat_at_1030.txt
```

**特点**：
- 一次性抓
- 当前 buffer 内的全部
- 文件可控

### 3.3 方式 3：properties 持久化（系统级，Android 17 推荐）

```bash
# 1. 启用持久 logcat
$ adb shell setprop persist.logd.logpersistd.enable true

# 2. 启用 logpersistd 服务
$ adb shell setprop persist.logd.logpersistd "logcat -v threadtime"

# 3. logpersistd 自动把 log 写 /data/misc/logd/
$ adb shell ls /data/misc/logd/logpersist/

# 4. 拉取
$ adb pull /data/misc/logd/logpersist/
```

**特点**：
- 系统级（开机自启）
- 写 /data/misc/logd（持久化）
- 适合长期 log 收集

### 3.4 3 种方式对比

| 维度 | tee | logcat -d | logpersistd |
|:-----|:----|:----------|:-----------|
| **实时** | ✅ | ❌ | ✅ |
| **持久** | ❌ | ❌ | ✅ |
| **自动** | ❌ | ❌ | ✅ |
| **可用空间** | 本地 | 本地 | /data/misc |
| **重启后** | 丢 | 丢 | **保留** |
| **何时用** | 调试期 | 一次性 | 长期收集 |

---

## 4. 持久 logcat 配置

### 4.1 properties 配置（AOSP 17）

```bash
# 1. 启用 logpersistd
$ adb shell setprop persist.logd.logpersistd.enable true

# 2. 配置 logpersistd 命令
$ adb shell setprop persist.logd.logpersistd "logcat -v threadtime -b all"

# 3. 限制大小
$ adb shell setprop persist.logd.logpersistd.size 16384  # KB

# 4. 限制文件数
$ adb shell setprop persist.logd.logpersistd.count 4
```

### 4.2 4 类核心 property

| property | 作用 | 默认 |
|:--------|:----|:-----|
| `persist.logd.logpersistd.enable` | 是否启用 | `false` |
| `persist.logd.logpersistd` | logpersistd 命令 | (空) |
| `persist.logd.logpersistd.size` | 单文件大小 KB | 16384 |
| `persist.logd.logpersistd.count` | 文件数 | 4 |

### 4.3 文件路径

```bash
# log 文件路径
$ adb shell ls -la /data/misc/logd/logpersist/
# logcat.1  logcat.2  logcat.3  logcat.4  logcat.5

# 拉取
$ adb pull /data/misc/logd/logpersist/ /tmp/
```

### 4.4 实战：长期收集某 app 的 log

```bash
# 1. 启用 logpersistd
$ adb shell setprop persist.logd.logpersistd.enable true
$ adb shell setprop persist.logd.logpersistd \
    "logcat -v threadtime --pid=$(adb shell pidof com.example.app)"

# 2. 1 小时后拉取
$ adb pull /data/misc/logd/logpersist/ /tmp/1h_logs/

# 3. 关闭
$ adb shell setprop persist.logd.logpersistd.enable false
```

---

## 5. logcat 容量管理

### 5.1 5 大 buffer 容量（AOSP 17 默认）

| buffer | 容量 | 行为 |
|:-------|:-----|:-----|
| main | 4MB | 满后覆盖最早的 |
| system | 256KB | 满后覆盖最早的 |
| crash | 256KB | 满后覆盖最早的 |
| events | 4MB | 满后覆盖最早的 |
| kernel | 1MB | 满后覆盖最早的 |

### 5.2 调整容量

```bash
# 1. 看当前容量
$ adb logcat -g
main: ring buffer is 4.0MB (1 used of 4MB)
system: ring buffer is 256KB (256 used of 256KB)  # 满了

# 2. 临时调大（重启失效）
$ adb shell setprop persist.logd.main 8M
$ adb shell setprop persist.logd.system 1M
$ adb shell setprop persist.logd.kernel 2M
$ adb shell setprop persist.logd.crash 1M
$ adb shell setprop persist.logd.events 8M
```

### 5.3 5 个 OOM 风险场景

```
[场景 1] main buffer 满 + 关键 log 被覆盖
   现象：logcat -d 看不到 30 分钟前的关键 log
   解决：调大 main + 缩短刷屏

[场景 2] system buffer 满（256KB 小）
   现象：init 启动 log 被覆盖，bootloop 看不到
   解决：setprop persist.logd.system 1M

[场景 3] events buffer 满
   现象：systrace 解析丢 events
   解决：setprop persist.logd.events 8M

[场景 4] kernel buffer 满（1MB 小）
   现象：kernel panic 前 log 被覆盖
   解决：setprop persist.logd.kernel 2M

[场景 5] crash buffer 满（256KB 小）
   现象：NE 现场丢部分栈
   解决：setprop persist.logd.crash 1M
```

---

## 6. 实战案例

### 6.1 案例 1：找某 app 5 分钟前 ANR 的根因

```bash
# 1. 确认时间窗
# 当前 10:35，5 分钟前是 10:30

# 2. 5 维度组合过滤
$ adb logcat -d -b system,main -v threadtime \
  --pid=$(adb shell pidof com.example.app) \
  | grep -E "07-27 10:3" \
  | grep -E "FATAL|ANR|died|ANR" \
  > /tmp/anr_rootcause.txt

# 3. 看输出
$ head -30 /tmp/anr_rootcause.txt
```

### 6.2 案例 2：长期 log 收集（7 天）

```bash
# 1. 启用 logpersistd
$ adb shell setprop persist.logd.logpersistd.enable true
$ adb shell setprop persist.logd.logpersistd "logcat -v threadtime -b all"
$ adb shell setprop persist.logd.logpersistd.size 32768  # 32MB per file
$ adb shell setprop persist.logd.logpersistd.count 7  # 7 个文件

# 2. 7 天后拉取
$ adb pull /data/misc/logd/logpersist/ /tmp/7d_logs/
```

### 6.3 案例 3：找 kernel 启动期 OOM

```bash
# 1. 时间窗（boot 后 60 秒）
$ adb logcat -d -b kernel -v threadtime \
  | grep -E "init" \
  | head -100

# 2. 找 OOM kill
$ adb logcat -d -b kernel | grep "Out of memory"
# [12345.678] Out of memory: Killed process 1234 (com.example.app) ...

# 3. 看 memcg
$ adb logcat -d -b kernel | grep "memory cgroup"
```

### 6.4 案例 4：找某 service 多次重启

```bash
# 1. 找 service 重启
$ adb logcat -d -b system | grep "Service.*restarted"

# 2. 找服务死
$ adb logcat -d -b system | grep "Service.*died"

# 3. 找服务退原因
$ adb logcat -d -b system | grep "Process.*died"
```

### 6.5 案例 5：实时监控某 tag

```bash
# 1. 实时监控 + 写入文件
$ adb logcat MyApp:V *:S -v threadtime | tee /tmp/myapp.log &

# 2. 同时在终端看
$ tail -f /tmp/myapp.log

# 3. 找关键字
$ grep "error" /tmp/myapp.log
```

---

## 7. logcat 性能优化

### 7.1 性能问题

**问题**：logcat 频繁调用会拖慢系统

```bash
# 1000+ log/s 时的 CPU 占用：
# - logcat 进程：5-10% CPU
# - logd 服务：3-5% CPU
# - 系统 call 路径：5-10% CPU
# 总计：13-25% CPU
```

### 7.2 5 个优化原则

```
1. 避免 V/D level 在生产环境
2. 控制 log 频率（不要每行 log）
3. 用条件判断
4. 减少字符串拼接
5. 长字符串不直接 log
```

### 7.3 实战：性能优化示例

```java
// 1. 差：每行都 log
for (int i = 0; i < 1000; i++) {
    Log.d(TAG, "Processing item " + i);  // 1000+ log/s
}

// 2. 好：批量 + 采样
int count = 0;
for (int i = 0; i < 1000; i++) {
    processItem(i);
    if (++count % 100 == 0) {  // 每 100 个 log 1 次
        Log.d(TAG, "Processed " + count);
    }
}

// 3. 更好：debug 模式才 log
if (BuildConfig.DEBUG) {
    Log.d(TAG, "Detail: " + largeObject.toString());
}
```

### 7.4 5 个 logcat 性能调优

```bash
# 1. 关 logcat 服务（不可逆，重启恢复）
$ adb shell stop logd

# 2. 调小 buffer
$ adb shell setprop persist.logd.main 1M
$ adb shell setprop persist.logd.system 128K

# 3. 临时静音某个 tag
$ adb shell setprop persist.log.tag.<TAG> SILENT

# 4. 看 logd 自身 log
$ adb logcat -d -b system | grep "logd"

# 5. 重启 logd
$ adb shell stop logd
$ adb shell start logd
```

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [02 Logcat 格式](02-Logcat格式与tag体系.md) | 上篇 |
| [04 Logcat 与 SELinux/avc](04-Logcat与SELinux-avc-denied行解读.md) | 下篇 |
| [Logcat_Complete_Guide](./Logcat_Complete_Guide.md) | 基础命令 |
| [03-Forensics/Bugreport/02 §4 logcat/ 详解](../../../../05-卷5-调查工具链/33-Dumpsys · Bugreport · DropBox/02-Bugreport-目录结构全梳理.md) | bugreport 中 logcat |
| [06-Foundation/Tools/Tracing/20-Trace抓取方法全面指南](../Tracing/20-Trace抓取方法全面指南：ftrace-atrace-systrace-perfetto.md) | trace 配合 logcat |
| [04-Tool/AmCommand/05-诊断与监控-hang-monitor](../../../../05-卷5-调查工具链/33-Dumpsys · Bugreport · DropBox/05-诊断与监控-hang-monitor.md) | hang 监控 |

---

## 9. 下一篇预告 + 自检

### 9.1 下一篇

[04 Logcat 与 SELinux/avc：denied 行解读](04-Logcat与SELinux-avc-denied行解读.md) 讲清：
- 5 大类 logcat 与 SELinux 集成（kernel / main / system / crash / events）
- denied 行的 8 字段精确读法（精简版，[SELinux/04](../../SELinux/04-AVC与avc_denied：从一次denied反推策略.md) 完整版）
- 5 个真实 case：denied 改 .te 的 5 步法
- oncall 现场 5 分钟定位

### 9.2 看完本文的自检

- [ ] 能用 5 大过滤维度组合定位
- [ ] 知道 3 种持久化方式的差异
- [ ] 知道 4 类核心 property
- [ ] 能用 §5 buffer 容量管理
- [ ] 能用 §2.2 5 大事故的过滤模板
- [ ] 能用 §7 性能优化 5 原则

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
