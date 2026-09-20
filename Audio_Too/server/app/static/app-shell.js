/*
 * app-shell.js — the shared global nav for every Audio_Too page (studio + business).
 *
 * Single source of truth for the top navigation. Previously each page hand-copied
 * the <nav class="studio-nav"> markup; now a page just links the theme and this
 * script and gets the exact same nav, styling, and active-state behaviour.
 *
 * Usage (in every page <head> or end of <body>):
 *   <link rel="stylesheet" href="/styles.css">
 *   <link rel="stylesheet" href="/studio-theme.css">
 *   <script src="/app-shell.js" data-active="dashboard" data-page="Dashboard" defer></script>
 *
 *   data-active : which nav link to highlight (one of the NAV ids below).
 *                 Omit to auto-match window.location.pathname.
 *   data-page   : optional label shown after the wordmark (e.g. "AudioGen").
 *
 * If a page already contains a hand-coded <nav class="studio-nav">, this replaces
 * it with the shared one, so migration is just adding the script tag.
 */
(function () {
  "use strict";

  // The global nav model — edit here once, every page updates.
  var NAV = [
    { id: "hub", label: "Hub", href: "/hub" },
    { id: "dashboard", label: "Dashboard", href: "/dashboard" },
    { id: "creative-lab", label: "AudioGen", href: "/creative-lab" },
    { id: "audio-analysis", label: "Mix Review", href: "/audio-analysis" },
    { id: "automix", label: "AutoMix", href: "/automix" },
    { id: "portfolio", label: "Portfolio", href: "/portfolio" },
  ];

  // Capture our own <script> synchronously (valid for defer + inline execution).
  var SELF = document.currentScript || (function () {
    var s = document.querySelectorAll('script[src*="app-shell.js"]');
    return s[s.length - 1] || null;
  })();

  function activeId() {
    var explicit = SELF && SELF.getAttribute("data-active");
    if (explicit) return explicit;
    var path = window.location.pathname.replace(/\/+$/, "") || "/";
    for (var i = 0; i < NAV.length; i++) {
      if (NAV[i].href === path) return NAV[i].id;
    }
    return "";
  }

  function buildNav(active, pageLabel) {
    var nav = document.createElement("nav");
    nav.className = "studio-nav";
    nav.setAttribute("data-shell", "1");

    var left = document.createElement("div");
    left.className = "studio-nav-left";

    var brand = document.createElement("a");
    brand.className = "studio-nav-wordmark";
    brand.href = "/hub";
    brand.innerHTML = "Thursday<span>.</span>";
    left.appendChild(brand);

    if (pageLabel) {
      var divider = document.createElement("div");
      divider.className = "studio-nav-div";
      var page = document.createElement("span");
      page.className = "studio-nav-page";
      page.textContent = pageLabel;
      left.appendChild(divider);
      left.appendChild(page);
    }

    var right = document.createElement("div");
    right.className = "studio-nav-right";
    NAV.forEach(function (item) {
      var link = document.createElement("a");
      link.className = "studio-nav-link" + (item.id === active ? " active" : "");
      link.href = item.href;
      link.textContent = item.label;
      right.appendChild(link);
    });

    nav.appendChild(left);
    nav.appendChild(right);
    return nav;
  }

  function inject() {
    if (document.querySelector('.studio-nav[data-shell]')) return; // idempotent
    var pageLabel = SELF && SELF.getAttribute("data-page");
    var nav = buildNav(activeId(), pageLabel);
    var existing = document.querySelector(".studio-nav");
    if (existing) {
      existing.replaceWith(nav); // supersede any hand-coded nav
    } else if (document.body) {
      document.body.insertBefore(nav, document.body.firstChild);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", inject);
  } else {
    inject();
  }
})();
