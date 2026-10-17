// Stage player (ui/templates/student/stage.html): time on the stage and video watching.
(() => {
  const csrf = () => {
    try {
      return JSON.parse(document.body.getAttribute("hx-headers") || "{}")["X-CSRFToken"] || "";
    } catch {
      return "";
    }
  };
  const post = (url, data) =>
    fetch(url, {
      method: "POST",
      keepalive: true,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(data || {}),
    });

  document.addEventListener("alpine:init", () => {
    // Theory: how much of the text has scrolled past the bottom of the screen (header progress bar).
    Alpine.data("readProgress", () => ({
      percent: 0,
      init() {
        const text = document.querySelector("[data-reading]");
        if (!text) return;
        const update = () => {
          const box = text.getBoundingClientRect();
          const seen = window.innerHeight - box.top;
          this.percent = Math.max(0, Math.min(100, Math.round((seen / box.height) * 100)));
        };
        update();
        window.addEventListener("scroll", update, { passive: true });
        window.addEventListener("resize", update);
      },
    }));

    // Theory: «On this page» — the h2 headings of the text, the one being read is highlighted.
    Alpine.data("tocNav", () => ({
      items: [],
      active: "",
      init() {
        const headings = [...document.querySelectorAll("[data-reading] h2")];
        headings.forEach((h, i) => {
          if (!h.id) h.id = `section-${i + 1}`;
          h.classList.add("scroll-mt-24");
        });
        this.items = headings.map((h) => ({ id: h.id, text: h.textContent.trim() }));
        if (!headings.length) return;
        this.active = headings[0].id;
        const observer = new IntersectionObserver(
          (entries) => entries.forEach((e) => e.isIntersecting && (this.active = e.target.id)),
          { rootMargin: "-80px 0px -65% 0px" },
        );
        headings.forEach((h) => observer.observe(h));
      },
    }));

    // A beat every 30 s while the page is visible → StageProgress.time_spent_s.
    Alpine.data("stagePing", (url) => ({
      init() {
        this.timer = setInterval(() => {
          if (document.visibilityState === "visible") post(url).catch(() => {});
        }, 30000);
      },
      destroy() {
        clearInterval(this.timer);
      },
    }));

    // Formula / equation input with the chemistry keyboard and a live preview (H2O2 → H₂O₂).
    Alpine.data("chemInput", () => ({
      value: "",
      insert(ch) {
        const input = this.$refs.input;
        const start = input.selectionStart ?? input.value.length;
        const end = input.selectionEnd ?? input.value.length;
        input.setRangeText(ch, start, end, "end");
        this.value = input.value;
        input.focus();
      },
      // Same charge rules as apps/assessments/chem.py: one digit is the charge of a one-element ion
      // (Zn2+) or after "]", a count in a polyatomic ion (NH4+); with two digits the last is the charge.
      get preview() {
        const sub = (d) => [...d].map((c) => "₀₁₂₃₄₅₆₇₈₉"[c]).join("");
        const sup = (d) => [...d].map((c) => "⁰¹²³⁴⁵⁶⁷⁸⁹"[c]).join("");
        const token = (t) => {
          let body = t, charge = "";
          const m = t.match(/^(.*?)(\^?)(\d*)([+-]+)$/);
          if (m && m[1]) {
            let [, b, caret, digits, signs] = m;
            if (caret) {
              // explicit: SO4^2- → the digits are the charge
            } else if (digits.length >= 2) [b, digits] = [b + digits.slice(0, -1), digits.slice(-1)];
            else if (digits.length === 1 && !(/^[A-Z][a-z]?$/.test(b) || b.endsWith("]"))) [b, digits] = [b + digits, ""];
            body = b;
            charge = sup(digits) + signs.replace(/\+/g, "⁺").replace(/-/g, "⁻");
          }
          return body.replace(/([A-Za-z)\]])(\d+)/g, (_, a, d) => a + sub(d)) + charge;
        };
        return this.value
          .replace(/<=>|<->/g, " ⇌ ")
          .replace(/->|=>/g, " → ")
          .split(/(\s+)/)
          .map((part) => (/^\s+$/.test(part) || part === "+" || /^[→⇌=]$/.test(part) ? part : token(part)))
          .join("")
          .replace(/\s{2,}/g, " ")
          .trim();
      },
    }));

    // Counts the seconds actually played (a jump forward is not counted) and reports the percentage.
    Alpine.data("videoTracker", (opts) => ({
      percent: opts.start || 0,
      done: opts.done,
      seen: new Set(),
      last: null,
      duration: 0,
      sent: opts.start || 0,

      init() {
        if (opts.provider === "file") this.bindFile();
        else if (opts.provider === "vimeo") this.bindVimeo();
        else this.bindYouTube();
        this.timer = setInterval(() => this.report(), 10000);
        window.addEventListener("pagehide", () => this.report());
      },
      destroy() {
        clearInterval(this.timer);
        clearInterval(this.poll);
      },
      tick(t, duration) {
        if (duration > 0) this.duration = duration;
        if (this.last !== null && t >= this.last && t - this.last < 2.5) {
          for (let s = Math.floor(this.last); s <= Math.floor(t); s++) this.seen.add(s);
        }
        this.last = t;
        if (this.duration) {
          const p = Math.min(100, Math.round((this.seen.size / Math.ceil(this.duration)) * 100));
          if (p > this.percent) this.percent = p;
        }
      },
      report() {
        if (this.done || this.percent <= this.sent) return;
        this.sent = this.percent;
        post(opts.url, { percent: this.percent })
          .then((r) => (r.ok ? r.json() : null))
          .then((data) => {
            if (data && data.done) this.done = true;
          })
          .catch(() => (this.sent = 0));
        if (this.percent >= opts.min) this.done = true;
      },
      bindFile() {
        const v = this.$refs.video;
        v.addEventListener("timeupdate", () => this.tick(v.currentTime, v.duration));
        v.addEventListener("seeking", () => (this.last = null));
        v.addEventListener("ended", () => this.report());
      },
      bindVimeo() {
        const frame = this.$refs.vimeo;
        const send = (method, value) => frame.contentWindow.postMessage({ method, value }, "https://player.vimeo.com");
        window.addEventListener("message", (e) => {
          if (e.origin !== "https://player.vimeo.com") return;
          let msg = e.data;
          if (typeof msg === "string") {
            try {
              msg = JSON.parse(msg);
            } catch {
              return;
            }
          }
          if (msg.event === "ready") {
            send("addEventListener", "timeupdate");
            send("addEventListener", "seeked");
            send("addEventListener", "ended");
          } else if (msg.event === "timeupdate") this.tick(msg.data.seconds, msg.data.duration);
          else if (msg.event === "seeked") this.last = null;
          else if (msg.event === "ended") this.report();
        });
      },
      bindYouTube() {
        const start = () => {
          const player = new YT.Player(this.$refs.youtube, {
            videoId: opts.id,
            playerVars: { rel: 0, modestbranding: 1 },
            events: {
              onStateChange: (e) => {
                clearInterval(this.poll);
                if (e.data === YT.PlayerState.PLAYING) {
                  this.poll = setInterval(() => this.tick(player.getCurrentTime(), player.getDuration()), 1000);
                } else {
                  this.last = null;
                  if (e.data === YT.PlayerState.ENDED) this.report();
                }
              },
            },
          });
        };
        if (window.YT && window.YT.Player) return start();
        const previous = window.onYouTubeIframeAPIReady;
        window.onYouTubeIframeAPIReady = () => {
          if (previous) previous();
          start();
        };
        if (!document.querySelector('script[src="https://www.youtube.com/iframe_api"]')) {
          const tag = document.createElement("script");
          tag.src = "https://www.youtube.com/iframe_api";
          document.head.appendChild(tag);
        }
      },
    }));
  });
})();
