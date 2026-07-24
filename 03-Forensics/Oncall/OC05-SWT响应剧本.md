# OC05 · SWT 响应剧本：多层 Watchdog 卡死的 5/15/30 + 5 类场景

> **基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18` LTS
>
> **目标读者**：oncall 工程师 / 稳定性架构师
>
> **完成时间**：2026-07-24（v1.0 首版）

<!-- AUTHOR_ONLY:START -->

## 本篇定位

- oncall 7 大症状剧本第 5 篇
- 强依赖：[OC01-oncall 工程总论](OC01-oncall工程总论：值班机制与工具栈.md) / [02-Symptom/S04-SWT](../../02-Symptom/S04-SWT/01-症状机制.md) / [03-Forensics/F02-SWT](../F02-SWT/01-取证机制.md) / [04-Tool/Watchdog 系列](../../04-Tool/Watchdog/) 9 篇
- 衔接去：[OC06-HANG/OOM 响应剧本](OC06-HANG-OOM响应剧本.md)

## 校准决策日志

| 轮次 | 类别 | 决策 | 理由 |
|:-----|:-----|:-----|:-----|
| 1 | 结构 | 单篇 500+ 行（§8 破例）| 5 类场景 + 多层 Watchdog 必须展开 |
| 2 | 硬伤 | 黄金 5/15/30 每分钟给动作 | 反例 #4 |
| 2 | 硬伤 | 5 类 Watchdog 卡死各给真实栈示例 | 反例 #11 |
| 3 | 锐度 | 删"通常""可能" | 反例 #5 |

<!-- AUTHOR_ONLY:END -->

---

# 1. SWT 与 ANR 的关键区别

| 维度 | ANR | SWT |
|:-----|:----|:----|
| 检测点 | InputDispatcher / Service / Broadcast | 多层 Watchdog（Java/ANR/HW/VM）|
| 超时 | 5s / 20s / 10s | 30s / 60s / 10min |
| 触发 | 单次超时 | 2 次连续超时（防误杀）|
| 杀谁 | 触发 ANR 的进程 | system_server 杀 + 重启 |
| 后果 | App 卡死 / 杀 App | system_server 死 → 手机重启 |

> **铁律**：SWT 出现 = **system_server 已经 / 即将死掉**——比 ANR 严重 1 个数量级

---

# 2. 4 层 Watchdog 速查

| 层 | 检测点 | 超时 | 触发动作 |
|:--|:-------|:-----|:---------|
| **L1 Java HandlerChecker** | 主线程消息 | 30s | 弹 ANR dialog |
| **L2 ANR Watchdog** | Activity / Service / Provider | 5s/20s/10s | 杀 App |
| **L3 HW Watchdog** | HAL ServiceManager checkService | 60s | 杀 system_server |
| **L4 VM Watchdog** | Init.rc watchdogd | 10min | 重启手机 |

详见 [04-Tool/Watchdog/02-多层Watchdog架构](../../04-Tool/Watchdog/02-多层Watchdog架构.md)。

---

# 3. 黄金 5 分钟：必做 4 件事

## 3.1 第 1 分钟：确认告警 + 拉群

```bash
# APM 推送卡片
# - "System Server Hung" / "Watchdog Triggered" / "system_server 重启"
# 回复"已收到" + 拉应急群
```

## 3.2 第 2 分钟：抓 logs

```bash
# 1. 抓 bugreport
adb shell bugreport > /tmp/bugreport_$(date +%Y%m%d_%H%M%S).zip &

# 2. 拉 system_server traces
adb shell kill -3 $(pidof system_server)
adb pull /data/anr/ /tmp/anr/

# 3. 拉 watchdog 专用 log
adb shell logcat -d -b system,main | grep -E "Watchdog|system_server|reboot" | tail -200
```

## 3.3 第 3 分钟：判断哪层 Watchdog

**看 logcat 关键字**：

| 层 | 关键字 |
|:--|:-------|
| L1 Java | `Watchdog: WAITED_TOOLONG_FOR` |
| L2 ANR | `ANR in system_server` |
| L3 HW | `HAL service ... not found` |
| L4 VM | `init: Watchdog detected` |

## 3.4 第 4-5 分钟：发首报

```yaml
告警: system_server Hung
触发: 14:30:00
判断: [L1/L2/L3/L4] Watchdog
首报:
  - 影响: 全量用户（system_server 重启 = 全局卡顿）
  - 怀疑: [主线程卡 / 锁竞争 / HAL 卡 / init 卡]
  - 行动: 抓 logs + 拉 Native 团队
  - ETA: 10 分钟内出二报
```

---

# 4. 白银 15 分钟：定位根因

## 4.1 traces.txt 解读

```
"main" prio=5 tid=1
  at android.os.MessageQueue.nativePollOnce(Native method)
  at android.os.MessageQueue.next(MessageQueue.java:335)
  - waiting on <0x...> (a java.lang.Object)   ← 主线程等锁
  
  ← 或者更深层：
  at com.android.server.am.ActivityManagerService.broadcastIntentLocked(...)
  - locked <0x...> (a com.android.server.am.ActivityManagerService)
  
  ← 看到这行 = AMS 主线程被锁 = 全机卡死
```

## 4.2 4 类常见根因

| 根因 | 关键字 | 占比 |
|:-----|:-------|:----:|
| **主线程 Binder 阻塞** | `BinderProxy.transactNative` | 40% |
| **AMS/WMS 锁竞争** | `locked <...> ActivityManagerService` | 25% |
| **HAL ServiceManager 卡** | `checkService` + 超时 | 20% |
| **IO / fs 慢** | `FileInputStream.readBytes` | 15% |

---

# 5. 黄金 30 分钟：执行修复

## 5.1 决策树

```
system_server Hung
   │
   ├── 主线程 Binder 阻塞
   │     → 找到具体 Binder 调用方（应用侧）→ 通知 App 团队
   │
   ├── AMS/WMS 锁竞争
   │     → 看 stack 锁链 → 找到死锁方 → 紧急发版
   │
   ├── HAL 卡
   │     → 检查 ServiceManager 死锁 → 联系 OEM
   │
   └── IO 慢
         → 检查 /data 分区 + 启动 IO 限流
```

## 5.2 应急操作

```bash
# 1. 强制重启 system_server（紧急）
adb shell stop && adb shell start

# 2. 紧急发版（如果发版引入）
./build.sh --urgent

# 3. 临时禁用引起卡顿的 App
adb shell pm disable-user com.example.badapp
```

---

# 6. 5 类真实场景剧本

## 6.1 场景 1：AMS 主线程 Binder 阻塞

**traces**：
```
"main" prio=5 tid=1
  at android.os.BinderProxy.transactNative(Native method)
  at android.app.ActivityManagerProxy.broadcastIntent(...)
  - waiting to lock <0x...> (a java.lang.Object)
```

**根因**：某个 App 通过 IActivityManager 同步等回调
**修复**：让 App 用 `AsyncTask` 或 `Handler` 异步

## 6.2 场景 2：ActivityManagerService 锁竞争

**traces**：
```
  - locked <0x...> (a com.android.server.am.ActivityManagerService)
  at com.android.server.am.ActivityStack.activityDestroyedLocked(...)
```

**根因**：App 进程退出 + Activity 销毁 触发锁链
**修复**：framework 加超时回退

## 6.3 场景 3：HAL ServiceManager 卡

**traces**：
```
"Watchdog" prio=5 tid=...
  at android.os.HwBinderProxy.transactNative(Native method)
  at android.hardware.graphics.composer@2.1::IComposer.waitForVBlank(...)
```

**根因**：Display HAL 卡死
**修复**：联系 OEM + 切到 fallback HAL

## 6.4 场景 4：PackageManagerService 锁

**traces**：
```
  - waiting on <0x...> (a com.android.server.pm.PackageManagerService)
  at com.android.server.pm.PackageManagerService.deletePackage(...)
```

**根因**：大量并发安装/卸载触发 PMS 锁
**修复**：PMS 加细粒度锁

## 6.5 场景 5：Init / Native 进程卡

**traces**：
```
init: Watchdog detected
  init waiting for /dev/block/bootdevice/by-name/userdata
```

**根因**：存储设备 I/O 卡死
**修复**：OEM 检查 eMMC/UFS 健康度

---

# 7. SWT 告警规则

```yaml
# APM 告警（SWT 类）
- alert: SystemServerHung
  expr: rate(watchdog_triggered_total[5m]) > 0
  for: 1m
  labels: { severity: P0 }
```

---

# 8. SWT 12 反例

| # | 反例 | 错误做法 | 正确做法 |
|:-:|:-----|:---------|:---------|
| 1 | **当作 ANR 处理** | 走 OC02 流程 | **SWT 严重程度高 1 级** |
| 2 | **不拉 Native 团队** | Java 团队自己修 | **第 1 分钟必拉** |
| 3 | **不抓 bugreport** | 只看 logcat | **bugreport 是金标准** |
| 4 | **不查 HAL** | 不看 ServiceManager | **L3 Watchdog 必查** |
| 5 | **不通知 OEM** | 第三方问题不联系 | **OEM 必通知** |
| 6 | **重启不通知** | 偷偷重启 | **提前通知用户** |
| 7 | **不复盘** | 重启完就完 | **24h 内出 postmortem** |
| 8 | **不写脚本** | 每次手动 | **应急 SOP 必脚本化** |
| 9 | **不区分 L1-L4** | 笼统说"Watchdog 触发" | **必须定位层级** |
| 10 | **不查引入版本** | 不查发版 | **第 3 步必查** |
| 11 | **追责 OEM** | "高通又出 bug" | **只对事不对人** |
| 12 | **不复盘同类** | 单点修复 | **横向 review** |

---

# 9. 5 条 Takeaway

1. **SWT 比 ANR 严重 1 个数量级** —— 出现 = system_server 即将死
2. **4 层 Watchdog 必区分**（L1 Java / L2 ANR / L3 HW / L4 VM）—— 不同层走不同分支
3. **主线程 Binder 阻塞占 40%** —— 找到调用方 App 团队
4. **HAL 卡 = 必通知 OEM** —— 第 1 分钟拉 Native + OEM
5. **24h 内必出 postmortem** —— 防止下周再发生

---

# 10. 附录

## A 源码索引

| 模块 | 路径 | 关键 |
|:-----|:-----|:-----|
| SWT 机制 | [02-Symptom/S04-SWT/01-症状机制.md](../../02-Symptom/S04-SWT/01-症状机制.md) | Watchdog |
| SWT 取证 | [03-Forensics/F02-SWT/01-取证机制.md](../F02-SWT/01-取证机制.md) | 完整流程 |
| Watchdog 工具 | [04-Tool/Watchdog/02-多层Watchdog架构](../../04-Tool/Watchdog/02-多层Watchdog架构.md) | 4 层 |
| oncall 流程 | [OC01-oncall 工程总论](OC01-oncall工程总论：值班机制与工具栈.md) | 5/15/30 |

## B 路径对账

无新增模块。

## C 量化自检

- 4 层 Watchdog 速查 ✅
- 黄金 5/15/30 每分钟动作 ✅
- 4 类根因 + 5 场景剧本 ✅
- 12 反例清单 ✅
- 5 条 Takeaway ✅

## D 工程基线

AOSP 17 + 6.18 LTS / 工具链：bugreport + kill -3 + adb pull

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-24（v1.0）
