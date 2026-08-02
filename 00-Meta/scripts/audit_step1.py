"""
smc-pub 内容审计 - 第 1 步：粗筛
- 输入：仓库根目录
- 输出：审计-待删清单-v1.md（清单 + 按规则分组的候选文件）
- 规则：纯机械判断，无主观判断
"""
import os
import re
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\deepLife\Documents\GitHub\smc-pub")
OUTPUT_MD = REPO_ROOT / "00-Meta" / "审计-待删清单-v1.md"

# 完全排除的目录
EXCLUDE_DIR_PARTS = {
    "00-Meta/overrides",
    "00-Meta/reader",
    "00-Meta/web",
    "docs",
    "site",
    ".git",
    "_archive",  # 单独处理为"整目录砍"
    "node_modules",
}

# 早期版本残留规则：-v2 / -v3 / -早期稿
# 注意：审计脚本自己（审计-待删清单-v1.md）也要排除
RE_EARLY_VERSION = re.compile(r"[-]v[2345](\.md)$|[-]v[2345][-]")
SELF_FILES = {
    "00-Meta/scripts/audit_step1.py",
    "00-Meta/审计-待删清单-v1.md",
}

# 短文件阈值
SHORT_FILE_BYTES = 500


def is_in_excluded_dir(p: Path) -> bool:
    rel = p.relative_to(REPO_ROOT).as_posix()
    return any(rel.startswith(d) for d in EXCLUDE_DIR_PARTS)


def categorize(p: Path) -> list[str]:
    """返回该文件命中的所有规则类别。"""
    rel = p.relative_to(REPO_ROOT).as_posix()
    categories = []
    if RE_EARLY_VERSION.search(p.name):
        categories.append("A_early_version")
    if p.stat().st_size == 0:
        categories.append("B_empty_file")
    if 0 < p.stat().st_size < SHORT_FILE_BYTES:
        categories.append("C_short_file")
    return categories


def is_empty_shell_readme(p: Path) -> str | None:
    """仅当文件是空壳子目录的 README 且内容 < 2000 字符，才算空壳。

    注意：S01-ANR 等目录下虽然只有 1 个 md，但每篇 28k-60k 字符，是真有效内容。
    """
    rel = p.relative_to(REPO_ROOT).as_posix()
    # 只有 README.md 且文件 < 2000 字符才算空壳
    if not rel.endswith("README.md"):
        return None
    if p.stat().st_size >= 2000:
        return None
    EMPTY_SHELL_DIRS = {
        "05-Governance/AI-Debug",
        "05-Governance/CrossPlatform",
        "05-Governance/LowEnd",
        "05-Governance/OEM-BSP",
        "05-Governance/PerfMem",
        "05-Governance/Security",
        "06-Case/Cases-Extended",
    }
    for shell in EMPTY_SHELL_DIRS:
        if rel == f"{shell}/README.md":
            return shell
    return None


def main():
    all_md = list(REPO_ROOT.rglob("*.md"))
    candidates: dict[str, list[tuple[str, str, int]]] = {
        "A_early_version": [],
        "B_empty_file": [],
        "C_short_file": [],
        "D_empty_shell": [],
        "E_archive": [],
    }

    for p in all_md:
        rel = p.relative_to(REPO_ROOT).as_posix()
        if rel in SELF_FILES:
            continue
        # _archive 子目录（仓库根 / Kernel/DM/）所有内容都砍
        if "_archive" in p.parts:
            size = p.stat().st_size
            candidates["E_archive"].append((rel, "E_整目录砍（_archive）", size))
            continue
        if is_in_excluded_dir(p):
            continue
        rel = p.relative_to(REPO_ROOT).as_posix()
        size = p.stat().st_size
        cats = categorize(p)
        shell = is_empty_shell_readme(p)
        if shell:
            candidates["D_empty_shell"].append((rel, f"D_空壳子目录 README（{shell}）", size))
        for c in cats:
            category_to_reason = {
                "A_early_version": "A_早期版本残留（*-v2/v3.md）",
                "B_empty_file": "B_空文件（0 字符）",
                "C_short_file": "C_短文件（< 500 字符，多为占位）",
            }
            candidates[c].append((rel, category_to_reason[c], size))

    # 输出报告
    lines: list[str] = []
    lines.append("# smc-pub 内容审计 — 第 1 步：粗筛（待删清单 v1）\n\n")
    lines.append(f"**生成时间**：{Path(__file__).stat().st_mtime}  ")
    lines.append(f"**审计范围**：smc-pub 仓库根目录下所有 .md   \n")
    lines.append(f"**排除目录**：`00-Meta/overrides` / `00-Meta/reader` / `00-Meta/web` / `docs` / `site` / `.git`\n\n")
    lines.append("---\n\n")

    total = 0
    for key in ["E_archive", "A_early_version", "B_empty_file", "D_empty_shell", "C_short_file"]:
        items = candidates[key]
        if not items:
            continue
        total += len(items)
        title_map = {
            "E_archive": "E. _archive 整目录（早期稿 + 旧 prompt）",
            "A_early_version": "A. 早期版本残留（*-v2/v3.md）",
            "B_empty_file": "B. 空文件（0 字符）",
            "D_empty_shell": "D. 空壳子目录（只有 README，无内容）",
            "C_short_file": "C. 短文件（< 500 字符，疑似占位）",
        }
        lines.append(f"## {title_map[key]}  ({len(items)} 个)\n\n")
        # 去重
        seen = set()
        for rel, reason, size in sorted(items):
            if rel in seen:
                continue
            seen.add(rel)
            lines.append(f"- `{rel}` ({size} 字符) — {reason}\n")
        lines.append("\n")

    lines.append(f"---\n\n**合计待删**：{total} 个文件\n\n")
    lines.append("## 处理建议\n\n")
    lines.append("- **A / B / D / E** 类：明确要删，**进入第 1 步执行**\n")
    lines.append("- **C 类**（短文件 < 500 字符）：需要人工评审，可能是有意简短的索引页（README / 索引 / 概览），**先列出但本次不删**\n\n")
    lines.append("## 砍后预估\n\n")
    lines.append(f"- 砍前总篇数：~{len(all_md) - sum(1 for p in all_md if is_in_excluded_dir(p) and '_archive' not in p.parts)}\n")
    lines.append(f"- 砍后预估：~{len(all_md) - sum(1 for p in all_md if is_in_excluded_dir(p) and '_archive' not in p.parts) - total + len(candidates['C_short_file'])}\n")

    OUTPUT_MD.write_text("".join(lines), encoding="utf-8")
    print(f"[OK] 清单已写到: {OUTPUT_MD}")
    print(f"    共发现 {total} 个待删候选")
    print(f"    A 早期版本: {len(candidates['A_early_version'])}")
    print(f"    B 空文件:   {len(candidates['B_empty_file'])}")
    print(f"    C 短文件:   {len(candidates['C_short_file'])} (本次不删，列参考)")
    print(f"    D 空壳:     {len(candidates['D_empty_shell'])}")
    print(f"    E archive:  {len(candidates['E_archive'])}")


if __name__ == "__main__":
    main()
