# 06-Foundation/Network · 03 · DNS / DHCP：从解析到连接的 5 秒流程

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 网络问题排查
>
> **强依赖**：[01 网络栈总览](01-网络栈总览：从app-socket到网卡的全链路.md) · [02 TCP/IP 状态机](02-TCP-IP协议栈：SYN-ACK-FIN-RST状态机.md) · [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 DNS 解析 + DHCP 分配 + 完整"打开一个网页"5 秒流程讲清楚——oncall 5 秒定位"网络卡在 DNS 还是 TCP"
- **不是**：不复述 [02 §2 三次握手](02-TCP-IP协议栈：SYN-ACK-FIN-RST状态机.md)（本文讲握手之前）；不复述具体 WiFi/Mobile（[06](06-WiFi协议栈：wpa-supplicant-HAL-连接.md)/[07](07-Mobile-Data：RIL-数据业务-漫游.md)）
- **承接自**：[02 §2.1 握手 1-50ms](02-TCP-IP协议栈：SYN-ACK-FIN-RST状态机.md) → 本文讲"握手之前 DNS 多少 ms"
- **衔接去**：[04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md) / [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | DNS / DHCP 合并 1 篇 | oncall 5 秒决策相关 |
| 2 | 第 4 章 5 秒"打开网页"流程 | 实战最常用 |
| 3 | 第 5 章 DoH / DoT 实战 | AOSP 17 默认 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**DNS + DHCP = TCP 之前的"准备"——oncall 5 秒定位"网络慢在准备"还是"在传输"。**

AOSP 17 上 30% 的"打开网页慢"根因在 DNS（不是 TCP）。理解 DNS / DHCP = 网络问题 5 秒定位。

---

## 1. DNS 是什么

### 1.1 一句话定义

**DNS = 把域名（`www.example.com`）转 IP（`93.184.216.34`）的分布式数据库——app 每次联网都要查 1-3 次。**

### 1.2 DNS 层级

```
[1] 根服务器 (root)
    └─ .  (13 个根服务器集群，全球)
[2] 顶级域服务器 (TLD)
    └─ .com / .net / .org / .cn / ...
[3] 权威服务器 (Authoritative)
    └─ example.com 的 ns1.example.com
[4] 本地缓存
    ├─ 浏览器缓存
    ├─ OS 缓存
    └─ Local DNS resolver
```

### 1.3 DNS 解析类型

| 类型 | 含义 | 用途 | 性能 |
|:-----|:-----|:-----|:-----|
| **A 记录** | 域名 → IPv4 | 主流 | 快 |
| **AAAA 记录** | 域名 → IPv6 | IPv6 | 快 |
| **CNAME** | 域名 → 域名 | 别名 | 多次查询 |
| **MX** | 邮件 | 邮件 | 中 |
| **TXT** | 文本 | SPF / DKIM | 中 |
| **NS** | 域名服务器 | 委派 | 中 |
| **PTR** | IP → 域名 | 反向解析 | 慢 |

### 1.4 真实查询流程

```
[app 调 java.net.InetAddress.getByName("www.example.com")]

[1] 检查浏览器缓存
    └─ 命中 → 直接返回（0 ms）
[2] 检查 OS 缓存（/etc/resolv.conf + nscd）
    └─ 命中 → 返回（0 ms）
[3] 调 local DNS resolver
    └─ 通常是 ISP 或 8.8.8.8
[4] local DNS 查根服务器
    └─ root → "找 .com"
[5] local DNS 查 .com TLD
    └─ "找 example.com 的 ns"
[6] local DNS 查 example.com ns
    └─ 拿到 IP
[7] 返回给 app
```

**关键**：
- local DNS 缓存是关键（命中 = 0 ms）
- 完整递归查询 = 30-100 ms（首次）
- TTL 决定缓存多久

---

## 2. Android 上的 DNS 架构

### 2.1 4 层 DNS 架构

```
[app 进程]
   │
   │ 调 java.net.InetAddress.getByName()
   ▼
[Java 框架]
   │ OpenJDK DNS resolver
   │ 看 InetAddress cache
   ▼
[JNI / libandroid_runtime]
   │ 调 libc getaddrinfo()
   ▼
[libc / bionic]
   │ 看 /etc/resolv.conf
   │ 调 socket() AF_INET
   │ 调 sendto() DNS query
   ▼
[netd]
   │ netd 拦截 DNS 请求（Android 10+）
   │ 走 DoH/DoT 加密
   ▼
[Kernel socket]
   │ UDP 53 端口
   ▼
[DNS server]
   └─ 8.8.8.8 / ISP
```

### 2.2 AOSP 17 DNS 新机制

#### DoH（DNS over HTTPS）

```bash
# 启用
$ adb shell settings put global dns_over_https_enabled 1
$ adb shell settings put global dns_over_https_specifier "https://dns.google/dns-query{?dns}"

# 流量特征
# 原来：UDP 53 端口
# 现在：TCP 443 端口 + TLS + HTTPS
```

#### DoT（DNS over TLS）

```bash
# 启用
$ adb shell settings put global private_dns_mode hostname
$ adb shell settings put global private_dns_specifier dns.google

# 流量特征
# TCP 853 端口 + TLS
```

#### netd DNS 拦截

```cpp
// system/netd/server/DnsProxyListener.cpp
// Android 10+：app 发的 DNS 请求必须经 netd
// 目的：统一管理 DoH/DoT + 缓存 + 统计
```

### 2.3 DNS 配置文件

```bash
# /etc/resolv.conf
nameserver 8.8.8.8
nameserver 1.1.1.1

# /etc/hosts
127.0.0.1 localhost
::1 localhost
```

### 2.4 DNS 缓存位置

| 缓存 | 路径 | TTL |
|:-----|:-----|:---|
| **app 进程** | `InetAddress.cache` | 由 TTL 决定 |
| **netd** | `system/netd/server/DnsProxyListener.cpp` | 60s |
| **libc** | `bionic/libc/netbsd/resolv` | 由 TTL 决定 |
| **浏览器** | Chrome 内置 | 60s |

---

## 3. DHCP 是什么

### 3.1 一句话定义

**DHCP = 自动给设备分配 IP 地址、子网掩码、DNS 服务器——Android 启动时连 WiFi 后由 DHCP 拉 IP。**

### 3.2 DHCP 4 步握手

```
[device]                              [DHCP server]
   |                                        |
   | 1. DISCOVER (广播)                    |
   |--------------------------------------->|
   |                                        |
   | 2. OFFER (含 IP 候选)                |
   |<---------------------------------------|
   |                                        |
   | 3. REQUEST (确认用这个 IP)            |
   |--------------------------------------->|
   |                                        |
   | 4. ACK (确认)                         |
   |<---------------------------------------|
   |                                        |
[device 设置 IP / DNS / 默认网关]
```

### 3.3 DHCP 提供的信息

```bash
# DHCP 分配的 5 大信息
IP 地址:    192.168.1.100
子网掩码:   255.255.255.0
默认网关:   192.168.1.1
DNS 服务器: 8.8.8.8, 1.1.1.1
租约时间:   86400 秒 (24 小时)
```

### 3.4 Android DHCP 架构

```
[Android WiFi 连接]
   │
   │ wpa_supplicant 完成 4 次握手 (WPA2)
   ▼
[system_server → ConnectivityService]
   │
   │ 触发 DHCP 客户端
   ▼
[netd / dhcpcd]
   │ system/netd/server/DhcpClient.cpp
   │ 或 external/dhcpcd
   ▼
[Linux 协议栈]
   │ raw socket 67 端口
   │ UDP 广播
   ▼
[DHCP server (路由器)]
```

**关键**：
- Android 用 dhcpcd 或 netd 内置 DHCP 客户端
- 租约时间到 → 续约（4 步）
- 移动到新 WiFi → 重新 DHCP

### 3.5 5 大 DHCP 异常场景

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **WiFi 已连但无网络** | DHCP 失败 | 查 IP |
| **IP 是 169.254.x.x** | DHCP 没成功（APIPA） | 查 WiFi |
| **DNS 解析失败** | DHCP 没分配 DNS | 查 resolv.conf |
| **WiFi 切换慢** | DHCP 续约慢 | 查 netd |
| **租约过期掉线** | DHCP 续约失败 | 查 lease |

---

## 4. 完整 5 秒"打开网页"流程

### 4.1 真实时间线

```
[场景] 打开 https://www.example.com/，DNS 首次解析，WiFi 已连

[时刻 0ms] app 调 URL.openConnection()
[时刻 0-30ms] DNS 解析
   ├─ [0-1ms] 检查 InetAddress 缓存
   │         未命中
   ├─ [1-2ms] 调 libc getaddrinfo()
   ├─ [2-3ms] 读 /etc/resolv.conf
   │         nameserver 8.8.8.8
   ├─ [3-50ms] UDP 请求 8.8.8.8:53
   │         → 查询 www.example.com
   │         → 8.8.8.8 查根 → .com → example.com ns
   │         → 返回 93.184.216.34
   └─ [50-51ms] 拿到 IP

[时刻 51-150ms] TCP 三次握手
   ├─ [51ms] SYN
   ├─ [100ms] SYN+ACK
   └─ [150ms] ACK

[时刻 150-250ms] TLS 握手
   ├─ [150ms] ClientHello
   ├─ [200ms] ServerHello + Certificate
   ├─ [240ms] Key Exchange
   └─ [250ms] Finished

[时刻 250-450ms] HTTP 请求 / 响应
   ├─ [250ms] GET / HTTP/1.1
   ├─ [350ms] HTTP/1.1 200 OK + 头
   └─ [450ms] body 完成

总耗时: 450ms
```

### 4.2 真实时间分布

```
DNS 解析:      30-50ms  (10%)
TCP 握手:      50-100ms (20%)
TLS 握手:      50-200ms (20%)
HTTP 请求:    100-300ms (50%)
```

**关键洞察**：
- 50% 时间在 HTTP 请求 / 响应（服务器处理）
- DNS 占 10%，但**慢 1 秒 = 多 1 秒总耗时**
- TLS 占 20%，**慢 = 服务器慢或网络差**

### 4.3 5 大慢的根因

| 阶段 | 慢的根因 | 测量命令 |
|:-----|:--------|:--------|
| **DNS** | DNS server 慢 / 跨网 | `nslookup time` |
| **TCP** | 网络 RTT 高 / 丢包 | `ping time` |
| **TLS** | 服务器慢 / 证书验证 | `openssl s_client` |
| **HTTP** | 服务器处理慢 | `curl time_total` |
| **数据下载** | 内容大 / 网络慢 | `curl size_download / time` |

### 4.4 oncall 5 步定位"打开网页慢"

```bash
# 1. DNS 时间
$ adb shell "time nslookup www.example.com"
# real 0m0.500s
# > 100ms = DNS 慢

# 2. TCP 握手
$ adb shell "time nc -zv www.example.com 443"
# real 0m0.150s
# > 200ms = TCP 慢

# 3. TLS 握手
$ adb shell "echo | openssl s_client -connect www.example.com:443 -servername www.example.com 2>/dev/null | head"
# 完成时间
# > 500ms = TLS 慢

# 4. 完整 HTTP
$ adb shell "curl -w 'DNS:%{time_namelookup} TCP:%{time_connect} TLS:%{time_appconnect} HTTP:%{time_total}\n' -o /dev/null -s https://www.example.com"
# DNS:0.030 TCP:0.080 TLS:0.180 HTTP:0.450
# 看哪段最慢

# 5. 总结
# DNS 30ms + TCP 80ms + TLS 180ms = 290ms
# HTTP 450ms - 290ms = 160ms 服务器处理
# 网络总耗时 290ms（可接受）
# 服务器 160ms（可接受）
```

---

## 5. DoH / DoT 实战

### 5.1 DoH（DNS over HTTPS）

**目的**：加密 DNS 查询，防止运营商窥探

```bash
# 启用
$ adb shell settings put global dns_over_https_enabled 1
$ adb shell settings put global dns_over_https_specifier \
    "https://dns.google/dns-query{?dns}"

# 验证
$ adb shell cmd netpolicy get restrict-background
# 期望：disabled 或 enabled

# 抓包看 DoH 流量
$ adb shell tcpdump -i any -nn -c 10 'tcp port 443'
# 看 443 端口的 DoH 流量
```

### 5.2 DoT（DNS over TLS）

```bash
# 启用
$ adb shell settings put global private_dns_mode hostname
$ adb shell settings put global private_dns_specifier "dns.google"

# 验证
$ adb shell "cmd network_stack get private_dns"
# 期望：dns.google

# 抓包看 DoT 流量
$ adb shell tcpdump -i any -nn -c 10 'tcp port 853'
# 看 853 端口的 DoT 流量
```

### 5.3 DoH vs DoT 对比

| 维度 | DoH | DoT |
|:-----|:----|:-----|
| **端口** | 443 (HTTPS) | 853 |
| **协议** | HTTPS (TCP) | TLS (TCP) |
| **兼容** | 通过 HTTPS 代理 | 需专用端口 |
| **延迟** | +50-100ms (TLS + HTTP) | +30-50ms (TLS) |
| **绕过** | 难以阻止 | 易识别 |

### 5.4 4 大 DNS server 选型

| DNS server | 性能 | 隐私 | 推荐 |
|:-----------|:-----|:-----|:-----|
| **8.8.8.8 (Google)** | 优 | 中 | 性能优先 |
| **1.1.1.1 (Cloudflare)** | 优 | 高 | 隐私优先 |
| **ISP** | 中 | 低 | 简单 |
| **DoH/DoT** | 优 | 高 | 隐私 + 性能 |

---

## 6. 实战：DNS / DHCP 排错 5 案例

### 6.1 案例 1：app 网络慢 2 秒

```
[症状] 打开 app 主页慢 2 秒

[Step 1] DNS
$ adb shell "time nslookup www.example.com"
# real 0m1.500s
# → DNS 慢 1.5 秒

[Step 2] 看 DNS server
$ adb shell cat /etc/resolv.conf
# nameserver 8.8.8.8
# （8.8.8.8 通常 < 50ms，不应该 1.5 秒）

[Step 3] 看 netd 状态
$ adb shell dumpsys netstats | head -20
# 看 DNS 查询

[Step 4] 看 WiFi 信号
$ adb shell dumpsys wifi | grep "RSSI"
# RSSI: -80 dBm (信号弱)

[Step 5] 结论：WiFi 弱导致 DNS 慢

[修法]
- 切到 Mobile Data
- 或加 5G 切换
- 或加 DoH 缓存
```

### 6.2 案例 2：IP 是 169.254.x.x

```
[症状] WiFi 已连但上不了网

[Step 1] 看 IP
$ adb shell ifconfig wlan0
# inet addr:169.254.123.45
# → APIPA（DHCP 失败）

[Step 2] 重连 WiFi
$ adb shell svc wifi disable
$ adb shell svc wifi enable
# 等 10 秒

[Step 3] 重新看 IP
$ adb shell ifconfig wlan0
# inet addr:192.168.1.100
# → DHCP 重新分到

[Step 4] 如果不行，看 DHCP server
$ adb shell "logcat -d -b system | grep DHCP"
# 看 DHCP 错误

[Step 5] 结论：DHCP server 暂时失败
```

### 6.3 案例 3：DoH 启用后断网

```
[症状] 启用 DoH 后 app 上不了网

[Step 1] 看 DoH 状态
$ adb shell settings get global dns_over_https_enabled
# 1

[Step 2] 看 DoH server
$ adb shell settings get global dns_over_https_specifier
# https://dns.google/dns-query{?dns}

[Step 3] 测试 DoH
$ adb shell "curl -v https://dns.google/dns-query 2>&1 | head"
# 期望 200 OK
# 如果 404 / timeout → DoH 失败

[Step 4] 关 DoH 测试
$ adb shell settings put global dns_over_https_enabled 0
# 5 秒后 app 恢复

[Step 5] 结论：DoH 流量被防火墙拦了

[修法]
- 改用 DoT
- 或允许 DoH 流量
```

### 6.4 案例 4：DHCP 续约慢

```
[症状] WiFi 跑 24 小时后断网

[Step 1] 看租约时间
$ adb shell "dumpsys wifi | grep 'lease'"
# lease duration: 86400
# expires: 2026-07-28 10:30:00

[Step 2] 看续约日志
$ adb shell "logcat -d -b system | grep -E 'DHCP|lease' | tail"

[Step 3] 看续约时间
# DHCP 续约 = 50% 租约时间 (12 小时)

[Step 4] 看是否续约成功
$ adb shell "logcat -d -b system | grep 'renewed'"
# 期望：renewed lease for ...

[Step 5] 结论：续约失败 → 租约到期 → 重新 DHCP 慢
```

### 6.5 案例 5：移动网络 DNS 失败

```
[症状] 4G/5G 下 app 上不了网，WiFi 正常

[Step 1] 看网络状态
$ adb shell dumpsys connectivity | grep "NetworkAgentInfo"
# 看到 wlan0 在线

[Step 2] 关 WiFi
$ adb shell svc wifi disable
# 等 5 秒

[Step 3] 看网络状态
$ adb shell dumpsys connectivity | grep "NetworkAgentInfo"
# 看到 rmnet_data0 在线

[Step 4] 测试 DNS
$ adb shell "nslookup www.example.com"
# 失败

[Step 5] 结论：Mobile DNS 失败（被运营商拦截）

[修法]
- 改用 DoH
- 或换 DNS server
```

---

## 7. 5 大性能指标

| 指标 | 单位 | 健康值 | 测量命令 |
|:-----|:-----|:------|:-------|
| **DNS 解析** | ms | < 50ms | `time nslookup` |
| **DHCP 4 步** | ms | < 500ms | `time dhclient` |
| **DHCP 续约** | ms | < 200ms | 看 logcat |
| **DoH 解析** | ms | < 200ms | `curl -w time_appconnect` |
| **DoT 解析** | ms | < 150ms | `tcpdump + curl` |

---

## 8. oncall 5 分钟决策

```
[问题] 网络相关（DNS/DHCP 视角）
  ↓
[1] 30 秒判断（5 秒）
  ├─ "网络慢" → DNS 慢？
  ├─ "WiFi 已连但无网络" → DHCP 失败？
  ├─ "DNS 解析失败" → DNS server 问题？
  ├─ "DoH 启用后断网" → DoH 流量被拦？
  └─ "WiFi 跑 24h 断" → DHCP 续约？
  ↓
[2] 抓现场（30-60 秒）
  ├─ DNS → nslookup + tcpdump
  ├─ DHCP → ifconfig + logcat
  ├─ DoH → curl + tcpdump
  └─ 续约 → logcat | grep lease
  ↓
[3] 5 分钟定位
  ├─ DNS 慢 → 改 server / 启 DoH
  ├─ DHCP 失败 → 重连 / 改 server
  ├─ DoH 失败 → 改 DoT
  └─ 续约失败 → 短租约
  ↓
[4] 出报告（5 分钟）
```

---

## 9. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 网络栈总览](01-网络栈总览：从app-socket到网卡的全链路.md) | 上篇 |
| [02 TCP/IP 状态机](02-TCP-IP协议栈：SYN-ACK-FIN-RST状态机.md) | 上篇 |
| [04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md) | 续篇 |
| [05 netd/NMS](05-netd-NetworkManagementService：网络策略.md) | 续篇 |
| [06 WiFi](06-WiFi协议栈：wpa-supplicant-HAL-连接.md) | 续篇 |
| [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md) | 续篇 |

---

## 10. 收官 + 自检

### 10.1 看完本文的自检

- [ ] 能说 DNS 4 步解析流程
- [ ] 能说 DHCP 4 步分配 IP
- [ ] 能用 curl 5 段时间定位
- [ ] 能区分 DoH / DoT / 传统 DNS
- [ ] 知道 Android 17 默认 DNS 配置
- [ ] 知道 5 大异常场景的修法
- [ ] 能用 4 大 DNS server 选型

### 10.2 收官话

DNS / DHCP 在网络栈里属于**"准备阶段"**——慢 1 秒 = 整个 HTTP 慢 1 秒。

下一步推荐读：
- [04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md) — 怎么选网络
- [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md) — 工具
- [06 WiFi](06-WiFi协议栈：wpa-supplicant-HAL-连接.md) — WiFi 协议栈

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
