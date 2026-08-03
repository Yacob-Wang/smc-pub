"""大章质量审计脚本 - 评估 8 卷 50 章所有 .md 文档

审计维度：
1. AOSP 版本基线（android-XX）
2. 字数（深度指标）
3. 结构完整性（frontmatter + H2/H3 章节数）
4. 写作时间（mtime）
5. 质量等级

等级：
- 🟢 优质 (A): AOSP 17/16 + 字数 > 10000 + 结构完整
- 🟢 良好 (B): AOSP 17/16 + 字数 5000-10000
- 🟡 适中 (C): AOSP 14/15 或字数百级 (3000-5000)
- 🟠 待更新 (D): AOSP < 14 或字数 < 3000
- ❌ 废弃 (E): 字数 < 1000 或无结构
"""
import re
import json
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

REPO = Path(__file__).resolve().parents[2]  # 00-Meta/scripts → 仓库根
EXCLUDE = ['00-Meta/overrides', '00-Meta/reader', '00-Meta/web', 'docs', 'site', '_archive']


# AOSP 版本模式
AOSP_PATTERNS = [
    (r'android-?(\d+)\.(\d+)\.(\d+)_r(\d+)', 'full'),  # android-15.0.0_r1
    (r'android-?(\d+)', 'major'),                    # android-17 / android17
    (r'AOSP\s*(\d+)', 'major'),                       # AOSP 17
    (r'API\s*(\d+)', 'api'),                          # API 37
    (r'android-17', 'major'),                         # android-17
]


def detect_aosp_version(text: str) -> tuple[str, int]:
    """返回 (版本字符串, 主版本号)。主版本 0 = 未检测到"""
    for pat, kind in AOSP_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            if kind == 'full':
                return m.group(0), int(m.group(1))
            elif kind == 'major':
                return m.group(0), int(m.group(1))
            elif kind == 'api':
                # API 36=Android 16, 37=Android 17
                api = int(m.group(1))
                if api >= 36:
                    return f'API{api}', api - 19  # 估算主版本
                return f'API{api}', 0
    return '', 0


def count_structure(text: str) -> dict:
    """统计文档结构"""
    return {
        'h1': len(re.findall(r'^# [^#]', text, re.MULTILINE)),
        'h2': len(re.findall(r'^## [^#]', text, re.MULTILINE)),
        'h3': len(re.findall(r'^### [^#]', text, re.MULTILINE)),
        'has_frontmatter': text.startswith('---'),
        'has_toc': '目录' in text[:500] or 'TOC' in text[:500],
        'code_blocks': len(re.findall(r'```', text)) // 2,
        'tables': len(re.findall(r'^\|.+\|$', text, re.MULTILINE)),
        'internal_links': len(re.findall(r'\]\((?!http)([^)]+)\)', text)),
    }


def assess_quality(chars: int, has_fm: bool, aosp_major: int, structure: dict) -> tuple[str, str]:
    """返回 (等级, 原因)

    新规则（更宽容）：
    - A 级（优质）：AOSP 17 + 字数 > 10000 + 结构完整（>10 H2）
    - B 级（良好）：AOSP 14-17 + 字数 > 5000
    - C 级（适中）：AOSP 14+ + 字数 > 3000
    - D 级（待更新）：AOSP 14-15 + 字数大（不是低质，是基线要更新到 17）
    - E 级（旧基线）：AOSP < 14（必须重写）
    """
    # E 级：旧基线
    if 0 < aosp_major < 14:
        return 'E', f'AOSP {aosp_major} < 14 旧基线'
    # D 级：待更新（基线老但内容好）
    if 14 <= aosp_major <= 15:
        if chars >= 5000:
            return 'D', f'基线 AOSP {aosp_major}，字数 {chars}（待更新到 17）'
        else:
            return 'E', f'基线 AOSP {aosp_major}，字数 {chars} 太少'
    # A 级：优质
    if aosp_major == 17 and chars >= 10000 and structure['h2'] >= 10:
        return 'A', f'AOSP 17 + {chars} chars + {structure["h2"]} H2'
    # B 级：良好
    if aosp_major >= 14 and chars >= 5000:
        return 'B', f'AOSP {aosp_major} + {chars} chars'
    # C 级：适中
    if aosp_major >= 14 and chars >= 3000:
        return 'C', f'AOSP {aosp_major} + {chars} chars'
    # E 级：字数极少
    if chars < 1000:
        return 'E', f'字数极少 ({chars})'
    if chars < 3000:
        return 'E', f'字数 {chars} 偏少'
    return 'C', f'字数 {chars}，AOSP {aosp_major}'


def main():
    # 扫所有 .md
    all_md = []
    for p in REPO.rglob('*.md'):
        rel = p.relative_to(REPO).as_posix()
        if any(rel.startswith(d) for d in EXCLUDE):
            continue
        # 排除 index.md / README.md（结构文件本身就该短）
        if p.name in ('index.md', 'README.md', 'Stability_README.md'):
            continue
        # 排除 _archive 目录
        if '_archive' in p.parts:
            continue
        all_md.append(p)
    print(f'[TOTAL] {len(all_md)} md files (排除 index/README)')

    # 审计
    results = []
    for p in all_md:
        rel = p.relative_to(REPO).as_posix()
        try:
            text = p.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        chars = len(text)
        structure = count_structure(text)
        aosp_str, aosp_major = detect_aosp_version(text)
        grade, reason = assess_quality(chars, structure['has_frontmatter'], aosp_major, structure)
        mtime = datetime.fromtimestamp(p.stat().st_mtime)
        results.append({
            'path': rel,
            'chars': chars,
            'words': chars // 2,  # 中文约 1 字 2 字节
            'h1': structure['h1'],
            'h2': structure['h2'],
            'h3': structure['h3'],
            'code_blocks': structure['code_blocks'],
            'tables': structure['tables'],
            'internal_links': structure['internal_links'],
            'has_frontmatter': structure['has_frontmatter'],
            'has_toc': structure['has_toc'],
            'aosp_version': aosp_str,
            'aosp_major': aosp_major,
            'grade': grade,
            'reason': reason,
            'mtime': mtime.strftime('%Y-%m-%d'),
        })

    # 写 JSON
    out_json = REPO / '00-Meta' / 'scripts' / '_quality_audit.json'
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[SAVED] {out_json}')

    # 统计
    grade_count = Counter(r['grade'] for r in results)
    print(f'\n[GRADE 分布]')
    for g in 'ABCDE':
        n = grade_count.get(g, 0)
        pct = 100 * n / len(results) if results else 0
        print(f'  {g}: {n} ({pct:.1f}%)')

    # AOSP 主版本分布
    aosp_count = Counter(r['aosp_major'] for r in results)
    print(f'\n[AOSP 主版本]')
    for v, n in sorted(aosp_count.items(), key=lambda x: -x[1])[:10]:
        label = f'AOSP {v}' if v > 0 else '未检测'
        print(f'  {label}: {n}')

    # 大章按卷/章分析
    print(f'\n[按卷统计]')
    by_vol = defaultdict(lambda: defaultdict(int))
    for r in results:
        parts = r['path'].split('/')
        vol = parts[0] if parts else 'root'
        grade = r['grade']
        by_vol[vol][grade] += 1
    for vol in sorted(by_vol):
        gs = by_vol[vol]
        line = f'  {vol}: '
        for g in 'ABCDE':
            if g in gs:
                line += f'{g}={gs[g]} '
        print(line)

    # 按卷/章统计 0/低质
    print(f'\n[大章 D/E 级统计]')
    by_chapter = defaultdict(lambda: {'D': 0, 'E': 0, 'total': 0, 'grade': []})
    for r in results:
        if r['grade'] in ('D', 'E'):
            # 提章节名
            parts = r['path'].split('/')
            if len(parts) >= 2:
                # 卷/章
                vol_ch = '/'.join(parts[:2])
            else:
                vol_ch = parts[0]
            by_chapter[vol_ch]['D' if r['grade'] == 'D' else 'E'] += 1
            by_chapter[vol_ch]['total'] += 1
            by_chapter[vol_ch]['grade'].append(r['path'])

    # 按 D+E 数量排序
    sorted_chs = sorted(by_chapter.items(), key=lambda x: -(x[1]['D'] + x[1]['E']))
    for ch, info in sorted_chs[:15]:
        n = info['D'] + info['E']
        print(f'  {ch}: D={info["D"]} E={info["E"]} (total {info["total"]}={n}/{len(info["grade"])})')

    # 旧版本基线（< 14）文章清单
    old_version = [r for r in results if r['aosp_major'] > 0 and r['aosp_major'] < 14]
    print(f'\n[旧版本基线 AOSP < 14]: {len(old_version)} 篇')
    for r in old_version[:10]:
        print(f'  AOSP {r["aosp_major"]}: {r["path"]}')

    # 详细按 AOSP 17/16/14-15/<14 分组
    print(f'\n[AOSP 17]: {len([r for r in results if r["aosp_major"] == 17])} 篇')
    print(f'[AOSP 16]: {len([r for r in results if r["aosp_major"] == 16])} 篇')
    print(f'[AOSP 14-15]: {len([r for r in results if 14 <= r["aosp_major"] <= 15])} 篇')
    print(f'[AOSP < 14]: {len([r for r in results if 0 < r["aosp_major"] < 14])} 篇')
    print(f'[未检测 AOSP]: {len([r for r in results if r["aosp_major"] == 0])} 篇')

    # 旧版本 + 低质 = 待替换
    print(f'\n[待替换清单 = 旧版本 OR D/E 低质]')
    need_replace = [
        r for r in results
        if r['aosp_major'] < 14 or r['grade'] in ('D', 'E')
    ]
    # 排序：AOSP 旧的优先 + 字数少的优先
    need_replace.sort(key=lambda r: (r['aosp_major'] if r['aosp_major'] > 0 else 99, r['chars']))
    print(f'[TOTAL 待替换] {len(need_replace)} 篇')
    for r in need_replace[:80]:
        marker = ' [OLD]' if r['aosp_major'] > 0 and r['aosp_major'] < 14 else f' [{r["grade"]}]'
        print(f'  {marker:6s} {r["chars"]:6d} ch  AOSP={r["aosp_major"]:2d}  {r["path"]}')
    if len(need_replace) > 80:
        print(f'  ... +{len(need_replace)-80} more')

    # 写 待替换 JSON + MD 清单
    out_json = REPO / '00-Meta' / 'scripts' / '_need_replace.json'
    out_json.write_text(json.dumps(need_replace, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n[SAVED] {out_json}')

    # MD 清单
    md_lines = [
        '# 待替换/重写文章清单',
        '',
        '> **生成时间**：2026-08-02',
        '> **基线**：写作标准统一为 AOSP 17.0.0_r1 + Linux 6.18 GKI',
        '> **总条数**：' + str(len(need_replace)) + ' 篇',
        '> **说明**：旧版本基线（AOSP < 14）或质量低（字数极少）的文章需要后续重写',
        '',
        '## 排序规则',
        '1. AOSP < 14 优先（旧基线）',
        '2. 字数少的优先（质量低）',
        '3. Grade D/E 标记（结构不完整）',
        '',
        '## 待替换清单',
        '',
    ]
    for r in need_replace:
        marker = '🔴 旧版本' if r['aosp_major'] > 0 and r['aosp_major'] < 14 else f'🟡 {r["grade"]} 级'
        md_lines.append(
            f'- {marker} | {r["chars"]} chars | AOSP {r["aosp_major"]} | `{r["path"]}`'
        )
    md_lines.append('')
    md_lines.append('---')
    md_lines.append('')
    md_lines.append(f'**生成脚本**：`00-Meta/scripts/quality_audit.py`')
    out_md = REPO / '00-Meta' / '待替换清单-v1.md'
    out_md.write_text('\n'.join(md_lines), encoding='utf-8')
    print(f'[SAVED] {out_md}')


if __name__ == '__main__':
    main()
