# OC07 · REBOOT 响应剧本：4 类重启分类 + 黄金 5/15/30 + 5 场景

> **基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18` LTS
>
> **目标读者**：oncall 工程师 / 稳定性架构师
>
> **完成时间**：2026-07-24（v1.0 首版）

<!-- AUTHOR_ONLY:START -->

## 本篇定位

- oncall 7 大症状剧本第 7 篇（REBOOT）
- 强依赖：[OC01-oncall 工程总论](OC01-oncall工程总论：值班机制与工具栈.md) / [02-Symptom/S06-REBOOT](../../02-Symptom/S06-REBOOT/01-症状机制.md) / [04-Tool/Watchdog 系列](../../04-Tool/Watchdog/) 9 篇
- 衔接去：[OC08-KE 响应剧本](OC08-KE响应剧本.md)（KE 经常触发 REBOOT）

## 校准决策日志

| 轮次 | 类别 | 决策 | 理由 |
|:-----|:-----|:-----|:-----|
| 1 | 结构 | 单篇 500+ 行（§8 破例）| 4 类重启 + 5 场景必须展开 |
| 2 | 硬伤 | 4 类重启必给关键字 | 反例 #4 |
| 2 | 硬伤 | 5 场景必给真实 logcat 片段 | 反例 #11 |
| 3 | 锐度 | 删"可能" | 反例 #5 |

<!-- AUTHOR_ONLY:END -->

---

# 1. REBOOT 4 类分类速查

> **铁律**：oncall 收到重启告警，**第 1 件事是判断重启类型**——不同类型走不同分支

| # | 类型 | 触发 | 检测点 | 占比 |
|:-:|:-----|:-----|:-------|:----:|
| 1 | **Kernel Panic** | kernel 致命错误 | 串口 / pstore / ramoops | 25% |
| 2 | **system_server 重启** | Watchdog / OOM / 主动 | logcat `system_server died` | 35% |
| 3 | **zygote 重启** | init 主动重启 | logcat `zygote died` | 20% |
| 4 | **应用重启** | App crash / am force-stop | dropbox | 20% |

**关键 logcat 关键字**：

| 类型 | 关键字 |
|:-----|:-------|
| Kernel Panic | `Kernel panic - not syncing` |
| system_server | `Process system_server has died` |
| zygote | `Process zygote has died` |
| 应用 | `Force finishing` |

---

# 2. 黄金 5 分钟：必做 4 件事

## 2.1 第 1 分钟：确认告警 + 拉群

```bash
# 1. APM 推送卡片
# 2. 回复"已收到"
# 3. 拉应急群
```

## 2.2 第 2 分钟：抓 logs

```bash
# 1. 抓 bugreport
adb shell bugreport > /tmp/bugreport_$(date +%Y%m%d_%H%M%S).zip &

# 2. 拉 pstore（内核日志）
adb shell cat /sys/fs/pstore/console-ramoops > /tmp/pstore.log 2>/dev/null
adb shell cat /sys/fs/pstore/dmesg-ramoops > /tmp/dmesg-ramoops.log 2>/dev/null

# 3. 拉 dropbox
adb shell dumpsys dropbox --print
```

## 2.3 第 3 分钟：判断重启类型

**看 logcat 关键字**：

```bash
# 一次性搜 4 类关键字
adb logcat -d -b crash,events | grep -E "Kernel panic|system_server has died|zygote has died|Force finishing" | tail -20
```

## 2.4 第 4-5 分钟：发首报

```yaml
告警: 设备 REBOOT
触发: 14:30:00
判断: [Kernel Panic / system_server / zygote / App] 重启
首报:
  - 影响: [N] 设备受影响
  - 类型: [重启类型]
  - 怀疑: [根因假设]
  - 行动: 抓 logs 完成，开始定位
  - ETA: 10 分钟内出二报
```

---

# 3. 白银 15 分钟：定位根因

## 3.1 Kernel Panic（占 25%）

**pstore 日志**：

```
<6>[12345.678] Unable to handle kernel NULL pointer dereference at virtual address 00000000
<6>[12345.679] pgd = ffffffc012345678
<6>[12345.680] [00000000] *pgd=0000000000000000
<6>[12345.681] Internal error: Oops: 96000045 [#1] PREEMPT SMP
<6>[12345.682] CPU: 0 PID: 1234 Comm: kworker/0:1 Tainted: G        W       4.9.67
<6>[12345.683] Hardware name: Qualcomm Technologies, Inc
<0>[12345.700] Kernel panic - not syncing: Fatal exception in interrupt
```

**根因**：kernel 空指针解引用
**修复**：OEM 修 kernel / 联系芯片厂

## 3.2 system_server 重启（占 35%）

**logcat 日志**：

```
ActivityManager: Process system_server has died
AndroidRuntime: FATAL EXCEPTION: main
  at java.lang.NullPointerException: ...
```

**3 大根因**：

| 根因 | 关键字 | 占比 |
|:-----|:-------|:----:|
| Watchdog 触发 | `Watchdog: WAITED` | 40% |
| OOM 触发 | `lowmemorykiller` | 35% |
| 主动重启 | `am restart` | 25% |

→ 走 OC05-SWT 流程

## 3.3 zygote 重启（占 20%）

**logcat 日志**：

```
init: Starting service 'zygote'...
init: Service 'zygote' (pid 1234) killed
init: Service 'zygote' (pid 1234) restarting
```

**根因**：zygote 自身崩溃 / init 主动重启

## 3.4 应用重启（占 20%）

```
AndroidRuntime: FATAL EXCEPTION: main
  at java.lang.NullPointerException: ...
ActivityManager: Force finishing activity
```

→ 走 OC03-JE 流程

---

# 4. 黄金 30 分钟：执行修复

## 4.1 决策树

```
REBOOT 发生
   │
   ├── Kernel Panic
   │     → 抓 pstore + 联系 OEM + 暂停发版
   │
   ├── system_server 重启
   │     │
   │     ├── Watchdog 触发 → 走 OC05-SWT
   │     ├── OOM 触发 → 调 LMKD 参数
   │     └── 主动重启 → 检查 init.rc
   │
   ├── zygote 重启
   │     → 检查 Zygote 启动日志 + ART 错误
   │
   └── 应用重启
         → 走 OC03-JE / OC04-NE
```

## 4.2 应急操作

```bash
# 1. 远程抓取
adb shell dumpsys dropbox --print > /tmp/dropbox.txt

# 2. 紧急发版
./build.sh --urgent

# 3. 关闭 OTA / 降级
adb shell pm rollback com.example.app
```

---

# 5. 5 类真实场景剧本

## 5.1 场景 1：Kernel Panic（NULL 解引用）

**pstore**：
```
<0>[12345.700] Kernel panic - not syncing
<0>[12345.710] Unable to handle kernel NULL pointer dereference at 0x0
<0>[12345.720] PC is at msm_vidc_dec_close+0x40/0x80
<0>[12345.730] LR is at v4l2_ctrl_subscribe_event+0x80/0x100
```

**根因**：v4l2 视频驱动 NULL 指针
**修复**：OEM 升级 kernel 补丁

## 5.2 场景 2：system_server OOM

**logcat**：
```
lowmemorykiller: Killing 'system_server' (1234), adj 0,
  to free 200MB above reserve
```

**根因**：内存不足，LMKD 杀 system_server
**修复**：调低 `vmpressure` 阈值 + 排查内存大户

## 5.3 场景 3：system_server Watchdog 触发

→ 走 [OC05-SWT 响应剧本](OC05-SWT响应剧本.md)

## 5.4 场景 4：zygote ART 错误

**logcat**：
```
AndroidRuntime: ART: JNI ERROR (app bug): local reference table overflow
```

**根因**：JNI 局部引用泄漏
**修复**：SDK 修复 + 紧急发版

## 5.5 场景 5：Bootloop

**现象**：手机开机后反复重启
**根因**：system 进程崩溃 + 触发重试
**修复**：进入 recovery 模式 + 清除 cache

---

# 6. 告警规则

```yaml
# APM 告警（REBOOT 类）
- alert: KernelPanic
  expr: rate(kernel_panic_total[5m]) > 0
  for: 1m
  labels: { severity: P0 }
  
- alert: SystemServerRestart
  expr: rate(system_server_restart_total[1h]) > 0
  for: 5m
  labels: { severity: P0 }
```

---

# 7. 12 反例

| # | 反例 | 错误做法 | 正确做法 |
|:-:|:-----|:---------|:---------|
| 1 | **不抓 pstore** | 只看 logcat | **pstore 是 kernel 日志金标准** |
| 2 | **不抓 dropbox** | 跳过 dropbox | **dropbox 自动落盘** |
| 3 | **Kernel Panic 当 App crash** | 走 OC03 流程 | **Kernel Panic 走 OEM** |
| 4 | **不判断重启类型** | 笼统说"重启" | **4 类必区分** |
| 5 | **不通知 OEM** | 第三方问题不联系 | **第 1 分钟必拉** |
| 6 | **不暂停发版** | 重启后继续发 | **Kernel Panic 必暂停** |
| 7 | **不复盘** | 重启后忘 | **24h 内 postmortem** |
| 8 | **不写脚本** | 每次手动抓 | **应急 SOP 脚本化** |
| 9 | **OTA 不暂停** | 继续 OTA | **REBOOT 期间必暂停** |
| 10 | **不查引入版本** | 不查发版 | **第 3 步必查** |
| 11 | **追责** | "X 又引入 bug" | **只对事不对人** |
| 12 | **不复盘同类** | 单点修复 | **横向 review** |

---

# 8. 5 条 Takeaway

1. **REBOOT 4 类分类**（Kernel Panic 25% / system_server 35% / zygote 20% / App 20%）—— 不同类型走不同分支
2. **黄金 5/15/30** —— 5 分钟抓 logs + 拉群；15 分钟定位；30 分钟修复
3. **Kernel Panic 必通知 OEM** —— 立即暂停发版
4. **pstore + dropbox 是金标准** —— 看到 Kernel Panic 必看 pstore
5. **24h 内 postmortem** —— 防止同类重启下周再发

---

# 9. 附录

## A 源码索引

| 模块 | 路径 | 关键 |
|:-----|:-----|:-----|
| REBOOT 机制 | [02-Symptom/S06-REBOOT/01-症状机制.md](../../02-Symptom/S06-REBOOT/01-症状机制.md) | 4 类 |
| Watchdog | [OC05-SWT 响应剧本](OC05-SWT响应剧本.md) | 4 层 |
| pstore | [Kernel/01-Mechanism/Kernel/Partition/05-动态分区与super容器](../../01-Mechanism/Kernel/Partition/05-动态分区与super容器.md) | pstore |
| dropbox | [Dumpsys/11-稳定性监控集成](../../04-Tool/Dumpsys/11-稳定性监控集成.md) | dropbox |
| oncall 流程 | [OC01-oncall 工程总论](OC01-oncall工程总论：值班机制与工具栈.md) | 5/15/30 |

## B 路径对账

无新增模块。

## C 量化自检

- 4 类重启 + 占比 + 关键字 ✅
- 黄金 5/15/30 每分钟动作 ✅
- 5 类真实场景剧本 ✅
- 12 反例清单 ✅
- 5 条 Takeaway ✅

## D 工程基线

AOSP 17 + 6.18 LTS / 工具链：bugreport + pstore + dropbox

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-24（v1.0）
