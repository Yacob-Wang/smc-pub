# 第 17 章　网络与连接

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：网络是移动端最大的环境变量——弱网导致的 ANR 与卡死需要专门的判定方法。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 17.1 网络协议栈：TCP / UDP / socket
- 17.2 ConnectivityService / NetworkAgent / 网络选路
- 17.3 WiFi / 移动数据 / VPN / 代理的切换时序
- 17.4 网络与耗电：信号弱 / 频繁重连 / DNS 超时
- 17.5 网络类 ANR 的判定：是网络慢还是服务阻塞
- 17.6 网络问题的现场采集

## 本章小结

网络 ANR ≠ 网络慢——大量案例实际是 ConnectivityService 或应用层锁阻塞。

---

**状态**：🚧 已有 17 篇，撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
