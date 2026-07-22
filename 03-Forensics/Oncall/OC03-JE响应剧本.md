# OC03 · JE 响应剧本：Java Exception 黄金 5/15/30 + 5 类异常分类 + 3 步定位

> **系列**：On-Call Playbook（03-Forensics/Oncall）· 第 3 篇 / 共 8 篇
>
> **基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18` LTS
>
> **目标读者**：oncall 工程师 / 稳定性架构师
>
> **完成时间**：2026-07-22（v1.0 首版）

<!-- AUTHOR_ONLY:START -->

## 本篇定位

- **本篇系列角色**：**oncall 7 大症状剧本第 2 篇** —— Java 异常（最常见崩溃）
- **强依赖**：
  - 必先读 [OC01-oncall 工程总论](OC01-oncall工程总论：值班机制与工具栈.md) —— 5/15/30 流程
  - 必先读 [02-Symptom/S02-JE/01-症状机制.md](../../02-Symptom/S02-JE/01-症状机制.md) —— JE 机制
  - 必先读 [03-Forensics/F03-JE/01-取证机制.md](../F03-JE/01-取证机制.md) —— JE 取证
  - 必先读 [04-Tool/Dumpsys 系列](../../04-Tool/Dumpsys/) —— dump 抓取
- **承接自**：OC01 + OC02 ANR
- **衔接去**：[OC04-NE 响应剧本](OC04-NE响应剧本.md) + [OC05-SWT 响应剧本](OC05-SWT响应剧本.md)（待补）
- **不重复内容**：OC01 流程 + S02 机制
- **本篇贡献**：
  1. **JE 黄金 5/15/30 标准动作**
  2. **5 类异常分类**（NPE / OOM / ConcurrentModification / ClassCast / IllegalState）
  3. **3 步定位法**（崩溃栈 → 触发场景 → 根因）
  4. **3 类真实场景剧本**（主线程 OOM / 后台 ConcurrentModification / 第三方 SDK 异常）
  5. **JE 12 反例清单**

## 校准决策日志

| 轮次 | 类别 | 决策 | 理由 | 影响范围 |
|:-----|:-----|:-----|:-----|:---------|
| 1 | 结构 | 单篇 500+ 行 | §8 破例 | 全文 |
| 1 | 结构 | 5 类异常 + 3 场景剧本 | 实战必备 | §4-§9 |
| 2 | 硬伤 | 黄金 5/15/30 每分钟给动作 | 反例 #4 | §3 |
| 2 | 硬伤 | 5 类异常每类给修复代码 | 反例 #11 | §4 |
| 3 | 锐度 | 删"可能"，改"必做" | 反例 #5 | 全文 |

## 角色设定

我是一名 **oncall 工程师**，刚收到 P0 告警：

> **告警**：`Crash-free Session` < 99.9%
> **触发时间**：14:30:00
> **影响范围**：约 30 万 DAU 出现 Java 崩溃

## 上下文

- **上一篇**：[OC02-ANR 响应剧本](OC02-ANR响应剧本.md)
- **下一篇**：[OC04-NE 响应剧本](OC04-NE响应剧本.md)
- **跨系列引用**：
  - [02-Symptom/S02-JE](../../02-Symptom/S02-JE/01-症状机制.md) JE 机制
  - [03-Forensics/F03-JE](../F03-JE/01-取证机制.md) JE 取证
  - [04-Tool/Dumpsys/01-dumpsys总览与架构](../../04-Tool/Dumpsys/01-dumpsys总览与架构.md) dump
- **本篇专题类型**：**实战剧本**

## 写作标准

> v5 规范 + 5 段前言 marker ✅

<!-- AUTHOR_ONLY:END -->

---

# 1. JE 5 大类别速查

> **铁律**：oncall 收到 JE 告警，**第 1 件事是看崩溃栈第一行**——确定异常类型

| # | 异常类型 | 占比 | 关键字 | 触发场景 |
|:-:|:---------|:----:|:-------|:---------|
| 1 | **NullPointerException** | 35% | `at ... null` | 引用为 null |
| 2 | **OutOfMemoryError** | 20% | `Failed to allocate` | 内存不足 |
| 3 | **ConcurrentModificationException** | 15% | `at java.util.AbstractList` | 遍历时修改 |
| 4 | **ClassCastException** | 10% | `cannot be cast to` | 类型转换错 |
| 5 | **IllegalStateException** | 10% | `not in proper state` | 状态机错 |
| 6 | **其他** | 10% | 各种 | 各种 |

---

# 2. 黄金 5 分钟：必做 4 件事

## 2.1 第 1 分钟：确认告警 + 拉群

```bash
# 1. APM 推送卡片（飞书/钉钉）
# 2. 回复"已收到"
# 3. 拉应急群
```

## 2.2 第 2 分钟：抓崩溃栈

```bash
# 1. APM 后台取崩溃栈（30 秒）
#   - 一般 APM 平台（Firestore Crashlytics / Sentry / 自研）有完整崩溃栈
#   - 关键字：exception_type + top_frame

# 2. 同步抓 logcat（30 秒）
adb logcat -d -b crash | tail -100
```

## 2.3 第 3 分钟：判断异常类型

**看崩溃栈第一行**：

```java
// 例 1：NPE
java.lang.NullPointerException: Attempt to invoke virtual method '...' on a null object reference
  at com.example.app.User.getName(User.java:45)

// 例 2：OOM
java.lang.OutOfMemoryError: Failed to allocate a 4MB byte allocation
  at com.example.app.ImageLoader.loadBitmap(ImageLoader.java:123)

// 例 3：ConcurrentModification
java.util.ConcurrentModificationException
  at java.util.ArrayList$Itr.next(ArrayList.java:860)
```

**判断结果**：
- NPE → §6
- OOM → §7
- ConcurrentModification → §8
- 其他 → §4 修复

## 2.4 第 4-5 分钟：发首报

```yaml
告警: JE 率超阈值
触发: 14:30:00
当前: oncall @A 已介入
判断: [NPE/OOM/CME/CCE/ISE] 异常
首报:
  - 影响: 30 万 DAU
  - 异常类型: [类型]
  - 崩溃栈: [top 5 frames]
  - 怀疑: [根因假设]
  - 行动: 已抓栈完成，开始定位
  - ETA: 5 分钟内出二报
```

---

# 3. 白银 15 分钟：3 步定位

## 3.1 Step 1：看崩溃栈 top 5 frames

**核心原则**：**top frame = 异常抛出点，**下面 3-5 帧 = 业务调用链

```
java.lang.NullPointerException
  at com.example.app.User.getName(User.java:45)        ← top frame（关键）
  at com.example.app.UserProfileFragment.bindView(UserProfileFragment.java:200)
  at com.example.app.MainActivity.onCreate(MainActivity.java:150)
  at android.app.Activity.performCreate(Activity.java:...)
  at android.app.Instrumentation.callActivityOnCreate(...)
```

**读法**：
1. top frame → 找哪个类的哪个方法
2. 看调用链 → 是从哪个业务入口来的
3. 看 Git blame → 是不是新代码

## 3.2 Step 2：复现 + 看触发条件

```
问题清单：
- [ ] 触发版本：是哪个版本引入？
- [ ] 触发机型：是所有机型还是特定机型？
- [ ] 触发页面：是哪个 Activity/Fragment 触发？
- [ ] 触发操作：用户做了什么？
- [ ] 触发链路：在线/离线/后台？
```

## 3.3 Step 3：根因 5 Whys

```
Why 1: 为什么会 NPE？
   → 答：user.getName() 时 user 为 null
Why 2: 为什么 user 为 null？
   → 答：方法参数没校验
Why 3: 为什么没校验？
   → 答：调用方传错了
Why 4: 为什么会传错？
   → 答：业务逻辑漏判 null
Why 5: 为什么漏判？
   → 答：测试没覆盖空 case
```

---

# 4. 黄金 30 分钟：执行修复

## 4.1 决策树

```
定位到根因
   │
   ├── 业务代码 bug
   │     │
   │     ├── 紧急程度高 → **热修**（应急发版）
   │     └── 紧急程度低 → **下个版本修**
   │
   ├── 第三方 SDK bug
   │     │
   │     ├── 第三方能修 → **联系 + 降级**
   │     └── 第三方不能修 → **主动 catch + 上报**
   │
   └── Framework bug
         │
         ├── Google 已修 → **升级 + 灰度**
         └── Google 未修 → **绕开 + 上报 issue**
```

## 4.2 修复代码（5 类异常）

### 4.2.1 NPE 修复

```java
// 错误
public String getUserName(User user) {
    return user.getName();  // ❌ user 可能为 null
}

// 正确（防御式）
public String getUserName(User user) {
    if (user == null) return "";  // ✅ 防御
    return user.getName();
}

// 更好（@NonNull 注解）
@NonNull
public String getUserName(@NonNull User user) {
    return user.getName();
}
```

### 4.2.2 OOM 修复

```java
// 错误
Bitmap bitmap = BitmapFactory.decodeFile(path);  // ❌ 大图直接解码

// 正确（inSampleSize 缩放）
BitmapFactory.Options opts = new BitmapFactory.Options();
opts.inJustDecodeBounds = true;
BitmapFactory.decodeFile(path, opts);
opts.inSampleSize = calculateInSampleSize(opts, 800, 600);  // ✅ 缩放
opts.inJustDecodeBounds = false;
Bitmap bitmap = BitmapFactory.decodeFile(path, opts);
```

### 4.2.3 ConcurrentModification 修复

```java
// 错误（遍历时修改）
for (User u : userList) {
    if (u.isExpired()) userList.remove(u);  // ❌ ConcurrentModification
}

// 正确（Iterator.remove）
Iterator<User> it = userList.iterator();
while (it.hasNext()) {
    if (it.next().isExpired()) it.remove();  // ✅
}

// 正确（CopyOnWriteArrayList）
List<User> safeList = new CopyOnWriteArrayList<>(userList);
for (User u : safeList) {
    if (u.isExpired()) safeList.remove(u);  // ✅ 线程安全
}
```

### 4.2.4 ClassCastException 修复

```java
// 错误
Object obj = getSomething();
User user = (User) obj;  // ❌ 强转失败

// 正确（instanceof 检查）
Object obj = getSomething();
if (obj instanceof User) {  // ✅
    User user = (User) obj;
}
```

### 4.2.5 IllegalStateException 修复

```java
// 错误
public void onCreate() {
    super.onCreate();
    FragmentManager.findFragmentById(...).doSomething();  // ❌ Fragment 未初始化
}

// 正确（生命周期检查）
public void onCreate() {
    super.onCreate();
    Fragment frag = FragmentManager.findFragmentById(...);
    if (frag != null && frag.isAdded()) {  // ✅
        frag.doSomething();
    }
}
```

---

# 5. 4 类常见场景

## 5.1 场景 1：主线程 OOM（图片解码）

**现象**：拍照后打开图片，App 闪退
**异常**：`OutOfMemoryError: Failed to allocate a 4MB byte allocation`
**根因**：直接 decode 大图（10MB+）
**修复**：用 `inSampleSize` 缩放 + BitmapFactory

## 5.2 场景 2：后台 ConcurrentModification

**现象**：后台定时任务清理数据时崩溃
**异常**：`ConcurrentModificationException at ArrayList$Itr.next`
**根因**：后台线程遍历时主线程修改 list
**修复**：用 `CopyOnWriteArrayList` 或加锁

## 5.3 场景 3：第三方 SDK 异常

**现象**：调用支付 SDK 后崩溃
**异常**：`NullPointerException at com.third.paysdk.PayManager.doPay`
**根因**：第三方 SDK 内部 NPE
**修复**：本地 catch + 上报到第三方

```java
// oncall 修复模式
try {
    thirdPayManager.doPay(order, callback);
} catch (NullPointerException e) {  // ✅ 主动 catch
    reportToThirdParty("doPay NPE", e);
    showToast("支付暂不可用");
}
```

## 5.4 场景 4：Fragment 状态异常

**现象**：用户快速切换页面，App 崩溃
**异常**：`IllegalStateException: Fragment ... not currently in the FragmentManager`
**根因**：Fragment 已 detach 后还在操作
**修复**：判断 `isAdded()` 或 `isResumed()`

---

# 6. JE 告警规则

```yaml
# APM 告警（JE 类）
- alert: JeFreeSessionDrop
  expr: |
    1 - (
      countIf(event_type='je_exception', session_id != '')
      / countIf(event_type='session_start')
    ) < 0.9995
  for: 2m
  labels: { severity: P0 }

- alert: Top1ExceptionSpike
  expr: |
    rate(je_exception_total{exception_type="NullPointerException"}[5m]) > 10
  for: 5m
  labels: { severity: P1 }
```

---

# 7. JE oncall 12 反例

| # | 反例 | 错误做法 | 正确做法 |
|:-:|:-----|:---------|:---------|
| 1 | **只看 top 1 frame** | 只看异常抛出点 | **看 top 5 frames** |
| 2 | **不抓 logcat** | 只看 APM 崩溃栈 | **logcat 互补** |
| 3 | **不查引入版本** | 不查 Git blame | **第 3 步必查** |
| 4 | **不区分类型** | "就是崩溃" | **5 类异常分类处理** |
| 5 | **catch 完不处理** | catch (Exception e) {} | **catch + 上报 + 兜底** |
| 6 | **不写 postmortem** | 修了就完 | **24h 内出** |
| 7 | **改 try-catch 凑数** | 不找根因 | **必须找到 5 Whys** |
| 8 | **不通知 TL** | 一个人修 | **第 1 分钟拉群** |
| 9 | **跨多模块改动** | 紧急改 5 个模块 | **最小改动 + 应急发版** |
| 10 | **不查 issue 池** | 不查类似 bug | **必须先查 issue** |
| 11 | **追责** | "X 写错代码" | **只对事不对人** |
| 12 | **不复盘同类** | 单点修复 | **横向 review 同类** |

---

# 8. 5 条 Takeaway

1. **JE 黄金 5/15/30** —— 5 分钟抓栈 + 拉群；15 分钟定位；30 分钟修复
2. **5 类异常分类**（NPE 35% / OOM 20% / ConcurrentModification 15% / ClassCast 10% / ISE 10%）—— 看 top frame 立刻分类
3. **3 步定位法**（top 5 frames → 触发条件 → 5 Whys）
4. **4 类真实场景**（主线程 OOM / 后台 CM / 第三方 SDK / Fragment 状态）
5. **catch + 上报 + 兜底** 三件套 —— 第三方 SDK 异常标准处理

---

# 9. 附录

## 附录 A：源码索引

| 模块 | 路径 | 关键类/方法 |
|:-----|:-----|:-------------|
| JE 机制 | [02-Symptom/S02-JE/01-症状机制.md](../../02-Symptom/S02-JE/01-症状机制.md) | UncaughtExceptionHandler |
| JE 取证 | [03-Forensics/F03-JE/01-取证机制.md](../F03-JE/01-取证机制.md) | 完整流程 |
| dumpsys | [04-Tool/Dumpsys/01-dumpsys总览与架构](../../04-Tool/Dumpsys/01-dumpsys总览与架构.md) | dumpsys |
| 内存分析 | [04-Tool/Dumpsys/04-内存分析](../../04-Tool/Dumpsys/04-内存分析.md) | meminfo |
| oncall 流程 | [OC01-oncall 工程总论](OC01-oncall工程总论：值班机制与工具栈.md) | 5/15/30 |

## 附录 B：路径对账

本篇新增模块无（沿用 S02 + F03 + dumpsys 已有路径）。

## 附录 C：量化自检

- 5 类异常分类 + 占比 ✅
- 黄金 5/15/30 每分钟动作 ✅
- 3 步定位法（top 5 / 触发条件 / 5 Whys）✅
- 4 类真实场景剧本 ✅
- 12 反例清单 ✅
- 5 条 Takeaway ✅

## 附录 D：工程基线

- AOSP 17.0.0_r1（API 37）
- 工具链：APM + logcat -b crash + adb pull
- 告警栈：Prometheus + APM 自研

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-22（v1.0）
