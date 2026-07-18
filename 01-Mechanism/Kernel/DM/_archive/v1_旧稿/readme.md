# v1 旧稿归档

**归档时间**：2026-07-17
**归档原因**：v1 旧稿基于 Linux 5.10 单基线，不符合 v4 规范（缺源码 + 缺 4 附录 + 用了 mermaid），已被 v2 重写取代。

## v2 新版（当前主推）

请看：

- [README-DM系列.md](../../README-DM系列.md) — 系列总览 v2
- [01-DM开篇-DeviceMapper是什么.md](../../01-DM开篇-DeviceMapper是什么.md) — 第 01 篇 v2
- [02-DM架构-双态协同.md](../../02-DM架构-双态协同.md) — 第 02 篇 v2
- ...（10 篇）

## 归档内容

| 旧文件 | v2 替代 | 备注 |
|--------|---------|------|
| 1-开篇Device Mapper 是什么？.md | 01-DM开篇-DeviceMapper是什么.md | 重写 |
| 《架构篇 ...》.md | 02-DM架构-双态协同.md | 重写 |
| 《原理篇 ...》.md | 03-DM原理-设备诞生与IO旅程.md | 重写 |
| Android-DM.md | 07-DM-Android17应用全景.md | 骨架已扩展为完整文章 |
| readme.md | README-DM系列.md | 系列总览 v2 |

**v2 关键升级**：
- 基线：AOSP 14 + 5.10/5.15 → AOSP 17 + android17-6.18
- 规范：v3 → v4（按 PROMPT-技术系列文章写作指南-v4.md 重写）
- 图表：mermaid → ASCII Art
- 附录：补 A/B/C/D 4 个附录
- 决策日志：每篇含 3 轮校准决策
- 6.18 新基线独家：dm-pcache / sheaves / eBPF 签名 / bcachefs 移除
- Android 17 新基线独家：强制大屏自适应 / 端侧 LLM 存储

—— 决策日志见 README-DM系列.md v2.1
