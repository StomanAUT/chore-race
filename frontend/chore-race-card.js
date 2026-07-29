/**
 * Interactive Chore Race Lovelace card.
 *
 * The card renders the current race and lets authenticated household
 * dashboards complete tasks. Race lifecycle controls remain admin-only.
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
  const assetUrl = (value) =>
    String(value ?? "").replace(
      /^\/chore-race-assets\//,
      "/local/chore-race-icons/",
    );
  const suggestedTaskImage = (name) => {
    const normalized = String(name ?? "").toLocaleLowerCase("de");
    const suggestions = [
      [/geschirrsp|spülmaschine/, "dishwasher.png"],
      [/waschmaschine|wäsche/, "laundry.png"],
      [/staubsaug/, "vacuum.png"],
      [/fenster/, "clean-windows.png"],
      [/\bbett\b/, "make-bed.png"],
      [/koch|essen/, "cooking.png"],
      [/rasen/, "mow-lawn.png"],
      [/tier|fütter|futter/, "feed-pets.png"],
      [/\bwc\b|toilette/, "clean-toilet.png"],
      [/\bbad\b|dusche/, "clean-bathroom.png"],
      [/bio.*müll/, "organic-waste.png"],
      [/rest.*müll|müll/, "general-waste.png"],
      [/papier/, "paper.png"],
      [/plastik/, "plastic.png"],
      [/wisch|boden/, "mop-floor.png"],
      [/staub/, "dust.png"],
      [/aufräum/, "tidy-up.png"],
    ];
    const match = suggestions.find(([pattern]) => pattern.test(normalized));
    return match ? `/local/chore-race-icons/${match[1]}` : undefined;
  };

  const errorMessage = (error) => {
    if (error instanceof Error) return error.message;
    if (typeof error === "string") return error;
    return (
      error?.message ??
      error?.body?.message ??
      error?.code ??
      "Daten konnten noch nicht geladen werden"
    );
  };

  class ChoreRaceCardEditor extends HTMLElement {
    setConfig(config) {
      this._config = { ...config };
      this._render();
    }

    connectedCallback() {
      this._render();
    }

    _render() {
      if (!this.isConnected) return;
      this.innerHTML = `
        <style>
          .editor { display:grid; gap:14px; padding:8px 0; }
          label { display:grid; gap:6px; color:var(--secondary-text-color);
            font-size:12px; font-weight:600; }
          input { min-height:42px; box-sizing:border-box; padding:8px 11px;
            color:var(--primary-text-color); background:var(--card-background-color);
            border:1px solid var(--divider-color); border-radius:10px; font:inherit; }
        </style>
        <div class="editor">
          <label>Maximale Breite (Pixel)
            <input name="max_width" type="number" min="280" max="1400"
              value="${escapeHtml(this._config?.max_width ?? 820)}">
          </label>
          <label>Akzentfarbe
            <input name="accent_color" type="color"
              value="${escapeHtml(this._config?.accent_color ?? "#74829a")}">
          </label>
        </div>`;
      this.querySelectorAll("input").forEach((input) => {
        input.addEventListener("change", () => {
          const config = { ...this._config };
          config[input.name] =
            input.type === "number" ? Number(input.value) : input.value;
          this._config = config;
          this.dispatchEvent(
            new CustomEvent("config-changed", {
              detail: { config },
              bubbles: true,
              composed: true,
            }),
          );
        });
      });
    }
  }

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
      this._countdownTimer = undefined;
      this._motionQuery = undefined;
      this._participants = [];
      this._areas = {};
      this._selectedTaskId = undefined;
      this._actionBusy = false;
      this._actionError = undefined;
      this._onMotionChange = () => this._render();
      this._onVisibilityChange = () => {
        if (!document.hidden) this._load();
      };
    }

    static getStubConfig() {
      return { title: "Chore Race", target_points: 10, max_width: 820 };
    }

    static getConfigElement() {
      return document.createElement("chore-race-card-editor");
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
      if (firstConnection) {
        this._data = {
          state: {
            open_tasks_today: 0,
            completed_tasks_today: 0,
            team_progress: { completed: 0, total: 0 },
          },
          leaderboard: [],
        };
        this._render();
        if (this._connected) this._load();
      }
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
      clearInterval(this._countdownTimer);
      this._countdownTimer = undefined;
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
        let raceState;
        try {
          raceState = await this._hass.callWS({
            type: "chore_race/get_race_state",
          });
        } catch (error) {
          this._raceApiError = errorMessage(error);
          raceState = undefined;
        }
        if (raceState) {
          this._raceApiError = undefined;
          this._raceReceivedAt = Date.now();
          const [participants, state, areas] = await Promise.all([
            this._hass.callWS({ type: "chore_race/get_participants" }),
            this._hass.callWS({ type: "chore_race/get_state" }),
            this._hass.callWS({ type: "chore_race/get_areas" }),
          ]);
          if (!this._connected || generation !== this._requestGeneration) return;
          const participantById = Object.fromEntries(
            participants.map((participant) => [participant.id, participant]),
          );
          this._participants = participants.filter((participant) => participant.active);
          this._areas = Object.fromEntries(
            areas.map((area) => [area.area_id, area.name]),
          );
          this._data = {
            raceState,
            state,
            leaderboard: (raceState.leaderboard ?? []).map((entry) => ({
              ...entry,
              points: Number(entry.points ?? entry.race_points ?? entry.score ?? 0),
              name:
                entry.name ??
                participantById[entry.participant_id]?.name ??
                "Teilnehmer",
              avatar:
                entry.avatar ?? participantById[entry.participant_id]?.avatar,
            })),
          };
          this._error = undefined;
          this._syncCountdownTimer();
          this._render();
          return;
        }
        const [participants, leaderboard, tasks] = await Promise.all([
          this._hass.callWS({ type: "chore_race/get_participants" }),
          this._hass.callWS({ type: "chore_race/get_leaderboard" }),
          this._hass.callWS({ type: "chore_race/get_tasks" }),
        ]);
        let state;
        try {
          state = await this._hass.callWS({ type: "chore_race/get_state" });
        } catch (_error) {
          const localDate = new Date();
          localDate.setMinutes(localDate.getMinutes() - localDate.getTimezoneOffset());
          const day = localDate.toISOString().slice(0, 10);
          const todayTasks = tasks.filter((task) => task.date === day);
          const completed = todayTasks.filter(
            (task) => task.status === "completed",
          ).length;
          state = {
            open_tasks_today: todayTasks.length - completed,
            completed_tasks_today: completed,
            team_progress: { completed, total: todayTasks.length },
          };
        }
        if (!this._connected || generation !== this._requestGeneration) return;
        const participantById = Object.fromEntries(
          participants.map((participant) => [participant.id, participant]),
        );
        this._data = {
          raceState: { status: "legacy" },
          state,
          leaderboard: leaderboard.map((entry) => ({
            ...entry,
            avatar: participantById[entry.participant_id]?.avatar,
          })),
        };
        this._error = this._raceApiError
          ? `Race API nicht verfügbar · ${this._raceApiError}`
          : undefined;
        this._syncCountdownTimer();
      } catch (error) {
        if (!this._connected || generation !== this._requestGeneration) return;
        this._error = errorMessage(error);
      }
      this._render();
    }

    async _completeRaceTask(participantId) {
      if (
        !this._hass?.callWS ||
        !this._selectedTaskId ||
        this._actionBusy ||
        this._data?.raceState?.status !== "running"
      ) {
        return;
      }
      this._actionBusy = true;
      this._actionError = undefined;
      this._render();
      try {
        const raceState = await this._hass.callWS({
          type: "chore_race/complete_race_task",
          task_id: this._selectedTaskId,
          participant_id: participantId,
        });
        this._selectedTaskId = undefined;
        this._raceReceivedAt = Date.now();
        this._data = {
          ...this._data,
          raceState,
          leaderboard: raceState.leaderboard ?? [],
        };
        await this._load();
      } catch (error) {
        this._actionError = errorMessage(error);
      } finally {
        this._actionBusy = false;
        this._render();
      }
    }

    async _changeRace(action) {
      if (!this._hass?.callWS || this._actionBusy) return;
      if (
        action === "stop_race" &&
        !window.confirm("Rennen wirklich beenden?")
      ) {
        return;
      }
      this._actionBusy = true;
      this._actionError = undefined;
      this._render();
      try {
        await this._hass.callWS({ type: `chore_race/${action}` });
        await this._load();
      } catch (error) {
        this._actionError = errorMessage(error);
      } finally {
        this._actionBusy = false;
        this._render();
      }
    }

    _bindRaceActions() {
      this.shadowRoot.querySelector("[data-start-race]")?.addEventListener(
        "click",
        () => this._changeRace("start_race"),
      );
      this.shadowRoot.querySelector("[data-stop-race]")?.addEventListener(
        "click",
        () => this._changeRace("stop_race"),
      );
      this.shadowRoot.querySelectorAll("[data-complete-task]").forEach((button) => {
        button.addEventListener("click", () => {
          if (this._data?.raceState?.status !== "running") return;
          this._selectedTaskId = button.dataset.completeTask;
          this._actionError = undefined;
          this._render();
        });
      });
      this.shadowRoot.querySelectorAll("[data-participant]").forEach((button) => {
        button.addEventListener("click", () =>
          this._completeRaceTask(button.dataset.participant),
        );
      });
      this.shadowRoot.querySelector("[data-close-picker]")?.addEventListener(
        "click",
        () => {
          if (this._actionBusy) return;
          this._selectedTaskId = undefined;
          this._actionError = undefined;
          this._render();
        },
      );
    }

    _remainingSeconds() {
      const race = this._data?.raceState;
      if (!race) return 0;
      if (race.ends_at) {
        return Math.max(0, Math.ceil((Date.parse(race.ends_at) - Date.now()) / 1000));
      }
      const elapsed = Math.floor((Date.now() - (this._raceReceivedAt ?? Date.now())) / 1000);
      return Math.max(0, (Number(race.remaining_seconds) || 0) - elapsed);
    }

    _syncCountdownTimer() {
      clearInterval(this._countdownTimer);
      this._countdownTimer = undefined;
      if (this._data?.raceState?.status !== "running") return;
      this._countdownTimer = setInterval(() => {
        if (document.hidden || !this._connected) return;
        if (this._remainingSeconds() <= 0) {
          clearInterval(this._countdownTimer);
          this._countdownTimer = undefined;
          this._load();
          return;
        }
        this._render();
      }, 1000);
    }

    _formatDuration(seconds) {
      const safe = Math.max(0, Math.floor(Number(seconds) || 0));
      const hours = Math.floor(safe / 3600);
      const minutes = Math.floor((safe % 3600) / 60);
      const remainder = safe % 60;
      return hours
        ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
        : `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
    }

    _render() {
      if (!this.shadowRoot) return;
      const state = this._data?.state ?? DEMO_DATA.state;
      const racers = this._data?.leaderboard ?? [];
      const race = this._data?.raceState ?? { status: "demo" };
      const status = ["ready", "running", "finished", "legacy"].includes(race.status)
        ? race.status
        : "ready";
      const statusCopy = {
        ready: {
          eyebrow: "RENNEN BEREIT",
          heading: "Startlinie",
          detail: "Macht euch bereit",
        },
        running: {
          eyebrow: "RENNEN LÄUFT",
          heading: "Noch",
          detail: "Jede Aufgabe zählt",
        },
        finished: {
          eyebrow: "RENNEN BEENDET",
          heading: "Zieleinlauf",
          detail: racers[0]?.name
            ? `${racers[0].name} liegt vorne`
            : "Ergebnis steht fest",
        },
        legacy: {
          eyebrow: "TEAMWERTUNG",
          heading: "Wochenstand",
          detail: "Kompatibilitätsmodus",
        },
      }[status];
      const remaining = this._remainingSeconds();
      const completed = Number(state.team_progress?.completed ?? 0);
      const total = Number(state.team_progress?.total ?? 0);
      const teamProgress = total > 0 ? clamp((completed / total) * 100, 0, 100) : 0;
      const highestScore = Math.max(0, ...racers.map((entry) => Number(entry.points) || 0));
      const configuredTarget = Number(this._config.target_points);
      const target = configuredTarget > 0 ? configuredTarget : Math.max(10, highestScore);
      const reducedMotion =
        this._config.force_reduced_motion === true || this._motionQuery?.matches;
      const title = escapeHtml(this._config.title ?? "Chore Race");
      const openTasks = race.open_tasks ?? [];
      const running = status === "running";
      const isAdmin = this._hass?.user?.is_admin === true;
      const selectedTask = openTasks.find(
        (task) => task.id === this._selectedTaskId,
      );

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

      const taskCards = openTasks.length
        ? openTasks
            .map((task) => {
              const imageUrl =
                (task.image && assetUrl(task.image)) ??
                suggestedTaskImage(task.name);
              const image = imageUrl
                ? `<img class="task-image" src="${escapeHtml(imageUrl)}"
                    alt="" loading="lazy" />`
                : `<div class="task-icon" aria-hidden="true">
                    <ha-icon icon="${escapeHtml(task.icon ?? "mdi:checkbox-marked-circle-outline")}"></ha-icon>
                  </div>`;
              return `
                <article class="task-card">
                  ${image}
                  <div class="task-copy">
                    <div>
                      <small>NÄCHSTE AUFGABE</small>
                      <h3>${escapeHtml(task.name ?? "Aufgabe")}</h3>
                      <span>${Number(task.race_points) || 0} Punkte${
                        task.area_id && this._areas[task.area_id]
                          ? ` · ${escapeHtml(this._areas[task.area_id])}`
                          : ""
                      }</span>
                    </div>
                    ${
                      running
                        ? `<button class="complete" data-complete-task="${escapeHtml(task.id)}"
                            ${this._actionBusy ? "disabled" : ""}>Erledigt</button>`
                        : `<span class="race-hint">${
                            status === "ready"
                              ? "Abschluss nach Rennstart möglich"
                              : "Rennen ist beendet"
                          }</span>`
                    }
                  </div>
                </article>`;
            })
            .join("")
        : `<div class="empty task-empty">Keine offenen Aufgaben für heute.</div>`;

      const participantPicker = this._selectedTaskId
        ? `<div class="picker-backdrop" role="presentation">
            <section class="picker" role="dialog" aria-modal="true"
              aria-labelledby="race-picker-title">
              <div class="picker-heading">
                <div><small>AUFGABE ERLEDIGT</small>
                  <h3 id="race-picker-title">Wer war's?</h3></div>
                <button class="close" data-close-picker aria-label="Schließen"
                  ${this._actionBusy ? "disabled" : ""}>×</button>
              </div>
              <div class="participant-grid">
                ${this._participants.length
                  ? this._participants
                      .map((participant) => {
                        const restricted =
                          selectedTask?.adult_only &&
                          participant.role !== "adult" &&
                          !participant.can_do_restricted_tasks;
                        const avatar = participant.avatar
                          ? `<img src="${escapeHtml(participant.avatar)}" alt="" />`
                          : `<span>${escapeHtml(
                              participant.name?.trim().charAt(0) || "?",
                            )}</span>`;
                        return `<button data-participant="${escapeHtml(participant.id)}"
                          ${this._actionBusy || restricted ? "disabled" : ""}
                          class="${restricted ? "restricted" : ""}">
                          ${avatar}<strong>${escapeHtml(participant.name)}</strong>
                          ${restricted ? "<small>Nur Erwachsene</small>" : ""}
                        </button>`;
                      })
                      .join("")
                  : `<p>Keine aktiven Teilnehmer verfügbar.</p>`}
              </div>
              ${this._actionBusy ? `<p class="action-status">Punkte werden gespeichert …</p>` : ""}
              ${this._actionError ? `<p class="action-error">${escapeHtml(this._actionError)}</p>` : ""}
            </section>
          </div>`
        : "";

      this.shadowRoot.innerHTML = `
        <style>${this._styles()}</style>
        <ha-card class="${reducedMotion ? "reduced-motion" : ""}">
          <header>
            <div>
              <span class="eyebrow">${statusCopy.eyebrow}</span>
              <h2>${title}</h2>
            </div>
            <div class="flag" aria-hidden="true"><i></i></div>
          </header>
          <section class="team race-summary" aria-label="Rennstatus">
            <div class="team-copy">
              <span>${statusCopy.heading}</span>
              <strong>${
                status === "ready"
                  ? "Bereit"
                  : status === "running"
                    ? this._formatDuration(remaining)
                  : status === "finished"
                    ? "Fertig"
                    : `${completed} / ${total}`
              }</strong>
            </div>
            <small class="status-detail">${escapeHtml(statusCopy.detail)}</small>
            ${
              status === "legacy"
                ? `<div class="meter" role="progressbar" aria-valuemin="0"
                    aria-valuemax="100" aria-valuenow="${Math.round(teamProgress)}">
                    <i style="--team-progress: ${teamProgress}%"></i></div>`
                : ""
            }
          </section>
          ${
            isAdmin && (status === "ready" || status === "finished")
              ? `<button class="race-control start-race" data-start-race
                  ${this._actionBusy ? "disabled" : ""}>
                  ${
                    this._actionBusy
                      ? "Rennen startet …"
                      : status === "finished"
                        ? "Neues Rennen starten"
                        : "Rennen starten"
                  }
                </button>`
              : isAdmin && status === "running"
                ? `<button class="race-control stop-race" data-stop-race
                    ${this._actionBusy ? "disabled" : ""}>Rennen beenden</button>`
                : ""
          }
          ${
            this._actionError && !this._selectedTaskId
              ? `<p class="action-error race-action-error">${escapeHtml(this._actionError)}</p>`
              : ""
          }
          <section class="tasks" aria-label="Offene Race-Aufgaben">
            ${taskCards}
          </section>
          <section class="lanes">${lanes}</section>
          <footer>
            <span>${
              status === "legacy"
                ? `${state.open_tasks_today ?? 0} Aufgaben offen`
                : race.race_id
                  ? `Rennen ${escapeHtml(race.race_id)}`
                  : "Chore Race"
            }</span>
            <span class="live"><i></i>${this._hass ? "Live" : "Demo"}</span>
          </footer>
          ${
            this._error
              ? `<p class="error">Letzter Stand &middot; ${escapeHtml(this._error)}</p>`
              : ""
          }
          ${participantPicker}
        </ha-card>`;
      this._bindRaceActions();
    }

    _styles() {
      const maxWidth = clamp(Number(this._config.max_width) || 820, 280, 1400);
      const accent = /^#[0-9a-f]{6}$/i.test(this._config.accent_color)
        ? this._config.accent_color
        : "#74829a";
      return `
        :host {
          display: block;
          min-width: 0;
          container-type: inline-size;
          width: min(100%, ${maxWidth}px);
          margin-inline: auto;
          --ink: var(--primary-text-color, #172036);
          --muted: var(--secondary-text-color, #667085);
          --accent: ${accent};
          --surface: var(--ha-card-background, var(--card-background-color, #fbfbff));
          --surface-raised: var(--secondary-background-color, rgba(255, 255, 255, .82));
          --line: var(--divider-color, rgba(105, 92, 255, .18));
        }
        * { box-sizing: border-box; }
        ha-card {
          display: block; overflow: hidden; color: var(--ink);
          background:
            radial-gradient(circle at 92% 0%,
              color-mix(in srgb, var(--accent) 14%, transparent), transparent 28%),
            linear-gradient(
              145deg,
              var(--surface),
              color-mix(in srgb, var(--surface) 92%, var(--accent))
            );
          border-radius: var(--ha-card-border-radius, 24px); padding: clamp(18px, 4vw, 28px);
          box-shadow: var(--ha-card-box-shadow, 0 18px 55px rgba(31, 38, 90, .12));
          font-family: var(--paper-font-body1_-_font-family, system-ui, sans-serif);
        }
        header, .team-copy, footer, .lane-heading, .driver { display: flex; align-items: center; }
        header { justify-content: space-between; gap: 16px; }
        .eyebrow { font-size: 11px; letter-spacing: .16em; font-weight: 800; color: var(--accent); }
        h2 { margin: 4px 0 0; color: var(--ink); font-size: clamp(24px, 6vw, 34px);
          line-height: 1; letter-spacing: -.04em; }
        .flag { position: relative; width: 48px; height: 48px; border-radius: 16px;
          background: color-mix(in srgb, var(--accent) 16%, transparent); transform: rotate(4deg); }
        .flag::before { content: ""; position: absolute; left: 14px; top: 9px;
          width: 3px; height: 31px; border-radius: 3px; background: var(--accent); }
        .flag i { position: absolute; left: 17px; top: 10px; width: 22px; height: 17px;
          background: repeating-conic-gradient(#172036 0 25%, #fff 0 50%) 0 / 8px 8px;
          clip-path: polygon(0 0, 100% 0, 82% 50%, 100% 100%, 0 100%); }
        .team { margin: 22px 0 18px; padding: 16px; border: 1px solid var(--line);
          border-radius: 18px; background: var(--surface-raised); }
        .team-copy { justify-content: space-between; gap: 12px; color: var(--muted); font-size: 13px; }
        .team-copy strong { color: var(--ink); font-size: 19px; }
        .team-copy small { color: var(--muted); font-size: 12px; font-weight: 600; }
        .status-detail { display:block; margin-top:5px; color:var(--muted);
          font-size:12px; }
        .race-summary .team-copy strong { font-variant-numeric: tabular-nums; }
        .meter { height: 9px; margin-top: 12px; border-radius: 99px;
          overflow: hidden; background: color-mix(in srgb, var(--accent) 14%, transparent); }
        .meter i { display: block; width: var(--team-progress); height: 100%; border-radius: inherit;
          background: linear-gradient(90deg, var(--accent), #54a995); transition: width .7s cubic-bezier(.2, .8, .2, 1); }
        .lanes { display: grid; gap: 14px; }
        .tasks { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
          gap:14px; margin:0 0 20px; }
        .task-card { min-width:0; overflow:hidden; border:1px solid var(--line);
          border-radius:20px; background:var(--surface-raised); }
        .task-image, .task-icon { width:100%; height:clamp(180px,28vw,280px);
          object-fit:contain; }
        .task-image { padding:10px;
          background:color-mix(in srgb,var(--accent) 7%,var(--surface)); }
        .task-icon { display:grid; place-items:center;
          color:var(--accent); background:color-mix(in srgb,var(--accent) 12%,var(--surface)); }
        .task-icon ha-icon { --mdc-icon-size:clamp(52px,12vw,86px); }
        .task-copy { display:flex; align-items:flex-end; justify-content:space-between;
          gap:14px; padding:15px; }
        .task-copy small, .picker-heading small { color:var(--accent); font-size:10px;
          font-weight:800; letter-spacing:.12em; }
        .task-copy h3, .picker h3 { margin:4px 0; color:var(--ink); font-size:19px; }
        .task-copy span { color:var(--muted); font-size:12px; }
        button { min-height:48px; border:0; border-radius:14px; padding:0 18px;
          font:inherit; font-weight:750; cursor:pointer; touch-action:manipulation; }
        button:focus-visible { outline:3px solid color-mix(in srgb,var(--accent) 45%,white);
          outline-offset:2px; }
        button:disabled { cursor:wait; opacity:.6; }
        .complete { flex:0 0 auto; color:white; background:var(--accent); }
        .race-control { width:100%; min-height:56px; margin:0 0 18px; }
        .start-race { color:white; background:var(--accent); font-size:17px; }
        .stop-race { min-height:48px; color:var(--muted);
          background:transparent; border:1px solid var(--line); font-size:13px; }
        .race-action-error { margin:-6px 0 18px; }
        .race-hint { max-width:145px; text-align:right; }
        .picker-backdrop { position:fixed; z-index:20; inset:0; display:grid;
          place-items:center; padding:18px; background:rgba(5,10,20,.68); }
        .picker { width:min(100%,520px); max-height:min(82vh,720px); overflow:auto;
          padding:20px; border:1px solid var(--line); border-radius:24px;
          color:var(--ink); background:var(--surface); box-shadow:0 24px 70px rgba(0,0,0,.35); }
        .picker-heading { display:flex; align-items:flex-start; justify-content:space-between;
          gap:16px; margin-bottom:16px; }
        .picker h3 { font-size:26px; }
        .close { width:48px; padding:0; color:var(--ink); background:var(--surface-raised);
          font-size:28px; }
        .participant-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
          gap:12px; }
        .participant-grid button { min-height:112px; display:grid; place-items:center;
          gap:7px; padding:12px; color:var(--ink); background:var(--surface-raised);
          border:1px solid var(--line); }
        .participant-grid button.restricted { cursor:not-allowed; opacity:.46; }
        .participant-grid button small { color:var(--muted); font-size:10px; }
        .participant-grid img, .participant-grid span { width:58px; height:58px;
          display:grid; place-items:center; object-fit:cover; border-radius:50%;
          color:white; background:var(--accent); font-size:22px; }
        .action-status, .action-error { margin:14px 0 0; text-align:center; font-size:13px; }
        .action-status { color:var(--muted); }
        .action-error { color:var(--error-color,#db4437); }
        .lane-heading { justify-content: space-between; margin-bottom: 6px;
          color: var(--ink); font-size: 12px; font-variant-numeric: tabular-nums; }
        .driver { gap: 8px; }
        .driver > span, .driver > img { width: 24px; height: 24px; border-radius: 50%; object-fit: cover;
          display: grid; place-items: center; background: var(--accent); color: white; font-size: 11px; font-weight: 800; }
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
            hsl(calc(215 + var(--lane) * 42) 52% 62%),
            hsl(calc(215 + var(--lane) * 42) 48% 46%)
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
          border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }
        .live { display: flex; gap: 6px; align-items: center; }
        .live i { width: 7px; height: 7px; border-radius: 50%; background: #24cf9e;
          box-shadow: 0 0 0 4px rgba(36,207,158,.13); animation: pulse 1.8s ease-in-out infinite; }
        .error { margin: 10px 0 0; color: var(--error-color, #db4437); font-size: 11px; }
        .empty { padding: 22px; color: var(--muted); text-align: center;
          background: var(--surface-raised);
          border: 1px dashed color-mix(in srgb,var(--accent) 52%,var(--line));
          border-radius: 14px; }
        @keyframes pulse { 50% { transform: scale(.6); opacity: .55; } }
        .reduced-motion *, .reduced-motion *::before, .reduced-motion *::after {
          animation-duration: .001ms !important; animation-iteration-count: 1 !important;
          scroll-behavior: auto !important; transition-duration: .001ms !important;
        }
        @media (prefers-reduced-motion: reduce) {
          *, *::before, *::after { animation-duration: .001ms !important; animation-iteration-count: 1 !important;
            scroll-behavior: auto !important; transition-duration: .001ms !important; }
        }
        @container (max-width: 420px) {
          ha-card { padding: 16px; border-radius: 20px; }
          .team { margin-top: 18px; } .track { height: 42px; }
          header { align-items: flex-start; }
          h2 { overflow-wrap: anywhere; }
          .team-copy { gap: 8px; }
          .lane-heading { gap: 8px; }
          .driver { min-width: 0; }
          .driver strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
          .tasks { grid-template-columns:1fr; }
          .task-copy { align-items:stretch; flex-direction:column; }
          .complete { width:100%; }
          .race-hint { max-width:none; text-align:left; }
          .participant-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
        }
      `;
    }
  }

  if (!customElements.get("chore-race-card")) {
    if (!customElements.get("chore-race-card-editor")) {
      customElements.define("chore-race-card-editor", ChoreRaceCardEditor);
    }
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
