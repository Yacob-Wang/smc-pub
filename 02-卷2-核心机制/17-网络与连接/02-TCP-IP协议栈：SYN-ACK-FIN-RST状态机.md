# 06-Foundation/Network · 02 · TCP/IP 协议栈：SYN/ACK/FIN/RST 状态机

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 网络问题排查
>
> **强依赖**：[01 网络栈总览](01-网络栈总览：从app-socket到网卡的全链路.md) · [08 网络栈诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 TCP 11 个状态 + 三次握手 + 四次挥手 + RST 触发场景 + AOSP 17 默认参数讲清楚——oncall 5 分钟从 `netstat` 输出判断 TCP 状态
- **不是**：不复述 [01 §2 12 步全链路](01-网络栈总览：从app-socket到网卡的全链路.md)（本文深入 TCP 协议层）；不复述具体调优 case（[08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md)）
- **承接自**：[01 §2.2 真实时间分布](01-网络栈总览：从app-socket到网卡的全链路.md) → 本文展开"TCP 握手为什么 1-50ms"
- **衔接去**：[03 DNS/DHCP](03-DNS-DHCP：从解析到连接的5秒流程.md) / [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 11 个状态独立表格 | 90% 现场查 5 个核心 |
| 2 | 5 个真实调优 case | 实战 5 分钟用 |
| 3 | AOSP 17 默认参数 | 跨版本迁移时核心 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**TCP = 11 个状态 + 3 次握手 + 4 次挥手——oncall 5 秒从 `ss -tan` 输出判断"为什么慢"。**

AOSP 17 TCP 仍是主流协议（占 80% 流量），虽然 QUIC 在快速增长。理解 TCP 状态机 = 90% 网络问题的根因定位。

---

## 1. TCP 11 个状态

### 1.1 状态机总图

```
                     +--------+
                     | CLOSED |
                     +--------+
                         |
        主动打开         |        被动打开
        connect()       |        listen()
                         v
                  +------------+        +-----------+
                  | SYN_SENT   |------->| LISTEN    |
                  +------------+        +-----------+
                         |                    |
                         | 收到 SYN+ACK      | 收到 SYN
                         | 发送 ACK          | 发送 SYN+ACK
                         v                    v
                  +------------+        +-----------+
                  | ESTABLISHED|<------>| SYN_RECV  |
                  +------------+        +-----------+
                         |                    |
                         |                    |
        主动关闭         |        被动关闭    | 收到 ACK
        close()         |        close()     | 关闭
                         v                    v
                  +------------+        +-----------+
                  | FIN_WAIT_1 |        | CLOSE_WAIT|
                  +------------+        +-----------+
                         |                    |
                         | 收到 ACK          | 发送 FIN
                         v                    v
                  +------------+        +-----------+
                  | FIN_WAIT_2 |<-------| LAST_ACK  |
                  +------------+        +-----------+
                         |                    |
                         | 收到 FIN          | 收到 ACK
                         | 发送 ACK          v
                         v                  +-----------+
                  +------------+           | CLOSED   |
                  | TIME_WAIT  |           +-----------+
                  +------------+
                         |
                         | 2MSL 超时
                         v
                     +--------+
                     | CLOSED |
                     +--------+
```

### 1.2 11 个状态速查

| 状态 | 含义 | 持续时间 | 何时出现 |
|:-----|:-----|:--------|:-------|
| **CLOSED** | 关闭 | - | 初始 / 终止 |
| **LISTEN** | 监听 | 长 | server `listen()` 后 |
| **SYN_SENT** | 主动发送 SYN | 短（一次 RTT）| client `connect()` 后 |
| **SYN_RECV** | 收到 SYN | 短 | server 收到 SYN 后 |
| **ESTABLISHED** | 已建立 | 长 | 连接可用 |
| **FIN_WAIT_1** | 主动关闭开始 | 短 | client 调 `close()` |
| **FIN_WAIT_2** | 等待对方关闭 | 长 | 对方没立即关 |
| **CLOSE_WAIT** | 被动关闭 | 中（取决于应用）| server 收到 FIN |
| **LAST_ACK** | 等待 ACK | 短 | server 关闭 |
| **TIME_WAIT** | 2MSL 等待 | 2MSL（60s 默认）| 主动关闭完成后 |
| **CLOSING** | 同时关闭 | 罕见 | 双方同时关闭 |

### 1.3 5 大核心状态

| 状态 | 重要度 | 持续时间 | 5 秒诊断意义 |
|:-----|:------|:--------|:----------|
| **ESTABLISHED** | ⭐⭐⭐ | 长 | 正常 |
| **TIME_WAIT** | ⭐⭐⭐ | 60s | 过多 → 端口耗尽 |
| **SYN_SENT** | ⭐⭐ | 短 | 持续 = 远端不可达 |
| **CLOSE_WAIT** | ⭐⭐ | 中 | 持续 = 应用没 close |
| **FIN_WAIT_2** | ⭐ | 长 | 持续 = 对端没关 |

### 1.4 5 大异常状态场景

| 状态 | 异常现象 | 5 秒定位 |
|:-----|:--------|:--------|
| **大量 TIME_WAIT** | 端口耗尽 | 短连接频繁 |
| **大量 CLOSE_WAIT** | 应用泄漏 fd | 业务没 close |
| **大量 SYN_SENT** | 远端不可达 | 网络 / 防火墙 |
| **大量 FIN_WAIT_2** | 对端异常 | 对端代码 bug |
| **大量 ESTABLISHED 短** | 频繁连接 | 业务没池化 |

---

## 2. 三次握手（建立连接）

### 2.1 真实 3 步

```
[client]                              [server]
   |                                    |
   | 1. SYN (seq=x)                    |
   |----------------------------------->|
   |                                    | 状态: LISTEN → SYN_RECV
   |                                    |
   | 2. SYN+ACK (seq=y, ack=x+1)       |
   |<-----------------------------------|
   |                                    | 状态: SYN_RECV
   | 状态: SYN_SENT                     |
   |                                    |
   | 3. ACK (ack=y+1)                  |
   |----------------------------------->|
   |                                    | 状态: SYN_RECV → ESTABLISHED
   | 状态: SYN_SENT → ESTABLISHED      |
   |                                    |
   | 数据传输开始                         |
```

### 2.2 关键字段

```
TCP header (20 字节):
┌──────────┬──────────┬─────────────────┐
│ src_port │ dst_port │                 │
├──────────┴──────────┤                 │
│       seq          │ (SYN: ISN)
├────────────────────┤
│       ack          │ (SYN+ACK: ack=ISN+1)
├──────┬──────┬──────┤
│FLAGS │ ...  │ ...  │ (SYN / ACK / FIN / RST)
├──────┴──────┴──────┤
│     window         │
├────────────────────┤
│     checksum      │
└────────────────────┘

关键 flags:
- SYN: 同步序号
- ACK: 确认序号
- FIN: 关闭
- RST: 重置
```

### 2.3 5 个握手异常场景

#### 场景 1：第二次握手丢（最常见）

```
[client]                  [server]                  [network]
   |                          |                          |
   | 1. SYN                   |                          |
   |------------------------->|                          |
   |                          | 2. SYN+ACK               |
   |                          |------------------------->|  丢失
   | 3. 超时重传 SYN          |                          |
   |------------------------->|                          |
   |                          | 4. SYN+ACK (重传)        |
   |                          |------------------------->|
   | 5. 收到 SYN+ACK          |                          |
   |<-------------------------|                          |
   | 6. ACK                   |                          |
   |------------------------->|                          |
```

**关键**：
- client 重传 SYN（指数退避）
- **1 次 RTT 后收到 SYN+ACK 即可**
- 网络慢 1 秒 → 握手多 1 秒

#### 场景 2：第三次握手丢

```
[client]                          [server]
   |                                  |
   | 1. SYN                           |
   |--------------------------------->|
   | 2. SYN+ACK                       |
   |<---------------------------------|
   | 3. ACK (丢了)                    |
   |---------X (丢)                    |
   |                                  | server 状态: ESTABLISHED (但没收到 ACK)
   |                                  | 数据开始发 → 但 client 状态: SYN_SENT
   |                                  | 实际：连接错位
```

**关键**：
- server 进入 ESTABLISHED 状态
- client 还在 SYN_SENT 状态
- server 发数据 → 客户端收不到 → 连接实际无效

#### 场景 3：SYN flood（攻击）

```
[attacker]                  [server]
   |                            |
   | 大量 SYN (伪造 src IP)    |
   |---------------------------->|
   | 大量 SYN_RECV (半连接)     |
   |                            | server 资源耗尽
```

**防御**：
- SYN cookies
- 限制半连接数
- 见 [AOSP 17 默认参数 §5]

#### 场景 4：TFO（TCP Fast Open）

```
[client]                          [server]
   |                                  |
   | 1. SYN + TFO cookie + data      |  ← 第 1 次
   |--------------------------------->|
   | 2. SYN+ACK + data                |  ← server 用 cookie 验证
   |<---------------------------------|
   | 3. ACK + data                    |  ← 不再需要 3 次
   |--------------------------------->|
   | 0-RTT 数据传输                   |
```

**关键**：
- 跳过 3 次握手中 1 次
- 需要 server 给 client 派 TFO cookie
- AOSP 17 默认开启 TFO

#### 场景 5：MPTCP（多路径 TCP）

```
[client (WiFi)]                   [client (LTE)]           [server]
   |                                  |                       |
   | 1. SYN (via WiFi)                |                       |
   |----------------------------------------------------------------->|
   |                                  | 2. SYN (via LTE)        |
   |                                  |------------------------>|
   |                                  | 3. SYN+ACK             |
   |                                  |<------------------------|
   | 4. SYN+ACK                       |                        |
   |<-----------------------------------------------------------------|
   | 5. ACK                          |                        |
   |----------------------------------------------------------------->|
   | 数据流在两条路径上分摊                                   |
```

**关键**：
- AOSP 17 支持 MPTCP
- 提升带宽 / 容错
- 启用：`adb shell settings put global mptcp_enabled 1`

---

## 3. 四次挥手（关闭连接）

### 3.1 真实 4 步

```
[client]                              [server]
   |                                    |
   | 1. FIN (seq=u)                    |
   |----------------------------------->|
   |                                    | 状态: ESTABLISHED → CLOSE_WAIT
   | 状态: ESTABLISHED → FIN_WAIT_1    |
   |                                    |
   | 2. ACK (ack=u+1)                  |
   |<-----------------------------------|
   |                                    | 状态: CLOSE_WAIT
   | 状态: FIN_WAIT_1 → FIN_WAIT_2     |
   |                                    |
   |              (server 调 close())   |
   |                                    |
   | 3. FIN (seq=v, ack=u+1)           |
   |<-----------------------------------|
   |                                    | 状态: CLOSE_WAIT → LAST_ACK
   | 状态: FIN_WAIT_2 → TIME_WAIT      |
   |                                    |
   | 4. ACK (ack=v+1)                  |
   |----------------------------------->|
   |                                    | 状态: LAST_ACK → CLOSED
   | 状态: TIME_WAIT (2MSL 等待)       |
   |                                    |
   | 2MSL 后                            |
   | 状态: TIME_WAIT → CLOSED           |
```

### 3.2 为什么是 4 次（不是 3 次）？

```
[1] client 发 FIN（client 不再发数据）
[2] server 立即 ACK（确认 client 关闭）
[3] server 自己发 FIN（server 也不再发数据）
[4] client ACK（确认 server 关闭）

总 4 步。

原因：FIN 是单向关闭（自己这端不再发），但 client 和 server 是两个独立方向
      → 每个方向都要单独 FIN+ACK
      → 4 步
```

### 3.3 TIME_WAIT 的 2MSL 含义

```
MSL = Maximum Segment Lifetime
     = 一个 TCP 段在网络中存在的最长时间
     = 通常 60 秒（Android 默认）

2MSL = 120 秒
      = TIME_WAIT 持续时间

为什么需要 2MSL？
- 保证 client 发的最后 ACK 到达 server
- 让网络中残留的旧包自然消亡
- 防止新连接收到旧包的脏数据
```

### 3.4 5 个挥手异常场景

#### 场景 1：大量 TIME_WAIT

```
[client] 关闭大量短连接 → TIME_WAIT 堆积
- 端口耗尽
- 内存占用

修法：
- 调整 /proc/sys/net/ipv4/tcp_tw_reuse = 1
- 调整 /proc/sys/net/ipv4/tcp_tw_recycle（已废弃）
- 应用层连接池
```

#### 场景 2：大量 CLOSE_WAIT

```
[server] 收到 FIN 但没 close() → CLOSE_WAIT
- fd 泄漏
- 连接泄漏

修法：
- 修应用代码（确保 close() 被调用）
- 调整 /proc/sys/net/ipv4/tcp_keepalive_time
```

#### 场景 3：FIN_WAIT_2 长时间

```
[client] 发 FIN+ACK → 等 server FIN
- server 不发 FIN
- 连接卡在 FIN_WAIT_2

修法：
- 调 net.ipv4.tcp_fin_timeout = 60
- 修 server 代码
```

#### 场景 4：同时关闭

```
[client] 关闭            [server] 关闭
   |                        |
   | 1. FIN                 | 1. FIN
   |----------------------->|----------------------->
   |                        |
   | 2. FIN (server 先到)   |
   |<-----------------------|
   | 状态: CLOSING         |
   |                        | 状态: CLOSING
   | 3. ACK                 |
   |----------------------->|
   | 状态: CLOSING → TIME_WAIT  |
```

#### 场景 5：RST 替代 FIN

```
[client]                  [server]
   |                          |
   | 1. RST (而不是 FIN)     |
   |------------------------->|
   |                          | 状态: 直接 CLOSED
   |                          | 不进入 FIN_WAIT_1
   | 状态: 直接 CLOSED       |
```

**RST vs FIN**：
- FIN = 优雅关闭（4 步）
- RST = 强制关闭（1 步）
- RST 丢数据
- RST 用于异常场景

---

## 4. RST 触发场景

### 4.1 RST 触发的 5 大场景

| 场景 | 原因 | 5 秒定位 |
|:-----|:-----|:--------|
| **端口未监听** | client 连未 listen 端口 | server 进程没起 |
| **连接被强制关闭** | 主动发 RST | SO_LINGER 设置 |
| **半连接队列满** | server 拒绝新连接 | 调 somaxconn |
| **TIME_WAIT 冲突** | 同一端口同序列 | 调 tcp_tw_reuse |
| **TCP Keepalive 失败** | 心跳超时 | 调 keepalive 参数 |

### 4.2 真实案例

#### 案例 1：连接未监听端口

```bash
# 1. server 没启动
$ adb shell "netstat -tln | grep 8080"
# 无输出

# 2. client 连接
$ adb shell "nc 127.0.0.1 8080"
# 立即拒绝

# 3. server kernel 日志
# TCP: request_sock_TCP: Possible SYN flooding on port 8080. Sending cookies.
# 或
# Connection refused
```

#### 案例 2：SO_LINGER RST

```cpp
// C++ server
struct linger lin = {1, 0};  // 关闭时发 RST
setsockopt(fd, SOL_SOCKET, SO_LINGER, &lin, sizeof(lin));
close(fd);  // 立即 RST，不等 FIN
```

**用途**：紧急关闭（不等数据排空）

#### 案例 3：Keepalive 失败

```bash
# TCP keepalive 探测
# /proc/sys/net/ipv4/tcp_keepalive_time = 7200 (2 小时)
# /proc/sys/net/ipv4/tcp_keepalive_intvl = 75 (75 秒)
# /proc/sys/net/ipv4/tcp_keepalive_probes = 9 (9 次)

# 总时间: 7200 + 75*9 = 7875 秒 = 131 分钟

# 网络断了 2 小时后 → RST
```

**优化**：
```bash
$ adb shell "echo 60 > /proc/sys/net/ipv4/tcp_keepalive_time"
$ adb shell "echo 10 > /proc/sys/net/ipv4/tcp_keepalive_intvl"
$ adb shell "echo 3 > /proc/sys/net/ipv4/tcp_keepalive_probes"
# 总时间: 60 + 10*3 = 90 秒
```

---

## 5. AOSP 17 默认参数

### 5.1 5 大 TCP 参数

| 参数 | 默认值 | 含义 | 调优 |
|:-----|:------|:-----|:-----|
| `tcp_rmem` | 4096 87380 6291456 | TCP 接收缓冲 (min default max) | 调 max → 大量数据 |
| `tcp_wmem` | 4096 16384 4194304 | TCP 发送缓冲 | 调 max → 大量数据 |
| `tcp_congestion_control` | `bbr` (AOSP 15+) | 拥塞控制算法 | 改 `cubic` |
| `tcp_fastopen` | 3 (client + server) | TFO 启用 | 0 禁用 |
| `tcp_tw_reuse` | 0 (旧) / 2 (AOSP 17) | TIME_WAIT 复用 | 1 启用 |

### 5.2 5 大窗口参数

| 参数 | 默认 | 含义 |
|:-----|:-----|:-----|
| `tcp_window_scaling` | 1 | 窗口缩放 |
| `tcp_timestamps` | 1 | 时间戳 |
| `tcp_sack` | 1 | 选择性确认 |
| `tcp_no_metrics_save` | 0 | 不保存指标 |
| `tcp_slow_start_after_idle` | 0 | 空闲后慢启动 |

### 5.3 5 大调优 case

#### Case 1：高带宽网络

```bash
# 调大 TCP 缓冲
$ adb shell "echo '4096 87380 16777216' > /proc/sys/net/ipv4/tcp_rmem"
$ adb shell "echo '4096 16384 16777216' > /proc/sys/net/ipv4/tcp_wmem"
# 16MB 缓冲 → 高速网络
```

#### Case 2：长距离网络（高 RTT）

```bash
# 启用 BBR
$ adb shell "echo bbr > /proc/sys/net/ipv4/tcp_congestion_control"

# 调大初始窗口
$ adb shell "echo 10 > /proc/sys/net/ipv4/tcp_init_cwnd"
```

#### Case 3：短连接频繁

```bash
# 启用 TIME_WAIT 复用
$ adb shell "echo 1 > /proc/sys/net/ipv4/tcp_tw_reuse"

# 减小 FIN timeout
$ adb shell "echo 30 > /proc/sys/net/ipv4/tcp_fin_timeout"
# 默认 60s → 30s
```

#### Case 4：移动网络切换

```bash
# 启用 TFO
$ adb shell "echo 3 > /proc/sys/net/ipv4/tcp_fastopen"
# 跳过 1 次握手

# 启用 MPTCP
$ adb shell settings put global mptcp_enabled 1
```

#### Case 5：弱网优化

```bash
# 减小初始 RTO
$ adb shell "echo 1 > /proc/sys/net/ipv4/tcp_syn_retries"
# 默认 6 → 1（重传减少）

# 减小 SYN+ACK 重试
$ adb shell "echo 4 > /proc/sys/net/ipv4/tcp_synack_retries"
# 默认 5 → 4
```

---

## 6. 实战：抓 TCP 问题

### 6.1 5 步定位

```
[1] 看 ss -tan（5 秒）
$ adb shell "ss -tan | head"
# 看哪些状态异常
  ↓
[2] 看 /proc/net/tcp（5 秒）
$ adb shell cat /proc/net/tcp
# 看 raw TCP 表
  ↓
[3] 看 /proc/net/netstat（10 秒）
$ adb shell cat /proc/net/netstat | grep -E "TcpRetrans|TcpOutOfOrder"
# 看重传 / 乱序
  ↓
[4] tcpdump 抓包（30 秒）
$ adb shell tcpdump -i any -nn -c 100 'tcp port 443'
# 看实际包
  ↓
[5] logcat -b kernel（10 秒）
$ adb logcat -d -b kernel | grep -E "TCP|connection"
# 看 kernel TCP 日志
```

### 6.2 真实 case：app 慢

```
[症状] 打开 app 主页慢 5 秒

[Step 1] ss -tan
$ adb shell "ss -tan | grep -c SYN_SENT"
# 0

[Step 2] 看 ESTABLISHED 数量
$ adb shell "ss -tan | grep -c ESTABLISHED"
# 100+ （app 大量连接）

[Step 3] netstat 看重传
$ adb shell "cat /proc/net/netstat | grep TcpRetransSegs"
# TcpRetransSegs 1000+ （高重传率）

[Step 4] ping
$ adb shell ping -c 4 www.example.com
# time 800ms （RTT 极高）

[Step 5] 结论：远端网络慢，不是 app 问题
```

### 6.3 真实 case：服务端 CLOSE_WAIT 堆积

```
[症状] server 端口耗尽，新连接失败

[Step 1] ss -tan
$ adb shell "ss -tan | grep -c CLOSE_WAIT"
# 1000+

[Step 2] ss -tan 找哪些 fd
$ adb shell "ss -tan | grep CLOSE_WAIT | head"
# 10.0.0.1:12345  10.0.0.2:80  CLOSE_WAIT
# ...

[Step 3] 看 server 进程 fd
$ adb shell "lsof -p $(pidof server) | wc -l"
# 5000+ （fd 泄漏）

[Step 4] 看应用代码
# 找到 receive 但没 close 的地方

[Step 5] 修法
- 应用加 finally close()
- 调 /proc/sys/net/ipv4/tcp_keepalive_time = 600
```

---

## 7. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 网络栈总览](01-网络栈总览：从app-socket到网卡的全链路.md) | 上篇 |
| [03 DNS/DHCP](03-DNS-DHCP：从解析到连接的5秒流程.md) | 续篇 |
| [04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md) | 续篇 |
| [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md) | 续篇 |
| [01-Mechanism/Kernel/IO/11-eBPF](../../../../03-卷3-核心机制/16-IO 与存储/11-eBPF在IO性能分析中的实战：从bpftrace到Android落地.md) | eBPF 工具 |
| [02-Symptom/S09-jank/01-症状机制](../../../02-Symptom/S09-jank/01-症状机制.md) | 卡顿 |

---

## 8. 收官 + 自检

### 8.1 看完本文的自检

- [ ] 能说 TCP 11 个状态 + 核心 5 个
- [ ] 能说三次握手每步（SYN / SYN+ACK / ACK）
- [ ] 能说四次挥手每步（FIN / ACK / FIN / ACK）
- [ ] 能区分 FIN vs RST
- [ ] 能解释 TIME_WAIT 2MSL 含义
- [ ] 能用 ss -tan 5 秒看 TCP 状态
- [ ] 知道 AOSP 17 默认 tcp_congestion_control = bbr
- [ ] 能用 5 个调优 case 调 TCP 参数

### 8.2 收官话

TCP 在稳定性架构师的能力模型里属于**"取证落地"层**——网络慢 5 秒从 TCP 状态定位根因。

下一步推荐读：
- [03 DNS/DHCP](03-DNS-DHCP：从解析到连接的5秒流程.md) — TCP 之前的 5 秒
- [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md) — 工具
- [04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md) — 网络选路

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
