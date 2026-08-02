# 第 17 章　网络与连接

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：网络 ANR ≠ 网络慢，可能是 ConnectivityService 阻塞。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 17.1 网络协议栈：TCP / UDP / socket
- 17.2 ConnectivityManager / NetworkAgent / NetworkFactory
- 17.3 WiFi / 移动数据 / VPN / 代理
- 17.4 Bluetooth / NFC / GPS
- 17.5 网络性能与耗电：网络切换 / 信号弱 / DNS 慢
- 17.6 网络类 ANR 调查：ConnectivityService / DataCall / Socket

## 本章小结

网络 ANR ≠ 网络慢，可能是 ConnectivityService 阻塞。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
