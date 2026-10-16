/* Experiment 4 — rate of H₂O₂ decomposition: tube A (no catalyst) vs tube B (MnO₂) */
ChemLab.scene("rate", (r) => {
  const p = r.exp.params;
  const SYRINGE_ML = 60;
  const SYRINGE_PX = 100; // px for SYRINGE_ML
  const TUBE_X = { a: 200, b: 350 }; // must match scenes/rate.html

  return {
    liquid: 0,
    started: false,
    running: false,
    showGraph: false,
    revealEquation: false,
    t: 0,
    vA: 0,
    vB: 0,
    dataA: [{ t: 0, v: 0 }],
    dataB: [{ t: 0, v: 0 }],
    table: [],

    syringePx(ml) {
      return (ml / SYRINGE_ML) * SYRINGE_PX;
    },
    /** Geometry of the gas syringe of tube A (pointing left) or B (pointing right). */
    syr(side) {
      const dir = side === "a" ? -1 : 1;
      const start = TUBE_X[side] + dir * 12;
      const len = SYRINGE_PX + 8;
      const v = side === "a" ? this.vA : this.vB;
      const piston = start + dir * this.syringePx(v);
      return {
        barrelX: dir > 0 ? start : start - len,
        barrelW: len,
        gasX: Math.min(start, piston),
        gasW: Math.abs(piston - start),
        piston,
        rodEnd: piston + dir * (len + 6),
        tick: (i) => start + dir * this.syringePx(i * 10),
      };
    },
    get chart() {
      return {
        tmax: p.seconds / 60,
        xdiv: 5,
        vmax: SYRINGE_ML,
        ref: p.v_max_ml,
        series: [
          { label: r.ui.tube_a, color: "#4a5b74", data: this.dataA },
          { label: r.ui.tube_b, color: "#b0124f", data: this.dataB },
        ],
      };
    },

    /** MnO₂ belongs in tube B only. */
    validateDrop(key, target) {
      if (key === "mno2" && target === "tube_a") return r.ui.mno2_only_b;
      return null;
    },
    onPlace(key) {
      if (key === "h2o2") {
        const fill = () => {
          this.liquid = Math.min(80, this.liquid + 3);
          if (this.liquid < 80) setTimeout(fill, 30);
        };
        fill();
      }
    },

    actions: {
      timer() {
        this.started = true;
        this.running = true;
      },
      graph() {
        this.showGraph = true;
        this.revealEquation = true;
      },
    },

    tick(dt) {
      if (!this.running) return;
      this.t = Math.min(p.seconds, this.t + dt * p.time_scale);
      this.vA = ChemLab.approach(p.v_max_ml, p.k_a_per_s, this.t);
      this.vB = ChemLab.approach(p.v_max_ml, p.k_b_per_s, this.t);
      const last = this.dataA[this.dataA.length - 1];
      if (this.t / 60 - last.t >= 0.05 || this.t >= p.seconds) {
        this.dataA.push({ t: this.t / 60, v: this.vA });
        this.dataB.push({ t: this.t / 60, v: this.vB });
      }
      const minute = Math.floor(this.t / 60);
      if (minute >= 1 && !this.table.some((row) => row.min === minute)) {
        this.table.push({ min: minute, a: this.vA, b: this.vB });
      }
      if (this.t >= p.seconds) {
        this.running = false;
        r.processDone();
      }
    },
  };
});
