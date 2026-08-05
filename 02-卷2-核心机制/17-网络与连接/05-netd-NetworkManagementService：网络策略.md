# 06-Foundation/Network · 05 · netd / NetworkManagementService：网络策略

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 防火墙 / 流量 / 路由问题
>
> **强依赖**：[01 网络栈总览](01-网络栈总览：从app-socket到网卡的全链路.md) · [04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 netd native daemon + NetworkManagementService (NMS) + iptables/route 完整讲清楚——oncall 5 秒定位"app 流量被谁拦了 / 路由表错"
- **不是**：不复述 [01 §3.2 路径 2 netd](01-网络栈总览：从app-socket到网卡的全链路.md)（本文展开 netd + NMS）；不复述 [04 ConnectivityService 选路](04-ConnectivityService：网络选路-评分-切换.md)（本文偏底层）
- **承接自**：[04 §3 NetworkAgent 选路](04-ConnectivityService：网络选路-评分-切换.md) → 本文讲"选好之后谁执行 iptables / 路由"
- **衔接去**：[06 WiFi](06-WiFi协议栈：wpa-supplicant-HAL-连接.md) / [07 Mobile Data](07-Mobile-Data：RIL-数据业务-漫游.md) / [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 2 章 netd 架构 + AOSP 17 重大变化 | oncall 5 秒定位关键 |
| 2 | 第 3 章 NMS 5 大职责 | 5 大责任清晰 |
| 3 | 第 5 章 5 大真实 case | 实战用 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**netd = native 层的网络"执行官"——调 iptables / 路由 / 限速 / 防火墙；NMS = java 层跟 netd 对话的"指挥官"。**

AOSP 17 上 netd 跑在 `/system/bin/netd`，NMS 跑在 system_server，两者通过 unix socket 通信。理解 netd/NMS = 5 秒定位"流量被拦 / 路由错 / 限速"。

---

## 1. netd 是什么

### 1.1 一句话定义

**netd = Android 的 native 网络 daemon——所有"动 iptables / 路由表"的操作都经 netd。**

### 1.2 netd 在网络栈的位置

```
[app 进程]
   │
   │ 调 ConnectivityManager
   ▼
[ConnectivityService (system_server)]
   │
   │ 调 NMS
   ▼
[NetworkManagementService (system_server)]
   │
   │ 通过 unix socket 通信
   ▼
[netd (native daemon)]
   │
   │ 调 netlink 调 kernel
   ▼
[Kernel Netfilter / Routing]
```

### 1.3 netd 关键源码

```
system/netd/
├── main.cpp                    ← netd 入口
├── server/                     ← netd 服务
│   ├── NetdService.cpp         ← IPC 入口
│   ├── RouteController.cpp      ← 路由
│   ├── FirewallController.cpp   ← iptables 封装
│   ├── BandwidthController.cpp  ← tc 限速
│   ├── ClatdController.cpp      ← CLAT (IPv4-IPv6)
│   ├── FwmarkServer.cpp         ← fwmark 标签
│   ├── IdletimerController.cpp  ← 流量统计
│   ├── InterfaceController.cpp  ← 接口管理
│   ├── TetherController.cpp     ← 热点
│   └── DnsProxyListener.cpp     ← DNS 拦截
├── client/                     ← netd 客户端
│   ├── NetdClient.cpp
│   └── ...
└── tests/                      ← 测试
```

### 1.4 关键概念

| 概念 | 含义 | 用途 |
|:-----|:-----|:-----|
| **fwmark** | 包标记（32 bit） | 路由选路 / 限速 |
| **UID** | Linux 用户 ID | 限速 / 计费 |
| **chain** | iptables 规则链 | 防火墙 |
| **rule** | 路由规则 | 选路 |
| **interface** | 网络接口 | 物理 / 虚拟 |

---

## 2. netd 架构

### 2.1 4 大子系统

| 子系统 | 干什么 | 关键文件 |
|:-------|:-----|:--------|
| **Firewall** | iptables 规则 | `FirewallController.cpp` |
| **Bandwidth** | tc 限速 | `BandwidthController.cpp` |
| **Route** | 路由表 | `RouteController.cpp` |
| **Tether** | 热点 | `TetherController.cpp` |

### 2.2 AOSP 17 netd 重大变化

#### A. netd-BPF 替代 iptables

AOSP 12+ 把 iptables 改成 eBPF：

```bash
# 旧（AOSP 11-）
$ adb shell iptables -L -n -v
# 显示 iptables 规则

# 新（AOSP 12+）
$ adb shell cmd netpolicy list
# 显示 netpolicy 规则（背后 eBPF）

# 实际数据
$ adb shell "cat /proc/net/ip_tables_names 2>/dev/null || echo 'no iptables'"
# AOSP 17 默认没有 iptables
```

**关键变化**：
- iptables 性能差（O(n) 遍历）
- eBPF 性能优（O(1) hash 查找）
- AOSP 17 默认 eBPF
- 老 iptables 工具还能用但底层变了

#### B. TrafficStats 增强

```bash
# 旧：AOSP 11- 用 /proc/net/xt_qtaguid
# 新：AOSP 12+ 用 eBPF
$ adb shell cat /proc/net/xt_qtaguid/stats
# AOSP 17 还在但用 eBPF 实现
```

#### C. DoH/DoT 集成

```bash
# AOSP 10+：app 发的 DNS 必须经 netd
# netd 拦截 + 走 DoH/DoT
$ adb shell dumpsys netstats | grep DNS
```

### 2.3 netd IPC

```cpp
// system/netd/server/NetdService.cpp
class NetdService : public BinderService<NetdService> {
    // 提供 binder 接口给 NMS
    binder::Status setFirewallUidChainRule(uid_t uid, int network, FirewallRule rule) {
        return mFwmarkServer.setFirewallUidChainRule(uid, network, rule);
    }
    
    binder::Status bandwidthAddNaughtyApps(int uid) {
        return mBandwidthController.addNaughtyApps(uid);
    }
    
    binder::Status networkAddInterface(...) {
        return mInterfaceController.addInterface(...);
    }
}
```

### 2.4 4 大 IPC 命令

| 命令 | 类 | 用法 |
|:-----|:---|:-----|
| `setFirewallUidChainRule` | Firewall | 给 uid 加防火墙规则 |
| `bandwidthAddNaughtyApps` | Bandwidth | 加限速 app |
| `networkAddRoute` | Route | 加路由 |
| `tetherStart` | Tether | 开热点 |

---

## 3. NetworkManagementService (NMS) 是什么

### 3.1 一句话定义

**NMS = system_server 内的"网络管理"服务——app 调 ConnectivityManager 时，NMS 调 netd 干活。**

### 3.2 NMS 5 大职责

| 职责 | 干什么 | 关键方法 |
|:-----|:-----|:--------|
| **防火墙** | app 是否能联网 | `setUidFirewallRule()` |
| **限速** | app 流量限制 | `setInterfaceQuota()` |
| **路由** | 路由表管理 | `addRoute()` |
| **统计** | 流量统计 | `getNetworkStatsUid()` |
| **配置** | 网络接口配置 | `setInterfaceUp/Down()` |

### 3.3 关键源码

```
frameworks/base/services/core/java/com/android/server/
├── NetworkManagementService.java  ← NMS 核心
├── NetworkStatsService.java       ← 流量统计
├── NetworkPolicyManagerService.java  ← 流量策略
└── ConnectivityService.java        ← CS 调 NMS
```

### 3.4 NMS 调 netd 的时序

```
[app 调 ConnectivityManager.setNetworkRestriction()]

[1] app → ConnectivityService (Binder)
[2] CS → NMS (Binder)
[3] NMS → netd (Unix socket, android/netd/NdcNd)
[4] netd → iptables / eBPF (Native call)
[5] netd → kernel (netlink)
[6] kernel → 生效

总耗时: 1-10ms
```

### 3.5 5 大 NMS 调 netd 命令

| 命令 | 类 | 用法 |
|:-----|:---|:-----|
| `setFirewallUidChainRule(uid, ...)` | Firewall | app 防火墙 |
| `bandwidthAddNaughtyApps(uid)` | Bandwidth | app 限速 |
| `setInterfaceQuota(iface, bytes)` | Quota | 接口配额 |
| `addRoute(iface, dest, gateway)` | Route | 加路由 |
| `setInterfaceUp(iface)` | Interface | 接口 up |

---

## 4. iptables / eBPF 实战

### 4.1 iptables 真实规则（AOSP 11 之前）

```bash
# 1. 看防火墙规则
$ adb shell iptables -L -n -v

# Chain INPUT (policy ACCEPT 0 packets, 0 bytes)
#  pkts bytes target  prot opt in  out source  destination
#  ... ...

# Chain FORWARD (policy ACCEPT)
#  ... ...

# Chain OUTPUT (policy ACCEPT)
#  ... ...

# 2. 看 nat 表
$ adb shell iptables -t nat -L -n -v

# 3. 看 mangle 表
$ adb shell iptables -t mangle -L -n -v
```

### 4.2 eBPF 实际查看（AOSP 17）

```bash
# 1. 看 netpolicy 规则
$ adb shell cmd netpolicy list
# allowed uids: 0, 1000, 1001
# blocked uids: 
# ...

# 2. 看防火墙规则
$ adb shell cmd netpolicy list uid-rules
# 10000: allow
# 10001: allow
# 10002: deny  ← 这个 app 禁网

# 3. 看限速规则
$ adb shell cmd netpolicy set restrict-background-whitelist 10001
# 10001 加入白名单
```

### 4.3 AOSP 17 iptables 真实状态

```bash
# 检查是否还有 iptables
$ adb shell which iptables
# /system/bin/iptables（还在，但实际不用）
$ adb shell "iptables -L 2>&1 | head -3"
# iptables v1.8.7 (legacy): can't initialize iptables table `filter': 
# Table does not exist (do you need to insmod?)
# → AOSP 17 默认没 iptables，eBPF 替代

# 看 eBPF
$ adb shell ls /sys/fs/bpf/netd/
# map:penalty_box
# map:uid_permission
# prog:sk_filter
# ...
```

### 4.4 5 大防火墙场景

| 场景 | 现象 | 5 秒定位 |
|:-----|:-----|:--------|
| **app 禁网** | "网络不可用" | `cmd netpolicy list uid-rules` |
| **app 限速** | 流量超额 | `cmd netpolicy list restrict-background` |
| **VPN 拦流量** | VPN 启用后 app 走 VPN | `dumpsys vpn` |
| **热点拦** | 热点开但 app 不能用 | `dumpsys connectivity tethering` |
| **后台受限** | 后台不能用流量 | `cmd netpolicy set restrict-background true` |

---

## 5. 5 大真实 case

### 5.1 Case 1：app 上不了网（被 firewall 拦了）

```
[症状] app 启动后 "网络不可用"

[Step 1] 看防火墙
$ adb shell cmd netpolicy list uid-rules
# 10001: deny  ← 这就是 app uid

[Step 2] 看完整规则
$ adb shell cmd netpolicy list
# allowed uids: 0, 1000
# blocked uids: 10001

[Step 3] 修法
$ adb shell cmd netpolicy set restrict-background-whitelist 10001
# 10001 加入白名单

[Step 4] 验证
$ adb shell cmd netpolicy list uid-rules
# 10001: allow

[Step 5] 结论：app 被 firewall 拦了
```

### 5.2 Case 2：app 流量超额被限速

```
[症状] app 后台被限速

[Step 1] 看 bandwidth
$ adb shell dumpsys netstats detail | grep "10001" | head

# 流量：500MB（已超）

[Step 2] 看 restrict-background
$ adb shell cmd netpolicy get restrict-background
# true（开了）

[Step 3] 看 deny-on-metered
$ adb shell cmd netpolicy list restrict-background-blocklist
# 10001 在 list

[Step 4] 修法
$ adb shell cmd netpolicy set restrict-background-whitelist 10001
# 加白名单

[Step 5] 结论：app 在 restrict-background-blocklist
```

### 5.3 Case 3：VPN 启用后 app 走错网络

```
[症状] VPN 启用后 app 仍用直连

[Step 1] 看 VPN
$ adb shell dumpsys connectivity | grep -A5 "VPN"
# VPN active

[Step 2] 看 underlyNetworks
$ adb shell "dumpsys connectivity | grep underly"

# underlyNetworks: [Mobile]
# → app bypass VPN

[Step 3] 看 firewall
$ adb shell cmd netpolicy list uid-rules
# 10001: allow  ← 直连允许

[Step 4] 修法
- 修 app 代码（去掉 NOT_VPN）
- 调 VPN 强制走 VPN
```

### 5.4 Case 4：热点开但 app 流量被拦

```
[症状] 热点开但连接设备不能上网

[Step 1] 看 tethering
$ adb shell dumpsys connectivity tethering
# Tethering state: ON

[Step 2] 看 iptables
$ adb shell iptables -t nat -L -n -v | head
# Chain POSTROUTING (policy ACCEPT)
# pkts bytes target prot opt in  out source destination
# ... MASQUERADE all -- * wlan0 192.168.43.0/24 !192.168.43.0/24

[Step 3] 看路由
$ adb shell ip route
# 192.168.43.0/24 dev wlan0 proto static scope link

[Step 4] 看 netd 状态
$ adb shell pidof netd
# 1234

[Step 5] 结论：NAT / 路由都对
# 问题可能在 mobile 端
```

### 5.5 Case 5：流量统计不准

```
[症状] 流量统计 0，但 app 实际用了流量

[Step 1] 看 NetworkStatsService
$ adb shell dumpsys netstats
# 看 dev 各 iface 流量

[Step 2] 看 /proc/net/dev
$ adb shell cat /proc/net/dev | head
# wlan0: 1234 bytes
# rmnet_data0: 5678 bytes

[Step 3] 对比
# NetworkStatsService 0 vs /proc/net/dev 1234
# → NetworkStatsService 缓存陈旧

[Step 4] 强制刷新
$ adb shell cmd netstats reset

[Step 5] 结论：NetworkStatsService 缓存
```

---

## 6. oncall 5 分钟决策

```
[问题] 网络相关（NMS/netd 视角）
  ↓
[1] 30 秒判断（5 秒）
  ├─ "app 不能上网" → firewall？
  ├─ "app 限速" → bandwidth？
  ├─ "流量统计错" → NetworkStatsService？
  ├─ "路由错" → ip route？
  └─ "VPN 错" → NMS firewall？
  ↓
[2] 抓现场（30-60 秒）
  ├─ cmd netpolicy list
  ├─ dumpsys netstats
  ├─ ip route
  ├─ iptables -L
  └─ logcat | grep netd
  ↓
[3] 5 分钟定位
  ├─ firewall → cmd netpolicy set
  ├─ bandwidth → cmd netpolicy set
  ├─ 路由 → ip route add/del
  └─ 统计 → cmd netstats reset
  ↓
[4] 出报告（5 分钟）
```

---

## 7. 5 大调优 case

### 7.1 Case 1：禁用后台流量

```bash
# 启用 restrict-background
$ adb shell cmd netpolicy set restrict-background true

# 加白名单
$ adb shell cmd netpolicy set restrict-background-whitelist 10001
# (10001 是关键 app，比如即时通讯)
```

### 7.2 Case 2：禁某 app 联网

```bash
# 禁某 uid
$ adb shell cmd netpolicy set uid-rule 10002 deny
# 10002 不能联网

# 解禁
$ adb shell cmd netpolicy set uid-rule 10002 allow
```

### 7.3 Case 3：限速某 app 流量

```bash
# 限速 1MB/s
$ adb shell cmd netpolicy set interface-quota wlan0 1048576
# wlan0 整体限速 1MB/s
```

### 7.4 Case 4：看每个 app 流量

```bash
# per-uid 流量
$ adb shell dumpsys netstats detail | head -30

# per-iface 流量
$ adb shell dumpsys netstats | head
```

### 7.5 Case 5：禁用 IPv6

```bash
# 禁用 IPv6（IPv4-only 环境）
$ adb shell settings put global ipv6_disabled 1
# app 只能走 IPv4
```

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 网络栈总览](01-网络栈总览：从app-socket到网卡的全链路.md) | 上篇 |
| [04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md) | 上篇 |
| [06 WiFi](06-WiFi协议栈：wpa-supplicant-HAL-连接.md) | 续篇 |
| [07 Mobile Data](07-Mobile-Data：RIL-数据业务-漫游.md) | 续篇 |
| [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md) | 续篇 |
| [06-Foundation/SELinux/04-AVC与avc_denied](../../01-卷1-平台基础与启动/05-安全基础（SELinux%20·%20AVB）/SELinux/04-AVC与avc_denied：从一次denied反推策略.md) | SELinux 视角 |
| [02-Symptom/S09-jank/01-症状机制](../../../02-Symptom/S09-jank/01-症状机制.md) | 卡顿 |

---

## 9. 收官 + 自检

### 9.1 看完本文的自检

- [ ] 能说 netd 4 大子系统（Firewall / Bandwidth / Route / Tether）
- [ ] 能说 NMS 5 大职责
- [ ] 能用 cmd netpolicy 5 秒看防火墙
- [ ] 能区分 iptables vs eBPF
- [ ] 知道 AOSP 17 netd 重大变化
- [ ] 能用 5 大 case 排错
- [ ] 知道 5 大调优 case

### 9.2 收官话

netd/NMS 在网络栈里属于**"策略层"**——管防火墙、限速、路由、计费。

下一步推荐读：
- [06 WiFi](06-WiFi协议栈：wpa-supplicant-HAL-连接.md) — WiFi 协议栈
- [07 Mobile Data](07-Mobile-Data：RIL-数据业务-漫游.md) — Mobile Data
- [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md) — 工具

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
