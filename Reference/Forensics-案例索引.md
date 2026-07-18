# Forensics 系列案例索引

> **目的**：跨 Forensics 8 篇文章的案例统一编号、跨系列检索。
>
> **编号规则**：`CASE-FORENSICS-XX`（XX 为两位数字）
>   - FORENSICS = 取证
>   - 00 = F00 总览
>   - 01-07 = F01-F07
>   - 每篇预留 2 个编号
>
> **使用规则**：
> - Forensics 系列所有文章引用案例时，**必须用本表编号**
> - 跨系列引用 Forensics 案例时，同样用本表编号
> - 案例必须标注【典型模式】或【真实案例（来源）】

---

## 案例编号预留表

| 编号 | 所属文章 | 案例主题 | 类型 | 状态 |
|------|---------|---------|------|------|
| CASE-FORENSICS-00-01 | F00 | 取证体系全栈：ANR 触发到 traces 抓取 4 步法 | 【典型模式】 | 预留 |
| CASE-FORENSICS-00-02 | F00 | 公开 bugreport：症状 × 日志类型 2 维矩阵应用 | 【公开 bugreport】 | 预留 |
| CASE-FORENSICS-01-01 | F01 ANR | 主线程 onTouchEvent 30ms → anr traces 完整抓取 | 【典型模式】 | 预留 |
| CASE-FORENSICS-01-02 | F01 ANR | AOSP Issue 公开 bugreport：am-anr Input dispatching | 【公开 bugreport】 | 预留 |
| CASE-FORENSICS-02-01 | F02 SWT | AMS binder 阻塞 60s → watchdog traces + SystemServer Perfetto 抓取 | 【典型模式】 | 预留 |
| CASE-FORENSICS-02-02 | F02 SWT | AOSP Issue 公开 bugreport：PMS installPackage SWT | 【公开 bugreport】 | 预留 |
| CASE-FORENSICS-03-01 | F03 JE | 异步 HandlerThread OOM → dropbox(APP_CRASH) 完整抓取 | 【典型模式】 | 预留 |
| CASE-FORENSICS-03-02 | F03 JE | AOSP Issue 公开 bugreport：RecyclerView ConcurrentModification | 【公开 bugreport】 | 预留 |
| CASE-FORENSICS-04-01 | F04 NE | JNI IsAssignableFrom → tombstone + 符号化完整抓取 | 【典型模式】 | 预留 |
| CASE-FORENSICS-04-02 | F04 NE | AOSP Issue 公开 bugreport：art SIGSEGV in ClassLinker | 【公开 bugreport】 | 预留 |
| CASE-FORENSICS-05-01 | F05 KE | binder 驱动 mutex 死锁 → pstore + last_kmsg 抓取 | 【典型模式】 | 预留 |
| CASE-FORENSICS-05-02 | F05 KE | AOSP Issue 公开 bugreport：binder rust 死锁 | 【公开 bugreport】 | 预留 |
| CASE-FORENSICS-06-01 | F06 HANG | Volley 4.5s 软卡 → systrace + 主线程 P95 主动抓 | 【典型模式】 | 预留 |
| CASE-FORENSICS-06-02 | F06 HANG | AOSP Issue 公开 bugreport：f2fs IO hang 30s | 【公开 bugreport】 | 预留 |
| CASE-FORENSICS-07-01 | F07 治理 | APM 接入：Sentry 自动化 bugreport + 商业符号化 | 【典型模式】 | 预留 |
| CASE-FORENSICS-07-02 | F07 治理 | 公开案例：某团队 bugreport 自动化节省 70% 排查时间 | 【公开 bugreport】 | 预留 |

---

## 案例质量要求（v4 §4 质量清单 #8）

每个案例必须含：

1. **现象**：贴关键 logcat / dmesg / systrace 片段
2. **环境**：Android 版本 / 内核版本 / 设备 / 复现步骤
3. **取证路径**：触发 → 抓取 → dump 文件路径 → 解读 4 步完整
4. **dump 文件示例**：截取关键段（anr traces / tombstone / dropbox / etc.）
5. **类型标注**：【典型模式】或【真实案例（来源：xxx）】

> **判定标准**：把"取证路径"删掉，案例还能复现吗？不能 → 案例不合格。
> **本系列特别强调"取证路径 4 步法"**——这是 Forensics 的核心价值。

---

## 跨系列案例引用示例

```markdown
> **案例引用**：本案例与 [Stability S01](../../Stability/S01-ANR.md) 案例 A（CASE-STAB-01-01）同源，
> 但 Forensics 视角重点讲"ANR 触发后怎么抓 anr traces.txt"，Stability 视角重点讲"ANR 触发机制"。
> 两者互补，建议对照阅读。
```

---

## 维护规则

- **新增案例**：在本表"预留"位置填写案例信息，状态从【预留】改为【已撰写】
- **跨系列引用**：在引用方文章中加 Markdown 链接指向本表对应行
- **案例失效**：状态改为【失效，原因：xxx】，避免误导

---

> **版本**：v1.0（2026-07-18 与 Stability-Forensics 系列同步建立）
>
> **下次维护触发点**：Forensics 系列每篇文章撰写完成后，对应案例状态更新
