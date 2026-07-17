#!/usr/bin/env python3
"""站点首页文案（与仓库 README 导航结构对齐，供 MkDocs 使用）。"""

from __future__ import annotations

from pathlib import Path


def build_reader_homepage() -> str:
    return """# 稳知库 · Stability Matrix Course

面向 **Android 稳定性架构师** 的系列技术博客。

从 Linux 内核到 Framework、从运行时到应用层，按「定位 → 边界 → 核心机制 → 风险 → 诊断治理」组织，便于排查 Crash / ANR / OOM。

---

## 怎么读

1. 顶栏或左侧进入模块
2. 打开某个**系列 README**（总览 + 篇章表）
3. 按表内链接阅读；也可用顶部搜索

---

## 模块

| 模块 | 说明 |
|------|------|
| [Linux 内核](Linux_Kernel/) | 进程 / 内存 / IO / Binder / Socket / epoll / 分区 … |
| [运行时 / ART](Runtime/) | ART、Java Crash、Native Crash |
| [Android Framework](Android_Framework/) | 进程、ANR、Watchdog、Input、Window … |
| [应用层](App/) | Handler / MessageQueue / Looper |
| [工具](Tools/) | 调试、追踪、内存分析、Git … |
| [Hook 专题](Hook/) | OEM Hook 等 |
| [AI Native](AI_Native_X/) | 端侧 AI Runtime / AI OS / AI for Stability / AI 工程 |

## 按问题进入

| 问题 | 入口 |
|------|------|
| Java Crash | [Runtime/Java_Crash](Runtime/Java_Crash/) |
| Native Crash | [Runtime/Native_Crash](Runtime/Native_Crash/) |
| ANR | [ANR_Detection](Android_Framework/ANR_Detection/)、[Input](Android_Framework/Input/) |
| Binder | [Linux_Kernel/Binder](Linux_Kernel/Binder/) |
| OOM / 内存 | [Memory_Management](Linux_Kernel/Memory_Management/)、[ART](Runtime/ART/) |
| Watchdog | [Android_Framework/Watchdog](Android_Framework/Watchdog/) |
| Socket / epoll | [socket](Linux_Kernel/socket/)、[epoll](Linux_Kernel/epoll/) |
| 端侧 AI | [AI_Native_X](AI_Native_X/) |

---

技术基线：AOSP 17 + android17-6.18

© Stability Matrix Course
"""


def build_public_readme(repo_root: Path | None = None) -> str:
    _ = repo_root
    return build_reader_homepage()


def sanitize_readme(src: str) -> str:
    _ = src
    return build_reader_homepage()
