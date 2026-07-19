# am_command_configs/am_command_matrix.md

> **配套文章**:[README-AmCommand系列 §3 am 全命令矩阵](../README-AmCommand系列.md#3-am-全命令矩阵)
>
> **基线**:AOSP `android-14.0.0_r1`

am 命令全量矩阵,按"用得最多"排序,标注系列篇目。

---

## 1. 进程管理类(系列 02 重点)

| 命令 | 作用 | 关键参数 | 实战 |
|------|------|---------|------|
| `am kill <pkg>` | 杀进程(等同 LMKD) | `--user <uid>` | 模拟后台被回收 |
| `am kill-all` | 杀所有后台进程 | 无 | 批量压测前清场 |
| `am force-stop <pkg>` | 强制停止(强杀 + 清任务栈) | `--user <uid>` | 模拟用户从最近任务滑掉 |
| `am crash <pkg>` | 触发 native crash | `--user <uid>` | 模拟 Crash 现场 |
| `am restart` | 重启 system_server | 无 | **慎用** |
| `am send-trim-memory <pid> <level>` | 触发 trimMemory | level: RUNNING_LOW / COMPLETE 等 | 模拟低内存 |

**典型用法**:

```bash
# 模拟后台被回收
adb shell am kill com.example.app

# 模拟用户从最近任务滑掉
adb shell am force-stop com.example.app

# 模拟 Crash(生成 tombstone)
adb shell am crash com.example.app

# 模拟低内存
adb shell am send-trim-memory 12345 RUNNING_LOW
```

---

## 2. 组件启动类(系列 01 重点)

| 命令 | 作用 | 实战 |
|------|------|------|
| `am start <intent>` | 启动 Activity | **最高频** |
| `am start-activity <intent>` | 启动 Activity(显式) | 推荐 |
| `am start-activity -W <intent>` | 启动 + 测耗时 | 冷启动 KPI |
| `am startservice <intent>` | 启动 Service | 验证服务保活 |
| `am stopservice <intent>` | 停止 Service | 验证清理路径 |
| `am broadcast <intent>` | 发送广播 | 测试广播接收器 |
| `am start-foreground-service <intent>` | 启动前台 Service | Android 8+ 限制下验证 |
| `am start-activity --receiver-permission <perm>` | 带权限的启动 | 受保护 receiver |

**典型用法**:

```bash
# 启动 Activity
adb shell am start-activity -n com.example.app/.MainActivity

# 冷启动 + 测耗时
adb shell am start-activity -W -n com.example.app/.MainActivity

# 启动 Service
adb shell am startservice -n com.example.app/.service.MyService

# 发系统广播(模拟网络变化)
adb shell am broadcast -a android.net.conn.CONNECTIVITY_CHANGE

# 发自定义广播
adb shell am broadcast -a com.example.app.CUSTOM_ACTION -n com.example.app/.receiver.MyReceiver
```

---

## 3. 诊断监控类(系列 05 重点)

| 命令 | 作用 | 关键参数 | 实战 |
|------|------|---------|------|
| `am hang [--allow-restart]` | 触发主线程 sleep 模拟 ANR | `--allow-restart` | ANR 现场测试 |
| `am monitor` | 实时监控 GC / Crash / LMK | `--gdb` | 压测期间后台观察 |
| `am stack list` | 列出所有 task stack | 无 | 任务栈异常排查 |
| `am task lock` | 锁定 task | 无 | 后台保活验证 |
| `am task unlock` | 解锁 task | 无 | 同上 |
| `am compat enable <change-id> <pkg>` | 启用 platform compat 行为 | `change-id` | 平台行为切换测试 |
| `am compat reset <pkg>` | 重置 compat 行为 | 无 | 同上 |
| `am get-config` | 获取 device config | 无 | 平台参数验证 |
| `am set-isolated-process <pkg>` | 设置 isolated process | 无 | 进程隔离验证 |
| `am bug-report` | 触发 bug report | 无 | 抓 system log + dropbox |

**典型用法**:

```bash
# 触发 ANR
adb shell am hang com.example.app

# 触发 ANR + 允许重启
adb shell am hang --allow-restart com.example.app

# 实时监控
adb shell am monitor

# 进 native 调试
adb shell am monitor --gdb

# 列出所有 task stack
adb shell am stack list

# 触发 bug report
adb shell am bug-report
```

---

## 4. 内存与性能类(系列 03/04 重点)

| 命令 | 作用 | 关键参数 | 系列篇目 |
|------|------|---------|---------|
| `am dumpheap <pid> <file>` | Java 堆转储 | `-n <uid>`、`-g` | **04** ⬅️ |
| `am profile start <proc> <file>` | 启动 Method Trace | 无 | 03 |
| `am profile start-sampling <proc> <file> <interval>` | Sampling Trace | `interval`: 采样间隔(us) | 03 |
| `am profile stop <proc>` | 停止 + pull trace | 无 | 03 |

**典型用法**:

```bash
# Java 堆 dump(本篇重点)
adb shell am dumpheap <pid> /data/local/tmp/heap.hprof

# 启动 Method Trace
adb shell am profile start com.example.app /data/local/tmp/trace.trace

# 启动 Sampling Trace(每 1000us 采样)
adb shell am profile start-sampling com.example.app /data/local/tmp/sample.trace 1000

# 停止采样
adb shell am profile stop com.example.app
```

---

## 5. 权限管理类

| 命令 | 作用 | 关键参数 |
|------|------|---------|
| `am grant <pkg> <perm>` | 授予权限 | `--user <uid>` |
| `am revoke <pkg> <perm>` | 撤销权限 | `--user <uid>` |
| `am revoke-all <pkg>` | 撤销所有权限 | `--user <uid>` |

**典型用法**:

```bash
# 授予 READ_EXTERNAL_STORAGE
adb shell am grant com.example.app android.permission.READ_EXTERNAL_STORAGE

# 撤销
adb shell am revoke com.example.app android.permission.READ_EXTERNAL_STORAGE
```

---

## 6. 用户管理类

| 命令 | 作用 |
|------|------|
| `am switch-user <uid>` | 切换 user |
| `am stop-user <uid>` | 停止 user |
| `am create-user <name>` | 创建 user |
| `am remove-user <uid>` | 删除 user |
| `am list-users` | 列出 user |

**典型用法**:

```bash
# 切换到 user 10
adb shell am switch-user 10

# 列出所有 user
adb shell am list-users
```

---

## 7. 选型决策树

```
要做什么?
├─ 让 app 行为改变(模拟用户)
│  ├─ 启动页面?     → am start-activity / am start
│  ├─ 启动服务?     → am startservice
│  ├─ 发广播?       → am broadcast
│  └─ 切后台/拉起?  → am start-activity + FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY
│
├─ 让 app 死亡/崩溃
│  ├─ 软杀(等同 LMKD)?  → am kill <pkg>
│  ├─ 强杀(清任务栈)?    → am force-stop <pkg>
│  └─ 主动 crash?        → am crash <pkg>
│
├─ 采集数据
│  ├─ Java 堆?         → am dumpheap (见 04)
│  ├─ Method Trace?    → am profile start (见 03)
│  └─ ANR 现场?        → am hang (见 05)
│
└─ 观察运行状态
   └─ → am monitor (见 05)
```

---

## 8. Android 版本差异速查

| 命令 | Android 11 行为 | Android 12 行为 | Android 14 行为 |
|------|----------------|----------------|----------------|
| `am start` | 强制 `-n` | 强制 `-n` | 强制 `-n` |
| `am dumpheap` | 引入 `-n` | 路径限制 `/data/local/tmp` | SELinux 收紧 |
| `am crash` | OK | OK | OK |
| `am broadcast` | 受限(后台) | 受限 | 受限 |
| `am stack list` | OK | OK | **需 PACKAGE_USAGE_STATS** |
| `am compat enable` | OK | OK | OK |
| `am send-trim-memory` | OK | OK | OK |

---

## 9. 30 秒记忆口诀

> **杀 crash 重启 + 起 service 广播 = am 命令全集**
>
> 杀:`kill` / `force-stop` / `crash` / `restart`
> 起:`start` / `startservice` / `broadcast`
> 采集:`dumpheap` / `profile`
> 监控:`hang` / `monitor` / `stack`

