/*
 * The lesson designer's stage editor (student/designer/editor.html, guide @S4-AI; picture image18).
 *
 *   <div x-data="stageEditor(JSON.parse(document.getElementById('editor-opts').textContent))">
 *
 * opts: saveUrl, csrf, cleared, title, minutes, fields {key: html}, total, edited, first (the first field key),
 * text {saving, saved, failed, clearFirst, inserted}.
 * The title, the minutes and the fields (x-model; CKEditor via x-rich) are saved 1.5 s after the last change and
 * when the page is left. «Add to the editor» in the AI panel sends «ai-insert» {id, html}: the HTML goes to the
 * field last focused, and the message id is sent with the next save (logged as the student's decision).
 * Below: the trial page's answer window (openTurn).
 */
document.addEventListener("alpine:init", () => {
  window.Alpine.data("stageEditor", (opts) => ({
    title: opts.title,
    minutes: opts.minutes,
    fields: opts.fields,
    cleared: opts.cleared,
    total: opts.total,
    edited: opts.edited,
    active: opts.first,
    state: "saved", // saved | dirty | saving | failed
    changed: false, // edited on this page (section 6: the AI check is out of date)
    inserted: null,
    notice: "",
    timer: null,
    noticeTimer: null,

    init() {
      if (!this.cleared) return;
      this.$watch("fields", () => this.queue());
      this.$watch("title", () => this.queue());
      this.$watch("minutes", () => this.queue());
      window.addEventListener("pagehide", () => {
        if (this.state === "dirty") this.save(true);
      });
    },

    queue() {
      this.state = "dirty";
      if (!this.changed) window.dispatchEvent(new CustomEvent("stage-changed"));
      this.changed = true;
      clearTimeout(this.timer);
      this.timer = setTimeout(() => this.save(), 1500);
    },

    async save(leaving = false) {
      clearTimeout(this.timer);
      this.state = "saving";
      const inserted = this.inserted;
      try {
        const response = await fetch(opts.saveUrl, {
          method: "POST",
          keepalive: leaving,
          headers: { "Content-Type": "application/json", "X-CSRFToken": opts.csrf },
          body: JSON.stringify({ title: this.title, minutes: this.minutes, fields: this.fields, inserted }),
        });
        if (!response.ok) throw new Error(String(response.status));
        const data = await response.json();
        if (this.inserted === inserted) this.inserted = null;
        this.total = data.minutes_total;
        this.edited = data.edited;
        if (this.state === "saving") this.state = "saved";
      } catch {
        this.state = "failed";
      }
    },

    get stateText() {
      return { saved: opts.text.saved, dirty: opts.text.saving, saving: opts.text.saving, failed: opts.text.failed }[
        this.state
      ];
    },

    insert(detail) {
      if (!this.cleared) {
        this.say(opts.text.clearFirst);
        return;
      }
      const box = this.$root.querySelector(`[data-field="${this.active}"]`);
      if (!box) return;
      box.querySelector("textarea").dispatchEvent(new CustomEvent("rich-insert", { detail: detail.html }));
      box.scrollIntoView({ behavior: "smooth", block: "center" });
      this.inserted = detail.id;
      this.say(opts.text.inserted);
      this.queue();
    },

    say(text) {
      this.notice = text;
      clearTimeout(this.noticeTimer);
      this.noticeTimer = setTimeout(() => (this.notice = ""), 3500);
    },
  }));
});

// The window «See the AI student's answer» (student/designer/trial.html): opened with a waiting state before the
// HTMX request; closing it after a new answer reloads the page so the stage list shows the answer.
window.openTurn = () => {
  const dialog = document.getElementById("turn-dialog");
  document.getElementById("turn-body").innerHTML = document.getElementById("turn-loading").innerHTML;
  if (!dialog.open) dialog.showModal();
};
document.addEventListener("DOMContentLoaded", () => {
  const dialog = document.getElementById("turn-dialog");
  dialog?.addEventListener("close", () => {
    if (document.querySelector("#turn-body [data-fresh]")) window.location.reload();
  });
});

// The microlesson's 10-minute timer (student/micro/dialog.html): it stands while the AI student answers (that time
// is not counted on the server either), takes the time left from each answer and finishes the trial at 0:00.
document.addEventListener("alpine:init", () => {
  window.Alpine.data("microTimer", (opts) => ({
    left: opts.left,
    total: opts.total,
    waiting: false,
    init() {
      this.timer = setInterval(() => {
        if (this.waiting || this.left <= 0) return;
        this.left -= 1;
        if (this.left === 0) this.$refs.finish.requestSubmit();
      }, 1000);
    },
    sync() {
      const box = document.getElementById("dialog");
      if (box && box.dataset.left) this.left = Number(box.dataset.left);
      if (box) box.scrollTop = box.scrollHeight;
    },
    get clock() {
      const m = Math.floor(this.left / 60);
      return `${m}:${String(this.left % 60).padStart(2, "0")}`;
    },
    get elapsed() {
      return this.total - this.left;
    },
    get stage() {
      const e = this.elapsed;
      return e < 120 ? 1 : e < 300 ? 2 : e < 480 ? 3 : 4;
    },
  }));
});
