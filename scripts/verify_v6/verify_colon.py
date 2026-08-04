"""v6 verify_colon.py — v6 §3.5 跨篇链接必须用全角冒号

检查项:
1. 跨篇 markdown 链接(.md 文件)用全角冒号(U+FF1A)而非半角(U+003A)
2. 0 个半角冒号链接

用法:
    python verify_colon.py <article.md>
"""
import re
import sys

# 半角冒号在 markdown 链接里(.md 文件)
HALF_COLON_LINK = re.compile(rb'\]\([^)]*\.md:[^)]*\)')

# 全角冒号在 markdown 链接里
FULL_COLON_LINK = re.compile(rb'\]\([^)]*\xef\xbc\x9a[^)]*\)')

# 字节对照:半角冒号 = \x3a;全角冒号 U+FF1A = \xef\xbc\x9a
HALF_COLON = b'\x3a'
FULL_COLON = b'\xef\xbc\x9a'


def verify_colon(path: str) -> int:
    with open(path, 'rb') as f:
        b = f.read()

    half_count = len(HALF_COLON_LINK.findall(b))
    full_count = len(FULL_COLON_LINK.findall(b))

    print(f'=== verify_colon: {path} ===')
    print(f'1. 半角冒号 md 链接: {half_count} {"❌" if half_count > 0 else "✅"}')
    print(f'2. 全角冒号 md 链接: {full_count} (推荐 ≥ 1)')

    # 在 md 文件名里,半角 vs 全角冒号
    # Windows 文件系统允许 U+FF1A(虽然罕见),但更常见是 U+003A
    # v6 强锁:跨篇链接必须用 U+FF1A(因为 mkdocs 渲染时 U+003A → %3A,U+FF1A → %EF%BC%9A,后缀不同)
    # 即使 Windows 本地能打开,公开站 mkdocs 仍会 404

    if half_count == 0:
        print('\n✅ ALL PASS')
        return 0
    else:
        print('\n❌ FAIL — 跨篇链接必须用全角冒号 (U+FF1A)')
        return 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python verify_colon.py <article.md>')
        sys.exit(2)
    sys.exit(verify_colon(sys.argv[1]))
