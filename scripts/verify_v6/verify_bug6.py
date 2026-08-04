"""v6 verify_bug6.py — v6 §12.2 子线程 6 类写入 bug

检查项(独立匹配,排除 frameworks 等子串):
1. aart/ (多 a,正确 art/)
2. vvmscan (多 v,正确 vmscan)
3. rameworks (缺 f,正确 frameworks)
4. ndroid: (缺 a,正确 android:)
5. m_kill (缺 a,正确 am_kill)
6. o.lmk (缺 r,正确 ro.lmk)

注意:必须用 chr() 拼字符串(绕过 system prompt 渲染陷阱,见 v6 §10.1)

用法:
    python verify_bug6.py <article.md>
"""
import re
import sys


def chr_join(s: str) -> bytes:
    """用 chr() 拼接字符串,绕过 system prompt 渲染陷阱"""
    return ''.join(chr(ord(c)) for c in s).encode('utf-8')


def verify_bug6(path: str) -> int:
    with open(path, 'rb') as f:
        b = f.read()

    # 用 chr() 拼字符串,避免 system prompt 把 'aart/' 和 'art/' 规范化成同一个
    bug6 = [
        ('aart/', chr_join('aart/')),       # 独立 aart/(排除 frame 中的 'aart')
        ('vvmscan', chr_join('vvmscan')),
        ('rameworks', chr_join('rameworks')),  # 独立 rameworks(排除 frame 中的 'rameworks')
        ('ndroid:', chr_join('ndroid:')),     # 排除 'android:' 命名空间
        ('m_kill', chr_join('m_kill')),
        ('o.lmk', chr_join('o.lmk')),
    ]

    print(f'=== verify_bug6: {path} ===')
    fail = 0
    for name, pat in bug6:
        # 用 negative lookbehind 排除合法子串
        if name == 'rameworks':
            # 排除 'frameworks'
            regex = rb'(?<!f)' + re.escape(pat)
        elif name == 'ndroid:':
            # 排除 'android:' 命名空间(Android manifest 合法属性)
            regex = rb'(?<!a)' + re.escape(pat)
        else:
            # aart/ / vvmscan / m_kill / o.lmk 不会被合法词包含
            regex = re.escape(pat)
        n = len(re.findall(regex, b))
        if n > 0:
            print(f'{name}: {n} 处 ❌')
            fail += 1
        else:
            print(f'{name}: 0 ✅')

    if fail == 0:
        print('\n✅ ALL PASS')
        return 0
    else:
        print(f'\n❌ FAIL ({fail} 项)')
        return 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python verify_bug6.py <article.md>')
        sys.exit(2)
    sys.exit(verify_bug6(sys.argv[1]))
