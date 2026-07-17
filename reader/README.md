# 稳知库（StabilityMatrix Reader）

Android 离线阅读 App **「稳知库」**，将本仓库 Markdown 正文打包进 APK，在手机/平板与 Android TV 上离线阅读。

## 架构

```
Markdown 源文件 (仓库根目录)
        │
        ▼
scripts/pack-content.ps1
        ├── catalog.json      模块 / 系列 / 篇章目录树
        ├── link-map.json     文内 .md 链接 → articleId
        ├── articles.db       FTS4 全文索引
        └── articles/**/*.md  正文副本
        │
        ▼
reader/app (Kotlin + Compose + Markwon)
        ├── mobile flavor    手机 + 触屏平板（三 Tab 底栏）
        └── tv flavor        Android TV 遥控（Leanback + D-pad）
```

## 构建

### 前置条件

- JDK 17+
- Android SDK（`compileSdk 34`，`local.properties` 中配置 `sdk.dir`）
- Windows PowerShell（打包脚本）
- `sqlite3`（PATH 中可用，用于生成 FTS 索引）

### 命令

**手机 / 触屏平板（mobile）：**

```bat
cd reader
gradlew.bat assembleMobileDebug
```

APK：`app/build/outputs/apk/mobile/debug/app-mobile-debug.apk`  
包名：`com.stabilitymatrix.reader`

**Android TV 遥控（tv）：**

```bat
cd reader
gradlew.bat assembleTvDebug
```

APK：`app/build/outputs/apk/tv/debug/app-tv-debug.apk`  
包名：`com.stabilitymatrix.reader.tv`（可与 mobile 同机并存）

**一次构建两个 flavor：**

```bat
gradlew.bat assembleMobileDebug assembleTvDebug
```

Release 构建：

```bat
gradlew.bat assembleMobileRelease assembleTvRelease
```

### 仅重新打包内容（不编译 App）

```bat
cd ..
scripts\pack-content.cmd
```

## 内容范围

**包含**：`Linux_Kernel/`、`Runtime/`、`Android_Framework/`、`App/`、`Tools/`、`Hook/`、`AI_Native_X/`、根目录 README。

## App 功能

| 功能 | 说明 |
|------|------|
| 首页模块树 | 对齐仓库顶层目录，可折叠 |
| 系列列表 | 解析各系列 README 表格确定篇章顺序 |
| 文章阅读 | 按 `##`/`###` 分段 LazyColumn 懒加载 |
| 文内链接 | 相对路径 `.md` 链接跳转至 App 内文章 |
| 上一篇/下一篇 | 系列内顺序 + 文首显式导航 |
| 全文搜索 | 预构建 SQLite FTS4 |
| 书签 / 阅读进度 | DataStore 持久化 |
| 设置 | 深色/浅色/跟随系统、字号 85%–145% |
| 平板 | 宽屏（≥840dp）左侧 TOC + 右侧正文 |
| 阅读统计 | 时长累计；≥45 秒记为已读 |
| **TV 遥控** | 顶部 Tab（继续阅读/目录/书架/设置）；阅读页 TOC + WebView + 底栏；D-pad / PageUp·PageDown 滚动 |

## 源码结构

```
app/src/main/               共享：数据层、主题、Markwon、mobile 通用 UI
app/src/mobile/             手机入口 MainActivity + LAUNCHER
app/src/tv/                 TV 入口 TvMainActivity + LEANBACK_LAUNCHER
  java/.../ui/tv/           TV 焦点、Tab、各 Screen
```

## 与正文的关系

- **Markdown 是唯一真相源**：在原目录编辑正文即可。
- **App 是只读渲染层**：构建时自动打包，不反向修改正文。
- `app/src/main/assets/` 为构建产物，已 gitignore，不入库。

## 已知限制（v1）
- Mermaid 图表以代码块形式展示，不做图形渲染
- 无 OTA 内容更新（需重新构建 APK）
- 打包脚本目前为 Windows PowerShell（可后续加 `pack-content.sh`）
- **TV v1 无全文搜索**（mobile 保留 FTS 搜索）
- TV 阅读页 Zone 切换（TOC ↔ 正文 ↔ 底栏）后续可继续优化焦点链
