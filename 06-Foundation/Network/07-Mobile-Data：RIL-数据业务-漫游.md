# 06-Foundation/Network · 07 · Mobile Data：RIL / 数据业务 / 漫游

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · Mobile Data 问题
>
> **强依赖**：[01 网络栈总览](01-网络栈总览：从app-socket到网卡的全链路.md) · [04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md) · [06 WiFi](06-WiFi协议栈：wpa-supplicant-HAL-连接.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 Mobile Data（4G/5G）从 RIL（Radio Interface Layer）→ 数据业务 → 漫游完整讲清楚——oncall 5 秒定位"4G/5G 切不到 / 没流量 / 漫游失败"
- **不是**：不复述 [04 CS 选路](04-ConnectivityService：网络选路-评分-切换.md)（本文深入 Modem 协议）；不复述 [06 WiFi](06-WiFi协议栈：wpa-supplicant-HAL-连接.md)（本文是蜂窝）
- **承接自**：[06 §1.3 Mobile Data NetworkAgent](06-WiFi协议栈：wpa-supplicant-HAL-连接.md) → 本文展开 Modem 协议
- **衔接去**：[05 netd/NMS](05-netd-NetworkManagementService：网络策略.md) / [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章 RIL 架构 + AOSP 17 5G 变化 | 核心 |
| 2 | 第 2 章 5 大数据业务 | 实战相关 |
| 3 | 第 5 章 5 大 case | oncall 用 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**Mobile Data = RIL（Radio Interface Layer）+ 数据业务（LTE/5G NR）+ 漫游——3 大子系统，5G/4G/3G/2G 多代并存。**

AOSP 17 上 phone 进程跑 RIL，Modem 通过 QMI/AT 命令通信。理解 Mobile Data = 5 秒定位"流量切不到 / 漫游失败 / 5G 降级"。

---

## 1. RIL（Radio Interface Layer）架构

### 1.1 4 层架构

```
[app 进程]
   │
   │ 调 TelephonyManager.getDataNetworkType()
   ▼
[TelephonyManager (framework)]
   │
   │ 调 Binder
   ▼
[phone 进程]
   │ /system/bin/phoneserver
   │ frameworks/opt/telephony/
   │
   │ 调 RIL 命令
   ▼
[RIL (Radio Interface Layer)]
   │ RIL.java / RILJ
   │ hardware/ril/
   │
   │ 通过 socket 调 modem
   ▼
[Modem (Baseband)]
   ├─ Qualcomm: QMI / QCRIL
   ├─ MediaTek: RILMD
   └─ Unisoc: rild_ext
```

### 1.2 AOSP 17 Mobile 新变化

| AOSP 版本 | 关键变化 |
|:---------|:-------|
| 7 | RILJ 重构 |
| 10 | Multi-SIM 增强 |
| 12 | 5G NSA / SA 基础 |
| 14 | 5G NR 完整支持 |
| 16 | Network Slicing API |
| **17** | **5G NR + Network Slicing 增强 + Satellite (NTN) 准备** |

**关键洞察**：
- AOSP 17 默认 5G
- Network Slicing（eMBB / URLLC / mMTC）
- 卫星通信 NTN（Non-Terrestrial Network）准备

### 1.3 关键源码

| 路径 | 干什么 |
|:-----|:------|
| `frameworks/opt/telephony/` | Telephony 框架 |
| `frameworks/base/telephony/` | TelephonyManager |
| `hardware/ril/` | RIL 接口 |
| `hardware/interfaces/radio/` | AIDL Radio HAL |
| `packages/modules/Telephony/` | mainline Telephony 模块化 |
| `packages/services/Telephony/` | Telephony 服务 |

### 1.4 4 大 RIL 命令

| 命令 | 干什么 |
|:-----|:-----|
| `RIL_REQUEST_SETUP_DATA_CALL` | 建立数据连接 |
| `RIL_REQUEST_DEACTIVATE_DATA_CALL` | 断开数据连接 |
| `RIL_REQUEST_DATA_REGISTRATION_STATE` | 查询网络注册状态 |
| `RIL_REQUEST_SIGNAL_STRENGTH` | 查询信号强度 |

---

## 2. 5 大数据业务（PS / Packet Switched）

### 2.1 5 大代际

| 代际 | 标准 | 频段 | 速率 | 延迟 |
|:-----|:-----|:-----|:-----|:-----|
| **2G** | GSM / GPRS / EDGE | 900 / 1800 MHz | 0.1 Mbps | 500ms |
| **3G** | UMTS / HSPA / HSPA+ | 850 / 1900 / 2100 MHz | 14 Mbps | 100ms |
| **4G** | LTE / LTE-A | 700-2600 MHz | 1 Gbps | 10ms |
| **5G NSA** | 5G NR (非独立) | Sub-6 / mmWave | 4 Gbps | 1ms |
| **5G SA** | 5G NR (独立) | Sub-6 / mmWave | 10 Gbps | 1ms |

### 2.2 数据业务的 4 大阶段

```
[1] ATTACH
    └─ 设备注册到网络（建立 signaling 通道）

[2] BEARER
    └─ 建立数据承载（default bearer + dedicated bearer）

[3] ACTIVATE
    └─ 激活 PDP context（IP 连接）

[4] TRANSFER
    └─ 实际数据传递
```

### 2.3 5G NR 关键概念

| 概念 | 含义 | 用途 |
|:-----|:-----|:-----|
| **5G NSA** | 5G + 4G 共存 | 早期 5G |
| **5G SA** | 纯 5G | 完整 5G |
| **Sub-6** | 6GHz 以下频段 | 覆盖广 |
| **mmWave** | 24-40 GHz | 高速 |
| **eMBB** | 增强移动宽带 | 高带宽 |
| **URLLC** | 超可靠低延迟 | 自动驾驶 |
| **mMTC** | 大规模机器通信 | IoT |
| **Network Slice** | 网络切片 | 定制服务 |

---

## 3. 4 大 RIL 事件

### 3.1 网络注册

```
phone 进程 (RIL)
   │
   │ RIL_REQUEST_DATA_REGISTRATION_STATE
   ▼
Modem
   │
   │ 通过 NAS 信令发到基站
   ▼
基站
   │
   │ 返回网络状态
   ▼
Modem
   │
   │ RIL_RESPONSE 回到 phone
   ▼
phone 进程
   │
   │ 发广播 TELEPHONY_EVENTS
   ▼
app 收到 NetworkStateChanged
```

### 3.2 信号强度

```
RIL_REQUEST_SIGNAL_STRENGTH → Modem → 返回
   │
   ▼
dumpsys telephony.registry | grep Signal
   │
   ▼
L: 4 (5 个等级: 0=无, 1=弱, 2=中, 3=好, 4=强)
RSRP: -85 dBm
RSRQ: -10 dB
SINR: 5 dB
```

### 3.3 数据连接建立

```
[1] ConnectivityService 调 phone 进程
[2] phone 调 RIL_REQUEST_SETUP_DATA_CALL
[3] RIL 调 Modem（AT 命令 / QMI）
[4] Modem 走 NAS 信令
[5] 基站接受
[6] Modem 返回 IP / DNS / 网关
[7] 设备获得 IP

耗时: 1-5 秒
```

### 3.4 漫游

```
[1] 设备移动到新网络覆盖区
[2] Modem 检测到新 PLMN
[3] 触发 PLMN selection（选网）
[4] 发起 registration
[5] 与新网络建立 NAS 信令
[6] Update Location 更新到 home network
[7] 数据连接恢复

耗时: 2-10 秒
```

---

## 4. 5 大性能指标

| 指标 | 单位 | 健康值 | 测量命令 |
|:-----|:-----|:------|:-------|
| **RSRP** | dBm | > -80 (优) | 信号强度 |
| **RSRQ** | dB | > -10 (优) | 信号质量 |
| **SINR** | dB | > 5 (优) | 信噪比 |
| **Throughput** | Mbps | > 50 | speedtest |
| **Latency** | ms | < 50 | ping |

### 4.1 5 大告警阈值

| 指标 | 阈值 | 含义 |
|:-----|:-----|:-----|
| RSRP | < -110 dBm | 信号弱 |
| RSRQ | < -15 dB | 信号差 |
| SINR | < 0 dB | 高干扰 |
| Throughput | < 1 Mbps | 流量慢 |
| Latency | > 200ms | 延迟高 |

---

## 5. 5 大真实 case

### 5.1 Case 1：4G 切不到 5G

```
[症状] 5G 信号但显示 4G

[Step 1] 看 network type
$ adb shell dumpsys telephony.registry | grep "mDataNetworkType"
# 13 = LTE  (4G)
# 20 = NR  (5G)

[Step 2] 看 5G 配置
$ adb shell settings get global preferred_network_mode
# 9 = NR / LTE / CDMA / EvDo / GSM / WCDMA
# 期望：包含 NR (5G)

[Step 3] 看 5G SA / NSA
$ adb shell settings get global nr_mode
# 0 = off
# 1 = NSA
# 2 = SA
# 3 = both
# 期望：1 或 2

[Step 4] 看 modem
$ adb shell "dumpsys telephony.registry | grep NR"
# mNrState: 0 (not connected)
# 或 3 (connected)

[Step 5] 修法
- 启用 5G：settings put global nr_mode 3
- 重启 Modem：settings put global airplane_mode_on 1 → 0
```

### 5.2 Case 2：漫游失败

```
[症状] 出国后无网络

[Step 1] 看 PLMN
$ adb shell dumpsys telephony.registry | grep "mOperator"
# mOperatorNumeric: 460 (中国) - 还在国内
# 但设备在国外

[Step 2] 看漫游状态
$ adb shell dumpsys telephony.registry | grep "Roaming"
# mDataRoamingEnabled: true
# mVoiceRoamingEnabled: true

[Step 3] 看 PLMN list
$ adb shell "dumpsys phone | grep PLMN"
# PLMN 列表

[Step 4] 手动选网
$ adb shell "dumpsys phone | grep 'selectNetwork'"

[Step 5] 修法
- 改 PLMN 选网优先级
- 联系运营商开通漫游
- 重启设备
```

### 5.3 Case 3：流量被劫持 / 走错 APN

```
[症状] app 上不了网

[Step 1] 看 APN
$ adb shell dumpsys telephony.registry | grep "mApn"
# mApn: cmnet (正确)
# 或 mApn: internet (可能错)

[Step 2] 看 default data
$ adb shell "dumpsys connectivity | grep mobile"

[Step 3] 看网络类型
$ adb shell dumpsys telephony.registry | grep "mDataNetworkType"
# 0 = unknown
# 3 = UMTS (3G)
# 13 = LTE (4G)
# 20 = NR (5G)

[Step 4] 看 active data
$ adb shell "dumpsys phone | grep -i 'active'"

[Step 5] 修法
- 改 APN：cmnet / cmwap / 3gnet
- 重启 radio
```

### 5.4 Case 4：双卡选错

```
[症状] 双卡设备 app 用错 SIM

[Step 1] 看 default data
$ adb shell "dumpsys phone | grep 'DataSub'"
# mDataSubId=1 (SIM 2)
# 期望：0 (SIM 1)

[Step 2] 看 preferred
$ adb shell "dumpsys phone | grep 'preferred'"

[Step 3] 切 preferred data
$ adb shell "cmd phone set-data-sub 0"
# 切到 SIM 1

[Step 4] 验证
$ adb shell "dumpsys phone | grep -i 'data'"

[Step 5] 修法
- set-data-sub 切卡
- 持久：cmd phone set-data-sub-default
```

### 5.5 Case 5：5G 掉到 4G

```
[症状] 5G 连接后掉到 4G

[Step 1] 看 NR state
$ adb shell dumpsys telephony.registry | grep "NrState"
# mNrState: 0 / 1 / 2 / 3

[Step 2] 看 5G 设置
$ adb shell settings get global nr_advanced
# 期望：true

[Step 3] 看 4G 锚点
$ adb shell "dumpsys phone | grep -i 'anchored'"

[Step 4] 看信号
$ adb shell dumpsys telephony.registry | grep "RSRP"
# 5G 信号弱 → 切 4G

[Step 5] 修法
- 启用 nr_advanced
- 启用 NSA 锚点
- 信号好时自动回 5G
```

---

## 6. 5 大调优 case

### 6.1 Case 1：禁用 5G 优先 4G（省电）

```bash
# 禁用 5G（用 4G）
$ adb shell settings put global preferred_network_mode 9
# 9 = NR / LTE / CDMA / EvDo / GSM / WCDMA
# 7 = LTE / CDMA / EvDo / GSM / WCDMA (no 5G)

# 7 是只 4G
```

### 6.2 Case 2：禁用数据（飞行模式）

```bash
# 飞行模式
$ adb shell settings put global airplane_mode_on 1
# 关闭飞行模式
$ adb shell settings put global airplane_mode_on 0
```

### 6.3 Case 3：禁用 Mobile Data

```bash
# 禁用数据
$ adb shell cmd connectivity set-mobile-data-enabled false
# 启用
$ adb shell cmd connectivity set-mobile-data-enabled true
```

### 6.4 Case 4：APN 设置

```bash
# 改 APN
$ adb shell content insert --uri content://telephony/carriers --bind name:s:cmnet
# 或用 am start -a android.settings.APN_SETTINGS
```

### 6.5 Case 5：禁用漫游

```bash
# 禁用数据漫游
$ adb shell settings put global data_roaming 0
# 启用
$ adb shell settings put global data_roaming 1
```

---

## 7. oncall 5 分钟决策

```
[问题] Mobile Data 相关
  ↓
[1] 30 秒判断（5 秒）
  ├─ "4G/5G 切不到" → 看 preferred_network_mode
  ├─ "漫游失败" → 看 PLMN + data_roaming
  ├─ "流量被劫持" → 看 APN
  ├─ "双卡选错" → 看 data sub
  └─ "5G 掉 4G" → 看 NR state + 信号
  ↓
[2] 抓现场（30-60 秒）
  ├─ dumpsys telephony.registry
  ├─ dumpsys phone
  ├─ dumpsys connectivity
  └─ logcat -b system | grep RIL
  ↓
[3] 5 分钟定位
  ├─ 切不到 → settings put global preferred_network_mode
  ├─ 漫游 → settings put global data_roaming 1
  ├─ APN 错 → 改 APN
  ├─ 双卡 → cmd phone set-data-sub
  └─ 5G 掉 → 启用 nr_advanced
  ↓
[4] 出报告（5 分钟）
```

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 网络栈总览](01-网络栈总览：从app-socket到网卡的全链路.md) | 上篇 |
| [04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md) | 上篇 |
| [05 netd/NMS](05-netd-NetworkManagementService：网络策略.md) | 续篇 |
| [06 WiFi](06-WiFi协议栈：wpa-supplicant-HAL-连接.md) | 续篇 |
| [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md) | 续篇 |

---

## 9. 收官 + 自检

### 9.1 看完本文的自检

- [ ] 能说 RIL 4 层架构
- [ ] 能说 5 大代际（2G/3G/4G/5G NSA/SA）
- [ ] 能用 dumpsys telephony.registry 5 秒看状态
- [ ] 能区分 RSRP / RSRQ / SINR
- [ ] 知道 AOSP 17 5G / NTN 准备
- [ ] 能用 5 大 case 排错
- [ ] 知道 5 大调优 case

### 9.2 收官话

Mobile Data 在网络栈里属于**"蜂窝链路"**——RIL + Modem + NAS 信令 + 漫游。

下一步推荐读：
- [08 诊断工具](08-网络栈诊断工具：tcpdump-ss-netstat-ping.md) — 工具
- [05 netd/NMS](05-netd-NetworkManagementService：网络策略.md) — 网络策略回看
- [04 ConnectivityService](04-ConnectivityService：网络选路-评分-切换.md) — 选路回看

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
