#!/usr/bin/env python3
"""站点首页文案（分层导航，避免信息堆叠）。"""

from __future__ import annotations

from pathlib import Path

from content_policy import MODULE_BLURBS, MODULE_TITLES, PUBLIC_MODULES


def build_reader_homepage() -> str:
    module_blocks: list[str] = []
    for mod in PUBLIC_MODULES:
        title = MODULE_TITLES.get(mod, mod)
        blurb = MODULE_BLURBS.get(mod, "")
        module_blocks.append(f"### [{title}]({mod}/)\n\n{blurb}\n")

    modules_md = "\n".join(module_blocks)

    return f"""# 稳知库 · Stability Matrix Course

面向 **Android 稳定性架构师** 的系列技术博客。

从 Linux 内核到 Framework、从运行时到应用层，按「定位 → 边界 → 核心机制 → 风险 → 诊断治理」组织。

!!! tip "阅读路径（三步）"
    1. **顶栏**选择模块（如 Linux 内核）
    2. **左侧**进入某个系列，打开「系列总览」
    3. 在总览的**篇章表**里点进单篇；也可用顶部搜索

---

## 模块

{modules_md}
---

## 按问题进入

需要排查具体问题时，可从这里直达相关系列：

| 问题 | 入口 |
|------|------|
| Java Crash | [Runtime / ART](Runtime/ART/) |
| Native Crash | [Native Crash](Runtime/Native_Crash/) |
| ANR | [ANR 检测](Android_Framework/ANR_Detection/)、[Input](Android_Framework/Input/) |
| Binder | [Binder](Linux_Kernel/Binder/) |
| OOM / 内存 | [内存管理](Linux_Kernel/Memory_Management/)、[ART](Runtime/ART/) |
| Watchdog | [Watchdog](Android_Framework/Watchdog/) |
| Socket / epoll | [Socket](Linux_Kernel/socket/)、[epoll](Linux_Kernel/epoll/) |
| 端侧 AI | [AI Native](AI_Native_X/) |

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
