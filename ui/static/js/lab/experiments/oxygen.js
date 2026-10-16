/* Experiment 2 — oxygen: 2H₂O₂ → 2H₂O + O₂↑ (MnO₂), run without and with the catalyst */
ChemLab.scene("oxygen", (r) => {
  const p = r.exp.params;
  const TOP = 116; // 0 mL mark of the inverted measuring tube
  const PX = 270; // pixels for collector_ml

  return {
    phase: "idle", // idle → nocat → between → cat → done
    liquid: 0,
    bubbling: 0, // 0 none, 1 single bubbles, 2 intensive
    simT: 0,
    V: 0,
    vAfterNocat: 0,
    rateNocat: 0,
    rateCat: 0,
    showRates: false,
    splint: false,
    flare: false,
    revealEquation: false,

    markY(ml) {
      return TOP + (ml / p.collector_ml) * PX;
    },
    gasHeight() {
      return (this.V / p.collector_ml) * PX;
    },

    onPlace(key) {
      if (key === "h2o2") {
        const fill = () => {
          this.liquid = Math.min(70, this.liquid + 3);
          if (this.liquid < 70) setTimeout(fill, 30);
        };
        fill();
      }
    },

    actions: {
      run_nocat() {
        this.phase = "nocat";
        this.simT = 0;
        this.bubbling = 1;
      },
      run_cat() {
        this.phase = "cat";
        this.simT = 0;
        this.bubbling = 2;
      },
      observe() {
        this.showRates = true;
        this.revealEquation = true;
        this.splint = true;
        setTimeout(() => {
          this.flare = true;
          r.say("observation", r.ui.splint_test);
        }, 900);
      },
    },

    tick(dt) {
      if (this.phase === "nocat") {
        this.simT += dt * p.time_scale;
        this.V = ChemLab.approach(p.v_max_ml, p.k_nocat_per_s, this.simT);
        if (this.simT >= p.nocat_seconds) {
          this.simT = p.nocat_seconds;
          this.vAfterNocat = this.V;
          this.rateNocat = this.V / (p.nocat_seconds / 60);
          this.phase = "between";
          this.bubbling = 1;
          r.processDone();
        }
      } else if (this.phase === "cat") {
        this.simT += dt * p.time_scale;
        const rest = p.v_max_ml - this.vAfterNocat;
        this.V = this.vAfterNocat + ChemLab.approach(rest, p.k_cat_per_s, this.simT);
        if (this.simT >= p.cat_seconds) {
          this.simT = p.cat_seconds;
          this.rateCat = (this.V - this.vAfterNocat) / (p.cat_seconds / 60);
          this.phase = "done";
          this.bubbling = 0;
          r.processDone();
        }
      }
    },
  };
});
