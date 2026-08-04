"""v6 verify_control.py — v6 §12.2 控制字符检查

检查项(子线程被 token 截断时输出乱码产生的控制字符):
1. 0x07 (BEL)
2. 0x08 (BS)
3. 0x0b (VT)
4. 0x0c (FF)
5. 0x1a (SUB)

注意:这些字符是 token 截断时输出乱码,正常 UTF-8 文件里不应该有

用法:
    python verify_control.py <article.md>
"""
import sys


def verify_control(path: str) -> int:
    with open(path, 'rb') as f:
        b = f.read()

    bad_chars = [0x07, 0x08, 0x0b, 0x0c, 0x1a]
    print(f'=== verify_control: {path} ===')
    fail = 0
    for c in bad_chars:
        n = b.count(bytes([c]))
        if n > 0:
            print(f'0x{c:02x}: {n} 处 ❌')
            fail += 1
        else:
            print(f'0x{c:02x}: 0 ✅')

    if fail == 0:
        print('\n✅ ALL PASS')
        return 0
    else:
        print(f'\n❌ FAIL ({fail} 项)')
        return 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python verify_control.py <article.md>')
        sys.exit(2)
    sys.exit(verify_control(sys.argv[1]))
