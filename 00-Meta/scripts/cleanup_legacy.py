"""清理 8 卷改造后的残留：旧 module 目录、重复元文档、一次性工作文档。

上一轮迁移把 102 篇正文搬进了 8 卷结构，但旧 module 目录里还剩 25 个
README.md 没处理——它们体积不小（10-30KB），当时按「正文」拦下了。

逐个看过之后分成两类：

  relocate  有实质内容的系列导读，并入对应卷/章，改名避开 index.md
  archive   描述旧目录结构的纯导航，进 _archive（站点不发布，git 留痕）

同时处理另外两处冗余：00-Meta 根与 Reference/ 下的同名重复文档，以及
一批已完成使命的迁移工作文档。

分阶段执行，可用 --phase 单独跑：
  readmes   旧 module README 的归位与归档
  dirs      删除已清空的旧 module 目录
  dedup     00-Meta 重复文档去重
  reflinks  把指向已删 Reference 副本的链接改指根副本
  workdocs  一次性工作文档归档
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ARCHIVE = "_archive"

V3 = "03-卷3-核心机制"
V4 = "04-卷4-诊断方法论与稳定性症状"
V7 = "07-卷7-APM与工程治理"

# 有实质内容的系列导读 → 目标路径（改名，避免和章节 index.md 冲突）
RELOCATE: list[tuple[str, str]] = [
    (
        "02-Symptom/README.md",
        f"{V4}/00-症状体系总览.md",
    ),
    (
        "03-Forensics/README.md",
        f"{V4}/00-取证体系总览.md",
    ),
    (
        "01-Mechanism/Kernel/Process/README.md",
        f"{V3}/13-进程与生命周期/00-Kernel进程系列导读.md",
    ),
    (
        "01-Mechanism/Framework/Service/README.md",
        f"{V3}/13-进程与生命周期/13.A-Android四大组件/00-Service系列导读.md",
    ),
    (
        "01-Mechanism/Framework/ContentProvider/README.md",
        f"{V3}/13-进程与生命周期/13.A-Android四大组件/00-ContentProvider系列导读.md",
    ),
    (
        "01-Mechanism/Framework/Broadcast/README.md",
        f"{V3}/13-进程与生命周期/13.A-Android四大组件/00-Broadcast系列导读.md",
    ),
    (
        "01-Mechanism/Kernel/IO/README.md",
        f"{V3}/16-IO 与存储/00-IO子系统系列导读.md",
    ),
    (
        "01-Mechanism/Runtime/ART/README.md",
        f"{V3}/20-ART 运行时/00-ART大模块总览.md",
    ),
    (
        "01-Mechanism/Runtime/ART/03-GC系统/README.md",
        f"{V3}/20-ART 运行时/20.C-GC系统/00-GC系统导读.md",
    ),
    (
        "05-Governance/AI-Native/03_AI_for_Stability/README.md",
        f"{V7}/46-AI-Native 调试/00-AI_for_Stability导读.md",
    ),
    (
        "05-Governance/AI-Native/04_AI_Engineering/README.md",
        f"{V7}/46-AI-Native 调试/00-AI工程实践导读.md",
    ),
]

# 描述旧 module / 旧文件夹结构的导航文档，内容已被各卷章的 index.md 取代，
# 且其目录树指向的路径大多已不存在。
ARCHIVE_README: list[str] = [
    "01-Mechanism/README.md",
    "04-Tool/README.md",
    "05-Governance/README.md",
    "06-Case/README.md",
    "06-Foundation/README.md",
    "06-Foundation/Tools/README.md",
    # Git 精通与本书主题无关
    "06-Foundation/Tools/Git_Mastery/README.md",
    # ART 各子目录的短导语，对应目录已重组为 20.A-20.E
    "01-Mechanism/Runtime/ART/01-字节码与指令集/README.md",
    "01-Mechanism/Runtime/ART/02-编译与执行/README.md",
    "01-Mechanism/Runtime/ART/03-类加载与链接/README.md",
    "01-Mechanism/Runtime/ART/05-JNI/README.md",
    "01-Mechanism/Runtime/ART/06-信号与ANR-Trace/README.md",
    "01-Mechanism/Runtime/ART/07-启动流程/README.md",
    "01-Mechanism/Runtime/ART/08-对比与演进/README.md",
]

LEGACY_DIRS = [
    "01-Mechanism",
    "02-Symptom",
    "03-Forensics",
    "04-Tool",
    "05-Governance",
    "06-Case",
    "06-Foundation",
]

# 00-Meta 根与 Reference/ 下的同名文档。根副本是顶栏导航的落点，保留；
# Reference/ 副本删除。术语表两份逐字节相同；案例索引与版本基线只差
# 相对路径深度（../ vs ../../），是同一份文档的不同深度拷贝。
DEDUP_DROP: list[str] = [
    "00-Meta/Reference/术语表.md",
    "00-Meta/Reference/案例索引.md",
    "00-Meta/Reference/版本基线.md",
]

# 已完成使命的一次性工作文档：迁移清单、长任务看板、写作准备等。
# 归档而非删除——里面记着为什么这么改，日后追溯有用。
WORKDOCS: list[str] = [
    "00-Meta/_rewrite_todo.md",
    "00-Meta/commit_list_msg.txt",
    "00-Meta/待替换清单-v1.md",
    "00-Meta/拟删除清单-v1.md",
    "00-Meta/章节-素材映射表-v1.md",
    "00-Meta/补全系列文章计划-v1.md",
    "00-Meta/缺项规划-P0补全路线图.md",
    "00-Meta/书籍改造-长任务看板.md",
    "00-Meta/书籍改造-整合后大纲-v1.md",
    "00-Meta/长任务清单-2026-08-02-重启.md",
    "00-Meta/第7章-Init进程-写作准备.md",
    "00-Meta/迁移日志.md",
]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8"
    )


def move(src_rel: str, dst_rel: str) -> bool:
    src, dst = REPO / src_rel, REPO / dst_rel
    if not src.exists():
        print(f"  skip (不存在) {src_rel}")
        return False
    if dst.exists():
        print(f"  !! 目标已存在，跳过 {dst_rel}")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    res = git("mv", src_rel, dst_rel)
    if res.returncode != 0:
        print(f"  !! git mv 失败 {src_rel}\n     {res.stderr.strip()}")
        return False
    print(f"  {src_rel}\n      → {dst_rel}")
    return True


def run_readmes() -> None:
    n = 0
    print("-- 归位（有实质内容的系列导读）--")
    for src, dst in RELOCATE:
        n += move(src, dst)
    print("-- 归档（描述旧目录结构的导航）--")
    for src in ARCHIVE_README:
        n += move(src, f"{ARCHIVE}/legacy-module-readmes/{src}")
    print(f"共处理 {n} 项")


def run_dirs() -> None:
    for d_rel in LEGACY_DIRS:
        d = REPO / d_rel
        if not d.exists():
            print(f"  skip (已清理) {d_rel}")
            continue
        leftovers = [
            p for p in d.rglob("*") if p.is_file() and p.name != "index.md"
        ]
        if leftovers:
            print(f"  !! {d_rel} 仍有 {len(leftovers)} 个文件，拒绝删除：")
            for p in leftovers[:5]:
                print(f"       {p.relative_to(REPO)}")
            continue
        res = git("rm", "-r", "-f", "-q", d_rel)
        if res.returncode != 0:
            # 目录里可能只剩未跟踪的 index.md，git rm 会报错，直接删
            import shutil

            shutil.rmtree(d)
            print(f"  已删除 {d_rel}（未跟踪残留）")
            continue
        print(f"  已删除 {d_rel}")


def run_dedup() -> None:
    for rel in DEDUP_DROP:
        p = REPO / rel
        if not p.exists():
            print(f"  skip (不存在) {rel}")
            continue
        res = git("rm", "-f", "-q", rel)
        if res.returncode != 0:
            print(f"  !! git rm 失败 {rel}\n     {res.stderr.strip()}")
            continue
        print(f"  已删除重复副本 {rel}")


LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+?)(\s+\"[^\"]*\")?\)")
SCAN_SKIP = {"_archive", "docs", "site", ".git", "node_modules"}


def _iter_markdown() -> list[Path]:
    out = []
    for p in REPO.rglob("*.md"):
        rel = p.relative_to(REPO)
        if rel.parts and rel.parts[0] in SCAN_SKIP:
            continue
        out.append(p)
    return out


def run_reflinks() -> None:
    """Reference/ 下的三份副本已删，把指过去的链接改指 00-Meta 根副本。"""
    names = {Path(rel).name for rel in DEDUP_DROP}
    ref_dir = (REPO / "00-Meta" / "Reference").resolve()
    n_files = n_links = 0

    for md in _iter_markdown():
        text = md.read_text(encoding="utf-8")

        def repl(m: re.Match) -> str:
            nonlocal n_links
            label, target, title = m.group(1), m.group(2), m.group(3) or ""
            path_part, sep, frag = target.partition("#")
            decoded = urllib.parse.unquote(path_part)
            if Path(decoded).name not in names:
                return m.group(0)
            if decoded.startswith(("http://", "https://", "/")):
                return m.group(0)
            try:
                resolved = (md.parent / decoded).resolve()
            except (OSError, ValueError):
                return m.group(0)
            if resolved.parent != ref_dir:
                return m.group(0)

            new_abs = REPO / "00-Meta" / resolved.name
            new_rel = Path(os.path.relpath(new_abs, md.parent)).as_posix()
            # 原链接把空格转义成 %20 时，新链接沿用同样的写法
            if "%20" in path_part:
                new_rel = new_rel.replace(" ", "%20")
            n_links += 1
            return f"[{label}]({new_rel}{sep}{frag}{title})"

        new_text = LINK_RE.sub(repl, text)
        if new_text != text:
            md.write_text(new_text, encoding="utf-8", newline="\n")
            n_files += 1
            print(f"  {md.relative_to(REPO)}")

    print(f"改写 {n_links} 条链接，涉及 {n_files} 个文件")


def run_workdocs() -> None:
    n = 0
    for rel in WORKDOCS:
        n += move(rel, f"{ARCHIVE}/legacy-workdocs/{Path(rel).name}")
    print(f"归档 {n} 份工作文档")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--phase",
        choices=["readmes", "dirs", "dedup", "reflinks", "workdocs", "all"],
        default="all",
    )
    args = ap.parse_args()

    if args.phase in ("readmes", "all"):
        print("=== 阶段 1：旧 module README ===")
        run_readmes()
    if args.phase in ("dirs", "all"):
        print("\n=== 阶段 2：删除旧 module 目录 ===")
        run_dirs()
    if args.phase in ("dedup", "all"):
        print("\n=== 阶段 3：00-Meta 去重 ===")
        run_dedup()
    if args.phase in ("reflinks", "all"):
        print("\n=== 阶段 4：修复指向 Reference 副本的链接 ===")
        run_reflinks()
    if args.phase in ("workdocs", "all"):
        print("\n=== 阶段 5：归档一次性工作文档 ===")
        run_workdocs()
    return 0


if __name__ == "__main__":
    sys.exit(main())
