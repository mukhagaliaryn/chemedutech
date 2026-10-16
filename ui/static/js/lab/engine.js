/*
 * ChemEduTech virtual lab runner.
 *
 * Generic part of every experiment: step order, equipment placement
 * (pointer drag & drop + buttons), warnings, the message feed, the lab
 * journal, finishing, the analysis task and the research event log.
 *
 * Experiment-specific behaviour lives in a "scene" registered with
 *   ChemLab.scene("hydrogen", (runner) => ({ ...state, onPlace, actions, tick }))
 * Scene methods are called as runner.sc.method(), so `this` inside them is the
 * reactive scene object; `runner` gives access to the runner API.
 */
(function () {
  "use strict";

  const scenes = {};
  window.ChemLab = {
    scene(key, factory) {
      scenes[key] = factory;
    },
    /** Exponential approach to a limit: V(t) = Vmax·(1 − e^(−k·t)). */
    approach(vmax, k, t) {
      return vmax * (1 - Math.exp(-k * t));
    },
    /** SVG polyline points for a series of {t, v} within a w×h box. */
    points(series, tmax, vmax, w, h) {
      return series
        .map((p) => `${((p.t / tmax) * w).toFixed(1)},${(h - (p.v / vmax) * h).toFixed(1)}`)
        .join(" ");
    },
    fmt(n, digits = 1) {
      return Number(n).toFixed(digits).replace(/\.0+$/, "");
    },
  };

  function csrfToken() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  async function postJSON(url, data, opts = {}) {
    const res = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      keepalive: !!opts.keepalive,
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  function fill(template, vars) {
    return template.replace(/%\((\w+)\)s/g, (_, k) => vars[k] ?? "");
  }

  document.addEventListener("alpine:init", () => {
    window.Alpine.data("labRunner", (config) => ({
      cfg: config,
      exp: config.experiment,
      ui: config.ui,
      placed: [],
      done: [],
      current: 0,
      busy: false,
      choiceOpen: false,
      messages: [],
      journal: {},
      journalSaved: false,
      journalError: "",
      analysisOpen: false,
      analysis: {},
      analysisResult: null,
      summary: null,
      finished: false,
      drag: null, // {key, x, y, over}
      startedAt: performance.now(),
      elapsed: 0,
      queue: [],
      seq: 0,
      netError: false,
      sc: {},
      reduceMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,

      init() {
        const factory = scenes[this.exp.scene];
        this.sc = factory ? factory(this) : {};
        this.exp.journal.forEach((f) => (this.journal[f.key] = ""));
        this.exp.questions.forEach((q) => (this.analysis[q.key] = ""));
        this.log("start", "", { lang: document.documentElement.lang });

        let last = performance.now();
        const loop = (now) => {
          const dt = Math.min(0.1, (now - last) / 1000);
          last = now;
          this.elapsed = Math.floor((now - this.startedAt) / 1000);
          if (this.sc.tick) this.sc.tick(dt);
          requestAnimationFrame(loop);
        };
        requestAnimationFrame(loop);

        setInterval(() => this.flush(), 5000);
        window.addEventListener("pagehide", () => this.flush(true));
      },

      // ---------- helpers used by templates ----------
      get step() {
        return this.exp.steps[this.current] || null;
      },
      has(key) {
        return this.placed.includes(key);
      },
      isDone(key) {
        return this.done.includes(key);
      },
      item(key) {
        return this.exp.items.find((i) => i.key === key);
      },
      stepState(i) {
        if (this.done.includes(this.exp.steps[i].key)) return "done";
        if (i === this.current) return this.busy ? "running" : "current";
        return "locked";
      },
      get clock() {
        const m = Math.floor(this.elapsed / 60);
        const s = this.elapsed % 60;
        return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
      },
      get itemGroups() {
        const groups = [
          { label: this.ui.glass, kinds: ["glass"] },
          { label: this.ui.devices, kinds: ["device"] },
          { label: this.ui.reagents, kinds: ["reagent"] },
        ];
        return groups
          .map((g) => ({ ...g, items: this.exp.items.filter((i) => g.kinds.includes(i.kind)) }))
          .filter((g) => g.items.length);
      },
      fmt(n, d = 1) {
        return window.ChemLab.fmt(n, d);
      },

      // ---------- messages & research log ----------
      say(kind, text) {
        if (!text) return;
        this.messages.unshift({ id: this.seq + "-" + Math.random(), kind, text, at: this.clock });
        this.messages = this.messages.slice(0, 40);
      },
      log(type, step = "", payload = {}) {
        this.seq += 1;
        this.queue.push({
          seq: this.seq,
          t: Math.round(performance.now() - this.startedAt),
          type,
          step,
          payload,
        });
      },
      async flush(keepalive = false) {
        if (!this.queue.length) return;
        const batch = this.queue.slice();
        try {
          await postJSON(this.cfg.urls.events, { events: batch }, { keepalive });
          this.queue = this.queue.filter((e) => !batch.includes(e));
          this.netError = false;
        } catch (e) {
          this.netError = true;
        }
      },

      // ---------- step logic ----------
      stepForItem(key) {
        return this.exp.steps.findIndex((s) => s.items.includes(key));
      },
      warnEarly(step) {
        const text = step.early_warning || fill(this.ui.order_error, { step: this.step ? this.step.command : "" });
        if (step.safety) {
          this.say("safety", text);
          this.log("safety_warning", step.key, { current: this.step && this.step.key });
        } else {
          this.say("error", text);
          this.log("order_error", step.key, { current: this.step && this.step.key });
        }
      },
      complete(step) {
        if (this.done.includes(step.key)) return;
        this.done.push(step.key);
        this.log("step_done", step.key);
        if (step.kind !== "journal" && step.kind !== "finish") this.say("observation", step.result);
        if (this.sc.onStepDone) this.sc.onStepDone(step.key);
        this.current = Math.min(this.current + 1, this.exp.steps.length);
        this.choiceOpen = this.step && this.step.kind === "choice" ? false : this.choiceOpen;
      },

      /** Item dropped on the bench or added with the button. */
      place(key, target = "bench") {
        const item = this.item(key);
        if (!item || this.finished) return;
        if (!item.required) {
          this.say("error", item.note || this.ui.not_needed);
          this.log("wrong_item", this.step ? this.step.key : "", { item: key, target });
          return;
        }
        if (this.has(key)) {
          this.say("info", this.ui.already_on_bench);
          return;
        }
        const idx = this.stepForItem(key);
        const step = this.exp.steps[idx];
        if (!step) return;
        if (idx !== this.current || this.busy) {
          this.warnEarly(step);
          return;
        }
        if (this.sc.validateDrop) {
          const problem = this.sc.validateDrop(key, target);
          if (problem) {
            this.say("error", problem);
            this.log("wrong_item", step.key, { item: key, target, reason: "target" });
            return;
          }
        }
        this.placed.push(key);
        this.log("item_placed", step.key, { item: key, target });
        if (this.sc.onPlace) this.sc.onPlace(key, target);
        if (step.items.every((k) => this.has(k))) this.execute(step, { via: "drop" });
      },

      /** Command button pressed. */
      command(i) {
        const step = this.exp.steps[i];
        if (!step || this.finished) return;
        this.log("command", step.key);
        if (this.done.includes(step.key)) {
          this.say("info", this.ui.already_done);
          return;
        }
        if (i !== this.current || this.busy) {
          this.warnEarly(step);
          return;
        }
        if (step.kind === "choice") {
          this.choiceOpen = true;
          return;
        }
        if (step.kind === "journal") {
          this.openJournal();
          return;
        }
        if (step.kind === "finish") {
          this.finish();
          return;
        }
        // place every missing item of this step through the same path as drag & drop
        for (const k of step.items) {
          if (!this.has(k)) {
            this.placed.push(k);
            this.log("item_placed", step.key, { item: k, target: "button" });
            if (this.sc.onPlace) this.sc.onPlace(k, "button");
          }
        }
        this.execute(step, { via: "button" });
      },

      execute(step) {
        const action = this.sc.actions && this.sc.actions[step.key];
        if (step.kind === "process") {
          this.busy = true;
          if (action) action.call(this.sc);
          else this.processDone();
          return;
        }
        if (action) action.call(this.sc);
        this.complete(step);
      },

      /** Called by a scene when a timed process is over. */
      processDone() {
        if (!this.busy) return;
        this.busy = false;
        this.complete(this.step);
      },

      choose(option) {
        const step = this.step;
        if (!step || step.kind !== "choice") return;
        if (!option.correct) {
          this.say("error", option.feedback);
          this.log("wrong_choice", step.key, { option: option.key });
          return;
        }
        this.log("command", step.key, { option: option.key });
        const action = this.sc.actions && this.sc.actions[step.key];
        if (action) action.call(this.sc, option);
        this.choiceOpen = false;
        this.say("info", option.feedback);
        this.complete(step);
      },

      hint() {
        const step = this.step;
        if (!step) return;
        const text = step.hint || fill(this.ui.order_error, { step: step.command }).replace(/^[^.]*\.\s*/, "");
        this.say("info", text);
        this.log("hint", step.key);
      },

      // ---------- journal ----------
      get journalStep() {
        return this.exp.steps.find((s) => s.kind === "journal");
      },
      get journalOpen() {
        const s = this.journalStep;
        return !!s && (this.done.includes(s.key) || (this.step && this.step.key === s.key && !this.busy));
      },
      openJournal() {
        const el = document.getElementById("lab-journal");
        if (el) {
          el.scrollIntoView({ behavior: this.reduceMotion ? "auto" : "smooth", block: "nearest" });
          const first = el.querySelector("input, select, textarea");
          if (first) first.focus({ preventScroll: true });
        }
      },
      async saveJournal() {
        const missing = this.exp.journal.filter((f) => f.required && String(this.journal[f.key]).trim() === "");
        if (missing.length) {
          this.journalError = this.ui.journal_required;
          return;
        }
        this.journalError = "";
        try {
          await postJSON(this.cfg.urls.journal, this.journal);
        } catch (e) {
          this.journalError = this.ui.network_error;
          return;
        }
        this.journalSaved = true;
        this.log("journal_saved", this.journalStep.key);
        this.say("info", this.ui.journal_saved);
        if (this.step && this.step.key === this.journalStep.key) this.complete(this.step);
      },

      // ---------- finish & analysis ----------
      async finish() {
        const step = this.step;
        this.log("finish", step.key);
        const events = this.queue.slice();
        try {
          this.summary = await postJSON(this.cfg.urls.finish, { events });
          this.queue = this.queue.filter((e) => !events.includes(e));
        } catch (e) {
          this.say("error", this.ui.network_error);
          return;
        }
        this.complete(step);
        this.finished = true;
        this.analysisOpen = true;
      },
      async submitAnalysis() {
        try {
          this.analysisResult = await postJSON(this.cfg.urls.analysis, this.analysis);
        } catch (e) {
          this.say("error", this.ui.network_error);
        }
      },
      restart() {
        if (!window.confirm(this.ui.restart_confirm)) return;
        this.log("restart", this.step ? this.step.key : "");
        this.flush(true).finally(() => window.location.assign(this.cfg.urls.restart));
      },
      formatDuration(s) {
        if (s == null) return "—";
        const m = Math.floor(s / 60);
        return m ? `${m} ${this.ui.min} ${s % 60} ${this.ui.s}` : `${s} ${this.ui.s}`;
      },

      // ---------- pointer drag & drop (mouse, pen and touch) ----------
      startDrag(ev, key) {
        if (this.finished) return;
        if (ev.button !== undefined && ev.button !== 0) return;
        ev.preventDefault();
        this.drag = { key, x: ev.clientX, y: ev.clientY, over: null, moved: false, sx: ev.clientX, sy: ev.clientY };
        const move = (e) => {
          if (!this.drag) return;
          this.drag.x = e.clientX;
          this.drag.y = e.clientY;
          if (Math.hypot(e.clientX - this.drag.sx, e.clientY - this.drag.sy) > 6) this.drag.moved = true;
          this.drag.over = this.dropTargetAt(e.clientX, e.clientY);
        };
        const up = (e) => {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", up);
          window.removeEventListener("pointercancel", up);
          const d = this.drag;
          this.drag = null;
          if (!d || !d.moved) return;
          const target = this.dropTargetAt(e.clientX, e.clientY);
          if (target) this.place(d.key, target);
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
        window.addEventListener("pointercancel", up);
      },
      dropTargetAt(x, y) {
        const el = document.elementFromPoint(x, y);
        if (!el) return null;
        const zone = el.closest("[data-drop]");
        return zone ? zone.dataset.drop : null;
      },
    }));
  });
})();
