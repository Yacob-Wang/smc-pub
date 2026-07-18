#!/usr/bin/env python3
"""
修复 smc-pub 仓库中指向已删除兼容层的跨文档引用。

兼容层 → 新结构映射（按"相对深度"统一处理）：
  Android_Framework/Activity/             → 01-Mechanism/Framework/Activity/
  Android_Framework/Service/              → 01-Mechanism/Framework/Service/
  Android_Framework/Broadcast/            → 01-Mechanism/Framework/Broadcast/
  Android_Framework/ContentProvider/      → 01-Mechanism/Framework/ContentProvider/
  Android_Framework/Input/                → 01-Mechanism/Framework/Input/
  Android_Framework/Window/               → 01-Mechanism/Framework/Window/
  Android_Framework/Process/              → 01-Mechanism/Framework/Process/
  Android_Framework/AOSP_Startup/         → 02-Symptom/S11-Startup/  (但 README 留 02-Symptom/S11-Startup/README.md)
  Android_Framework/Stability/            → 02-Symptom/
  Android_Framework/Stability-Forensics/  → 03-Forensics/
  Android_Framework/Dumpsys/              → 04-Tool/Dumpsys/
  Android_Framework/Watchdog/             → 04-Tool/Watchdog/
  Android_Framework/Perfetto/             → 04-Tool/Perfetto/
  Android_Framework/Hprof/                → 04-Tool/Hprof/
  Android_Framework/AmCommand/            → 04-Tool/AmCommand/
  Android_Framework/ANR_Detection/        → 04-Tool/ANR-Detection/
  Android_Framework/Build_System/         → 06-Foundation/Build-System/
  Android_Framework/System_Integration/   → 06-Foundation/System-Integration/
  Android_Framework/Dynamic_Updates/      → 06-Foundation/Dynamic-Updates/
  Android_Framework/Reference/            → 00-Meta/Reference/
  Linux_Kernel/                            → 01-Mechanism/Kernel/
  Runtime/                                 → 01-Mechanism/Runtime/
  Hook/                                    → 01-Mechanism/App/Hook/
  App/Handler_MessageQueue_Looper/         → 01-Mechanism/App/Handler-MessageQueue-Looper/  (子目录名也改)
  AI_Native_X/                             → 05-Governance/AI-Native/
  Tools/                                   → 06-Foundation/Tools/

由于引用是相对路径 (../+.../X/...)，前缀 `../` 的数量由文件所在位置决定；
本脚本通过"取被替换前缀后的部分 + 新前缀"统一处理。
"""

import os
import re
from pathlib import Path

ROOT = Path(r"C:\Users\deepLife\Documents\GitHub\smc-pub")

# 旧前缀 → 新前缀（不含 ../）
LEGACY_MAP = [
    # Android_Framework 优先级最高（先匹配更具体）
    ("Android_Framework/Activity", "01-Mechanism/Framework/Activity"),
    ("Android_Framework/Service", "01-Mechanism/Framework/Service"),
    ("Android_Framework/Broadcast", "01-Mechanism/Framework/Broadcast"),
    ("Android_Framework/ContentProvider", "01-Mechanism/Framework/ContentProvider"),
    ("Android_Framework/Input", "01-Mechanism/Framework/Input"),
    ("Android_Framework/Window", "01-Mechanism/Framework/Window"),
    ("Android_Framework/Process", "01-Mechanism/Framework/Process"),
    ("Android_Framework/AOSP_Startup", "02-Symptom/S11-Startup"),
    ("Android_Framework/Stability-Forensics", "03-Forensics"),
    ("Android_Framework/Stability", "02-Symptom"),
    ("Android_Framework/Dumpsys", "04-Tool/Dumpsys"),
    ("Android_Framework/Watchdog", "04-Tool/Watchdog"),
    ("Android_Framework/Perfetto", "04-Tool/Perfetto"),
    ("Android_Framework/Hprof", "04-Tool/Hprof"),
    ("Android_Framework/AmCommand", "04-Tool/AmCommand"),
    ("Android_Framework/ANR_Detection", "04-Tool/ANR-Detection"),
    ("Android_Framework/Build_System", "06-Foundation/Build-System"),
    ("Android_Framework/System_Integration", "06-Foundation/System-Integration"),
    ("Android_Framework/Dynamic_Updates", "06-Foundation/Dynamic-Updates"),
    ("Android_Framework/Reference", "00-Meta/Reference"),
    # 顶层兼容层
    ("Linux_Kernel", "01-Mechanism/Kernel"),
    ("Runtime", "01-Mechanism/Runtime"),
    ("Hook", "01-Mechanism/App/Hook"),
    ("App/Handler_MessageQueue_Looper", "01-Mechanism/App/Handler-MessageQueue-Looper"),
    ("AI_Native_X", "05-Governance/AI-Native"),
    ("Tools", "06-Foundation/Tools"),
]

# 匹配 (\./)*\.\./<legacy>/<rest> 或 \./<legacy>/<rest>
PATH_RE = re.compile(r"(\.{1,2}/)+(?:[^/\s`)\]\"'<>]+/)*(" + "|".join(re.escape(k) for k, _ in LEGACY_MAP) + r")(/[^)\]\\s\"'<>]*)?")

def fix_path(m: re.Match) -> str:
    leading = m.group(1) or ""  # "../" or "./"
    legacy_key = m.group(2)
    tail = m.group(3) or ""
    new_prefix = next(v for k, v in LEGACY_MAP if k == legacy_key)
    return leading + new_prefix + tail

def process(file: Path) -> int:
    text = file.read_text(encoding="utf-8")
    new_text, n = PATH_RE.subn(fix_path, text)
    if n > 0:
        file.write_text(new_text, encoding="utf-8")
    return n

def main():
    md_files = list(ROOT.rglob("*.md"))
    # 排除 .git/.idea/.github/reader/web/node_modules
    skip = {".git", ".idea", ".github", "reader", "web", "node_modules"}
    total = 0
    touched = []
    for f in md_files:
        if any(part in skip for part in f.parts):
            continue
        # 不要递归进 reader/ web/ 这些二进制/模板
        rel = f.relative_to(ROOT)
        if rel.parts[0] in {"reader", "web"}:
            continue
        n = process(f)
        if n > 0:
            touched.append((str(rel), n))
            total += n
    print(f"=== Fixed {total} references in {len(touched)} files ===")
    for path, n in sorted(touched, key=lambda x: -x[1])[:20]:
        print(f"  [{n:3d}] {path}")

if __name__ == "__main__":
    main()
