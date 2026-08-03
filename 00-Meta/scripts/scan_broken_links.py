"""自己扫描所有 md 里的 markdown link，定位失效 link。"""
import re
from pathlib import Path
from collections import Counter, defaultdict

REPO = Path(r"C:\Users\deepLife\Documents\GitHub\smc-pub")
DOCS = REPO / "docs"  # mkdocs docs_dir

# markdown link: ](path) 或 ](path "title")
LINK_PAT = re.compile(r"\]\(([^)\s#]+)(?:\s+\"[^\"]*\")?\)")
# 但要排除外链 (http, mailto, #)
EXCLUDE_PAT = re.compile(r"^(?:https?:|mailto:|#|data:)")

# 所有已存在的 .md 文件路径（以 docs/ 为基准）
existing = set()
for p in DOCS.rglob("*.md"):
    rel = p.relative_to(DOCS).as_posix()
    existing.add(rel)

# 所有 .md 父目录（用于目录 link）
existing_dirs = set()
for p in DOCS.rglob("*.md"):
    rel = p.relative_to(DOCS).as_posix()
    parent = str(Path(rel).parent) + "/"
    existing_dirs.add(parent)
# 也加 index.md (mkdocs 目录隐式)
for d in [p.relative_to(DOCS).as_posix() + "/" for p in DOCS.rglob("") if p.is_dir()]:
    existing_dirs.add(d)

# 跑全 docs
bad = []  # (source_file, link, target_normalized)
ok = 0
for src in DOCS.rglob("*.md"):
    if "/.git" in str(src):
        continue
    if "/node_modules" in str(src):
        continue
    src_rel = src.relative_to(DOCS).as_posix()
    text = src.read_text(encoding="utf-8", errors="replace")
    for m in LINK_PAT.finditer(text):
        link = m.group(1)
        if EXCLUDE_PAT.match(link):
            continue
        if link.startswith("/"):
            # 绝对路径（从仓库根）
            target = link.lstrip("/")
        else:
            # 相对路径，从 src 解析
            src_dir = Path(src_rel).parent
            target = (src_dir / link).as_posix()
        # 去掉 query / fragment
        target = target.split("?")[0].split("#")[0]
        if not target:
            continue
        # 解析 .. 父目录
        target_parts = []
        for part in target.split("/"):
            if part == "..":
                if target_parts:
                    target_parts.pop()
            elif part and part != ".":
                target_parts.append(part)
        target_norm = "/".join(target_parts)

        # 检查存在性：直接是 md 文件 / 或目录（index.md 隐式）
        if target_norm in existing:
            ok += 1
            continue
        if (target_norm + "/index.md") in existing:
            ok += 1
            continue
        # target 可能是目录（不带 .md）
        if (target_norm.endswith("/") or not Path(target_norm).suffix) and target_norm + "index.md" in existing:
            ok += 1
            continue
        # target 是 .md 但 mkdocs 用 clean URL 实际渲染
        # 也允许 target.md 存在
        if target_norm + ".md" in existing:
            ok += 1
            continue
        # 父目录作为模块
        target_dir = target_norm + "/" if not target_norm.endswith("/") else target_norm
        if target_dir in existing_dirs:
            ok += 1
            continue
        bad.append((src_rel, link, target_norm))

print(f"[TOTAL] ok={ok} bad={len(bad)}")

by_link = Counter()
by_src = Counter()
for s, l, t in bad:
    by_link[l] += 1
    by_src[s] += 1

print("\n[Top 30 by broken link]")
for link, n in by_link.most_common(30):
    print(f"  {n:4d}  {link}")

print("\n[Top 30 by source file]")
for src, n in by_src.most_common(30):
    print(f"  {n:4d}  {src}")

# 存 raw bad 列表
out = REPO / "00-Meta" / "scripts" / "_bad_links.txt"
out.write_text(
    "\n".join(f"{s}\t{l}\t{t}" for s, l, t in bad),
    encoding="utf-8",
)
print(f"\n[SAVED] {out}")
