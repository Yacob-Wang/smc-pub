/* ============================================================================
   jk-filter —— 左侧栏顶部 Filter 框
   - 实时模糊匹配每个 nav item 的文本
   - 不匹配的 item 隐藏（不删除 DOM）
   - 父级 section 若所有子项都被过滤，自动隐藏该 section
   - 全局快捷键: "f" 聚焦（仅非 input/textarea 时），不与 "/" 冲突
   ============================================================================ */

(function () {
  "use strict";

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

  function highlight(text, q) {
    if (!q) return text;
    const re = new RegExp("(" + escapeRe(q) + ")", "ig");
    return text.replace(re, '<mark style="background:var(--jk-bg-active);color:var(--jk-text-active);padding:0 1px;border-radius:2px">$1</mark>');
  }

  function init() {
    // 1) 注入 Filter 框（如果还没有）
    let input = $("[data-jk-filter-input]");
    if (!input) {
      const sidebar = $(".md-sidebar--primary .md-sidebar__scrollwrap");
      if (!sidebar) return;
      const wrap = document.createElement("div");
      wrap.className = "jk-filter";
      wrap.innerHTML =
        '<input type="text" class="jk-filter__input" placeholder="过滤…" ' +
        'aria-label="过滤侧栏导航" autocomplete="off" spellcheck="false" ' +
        'data-jk-filter-input>';
      sidebar.insertBefore(wrap, sidebar.firstChild);
      input = $("[data-jk-filter-input]", wrap);
    }

    if (!input) return;

    // 2) 缓存原始 label 文本
    const nav = $(".md-sidebar--primary .md-nav--primary");
    if (!nav) return;

    const links = $$(".md-nav--primary .md-nav__link", nav);
    const originalLabels = new Map();
    links.forEach((a) => {
      const ellipsis = a.querySelector(".md-ellipsis");
      if (ellipsis && !originalLabels.has(a)) {
        originalLabels.set(a, ellipsis.textContent);
      }
    });

    function applyFilter() {
      const q = input.value.trim();
      const lower = q.toLowerCase();

      // 1. 遍历每个叶子 item
      $$(".md-nav--primary .md-nav__item", nav).forEach((item) => {
        // 跳过一级 section（直接看子级）
        if (item.classList.contains("md-nav__item--section")) return;
        const a = item.querySelector(":scope > .md-nav__link");
        if (!a) return;
        const text = (originalLabels.get(a) || a.textContent || "").toLowerCase();
        const match = !q || text.includes(lower);
        item.style.display = match ? "" : "none";
      });

      // 2. 处理一级 section：若其下所有子项都被隐藏，也隐藏自己
      $$(".md-nav--primary > .md-nav__list > .md-nav__item--section", nav).forEach((section) => {
        // 找该 section 下的所有叶子
        const all = $$(".md-nav__item", section).filter((x) => !x.classList.contains("md-nav__item--section"));
        const anyVisible = all.some((x) => x.style.display !== "none");
        section.style.display = anyVisible ? "" : "none";

        // 3. 高亮匹配文本
        const link = section.querySelector(":scope > .md-nav__link");
        if (link) {
          const ellipsis = link.querySelector(".md-ellipsis");
          if (ellipsis) {
            const orig = originalLabels.get(link) || "";
            ellipsis.innerHTML = q ? highlight(orig, q) : orig;
          }
        }
      });

      // 4. 高亮子项
      links.forEach((a) => {
        const ellipsis = a.querySelector(".md-ellipsis");
        if (!ellipsis) return;
        const orig = originalLabels.get(a) || "";
        const parentSection = a.closest(".md-nav__item--section");
        if (parentSection && q) {
          // 只高亮属于显示中 section 的
          if (parentSection.style.display === "none") return;
          ellipsis.innerHTML = highlight(orig, q);
        } else if (!q) {
          ellipsis.innerHTML = orig;
        }
      });
    }

    let timer = null;
    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(applyFilter, 80);
    });

    // 全局快捷键 "f" 聚焦（避免与搜索框的 "/" 冲突）
    document.addEventListener("keydown", (e) => {
      if (e.key === "f" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const t = e.target;
        const tag = t && t.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || (t && t.isContentEditable)) return;
        e.preventDefault();
        input.focus();
        input.select();
      }
      // Esc 清空
      if (e.key === "Escape" && document.activeElement === input) {
        input.value = "";
        applyFilter();
        input.blur();
      }
    });
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(() => init());
  } else if (document.readyState !== "loading") {
    init();
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
