# Logcat 命令完整指南

## 目录
1. [简介](#简介)
2. [基本语法](#基本语法)
3. [常用命令](#常用命令)
4. [过滤选项](#过滤选项)
5. [格式化选项](#格式化选项)
6. [日志级别](#日志级别)
7. [高级用法](#高级用法)
8. [实战案例](#实战案例)
9. [性能优化](#性能优化)
10. [常见问题](#常见问题)

---

## 简介

`logcat` 是 Android 系统提供的日志查看工具，用于查看系统日志、应用日志和内核日志。它是 Android 开发和调试中最重要的工具之一。

### 基本概念
- **日志缓冲区**：Android 系统维护多个日志缓冲区，包括 main、system、radio、events、crash 等
- **日志标签（Tag）**：每条日志都有一个标签，用于标识日志来源
- **优先级（Priority）**：日志有不同的优先级级别，从低到高为 V、D、I、W、E、F、S

---

## 基本语法

```bash
adb logcat [选项] [过滤器表达式]
```

### 基本示例
```bash
# 查看所有日志
adb logcat

# 查看并清空日志缓冲区
adb logcat -c && adb logcat

# 查看日志并保存到文件
adb logcat > logcat.txt
```

---

## 常用命令

### 1. 查看所有日志
```bash
adb logcat
```

### 2. 清空日志缓冲区
```bash
adb logcat -c
```

### 3. 查看指定缓冲区
```bash
# 查看主缓冲区（默认）
adb logcat -b main

# 查看系统缓冲区
adb logcat -b system

# 查看无线电缓冲区
adb logcat -b radio

# 查看事件缓冲区
adb logcat -b events

# 查看崩溃缓冲区
adb logcat -b crash

# 查看所有缓冲区
adb logcat -b all
```

### 4. 保存日志到文件
```bash
# 保存到文件
adb logcat > logcat.txt

# 追加到文件
adb logcat >> logcat.txt

# 同时显示在终端和保存到文件
adb logcat | tee logcat.txt
```

### 5. 查看日志并退出
```bash
# 查看指定行数后退出
adb logcat -d

# 查看并保存到文件
adb logcat -d > logcat.txt
```

---

## 过滤选项

### 按标签（Tag）过滤
```bash
# 只显示指定标签的日志
adb logcat -s TAG_NAME

# 显示多个标签
adb logcat -s TAG1 TAG2 TAG3

# 使用通配符
adb logcat -s "TAG*"
```

### 按优先级过滤
```bash
# 只显示指定优先级及以上的日志
adb logcat *:PRIORITY

# 优先级级别：
# V - Verbose (最低)
# D - Debug
# I - Info
# W - Warning
# E - Error
# F - Fatal
# S - Silent (最高，不显示任何日志)

# 示例：只显示 Warning 及以上
adb logcat *:W
```

### 组合过滤
```bash
# 格式：tag:priority tag:priority ...
# 只显示指定标签的指定优先级及以上日志

# 示例：显示 SystemUI 的 Error 及以上，其他标签的 Warning 及以上
adb logcat SystemUI:E *:W

# 示例：只显示特定应用的 Debug 及以上日志
adb logcat MyApp:D *:S
```

### 按进程ID过滤
```bash
# 只显示指定进程的日志
adb logcat --pid=12345
```

### 按包名过滤
```bash
# 只显示指定包名的日志
adb logcat | grep "com.example.app"
```

---

## 格式化选项

### 1. 时间格式
```bash
# 显示时间戳（默认格式）
adb logcat -v time

# 显示日期和时间
adb logcat -v long

# 显示可读的时间格式
adb logcat -v threadtime

# 显示原始格式（无时间戳）
adb logcat -v raw

# 显示进程ID和线程ID
adb logcat -v process

# 显示标签和优先级
adb logcat -v tag

# 显示年份
adb logcat -v year

# 显示单调时间
adb logcat -v monotonic

# 显示UTC时间
adb logcat -v UTC

# 显示可读时间（包含年份）
adb logcat -v threadtime -v year
```

### 2. 颜色输出
```bash
# 使用颜色区分不同优先级的日志（需要终端支持）
adb logcat -v color
```

### 3. 组合格式
```bash
# 使用 threadtime 格式（推荐）
adb logcat -v threadtime

# 输出示例：
# 01-28 10:30:45.123  1234  5678 I TagName: Log message
# 日期   时间       PID  TID 级别 标签   消息
```

---

## 日志级别

### 级别说明
| 级别 | 说明 | 使用场景 |
|------|------|----------|
| **V (Verbose)** | 详细信息 | 开发调试时使用，生产环境应关闭 |
| **D (Debug)** | 调试信息 | 调试时使用，帮助定位问题 |
| **I (Info)** | 一般信息 | 记录重要操作和状态变化 |
| **W (Warning)** | 警告信息 | 潜在问题，但不影响功能 |
| **E (Error)** | 错误信息 | 错误发生，但应用可以恢复 |
| **F (Fatal)** | 严重错误 | 严重错误，可能导致崩溃 |
| **S (Silent)** | 静默 | 不显示任何日志 |

### 设置日志级别
```bash
# 在代码中设置
Log.v(TAG, "Verbose message");
Log.d(TAG, "Debug message");
Log.i(TAG, "Info message");
Log.w(TAG, "Warning message");
Log.e(TAG, "Error message");
```

---

## 高级用法

### 1. 实时监控特定日志
```bash
# 监控 ANR 相关日志
adb logcat | grep -i "anr"

# 监控崩溃日志
adb logcat | grep -i "fatal\|crash\|exception"

# 监控特定应用的日志
adb logcat | grep "com.example.app"
```

### 2. 多条件过滤
```bash
# 使用 grep 进行复杂过滤
adb logcat | grep -E "ERROR|WARN" | grep "MyTag"

# 排除某些标签
adb logcat | grep -v "NoisyTag"
```

### 3. 查看历史日志
```bash
# 查看环形缓冲区中的历史日志
adb logcat -d

# 查看并保存历史日志
adb logcat -d > history.log
```

### 4. 监控多个设备
```bash
# 列出所有设备
adb devices

# 指定设备查看日志
adb -s DEVICE_ID logcat
```

### 5. 清除特定标签的日志
```bash
# 清除所有日志
adb logcat -c

# 清除后立即开始记录
adb logcat -c && adb logcat
```

### 6. 限制日志输出
```bash
# 限制缓冲区大小（需要 root）
adb logcat -G 4M

# 查看当前缓冲区大小
adb logcat -g
```

### 7. 使用 logcat 调试 ANR
```bash
# 监控主线程阻塞
adb logcat | grep -E "ANR|am_anr|ActivityManager"

# 监控系统负载
adb logcat | grep -E "lowmemorykiller|lmkd|ActivityManager"
```

### 8. 使用 logcat 调试崩溃
```bash
# 监控崩溃日志
adb logcat -b crash

# 监控 Java 异常
adb logcat | grep -i "exception\|error\|fatal"

# 监控 Native 崩溃
adb logcat | grep -i "tombstone\|signal\|abort"
```

---

## 实战案例

### 案例1：调试应用启动问题
```bash
# 1. 清空日志
adb logcat -c

# 2. 启动应用
adb shell am start -n com.example.app/.MainActivity

# 3. 查看启动相关日志
adb logcat -v threadtime | grep -E "ActivityManager|com.example.app"
```

### 案例2：监控内存问题
```bash
# 监控内存相关日志
adb logcat | grep -iE "lowmemory|oom|gc|memory"
```

### 案例3：调试网络问题
```bash
# 监控网络相关日志
adb logcat | grep -iE "network|http|socket|connection"
```

### 案例4：调试性能问题
```bash
# 监控性能相关日志
adb logcat | grep -iE "slow|performance|lag|jank"
```

### 案例5：完整的调试流程
```bash
# 1. 清空日志并开始记录
adb logcat -c
adb logcat -v threadtime > debug.log &

# 2. 执行操作（复现问题）

# 3. 停止记录
kill %1

# 4. 分析日志
cat debug.log | grep -i "error\|exception\|crash"
```

### 案例6：监控系统事件
```bash
# 查看系统事件缓冲区
adb logcat -b events

# 查看特定事件
adb logcat -b events | grep -E "am_|wm_|sys_"
```

---

## 性能优化

### 1. 减少日志输出
```bash
# 只显示重要日志（Warning 及以上）
adb logcat *:W

# 排除噪音标签
adb logcat | grep -v "NoisyTag1\|NoisyTag2"
```

### 2. 使用缓冲区
```bash
# 查看特定缓冲区，减少数据量
adb logcat -b main

# 而不是查看所有缓冲区
# adb logcat -b all  # 数据量大，可能影响性能
```

### 3. 限制日志文件大小
```bash
# 使用 head 限制输出行数
adb logcat | head -n 1000

# 使用 tail 只查看最新日志
adb logcat | tail -n 100
```

### 4. 后台运行
```bash
# 后台运行并保存到文件
adb logcat > logcat.txt &

# 查看进程
jobs

# 停止后台任务
kill %1
```

---

## 常见问题

### Q1: logcat 没有输出怎么办？
```bash
# 检查 adb 连接
adb devices

# 检查设备是否授权
# 在设备上点击"允许 USB 调试"

# 尝试重启 adb
adb kill-server
adb start-server
```

### Q2: 如何查看更早的日志？
```bash
# 查看环形缓冲区中的历史日志
adb logcat -d

# 注意：缓冲区大小有限，更早的日志可能已被覆盖
```

### Q3: 日志太多，如何过滤？
```bash
# 使用过滤器表达式
adb logcat MyApp:D *:S

# 使用 grep 进一步过滤
adb logcat | grep "keyword"
```

### Q4: 如何查看特定时间段的日志？
```bash
# 使用脚本记录并过滤
adb logcat -v time | awk '/2026-01-28 10:00:00/,/2026-01-28 11:00:00/'
```

### Q5: 如何查看 Native 日志？
```bash
# Native 日志通常使用 __android_log_print
# 查看所有日志，Native 日志会显示
adb logcat

# 查看特定标签
adb logcat -s native_tag
```

### Q6: 日志缓冲区满了怎么办？
```bash
# 清空缓冲区
adb logcat -c

# 增加缓冲区大小（需要 root）
adb root
adb logcat -G 16M
```

### Q7: 如何同时查看多个标签？
```bash
# 使用多个 -s 选项
adb logcat -s Tag1 -s Tag2 -s Tag3

# 或使用过滤器表达式
adb logcat Tag1:D Tag2:D Tag3:D *:S
```

### Q8: 如何查看系统启动日志？
```bash
# 系统启动日志在 main 缓冲区
adb logcat -b main -d

# 查看更详细的启动日志
adb logcat -b all -d | grep -i "boot\|startup\|init"
```

---

## 最佳实践

### 1. 开发阶段
- 使用 `-v threadtime` 格式，便于定位问题
- 使用合适的日志级别，避免过多 Verbose 日志
- 使用有意义的标签名称

### 2. 调试阶段
- 先清空日志缓冲区：`adb logcat -c`
- 使用过滤器减少噪音：`adb logcat MyApp:D *:S`
- 保存日志到文件便于分析：`adb logcat > debug.log`

### 3. 生产环境
- 关闭 Verbose 和 Debug 日志
- 只记录重要的 Info、Warning 和 Error
- 使用远程日志收集系统

### 4. 性能分析
- 使用 `-b main` 只查看主缓冲区
- 避免使用 `-b all`，数据量太大
- 使用过滤器减少输出

### 5. 问题排查
- 记录问题发生前后的完整日志
- 使用时间戳定位问题发生时间
- 结合其他工具（如 systrace、dumpsys）一起分析

---

## 相关工具

### 1. Android Studio Logcat
- 图形化界面，更易使用
- 支持过滤、搜索、导出
- 支持多设备同时查看

### 2. Logcat Reader
- 第三方工具，功能更强大
- 支持日志分析、统计
- 支持正则表达式过滤

### 3. 脚本工具
```bash
# 创建便捷脚本
#!/bin/bash
# logcat_debug.sh
adb logcat -c
adb logcat -v threadtime | grep -E "$1"
```

---

## 总结

`logcat` 是 Android 开发和调试的核心工具，掌握其使用方法对于：
- **问题定位**：快速找到错误和异常
- **性能分析**：了解系统运行状态
- **行为监控**：跟踪应用和系统行为
- **稳定性分析**：排查 ANR、崩溃等问题

通过合理使用过滤、格式化和缓冲区选项，可以大大提高调试效率。

---

## 参考资源

- [Android 官方文档 - Logcat](https://developer.android.com/studio/command-line/logcat)
- [ADB 官方文档](https://developer.android.com/studio/command-line/adb)
- Android 源码：`system/core/logcat/`

---

*最后更新：2026-01-28*
