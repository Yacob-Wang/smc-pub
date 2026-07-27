# 06-Foundation/Network · 04 · ConnectivityService：网络选路 / 评分 / 切换

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 网络切换问题
>
> **强依赖**：[01 网络栈总览](01-网络栈总览：从app-socket到网卡的全链路.md) · [06 WiFi](06-WiFi协议栈：wpa-supplicant-HAL-连接.md) · [07 Mobile Data](07-Mobile-Data：RIL-数据业务-漫游.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 ConnectivityService 怎么在 WiFi / Mobile / Ethernet / VPN 多个网络间"选路 / 评分 / 切换"讲清楚——oncall 5 秒定位"为什么 app 用了错的网络"
- **不是**：不复述 [06 WiFi](06-WiFi协议栈：wpa-supplicant-HAL-连接.md) / [07 Mobile Data](07-Mobile-Data：RIL-数据业务-漫游.md)（本文是上层"选路"层）；不复述 [05 netd/NMS](05-netd-NetworkManagementService：网络策略.md)（本文偏 java framework 层）
- **承接自**：[03 DNS / DHCP](03-DNS-DHCP：从解析到连接的5秒流程.md) 5 秒流程 → 本文讲"5 秒里第 0 秒选哪张网卡"
- **衔接去**：[05 netd/NMS](05-netd-NetworkManagementService：网络策略.md) / [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md) / [02-Symptom/S09-jank/01-症状机制](../../../02-Symptom/S09-jank/01-症状机制.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 3 章用 NetworkScore 评分表 | 选路核心 |
| 2 | 第 4 章 6 大 NetworkCapability | capability 视角 |
| 3 | 第 5 章 5 个真实切换 case | oncall 实战 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**ConnectivityService = Android 的"网络选路大脑"——同时有 WiFi / Mobile / Ethernet / VPN 时，CS 决定"app 该走哪张网卡"。**

AOSP 17 上 CS 跑在 system_server，每秒处理 100+ 网络状态变化。理解 CS = 5 秒定位"app 用错网络"或"WiFi/Mobile 切换慢"。

---

## 1. ConnectivityService 是什么

### 1.1 一句话定义

**ConnectivityService = system_server 内的"网络选路"服务——管理 5+ 网络 agent、评分、切换、限速。**

### 1.2 CS 在网络栈的位置

```
[app 进程]
   │
   │ 调 ConnectivityManager.requestNetwork()
   ▼
[ConnectivityService (system_server)]
   │
   │ 协调 NetworkAgent 列表
   │ 评分 / 选路
   ▼
[NetworkAgent list]
   ├─ WiFi NetworkAgent
   ├─ Mobile NetworkAgent
   ├─ Ethernet NetworkAgent
   ├─ VPN NetworkAgent
   └─ ...
   │
   │ 调 NMS / netd
   ▼
[netd (native)]
   │ iptables / 路由
   ▼
[Kernel]
```

### 1.3 CS 核心 4 大职责

| 职责 | 干什么 | 关键类 |
|:-----|:-----|:------|
| **网络管理** | 维护 NetworkAgent 列表 | `ConnectivityService.java` |
| **评分** | 哪个网络"更好" | `NetworkScore.java` |
| **选路** | app 走哪张网卡 | `Vpn.java`、`NetworkAgentInfo.java` |
| **能力** | 这个网络支持什么 capability | `NetworkCapabilities.java` |

---

## 2. 5 大 NetworkAgent

### 2.1 NetworkAgent 是什么

**NetworkAgent = 某个网络接口的代表（WiFi/Mobile/Ethernet/VPN），CS 管理的"棋子"。**

### 2.2 5 大 NetworkAgent 详解

| Agent | 进程 | 创建时机 | 能力 |
|:------|:-----|:--------|:----|
| **WiFi** | wpa_supplicant (native) | WiFi 开启 | INTERNET / NOT_METERED |
| **Mobile** | phone 进程 | SIM 卡激活 | INTERNET / METERED |
| **Ethernet** | system_server | 网线插入 | INTERNET / NOT_METERED |
| **VPN** | system_server | VPN 启动 | INTERNET / NOT_VPN |
| **WiFi P2P** | wpa_supplicant | P2P 启动 | LOCAL_ONLY |

### 2.3 NetworkAgent 生命周期

```
[1] NetworkAgent 被创建（NetworkFactory 启动时）
[2] NetworkAgent 注册到 CS（registerNetworkAgent）
[3] CS 给 NetworkAgent 打分（基于 signal / score）
[4] CS 选最佳网络（highest score）
[5] app 注册 NetworkRequest → 拿到 Network
[6] 网络变化时 CS 通知 app（callback）
```

### 2.4 真实 dumpsys 输出

```bash
$ adb shell dumpsys connectivity | head -100

NetworkAgentInfo:
  ┌─ WiFi NetworkAgent (wlan0)
  │   state: CONNECTED
  │   score: 60
  │   capabilities: INTERNET, NOT_METERED, TRUSTED, NOT_VPN
  │   linkProperties: 192.168.1.100/24, gateway 192.168.1.1
  │   dns: 8.8.8.8, 1.1.1.1
  │
  └─ Mobile NetworkAgent (rmnet_data0)
      state: CONNECTED
      score: 50
      capabilities: INTERNET, METERED, TRUSTED, NOT_VPN
      linkProperties: 10.0.0.5/24, gateway 10.0.0.1
      dns: 8.8.8.8

Active default network: WiFi (wlan0)
```

---

## 3. 评分机制（NetworkScore）

### 3.1 评分公式

```java
// NetworkScore.java (framework)
public class NetworkScore {
    public int score;          // 0-100 基础分
    public int policy;         // POLICY_* 常量
    public int legacyScore;    // 旧分（兼容）
}
```

### 3.2 5 大常见分数

| 网络 | 默认分 | 含义 |
|:-----|:------|:-----|
| **Ethernet** | 70 | 有线（最可靠）|
| **WiFi** | 60 | WiFi 强信号 |
| **WiFi (弱)** | 30 | WiFi 信号差 |
| **Mobile (4G/5G)** | 50 | 蜂窝 |
| **VPN** | -1 | 不参与评分 |

### 3.3 评分调整规则

```java
// ConnectivityService.java
int score = NetworkScore.INVALID;
if (network.hasTransport(TRANSPORT_WIFI)) {
    score = 60 - wifiRssi;  // RSSI 越低分越低
} else if (network.hasTransport(TRANSPORT_CELLULAR)) {
    score = 50;
} else if (network.hasTransport(TRANSPORT_ETHERNET)) {
    score = 70;
}
```

### 3.4 5 大评分场景

| 场景 | CS 决策 | 5 秒诊断 |
|:-----|:--------|:--------|
| **WiFi 满信号** | WiFi 60 > Mobile 50 | 选 WiFi |
| **WiFi 弱信号** | WiFi 30 < Mobile 50 | 选 Mobile |
| **WiFi 满信号但 VPN 启用** | WiFi 60 但 VPN 包裹 | 走 VPN |
| **WiFi + Mobile 同时** | WiFi 60 > Mobile 50 | 选 WiFi |
| **飞行模式** | 全部 INVALID | 选无 |

---

## 4. 6 大 NetworkCapability

### 4.1 NetworkCapability 是什么

**NetworkCapability = 这个网络能"干什么"（INTERNET / METERED / NOT_VPN / ...）。app 可按 capability 选网络。**

### 4.2 6 大常见 capability

| Capability | 含义 | 何时用 |
|:----------|:-----|:------|
| **INTERNET** | 有网络（核心）| 几乎所有 |
| **METERED** | 流量计费 | Mobile Data |
| **NOT_METERED** | 不计费 | WiFi / Ethernet |
| **TRUSTED** | 系统信任 | 多数网络 |
| **NOT_VPN** | 不是 VPN | 默认 |
| **VALIDATED** | 验证过（captive portal 测过）| 已通过登录 |

### 4.3 app 怎么用 capability

```java
NetworkRequest req = new NetworkRequest.Builder()
    .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    .addCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)  // 不要流量
    .build();
cm.requestNetwork(req, callback);
```

**关键**：
- app 想要"非计费网络" → WiFi 优先
- app 想要"低延迟" → 选 Ethernet
- app 想要"VPN 流量" → 选 VPN

### 4.4 5 大 capability 异常场景

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **app 一直用 Mobile** | WiFi 缺 NOT_METERED | 查 WiFi capability |
| **VPN 后断网** | app 强制要求 NOT_VPN | 查 app 代码 |
| **不连 WiFi 提示** | 缺 VALIDATED | captive portal |
| **流量大** | 选 METERED 网络 | NetworkStatsService |
| **网络慢** | 低分数网络 | 查 score |

---

## 5. 5 个真实切换场景

### 5.1 场景 1：WiFi 切 Mobile 慢

```
[症状] 关 WiFi 后 5 秒才切到 Mobile

[Step 1] 看 CS 状态
$ adb shell dumpsys connectivity | grep "NetworkAgentInfo"
# WiFi: CONNECTED
# Mobile: CONNECTED

[Step 2] 看 active network
$ adb shell dumpsys connectivity | grep "Active"
# Active: WiFi (wlan0)
# 关 WiFi 后

[Step 3] 看 logcat
$ adb shell "logcat -d -b system | grep -E 'ConnectivityService|Mobile'"
# ConnectivityService: Mobile becoming the default

[Step 4] 测时间
$ adb shell svc wifi disable
$ time adb shell ping -c 1 8.8.8.8
# 实际 5 秒

[Step 5] 结论：CS 切换慢

[修法]
- 调 networkScore 低 Mobile 阈值
- 启用 Mobile Data Always
```

### 5.2 场景 2：VPN 启用后 app 选错网络

```
[症状] VPN 启用后 app 仍用直连网络

[Step 1] 看 VPN
$ adb shell dumpsys connectivity | grep -A5 "VPN"
# VPN NetworkAgent: connected
# capabilities: INTERNET, TRUSTED, NOT_VPN  ← 重要

[Step 2] 看 app 用的网络
$ adb shell "dumpsys netstats | head -50"
# 看 app 是否走 VPN

[Step 3] 看 app 的 NetworkRequest
# app 可能强制 NOT_VPN
# → app 走直连，绕过 VPN

[Step 4] 看 logcat
$ adb shell "logcat -d -b system | grep -E 'VPN|underly'"
# 关键：underlyNetworks (app bypass VPN)

[Step 5] 结论：app 强制 NOT_VPN

[修法]
- 修 app（去掉 NOT_VPN 要求）
- 改 VPN 配置
```

### 5.3 场景 3：captive portal 失败

```
[症状] 连 WiFi 后弹"需要登录"

[Step 1] 看 network state
$ adb shell dumpsys connectivity | grep "VALIDATED"
# 看哪个 network 标 NOT_VALIDATED

[Step 2] 看 captive portal server
$ adb shell settings get global captive_portal_server
# connectivitycheck.gstatic.com

[Step 3] 测试
$ adb shell "curl -I http://connectivitycheck.gstatic.com/generate_204"
# 期望 204
# 如果不是 → captive portal 拦截

[Step 4] 跳过 captive portal 检测（debug）
$ adb shell settings put global captive_portal_mode 0

[Step 5] 结论：captive portal 检测失败
```

### 5.4 场景 4：双卡选错

```
[症状] 双卡设备 app 用错 SIM 卡

[Step 1] 看当前 default data
$ adb shell dumpsys telephony.registry | grep "DataSub"
# mDataSubId=1 (SIM 2)

[Step 2] 看 preferred data
$ adb shell "dumpsys phone | grep -i 'preferred'"
# preferred: 1 (SIM 1)

[Step 3] 切 preferred
$ adb shell "cmd phone set-data-sub 0"
# (SIM 1)

[Step 4] 看 NetworkAgent
$ adb shell "dumpsys connectivity | grep -i 'subId'"

[Step 5] 结论：CS 选错卡
```

### 5.5 场景 5：网络断后不自动重连

```
[症状] 网络断后 app 不自动恢复

[Step 1] 看 NetworkRequest
$ adb shell "dumpsys connectivity | grep -A5 'Request'"
# 看 app 注册的 NetworkRequest

[Step 2] 看 NetworkCallback
$ adb shell "dumpsys connectivity | grep -A5 'Callback'"
# 看 app 的 callback

[Step 3] 看 reconnect 行为
$ adb shell "dumpsys connectivity | grep 'reconnect'"

[Step 4] 测
$ adb shell svc wifi disable
$ adb shell svc wifi enable
# app 应自动重连

[Step 5] 结论：app 错过 reconnect 事件

[修法]
- app 代码要处理 onAvailable / onLost
- 加 retry
```

---

## 6. oncall 5 分钟决策

```
[问题] 网络相关（CS 视角）
  ↓
[1] 30 秒判断（5 秒）
  ├─ "app 走错网络" → 看 NetworkAgentInfo
  ├─ "切换慢" → 看 active network
  ├─ "VPN 后断" → 看 underlyNetworks
  ├─ "WiFi 弹出登录" → 看 VALIDATED
  └─ "双卡选错" → 看 data sub
  ↓
[2] 抓现场（30-60 秒）
  ├─ dumpsys connectivity
  ├─ dumpsys wifi
  ├─ dumpsys telephony.registry
  └─ logcat -b system | grep ConnectivityService
  ↓
[3] 5 分钟定位
  ├─ app 走错网络 → 调 capability 要求
  ├─ 切换慢 → 调 network score 阈值
  ├─ VPN 后断 → 修 app
  └─ captive portal 失败 → 改检测 server
  ↓
[4] 出报告（5 分钟）
```

---

## 7. 5 大调优 case

### 7.1 Case 1：禁用 Mobile Data Always

```bash
# 启用
$ adb shell settings put global mobile_data_always_on 1
# → WiFi 断开时立即切到 Mobile（无 5 秒等待）
```

### 7.2 Case 2：调低 Mobile 阈值

```bash
# Mobile 评分阈值调低（CS 切得更激进）
$ adb shell settings put global network_metered_mobile_threshold 5242880
# 默认 5MB → 5MB
```

### 7.3 Case 3：启用网络切换预测

```bash
# 启用 5G/WiFi 预测
$ adb shell settings put global network_prediction_active 1
# → 提前预判切换，减少卡顿
```

### 7.4 Case 4：禁用双 IMS 切换

```bash
# 禁用双 IMS（避免双卡切换延迟）
$ adb shell settings put global multiple_ims_enabled 0
```

### 7.5 Case 5：调整 captive portal 检测

```bash
# 改 captive portal server
$ adb shell settings put global captive_portal_server "captive.apple.com"
# 改检测 URL
```

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 网络栈总览](01-网络栈总览：从app-socket到网卡的全链路.md) | 上篇 |
| [02 TCP/IP 状态机](02-TCP-IP协议栈：SYN-ACK-FIN-RST状态机.md) | 上篇 |
| [03 DNS/DHCP](03-DNS-DHCP：从解析到连接的5秒流程.md) | 上篇 |
| [05 netd/NMS](05-netd-NetworkManagementService：网络策略.md) | 续篇 |
| [06 WiFi](06-WiFi协议栈：wpa-supplicant-HAL-连接.md) | 续篇 |
| [07 Mobile Data](07-Mobile-Data：RIL-数据业务-漫游.md) | 续篇 |
| [02-Symptom/S09-jank/01-症状机制](../../../02-Symptom/S09-jank/01-症状机制.md) | 卡顿 |
| [03-Forensics/F04-NE/01-取证机制](../../../03-Forensics/F04-NE/01-取证机制.md) | NE 取证 |

---

## 9. 收官 + 自检

### 9.1 看完本文的自检

- [ ] 能说 ConnectivityService 4 大职责
- [ ] 能说 5 大 NetworkAgent + capability
- [ ] 能用 NetworkScore 5 大常见分数
- [ ] 能区分 6 大 NetworkCapability
- [ ] 能用 dumpsys connectivity 5 秒看状态
- [ ] 知道 5 大真实切换场景的修法
- [ ] 能用 5 大调优 case

### 9.2 收官话

ConnectivityService 在网络栈里属于**"选路层"**——4+ 网络并存时，CS 决定"app 走哪张网卡"。

下一步推荐读：
- [05 netd/NMS](05-netd-NetworkManagementService：网络策略.md) — iptables / 路由
- [06 WiFi](06-WiFi协议栈：wpa-supplicant-HAL-连接.md) — WiFi 协议栈
- [07 Mobile Data](07-Mobile-Data：RIL-数据业务-漫游.md) — Mobile Data 协议栈

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
