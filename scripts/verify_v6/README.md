# v6 verify 工具集

> 落地 v6 §10.4 / §13.4 规范。每个工具独立可执行,也可 `run_all.py` 一键跑全套。

## 工具清单

| 工具 | 章节 | 检查项 | 退出码 |
|---|---|---|---|
| `verify_marker.py` | §9.2 | 0 rogue + 0 嵌套 + 2 段配对 | 0=PASS / 1=FAIL |
| `verify_strip.py` | §9.4 | 0 公开站元信息残留 | 0=PASS / 1=FAIL |
| `verify_colon.py` | §3.5 | 0 半角冒号链接 | 0=PASS / 1=FAIL |
| `verify_paths.py` | §12.1 | 0 路径/类名/作者/时间线 blacklist | 0=PASS / 1=FAIL |
| `verify_bug6.py` | §12.2 | 0 子线程 6 类 bug(aart/ vvmscan rameworks ndroid: m_kill o.lmk) | 0=PASS / 1=FAIL |
| `verify_control.py` | §12.2 | 0 控制字符(0x07/0x08/0x0b/0x0c/0x1a) | 0=PASS / 1=FAIL |
| `verify_ai_words.py` | §5.3 | 0 反 AI 自嗨词表 20 个 | 0=PASS / 1=FAIL |

## 用法

### 单个工具

```bash
python verify_marker.py <article.md>
python verify_paths.py <article.md>
...
```

### 一键跑全部

```bash
python run_all.py <article.md>
```

## 设计原则

1. **每个工具独立可执行** — 不依赖其他工具,失败时能定位到具体哪个出问题
2. **统一退出码** — 0=PASS / 1=FAIL,方便集成到 CI / 自动化
3. **统一输出格式** — `=== <tool>: <file> ===` 开头,逐项 `1. <检查项>: <n> 处 ✅/❌`,最后 `✅ ALL PASS` 或 `❌ FAIL`
4. **用 chr() 拼字符串** — 避免 system prompt 渲染陷阱(v6 §10.1)
5. **负向 lookbehind** — `verify_bug6.py` 排除 `frameworks` 等合法子串

## 实战数据(2026-08-04 第 9 章落地)

- 7 个工具,9.1-9.6 6 篇文章全部 PASS
- 0 子线程 6 类 bug / 0 控制字符 / 0 半角冒号 / 0 rogue marker / 0 反 AI 自嗨词
- 主线程 hygiene:每篇 commit 前必跑

## 后续扩展(v6.1+ 候选)

- `verify_struct.py` — 26 项质量清单(内容质量 10 项 + 结构完整性 6 项 + 系列一致性 5 项 + AI 生成质量 5 项)
- `verify_facts.py` — 关键事实校准(AOSP 17 发布日 / MGLRU 版本 / 路径 等)
- `verify_chinese.py` — 中文字数 ≥ 8000
- `verify_chapter.py` — 章节完整性(H1 数量 + 标题完整性)
- `verify_quotes.py` — 量化数据附录 C 自检
- `verify_dual_view.py` — 公开站 vs 作者视图一致性

## 来源

v6 §10.4 / §13.4 实战沉淀
