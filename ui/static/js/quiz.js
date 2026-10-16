// Quiz player (ui/templates/assessments/take.html): one question at a time, answered marks, countdown.
// Without JavaScript every question is shown on one page and the form still submits.
document.addEventListener("alpine:init", () => {
  Alpine.data("quizPlayer", (opts) => ({
    current: 0,
    total: opts.total,
    answered: Array(opts.total).fill(false),
    deadline: opts.deadline ? new Date(opts.deadline).getTime() : null,
    left: null,
    submitting: false,

    init() {
      if (this.deadline) {
        this.tick();
        this.timer = setInterval(() => this.tick(), 1000);
      }
    },
    tick() {
      this.left = Math.max(0, Math.round((this.deadline - Date.now()) / 1000));
      if (this.left === 0 && !this.submitting) {
        clearInterval(this.timer);
        this.submitting = true;
        this.$refs.form.submit();
      }
    },
    get clock() {
      if (this.left === null) return "";
      const m = Math.floor(this.left / 60);
      const s = String(this.left % 60).padStart(2, "0");
      return `${m}:${s}`;
    },
    get unanswered() {
      return this.answered.filter((a) => !a).length;
    },
    mark(i, event) {
      const box = event.currentTarget;
      const filled = [...box.querySelectorAll("input")].some((el) =>
        el.type === "radio" || el.type === "checkbox" ? el.checked : el.value.trim() !== "",
      );
      this.answered[i] = filled;
    },
    go(i) {
      this.current = Math.min(Math.max(i, 0), this.total - 1);
      this.$nextTick(() => this.$refs.top?.scrollIntoView({ block: "nearest" }));
    },
  }));
});
