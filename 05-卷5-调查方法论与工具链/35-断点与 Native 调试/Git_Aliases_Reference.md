# Git 别名参考手册

## 📋 概述

已为您配置了常用的 Git 别名，让 Git 命令更简短易用。

## 🚀 常用命令别名

### 状态和查看

| 别名 | 完整命令 | 说明 |
|------|---------|------|
| `git st` | `git status` | 查看工作区状态 |
| `git ll` | `git log --oneline` | 简洁的提交历史 |
| `git lg` | `git log --color --graph --pretty=format:...` | 美观的图形化提交历史 |
| `git last` | `git log -1 HEAD` | 查看最后一次提交 |
| `git df` | `git diff` | 查看工作区差异 |
| `git dc` | `git diff --cached` | 查看暂存区差异 |

### 分支操作

| 别名 | 完整命令 | 说明 |
|------|---------|------|
| `git br` | `git branch` | 查看分支列表 |
| `git co` | `git checkout` | 切换分支 |
| `git co -b <name>` | `git checkout -b <name>` | 创建并切换分支 |

### 提交操作

| 别名 | 完整命令 | 说明 |
|------|---------|------|
| `git ci` | `git commit` | 提交更改 |
| `git cm "message"` | `git commit -m "message"` | 提交并添加消息 |
| `git ca` | `git commit -a` | 提交所有已跟踪文件的更改 |
| `git cam "message"` | `git commit -am "message"` | 提交所有更改并添加消息 |
| `git amend` | `git commit --amend` | 修改最后一次提交 |
| `git undo` | `git reset HEAD~1` | 撤销最后一次提交（保留更改） |

### 添加和暂存

| 别名 | 完整命令 | 说明 |
|------|---------|------|
| `git aa` | `git add .` | 添加所有文件到暂存区 |
| `git unstage <file>` | `git reset HEAD -- <file>` | 取消暂存文件 |

### 远程操作

| 别名 | 完整命令 | 说明 |
|------|---------|------|
| `git ps` | `git push` | 推送到远程 |
| `git pl` | `git pull` | 从远程拉取 |
| `git f` | `git fetch` | 获取远程更新 |
| `git r` | `git remote` | 管理远程仓库 |
| `git rv` | `git remote -v` | 查看远程仓库地址 |
| `git cl <url>` | `git clone <url>` | 克隆仓库 |

### Stash 操作

| 别名 | 完整命令 | 说明 |
|------|---------|------|
| `git stash-all` | `git stash --include-untracked` | 暂存所有更改（包括未跟踪文件） |
| `git stash-list` | `git stash list` | 查看暂存列表 |
| `git stash-pop` | `git stash pop` | 应用并删除最新的暂存 |
| `git stash-apply` | `git stash apply` | 应用最新的暂存（不删除） |

## 💡 使用示例

### 日常开发流程

```bash
# 查看状态
git st

# 添加所有更改
git aa

# 提交更改
git cm "fix: 修复某个bug"

# 推送到远程
git ps
```

### 查看历史

```bash
# 简洁的提交历史
git ll

# 美观的图形化历史
git lg

# 查看最后一次提交
git last
```

### 分支操作

```bash
# 查看所有分支
git br

# 创建新分支
git co -b feature/new-feature

# 切换分支
git co main
```

### 撤销操作

```bash
# 取消暂存某个文件
git unstage file.txt

# 撤销最后一次提交（保留更改）
git undo
```

## 📝 查看所有别名

要查看所有已配置的别名，可以使用：

```bash
git config --global --list | grep alias
```

或者：

```bash
git config --global --get-regexp alias
```

## 🔧 自定义别名

如果您想添加更多别名，可以使用：

```bash
git config --global alias.<别名> <命令>
```

例如：

```bash
# 添加一个查看未跟踪文件的别名
git config --global alias.untracked "ls-files --others --exclude-standard"

# 添加一个查看所有分支（包括远程）的别名
git config --global alias.bra "branch -a"
```

## ⚠️ 注意事项

1. **全局配置**：这些别名是全局配置的，对所有 Git 仓库都有效
2. **别名冲突**：如果别名与 Git 内置命令冲突，别名会优先
3. **参数传递**：别名可以接受参数，例如 `git cm "message"`

## 🎯 推荐工作流

```bash
# 1. 查看状态
git st

# 2. 添加更改
git aa

# 3. 提交
git cm "你的提交信息"

# 4. 推送
git ps
```

---

**提示**：这些别名已经配置为全局设置，您可以在任何 Git 仓库中使用它们！
