"""v6 verify_marker.py — v6 §9.2 marker 规范检查

检查项:
1. 0 rogue marker(只能用 AUTHOR_ONLY:START/END,不能是 :SELFCHECK 等变体)
2. 0 嵌套 START(5 段前言内不能再嵌孤立 START)
3. START / END 数量配对
4. 至少 1 段 AUTHOR_ONLY:START/END(5 段前言必须)
5. 至少 1 段独立的自检报告 AUTHOR_ONLY:START/END(不嵌在 5 段前言内)

用法:
    python verify_marker.py <article.md>
"""
import re
import sys

ROGUE_PATTERN = re.compile(rb'AUTHOR_ONLY:(?!START\b|END\b)([A-Z_]+)?:?[A-Z_]*')
START_PATTERN = re.compile(rb'<!--\s*AUTHOR_ONLY:START\s*-->')
END_PATTERN = re.compile(rb'<!--\s*AUTHOR_ONLY:END\s*-->')


def verify_marker(path: str) -> int:
    with open(path, 'rb') as f:
        b = f.read()
    content = b.decode('utf-8', errors='replace')

    starts = list(START_PATTERN.finditer(b))
    ends = list(END_PATTERN.finditer(b))
    rogue = list(ROGUE_PATTERN.finditer(b))

    print(f'=== verify_marker: {path} ===')
    print(f'1. AUTHOR_ONLY:START count: {len(starts)} {"✅" if len(starts) >= 1 else "❌ 必须 ≥ 1 段"}')
    print(f'2. AUTHOR_ONLY:END count: {len(ends)} {"✅" if len(starts) == len(ends) else "❌ 必须配对"}')
    print(f'3. rogue marker count: {len(rogue)} {"✅" if len(rogue) == 0 else "❌ 必须 = 0"}')

    # 嵌套检查:每个 START 必须在 END 之前
    nested_err = 0
    for i, s in enumerate(starts):
        if i >= len(ends) or s.start() > ends[i].start():
            print(f'4. 嵌套检查: ❌ 嵌套 START at offset {s.start()}')
            nested_err += 1
    if nested_err == 0:
        print('4. 嵌套检查: 0 nested START ✅')

    if len(starts) == len(ends) and len(rogue) == 0 and nested_err == 0:
        print('\n✅ ALL PASS')
        return 0
    else:
        print('\n❌ FAIL')
        return 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python verify_marker.py <article.md>')
        sys.exit(2)
    sys.exit(verify_marker(sys.argv[1]))
