#!/usr/bin/env python3
"""站点首页文案（卡片式模块布局）。"""

from __future__ import annotations

from pathlib import Path

from content_policy import MODULE_BLURBS, MODULE_TITLES, PUBLIC_MODULES


def build_reader_homepage() -> str:
    cards: list[str] = []
    for mod in PUBLIC_MODULES:
        title = MODULE_TITLES.get(mod, mod)
        blurb = MODULE_BLURBS.get(mod, "")
        cards.append(
            f'<a class="jk-card" href="{mod}/">'
            f'<div class="jk-card__title">{title}</div>'
            f'<p class="jk-card__desc">{blurb}</p>'
            f'<span class="jk-card__arrow">进入模块 →</span>'
            f"</a>"
        )
    cards_html = "\n".join(cards)

    return f"""---
title: 首页
hide:
  - navigation
  - toc
---

<div class="jk-hero" markdown="0">
  <h1>稳知库 · Stability Matrix Course</h1>
  <p class="jk-hero__lead">面向 Android 稳定性架构师的系列技术博客。从 Linux 内核到 Framework、从运行时到应用层，按「定位 → 边界 → 核心机制 → 风险 → 诊断治理」组织。</p>
  <div class="jk-hero__meta">
    <span class="jk-chip jk-chip--accent">Author · JacobKing</span>
    <span class="jk-chip">AOSP 17 + android17-6.18</span>
    <span class="jk-chip">Crash / ANR / OOM</span>
  </div>
</div>

<ol class="jk-steps" markdown="0">
  <li><strong>选模块</strong><span>顶栏切换 Linux 内核 / 运行时 / Framework 等</span></li>
  <li><strong>进系列</strong><span>左侧打开「系列总览」，先看目录结构</span></li>
  <li><strong>读篇章</strong><span>从总览篇章表进入单篇，或用顶部搜索</span></li>
</ol>

<p class="jk-section-title"><strong>模块</strong></p>

<div class="jk-grid" markdown="0">
{cards_html}
</div>

<p class="jk-section-title"><strong>按问题进入</strong></p>

| 问题 | 入口 |
|------|------|
| Native Crash | [Native Crash](Runtime/Native_Crash/) |
| ANR | [ANR 检测](Android_Framework/ANR_Detection/)、[Input](Android_Framework/Input/) |
| Binder | [Binder](Linux_Kernel/Binder/) |
| OOM / 内存 | [内存管理](Linux_Kernel/Memory_Management/)、[ART](Runtime/ART/) |
| Watchdog | [Watchdog](Android_Framework/Watchdog/) |
| Socket / epoll | [Socket](Linux_Kernel/socket/)、[epoll](Linux_Kernel/epoll/) |
| 端侧 AI | [AI Native](AI_Native_X/) |

{{: .jk-quick }}

<p class="jk-foot">© JacobKing · Stability Matrix Course</p>
"""


def build_public_readme(repo_root: Path | None = None) -> str:
    _ = repo_root
    return build_reader_homepage()


def sanitize_readme(src: str) -> str:
    _ = src
    return build_reader_homepage()
