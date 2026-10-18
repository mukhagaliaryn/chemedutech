/*
 * Generic test-tube bench (topics 2–5). The experiment's params describe the tubes and, per step key, what
 * happens in them — so a new test-tube experiment needs no JavaScript:
 *
 *   params = {
 *     rack_item: "rack",                          // the rack appears with this item (optional)
 *     tubes: [{label: "A"}, {label: "B"}],
 *     ops: {
 *       add_ki: [{tube: 0, pour: "#eef6f9", level: 0.3, text: "KI"}],
 *       add_cl2: [{tube: 0, pour: "#e4ef9a", level: 0.45}, {tube: 0, color: "#b5651d", at: 0.8, dur: 2}],
 *       compare: [{reveal: true}],
 *     },
 *   }
 *
 * An op: tube (index), at (s, delay), dur (s) and any of pour (colour) + level/text, color, text,
 * precipitate (colour) + amount, cloud (0–1, white or cloud_color), gel (colour), gas (colour or ""),
 * bubbles (bool), heat (bool), paper (colour or ""), pipe ([from, to]), reveal (the equation strip).
 * A «process» step ends when its last op is over (runner.processDone()).
 */
ChemLab.scene("tubes", (r) => {
  const p = r.exp.params;
  const n = p.tubes.length;
  const spacing = n > 1 ? Math.min(170, 620 / (n - 1)) : 0;
  const TOP = 140; // tube mouth
  const BOTTOM = 392; // where the round bottom starts
  const INNER = 230; // px of a full tube

  const make = (t) => ({
    name: t.label,
    text: t.text || "",
    level: 0,
    target: 0,
    color: t.color || "#e6f2f8",
    fade: 1.2,
    ppt: 0,
    pptTarget: 0,
    pptColor: "#ffffff",
    cloud: 0,
    cloudColor: "#ffffff",
    gel: 0,
    gelColor: "#e9efe3",
    gas: 0,
    gasColor: "#cfe27a",
    bubbles: false,
    heat: false,
    paper: "",
    pouring: false,
  });

  const timers = [];
  const later = (s, fn) => timers.push(setTimeout(fn, s * 1000));

  const scene = {
    tubes: p.tubes.map(make),
    pipes: [],
    revealEquation: false,

    shown() {
      return !p.rack_item || r.has(p.rack_item);
    },
    x(i) {
      return 450 + (i - (n - 1) / 2) * spacing;
    },
    rackX() {
      return this.x(0) - 70;
    },
    rackW() {
      return this.x(n - 1) - this.x(0) + 140;
    },
    inner(i) {
      const x = this.x(i);
      return `M${x - 17},${TOP} V${BOTTOM} a17,17 0 0 0 34,0 V${TOP} Z`;
    },
    outline(i) {
      const x = this.x(i);
      return `M${x - 19},${TOP} V${BOTTOM} a19,19 0 0 0 38,0 V${TOP}`;
    },
    liquidTop(i) {
      return BOTTOM - this.tubes[i].level * INNER;
    },
    liquidH(i) {
      return this.tubes[i].level * INNER + 24;
    },
    pipePath(k) {
      const pipe = this.pipes[k];
      if (!pipe) return "";
      const [a, b] = pipe;
      const xa = this.x(a);
      const xb = this.x(b);
      const dir = xb > xa ? 1 : -1;
      return `M${xa},${TOP + 6} V96 Q${xa},84 ${xa + dir * 12},84 H${xb - dir * 12} Q${xb},84 ${xb},96 V${BOTTOM - 10}`;
    },

    apply(op) {
      const t = op.tube !== undefined ? this.tubes[op.tube] : null;
      if (t) {
        if (op.dur) t.fade = op.dur;
        if (op.pour) {
          t.color = op.pour;
          t.target = op.level ?? Math.min(0.8, t.target + 0.25);
          t.pouring = true;
          later(1.4, () => (t.pouring = false));
        }
        if (op.color) t.color = op.color;
        if (op.text !== undefined) t.text = op.text;
        if (op.precipitate) {
          t.pptColor = op.precipitate;
          t.pptTarget = op.amount ?? 1;
        }
        if (op.cloud !== undefined) {
          t.cloud = op.cloud;
          if (op.cloud_color) t.cloudColor = op.cloud_color;
        }
        if (op.gel) {
          t.gelColor = op.gel;
          t.gel = op.amount ?? 1;
        }
        if (op.gas !== undefined) {
          if (op.gas) t.gasColor = op.gas;
          t.gas = op.gas ? (op.amount ?? 0.55) : 0;
        }
        if (op.bubbles !== undefined) t.bubbles = op.bubbles;
        if (op.heat !== undefined) t.heat = op.heat;
        if (op.paper !== undefined) t.paper = op.paper;
      }
      if (op.pipe) this.pipes.push(op.pipe);
      if (op.reveal) this.revealEquation = true;
    },

    actions: {},

    tick(dt) {
      for (const t of this.tubes) {
        if (t.level !== t.target) {
          const d = t.target - t.level;
          t.level = Math.abs(d) < 0.004 ? t.target : t.level + Math.sign(d) * Math.min(Math.abs(d), dt * 0.35);
        }
        if (t.ppt < t.pptTarget) t.ppt = Math.min(t.pptTarget, t.ppt + dt * 0.4);
      }
    },
  };

  // one action per step key: play its ops; a process step is over when the last op is
  for (const [key, ops] of Object.entries(p.ops || {})) {
    scene.actions[key] = function () {
      let end = 0;
      for (const op of ops) {
        const at = op.at || 0;
        end = Math.max(end, at + (op.dur ?? 1));
        later(at, () => this.apply(op));
      }
      const step = r.exp.steps.find((s) => s.key === key);
      if (step && step.kind === "process") later(end, () => r.processDone());
    };
  }
  return scene;
});
