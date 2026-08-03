# 第 5 章　安全基础（SELinux / AVB）

> **所属卷**：卷 1　Android 系统基础与平台
> **章定位**：权限失败 ≠ 应用问题，可能是 SELinux 拒绝或 AVB 校验失败。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 5.1 Android 安全模型：沙箱 / UID / 权限 / 签名
- 5.2 SELinux：sepolicy / 域 / 类型 / 强制访问控制
- 5.3 AVB（Android Verified Boot）：启动验证链
- 5.4 权限框架：Android Permission / Runtime Permission / AppOps
- 5.5 权限拒绝类问题的调查方法

## 本章小结

权限失败 ≠ 应用问题，可能是 SELinux 拒绝或 AVB 校验失败。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
