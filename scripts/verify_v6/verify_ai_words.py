"""v6 verify_ai_words.py — v6 §5.3 反 AI 自嗨词表

分两类:
1. STRICT(FAIL 0 容忍):AI 自嗨高频词
   一定 / 必然 / 必定 / 极其 / 极度 / 相当 / 精妙 / 卓越 / 杰出 / 突出 / 优秀
   体现了 / 彰显了 / 凸显了 / 充分证明 / 深入浅出
   深度融合 / 高度集成 / 无缝衔接
2. WARN(高频合法词,作者自觉少用):不 FAIL,只给提醒
   可能 / 通常 / 大约 / 大概 / 系统 / 完整

注意:必须用 chr() 拼字符串(绕过 system prompt 渲染陷阱,见 v6 §10.1)

用法:
    python verify_ai_words.py <article.md>
"""
import re
import sys


def chr_join(s: str) -> bytes:
    return ''.join(chr(ord(c)) for c in s).encode('utf-8')


# STRICT 词(FAIL 0 容忍)
STRICT_WORDS = [
    '一定', '必然', '必定',                  # 必然词
    '极其', '极度', '相当',                  # 程度副词
    '精妙', '卓越', '杰出', '突出', '优秀',  # 评价词
    '体现了', '彰显了', '凸显了', '充分证明',  # 强调词
    '深入浅出',                              # 程度副词(2)
    '深度融合', '高度集成', '无缝衔接',       # 强调短语
]

# WARN 词(高频合法但要自觉少用)
WARN_WORDS = [
    '可能', '通常', '大约', '大概',          # 模糊程度
    '系统', '完整',                          # 高频合法
]


def verify_ai_words(path: str) -> int:
    with open(path, 'rb') as f:
        b = f.read()
    content = b.decode('utf-8', errors='replace')

    print(f'=== verify_ai_words: {path} ===')
    fail = 0
    warn = 0

    print('-- STRICT (FAIL 0 容忍) --')
    for word in STRICT_WORDS:
        n = content.count(word)
        if n > 0:
            print(f'  "{word}": {n} 处 ❌')
            fail += n
        else:
            print(f'  "{word}": 0 ✅')

    print('-- WARN (高频合法词,自觉少用) --')
    for word in WARN_WORDS:
        n = content.count(word)
        if n > 0:
            print(f'  "{word}": {n} 处 ⚠️  WARN(不 FAIL,自觉少用)')
            warn += n
        else:
            print(f'  "{word}": 0 ✅')

    print()
    if fail == 0:
        print(f'✅ STRICT ALL PASS / WARN 共 {warn} 处')
        return 0
    else:
        print(f'❌ FAIL ({fail} STRICT 项, {warn} WARN 项)')
        return 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python verify_ai_words.py <article.md>')
        sys.exit(2)
    sys.exit(verify_ai_words(sys.argv[1]))
