# Git 基础

## 📋 学习目标

掌握 Git 的基本概念和常用操作，能够独立完成日常开发工作。

## 📚 学习内容

### 第一章：Git 入门

#### 1.1 Git 是什么
- Git 的定义和特点
- 版本控制系统的分类
- Git 与其他版本控制系统的区别
- Git 的历史和发展

#### 1.2 安装和配置

##### 安装 Git

**Windows**：
1. 下载安装包：访问 https://git-scm.com/download/win
2. 运行安装程序，使用默认选项
3. 安装完成后，在命令行验证

**Mac**：
```bash
# 使用 Homebrew（推荐）
brew install git

# 或下载安装包
# 访问 https://git-scm.com/download/mac
```

**Linux**：
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install git

# CentOS/RHEL
sudo yum install git

# Fedora
sudo dnf install git
```

##### 验证安装

```bash
git --version
```
- 输出示例：`git version 2.40.0`
- 如果显示版本号，说明安装成功
- 如果提示"命令未找到"，需要检查 PATH 环境变量

##### Git 配置的三个级别

Git 配置有三个级别，优先级从高到低：

1. **本地配置**（`.git/config`）：只对当前仓库有效
2. **全局配置**（`~/.gitconfig`）：对当前用户的所有仓库有效
3. **系统配置**（`/etc/gitconfig`）：对所有用户有效

**配置命令**：
```bash
# 本地配置（不加参数）
git config user.name "Your Name"

# 全局配置（--global）
git config --global user.name "Your Name"

# 系统配置（--system，需要管理员权限）
git config --system user.name "Your Name"
```

##### 基本配置

**1. 配置用户信息（必须）**

```bash
# 配置用户名
git config --global user.name "Your Name"

# 配置邮箱
git config --global user.email "your.email@example.com"
```

**为什么需要配置？**
- Git 需要知道谁做了提交
- 提交信息中会包含作者信息
- 用于代码审查和问题追踪

**注意事项**：
- 使用真实姓名和邮箱
- 如果使用 GitHub，邮箱要与 GitHub 账户关联
- 可以为不同仓库配置不同的用户信息

**2. 配置编辑器**

```bash
# 使用 VS Code
git config --global core.editor "code --wait"

# 使用 Vim
git config --global core.editor "vim"

# 使用 Nano
git config --global core.editor "nano"

# Windows 使用记事本
git config --global core.editor "notepad"
```

**什么时候会用到编辑器？**
- 编写提交信息（不使用 `-m` 参数时）
- 交互式 rebase
- 合并冲突标记

**3. 配置默认分支名称**

```bash
# 设置默认分支为 main（而不是 master）
git config --global init.defaultBranch main
```

##### 查看配置

**查看所有配置**：
```bash
git config --list
```

**查看特定配置**：
```bash
# 查看用户名
git config user.name

# 查看邮箱
git config user.email

# 查看编辑器
git config core.editor
```

**查看配置来源**：
```bash
git config --list --show-origin
```
- 显示每个配置的来源文件
- 帮助理解配置的优先级

**查看配置的完整路径**：
```bash
git config --list --show-scope
```
- 显示配置的作用域（local、global、system）

##### 其他常用配置

**1. 配置行尾符处理**

```bash
# Windows（推荐）
git config --global core.autocrlf true

# Mac/Linux
git config --global core.autocrlf input

# 禁用自动转换
git config --global core.autocrlf false
```

**说明**：
- Windows 使用 CRLF（`\r\n`），Unix 使用 LF（`\n`）
- `true`：提交时转换为 LF，检出时转换为 CRLF
- `input`：提交时转换为 LF，检出时不转换
- `false`：不进行转换

**2. 配置颜色输出**

```bash
# 启用颜色
git config --global color.ui auto

# 或分别配置
git config --global color.branch auto
git config --global color.diff auto
git config --global color.status auto
```

**3. 配置别名（提高效率）**

```bash
# 查看状态
git config --global alias.st status

# 查看简洁日志
git config --global alias.ll "log --oneline"

# 查看图形化日志
git config --global alias.lg "log --graph --oneline --all"
```

##### 编辑配置文件

**直接编辑配置文件**：
```bash
# 编辑全局配置
git config --global --edit

# 编辑本地配置
git config --edit
```

**配置文件格式**：
```ini
[user]
    name = Your Name
    email = your.email@example.com
[core]
    editor = code --wait
    autocrlf = true
[alias]
    st = status
    ll = log --oneline
```

##### 删除配置

```bash
# 删除全局配置
git config --global --unset user.name

# 删除本地配置
git config --unset user.name
```

#### 1.3 创建第一个仓库

##### 初始化新仓库

**命令**：
```bash
git init
```

**作用**：
- 在当前目录创建新的 Git 仓库
- 创建 `.git` 目录（隐藏目录）
- 初始化仓库结构

**完整流程**：
```bash
# 1. 创建项目目录
mkdir my-project
cd my-project

# 2. 初始化 Git 仓库
git init

# 输出：Initialized empty Git repository in /path/to/my-project/.git/

# 3. 查看状态
git status
# 输出：On branch main（或 master，取决于配置）
```

**在已有目录中初始化**：
```bash
# 如果目录已有文件
cd existing-project
git init
git add .
git commit -m "Initial commit"
```

**指定目录初始化**：
```bash
# 在当前目录创建指定名称的目录并初始化
git init my-project
```

##### 克隆现有仓库

**命令格式**：
```bash
git clone <repository-url> [directory-name]
```

**克隆方式**：

1. **HTTPS 克隆**（最常用）
   ```bash
   git clone https://github.com/user/repo.git
   ```
   - 需要输入用户名和密码（或 token）
   - 适合所有情况

2. **SSH 克隆**（推荐）
   ```bash
   git clone git@github.com:user/repo.git
   ```
   - 需要配置 SSH 密钥
   - 不需要每次输入密码
   - 更安全

3. **指定目录名**
   ```bash
   git clone https://github.com/user/repo.git my-project
   ```
   - 克隆到指定目录
   - 如果不指定，使用仓库名作为目录名

**克隆选项**：

```bash
# 浅克隆（只克隆最近的历史）
git clone --depth 1 https://github.com/user/repo.git

# 克隆特定分支
git clone -b main https://github.com/user/repo.git

# 克隆但不检出工作目录（只获取 .git）
git clone --bare https://github.com/user/repo.git

# 克隆并指定远程名称
git clone -o upstream https://github.com/user/repo.git
```

##### 仓库的基本结构

**初始化后的目录结构**：
```
my-project/
├── .git/              # Git 仓库数据（隐藏目录）
│   ├── HEAD           # 当前分支引用
│   ├── config         # 仓库配置
│   ├── objects/       # 对象存储
│   ├── refs/          # 引用（分支、标签）
│   └── ...
└── （你的项目文件）
```

##### `.git` 目录详解

**重要文件和目录**：

1. **HEAD**
   - 指向当前分支
   - 内容示例：`ref: refs/heads/main`

2. **config**
   - 仓库的配置文件
   - 包含远程仓库、分支等信息

3. **objects/**
   - 存储所有 Git 对象（blob、tree、commit）
   - 使用 SHA-1 哈希组织

4. **refs/**
   - `heads/`：本地分支引用
   - `tags/`：标签引用
   - `remotes/`：远程分支引用

5. **index**
   - 暂存区（索引）
   - 二进制文件

6. **hooks/**
   - Git hooks 脚本
   - 可以自定义 Git 行为

**查看 .git 目录**：
```bash
# 显示隐藏文件
ls -la

# 查看 HEAD
cat .git/HEAD

# 查看配置
cat .git/config
```

##### 远程仓库

**查看远程仓库**：
```bash
git remote -v
```

**添加远程仓库**：
```bash
# 添加远程仓库（origin 是默认名称）
git remote add origin https://github.com/user/repo.git

# 添加多个远程仓库
git remote add upstream https://github.com/original/repo.git
```

**远程仓库操作**：
```bash
# 查看远程仓库
git remote show origin

# 重命名远程仓库
git remote rename origin upstream

# 删除远程仓库
git remote remove origin

# 修改远程仓库 URL
git remote set-url origin https://github.com/user/new-repo.git
```

---

### 第二章：基本操作

#### 2.1 工作区、暂存区、仓库

##### 三个区域的概念

Git 有三个重要的区域，理解它们对掌握 Git 至关重要：

**1. 工作区（Working Directory）**

- **定义**：你正在编辑的文件所在的目录
- **特点**：
  - 就是你的项目文件夹
  - 可以直接编辑文件
  - 文件修改后不会自动保存到 Git

**2. 暂存区（Staging Area / Index）**

- **定义**：准备提交的文件临时存放的地方
- **特点**：
  - 是一个中间状态
  - 可以选择性地添加文件
  - 允许你组织提交内容

**3. 仓库（Repository）**

- **定义**：Git 保存所有版本历史的地方
- **特点**：
  - 存储在 `.git` 目录中
  - 包含所有提交历史
  - 提交后文件才真正保存到仓库

##### 文件的状态

文件在 Git 中有四种状态：

**1. 未跟踪（Untracked）**

- 新创建的文件，Git 还没有跟踪
- 不会出现在 `git status` 的已跟踪文件列表中
- 需要 `git add` 添加到暂存区

**2. 已修改（Modified）**

- 文件已被 Git 跟踪
- 工作区中的文件已被修改
- 但修改还没有添加到暂存区

**3. 已暂存（Staged）**

- 文件已添加到暂存区
- 准备在下一次提交中包含
- 使用 `git add` 后进入此状态

**4. 已提交（Committed）**

- 文件已保存到仓库
- 成为 Git 历史的一部分
- 使用 `git commit` 后进入此状态

##### 状态转换流程

**完整流程图**：
```
未跟踪文件
    ↓ git add
已暂存
    ↓ git commit
已提交（在仓库中）
    ↓ 修改文件
已修改
    ↓ git add
已暂存
    ↓ git commit
已提交
```

**查看文件状态**：
```bash
git status
```

**输出示例**：
```
On branch main
Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
        new file:   new-file.txt

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
        modified:   modified-file.txt

Untracked files:
  (use "git add <file>..." to include in what will be committed)
        untracked-file.txt
```

**状态说明**：
- `Changes to be committed`：已暂存的文件
- `Changes not staged for commit`：已修改但未暂存
- `Untracked files`：未跟踪的文件

##### 为什么需要暂存区？

**暂存区的优势**：

1. **选择性提交**
   - 可以只提交部分修改
   - 将相关更改组织在一起
   - 创建更有意义的提交

2. **审查更改**
   - 在提交前查看暂存区的内容
   - 确保提交的内容正确
   - 避免提交错误

3. **分批提交**
   - 可以将大量更改分成多个提交
   - 每个提交解决一个问题
   - 便于代码审查和问题追踪

**示例场景**：
```bash
# 修改了多个文件
# file1.txt - 修复 bug
# file2.txt - 添加新功能
# file3.txt - 更新文档

# 只提交 bug 修复
git add file1.txt
git commit -m "Fix bug in file1"

# 然后提交新功能
git add file2.txt
git commit -m "Add new feature"

# 最后提交文档更新
git add file3.txt
git commit -m "Update documentation"
```

#### 2.2 添加和提交

##### git add 详解

**基本用法**：
```bash
git add <file>
```

**作用**：
- 将文件从工作区添加到暂存区
- 标记文件为"准备提交"状态
- 不会立即提交，只是准备

**常用方式**：

1. **添加单个文件**
   ```bash
   git add file.txt
   ```

2. **添加多个文件**
   ```bash
   git add file1.txt file2.txt file3.txt
   ```

3. **添加所有文件**
   ```bash
   git add .
   ```
   - 添加当前目录及子目录中的所有文件
   - 包括新文件和已修改的文件
   - ⚠️ 注意：会添加所有文件，包括临时文件

4. **添加所有已修改的文件**
   ```bash
   git add -u
   # 或
   git add --update
   ```
   - 只添加已跟踪的已修改文件
   - 不添加新文件

5. **使用通配符**
   ```bash
   git add *.js              # 所有 .js 文件
   git add src/*.java        # src 目录下所有 .java 文件
   git add "*.txt"           # 所有 .txt 文件（引号防止 shell 展开）
   ```

6. **交互式添加**
   ```bash
   git add -i
   # 或
   git add --interactive
   ```
   - 交互式选择要添加的文件
   - 可以选择部分更改（hunk）

7. **添加部分更改**
   ```bash
   git add -p
   # 或
   git add --patch
   ```
   - 交互式选择文件中的部分更改
   - 可以将一个文件的修改分成多次提交

**参数说明**：
- `-A` 或 `--all`：添加所有更改（新文件、修改、删除）
- `-u` 或 `--update`：只添加已跟踪文件的更改
- `-f` 或 `--force`：强制添加被忽略的文件
- `-n` 或 `--dry-run`：预览将要添加的文件，不实际添加
- `-v` 或 `--verbose`：显示详细信息

**查看将要添加的内容**：
```bash
# 预览
git add -n .

# 查看暂存区内容
git diff --cached
# 或
git diff --staged
```

##### git commit 详解

**基本用法**：
```bash
git commit -m "提交信息"
```

**作用**：
- 将暂存区的更改保存到仓库
- 创建一个新的提交对象
- 提交后，更改成为 Git 历史的一部分

**提交信息的重要性**：

好的提交信息应该：
- ✅ 清晰描述做了什么
- ✅ 说明为什么这样做（如果需要）
- ✅ 遵循团队规范
- ❌ 避免无意义的描述（如"fix"、"update"）

**提交信息格式**（推荐）：
```
<type>: <subject>

<body>

<footer>
```

**示例**：
```
feat: Add user authentication

Implement login and logout functionality with JWT tokens.
Add password hashing using bcrypt.

Closes #123
```

**常用参数**：

1. **-m：添加提交信息**
   ```bash
   git commit -m "Fix bug"
   ```

2. **-a：自动添加已跟踪文件的更改**
   ```bash
   git commit -am "Quick commit"
   ```
   - 相当于 `git add -u` + `git commit`
   - ⚠️ 只添加已跟踪的文件，不添加新文件

3. **--amend：修改最后一次提交**
   ```bash
   git commit --amend -m "New message"
   ```
   - 修改提交信息
   - 或添加遗漏的文件

4. **--no-verify：跳过 hooks**
   ```bash
   git commit --no-verify -m "Commit"
   ```
   - 跳过 pre-commit 等 hooks
   - ⚠️ 谨慎使用

5. **-v：显示更改内容**
   ```bash
   git commit -v -m "Commit message"
   ```
   - 在编辑器中显示更改内容
   - 帮助编写更好的提交信息

**多行提交信息**：
```bash
# 不使用 -m，打开编辑器
git commit

# 或在 -m 后使用换行
git commit -m "First line

Second line with more details."
```

**提交信息模板**：
```bash
# 配置模板
git config --global commit.template ~/.gitmessage

# 模板内容示例
cat > ~/.gitmessage << 'EOF'
# <type>: <subject>
#
# <body>
#
# <footer>
EOF
```

##### 查看提交历史

**git log 详解**

**基本用法**：
```bash
git log
```

**常用选项**：

1. **简洁模式**
   ```bash
   git log --oneline
   ```
   - 每个提交显示一行
   - 只显示哈希和提交信息

2. **图形化显示**
   ```bash
   git log --graph
   ```
   - 显示分支和合并的可视化图形

3. **显示更改内容**
   ```bash
   git log -p
   # 或
   git log --patch
   ```
   - 显示每个提交的详细更改

4. **限制显示数量**
   ```bash
   git log -5              # 最近 5 个提交
   git log -n 10           # 最近 10 个提交
   ```

5. **按作者筛选**
   ```bash
   git log --author="John"
   ```

6. **按时间筛选**
   ```bash
   git log --since="2 weeks ago"
   git log --until="2024-01-01"
   ```

7. **按文件筛选**
   ```bash
   git log -- file.txt
   ```

8. **组合使用**
   ```bash
   git log --oneline --graph --all -10
   ```

**格式化输出**：
```bash
# 自定义格式
git log --pretty=format:"%h - %an, %ar : %s"

# 格式说明：
# %h: 简短哈希
# %an: 作者名
# %ar: 相对时间
# %s: 提交信息
```

**查看统计信息**：
```bash
git log --stat              # 显示更改的文件统计
git log --shortstat         # 只显示统计摘要
```

#### 2.3 查看更改

##### git diff 详解

**git diff** 用于查看文件之间的差异，是 Git 中最常用的命令之一。

**基本用法**：

1. **查看工作区更改**（未暂存的更改）
   ```bash
   git diff
   ```
   - 显示工作区与暂存区的差异
   - 只显示已修改但未暂存的文件

2. **查看暂存区更改**（已暂存的更改）
   ```bash
   git diff --staged
   # 或
   git diff --cached
   ```
   - 显示暂存区与最后一次提交的差异
   - 显示即将提交的内容

3. **查看两个提交之间的差异**
   ```bash
   git diff HEAD~1 HEAD
   git diff <commit1> <commit2>
   ```

4. **查看特定文件的更改**
   ```bash
   git diff file.txt
   git diff --staged file.txt
   ```

**输出格式说明**：

```
diff --git a/file.txt b/file.txt
index 1234567..abcdefg 100644
--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,4 @@
 line 1
-line 2 (删除的行，以 - 开头)
+line 2 modified (修改的行)
+new line (新增的行，以 + 开头)
 line 3
```

**常用选项**：

```bash
# 只显示文件名，不显示内容
git diff --name-only

# 显示统计信息
git diff --stat

# 显示简短统计
git diff --shortstat

# 忽略空白字符的差异
git diff -w
git diff --ignore-all-space

# 显示单词级别的差异（而不是行级别）
git diff --word-diff

# 并排显示差异
git diff --side-by-side
```

##### git show 详解

**git show** 用于显示特定对象（提交、标签、树等）的详细信息。

**基本用法**：

1. **查看最后一次提交**
   ```bash
   git show
   # 或
   git show HEAD
   ```

2. **查看特定提交**
   ```bash
   git show <commit-hash>
   git show abc1234
   ```

3. **查看提交的特定文件**
   ```bash
   git show HEAD:file.txt
   git show abc1234:path/to/file.txt
   ```

**输出内容**：
- 提交信息（作者、时间、消息）
- 提交的更改内容（类似 `git diff`）
- 统计信息

**常用选项**：

```bash
# 只显示提交信息，不显示更改
git show --stat

# 只显示提交信息
git show --pretty=fuller

# 只显示更改的文件名
git show --name-only

# 显示特定文件的更改
git show HEAD -- file.txt
```

##### 其他查看命令

**git status 详细输出**：
```bash
# 简短输出
git status -s
git status --short

# 显示未跟踪文件的详细信息
git status -u
git status --untracked-files=all
```

**git log 的更多用法**：
```bash
# 查看文件的提交历史
git log --follow -- file.txt

# 查看谁修改了文件的每一行
git blame file.txt

# 查看文件的完整历史（包括重命名）
git log --all --full-history -- file.txt
```

---

### 第三章：分支管理

#### 3.1 分支的概念
- 什么是分支
- 分支的作用
- 主分支（main/master）
- 分支的创建和切换

#### 3.2 基本分支操作

##### git branch 详解

**git branch** 用于管理分支：查看、创建、删除、重命名分支。

**查看分支**：

```bash
# 查看本地分支
git branch

# 查看所有分支（包括远程）
git branch -a

# 查看远程分支
git branch -r

# 显示更多信息（最后提交、跟踪关系）
git branch -v

# 显示跟踪关系
git branch -vv
```

**创建分支**：

```bash
# 基于当前分支创建新分支
git branch feature/new-feature

# 基于指定提交创建分支
git branch feature/new-feature abc1234

# 基于远程分支创建本地分支
git branch feature/new-feature origin/feature/new-feature
```

**删除分支**：

```bash
# 删除已合并的分支
git branch -d feature/old

# 强制删除分支（即使未合并）
git branch -D feature/old

# 删除远程分支（需要推送）
git push origin --delete feature/old
```

**重命名分支**：

```bash
# 重命名当前分支
git branch -m new-name

# 重命名指定分支
git branch -m old-name new-name
```

##### git checkout 详解

**git checkout** 用于切换分支或恢复文件。

**切换分支**：

```bash
# 切换到指定分支
git checkout main

# 创建并切换到新分支
git checkout -b feature/new-feature

# 基于远程分支创建并切换
git checkout -b feature/new origin/feature/new
```

**恢复文件**（旧方式，不推荐）：

```bash
# 恢复工作区的文件（丢弃更改）
git checkout -- file.txt

# 从指定提交恢复文件
git checkout HEAD~1 -- file.txt
```

**⚠️ 注意**：`git checkout` 功能太多，容易混淆。Git 2.23+ 引入了更明确的命令：
- `git switch`：专门用于切换分支
- `git restore`：专门用于恢复文件

##### git switch 详解（推荐）

**git switch** 是 Git 2.23+ 引入的新命令，专门用于切换分支，更清晰明确。

**基本用法**：

```bash
# 切换到现有分支
git switch main

# 创建并切换到新分支
git switch -c feature/new-feature

# 基于远程分支创建并切换
git switch -c feature/new origin/feature/new
```

**参数说明**：
- `-c` 或 `--create`：创建新分支
- `-C`：强制创建（如果分支已存在则覆盖）

**优势**：
- ✅ 功能单一，不会误操作
- ✅ 命令更直观
- ✅ 避免与文件恢复混淆

##### git merge 详解

**git merge** 用于合并分支，将另一个分支的更改合并到当前分支。

**基本用法**：

```bash
# 1. 切换到目标分支
git checkout main

# 2. 合并功能分支
git merge feature/new-feature
```

**合并类型**：

1. **Fast-forward 合并**（快进合并）
   - 如果目标分支没有新的提交
   - Git 只需要移动指针
   - 不会创建合并提交
   - 历史保持线性

2. **三方合并**（Three-way merge）
   - 如果两个分支都有新提交
   - Git 创建新的合并提交
   - 历史出现分叉和合并

**合并选项**：

```bash
# 禁止 fast-forward，总是创建合并提交
git merge --no-ff feature/new-feature

# 只合并，不提交（可以检查后再提交）
git merge --no-commit feature/new-feature

# 使用指定的合并策略
git merge -s ours feature/new-feature    # 使用我们的版本
git merge -s theirs feature/new-feature  # 使用他们的版本（很少用）
```

**合并后操作**：

```bash
# 如果合并成功，自动创建提交
# 如果遇到冲突，需要解决冲突后：
git add <resolved-files>
git commit
```

##### 合并冲突处理

**冲突产生的原因**：
- 两个分支修改了同一文件的同一部分
- Git 无法自动决定保留哪个版本

**识别冲突**：

```bash
# 查看冲突文件
git status
# 显示：both modified: file.txt
```

**冲突标记**：

```
<<<<<<< HEAD
当前分支的内容
=======
要合并的分支内容
>>>>>>> feature/new-feature
```

**解决冲突的步骤**：

1. **打开冲突文件**
   - 找到冲突标记
   - 理解两边的更改

2. **手动解决冲突**
   - 选择保留的内容
   - 或合并两边的更改
   - 删除冲突标记

3. **标记为已解决**
   ```bash
   git add resolved-file.txt
   ```

4. **完成合并**
   ```bash
   git commit
   ```

**使用合并工具**：

```bash
# 配置合并工具
git config --global merge.tool vimdiff

# 使用合并工具
git mergetool
```

**中止合并**：

```bash
# 如果想放弃合并
git merge --abort
```

#### 3.3 合并冲突
- 冲突产生的原因
- 识别冲突文件
- 解决冲突的方法
- 完成合并

**实践**：
```bash
# 合并时发生冲突
git merge feature/conflict

# 查看冲突文件
git status

# 手动解决冲突（编辑文件）
# <<<<<<< HEAD
# 当前分支的内容
# =======
# 要合并的分支内容
# >>>>>>> feature/conflict

# 解决后标记为已解决
git add resolved-file.txt
git commit
```

---

### 第四章：远程仓库

#### 4.1 远程仓库概念
- 什么是远程仓库
- 本地仓库与远程仓库的关系
- 常见的远程仓库服务（GitHub、GitLab、Gitee）

#### 4.2 远程仓库操作

##### git remote 详解

**git remote** 用于管理远程仓库的引用。

**查看远程仓库**：

```bash
# 列出所有远程仓库
git remote

# 显示详细信息（包括 URL）
git remote -v
# 输出：
# origin  https://github.com/user/repo.git (fetch)
# origin  https://github.com/user/repo.git (push)
```

**添加远程仓库**：

```bash
# 添加远程仓库（origin 是约定俗成的名称）
git remote add origin https://github.com/user/repo.git

# 添加多个远程仓库
git remote add upstream https://github.com/original/repo.git
```

**远程仓库名称说明**：
- `origin`：默认的远程仓库名称（克隆时自动设置）
- `upstream`：常用于 fork 的原始仓库
- 可以自定义任何名称

**其他操作**：

```bash
# 查看远程仓库详细信息
git remote show origin

# 重命名远程仓库
git remote rename origin upstream

# 修改远程仓库 URL
git remote set-url origin https://github.com/user/new-repo.git

# 删除远程仓库
git remote remove origin
```

##### git fetch 详解

**git fetch** 从远程仓库下载数据，但不会自动合并。

**基本用法**：

```bash
# 获取所有远程分支的更新
git fetch origin

# 获取特定远程分支
git fetch origin main

# 获取所有远程仓库的更新
git fetch --all
```

**作用**：
- ✅ 下载远程分支的最新提交
- ✅ 更新远程分支引用（如 `origin/main`）
- ✅ 不会修改工作区和当前分支
- ✅ 安全操作，不会丢失数据

**查看获取的内容**：

```bash
# 获取后查看远程分支
git branch -r

# 查看远程分支的提交
git log origin/main

# 比较本地和远程
git log main..origin/main
```

##### git pull 详解

**git pull** = `git fetch` + `git merge`，一次性完成获取和合并。

**基本用法**：

```bash
# 拉取当前分支的远程更新
git pull

# 拉取指定远程分支
git pull origin main

# 拉取并 rebase（而不是 merge）
git pull --rebase origin main
```

**工作原理**：

1. 执行 `git fetch` 获取远程更新
2. 自动执行 `git merge` 合并到当前分支

**⚠️ 注意事项**：
- 如果有未提交的更改，pull 可能失败
- 建议先提交或暂存更改
- 或使用 `git stash` 暂存更改

**处理冲突**：
- 如果 pull 时遇到冲突，处理方式与 merge 相同
- 解决冲突后完成合并

##### git push 详解

**git push** 将本地提交推送到远程仓库。

**基本用法**：

```bash
# 推送到远程
git push origin main

# 设置上游分支并推送
git push -u origin main
# 之后可以直接使用 git push
```

**常用选项**：

```bash
# 推送所有分支
git push --all origin

# 推送所有标签
git push --tags origin

# 强制推送（危险！）
git push --force origin main

# 更安全的强制推送
git push --force-with-lease origin main
```

**⚠️ 强制推送警告**：
- `--force`：会覆盖远程分支，可能丢失其他人的提交
- `--force-with-lease`：更安全，会检查远程是否有其他人的提交
- 只在确定的情况下使用

**推送新分支**：

```bash
# 推送新分支到远程
git push -u origin new-branch

# -u 设置上游分支，之后可以直接 git push
```

**删除远程分支**：

```bash
# 方法 1
git push origin --delete branch-name

# 方法 2
git push origin :branch-name
```

#### 4.3 远程分支
- 远程分支的概念
- 跟踪远程分支
- 推送和拉取远程分支

**实践**：
```bash
# 查看远程分支
git branch -r

# 创建本地分支跟踪远程分支
git checkout -b local-branch origin/remote-branch
git checkout --track origin/remote-branch

# 推送新分支到远程
git push -u origin new-branch

# 删除远程分支
git push origin --delete branch-name
```

---

### 第五章：撤销和恢复

#### 5.1 撤销工作区更改

##### 什么时候需要撤销工作区更改？

- 修改了文件但发现改错了
- 想回到最后一次提交的状态
- 测试性修改后想丢弃

##### git restore 详解（推荐）

**git restore** 是 Git 2.23+ 引入的新命令，专门用于恢复文件，更清晰明确。

**恢复工作区文件**：

```bash
# 恢复单个文件
git restore file.txt

# 恢复多个文件
git restore file1.txt file2.txt

# 恢复所有文件
git restore .

# 恢复特定目录
git restore src/
```

**作用**：
- 将文件恢复到最后一次提交的状态
- 丢弃工作区的所有更改
- ⚠️ 不可恢复，请谨慎使用

**从指定提交恢复**：

```bash
# 从最后一次提交恢复
git restore --source=HEAD file.txt

# 从指定提交恢复
git restore --source=abc1234 file.txt

# 从另一个分支恢复
git restore --source=main file.txt
```

##### git checkout -- <file>（旧方式）

```bash
# 旧方式（仍然可用，但不推荐）
git checkout -- file.txt
git checkout HEAD -- file.txt
```

**为什么不推荐？**
- `git checkout` 功能太多，容易混淆
- 可能误操作切换到其他分支
- `git restore` 更明确、更安全

##### 安全撤销

**查看将要丢弃的更改**：

```bash
# 先查看差异
git diff file.txt

# 确认后再恢复
git restore file.txt
```

**部分恢复**：

```bash
# 交互式选择要恢复的部分
git restore -p file.txt
```

#### 5.2 撤销暂存区更改
- `git restore --staged`：取消暂存
- `git reset HEAD <file>`：取消暂存（旧方式）

**实践**：
```bash
# 取消暂存
git restore --staged file.txt
git reset HEAD file.txt      # 旧方式
```

#### 5.3 修改提交
- `git commit --amend`：修改最后一次提交
- 修改提交信息
- 添加遗漏的文件

**实践**：
```bash
# 修改最后一次提交信息
git commit --amend -m "New message"

# 添加遗漏的文件
git add forgotten-file.txt
git commit --amend --no-edit
```

#### 5.4 恢复提交
- `git reset`：重置到指定提交
- `git revert`：创建新提交撤销更改
- 软重置 vs 硬重置

**实践**：
```bash
# 软重置（保留更改）
git reset --soft HEAD~1

# 混合重置（保留工作区更改）
git reset HEAD~1
git reset --mixed HEAD~1

# 硬重置（丢弃所有更改）
git reset --hard HEAD~1

# 撤销提交（创建新提交）
git revert HEAD
```

---

### 第六章：标签管理

#### 6.1 标签的概念

##### 什么是标签？

**标签（Tag）** 是 Git 中用于标记特定提交的引用，通常用于标记发布版本、重要里程碑等。

**标签的特点**：
- 指向特定的提交（commit）
- 创建后通常不会移动（除非手动更新）
- 用于标记重要的时间点
- 便于查找和引用特定版本

##### 标签的作用

**1. 版本发布标记**
- 标记软件发布版本（如 v1.0.0、v2.1.3）
- 便于用户和开发者找到特定版本
- 支持语义化版本控制

**2. 重要里程碑标记**
- 标记项目的重要节点
- 标记功能完成、测试通过等关键事件
- 便于项目管理和回顾

**3. 快速访问特定版本**
- 通过标签名快速切换到特定版本
- 比记住提交哈希更方便
- 便于部署和回滚

**4. 发布管理**
- 与 CI/CD 集成，自动构建和部署
- 生成发布说明和变更日志
- 管理多个版本并行维护

##### 标签 vs 分支

**关键区别**：

| 特性 | 标签（Tag） | 分支（Branch） |
|------|------------|---------------|
| **移动性** | 固定，不移动 | 会随着提交移动 |
| **用途** | 标记特定点 | 开发线 |
| **更新** | 通常不更新 | 频繁更新 |
| **删除** | 可以删除 | 可以删除 |
| **推送** | 需要显式推送 | 推送时自动推送 |

**示例**：
```bash
# 标签：标记 v1.0.0 发布
git tag v1.0.0

# 分支：继续开发
git checkout -b develop
# 分支会随着新提交移动，标签不会
```

**何时使用标签？**
- ✅ 标记发布版本
- ✅ 标记重要里程碑
- ✅ 需要固定引用某个提交
- ✅ 与 CI/CD 集成

**何时使用分支？**
- ✅ 开发新功能
- ✅ 修复 bug
- ✅ 需要持续更新
- ✅ 并行开发

#### 6.2 标签的类型

Git 支持两种类型的标签：

##### 1. 轻量标签（Lightweight Tag）

**特点**：
- 只是一个指向提交的引用
- 不包含额外信息
- 类似于一个不会移动的分支

**创建方式**：
```bash
git tag v1.0.0
```

**查看轻量标签**：
```bash
git show v1.0.0
# 只显示提交信息，没有标签信息
```

**适用场景**：
- 临时标记
- 个人使用的标记
- 不需要详细信息的简单标记

##### 2. 附注标签（Annotated Tag）

**特点**：
- 是 Git 数据库中的完整对象
- 包含标签创建者、创建时间、标签信息
- 可以签名验证
- 推荐用于正式发布

**创建方式**：
```bash
# 使用 -a 创建附注标签
git tag -a v1.0.0 -m "Release version 1.0.0"

# 不使用 -m 会打开编辑器输入标签信息
git tag -a v1.0.0
```

**查看附注标签**：
```bash
git show v1.0.0
# 输出：
# tag v1.0.0
# Tagger: Name <email>
# Date: Mon Jan 15 10:30:00 2024 +0800
# 
# Release version 1.0.0
# 
# commit abc1234...
# Author: ...
# Date: ...
# 
# Commit message
```

**适用场景**：
- ✅ 正式发布版本（强烈推荐）
- ✅ 需要记录标签信息的场景
- ✅ 需要签名验证的场景
- ✅ 团队协作项目

##### 如何选择？

**推荐使用附注标签**，因为：
- 包含更多信息（创建者、时间、说明）
- 可以签名验证
- 更符合最佳实践
- 便于团队协作

**轻量标签适用于**：
- 临时标记
- 个人项目
- 不需要详细信息的场景

#### 6.3 创建标签

##### 为当前提交创建标签

**创建轻量标签**：
```bash
# 为当前提交创建标签
git tag v1.0.0

# 创建多个标签
git tag v1.0.0 v1.0.1 v1.0.2
```

**创建附注标签**：
```bash
# 使用 -m 添加标签信息
git tag -a v1.0.0 -m "Release version 1.0.0"

# 使用编辑器输入标签信息
git tag -a v1.0.0
# 会打开编辑器，可以输入多行信息
```

**标签信息示例**：
```
Release version 1.0.0

This release includes:
- New user authentication system
- Performance improvements
- Bug fixes

See CHANGELOG.md for details.
```

##### 为历史提交创建标签

**为特定提交创建标签**：
```bash
# 为指定提交创建标签
git tag -a v1.0.0 abc1234 -m "Release version 1.0.0"

# 使用提交哈希的简短形式
git tag -a v1.0.0 abc12 -m "Release version 1.0.0"

# 使用相对引用
git tag -a v1.0.0 HEAD~5 -m "Release version 1.0.0"
```

**查看提交历史选择提交**：
```bash
# 查看提交历史
git log --oneline

# 输出示例：
# abc1234 Add new feature
# def5678 Fix bug
# ghi9012 Initial commit

# 为特定提交创建标签
git tag -a v1.0.0 def5678 -m "Release version 1.0.0"
```

##### 标签命名规范

**推荐命名方式**：

1. **语义化版本（Semantic Versioning）**
   ```
   v<major>.<minor>.<patch>
   ```
   - `v1.0.0`：主版本号.次版本号.修订号
   - `v2.1.3`：主版本 2，次版本 1，修订 3
   - `v1.0.0-beta.1`：预发布版本

2. **日期版本**
   ```
   v2024.01.15
   v20240115
   ```

3. **功能版本**
   ```
   feature-auth-v1
   release-2024-Q1
   ```

**命名最佳实践**：
- ✅ 使用有意义的名称
- ✅ 遵循团队规范
- ✅ 使用统一的前缀（如 `v`）
- ✅ 避免使用空格和特殊字符
- ❌ 不要使用已存在的标签名

#### 6.4 查看标签

##### 列出所有标签

**基本命令**：
```bash
# 列出所有标签（按字母顺序）
git tag

# 输出示例：
# v1.0.0
# v1.0.1
# v1.1.0
# v2.0.0
```

**使用模式过滤**：
```bash
# 列出匹配模式的标签
git tag -l "v1.*"
# 输出：v1.0.0, v1.0.1, v1.1.0

git tag -l "v1.0.*"
# 输出：v1.0.0, v1.0.1

# 列出所有 v2 开头的标签
git tag -l "v2*"
```

**排序标签**：
```bash
# 按版本号排序（需要安装额外工具）
git tag -l | sort -V

# 按时间排序（最近创建的在前）
git tag --sort=-creatordate

# 按版本号排序（语义化版本）
git tag --sort=version:refname
```

##### 查看标签详细信息

**查看标签信息**：
```bash
# 查看标签的详细信息
git show v1.0.0

# 对于附注标签，显示：
# - 标签创建者
# - 创建时间
# - 标签信息
# - 指向的提交信息

# 对于轻量标签，只显示提交信息
```

**查看标签指向的提交**：
```bash
# 查看标签指向的提交
git log v1.0.0

# 查看标签与当前分支的差异
git log HEAD..v1.0.0

# 查看标签之间的差异
git log v1.0.0..v2.0.0
```

**查看标签列表（带提交信息）**：
```bash
# 显示标签及其指向的提交
git tag -l -n1

# 输出示例：
# v1.0.0          Release version 1.0.0
# v1.0.1          Fix critical bug
# v1.1.0          Add new features

# 显示更多行（标签信息）
git tag -l -n5
```

##### 检查标签是否存在

```bash
# 检查标签是否存在
git tag -l v1.0.0
# 如果存在，输出标签名；如果不存在，无输出

# 使用条件判断
if git rev-parse v1.0.0 >/dev/null 2>&1; then
    echo "Tag exists"
else
    echo "Tag does not exist"
fi
```

#### 6.5 推送标签

##### 推送单个标签

**基本命令**：
```bash
# 推送指定标签到远程
git push origin v1.0.0

# 推送时指定远程名称
git push upstream v1.0.0
```

**推送所有标签**：
```bash
# 推送所有标签
git push origin --tags

# 或使用
git push --tags origin
```

**⚠️ 注意事项**：
- 标签不会随 `git push` 自动推送
- 需要显式使用 `--tags` 或指定标签名
- 推送标签后，团队成员可以通过 `git fetch --tags` 获取

##### 推送特定标签

```bash
# 推送匹配模式的标签
git push origin 'refs/tags/v1.*'

# 推送多个指定标签
git push origin v1.0.0 v1.0.1 v1.1.0
```

##### 获取远程标签

**获取所有远程标签**：
```bash
# 获取所有远程标签
git fetch --tags

# 或
git fetch origin --tags
```

**获取特定远程标签**：
```bash
# 获取指定标签
git fetch origin tag v1.0.0

# 获取匹配模式的标签
git fetch origin 'refs/tags/v1.*:refs/tags/v1.*'
```

**查看远程标签**：
```bash
# 列出远程标签
git ls-remote --tags origin

# 输出示例：
# abc1234...    refs/tags/v1.0.0
# def5678...    refs/tags/v1.0.1
```

#### 6.6 删除标签

##### 删除本地标签

**基本命令**：
```bash
# 删除本地标签
git tag -d v1.0.0

# 或使用完整命令
git tag --delete v1.0.0
```

**删除多个标签**：
```bash
# 删除多个标签
git tag -d v1.0.0 v1.0.1 v1.0.2

# 删除匹配模式的标签（需要配合其他工具）
git tag -l "v1.0.*" | xargs git tag -d
```

##### 删除远程标签

**方法 1：使用 push 删除**
```bash
# 删除远程标签（推荐）
git push origin --delete v1.0.0

# 或使用简写
git push origin :refs/tags/v1.0.0
```

**方法 2：推送空引用**
```bash
# 推送空引用到标签（删除标签）
git push origin :v1.0.0
```

**删除多个远程标签**：
```bash
# 删除多个远程标签
git push origin --delete v1.0.0 v1.0.1

# 或使用脚本
git tag -l "v1.0.*" | xargs -I {} git push origin --delete {}
```

##### 完整删除流程

```bash
# 1. 删除本地标签
git tag -d v1.0.0

# 2. 删除远程标签
git push origin --delete v1.0.0

# 3. 验证删除
git tag -l v1.0.0
# 应该无输出
```

#### 6.7 使用标签

##### 切换到标签

**检出标签**：
```bash
# 切换到标签（会进入"detached HEAD"状态）
git checkout v1.0.0

# 输出警告：
# Note: checking out 'v1.0.0'.
# You are in 'detached HEAD' state...
```

**⚠️ 重要提示**：
- 检出标签会进入"分离 HEAD"状态
- 在此状态下的提交不会属于任何分支
- 如果需要基于标签开发，应该创建新分支

**基于标签创建分支**：
```bash
# 基于标签创建新分支（推荐）
git checkout -b release-v1.0.0 v1.0.0

# 或先检出标签，再创建分支
git checkout v1.0.0
git checkout -b hotfix-branch
```

##### 比较标签

**比较两个标签**：
```bash
# 查看两个标签之间的差异
git diff v1.0.0 v2.0.0

# 查看两个标签之间的提交
git log v1.0.0..v2.0.0

# 查看统计信息
git diff --stat v1.0.0 v2.0.0
```

**比较标签与当前分支**：
```bash
# 查看当前分支与标签的差异
git diff v1.0.0

# 查看标签之后的新提交
git log v1.0.0..HEAD
```

##### 在 CI/CD 中使用标签

**触发构建**：
```yaml
# GitHub Actions 示例
on:
  push:
    tags:
      - 'v*'  # 匹配所有 v 开头的标签
```

**部署特定版本**：
```bash
# 检出标签并部署
git checkout v1.0.0
./deploy.sh
```

#### 6.8 标签最佳实践

##### 1. 使用语义化版本

**语义化版本规范（SemVer）**：
```
<major>.<minor>.<patch>
```

- **主版本号（Major）**：不兼容的 API 修改
- **次版本号（Minor）**：向下兼容的功能性新增
- **修订号（Patch）**：向下兼容的问题修正

**示例**：
```
v1.0.0    # 初始发布
v1.0.1    # 修复 bug
v1.1.0    # 新功能
v2.0.0    # 重大更新（可能不兼容）
```

##### 2. 使用附注标签

- ✅ 总是使用 `-a` 创建附注标签
- ✅ 提供有意义的标签信息
- ✅ 包含发布说明和变更摘要

##### 3. 标签命名规范

- ✅ 使用统一的前缀（如 `v`）
- ✅ 遵循语义化版本规范
- ✅ 使用有意义的名称
- ❌ 避免使用空格和特殊字符

##### 4. 及时推送标签

- ✅ 创建标签后及时推送到远程
- ✅ 与团队共享重要标记
- ✅ 便于 CI/CD 集成

##### 5. 不要移动标签

- ❌ 不要更新已推送的标签
- ❌ 不要强制推送标签（除非必要）
- ✅ 如果需要修改，创建新标签

##### 6. 文档化标签策略

- ✅ 在项目文档中说明标签策略
- ✅ 说明版本号的含义
- ✅ 提供标签使用指南

**实践示例**：
```bash
# 1. 创建附注标签
git tag -a v1.0.0 -m "Release version 1.0.0

This release includes:
- User authentication system
- Dashboard UI improvements
- Performance optimizations

See CHANGELOG.md for details."

# 2. 推送标签
git push origin v1.0.0

# 3. 验证
git show v1.0.0
```

---

### 第七章：常用技巧

#### 7.1 忽略文件
- `.gitignore` 文件
- 忽略规则语法
- 常见忽略模式

**实践**：
```bash
# 创建 .gitignore
touch .gitignore

# 常见规则
*.log
node_modules/
.DS_Store
*.class
build/
```

#### 7.2 别名配置
- 配置 Git 别名
- 常用别名示例
- 提高工作效率

**实践**：
```bash
# 配置别名
git config --global alias.st status
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.ci commit
git config --global alias.ll "log --oneline"
```

#### 7.3 Stash 暂存
- `git stash`：暂存更改
- `git stash list`：查看暂存列表
- `git stash pop`：应用暂存
- `git stash apply`：应用但不删除

**实践**：
```bash
# 暂存当前更改
git stash
git stash save "WIP: working on feature"

# 查看暂存列表
git stash list

# 应用暂存
git stash pop                # 应用并删除
git stash apply              # 应用但不删除
git stash apply stash@{0}    # 应用指定暂存

# 删除暂存
git stash drop stash@{0}
git stash clear              # 清空所有暂存
```

---

## 🎯 实践项目

### 项目 1：个人项目管理

1. 创建本地仓库
2. 添加文件并提交
3. 创建功能分支
4. 合并分支
5. 推送到远程仓库

### 项目 2：协作开发模拟

1. 克隆远程仓库
2. 创建自己的分支
3. 提交更改
4. 处理合并冲突
5. 推送到远程

---

## ✅ 学习检查点

完成基础学习后，您应该能够：

- [ ] 理解 Git 的基本概念（工作区、暂存区、仓库）
- [ ] 能够创建和克隆仓库
- [ ] 能够添加、提交、查看更改
- [ ] 能够创建和管理分支
- [ ] 能够解决简单的合并冲突
- [ ] 能够操作远程仓库（推送、拉取）
- [ ] 能够撤销和恢复更改
- [ ] 能够使用标签管理版本
- [ ] 能够配置和使用别名
- [ ] 能够使用 stash 暂存更改

---

## 📖 推荐资源

- [Pro Git 中文版 - 第 1-3 章](https://git-scm.com/book/zh/v2)
- [Git 官方教程](https://git-scm.com/docs/gittutorial)
- [GitHub 学习资源](https://github.com/git/git)

---

**下一步**：完成基础学习后，进入 `02_Advanced` 学习 Git 进阶内容。
