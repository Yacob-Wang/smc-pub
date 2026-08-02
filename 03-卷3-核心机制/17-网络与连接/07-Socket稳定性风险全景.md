# Socket 07：稳定性风险全景

> **系列**：面向稳定性的 Android Socket 子系统深度解析系列(Socket)
>
> **源码基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)
>
> **内核矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇风险涉及 `net/core/sock.c`、`net/ipv4/tcp.c`、`net/unix/af_unix.c`、`include/net/sock.h`;Android 14 SELinux socket class 限制见 §3)
>
> **目标读者**:Android 稳定性框架架构师
>
> **前置阅读**:本系列 01-06 全篇
>
> **下一篇**:[08-Socket 诊断工具与治理体系](08-Socket诊断工具与治理体系.md)

> 面向 Android 稳定性架构师：把 socket 系列 6 大场景的所有风险统一为一张"风险地图"——按"6 大场景"和"5 大类风险"两个维度交叉，**让你 5 分钟内定位线上问题在 socket 哪个层面、怎么查、怎么防**。

---

## 本篇定位

- **本篇系列角色**:Socket 系列第 7 篇「稳定性风险全景」(socket 系列 8 篇规划"第三篇章:诊断实战与治理"的入口;与 01/04/05/06 各篇"零散风险"对应,本篇做**风险收口**)
- **强依赖**:
  - [Socket 01-Socket总览](01-Socket总览.md)(6 大场景的"全图",本篇的"6 大场景风险矩阵"建立在此之上)
  - [Socket 04-Socket缓冲区与数据收发](04-Socket缓冲区与数据收发.md)(§3.5 阻塞/EAGAIN、§4 风险地图——本篇合并其 P0 风险)
  - [Socket 05-listen_backlog与连接队列](05-listen_backlog与连接队列.md)(§4 风险地图、ListenDrops/ListenOverflows 监控指标)
  - [Socket 06-Unix_Domain_Socket与Android使用](06-Unix_Domain_Socket与Android使用.md)(§5 UDS 风险地图、abstract 命名冲突)
  - [epoll 01-epoll总览与核心机制](../epoll/01-epoll总览与核心机制.md)(§6 风险地图、ET/LT 误用)
  - [IO 06-IO 与进程的深度耦合](../../IO/06-IO与进程的深度耦合：D状态、iowait、IO-hang、进程阻塞.md)(D 状态、wait queue 唤醒——socket 阻塞时关联)
- **承接自**:socket 04/05/06 各篇"风险速查表"分散在 §4-§5;本篇把它们合并为**统一的风险图**——按"6 大场景"和"5 大类"两个维度交叉
- **衔接去**:本篇末尾会预告下一篇 [08-Socket诊断工具与治理体系](08-Socket诊断工具与治理体系.md) 给出"5 分钟内定位 + 治理"工具集
- **不重复内容**:风险的具体机制(如 ET/LT 原理、SO_SNDBUF 细节)——由强依赖文章承担;本篇只做**风险收口 + 排查路径决策树**

#### §0 锚点案例的可验证 4 件套:某 App 上线后 FD 飙到 8000,LMKD 杀进程,雪崩

> **环境**:
> - 设备:某机型线上统计(Pixel 6 占比 30%)
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI(`/proc/sys/fs/file-max` 默认 187218)
> - App:某 IM App v7.3(脱敏代号 `ChatApp`,新版上线后接入新 SDK)
> - 工具:`dumpsys meminfo --package` + `ls /proc/<pid>/fd | wc -l` + `dumpsys activity processes` + LMKD 日志

> **复现步骤**:
> 1. 灰度发布 ChatApp v7.3 到 10% 用户
> 2. 监控大盘发现 ChatApp 进程 FD 数从基线 200 飙到 8000(24h 内)
> 3. `dumpsys meminfo com.chat.app` 看 fd 统计 + LMKD 日志
> 4. `ls /proc/$(pidof com.chat.app)/fd | wc -l` + `cat /proc/$(pidof com.chat.app)/status | grep Threads`
> 5. 5 天内 LMKD 杀进程次数从 1/天 涨到 50/天,用户反馈"App 频繁被杀"

> **logcat / dumpsys 关键片段**:
> ```
> # dumpsys meminfo com.chat.app
> Applications Memory Usage (kB):
> ...
>   FDs:  8000 / 32768   ← 8000 个 FD 占上限 24%
>   Threads: 256 / 2048  ← 线程数 256 也偏多
> # /proc/$(pidof com.chat.app)/status
> FDSize: 32768
> Threads: 256
> ...
> # LMKD 日志
> lowmemorykiller: Kill com.chat.app (pid 12345) due to memory pressure (FDs: 8000)
> # ss -tan(看 socket 类型分布)
> ESTAB  5234
> TIME-WAIT  1234
> CLOSE-WAIT  123
> ...
> # lsof -p $(pidof com.chat.app) | grep -c unix
> 1832   ← UDS 占大头,SDK 的匿名 UDS pair 泄漏
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/sdk/src/main/cpp/conn_manager.cpp
> +++ b/sdk/src/main/cpp/conn_manager.cpp
> @@ connection_manager::release_connection()
> -    // 旧版:连接池满时新建连接,旧的仅 close 一边
> -    if (pool_.size() > MAX_POOL) {
> -        auto old = pool_.front();
> -        old->close();   // 只 close 应用层
> -        pool_.pop_front();
> -    }
> +    // 修复:关闭连接时双向 close UDS pair,FD 引用计数归零
> +    if (pool_.size() > MAX_POOL) {
> +        auto old = pool_.front();
> +        old->closeFdPair();   // 双 close + shutdown(SHUT_RDWR)
> +        pool_.pop_front();
> +    }
> ```
> ```diff
> --- a/build.gradle
> +++ b/build.gradle
> @@ dependencies
> -    implementation 'com.thirdpartysdk:conn-sdk:3.2.0'
> +    implementation ('com.thirdpartysdk:conn-sdk:3.3.0') {
> +        // SDK 升级:修复 FD 泄漏,3.2.0 → 3.3.0 释放 6000 个 fd 槽位
> +        exclude group: 'com.thirdpartysdk', module: 'leaky-uds'
> +    }
> ```
> 完整 FD 泄漏 ↔ socket 类型分布 ↔ LMKD ↔ 治理决策树见 §2-§7。

> 面向 Android 稳定性架构师：把 socket 系列 6 大场景的所有风险统一为一张"风险地图"——按"6 大场景"和"5 大类风险"两个维度交叉，**让你 5 分钟内定位线上问题在 socket 哪个层面、怎么查、怎么防**。

## 一、背景与定义

### 1.1 什么是"风险全景"

风险全景是把分散在 socket 各篇的"零散风险点"汇总成**可指导实战的"排查工具"**——它不是新知识，而是把已知风险**重新组织**成便于现场排查的形式。

**为什么需要这张图**：

- **实战场景**：线上反馈"app 无法联网"或"触摸无响应"——你需要 5 分钟内判断"这是 socket 哪一类问题"
- **零散风险不可用**：socket 04 §4 给了 12 个风险、socket 05 §4 给了 11 个、socket 06 §5 给了 12 个——35+ 个风险在不同文档里，**没有交叉视角**就难以定位
- **两个维度的价值**：
  - **按"6 大场景"** → "我在排查 InputChannel 还是 Zygote？"
  - **按"5 大类风险"** → "是 FD 耗尽还是主线程阻塞？"
  - **两者交叉** → "InputChannel 的 FD 耗尽 / Zygote 的主线程阻塞"——直接命中

### 1.2 风险全景的两个维度

```
         │  ① FD 耗尽   │  ② 主线程阻塞  │  ③ 队列积压  │  ④ 协议失败  │  ⑤ 权限/路径 │
─────────┼──────────────┼───────────────┼─────────────┼──────────────┼─────────────│
Zygote   │   P2         │   P0 启动 ANR │   P1 排队   │   P0 拒连   │   P0 启动失败│
InputCh  │   P0 触摸无  │   P0 ANR      │   P0 满     │   P1 拒连   │   P2 少     │
Choreog  │   P1 丢帧    │   P0 丢帧     │   P0 满     │   P2 少     │   P2 少     │
adb      │   P1 adb挂   │   P2 少       │   P0 假死   │   P0 拒连   │   P0 adb 不可用│
Local    │   P0 服务挂  │   P1 daemon卡 │   P1 排队   │   P0 拒连   │   P0 selinux│
网络     │   P0 联网失败│   P0 ANR      │   P0 TIME_WAIT│  P0 TCP 错  │   P2 少     │

P0 = 用户直接感知（ANR/无响应/无法使用）
P1 = 性能/次级影响（卡顿/慢/偶尔失败）
P2 = 偶发/低概率（需特殊场景触发）
```

**关键观察**：

- **P0 高频在"主线程阻塞"列**——这是 socket 相关 ANR 的主要来源
- **P0 高频在"协议失败"列**——TCP 握手失败、UDS 路径错
- **Zygote 和 adb 的"权限/路径"列是 P0**——vendor 改错配置直接瘫痪
- **"队列积压"在 4 个场景都是 P0**——缓冲满 = 用户感知

### 1.3 与其他 4 篇的关系

| 已有文章 | 提供的"零散风险" | 本篇的"汇总" |
|----------|------------------|--------------|
| 01 总览 | 三大根本风险（FD 耗尽/主线程阻塞/队列积压） | 横向扩展到 5 大类 |
| 04 缓冲区 | 12 个缓冲区风险 | 整合到"队列积压" + "主线程阻塞" |
| 05 backlog | 11 个 TCP 风险 | 整合到"协议失败" + "队列积压" |
| 06 UDS | 12 个 UDS 风险 | 整合到"权限/路径" + "FD 耗尽" |
| epoll 01 | ET/LT 风险、wakeup 风险 | 整合到"主线程阻塞" + "FD 耗尽" |

**本篇是 socket 系列的"风险枢纽"**——后续 08 诊断工具和治理会引用本篇的风险分类。

---

## 二、6 大场景风险矩阵

### 2.1 ① Zygote Socket（UDS SOCK_STREAM）

| 风险 | 等级 | 触发条件 | 现象 | 排查入口 |
|------|------|----------|------|----------|
| 启动 ANR | P0 | Zygote accept 慢 | app 启动黑屏 5s+ | ANR trace 中 Zygote 栈 |
| fork 失败 | P0 | Zygote 路径被改/selinux 错 | AMS 日志 `Process: skipped` | `ls -lZ /dev/socket/zygote` |
| accept 慢 | P0 | Zygote 业务卡 | 进程启动 ANR | `dumpsys activity processes` |
| usap fd 泄漏 | P1 | usap 进程异常退出 | Zygote 监听集合膨胀 | `ls /proc/<pid>/fd \| wc -l` |
| 路径权限被改 | P0 | vendor OTA 漏 restorecon | 所有 app 启动失败 | `restorecon` + 监控 |
| abstract 命名冲突 | P2 | `@zygote` 与其他冲突 | bind 失败 | `/proc/net/unix` |

### 2.2 ② InputChannel（UDS SOCK_SEQPACKET）

| 风险 | 等级 | 触发条件 | 现象 | 排查入口 |
|------|------|----------|------|----------|
| 触摸无响应 | P0 | app 主线程不消费 | `Consumer is not responding` | `dumpsys input` |
| ANR | P0 | InputChannel buffer 满 + 主线程卡 | Input ANR trace | ANR trace 中 `MessageQueue.next` |
| fd 泄漏 | P0 | `InputEventReceiver` 未 dispose | 单进程 fd 增长 | `ls /proc/<pid>/fd \| wc -l` |
| eventfd wakeup 失败 | P0 | wakeup fd 未设 NONBLOCK | 整个 Input 停摆 | systrace `epoll_wait` |
| 序列包顺序错乱 | P2 | seqpacket 内核 bug（极少） | 触摸位置错乱 | InputFlinger 调试 |
| InputChannel 未正确注册 | P1 | window 异常退出 | 当前 window 触摸无响应 | `dumpsys window` |

### 2.3 ③ Choreographer BitTube（UDS SOCK_STREAM socketpair）

| 风险 | 等级 | 触发条件 | 现象 | 排查入口 |
|------|------|----------|------|----------|
| 丢帧 | P0 | 主线程卡顿 | 帧率 60→30 fps | `dumpsys gfxinfo` |
| BitTube 满 | P0 | VSync 频率高（90/120Hz）+ 主线程卡 | VSync 积压 | `dumpsys SurfaceFlinger` |
| Buffer 太小 | P1 | bufsize 设过小 | 高频 VSync 溢出 | `BitTube.cpp` 编译期常量 |
| 帧抖动 | P1 | 主线程没及时处理 VSync | 帧间隔不均 | systrace `Choreographer` |
| 渲染线程未启动 | P2 | 极少见 | 完全无画面 | `dumpsys SurfaceFlinger` |

### 2.4 ④ adb (adbd)（TCP）

| 风险 | 等级 | 触发条件 | 现象 | 排查入口 |
|------|------|----------|------|----------|
| adb 不可用 | P0 | adbd 进程挂/端口被占 | `adb devices` 看不到 | `pidof adbd` + `netstat` |
| adb 假死 | P0 | 全连接队列满 | adb shell 卡几十秒 | `ListenDrops` |
| SYN flood | P0 | vendor 关 SYN cookie | 正常 adb 连接被拒 | `ListenOverflows` + `tcp_syncookies` |
| 无线调试配对失败 | P1 | mDNS / TLS 配置 | adb pair 失败 | `adb pair` 日志 |
| 端口被占 | P0 | 5555 被其他进程占 | adb 启动失败 | `lsof -i :5555` |
| adbd 重启残留 | P1 | `/dev/socket/adbd` 残留 | bind 失败 | `rm /dev/socket/adbd` |

### 2.5 ⑤ LocalSocket / LocalServerSocket（UDS）

| 风险 | 等级 | 触发条件 | 现象 | 排查入口 |
|------|------|----------|------|----------|
| 路径权限 | P0 | chmod 改错 | 服务不可用 | `ls -lZ /dev/socket/<name>` |
| selinux 失败 | P0 | label 改错 | `avc: denied` | `dmesg \| grep -i avc` |
| abstract 命名冲突 | P0 | 多个进程用同名 | EADDRINUSE | 应用层日志 |
| 路径残留 | P0 | 进程退出未 unlink | 后续 bind 失败 | `ls /dev/socket/` |
| daemon 处理慢 | P1 | 业务卡 | client 反压 | strace + systrace |
| fd 泄漏 | P0 | 异常路径未 close | EMFILE | `ls /proc/<pid>/fd \| wc -l` |

### 2.6 ⑥ 网络请求（TCP）

| 风险 | 等级 | 触发条件 | 现象 | 排查入口 |
|------|------|----------|------|----------|
| EMFILE | P0 | fd 耗尽 | 新连接失败 | `ls /proc/<pid>/fd \| wc -l` |
| TIME_WAIT 多 | P0 | 短连接高频 | 端口耗尽 | `netstat -n \| grep TIME_WAIT` |
| 主线程 IO | P0 | 主线程做网络请求 | ANR | ANR trace 中网络栈 |
| TCP 建连慢 | P1 | DNS / 握手慢 | 请求延迟 | tcpdump + strace |
| SO_RCVBUF 调大后 OOM | P0 | 连接数 × 缓冲 = GB 级 | 内存爆炸 | `/proc/<pid>/net/tcp` |
| TCP 重传多 | P1 | 网络差 | 请求失败 | `netstat -s \| grep retrans` |
| 协议版本错 | P1 | 用了被禁用的 TLS 版本 | TLS 握手失败 | openssl s_client |
| 长连接断开 | P1 | NAT/防火墙超时 | 连接莫名断 | `SO_KEEPALIVE` 调试 |

### 2.7 风险矩阵的"热力"视图

```
        ①FD耗尽  ②主线程阻塞  ③队列积压  ④协议失败  ⑤权限/路径
Zygote    ░░       ▓▓▓▓        ▒▒▒        ▓▓▓▓       ▓▓▓▓
InputCh   ▓▓▓▓     ▓▓▓▓        ▓▓▓▓       ▒▒▒        ░░
Choreog   ▒▒▒      ▓▓▓▓        ▓▓▓▓       ░░         ░░
adb       ▒▒▒      ▒▒▒         ▓▓▓▓       ▓▓▓▓       ▓▓▓▓
Local     ▓▓▓▓     ▒▒▒         ▒▒▒        ▓▓▓▓       ▓▓▓▓
网络      ▓▓▓▓     ▓▓▓▓        ▓▓▓▓       ▓▓▓▓       ▒▒▒

▓▓▓▓ P0（用户直接感知）  ▒▒▒ P1（性能影响）  ░░ P2（偶发）
```

**关键观察**：

- **"主线程阻塞" + "队列积压"** 几乎在所有场景都是 P0——**Android socket 风险的两大主轴**
- **"权限/路径"在 Zygote/adb/Local 三个系统服务场景是 P0**——vendor 必须重视
- **网络场景 4 类风险都很高**——业务层 socket 代码最容易踩坑

---

## 三、5 大类风险专题

### 3.1 类 ① FD 耗尽（EMFILE / ENFILE）

> **详见**：socket 01 §5、04 §4、06 §5

#### 3.1.1 触发机制

```
进程 fd 持续增长
  ↓
达到 RLIMIT_NOFILE（Android 默认 32768）
  ↓
新 socket()/open() 返回 EMFILE
  ↓
所有 fd 类操作失败
```

#### 3.1.2 三大典型场景

**场景 A：app 端 InputChannel 漏关**（InputChannel onDetachedFromWindow 未 dispose）

```
每次 View 重建 +2 个 fd
100 次重建 +200 个 fd
高频操作 1 天 +10000+ 个 fd
触发 EMFILE
```

**场景 B：app 端 LocalSocket 异常路径未 close**

```java
Selector.open();  // 3 个 fd：epoll + pipe0 + pipe1
catch (IOException e) {
    // 忘了 close
}
```

**场景 C：system_server 端 fd 增长**

```
系统服务长期运行
监听多 socket
+1 漏关 = 永久泄漏
```

#### 3.1.3 排查路径

```
EMFILE 错误
  ↓
ls /proc/<pid>/fd | wc -l  ← 进程 fd 数
  ↓
ls /proc/<pid>/fd | awk '{print $NF}' | sort | uniq -c  ← fd 类型统计
  ↓
定位泄漏源头（看哪种 fd 占比异常）
  ↓
heap dump + fdsan 配合
  ↓
业务代码审查（add/remove 配对、异常路径 close）
```

#### 3.1.4 监控指标

```bash
# 进程级
WARN > 80% × RLIMIT_NOFILE
EMERG > 95% × RLIMIT_NOFILE

# 系统级
WARN > 80% × file-max
EMERG > 95% × file-max
```

#### 3.1.5 工程防护

- **fdsan 必须开启**（Android 14+）
- **try-with-resources / try-finally 严格配对**
- **app 层不要持有未配对 fd**（每次 open 都对应 close）
- **CI 校验**：跑 30 分钟业务场景，fd 数不能单调增长

---

### 3.2 类 ② 主线程阻塞

> **详见**：socket 04 §3.5、epoll 01 §6.1

#### 3.2.1 触发机制

```
app 主线程做 socket IO
  ↓
阻塞 send/recv → 主线程进 S 状态
  ↓
InputDispatcher 等不到主线程消费 input
  ↓
5 秒超时 → Input ANR
```

#### 3.2.2 五大常见模式

**模式 A：主线程直接发网络请求**（最常见）

```java
// 错误
public void onResume() {
    super.onResume();
    sendHttpRequest();  // 同步阻塞
}

// 正确
public void onResume() {
    super.onResume();
    runOnThread(this::sendHttpRequest);
}
```

**模式 B：主线程读 InputChannel**（隐性阻塞）

```java
// 错误：阻塞读 input
InputEvent event = new InputEvent();
channel.receive(event);  // 阻塞
// 正确：用 InputEventReceiver 的回调
```

**模式 C：主线程读 Choreographer BitTube**

VSync 是高频事件，主线程不读就丢帧。

**模式 D：主线程做 zygote fork 等 IPC**

```java
// 错误
Process.start(...);  // 同步等 fork
```

**模式 E：主线程在 onCreate/onResume 同步初始化**

任何长于 100ms 的同步操作都是 P0 风险。

#### 3.2.3 排查路径

```
ANR trace
  ↓
主线程栈 → 看是否有 socket/connect/read/write
  ↓
是 → 业务代码改异步
  ↓
否 → 看 InputDispatcher 是否在等主线程
  ↓
是 → 主线程卡在别处（如同步 IO、锁等待、死循环）
```

#### 3.2.4 工程防护

- **StrictMode 开启** `detectNetwork` + `detectCustomSlowCalls`
- **业务层 Lint 规则**：禁止主线程做网络/IO
- **CI 校验**：主线程阻塞超过 100ms 即报警

---

### 3.3 类 ③ 队列积压（缓冲满 / backlog 满）

> **详见**：socket 04 §4、05 §4

#### 3.3.1 三大缓冲类型

| 缓冲 | 上限 | 满时行为 |
|------|------|----------|
| **socket sk_buff 队列** | `SO_SNDBUF` / `SO_RCVBUF`（×2 弹性） | send 阻塞或 EAGAIN |
| **全连接队列** | `min(backlog, somaxconn)` | 丢 ACK / RST |
| **半连接队列** | `tcp_max_syn_backlog` | SYN cookie / 丢 SYN |

#### 3.3.2 五大典型场景

**场景 A：InputChannel 缓冲满**

- 8-32 消息上限
- 主线程卡 → app 端不读 → 满 → InputDispatcher 写阻塞 → 触摸无响应

**场景 B：BitTube 缓冲满**

- 8KB-64KB 上限
- 主线程卡 → app 端不读 → VSync 积压 → 丢帧

**场景 C：全连接队列满**（adbd 假死）

- `ListenDrops` 增长
- 客户端连不上 / 卡几十秒

**场景 D：半连接队列满**（SYN flood）

- `ListenOverflows` 增长
- 正常连接被拒

**场景 E：网络 socket 单连接占满**

- SO_RCVBUF 调大后被对端"灌包"
- 单连接 1MB+ 内存

#### 3.3.3 排查路径

```
队列满
  ↓
ss -m / ss -lnt  ← 看 Send-Q / Recv-Q
  ↓
cat /proc/net/netstat | grep -i listen  ← ListenDrops / ListenOverflows
  ↓
dumpsys input / dumpsys SurfaceFlinger  ← Android 专用
  ↓
定位"谁在写"和"谁没读"
```

#### 3.3.4 工程防护

- **进程 fd 数监控 + Recv-Q 监控**
- **背压机制**：业务层要"边读边处理"，不能"积压到一定量再读"
- **资源上限**：连接池 × buffer = 内存上限，要设上限

---

### 3.4 类 ④ 协议失败

> **详见**：socket 01 §3、03 §3、05 §3.5

#### 3.4.1 五大典型场景

**场景 A：TCP 三次握手失败**

- 网络差 / 防火墙 / 服务端未 listen
- 客户端 connect 返回 ETIMEDOUT 或 ECONNREFUSED

**场景 B：TCP 半连接超时**

- `tcp_synack_retries=5` 默认（60+ 秒）
- SYN flood 期间被丢

**场景 C：UDS 路径不对**

- 服务端未启动 / 路径权限错
- 客户端 connect 返回 ENOENT 或 EACCES

**场景 D：abstract namespace 冲突**

- 第二个 bind 失败 EADDRINUSE

**场景 E：协议版本错**（TLS / HTTP/2）

- TLS 版本不匹配
- HTTP/2 SETTINGS 帧失败

#### 3.4.2 排查路径

```
协议失败
  ↓
strace 看 syscall 错误码
  ↓
errno 解读：
  · ETIMEDOUT → 超时（网络差 / 服务端慢 / 全连接队列满）
  · ECONNREFUSED → 拒绝（服务端未 listen / 防火墙）
  · EACCES → 权限（UDS 路径 / selinux）
  · ENOENT → 路径不存在（UDS 路径错）
  · EADDRINUSE → 端口占用 / abstract 冲突
  · EHOSTUNREACH → 路由问题
```

#### 3.4.3 工程防护

- **客户端合理超时**（不要用默认 75 秒）
- **重试 + 退避**（指数退避）
- **服务端 `tcp_abort_on_overflow=1`**（避免客户端等几十秒）
- **业务层协议版本协商**（TLS 1.2+ / HTTP/1.1 fallback）

---

### 3.5 类 ⑤ 权限/路径

> **详见**：socket 06 §4.5、§5.2

#### 3.5.1 三大典型场景

**场景 A：vendor OTA 后 selinux label 错**

```
restorecon 漏跑
  ↓
service 启动失败
  ↓
整设备瘫痪
```

**场景 B：路径权限被 chmod 改错**

```
chmod 0666 /dev/socket/zygote
  ↓
所有 app 可连 zygote
  ↓
安全 + 稳定性双失
```

**场景 C：abstract namespace 命名冲突**

```
App A：new LocalServerSocket("@server")
App B：new LocalServerSocket("@server")
  ↓
第二个 bind 失败
```

#### 3.5.2 排查路径

```
权限/路径问题
  ↓
ls -lZ /dev/socket/<name>  ← 权限 + selinux
  ↓
dmesg | grep -i avc  ← selinux 拒绝
  ↓
cat /proc/net/unix  ← abstract 冲突
  ↓
fuser /dev/socket/<name>  ← 路径占用
```

#### 3.5.3 工程防护

- **CI 校验关键 socket 路径的权限和 selinux label**
- **OTA 流程必须 `restorecon`**
- **abstract namespace 命名规范**（加包名前缀）
- **路径残留清理**（unlink 在 unbind 时）

---

## 四、监控指标全景

### 4.1 进程级指标

| 指标 | 命令 | 告警阈值 | 关联风险 |
|------|------|----------|----------|
| 进程 fd 数 | `ls /proc/<pid>/fd \| wc -l` | > 80% × RLIMIT_NOFILE | ① FD 耗尽 |
| 进程 socket fd 数 | `ls /proc/<pid>/fd \| grep socket \| wc -l` | 视业务 | ① FD 耗尽 |
| 进程 socket 内存 | `cat /proc/<pid>/net/tcp` | > 进程 RSS 20% | ③ 队列积压 |
| InputChannel 队列 | `dumpsys input` | Recv-Q > 8 | ② 主线程阻塞 + ③ 队列积压 |
| BitTube 队列 | `dumpsys SurfaceFlinger` | Recv-Q 持续 > 0 | ② 主线程阻塞 + ③ 队列积压 |
| 单 socket Recv-Q | `ss -m` | > 80% × SO_RCVBUF | ③ 队列积压 |
| 单 socket Send-Q | `ss -m` | > 80% × SO_SNDBUF | ③ 队列积压 |

### 4.2 系统级指标

| 指标 | 命令 | 告警阈值 | 关联风险 |
|------|------|----------|----------|
| 系统 fd 数 | `cat /proc/sys/fs/file-nr` | > 80% × file-max | ① FD 耗尽 |
| TCP socket 数 | `cat /proc/net/sockstat` | 视业务 | ① FD 耗尽 |
| 全机 socket 内存 | `cat /proc/sys/net/ipv4/tcp_mem` | 接近上限 | ③ 队列积压 |
| TIME_WAIT 数 | `netstat -n \| grep TIME_WAIT \| wc -l` | > 5000 | ③ 队列积压 |
| ListenOverflows | `cat /proc/net/netstat` | > 0 立即告警 | ③ 半连接队列满 |
| ListenDrops | `cat /proc/net/netstat` | > 0 立即告警 | ③ 全连接队列满 |
| SyncookiesSent | `cat /proc/net/netstat` | 突增告警 | ③ SYN flood 早期 |
| ListenOverflows 增长率 | 同上 | > 100/s 告警 | ④ 协议失败（攻击） |
| adb 端口状态 | `netstat -lnt \| grep 5555` | 端口未监听告警 | ⑤ adb 不可用 |
| `/dev/socket/` 残留 | `ls /dev/socket/` | 与 init 配置不一致 | ⑤ 路径权限 |

### 4.3 CI 校验项

```bash
# 关键 socket 路径权限
for path in /dev/socket/zygote /dev/socket/installd /dev/socket/vold; do
    perm=$(adb shell stat -c '%a %U %G' $path)
    expected="660 root 10110"
    if [ "$perm" != "$expected" ]; then
        echo "FAIL: $path 权限异常 $perm (期望 $expected)"
    fi
done

# selinux label
for path in /dev/socket/*; do
    adb shell ls -lZ $path | grep -q "u:object_r" || echo "FAIL: $path 缺 selinux label"
done

# 系统参数
for param in net.core.somaxconn net.ipv4.tcp_syncookies net.ipv4.tcp_abort_on_overflow; do
    val=$(adb shell cat /proc/sys/${param//.//})
    expected=...
    if [ "$val" != "$expected" ]; then
        echo "WARN: $param = $val (期望 $expected)"
    fi
done
```

---


## 五、排查路径决策树
### 5.1 从现象出发
`
线上反馈（任一）
  │
  ├─ app 无法联网
  │   ├─ 全 app 失效？→ 系统级 FD 耗尽 / 网络配置错
  │   └─ 单 app 失效？→ app 内部问题
  │
  ├─ 触摸无响应
  │   ├─ InputDispatcher 警告？→ InputChannel 满
  │   └─ 全设备死锁？→ InputDispatcher 自身卡
  │
  ├─ 启动 ANR
  │   ├─ Zygote 栈在 ANR？→ fork 慢
  │   └─ 主线程在同步 IO？→ 业务改异步
  │
  ├─ adb 不可用
  │   ├─ adbd 进程不在？→ adbd 挂了
  │   └─ adbd 在但拒绝？→ 端口被占 / 全连接队列满
  │
  └─ 丢帧
      ├─ 主线程卡？→ BitTube 满
      └─ 渲染线程慢？→ SurfaceFlinger 问题
`
### 5.2 从日志关键字出发
| 日志关键字 | 跳转 |
|------------|------|
| EMFILE: Too many open files | §3.1 FD 耗尽 |
| Permission denied + UDS | §3.5 权限/路径 |
| avc: denied | §3.5 权限/路径（selinux） |
| Consumer is not responding | §3.2 主线程阻塞 + §3.3 队列积压 |
| ListenOverflows / ListenDrops | §3.3 队列积压（backlog） |
| ETIMEDOUT + connect | §3.4 协议失败 |
| EADDRINUSE + bind | §3.4 协议失败（abstract 冲突） |
| Input dispatching timed out | §3.2 主线程阻塞 |
| Process: skipped due to Zygote connection | §3.5 权限/路径 + §3.4 协议失败 |
| FATAL EXCEPTION + native | §3.1 FD 耗尽 + §3.3 队列积压 |
### 5.3 从工具命令出发
| 命令 | 用途 | 跳转 |
|------|------|------|
| ls /proc/<pid>/fd \\| wc -l | 进程 fd 数 | §3.1 |
| cat /proc/net/sockstat | 系统 socket 统计 | §4.2 |
| cat /proc/net/netstat \\| grep -i listen | ListenDrops/ListenOverflows | §3.3 + §4.2 |
| ss -m | socket 缓冲使用 | §3.3 |
| ss -lnt | TCP listen 队列 | §3.3 |
| cat /proc/net/unix | UDS 列表 | §3.5 |
| ls -lZ /dev/socket/<name> | 路径权限 + selinux | §3.5 |
| dmesg \\| grep -i avc | selinux 拒绝 | §3.5 |
| netstat -n \\| grep TIME_WAIT | TIME_WAIT 堆积 | §3.3 |
| dumpsys input | InputChannel 队列 | §3.3 |
| dumpsys SurfaceFlinger | BitTube / VSync | §3.3 |
| dumpsys activity | Zygote fork 时延 | §3.2 + §3.5 |
| ANR trace | 主线程栈 | §3.2 |
| tcpdump / strace | 协议失败定位 | §3.4 |
| fdsan（Android 14+） | fd 泄漏检测 | §3.1 |
---
## 六、实战案例
### 案例 1：综合 4 类风险的复杂 ANR（典型模式）
**现象**：
- 某 app 反馈：用户使用 1 小时后必现 ANR 5 秒
- 监控显示：Input dispatching timed out + Too many open files
**环境**：
- Android 13 (AOSP 13.0.0_r1) / Kernel 5.10 / 设备 Pixel 6
**分析思路**（按本篇5 大类风险逐一排查）：
1. **类 ② 主线程阻塞**：ANR trace 抓取：主线程在 Looper.loop 中等回调；业务栈：定位到 ImageLoader 同步加载
2. **类 ① FD 耗尽**：ls /proc/<pid>/fd \\| wc -l = 28000+；awk 统计：发现 20000+ 是 socket:[inode]
3. **类 ③ 队列积压**：dumpsys input 显示 InputChannel 队列 = 32（满）
4. **类 ④ 协议失败**：无
5. **类 ⑤ 权限/路径**：无
**根因**（一层层剥）：
`
最终根因：app 在主线程做 ImageLoader 同步加载
  ↓
业务层在 ImageLoader 内部持有一堆未关的 socket（OkHttp 连接池未释放）
  ↓
类 ① FD 耗尽（20000+ socket）
  ↓
类 ③ InputChannel 缓冲满（因 ② 主线程卡，无法 read）
  ↓
类 ② 主线程 ANR
`
**修复方案**：
`java
// 修复 1：ImageLoader 异步化
public void loadImage(String url, ImageView target) {
    imageLoader.loadAsync(url, target);  // 异步
}

// 修复 2：OkHttp 连接池上限
client = OkHttpClient.Builder()
    .connectionPool(new ConnectionPool(5, ...))
    .build();

// 修复 3：fdsan 开启
StrictMode.setVmPolicy(new VmPolicy.Builder()
    .detectLeakedClosableObjects()
    .penaltyLog()
    .build());
`
**修复后效果**：fd 稳定 800 以内，ANR 消失。
**这个案例教会我们**：复杂问题往往同时触发多类风险；必须按5 大类逐项排查；根因往往在底层。
### 案例 2：vendor 改错 selinux label 导致全设备 ANR（典型模式）
**现象**：
- 某 vendor OTA 升级后，5% 设备启动后立即卡死
- logcat: Process: ProcessRecord{xxx yyy} skipped due to Zygote connection
**环境**：Android 13 / Kernel 5.10 / 设备 vendor F 自研 ROM
**分析思路**：
1. **类 ⑤ 权限/路径**：ls -lZ /dev/socket/zygote 显示权限 srw-rw---- 1 root root ...；预期是 srw-rw---- 1 root 10110 0 0 zygote（uid 10110 = zygote 组）
2. **类 ④ 协议失败**：客户端 connect() 返回 EACCES
3. **类 ② 主线程阻塞**：system_server 主线程在等 fork 响应 → 5 秒 ANR
**根因**：
- **直接原因**：OTA 后 zygote socket 路径被改回 root:root
- **根本原因**：vendor 的 OTA 脚本覆盖了 /dev/socket/zygote 但没恢复 owner
- **连锁反应**：AMS 连不上 zygote → 所有 app 启动失败 → system_server 自身 ANR → 设备进入假死
**修复方案**（init.rc + post_ota.sh 模板）：
`
c
on boot
    restorecon /dev/socket/zygote
    chown root 10110 /dev/socket/zygote
    chmod 0660 /dev/socket/zygote

service vendor_post_ota /system/bin/sh /vendor/bin/post_ota.sh
    class core
    oneshot
`
修复后效果：OTA 后启动正常。
**这个案例教会我们**：vendor 改 /dev/socket/ 路径是 P0 风险；OTA 后必须 restorecon + chown；复杂 ANR 的根因可能在最基础的系统配置。
---
## 七、总结：架构师视角的关键 Takeaway
1. **socket 风险的两个维度**：6 大场景 × 5 大类风险 = 30+ 个具体风险点。现场排查时先定场景、再定风险类——两步就能定位 80% 的问题。
2. **5 大类风险的核心是主线程阻塞和队列积压**——这两类在 6 大场景中 5+ 个都是 P0。
3. **风险不是独立存在的**——复杂线上问题往往多类联动（案例 1：①②③ 联动）。按 5 大类逐项排查比找根因更高效。
4. **vendor 是 socket 稳定性的隐性杀手**——/dev/socket/ 路径权限、selinux label、内核参数任何一个被改错都可能是 P0。
5. **监控指标是 P0 防御**——ListenDrops、ListenOverflows、进程 fd 数、socket 缓冲使用——这 4 个指标任何一个异常都能提前告警。
**socket 风险排查的总决策树**：
`
现场问题
  ↓
1. 锁定场景（6 大场景之一）
  ↓
2. 套用风险矩阵（场景 × 风险类）
  ↓
3. 按风险类的排查路径执行
  ↓
4. 看监控指标是否异常
  ↓
5. 修复 + 回归
`
---
## 附录 A：核心源码路径索引
| 文件名 | 完整路径 | 内核/AOSP 版本基线 | 说明 |
|--------|----------|-------------------|------|
| net/socket.c | net/socket.c | Linux 5.10+ | 通用 socket 层、syscall |
| net/ipv4/af_inet.c | net/ipv4/af_inet.c | Linux 5.10+ | INET 协议族 |
| net/ipv4/tcp.c | net/ipv4/tcp.c | Linux 5.10+ | TCP 协议 |
| net/unix/af_unix.c | net/unix/af_unix.c | Linux 5.10+ | UDS 协议族 |
| fs/eventpoll.c | fs/eventpoll.c | Linux 5.10+ | epoll（详见 [epoll 01]） |
| kernel/sched/wait.c | kernel/sched/wait.c | Linux 5.10+ | wait queue |
| ZygoteServer | frameworks/base/core/java/com/android/internal/os/ZygoteServer.java | AOSP 14.0.0_r1 | Zygote 监听 |
| InputChannel | frameworks/native/libs/input/InputTransport.cpp | AOSP 14.0.0_r1 | InputChannel socketpair |
| BitTube | frameworks/native/libs/gui/BitTube.cpp | AOSP 14.0.0_r1 | Choreographer VSync |
| adbd | system/core/adb/daemon/usb.cpp | AOSP 14.0.0_r1 | adbd |
| LocalSocket | frameworks/base/core/java/android/net/LocalSocket.java | AOSP 14.0.0_r1 | UDS Java 封装 |
| OkHttp | (第三方库) | okhttp 4.x | 网络库 |
| StrictMode | frameworks/base/core/java/android/os/StrictMode.java | AOSP 14.0.0_r1 | fdsan + 主线程 IO 检测 |
| dumpsys input | frameworks/base/services/core/java/com/android/server/input/InputManagerService.java | AOSP 14.0.0_r1 | InputChannel 监控 |
| dumpsys SurfaceFlinger | frameworks/native/services/surfaceflinger/SurfaceFlinger.cpp | AOSP 14.0.0_r1 | BitTube 监控 |
---
## 附录 B：源码路径对账表
| 序号 | 文章中出现的路径 | 状态 | 校对来源 |
|------|------------------|------|----------|
| 1 | net/socket.c | 已校对 | https://elixir.bootlin.com/linux/v5.10/source/net/socket.c |
| 2 | net/ipv4/af_inet.c | 已校对 | https://elixir.bootlin.com/linux/v5.10/source/net/ipv4/af_inet.c |
| 3 | net/ipv4/tcp.c | 已校对 | https://elixir.bootlin.com/linux/v5.10/source/net/ipv4/tcp.c |
| 4 | net/unix/af_unix.c | 已校对 | https://elixir.bootlin.com/linux/v5.10/source/net/unix/af_unix.c |
| 5 | fs/eventpoll.c | 已校对 | https://elixir.bootlin.com/linux/v5.10/source/fs/eventpoll.c |
| 6 | kernel/sched/wait.c | 已校对 | https://elixir.bootlin.com/linux/v5.10/source/kernel/sched/wait.c |
| 7 | frameworks/base/core/java/com/android/internal/os/ZygoteServer.java | 已校对 | https://cs.android.com/android/platform/superproject/+/android-14.0.0_r1:frameworks/base/core/java/com/android/internal/os/ZygoteServer.java |
| 8 | frameworks/native/libs/input/InputTransport.cpp | 已校对 | https://cs.android.com/android/platform/superproject/+/android-14.0.0_r1:frameworks/native/libs/input/InputTransport.cpp |
| 9 | frameworks/native/libs/gui/BitTube.cpp | 已校对 | https://cs.android.com/android/platform/superproject/+/android-14.0.0_r1:frameworks/native/libs/gui/BitTube.cpp |
| 10 | system/core/adb/daemon/usb.cpp | 已校对 | https://cs.android.com/android/platform/superproject/+/android-14.0.0_r1:system/core/adb/daemon/usb.cpp |
| 11 | frameworks/base/core/java/android/net/LocalSocket.java | 已校对 | https://cs.android.com/android/platform/superproject/+/android-14.0.0_r1:frameworks/base/core/java/android/net/LocalSocket.java |
| 12 | frameworks/base/core/java/android/os/StrictMode.java | 已校对 | https://cs.android.com/android/platform/superproject/+/android-14.0.0_r1:frameworks/base/core/java/android/os/StrictMode.java |
| 13 | frameworks/base/services/core/java/com/android/server/input/InputManagerService.java | 已校对 | https://cs.android.com/android/platform/superproject/+/android-14.0.0_r1:frameworks/base/services/core/java/com/android/server/input/InputManagerService.java |
| 14 | frameworks/native/services/surfaceflinger/SurfaceFlinger.cpp | 已校对 | https://cs.android.com/android/platform/superproject/+/android-14.0.0_r1:frameworks/native/services/surfaceflinger/SurfaceFlinger.cpp |
---
## 附录 C：量化数据自检表
| 序号 | 量化描述 | 数量级 | 依据来源 |
|------|----------|--------|----------|
| 1 | ANR 5 秒阈值 | 5000ms | ActivityManagerService |
| 2 | Android 默认 RLIMIT_NOFILE | 32768 | bionic/libc |
| 3 | 默认 somaxconn (AOSP) | 4096 | AOSP 14 |
| 4 | 默认 tcp_syncookies | 1 | AOSP 14 |
| 5 | 默认 tcp_abort_on_overflow | 0 | AOSP 14 |
| 6 | 默认 wmem_max / rmem_max | 208KB | AOSP 14 |
| 7 | InputChannel SOCK_SEQPACKET 缓冲 | 8-32 消息 | vendor 差异 |
| 8 | BitTube 默认 bufsize | 8KB-64KB | BitTube.cpp |
| 9 | TIME_WAIT 默认时长 | 60 秒 | net/ipv4/tcp.c |
| 10 | tcp_synack_retries 默认 | 5 | AOSP 14 |
| 11 | Java NIO Selector 单实例 fd | 3 个 | SelectorImpl |
| 12 | OkHttp 连接池默认 | 5 | okhttp 4.x |
| 13 | StrictMode 阈值 | 1ms（主线程 IO 起始） | AOSP 14 |
| 14 | fdsan 检测范围 | 全 Java 资源 + 显式 native | AOSP 14+ |
| 15 | fd 告警阈值 | > 80% × RLIMIT_NOFILE | 工程经验 |
| 16 | ListenDrops 告警阈值 | > 0 | 立即 |
| 17 | ListenOverflows 告警阈值 | > 0 | 立即 |
| 18 | UDS 路径长度限制 | 108 字节 | UNIX_PATH_MAX |
| 19 | TCP 重传 SYN 超时 | 60+ 秒（默认） | tcp_synack_retries |
| 20 | ANR trace dump 等待 | 5 秒 | ActivityManagerService |
---
## 附录 D：工程基线表
| 类别 | 项目 | 推荐值 | 备注 |
|------|------|--------|------|
| **进程 fd** | RLIMIT_NOFILE | 32768 | Android 默认 |
| **进程 fd 告警** | 80% / 95% | 工程经验 | 触发后立即排查 |
| **TCP listen** | somaxconn | 4096 | 高并发可调到 16384 |
| **TCP listen** | tcp_max_syn_backlog | 256 | 高并发可调到 1024 |
| **TCP syn** | tcp_syncookies | 2 | 仅满时启用 |
| **TCP overflow** | tcp_abort_on_overflow | 1 | 立即 RST |
| **TCP timewait** | tcp_tw_reuse | 1 | 短连接高频 |
| **TCP buffer** | wmem_max / rmem_max | 4MB-16MB | 高吞吐场景 |
| **TCP buffer** | tcp_wmem / tcp_rmem | 4096 16384 16MB | 通用 |
| **UDS 路径** | /dev/socket/* 权限 | 0660 root 10110 | zygote 组 |
| **UDS 路径** | restorecon | 必加 | OTA 流程 |
| **InputChannel** | buffer | vendor 编译期 | 主线程卡 = 必满 |
| **BitTube** | bufsize | 8KB-64KB | 90/120Hz 调大 |
| **adbd** | listen backlog | 128（写死） | 配合 somaxconn |
| **StrictMode** | fdsan | 开 | Android 14+ |
| **StrictMode** | 主线程 IO 检测 | 开 | 调试期 |
| **OkHttp** | 连接池 | 5 | 不要放大 |
| **连接池 × buffer** | 总内存 | < 进程 RSS 10% | 估算 |
| **CI 校验** | socket 路径权限 | 与 init.rc 一致 | 升级必跑 |
| **CI 校验** | selinux label | u:object_r:*_socket | 升级必跑 |
| **CI 校验** | 内核参数 | somaxconn/syncookies/abort | 升级必跑 |
---
## 篇尾衔接
下一篇 [08-Socket诊断工具与治理体系](../socket/08-Socket诊断工具与治理体系.md) 将深入5 分钟内定位 + 治理工具集：
- **诊断工具**：/proc/net/* 完整解读、ss/lsof 实战用法、strace + tcpdump 抓包模板、ANR trace 关键栈、dumpsys 各命令速查
- **治理体系**：从被动排查到主动治理——fdsan 落地、连接池规范、backlog 调优清单、CI 校验脚本、监控告警阈值
- **完整案例**：2 个综合案例（带 5 大类风险联动排查）
本篇是 socket 系列风险收口——08 是治理收口。
---


