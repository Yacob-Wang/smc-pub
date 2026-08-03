"""把滞留在旧 module 目录里的文章迁进 8 卷结构，并修复全库失效链接。

旧的 01-Mechanism / 02-Symptom / ... 目录里还有 102 篇正文从未进入
「8 卷 50 章」结构，对应章节反而是空的（例如第 18 章输入系统只有
index.md，而 28 篇 Input 文章滞留在旧目录）。这些文章不是新卷内容的
副本——文件名重合的只有 1 篇。

迁移按「系列整体进子目录」而非「打散成编号文件」，原因有二：系列内部
有大量互相引用，拆开会全部失效；现有章节的平铺编号已经出现撞车
（第 16 章有两个 01- 前缀），再塞进去会更乱。

分三个阶段，可用 --phase 单独跑：
  moves    git mv 系列目录与散篇（保留 git 历史）
  cleanup  git rm 只剩 index/README 骨架的旧目录
  links    全库链接修复（按 basename 反查唯一目标后重写相对路径）
"""

from __future__ import annotations

import argparse
import posixpath
import re
import subprocess
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

V1 = "01-卷1-Android系统基础与平台"
V3 = "03-卷3-核心机制"
V4 = "04-卷4-诊断方法论与稳定性症状"
V5 = "05-卷5-调查工具链"
V7 = "07-卷7-APM与工程治理"

# 系列目录 → 目标章节下的子目录。子目录名沿用各章已有的 N.X 命名习惯。
SERIES_MOVES: list[tuple[str, str]] = [
    (
        "01-Mechanism/Framework/Input",
        f"{V3}/18-输入系统/18.A-Framework 输入链路",
    ),
    (
        "01-Mechanism/Kernel/Input_Driver",
        f"{V3}/18-输入系统/18.B-Kernel 输入驱动全流程",
    ),
    (
        "01-Mechanism/Kernel/DM",
        f"{V3}/16-IO 与存储/16.D-Device Mapper",
    ),
    (
        "01-Mechanism/Kernel/epoll",
        f"{V3}/14-线程与 Handler 消息机制/14.A-epoll 与事件循环",
    ),
    (
        "01-Mechanism/Kernel/Program_Execution",
        f"{V3}/13-进程与生命周期/13.D-程序加载与执行链路",
    ),
    (
        "01-Mechanism/Kernel/GKI",
        f"{V1}/02-AOSP 源码结构与构建系统/2.A-GKI 与内核模块化",
    ),
    (
        "01-Mechanism/Kernel/Partition",
        f"{V1}/02-AOSP 源码结构与构建系统/2.B-分区架构演进",
    ),
    (
        "01-Mechanism/Kernel/Syscalls",
        f"{V1}/04-Linux Kernel 基础（Android 视角）/4.A-系统调用",
    ),
    (
        "05-Governance/AI-Native/01_AI_Native_Runtime",
        f"{V7}/46-AI-Native 调试/46.A-端侧 AI 运行时",
    ),
]

# 散篇 → 目标位置。dst 以 .md 结尾时视为完整目标路径（可顺带改名），
# 否则视为目标目录、保留原文件名。
FILE_MOVES: list[tuple[str, str]] = [
    (
        "01-Mechanism/Runtime/ART/08-对比与演进/04-监控与诊断基础设施.md",
        f"{V3}/20-ART 运行时/20.D-信号与Hook",
    ),
    (
        "01-Mechanism/Runtime/ART/README-ART系列.md",
        f"{V3}/20-ART 运行时",
    ),
    (
        "02-Symptom/S00-症状总览.md",
        f"{V4}/22-稳定性调查方法论",
    ),
    # 取证系列 F00-F06 已按症状分散到卷 4 各章，各自叫 01-取证机制.md。
    # F07 讲取证治理与 APM 接入，没有对应症状章，归卷 7；同时改名，
    # 否则和第 22 章的 F00 撞名。
    (
        "03-Forensics/F07-Governance/01-取证机制.md",
        f"{V7}/43-APM 架构与自研实践/01-取证治理：APM接入与bugreport自动化.md",
    ),
    (
        "06-Foundation/System-Integration/01_System_Composition_And_Boot.md",
        f"{V1}/01-Android 系统全景与 AOSP 17",
    ),
    (
        "06-Foundation/Tools/Android_Tools/04-Logcat与SELinux-avc-denied行解读.md",
        f"{V1}/05-安全基础（SELinux · AVB）",
    ),
    # 旧结构的元文档，和书稿正文无关，归到 00-Meta
    ("02-Symptom/README-学习路线.md", "00-Meta"),
    ("02-Symptom/README-质量评估.md", "00-Meta"),
]

# 旧目录里除了文章还有非 markdown 资产：Perfetto/Hprof 的配置、分析 SQL、
# 采集脚本，以及被正文引用的插图。这些跟着对应的工具章 / 文章走。
ASSET_MOVES: list[tuple[str, str]] = [
    ("04-Tool/Perfetto", f"{V5}/31-Perfetto 全栈使用/工具包"),
    ("04-Tool/Hprof", f"{V5}/34-Hprof 与内存分析/工具包"),
    ("04-Tool/AmCommand", f"{V5}/33-Dumpsys · Bugreport · DropBox/工具包"),
    # 这两张图被第 14 章的文章按同目录相对路径引用
    (
        "01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/img.png",
        f"{V3}/14-线程与 Handler 消息机制/img.png",
    ),
    (
        "01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/img_1.png",
        f"{V3}/14-线程与 Handler 消息机制/img_1.png",
    ),
]

# 正文与资产搬空后只剩 index/README 骨架，整体删除
LEGACY_DIRS = [
    "01-Mechanism",
    "02-Symptom",
    "03-Forensics",
    "04-Tool",
    "05-Governance",
    "06-Case",
    "06-Foundation",
]

SKIP_DIRS = {".git", "site", "docs", "_tmp", "node_modules", ".github", "tmp"}


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def run_moves() -> None:
    moved = 0
    for src_rel, dst_rel in SERIES_MOVES:
        src, dst = REPO / src_rel, REPO / dst_rel
        if not src.exists():
            print(f"  skip (已迁移) {src_rel}")
            continue
        if dst.exists():
            print(f"  !! 目标已存在，跳过 {dst_rel}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        res = git("mv", src_rel, dst_rel)
        if res.returncode != 0:
            print(f"  !! git mv 失败 {src_rel}\n     {res.stderr.strip()}")
            continue
        n = len(list(dst.rglob("*.md")))
        print(f"  {src_rel}  →  {dst_rel}  ({n} 篇)")
        moved += 1

    for src_rel, dst_rel in FILE_MOVES:
        src = REPO / src_rel
        dst = (
            REPO / dst_rel
            if dst_rel.endswith(".md")
            else REPO / dst_rel / Path(src_rel).name
        )
        if not src.exists():
            print(f"  skip (已迁移) {src_rel}")
            continue
        if dst.exists():
            print(f"  !! 目标已存在，跳过 {dst.relative_to(REPO)}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        res = git("mv", src_rel, dst.relative_to(REPO).as_posix())
        if res.returncode != 0:
            print(f"  !! git mv 失败 {src_rel}\n     {res.stderr.strip()}")
            continue
        print(f"  {src_rel}  →  {dst.relative_to(REPO).as_posix()}")
        moved += 1

    for src_rel, dst_rel in ASSET_MOVES:
        src, dst = REPO / src_rel, REPO / dst_rel
        if not src.exists():
            print(f"  skip (已迁移) {src_rel}")
            continue
        if dst.exists():
            print(f"  !! 目标已存在，跳过 {dst_rel}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        res = git("mv", src_rel, dst_rel)
        if res.returncode != 0:
            print(f"  !! git mv 失败 {src_rel}\n     {res.stderr.strip()}")
            continue
        n = 1 if dst.is_file() else len([p for p in dst.rglob("*") if p.is_file()])
        print(f"  {src_rel}  →  {dst_rel}  ({n} 个文件)")
        moved += 1

    print(f"移动完成：{moved} 项")


def run_cleanup() -> None:
    for d_rel in LEGACY_DIRS:
        d = REPO / d_rel
        if not d.exists():
            print(f"  skip (已清理) {d_rel}")
            continue
        # 只有 index.md 算可删骨架。检查所有文件类型而不只是 markdown：
        # 旧目录里还有脚本、SQL、配置和插图，只看 .md 会把它们当空目录删掉。
        # 各模块的 README.md 多是 10-30KB 的系列总览，属于正文，必须拦下。
        leftovers = [
            p for p in d.rglob("*") if p.is_file() and p.name != "index.md"
        ]
        if leftovers:
            print(f"  !! {d_rel} 仍有 {len(leftovers)} 个非骨架文件，拒绝删除：")
            for p in leftovers[:5]:
                print(f"       {p.relative_to(REPO)}")
            continue
        res = git("rm", "-r", "-f", "-q", d_rel)
        if res.returncode != 0:
            print(f"  !! git rm 失败 {d_rel}\n     {res.stderr.strip()}")
            continue
        print(f"  已删除骨架目录 {d_rel}")


# --- 链接修复 -------------------------------------------------------------

LINK_RE = re.compile(r"(?<!\!)\[([^\]\n]*)\]\(([^)\s]+)\)")


def iter_md_files() -> list[Path]:
    out = []
    for p in REPO.rglob("*.md"):
        rel = p.relative_to(REPO)
        if rel.parts[0] in SKIP_DIRS or rel.parts[0].startswith("_"):
            continue
        out.append(p)
    return out


def encode(path: str) -> str:
    return path.replace(" ", "%20")


def decode(path: str) -> str:
    return urllib.parse.unquote(path)


def target_exists(base_dir: Path, target: str) -> bool:
    raw = decode(target)
    cand = (base_dir / raw).resolve()
    if cand.is_file():
        return True
    if cand.is_dir() and (cand / "index.md").is_file():
        return True
    return False


def resolve(body: str, by_name: dict[str, list[Path]]) -> Path | None:
    """按文件名反查失效链接的真实目标，用路径上的目录名消歧。

    大量链接指向目录（`../foo/`）或同名文件（全库 40 多个 index.md），
    只看 basename 不够。做法是先收集同名候选，再比较候选与原链接在
    目录层级上的公共后缀长度，取唯一最优。
    """
    raw = decode(body).rstrip("/")
    if not raw:
        return None

    name = posixpath.basename(raw)
    if not name:
        return None

    candidates = by_name.get(name, [])

    # 链接写的是目录名时，落到该目录的 index.md
    if not name.endswith(".md"):
        candidates = candidates + [
            p for p in by_name.get("index.md", []) if p.parent.name == name
        ]

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # 用原链接里 basename 之前的目录名做后缀匹配打分
    wanted = [
        part for part in posixpath.dirname(raw).split("/")
        if part not in ("", ".", "..")
    ]
    if not wanted:
        return None

    def score(p: Path) -> int:
        actual = [x for x in p.relative_to(REPO).parts[:-1]]
        n = 0
        while (
            n < len(wanted)
            and n < len(actual)
            and wanted[-1 - n] == actual[-1 - n]
        ):
            n += 1
        return n

    scored = sorted(((score(p), p) for p in candidates), key=lambda t: -t[0])
    if scored[0][0] == 0:
        return None
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


def run_links(dry_run: bool = False) -> None:
    files = iter_md_files()
    print(f"扫描 {len(files)} 个 markdown 文件")

    by_name: dict[str, list[Path]] = defaultdict(list)
    for p in files:
        by_name[p.name].append(p)

    total_broken = 0
    total_fixed = 0
    unresolved: list[str] = []

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"  !! 非 UTF-8，跳过 {path.relative_to(REPO)}")
            continue

        changed = False

        def repl(m: re.Match) -> str:
            nonlocal changed, total_broken, total_fixed
            label, target = m.group(1), m.group(2)

            if re.match(r"^(https?:|mailto:|#|/)", target):
                return m.group(0)

            body, sep, anchor = target.partition("#")
            if not body:
                return m.group(0)

            if target_exists(path.parent, body):
                return m.group(0)

            total_broken += 1

            hit = resolve(body, by_name)
            if hit is None:
                name = posixpath.basename(decode(body).rstrip("/"))
                n = len(by_name.get(name, []))
                why = "目标不存在" if n == 0 else f"{n} 个同名候选无法消歧"
                unresolved.append(
                    f"[{why}] {path.relative_to(REPO)} → {target}"
                )
                return m.group(0)

            new_rel = posixpath.relpath(hit.as_posix(), path.parent.as_posix())
            changed = True
            total_fixed += 1
            return f"[{label}]({encode(new_rel)}{sep}{anchor})"

        new_text = LINK_RE.sub(repl, text)
        if changed and not dry_run:
            path.write_text(new_text, encoding="utf-8")

    print(f"失效链接 {total_broken} 条，自动修复 {total_fixed} 条，"
          f"待人工处理 {len(unresolved)} 条")
    if unresolved:
        report = REPO / "_tmp" / "unresolved_links.txt"
        report.parent.mkdir(exist_ok=True)
        report.write_text("\n".join(unresolved), encoding="utf-8")
        print(f"未解析清单已写入 {report.relative_to(REPO)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--phase",
        choices=["moves", "cleanup", "links", "all"],
        default="all",
    )
    ap.add_argument("--dry-run", action="store_true", help="仅链接阶段生效")
    args = ap.parse_args()

    if args.phase in ("moves", "all"):
        print("=== 阶段 1：迁移滞留文章 ===")
        run_moves()
    if args.phase in ("cleanup", "all"):
        print("\n=== 阶段 2：清理旧骨架目录 ===")
        run_cleanup()
    if args.phase in ("links", "all"):
        print("\n=== 阶段 3：修复失效链接 ===")
        run_links(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
