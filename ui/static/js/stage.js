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
