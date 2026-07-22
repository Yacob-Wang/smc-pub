# OC02 · ANR 响应剧本：黄金 5/15/30 + Input/Service/Broadcast 三轨分类处置

> **系列**：On-Call Playbook（03-Forensics/Oncall）· 第 2 篇 / 共 8 篇
>
> **基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18` LTS
>
> **目标读者**：oncall 工程师 / 稳定性架构师
>
> **完成时间**：2026-07-22（v1.0 首版）

<!-- AUTHOR_ONLY:START -->

## 本篇定位

- **本篇系列角色**：**oncall 7 大症状剧本第 1 篇** —— 7 大症状中**最常触发**的 ANR
- **强依赖**：
  - 必先读 [OC01-oncall 工程总论](OC01-oncall工程总论：值班机制与工具栈.md) —— 知道 5/15/30 升级 + 工具栈
  - 必先读 [02-Symptom/S01-ANR/01-症状机制.md](../../02-Symptom/S01-ANR/01-症状机制.md) —— ANR 机制与 4 类触发条件
  - 必先读 [03-Forensics/F01-ANR/01-取证机制.md](../F01-ANR/01-取证机制.md) —— ANR 取证
  - 必先读 [04-Tool/ANR-Detection 系列](../../04-Tool/ANR-Detection/) —— 3 类 ANR 检测深潜
- **承接自**：OC01 §3 §4 工具栈 + 升级矩阵
- **衔接去**：[OC03-JE 响应剧本](OC03-JE响应剧本.md) + [OC04-NE 响应剧本](OC04-NE响应剧本.md)
- **不重复内容**：
  - **不重复** OC01 值班/升级/工具栈（流程留给 OC01）
  - **不重复** S01-ANR 机制定义（机制留给 S01）
- **本篇贡献**：
  1. **ANR 黄金 5/15/30 标准动作**（每分钟必做什么）
  2. **Input/Service/Broadcast 三轨分类处置**（不同类型 ANR 走不同分支）
  3. **AM/PM/EM 三段告警升级**（告警模板 + 升级路径）
  4. **4 类真实场景剧本**（Input 主线程 / Service onCreate / Broadcast 串行 / Provider）
  5. **ANR 反例清单**（12 条 oncall 常见错误）

## 校准决策日志

| 轮次 | 类别 | 决策 | 理由 | 影响范围 |
|:-----|:-----|:-----|:-----|:---------|
| 1 | 结构 | 单篇 500+ 行（v4 默认 300） | §8 破例：3 类 ANR × 完整剧本必须展开 | 全文 |
| 1 | 结构 | 4 个真实场景剧本（§6-§9）| oncall 必须按场景演练 | §6-§9 |
| 2 | 硬伤 | 黄金 5/15/30 每分钟给具体动作 | 反例 #4 模糊量化 | §3 |
| 2 | 硬伤 | 三类 ANR 分类必须给"看哪个关键字" | 反例 #5 模糊量化 | §4 |
| 3 | 锐度 | 删"可能""大概"，改"必做/必查" | 反例 #5 模糊量化 | 全文 |
| 3 | 锐度 | 5 条 Takeaway 含 2 条指向 S01/F01 | §4 必备 | §11 |

## 角色设定

我是一名 **oncall 工程师**，刚收到 P0 告警：

> **告警**：`Input ANR-free Session` < 99.5%（阈值 99.9%）
> **触发时间**：14:30:00
> **影响范围**：约 50 万 DAU
> **当前状态**：oncall 5 分钟内必须介入

本篇要交付：**一份能直接照着做的 ANR 响应剧本**。

## 上下文

- **上一篇**：[OC01-oncall 工程总论](OC01-oncall工程总论：值班机制与工具栈.md)
- **下一篇**：[OC03-JE 响应剧本](OC03-JE响应剧本.md)
- **本系列规划**：8 篇（OC01-OC08）
- **跨系列引用**：
  - [02-Symptom/S01-ANR](../../02-Symptom/S01-ANR/01-症状机制.md) ANR 机制
  - [03-Forensics/F01-ANR](../F01-ANR/01-取证机制.md) ANR 取证
  - [04-Tool/ANR-Detection](../../04-Tool/ANR-Detection/) ANR 检测
  - [04-Tool/Perfetto](../../04-Tool/Perfetto/) ANR 后抓 trace
  - [01-Mechanism/Framework/Input/06-InputANR.md](../../01-Mechanism/Framework/Input/06-InputANR.md) Input ANR 深潜
- **本篇专题类型**：**实战剧本**（§8 破例）

## 写作标准

> 沿用 v5 一站式模板 + 5 段作者前言（marker 包裹）
>
> - 顶部 4 行 blockquote ✅
> - 5 段前言：`<!-- AUTHOR_ONLY:START -->` 包裹 ✅
> - 单篇 ≤ 1000 行（§8 破例外）✅
> - 9 项硬指标 + 12 反例清单 ✅

<!-- AUTHOR_ONLY:END -->

---

# 1. ANR 4 类触发条件速查

> **铁律**：oncall 收到 ANR 告警，**第 1 件事是判断 ANR 类型**——不同类型走不同分支

| # | 类型 | 触发条件 | 检测点 | 占比 |
|:-:|:-----|:---------|:-------|:----:|
| 1 | **Input** | 5s 内无 Input 事件响应 | InputDispatcher | 60% |
| 2 | **Service** | 前台 20s / 后台 200s 无响应 | ActiveServices | 20% |
| 3 | **Broadcast** | 前台 10s / 后台 60s 无返回 | BroadcastQueue | 15% |
| 4 | **ContentProvider** | 10s 无 publish | ContentProvider | 5% |

**关键日志关键字**（oncall 第一眼看的）：

| 类型 | 关键字（logcat 搜）|
|:-----|:--------------------|
| Input | `Input event injection finished but no response` |
| Service | `ANR in xxxService` / `executing service` |
| Broadcast | `ANR in xxxReceiver` / `Broadcast of xxx` |
| Provider | `ANR in publishing` |

---

# 2. 黄金 5 分钟：必做 4 件事

> **铁律**：**5 分钟内必做以下 4 件事** —— 不做完不升级

## 2.1 第 1 分钟：确认告警 + 拉群

```bash
# 1. 确认 APM 告警（5 秒）
# 飞书/钉钉机器人推送的卡片：
#   - 告警级别 / 触发时间 / 影响范围 / 当前 oncall
# 2. 回复"已收到"（5 秒）
# 3. 拉群（飞书/钉钉自动拉）
```

## 2.2 第 2 分钟：抓 bugreport + traces

```bash
# 1. 抓 bugreport（30 秒，IO 重，异步执行）
adb shell bugreport > /data/bugreports/$(date +%Y%m%d_%H%M%S).zip &

# 2. 拉 system_server 关键 traces（30 秒）
adb shell kill -3 $(pidof system_server)
adb shell ls /data/anr/  # 列出所有 traces.txt

# 3. 拉最近 5 个 ANR traces（关键）
adb pull /data/anr/anr_$(date +%Y-%m-%d-%H-%M-%S)*.txt /tmp/anr/
```

## 2.3 第 3 分钟：判断 ANR 类型

> **看 logcat 关键字**（30 秒判断）

```bash
# 一次性搜 4 类关键字
adb logcat -d -b events,main | grep -E "ANR in|Input event injection|Broadcast of" | tail -20
```

**判断结果**：
- 看到 `Input event injection` → **Input ANR**（→ §6）
- 看到 `ANR in xxxService` → **Service ANR**（→ §7）
- 看到 `ANR in xxxReceiver` → **Broadcast ANR**（→ §8）
- 看到 `ANR in publishing` → **Provider ANR**（→ §9）

## 2.4 第 4-5 分钟：发首报

**飞书/Lark 卡片模板**：

```yaml
告警: ANR 率超过阈值
触发: 14:30:00
当前: oncall @A 已介入
判断: [Input/Service/Broadcast/Provider] ANR
首报:
  - 影响: 50 万 DAU
  - 怀疑: [主线程阻塞 / 后台服务超时 / 串行广播卡住 / Provider 慢查询]
  - 行动: 抓 traces 完成，开始定位
  - ETA: 5 分钟内出二报
```

---

# 3. 白银 15 分钟：定位根因

## 3.1 Input ANR（占 60%）

**traces.txt 关键字**：

```
"main" prio=5 tid=1 ...
  at android.os.MessageQueue.nativePollOnce(Native method)
  at android.os.MessageQueue.next(MessageQueue.java:...)
  - waiting on <0x...> (a java.lang.Object)   ← 主线程等锁
  - locked <0x...> (a android.os.MessageQueue)
```

**5 大根因**：

| 根因 | traces 关键字 | 修复 |
|:-----|:---------------|:-----|
| **主线程 IO** | `at java.io.FileInputStream.read` | 移到子线程 |
| **主线程网络** | `at java.net.SocketInputStream.read` | 移到子线程 |
| **主线程锁** | `waiting on <0x...>` | 异步化 |
| **主线程 Binder 调用** | `at android.os.BinderProxy.transactNative` | 移到子线程 |
| **Handler 消息卡死** | `at android.os.Handler.dispatchMessage` | 检查 handleMessage |

详见 [04-Tool/ANR-Detection/Input_Dispatch_Timeout_ANR_Deep_Dive.md](../../04-Tool/ANR-Detection/Input_Dispatch_Timeout_ANR_Deep_Dive.md)。

## 3.2 Service ANR（占 20%）

**traces.txt 关键字**：

```
"AsyncTask #1" prio=5 tid=...
  at java.net.Socket.read  ← 后台 service 同步 IO
  ...
"Binder:xxx" prio=5 tid=...
  at android.os.BinderProxy.transactNative  ← 同步等系统服务
```

**4 大根因**：

| 根因 | traces 关键字 | 修复 |
|:-----|:---------------|:-----|
| **onCreate 同步 IO** | `executing service ... onCreate` + IO | 异步化 |
| **onStartCommand 卡死** | `executing service ... onStartCommand` + 同步 | 异步化 |
| **同步等系统服务** | `BinderProxy.transactNative` | 改异步 |
| **多次 start 串行** | service 堆积 | 用 startId 区分 |

详见 [04-Tool/ANR-Detection/Service_ANR_Deep_Dive.md](../../04-Tool/ANR-Detection/Service_ANR_Deep_Dive.md)。

## 3.3 Broadcast ANR（占 15%）

**traces.txt 关键字**：

```
"Binder:xxx" prio=5 tid=...
  at android.content.BroadcastReceiver.onReceive  ← 同步卡死
```

**3 大根因**：

| 根因 | traces 关键字 | 修复 |
|:-----|:---------------|:-----|
| **onReceive 同步** | `at BroadcastReceiver.onReceive` + 同步调用 | 改 goAsync() |
| **串行队列卡死** | `waiting for ... receiver` | 排查前一个 receiver |
| **manifest 注册** | `static` 注册 + 启动时间紧 | 改动态注册 |

详见 [02-Symptom/S01-ANR/01-症状机制.md](../../02-Symptom/S01-ANR/01-症状机制.md) §3。

## 3.4 Provider ANR（占 5%）

**traces.txt 关键字**：

```
"Binder:xxx" prio=5 tid=...
  at android.content.ContentProvider.publish  ← Provider 阻塞
```

**2 大根因**：

| 根因 | traces 关键字 | 修复 |
|:-----|:---------------|:-----|
| **publish 慢** | `at ContentProvider.publish` + IO | 异步化 |
| **query/update 慢** | `at ContentProvider.query` + 慢查询 | 加索引 |

---

# 4. 黄金 30 分钟：执行修复

## 4.1 决策树：回滚 vs 热修

```
定位到根因
   │
   ├── 已知 bug，本次发版引入
   │     │
   │     ├── 已发版 30% 以下 → **热修**（走应急发版）
   │     └── 已发版 30% 以上 → **回滚**（不冒险）
   │
   ├── 第三方 SDK 引起
   │     │
   │     ├── 第三方能发版 → **切回旧版 + 联系第三方**
   │     └── 第三方不能发版 → **降级 + 回滚**
   │
   └── 底层机制问题（如 framework bug）
         │
         ├── Google 已修复 → **升级 + 灰度**
         └── Google 未修复 → **回滚 + 提交 issue**
```

## 4.2 应急发版 SOP

```bash
# 1. 紧急代码合入
git checkout main
git pull
# 改代码（fix）
git add .
git commit -m "fix: [ANR 修复描述]"

# 2. 触发紧急构建
./build.sh --urgent --channel=hotfix
# （自动走最快的构建通道，30-60 分钟出包）

# 3. 灰度发布（1% → 10% → 50% → 100%）
# 每阶段观察 30 分钟
```

## 4.3 自动回滚脚本

```bash
#!/bin/bash
# 紧急回滚脚本（oncall 可一键执行）
VERSION=$(adb shell dumpsys package com.example.app | grep versionName | head -1)
if [[ "$VERSION" > "1.2.3" ]]; then
    echo "回滚到 1.2.2"
    adb shell am force-stop com.example.app
    adb install -r old_version.apk
    # 触发监控
    echo "回滚完成，请 APM 同事跟踪指标"
fi
```

---

# 5. ANR 告警模板

## 5.1 AM（Alert Manager）告警规则

```yaml
# Prometheus 告警规则（ANR 类）
- alert: AnrFreeSessionDrop
  expr: |
    1 - (
      countIf(event_type='anr', session_id != '')
      / countIf(event_type='session_start')
    ) < 0.999
  for: 2m
  labels:
    severity: P0
  annotations:
    summary: "ANR 率超过 0.1%"
    description: "当前 ANR-free Session 率 {{ $value }}%"

- alert: InputAnrSpike
  expr: |
    rate(anr_total{type="input"}[5m]) > rate(anr_total{type="input"}[1h] offset 1d) * 2
  for: 5m
  labels:
    severity: P1
  annotations:
    summary: "Input ANR 5 分钟内增长 2 倍"
```

## 5.2 EM（Escalation Manager）升级路径

| 阶段 | 时长 | 责任人 | 动作 |
|:-----|:-----|:-------|:-----|
| **L1 oncall** | 0-5 分钟 | 主 R | 抓 dump + 拉群 |
| **L2 备 R1** | 5 分钟未响应 | 备 R1 | 接管 + 继续 |
| **L3 Tech Lead** | 15 分钟未定位 | TL | 介入 + 决策回滚 |
| **L4 架构师** | 30 分钟未恢复 | 稳定性架构师 | 升级到 P0 + 全员 |

详见 [OC01 §3 升级矩阵](OC01-oncall工程总论：值班机制与工具栈.md)。

## 5.3 PM（Problem Manager）记录

每起 ANR P0 必填以下字段：

```yaml
problem_id: P202607221430
trigger: APM 告警 / 用户反馈
type: input/service/broadcast/provider
root_cause: [一句话]
traces_file: /data/anr/anr_20260722_143001.txt
fix_pr: [PR 链接]
fix_time: 30 分钟 / 1 小时 / 1 天
action_items: [P0/P1/P2/P3]
```

---

# 6. 场景剧本 1：Input ANR（主线程等锁）

## 6.1 现象

- APM：`Input ANR-free Session` < 99%
- 用户反馈：滑动列表卡死，弹"应用无响应"
- logcat：`Input event injection finished but no response`

## 6.2 黄金 5/15/30 实战

**黄金 5 分钟**：
```bash
# 抓 traces
adb pull /data/anr/anr_*_inputdispatcher.txt
# 看 main 线程等哪个锁
```

**白银 15 分钟**：
```
"main" prio=5 tid=1
  at android.os.MessageQueue.nativePollOnce(Native method)
  at android.os.MessageQueue.next(MessageQueue.java:335)
  - waiting on <0x12345> (a java.lang.Object)  ← 等 App 自己的锁
  - locked <0x67890> (a android.os.MessageQueue)
  ...
  at com.example.app.MainActivity.onCreate(...)
  at com.example.app.SomeManager.doSomething(SomeManager.java:123)
  at com.example.app.SomeManager.syncWait(SomeManager.java:200)  ← 同步等回调
```

**根因**：App `MainActivity.onCreate` 同步等 `SomeManager` 回调，回调又发到主线程 → 死锁

**黄金 30 分钟**：
- 临时方案：直接 `force-stop` + 回滚
- 永久方案：让 `SomeManager.syncWait` 改为异步回调 + 超时

## 6.3 修复代码

```java
// 错误写法（主线程同步等回调）
public void onCreate() {
    super.onCreate();
    someManager.doSomething(result -> {
        // ❌ 回调在主线程，触发死锁
        updateUI(result);
    });
    waitForResult();  // ❌ 同步等
}

// 正确写法（异步 + 超时）
public void onCreate() {
    super.onCreate();
    someManager.doSomething(result -> {
        runOnUiThread(() -> updateUI(result));
    });
    // 不等待，继续初始化
}
```

---

# 7. 场景剧本 2：Service ANR（onCreate 同步 IO）

## 7.1 现象

- APM：`Service ANR-free Session` < 99.5%
- 用户反馈：App 启动后某些功能不能用
- logcat：`ANR in com.example.app.xxxService`

## 7.2 黄金 5/15/30 实战

**白银 15 分钟**：
```
"main" prio=5 tid=1
  at java.io.FileInputStream.readBytes(Native method)
  at java.io.FileInputStream.read(FileInputStream.java:...)
  at com.example.app.MyService.onCreate(MyService.java:67)  ← 同步读文件
  at android.app.ActivityThread.handleCreateService(ActivityThread.java:...)
```

**根因**：`MyService.onCreate` 同步读大文件（10MB+），耗时 25s，超过 20s 阈值

**黄金 30 分钟**：
- 临时方案：回滚 + 后台 service 替换
- 永久方案：把 IO 移到 WorkManager 异步

## 7.3 修复代码

```java
// 错误写法（onCreate 同步 IO）
public void onCreate() {
    super.onCreate();
    FileInputStream fis = new FileInputStream(getFilesDir() + "/big.bin");  // ❌ 10MB
    // ...
}

// 正确写法（WorkManager 异步）
public void onCreate() {
    super.onCreate();
    WorkManager.getInstance(this).enqueue(
        new OneTimeWorkRequest.Builder(ReadBigFileWorker.class).build()
    );
}
```

---

# 8. 场景剧本 3：Broadcast ANR（串行队列卡死）

## 8.1 现象

- APM：`Broadcast ANR-free Session` < 99.5%
- 用户反馈：App 启动时卡住
- logcat：`ANR in com.example.app.BootReceiver`

## 8.2 黄金 5/15/30 实战

**白银 15 分钟**：
```
"Binder:xxx" prio=5 tid=27
  at android.content.BroadcastReceiver.onReceive(BroadcastReceiver.java:...)
  at com.example.app.BootReceiver.onReceive(BootReceiver.java:45)
  at com.example.app.DataSync.sync(DataSync.java:123)  ← 同步网络
```

**根因**：BOOT_COMPLETED 后有 3 个 receiver 串行执行，第 1 个卡住导致后续全卡

**黄金 30 分钟**：
- 临时方案：取消 BOOT_COMPLETED 注册
- 永久方案：改 `goAsync()` + WorkManager

## 8.3 修复代码

```java
// 错误写法（同步等）
public void onReceive(Context context, Intent intent) {
    DataSync.sync();  // ❌ 10s 网络
}

// 正确写法（goAsync + 异步）
public void onReceive(Context context, Intent intent) {
    final PendingResult result = goAsync();
    new Thread(() -> {
        try {
            DataSync.sync();
        } finally {
            result.finish();
        }
    }).start();
}
```

---

# 9. 场景剧本 4：Provider ANR（慢查询）

## 9.1 现象

- APM：`Provider ANR-free Session` < 99.8%
- 用户反馈：联系人列表加载慢
- logcat：`ANR in publishing com.example.app.ContactProvider`

## 9.2 黄金 5/15/30 实战

**白银 15 分钟**：
```
"Binder:xxx" prio=5 tid=...
  at android.content.ContentProvider.query(ContentProvider.java:...)
  at android.database.sqlite.SQLiteQueryBuilder.query(SQLiteQueryBuilder.java:...)
  - waiting on <0x...> (a android.database.sqlite.SQLiteDatabase)
```

**根因**：`ContactProvider.query` 全表扫描，10 万行表无索引

**黄金 30 分钟**：
- 临时方案：加索引
- 永久方案：分页 + Room 缓存

---

# 10. ANR oncall 12 反例

| # | 反例 | 错误做法 | 正确做法 |
|:-:|:-----|:---------|:---------|
| 1 | **不抓 traces** | 只看 logcat 关键字 | **traces.txt 是金标准** |
| 2 | **没升级就硬撑** | 5 分钟超时不升级 | 必走 5/15/30 升级 |
| 3 | **不判断类型** | 直接定位"主线程卡了" | **先判断 Input/Service/Broadcast** |
| 4 | **抓 bugreport 阻塞 1 分钟** | 等 bugreport 完才下一步 | **异步 + 先抓 traces** |
| 5 | **不写 postmortem** | 修了就完 | **24h 内出 postmortem** |
| 6 | **没拉群就动手** | 一个人 debug | **第 1 分钟拉群** |
| 7 | **不确认版本** | 不知道当前线上版本 | **先看 `dumpsys package`** |
| 8 | **回滚不通知** | 偷偷回滚 | **回滚前通知 + 拉 TL** |
| 9 | **应急发版没灰度** | 直接 100% | **1% → 10% → 50% → 100%** |
| 10 | **不查根因就修** | 改个 try-catch 完事 | **必须找到根因** |
| 11 | **追责** | "这次是 X 的锅" | **只对事不对人** |
| 12 | **不复盘** | 24h 后忘光 | **72h 内开复盘会** |

---

# 11. 5 条 Takeaway

1. **ANR 黄金 5/15/30** —— 5 分钟抓 dump + 拉群；15 分钟定位；30 分钟修复
2. **三轨分类处置**（Input 60% / Service 20% / Broadcast 15% / Provider 5%）—— **不同类型走不同分支**
3. **traces.txt 是金标准** —— 不要只靠 logcat 关键字
4. **4 类真实场景剧本** —— Input 主线程 / Service onCreate / Broadcast 串行 / Provider 慢查询
5. **必须 24h 内出 postmortem** —— 否则同类 ANR 下周会再发生

---

# 12. 附录

## 附录 A：源码索引

| 模块 | 路径 | 关键类/方法 |
|:-----|:-----|:-------------|
| ANR 机制 | [02-Symptom/S01-ANR/01-症状机制.md](../../02-Symptom/S01-ANR/01-症状机制.md) | 4 类触发 |
| ANR 取证 | [03-Forensics/F01-ANR/01-取证机制.md](../F01-ANR/01-取证机制.md) | 完整流程 |
| Input ANR 深潜 | [04-Tool/ANR-Detection/Input_Dispatch_Timeout_ANR_Deep_Dive.md](../../04-Tool/ANR-Detection/Input_Dispatch_Timeout_ANR_Deep_Dive.md) | Input 5s |
| Service ANR 深潜 | [04-Tool/ANR-Detection/Service_ANR_Deep_Dive.md](../../04-Tool/ANR-Detection/Service_ANR_Deep_Dive.md) | Service 20s |
| NoFocusWindow ANR | [04-Tool/ANR-Detection/No_Focus_Window_ANR_Deep_Dive.md](../../04-Tool/ANR-Detection/No_Focus_Window_ANR_Deep_Dive.md) | 焦点窗口 |
| oncall 流程 | [OC01-oncall 工程总论](OC01-oncall工程总论：值班机制与工具栈.md) | 5/15/30 |
| Input ANR 机制 | [01-Mechanism/Framework/Input/06-InputANR.md](../../01-Mechanism/Framework/Input/06-InputANR.md) | InputDispatcher |

## 附录 B：路径对账

本篇新增模块无（沿用 S01 + F01 + ANR-Detection + OC01 已有路径）。

## 附录 C：量化自检

- 4 类 ANR 触发条件 + logcat 关键字 ✅
- 黄金 5/15/30 每分钟动作 ✅
- 三轨分类处置（Input/Service/Broadcast/Provider）✅
- 4 个真实场景剧本（Input/Service/Broadcast/Provider）✅
- 12 反例清单 ✅
- 5 条 Takeaway ✅

## 附录 D：工程基线

- AOSP 17.0.0_r1（API 37）
- Linux android17-6.18 LTS
- 工具链：bugreport + adb pull + kill -3 + am force-stop
- 告警栈：Prometheus + AlertManager + 飞书/钉钉

---

**作者**：Mavis · Stability Matrix Course
**基线**：AOSP 17 + android17-6.18
**最后更新**：2026-07-22（v1.0）
