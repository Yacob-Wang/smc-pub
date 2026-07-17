查看 tag 的常用方法如下：

## 1. 查看所有 tag

```powershell
# 列出所有 tag
git tag

# 按版本排序列出 tag
git tag -l | Sort-Object

# 列出匹配特定模式的 tag（例如 android13-5.15 相关的）
git tag -l "android13-5.15*"
```

## 2. 查看 tag 的详细信息

```powershell
# 查看特定 tag 的详细信息（包括提交信息、作者、日期等）
git show android13-5.15-2024-11_r3

# 只查看 tag 的提交信息
git log -1 android13-5.15-2024-11_r3

# 查看 tag 指向的提交哈希
git rev-parse android13-5.15-2024-11_r3
```

## 3. 查看 tag 包含的文件

```powershell
# 查看 tag 的目录树结构
git ls-tree -r android13-5.15-2024-11_r3

# 统计 tag 中的文件数量
git ls-tree -r android13-5.15-2024-11_r3 | Measure-Object -Line

# 查看 tag 中特定目录的内容
git ls-tree -r android13-5.15-2024-11_r3 --name-only | Select-String "arch/arm64"
```

## 4. 比较不同 tag

```powershell
# 查看两个 tag 之间的差异统计
git diff --stat android13-5.15-2024-11_r3 android13-5.15-2025-01_r1

# 查看两个 tag 之间的提交历史
git log --oneline android13-5.15-2024-11_r3..android13-5.15-2025-01_r1

# 查看特定文件在不同 tag 中的差异
git diff android13-5.15-2024-11_r3 android13-5.15-2025-01_r1 -- arch/arm64/mm/mmu.c
```

## 5. 查看当前所在的 tag

```powershell
# 查看当前 HEAD 指向的 tag（如果处于 detached HEAD 状态）
git describe --tags

# 查看当前所在的 tag 和提交信息
git describe --tags --exact-match
git log -1 --oneline
```

## 6. 查看远程 tag

```powershell
# 查看所有远程 tag
git ls-remote --tags origin

# 只查看远程 tag 名称
git ls-remote --tags origin | Select-String "android13-5.15"
```

## 7. 查看 tag 的创建时间和排序

```powershell
# 按时间顺序列出 tag（最新的在前）
git tag --sort=-creatordate

# 查看 tag 的详细信息（包括创建时间）
git for-each-ref --sort=-creatordate --format='%(refname:short) %(creatordate) %(subject)' refs/tags | Select-String "android13-5.15"
```

## 实用示例

查看所有 android13-5.15 相关的 tag，并按时间排序：

```powershell
cd D:\ACK\common
git tag -l "android13-5.15*" | Sort-Object
```

查看某个 tag 是否包含完整源码（通过文件数量判断）：

```powershell
cd D:\ACK\common
# 查看完整源码的 tag（应该有很多文件）
git ls-tree -r android13-5.15-2024-11_r3 | Measure-Object -Line

# 查看新 tag（可能只有很少文件）
git ls-tree -r android13-5.15-2025-01_r1 | Measure-Object -Line
```

查看当前状态和最近的 tag：

```powershell
cd D:\ACK\common
# 查看当前所在的 tag
git describe --tags

# 查看最近的几个 tag
git tag --sort=-creatordate | Select-Object -First 10
```

需要我帮你查看特定的 tag 信息吗？可以告诉我你想查看哪个 tag，或切换到 agent mode 让我直接运行命令。