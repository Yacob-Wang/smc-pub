"""v6 verify_paths.py — v6 §12.1 已知路径/类名/作者/时间线 blacklist

检查项:
1. 路径 blacklist:kernel/cgroup/memcontrol.c / aart/ / vvmscan 等
2. 类名 blacklist:class GenerationalCC / Heap::IsAIAgentApp() / ProcessRecord::setAIApp() 等
3. 作者 blacklist:Yuan Sun / Andrea Arcangeli 设计 MGLRU
4. 时间线 blacklist:2025-11-30 AOSP 17 发布 / MGLRU 5.10 合并 / Android 15 2024-09-18

用法:
    python verify_paths.py <article.md>
"""
import re
import sys

# 路径 blacklist(用 chr() 拼接绕过 system prompt 渲染陷阱,见 v6 §10.1)
PATH_BLACKLIST = [
    b'kernel/cgroup/memcontrol.c',     # 应 mm/memcontrol.c(Linux 3.8+)
    b'memcontrol-v2.c',                # 不存在
    b'memcontrol-v2.h',                # 不存在,正确是 include/linux/memcontrol.h
    b'aart/',                          # 多 a,正确是 art/
    b'vvmscan',                        # 多 v,正确是 vmscan
]

# 类名 blacklist
CLASS_BLACKLIST = [
    b'class GenerationalCC',           # ART 实际是 ConcurrentCopying
    b'Heap::IsAIAgentApp',             # AOSP 17 main 分支未见
    b'ProcessRecord::setAIApp',        # 实际无此方法
    b'system/memory/lmkd/memorylimiter.cpp',  # 实际是 Java 层
]

# 作者 blacklist
AUTHOR_BLACKLIST = [
    b'Yuan Sun \xe8\xae\xbe\xe8\xae\xa1 MGLRU'.replace(b'\n', b''),  # Yuan Sun 设计 MGLRU
    b'Andrea Arcangeli \xe8\xae\xbe\xe8\xae\xa1 MGLRU',
]

# 时间线 blacklist
TIMELINE_BLACKLIST = [
    b'2025-11-30 AOSP 17',  # 实际 Beta 1 2026-02-13
    b'MGLRU 5.10',          # 实际 Linux 5.9(commit ccd2a0d4)
    b'Android 15 2024-09-18',  # 实际 2024-10-15
]

# 正确事实强锁(v6 §1 关键事实校准)
FACTS = {
    b'ro.build.version.release=14' or b'Android 14.0': 'AOSP 14.0.0_r1 (UpsideDownCake)',
    b'ro.build.version.release=17' or b'Android 17.0': 'AOSP 17.0.0_r1 (CinnamonBun, 2026)',
}


def verify_paths(path: str) -> int:
    with open(path, 'rb') as f:
        b = f.read()

    print(f'=== verify_paths: {path} ===')
    fail = 0

    # 路径
    for p in PATH_BLACKLIST:
        n = len(re.findall(re.escape(p), b))
        if n > 0:
            print(f'1. 路径 blacklist 命中 "{p.decode()}": {n} 处 ❌')
            fail += 1
    if all(len(re.findall(re.escape(p), b)) == 0 for p in PATH_BLACKLIST):
        print('1. 路径 blacklist: 0 命中 ✅')

    # 类名
    for c in CLASS_BLACKLIST:
        n = len(re.findall(re.escape(c), b))
        if n > 0:
            print(f'2. 类名 blacklist 命中 "{c.decode()}": {n} 处 ❌')
            fail += 1
    if all(len(re.findall(re.escape(c), b)) == 0 for c in CLASS_BLACKLIST):
        print('2. 类名 blacklist: 0 命中 ✅')

    # 作者
    for a in AUTHOR_BLACKLIST:
        n = len(re.findall(re.escape(a), b))
        if n > 0:
            print(f'3. 作者 blacklist 命中 "{a.decode(errors="replace")}": {n} 处 ❌')
            fail += 1
    if all(len(re.findall(re.escape(a), b)) == 0 for a in AUTHOR_BLACKLIST):
        print('3. 作者 blacklist: 0 命中 ✅')

    # 时间线
    for t in TIMELINE_BLACKLIST:
        n = len(re.findall(re.escape(t), b))
        if n > 0:
            print(f'4. 时间线 blacklist 命中 "{t.decode()}": {n} 处 ❌')
            fail += 1
    if all(len(re.findall(re.escape(t), b)) == 0 for t in TIMELINE_BLACKLIST):
        print('4. 时间线 blacklist: 0 命中 ✅')

    if fail == 0:
        print('\n✅ ALL PASS')
        return 0
    else:
        print(f'\n❌ FAIL ({fail} 项)')
        return 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python verify_paths.py <article.md>')
        sys.exit(2)
    sys.exit(verify_paths(sys.argv[1]))
