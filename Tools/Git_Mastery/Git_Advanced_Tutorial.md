# Git 进阶

## 📋 学习目标

深入理解 Git 内部机制，掌握高级功能，能够解决复杂问题，优化工作流程。

## 📚 学习内容

### 第一章：Git 内部机制

#### 1.1 Git 对象模型

##### Git 的三种对象类型

Git 的核心是一个简单的键值对数据库。所有内容都存储为对象，每个对象都有一个唯一的 SHA-1 哈希值。

**1. Blob 对象（Binary Large Object）**

- **作用**：存储文件内容
- **特点**：
  - 只存储文件内容，不存储文件名
  - 相同内容的文件共享同一个 blob
  - 这是 Git 高效存储的基础

**2. Tree 对象**

- **作用**：存储目录结构
- **内容**：
  - 指向 blob 对象（文件）
  - 指向其他 tree 对象（子目录）
  - 包含文件名、权限、对象哈希

**3. Commit 对象**

- **作用**：存储提交信息
- **内容**：
  - 指向一个 tree 对象（项目快照）
  - 指向父提交（parent commit）
  - 包含作者、提交者、时间戳、提交信息

**对象关系图**：
```
Commit
  ├── Tree (项目根目录)
  │   ├── Tree (子目录)
  │   │   └── Blob (文件内容)
  │   └── Blob (文件内容)
  └── Parent Commit
```

##### 命令详解

**git cat-file**

查看 Git 对象的详细信息。

```bash
git cat-file -t <hash>      # 查看对象类型
git cat-file -p <hash>      # 查看对象内容（pretty-print）
git cat-file -s <hash>      # 查看对象大小（size）
```

**参数说明**：
- `-t`：显示对象类型（blob、tree、commit、tag）
- `-p`：以可读格式显示对象内容
- `-s`：显示对象大小（字节）

**示例**：
```bash
# 1. 查看 HEAD 提交的类型
git cat-file -t HEAD
# 输出：commit

# 2. 查看提交的完整内容
git cat-file -p HEAD
# 输出：
# tree abc1234...
# parent def5678...
# author Name <email> timestamp
# committer Name <email> timestamp
# 
# Commit message

# 3. 查看提交指向的树对象
git cat-file -p HEAD | grep tree
# 输出：tree abc1234...

# 4. 查看树对象的内容
git cat-file -p abc1234
# 输出：
# 100644 blob ghi9012... file1.txt
# 040000 tree jkl3456... subdir
```

**git ls-tree**

列出树对象的内容（类似 `ls` 命令）。

```bash
git ls-tree HEAD                    # 列出 HEAD 指向的树
git ls-tree <tree-hash>             # 列出指定树对象
git ls-tree -r HEAD                 # 递归列出所有文件
git ls-tree --name-only HEAD        # 只显示文件名
git ls-tree -l HEAD                 # 显示文件大小
```

**参数说明**：
- `-r`：递归显示所有子目录
- `--name-only`：只显示文件名
- `-l`：显示文件大小
- `-t`：显示树对象（目录）

**示例**：
```bash
# 查看项目根目录结构
git ls-tree HEAD
# 输出：
# 100644 blob abc123... README.md
# 040000 tree def456... src
# 100644 blob ghi789... .gitignore

# 递归查看所有文件
git ls-tree -r HEAD --name-only
# 输出所有文件的路径

# 查看特定目录
git ls-tree HEAD:src/
```

##### SHA-1 哈希值

**什么是 SHA-1？**

SHA-1（Secure Hash Algorithm 1）是一种加密哈希函数，Git 使用它来生成对象的唯一标识符。

**特点**：
- 相同内容总是产生相同的哈希
- 不同内容几乎不可能产生相同哈希（碰撞概率极低）
- 哈希值固定长度（40 个十六进制字符）

**示例**：
```bash
# 查看文件的哈希值
git hash-object file.txt
# 输出：abc123def456...

# 相同内容的文件有相同的哈希
echo "Hello" > file1.txt
echo "Hello" > file2.txt
git hash-object file1.txt
git hash-object file2.txt
# 两个文件的哈希值相同
```

**Git 使用简短哈希**：
```bash
# 完整哈希：abc123def456789...
# 简短哈希：abc123（通常前 7 位就足够唯一）

# Git 会自动识别简短哈希
git show abc123
git show abc123def456789
# 两者指向同一个提交（如果唯一）
```

##### 对象存储机制

**存储位置**：

所有对象都存储在 `.git/objects/` 目录中：

```
.git/objects/
├── ab/
│   └── c123...        # 对象文件（前两位作为目录名）
├── de/
│   └── f456...
└── ...
```

**存储格式**：

对象以压缩格式存储，使用 zlib 压缩。

**查看对象存储**：
```bash
# 查看对象目录结构
ls .git/objects/

# 查看特定对象
git cat-file -p <hash>

# 查看对象原始内容（压缩的）
cat .git/objects/ab/c123...
# 输出：压缩的二进制数据
```

**对象共享**：

Git 通过对象共享实现高效存储：

```bash
# 两个文件内容相同，共享同一个 blob
echo "Hello" > file1.txt
echo "Hello" > file2.txt
git add file1.txt file2.txt

# 查看它们的哈希
git ls-files --stage
# 两个文件指向同一个 blob 对象
```

#### 1.2 引用系统
- HEAD 引用
- 分支引用
- 标签引用
- 远程引用

**实践**：
```bash
# 查看引用
cat .git/HEAD
cat .git/refs/heads/main
cat .git/refs/remotes/origin/main

# 查看所有引用
git show-ref
```

#### 1.3 索引（暂存区）
- 索引的作用
- 索引文件结构
- 查看索引内容

**实践**：
```bash
# 查看索引
git ls-files --stage

# 查看索引统计
git diff --cached --stat
```

---

### 第二章：高级分支操作

#### 2.1 Rebase 变基

##### Rebase 的概念

**什么是 Rebase？**

Rebase（变基）是将一系列提交"重新播放"到另一个基础提交上的操作。它通过创建新的提交来重写提交历史，使历史更加线性和清晰。

**工作原理**：

1. 找到当前分支和目标分支的共同祖先
2. 将当前分支的提交"撤销"（临时保存）
3. 将当前分支指向目标分支的最新提交
4. 将保存的提交"重新应用"到新基础上

**图解**：

```
Rebase 前：
main:    A---B---C
              \
feature:       D---E---F

Rebase 后：
main:    A---B---C
                  \
feature:           D'---E'---F'
```

##### Rebase vs Merge

**Merge（合并）**：
- ✅ 保留完整的历史记录
- ✅ 不会改变现有提交
- ✅ 更安全，不会丢失信息
- ❌ 产生合并提交，历史图更复杂
- ❌ 历史记录可能难以阅读

**Rebase（变基）**：
- ✅ 创建线性的历史记录
- ✅ 历史更清晰，易于阅读
- ✅ 没有多余的合并提交
- ❌ 重写提交历史（改变提交哈希）
- ❌ 如果已推送，需要强制推送
- ❌ 可能丢失合并的上下文信息

**何时使用 Merge？**
- 公共分支（main、develop）
- 需要保留合并上下文
- 团队协作，避免强制推送

**何时使用 Rebase？**
- 个人功能分支
- 合并到主分支前整理历史
- 希望保持线性历史

##### 基本 Rebase 操作

**命令格式**：
```bash
git rebase <目标分支>
```

**完整流程**：

```bash
# 1. 切换到要变基的分支
git checkout feature

# 2. 执行 rebase
git rebase main

# 3. 如果遇到冲突：
#    - Git 会暂停，显示冲突文件
#    - 手动解决冲突
#    - 标记为已解决
git add <resolved-files>

# 4. 继续 rebase
git rebase --continue

# 5. 如果想中止 rebase
git rebase --abort

# 6. 如果想跳过当前提交
git rebase --skip
```

**参数说明**：
- `<目标分支>`：要变基到的目标分支
- `--continue`：解决冲突后继续 rebase
- `--abort`：中止 rebase，回到 rebase 前的状态
- `--skip`：跳过当前提交（通常用于冲突无法解决的情况）

##### 交互式 Rebase

交互式 Rebase（`git rebase -i`）允许在 rebase 过程中修改提交。

**命令格式**：
```bash
git rebase -i <起始提交>
```

**常用起始点**：
- `HEAD~3`：最近 3 个提交
- `<commit-hash>`：特定提交
- `<branch-name>`：另一个分支

**操作选项**（在编辑器中）：
- `pick`（p）：使用提交，不做修改
- `reword`（r）：修改提交信息
- `edit`（e）：修改提交内容
- `squash`（s）：合并到上一个提交
- `fixup`（f）：类似 squash，但丢弃提交信息
- `drop`（d）：删除提交
- `exec`（x）：执行 shell 命令

**示例：整理提交历史**

```bash
# 1. 启动交互式 rebase
git rebase -i HEAD~5

# 2. 编辑器打开，显示：
pick abc1234 Add login feature
pick def5678 Fix typo
pick ghi9012 Add tests
pick jkl3456 Refactor code
pick mno7890 Update docs

# 3. 修改为：
pick abc1234 Add login feature
squash def5678 Fix typo          # 合并到上一个
squash ghi9012 Add tests         # 合并到上一个
pick jkl3456 Refactor code
fixup mno7890 Update docs         # 合并但不保留信息

# 4. 保存后，Git 会：
#    - 合并前三个提交，要求编辑合并后的信息
#    - 将文档更新合并到重构提交中

# 5. 最终结果：5 个提交变成 2 个提交
```

##### Rebase 的风险和注意事项

**⚠️ 重要警告**：

1. **不要对公共分支使用 Rebase**
   ```bash
   # ❌ 错误：不要这样做
   git checkout main
   git rebase feature
   ```
   - 会重写公共历史
   - 影响所有协作者
   - 需要所有人重新同步

2. **已推送的分支要谨慎**
   - Rebase 会改变提交哈希
   - 需要强制推送：`git push --force`
   - 更安全的方式：`git push --force-with-lease`

3. **处理冲突**
   - Rebase 过程中可能多次遇到冲突
   - 每次冲突都需要解决
   - 使用 `git rebase --continue` 继续

4. **备份重要分支**
   ```bash
   # 在 rebase 前创建备份
   git branch feature-backup feature
   git rebase main
   ```

**最佳实践**：

```bash
# ✅ 推荐：在合并前 rebase 功能分支
git checkout feature
git rebase main              # 整理历史
git checkout main
git merge feature            # 快进合并

# ✅ 推荐：使用 --force-with-lease 而不是 --force
git push --force-with-lease origin feature

# ✅ 推荐：定期从主分支 rebase
git checkout feature
git fetch origin
git rebase origin/main       # 保持与主分支同步
```

#### 2.2 Cherry-pick

##### Cherry-pick 的概念

**什么是 Cherry-pick？**

Cherry-pick 是"挑选"特定提交并应用到当前分支的操作。它允许你选择性地应用其他分支的提交，而不需要合并整个分支。

**使用场景**：

1. **修复 Bug**
   - 在 main 分支修复了 bug
   - 需要将修复应用到 release 分支
   - 不需要合并整个 main 分支

2. **功能回退**
   - 某个功能在 feature 分支开发
   - 需要先应用到 hotfix 分支
   - 稍后再合并整个 feature 分支

3. **选择性合并**
   - 只需要某个分支的部分提交
   - 不想引入其他不相关的更改

##### 基本 Cherry-pick 操作

**命令格式**：
```bash
git cherry-pick <commit-hash>
```

**完整流程**：

```bash
# 1. 切换到目标分支
git checkout target-branch

# 2. 应用提交
git cherry-pick abc1234

# 3. 如果遇到冲突：
#    - Git 会暂停，显示冲突
#    - 手动解决冲突
#    - 标记为已解决
git add <resolved-files>

# 4. 继续 cherry-pick
git cherry-pick --continue

# 5. 如果想中止
git cherry-pick --abort

# 6. 如果想跳过当前提交
git cherry-pick --skip
```

**参数说明**：

- `<commit-hash>`：要应用的提交哈希（完整或简短）
- `--continue`：解决冲突后继续
- `--abort`：中止 cherry-pick，回到操作前状态
- `--skip`：跳过当前提交
- `-n` 或 `--no-commit`：只应用更改，不自动提交
- `-e` 或 `--edit`：应用前编辑提交信息
- `-x`：在提交信息中添加来源信息

##### 应用多个提交

**方式 1：指定多个提交**
```bash
git cherry-pick abc1234 def5678 ghi9012
```
- 按顺序应用提交
- 每个提交都会创建新的提交

**方式 2：应用提交范围**
```bash
git cherry-pick <start-hash>..<end-hash>
```
- 应用从 start（不包含）到 end（包含）的所有提交
- 注意：`..` 不包含起始提交

```bash
git cherry-pick <start-hash>^..<end-hash>
```
- 使用 `^` 包含起始提交

**示例**：
```bash
# 应用提交 A 到 D（不包含 A）
git cherry-pick A..D
# 结果：应用 B, C, D

# 应用提交 A 到 D（包含 A）
git cherry-pick A^..D
# 结果：应用 A, B, C, D
```

##### 只应用更改不提交

**使用场景**：
- 需要修改后再提交
- 想将多个提交合并为一个
- 需要调整提交内容

**操作**：
```bash
# 1. 应用提交但不提交
git cherry-pick -n abc1234

# 2. 查看更改
git status
git diff --cached

# 3. 修改更改（可选）
# 编辑文件...

# 4. 手动提交
git commit -m "Apply fix from feature branch"
```

##### 处理冲突

Cherry-pick 可能遇到冲突，处理方式与 merge 类似：

```bash
# 1. 查看冲突文件
git status

# 2. 解决冲突
# 编辑冲突文件，移除冲突标记

# 3. 标记为已解决
git add <resolved-files>

# 4. 继续
git cherry-pick --continue
```

**冲突标记**：
```
<<<<<<< HEAD
当前分支的内容
=======
要应用的提交内容
>>>>>>> abc1234... Commit message
```

##### 实际应用示例

**场景 1：将 Bug 修复应用到多个分支**

```bash
# 在 main 分支修复了 bug（提交 abc1234）
git checkout main
git commit -m "Fix critical bug"

# 应用到 release 分支
git checkout release
git cherry-pick abc1234

# 应用到 hotfix 分支
git checkout hotfix
git cherry-pick abc1234
```

**场景 2：选择性应用功能**

```bash
# feature 分支有多个提交，只需要部分
git log feature --oneline
# abc1234 Add feature A
# def5678 Add feature B
# ghi9012 Fix typo

# 只应用 feature A
git checkout main
git cherry-pick abc1234
```

**场景 3：整理提交**

```bash
# 应用多个提交但合并为一个
git cherry-pick -n abc1234 def5678 ghi9012
git commit -m "Add complete feature with fixes"
```

##### 注意事项

1. **提交哈希会改变**
   - Cherry-pick 会创建新的提交
   - 新提交有不同的哈希值
   - 但内容相同（如果没有冲突）

2. **可能重复应用**
   - 如果提交已经存在，cherry-pick 可能失败
   - 使用 `--allow-empty` 允许空提交

3. **保持提交信息**
   - 默认保留原始提交信息
   - 使用 `-e` 可以编辑
   - 使用 `-x` 添加来源信息

4. **与 Rebase 的区别**
   - Rebase：重写历史，保持提交顺序
   - Cherry-pick：选择性应用，不改变原分支

#### 2.3 分支策略
- 长期分支 vs 短期分支
- 功能分支工作流
- 发布分支管理
- 热修复分支

---

### 第三章：历史重写

#### 3.1 修改历史

##### 为什么需要修改历史？

在实际开发中，我们经常需要修改提交历史，主要原因包括：

1. **提交信息不规范**
   - 提交信息拼写错误
   - 提交信息不够清晰，需要补充说明
   - 提交信息格式不符合团队规范

2. **提交粒度不合理**
   - 提交过于零散，需要合并相关提交
   - 提交包含不相关的更改，需要拆分

3. **包含敏感信息**
   - 提交中意外包含了密码、密钥等敏感信息
   - 需要从历史中完全删除

4. **代码质量问题**
   - 提交中包含了调试代码、注释掉的代码
   - 需要清理不必要的文件

5. **整理提交历史**
   - 在合并到主分支前，整理提交历史使其更清晰
   - 便于代码审查和问题追踪

##### 修改历史的风险

**⚠️ 重要警告**：修改已推送到远程仓库的提交历史是**危险**的操作！

**风险包括**：

1. **破坏团队协作**
   - 如果其他人已经基于这些提交工作，修改历史会导致他们的本地仓库与远程不一致
   - 强制推送（`git push --force`）会覆盖远程历史，可能导致其他人的工作丢失

2. **丢失提交**
   - 如果操作不当，可能会意外删除重要的提交
   - 虽然可以通过 reflog 恢复，但会增加恢复成本

3. **破坏 CI/CD**
   - 如果 CI/CD 系统基于提交哈希进行构建，修改历史会导致构建失败
   - 需要重新触发构建流程

4. **审计问题**
   - 修改历史会改变提交的哈希值，影响代码审计
   - 某些合规要求不允许修改历史

**最佳实践**：
- ✅ **只修改未推送的提交**：如果提交还没有推送到远程，可以安全地修改
- ✅ **团队沟通**：如果必须修改已推送的历史，务必与团队沟通
- ✅ **备份重要分支**：修改前创建备份分支
- ✅ **使用 `--force-with-lease`**：比 `--force` 更安全，会检查远程是否有其他人的提交

##### 交互式 Rebase 修改历史

交互式 Rebase（`git rebase -i`）是修改提交历史最常用的方法。

**命令详解**：

```bash
git rebase -i HEAD~3
```

**参数说明**：
- `-i` 或 `--interactive`：启用交互模式
- `HEAD~3`：指定要修改的提交范围，表示最近 3 个提交
- 也可以使用提交哈希：`git rebase -i <commit-hash>`

**操作步骤**：

1. **启动交互式 Rebase**
   ```bash
   git rebase -i HEAD~3
   ```

2. **编辑器会打开，显示类似内容**：
   ```
   pick abc1234 First commit message
   pick def5678 Second commit message
   pick ghi9012 Third commit message
   
   # Rebase instructions:
   # p, pick <commit> = use commit
   # r, reword <commit> = use commit, but edit the commit message
   # e, edit <commit> = use commit, but stop for amending
   # s, squash <commit> = use commit, but meld into previous commit
   # f, fixup <commit> = like "squash", but discard this commit's log message
   # d, drop <commit> = remove commit
   # x, exec <command> = run command (the rest of the line) using shell
   ```

3. **修改提交的操作类型**：

   **pick（p）**：使用提交，不做修改
   ```
   pick abc1234 First commit message
   ```

   **reword（r）**：修改提交信息
   ```
   reword abc1234 First commit message
   ```
   - 保存后，Git 会为每个标记为 `reword` 的提交打开编辑器
   - 可以修改提交信息

   **edit（e）**：修改提交内容
   ```
   edit abc1234 First commit message
   ```
   - Git 会在这个提交处暂停
   - 可以修改文件、添加文件、删除文件
   - 使用 `git commit --amend` 完成修改
   - 使用 `git rebase --continue` 继续

   **squash（s）**：合并到上一个提交
   ```
   pick abc1234 First commit message
   squash def5678 Second commit message
   ```
   - 将第二个提交合并到第一个提交
   - 会打开编辑器，可以编辑合并后的提交信息

   **fixup（f）**：类似 squash，但丢弃提交信息
   ```
   pick abc1234 First commit message
   fixup def5678 Second commit message
   ```
   - 合并提交，但使用第一个提交的信息
   - 不会打开编辑器

   **drop（d）**：删除提交
   ```
   drop def5678 Second commit message
   ```
   - 完全删除这个提交及其更改

4. **保存并退出编辑器**

5. **根据操作类型执行后续步骤**：
   - 如果是 `reword`：修改提交信息后保存
   - 如果是 `edit`：修改文件后执行 `git commit --amend`，然后 `git rebase --continue`
   - 如果是 `squash`：编辑合并后的提交信息

6. **完成 Rebase**
   - 如果遇到冲突，解决冲突后执行 `git add` 和 `git rebase --continue`
   - 如果想中止，执行 `git rebase --abort`

**完整示例**：

```bash
# 1. 启动交互式 Rebase
git rebase -i HEAD~3

# 2. 在编辑器中修改（例如：合并后两个提交）
pick abc1234 Add feature A
squash def5678 Fix typo in feature A
squash ghi9012 Add tests for feature A

# 3. 保存后，Git 会打开编辑器编辑合并后的提交信息
# 可以修改为：Add feature A with tests

# 4. 如果一切顺利，Rebase 完成
# 如果遇到冲突：
git add <resolved-files>
git rebase --continue

# 5. 查看结果
git log --oneline
```

**注意事项**：
- 修改提交会改变提交的哈希值
- 如果提交已推送，需要使用 `git push --force-with-lease` 强制推送
- 建议在修改前创建备份分支：`git branch backup-branch`

#### 3.2 清理历史

##### 为什么需要清理历史？

1. **删除敏感信息**
   - 密码、API 密钥、证书等敏感数据被意外提交
   - 即使后续删除文件，历史记录中仍然存在
   - 需要从整个历史中彻底删除

2. **压缩历史**
   - 仓库历史过长，影响克隆和操作速度
   - 包含大量小提交，需要合并
   - 删除无用的分支和标签

3. **规范化提交信息**
   - 统一提交者信息（姓名、邮箱）
   - 修复历史提交中的错误信息

##### 使用 filter-branch 清理历史

`git filter-branch` 是 Git 内置的历史重写工具，可以批量修改整个仓库历史。

**⚠️ 警告**：`filter-branch` 操作会重写整个历史，非常耗时且危险。建议先备份仓库。

**命令格式**：
```bash
git filter-branch [选项] <过滤器> [修订范围]
```

**常用过滤器类型**：

1. **--tree-filter**：在每个提交上执行命令，修改工作树
   ```bash
   # 删除文件历史
   git filter-branch --tree-filter 'rm -f password.txt' HEAD
   ```
   - `'rm -f password.txt'`：在每个提交中删除该文件
   - `HEAD`：从当前提交开始，重写所有历史
   - 这会为每个提交创建新的提交对象，非常慢

2. **--index-filter**：只修改索引，不检出文件（更快）
   ```bash
   # 从索引中删除文件（不检出文件，速度更快）
   git filter-branch --index-filter 'git rm --cached --ignore-unmatch password.txt' HEAD
   ```
   - `--ignore-unmatch`：如果文件不存在也不报错
   - 比 `--tree-filter` 快得多，因为不需要检出文件

3. **--env-filter**：修改提交环境变量（作者信息等）
   ```bash
   # 重写所有提交的邮箱
   git filter-branch --env-filter '
   OLD_EMAIL="old@example.com"
   CORRECT_NAME="Your Name"
   CORRECT_EMAIL="new@example.com"
   if [ "$GIT_COMMITTER_EMAIL" = "$OLD_EMAIL" ]
   then
       export GIT_COMMITTER_NAME="$CORRECT_NAME"
       export GIT_COMMITTER_EMAIL="$CORRECT_EMAIL"
   fi
   if [ "$GIT_AUTHOR_EMAIL" = "$OLD_EMAIL" ]
   then
       export GIT_AUTHOR_NAME="$CORRECT_NAME"
       export GIT_AUTHOR_EMAIL="$CORRECT_EMAIL"
   fi
   ' --tag-name-filter cat -- --branches --tags
   ```
   - `GIT_COMMITTER_*`：提交者信息
   - `GIT_AUTHOR_*`：作者信息
   - `--tag-name-filter cat`：保持标签名称不变
   - `-- --branches --tags`：处理所有分支和标签

4. **--msg-filter**：修改提交信息
   ```bash
   # 在所有提交信息前添加前缀
   git filter-branch --msg-filter 'echo "[OLD] $GIT_COMMIT_MSG"' HEAD
   ```

**完整示例：删除敏感文件**

```bash
# 1. 备份仓库
git clone --mirror . ../backup-repo.git

# 2. 删除文件历史
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch secrets.txt' \
  --prune-empty --tag-name-filter cat -- --all

# 参数说明：
# --force：强制覆盖已有的备份
# --index-filter：只修改索引，不检出文件（更快）
# --prune-empty：删除变为空的提交
# --tag-name-filter cat：保持标签名称
# -- --all：处理所有分支和标签

# 3. 清理备份引用
git for-each-ref --format="delete %(refname)" refs/original | git update-ref --stdin
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# 4. 强制推送到远程（危险！）
git push origin --force --all
git push origin --force --tags
```

##### 使用 git-filter-repo（推荐）

`git-filter-repo` 是 `filter-branch` 的现代替代品，更快、更安全、更易用。

**安装**：
```bash
# Python 3.5+ 需要
pip install git-filter-repo
```

**常用操作**：

1. **删除文件**
   ```bash
   git filter-repo --path password.txt --invert-paths
   ```
   - `--path password.txt`：指定文件路径
   - `--invert-paths`：删除匹配的路径（不加此选项会只保留匹配的路径）

2. **删除目录**
   ```bash
   git filter-repo --path secrets/ --invert-paths
   ```

3. **修改提交者信息**
   ```bash
   git filter-repo --email-callback '
   return email.replace(b"old@example.com", b"new@example.com")
   '
   ```

4. **保留特定路径**
   ```bash
   # 只保留 src/ 目录的历史
   git filter-repo --path src/
   ```

**优势**：
- ✅ 速度更快（比 filter-branch 快 10-50 倍）
- ✅ 自动清理备份引用
- ✅ 更安全的默认行为
- ✅ 更好的错误处理

#### 3.3 恢复丢失的提交

##### 为什么提交会丢失？

1. **误操作**
   - 使用 `git reset --hard` 回退太远
   - 误删分支
   - 强制推送覆盖了提交

2. **清理操作**
   - 使用 `git gc` 清理后，未引用的对象可能被删除
   - 使用 `git prune` 删除了悬空对象

3. **仓库损坏**
   - 磁盘故障
   - 文件系统错误

##### 使用 reflog 恢复

**什么是 reflog？**

Reflog（引用日志）记录 HEAD 和分支引用的所有变更历史，是恢复丢失提交的"救命稻草"。

**重要特性**：
- Reflog 默认保留 90 天
- 只记录本地操作，不会推送到远程
- 每个分支都有独立的 reflog

**命令详解**：

```bash
# 查看 reflog
git reflog
```

**输出示例**：
```
abc1234 HEAD@{0}: commit: Add new feature
def5678 HEAD@{1}: reset: moving to HEAD~2
ghi9012 HEAD@{2}: commit: Fix bug
jkl3456 HEAD@{3}: commit: Initial commit
```

**格式说明**：
- `abc1234`：提交哈希
- `HEAD@{0}`：HEAD 的位置（0 表示最近）
- `commit:`：操作类型
- `Add new feature`：操作描述

**恢复提交的步骤**：

1. **查看 reflog，找到丢失的提交**
   ```bash
   git reflog
   # 找到类似：abc1234 HEAD@{5}: commit: Important work
   ```

2. **创建新分支指向该提交**
   ```bash
   git branch recovered-branch abc1234
   ```

3. **切换到恢复的分支**
   ```bash
   git checkout recovered-branch
   ```

4. **验证内容**
   ```bash
   git log --oneline
   git show HEAD
   ```

5. **如果需要，合并回主分支**
   ```bash
   git checkout main
   git merge recovered-branch
   ```

**恢复已删除的分支**：

```bash
# 1. 查看所有 reflog（包括已删除的分支）
git reflog --all

# 2. 找到分支删除前的最后一次提交
# 例如：abc1234 refs/heads/feature-branch@{0}: commit: Last commit

# 3. 恢复分支
git branch feature-branch abc1234

# 或者直接恢复并切换
git checkout -b feature-branch abc1234
```

**恢复特定时间的提交**：

```bash
# 使用时间表达式
git reflog --date=iso
# 输出：abc1234 HEAD@{2024-01-15 10:30:00}: commit: ...

# 恢复到特定时间
git checkout HEAD@{2024-01-15 10:30:00}
git checkout -b recovered-branch HEAD@{2024-01-15 10:30:00}
```

**使用 fsck 查找悬空对象**：

如果 reflog 中没有记录，可以查找悬空对象（dangling objects）：

```bash
# 查找所有悬空提交
git fsck --lost-found

# 查看悬空提交的详细信息
git show <dangling-commit-hash>

# 如果找到需要的提交，创建分支
git branch recovered-branch <dangling-commit-hash>
```

**预防措施**：

1. **定期备份**
   ```bash
   git clone --mirror . ../backup.git
   ```

2. **使用标签标记重要提交**
   ```bash
   git tag important-milestone HEAD
   ```

3. **推送到远程**
   ```bash
   git push origin feature-branch
   ```

4. **谨慎使用危险命令**
   - `git reset --hard`
   - `git push --force`
   - `git gc --prune=now`

---

### 第四章：高级合并

#### 4.1 合并策略
- Fast-forward 合并
- 三方合并
- 递归合并
- 我们的 vs 他们的策略

**实践**：
```bash
# 指定合并策略
git merge -s recursive -X ours feature
git merge -s recursive -X theirs feature

# 禁止 fast-forward
git merge --no-ff feature

# 只合并，不提交
git merge --no-commit feature
```

#### 4.2 解决复杂冲突
- 理解冲突标记
- 使用合并工具
- 手动解决冲突
- 验证合并结果

**实践**：
```bash
# 配置合并工具
git config --global merge.tool vimdiff

# 使用合并工具
git mergetool

# 查看冲突文件
git diff --name-only --diff-filter=U

# 标记为已解决
git add resolved-file.txt
```

#### 4.3 合并多个分支
- 合并多个功能分支
- 处理依赖关系
- 合并顺序的重要性

---

### 第五章：Git Hooks

#### 5.1 Hooks 概述
- 什么是 Git Hooks
- Hooks 的类型
- Hooks 的执行时机
- Hooks 的位置

#### 5.2 客户端 Hooks
- pre-commit：提交前检查
- commit-msg：验证提交信息
- post-commit：提交后操作
- pre-push：推送前检查

**实践**：
```bash
# 创建 pre-commit hook
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/sh
# 运行测试
npm test
EOF

chmod +x .git/hooks/pre-commit

# 创建 commit-msg hook（验证提交信息格式）
cat > .git/hooks/commit-msg << 'EOF'
#!/bin/sh
commit_msg=$(cat $1)
if ! echo "$commit_msg" | grep -qE "^(feat|fix|docs|style|refactor|test|chore):"; then
    echo "提交信息格式错误！"
    echo "格式: <type>: <description>"
    exit 1
fi
EOF

chmod +x .git/hooks/commit-msg
```

#### 5.3 服务端 Hooks
- pre-receive：接收前检查
- update：更新分支前
- post-receive：接收后操作

#### 5.4 使用 Hooks 框架
- Husky（Node.js）
- pre-commit（Python）
- 自定义 Hooks 脚本

---

### 第六章：子模块和子树

#### 6.1 Git Submodule
- 子模块的概念
- 添加子模块
- 更新子模块
- 删除子模块

**实践**：
```bash
# 添加子模块
git submodule add https://github.com/user/repo.git path/to/submodule

# 初始化子模块
git submodule init
git submodule update

# 更新子模块
git submodule update --remote

# 删除子模块
git submodule deinit path/to/submodule
git rm path/to/submodule
```

#### 6.2 Git Subtree
- 子树的概念
- 子树 vs 子模块
- 添加子树
- 同步子树

**实践**：
```bash
# 添加子树
git subtree add --prefix=lib/external https://github.com/user/repo.git main --squash

# 更新子树
git subtree pull --prefix=lib/external https://github.com/user/repo.git main --squash

# 推送子树更改
git subtree push --prefix=lib/external https://github.com/user/repo.git main
```

---

### 第七章：标签高级用法

#### 7.1 标签验证和签名

##### GPG 签名标签

**为什么需要签名标签？**
- 验证标签的创建者身份
- 防止标签被篡改
- 提高安全性
- 符合安全最佳实践

**配置 GPG 密钥**：
```bash
# 1. 生成 GPG 密钥（如果还没有）
gpg --gen-key

# 2. 列出 GPG 密钥
gpg --list-secret-keys --keyid-format LONG

# 3. 配置 Git 使用 GPG 密钥
git config --global user.signingkey <key-id>

# 示例
git config --global user.signingkey 3AA5C34371567BD2
```

**创建签名标签**：
```bash
# 使用 -s 创建签名标签
git tag -s v1.0.0 -m "Release version 1.0.0"

# 或使用完整命令
git tag --sign v1.0.0 -m "Release version 1.0.0"
```

**验证签名标签**：
```bash
# 验证标签签名
git tag -v v1.0.0

# 输出示例：
# object abc1234...
# type commit
# tag v1.0.0
# tagger Name <email> timestamp
# 
# Release version 1.0.0
# gpg: Signature made ...
# gpg: Good signature from "Name <email>"

# 如果签名无效，会显示错误
```

**查看所有标签的签名状态**：
```bash
# 查看标签及其签名状态
git tag -l --format='%(refname:short) %(signer) %(signature:status)'

# 输出示例：
# v1.0.0 Name <email> G
# v1.0.1 Name <email> G
# v1.0.2 (no signature)
```

**签名状态说明**：
- `G`：有效签名（Good）
- `B`：无效签名（Bad）
- `U`：未知签名者（Unknown）
- `X`：已过期（Expired）
- `Y`：已撤销（Revoked）
- `E`：无法检查（Error）
- `N`：无签名（No signature）

##### 配置自动签名

**为所有新标签自动签名**：
```bash
# 配置自动签名标签
git config --global tag.forceSignAnnotated true

# 之后创建附注标签时会自动签名
git tag -a v1.0.0 -m "Release"
# 会自动签名
```

**验证配置**：
```bash
# 查看标签相关配置
git config --get tag.forceSignAnnotated
```

#### 7.2 标签重命名和更新

##### 重命名标签

**重命名本地标签**：
```bash
# 方法 1：删除旧标签，创建新标签
git tag new-name old-name
git tag -d old-name

# 方法 2：使用 -f 强制创建（如果新标签已存在）
git tag -f new-name old-name
```

**重命名远程标签**：
```bash
# 1. 删除远程旧标签
git push origin --delete old-name

# 2. 推送新标签
git push origin new-name

# 或使用重命名后的本地标签
git tag new-name old-name
git tag -d old-name
git push origin --delete old-name
git push origin new-name
```

**完整重命名流程**：
```bash
# 1. 重命名本地标签
git tag new-name old-name
git tag -d old-name

# 2. 删除远程旧标签
git push origin --delete old-name

# 3. 推送新标签
git push origin new-name
```

##### 更新标签

**⚠️ 重要提示**：通常不应该更新已推送的标签，因为：
- 可能影响其他团队成员
- 可能破坏 CI/CD 流程
- 不符合最佳实践

**如果必须更新标签**：
```bash
# 1. 删除旧标签（本地和远程）
git tag -d v1.0.0
git push origin --delete v1.0.0

# 2. 创建新标签指向新提交
git tag -a v1.0.0 <new-commit-hash> -m "Updated release"

# 3. 推送新标签
git push origin v1.0.0
```

**更安全的方式**：创建新版本号
```bash
# 不要更新 v1.0.0，而是创建 v1.0.1
git tag -a v1.0.1 -m "Release version 1.0.1 (updated)"
git push origin v1.0.1
```

#### 7.3 基于标签的发布管理

##### 语义化版本控制

**版本号格式**：
```
<major>.<minor>.<patch>[-<prerelease>][+<build>]
```

**版本号递增规则**：
- **主版本号（Major）**：不兼容的 API 修改
- **次版本号（Minor）**：向下兼容的功能性新增
- **修订号（Patch）**：向下兼容的问题修正
- **预发布版本（Prerelease）**：alpha、beta、rc 等
- **构建元数据（Build）**：构建号、日期等

**示例**：
```bash
# 主版本
v1.0.0
v2.0.0

# 次版本
v1.1.0
v1.2.0

# 修订版本
v1.0.1
v1.0.2

# 预发布版本
v1.0.0-alpha.1
v1.0.0-beta.1
v1.0.0-rc.1

# 构建元数据
v1.0.0+20240115
v1.0.0+build.123
```

##### 发布工作流

**1. 准备发布**：
```bash
# 确保代码是最新的
git checkout main
git pull origin main

# 运行测试
npm test

# 更新版本号（在 package.json、CHANGELOG.md 等）
# 提交版本更新
git add .
git commit -m "chore: bump version to 1.0.0"
```

**2. 创建发布标签**：
```bash
# 创建附注标签
git tag -a v1.0.0 -m "Release version 1.0.0

Features:
- New user authentication
- Dashboard improvements

Bug Fixes:
- Fixed memory leak
- Fixed UI rendering issue

See CHANGELOG.md for details."
```

**3. 推送标签**：
```bash
# 推送标签
git push origin v1.0.0

# 推送所有标签（如果需要）
git push origin --tags
```

**4. 创建 GitHub Release**：
- 在 GitHub 上基于标签创建 Release
- 添加发布说明
- 上传构建产物

##### 自动化发布脚本

**示例脚本**：
```bash
#!/bin/bash
# release.sh

VERSION=$1
if [ -z "$VERSION" ]; then
    echo "Usage: ./release.sh <version>"
    echo "Example: ./release.sh 1.0.0"
    exit 1
fi

# 1. 确保在 main 分支
git checkout main
git pull origin main

# 2. 运行测试
echo "Running tests..."
npm test || exit 1

# 3. 更新版本号
echo "Updating version to $VERSION..."
npm version $VERSION --no-git-tag-version

# 4. 提交版本更新
git add package.json package-lock.json
git commit -m "chore: bump version to $VERSION"

# 5. 创建标签
git tag -a "v$VERSION" -m "Release version $VERSION"

# 6. 推送提交和标签
git push origin main
git push origin "v$VERSION"

echo "Release $VERSION created successfully!"
```

**使用方式**：
```bash
chmod +x release.sh
./release.sh 1.0.0
```

#### 7.4 标签与 CI/CD 集成

##### GitHub Actions 示例

**触发标签构建**：
```yaml
name: Release

on:
  push:
    tags:
      - 'v*'  # 匹配所有 v 开头的标签

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Build
        run: npm run build
      
      - name: Create Release
        uses: actions/create-release@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tag_name: ${{ github.ref }}
          release_name: Release ${{ github.ref }}
          body: |
            See CHANGELOG.md for details
          draft: false
          prerelease: false
```

##### GitLab CI 示例

```yaml
release:
  stage: deploy
  only:
    - tags
  script:
    - echo "Building release $CI_COMMIT_TAG"
    - npm run build
    - ./deploy.sh
```

##### 提取版本号

**从标签提取版本号**：
```bash
# 获取当前标签
TAG=$(git describe --tags --exact-match HEAD 2>/dev/null)

# 提取版本号（去掉 v 前缀）
VERSION=${TAG#v}

# 在脚本中使用
echo "Building version $VERSION"
```

**获取最新标签**：
```bash
# 获取最新标签
LATEST_TAG=$(git describe --tags --abbrev=0)

# 获取版本号
VERSION=${LATEST_TAG#v}

echo "Latest version: $VERSION"
```

#### 7.5 标签查询和过滤

##### 高级查询

**按时间查询**：
```bash
# 列出最近创建的标签
git tag --sort=-creatordate -l "v*" | head -5

# 列出特定时间范围内的标签
git for-each-ref --format='%(refname:short) %(creatordate)' refs/tags | \
  awk '$2 >= "2024-01-01" && $2 <= "2024-12-31"'
```

**按提交者查询**：
```bash
# 列出特定创建者的标签
git for-each-ref --format='%(refname:short) %(taggername)' refs/tags | \
  grep "Name"
```

**按提交信息查询**：
```bash
# 查找包含特定信息的标签
git tag -l -n1 | grep "bug fix"
```

##### 标签统计

**统计标签数量**：
```bash
# 统计所有标签
git tag | wc -l

# 统计匹配模式的标签
git tag -l "v1.*" | wc -l
```

**标签时间线**：
```bash
# 显示标签及其创建时间
git for-each-ref --format='%(refname:short) %(creatordate:short)' \
  --sort=-creatordate refs/tags
```

#### 7.6 标签最佳实践总结

##### 创建标签

- ✅ 使用附注标签（`-a`）
- ✅ 提供有意义的标签信息（`-m`）
- ✅ 使用语义化版本号
- ✅ 签名重要标签（`-s`）
- ❌ 避免使用轻量标签（除非临时标记）

##### 命名规范

- ✅ 使用统一前缀（如 `v`）
- ✅ 遵循语义化版本规范
- ✅ 使用有意义的名称
- ❌ 避免空格和特殊字符

##### 推送和共享

- ✅ 及时推送标签到远程
- ✅ 与团队共享重要标记
- ✅ 在 CI/CD 中使用标签
- ❌ 不要更新已推送的标签

##### 版本管理

- ✅ 使用语义化版本控制
- ✅ 维护 CHANGELOG
- ✅ 自动化发布流程
- ✅ 文档化版本策略

##### 安全

- ✅ 签名重要标签
- ✅ 验证标签签名
- ✅ 保护发布分支
- ✅ 审查标签创建权限

---

### 第八章：高级调试

#### 7.1 二分查找
- 使用 git bisect 查找问题
- 自动化二分查找
- 二分查找最佳实践

**实践**：
```bash
# 开始二分查找
git bisect start

# 标记为坏提交
git bisect bad

# 标记为好提交
git bisect good <commit-hash>

# Git 会自动切换到中间提交
# 测试后标记 good 或 bad
git bisect good
git bisect bad

# 完成二分查找
git bisect reset
```

#### 7.2 查找问题
- 使用 git blame 查找作者
- 使用 git log 查找历史
- 使用 git grep 搜索内容

**实践**：
```bash
# 查看文件每行的作者
git blame file.txt

# 查找包含特定内容的提交
git log -S "function_name" --source --all

# 搜索文件内容
git grep "search_term"
```

---

### 第八章：性能优化

#### 8.1 大型仓库优化
- 浅克隆
- 部分克隆
- 稀疏检出

**实践**：
```bash
# 浅克隆（只克隆最近的历史）
git clone --depth 1 https://github.com/user/repo.git

# 部分克隆（只克隆特定分支）
git clone --single-branch --branch main https://github.com/user/repo.git

# 稀疏检出（只检出部分文件）
git clone --filter=blob:none --sparse https://github.com/user/repo.git
cd repo
git sparse-checkout set dir1 dir2
```

#### 8.2 仓库维护
- 垃圾回收
- 压缩仓库
- 清理未使用的对象

**实践**：
```bash
# 手动触发垃圾回收
git gc

# 积极压缩
git gc --aggressive

# 清理未跟踪文件
git clean -n              # 预览
git clean -f              # 删除未跟踪文件
git clean -fd             # 删除未跟踪文件和目录
```

---

## 🎯 实践项目

### 项目 1：重构提交历史

1. 使用交互式 Rebase 整理提交
2. 合并相关提交
3. 修改提交信息
4. 验证历史

### 项目 2：实现 Git Hooks

1. 创建 pre-commit hook 检查代码
2. 创建 commit-msg hook 验证格式
3. 创建 post-commit hook 发送通知

### 项目 3：使用子模块管理依赖

1. 添加外部库作为子模块
2. 更新子模块
3. 处理子模块冲突

---

## ✅ 学习检查点

完成进阶学习后，您应该能够：

- [ ] 理解 Git 内部机制（对象、引用、索引）
- [ ] 能够使用 rebase 整理提交历史
- [ ] 能够使用 cherry-pick 选择性应用提交
- [ ] 能够修改和清理提交历史
- [ ] 能够使用 reflog 恢复丢失的提交
- [ ] 能够解决复杂的合并冲突
- [ ] 能够编写和使用 Git hooks
- [ ] 能够使用子模块和子树
- [ ] 能够使用 bisect 查找问题
- [ ] 能够优化大型仓库性能

---

## 📖 推荐资源

- [Pro Git 中文版 - 第 6-10 章](https://git-scm.com/book/zh/v2)
- [Git 内部原理](https://git-scm.com/book/zh/v2/Git-%E5%86%85%E9%83%A8%E5%8E%9F%E7%90%86)
- [Git Hooks 文档](https://git-scm.com/docs/githooks)

---

**下一步**：完成进阶学习后，进入 `03_Expert` 学习 Git 专家级内容。
