/* ============================================================================
   jk-search —— 顶栏内联搜索组件
   - 复用 mkdocs Material 的 search_index.json
   - 实时模糊匹配 title + text，前 8 条结果下拉
   - 键盘: ↑↓ 选中、Enter 跳转、Esc 关闭
   - 全局快捷键: "/" 聚焦（仅在非 input/textarea 时）
   ============================================================================ */

(function () {
  "use strict";

  const SEARCH_INDEX_URL = (function () {
    // mkdocs 在每页注入 base_url: __md_get("__base")
    if (typeof window.__md_get === "function") {
      try { return window.__md_get("__base") + "search/search_index.json"; }
      catch (e) { /* fall through */ }
    }
    // 兜底：从当前页 URL 推断
    const path = window.location.pathname;
    const depth = path.split("/").filter(Boolean).length;
    const base = depth > 0 ? "../".repeat(depth) : "./";
    return base + "search/search_index.json";
  })();

  const MAX_RESULTS = 8;
  const SNIPPET_LEN = 80;
  const DEBOUNCE_MS = 120;

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  function init() {
    const input = $("[data-jk-search-input]");
    const results = $("[data-jk-search-results]");
    const root = $(".jk-search");
    if (!input || !results || !root) return;

    let index = null;
    let loading = null;
    let active = -1;
    let hits = [];

    // --- 索引加载（懒） -------------------------------------------------
    function ensureIndex() {
      if (index) return Promise.resolve(index);
      if (loading) return loading;
      loading = fetch(SEARCH_INDEX_URL, { credentials: "same-origin" })
        .then((r) => {
          if (!r.ok) throw new Error("search index " + r.status);
          return r.json();
        })
        .then((data) => { index = data; return data; })
        .catch((err) => {
          console.warn("[jk-search] index load failed:", err);
          index = { docs: [] };
          return index;
        });
      return loading;
    }

    // --- 搜索 ----------------------------------------------------------
    function search(q) {
      q = (q || "").trim().toLowerCase();
      if (!q || !index || !Array.isArray(index.docs)) return [];
      const out = [];
      for (let i = 0; i < index.docs.length && out.length < MAX_RESULTS; i++) {
        const d = index.docs[i];
        const title = (d.title || "").toLowerCase();
        const text = (d.text || "").toLowerCase();
        const ti = title.indexOf(q);
        const te = text.indexOf(q);
        if (ti < 0 && te < 0) continue;
        // 评分：title 命中权重更高
        const score = (ti >= 0 ? -ti : 1000) + (te >= 0 ? te * 0.01 : 1000);
        out.push({ doc: d, score: score, textIdx: te });
      }
      out.sort((a, b) => a.score - b.score);
      return out.slice(0, MAX_RESULTS);
    }

    // --- 渲染 ----------------------------------------------------------
    function baseUrl() {
      if (typeof window.__md_get === "function") {
        try { return window.__md_get("__base"); } catch (e) {}
      }
      return "";
    }

    function snippet(text, idx, q) {
      if (!text) return "";
      if (idx < 0) {
        return text.slice(0, SNIPPET_LEN) + (text.length > SNIPPET_LEN ? "…" : "");
      }
      const start = Math.max(0, idx - 20);
      const end = Math.min(text.length, idx + q.length + SNIPPET_LEN - 20);
      const before = start > 0 ? "…" : "";
      const after = end < text.length ? "…" : "";
      return before + text.slice(start, end) + after;
    }

    function highlight(text, q) {
      if (!q) return text;
      const re = new RegExp("(" + q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig");
      return text.replace(re, '<mark style="background:var(--jk-bg-active);color:var(--jk-text-active);padding:0 1px;border-radius:2px">$1</mark>');
    }

    function render(q) {
      const empty = $(".jk-search__hint");
      if (!q) {
        results.innerHTML =
          '<div class="jk-search__hint">输入关键词开始搜索 · 按 <kbd>/</kbd> 聚焦 · <kbd>Esc</kbd> 关闭</div>';
        return;
      }
      hits = search(q);
      if (hits.length === 0) {
        results.innerHTML = '<div class="jk-search__empty">没有匹配结果</div>';
        return;
      }
      results.innerHTML = hits.map((h, i) => {
        const loc = h.doc.location;
        const title = h.doc.title || "(无标题)";
        const snip = snippet(h.doc.text || "", h.textIdx, q);
        return (
          '<a class="jk-search__hit" href="' + baseUrl() + loc + '" data-idx="' + i + '">' +
            '<div class="jk-search__title">' + highlight(title, q) + '</div>' +
            '<div class="jk-search__text">' + highlight(snip, q) + '</div>' +
          '</a>'
        );
      }).join("");
      active = -1;
    }

    // --- 行为 ----------------------------------------------------------
    let timer = null;
    function scheduleRender() {
      clearTimeout(timer);
      timer = setTimeout(() => render(input.value), DEBOUNCE_MS);
    }

    function open() {
      root.classList.add("jk-search--open");
      if (input.value.trim()) {
        // 用户已经输入了字符 → 立刻拉索引渲染
        ensureIndex().then(() => render(input.value));
      } else {
        results.innerHTML =
          '<div class="jk-search__hint">输入关键词开始搜索 · 按 <kbd>/</kbd> 聚焦 · <kbd>Esc</kbd> 关闭</div>';
      }
    }

    function close() {
      root.classList.remove("jk-search--open");
      active = -1;
    }

    function updateActive() {
      $$(".jk-search__hit", results).forEach((el, i) => {
        el.classList.toggle("jk-search__hit--active", i === active);
        if (i === active) {
          el.scrollIntoView({ block: "nearest" });
        }
      });
    }

    function activate(idx) {
      const a = results.querySelector('[data-idx="' + idx + '"]');
      if (a) window.location.href = a.getAttribute("href");
    }

    // --- 事件绑定 -------------------------------------------------------
    input.addEventListener("focus", () => { open(); ensureIndex(); });
    input.addEventListener("input", () => { open(); scheduleRender(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { close(); input.blur(); return; }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (hits.length > 0) { active = (active + 1) % hits.length; updateActive(); }
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        if (hits.length > 0) { active = (active - 1 + hits.length) % hits.length; updateActive(); }
        return;
      }
      if (e.key === "Enter") {
        if (active >= 0) { e.preventDefault(); activate(active); return; }
        // 没有选中时，命中第一条
        const first = $(".jk-search__hit", results);
        if (first) { e.preventDefault(); window.location.href = first.getAttribute("href"); }
      }
    });

    // 全局快捷键 "/" 聚焦
    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const t = e.target;
        const tag = t && t.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || (t && t.isContentEditable)) return;
        e.preventDefault();
        input.focus();
        input.select();
      }
    });

    // 点击外部关闭
    document.addEventListener("click", (e) => {
      if (!root.contains(e.target)) close();
    });

    // shortcut hint（macOS 显示 ⌘ 符号）
    const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
    const shortcut = $("[data-jk-search-shortcut]");
    if (shortcut) shortcut.textContent = isMac ? "⌘ K" : "/";
  }

  // mkdocs 用 document$ 订阅 instant nav，重新绑定
  if (typeof document$ !== "undefined") {
    document$.subscribe(() => init());
  } else if (document.readyState !== "loading") {
    init();
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
