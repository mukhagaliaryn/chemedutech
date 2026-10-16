/* Experiment 3 — electrolysis of water: 2H₂O → 2H₂↑ + O₂↑ (NaOH electrolyte) */
ChemLab.scene("electrolysis", (r) => {
  const p = r.exp.params;
  const TOP = 80; // 0 mL mark
  const PX = 280; // px for tube_ml
  const H2_ML_PER_S = (p.current_a / (2 * p.faraday)) * p.vm_ml; // ≈ 0.058 mL/s
  const T_END = p.minutes * 60;

  return {
    filled: false,
    electrolyte: "",
    connected: false,
    started: false,
    running: false,
    compared: false,
    revealEquation: false,
    t: 0,
    vH: 0,
    vO: 0,
    dataH: [{ t: 0, v: 0 }],
    dataO: [{ t: 0, v: 0 }],

    liquidColor() {
      return "#d4ebf4";
    },
    markY(ml) {
      return TOP + (ml / p.tube_ml) * PX;
    },
    gasPx(ml) {
      return (ml / p.tube_ml) * PX;
    },
    reservoirDrop() {
      return 0; // displaced liquid rises into the bulb; kept static for clarity
    },
    get chart() {
      return {
        tmax: p.minutes,
        xdiv: 5,
        vmax: 40,
        ref: null,
        series: [
          { label: "H<sub>2</sub> (" + r.ui.cathode + ")", color: "#1d2f4b", data: this.dataH },
          { label: "O<sub>2</sub> (" + r.ui.anode + ")", color: "#b0124f", data: this.dataO },
        ],
      };
    },

    actions: {
      electrolyte(option) {
        this.electrolyte = option.key;
        this.filled = true;
      },
      connect() {
        this.connected = true;
      },
      power_on() {
        this.started = true;
      },
      run_time() {
        this.running = true;
      },
      compare() {
        this.compared = true;
        this.revealEquation = true;
      },
    },

    tick(dt) {
      if (!this.running) return;
      this.t = Math.min(T_END, this.t + dt * p.time_scale);
      this.vH = H2_ML_PER_S * this.t;
      this.vO = this.vH / 2;
      const last = this.dataH[this.dataH.length - 1];
      if (this.t / 60 - last.t >= 0.1 || this.t >= T_END) {
        this.dataH.push({ t: this.t / 60, v: this.vH });
        this.dataO.push({ t: this.t / 60, v: this.vO });
      }
      if (this.t >= T_END) {
        this.running = false;
        r.processDone();
      }
    },
  };
});
