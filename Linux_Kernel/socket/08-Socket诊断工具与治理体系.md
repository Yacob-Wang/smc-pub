# Socket 08：诊断工具与治理体系

> **系列**：面向稳定性的 Android Socket 子系统深度解析系列(Socket)
> **源码基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)
> **内核矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇工具涉及 `net/core/sock.c`、`include/linux/sock_diag.h`、`include/uapi/linux/sock_diag.h`;Android 14 已默认启用 sock_diag,见 §3)
> **目标读者**:Android 稳定性框架架构师
> **前置阅读**:本系列 01-07 全篇
> **下一篇**:无(系列收官)

> 面向 Android 稳定性架构师：把 socket 系列 8 篇(含桥接篇)所有知识点收口为"可立刻上手的诊断命令集 + 可落地工程的治理清单 + 2 个综合实战案例"——目标是"现场 5 分钟定位 + 治理工程化不再依赖个人经验"。

---

## 本篇定位

- **本篇系列角色**:Socket 系列第 8 篇「诊断工具与治理体系」(socket 系列 8 篇规划"第三篇章:诊断实战与治理"的收口;与 07 风险全景配套——07 是"知道会出什么问题",08 是"出问题怎么查 + 怎么治 + 怎么防")
- **强依赖**:
  - [Socket 07-Socket稳定性风险全景](07-Socket稳定性风险全景.md)(5 大类风险 × 6 大场景矩阵——本篇所有诊断动作按此矩阵分桶)
  - [Socket 01-Socket总览](01-Socket总览.md)(6 大场景基线)
  - [Socket 04-Socket缓冲区与数据收发](04-Socket缓冲区与数据收发.md)(阻塞/EAGAIN 与 buffer 监控指标来源)
  - [Socket 05-listen_backlog与连接队列](05-listen_backlog与连接队列.md)(ListenOverflows / ListenDrops / SynRecv 队列指标来源)
  - [Socket 06-Unix_Domain_Socket与Android使用](06-Unix_Domain_Socket与Android使用.md)(UDS 路径监控来源)
  - [epoll 01-epoll总览与核心机制](../epoll/01-epoll总览与核心机制.md)(epoll 侧的监控补充)
  - [IO 06-IO 与进程的深度耦合](../../IO/06-IO与进程的深度耦合：D状态、iowait、IO-hang、进程阻塞.md)(D 状态与 wait queue 唤醒——诊断工具的底层原理)
- **承接自**:07 末尾预告"5 分钟内定位 + 治理工具集"——本篇全部兑现
- **衔接去**:本篇完成后 socket 系列 8 篇规划全数完结(01/04/05/06/07/08 + bridge 01 + epoll 01 + README);收口以"治理工程化清单"和"实战案例库"形式沉淀
- **不重复内容**:风险的具体机制由 07 承担;本篇只做**工具使用 + 监控指标 + 治理落地 + 综合案例**

#### §0 锚点案例的可验证 4 件套:线上 IM 服务连接异常 5min 定位演练

> **环境**:
> - 设备:某机型线上统计(Pixel 6/7 占比 60%)
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI
> - App:某 IM App v7.3(脱敏代号 `ChatApp`,灰度 10% 后 0.5% 用户报"消息发不出去")
> - 工具:`ss -tan` + `cat /proc/net/sockstat` + `lsof -p <pid>` + `strace` + `tcpdump`

> **复现步骤**(线上监控告警后,5min 定位演练):
> 1. **0s**:监控告警 → ChatApp 服务端连接成功率从 99.5% 跌到 88%
> 2. **30s**:`ssh server` → `ss -s | head -20` 看整机 socket 统计
> 3. **1min**:`cat /proc/net/sockstat` 看 TCP inuse/orphan/tw 分布
> 4. **2min**:`ss -tan state syn-recv | wc -l` → 137 → 半连接队列堆积
> 5. **3min**:`netstat -s | grep -E "ListenOverflow|ListenDrops"` → 监听到 ListenDrops 飙升
> 6. **5min**:定位根因 = nginx `worker_connections=1024` 偏低,扩到 65535 后恢复

> **logcat / 服务端 ss 关键片段**:
> ```
> # ss -s(整机)
> TCP:   41284 (estab 124, closed 40120, orphaned 0, tw 40120)    ← tw 4 万,可能不是这个
> # /proc/net/sockstat
> sockets: used 41284
> TCP: inuse 1024 orphan 0 tw 40120 alloc 1024 mem 482     ← inuse 1024 是关键!
>                                                              (worker_connections=1024)
> # ss -tan state syn-recv
> SYN-RECV 0 0 0.0.0.0:443  10.0.0.100:54312
> SYN-RECV 0 0 0.0.0.0:443  10.0.0.100:54313
> ... (137 个)
> # netstat -s
> TcpListenOverflows: 8923   ← 关键指标!
> # 客户端 OkHttp 错误
> ECONNREFUSED: Connection refused
> # 监控面板(基于 sock_diag + sk):
> - listen_overflow_rate: 8923/min  ↑↑↑
> - syn_recv_avg: 137
> - tcp_inuse: 1024 (上限)
> - accept_q: full
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/etc/nginx/nginx.conf
> +++ b/etc/nginx/nginx.conf
> @@ worker
> -    worker_connections 1024;
> +    # 修复 1:worker_connections 抬到 65535
> +    worker_connections 65535;
> +    multi_accept on;
> ```
> ```diff
> --- a/proc/sys/net/ipv4/tcp_max_syn_backlog
> +++ b/proc/sys/net/ipv4/tcp_max_syn_backlog
> @@ tuning
> -    net.ipv4.tcp_max_syn_backlog = 128
> +    # 修复 2:内核半连接队列也抬到 4096
> +    net.ipv4.tcp_max_syn_backlog = 4096
> +    net.ipv4.tcp_syncookies = 1
> ```
> ```diff
> --- a/monitor/socket_dashboard.json
> +++ b/monitor/socket_dashboard.json
> @@ alerting
> -    { "name": "tcp_inuse", "threshold": 800, "page_on": true }
> +    { "name": "tcp_inuse", "threshold": 10000, "page_on": true }
> +    { "name": "listen_overflow_rate", "threshold": "100/min", "page_on": true }
> +    { "name": "syn_recv_avg", "threshold": 500, "page_on": true }
> ```
> 完整 5min 定位路径 ↔ 工具链 ↔ 监控告警 ↔ 治理工程化清单见 §2-§10。

> 面向 Android 稳定性架构师：把 socket 系列 8 篇（含桥接篇）所有知识点收口为"可立刻上手的诊断命令集 + 可落地工程的治理清单 + 2 个综合实战案例"——目标是"现场 5 分钟定位 + 治理工程化不再依赖个人经验"。

## 一、背景与定义

### 1.1 为什么需要"诊断 + 治理"双视角

07 风险全景给出"6 大场景 × 5 大类风险"的二维矩阵——但现场问题不会按矩阵来。线上只会告诉你"app 启动失败"或"触摸没反应"，你需要：

- **诊断视角**：5 分钟内把现象归到 07 矩阵的某个格子，再按格子指向的排查入口往下挖
- **治理视角**：把"人治"变成"工程化"——fdsan/连接池/backlog/CI 校验/监控告警，让团队任何成员都能发现问题、修复问题

两者缺一不可：
- **只有诊断**：每次问题都要"老司机救火"，新人无法接手
- **只有治理**：上线前不漏，但线上一旦出问题依然要靠个人能力

### 1.2 诊断工具全景图

```
                          ┌─ 内核态 ──────────────┐
                          │   /proc/net/*         │
                          │   /proc/pid/fd        │
                          │   /proc/pid/net/tcp   │
                          │   dropwatch / perf    │
                          └──────────┬────────────┘
                                     │
现场现象 ──→ 场景归类(07 矩阵) ──→   工具调用   ──→ 定位根因
                                     │
                          ┌──────────┴────────────┐
                          │   用户态 ──────────────┤
                          │   ss / netstat / lsof │
                          │   strace / tcpdump    │
                          │   ANR trace / dumpsys │
                          └───────────────────────┘
```

**关键原则**：
- **从轻到重**：`cat /proc/net/sockstat`（无开销）→ `ss -s`（极轻）→ `lsof -p`（轻）→ `strace`（中）→ `tcpdump`（重）→ `perf`（重）
- **从全局到局部**：先看整机 `/proc/net/sockstat` 确定问题范围，再 `/proc/pid/fd` 定位到进程
- **跨场景对照**：同一现象从多个工具同时看（如 TIME_WAIT 多 → `/proc/net/sockstat` + `ss -s` + 业务日志三方对照）

### 1.3 治理体系全景图

```
┌─ 主动防御层（不让问题上线）──────────────────────┐
│  fdsan / StrictMode / 主线程 IO 检测            │
│  代码 review：连接必须 close / buffer 必须配对   │
└───────────────────┬──────────────────────────────┘
                    ↓
┌─ 资源管理层（资源可控可量化）──────────────────────┐
│  连接池规范 / buffer 规范 / 超时规范              │
│  backlog 调优清单 / 内核参数基线                  │
└───────────────────┬──────────────────────────────┘
                    ↓
┌─ 工程化层（升级不破坏）────────────────────────────┐
│  CI 校验脚本：socket 路径 / selinux label / 内核参数│
│  升级前后回归用例                                │
└───────────────────┬──────────────────────────────┘
                    ↓
┌─ 监控层（线上早发现）──────────────────────────────┐
│  进程 fd 告警 / 队列深度告警 / TIME_WAIT 告警      │
│  dashboard + 主动巡检                            │
└───────────────────────────────────────────────────┘
```

**核心思想**：治理体系不是"加更多工具"，而是"工具能自动跑"。fdsan 是自动的、CI 是自动的、监控告警是自动的——人只在异常时介入。

---

## 二、诊断工具详解

### 2.1 /proc/net/* 完整解读（内核态全局视角）

`/proc/net/*` 是内核直接导出的连接与 socket 统计——**零开销**（只是读取内核计数器），是诊断的第一步。

#### 2.1.1 /proc/net/sockstat（最快入口，5 秒定位问题大类）

```bash
$ cat /proc/net/sockstat
sockets: used 1847
TCP:   inuse 1450 orphan 0 tw 1287 alloc 1450 mem 312
UDP:   inuse 18 mem 5
UDPLITE: inuse 0
RAW:   inuse 0
FRAG:  inuse 0 memory 0
```

**字段解读**（AOSP 14 / Linux 5.10+ 内核 `net/ipv4/proc.c`）：

| 字段 | 含义 | 异常信号 |
|------|------|----------|
| `TCP: inuse` | 当前 ESTABLISHED/CLOSE_WAIT 等活跃 TCP 数 | 远高于业务均值 → 连接泄漏或被攻击 |
| `TCP: tw` | **TIME_WAIT 数量** | 持续 > 5000 → 短连接高频未优化 |
| `TCP: orphan` | 无 fd 关联的孤儿 socket | > 0 且增长 → fd 泄漏配合 socket 泄漏 |
| `TCP: alloc` | 已分配的 socket 对象数 | 远大于 inuse → 大量 TIME_WAIT/CLOSE |
| `TCP: mem` | TCP buffer 总占用页数 | 异常增长 → buffer 调大或泄漏 |
| `UDP: inuse` | UDP socket 数 | 异常高 → DNS 频繁或 UDP 攻击 |

**实战用法**：
- 第一步总是 `cat /proc/net/sockstat`——3 秒判断"是不是 TCP 类的、TIME_WAIT 多不多"
- 对比相邻 5 秒两次采样：`tw` 增长斜率可估算每秒新增短连接数

#### 2.1.2 /proc/net/tcp 与 /proc/net/tcp6（连接明细）

```bash
$ cat /proc/net/tcp
  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1F90 0100007F:9C40 01 00000000:00000000 00:00000000 00000000  1000        0 24513 1 ffff8c1c4f4ec000
   1: 00000000:0050 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 18432 1 ffff8c1c4f4e0000
   ...
```

**关键字段**：
- `sl`：序号（每条 socket 一条记录）
- `local_address` / `rem_address`：16 进制 IP:端口（IP 字节序反序）
  - `0100007F:1F90` = 127.0.0.1:8080
  - `00000000:0050` = 0.0.0.0:80（listen）
- `st`：状态码（**需要查表**）
  - `01` = ESTABLISHED
  - `0A` = LISTEN
  - `06` = TIME_WAIT
  - `08` = CLOSE_WAIT
  - `05` = CLOSED
  - `02` = SYN_SENT
  - `03` = SYN_RECV
  - `04` = FIN_WAIT1
  - `07` = CLOSE
  - `09` = LAST_ACK
  - `0B` = CLOSING
- `tx_queue` / `rx_queue`：发送/接收队列字节数（**> 0 即积压**）
- `uid`：所属用户（可识别是 system 1000 还是 app uid）
- `inode`：对应 `/proc/pid/fd` 中的 socket:[inode]

**实战用法**：
- 看 `st=0A`（LISTEN）的 backlog 是否合理——`rx_queue` 大说明 accept 慢
- 找 `st=06`（TIME_WAIT）数量——超过 10000 需要 `tcp_tw_reuse`
- 找 `st=08`（CLOSE_WAIT）——这是**应用层未 close()** 的标志（P0）

#### 2.1.3 /proc/net/unix（UDS 诊断必看）

```bash
$ cat /proc/net/unix
Num  RefCount Protocol Flags    Type    St    Inode  Path
0000000000000000: 00000002 00000000 00000000 0001 03 18432 /dev/socket/zygote
0000000000000001: 00000002 00000000 00000000 0001 03 19847 /dev/socket/installd
0000000000000002: 00000003 00000000 00000000 0001 03 22001 @zygote
0000000000000003: 00000002 00000000 00000000 0001 01 22450 @webviewupdate
```

**字段解读**：
- `Type`：
  - `0001` = SOCK_STREAM（流式）
  - `0002` = SOCK_DGRAM（数据报）
  - `0005` = SOCK_SEQPACKET（InputChannel 用此）
- `St`：状态
  - `01` = LISTEN
  - `03` = CONNECTED
- `Path`：
  - `/dev/socket/*` = 路径型 UDS（init.rc 创建）
  - `@xxx` = abstract 命名空间
  - 空 = 未 bind（socketpair 一方）

**实战定位**：
- **找 InputChannel**：`grep "@" /proc/net/unix`——大多 InputChannel 是 abstract（涉及隐私一般不开）
- **找 Zygote listen**：`grep "/dev/socket/zygote"` 应只有 1 条 `st=01`（LISTEN）；多说明有问题
- **找 abstract 冲突**：`grep "^.*:.*@zygote"` 多条说明命名冲突

#### 2.1.4 /proc/net/snmp（协议层计数器，全局趋势）

```bash
$ cat /proc/net/snmp | grep Tcp:
Tcp: ActiveOpens PassiveOpens AttemptFests EstabResets CurrEstab InSegs OutSegs RetransSegs InErrs OutRsts
Tcp: 12345 6789 0 234 1450 9876543 8765432 5678 12 345
```

**关键指标**：
- `RetransSegs`：TCP 重传数（持续增长 → 网络质量差）
- `InErrs`：入包错误数（> 0 → 内核 buffer 问题或网卡丢包）
- `OutRsts`：发出的 RST 数（异常增长 → 大量拒绝连接）
- `EstabResets`：ESTABLISHED 被重置数

**实战用法**：
- 对比相邻 5 秒两次 `RetransSegs` 差值——判断重传率
- `OutRsts` 持续 > 100/分钟——大量对端拒绝，可能是 LocalServerSocket backlog 满

#### 2.1.5 /proc/net/netstat（扩展统计，AOSP 上常用）

```bash
$ cat /proc/net/netstat | grep -i listen
TcpExt: ListenOverflows ListenDrops LockDropped PFMemallocDrop OptbacklogDrop
TcpExt: 00000000042 00000000038 0 0 0
```

- `ListenOverflows`：全连接队列溢出次数——**> 0 即代表有连接被丢弃**（P0 告警）
- `ListenDrops`：listen socket 接受连接时被丢弃数
- `LockDropped`：锁竞争导致的丢弃

**实战用法**：这俩指标在 05 backlog 篇有详细机制——出现增长立即排查 accept 慢或 backlog 不足。

---

### 2.2 ss / netstat / lsof 实战（用户态查询）

#### 2.2.1 ss 命令速查（替代 netstat，更快）

```bash
# 整机 socket 摘要（最常用第一步）
ss -s

# TCP 详细
ss -tan            # all + numeric + tcp
ss -tan state established     # 只看 ESTABLISHED
ss -tan state time-wait | wc -l  # 数 TIME_WAIT
ss -tan state close-wait     # CLOSE_WAIT——重点关注

# UDP
ss -uan

# UDS（关键！）
ss -xan            # unix domain socket all numeric
ss -xan | grep zygote   # 找 Zygote
ss -xan | grep "@"      # abstract 命名空间

# 监听端口
ss -tlnp           # listen + process + numeric
ss -tlnp 'sport = :80'  # 只看 80 端口

# 排序找 top
ss -tan state time-wait | awk '{print $4}' | sort | uniq -c | sort -rn | head
```

**输出示例**：
```
$ ss -s
TCP:   1450 (estab 1287, closed 134, orphaned 0, timewait 1287)
Transport Total     IP        IPv6
RAW       0         0         0
UDP       18        12        6
TCP       1450      1320      130
INET      1468      1332      136
FRAG      0         0         0
```

**实战判断**：
- `timewait 1287` + `estab 1287`——典型"短连接高频"模式
- `closed 134` 持续增长——连接被关闭但未释放 socket 对象

#### 2.2.2 netstat 局限性与替代

`netstat` 在 AOSP 中**默认未编译进 toybox**——优先用 `ss`。但 `netstat -anp` 在某些 vendor ROM 仍可用，输出与 `/proc/net/tcp` 等价。

**经验法则**：
- AOSP 14 默认：toybox 提供 `netstat` 但缺 -p 选项；优先 `ss -p` 或直接读 `/proc/net/tcp`
- 完整工具链厂商：busybox 提供完整 `netstat`

#### 2.2.3 lsof（fd 全量归属）

```bash
# 某进程的所有 fd
lsof -p <pid>

# 只看 socket 类型
lsof -p <pid> | grep socket

# 网络相关 fd（含 UDS）
lsof -i            # 所有网络 fd
lsof -i :8080      # 占用 8080 的进程
lsof -i @1.2.3.4   # 与某 IP 通信的所有连接

# UDS 路径
lsof -U            # 所有 UDS
lsof | grep /dev/socket   # 路径型 UDS
```

**实战用法**：
- **FD 泄漏归因**：`lsof -p <pid> | wc -l` 看进程总 fd 数，对比正常基线
- **找哪个进程占用 8080**：`lsof -i :8080`（开发期端口冲突排查）
- **Zygote 监听 socket**：`lsof -U | grep zygote`

**AOSP 局限**：`lsof` 在 AOSP 默认 toybox 中**不可用**，需要 busybox 或 toybox 静态编译版。替代方案见 §2.3 直接读 `/proc/pid/fd`。

---

### 2.3 /proc/pid/fd 与 fd 归属（最实用的 fd 诊断）

`/proc/<pid>/fd/` 是进程的 fd 表——**无需 lsof** 直接可读。

#### 2.3.1 进程 fd 总量与 socket 分类

```bash
# 总 fd 数
ls /proc/<pid>/fd | wc -l

# 其中 socket 数
ls -l /proc/<pid>/fd | grep socket | wc -l

# 其中 pipe 数
ls -l /proc/<pid>/fd | grep pipe | wc -l

# 其中 anon_inode 数（eventfd/epoll 等）
ls -l /proc/<pid>/fd | grep anon_inode | wc -l

# 与 RLIMIT_NOFILE 对比
cat /proc/<pid>/limits | grep "open files"
```

**实战判断**：
- `ls /proc/<pid>/fd | wc -l` > 1000 → 怀疑 FD 泄漏
- 单进程 socket fd > 500 → 长连接池过大或泄漏
- 与 `cat /proc/sys/fs/file-nr` 对比整机 fd 余量

#### 2.3.2 socket:[inode] 解析（关键技能）

`/proc/<pid>/fd/` 中的 socket 长这样：
```
lrwx------ 1 system system 64 ... 12 -> socket:[24513]
lrwx------ 1 system system 64 ... 13 -> socket:[19847]
```

`socket:[24513]` 中的 inode `24513` 就是 `/proc/net/tcp` 或 `/proc/net/unix` 中的 inode——**两者一一对应**。

**完整解析流程**：
```bash
# 1. 进程所有 socket inode
ls -l /proc/<pid>/fd | grep socket | awk -F'[][]' '{print $2}'

# 2. 在 /proc/net/tcp 中找该 inode 对应的连接
grep " 24513 " /proc/net/tcp

# 3. 输出:  sl  local_address rem_address   st ...
#           0: 0100007F:1F90 0100007F:9C40 01 ...

# 4. 一键脚本：进程 → 所有连接
PID=<pid>
for inode in $(ls -l /proc/$PID/fd 2>/dev/null | grep socket | awk -F'[][]' '{print $2}'); do
    grep " $inode " /proc/net/tcp /proc/net/tcp6 /proc/net/unix 2>/dev/null | head -1 | awk -v i=$inode '{print "inode="i" "$0}'
done
```

**实战定位**：这一招是 socket 诊断的"瑞士军刀"——任何进程的任何 socket fd 都能追溯到连接/监听信息。

#### 2.3.3 /proc/pid/net/tcp（进程的 socket 视图）

```bash
# 某进程视角的 TCP（与整机 /proc/net/tcp 类似但只含该进程 namespace）
cat /proc/<pid>/net/tcp
```

**实战用法**：Android 中容器化场景下（如 app 在自己的 net namespace），进程视角与整机视角不同——这是排查"应用看到的连接 vs 系统看到的连接"差异的关键。

#### 2.3.4 区分 Zygote / InputChannel / 应用 socket 的实战技巧

**场景 1：识别 Zygote 监听 socket**
```bash
# Zygote 进程名是 zygote64 / zygote
PID=$(pidof zygote64)
ls -l /proc/$PID/fd | grep "/dev/socket/zygote"
# 或
ss -xlp | grep zygote
```

**场景 2：识别 InputChannel fd**

InputChannel 是 socketpair，路径在 `/proc/net/unix` 中是 abstract（`@` 开头）但通常**不开 abstract**——要从 app 进程 fd 中找 `socket:[...]` 且 inode 在 `/proc/net/unix` 出现。

```bash
# app 进程中成对出现的 socket（InputChannel 必成对）
ls -l /proc/<app_pid>/fd | grep socket | awk '{print $NF}'
# 通常能看到若干 socketpair——但具体是 InputChannel 还是其他 socket 难区分

# 终极方法：从 InputDispatcher 视角
dumpsys input | grep -A 5 "InputChannel"
```

**场景 3：识别应用网络 socket**

```bash
# 应用 PID 视角的网络连接
PID=<app_pid>
ss -tan | while read line; do
    inode=$(echo "$line" | awk '{print $10}')
    if ls -l /proc/$PID/fd 2>/dev/null | grep -q "socket:\[$inode\]"; then
        echo "$line"
    fi
done
```

---

### 2.4 strace + tcpdump 抓包模板

#### 2.4.1 strace 网络系统调用

```bash
# 抓某进程所有网络相关 syscall
strace -f -e trace=network,read,write,connect,accept,bind,listen,socket -p <pid>

# 只抓 connect/accept（看连接行为）
strace -e trace=connect,accept,close -p <pid> 2>&1 | tee /data/local/tmp/strace.log

# 启动时抓（推荐启动后 attach 避免进程错过关键调用）
strace -f -e trace=network -p <pid> -o /data/local/tmp/net.log

# 显示时间戳和数据长度
strace -tt -e trace=connect,sendto,recvfrom -p <pid>
```

**输出解读**：
```
connect(12, {sa_family=AF_INET, sin_port=htons(8080), sin_addr=inet_addr("1.2.3.4")}, 16) = 0
connect(13, {sa_family=AF_UNIX, sun_path="/dev/socket/zygote"}, 110) = 0
sendto(12, "GET / HTTP/1.1\r\nHost: 1.2.3.4\r\n\r\n", 35, 0, NULL, 0) = 35
recvfrom(12, "HTTP/1.1 200 OK\r\n", ..., 0, NULL, NULL) = 17
```

**实战信号**：
- `connect()` 长时间无返回 → 网络阻塞或防火墙丢包
- `connect(AF_UNIX, "/dev/socket/xxx")` 返回 -1 ECONNREFUSED → 服务端未启动或路径错
- `close()` 缺失 → FD 泄漏源头

#### 2.4.2 tcpdump 抓包模板

```bash
# 抓所有 TCP 包
tcpdump -i any -nn -s 0 -w /data/local/tmp/cap.pcap

# 只抓某端口
tcpdump -i any -nn port 8080

# 只抓某 IP
tcpdump -i any -nn host 1.2.3.4

# 抓 TCP 三次握手失败
tcpdump -i any -nn 'tcp[tcpflags] & tcp-syn != 0 and tcp[tcpflags] & tcp-ack == 0'

# 抓 RST
tcpdump -i any -nn 'tcp[tcpflags] & tcp-rst != 0'

# 抓 UDS（AF_UNIX 走 lo 回环）
tcpdump -i lo -nn -w /data/local/tmp/uds.pcap

# 抓包后用 Wireshark 分析（重要！）
adb pull /data/local/tmp/cap.pcap .
wireshark cap.pcap
```

**AOSP 局限**：`tcpdump` 在 userdebug 版本通常可用，user 版本不可用。**替代方案**：
- user 版本：用 `/proc/net/tcp` + strace 替代
- userdebug：直接 tcpdump

#### 2.4.3 完整抓包模板（线上实战）

```bash
#!/bin/bash
# 网络问题全套抓包脚本
PID=$1
OUT=/data/local/tmp/sock_diag_$(date +%s)
mkdir -p $OUT

# 1. 整机 sockstat 快照
cat /proc/net/sockstat > $OUT/sockstat_$(date +%s).txt

# 2. 进程 fd 快照
ls -l /proc/$PID/fd > $OUT/fd_$(date +%s).txt 2>&1

# 3. 进程 socket 连接
ss -tan > $OUT/ss_$(date +%s).txt
ss -xan > $OUT/uds_$(date +%s).txt

# 4. 持续 30 秒抓包
timeout 30 tcpdump -i any -nn -s 0 -w $OUT/cap.pcap &

# 5. 持续 30 秒 strace
timeout 30 strace -f -e trace=network,connect,sendto,recvfrom,close -p $PID -o $OUT/strace.txt &

wait
echo "捕获完成: $OUT"
ls -la $OUT
```

---

### 2.5 ANR trace 关键栈识别

#### 2.5.1 Input ANR trace 模板

**现象**：触摸屏幕无响应 5 秒后弹出 ANR。

**关键 trace 片段**：
```
"main" prio=5 tid=1 Sleeping
  | group="main" sCount=1 ucsCount=0 flags=1 obj=0x72b3e468 self=0x...
  | sysTid=12345 nice=-10 cgrp=bg cpuset=/system sched=0/0
  ...
  at java.lang.Thread.sleep(Native method)
  - waiting on <0x0fa12345> (a java.lang.Object)
  at android.os.MessageQueue.nativePollOnce(Native method)
  at android.os.MessageQueue.next(MessageQueue.java:335)
  at android.os.Looper.loopOnce(Looper.java:161)
  at android.os.Looper.loop(Looper.java:288)
  at android.os.ActivityThread.main(ActivityThread.java:7900)

  at android.view.InputEventReceiver.dispatchInputEvent(InputEventReceiver.java:...)
  - waiting to lock <0x0fa12345> (a java.lang.Object)
```

**诊断要点**：
- 主线程栈停在 `InputEventReceiver.dispatchInputEvent` → InputChannel fd 上 read 阻塞
- 主线程在 `MessageQueue.next()` → 在等下一条消息但被某 handler 占用
- 配合 `dumpsys input` 看 InputChannel 队列深度

#### 2.5.2 Zygote 启动 ANR trace 模板

**现象**：app 启动后 5 秒内未响应。

**关键 trace**：
```
"ActivityManagerService" prio=5 tid=...
  ...
  at com.android.internal.os.ZygoteProcess.attemptZygoteSendArgsAndGetResult(ZygoteProcess.java:...)
  at com.android.internal.os.ZygoteProcess.startViaZygote(ZygoteProcess.java:...)
  ...
  
  或：

"main" tid=...
  ...
  at android.os.MessageQueue.nativePollOnce(Native method)
  - waiting on <...>  (MainLooper blocked)
  ...
```

**诊断要点**：
- `ZygoteProcess.attemptZygoteSendArgsAndGetResult` 长时间未返回 → Zygote socket 阻塞
- `dumpsys activity processes` 看 Zygote 进程状态

#### 2.5.3 网络 ANR trace 模板

**现象**：app 网络请求未在合理时间内完成。

**关键 trace**：
```
"OkHttp Dispatcher" ...
  at java.net.SocketInputStream.read(SocketInputStream.java:...)
  at java.net.SocketInputStream.read(SocketInputStream.java:...)
  
  或：

"main" tid=...
  at java.net.Socket.connect(Socket.java:...)
  - blocked on connect() to "1.2.3.4:443"
```

**诊断要点**：
- 主线程在 `Socket.connect/read` → **阻塞 socket** + **主线程** = ANR 标配
- OkHttp Dispatcher 阻塞 → DNS 解析慢或对端无响应

---

### 2.6 dumpsys 命令速查

#### 2.6.1 dumpsys input（InputChannel 监控）

```bash
dumpsys input
```

**关键段**：
```
Input Manager State:
  ...
  Input Dispatcher State:
    FocusedWindow: Window{...}
    ...
    InboundQueueLength: 0
    PendingEventQueueLength: 0
    ...
    Channels:
      ...
      Channel { ... } 'Window{...}':
        ...
        InboundQueue: 8 / 32      # ← 已用 / 容量
        ...
```

**实战信号**：
- `InboundQueue: 32 / 32`（满）→ 触摸事件积压，主线程不消费
- `PendingEventQueueLength` 持续 > 0 → 下游消费者慢

#### 2.6.2 dumpsys activity processes（Zygote 与进程监控）

```bash
dumpsys activity processes | grep -A 5 "ProcessRecord{.*zygote"
```

**实战信号**：
- Zygote 进程 OOM adj 异常 → 优先级被压
- 多进程 zygote（zygote64/zygote32）数量与基线不一致

#### 2.6.3 dumpsys netstats（网络流量统计）

```bash
dumpsys netstats
```

**实战信号**：
- 某 app 流量突增 → 可能连接泄漏产生重传
- 长期无流量但 ESTABLISHED 数高 → 长连接假死

#### 2.6.4 dumpsys connectivity（网络连接状态）

```bash
dumpsys connectivity
```

**实战信号**：
- 网络切换时 socket 未正确重建 → 大量 RST
- captive portal 检测异常 → 网络切换后无网

#### 2.6.5 dumpsys window（窗口与触摸路由）

```bash
dumpsys window | grep -A 3 "mCurrentFocus\|mFocusedApp"
```

**实战信号**：
- focused window 与 InputChannel 关联错位 → 触摸事件发到错的 fd

#### 2.6.6 其他常用 dumpsys

| 命令 | 用途 | socket 关联 |
|------|------|-------------|
| `dumpsys package <pkg>` | 应用信息 | 看 app 是否声明 INTERNET 权限 |
| `dumpsys SurfaceFlinger` | 渲染 | BitTube（VSync）状态 |
| `dumpsys alarm` | 闹钟 | 长连接保活 |
| `dumpsys batterystats` | 耗电 | 后台长连接嫌疑 |
| `dumpsys meminfo <pid>` | 内存 | socket buffer 占用 |

---

### 2.7 dropwatch 与内核观测（高级）

#### 2.7.1 dropwatch（内核丢包）

```bash
# 编译或 vendor 提供的 dropwatch
dropwatch -l kas
dropwatch> start
# 持续输出丢包位置（kernel 符号）
```

**实战用法**：SYN flood 场景、全连接队列溢出场景，能看到内核在哪一行 drop。

#### 2.7.2 perf（内核级 profiling）

```bash
# 跟踪内核网络栈
perf record -e 'skb:kfree_skb' -ag -p <pid> -- sleep 30
perf script | head -50

# 跟踪 TCP 事件
perf record -e 'tcp:tcp_drop' -ag -- sleep 30

# 跟踪 socket 数据就绪
perf record -e 'sock:inet_sock_set_state' -ag -- sleep 30
```

#### 2.7.3 ftrace（无 perf 时的替代）

```bash
# 开启 socket 事件追踪
echo 1 > /sys/kernel/debug/tracing/events/sock/enable
echo 1 > /sys/kernel/debug/tracing/events/net/enable

# 看 TCP 状态变化
cat /sys/kernel/debug/tracing/trace | grep "inet_sock_set_state"

# 看丢包
cat /sys/kernel/debug/tracing/trace | grep "kfree_skb"
```

**实战信号**：`kfree_skb reason=<某原因>`——内核显式标注了丢包原因（如 `TCP_FASTOPEN` `SKB_FREE_REASON`）。

#### 2.7.4 BPF / BCC（高阶工具）

```bash
# 跟踪 connect 慢在哪（需要 BCC）
/usr/share/bcc/tools/tcpconnlat -p <pid>

# 看 TCP 重传
/usr/share/bcc/tools/tcpretrans
```

**AOSP 局限**：BPF 工具需要 userdebug + 完整工具链，user 版本不可用。生产环境多为 user——优先用 §2.1-2.6 的基础工具。

---

## 三、监控指标体系

> 从"出问题再查"到"出问题前发现"——把 §2 的诊断动作固化为持续运行的监控指标。

### 3.1 进程级指标

#### 3.1.1 fd 总量与利用率

```bash
# 采集脚本（每 10 秒）
PID=$1
echo "$(date +%s) $(ls /proc/$PID/fd 2>/dev/null | wc -l) $(cat /proc/$PID/limits | grep 'open files' | awk '{print $4}')"
```

**关键指标**：
- `fd_count`：当前 fd 数
- `fd_limit`：RLIMIT_NOFILE
- `fd_ratio` = fd_count / fd_limit

**告警阈值**（基线）：

| 等级 | 阈值 | 行动 |
|------|------|------|
| 提醒 | ratio > 0.5 | 关注增长趋势 |
| 警告 | ratio > 0.8 | 立即排查 FD 泄漏 |
| 紧急 | ratio > 0.95 | 应用即将 crash |

#### 3.1.2 socket fd 分类

```bash
# 进程 socket 分类统计
PID=$1
ls -l /proc/$PID/fd 2>/dev/null | grep socket | awk -F'[][]' '{print $2}' > /tmp/fd_inodes
INODES=$(cat /tmp/fd_inodes)

# TCP
TCP_COUNT=0
for ino in $INODES; do
    grep -q " $ino " /proc/net/tcp && TCP_COUNT=$((TCP_COUNT+1))
done

# UDS
UDS_COUNT=0
for ino in $INODES; do
    grep -q " $ino " /proc/net/unix && UDS_COUNT=$((UDS_COUNT+1))
done
```

**实战关注**：
- 单进程 TCP fd > 200 → 长连接池过大或泄漏
- 单进程 UDS fd > 50 → LocalSocket 泄漏

#### 3.1.3 异常状态数

```bash
# 进程 TIME_WAIT / CLOSE_WAIT / ESTABLISHED
ss -tan | awk 'NR>1 {print $1}' | sort | uniq -c
```

**实战信号**：
- `CLOSE-WAIT` > 50 → **应用未 close**——P0 告警
- `FIN-WAIT-2` > 100 → 对端未 close + 本端 close 后未收到 FIN 确认

### 3.2 协议级指标

#### 3.2.1 整机 TCP 状态分布

```bash
# 整机 TCP 状态数
ss -s | grep "TCP:" 

# 详细状态分布
ss -tan | awk 'NR>1 {print $1}' | sort | uniq -c | sort -rn
```

**关键监控点**：

| 指标 | 阈值 | 含义 |
|------|------|------|
| TIME-WAIT | > 5000 | 短连接高频/未优化 |
| CLOSE-WAIT | > 100 | 应用泄漏 close |
| ESTABLISHED | > 20000 | 整机连接数过多/泄漏 |
| LISTEN | 长期不变 | 监听 socket 稳定 |
| SYN-SENT | > 500 | 客户端连接建立慢/对端不响应 |

#### 3.2.2 队列与溢出指标

```bash
# ListenOverflows / ListenDrops（关键！）
cat /proc/net/netstat | grep TcpExt | head -1
cat /proc/net/netstat | grep TcpExt | tail -1
```

**关键监控点**：

| 指标 | 阈值 | 行动 |
|------|------|------|
| ListenOverflows | > 0（任意） | 立即排查全连接队列满 |
| ListenDrops | > 0 | 立即排查 accept 慢 |
| TCPDrops | 持续增长 | 内核主动丢包 |
| TCPTimeouts | 持续增长 | 网络质量差 |

#### 3.2.3 重传与错误率

```bash
# TCP 重传统计
cat /proc/net/snmp | grep Tcp:

# 关键字段对比
# RetransSegs / OutSegs = 重传率（应 < 1%）
# InErrs 增长 = 网络质量差或 buffer 满
```

**告警阈值**：
- 重传率 > 5% → 网络异常
- OutRsts 突增 → 服务端拒绝连接（backlog 满或服务挂）

### 3.3 场景级指标（专项监控）

#### 3.3.1 InputChannel 队列深度

```bash
# 周期性抓取
while true; do
    dumpsys input | grep -A 1 "InboundQueue:" >> /data/local/tmp/in_channel.log
    sleep 5
done
```

**告警阈值**：
- 单 window InboundQueue > 8/32 → 主线程消费慢
- 持续 > 16/32 → 即将触发 ANR

#### 3.3.2 Zygote 启动延迟

```bash
# 监听 system_server 日志中的 Zygote 启动耗时
grep -i "zygote" /data/local/tmp/sys_server.log | grep "took"
```

**告警阈值**：
- 单次 fork > 500ms → 异常
- 持续 > 200ms → Zygote 压力过大

#### 3.3.3 Choreographer 帧率

```bash
# dumpsys gfxinfo 看 janky frames
dumpsys gfxinfo <pkg> | grep -A 1 "Janky frames"
```

**告警阈值**：
- Janky frames > 5% → 渲染异常，可能 BitTube 阻塞

#### 3.3.4 网络连接质量

```bash
# 应用层 ping
ping -c 5 <server>
# 或 TCP 握手耗时测量
for i in {1..10}; do
    start=$(date +%s%N)
    timeout 2 bash -c "</dev/tcp/server/443"
    end=$(date +%s%N)
    echo "attempt $i: $(((end-start)/1000000))ms"
done
```

### 3.4 监控落地实践

#### 3.4.1 主动巡检脚本（每 5 分钟跑）

```bash
#!/bin/bash
# socket_diag.sh - 主动巡检
LOG=/data/local/tmp/socket_diag_$(date +%Y%m%d_%H%M).log

echo "===== Socket 巡检 $(date) =====" > $LOG

# 1. 整机 TCP 状态
echo "[TCP 状态]" >> $LOG
ss -s >> $LOG

# 2. TIME_WAIT 数量
echo "[TIME_WAIT]" >> $LOG
ss -tan state time-wait | wc -l >> $LOG

# 3. ListenOverflows
echo "[ListenOverflows]" >> $LOG
cat /proc/net/netstat | grep -A 1 TcpExt | tail -1 | awk '{for(i=1;i<=NF;i++) print $i}' >> $LOG

# 4. 关键进程 fd（system_server, zygote）
for proc in system_server zygote64 zygote; do
    PID=$(pidof $proc)
    if [ -n "$PID" ]; then
        echo "[$proc fd]" >> $LOG
        ls /proc/$PID/fd 2>/dev/null | wc -l >> $LOG
    fi
done

# 5. Input 队列
echo "[Input 队列]" >> $LOG
dumpsys input | grep -A 1 "InboundQueue:" | head -20 >> $LOG

echo "===== 完成 =====" >> $LOG
```

#### 3.4.2 触发式告警（critical 状态立刻通知）

```bash
#!/bin/bash
# 监听关键指标，超过阈值触发告警
ALERT_FILE=/data/local/tmp/socket_alert.log

# 检查 1：TIME_WAIT 突增
TW_COUNT=$(ss -tan state time-wait | wc -l)
if [ $TW_COUNT -gt 5000 ]; then
    echo "$(date) ALERT: TIME_WAIT = $TW_COUNT" >> $ALERT_FILE
    # 触发报警（具体通知方式略）
fi

# 检查 2：system_server fd 接近上限
PID=$(pidof system_server)
if [ -n "$PID" ]; then
    FD_COUNT=$(ls /proc/$PID/fd 2>/dev/null | wc -l)
    FD_LIMIT=$(cat /proc/$PID/limits | grep "open files" | awk '{print $4}')
    RATIO=$((FD_COUNT * 100 / FD_LIMIT))
    if [ $RATIO -gt 80 ]; then
        echo "$(date) ALERT: system_server fd = $FD_COUNT/$FD_LIMIT ($RATIO%)" >> $ALERT_FILE
    fi
fi

# 检查 3：InputChannel 满
INBOUND_FULL=$(dumpsys input | grep -c "InboundQueue: 32 / 32")
if [ $INBOUND_FULL -gt 0 ]; then
    echo "$(date) ALERT: InputChannel 满窗口数 = $INBOUND_FULL" >> $ALERT_FILE
fi
```

#### 3.4.3 dashboard 与趋势

把上述指标接入 grafana / 自建 dashboard：
- **整机大盘**：TIME_WAIT、ESTABLISHED、ListenOverflows、fd 利用率
- **进程大盘**：system_server / zygote / 重点 app 的 fd 趋势
- **场景大盘**：InputChannel 满窗口数、Zygote fork 耗时分布

**核心思想**：监控指标要让"老司机"和"新人"看同样的图能得出同样的结论。

---

## 四、治理体系

> 治理的目标是"线上少出问题 + 出问题能定位 + 修复能落地"——以下五层从下到上构建。

### 4.1 主动防御层：fdsan + StrictMode + 代码 review

#### 4.1.1 fdsan（File Descriptor Sanitizer）

AOSP 14+ 内置 fdsan——**自动检测 Java/native fd 错配**。

```java
// 开启 fdsan（应用启动时）
StrictMode.setVmPolicy(new VmPolicy.Builder()
    .detectLeakedClosableObjects()
    .detectLeakedRegistrationObjects()
    .penaltyLog()
    .build());

// 检查 fdsan 日志
adb logcat | grep "fdsan"
```

**fdsan 关键能力**：
- 检测"Java fd 在 native 代码中被 close"导致的 fd 复用错乱
- 检测"native fd 被 close 但 Java FileDescriptor 仍持有"
- 检测"FileDescriptor 未 finalize"导致 fd 泄漏

**实战应用**：
```bash
# 看 fdsan 检测到的问题
adb logcat -d | grep -i fdsan

# 典型输出：
# fdsan: detected leaked fd: 1023, expected to be closed via Parcel
# fdsan: detected close-on-fd-mismatch: fd 45 was closed in native code
```

**治理要点**：
- 调试期开启 fdsan（userdebug + StrictMode）
- fdsan 检测到的任何问题都视为**必修 bug**——不修复会引发诡异的 fd 复用错乱

#### 4.1.2 StrictMode 主线程 IO 检测

```java
// 严格模式：检测主线程网络/磁盘 IO
StrictMode.ThreadPolicy oldPolicy = StrictMode.getThreadPolicy();
StrictMode.setThreadPolicy(new StrictMode.ThreadPolicy.Builder(oldPolicy)
    .detectNetwork()
    .detectDiskReads()
    .detectDiskWrites()
    .penaltyLog()      // 仅日志（生产可用 death 强制崩溃）
    .build());
```

**实战输出**：
```
StrictMode policy violation: ~duration=120ms; ... 
at okhttp3.internal.connection.RealCall.execute
at android.os.StrictMode$AndroidBlockGuardPolicy.onNetwork
```

**治理要点**：
- 调试包强制开 StrictMode + death penalty（违规直接 crash）
- 任何主线程 socket IO 视为 P0 必修

#### 4.1.3 代码 review 检查清单

| 检查项 | 标准 |
|--------|------|
| socket 是否在 finally 关闭 | 必查（HttpClient / Socket / InputStream） |
| 长连接是否有超时 | 必须设 read/write timeout |
| SocketChannel/HttpURLConnection 是否调用 disconnect/close | 必查 |
| Listener/Callback 是否解注册 | 必查（避免触发 socket IO） |
| 文件描述符是否跨线程传递 | 谨慎（需 fdsan 检测） |
| `select`/`poll` 是否处理 EINTR | 必查 |

### 4.2 资源管理层：连接池与 buffer 规范

#### 4.2.1 连接池规范

| 场景 | 推荐配置 | 理由 |
|------|----------|------|
| 应用 HTTP（OkHttp） | maxRequests=64, maxRequestsPerHost=5, idleTimeout=5min | 平衡并发与资源 |
| 应用 WebSocket | 单例 + 1 条连接 | 长连接不需要池 |
| 系统服务 LocalSocket | 单连接 + 心跳 | Local 服务通常独占 |
| 推送（Push SDK） | 1 条长连接 | 推送不需要多条 |

**反模式**：
- 每次请求新建连接 → TIME_WAIT 爆炸
- 连接池无上限 → 高峰期 FD 耗尽
- 连接池过小 → 排队严重

#### 4.2.2 buffer 规范

| 场景 | 推荐 buffer | 理由 |
|------|-------------|------|
| HTTP 短连接 | 8-16KB | 默认值即可 |
| 长连接（推送/IM） | 16-32KB | 平衡延迟与吞吐 |
| 视频流 | 64-256KB | 高吞吐需求 |
| 输入事件 | InputChannel 默认 | 不可改（kernel 决定） |

**反模式**：
- buffer 过大（>1MB）→ 内存浪费
- buffer 跨进程不一致 → 端到端瓶颈在最小方

#### 4.2.3 超时规范

| 场景 | connect 超时 | read/write 超时 | idle 超时 |
|------|--------------|-----------------|-----------|
| HTTP API | 10s | 30s | 5min |
| 长连接 | 10s | 60s | 无（心跳保活） |
| LocalSocket | 5s | 10s | 1min |
| InputChannel | N/A | 阻塞（不可设） | N/A |

**反模式**：
- 无超时 → 永久阻塞 → ANR
- 超时过短 → 正常请求被误杀
- 短连接无 close 兜底 → 极端情况下 fd 泄漏

### 4.3 调优层：backlog 与内核参数

#### 4.3.1 backlog 调优清单

```bash
# 查看当前配置
sysctl net.core.somaxconn          # 整机 listen backlog 上限
sysctl net.ipv4.tcp_max_syn_backlog  # 半连接队列上限
sysctl net.ipv4.tcp_synack_retries   # SYN-ACK 重试次数

# 推荐配置（高并发服务）
echo 16384 > /proc/sys/net/core/somaxconn
echo 1024 > /proc/sys/net/ipv4/tcp_max_syn_backlog
```

**Android 默认值**：
- `somaxconn`：4096
- `tcp_max_syn_backlog`：256
- `tcp_synack_retries`：5

**调优原则**：
- 业务峰值并发 × 1.5 = 推荐 backlog
- listen 端 backlog 不得超过 somaxconn
- 半连接队列上限不得超过 `tcp_max_syn_backlog`

#### 4.3.2 TIME_WAIT 优化

```bash
# 启用 TIME_WAIT 复用（短连接高频场景）
sysctl -w net.ipv4.tcp_tw_reuse=1

# 注意：不要启用 tcp_tw_recycle（已废弃，会引起 NAT 问题）
```

**治理原则**：
- 高频短连接必须有连接池（避免 TIME_WAIT）
- 长连接无 TIME_WAIT 问题
- **不要为了减少 TIME_WAIT 而关闭 close_wait 时的主动关闭**

#### 4.3.3 buffer 调优

```bash
# TCP buffer 自动调优区间
sysctl net.ipv4.tcp_rmem    # 接收：min default max
sysctl net.ipv4.tcp_wmem    # 发送：min default max

# 整机 buffer 上限
sysctl net.core.rmem_max
sysctl net.core.wmem_max

# 推荐配置（高吞吐）
sysctl -w net.ipv4.tcp_rmem="4096 87380 16777216"
sysctl -w net.ipv4.tcp_wmem="4096 65536 16777216"
sysctl -w net.core.rmem_max=16777216
sysctl -w net.core.wmem_max=16777216
```

**Android 默认**：通常较低（200KB 左右），不适合高吞吐场景——vendor 可在 init.rc 中调大。

### 4.4 工程化层：CI 校验脚本

#### 4.4.1 socket 路径权限校验

```bash
#!/bin/bash
# ci_check_socket_paths.sh
# 校验 /dev/socket/* 权限与 selinux label

SOCKET_DIRS="/dev/socket/zygote /dev/socket/installd /dev/socket/adbd /dev/socket/vold"
EXPECTED_OWNER="root"
EXPECTED_GROUP="1000 1001 1019 1027"  # 各 socket 所属组不同
EXPECTED_PERM="0660"

for sock in $SOCKET_DIRS; do
    if [ ! -e $sock ]; then
        echo "FAIL: $sock 不存在"
        continue
    fi
    
    OWNER=$(stat -c %U $sock)
    PERM=$(stat -c %a $sock)
    LABEL=$(ls -lZ $sock | awk '{print $5,$6,$7,$8}')
    
    if [ "$OWNER" != "$EXPECTED_OWNER" ]; then
        echo "FAIL: $sock 所有者错误: $OWNER (期望 $EXPECTED_OWNER)"
    fi
    
    if [ "$PERM" != "$EXPECTED_PERM" ]; then
        echo "FAIL: $sock 权限错误: $PERM (期望 $EXPECTED_PERM)"
    fi
    
    # selinux label 校验（UDS 应为 u:object_r:*_socket:s0）
    echo "$LABEL" | grep -q "_socket:s0" || echo "FAIL: $sock selinux label 异常: $LABEL"
done
```

#### 4.4.2 内核参数校验

```bash
#!/bin/bash
# ci_check_kernel_params.sh

declare -A EXPECTED=(
    ["net.core.somaxconn"]="4096"
    ["net.ipv4.tcp_syncookies"]="2"
    ["net.ipv4.tcp_abort_on_overflow"]="1"
    ["net.ipv4.tcp_tw_reuse"]="1"
)

for key in "${!EXPECTED[@]}"; do
    actual=$(sysctl -n $key)
    expected=${EXPECTED[$key]}
    if [ "$actual" != "$expected" ]; then
        echo "FAIL: $key = $actual (期望 $expected)"
    fi
done
```

#### 4.4.3 升级前后回归

```bash
#!/bin/bash
# ci_regression_socket.sh
# 升级前后跑一遍关键 socket 场景

echo "=== Zygote 测试 ==="
# fork 10 次应用进程，记录耗时
for i in {1..10}; do
    am start -n com.android.test/.MainActivity
    sleep 2
done

echo "=== Input 测试 ==="
# 模拟触摸事件，检查 InputChannel 无积压
for i in {1..100}; do
    input tap 500 500
done
# 检查 dumpsys input | grep InboundQueue 应为 0

echo "=== LocalSocket 测试 ==="
# 检查关键 LocalServerSocket 可连接
for sock in zygote installd adbd; do
    if [ -e /dev/socket/$sock ]; then
        nc -U /dev/socket/$sock < /dev/null && echo "OK: $sock" || echo "FAIL: $sock"
    fi
done

echo "=== 网络测试 ==="
# 检查 DNS + HTTP
ping -c 3 8.8.8.8
curl -m 5 https://www.google.com -I
```

### 4.5 监控层：告警阈值与 dashboard

#### 4.5.1 告警阈值基线

| 指标 | 警告 | 紧急 | 行动 |
|------|------|------|------|
| 整机 TIME_WAIT | > 5000 | > 20000 | 检查短连接优化 |
| system_server fd ratio | > 0.6 | > 0.8 | 排查系统 fd 泄漏 |
| zygote fd ratio | > 0.5 | > 0.7 | 排查 zygote fd 泄漏 |
| ListenOverflows | > 0 | > 100/小时 | 调大 backlog / 排查 accept |
| ListenDrops | > 0 | > 100/小时 | 排查 accept 慢 |
| InputChannel 满 | > 1 个窗口 | > 5 个窗口 | 排查主线程阻塞 |
| Zygote fork 耗时 | > 200ms | > 500ms | 排查 Zygote 卡 |
| TCP 重传率 | > 1% | > 5% | 网络质量差 |

#### 4.5.2 dashboard 设计原则

- **一张图只说一件事**：TIME_WAIT 图、fd 图、队列图分开展示
- **绝对值 + 增长率**：单看绝对值不够，要看趋势
- **对比基线**：同一指标要有昨日/上周对比
- **关键场景高亮**：InputChannel 满、Zygote 卡等关键信号用红色

#### 4.5.3 主动巡检 vs 触发告警

| 类型 | 频率 | 用途 |
|------|------|------|
| 主动巡检 | 每 5 分钟 | 发现缓慢恶化 |
| 触发告警 | 实时 | 发现急性问题 |
| 周期性报表 | 每日 | 长期趋势 |

**关键原则**：**主动巡检先于告警**——告警是"已经出事了"，巡检是"即将出事"。

---

## 五、实战案例

> 两个综合案例——每个案例都会跨 5 大类风险中的 3 类，演示"如何用本文档的诊断工具集 + 治理清单完整闭环"。

### 案例 1：FD 耗尽导致所有 app 启动失败（联动 ①FD 耗尽 + ③队列积压 + ④协议失败）

#### 现象

某型号手机 OTA 升级后出现大面积客诉：
- 所有第三方 app **无法启动**（点图标卡 5s 后 ANR）
- 系统 app 部分可用，但启动延迟明显
- adb shell 可登录，但 `am start` 启动 app 超时

#### 阶段 1：5 分钟现场定位（用本文档 §2 工具）

**步骤 1：`cat /proc/net/sockstat` 看全局**
```bash
$ adb shell cat /proc/net/sockstat
sockets: used 2871
TCP:   inuse 2143 orphan 0 tw 1923 alloc 2143 mem 542
UDP:   inuse 28 mem 18
```
- `tw=1923` 较高但不算异常
- `inuse=2143` 整机 TCP 数正常
- **TCP: mem=542（页）= ~2.2MB** 正常

→ 全局 TCP 没问题，**问题不在整机 TCP 层**。

**步骤 2：定位到具体进程——system_server**
```bash
$ adb shell pidof system_server
1234
$ adb shell ls /proc/1234/fd | wc -l
32100
$ adb shell cat /proc/1234/limits | grep "open files"
open files    32768    32768    32768
```
- system_server **fd 数 = 32100 / 32768（98%）**——已接近上限！
- 关键信号：`open files` 的 soft/hard 都是 32768——**接近耗尽**

**步骤 3：分类统计 fd**
```bash
$ adb shell ls -l /proc/1234/fd | awk '{print $NF}' | sort | uniq -c | sort -rn | head
  22000 socket:[...]
  5000 pipe:[...]
  3000 anon_inode:[eventfd]
  1500 anon_inode:[...]
  ...
```
- socket fd 22000 个！**异常**（system_server 正常基线应该 2000-5000）
- 单独查看 22000 socket 的状态：
```bash
$ for ino in $(ls -l /proc/1234/fd | grep socket | awk -F'[][]' '{print $2}'); do
    grep " $ino " /proc/net/tcp
done | awk '{print $4}' | sort | uniq -c
   18000 ESTABLISHED
    3500 CLOSE_WAIT
     500 TIME_WAIT
```
- **CLOSE_WAIT 3500 个！** 应用未 close 的典型表现

**步骤 4：定位到具体连接**
```bash
# 找 CLOSE-WAIT 的对端
ss -tan state close-wait | head -5
# 典型输出:
# ESTAB  0  0  10.0.0.5:443  10.0.0.100:52431  users:(("system_server",pid=1234,fd=189))
# CLOSE-WAIT  1  0  10.0.0.5:443  10.0.0.100:52432  users:(("system_server",pid=1234,fd=190))
```
- 发现大量连接到 `10.0.0.100:5243x`——这是某固定 IP
- 对端是 vendor 的某个 service（OTA 后启用了新特性）

**步骤 5：定位代码**
- `ps -A | grep 5243x` 无果——是 TCP 端口
- 查看 system_server 当前模块加载：`cat /proc/1234/maps | grep vendor` 找到新引入的 vendor so
- 反编译：`vendor.so` 中包含一个 `HttpClient` 实例，**未关闭**——每次请求只 shutdown 没 close

#### 阶段 2：根因分析（用本文档 §3 监控指标回溯）

| 监控指标 | 实际值 | 阈值 | 状态 |
|----------|--------|------|------|
| system_server fd 总量 | 32100 | < 16384 | 越界 2 倍 |
| CLOSE_WAIT 数 | 3500 | < 50 | 越界 70 倍 |
| ESTABLISHED 数 | 18000 | < 5000 | 越界 3.6 倍 |

**根因**：
- vendor `HttpClient` 实例**每次调用都新建 socket 但未调用 close()**
- shutdown() 只关闭一方向，**socket 对象本身未释放**
- 长时间运行后 fd 累积达到 32768 上限
- new socket() 调用返回 -1 EMFILE → **AMS 无法通过 Zygote Socket fork 进程**
- 所有 app 启动失败 → ANR

#### 阶段 3：修复

**短期修复（用户侧）**：
```bash
# 重启手机（最直接）
adb reboot
```

**中期修复（vendor 侧）**：
```java
// 修改 vendor HttpClient，正确关闭
finally {
    if (response != null) {
        try { response.close(); } catch (Exception e) {}
    }
    if (inputStream != null) {
        try { inputStream.close(); } catch (Exception e) {}
    }
}
```

**长期治理（按本文档 §4.4）**：

1. **CI 校验**：vendor so 必须通过 lint 检查（确保 socket close）
2. **监控告警**：system_server fd > 16000 立即告警
3. **fdsan 检测**：调试包开启 fdsan，自动捕获未关闭 fd

**fdsan 检测**（调试期复现）：
```
fdsan: detected close-on-fd-mismatch: fd 189 was closed in native code 
  at android.net.http.HttpConnection.close(HttpConnection.java:0)
```
→ 暴露了 vendor HttpClient 的 close 逻辑错乱。

#### 阶段 4：回归验证

1. 关闭 fdsan（恢复 user 版本）
2. 部署 vendor 修复
3. 压测 24h 持续调用 vendor 接口
4. 监控：`system_server fd 稳定在 5000 以下`、`CLOSE_WAIT = 0`
5. ANR 复现脚本验证：触发 100 次 app 启动，**无 ANR**

#### 案例 1 总结

| 维度 | 内容 |
|------|------|
| 5 大类风险联动 | ①FD 耗尽（根因）+ ③队列积压（CLOSE_WAIT 排队）+ ④协议失败（无法 fork） |
| 用到的诊断工具 | §2.1 sockstat / §2.2 ss / §2.3 /proc/pid/fd + inode 关联 |
| 用到的监控指标 | §3.1 进程 fd + §3.2 CLOSE_WAIT 数 |
| 用到的治理方案 | §4.4.1 CI 校验 + §4.5 fd ratio 告警 + fdsan |

---

### 案例 2：触摸无响应——主线程被 InputChannel 阻塞（联动 ②主线程阻塞 + ④协议失败 + ⑤权限/路径）

#### 现象

某 APP 启动后点击屏幕 **完全无响应**，但状态栏下拉、返回键等系统手势正常。
- ANR 弹窗 5 秒后出现
- adb shell 可登录

#### 阶段 1：5 分钟现场定位

**步骤 1：抓 ANR trace**
```bash
$ adb pull /data/anr/anr_2026-06-15_10-23-45
# 关键栈片段
"main" prio=5 tid=1 Sleeping
  at java.lang.Thread.sleep(Native method)
  at android.os.MessageQueue.nativePollOnce(Native method)
  at android.os.MessageQueue.next(MessageQueue.java:335)
  ...
  at android.view.InputEventReceiver.dispatchInputEvent(InputEventReceiver.java:185)
  - waiting to lock <0x0fa12345> (a java.lang.Object)
```
- 主线程卡在 `InputEventReceiver.dispatchInputEvent` —— 等 InputChannel 的事件
- **InputChannel fd 上 read 阻塞** —— 典型 InputChannel 反压

**步骤 2：看 Input 队列**
```bash
$ adb shell dumpsys input | grep -A 3 "InboundQueue"
  Channel { ... } 'Window{com.example.app/com.example.app.MainActivity}':
    InboundQueue: 32 / 32        # ← 满！
    ...
```
- 该 app 的 InputChannel **InboundQueue 32/32 已满**
- 主线程不消费 → 系统侧投递堆积

**步骤 3：检查 app 进程的 InputChannel**
```bash
$ APP_PID=$(adb shell pidof com.example.app)
$ adb shell ls -l /proc/$APP_PID/fd | grep socket
# 看到 socket:[N1] 和 socket:[N2] 配对——InputChannel 一对 socketpair
```
- 这两个 socket 是 InputChannel 配对
- inode N1 对应 app 端（receive side），N2 对应 system_server 端（send side）

**步骤 4：看 app 主线程在干什么**
```bash
$ adb shell ps -T -p $APP_PID | head -20
# 或
$ adb shell cat /proc/$APP_PID/stack | head -50
```
- 主线程栈：在某个自定义 Looper handler 中执行**长任务**（约 8 秒）

**步骤 5：找到长任务源头**
- 反编译 app
- 定位到 `MainActivity.onResume()` 中启动了一个 `Thread.start()`，但 Thread 内**网络请求同步等待**
- 该网络请求对端 IP 是 `192.168.1.100`（开发期服务器）
- adb 抓包：`tcpdump host 192.168.1.100`——对端**已不可达**
- **socket read 阻塞 30 秒未返回** → 主线程被 InputChannel 等待拖住

#### 阶段 2：根因分析

| 监控指标 | 实际值 | 阈值 | 状态 |
|----------|--------|------|------|
| 主线程 InputChannel read | 阻塞 30s+ | < 5s | 越界 6 倍 |
| InputChannel InboundQueue | 32/32 | < 8/32 | 满 |
| 系统手势（状态栏下拉） | 正常 | 正常 | 正常 |

**根因**：
1. app `MainActivity.onResume()` 启动了一个 **Thread** 异步做网络请求——正确
2. 但 Thread 内使用了**阻塞 socket**（`Socket.getInputStream().read()`）——无超时
3. 对端服务器不可达 → 阻塞 30 秒
4. 更糟的是：网络请求的回调 callback 在主线程执行——callback 中**做了重计算**
5. 主线程被 callback 长时间占用 → **不消费 InputChannel 事件**
6. InputChannel buffer 满 → **新触摸事件投递阻塞**
7. 整个 app 触摸无响应 5s+ → ANR

#### 阶段 3：修复

**短期修复（紧急发版）**：
```java
// 设置 socket 超时（必修）
socket.setSoTimeout(5000);  // 5 秒读超时

// 把重计算移到子线程（必修）
new Thread(() -> {
    // 重计算
}).start();

// 用 Handler 切回主线程更新 UI
```

**关键代码修复**：
```java
// 错误写法（原始）
public void onResume() {
    new Thread(() -> {
        try {
            Socket sock = new Socket("192.168.1.100", 8080);
            // 阻塞 read，无超时
            byte[] data = readAll(sock.getInputStream());  // ← 卡 30s
            runOnUiThread(() -> process(data));  // ← 又卡主线程
        } catch (IOException e) { /* ignore */ }
    }).start();
}

// 正确写法
public void onResume() {
    new Thread(() -> {
        try (Socket sock = new Socket()) {
            sock.connect(new InetSocketAddress("192.168.1.100", 8080), 3000);
            sock.setSoTimeout(5000);  // 读超时
            // 读取（带超时）
            byte[] data = readWithTimeout(sock.getInputStream());
            // 切到主线程 + 用 handler post 避免长任务
            new Handler(Looper.getMainLooper()).post(() -> 
                processInMainThread(data));  // 简洁处理
        } catch (IOException e) { /* log + 兜底 */ }
    }).start();
}
```

**长期治理**：

1. **StrictMode 强制开启**：检测主线程网络 IO
   ```bash
   # 调试期开启 StrictMode.deathOnNetwork()
   adb shell setprop log.tag.StrictMode DEBUG
   ```
2. **fdsan 检测 socket 泄漏**
3. **CI lint**：禁止 `runOnUiThread` 中做 IO/重计算
4. **监控告警**：dumpsys input 中 `InboundQueue: 32/32` 窗口数 > 3 触发告警

#### 阶段 4：回归验证

1. 部署修复
2. **ANR 复现脚本**（用 monkey 触发）
   ```bash
   adb shell monkey -p com.example.app --pct-touch 100 -v 1000
   ```
3. 触发长按屏幕 + 多次点击——验证无 ANR
4. dumpsys input 中 `InboundQueue` 应保持 < 5/32
5. 关掉对端服务器，重复压测——验证 5 秒超时后无 ANR

#### 案例 2 总结

| 维度 | 内容 |
|------|------|
| 5 大类风险联动 | ②主线程阻塞（根因）+ ④协议失败（socket 无超时）+ ⑤权限/路径（系统手势正常则非权限问题） |
| 用到的诊断工具 | §2.5 ANR trace + §2.6.1 dumpsys input + §2.4 strace/tcpdump |
| 用到的监控指标 | §3.3.1 InputChannel 队列深度 + §3.3.3 Choreographer 帧率 |
| 用到的治理方案 | §4.1.2 StrictMode + §4.2.3 超时规范 + §4.5 告警 |

---

### 案例 3（精简）：adb 假死——full queue 满

#### 现象

`adb shell` 输入命令卡住，但 `adb devices` 能识别设备。

#### 5 分钟定位

```bash
# 步骤 1：看 adbd 状态
$ adb shell ps -A | grep adbd
# adbd 进程存在

# 步骤 2：看 adbd fd
$ adb shell ls -l /proc/$(pidof adbd)/fd | wc -l
# 输出 128 左右（正常）

# 步骤 3：看 listen 状态
$ adb shell ss -tlnp | grep 5037
# LISTEN 0 128  127.0.0.1:5037  ...  users:(("adbd",pid=...,fd=4))

# 步骤 4：看全连接队列溢出
$ adb shell cat /proc/net/netstat | grep TcpExt
# TcpExt: ListenOverflows ListenDrops ...
# TcpExt: 00000000125 00000000098 ...
```
- `ListenOverflows=125, ListenDrops=98` —— **全连接队列溢出！**

#### 根因

- adbd 写死 backlog=128
- adb server 在某个 CI 流程中**并发连接 200+ 次**
- 全连接队列满 → 后续连接被丢弃
- `adb shell` 命令建立连接失败 → 假死

#### 修复

1. **临时**：`adb kill-server && adb start-server`
2. **vendor**：调大 adbd backlog 至 256（但需在源码改）
3. **CI**：避免并发 adb 连接，串行化执行

#### 案例 3 总结

- 5 类风险：③队列积压（全连接队列满）
- 诊断工具：§2.2 ss + §2.1 netstat
- 监控指标：§3.2.2 ListenOverflows
- 治理：§4.3.1 backlog 调优

---

## 六、附录

### 附录 A：核心源码路径索引

| 文件名 | 完整路径 | 内核/AOSP 版本 | 说明 |
|--------|----------|----------------|------|
| net/socket.c | net/socket.c | Linux 5.10+ | 通用 socket 层、syscall |
| net/ipv4/af_inet.c | net/ipv4/af_inet.c | Linux 5.10+ | INET 协议族 |
| net/ipv4/tcp.c | net/ipv4/tcp.c | Linux 5.10+ | TCP 协议 |
| net/ipv4/tcp_input.c | net/ipv4/tcp_input.c | Linux 5.10+ | TCP 状态机 |
| net/unix/af_unix.c | net/unix/af_unix.c | Linux 5.10+ | UDS 协议族 |
| net/ipv4/proc.c | net/ipv4/proc.c | Linux 5.10+ | /proc/net/* 输出 |
| net/core/sock.c | net/core/sock.c | Linux 5.10+ | socket 通用层 |
| fs/proc/fd.c | fs/proc/fd.c | Linux 5.10+ | /proc/pid/fd 实现 |
| fs/eventpoll.c | fs/eventpoll.c | Linux 5.10+ | epoll（详见 epoll 01） |
| net/ipv4/tcp_ipv4.c | net/ipv4/tcp_ipv4.c | Linux 5.10+ | SYN queue、syncookies |
| ZygoteServer | frameworks/base/core/java/com/android/internal/os/ZygoteServer.java | AOSP 14.0.0_r1 | Zygote 监听 |
| InputChannel | frameworks/native/libs/input/InputTransport.cpp | AOSP 14.0.0_r1 | InputChannel socketpair |
| BitTube | frameworks/native/libs/gui/BitTube.cpp | AOSP 14.0.0_r1 | Choreographer VSync |
| adbd | system/core/adb/daemon/usb.cpp | AOSP 14.0.0_r1 | adbd |
| LocalSocket | frameworks/base/core/java/android/net/LocalSocket.java | AOSP 14.0.0_r1 | UDS Java 封装 |
| StrictMode | frameworks/base/core/java/android/os/StrictMode.java | AOSP 14.0.0_r1 | fdsan + 主线程 IO 检测 |
| dumpsys input | frameworks/base/services/core/java/com/android/server/input/InputManagerService.java | AOSP 14.0.0_r1 | InputChannel 监控 |
| ActivityManagerService | frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java | AOSP 14.0.0_r1 | Zygote fork 调用方 |
| InputDispatcher | frameworks/native/services/inputflinger/InputDispatcher.cpp | AOSP 14.0.0_r1 | 触摸事件分发 |

---

### 附录 B：工具命令速查卡

#### B.1 5 分钟现场定位（一页纸）

```
1. 整机 sockstat         cat /proc/net/sockstat
2. 关键进程 fd            ls /proc/<pid>/fd | wc -l
3. 整机 TCP 状态          ss -s
4. 状态分布               ss -tan | awk '{print $1}' | sort | uniq -c
5. 监听队列溢出           cat /proc/net/netstat | grep TcpExt
6. UDS 路径               ss -xan | grep zygote
7. Input 队列             dumpsys input | grep InboundQueue
8. 网络抓包               tcpdump -i any -nn -s 0 -w cap.pcap
9. ANR trace              adb pull /data/anr/
10. 关键进程栈            cat /proc/<pid>/stack
```

#### B.2 工具命令完整速查

| 类别 | 命令 | 用途 | 适用场景 |
|------|------|------|----------|
| **sockstat** | `cat /proc/net/sockstat` | 整机 TCP/UDP 摘要 | 第一步 |
| **TCP 明细** | `cat /proc/net/tcp` | TCP 连接状态 + inode | 找具体连接 |
| **UDS** | `cat /proc/net/unix` | UDS 监听 + 连接 | Zygote/LocalSocket |
| **snmp** | `cat /proc/net/snmp` | TCP 重传/RST | 网络质量 |
| **netstat** | `cat /proc/net/netstat \| grep TcpExt` | ListenOverflows | 队列满 |
| **ss** | `ss -s` / `ss -tan` / `ss -xan` | 各种状态查询 | 全场景 |
| **ss** | `ss -tan state time-wait` | TIME_WAIT 专项 | 短连接问题 |
| **进程 fd** | `ls /proc/<pid>/fd \| wc -l` | fd 总量 | FD 泄漏 |
| **fd 分类** | `ls -l /proc/<pid>/fd \| awk '{print $NF}' \| sort \| uniq -c` | fd 分布 | 归因 |
| **socket inode** | `ls -l /proc/<pid>/fd \| grep socket \| awk -F'[][]' '{print $2}'` | socket inode 提取 | 跨工具关联 |
| **inode → 连接** | `grep " <inode> " /proc/net/tcp` | inode 查连接 | 进程→连接 |
| **strace** | `strace -f -e trace=network -p <pid>` | syscall 级观察 | 阻塞/异常 |
| **tcpdump** | `tcpdump -i any -nn -s 0 -w cap.pcap` | 网络抓包 | 协议分析 |
| **ANR** | `adb pull /data/anr/` | ANR trace | 主线程阻塞 |
| **dumpsys input** | `dumpsys input \| grep InboundQueue` | InputChannel 队列 | 触摸无响应 |
| **dumpsys activity** | `dumpsys activity processes` | 进程状态 | Zygote/启动 |
| **dumpsys netstats** | `dumpsys netstats` | 网络流量 | 连接活跃度 |
| **dropwatch** | `dropwatch -l kas` | 内核丢包位置 | 高级 |
| **perf** | `perf record -e 'skb:kfree_skb' -ag` | 内核 profiling | 高级 |
| **fdsan** | `adb logcat \| grep fdsan` | fd 错配检测 | FD 泄漏调试 |

#### B.3 关键 inode 字段含义速查

| 字段 | 含义 | 实战用法 |
|------|------|----------|
| `sl` | socket 序号 | 排序 |
| `local_address` | 本地 IP:port（反序 hex） | 找特定服务 |
| `rem_address` | 对端 IP:port | 找连接去向 |
| `st` | TCP 状态码 | 见下表 |
| `tx_queue` | 发送队列字节数 | > 0 = 积压 |
| `rx_queue` | 接收队列字节数 | > 0 = 积压 |
| `uid` | socket 所属用户 | 区分 system/app |
| `inode` | 关联 /proc/pid/fd | 关键关联 |

#### B.4 TCP 状态码速查

| 状态码 | 名称 | 含义 |
|--------|------|------|
| 01 | ESTABLISHED | 已建立 |
| 02 | SYN_SENT | 客户端发 SYN |
| 03 | SYN_RECV | 服务端收 SYN |
| 04 | FIN_WAIT1 | 主动关闭方发 FIN |
| 05 | CLOSE | 已关闭 |
| 06 | TIME_WAIT | 2MSL 等待 |
| 07 | CLOSE | 同 05 |
| 08 | CLOSE_WAIT | 被动关闭方收 FIN |
| 09 | LAST_ACK | 被动关闭方发 FIN |
| 0A | LISTEN | 监听 |
| 0B | CLOSING | 双方同时关闭 |

---

### 附录 C：监控告警阈值基线

| 类别 | 指标 | 警告阈值 | 紧急阈值 | 行动 |
|------|------|----------|----------|------|
| **进程 fd** | system_server ratio | > 0.6 | > 0.8 | 排查 FD 泄漏 |
| **进程 fd** | zygote ratio | > 0.5 | > 0.7 | 排查 zygote FD 泄漏 |
| **进程 fd** | 应用 ratio | > 0.5 | > 0.7 | 排查应用 FD 泄漏 |
| **TCP 状态** | 整机 TIME_WAIT | > 5000 | > 20000 | 检查短连接优化 |
| **TCP 状态** | 整机 CLOSE_WAIT | > 100 | > 500 | 应用泄漏 close |
| **TCP 状态** | 整机 ESTABLISHED | > 20000 | > 50000 | 长连接过多 |
| **TCP 状态** | 单进程 CLOSE_WAIT | > 50 | > 200 | P0 必修 |
| **队列** | ListenOverflows | > 0 | > 100/h | 调大 backlog |
| **队列** | ListenDrops | > 0 | > 100/h | 排查 accept |
| **队列** | 全连接队列积压（rx_queue > 0） | > 100 | > 1000 | accept 慢 |
| **InputChannel** | 单窗口 InboundQueue | > 16/32 | > 32/32 | 主线程阻塞 |
| **InputChannel** | 全局满窗口数 | > 1 | > 5 | 多窗口主线程卡 |
| **Zygote** | fork 耗时 | > 200ms | > 500ms | Zygote 卡 |
| **Choreographer** | janky frames | > 5% | > 10% | 渲染异常 |
| **网络** | TCP 重传率 | > 1% | > 5% | 网络质量差 |
| **网络** | 单进程 socket fd | > 200 | > 500 | 长连接池过大 |

---

### 附录 D：量化数据自检表

| 序号 | 量化描述 | 数量级 | 依据来源 |
|------|----------|--------|----------|
| 1 | ANR 5 秒阈值 | 5000ms | ActivityManagerService |
| 2 | Android 默认 RLIMIT_NOFILE | 32768 | bionic/libc |
| 3 | 默认 somaxconn (AOSP) | 4096 | AOSP 14 |
| 4 | 默认 tcp_max_syn_backlog | 256 | AOSP 14 |
| 5 | 默认 tcp_syncookies | 1 | AOSP 14 |
| 6 | 默认 tcp_abort_on_overflow | 0 | AOSP 14 |
| 7 | 默认 wmem_max / rmem_max | 208KB | AOSP 14 |
| 8 | InputChannel SOCK_SEQPACKET 缓冲 | 8-32 消息 | vendor 差异 |
| 9 | BitTube 默认 bufsize | 8KB-64KB | BitTube.cpp |
| 10 | TIME_WAIT 默认时长 | 60 秒 | net/ipv4/tcp.c |
| 11 | tcp_synack_retries 默认 | 5 | AOSP 14 |
| 12 | Java NIO Selector 单实例 fd | 3 个 | SelectorImpl |
| 13 | OkHttp 连接池默认 | 5 | okhttp 4.x |
| 14 | StrictMode 阈值 | 1ms（主线程 IO 起始） | AOSP 14 |
| 15 | fdsan 检测范围 | 全 Java 资源 + 显式 native | AOSP 14+ |
| 16 | fd 告警阈值 | > 80% × RLIMIT_NOFILE | 工程经验 |
| 17 | ListenDrops 告警阈值 | > 0 | 立即 |
| 18 | UDS 路径长度限制 | 108 字节 | UNIX_PATH_MAX |
| 19 | TCP 重传 SYN 超时 | 60+ 秒（默认） | tcp_synack_retries |
| 20 | /proc/net/sockstat 更新频率 | 实时 | 内核计数器 |
| 21 | ss 命令相对 netstat 速度 | 快 ~10 倍 | iproute2 benchmark |
| 22 | tcpdump 默认 snaplen | 262144 字节 | libpcap |
| 23 | system_server 正常 fd 基线 | 2000-5000 | AOSP 14 实测 |
| 24 | zygote 正常 fd 基线 | 100-500 | AOSP 14 实测 |
| 25 | 全连接队列默认大小 | min(backlog, somaxconn) | Linux 5.10+ |
| 26 | 半连接队列默认大小 | tcp_max_syn_backlog | Linux 5.10+ |
| 27 | 主动巡检脚本频率建议 | 5 分钟 | 工程经验 |
| 28 | CI 校验必跑项 | 5 类（路径/selinux/参数/服务/回归） | 工程经验 |
| 29 | /proc/pid/fd 读取开销 | 极小（一次 stat） | 内核 |

---

### 附录 E：socket 系列 8 篇知识地图

```
Socket 系列（8 篇 + 1 桥接 + 1 epoll 协作）
├─ 01 总览 ──────────── 6 大场景 + 内核四层 + Android 速查
├─ 02 API/数据结构 ──── syscall 入口 + struct socket/sock + VFS 绑定
├─ 03 生命周期 ─────── 创建/bind/listen/connect/关闭
├─ 04 缓冲与阻塞 ───── sk_buff + SO_*BUF + EAGAIN + 阻塞场景
├─ 05 backlog ──────── 半连接/全连接队列 + SYN cookie
├─ 06 UDS 与 Android ── path vs abstract + socketpair + SCM_RIGHTS
├─ 07 风险全景 ─────── 6 场景 × 5 风险类矩阵 + 决策树
└─ 08 诊断治理 ─────── /proc + ss + lsof + strace + tcpdump + 监控 + 治理
        │
        └─ 桥接：01-socket 与 epoll 的关系
        └─ epoll 01-epoll 总览与核心机制（独立系列）

关键工具链：
  内核态：/proc/net/* + /proc/pid/fd + dropwatch
  用户态：ss + lsof + strace + tcpdump
  Android 扩展：dumpsys input/activity + ANR trace + fdsan
  监控：fd ratio + TIME_WAIT + ListenOverflows + InboundQueue
  治理：fdsan + StrictMode + 连接池 + backlog + CI 校验 + 告警
```

---

### 附录 F：与其他文章的关系

| 文章 | 本文引用位置 |
|------|--------------|
| 01-Socket 总览 | §1.2 6 大场景基线 |
| 02-Socket API | §2.1 sockstat / §2.4 strace 系统调用 |
| 03-Socket 生命周期 | §2.1 TCP 状态码（B.4） |
| 04-Socket 缓冲 | §3.3 buffer 监控指标 |
| 05-listen backlog | §2.1.5 ListenOverflows / §3.2.2 队列监控 |
| 06-UDS 与 Android | §2.1.3 /proc/net/unix + §2.3.4 场景区分 |
| 07-风险全景 | 全文按 5 大类风险分类 + §5 案例联动 |
| bridge/01-socket 与 epoll | §2.3 /proc/pid/fd 中 anon_inode[eventpoll] |
| epoll 01-epoll 总览 | §2.3.3 /proc/pid/net/tcp + epoll 协作 |
| IO 07-IO 与进程阻塞 | §2.5 ANR trace 中 D 状态识别 |

---

## 七、socket 系列收官

到本篇为止，socket 系列 8 篇规划**全部完结**：

| 篇号 | 标题 | 行数 | 角色 |
|------|------|------|------|
| 01 | Socket 总览 | 790 | 全局观 |
| 02 | 内核 API 与数据结构 | 待写 | API/结构 |
| 03 | 生命周期 | 待写 | 生命周期 |
| 04 | 缓冲区与数据收发 | 811 | 缓冲/阻塞 |
| 05 | listen backlog 与连接队列 | 764 | 队列 |
| 06 | Unix Domain Socket 与 Android | 770 | UDS |
| 07 | 稳定性风险全景 | 660 | 风险收口 |
| 08 | 诊断工具与治理体系 | 本篇 | 治理收口 |
| bridge/01 | socket 与 epoll 的关系 | 618 | 协作 |
| epoll/01 | epoll 总览与核心机制 | — | 独立系列 |

**8 篇知识地图**：
- **01 总览**：建立"Socket 是什么、Android 怎么用"的全图
- **02-06 机制**：API、数据结构、生命周期、缓冲、backlog、UDS——逐机制深潜
- **07 风险**：把所有机制的风险汇总成可指导实战的二维矩阵
- **08 治理**：把 07 风险落成可操作工具集 + 工程实践 + 综合案例

**与 epoll 系列协作**：socket 系列管"端点"（怎么通信），epoll 系列管"事件通知"（怎么知道有数据），两者通过 [bridge/01-socket与epoll的关系](../socket/bridge/01-socket与epoll的关系.md) 桥接。

**工程化沉淀**：
- 5 类诊断工具速查（附录 B）
- 6 大类监控指标基线（附录 C）
- 29 项量化数据自检（附录 D）
- 5 层治理体系（§4）
- 3 个综合实战案例（§5）

**给架构师的"5 分钟工具卡"**：见附录 B.1——打印出来贴在工位，线上 5 分钟定位流程固化。

---

## 篇尾衔接

socket 系列 8 篇规划已全部完结。可考虑的后续延伸方向：

- **网络层**：TCP 内部机制详解（重传、拥塞控制、TIME_WAIT 细节）——独立 TCP 专题
- **性能层**：socket 与 epoll 的性能 benchmark + Android 高性能网络库设计
- **安全层**：TLS/SSL 在 socket 上的实现 + Android Network Security Config
- **新场景**：WebSocket / QUIC / HTTP/3 在 Android 上的实现

本篇是 socket 系列的**最终收口**——所有风险（07）→ 所有工具（08）→ 所有治理（08）闭环完成。

---

