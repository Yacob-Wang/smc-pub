#!/usr/bin/env Python3
"""站点首页文案（Source.android.com 风格 — 简洁 header + 模块导览 + 问题索引）。

对比之前的版本：去掉了 Android 绿渐变 hero、CTA 按钮、3 步说明卡片；
改成轻量的 header（H1 + 简短 lead + chip 行）+ 8 大分类卡片 grid + 问题索引表格。
"""

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
title: Home
hide:
  - navigation
  - toc
---

<div class="jk-home-header" markdown="0">
  <h1>稳知库 · Android 稳定性架构师系列</h1>
  <p class="jk-home-header__lead">面向 Android 稳定性架构师的技术博客。从 Linux 内核到 Framework、从 ART 运行时到应用层，按 AOSP 系统分层 + oncall 工作流双轴组织 — 覆盖 Crash / ANR / OOM / 性能退化全部 11 大症状。</p>
  <div class="jk-home-header__meta">
    <span class="jk-chip jk-chip--accent">Author · JacobKing</span>
    <span class="jk-chip">AOSP 17 + android17-6.18</span>
    <span class="jk-chip">233 篇 · 8 大分类</span>
  </div>
</div>

<p class="jk-section-title"><strong>模块导览</strong></p>

<div class="jk-grid" markdown="0">
{cards_html}
</div>

<p class="jk-section-title"><strong>按问题进入</strong></p>

| 问题 | 入口 |
|------|------|
| **Native Crash** | [Native Crash](01-Mechanism/Runtime/Native_Crash/) |
| **Java 异常 / ANR** | [ANR 症状](02-Symptom/S01-ANR/) · [ANR 取证](03-Forensics/F01-ANR/) · [ANR-Detection](04-Tool/ANR-Detection/) |
| **Binder / IPC** | [Binder](01-Mechanism/Kernel/Binder/) |
| **OOM / 内存** | [内存管理](01-Mechanism/Kernel/Memory_Management/) · [ART](01-Mechanism/Runtime/ART/) · [Hprof](04-Tool/Hprof/) |
| **Watchdog / SWT** | [Watchdog](04-Tool/Watchdog/) · [SWT 取证](03-Forensics/F02-SWT/) |
| **Socket / epoll** | [Socket](01-Mechanism/Kernel/socket/) · [epoll](01-Mechanism/Kernel/epoll/) |
| **启动专项** | [S11 启动专项](02-Symptom/S11-Startup/) · [启动案例](06-Case/Startup/) · [Perfetto Boot Trace](04-Tool/Perfetto/) |
| **AOSP 17 + K 6.18 演进** | [S08 演进全景](02-Symptom/S08-AOSP17-K618/) |
| **性能 vs 稳定性** | [S09 横切专题](02-Symptom/S09-PerfVsStab/) |
| **度量 + 门禁** | [S10 度量门禁](02-Symptom/S10-Measure/) · [APM](05-Governance/APM/) |
| **OEM 厂商适配** | [OEM-BSP](05-Governance/OEM-BSP/) |
| **跨平台 / HarmonyOS** | [CrossPlatform](05-Governance/CrossPlatform/) |
| **低端机治理** | [LowEnd](05-Governance/LowEnd/) |
| **端侧 AI / AI OS** | [AI Native](05-Governance/AI-Native/) · [AI for Stability](05-Governance/AI-Native/03_AI_for_Stability/) |
| **AI 辅助调试** | [AI-Debug](05-Governance/AI-Debug/) |
| **性能 vs 内存** | [PerfMem](05-Governance/PerfMem/) |
| **安全 + 稳定性** | [Security](05-Governance/Security/) |

{{: .jk-quick }}

<p class="jk-foot">© JacobKing · Stability Matrix Course</p>
"""


def build_public_readme(repo_root: Path | None = None) -> str:
    _ = repo_root
    return build_reader_homepage()


def sanitize_readme(src: str) -> str:
    _ = src
    return build_reader_homepage()
