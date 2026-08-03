from pathlib import Path
REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')
locs = [
    REPO / '02-Symptom',
    REPO / 'docs' / '02-Symptom',
    REPO / 'docs' / '02-Symptom' / 'S11-Startup' / 'D-启动工具' / 'D01-Perfetto-Boot-Trace抓全栈启动时序.md',
    REPO / '03-Forensics',
    REPO / '04-Tool',
    REPO / '05-Governance',
    REPO / '06-Case',
    REPO / '06-Foundation',
]
for d in locs:
    rel = d.relative_to(REPO) if d.exists() else '(NO)'
    print(f'  {rel}: {d.exists()}')
