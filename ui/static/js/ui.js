// Small behaviours shared by every page.

// components/modal.html: <button data-open-modal="ID"> opens <dialog id="ID">.
document.addEventListener("click", (event) => {
  const opener = event.target.closest("[data-open-modal]");
  if (!opener) return;
  const dialog = document.getElementById(opener.dataset.openModal);
  if (dialog && typeof dialog.showModal === "function") {
    event.preventDefault();
    dialog.showModal();
  }
});

// ⌘K / Ctrl+K focuses the Topbar search.
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    const input = document.querySelector("[data-search]");
    if (input && input.offsetParent !== null) {
      event.preventDefault();
      input.focus();
      input.select();
    }
  }
});

// Copy to clipboard: <button data-copy="text" data-copied-label="Көшірілді ✓">.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  try {
    await navigator.clipboard.writeText(button.dataset.copy);
  } catch {
    return;
  }
  const label = button.querySelector("[data-copy-label]") || button;
  const before = label.textContent;
  label.textContent = button.dataset.copiedLabel || "✓";
  setTimeout(() => (label.textContent = before), 2000);
});

const store = {
  get(key) {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* private mode: the state just is not remembered */
    }
  },
};

document.addEventListener("alpine:init", () => {
  // layouts/cabinet.html: mobile drawer (nav) and the collapsible desktop rail.
  window.Alpine.data("cabinet", () => ({
    nav: false,
    collapsed: store.get("ct-rail") === "1",
    wide: window.matchMedia("(min-width: 1024px)").matches,
    init() {
      const query = window.matchMedia("(min-width: 1024px)");
      query.addEventListener("change", (e) => {
        this.wide = e.matches;
        if (e.matches) this.nav = false;
      });
    },
    get rail() {
      return this.collapsed && this.wide;
    },
    toggleRail() {
      this.collapsed = !this.collapsed;
      store.set("ct-rail", this.collapsed ? "1" : "0");
    },
  }));
});
