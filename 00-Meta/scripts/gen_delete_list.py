"""生成 拟删除清单（E 级低质）"""
import json
from pathlib import Path

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')
data = json.loads((REPO / '00-Meta' / 'scripts' / '_quality_audit.json').read_text(encoding='utf-8'))

# E 级 = 拟删除
e_files = [r for r in data if r['grade'] == 'E']
e_files.sort(key=lambda r: r['chars'])

md = [
    '# 拟删除清单 - E 级低质/旧基线',
    '',
    '> **生成时间**：2026-08-02',
    '> **基线**：写作标准 v1（AOSP 17.0.0_r1）',
    '> **E 级标准**：AOSP < 14 旧基线 或 字数 < 1000 极短',
    f'> **总条数**：{len(e_files)} 篇',
    '',
    '## 删除原则',
    '',
    '1. **优先删除**：字数 < 1000 的极短文件（信息密度太低，无法独立成文）',
    '2. **次优先删除**：AOSP < 14 的旧基线文件（基础研究已过时）',
    '3. **保留**：1000-3000 字符的简短笔记类（可作为索引或补充）',
    '4. **重写**：3000+ 字符但 AOSP < 14 的文件（保留内容但需重写到 AOSP 17）',
    '',
    '## 拟删除清单（按字数排序）',
    '',
    '| # | 字数 | AOSP | 状态 | 路径 |',
    '|---|---:|---:|---|---|',
]

for i, r in enumerate(e_files, 1):
    aosp_label = f'AOSP {r["aosp_major"]}' if r['aosp_major'] > 0 else '未检测'
    if r['aosp_major'] > 0 and r['aosp_major'] < 14:
        status = '🔴 旧基线 - 重写或删除'
    elif r['chars'] < 1000:
        status = '🟡 极短 - 建议删除'
    elif r['chars'] < 3000:
        status = '🟠 简短 - 评估是否需要'
    else:
        status = '🟡 评估中'
    md.append(f'| {i} | {r["chars"]} | {aosp_label} | {status} | `{r["path"]}` |')

md.extend([
    '',
    '## 分类汇总',
    '',
])

# 分类
from collections import Counter
by_vol = Counter()
for r in e_files:
    by_vol[r['path'].split('/')[0]] += 1

md.append('| 卷 | 数量 |')
md.append('|---|---:|')
for v, n in sorted(by_vol.items(), key=lambda x: -x[1]):
    md.append(f'| {v} | {n} |')

md.extend([
    '',
    '## 处理建议',
    '',
    '### 阶段 1：立即删除（信息密度低 + 旧基线）',
    '- 字数 < 1000 且 AOSP < 14 的极短文件',
    '- 列表见上 `🟡 极短` 和 `🔴 旧基线` 行',
    '',
    '### 阶段 2：重写（内容可参考但需更新）',
    '- 3000+ 字符但 AOSP 12-13 的文件',
    '- 列表见上 `🟡 评估中` 行',
    '',
    '### 阶段 3：评估（需人工判断）',
    '- 字数 1000-3000 的简短笔记',
    '- 列表见上 `🟠 简短` 行',
    '',
    '---',
    '',
    '**生成脚本**：`00-Meta/scripts/quality_audit.py`',
    '**配套文档**：`00-Meta/写作标准-v1.md`',
])

out = REPO / '00-Meta' / '拟删除清单-v1.md'
out.write_text('\n'.join(md), encoding='utf-8')
print(f'[SAVED] {out}')
print(f'[E 级] {len(e_files)} 篇')
