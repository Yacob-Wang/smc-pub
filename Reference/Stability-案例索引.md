# Stability 系列案例索引

> **目的**：跨 Stability 8 篇文章的案例统一编号、跨系列检索。
>
> **编号规则**：`CASE-STAB-XX`（XX 为两位数字）
>   - STAB = Stability
>   - 00 = S00 总览
>   - 01-07 = S01-S07
>   - 每篇预留 2 个编号
>
> **使用规则**：
> - Stability 系列所有文章引用案例时，**必须用本表编号**
> - 跨系列引用 Stability 案例时，同样用本表编号
> - 案例必须标注【典型模式】或【真实案例（来源）】

---

## 案例编号预留表

| 编号 | 所属文章 | 案例主题 | 类型 | 状态 |
|------|---------|---------|------|------|
| CASE-STAB-00-01 | S00 | cascade 链路：binder hang → ANR → SWT → REBOOT | 【典型模式】 | 预留 |
| CASE-STAB-00-02 | S00 | 公开 bugreport：AOSP issue 链 | 【公开 bugreport】 | 预留 |
| CASE-STAB-01-01 | S01 ANR | 主线程 onTouchEvent 同步操作 30ms → Input ANR | 【典型模式】 | 预留 |
| CASE-STAB-01-02 | S01 ANR | AOSP Issue 2314383 am-anr Input dispatching timeout | 【公开 bugreport】 | 预留 |
| CASE-STAB-02-01 | S02 JE | 异步 HandlerThread OOM 静默被杀 + dropbox 抓取 | 【典型模式】 | 预留 |
| CASE-STAB-02-02 | S02 JE | AOSP Issue 240112930 RecyclerView ConcurrentModification | 【公开 bugreport】 | 预留 |
| CASE-STAB-03-01 | S03 NE | JNI 未检查 IsAssignableFrom → SIGSEGV | 【典型模式】 | 预留 |
| CASE-STAB-03-02 | S03 NE | AOSP Issue 268068355 art SIGSEGV in ClassLinker | 【公开 bugreport】 | 预留 |
| CASE-STAB-04-01 | S04 SWT | AMS binder 调用主线程阻塞 60s → SWT 杀 SystemServer | 【典型模式】 | 预留 |
| CASE-STAB-04-02 | S04 SWT | AOSP Issue 290873281 PMS installPackage 阻塞 | 【公开 bugreport】 | 预留 |
| CASE-STAB-05-01 | S05 HANG | 主线程被 Volley 回调阻塞 4.5s（未到 5s 阈值） | 【典型模式】 | 预留 |
| CASE-STAB-05-02 | S05 HANG | AOSP Issue 264150921 f2fs IO hang | 【公开 bugreport】 | 预留 |
| CASE-STAB-06-01 | S06 REBOOT | SystemServer 反复重启 → pstore 抓 kernel log → GPU driver 卡死 | 【典型模式】 | 预留 |
| CASE-STAB-06-02 | S06 REBOOT | AOSP Issue 260500213 Zygote 死导致整机重启 | 【公开 bugreport】 | 预留 |
| CASE-STAB-07-01 | S07 KE | binder 驱动 mutex 死锁 → hung_task → pstore 取证 | 【典型模式】 | 预留 |
| CASE-STAB-07-02 | S07 KE | AOSP Issue 252354175 binder rust 死锁 | 【公开 bugreport】 | 预留 |

---

## 案例质量要求（v4 §4 质量清单 #8）

每个案例必须含：

1. **现象**：贴关键 logcat / dmesg / systrace / tombstone 片段
2. **环境**：Android 版本 / 内核版本 / 设备 / 复现步骤
3. **根因**：明确指出代码层 / 机制层根因
4. **修复**：贴修复 commit 或配置 diff
5. **类型标注**：【典型模式】或【真实案例（来源：xxx）】

> **判定标准**：把"环境"或"复现步骤"删掉，案例还能复现吗？不能 → 案例不合格。

---

## 跨系列案例引用示例

```markdown
> **案例引用**：本案例与 [Linux_Kernel/Binder](../../Linux_Kernel/Binder/) 系列
> [binder 死锁案例 CASE-BINDER-03](../../Linux_Kernel/Binder/CASE-BINDER-03.md) 同源，
> 但本案例从"症状视角"切入，重点讲排查路径而非内核机制。
```

---

## 维护规则

- **新增案例**：在本表"预留"位置填写案例信息，状态从【预留】改为【已撰写】
- **跨系列引用**：在引用方文章中加 Markdown 链接指向本表对应行
- **案例失效**：状态改为【失效，原因：xxx】，避免误导

---

> **版本**：v1.0（2026-07-18 与 Stability 系列同步建立）
>
> **下次维护触发点**：Stability 系列每篇文章撰写完成后，对应案例状态更新
