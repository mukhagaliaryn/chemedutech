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
      if (this.step === 1 && document.querySelector('#username-status[data-status="error"]')) {
        form.elements.username.focus();
        return false;
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
      this.review.login = [e.username.value, e.email.value].filter(Boolean).join(" / ") || "—";
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
