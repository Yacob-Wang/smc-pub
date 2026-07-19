"""把 01-Mechanism/Framework/SystemServer/A04-Zygote+SystemServer.md 的引用，重写到 02-Symptom 版本"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# (src_dir, old_path_pattern, new_path)
REPLACEMENTS = [
    (
        "01-Mechanism/Hardware",
        re.compile(r"\]\(\.\./Framework/SystemServer/A04-Zygote\+SystemServer\.md(#[^)]*)?\)"),
        r"](../../../02-Symptom/S11-Startup/A-启动机制/A04-Zygote+SystemServer.md\1)",
    ),
    (
        "06-Case/Startup",
        re.compile(r"\]\(\.\./\.\./01-Mechanism/Framework/SystemServer/A04-Zygote\+SystemServer\.md(#[^)]*)?\)"),
        r"](../../02-Symptom/S11-Startup/A-启动机制/A04-Zygote+SystemServer.md\1)",
    ),
]

total_files = 0
total_changes = 0
for src_dir_rel, pattern, replacement in REPLACEMENTS:
    src_dir = REPO / src_dir_rel
    for fp in src_dir.rglob("*.md"):
        text = fp.read_text(encoding="utf-8", errors="replace")
        orig = text
        text = pattern.sub(replacement, text)
        if text != orig:
            fp.write_text(text, encoding="utf-8")
            total_files += 1
            count = len(pattern.findall(orig))
            total_changes += count
            print(f"  {fp.relative_to(REPO)}: {count} changes")

print(f"\nTOTAL: {total_files} files, {total_changes} changes")
