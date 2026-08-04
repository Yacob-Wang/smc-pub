"""v6 run_all.py — 一键跑全部 v6 verify 工具

用法:
    python run_all.py <article.md>

会依次跑:
1. verify_marker.py (v6 §9.2 marker 规范)
2. verify_strip.py (v6 §9.4 公开站剥离)
3. verify_colon.py (v6 §3.5 跨篇全角冒号)
4. verify_paths.py (v6 §12.1 已知幻觉)
5. verify_bug6.py (v6 §12.2 子线程 6 类)
6. verify_control.py (v6 §12.2 控制字符)
7. verify_ai_words.py (v6 §5.3 反 AI 自嗨词表)

返回: 全部 PASS 返回 0,任一 FAIL 返回 1
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = [
    'verify_marker.py',
    'verify_strip.py',
    'verify_colon.py',
    'verify_paths.py',
    'verify_bug6.py',
    'verify_control.py',
    'verify_ai_words.py',
]


def main():
    if len(sys.argv) < 2:
        print('用法: python run_all.py <article.md>')
        sys.exit(2)
    article = sys.argv[1]
    if not os.path.isfile(article):
        print(f'❌ 文件不存在: {article}')
        sys.exit(2)

    print('=' * 60)
    print(f'v6 全部 verify 一键跑 — {article}')
    print('=' * 60)

    fails = 0
    for tool in TOOLS:
        tool_path = os.path.join(HERE, tool)
        if not os.path.isfile(tool_path):
            print(f'⚠️ 工具缺失: {tool}')
            continue
        print()
        result = subprocess.run(
            [sys.executable, tool_path, article],
            capture_output=False,
        )
        if result.returncode != 0:
            fails += 1

    print()
    print('=' * 60)
    if fails == 0:
        print('✅ ALL TOOLS PASS')
        sys.exit(0)
    else:
        print(f'❌ {fails} / {len(TOOLS)} tools FAIL')
        sys.exit(1)


if __name__ == '__main__':
    main()
