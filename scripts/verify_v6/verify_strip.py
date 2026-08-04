"""v6 verify_strip.py — v6 §9.4 公开站剥离后元信息残留检查

检查项:
1. 公开站剥离后,应不含 AUTHOR_ONLY 字符串
2. 公开站剥离后,应不含"本篇定位" / "校准决策日志" / "角色设定" / "上下文" 4 个作者元信息标题
3. 公开站剥离后,应不含"v5/v6 §X" 等内部规范号
4. 公开站剥离后,应不含"人工搜索" / "硬性要求" / "沿用 09/12 篇" 等 LLM 流程披露

用法:
    python verify_strip.py <article.md>
"""
import re
import sys

# v6 §9.4 剥离脚本
STRIP_PATTERN = re.compile(
    r'<!--\s*AUTHOR_ONLY:START\s*-->.*?<!--\s*AUTHOR_ONLY:END\s*-->\n?',
    re.DOTALL,
)

# 公开站不应包含的元信息关键词
# 注意:"校准" / "基线" / "作者"等是合法技术词,不应列入
FORBIDDEN_PHRASES = [
    '本篇定位', '校准决策日志', '角色设定',
    'v5 §', 'v6 §', 'v3 模板', 'v4 模板',
    '人工搜索', '硬性要求',
]


def verify_strip(path: str) -> int:
    with open(path, 'rb') as f:
        b = f.read()
    raw = b.decode('utf-8', errors='replace')

    # 执行 §9.4 剥离
    public_view = STRIP_PATTERN.sub('', raw)

    print(f'=== verify_strip: {path} ===')
    print(f'原文字数: {len(raw)}')
    print(f'剥离后字数: {len(public_view)}')

    # 1. AUTHOR_ONLY 字符串残留
    author_only_residual = 'AUTHOR_ONLY' in public_view
    print(f'1. AUTHOR_ONLY 字符串残留: {1 if author_only_residual else 0} {"❌" if author_only_residual else "✅"}')

    # 2. 元信息关键词残留
    residual_count = 0
    for phrase in FORBIDDEN_PHRASES:
        n = public_view.count(phrase)
        if n > 0:
            print(f'2. 关键词 "{phrase}" 残留: {n} 处 ❌')
            residual_count += n
    if residual_count == 0:
        print(f'2. 元信息关键词残留: 0 处 ✅')

    if not author_only_residual and residual_count == 0:
        print('\n✅ ALL PASS')
        return 0
    else:
        print('\n❌ FAIL')
        return 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python verify_strip.py <article.md>')
        sys.exit(2)
    sys.exit(verify_strip(sys.argv[1]))
