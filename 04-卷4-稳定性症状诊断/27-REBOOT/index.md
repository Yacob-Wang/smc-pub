# 第 27 章　REBOOT

> **所属卷**：卷 4　稳定性症状诊断
> **章定位**：重启栈是唯一能告诉你为什么重启的证据，必须保留。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 27.1 重启类型分类：kernel panic / native restart / 异常掉电 / 用户操作
- 27.2 kernel panic：分析流程
- 27.3 native restart：watchdog / panic 重启
- 27.4 异常掉电：under-voltage / 异常关机 / 死机
- 27.5 重启栈分析：last_kmsg / pstore / ramoops / console-ramoops
- 27.6 重启率治理：监控 / 告警 / 防御

## 本章小结

重启栈是唯一能告诉你为什么重启的证据，必须保留。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
