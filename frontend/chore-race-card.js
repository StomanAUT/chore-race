/**
 * Chore Race card animation prototype.
 *
 * Experimental: this file is not registered as a Home Assistant resource by
 * the integration. It only consumes the read-only v0.1 WebSocket API.
 */
(() => {
  const DEMO_DATA = {
    state: {
      open_tasks_today: 5,
      completed_tasks_today: 7,
      team_progress: { completed: 7, total: 12 },
    },
    leaderboard: [
      { participant_id: "demo-lina", name: "Lina", points: 8 },
      { participant_id: "demo-noah", name: "Noah", points: 6 },
      { participant_id: "demo-sam", name: "Sam", points: 3 },
    ],
  };

  const escapeHtml = (value) =>
    String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  class ChoreRaceCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._config = {};
      this._hass = undefined;
      this._data = DEMO_DATA;
      this._connected = false;
      this._requestGeneration = 0;
      this._refreshTimer = undefined;
      this._motionQuery = undefined;
      this._onMotionChange = () => this._render();
      this._onVisibilityChange = () => {
        if (!document.hidden) this._load();
      };
    }

    static getStubConfig() {
      return { title: "Chore Race", target_points: 10 };
    }

    setConfig(config) {
      if (config && typeof config !== "object") {
        throw new Error("Chore Race card configuration must be an object");
      }
      this._config = { ...config };
      this._restartRefreshTimer();
      this._render();
    }

    set hass(hass) {
      const firstConnection = !this._hass && hass;
      this._hass = hass;
      if (firstConnection && this._connected) this._load();
    }

    getCardSize() {
      return Math.max(3, (this._data?.leaderboard?.length ?? 0) + 2);
    }

    connectedCallback() {
      if (this._connected) return;
      this._connected = true;
      this._motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
      this._motionQuery.addEventListener?.("change", this._onMotionChange);
      document.addEventListener("visibilitychange", this._onVisibilityChange);
      this._restartRefreshTimer();
      this._render();
      if (this._hass) this._load();
    }

    disconnectedCallback() {
      this._connected = false;
      this._requestGeneration += 1;
      clearInterval(this._refreshTimer);
      this._refreshTimer = undefined;
      this._motionQuery?.removeEventListener?.("change", this._onMotionChange);
      document.removeEventListener("visibilitychange", this._onVisibilityChange);
    }

    _restartRefreshTimer() {
      clearInterval(this._refreshTimer);
      this._refreshTimer = undefined;
      if (!this._connected || !this._hass) return;
      const seconds = clamp(Number(this._config.refresh_interval ?? 30), 10, 300);
      this._refreshTimer = setInterval(() => {
        if (!document.hidden) this._load();
      }, seconds * 1000);
    }

    async _load() {
      if (!this._connected || !this._hass?.callWS) return;
      const generation = ++this._requestGeneration;
      try {
        const [state, participants, leaderboard] = await Promise.all([
          this._hass.callWS({ type: "chore_race/get_state" }),
          this._hass.callWS({ type: "chore_race/get_participants" }),
          this._hass.callWS({ type: "chore_race/get_leaderboard" }),
        ]);
        if (!this._connected || generation !== this._requestGeneration) return;
        const participantById = Object.fromEntries(
          participants.map((participant) => [participant.id, participant]),
        );
        this._data = {
          state,
          leaderboard: leaderboard.map((entry) => ({
            ...entry,
            avatar: participantById[entry.participant_id]?.avatar,
          })),
        };
        this._error = undefined;
      } catch (error) {
        if (!this._connected || generation !== this._requestGeneration) return;
        this._error = error instanceof Error ? error.message : String(error);
      }
      this._render();
    }

    _render() {
      if (!this.shadowRoot) return;
      const state = this._data?.state ?? DEMO_DATA.state;
      const racers = this._data?.leaderboard ?? [];
      const completed = Number(state.team_progress?.completed ?? 0);
      const total = Number(state.team_progress?.total ?? 0);
      const teamProgress = total > 0 ? clamp((completed / total) * 100, 0, 100) : 0;
      const highestScore = Math.max(0, ...racers.map((entry) => Number(entry.points) || 0));
      const configuredTarget = Number(this._config.target_points);
      const target = configuredTarget > 0 ? configuredTarget : Math.max(10, highestScore);
      const reducedMotion =
        this._config.force_reduced_motion === true || this._motionQuery?.matches;
      const title = escapeHtml(this._config.title ?? "Chore Race");

      const lanes = racers.length
        ? racers
            .map((racer, index) => {
              const points = Number(racer.points) || 0;
              const progress = clamp((points / target) * 100, 0, 100);
              const name = escapeHtml(racer.name ?? "Fahrer");
              const initial = escapeHtml(
                (racer.name ?? "?").trim().charAt(0).toUpperCase() || "?",
              );
              const avatar = racer.avatar
                ? `<img src="${escapeHtml(racer.avatar)}" alt="" />`
                : `<span aria-hidden="true">${initial}</span>`;
              return `
                <div class="lane" style="--lane: ${index};">
                  <div class="lane-heading">
                    <div class="driver">${avatar}<strong>${name}</strong></div>
                    <span>${points} P</span>
                  </div>
                  <div class="track" role="progressbar"
                    aria-label="${name}: ${points} von ${target} Punkten"
                    aria-valuemin="0" aria-valuemax="${target}"
                    aria-valuenow="${points}">
                    <div class="track-lines"></div>
                    <div class="racer" style="--race-shift: ${progress}%;">
                      <div class="car" aria-hidden="true">
                        <i class="window"></i><i class="wheel one"></i><i class="wheel two"></i>
                      </div>
                    </div>
                    <div class="finish" aria-hidden="true"></div>
                  </div>
                </div>`;
            })
            .join("")
        : `<div class="empty">Noch keine aktiven Teilnehmer.</div>`;

      this.shadowRoot.innerHTML = `
        <style>${this._styles()}</style>
        <ha-card class="${reducedMotion ? "reduced-motion" : ""}">
          <header>
            <div>
              <span class="eyebrow">HEUTE &middot; TEAMMODUS</span>
              <h2>${title}</h2>
            </div>
            <div class="flag" aria-hidden="true"><i></i></div>
          </header>
          <section class="team" aria-label="Teamfortschritt">
            <div class="team-copy">
              <span>Gemeinsam geschafft</span>
              <strong>${completed}<small> / ${total} Aufgaben</small></strong>
            </div>
            <div class="meter" role="progressbar" aria-valuemin="0" aria-valuemax="100"
              aria-valuenow="${Math.round(teamProgress)}">
              <i style="--team-progress: ${teamProgress}%"></i>
            </div>
          </section>
          <section class="lanes">${lanes}</section>
          <footer>
            <span>${state.open_tasks_today ?? 0} Aufgaben offen</span>
            <span class="live"><i></i>${this._hass ? "Live" : "Demo"}</span>
          </footer>
          ${
            this._error
              ? `<p class="error">Letzter Stand &middot; ${escapeHtml(this._error)}</p>`
              : ""
          }
        </ha-card>`;
    }

    _styles() {
      return `
        :host { display: block; --ink: var(--primary-text-color, #172036); }
        * { box-sizing: border-box; }
        ha-card {
          display: block; overflow: hidden; color: var(--ink);
          background:
            radial-gradient(circle at 92% 0%, rgba(105, 92, 255, .2), transparent 28%),
            linear-gradient(
              145deg,
              var(--ha-card-background, #fff),
              color-mix(
                in srgb,
                var(--ha-card-background, #fff) 94%,
                #695cff
              )
            );
          border-radius: var(--ha-card-border-radius, 24px); padding: clamp(18px, 4vw, 28px);
          box-shadow: var(--ha-card-box-shadow, 0 18px 55px rgba(31, 38, 90, .12));
          font-family: var(--paper-font-body1_-_font-family, system-ui, sans-serif);
        }
        header, .team-copy, footer, .lane-heading, .driver { display: flex; align-items: center; }
        header { justify-content: space-between; gap: 16px; }
        .eyebrow { font-size: 11px; letter-spacing: .16em; font-weight: 800; color: #695cff; }
        h2 { margin: 4px 0 0; font-size: clamp(24px, 6vw, 34px); line-height: 1; letter-spacing: -.04em; }
        .flag { position: relative; width: 48px; height: 48px; border-radius: 16px;
          background: rgba(105, 92, 255, .12); transform: rotate(4deg); }
        .flag::before { content: ""; position: absolute; left: 14px; top: 9px;
          width: 3px; height: 31px; border-radius: 3px; background: #695cff; }
        .flag i { position: absolute; left: 17px; top: 10px; width: 22px; height: 17px;
          background: repeating-conic-gradient(#172036 0 25%, #fff 0 50%) 0 / 8px 8px;
          clip-path: polygon(0 0, 100% 0, 82% 50%, 100% 100%, 0 100%); }
        .team { margin: 22px 0 18px; padding: 16px; border: 1px solid rgba(105, 92, 255, .14);
          border-radius: 18px; background: color-mix(in srgb, var(--ha-card-background, #fff) 76%, transparent); }
        .team-copy { justify-content: space-between; gap: 12px; font-size: 13px; }
        .team-copy strong { font-size: 19px; }
        .team-copy small { font-size: 12px; font-weight: 600; opacity: .6; }
        .meter { height: 9px; margin-top: 12px; border-radius: 99px;
          overflow: hidden; background: rgba(105, 92, 255, .12); }
        .meter i { display: block; width: var(--team-progress); height: 100%; border-radius: inherit;
          background: linear-gradient(90deg, #695cff, #24cf9e); transition: width .7s cubic-bezier(.2, .8, .2, 1); }
        .lanes { display: grid; gap: 14px; }
        .lane-heading { justify-content: space-between; margin-bottom: 6px;
          font-size: 12px; font-variant-numeric: tabular-nums; }
        .driver { gap: 8px; }
        .driver > span, .driver > img { width: 24px; height: 24px; border-radius: 50%; object-fit: cover;
          display: grid; place-items: center; background: #695cff; color: white; font-size: 11px; font-weight: 800; }
        .track { position: relative; height: 45px; overflow: hidden; border-radius: 13px;
          background: linear-gradient(180deg, #3b4050, #272b38); box-shadow: inset 0 2px 7px rgba(0,0,0,.28); }
        .track-lines { position: absolute; inset: 21px 12px auto; height: 2px;
          background: repeating-linear-gradient(90deg, rgba(255,255,255,.55) 0 12px, transparent 12px 24px); }
        .finish { position: absolute; right: 9px; inset-block: 0; width: 8px; opacity: .75;
          background: repeating-conic-gradient(#fff 0 25%, #151923 0 50%) 0 / 8px 8px; }
        .racer { position: absolute; z-index: 2; inset: 7px auto auto 5px; width: calc(100% - 61px);
          transform: translateX(var(--race-shift)); transition: transform .85s cubic-bezier(.16, 1, .3, 1); }
        .car { position: relative; width: 50px; height: 25px; border-radius: 9px 13px 7px 7px;
          background: linear-gradient(
            145deg,
            hsl(calc(250 + var(--lane) * 48) 80% 64%),
            hsl(calc(250 + var(--lane) * 48) 72% 48%)
          );
          filter: drop-shadow(0 4px 3px rgba(0,0,0,.3)); }
        .car::before { content: ""; position: absolute; left: 12px; top: -7px; width: 25px; height: 11px;
          border-radius: 10px 11px 0 0; background: inherit; }
        .window { position: absolute; z-index: 1; left: 20px; top: -4px; width: 14px; height: 7px;
          border-radius: 7px 7px 2px 2px; background: #dff7ff; opacity: .9; }
        .wheel { position: absolute; bottom: -4px; width: 9px; height: 9px; border: 2px solid #aeb5c7;
          border-radius: 50%; background: #151923; }
        .wheel.one { left: 8px; } .wheel.two { right: 7px; }
        footer { justify-content: space-between; margin-top: 18px; padding-top: 14px;
          border-top: 1px solid rgba(105, 92, 255, .12); font-size: 12px; opacity: .72; }
        .live { display: flex; gap: 6px; align-items: center; }
        .live i { width: 7px; height: 7px; border-radius: 50%; background: #24cf9e;
          box-shadow: 0 0 0 4px rgba(36,207,158,.13); animation: pulse 1.8s ease-in-out infinite; }
        .error { margin: 10px 0 0; color: var(--error-color, #db4437); font-size: 11px; }
        .empty { padding: 22px; text-align: center; opacity: .6; border: 1px dashed currentColor; border-radius: 14px; }
        @keyframes pulse { 50% { transform: scale(.6); opacity: .55; } }
        .reduced-motion *, .reduced-motion *::before, .reduced-motion *::after {
          animation-duration: .001ms !important; animation-iteration-count: 1 !important;
          scroll-behavior: auto !important; transition-duration: .001ms !important;
        }
        @media (prefers-reduced-motion: reduce) {
          *, *::before, *::after { animation-duration: .001ms !important; animation-iteration-count: 1 !important;
            scroll-behavior: auto !important; transition-duration: .001ms !important; }
        }
        @media (max-width: 420px) {
          ha-card { padding: 16px; border-radius: 20px; }
          .team { margin-top: 18px; } .track { height: 42px; }
        }
      `;
    }
  }

  if (!customElements.get("chore-race-card")) {
    customElements.define("chore-race-card", ChoreRaceCard);
    window.customCards = window.customCards || [];
    window.customCards.push({
      type: "chore-race-card",
      name: "Chore Race (experimental)",
      description: "Animated team race preview using the Chore Race v0.1 API.",
      preview: true,
    });
  }
})();
