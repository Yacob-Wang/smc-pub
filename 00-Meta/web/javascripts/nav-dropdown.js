(function () {
  "use strict";

  var FINE_POINTER = "(hover: hover) and (pointer: fine)";
  var MOBILE = "(max-width: 59.9375em)";

  var LABELS = {
    menu: "菜单",
    menuAria: "打开模块导航",
    sheetTitle: "模块导航",
    layerOverview: "本层总览",
    close: "关闭",
  };

  function isFinePointer() {
    return window.matchMedia(FINE_POINTER).matches;
  }

  function isMobile() {
    return window.matchMedia(MOBILE).matches;
  }

  function siteBase() {
    return typeof __md_scope !== "undefined" ? __md_scope : new URL("./", location.href);
  }

  function normalizePath(pathname) {
    var path = decodeURIComponent(pathname || "/");
    if (!path.startsWith("/")) path = "/" + path;
    path = path.replace(/\/index\.html$/, "/");
    if (path.length > 1 && path.endsWith("/")) path = path.slice(0, -1);
    return path;
  }

  function currentPath() {
    var base = normalizePath(siteBase().pathname);
    var full = normalizePath(location.pathname);
    if (full.startsWith(base)) {
      full = full.slice(base.length) || "/";
    }
    return full;
  }

  function resolveNavPath(href) {
    if (!href) return null;
    try {
      var base = normalizePath(siteBase().pathname);
      var abs = normalizePath(new URL(href, location.href).pathname);
      if (abs.startsWith(base)) {
        return abs.slice(base.length) || "/";
      }
      return abs;
    } catch (error) {
      return null;
    }
  }

  function pathMatches(href) {
    var target = resolveNavPath(href);
    var current = currentPath();
    if (!target) return false;
    if (target === current) return true;
    return current.startsWith(target + "/");
  }

  function scrollChipIntoView(container, selector) {
    if (!container) return;
    var active = container.querySelector(selector);
    if (!active) return;
    var offset = active.offsetLeft - container.clientWidth / 2 + active.clientWidth / 2;
    container.scrollTo({ left: Math.max(0, offset), behavior: "smooth" });
  }

  function formatArticleLabel(link) {
    var text = link.textContent.trim();
    var href = link.getAttribute("href") || "";
    var decoded = decodeURIComponent(href);
    var hrefMatch = decoded.match(/\/(\d+)[-_]/);
    if (hrefMatch && text.indexOf(hrefMatch[1]) !== 0) {
      return hrefMatch[1] + " · " + text;
    }
    return text;
  }

  function buildChip(link, extraClass, labelFormatter) {
    var chip = document.createElement("a");
    chip.className = "jk-strip__link" + (extraClass ? " " + extraClass : "");
    chip.href = link.getAttribute("href") || "#";
    chip.textContent = labelFormatter ? labelFormatter(link) : link.textContent.trim();
    if (pathMatches(chip.href)) {
      chip.classList.add("jk-strip__link--active");
    }
    return chip;
  }

  function buildStrip(container, links, scrollClass, linkClass, withMenu, labelFormatter) {
    container.innerHTML = "";
    if (!links.length) {
      container.hidden = true;
      return false;
    }
    var scroll = document.createElement("div");
    scroll.className = scrollClass;
    links.forEach(function (link) {
      scroll.appendChild(buildChip(link, linkClass, labelFormatter));
    });
    if (withMenu) {
      var menuBtn = document.createElement("button");
      menuBtn.type = "button";
      menuBtn.className = "jk-strip__menu-btn";
      menuBtn.setAttribute("aria-label", LABELS.menuAria);
      menuBtn.textContent = LABELS.menu;
      menuBtn.addEventListener("click", openNavSheet);
      scroll.appendChild(menuBtn);
    }
    container.hidden = false;
    container.appendChild(scroll);
    scrollChipIntoView(scroll, ".jk-strip__link--active");
    return true;
  }

  function getActiveTabMenu() {
    var activeTab = document.querySelector(".md-tabs__item--active.jk-tabs__item--menu");
    if (!activeTab) return null;
    return activeTab.querySelector(".jk-tabs__menu");
  }

  function moduleLinks(menu) {
    var selector = ":scope > .jk-tabs__menu-link, :scope > .jk-tabs__menu-item--has-sub > .jk-tabs__menu-link";
    return Array.prototype.slice.call(menu.querySelectorAll(selector));
  }

  function findActiveFlyout(menu) {
    var current = currentPath();
    var best = null;
    var bestLen = -1;
    menu.querySelectorAll(".jk-tabs__menu-item--has-sub").forEach(function (item) {
      var category = item.querySelector(":scope > .jk-tabs__menu-link");
      if (!category) return;
      var categoryPath = resolveNavPath(category.getAttribute("href"));
      var matched = false;
      if (categoryPath && (current === categoryPath || current.startsWith(categoryPath + "/"))) {
        matched = true;
      }
      item.querySelectorAll(".jk-tabs__submenu-link").forEach(function (link) {
        var subPath = resolveNavPath(link.getAttribute("href"));
        if (subPath && (current === subPath || current.startsWith(subPath + "/"))) {
          matched = true;
        }
      });
      if (matched && categoryPath && categoryPath.length > bestLen) {
        best = item;
        bestLen = categoryPath.length;
      }
    });
    return best;
  }

  function seriesLinks(flyoutItem) {
    var links = [];
    var category = flyoutItem.querySelector(":scope > .jk-tabs__menu-link");
    if (category) links.push(category);
    flyoutItem.querySelectorAll(".jk-tabs__submenu-link").forEach(function (link) {
      links.push(link);
    });
    return links;
  }

  function articleLinksFromSidebar() {
    var active = document.querySelector(".md-sidebar--primary .md-nav__link--active");
    if (!active) return [];
    var item = active.closest(".md-nav__item");
    if (!item) return [];
    var list = item.parentElement;
    if (!list) return [];
    var items = list.querySelectorAll(":scope > .md-nav__item");
    if (items.length < 2) {
      var section = list.closest(".md-nav__item");
      if (!section) return [];
      var nested = section.querySelector(":scope > nav .md-nav__list");
      if (!nested) return [];
      items = nested.querySelectorAll(":scope > .md-nav__item");
    }
    if (items.length < 2) return [];
    var links = [];
    items.forEach(function (navItem) {
      var link = navItem.querySelector(":scope > .md-nav__link");
      if (link && link.getAttribute("href")) links.push(link);
    });
    return links;
  }

  function getSeriesDirPrefix() {
    var canonical = document.querySelector('link[rel="canonical"]');
    if (!canonical) return null;
    var path = resolveNavPath(canonical.href);
    if (!path) return null;
    var parts = path.split("/").filter(Boolean);
    if (parts.length < 3) return null;
    parts.pop();
    return "/" + parts.join("/") + "/";
  }

  function articleLinksFromSeriesPath() {
    var prefix = getSeriesDirPrefix();
    if (!prefix) return [];
    var links = [];
    var seen = new Set();
    document.querySelectorAll(".md-sidebar--primary .md-nav__link[href]").forEach(function (link) {
      var href = link.getAttribute("href");
      var path = resolveNavPath(href);
      if (!path || seen.has(href)) return;
      if (path + "/" === prefix || path.startsWith(prefix)) {
        if (path !== prefix.replace(/\/$/, "")) {
          seen.add(href);
          links.push(link);
        }
      }
    });
    return links;
  }

  function collectArticleLinks() {
    var sidebar = articleLinksFromSidebar();
    if (sidebar.length >= 2) return sidebar;
    return articleLinksFromSeriesPath();
  }

  function initSeriesStrip() {
    var strip = document.querySelector("[data-jk-series-strip]");
    if (!strip) return;
    if (!isMobile()) {
      strip.hidden = true;
      return;
    }
    var menu = getActiveTabMenu();
    if (!menu) {
      strip.hidden = true;
      return;
    }
    var flyout = findActiveFlyout(menu);
    if (!flyout) {
      strip.hidden = true;
      return;
    }
    var links = seriesLinks(flyout);
    if (links.length < 2) {
      strip.hidden = true;
      return;
    }
    buildStrip(strip, links, "jk-series-strip__scroll", "jk-series-strip__link", false);
  }

  function initArticleStrip() {
    var strip = document.querySelector("[data-jk-article-strip]");
    if (!strip) return;
    if (!isMobile()) {
      strip.hidden = true;
      return;
    }
    var links = collectArticleLinks();
    if (links.length < 2) {
      strip.hidden = true;
      return;
    }
    buildStrip(
      strip,
      links,
      "jk-article-strip__scroll",
      "jk-article-strip__link",
      false,
      formatArticleLabel
    );
  }

  function closeNavSheet() {
    var sheet = document.querySelector("[data-jk-nav-sheet]");
    if (!sheet) return;
    sheet.hidden = true;
    document.body.classList.remove("jk-nav-sheet-open");
  }

  function openNavSheet() {
    var sheet = document.querySelector("[data-jk-nav-sheet]");
    var body = document.querySelector("[data-jk-nav-sheet-body]");
    var title = document.querySelector("[data-jk-nav-sheet-title]");
    var menu = getActiveTabMenu();
    var activeTab = document.querySelector(".md-tabs__item--active.jk-tabs__item--menu > .md-tabs__link");
    if (!sheet || !body || !menu) return;

    body.innerHTML = "";
    if (title) title.textContent = activeTab ? activeTab.textContent.trim() : LABELS.sheetTitle;

    menu.childNodes.forEach(function (node) {
      if (node.nodeType !== 1) return;
      if (node.matches(".jk-tabs__menu-link")) {
        var row = document.createElement("a");
        row.className = "jk-nav-sheet__link";
        row.href = node.getAttribute("href") || "#";
        row.textContent = node.textContent.trim();
        if (pathMatches(row.href)) row.classList.add("jk-nav-sheet__link--active");
        body.appendChild(row);
        return;
      }
      if (node.matches(".jk-tabs__menu-item--has-sub")) {
        var group = document.createElement("details");
        group.className = "jk-nav-sheet__group";
        var category = node.querySelector(":scope > .jk-tabs__menu-link");
        var summary = document.createElement("summary");
        summary.className = "jk-nav-sheet__summary";
        summary.textContent = category ? category.textContent.trim() : "更多";
        group.appendChild(summary);
        if (category) {
          var overview = document.createElement("a");
          overview.className = "jk-nav-sheet__link";
          overview.href = category.getAttribute("href") || "#";
          overview.textContent = LABELS.layerOverview;
          if (pathMatches(overview.href)) overview.classList.add("jk-nav-sheet__link--active");
          group.appendChild(overview);
        }
        node.querySelectorAll(".jk-tabs__submenu-link").forEach(function (link) {
          var row = document.createElement("a");
          row.className = "jk-nav-sheet__link jk-nav-sheet__link--nested";
          row.href = link.getAttribute("href") || "#";
          row.textContent = link.textContent.trim();
          if (pathMatches(row.href)) {
            row.classList.add("jk-nav-sheet__link--active");
            group.open = true;
          }
          group.appendChild(row);
        });
        if (category && pathMatches(category.getAttribute("href"))) group.open = true;
        body.appendChild(group);
      }
    });

    sheet.hidden = false;
    document.body.classList.add("jk-nav-sheet-open");
  }

  function closeAllMenus(except) {
    document.querySelectorAll(".jk-tabs__item--menu.is-open").forEach(function (item) {
      if (item === except) return;
      item.classList.remove("is-open");
      var link = item.querySelector(".md-tabs__link");
      if (link) link.setAttribute("aria-expanded", "false");
    });
    closeAllSubmenus(null);
  }

  function closeAllSubmenus(except) {
    document.querySelectorAll(".jk-tabs__menu-item--has-sub.is-sub-open").forEach(function (item) {
      if (item === except) return;
      item.classList.remove("is-sub-open");
      var link = item.querySelector(".jk-tabs__menu-link");
      if (link) link.setAttribute("aria-expanded", "false");
    });
  }

  function openSubmenu(item) {
    closeAllSubmenus(item);
    item.classList.add("is-sub-open");
    var link = item.querySelector(".jk-tabs__menu-link");
    if (link) link.setAttribute("aria-expanded", "true");
    adjustSubmenuPosition(item);
  }

  function adjustSubmenuPosition(item) {
    var submenu = item.querySelector(".jk-tabs__submenu");
    if (!submenu) return;
    submenu.classList.remove("jk-tabs__submenu--flip");
    var rect = submenu.getBoundingClientRect();
    if (rect.right > window.innerWidth - 8) {
      submenu.classList.add("jk-tabs__submenu--flip");
    }
  }

  function initFlyoutA11y() {
    document.querySelectorAll(".jk-tabs__menu-item--has-sub").forEach(function (item) {
      var link = item.querySelector(".jk-tabs__menu-link");
      var submenu = item.querySelector(".jk-tabs__submenu");
      if (!link || !submenu || link.dataset.jkA11yBound === "1") return;
      link.dataset.jkA11yBound = "1";
      if (!submenu.id) {
        submenu.id = "jk-flyout-" + Math.random().toString(36).slice(2, 9);
      }
      link.setAttribute("aria-controls", submenu.id);
      link.setAttribute("aria-expanded", item.classList.contains("is-sub-open") ? "true" : "false");

      link.addEventListener("keydown", function (event) {
        if (event.key === "ArrowRight" || event.key === "Enter" || event.key === " ") {
          if (isFinePointer()) {
            openSubmenu(item);
            var first = submenu.querySelector(".jk-tabs__submenu-link");
            if (first) first.focus();
            event.preventDefault();
          }
        }
        if (event.key === "ArrowLeft" || event.key === "Escape") {
          item.classList.remove("is-sub-open");
          link.setAttribute("aria-expanded", "false");
        }
      });
    });
  }

  function initTabMenus() {
    document.querySelectorAll(".jk-tabs__item--menu").forEach(function (item) {
      var link = item.querySelector(".md-tabs__link");
      if (!link || link.dataset.jkMenuBound === "1") return;
      link.dataset.jkMenuBound = "1";

      link.addEventListener("click", function (event) {
        if (isFinePointer() || isMobile()) return;
        event.preventDefault();
        var open = item.classList.toggle("is-open");
        link.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) closeAllMenus(item);
      });
    });

    document.querySelectorAll(".jk-tabs__menu-item--has-sub").forEach(function (item) {
      var link = item.querySelector(".jk-tabs__menu-link");
      if (!link || link.dataset.jkSubBound === "1") return;
      link.dataset.jkSubBound = "1";

      link.addEventListener("click", function (event) {
        if (isFinePointer()) return;
        if (isMobile()) return;
        if (!item.classList.contains("is-sub-open")) {
          event.preventDefault();
          openSubmenu(item);
        }
      });
    });

    document.querySelectorAll("[data-jk-nav-sheet-close]").forEach(function (el) {
      if (el.dataset.jkSheetBound === "1") return;
      el.dataset.jkSheetBound = "1";
      el.addEventListener("click", closeNavSheet);
    });

    document.addEventListener("click", function (event) {
      if (!event.target.closest(".jk-tabs__item--menu")) closeAllMenus(null);
      if (!event.target.closest(".jk-tabs__menu-item--has-sub")) closeAllSubmenus(null);
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeAllMenus(null);
        closeNavSheet();
      }
    });

    initFlyoutA11y();
  }

  function initDesktopNavActive() {
    document.querySelectorAll(".jk-tabs__menu-link").forEach(function (link) {
      if (pathMatches(link.getAttribute("href"))) {
        link.classList.add("jk-tabs__menu-link--active");
      }
    });
    document.querySelectorAll(".jk-tabs__submenu-link").forEach(function (link) {
      if (pathMatches(link.getAttribute("href"))) {
        link.classList.add("jk-tabs__submenu-link--active");
      }
    });
  }

  function syncLandingLayout() {
    var landing = !!document.querySelector(".md-content__inner .jk-page-hero");
    document.body.classList.toggle("jk-landing", landing);
  }

  function sidebarModuleLinks() {
    var active = document.querySelector(".md-sidebar--primary .md-nav__link--active");
    if (!active) return [];
    var item = active.closest(".md-nav__item");
    if (!item) return [];
    var list = item.parentElement;
    if (!list) return [];
    var section = list.closest(".md-nav__item");
    if (section) {
      var nested = section.querySelector(":scope > nav > .md-nav__list");
      if (nested) list = nested;
    }
    var items = list.querySelectorAll(":scope > .md-nav__item");
    if (items.length < 2) return [];
    var links = [];
    items.forEach(function (navItem) {
      var link = navItem.querySelector(":scope > .md-nav__link[href]");
      if (link) links.push(link);
    });
    return links;
  }

  function initModuleStrip() {
    var strip = document.querySelector("[data-jk-module-strip]");
    if (!strip) return;
    if (!isMobile()) {
      strip.hidden = true;
      return;
    }
    var menu = getActiveTabMenu();
    var links = menu ? moduleLinks(menu) : [];
    if (links.length < 2) {
      links = sidebarModuleLinks();
    }
    buildStrip(strip, links, "jk-module-strip__scroll", "jk-module-strip__link", true);
  }

  function initNavigationChrome() {
    syncLandingLayout();
    initTabMenus();
    initDesktopNavActive();
    initModuleStrip();
    initSeriesStrip();
    initArticleStrip();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initNavigationChrome);
  } else {
    initNavigationChrome();
  }

  document$.subscribe(initNavigationChrome);

  window.addEventListener("resize", function () {
    syncLandingLayout();
    initModuleStrip();
    initSeriesStrip();
    initArticleStrip();
    document.querySelectorAll(".jk-tabs__menu-item--has-sub.is-sub-open").forEach(adjustSubmenuPosition);
  });
})();
