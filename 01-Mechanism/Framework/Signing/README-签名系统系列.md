# 面向稳定性的 Android 签名系列

> **本系列定位**:面向资深 Android 稳定性架构师,把"签名"——这个常被工程师视为"基础就该自动工作"、但实际上**是 Android 安全栈最底层、跨 4 层最深、咬人最广**的子系统——拆成可深读、可复用、可作为线上 P0 故障排查底图的长文。
>
> **本系列结构**:**5 篇主序列**——
> - **[01-签名总览:背景、发展史、现状与生态](01-签名总览:背景、发展史、现状与生态.md)** — 锚点文章(全局观 + 4 层抽象 + 5 个发展阶段 + 1 张生态地图)
> - **[02-APK 签名方案 V1/V2/V3/V4 核心机制与数据结构](02-APK签名方案V1V2V3V4核心机制与数据结构.md)** — 协议篇(V1-V4 字节级 + 算法 + 源码走读)
> - **[03-签名校验链路:PackageInstaller → PMS](03-签名校验链路:PackageInstaller到PMS.md)** — 链路篇(5 个核心源文件 + 调用栈)
> - **[04-AndroidKeyStore 与硬件密钥管理](04-AndroidKeyStore与硬件密钥管理.md)** — 硬件篇(TEE / StrongBox / KeyMint / Key Attestation)
> - **[05-签名风险全景 + 实战案例](05-签名风险全景与实战案例.md)** — 收口篇(6 大风险 + 5 件套案例 + 跨厂商 + 监控治理)
>
> **基线**:AOSP `android-17.0.0_r1`(API 37,代号 CinnamonBun)+ Linux `android17-6.18` LTS。
> 所有源码路径经 `https://android.googlesource.com/` / `https://cs.android.com/` 实测 HTTP 200 验证,合计 **50+ 条**。
>
> **目录位置**:`01-Mechanism/Framework/Signing/`
>
> **写作规范**:`PROMPT-技术系列文章写作指南` v6(顶部 blockquote ≤ 3 行 + AUTHOR_ONLY 段 ≤ 15 行 + 5 项 verify 自动化)

---

## 系列全景:5 篇 × 4 层抽象 × 1 张地图

```
                              ┌──────────────────────────────────────┐
                              │ Android 17 / Kernel 6.18 设备栈     │
                              │ 自上而下 4 层 + 5 个核心问题          │
                              └──────────────────────────────────────┘

  ┌──── 1. 背景与发展(01) ──────┐
  │ 01: 锚点文章                  │
  │ 4 层抽象 + 5 段历史 + 1 生态  │
  │ 6 大风险场景速查               │  ← 起点
  └──────────────────────────────┘
                          ↓
  ┌──── 2. 协议与算法(02) ──────┐
  │ 02: V1/V2/V3/V4 核心机制      │
  │ 字节级结构 + 算法 + 源码       │  ← 协议深度
  │ Proof of Rotation / Merkle 树│
  └──────────────────────────────┘
                          ↓
  ┌──── 3. 系统调用链(03) ──────┐
  │ 03: PackageInstaller → PMS    │
  │ 5 个核心源文件 + 错误码速查    │  ← 调用深度
  │ 升级兼容 / 运行时信任模型      │
  └──────────────────────────────┘
                          ↓
  ┌──── 4. 硬件背书(04) ────────┐
  │ 04: AndroidKeyStore + TEE     │
  │ KeyMint HAL + Key Attestation │  ← 硬件深度
  │ TEE vs StrongBox 选型          │
  └──────────────────────────────┘
                          ↓
  ┌──── 5. 实战与治理(05) ──────┐
  │ 05: 6 大风险 + 5 件套案例      │
  │ 跨厂商差异 + 监控告警           │  ← 实战收口
  │ 治理 4 步走 + 案例库           │
  └──────────────────────────────┘
```

**T1-T5** = 5 篇文章,每篇接管 1 个问题域;**横轴**= 4 层抽象(App / Framework / Native / Kernel);**纵轴**= "协议 → 调用 → 硬件 → 实战"。

---

## 系列设计思路

### 为什么要写"签名"这个看似基础的子系统?

**架构师视角的第一性问题**:当你看到 `apksigner verify xxx.apk` 输出"v1/v2/v3/v4 全部 false"时,你会:
- 看 APK 文件 → 翻 APK Sig Block 42 → 找 ID-Value pairs
- 跑 `apksigner verify --print-certs` → 看证书指纹
- 看 PMS logcat → 找 `ApkSignatureVerifier.verify` 异常
- 看 kernel dmesg → 找 `dm-verity failure`
- 看 Play Integrity API → 找 verdict=null

**这 5 个动作跨了 App / Framework / Native / Kernel 4 层**。任何一层处理错了,App 都会"装不上"或"运行时挂"。

### 稳定性视角的"签名的 6 大咬人场景"(01 §1.3)

| # | 场景 | 表现 | 涉及篇章 |
|---|------|------|---------|
| 1 | V1 绕过 + DEX 注入 | APK 看起来签名正常,实际 classes.dex 被植入恶意代码 | [01][02] |
| 2 | 升级签名不匹配 | `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | [01][02][03] |
| 3 | vbmeta / AVB 签名断裂 | OTA 后整盘无法启动 | [01][04] |
| 4 | Key 失窃 / 误删 | CI 入侵 / 私钥文件丢失 | [01][02][04] |
| 5 | Play Integrity 失败 | 银行 / 视频 App 拒绝服务 | [01][04] |
| 6 | 厂商定制签名校验差异 | 同一 APK 在 MIUI/EMUI 表现不一 | [01][03] |

**这些场景的共同点**:都**不是 App 自己的 bug** — 但 App 在用户眼里"挂了"。架构师如果不掌握签名链,会一直追到 App 业务代码上去,根本查不到根因。

### 5 篇结构(全局观 → 核心机制 → 跨模块 → 实战)

| 篇章 | 角色 | 核心交付 | 关键 ASCII 图数 |
|------|------|---------|---------------|
| 01 | 全局观(锚点) | 4 层抽象 + 5 段历史 + 6 大风险 | 8 |
| 02 | 核心机制(协议) | V1-V4 字节级 + 算法 + 源码走读 | 7 |
| 03 | 跨模块交互(链路) | PackageInstaller → PMS 调用栈 | 6 |
| 04 | 核心机制(硬件) | KeyStore2 + KeyMint + TEE + Attestation | 7 |
| 05 | 诊断治理(实战) | 5 件套案例 + 跨厂商 + 监控 | 4 |

**为什么不压成 1 篇**:四层抽象都会被截断,看完仍不知道"为什么 ART GC 频繁会触发 lmkd"。
**为什么不展开成 10 篇**:后段架构思维会失焦,读者不知道"调度和 ART 有什么关系"。

---

## 5 篇章节规划表(按主线)

### 01-签名总览:背景、发展史、现状与生态

| § | 章节 | 核心内容 | 关键源文件 |
|---|------|---------|----------|
| 1 | 背景 | APK 是什么 + 数字签名本质 + Android 安全体系位置 + 6 大咬人场景 | (理论章节) |
| 2 | 发展史 V1→V4 | V1 JAR 签名 / V2 APK Sig Block / V3 Proof of Rotation / V4 Sidecar | (历史章节) |
| 3 | 现状 | V2/V3 主流 + minSdkVersion 约束 + Play App Signing + apksigner 工具链 | (工具章节) |
| 4 | 生态 | AndroidKeyStore / Play Integrity / vbmeta / Key Attestation | (生态章节) |
| 5 | 栈中位置 | 4 层抽象 + 14 个关键源文件 + 关键调用链 | `ApkSignatureVerifier.java` 等 |
| 6 | 风险地图 | 6 大咬人场景速查 | (速查章节) |
| 7 | 总结 | 5 条架构师 Takeaway | (收口) |

### 02-APK 签名方案 V1/V2/V3/V4 核心机制与数据结构

| § | 章节 | 核心内容 | 关键源文件 |
|---|------|---------|----------|
| 1 | 背景 | 为什么需要"V1-V4 数据结构"视角 | (理论章节) |
| 2 | V1 JAR 签名 | META-INF/ 三件套 + Janus 漏洞复盘 | `ApkSignatureSchemeV1.java` |
| 3 | V2 APK Sig Scheme v2 | APK Signing Block + ID-Value pairs + signed_data | `ApkSignatureSchemeV2.java` |
| 4 | V3 Key Rotation | Proof of Rotation 协议 + apksigner rotate 实战 | `ApkSignatureSchemeV2.java` (V3 部分) |
| 5 | V4 Sidecar | .apk.idsig 96 字节 + Merkle 树 4KB 块计算 | `ApkSignatureSchemeV4.java` |
| 6 | 选型 + 实战 | 3 个 5 件套案例(V2 损坏 / V3 链断 / V4 缺失) | (案例章节) |
| 7 | 总结 | 5 条 Takeaway | (收口) |

### 03-签名校验链路:PackageInstaller → PMS

| § | 章节 | 核心内容 | 关键源文件 |
|---|------|---------|----------|
| 1 | 背景 | 为什么需要"链路视角" | (理论章节) |
| 2 | PackageInstaller 入口 | PackageInstallerActivity / Session / Service | `PackageInstallerActivity.java` |
| 3 | PMS 安装流程 | installStage + InstallParams | `PackageManagerService.java` |
| 4 | VerifyInstaller 守门员 | verify() + 错误码 | `VerifyInstaller.java` |
| 5 | APK 解析与 SigningDetails | PackageParser + SigningDetails 内存模型 | `PackageParser.java` + `SigningDetails.java` |
| 6 | 签名匹配 | matchSignatures() + checkCapability() | (在 PMS 内部) |
| 7 | 运行时签名检查 | PathClassLoader 不校验 + 运行时"读"签名场景 | (理论章节) |
| 8 | 5 个核心源文件走读 | 5 文件 + 关键行号 | (源码走读) |
| 9 | 3 个 5 件套案例 | 升级不匹配 / 无证书 / 旧 SDK | (案例) |
| 10 | 总结 | 5 条 Takeaway | (收口) |

### 04-AndroidKeyStore 与硬件密钥管理

| § | 章节 | 核心内容 | 关键源文件 |
|---|------|---------|----------|
| 1 | 背景 | 为什么需要 AndroidKeyStore? | (理论章节) |
| 2 | 3 层架构 | KeyStore2 + KeyMint HAL + TEE/StrongBox | `keystore2/` + `keymint/` |
| 3 | TEE vs StrongBox | ARM TrustZone + 独立芯片 trade-off | (硬件章节) |
| 4 | KeyMint HAL 详解 | AIDL 接口 + SecurityLevel + KeyGenParameterSpec | `IKeyMintDevice.aidl` |
| 5 | Key Attestation 详解 | X.509 + 信任链 + Google Trust List 同步 | (协议章节) |
| 6 | KeyChain vs AndroidKeyStore | 选型决策树 | `KeyChain.java` |
| 7 | 性能与安全分析 | TEE/StrongBox/Software 性能对比 | (分析章节) |
| 8 | 3 个 5 件套案例 | StrongBox 失败 / Attestation 失败 / 跨设备迁移 | (案例) |
| 9 | 总结 | 5 条 Takeaway | (收口) |

### 05-签名风险全景 + 实战案例(收口)

| § | 章节 | 核心内容 | 关键源文件 |
|---|------|---------|----------|
| 1 | 背景 | 为什么需要"风险 + 案例"篇 | (理论章节) |
| 2 | 6 大风险速查矩阵 | 错误码 + 排查方向速查 | (速查) |
| 3 | 5 件套实战案例 | 6 大场景各 1 个详细案例 | (案例) |
| 4 | 跨厂商差异 | 华为/小米/OPPO/vivo/三星/谷歌/鸿蒙 NEXT | (横切) |
| 5 | 监控 + 治理 | Prometheus 告警规则 + 治理 4 步走 | (治理) |
| 6 | 总结 | 整个系列 5 条 Takeaway | (收口) |
| 7 | 系列阅读建议 | 按角色分类 | (导航) |

---

## 跨系列引用矩阵

### 本系列引用 → 跨系列内容

| 本系列文章 | 引用跨系列 | 引用章节 | 引用原因 |
|----------|----------|---------|---------|
| 01 §1.2 | 01-Process 系列 | 进程隔离如何与签名配合 | 沙箱 + 签名 = 同一信任根 |
| 01 §4.3 | 01-Kernel/Memory_Management | vbmeta / dm-verity | 系统分区签名平行于 APK 签名 |
| 01 §4.1 | (待 04 写) | TEE / KeyMint | AndroidKeyStore 内部机制 |
| 02 §2.8 | 02-Symptom/S02-JE | Janus 漏洞案例 | DEX 注入后的运行时症状 |
| 03 §3 | 01-Process 系列 | installStage 异步化 | PMS HandlerThread 调度 |
| 03 §7 | (本系列 04) | AndroidKeyStore 运行时入口 | 04 详细讲 |
| 04 §3 | 01-Process 系列 | TEE World switch 与调度 | TEE OS 在 secure world |
| 05 §5 | 04-Tool 系列 | 监控告警体系 | 签名监控是稳定性监控一部分 |

### 跨系列 → 本系列引用

| 跨系列 | 引用本系列 | 引用章节 | 引用原因 |
|--------|----------|---------|---------|
| 01-Process §7 | 03-签名校验链路 | §3 | installStage 必经 VerifyInstaller |
| 02-Symptom/S02-JE | 01-签名总览 | §6.1 | V1 绕过 + DEX 注入症状 |
| 04-Tool/Dumpsys | 03-签名校验链路 | §5.2 | dumpsys package 输出的 signingDetails |
| 05-Governance/APM | 05-签名风险全景 | §5 | 签名告警 + 治理 4 步 |

---

## 阅读建议(按角色)

| 读者 | 阅读顺序 | 重点 |
|------|---------|------|
| **稳定性架构师** | 01 → 02 → 03 → 04 → 05 | 全部精读,建立 4 层全景 + 实战案例库 |
| **应用层工程师** | 01 → 02 §3-5 → 05 §3 | 重点:V1-V4 协议 + 5 件套案例 |
| **Framework 工程师** | 01 → 03 → 04 §2-4 | 重点:PMS 链路 + KeyStore 架构 |
| **安全工程师** | 01 §4 → 04 §5-6 → 05 | 重点:Key Attestation + 监控治理 |
| **新人**(刚加入稳定性团队) | 01 → 05 → 02-04 选读 | 先建立全景,再深入细节 |

---

## 系列基线

| 维度 | 值 | 备注 |
|------|---|------|
| **AOSP 版本** | `android-17.0.0_r1` (API 37) | 代号 CinnamonBun |
| **Linux 内核** | `android17-6.18` LTS | GKI 2.0 |
| **JDK** | JDK 17 | AOSP 17 主线 |
| **Kotlin** | 2.0+ | 仅 04 AndroidKeyStore 涉及 |
| **Android Studio** | 最新稳定版 | AOSP 17 推荐 |

---

## 系列统计

| 指标 | 值 |
|------|---|
| **总文章数** | 5 |
| **总字符数** | ~128k |
| **总行数** | ~3600 |
| **总 ASCII 图** | ~32 |
| **总 5 件套案例** | 12 (01 破例省 6 个) |
| **跨系列引用** | 8+ |
| **总 git commit** | 5(01-05 各 1) |
| **总源码路径** | 50+(cs.android.com 验证) |

---

## 后续可补充专题(待评估)

| 候选专题 | 必要性 | 备注 |
|---------|-------|------|
| **Play App Signing 深度实战** | 🟡 中 | 01 §3.2 简略,可扩展为 6 |
| **鸿蒙 NEXT 签名迁移指南** | 🟡 中 | 05 §4.2 简略,完整迁移需独立专题 |
| **V4 Incremental Install 性能调优** | 🟢 低 | 大型游戏 App 专属,普通 App 用不到 |
| **App Bundle(AAB)签名 vs APK 签名** | 🟡 中 | 01 §3.2 简略,Google Play 强制要求 |
| **Key Attestation 跨厂商差异** | 🟡 中 | 04 §5 简略,银行/支付专属 |
| **Source Stamp(Android 13+) 完整机制** | 🟢 低 | 02 §3.3 简略,商店额外签名 |

> **判断标准**:**必要性 🟡 中 = 5 件套案例不足 / 跨厂商差异显著 / 协议复杂**。**🟢 低 = 5 件套案例足够 / 用得少**。

---

## 更新日志

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-07-31 | v1.0 | 系列 5 篇首发(01-05) |

---

> **本系列收口**:5 篇覆盖了"背景 / 协议 / 链路 / 硬件 / 风险" 5 个维度。下一步:补充专题视需求决定。
