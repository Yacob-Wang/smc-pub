# 稳知库 · Stability Matrix Course

面向 **Android 稳定性架构师** 的系列技术博客。

从 Linux 内核到 Framework、从运行时到应用层，按「定位 → 边界 → 核心机制 → 风险 → 诊断治理」组织，便于排查 Crash / ANR / OOM。

本仓库即站点源码：推送到 GitHub 后，由 Actions 构建并发布为 GitHub Pages。

---

## 怎么读

1. 打开下方某个**模块**
2. 进入该模块下的**系列 README**（总览 + 篇章目录）
3. 按目录阅读单篇；站点内也支持全文搜索

---

## 模块

| 模块 | 说明 |
|------|------|
| [Linux 内核](Linux_Kernel/) | 进程 / 内存 / IO / Binder / Socket / epoll / 分区 … |
| [运行时 / ART](Runtime/) | ART、Java Crash、Native Crash |
| [Android Framework](Android_Framework/) | 进程、ANR、Watchdog、Input、Window … |
| [应用层](App/) | Handler / MessageQueue / Looper |
| [工具](Tools/) | 调试、追踪、内存分析、Git … |
| [Hook 专题](Hook/) | OEM Hook 等 |
| [AI Native](AI_Native_X/) | 端侧 AI Runtime / AI OS / AI for Stability / AI 工程 |

## 按问题进入

| 问题 | 入口 |
|------|------|
| Java Crash | [Runtime/Java_Crash](Runtime/Java_Crash/) |
| Native Crash | [Runtime/Native_Crash](Runtime/Native_Crash/) |
| ANR | [ANR_Detection](Android_Framework/ANR_Detection/)、[Input](Android_Framework/Input/) |
| Binder | [Linux_Kernel/Binder](Linux_Kernel/Binder/) |
| OOM / 内存 | [Memory_Management](Linux_Kernel/Memory_Management/)、[ART](Runtime/ART/) |
| Watchdog | [Android_Framework/Watchdog](Android_Framework/Watchdog/) |
| Socket / epoll | [socket](Linux_Kernel/socket/)、[epoll](Linux_Kernel/epoll/) |
| 端侧 AI | [AI_Native_X](AI_Native_X/) |

---

## 本地预览

```bat
pip install -r scripts\requirements-docs.txt
py -3.12 scripts\prepare_web_docs.py
mkdocs serve
```

浏览器打开 `http://127.0.0.1:8000`。

`docs/` 为构建时生成的临时目录，请勿手改。

## 发布到 GitHub Pages

1. 在 GitHub 新建**公开**仓库（例如 `smc-pub`），不要勾选自动添加 README
2. 绑定远程并推送：

```bat
git remote add origin https://github.com/<你的用户名>/smc-pub.git
git push -u origin master
```

3. 仓库 → **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**
4. 等待 `Deploy GitHub Pages` workflow 成功后，站点地址一般为：

`https://<你的用户名>.github.io/smc-pub/`

---

技术基线：AOSP 17 + android17-6.18（详见各系列 README）

© Stability Matrix Course
