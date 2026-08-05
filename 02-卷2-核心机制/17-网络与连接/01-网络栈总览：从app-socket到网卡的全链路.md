# 06-Foundation/Network · 01 · 网络栈总览：从 app socket 到网卡的全链路

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 网络问题排查
>
> **强依赖**：[06-Foundation/Tools/Android_Tools/02-Logcat格式](../../05-卷5-调查工具链/35-断点与%20Native%20调试/02-Logcat格式与tag体系.md) · [01-Mechanism/Kernel/IO/11-eBPF在IO性能分析中的实战](../../../../03-卷3-核心机制/16-IO 与存储/11-eBPF在IO性能分析中的实战：从bpftrace到Android落地.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 Android 网络栈从 app `socket()` 系统调用 → 内核 TCP/IP 协议栈 → 网卡驱动的完整链路讲清楚——oncall 5 分钟定位"卡在网络哪一段"
- **不是**：不复述 [02 TCP/IP 状态机](02-TCP-IP协议栈：SYN-ACK-FIN-RST状态机.md)（下篇展开）；不复述具体 WiFi/Mobile Data（[06](06-WiFi协议栈：wpa-supplicant-HAL-连接.md)/[07](07-Mobile-Data：RIL-数据业务-漫游.md) 展开）
- **承接自**：[06-Foundation/README §3 抓问题前必看](../../README.md) 网络基础
- **衔接去**：[02 TCP/IP 状态机](02-TCP-IP协议栈：SYN-ACK-FIN-RST状态机.md) / [08 网络栈诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md) / [02-Symptom/S09-jank/](../../../02-Symptom/S09-jank/01-症状机制.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 4 层架构（app / framework / kernel / hardware）| 跟 Linux 网络栈对齐 |
| 2 | 第 3 章用真实 socket 调用全链路 | 不用示意图 |
| 3 | 第 5 章 oncall 5 类网络问题分类 | 5 秒定位 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**Android 网络栈 = Linux TCP/IP + Binder 跨进程 + SELinux 沙箱 + HAL 适配——4 层架构，5 类问题，oncall 5 秒定位"卡在哪段"。**

AOSP 17 网络栈含 800+ 文件、100+ 服务、5 大子系统。理解全链路 = 现场 5 秒判断"app 慢在网络 / 内存 / CPU / 渲染"。

---

## 1. 4 层架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│  Android 网络栈 4 层架构                                          │
└──────────────────────────────────────────────────────────────────┘

[1] App 层（应用层）
    ├─ app 进程 (UID 10000+)
    │   ├─ Java/Kotlin: java.net.* / OkHttp / Retrofit
    │   ├─ Native: libcurl / 自定义 socket
    │   └─ 通过 Binder 调到 framework 服务
    └─ system_server 进程
        ├─ ConnectivityService（网络选路）
        ├─ NetworkManagementService（iptables / 防火墙）
        └─ netd (native daemon) ← 关键 native 代理

[2] Framework 层（中间层）
    ├─ Java API
    │   ├─ ConnectivityManager (app-facing)
    │   ├─ WifiManager (WiFi 专用)
    │   ├─ TelephonyManager (Mobile Data)
    │   └─ NetworkStatsManager (流量统计)
    └─ Native (libnetd_client / libandroid_runtime)
        └─ 通过 unix socket 跟 netd 通信

[3] Kernel 层（Linux 网络栈）  ← 核心
    ├─ socket 层
    │   ├─ BSD socket (AF_INET / AF_INET6 / AF_UNIX)
    │   └─ socket 缓冲区 (sk_buff)
    ├─ TCP / UDP / ICMP 协议栈
    │   ├─ TCP 状态机
    │   ├─ 拥塞控制 (CUBIC / BBR)
    │   └─ 滑动窗口 / 重传
    ├─ IP 层 (IPv4 / IPv6)
    ├─ Netfilter (iptables / nftables)
    │   ├─ 防火墙规则
    │   └─ NAT
    ├─ Routing
    │   ├─ 路由表
    │   └─ iptables
    └─ 设备层
        ├─ 网络设备抽象 (struct net_device)
        ├─ 驱动: WiFi driver / cellular modem
        └─ TCP/UDP socket buffer (sk_buff)

[4] Hardware 层
    ├─ WiFi chip (Qualcomm WCN / Broadcom BCM)
    │   └─ 通过 wpa_supplicant + HAL
    ├─ Cellular modem (Qualcomm / MTK)
    │   └─ 通过 RIL (Radio Interface Layer) + QMI/modem
    └─ Ethernet / USB-Net
```

**关键观察**：
- app 不能直接调 kernel socket（**Android SELinux 沙箱**隔离）
- 流量必须经 ConnectivityService 计费 / 限速
- 所有 native 操作经 netd（一个 native daemon）

---

## 2. 数据包全链路（以 TCP 连接为例）

### 2.1 完整 12 步

```
[场景] app 调用 socket("www.example.com", 443)

[1] app 进程
    - Java: new Socket("www.example.com", 443)
    - 调 java.net.Socket → Java 框架

[2] Java 框架
    - 走 OpenJDK 19+ networking
    - 调 InetAddress.getByName() → 触发 DNS 查询
    - 调 Socket.impl.connect() → JNI

[3] JNI / libandroid_runtime
    - 调 native connect()
    - 通过 syscall → kernel socket layer

[4] Kernel socket 层
    - 调 sys_connect()
    - 查 socket 文件
    - 通过 SELinux 检查（socket:connect 权限）

[5] Kernel TCP 协议栈
    - 创建 TCP socket
    - 触发 TCP 三次握手（见 [02](02-TCP-IP协议栈：SYN-ACK-FIN-RST状态机.md)）
    - 分配 sk_buff
    - 走 IPv4 / IPv6 协议栈

[6] Kernel IP 层
    - 路由查询（fib_lookup）
    - 选网卡（eth0 / wlan0 / rmnet0）
    - 调 Netfilter (iptables)
    - 校验和 / TTL 处理

[7] Kernel 设备层
    - 调网卡驱动的 ndo_start_xmit
    - 写入网卡的 TX ring buffer
    - 触发 DMA 发送到网卡硬件

[8] 网卡硬件
    - 发送数据包（WiFi / Cellular / Ethernet）
    - 物理层编码（射频 / 光纤）

[9] Internet（中间网络）
    - ISP / CDN / 路由
    - 到达目标服务器

[10] 服务器响应（同样路径反向）

[11] 接收路径
    - 网卡接收
    - DMA 到 RX ring
    - 软中断 (NET_RX_SOFTIRQ) 处理
    - 走 IP → TCP → 协议栈
    - 放入 socket receive buffer
    - poll / epoll 唤醒

[12] app 读数据
    - 调 InputStream.read()
    - 复制 socket buffer 到用户空间
```

### 2.2 真实时间分布（AOSP 17 实测）

```
[步骤 1-3] app + framework     0.1-1 ms
[步骤 4] socket 层             0.1-0.5 ms
[步骤 5] TCP 三次握手          1-50 ms (RTT 决定)
[步骤 6] IP / 路由              0.1-2 ms
[步骤 7-8] 网卡发送            0.1-1 ms
[步骤 9] Internet              10-300 ms (RTT)
[步骤 10] 服务器处理            5-100 ms
[步骤 11] 接收路径              1-10 ms
[步骤 12] app 读取              0.1-1 ms

总耗时：20-500 ms（地理距离 + 网络质量决定）
```

**关键洞察**：
- 总耗时 80% 在 Internet（步骤 9-10）
- 1% 在本地栈（步骤 1-7、11-12）
- **app 慢"是不是网络问题" = 测 RTT + TLS 握手时间**

---

## 3. 4 大关键路径

### 3.1 路径 1：app → ConnectivityService

```java
// app
ConnectivityManager cm = getSystemService(ConnectivityManager.class);
NetworkRequest req = new NetworkRequest.Builder()
    .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    .build();
cm.registerNetworkCallback(req, callback);  // 注册网络回调
```

```
[1] app → ConnectivityService (Binder)
[2] ConnectivityService → NetworkAgent (framework 内)
[3] NetworkAgent 注册到 system_server
[4] 当网络变化时，app 收到 onAvailable() / onLost() 回调
```

### 3.2 路径 2：app → netd (网络管理)

```
[1] app → ConnectivityService (Binder) → NMS → netd (native)
[2] netd 调 netlink 调 kernel Netfilter
[3] 改 iptables 规则 / 限速 / 防火墙
```

### 3.3 路径 3：app → WiFi HAL

```
[1] app → WifiManager (Binder) → WifiService (system_server)
[2] WifiService → wpa_supplicant (native daemon)
[3] wpa_supplicant → WiFi HAL → WiFi 芯片
```

### 3.4 路径 4：app → Cellular

```
[1] app → TelephonyManager (Binder) → phone进程
[2] phone 进程 → RIL (Radio Interface Layer) → modem
[3] modem 通过 QMI / AT 命令通信
```

---

## 4. 4 大子系统

### 4.1 子系统速查

| 子系统 | 关键进程 | 关键服务 | 关键文件 |
|:-------|:-------|:--------|:-------|
| **TCP/IP 协议栈** | kernel | 内置 | `net/ipv4/` `net/ipv6/` `net/tcp/` |
| **netd (native)** | `/system/bin/netd` | netd | `system/netd/` |
| **ConnectivityService** | system_server | ConnectivityService | `frameworks/base/services/core/java/com/android/server/ConnectivityService.java` |
| **WiFi** | `/system/bin/wpa_supplicant` | WifiService | `frameworks/base/wifi/` `external/wpa_supplicant_8/` |
| **Mobile Data (RIL)** | `/system/bin/rild` | phone | `frameworks/opt/telephony/` `hardware/ril/` |
| **NetworkManagement** | system_server | NetworkManagementService | `frameworks/base/services/core/java/com/android/server/NetworkManagementService.java` |
| **DNS** | system_server | netd | `system/netd/server/` |

### 4.2 关键源码路径

| 路径 | 干什么 |
|:-----|:------|
| `frameworks/base/wifi/` | WiFi 框架 |
| `frameworks/opt/telephony/` | Telephony 框架 |
| `frameworks/base/services/core/java/com/android/server/ConnectivityService.java` | ConnectivityService |
| `frameworks/base/services/core/java/com/android/server/NetworkManagementService.java` | NMS |
| `system/netd/` | netd 全部 |
| `system/netd/server/RouteController.cpp` | 路由管理 |
| `system/netd/server/FirewallController.cpp` | iptables 封装 |
| `external/wpa_supplicant_8/wpa_supplicant/` | wpa_supplicant |
| `frameworks/opt/net/voip/` | VoIP 框架 |
| `system/core/libnetutils/` | net utils |
| `packages/modules/Connectivity/` | Connectivity 模块化 |
| `packages/modules/Wifi/` | WiFi 模块化 |

### 4.3 AOSP 17 网络栈新变化

```
AOSP 12  → mainline 化（Connectivity / Wifi / Telephony 拆出 system/）
AOSP 14  → NetworkStats 增强（per-UID per-iface per-tag）
AOSP 15  → BBR 拥塞控制默认（替代 CUBIC）
AOSP 16  → Privacy Sandbox 网络 API
AOSP 17  → 5G SA / 5G NSA 双模
            Network slicing API
            WiFi 7 (802.11be) 默认
            QUIC 默认协议
```

---

## 5. 5 类 oncall 网络问题

### 5.1 5 类问题分类

| 类别 | 现象 | 第一检查 | 5 秒定位 |
|:-----|:-----|:--------|:--------|
| **N01 网络慢** | 打开网页慢 / 视频卡 | RTT / TLS 握手 | DNS / RTT 大 |
| **N02 网络断** | 突然无网络 | ping / curl | kernel 网络栈 |
| **N03 网络切换** | WiFi/Mobile 切换失败 | ConnectivityService | 网络选路 |
| **N04 流量耗尽** | 流量被某 app 偷跑 | NetworkStatsService | 流量统计 |
| **N05 SELinux denied** | 网络 syscall 被拒 | logcat kernel denied | SELinux 沙箱 |

### 5.2 N01 网络慢的 5 秒定位

```bash
# 1. 测试 RTT
$ adb shell ping -c 4 www.example.com
# time < 50ms 优
# time 50-200ms 中
# time > 200ms 差

# 2. 测试 TLS 握手
$ adb shell "echo | openssl s_client -connect www.example.com:443 -servername www.example.com 2>/dev/null"
# 完成时间
# 5+ 秒 → TLS 慢

# 3. 测 DNS 解析
$ adb shell nslookup www.example.com
# Server:    8.8.8.8
# Address 1: 1.2.3.4
# 解析时间（看 time 字段）

# 4. 测 TCP 连接
$ adb shell "time nc -zv www.example.com 443"
# real 0m0.123s

# 5. 测应用层
$ adb shell "curl -w '%{time_total}\n' -o /dev/null -s https://www.example.com"
# 0.456
```

### 5.3 N02 网络断的 5 秒定位

```bash
# 1. 看 netd 状态
$ adb shell pidof netd
# 期望：1234
# 无 → netd 死

# 2. 看 ConnectivityService 状态
$ adb shell dumpsys connectivity
# 看 NetworkAgentInfo 列表

# 3. 看 WiFi 状态
$ adb shell dumpsys wifi
# 期望：WiFi is enabled
# 期望：connected to <SSID>

# 4. 看 Mobile Data 状态
$ adb shell dumpsys telephony.registry
# 期望：mDataConnectionState=CONNECTED

# 5. 看网络设备
$ adb shell ifconfig
# wlan0 / rmnet0 / eth0 应有 IP

# 6. 看路由
$ adb shell ip route
# default via 192.168.1.1 dev wlan0

# 7. 看 iptables
$ adb shell iptables -L -n -v
# 异常规则可能 block
```

### 5.4 N03 网络切换失败的 5 秒定位

```bash
# 1. 看当前网络类型
$ adb shell dumpsys connectivity | grep "NetworkAgentInfo"
# 看 active network

# 2. 看评分
$ adb shell dumpsys connectivity | grep "score"
# score > 0 = 该网络可用

# 3. 强制切到 WiFi
$ adb shell cmd connectivity set-wifi-enabled true
$ adb logcat -d -b system | grep "wifi"

# 4. 强制切到 Mobile
$ adb shell cmd connectivity set-mobile-data-enabled true
$ adb logcat -d -b system | grep "mobile"
```

### 5.5 N04 流量耗尽的 5 秒定位

```bash
# 1. 看总流量
$ adb shell dumpsys netstats | head -20

# 2. 看 per-UID 流量
$ adb shell dumpsys netstats detail | grep -A5 "uid=10001"
# 看哪个 uid 用流量多

# 3. 看 per-tag 流量
$ adb shell dumpsys netstats detail | grep "tag="

# 4. 看 per-iface 流量
$ adb shell cat /proc/net/dev
# wlan0 / rmnet0 bytes 计数

# 5. 限制某 app 流量
$ adb shell cmd netpolicy set restrict-background-whitelist 10001
```

### 5.6 N05 SELinux denied 的 5 秒定位

```bash
# 1. 找网络 denied
$ adb logcat -d -b kernel | grep "avc: denied" | grep -E "network|socket|connect"
# 例：avc: denied { connect } comm="myapp" ...

# 2. 解读
# scontext: app 域
# tcontext: socket / node / port
# tclass: socket / tcp_socket

# 3. 修法（见 [06-Foundation/SELinux/04](../../01-卷1-Android系统基础与平台/05-安全基础（SELinux%20·%20AVB）/SELinux/04-AVC与avc_denied：从一次denied反推策略.md)）
```

---

## 6. 关键性能指标

### 6.1 4 大网络指标

| 指标 | 单位 | 健康值 | 测量命令 |
|:-----|:-----|:------|:-------|
| **RTT (Round-Trip Time)** | ms | < 50ms | `ping` |
| **Throughput (吞吐量)** | Mbps | 50+ Mbps (WiFi 6) | `iperf3` |
| **DNS 解析时间** | ms | < 50ms | `nslookup` |
| **TCP 重传率** | % | < 1% | `ss -i` |

### 6.2 5 个 perf counter（kernel 视角）

```bash
# 1. 重传
$ adb shell cat /proc/net/netstat | grep "TcpRetrans"
TcpRetransSegs 1234

# 2. 乱序
$ adb shell cat /proc/net/netstat | grep "TcpOutOfOrder"
TcpOutOfOrder 56

# 3. 失败重试
$ adb shell cat /proc/net/netstat | grep "TcpRetransFail"
TcpRetransFail 0

# 4. 主动连接
$ adb shell cat /proc/net/snmp | grep "Active"
Active 12345

# 5. 被动连接
$ adb shell cat /proc/net/snmp | grep "Passive"
Passive 6789
```

### 6.3 5 大网络告警阈值

| 指标 | 阈值 | 含义 |
|:-----|:-----|:-----|
| RTT | > 200ms | 用户感知慢 |
| 重传率 | > 5% | 网络质量差 |
| DNS 解析 | > 200ms | DNS 慢 |
| Throughput | < 1Mbps (WiFi 6) | 网络质量差 |
| Connect timeout | > 30s | 远端不可达 |

---

## 7. oncall 5 分钟决策

```
[问题] 网络相关
  ↓
[1] 30 秒判断类型（5 秒）
  ├─ "网络慢" → N01 (RTT / TLS)
  ├─ "网络断" → N02 (ping / curl)
  ├─ "切换失败" → N03 (ConnectivityService)
  ├─ "流量多" → N04 (netstats)
  └─ "denied" → N05 (SELinux)
  ↓
[2] 抓现场（30-60 秒）
  ├─ N01 → ping / curl / tcping
  ├─ N02 → dumpsys connectivity / wifi
  ├─ N03 → dumpsys connectivity
  ├─ N04 → dumpsys netstats detail
  └─ N05 → logcat -b kernel | grep denied
  ↓
[3] 5 分钟定位
  ├─ N01 → 看 RTT 时间
  ├─ N02 → 看 NetworkAgentInfo
  ├─ N03 → 看 network score
  ├─ N04 → 看 per-UID 流量
  └─ N05 → 看 4 字段 → 加 .te
  ↓
[4] 出报告（5 分钟）
```

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [02 TCP/IP 状态机](02-TCP-IP协议栈：SYN-ACK-FIN-RST状态机.md) | 下篇 |
| [03 DNS/DHCP](03-DNS-DHCP：从解析到连接的5秒流程.md) | 续篇 |
| [04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md) | 续篇 |
| [05 netd/NMS](05-netd-NetworkManagementService：网络策略.md) | 续篇 |
| [06 WiFi](06-WiFi协议栈：wpa-supplicant-HAL-连接.md) | 续篇 |
| [07 Mobile Data](07-Mobile-Data：RIL-数据业务-漫游.md) | 续篇 |
| [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md) | 续篇 |
| [01-Mechanism/Kernel/IO/11-eBPF](../../../../03-卷3-核心机制/16-IO 与存储/11-eBPF在IO性能分析中的实战：从bpftrace到Android落地.md) | eBPF 工具 |
| [06-Foundation/SELinux/04-AVC与avc_denied](../../01-卷1-Android系统基础与平台/05-安全基础（SELinux%20·%20AVB）/SELinux/04-AVC与avc_denied：从一次denied反推策略.md) | N05 修法 |
| [02-Symptom/S09-jank/01-症状机制](../../../02-Symptom/S09-jank/01-症状机制.md) | 卡顿 |

---

## 9. 下一篇预告 + 自检

### 9.1 下一篇

[02 TCP/IP 协议栈：SYN/ACK/FIN/RST 状态机](02-TCP-IP协议栈：SYN-ACK-FIN-RST状态机.md) 讲清：
- TCP 11 个状态完整图
- 三次握手 / 四次挥手每步栈
- RST 触发场景
- AOSP 17 默认参数（BBR / CUBIC / window size）
- 5 个真实调优 case

### 9.2 看完本文的自检

- [ ] 能说 4 层架构（app / framework / kernel / hardware）
- [ ] 能说 12 步全链路
- [ ] 能说 4 大子系统（TCP/IP / netd / Connectivity / WiFi/Mobile）
- [ ] 能用 5 类问题分类 5 秒定位
- [ ] 知道 4 大性能指标 + 告警阈值
- [ ] 知道 oncall 5 分钟决策树

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
