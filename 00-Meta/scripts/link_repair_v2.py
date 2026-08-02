"""
link_repair_v2.py - 链接修复 v2：hardcode 5 档深度
"""
import re
from pathlib import Path

REPO = Path(r"C:\Users\deepLife\Documents\GitHub\smc-pub")

# 旧路径前缀（不含 ../）→ 新路径前缀（不含 ../）
PATH_MAP = [
    ("02-Symptom/S11-Startup/", "02-卷2-系统启动/"),
    ("02-Symptom/S08-AOSP17-K618/", "01-卷1-Android系统基础与平台/01-Android 系统全景与 AOSP 17/"),
    ("06-Foundation/Build-System/", "01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/"),
    ("06-Foundation/SELinux/", "01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/SELinux/"),
    ("06-Foundation/Dynamic-Updates/", "01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/Dynamic-Updates/"),
]

# 5 档深度（src 在深度 1-5）
DEPTH_LEVELS = [
    ("../../../", "../../../../", 4),  # src depth 4+ → 加 1 个 ../
    ("../../", "../../../", 3),  # src depth 3 → 加 1 个 ../
    ("../", "../../", 2),  # src depth 2 → 加 1 个 ../
]


def transform_link(text: str) -> str:
    """Transform all (../old/...) links in text. Returns (new_text, count)."""
    count = 0
    for old_dot, new_dot, _depth in DEPTH_LEVELS:
        for old_p, new_p in PATH_MAP:
            pattern = old_dot + old_p
            replacement = new_dot + new_p
            if pattern in text:
                text = text.replace(pattern, replacement)
                # 估算替换数（不精确）
                count += text.count(replacement) - text.count(replacement) // 2
    return text, count


def main():
    all_md = []
    exclude_prefixes = ["00-Meta/overrides", "00-Meta/reader", "00-Meta/web", "docs", "site", "_archive"]
    for p in REPO.rglob("*.md"):
        rel = p.relative_to(REPO).as_posix()
        if any(rel.startswith(d) for d in exclude_prefixes):
            continue
        all_md.append(p)
    print(f"[STEP] target: {len(all_md)} md files")

    total_files = 0
    total_replacements = 0
    for p in all_md:
        text = p.read_text(encoding="utf-8", errors="replace")
        new_text, n = transform_link(text)
        if new_text != text:
            p.write_text(new_text, encoding="utf-8")
            total_files += 1
            total_replacements += n

    print(f"[OK] changed {total_files} files, ~{total_replacements} replacements")


if __name__ == "__main__":
    main()
