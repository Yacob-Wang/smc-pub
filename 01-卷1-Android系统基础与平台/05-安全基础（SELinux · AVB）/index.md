# 第 5 章　安全基础（SELinux / AVB）

> **所属卷**：卷 1　Android 系统基础与平台
> **章定位**：Android 安全模型——沙箱 + 权限 + SELinux + AVB。理解安全边界才能识别「看起来像 bug、实际是权限拒绝」的问题。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 5.1 Android 安全模型：沙箱 / UID / 权限 / 签名
- 5.2 SELinux：sepolicy / 域 / 类型 / 强制访问控制
- 5.3 权限框架：Android Permission / Runtime Permission / AppOps
- 5.4 AVB（Android Verified Boot）：启动验证链
- 5.5 权限拒绝类问题的调查方法：从 avc denied 反推策略

## 本章小结

权限失败 ≠ 应用问题，可能是 SELinux 拒绝或 AVB 校验失败——这类问题的日志特征与普通崩溃完全不同。

---

**状态**：🚧 已有 9 篇，撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
