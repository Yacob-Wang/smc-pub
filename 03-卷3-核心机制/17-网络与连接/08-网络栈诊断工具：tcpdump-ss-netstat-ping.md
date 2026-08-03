# 06-Foundation/Network · 08 · 网络栈诊断工具：tcpdump / ss / netstat / ping

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 网络问题排查
>
> **强依赖**：[01]-[07] 网络栈全系列

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把网络栈 8 大诊断工具（ping / traceroute / ss / netstat / tcpdump / ndc / ip / iptables）讲清楚——oncall 5 分钟工具箱
- **不是**：不复述 [01]-[07] 任一篇；不复述 [06-Foundation/Tools/Tracing/20-Trace抓取方法全面指南](../../05-卷5-调查工具链/35-断点与%20Native%20调试/20-Trace抓取方法全面指南：ftrace-atrace-systrace-perfetto.md)（trace 类工具）
- **承接自**：[07 Mobile Data](07-Mobile-Data：RIL-数据业务-漫游.md) → 本文给 8 大工具实战
- **衔接去**：[01]-[07] 任一篇

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 8 大工具独立小节 | oncall 5 秒选 |
| 2 | 第 7 章 5 大 case 走完 8 工具 | 实战 |
| 3 | 第 10 章 8 篇收官引用矩阵 | 系列收官 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**8 大网络工具 = oncall 5 分钟工具箱——ping / traceroute / ss / netstat / tcpdump / ndc / ip / iptables 各管一摊，组合 5 秒定位。**

AOSP 17 工具栈 = Linux 标准工具 + Android 特有工具（dumpsys / cmd network_stack / ndc）。

---

## 1. 8 大工具速查

| 工具 | 用途 | 关键命令 | oncall 何时用 |
|:-----|:-----|:--------|:----------|
| **ping** | 测试连通性 + RTT | `ping -c 4 <host>` | "能不能通" |
| **traceroute** | 路径 + 每跳 RTT | `traceroute <host>` | "卡在哪一跳" |
| **ss** | socket 状态 | `ss -tan` | "TCP 卡在什么状态" |
| **netstat** | 网络连接（兼容）| `netstat -an` | "连接列表" |
| **tcpdump** | 抓包 | `tcpdump -i any -nn` | "实际数据包" |
| **ndc** | netd 命令 | `ndc resolver` | "DNS 解析" |
| **ip** | 网络接口 / 路由 | `ip route` | "路由表" |
| **iptables** | 防火墙（老）| `iptables -L -n` | "防火墙规则" |

---

## 2. ping — 连通性 + RTT

### 2.1 基础用法

```bash
# 1. 测 IP
$ adb shell ping -c 4 8.8.8.8
PING 8.8.8.8 (8.8.8.8): 56 data bytes
64 bytes from 8.8.8.8: icmp_seq=0 ttl=117 time=10.5 ms
64 bytes from 8.8.8.8: icmp_seq=1 ttl=117 time=10.2 ms
64 bytes from 8.8.8.8: icmp_seq=2 ttl=117 time=10.0 ms
64 bytes from 8.8.8.8: icmp_seq=3 ttl=117 time=10.1 ms

--- 8.8.8.8 ping statistics ---
4 packets transmitted, 4 packets received, 0.0% packet loss
round-trip min/avg/max/stddev = 10.0/10.2/10.5/0.2 ms
```

### 2.2 5 大关键参数

| 参数 | 含义 | 阈值 |
|:-----|:-----|:-----|
| **time** | RTT | < 50ms 优 |
| **packet loss** | 丢包率 | < 1% 优 |
| **ttl** | 跳数 | 64 / 128 主流 |
| **icmp_seq** | 序号 | 连续 = 稳定 |
| **mdev** | 抖动 | < 5ms 优 |

### 2.3 5 大场景

```bash
# 1. 测域名
$ adb shell ping -c 4 www.example.com

# 2. 测 IP
$ adb shell ping -c 4 8.8.8.8

# 3. 强制 IPv4
$ adb shell ping -4 -c 4 8.8.8.8

# 4. 强制 IPv6
$ adb shell ping -6 -c 4 2001:4860:4860::8888

# 5. 测接口
$ adb shell ping -I wlan0 -c 4 8.8.8.8
```

### 2.4 5 大异常分析

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **0% received** | 网络不通 | 查 connectivity |
| **50% loss** | 网络不稳 | 查 WiFi/Mobile |
| **time > 200ms** | 高 RTT | 切网络 / 走近 |
| **time 抖动大** | 网络拥塞 | 测多次 |
| **Destination unreachable** | 路由错 | 查 ip route |

---

## 3. traceroute — 路径 + 跳数

### 3.1 基础用法

```bash
# 1. 测路径
$ adb shell traceroute www.example.com
traceroute to www.example.com (93.184.216.34), 30 hops max
 1  192.168.1.1  2.123 ms  1.234 ms  1.345 ms  ← 路由器
 2  10.0.0.1     5.123 ms  5.234 ms  5.345 ms  ← ISP
 3  * * *                                       ← 跳
 4  93.184.216.34 100.123 ms 100.234 ms 100.345 ms  ← 目标
```

### 3.2 5 大关键参数

| 参数 | 含义 |
|:-----|:-----|
| **hop** | 第几跳 |
| **RTT 3 个数** | 同一跳 3 次探测（防丢失）|
| **\*** | 跳未响应（限速 / 禁 ICMP）|
| **!** | 不可达 |

### 3.3 5 大场景

```bash
# 1. TCP 路径
$ adb shell traceroute -T -p 443 www.example.com

# 2. ICMP 路径（默认）
$ adb shell traceroute www.example.com

# 3. UDP 路径
$ adb shell traceroute -U www.example.com

# 4. 最大跳数
$ adb shell traceroute -m 10 www.example.com

# 5. 不解析 IP
$ adb shell traceroute -n www.example.com
```

### 3.4 5 大异常

| 现象 | 根因 |
|:-----|:-----|
| **第 1 跳就 \* \* \*** | 路由器禁 ICMP |
| **中间跳慢** | ISP 拥塞 |
| **某跳突然超 200ms** | 跨境路由 |
| **目标跳不通** | 服务端禁 ICMP |
| **完全没路径** | 路由表错 |

---

## 4. ss / netstat — socket 状态

### 4.1 ss 基础用法

```bash
# 1. 全部 TCP
$ adb shell ss -tan
State      Recv-Q Send-Q  Local Address:Port   Peer Address:Port
ESTAB      0       0       192.168.1.100:12345   93.184.216.34:443
TIME-WAIT  0       0       192.168.1.100:12346   93.184.216.34:443
CLOSE-WAIT 0       0       192.168.1.100:12347   93.184.216.34:443
...

# 2. 看某端口
$ adb shell ss -tan 'sport = :443'
# 看所有连 443 端口的连接

# 3. 监听端口
$ adb shell ss -tln
# 看 server 监听

# 4. UDP
$ adb shell ss -uan
```

### 4.2 ss 5 大状态字段

| 字段 | 含义 |
|:-----|:-----|
| **State** | TCP 状态（ESTAB / TIME-WAIT / CLOSE-WAIT）|
| **Recv-Q** | 接收队列字节数 |
| **Send-Q** | 发送队列字节数 |
| **Local** | 本地 IP: 端口 |
| **Peer** | 远端 IP: 端口 |

### 4.3 netstat 基础用法

```bash
# 1. 全部
$ adb shell netstat -an
# 输出同 ss（兼容）

# 2. 看 socket 状态
$ adb shell netstat -tan

# 3. 路由表
$ adb shell netstat -rn

# 4. 接口统计
$ adb shell netstat -i
```

### 4.4 ss vs netstat

| 工具 | 速度 | 推荐 |
|:-----|:-----|:----|
| **ss** | 快 | 优 |
| **netstat** | 慢 | 兼容 |

**AOSP 17 默认有 ss 和 netstat**。

### 4.5 5 大异常 case

| 现象 | 根因 | 修法 |
|:-----|:-----|:-----|
| **大量 TIME_WAIT** | 端口耗尽 | 调 tcp_tw_reuse |
| **大量 CLOSE_WAIT** | fd 泄漏 | 修 app |
| **SYN_SENT 持续** | 远端不可达 | 查 netd / 防火墙 |
| **Recv-Q 持续大** | 接收慢 | 看 TCP buffer |
| **Send-Q 持续大** | 发送慢 | 查网络 |

---

## 5. tcpdump — 抓包

### 5.1 基础用法

```bash
# 1. 抓所有包（root）
$ adb shell tcpdump -i any -nn -c 100
# 抓 100 个包后停止

# 2. 抓特定端口
$ adb shell tcpdump -i any -nn -c 100 'tcp port 443'

# 3. 抓特定 host
$ adb shell tcpdump -i any -nn -c 100 'host 8.8.8.8'

# 4. 抓 DNS
$ adb shell tcpdump -i any -nn -c 100 'udp port 53'

# 5. 写文件
$ adb shell tcpdump -i any -w /sdcard/capture.pcap

# 6. 实时显示（-l + -A）
$ adb shell tcpdump -i any -nn -l -A 'tcp port 80'
# ASCII 显示包内容
```

### 5.2 5 大过滤表达式

| 表达式 | 用途 |
|:-------|:----|
| `tcp port 443` | TCP 443 端口 |
| `udp port 53` | UDP 53 端口 |
| `host 8.8.8.8` | 特定 host |
| `src 192.168.1.100` | 源 IP |
| `dst port 80` | 目标端口 |
| `tcp[tcpflags] & (tcp-syn) != 0` | SYN 包 |
| `greater 1000` | 大于 1000 字节的包 |

### 5.3 5 大异常 case

```bash
# 1. 看 DNS 解析
$ adb shell tcpdump -i any -nn -c 10 'udp port 53'
# 看发了什么 DNS 查询

# 2. 看 TLS 握手
$ adb shell tcpdump -i any -nn -c 20 'tcp port 443'
# 第一个 SYN 看到 → 1 RTT 后 SYN+ACK → 1 RTT 后 ACK

# 3. 看连接重置
$ adb shell tcpdump -i any -nn -c 100 'tcp[tcpflags] & (tcp-rst) != 0'
# 找 RST 包 → 哪里在拒绝

# 4. 看 5 秒内没数据
$ adb shell tcpdump -i any -nn -c 1000
# 看是不是 TCP 一直连但没数据

# 5. 看 SYN 风暴
$ adb shell tcpdump -i any -nn -c 1000 'tcp[tcpflags] & (tcp-syn) != 0'
# 大量 SYN = 攻击或端口被扫
```

---

## 6. ndc / ip / iptables — 系统级工具

### 6.1 ndc（Network Domain Command）

```bash
# 1. netd 命令
$ adb shell ndc resolver gethostbyname www.example.com
# DNS 解析

# 2. 看 tethering
$ adb shell ndc tether status
# 看热点状态

# 3. 看 firewall
$ adb shell ndc firewall get_uid_rule 10001
# 看 10001 防火墙规则
# allow / deny

# 4. 路由
$ adb shell ndc network route
# 看路由
```

### 6.2 ip（iproute2）

```bash
# 1. 看接口
$ adb shell ip addr
# wlan0: 192.168.1.100/24
# rmnet_data0: 10.0.0.5/24

# 2. 看路由表
$ adb shell ip route
# default via 192.168.1.1 dev wlan0
# 10.0.0.0/24 dev rmnet_data0

# 3. 看 link
$ adb shell ip link
# 物理 / 虚拟接口

# 4. 看 neighbor（ARP）
$ adb shell ip neigh
# ARP 表

# 5. 看 rule
$ adb shell ip rule
# 路由策略规则

# 6. 加路由
$ adb shell ip route add 192.168.2.0/24 via 192.168.1.1
```

### 6.3 iptables（兼容）

```bash
# 1. 看防火墙
$ adb shell iptables -L -n -v

# 2. 看 nat
$ adb shell iptables -t nat -L -n -v

# 3. 看 mangle
$ adb shell iptables -t mangle -L -n -v

# 4. 看 raw
$ adb shell iptables -t raw -L -n -v

# 5. 看 rule 统计
$ adb shell iptables -L -n -v --line-numbers
```

**AOSP 17 警告**：
- iptables 已废弃
- eBPF 替代
- 上面命令可能"Table does not exist"

### 6.4 5 大异常

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **ping 不通** | 路由错 | `ip route` |
| **DNS 不通** | resolver 错 | `ndc resolver gethostbyname` |
| **app 禁网** | firewall | `ndc firewall` |
| **流量被劫持** | NAT | `iptables -t nat` |
| **网络慢** | qdisc | `tc qdisc show` |

---

## 7. 5 大实战 case

### 7.1 Case 1：app 上不了网 5 分钟定位

```bash
# 1. 看 network state
$ adb shell dumpsys connectivity | head
# 看 active network

# 2. 看 network type
$ adb shell ifconfig | head
# 看 wlan0 / rmnet_data0

# 3. ping
$ adb shell ping -c 4 8.8.8.8
# 50% received → 网络不稳

# 4. 测 DNS
$ adb shell ndc resolver gethostbyname www.example.com
# 看 resolver 是否能解析

# 5. 看 socket
$ adb shell ss -tan
# 看 app 的连接

# 结论：网络不稳 / DNS 慢
```

### 7.2 Case 2：网络慢 5 分钟定位

```bash
# 1. ping
$ adb shell ping -c 4 8.8.8.8
# time > 200ms 慢

# 2. traceroute
$ adb shell traceroute www.example.com
# 看哪一跳慢

# 3. tcpdump 抓 30 秒
$ adb shell tcpdump -i any -nn -c 100 'tcp port 443'
# 看实际包的 RTT

# 4. 看 RTT
$ adb shell ss -tin 'sport = :443'
# 看每个 socket 的 RTT

# 5. 看 netd
$ adb shell ndc bandwidth getinterfacequota wlan0
# 看限速
```

### 7.3 Case 3：网络断 5 分钟定位

```bash
# 1. ping
$ adb shell ping -c 4 8.8.8.8
# 100% loss

# 2. 看 interface
$ adb shell ifconfig wlan0
# 看是否 UP

# 3. 看 routing
$ adb shell ip route
# 看 default route

# 4. 看 firewall
$ adb shell ndc firewall get_uid_rule 10001
# 看 app 是否 deny

# 5. 看 wifi
$ adb shell dumpsys wifi | head -30
# 看 WiFi 状态
```

### 7.4 Case 4：5G 切不到 5 分钟定位

```bash
# 1. 看 network type
$ adb shell dumpsys telephony.registry | grep "mDataNetworkType"
# 13 = LTE 4G
# 20 = NR 5G

# 2. 看 5G 设置
$ adb shell settings get global preferred_network_mode
# 应包含 NR (5G)

# 3. 看 NR mode
$ adb shell settings get global nr_mode
# 应是 1 / 2 / 3

# 4. 看 signal
$ adb shell dumpsys telephony.registry | grep "RSRP"
# 5G 信号弱 → 切 4G

# 5. 看 PLMN
$ adb shell dumpsys phone | grep "PLMN"
# 运营商网络
```

### 7.5 Case 5：流量被劫持 5 分钟定位

```bash
# 1. 看路由
$ adb shell ip route
# 看 default route 是不是合法

# 2. 看 DNS
$ adb shell ndc resolver gethostbyname www.example.com
# 看 DNS 解析到哪

# 3. 看 VPN
$ adb shell dumpsys connectivity | grep "VPN"
# 看 VPN 是否启用

# 4. 看 underlyNetworks
$ adb shell "dumpsys connectivity | grep underly"
# app 是否 bypass VPN

# 5. tcpdump 抓包
$ adb shell tcpdump -i any -nn -c 100 'tcp port 443'
# 看实际流量
```

---

## 8. oncall 5 分钟工具箱

```
[问题] 网络相关
  ↓
[1] 30 秒判断（5 秒）
  ├─ "连不上" → ping
  ├─ "卡在哪" → traceroute
  ├─ "TCP 状态" → ss
  ├─ "实际包" → tcpdump
  └─ "策略" → ndc / ip / iptables
  ↓
[2] 抓现场（30-60 秒）
  ├─ ping + traceroute
  ├─ ss -tan + ss -tin
  ├─ tcpdump -i any
  ├─ ip route
  └─ ndc firewall / resolver
  ↓
[3] 5 分钟定位
  ├─ 网络层问题 → ping / traceroute
  ├─ 传输层问题 → ss / tcpdump
  ├─ 策略问题 → ndc / iptables
  └─ 路由问题 → ip route
  ↓
[4] 出报告（5 分钟）
```

---

## 9. 8 大工具速查表

| 工具 | 关键命令 | 5 秒判断 |
|:-----|:---------|:--------|
| **ping** | `ping -c 4 <host>` | time < 50ms 优 |
| **traceroute** | `traceroute <host>` | 哪一跳慢 |
| **ss** | `ss -tan` | 哪个 socket 异常 |
| **netstat** | `netstat -an` | 兼容 ss |
| **tcpdump** | `tcpdump -i any -nn` | 看实际包 |
| **ndc** | `ndc firewall` | 看 netd 策略 |
| **ip** | `ip route` | 路由表 |
| **iptables** | `iptables -L` | 防火墙（已废弃） |

---

## 10. 与 smc-pub 其他文章的对接 + 8 篇收官

### 10.1 与网络栈其他 7 篇对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 网络栈总览](01-网络栈总览：从app-socket到网卡的全链路.md) | 起点 |
| [02 TCP/IP 状态机](02-TCP-IP协议栈：SYN-ACK-FIN-RST状态机.md) | TCP 深入 |
| [03 DNS/DHCP](03-DNS-DHCP：从解析到连接的5秒流程.md) | DNS/DHCP 深入 |
| [04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md) | 选路 |
| [05 netd/NMS](05-netd-NetworkManagementService：网络策略.md) | 策略 |
| [06 WiFi](06-WiFi协议栈：wpa-supplicant-HAL-连接.md) | WiFi 协议 |
| [07 Mobile Data](07-Mobile-Data：RIL-数据业务-漫游.md) | Mobile 协议 |

### 10.2 8 篇引用矩阵（收官）

```
┌─────────────────────────────────────────────────────────────┐
│  网络栈 8 篇全引用矩阵                                        │
└─────────────────────────────────────────────────────────────┘

[01] 网络栈总览 (你正在看)
  ↓ 引用 → [02-08] 全部
  ↑ 引用 ← 全部

[02] TCP/IP 状态机
  ↓ 引用 → [03] DNS (握手前的 5 秒) / [08] 工具 (看 TCP 状态)
  ↑ 引用 ← [01] [08]

[03] DNS / DHCP
  ↓ 引用 → [04] CS (选网) / [08] 工具 (测 DNS)
  ↑ 引用 ← [02] [04] [08]

[04] ConnectivityService
  ↓ 引用 → [05] netd (执行) / [06-07] WiFi/Mobile
  ↑ 引用 ← [01] [03] [05] [06] [07]

[05] netd / NMS
  ↓ 引用 → [08] 工具 (ndc / iptables)
  ↑ 引用 ← [04] [08]

[06] WiFi
  ↓ 引用 → [08] 工具 (dumpsys wifi)
  ↑ 引用 ← [04] [07]

[07] Mobile Data
  ↓ 引用 → [08] 工具 (dumpsys telephony)
  ↑ 引用 ← [04] [06]

[08] 8 大工具（你正在读）
  ↑ 引用 ← 全部 7 篇
```

### 10.3 8 篇核心 takeaway

- **01 总览**：4 层架构 + 5 类问题（5 秒判断）
- **02 TCP**：11 状态 + 3/4 握手（5 秒看 ss 输出）
- **03 DNS/DHCP**：5 秒流程 + DoH/DoT
- **04 CS**：5 NetworkAgent + 评分 + capability
- **05 netd/NMS**：iptables/eBPF + 防火墙
- **06 WiFi**：3 层 + 5 阶段 + 4 次握手
- **07 Mobile**：RIL + 5 代际 + 漫游
- **08 工具**：8 工具 + 5 案例 + 5 分钟决策

### 10.4 8 篇统一资源

- **真实工具**：ping / ss / tcpdump / ndc / ip
- **真实命令**：dumpsys / settings / cmd
- **真实场景**：5 大 case × 8 篇
- **真实耗时**：每篇 5-15 分钟读 + 5 分钟现场用

---

## 11. 收官 + 自检

### 11.1 看完 8 篇网络栈的自检

- [ ] 能说 4 层架构 + 5 类问题
- [ ] 能说 TCP 11 状态 + 3/4 握手
- [ ] 能说 DNS / DHCP 5 秒流程
- [ ] 能说 CS 5 NetworkAgent + 评分
- [ ] 能说 netd / NMS 5 大职责
- [ ] 能说 WiFi 5 阶段 + 4 次握手
- [ ] 能说 Mobile 5 代际 + RIL
- [ ] 能用 8 大工具 5 分钟定位

### 11.2 收官话

网络栈 8 篇在稳定性架构师的能力模型里属于**"机制理解" + "取证落地"两层交集**——oncall 7×24 网络问题的完整工具箱。

下一步推荐读：
- **P0 next**：SurfaceFlinger / 图形完整系列（5-7 篇）
- **P0 next**：PowerManager / 唤醒锁系列（3-5 篇）
- **P1**：启动链完整系列（5-7 篇）

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，**网络栈 8 篇收官**）
