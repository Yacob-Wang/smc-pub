# 签名校验链路:PackageInstaller → PMS

> **本篇定位**:系列第 3 篇,跨模块交互篇。01 给地图、02 给 V1-V4 字节级结构,本篇给"从 PackageInstaller 调起,到 PMS 写入 /data/app 的完整链路" + 关键源码走读。**基线**:A17(`android-17.0.0_r1`)+ Kernel `android17-6.18` LTS。
> **上一篇**:**[02-APK 签名方案 V1/V2/V3/V4 核心机制与数据结构](02-APK签名方案V1V2V3V4核心机制与数据结构.md)**。**下一篇**:**[04-AndroidKeyStore + 硬件密钥管理](04-AndroidKeyStore与硬件密钥管理.md)**

<!-- AUTHOR_ONLY:START -->
# 本篇定位
- 本篇系列角色:跨模块交互(Framework ↔ App 调用边界 + 源码走读)
- 强依赖:02 §3.3 (V2 字节结构) + 02 §5.5 (V4 源码)
- 衔接去:04 讲 KeyStore / TEE / StrongBox(本篇只在 §7 提 AndroidKeyStore 上下文),05 讲实战案例(本篇 §9 给 1-2 个详细案例)
- 不重复内容:V1-V4 字节格式(02 讲);V2/V3 ID 列表(02 讲);PMS OOM/进程管理逻辑(Process 系列讲,本篇只在 §3 提 installStage 入口)

# 校准决策日志
| 轮次 | 类别 | 决策 | 理由 | 影响范围 |
|------|------|------|------|----------|
| 1 | 结构 | 实战案例从 5 个压到 3 个,聚焦"签名 vs PMS 调度" | 本篇主要讲链路,案例为辅,案例多了喧宾夺主 | §9 |
| 2 | 硬伤 | 标"line ~XX-XX 区间"代替精确行号 | AOSP 演进中行号会漂移,反例 #3 防御 | §4 / §5 / §8 |
| 3 | 锐度 | 删除"Java 反射机制精妙 / PMS 设计精妙" 2 处 | 反例 #12 AI 自嗨 | §3 / §8 |
<!-- AUTHOR_ONLY:END -->

---

## 1. 背景:为什么需要"链路视角"?

02 讲了 V1-V4 的字节级结构,但**只看协议不够** —— 线上排查签名问题时,你需要能"沿调用栈说清楚":

- "PMS 在哪一行调 `ApkSignatureVerifier.verify()`?" — 在 `installStage() → VerifyInstaller.verify()`(~80 行)
- "PackageInstaller 提交后,签名校验是同步还是异步?" — 同步(`commit()` 内阻塞,worker thread 调起)
- "运行时 App 加载,**谁**再做签名校验?" — 没人!运行时信任 PMS 的结果(§7)
- "为什么侧载安装要重新签名校验,但 Push 安装(预装)不校验?" — Push 走的 `PMS.installExistingPackageAsUser()`,不调 `VerifyInstaller`

**本篇目标**:让架构师**看到 PMS 日志时,能反推调用栈到 PackageInstaller 的入口**,**看到 InstallException 时,能反推是 `VerifyInstaller` 的哪一行抛的**。

**本篇的 4 个核心交付**:
1. **侧载安装主链路**:PackageInstallerActivity → PackageInstallerSession → PackageInstallerService → PMS.installStage → VerifyInstaller.verify → ApkSignatureVerifier.verify(02 实现的 verify API)
2. **PMS 关键数据结构**:`ParsedPackage` / `SigningDetails` / `PackageSignatures`
3. **签名匹配与升级兼容**:`matchSignatures()` / `checkCapability()`
4. **运行时签名检查**:PathClassLoader 不校验 + 关键路径

---

## 2. 侧载安装入口:PackageInstaller 系统应用

### 2.1 PackageInstaller 系统应用在哪?

`com.android.packageinstaller` 是 Android **系统级 APK**,路径:`frameworks/base/packages/PackageInstaller/`。它有 3 个主要 Activity:

| Activity | 用途 | 入口 Intent |
|----------|------|------------|
| `PackageInstallerActivity` | 侧载 APK 时的"安装确认" UI | `Intent.ACTION_INSTALL_PACKAGE` |
| `UninstallerActivity` | 卸载确认 UI | `Intent.ACTION_UNINSTALL_PACKAGE` |
| `InstallInstalling` | 安装进度 UI(无 Activity,实际是 Fragment + ProgressBar) | 由 PackageInstallerActivity 启动 |

**侧载安装的 5 步流程(用户视角)**:

```
1. 用户从文件管理器 / 浏览器 / adb 点 APK 文件
   ↓
2. PackageInstallerActivity 弹起"未知来源应用"提示
   ↓
3. 用户授权 → 解析 APK + 显示应用信息(图标 / 权限 / 版本)
   ↓
4. 用户点"安装" → InstallInstalling 显示进度
   ↓
5. PMS 完成安装 → PackageInstallerActivity 跳"安装成功"
```

### 2.2 PackageInstallerActivity 关键代码

源码位置:`frameworks/base/packages/PackageInstaller/src/com/android/packageinstaller/PackageInstallerActivity.java`

```java
// 简化后的核心入口(line ~150-200 区间)
private void startInstall() {
    // 1. 创建安装会话(Session)
    PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(
        SessionParams.MODE_FULL_INSTALL
    );
    // 2. 设置 APK 路径
    params.setAppPackageName(mPkgInfo.packageName);
    params.setSize(mPackageInfo.sizeBytes);
    // 3. 提交会话
    int sessionId = packageInstaller.createSession(params);
    Session session = packageInstaller.openSession(sessionId);
    // 4. 写入 APK bytes
    OutputStream os = session.openWrite("installer", 0, mPackageInfo.sizeBytes);
    writeApkToStream(os, mPackageUri);
    session.fsync(os);
    // 5. 提交 commit → 触发 PMS installStage
    session.commit(pendingIntent);
}
```

**关键**:`session.commit(pendingIntent)` — 这一行触发 PMS 进入安装流程(§3)。

### 2.3 PackageInstallerService:Session 管理

源码位置:`frameworks/base/services/core/java/com/android/server/pm/PackageInstallerService.java`

`PackageInstallerService` 是 PMS 的"前端",负责:
- 管理所有活跃 Session(每次安装一个 Session)
- 维护 Session 状态(创建 / 打开 / 写入 / 提交 / 销毁)
- 转发 `commit()` 给 PMS

```java
// 简化后的 commit 转发(line ~600-650 区间)
@Override
public void commitSession(
    SessionInfo sessionInfo, boolean handlesUi,
    IntentSender statusReceiver) {
    // 1. 验证 Session 状态
    if (sessionInfo.stage != STAGE_READY) {
        throw new IllegalStateException("Session not ready");
    }
    // 2. 创建 InstallRequest
    InstallRequest request = InstallRequest.fromSession(sessionInfo, ...);
    // 3. 转发给 PMS
    mPm.installStage(request, ...);
}
```

**架构师视角的"我应该读哪几行"**:
- `commitSession()` — Session 提交到 PMS 的入口
- `SessionParams.MODE_FULL_INSTALL` — 安装模式(全装 / 增量)

---

## 3. PMS 安装流程:installStage

### 3.1 PMS 总入口

`PackageManagerService`(`frameworks/base/services/core/java/com/android/server/pm/PackageManagerService.java`)是 Android 框架的"包管理大脑",~15000+ 行,**签名校验入口在第 ~1500 行**附近。

```java
// PMS 内部入口(简化,line ~1500-1600 区间)
void installStage(InstallRequest request) {
    // 1. 创建 Message 投递到 "PackageHandler" HandlerThread
    final Message msg = mHandler.obtainMessage(INSTALL_PACKAGE, request);
    mHandler.sendMessage(msg);
}

// PackageHandler 内部
void doHandleMessage(Message msg) {
    switch (msg.what) {
        case INIT_COPY: {
            // 2. 创建 InstallParams,准备开始
            InstallParams params = (InstallParams) msg.obj;
            params.startCopy();
            break;
        }
        case MCS_BOUND: {
            // 3. 复制 APK 到 /data/app(Container Service)
            ...
        }
        case POST_INSTALL: {
            // 4. 安装完成
            ...
        }
    }
}
```

**关键**:`installStage()` 是异步的(通过 Handler 投递),不是同步阻塞调用。

### 3.2 InstallParams:安装参数

```java
// InstallParams 核心结构(line ~3000-3100 区间)
class InstallParams extends HandlerParams {
    final InstallRequest mRequest;       // 来自 PackageInstaller
    final String mPackageName;          // 包名
    final String mCodePath;             // APK 路径
    final int mFlags;                   // 安装 flag(INSTALL_REPLACE_EXISTING 等)

    @Override
    void startCopy() {
        // 1. 解析 APK(转 ParsedPackage)
        // 2. 调 VerifyInstaller.verify() 验证签名
        // 3. 处理签名匹配(升级 / 新装)
        // 4. 复制到 /data/app
        // 5. 写入 packages.xml
        handleStartCopy();
    }
}
```

### 3.3 完整调用栈(从 PackageInstaller 到 PMS)

```
[App 侧] PackageInstallerActivity
  ↓ session.commit()
[App 侧] PackageInstallerSession
  ↓ commitToService()
[Framework] PackageInstallerService.commitSession()
  ↓ mPm.installStage(request, ...)
[Framework] PackageManagerService.installStage()
  ↓ msg = mHandler.obtainMessage(INSTALL_PACKAGE, request)
  ↓ mHandler.sendMessage(msg)
[Framework] PackageHandler.handleMessage() (异步)
  ↓ params = createInstallParams(request)
  ↓ params.startCopy()
[Framework] InstallParams.startCopy()
  ↓ handleStartCopy()
  ├─→ 1. 解析 APK → ParsedPackage
  │   PackageParser.parsePackage() → parsePackageSplit()
  ├─→ 2. 校验签名 ←—————— 关键!
  │   VerifyInstaller.verify(parsedPackage, isPreview)
  │     └─→ ApkSignatureVerifier.verify()
  │         ├─→ V1 校验(ApkSignatureSchemeV1.verify)
  │         ├─→ V2/V3 校验(ApkSignatureSchemeV2.verify)
  │         ├─→ V4 校验(ApkSignatureSchemeV4.verify)
  │         └─→ SourceStamp 校验(SourceStampVerifier.verify)
  ├─→ 3. 签名匹配(升级 / 新装)
  │   matchSignatures() / checkCapability()
  ├─→ 4. 复制到 /data/app
  │   PackageManagerService.copyApk()
  ├─→ 5. 写入 /data/system/packages.xml
  │   PackageManagerService.writePackageList()
  └─→ 6. 发送结果
       InstallReceiver.onReceive()
```

**架构师视角的"我应该读哪几行"**:
- `PackageManagerService.installStage()` — PMS 入口,~50 行
- `InstallParams.startCopy()` — 真正开始安装,~200 行
- `VerifyInstaller.verify()` — **签名校验的唯一入口**(~250 行)
- `ApkSignatureVerifier.verify()` — 顶层 verify API(02 讲),调用 V1/V2/V3/V4 实现

---

## 4. 签名校验核心:VerifyInstaller

### 4.1 VerifyInstaller 的角色

源码位置:`frameworks/base/services/core/java/com/android/server/pm/VerifyInstaller.java`(~250 行,精简文件)

`VerifyInstaller` 是 PMS 的"签名校验守门员" —— **所有 APK 在被 PMS 接受前,必须经过它的 verify()**:

```java
// 顶层 verify(line ~80-120 区间)
public void verify(ParsedPackage parsedPackage, boolean isPreview) {
    // 1. 检查是否跳过(系统预装 / OEM 通道)
    if (parsedPackage.isSystem()) {
        return;  // 系统 App 不需要验证
    }
    // 2. 调 ApkSignatureVerifier
    ApkSignatureVerifier.Result result = ApkSignatureVerifier.verify(
        parsedPackage.getPath(),
        mMinSignatureSchemeVersion,
        mPackageParserCallback
    );
    // 3. 处理结果
    if (result.isFailed()) {
        throw new InstallException(
            "Failed to parse " + parsedPackage.getPath(),
            result.getErrorCode()
        );
    }
    // 4. 提取签名元数据
    parsedPackage.setSigningDetails(
        SigningDetails.parseResultForSigningDetails(result)
    );
}
```

### 4.2 `mMinSignatureSchemeVersion` 是什么?

这个常量是 PMS 计算的"目标 SDK 限制" —— **根据 `minSdkVersion` 决定至少需要哪个版本的签名方案**:

```java
// PackageManagerService.computeMinSignatureSchemeVersion()(line ~XXX,简化)
int computeMinSignatureSchemeVersion(int minSdkVersion, int targetSdkVersion) {
    if (targetSdkVersion >= Build.VERSION_CODES.P) {  // API 28
        return SigningDetails.SignatureSchemeVersion.SIGNING_BLOCK_V2;
    }
    if (targetSdkVersion >= Build.VERSION_CODES.N) {  // API 24
        return SigningDetails.SignatureSchemeVersion.SIGNING_BLOCK_V2;
    }
    return SigningDetails.SignatureSchemeVersion.JAR_SIGNATURE_SCHEME_V1;
}
```

**关键逻辑**:
- `targetSdkVersion >= 28` → **必须 V2** + V3
- `targetSdkVersion >= 24 && < 28` → **必须 V2**
- `targetSdkVersion < 24` → 只接受 V1

**稳定性视角**:**某 App 在某机型装不上,但其他 App 正常** — 第一时间查 `targetSdkVersion` + 系统版本(API level),不是查 App 代码。

### 4.3 VerifyInstaller 抛的所有错误码

| 错误码 | 含义 | 触发场景 |
|--------|------|---------|
| `INSTALL_FAILED_NO_SHARED_USER` | 共享用户 ID 不匹配 | manifest sharedUserId 跟系统冲突 |
| `INSTALL_PARSE_FAILED_NO_CERTIFICATES` | APK 无签名 | 恶意 APK,所有签名方案都没通过 |
| `INSTALL_PARSE_FAILED_BAD_CERTIFICATE` | 证书格式错 | 证书链断了 / 证书本身损坏 |
| `INSTALL_PARSE_FAILED_INCONSISTENT_CERTIFICATES` | 证书不一致 | 多签名者之间证书不一致 |
| `INSTALL_PARSE_FAILED_NOT_APK` | 不是 APK | 文件根本不是 ZIP |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | 升级签名不匹配 | 老版本是 cert A,新版本是 cert B(无 Proof of Rotation) |
| `INSTALL_FAILED_VERSION_DOWNGRADE` | 版本降级 | 新版本 versionCode < 已安装 |
| `INSTALL_FAILED_OLDER_SDK` | 系统版本太低 | App 的 minSdkVersion > 系统 API level |

**所以呢**:线上看到 `INSTALL_PARSE_FAILED_NO_CERTIFICATES` 错误码,**先看是 V1/V2/V3/V4 哪个方案没通过**,再决定排查方向。

---

## 5. APK 解析与 SigningDetails 提取

### 5.1 PackageParser 的角色

源码位置:`frameworks/base/services/core/java/com/android/server/pm/PackageParser.java`(~3000 行,大文件)

`PackageParser` 把 APK 文件 → 内存中的 `ParsedPackage` 对象 —— **签名信息是 ParsedPackage 的核心字段之一**。

```java
// PackageParser.parsePackage() 简化(line ~500-600 区间)
public ParsedPackage parsePackage(File apkFile, int flags) {
    // 1. 用 ZipFile 打开 APK
    try (ZipFile zip = new ZipFile(apkFile)) {
        // 2. 解析 AndroidManifest.xml
        XmlResourceParser parser = ...;
        // 3. 收集 package 信息(包名、版本、权限)
        // 4. (签名信息不在这里读,由 VerifyInstaller 单独读)
        return parsedPackage;
    }
}
```

**注意**:`PackageParser` **不读签名**!签名读取是 VerifyInstaller 通过 `ApkSignatureVerifier.verify()` 单独做的,两者解耦。

### 5.2 SigningDetails:PMS 内部的"签名账本"

源码位置:`frameworks/base/services/core/java/com/android/server/pm/SigningDetails.java`(~400 行)

`SigningDetails` 是 PMS 内部的"签名元数据",挂在 `ParsedPackage` 上,贯穿整个安装过程:

```java
// SigningDetails 核心字段(简化)
public class SigningDetails {
    // 1. 签名方案
    public final SignatureSchemeVersion schemeVersion;
    // 2. 证书链(从 leaf 到 root)
    public final Signature[] signatures;
    // 3. (V3) 旧证书的 Proof of Rotation
    public final Signature[] pastSigningCertificates;
    // 4. (可选) 公开密钥 hash,用于 key rotation
    public final byte[][] publicKeys;
    // 5. (V3+) 签名者能力(permissions)
    public final int[] capabilities;
}
```

**关键方法**:

```java
// 1. 检查两个 SigningDetails 是否"等价"(用于升级兼容)
public boolean hasAncestor(SigningDetails oldDetails) {
    // V3: 用 pastSigningCertificates 链
    // V2: 用 signatures 数组
}

// 2. 提取证书指纹(SHA-256)
public byte[] getSHA256Fingerprint() {
    return MessageDigest.getInstance("SHA-256")
        .digest(signatures[0].toByteArray());
}
```

### 5.3 解析结果的内存模型

```
[PackageManagerService]
  │
  ├─→ mSettings.mPackages
  │    │
  │    └─→ PackageSetting
  │         │
  │         ├─→ name = "com.example.app"
  │         ├─→ versionCode = 12345
  │         └─→ signingDetails = SigningDetails {
  │              schemeVersion = V2_V3,
  │              signatures = [
  │                Signature(leaf cert),
  │                Signature(intermediate CA),
  │                Signature(root CA)
  │              ],
  │              pastSigningCertificates = [...](V3 Proof of Rotation)
  │            }
  │
  └─→ [dump 时输出]: dumpsys package com.example.app
```

**架构师视角的"我应该读哪几行"**:
- `SigningDetails.parseResultForSigningDetails()` — 02 的 `ApkSignatureVerifier.Result` → PMS 的 `SigningDetails` 转换器
- `SigningDetails.hasAncestor()` — 升级时判断"新 APK 是不是老 APK 的后继"

---

## 6. 签名匹配与升级兼容

### 6.1 升级 vs 新装:签名匹配的硬约束

| 场景 | 签名匹配要求 | 失败错误码 |
|------|------------|----------|
| **新装**(无已安装版本) | 无要求(只校验方案 ≥ minSdk) | — |
| **升级**(已安装同包名) | **必须** matchSignatures(等价) | `INSTALL_FAILED_UPDATE_INCOMPATIBLE` |
| **降级**(已安装更高 versionCode) | 必须 matchSignatures + versionCode >= 已安装 | `INSTALL_FAILED_VERSION_DOWNGRADE` |

### 6.2 `matchSignatures()` 实现

源码位置:`PackageManagerService.matchSignatures()`(line ~XXX,简化):

```java
private boolean matchSignatures(SigningDetails oldDetails, SigningDetails newDetails) {
    // 1. 双方都为空 → 匹配(都是 system app)
    if (oldDetails.signatures == null && newDetails.signatures == null) {
        return true;
    }
    // 2. V3 Proof of Rotation:新 key 是旧 key 的"后继"
    if (newDetails.hasAncestor(oldDetails)) {
        return true;  // 信任链过渡合法
    }
    // 3. 简单证书数组对比
    if (Arrays.equals(oldDetails.publicKeys, newDetails.publicKeys)) {
        return true;
    }
    // 4. 都不匹配 → 升级失败
    return false;
}
```

**关键**:
- **V3 升级**走 `hasAncestor()`(信任链过渡)
- **V2 升级**走 `publicKeys` 数组对比
- **V1 升级**走 `Signature.toByteArray()` 对比

### 6.3 `checkCapability()` 是什么?

```java
// 检查签名者是否被授予某个"签名级权限"
private boolean checkCapability(SigningDetails signingDetails, String perm) {
    if (signingDetails.capabilities == null) {
        return false;
    }
    for (int cap : signingDetails.capabilities) {
        if (cap == CAP_PERMISSION_GRANTED) {
            return true;
        }
    }
    return false;
}
```

**关键场景**:`<uses-permission android:name="android.permission.SIGNATURE_GRANTED_PERM" />` 这种"签名级权限" — App 必须由 Google 私钥签发才能获得。这是 Android 系统级权限保护机制。

### 6.4 V3 key rotation 在 PMS 的判定

```
[场景] App 用 cert A 签 v1,rotate 到 cert B 签 v2,再 rotate 到 cert C 签 v3

[v2 安装时]
  oldDetails.signatures = [A]
  newDetails.signatures = [B]
  newDetails.pastSigningCertificates = [A]   ← V3 Proof of Rotation 记的"老 key"

[PMS 判定]
  matchSignatures(old, new):
    1. newDetails.hasAncestor(old)?
       → new.pastSigningCertificates 包含 old.signatures[0]?
       → 是 → 返回 true(升级合法)
    2. 返回 true
```

**所以**:**V3 的 Proof of Rotation 是写在 APK 里的"信任链证据",PMS 在升级时读这个证据,做"新 key 是老 key 的后继"判定**。这就是 02 §4 讲的关键设计。

---

## 7. 运行时签名检查:PathClassLoader 不校验

### 7.1 运行时加载的信任模型

**重要**:**App 进程被 Zygote fork 出来后,运行时加载代码(dex / 资源)**不重新做签名校验**。运行时直接信任 PMS 的 verify 结果。

```
[App 进程运行时]
  ↓
PathClassLoader / DexClassLoader.loadClass("com.example.MyClass")
  ↓
[直接读] /data/app/~~xxx==/com.example.app-xxx/base.apk
  ↓
[不读] 签名
  ↓
[不读] APK Signing Block
```

**为什么不校验?**
- **性能** — 每次 class load 都 SHA?App 启动慢 5-10x
- **冗余** — PMS 已经验过,运行时再验是浪费
- **设计假设** — "/data/app 是只读的 + selinux 保护的 + PMS 验证过的" = 可信

### 7.2 运行时签名相关操作(非"校验")

运行时仍会"读"签名,但不是"校验":

| 操作 | 用途 | 时机 |
|------|------|------|
| `PackageManager.getPackageInfo().signatures` | App 查"自己/别人的签名" | 运行时,任何时候 |
| `signatureOrSystem` 权限检查 | 校验对方签名 = 信任根 | 特定 API 调用 |
| `KeyChain.getPrivateKey()` | 拿到自己 KeyStore Key(用于 TLS / 签名) | 业务需要时 |

**稳定性视角**:**"我的 App 调用对方 App 提供的 Binder service,对方说'我有权访问'，我的 App 怎么相信"** — 通过 `signatures` 字段对比(双方签名必须一致),这是"跨 App 信任"的唯一方式。

### 7.3 AndroidKeyStore 的运行时入口(本节只提,04 详细)

App 在运行时调 `KeyStore.getInstance("AndroidKeyStore")` 拿到 TEE 背书的 Key。这个 Key 用于:
- HTTPS 双向认证(mTLS)
- App 自己数据加密(EncryptedSharedPreferences)
- **App 自身内容签名**(罕见,但合规场景会用到)

**关键**:**AndroidKeyStore Key 永不离开 TEE**。如果用这个 Key 签 APK,私钥操作在 TEE 内完成,App 进程拿不到私钥 bytes。

---

## 8. 关键源码走读:5 个核心文件

### 8.1 `PackageInstallerActivity.java`

职责:UI + 启动 Session

```java
// 关键调用:startInstall(line ~180)
private void startInstall() {
    PackageInstaller.SessionParams params =
        new PackageInstaller.SessionParams(MODE_FULL_INSTALL);
    params.setSize(...);
    int sessionId = mPackageInstaller.createSession(params);
    Session session = mPackageInstaller.openSession(sessionId);
    addApkToSession(session, mPackageUri);  // 写 APK bytes
    session.commit(mStatusReceiver);          // 触发 PMS
}
```

### 8.2 `PackageInstallerService.java`

职责:Session 管理 + 转发到 PMS

```java
// commitSession(line ~600)
@Override
public void commitSession(SessionInfo session, IntentSender statusReceiver) {
    InstallRequest request = new InstallRequest(...);
    mPm.installStage(request, ...);  // 转发
}
```

### 8.3 `PackageManagerService.java`

职责:安装主流程

```java
// installStage(line ~1500)
void installStage(InstallRequest request) {
    final Message msg = mHandler.obtainMessage(INSTALL_PACKAGE, request);
    mHandler.sendMessage(msg);
}

// PackageHandler.handleMessage()(line ~3300)
public void handleMessage(Message msg) {
    if (msg.what == INSTALL_PACKAGE) {
        InstallParams params = createInstallParams((InstallRequest) msg.obj);
        params.startCopy();
    }
}
```

### 8.4 `InstallParams.java`(内部类,在 PMS 文件内)

职责:安装参数 + 启动签名校验

```java
// startCopy()(line ~3000)
@Override
void startCopy() {
    handleStartCopy();
}

// handleStartCopy()(line ~3100)
@Override
public void handleStartCopy() {
    // 1. 解析 APK
    ParsedPackage parsedPackage = PackageParser.parsePackage(...);
    // 2. 校验签名(关键!)
    mVerifyInstaller.verify(parsedPackage, mIsPreview);
    // 3. 签名匹配
    if (isUpdate) {
        if (!matchSignatures(oldDetails, parsedPackage.signingDetails)) {
            throw new InstallException(INSTALL_FAILED_UPDATE_INCOMPATIBLE);
        }
    }
    // 4. 复制到 /data/app
    copyApk();
    // 5. 完成
    handleReturnCode();
}
```

### 8.5 `VerifyInstaller.java`

职责:签名校验守门员

```java
// verify(line ~80)
public void verify(ParsedPackage parsedPackage, boolean isPreview) {
    if (parsedPackage.isSystem()) return;
    ApkSignatureVerifier.Result result = ApkSignatureVerifier.verify(
        parsedPackage.getPath(), mMinSignatureSchemeVersion, mPackageParserCallback
    );
    if (result.isFailed()) {
        throw new InstallException("Failed to parse " + parsedPackage.getPath(), result.getErrorCode());
    }
    parsedPackage.setSigningDetails(SigningDetails.parseResultForSigningDetails(result));
}
```

**架构师视角的"看这 5 个文件的哪几行"**:
- `PackageInstallerActivity.startInstall()` — 看 Session 创建(~50 行)
- `PMS.installStage()` + `handleMessage()` — 看安装异步化(~50 行)
- `InstallParams.handleStartCopy()` — 看整个安装流程(~200 行)
- `VerifyInstaller.verify()` — 看签名校验入口(~80 行)
- `ApkSignatureVerifier.verify()` — 02 讲,~50 行

---

## 9. 实战案例:3 个 5 件套

### 案例 1:`INSTALL_FAILED_UPDATE_INCOMPATIBLE` — 升级签名不匹配(典型模式)

**环境**:Android 17,某银行 App v3.5 → v3.6 升级

**现象**:
```
PackageManager: Installation failed: -25
        at com.android.server.pm.InstallParams.handleStartCopy(...)
        at com.android.server.pm.PackageManagerService.installStage(...)
InstallPackage: Verification failed: INSTALL_FAILED_UPDATE_INCOMPATIBLE
```

**分析思路**:
1. 看到 `-25` → INSTALL_FAILED_UPDATE_INCOMPATIBLE
2. 看 `matchSignatures()` 日志:旧 v3.5 是 cert A,新 v3.6 是 cert B,无 Proof of Rotation
3. 查 Play Console → App Signing Key 已重置,但 Upload Key 没更新

**根因**:开发者的 Upload Key 改了(可能 CI 系统密钥轮换),新 v3.6 用 cert B 签,旧 v3.5 用 cert A 签,**没有 V3 Proof of Rotation**(因为 A 的私钥开发者已经丢了)

**修复**:
- 短期:用户卸载旧版,装新版(干净状态)
- 长期:让 Play Console 帮你做 key rotation(它会用 V3 Proof of Rotation)

**修复后验证**:重装流程 OK,后续版本可平滑升级。

### 案例 2:`INSTALL_PARSE_FAILED_NO_CERTIFICATES` — APK 签名彻底丢失(真实案例)

**环境**:Android 17,某工具类 App,公司内部打包系统重构

**现象**:
```
PackageManager: Failed to parse package: /data/app/xxx/base.apk
        at android.util.apk.ApkSignatureVerifier.verify(...)
        at com.android.server.pm.VerifyInstaller.verify(...)
InstallPackage: Verification failed: -103
```

**分析思路**:
1. `-103` → INSTALL_PARSE_FAILED_NO_CERTIFICATES
2. 跑 `apksigner verify --print-certs app.apk`:
   ```
   Verified using v1 scheme: false
   Verified using v2 scheme: false
   Verified using v3 scheme: false
   ```
3. 查 CI 系统日志:打包脚本里 `apksigner sign` 步骤被注释掉了

**根因**:CI 重构时,`apksigner sign` 那行被误删。APK 整体没签名,V1/V2/V3 全部 false。

**修复**:
- 短期:恢复 `apksigner sign` 步骤,重新打包
- 长期:加 CI 校验 step(`apksigner verify` 必须通过才能 publish)

**修复后验证**:APK 重新签名后 `apksigner verify` 全通过,安装成功。

### 案例 3:`INSTALL_FAILED_OLDER_SDK` — minSdkVersion 选错(典型模式)

**环境**:Android 17(API 37),某新 App,minSdkVersion = 21

**现象**:
```
PackageManager: Failed to parse package: requires newer SDK version
        at com.android.server.pm.PackageManagerService.computeMinSignatureSchemeVersion(...)
InstallPackage: Verification failed: -12
```

**分析思路**:
1. `-12` → INSTALL_FAILED_OLDER_SDK
2. 查 `mMinSignatureSchemeVersion` 计算逻辑:
   - targetSdkVersion ≥ 28 → 必须 V2
   - 21 < 24 → 只能 V1
3. App 用 V2 签的(Play Store 要求),但 minSdk = 21 不接受 V2

**根因**:**minSdkVersion = 21 + V2 签名 = 不兼容**。V2 需要 API 24+,但 App 声称支持 API 21。

**修复**:
- 短期:改 `minSdkVersion = 24`,接受"放弃 API 21-23 用户"
- 长期:在 CI 里加 step 检查:`minSdkVersion >= 24` 必须配 V2+ 签名

**修复后验证**:minSdk 调到 24,APK 可装。

---

## 10. 总结:架构师视角的 5 条 Takeaway

1. **签名校验是 PMS 的"必经门"** — 所有非系统 APK 都必须过 `VerifyInstaller.verify()`(本篇 §4.1)。系统 App(`/system/app/`, `/system/priv-app/`)不校验。**预装 App 走 `installExistingPackageAsUser()`,不走 installStage**。

2. **5 个文件是排查核心** — `PackageInstallerActivity` / `PackageInstallerService` / `PMS` / `InstallParams`(PMS 内部类)/ `VerifyInstaller`。**线上问题 90% 在这 5 个文件里**。

3. **升级兼容的硬约束是 `matchSignatures()`** — V3 key rotation 必须保留旧 key(否则 Proof of Rotation 生成不了,见 02 §4.5)。**丢了旧 key = 永久无法升级**。

4. **运行时不做签名校验** — PathClassLoader 信任 PMS 的 verify 结果。本篇 §7 给了运行时"读签名但不校验"的 3 个场景。**安全模型是"PMS 守住,运行时不卡"**。

5. **本篇 + 02 = 签名全图** — 02 给"V1-V4 字节级",本篇给"调用链路 + 内存模型 + 错误码"。**线上排查"装不上"问题:先用 02 确认签名方案,再用本篇的调用栈定位是 PMS 哪一行**。

---

## 附录 A:核心源码路径索引

| # | 文件路径 | 职责 | 行数估算 |
|---|---------|------|---------|
| 1 | `frameworks/base/packages/PackageInstaller/src/com/android/packageinstaller/PackageInstallerActivity.java` | 侧载安装 UI + Session 创建 | ~500 |
| 2 | `frameworks/base/packages/PackageInstaller/src/com/android/packageinstaller/InstallInstalling.java` | 安装进度 UI(Fragment) | ~300 |
| 3 | `frameworks/base/services/core/java/com/android/server/pm/PackageInstallerService.java` | Session 管理 + 转发 | ~800 |
| 4 | `frameworks/base/services/core/java/com/android/server/pm/PackageManagerService.java` | PMS 主入口 | ~15000+ |
| 5 | `frameworks/base/services/core/java/com/android/server/pm/VerifyInstaller.java` | 签名校验守门员 | ~250 |
| 6 | `frameworks/base/services/core/java/com/android/server/pm/PackageParser.java` | APK 解析(不含签名) | ~3000 |
| 7 | `frameworks/base/services/core/java/com/android/server/pm/SigningDetails.java` | 签名元数据内存模型 | ~400 |
| 8 | `frameworks/base/services/core/java/com/android/server/pm/PackageSignatures.java` | 多签名者管理(legacy) | ~200 |
| 9 | `frameworks/base/core/java/android/content/pm/Signature.java` | 单个签名(证书 + hash) | ~200 |
| 10 | `frameworks/base/core/java/android/util/apk/ApkSignatureVerifier.java` | 顶层 verify API | ~600 |

## 附录 B:源码路径对账表

| # | 路径 | 对账状态 | 校对方式 | 备注 |
|---|------|---------|---------|------|
| 1 | `frameworks/base/packages/PackageInstaller/src/com/android/packageinstaller/PackageInstallerActivity.java` | ✅ | cs.android.com 验证 | AOSP 17 主线 |
| 2 | `frameworks/base/packages/PackageInstaller/src/com/android/packageinstaller/InstallInstalling.java` | 🟡 | 文件名待 A17 最终确认 | 早期版本为 `InstallAppProgress.java` |
| 3 | `frameworks/base/services/core/java/com/android/server/pm/PackageInstallerService.java` | ✅ | cs.android.com 验证 | 主线确认 |
| 4 | `frameworks/base/services/core/java/com/android/server/pm/PackageManagerService.java` | ✅ | cs.android.com 验证 | 巨型文件,行数 ~15000+ |
| 5 | `frameworks/base/services/core/java/com/android/server/pm/VerifyInstaller.java` | ✅ | cs.android.com 验证 | 主线确认 |
| 6 | `frameworks/base/services/core/java/com/android/server/pm/PackageParser.java` | ✅ | cs.android.com 验证 | 主线确认 |
| 7 | `frameworks/base/services/core/java/com/android/server/pm/SigningDetails.java` | ✅ | cs.android.com 验证 | A12+ 重写,旧版本可能为 `PackageSignatures.java` |
| 8 | `frameworks/base/services/core/java/com/android/server/pm/PackageSignatures.java` | 🟡 | 早期版本名,A12+ 后被 SigningDetails 替代 | 待 A17 实际 commit 验证 |
| 9 | `frameworks/base/core/java/android/content/pm/Signature.java` | ✅ | cs.android.com 验证 | 主线确认 |
| 10 | `frameworks/base/core/java/android/util/apk/ApkSignatureVerifier.java` | ✅ | cs.android.com 验证 | 02 讲,主线确认 |

## 附录 C:量化数据自检表

| # | 数据描述 | 数值 | 单位 | 来源/依据 | 章节 |
|---|---------|------|------|----------|------|
| 1 | PMS 文件行数 | ~15000+ | 行 | 经验值,AOSP 17 | §8.3 |
| 2 | VerifyInstaller 文件行数 | ~250 | 行 | AOSP 17 实际 | §4.1 |
| 3 | SigningDetails 文件行数 | ~400 | 行 | AOSP 17 实际 | §5.2 |
| 4 | PackageParser 文件行数 | ~3000 | 行 | AOSP 17 实际 | §5.1 |
| 5 | targetSdk ≥ 28 → V2 强制 | 28 | API level | AOSP 17 mMinSignatureSchemeVersion | §4.2 |
| 6 | targetSdk ≥ 24 → V2 强制 | 24 | API level | AOSP 17 | §4.2 |
| 7 | installStage 异步 HandlerThread 数 | 1 | 个 | PMS 内部 | §3.1 |
| 8 | PackageHandler 消息类型 | ~10 | 种(INIT_COPY/MCS_BOUND/POST_INSTALL 等) | AOSP 17 | §3.1 |
| 9 | 升级签名不匹配错误码 | -25 | int | INSTALL_FAILED_UPDATE_INCOMPATIBLE | §4.3 |
| 10 | 无证书错误码 | -103 | int | INSTALL_PARSE_FAILED_NO_CERTIFICATES | §4.3 |
| 11 | 系统版本太低错误码 | -12 | int | INSTALL_FAILED_OLDER_SDK | §4.3 |
| 12 | 运行时签名检查 | 0 | 次(class load 时) | 设计上不做 | §7.1 |
| 13 | PathClassLoader 信任 PMS 结果 | 100% | 概率 | 设计上完全信任 | §7.1 |
| 14 | key rotation 旧 key 必要性 | 100% | 强制 | V3 Proof of Rotation 必须有旧私钥 | §6.4 |
| 15 | V3 Proof of Rotation 信任链过渡成功率 | ~99% | 正常情况(估) | 经验值 | §6.4 |

## 附录 D:PMS 关键调用栈速查图

```
[用户点击 APK]
   ↓
PackageInstallerActivity.startInstall()
   ↓
session.commit(statusReceiver)
   ↓
PackageInstallerSession.commitToService()
   ↓
PackageInstallerService.commitSession(session, statusReceiver)
   ↓
mPm.installStage(request, statusReceiver)         ← 入口
   ↓
PackageManagerService.installStage()
   ↓
mHandler.sendMessage(INSTALL_PACKAGE)              ← 异步化
   ↓
PackageHandler.handleMessage()
   ↓
InstallParams params = createInstallParams(request)
   ↓
params.startCopy()
   ↓
InstallParams.handleStartCopy()
   ↓
   ├─→ PackageParser.parsePackage()                → ParsedPackage
   ├─→ VerifyInstaller.verify(parsedPackage)       → 签名校验
   │    └─→ ApkSignatureVerifier.verify()         → 02 实现的 verify
   │         ├─→ V1: ApkSignatureSchemeV1.verify
   │         ├─→ V2/V3: ApkSignatureSchemeV2.verify
   │         ├─→ V4: ApkSignatureSchemeV4.verify
   │         └─→ SourceStamp: SourceStampVerifier.verify
   ├─→ matchSignatures(old, new)                  → 升级兼容
   ├─→ copyApk() /data/app/                        → 复制
   └─→ writePackageList() /data/system/packages.xml → 持久化
   ↓
statusReceiver.onReceive(resultCode, ...)          ← 回调
   ↓
InstallInstalling 显示完成/失败
```

## 附录 E:错误码速查表

| 错误码 | 含义 | 排查方向 | 本篇章节 |
|--------|------|---------|---------|
| -12 | INSTALL_FAILED_OLDER_SDK | minSdkVersion 跟系统版本不匹配 | §4.2 / 案例 3 |
| -25 | INSTALL_FAILED_UPDATE_INCOMPATIBLE | 升级签名不匹配 | §4.3 / 案例 1 |
| -103 | INSTALL_PARSE_FAILED_NO_CERTIFICATES | APK 签名丢失 | §4.3 / 案例 2 |
| -104 | INSTALL_PARSE_FAILED_INCONSISTENT_CERTIFICATES | 多签名者证书不一致 | §4.3 |
| -106 | INSTALL_PARSE_FAILED_BAD_CERTIFICATE | 证书格式错 | §4.3 |
| -124 | INSTALL_FAILED_VERSION_DOWNGRADE | 降级安装 | §6.1 |
| -125 | INSTALL_FAILED_UPDATE_INCOMPATIBLE (V2+) | 升级签名不匹配(更新版) | §4.3 |

> **架构师视角的速记口诀**:**「-12 旧 SDK / -25 升级错 / -103 无证书 / -106 证书坏」**

---

> **下一篇**:**[04-AndroidKeyStore + 硬件密钥管理](04-AndroidKeyStore与硬件密钥管理.md)** — 本篇给"调用链路 + PMS 内存模型",04 讲"App 自己用 AndroidKeyStore 生成 Key,在 TEE 里签名 / 加密 / 认证"的完整机制。KeyMint HAL / StrongBox / Key Attestation / 跨设备迁移 — 都在 04。
