"""看 R 行真实格式"""
import subprocess
REPO = r'C:\Users\deepLife\Documents\GitHub\smc-pub'
r = subprocess.run(
    ['git', 'status', '--porcelain', '-z'],
    capture_output=True,
    text=True,
    encoding='utf-8',
    cwd=REPO,
)
items = r.stdout.split('\x00')
# 找 R 开头
for it in items:
    if it.startswith('R'):
        print(f'  [R-format] {repr(it[:200])}')
        break
