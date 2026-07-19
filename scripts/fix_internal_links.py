#!/usr/bin/env python3
"""修复 smc-pub 全仓 .md 内部链接的相对路径（按"文件实际位置"反推）。"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 只处理这些 module 的 .md
TARGET_DIRS = [
    "00-Meta", "01-Mechanism", "02-Symptom", "03-Forensics",
    "04-Tool", "05-Governance", "06-Case", "06-Foundation",
]

# md 链接 pattern: ](Xxx.md) 或 ](Xxx.md#anchor)
LINK_RE = re.compile(r"\]\(([^\)\#]+\.md)(?:#[^\)]*)?\)")

# 排除占位符
PLACEHOLDER_RE = re.compile(r"^[\?\.\*]+$|\{.*?\}")


# 全仓 .md basename → [paths] 索引（延迟构建）
_BASENAME_INDEX: dict[str, list[Path]] | None = None


# 死引用别名 → 实际目标（用于 478 个死引用的处理）
# 适用于：AOSP_Startup 合并到 S11-Startup、Forensics 命名规范化等
ALIAS_MAP: dict[str, str] = {
    # AOSP_Startup 已合并 → S11-Startup（README 路径）
    "README-AOSP_Startup系列.md": "S11-Startup/README.md",
    "13-Rust Binder专题.md": "暂未找到",
    "13-Rust%20Binder专题.md": "暂未找到",

    # Forensics 命名（旧 → 新）
    "F00-取证体系总览.md": "F00-Overview/01-取证机制.md",
    "F01-ANR取证.md": "F01-ANR/01-取证机制.md",
    "F02-SWT取证.md": "F02-SWT/01-取证机制.md",
    "F03-JE取证.md": "F03-JE/01-取证机制.md",
    "F04-NE取证.md": "F04-NE/01-取证机制.md",
    "F05-KE取证.md": "F05-KE/01-取证机制.md",
    "F06-HANG与OOM取证.md": "F06-HANG-OOM/01-取证机制.md",
    "README-Forensics系列.md": "README.md",
    "F07-取证机制.md": "F07-Governance/01-取证机制.md",
    "F07-取证治理.md": "F07-Governance/01-取证机制.md",
    "README-系列通用总览索引.md": "../README.md",
    "README-Stability系列.md": "../README.md",
    "README-学习路线-稳定性架构师.md": "README-学习路线.md",

    # 死引用 → 实际目标（早期命名简化）
    "S00-稳定性症状总览.md": "../S00-症状总览.md",
    "S01-ANR.md": "../S01-ANR/01-症状机制.md",
    "S02-JE.md": "../S02-JE/01-症状机制.md",
    "S03-NE.md": "../S03-NE/01-症状机制.md",
    "S04-SWT.md": "../S04-SWT/01-症状机制.md",
    "S05-HANG.md": "../S05-HANG/01-症状机制.md",
    "S06-REBOOT.md": "../S06-REBOOT/01-症状机制.md",
    "S07-KE.md": "../S07-KE/01-症状机制.md",
    "S08-AOSP17与K618稳定性全景.md": "../S08-AOSP17-K618/01-症状机制.md",
    "S09-PerfVsStab.md": "../S09-PerfVsStab/01-症状机制.md",
    "S10-Measure.md": "../S10-Measure/01-症状机制.md",
    "S09-性能vs稳定性横切专题.md": "../S09-PerfVsStab/01-症状机制.md",

    # 启动专项 → S11-Startup 子篇
    "E02-案例2_开机卡SystemServer60%阻塞.md": "E02-SystemServer60%阻塞.md",
    "E03-案例3_开机卡30s-SurfaceFlinger阻塞.md": "E03-开机卡30s.md",
    "D04-启动期dumpsys-systrace-traceview综合.md": "../D-启动工具/D04-启动期dumpsys-systrace-traceview综合.md",
    "12-Binder节点文件全景.md": "01-Mechanism/Kernel/Binder/12-Binder节点文件全景与问题实战.md",
}


def _build_basename_index() -> dict[str, list[Path]]:
    global _BASENAME_INDEX
    if _BASENAME_INDEX is not None:
        return _BASENAME_INDEX
    idx: dict[str, list[Path]] = {}
    for mod in TARGET_DIRS:
        mod_path = REPO_ROOT / mod
        if not mod_path.is_dir():
            continue
        for fp in mod_path.rglob("*.md"):
            base = fp.name
            idx.setdefault(base, []).append(fp)
            # 全角/半角冒号都索引（让两种变体都查得到）
            if "：" in base:
                idx.setdefault(base.replace("：", ":"), []).append(fp)
            elif ":" in base:
                idx.setdefault(base.replace(":", "："), []).append(fp)
    _BASENAME_INDEX = idx
    return idx


def _normalize_basename(name: str) -> str:
    """归一化文件名用于模糊匹配：URL 解码、全角/半角冒号统一。"""
    from urllib.parse import unquote
    name = unquote(name)
    # 全角冒号 :（U+FF1A）<-> 半角冒号 : (U+003A)
    name = name.replace("：", ":")
    return name


def _denormalize_basename(name: str) -> str:
    """反向归一化：半角冒号 → 全角冒号（用于链接端。文件名端是全角）。"""
    return name.replace(":", "：")


def _link_variants(link: str) -> list[str]:
    """生成链接名的多种变体（URL 解码、全/半角冒号、连接词归一、短标题截断）。"""
    variants = [link]
    # URL 解码
    variants.append(_normalize_basename(link))
    # 全角冒号也试（如果原链接是半角）
    if ":" in link:
        variants.append(_denormalize_basename(link))
    # 用 / 与 互换
    base = Path(link).stem
    if "_与_" in base:
        variants.append(link.replace("_与_", "与"))
        variants.append(link.replace("_与_", "和"))
    if "与" in base and "_与_" not in link:
        variants.append(link.replace("与", "_与_"))
    # 短标题截断（"B01-BootTime测量_描述后缀.md" → "B01-BootTime测量.md"）
    parts = base.split("_")
    if len(parts) >= 2:
        short = parts[0]
        short_link = short + Path(link).suffix
        variants.append(short_link)
        variants.append(_normalize_basename(short_link))
        variants.append(_denormalize_basename(short_link))
    # 长描述截断（"C02-启动死锁与SystemServer僵死.md" → "C02-启动死锁.md"）
    # 按"与/和/空格/冒号"截断到数字编号后第一个短语
    import re as _re
    for sep in ["与", "和", " ", ":", "："]:
        if sep in base:
            short = base.split(sep, 1)[0]
            if _re.match(r"^[A-Za-z]?\d+-", short):
                short_link = short + Path(link).suffix
                variants.append(short_link)
                variants.append(_normalize_basename(short_link))
                variants.append(_denormalize_basename(short_link))
    # 去重
    seen = set()
    out = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def find_real_target(link: str, src_path: Path) -> Path | None:
    """从 src_path 出发，按"父目录向上"找 link 实际指向的文件。返回绝对路径。

    优先选最近的目录（最少的 ../）。找不到时回退到全仓唯一 basename 匹配。
    """
    src_dir = src_path.parent
    seen: set[Path] = set()

    # 1. 尝试原 link + 各种变体向上找
    for variant in _link_variants(link):
        cur = src_dir
        depth = 0
        while depth < 12 and cur not in seen:
            seen.add(cur)
            target = cur / variant
            if target.is_file():
                return target
            cur = cur.parent
            depth += 1

    # 2. 回退：全仓找唯一 basename 匹配（变体归一后）
    variant_bases = {_normalize_basename(Path(v).name) for v in _link_variants(link)}
    idx = _build_basename_index()
    all_candidates: list[Path] = []
    for v_base in variant_bases:
        for c in idx.get(v_base, []):
            if c not in all_candidates:
                all_candidates.append(c)
    if not all_candidates:
        return None
    if len(all_candidates) == 1:
        return all_candidates[0]
    # 3. 多义：按 src_path 所在 module 优先
    src_mod = None
    for mod in TARGET_DIRS:
        try:
            if src_path.is_relative_to(REPO_ROOT / mod):
                src_mod = mod
                break
        except ValueError:
            continue
    if src_mod:
        for c in all_candidates:
            try:
                for mod in TARGET_DIRS:
                    if c.is_relative_to(REPO_ROOT / mod):
                        if mod == src_mod:
                            return c
                        break
            except ValueError:
                continue
    # 4. 退而求其次：返回最近（path 最短）的
    all_candidates.sort(key=lambda p: (len(p.parts), str(p)))
    return all_candidates[0]


def resolve_alias(link: str, src_path: Path) -> str | None:
    """死引用别名解析：返回修正后的相对路径字符串。"""
    base = Path(link).name
    if base not in ALIAS_MAP:
        return None
    target_rel = ALIAS_MAP[base]
    if target_rel == "暂未找到":
        return None
    src_mod = None
    for mod in TARGET_DIRS:
        try:
            if src_path.is_relative_to(REPO_ROOT / mod):
                src_mod = mod
                break
        except ValueError:
            continue

    # 解析 target
    target: Path | None = None

    # 1. Forensics 别名
    forensics_targets = {"F00-Overview/01-取证机制.md", "F01-ANR/01-取证机制.md",
                         "F02-SWT/01-取证机制.md", "F03-JE/01-取证机制.md",
                         "F04-NE/01-取证机制.md", "F05-KE/01-取证机制.md",
                         "F06-HANG-OOM/01-取证机制.md", "F07-Governance/01-取证机制.md",
                         "README.md", "README-Forensics系列.md"}
    if target_rel in forensics_targets:
        target = REPO_ROOT / "03-Forensics" / target_rel

    # 2. S11-Startup 别名
    elif target_rel == "S11-Startup/README.md":
        target = REPO_ROOT / "02-Symptom" / target_rel

    # 3. 02-Symptom 根的相对路径（如 ../S00-症状总览.md）
    elif target_rel.startswith("../") and src_mod == "02-Symptom":
        # 去掉 ../ 前缀
        sub = target_rel[3:]
        target = REPO_ROOT / "02-Symptom" / sub

    # 4. 同 module 的相对路径（如 ../D-启动工具/D04-...）
    elif target_rel.startswith("../") and src_mod:
        sub = target_rel[3:]
        target = REPO_ROOT / src_mod / sub

    # 5. 仓库内绝对路径（不含 ../../ 前缀，直接以 module 名开头）
    elif "/" in target_rel and not target_rel.startswith("."):
        candidate = REPO_ROOT / target_rel
        if candidate.is_file():
            target = candidate

    # 6. 同 module 内（E02-...md → 同目录的 E02-...md）
    elif src_mod and "/" not in target_rel:
        target = REPO_ROOT / src_mod / target_rel

    if target is None or not target.is_file():
        return None
    return to_relative(target, src_path)


def to_relative(target_abs: Path, src_path: Path) -> str:
    """target 相对 src_path 的相对路径，用 POSIX 分隔。"""
    rel = os.path.relpath(target_abs, src_path.parent)
    return rel.replace("\\", "/")


def fix_file(src_path: Path) -> int:
    text = src_path.read_text(encoding="utf-8", errors="replace")
    orig = text
    changes = 0

    def replace(m: re.Match) -> str:
        nonlocal changes
        link = m.group(1)
        # 跳过已经带 ../ ./ / http
        if link.startswith(("../", "./", "/", "http://", "https://")):
            return m.group(0)
        # 跳过占位符
        if PLACEHOLDER_RE.search(link):
            return m.group(0)
        # 找真实目标
        target = find_real_target(link, src_path)
        if target is None:
            # 试别名
            alias_link = resolve_alias(link, src_path)
            if alias_link and alias_link != link:
                changes += 1
                anchor = m.group(0).split("#", 1)
                suffix = "#" + anchor[1] if len(anchor) > 1 else ""
                return f"]({alias_link}{suffix})"
            return m.group(0)  # 找不到，保留原样
        # 算相对路径
        new_link = to_relative(target, src_path)
        if new_link == link:
            return m.group(0)  # 没变化
        changes += 1
        # 保留 anchor
        anchor = m.group(0).split("#", 1)
        suffix = "#" + anchor[1] if len(anchor) > 1 else ""
        return f"]({new_link}{suffix})"

    new = LINK_RE.sub(replace, text)
    if new != orig:
        src_path.write_text(new, encoding="utf-8")
    return changes


def main() -> int:
    total_files = 0
    total_changes = 0
    for mod in TARGET_DIRS:
        mod_path = REPO_ROOT / mod
        if not mod_path.is_dir():
            continue
        for fp in mod_path.rglob("*.md"):
            if not fp.is_file():
                continue
            changes = fix_file(fp)
            if changes > 0:
                total_files += 1
                total_changes += changes
                rel = fp.relative_to(REPO_ROOT)
                print(f"  {rel}: {changes} changes")
    print(f"\nTOTAL: {total_files} files, {total_changes} link changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
