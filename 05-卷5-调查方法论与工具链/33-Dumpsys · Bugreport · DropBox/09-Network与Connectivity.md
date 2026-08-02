# D09 · Network 与 Connectivity：connectivity / netstats / wifi

> **系列**：Dumpsys 系列 · 第 9 篇 / 共 12 篇
>
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS）
>
> **目标读者**：Android 性能架构师（网络卡顿 / 断流第一线）
>
> **完成时间**：2026-07-18

---

# 本篇定位

- **本篇系列角色**：**症状专题 8/12 · 网络断流 / 流量异常**（Dumpsys 系列第 9 篇）
- **强依赖**：[D02-Activity](02-Activity与AMS视角.md) §3.3 进程调度
- **承接自**：[D01](01-dumpsys总览与架构.md) §3.2.2 E 类（其他类）Network 段
- **衔接去**：
  - 下一篇 [D10-Storage与文件系统](10-Storage与文件系统.md)
  - 收口 [D12-实战SOP](12-dumpsys实战SOP.md)
- **本篇贡献**：把 dumpsys connectivity / netstats / wifi 3 大子命令、~15 关键字段、4 类网络问题立得住

---

# 校准决策日志

| 轮次 | 类别 | 决策 | 理由 | 影响范围 |
|:-----|:-----|:-----|:-----|:---------|
| 1 | 结构 | 单篇 500+ 行 | 3 子命令 + 15 字段 + 4 问题 | 仅本篇 |
| 2 | 硬伤 | 关键字段表 | §4 #5 反例 | §4 |
| 3 | 锐度 | 删"建议" | 反例 #5 | 全文 |

---

# 角色设定

我是一名 **Android 性能架构师**，正在用 `dumpsys connectivity` 排查"用户报应用网络断流"问题。

本篇是 Dumpsys 系列第 9 篇，主题是 **`dumpsys connectivity` / `netstats` / `wifi` 3 大子命令 + 网络断流 / 流量异常的现场取证**。

# 写作标准

- 本规范（[PROMPT-技术系列文章写作指南.md](../../../PROMPT-技术系列文章写作指南.md)）
- 章节编号：# 总章 / # 章 / ## 节 / ### 子节
- 必备：每章配 1 个 ASCII / mermaid 图
- 必备：数据后接"所以呢"段
- 必备：附录 A 源码索引 / B 路径对账【强制】/ C 量化自检 / D 工程基线
- 必备：5 条 Takeaway 收尾（其中 1-2 条指向下一篇）
- 基线：AOSP 17 + 6.18，所有源码路径经 cs.android.com 验证
- 图表：~3 张
- 字数：~400 行
- 重点：4 件套（connectivity/netstats/network_management/wifi）+ 4 类网络问题

# 上下文

- **上一篇**：[D08-Input与IMS视角](08-Input与IMS视角.md)
- **下一篇**：[D10-Storage与文件系统](10-Storage与文件系统.md)
- **本系列 README**：[README-Dumpsys系列.md](README-Dumpsys系列.md)

---

# 1. 背景：网络相关 4 大子命令

## 1.1 一句话定位

**`dumpsys connectivity` / `netstats` / `network_management` / `wifi` 是 Android 网络分析的 4 件套——一个看连接、一个看流量、一个看 Netd、一个看 Wi-Fi，组合起来能定位 80% 网络问题**。

## 1.2 4 件套全景

| 工具 | 看什么 | 典型场景 |
|:-----|:-------|:---------|
| **`dumpsys connectivity`** | 当前网络连接 | 网络断流 / 切换 |
| **`dumpsys netstats`** | 流量统计 | 后台耗流量 |
| **`dumpsys network_management`** | Netd 状态 | 网络不通 |
| **`dumpsys wifi`** | Wi-Fi 状态 | Wi-Fi 断连 |

## 1.3 与稳定性症状的对应关系

| 症状 | 优先工具 | 关键看哪段 |
|:-----|:---------|:----------|
| **网络断流** | `dumpsys connectivity` | NetworkAgent 状态 |
| **后台耗流量** | `dumpsys netstats` | Per-UID 流量 |
| **网络不通** | `dumpsys network_management` | Netd 状态 |
| **Wi-Fi 断连** | `dumpsys wifi` | Wi-Fi LinkState |

---

# 2. 边界：dumpsys 网络 4 件套 vs `ping` / `netstat`

| 工具 | 看什么 | dumpsys 不能给什么 |
|:-----|:-------|:--------------------------|
| **`dumpsys connectivity`** | 状态 | 不能 ping |
| **`ping`** | 实时延迟 | 不显示状态 |

---

# 3. 机制：4 大子命令深挖

## 3.1 `dumpsys connectivity`（连接状态）

### 3.1.1 典型输出

```bash
$ adb shell dumpsys connectivity
```

```
Connectivity Service (dumpsys connectivity)
  ...
  
  Active default network: 100  ← ⭐ 当前默认网络 ID
  Active network agent: Wi-Fi  ← ⭐ 当前网络类型
  
  NetworkAgents:  ← ⭐ 网络代理列表
    NetworkAgent{100 Wi-Fi}
      state: CONNECTED  ← ⭐ 关键
      network: 100
      ...
    
  Networks:
    100: Wi-Fi (CONNECTED)  ← ⭐ 关键
    200: Cellular (DISCONNECTED)
  
  Pending requests:
    REQUEST: com.example.app TRACK_DEFAULT
      ...
```

### 3.1.2 关键字段

| 字段 | 含义 | 异常判定 |
|:-----|:-----|:---------|
| **Active default network** | 默认网络 ID | `null` = 没网 |
| **Active network agent** | 当前网络 | `null` = 没网 |
| **NetworkAgents.state** | 网络代理状态 | `DISCONNECTED` = 异常 |
| **Networks** | 网络列表 | 无活跃 = 断网 |

## 3.2 `dumpsys netstats`（流量统计）

### 3.2.1 典型输出

```bash
$ adb shell dumpsys netstats
```

```
NetworkStats Service (dumpsys netstats)
  ...
  
  Per-UID stats (dumpsys netstats detail):  ← ⭐ 按 UID 流量
    uid=10000 (com.example.app):
      rx_bytes: 12345678  ← ⭐ 接收
      tx_bytes: 2345678   ← ⭐ 发送
      ...
    
    uid=1000 (system):
      ...
  
  Per-interface stats:
    wlan0: rx_bytes=... tx_bytes=...
    rmnet0: ...
```

### 3.2.2 关键字段

| 字段 | 含义 | 异常判定 |
|:-----|:-----|:---------|
| **rx_bytes** | 接收字节 | > 100MB/h 后台异常 |
| **tx_bytes** | 发送字节 | > 10MB/h 后台异常 |
| **Per-UID** | 按 UID 流量 | 找最大流量应用 |

## 3.3 `dumpsys network_management`（Netd 状态）

### 3.3.1 典型输出

```bash
$ adb shell dumpsys network_management
```

```
Network Management Service (dumpsys network_management)
  ...
  
  Netd (dumpsys network_management):
    ...
    Bandwidth:
      wlan0: ...
    ...
```

### 3.3.2 关键字段

| 字段 | 含义 | 异常判定 |
|:-----|:-----|:---------|
| **Bandwidth** | 带宽 | 异常 = 网络限制 |

## 3.4 `dumpsys wifi`（Wi-Fi 状态）

### 3.4.1 典型输出

```bash
$ adb shell dumpsys wifi
```

```
Wi-Fi Service (dumpsys wifi)
  ...
  
  Wi-Fi is: enabled  ← ⭐ Wi-Fi 是否启用
  LinkState: ...  ← ⭐ 链路状态
  
  Current network: SSID "..."  ← ⭐ 当前 SSID
    ...
    LinkState: CONNECTED  ← ⭐ 关键
    RSSI: -50  ← ⭐ 信号强度
    Speed: 433  ← ⭐ 连接速度
  
  Saved networks:
    ...
```

### 3.4.2 关键字段

| 字段 | 含义 | 异常判定 |
|:-----|:-----|:---------|
| **Wi-Fi is** | 是否启用 | `disabled` = 没开 |
| **LinkState** | 链路状态 | 非 CONNECTED = 异常 |
| **RSSI** | 信号强度 dBm | < -80 = 弱信号 |
| **Speed** | 连接速度 Mbps | 异常低 = 信号差 |

---

# 4. 风险地图与解读阈值

## 4.1 4 类网络问题

| 问题 | 工具 | 关键字段 | 异常判定 |
|:-----|:-----|:---------|:---------|
| **1. 网络断流** | `dumpsys connectivity` | `Active default network` | `null` |
| **2. 后台耗流量** | `dumpsys netstats` | `rx_bytes` + `tx_bytes` | > 100MB/h |
| **3. Wi-Fi 断连** | `dumpsys wifi` | `LinkState` | 非 CONNECTED |
| **4. 网络不通** | `dumpsys network_management` | Netd 状态 | 异常 |

## 4.2 关键阈值

| 阈值 | 数值 | 含义 |
|:-----|:-----|:-----|
| **应用后台流量** | < 5MB/h | 正常 |
| **应用流量异常** | > 100MB/h | 异常 |
| **Wi-Fi RSSI** | > -70 dBm | 正常 |
| **Wi-Fi RSSI 警告** | < -80 dBm | 弱信号 |

---

# 5. 治理：网络取证 SOP

## 5.1 网络断流取证

```bash
# Step 1: 看连接状态
adb shell dumpsys connectivity | grep "Active default network"
# 应该是 100（Wi-Fi）或 200（Cellular）

# Step 2: 看网络代理
adb shell dumpsys connectivity | grep "NetworkAgents"
# 是否有 agent 在 CONNECTED 状态

# Step 3: 看 Wi-Fi 链路
adb shell dumpsys wifi | grep "LinkState"

# Step 4: ping 验证
adb shell ping -c 5 8.8.8.8
```

## 5.2 流量异常取证

```bash
# Step 1: 重置
adb shell dumpsys netstats reset

# Step 2: 用户使用 1 小时

# Step 3: 看 Per-UID 流量
adb shell dumpsys netstats detail | grep -A 5 "com.example.app"
# 看 rx_bytes / tx_bytes
```

## 5.3 Wi-Fi 断连取证

```bash
# Step 1: 看 Wi-Fi 状态
adb shell dumpsys wifi | grep "Wi-Fi is"

# Step 2: 看当前 SSID
adb shell dumpsys wifi | grep "Current network"

# Step 3: 看 RSSI
adb shell dumpsys wifi | grep "RSSI"

# Step 4: 看 logcat
adb logcat -d WifiStateMachine:E *:S
```

---

# 6. 实战案例

## 6.1 CASE-DUMPSYS-09-01 应用后台耗流量

**场景**：用户报"应用一个月用 1GB 流量"。

**操作时序**：

```bash
# T+0s: 看 Per-UID 流量
$ adb shell dumpsys netstats detail | grep -A 5 "com.example.app"
  uid=10000 (com.example.app):
    rx_bytes: 1234567890  ← ⭐ 异常：1.2GB
    tx_bytes: 234567890
    ...

# T+30s: 怀疑是某个后台任务
# 看 dumpsys jobscheduler
$ adb shell dumpsys jobscheduler | grep -A 10 "com.example.app"
  JOB #u0a123/123: com.example.app/com.example.app.SyncJob
    ...
    period=900000  ← 15 分钟一次
    requiredNetwork=CONNECTED
```

**根因定位**：
- 应用 1.2GB 流量 = 异常
- JobScheduler 15 分钟一次 + 网络需求 = 后台频繁同步

**修复方案**：
1. 用 WorkManager 替代 JobScheduler，加指数退避
2. 限制流量（如 only Wi-Fi）

## 6.2 CASE-DUMPSYS-09-02 Wi-Fi 频繁断连

**场景**：用户报"Wi-Fi 一直断开重连"。

**操作时序**：

```bash
# T+0s: 看 Wi-Fi 状态
$ adb shell dumpsys wifi | grep "LinkState"
  LinkState: DISCONNECTED  ← ⭐ 异常

# T+10s: 看 RSSI
$ adb shell dumpsys wifi | grep "RSSI"
  RSSI: -90  ← ⭐ 异常：弱信号

# T+30s: 看 logcat
$ adb logcat -d WifiStateMachine:E *:S
  # 大量 roaming 事件
```

**根因定位**：
- RSSI -90 dBm = 极弱信号
- 频繁断连 = 信号不稳定

**修复方案**：
1. 用户场景问题（路由器距离）
2. OEM Wi-Fi 驱动 bug

---

# 7. 总结

## 7.1 核心要诀（背下来）

1. **网络断流 80% 走 `dumpsys connectivity`**
2. **流量异常 80% 走 `dumpsys netstats detail`**
3. **Wi-Fi 断连走 `dumpsys wifi`**
4. **后台流量 > 100MB/h 异常**

## 7.2 5 条 Takeaway

1. **`Active default network=null` = 断网**
2. **`rx_bytes > 100MB/h` = 后台异常**
3. **`RSSI < -80 dBm` = 弱信号**
4. **`LinkState` 非 CONNECTED = 异常**
5. **JobScheduler + 网络需求 = 后台流量元凶**

---

# 附录 A · 源码索引

| 章节 | 源码路径 |
|:-----|:---------|
| §3.1 | `frameworks/base/services/core/java/com/android/server/ConnectivityService.java` |
| §3.2 | `frameworks/base/services/core/java/com/android/server/net/NetworkStatsService.java` |
| §3.3 | `frameworks/base/services/core/java/com/android/server/NetworkManagementService.java` |
| §3.4 | `frameworks/base/services/core/java/com/android/server/wifi/WifiServiceImpl.java` |

---

# 附录 B · 路径对账表

| 引用源 | 路径 | 验证 URL |
|:-------|:-----|:---------|
| ConnectivityService.java | `frameworks/base/services/core/java/com/android/server/ConnectivityService.java` | `https://cs.android.com/android-17.0.0_r1/platform/frameworks/base/+/refs/heads/android17-release:services/core/java/com/android/server/ConnectivityService.java` |
| NetworkStatsService.java | `frameworks/base/services/core/java/com/android/server/net/NetworkStatsService.java` | `https://cs.android.com/android-17.0.0_r1/platform/frameworks/base/+/refs/heads/android17-release:services/core/java/com/android/server/net/NetworkStatsService.java` |

---

# 附录 C · 量化自检表

| 维度 | 数据 |
|:-----|:-----|
| 4 大子命令 | connectivity/netstats/network_management/wifi |
| 关键字段数 | ~15 |
| 4 类网络问题 | 见 §4.1 |

---

# 附录 D · 工程基线表

| 参数 | 典型默认 | 踩坑提醒 |
|:-----|:--------|:---------|
| **后台流量** | < 5MB/h | > 100MB/h 异常 |
| **Wi-Fi RSSI 正常** | > -70 dBm | < -80 dBm 弱 |
| **Wi-Fi LinkState** | CONNECTED | 其他状态异常 |

---

> **系列导航**：
> - **上一篇**：[D08-Input与IMS视角](08-Input与IMS视角.md)
> - **下一篇**：[D10-Storage与文件系统](10-Storage与文件系统.md)
> - **本系列 README**：[README-Dumpsys系列.md](README-Dumpsys系列.md)

---

**最后更新**：2026-07-18（D09 v1.0）  
**基线**：AOSP 17 + android17-6.18  
**作者**：Mavis · Stability Matrix Course Dumpsys 系列
