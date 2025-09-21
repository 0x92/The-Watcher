import "./styles/theme.css";
import "./styles/layout.css";
import "./styles/components.css";

import { initGraph } from "./modules/graph.js";
import { initPatterns } from "./modules/patterns.js";
import { initHeatmap } from "./modules/heatmap.js";
import { initOverview } from "./modules/overview.js";

const page = document.body.dataset.page || "";

const registry = {
  "ui.graph": initGraph,
  "ui.patterns": initPatterns,
  "ui.heatmap": initHeatmap,
  "ui.overview": initOverview,
};

function initThemeToggle() {
  const toggle = document.querySelector("button[data-theme-toggle]");
  if (!toggle) {
    return;
  }

  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)");
  const THEME_KEY = "the-watcher-theme";

  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    toggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    toggle.querySelector("span[data-role='label']").textContent = theme === "dark" ? "Dark" : "Light";
  }

  function currentTheme() {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "light" || stored === "dark") {
      return stored;
    }
    return prefersDark.matches ? "dark" : "light";
  }

  apply(currentTheme());

  toggle.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, next);
    apply(next);
  });

  prefersDark.addEventListener("change", () => {
    const stored = localStorage.getItem(THEME_KEY);
    if (!stored) {
      apply(prefersDark.matches ? "dark" : "light");
    }
  });
}

requestAnimationFrame(() => {
  initThemeToggle();
  const initializer = registry[page];
  if (initializer) {
    initializer();
  }
});
