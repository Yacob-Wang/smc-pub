"""
v6 写作规范 verify 脚本 (适用于合并单版)
检查项:
  1. AUTHOR_ONLY 段行数 <= 15 (v6 §3.2)
  2. 顶部 blockquote <= 3 行 (v6 §3.1)
  3. 禁用元叙述扫描 (v6 §10.3)
  4. 公开站剥离后元信息残留 = 0 (v6 §9.3)
  5. 强制要求:标题、本篇定位声明、附录 A/B/C/D 存在
"""
import re
import sys
from pathlib import Path

# v6 §10.1 禁用元叙述(7 类)
# 用 chr() 拼接避免 system prompt 字符串规范化
BANNED_PATTERNS = [
    # 章节首句元叙述
    (chr(0x672c)+chr(0x7ae0)+chr(0x5c06)+chr(0x4ecb)+chr(0x7ecd), '章节首句: 本章将介绍'),
    (chr(0x63a5)+chr(0x4e0b)+chr(0x6765)+chr(0x6211)+chr(0x4eec)+chr(0x8ba8)+chr(0x8bba), '段落切换: 接下来我们讨论'),
    (chr(0x63a5)+chr(0x4e0b)+chr(0x6765)+chr(0x770b)+chr(0x4e00)+chr(0x6bb5)+chr(0x4ee3)+chr(0x7801), '流程指示: 接下来看一段代码'),
    # 结构承诺式
    (chr(0x6211)+chr(0x4eec)+chr(0x5c06)+chr(0x5728)+chr(0x540e)+chr(0x7eed)+chr(0x6587)+chr(0x7ae0)+chr(0x8be6)+chr(0x7ec6)+chr(0x8bb2), '结构承诺: 我们将在后续文章详细讲'),
    (chr(0x9650)+chr(0x4e8e)+chr(0x7247)+chr(0x7a3f)+chr(0x6211)+chr(0x4eec)+chr(0x4e0d)+chr(0x5c55)+chr(0x5f00), '结构承诺: 限于篇幅我们不展开'),
    # AI 自嗨式
    (chr(0x975e)+chr(0x5e38)+chr(0x7cbe)+chr(0x5999), 'AI 自嗨: 非常精妙'),
    (chr(0x7cbe)+chr(0x5999)+chr(0x7684)+chr(0x8bbe)+chr(0x8ba1), 'AI 自嗨: 精妙的设计'),
    (chr(0x4f53)+chr(0x73b0)+chr(0x4e86)+chr(0x2026)+chr(0x6df1)+chr(0x5ea6)+chr(0x878d)+chr(0x5408), 'AI 自嗨: 体现了...深度融合'),
    # 空泛总结式
    (chr(0x7efc)+chr(0x4e0a)+chr(0x6240)+chr(0x8ff0), '空泛总结: 综上所述'),
    (chr(0x603b)+chr(0x4e4b)+chr(0x800c)+chr(0x8a00), '空泛总结: 总而言之'),
    (chr(0x7531)+chr(0x6b64)+chr(0x53ef)+chr(0x89c1), '空泛总结: 由此可见'),
    (chr(0x4ece)+chr(0x4ee5)+chr(0x4e0a)+chr(0x5206)+chr(0x6790)+chr(0x53ef)+chr(0x4ee5)+chr(0x770b)+chr(0x51fa), '空泛总结: 从以上分析可以看出'),
    # 过度铺垫式
    (chr(0x5728)+chr(0x6b63)+chr(0x5f0f)+chr(0x5f00)+chr(0x59cb)+chr(0x4e4b)+chr(0x524d), '过度铺垫: 在正式开始之前'),
    (chr(0x8ba9)+chr(0x6211)+chr(0x4eec)+chr(0x5148)+chr(0x770b), '过度铺垫: 让我们先看'),
]

# v6 §9.3 剥离脚本(只剥 AUTHOR_ONLY 段)
STRIP_PATTERN = re.compile(
    r'<!--\s*AUTHOR_ONLY:START\s*-->.*?<!--\s*AUTHOR_ONLY:END\s*-->\n?',
    re.DOTALL
)


def check_author_only_lines(content):
    """检查 1: AUTHOR_ONLY 段行数 <= 15"""
    m = re.search(r'<!--\s*AUTHOR_ONLY:START\s*-->.*?<!--\s*AUTHOR_ONLY:END\s*-->', content, re.DOTALL)
    if not m:
        return 0, 'AUTHOR_ONLY 段不存在'

    segment = m.group(0)
    # 计算行数
    n = len(segment.splitlines())
    return n, f'AUTHOR_ONLY 段 {n} 行(规范: <=15)'


def check_top_blockquote(content):
    """检查 2: 顶部 blockquote <= 3 行"""
    # 找第一个 ## 标题之前的 blockquote 段
    lines = content.splitlines()
    blockquote_lines = []
    for line in lines:
        if line.startswith('## '):
            break
        if line.startswith('> '):
            blockquote_lines.append(line)

    n = len(blockquote_lines)
    return n, f'顶部 blockquote {n} 行(规范: <=3)'


def check_banned_words(content):
    """检查 3: 禁用元叙述扫描"""
    # 剥掉 AUTHOR_ONLY 段(作者前言不算正文)
    stripped = STRIP_PATTERN.sub('', content)

    findings = []
    for pattern, desc in BANNED_PATTERNS:
        for m in re.finditer(pattern, stripped):
            # 找到行号(用 stripped 的行号)
            line_no = stripped[:m.start()].count('\n') + 1
            findings.append((line_no, desc, m.group(0)))

    return findings


def check_public_strip_leakage(content):
    """检查 4: 公开站剥离后元信息残留 = 0"""
    stripped = STRIP_PATTERN.sub('', content)

    # 关键元信息关键词(公开站不能漏)
    # 注:"本篇定位声明"是 H2 章节标题(读者需要),不算残留
    leak_keywords = [
        'AUTHOR_ONLY',  # marker 本身不能漏
        '校准决策日志',  # AUTHOR_ONLY 段内专有标题
        '角色设定',  # v6 已删,出现就漏
        '写作标准',  # v6 已删,出现就漏
        '硬性要求 8 条',  # v6 已删,出现就漏
    ]

    findings = []
    for kw in leak_keywords:
        if kw in stripped:
            # 找到第一个位置
            pos = stripped.find(kw)
            line_no = stripped[:pos].count('\n') + 1
            findings.append((line_no, kw))

    return findings, stripped


def check_required_sections(content):
    """检查 5: 强制要求章节存在"""
    required = [
        ('## 0. 本篇定位声明', '本篇定位声明'),
        ('## 附录 A', '附录 A 源码索引'),
        ('## 附录 B', '附录 B 路径对账'),
        ('## 附录 C', '附录 C 量化自检'),
        ('## 附录 D', '附录 D 工程基线'),
        ('<!-- AUTHOR_ONLY:START -->', 'AUTHOR_ONLY 段标记'),
        ('<!-- AUTHOR_ONLY:END -->', 'AUTHOR_ONLY 段结束标记'),
    ]
    missing = []
    for marker, name in required:
        if marker not in content:
            missing.append(name)
    return missing


def verify_file(path):
    print(f'\n{"="*70}')
    print(f'Verify: {path}')
    print(f'{"="*70}')

    content = Path(path).read_text(encoding='utf-8')
    total_lines = len(content.splitlines())
    print(f'文件: {total_lines} 行 / {len(content.encode("utf-8"))} 字节\n')

    failed = []

    # Check 1
    n, msg = check_author_only_lines(content)
    print(f'[1] AUTHOR_ONLY 段: {msg}')
    if n > 15:
        failed.append(f'AUTHOR_ONLY 段行数 {n} > 15')

    # Check 2
    n, msg = check_top_blockquote(content)
    print(f'[2] 顶部 blockquote: {msg}')
    if n > 3:
        failed.append(f'顶部 blockquote {n} 行 > 3')

    # Check 3
    findings = check_banned_words(content)
    if findings:
        print(f'[3] 禁用元叙述扫描: ❌ 发现 {len(findings)} 处')
        for line_no, desc, text in findings[:10]:
            print(f'    行 {line_no}: [{desc}] "{text}"')
        if len(findings) > 10:
            print(f'    ... 另 {len(findings)-10} 处')
        failed.append(f'禁用元叙述 {len(findings)} 处')
    else:
        print(f'[3] 禁用元叙述扫描: ✅ 无')

    # Check 4
    findings, stripped = check_public_strip_leakage(content)
    stripped_lines = len(stripped.splitlines())
    print(f'[4] 公开站剥离后: {stripped_lines} 行')
    if findings:
        print(f'    ❌ 元信息残留: {len(findings)} 处')
        for line_no, kw in findings:
            print(f'    行 {line_no}: "{kw}"')
        failed.append(f'元信息残留 {len(findings)} 处')
    else:
        print(f'    ✅ 元信息残留 = 0')

    # Check 5
    missing = check_required_sections(content)
    if missing:
        print(f'[5] 强制章节: ❌ 缺失 {len(missing)} 个')
        for name in missing:
            print(f'    缺: {name}')
        failed.append(f'缺失章节 {len(missing)} 个')
    else:
        print(f'[5] 强制章节: ✅ 全部存在')

    # 总结
    print(f'\n{"="*70}')
    if failed:
        print(f'❌ 失败 {len(failed)} 项:')
        for f in failed:
            print(f'   - {f}')
        return False
    else:
        print('✅ 全部通过')
        return True


if __name__ == '__main__':
    files = sys.argv[1:] if len(sys.argv) > 1 else [
        r'E:\smc-pub\01-Mechanism\Runtime\ART\03-GC系统\01-基础理论专题.md',
    ]
    all_pass = True
    for f in files:
        if not verify_file(f):
            all_pass = False
    sys.exit(0 if all_pass else 1)
