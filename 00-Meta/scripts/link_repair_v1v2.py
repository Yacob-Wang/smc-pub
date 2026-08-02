"""
link_repair_v1v2.py - 链接修复（处理卷 1+2 迁移造成的断）
不处理"原本就断"的链接（如 Kernel/FS/ 这种拼写错误）
"""
import re
from pathlib import Path

REPO = Path(r"C:\Users\deepLife\Documents\GitHub\smc-pub")

# 路径前缀映射（旧 → 新），按从具体到通用排序
# 注意：保留 ../ 数量，src 前缀包括完整 ../ 链
PATH_PREFIX_MAP = [
    # 卷 2 系统启动（depth 2-3 的文章引用 ../S11-Startup/，深度增加 1 级）
    ("../../../02-Symptom/S11-Startup/",
     "../../../../02-卷2-系统启动/"),
    ("../../02-Symptom/S11-Startup/",
     "../../../02-卷2-系统启动/"),
    ("../02-Symptom/S11-Startup/",
     "../../02-卷2-系统启动/"),
    # 绝对路径（少数文章用）
    ("/02-Symptom/S11-Startup/",
     "/02-卷2-系统启动/"),
    # 卷 1 第 1 章（来自 02-Symptom/S08）
    ("../../../02-Symptom/S08-AOSP17-K618/",
     "../../../../01-卷1-Android系统基础与平台/01-Android 系统全景与 AOSP 17/"),
    ("../../02-Symptom/S08-AOSP17-K618/",
     "../../../01-卷1-Android系统基础与平台/01-Android 系统全景与 AOSP 17/"),
    ("../02-Symptom/S08-AOSP17-K618/",
     "../../01-卷1-Android系统基础与平台/01-Android 系统全景与 AOSP 17/"),
    # 卷 1 第 2 章（来自 06-Foundation/Build-System）
    ("../../../06-Foundation/Build-System/",
     "../../../../01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/"),
    ("../../06-Foundation/Build-System/",
     "../../../01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/"),
    ("../06-Foundation/Build-System/",
     "../../01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/"),
    # 卷 1 第 5 章（来自 06-Foundation/SELinux / Dynamic-Updates）
    ("../../../06-Foundation/SELinux/",
     "../../../../01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/SELinux/"),
    ("../../06-Foundation/SELinux/",
     "../../../01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/SELinux/"),
    ("../06-Foundation/SELinux/",
     "../../01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/SELinux/"),
    ("../../../06-Foundation/Dynamic-Updates/",
     "../../../../01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/Dynamic-Updates/"),
    ("../../06-Foundation/Dynamic-Updates/",
     "../../../01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/Dynamic-Updates/"),
    ("../06-Foundation/Dynamic-Updates/",
     "../../01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/Dynamic-Updates/"),
    # 绝对路径
    ("/02-Symptom/S08-AOSP17-K618/",
     "/01-卷1-Android系统基础与平台/01-Android 系统全景与 AOSP 17/"),
    ("/06-Foundation/Build-System/",
     "/01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/"),
    ("/06-Foundation/SELinux/",
     "/01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/SELinux/"),
    ("/06-Foundation/Dynamic-Updates/",
     "/01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/Dynamic-Updates/"),
]

# Markdown link 模式： ](path) 或 ](path "title")
LINK_PATTERN = re.compile(r"\](\([^\)]+\))")


def repair_file(path: Path) -> tuple[int, str]:
    """Repair links in a single file. Returns (count, new_text)."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return 0, ""
    original = text
    count = 0
    for old_prefix, new_prefix in PATH_PREFIX_MAP:
        if old_prefix in text:
            text = text.replace(old_prefix, new_prefix)
            # 简化：不精确算 count，只在变化时 +1
    if text != original:
        path.write_text(text, encoding="utf-8")
        # 计算大致替换次数
        count = sum(original.count(o) - text.count(o) for o, _ in PATH_PREFIX_MAP)
    return max(count, 0), text


def main():
    # 只处理卷 1+2 内部（因为只有它们搬了）
    target_dirs = [
        REPO / "01-卷1-Android系统基础与平台",
        REPO / "02-卷2-系统启动",
        # 也扫卷 3-8 因为他们可能引用卷 1+2 内容
        REPO / "00-Meta",  # 00-Meta 也可能引用 S11-Startup
    ]
    all_md = []
    for d in target_dirs:
        if d.exists():
            all_md.extend(d.rglob("*.md"))
    print(f"[STEP] target: {len(all_md)} md files in {len(target_dirs)} dirs")

    # 全仓扫也包括其他 module（但只对搬运过的路径生效）
    extra = [
        REPO / "01-Mechanism", REPO / "02-Symptom", REPO / "03-Forensics",
        REPO / "04-Tool", REPO / "05-Governance", REPO / "06-Case", REPO / "06-Foundation",
    ]
    for d in extra:
        if d.exists():
            all_md.extend(d.rglob("*.md"))
    print(f"[STEP] all md (incl other modules): {len(all_md)}")

    total_files_changed = 0
    total_replacements = 0
    changed_files = []
    for p in all_md:
        if "_archive" in p.parts:
            continue
        if any(p.as_posix().startswith(d) for d in ["00-Meta/overrides", "00-Meta/reader", "00-Meta/web", "docs", "site"]):
            continue
        c, _ = repair_file(p)
        if c > 0:
            total_files_changed += 1
            total_replacements += c
            changed_files.append((p, c))

    print()
    print(f"[OK] changed {total_files_changed} files, {total_replacements} replacements")
    print()
    print("Sample changes (first 10):")
    for p, c in changed_files[:10]:
        print(f"  {p.relative_to(REPO)} ({c})")


if __name__ == "__main__":
    main()
