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
