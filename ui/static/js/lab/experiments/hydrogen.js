/* Experiment 1 — obtaining and collecting hydrogen: Zn + 2HCl → ZnCl₂ + H₂↑ */
ChemLab.scene("hydrogen", (r) => {
  const p = r.exp.params;
  const CYL_TOP = 106; // inner top of the inverted cylinder (0 mL)
  const CYL_PX = 280; // pixels for the full scale (cylinder_ml)

  const bubbles = (n, x0, spread, seed) =>
    Array.from({ length: n }, (_, i) => ({
      id: seed + i,
      x: x0 + ((i * 37) % spread) - spread / 2,
      r: 2 + ((i * 7) % 4),
      dur: 1.1 + ((i * 13) % 9) / 10,
      delay: ((i * 29) % 17) / 10,
    }));

  return {
    acidLevel: 0,
    reacting: false,
    collecting: false,
    started: false,
    pouring: false,
    popTest: false,
    revealEquation: false,
    t: 0,
    V: 0,
    granules: [
      { id: 1, x: 205, r: 7, c: "#8b949c" },
      { id: 2, x: 224, r: 8.5, c: "#9aa3ab" },
      { id: 3, x: 246, r: 6.5, c: "#7d8790" },
      { id: 4, x: 262, r: 7.5, c: "#a6aeb5" },
      { id: 5, x: 186, r: 6, c: "#909aa2" },
    ],
    flaskBubbles: bubbles(12, 228, 90, 0),
    cylBubbles: bubbles(6, 645, 30, 100),

    znScale() {
      return 1 - 0.75 * (this.V / p.v_max_ml);
    },
    markY(ml) {
      return CYL_TOP + (ml / p.cylinder_ml) * CYL_PX;
    },
    gasHeight() {
      return (this.V / p.cylinder_ml) * CYL_PX;
    },

    actions: {
      add_acid() {
        this.pouring = true;
        setTimeout(() => (this.pouring = false), 1400);
        const target = 64;
        const fill = () => {
          this.acidLevel = Math.min(target, this.acidLevel + 3);
          if (this.acidLevel < target) setTimeout(fill, 30);
          else this.reacting = true;
        };
        setTimeout(fill, 500);
      },
      collect() {
        this.collecting = true;
        this.started = true;
      },
      observe() {
        this.revealEquation = true;
        this.popTest = true;
        r.say("observation", r.ui.purity_test);
        setTimeout(() => (this.popTest = false), 2600);
      },
    },

    tick(dt) {
      if (!this.collecting) return;
      this.t += dt;
      this.V = ChemLab.approach(p.v_max_ml, p.k_per_s, this.t);
      if (this.V >= 0.985 * p.v_max_ml) {
        this.V = p.v_max_ml;
        this.collecting = false;
        this.reacting = false;
        r.processDone();
      }
    },
  };
});
