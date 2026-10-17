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

// components/confirm.html: a submit button with data-confirm asks in the shared dialog first.
(() => {
  const TILES = {
    danger: "bg-danger-50 text-danger-600",
    success: "bg-success-50 text-success-600",
    primary: "bg-primary-50 text-primary-600",
  };
  let pending = null;
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-confirm]");
    if (!trigger || trigger.dataset.confirmed) return;
    const dialog = document.getElementById("confirm-dialog");
    if (!dialog || typeof dialog.showModal !== "function") return;
    event.preventDefault();
    const variant = trigger.dataset.confirmVariant || "primary";
    const icon = trigger.dataset.confirmIcon || (variant === "danger" ? "trash" : "help");
    dialog.querySelector("#confirm-title").textContent = trigger.dataset.confirm;
    const text = dialog.querySelector("#confirm-text");
    text.textContent = trigger.dataset.confirmText || "";
    text.hidden = !text.textContent;
    const tile = dialog.querySelector("[data-confirm-tile]");
    tile.className = `grid size-16 place-items-center rounded-[20px] ${TILES[variant] || TILES.primary}`;
    for (const glyph of dialog.querySelectorAll("[data-confirm-glyph]")) glyph.hidden = glyph.dataset.confirmGlyph !== icon;
    const ok = dialog.querySelector("[data-confirm-ok]");
    ok.className = `btn btn-${variant}`;
    ok.textContent = trigger.dataset.confirmLabel || trigger.textContent.trim();
    pending = trigger;
    dialog.showModal();
    ok.focus();
  });
  document.addEventListener("click", (event) => {
    const dialog = document.getElementById("confirm-dialog");
    if (!dialog || !dialog.open) return;
    if (event.target.closest("[data-confirm-cancel]")) {
      dialog.close();
      pending = null;
    } else if (event.target.closest("[data-confirm-ok]") && pending) {
      const trigger = pending;
      pending = null;
      dialog.close();
      trigger.dataset.confirmed = "1";
      if (trigger.form) trigger.form.requestSubmit(trigger.type === "submit" ? trigger : undefined);
      else trigger.click();
      delete trigger.dataset.confirmed;
    }
  });
})();

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

  // accounts/signup.html: a 3-step wizard over one form (the server validates again on submit).
  window.Alpine.data("signupWizard", ({ step, mode }) => ({
    step,
    mode,
    password: "",
    busy: false,
    review: { name: "", login: "", department: "", group: "" },
    init() {
      const field = this.$refs.form.elements.password1;
      if (field) this.password = field.value;
      if (this.step === 3) this.fillReview();
    },
    get progress() {
      return [12, 45, 78][this.step - 1] ?? 100;
    },
    get strength() {
      const p = this.password || "";
      let score = 0;
      if (p.length >= 8) score++;
      if (/[A-ZА-ЯӘҒҚҢӨҰҮҺІЁ]/.test(p)) score++;
      if (/[0-9]/.test(p)) score++;
      if (/[^A-Za-z0-9А-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІіЁё]/.test(p) || p.length >= 12) score++;
      return score;
    },
    get strengthBar() {
      return ["bg-danger-600", "bg-warning-500", "bg-primary-500", "bg-success-600"][Math.max(this.strength - 1, 0)];
    },
    get strengthText() {
      return ["text-danger-700", "text-warning-700", "text-primary-700", "text-success-700"][Math.max(this.strength - 1, 0)];
    },
    get strengthLabel() {
      return (this.$root.dataset.strength || "").split("|")[Math.max(this.strength - 1, 0)];
    },
    stepValid() {
      const form = this.$refs.form;
      if (this.step === 2) {
        const field = this.mode === "code" ? form.elements.join_code : form.elements.group;
        if (field && !field.value) {
          field.setCustomValidity(this.$root.dataset.required || "");
          field.reportValidity();
          field.addEventListener("input", () => field.setCustomValidity(""), { once: true });
          field.addEventListener("change", () => field.setCustomValidity(""), { once: true });
          return false;
        }
        return true;
      }
      for (const field of form.querySelectorAll(`[data-step="${this.step}"] input`)) {
        if (!field.checkValidity()) {
          field.reportValidity();
          return false;
        }
      }
      return true;
    },
    next() {
      if (!this.stepValid()) return;
      this.step += 1;
      if (this.step === 3) this.fillReview();
      this.$root.scrollIntoView({ behavior: "smooth", block: "start" });
    },
    back() {
      if (this.step > 1) this.step -= 1;
    },
    fillReview() {
      const e = this.$refs.form.elements;
      const text = (select) => (select && select.value ? select.selectedOptions[0].text : "—");
      this.review.name = `${e.first_name.value} ${e.last_name.value}`.trim() || "—";
      this.review.login = e.email.value || "—";
      if (this.mode === "code") {
        const found = document.querySelector("#join-code-status b");
        this.review.group = found ? found.textContent : e.join_code.value || "—";
        this.review.department = "—";
      } else {
        this.review.department = text(e.department);
        this.review.group = text(e.group);
      }
    },
    onSubmit(event) {
      if (this.busy) event.preventDefault();
      this.busy = true;
    },
  }));
});
