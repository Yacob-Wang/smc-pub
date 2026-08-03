"""找 PUBLIC_MODULES 定义"""
import subprocess
r = subprocess.run(
    ['python', '-c', """
import re
text = open(r'C:\\Users\\deepLife\\Documents\\GitHub\\smc-pub\\00-Meta\\scripts\\prepare_web_docs.py', encoding='utf-8').read()
# 找 PUBLIC_MODULES = [
m = re.search(r'PUBLIC_MODULES\\s*=\\s*\\[(.*?)\\]', text, re.DOTALL)
if m:
    print(m.group()[:2000])
else:
    print('NOT FOUND')
"""],
    capture_output=True,
    text=True,
    encoding='utf-8',
)
print(r.stdout)
print('STDERR:', r.stderr)
