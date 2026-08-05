# 06-Foundation/Network · 06 · WiFi 协议栈：wpa_supplicant / HAL / 连接

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · WiFi 连接问题
>
> **强依赖**：[01 网络栈总览](01-网络栈总览：从app-socket到网卡的全链路.md) · [04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md) · [03 DNS/DHCP](03-DNS-DHCP：从解析到连接的5秒流程.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 WiFi 协议栈（wpa_supplicant → WiFi HAL → 芯片）从"按 SSID 扫描"到"分配 IP"的完整连接流程讲清楚——oncall 5 秒定位"WiFi 连不上 / 慢 / 断"
- **不是**：不复述 [01 §1.4 WiFi 路径](01-网络栈总览：从app-socket到网卡的全链路.md)（本文是 WiFi 协议栈深入）；不复述 [04 CS 选路](04-ConnectivityService：网络选路-评分-切换.md)（本文偏底层 wpa_supplicant）
- **承接自**：[03 §3 DHCP 4 步](03-DNS-DHCP：从解析到连接的5秒流程.md) → 本文讲"DHCP 之前的 WiFi 连接"
- **衔接去**：[05 netd/NMS](05-netd-NetworkManagementService：网络策略.md) / [07 Mobile Data](07-Mobile-Data：RIL-数据业务-漫游.md) / [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 3 章扫描 + 4 次握手 | WiFi 核心 |
| 2 | 第 4 章 AOSP 17 WiFi 7 / 6E | 最新 |
| 3 | 第 5 章 5 大 case | 实战 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**WiFi 协议栈 = wpa_supplicant（加密认证）+ WiFi HAL（驱动抽象）+ 芯片（射频）——3 层架构，扫描到 IP 分配 5 大阶段。**

AOSP 17 上 wpa_supplicant 跑在 native，WiFi HAL 通过 HIDL/AIDL 跟 driver 通信。理解 WiFi = 5 秒定位"连不上 / 慢 / 断"。

---

## 1. WiFi 协议栈 3 层架构

```
[app 进程]
   │
   │ 调 WifiManager.connect()
   ▼
[WifiService (system_server)]
   │
   │ 调 wifi hal client
   ▼
[wpa_supplicant (native daemon)]
   │ /system/bin/wpa_supplicant
   │ external/wpa_supplicant_8/wpa_supplicant/
   │
   │ 调 WiFi HAL (HIDL/AIDL)
   ▼
[WiFi HAL (HIDL/AIDL)]
   │ hardware/interfaces/wifi/
   │
   │ 调 kernel driver
   ▼
[Kernel WiFi driver]
   │ cfg80211 / mac80211 / ath10k / rtw88
   │
   │ 调硬件
   ▼
[WiFi 芯片]
   ├─ Qualcomm WCN 系列 (QCA6391 / QCA6595)
   ├─ Broadcom BCM 系列
   ├─ MediaTek MT 系列
   └─ ...
```

### 1.1 4 大组件

| 组件 | 进程 | 路径 | 作用 |
|:-----|:-----|:-----|:-----|
| **WifiService** | system_server | `frameworks/base/wifi/java/` | app-facing |
| **wpa_supplicant** | native | `external/wpa_supplicant_8/` | 加密认证 |
| **WiFi HAL** | HIDL/AIDL | `hardware/interfaces/wifi/` | 驱动抽象 |
| **Kernel driver** | kernel | `drivers/net/wireless/` | 硬件控制 |

### 1.2 AOSP 17 WiFi 新变化

| AOSP 版本 | 关键变化 |
|:---------|:-------|
| 8 | HAL 3.0 (HIDL) |
| 12 | WiFi 6 (802.11ax) 默认 |
| 13 | WiFi 6E (6GHz) |
| 14 | WPA3 强制 |
| 15 | AIDL 替代 HIDL |
| 16 | WiFi RTT (FTM) 增强 |
| **17** | **WiFi 7 (802.11be) 默认 + Multi-Link Operation (MLO)** |

**关键洞察**：
- AOSP 17 默认 WiFi 7
- 支持 MLO（同时连接 2.4G / 5G / 6G 频段）
- WPA3 是强制要求

---

## 2. WiFi 5 大阶段（从扫描到 IP）

### 2.1 阶段 1：扫描（Scan）

```
[1] WifiService 收到 app scanNetworks()
[2] WifiService 调 wpa_supplicant SCAN
[3] wpa_supplicant 调 kernel cfg80211
[4] kernel 通过 driver 扫描所有频段
[5] 收到 probe response / beacon
[6] 返回给 WifiService
[7] app 看到 scan result

耗时: 1-3 秒（主动扫描）
      100ms（被动扫描）
```

**关键参数**：
- 频段：2.4G / 5G / 6G
- 信道：2.4G（1-13）/ 5G（36-165）
- 扫描类型：active（发 probe）/ passive（只听）

### 2.2 阶段 2：认证（4 次握手 / SAE）

```
[1] WifiService 收到 connect()，带 SSID + password
[2] WifiService 调 wpa_supplicant (网络添加/设置)
[3] wpa_supplicant 关联（associate）到 AP
[4] 4 次握手（WPA2）或 SAE（WPA3）

[WPA2 4 次握手]
[1] AP → client: ANonce
[2] client → AP: SNonce + MIC
[3] AP → client: GTK + MIC
[4] client → AP: ACK

[WPA3 SAE]
- Simultaneous Authentication of Equals
- 用 Dragonfly 协议防字典攻击
- 替换 WPA2 4 次握手

耗时: 50-200ms
```

### 2.3 阶段 3：DHCP（IP 分配）

```
[1] WifiService 通知 ConnectivityService
[2] CS 触发 netd DHCP 客户端
[3] netd 发 DHCP DISCOVER
[4] DHCP server 分配 IP / DNS / 网关
[5] 设备收到 IP

耗时: 100-500ms
```

### 2.4 阶段 4：连接验证

```
[1] 设备发 ARP 探测
[2] 测试 DNS 解析
[3] 测试 HTTPS 连接（captive portal 检测）

耗时: 1-5 秒
```

### 2.5 阶段 5：通知应用

```
[1] NetworkAgent 状态变 CONNECTED
[2] ConnectivityService 通知所有 callback
[3] app 收到 onAvailable()

耗时: < 1 秒
```

**总耗时**: 3-10 秒

---

## 3. 4 次握手详解（WPA2）

### 3.1 真实 4 步

```
[client]                              [AP]
   |                                    |
   | 1. ANonce (AP nonce)               |
   |<-----------------------------------|
   |                                    |
   | 2. SNonce + MIC                    |
   |----------------------------------->|
   |                                    |
   | 3. GTK (Group Key) + MIC           |
   |<-----------------------------------|
   |                                    |
   | 4. ACK                             |
   |----------------------------------->|
   |                                    |
[连接已建立，client 可发加密数据]
```

### 3.2 关键密钥

| 密钥 | 用途 |
|:-----|:-----|
| **PMK (Pairwise Master Key)** | 来自 password |
| **ANonce / SNonce** | 双方随机数 |
| **PTK (Pairwise Transient Key)** | 临时密钥 |
| **GTK (Group Temporal Key)** | 组播密钥 |
| **MIC (Message Integrity Code)** | 防篡改 |

### 3.3 4 次握手的 4 大异常场景

#### 场景 1：密码错

```
[AP] 不响应或响应错误
[client] 连接超时 / 密码错
```

**修法**：
- 重输密码
- 检查 802.11 标准（WPA2 vs WPA3）

#### 场景 2：信号弱

```
[client] RSSI < -80 dBm
[AP] 收不到 / 频繁掉
```

**修法**：
- 走近 AP
- 换 5G 频段

#### 场景 3：AP 满载

```
[AP] 16 / 32 client 已满
[client] 关联失败
```

**修法**：
- 找别的 AP
- 升级 AP 容量

#### 场景 4：TKIP / CCMP 不匹配

```
[client] WPA2-CCMP
[AP] WPA-TKIP
→ 不兼容
```

**修法**：
- 统一加密方式

---

## 4. 4 大 WiFi 标准

### 4.1 802.11 协议对照表

| 标准 | 年份 | 频段 | 最大速率 | 特点 |
|:-----|:-----|:-----|:--------|:----|
| **802.11n (WiFi 4)** | 2009 | 2.4G / 5G | 600 Mbps | MIMO |
| **802.11ac (WiFi 5)** | 2013 | 5G | 6.9 Gbps | MU-MIMO |
| **802.11ax (WiFi 6)** | 2019 | 2.4G / 5G | 9.6 Gbps | OFDMA |
| **802.11ax (WiFi 6E)** | 2020 | 6G | 9.6 Gbps | 6GHz 频段 |
| **802.11be (WiFi 7)** | 2024 | 2.4G / 5G / 6G | 46 Gbps | MLO + 320MHz |

### 4.2 5 大加密

| 加密 | 强度 | 何时用 | 备注 |
|:-----|:----|:------|:----|
| **WEP** | 弱 | 禁用 | 已破 |
| **WPA** | 弱 | 禁用 | TKIP，已破 |
| **WPA2** | 强 | 主流 | CCMP / AES |
| **WPA3** | 很强 | AOSP 14+ 强制 | SAE / Dragonfly |
| **OWE** | 强 | 公共 WiFi | 无密码 |

### 4.3 6 大 WiFi 加密参数

```bash
# 1. 加密类型
$ adb shell dumpsys wifi | grep "Encryption"
# WPA3-Personal / WPA2-Personal / WPA2-Enterprise

# 2. 密码管理
$ adb shell dumpsys wifi | grep -A2 "password"
# 已保存的密码列表

# 3. 频段
$ adb shell dumpsys wifi | grep -i "frequency\|band"
# 2.4G / 5G / 6G

# 4. 信道
$ adb shell dumpsys wifi | grep -i "channel"

# 5. RSSI（信号强度）
$ adb shell dumpsys wifi | grep "RSSI"
# RSSI: -50 dBm（信号强）
# RSSI: -80 dBm（信号弱）

# 6. 链路速度
$ adb shell dumpsys wifi | grep "Link speed"
# Link speed: 1200 Mbps
```

---

## 5. 5 大真实 case

### 5.1 Case 1：连不上 WiFi

```
[症状] 输入密码后连不上

[Step 1] 看 WiFi 状态
$ adb shell dumpsys wifi | head -50

[Step 2] 看错误
$ adb shell "logcat -d -b system | grep -E 'Wifi|wpa_supplicant' | tail -20"

[Step 3] 看 supplicant 状态
$ adb shell "wpa_cli -i wlan0 status" 2>&1 | head

[Step 4] 常见原因
- 密码错
- 信号弱（RSSI < -80）
- AP 满载
- 加密不兼容

[Step 5] 修法
- 重输密码
- 走近
- 切 5G
- 改 WPA2/3
```

### 5.2 Case 2：WiFi 频繁断

```
[症状] 1 分钟断 1 次

[Step 1] 看 wpa_supplicant 事件
$ adb shell "logcat -d -b system | grep -E 'wpa_supplicant' | tail -50"

# 关键事件：
# - CTRL-EVENT-DISCONNECTED
# - CTRL-EVENT-BEACON-LOSS
# - CTRL-EVENT-SCAN-RESULTS

[Step 2] 看 RSSI
$ adb shell dumpsys wifi | grep RSSI
# -85 dBm（弱）

[Step 3] 看 roaming 状态
$ adb shell "dumpsys wifi | grep -A3 'roam'"
# 期望：roaming enabled

[Step 4] 修法
- 走近 AP
- 启用 roaming
- 调 wpa_supplicant 重连参数
```

### 5.3 Case 3：WiFi 慢

```
[症状] WiFi 已连但慢

[Step 1] 测速
$ adb shell "curl -w 'time:%{time_total}\n' -o /dev/null -s https://www.example.com"
# time:5.000
# 慢

[Step 2] 看 link speed
$ adb shell dumpsys wifi | grep "Link speed"
# 1 Mbps（慢）
# 期望：100+ Mbps

[Step 3] 看 RSSI
$ adb shell dumpsys wifi | grep RSSI
# -70 dBm（中）

[Step 4] 看干扰
$ adb shell dumpsys wifi | grep -i "channel\|frequency"
# 拥挤的信道

[Step 5] 修法
- 切 5G
- 切到空闲信道
- 走近
```

### 5.4 Case 4：captive portal 失败

```
[症状] WiFi 连上但弹"需要登录"

[Step 1] 看 captive portal 检测
$ adb shell settings get global captive_portal_server
# connectivitycheck.gstatic.com

[Step 2] 测
$ adb shell "curl -I http://connectivitycheck.gstatic.com/generate_204"
# 期望 204
# 如果 200/302 → 拦截

[Step 3] 看 network state
$ adb shell dumpsys connectivity | grep "VALIDATED"
# VALIDATED: false  ← captive portal 失败

[Step 4] 跳过检测（debug）
$ adb shell settings put global captive_portal_mode 0

[Step 5] 结论：captive portal 检测
```

### 5.5 Case 5：WiFi 7 不工作

```
[症状] WiFi 7 路由器但设备连不上

[Step 1] 看 WiFi 7 支持
$ adb shell dumpsys wifi | grep "802.11be"
# 支持

[Step 2] 看 MLO（Multi-Link Operation）
$ adb shell dumpsys wifi | grep "MLO"
# 期望 MLO enabled

[Step 3] 看 router
# WiFi 7 路由器开启 6GHz

[Step 4] 看干扰
# 6GHz 干扰小但穿墙差

[Step 5] 修法
- 走近（6GHz 穿墙差）
- 启用 MLO
- 切 5G 备用
```

---

## 6. 5 大调优 case

### 6.1 Case 1：禁用省电模式

```bash
# 关闭 WiFi 省电（耗电但稳）
$ adb shell settings put global wifi_sleep_policy 2
# 0 = 始终
# 1 = 永不禁用
# 2 = 屏幕关时禁用
```

### 6.2 Case 2：禁用 WiFi RTT（省电）

```bash
# 禁用 WiFi RTT（精确定位功能）
$ adb shell settings put global wifi_rtt_enabled 0
# 省电
```

### 6.3 Case 3：禁用 WiFi 扫描

```bash
# 禁用后台 WiFi 扫描
$ adb shell settings put global wifi_scan_always_enabled 0
# 省电
```

### 6.4 Case 4：调整漫游

```bash
# 启用漫游
$ adb shell settings put global wifi_roam_enabled 1

# 漫游阈值（dBm）
$ adb shell settings put global wifi_roam_trigger 5
# RSSI 跌 5dB 触发漫游
```

### 6.5 Case 5：启用 5G 优先

```bash
# WiFi 频段优先级
$ adb shell settings put global wifi_frequency_band 5
# 5G 优先
```

---

## 7. oncall 5 分钟决策

```
[问题] WiFi 相关
  ↓
[1] 30 秒判断（5 秒）
  ├─ "连不上" → 看 dumpsys wifi + logcat
  ├─ "频繁断" → 看 RSSI + roaming
  ├─ "WiFi 慢" → 看 link speed + 干扰
  ├─ "captive portal" → 看检测 URL
  └─ "WiFi 7 异常" → 看 MLO + 6GHz
  ↓
[2] 抓现场（30-60 秒）
  ├─ dumpsys wifi
  ├─ logcat -b system | grep wpa
  ├─ wpa_cli status
  └─ 测 link speed
  ↓
[3] 5 分钟定位
  ├─ 密码错 → 重输
  ├─ 信号弱 → 走近
  ├─ 干扰 → 切信道
  └─ 兼容 → 改加密
  ↓
[4] 出报告（5 分钟）
```

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 网络栈总览](01-网络栈总览：从app-socket到网卡的全链路.md) | 上篇 |
| [03 DNS/DHCP](03-DNS-DHCP：从解析到连接的5秒流程.md) | 上篇 |
| [04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md) | 上篇 |
| [05 netd/NMS](05-netd-NetworkManagementService：网络策略.md) | 续篇 |
| [07 Mobile Data](07-Mobile-Data：RIL-数据业务-漫游.md) | 续篇 |
| [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md) | 续篇 |

---

## 9. 收官 + 自检

### 9.1 看完本文的自检

- [ ] 能说 3 层架构（wpa_supplicant / HAL / driver）
- [ ] 能说 5 大阶段（扫描 / 认证 / DHCP / 验证 / 通知）
- [ ] 能用 dumpsys wifi 5 秒看状态
- [ ] 能说 4 次握手的 4 步 + 4 大异常
- [ ] 知道 802.11 演进（n / ac / ax / be）
- [ ] 知道 5 大加密（WEP / WPA / WPA2 / WPA3 / OWE）
- [ ] 能用 5 大 case 排错

### 9.2 收官话

WiFi 协议栈在网络栈里属于**"链路层"**——物理层 / MAC 层 / 加密 / 漫游。

下一步推荐读：
- [07 Mobile Data](07-Mobile-Data：RIL-数据业务-漫游.md) — Mobile 协议栈
- [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md) — 工具
- [04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md) — 选路回看

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
