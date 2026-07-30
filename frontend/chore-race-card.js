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
  const normalizeTaskChains = (value) => {
    const chains = Array.isArray(value)
      ? value
      : value && typeof value === "object"
        ? Object.entries(value).map(([id, chain]) => ({ id, ...chain }))
        : [];
    return chains
      .filter((chain) => chain && typeof chain === "object")
      .map((chain, chainIndex) => ({
        ...chain,
        id: String(chain.id ?? `chain-${chainIndex}`),
        name: String(chain.name ?? "Aufgabenkette"),
        steps: (Array.isArray(chain.steps) ? chain.steps : [])
          .filter((step) => step && typeof step === "object")
          .map((step, stepIndex) => ({
            ...step,
            id: String(step.id ?? `step-${stepIndex + 1}`),
            sort_order: Number(step.sort_order ?? stepIndex),
          }))
          .sort((a, b) => a.sort_order - b.sort_order),
      }));
  };
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
      this._floors = {};
      this._selectedTaskId = undefined;
      this._selectedParticipantId = undefined;
      this._selectedCopilotId = undefined;
      this._fairPlay = false;
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
          const [participants, state, places] = await Promise.all([
            this._hass.callWS({ type: "chore_race/get_participants" }),
            this._hass.callWS({ type: "chore_race/get_state" }),
            this._hass.callWS({ type: "chore_race/get_areas" }),
          ]);
          if (!this._connected || generation !== this._requestGeneration) return;
          const participantById = Object.fromEntries(
            participants.map((participant) => [participant.id, participant]),
          );
          const raceRunning = raceState.status === "running";
          const raceParticipantIds = new Set(raceState.participant_ids ?? []);
          this._participants = participants.filter(
            (participant) =>
              participant.active &&
              (!raceRunning || raceParticipantIds.has(participant.id)),
          );
          this._areas = Object.fromEntries(
            places
              .filter((place) => place.kind !== "floor")
              .map((area) => [area.area_id, area.name]),
          );
          this._floors = Object.fromEntries(
            places
              .filter((place) => place.kind === "floor")
              .map((floor) => [floor.floor_id, floor.name]),
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

    async _completeTask() {
      if (
        !this._hass?.callWS ||
        !this._selectedTaskId ||
        !this._selectedParticipantId ||
        this._actionBusy
      ) {
        return;
      }
      const running = this._data?.raceState?.status === "running";
      this._actionBusy = true;
      this._actionError = undefined;
      this._render();
      try {
        const raceState = await this._hass.callWS({
          type: running
            ? "chore_race/complete_race_task"
            : "chore_race/complete_task",
          task_id: this._selectedTaskId,
          participant_id: this._selectedParticipantId,
          ...(running && this._selectedCopilotId
            ? { copilot_participant_id: this._selectedCopilotId }
            : {}),
          ...(running ? { fair_play: this._fairPlay } : {}),
        });
        this._selectedTaskId = undefined;
        this._selectedParticipantId = undefined;
        this._selectedCopilotId = undefined;
        this._fairPlay = false;
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

    async _selectReward(rewardId) {
      const raceId = this._data?.raceState?.race_id;
      if (!this._hass?.callWS || !raceId || !rewardId || this._actionBusy) return;
      if (!window.confirm("Diese Belohnung verbindlich für den Champion auswählen?")) {
        return;
      }
      this._actionBusy = true;
      this._actionError = undefined;
      this._render();
      try {
        const raceState = await this._hass.callWS({
          type: "chore_race/select_reward",
          race_id: raceId,
          reward_id: rewardId,
        });
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

    async _changeRace(action, payload = {}) {
      if (!this._hass?.callWS || this._actionBusy) return;
      const confirmations = {
        stop_race: "Rennen wirklich beenden?",
        reset_race:
          "Rennen wirklich zurücksetzen? Alle Wertungen dieses Rennens werden rückgängig gemacht und die Aufgaben wieder geöffnet.",
        remove_race_participant:
          "Teilnehmer wirklich entfernen? Die Person verschwindet auch aus dem Planer. Historische Rennen bleiben erhalten; Wertungen dieses Rennens werden rückgängig gemacht und deren Aufgaben wieder geöffnet.",
      };
      if (confirmations[action] && !window.confirm(confirmations[action])) return;
      this._actionBusy = true;
      this._actionError = undefined;
      this._render();
      try {
        await this._hass.callWS({
          type: `chore_race/${action}`,
          ...payload,
        });
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
      this.shadowRoot.querySelector("[data-reset-race]")?.addEventListener(
        "click",
        () => this._changeRace("reset_race"),
      );
      this.shadowRoot
        .querySelectorAll("[data-remove-race-participant]")
        .forEach((button) => {
          button.addEventListener("click", () =>
            this._changeRace("remove_race_participant", {
              participant_id: button.dataset.removeRaceParticipant,
            }),
          );
        });
      this.shadowRoot.querySelectorAll("[data-select-reward]").forEach((button) => {
        button.addEventListener("click", () =>
          this._selectReward(button.dataset.selectReward),
        );
      });
      this.shadowRoot.querySelectorAll("[data-complete-task]").forEach((button) => {
        button.addEventListener("click", () => {
          this._selectedTaskId = button.dataset.completeTask;
          this._selectedParticipantId = undefined;
          this._selectedCopilotId = undefined;
          this._fairPlay = false;
          this._actionError = undefined;
          this._render();
        });
      });
      this.shadowRoot.querySelectorAll("[data-participant]").forEach((button) => {
        button.addEventListener("click", () => {
          this._selectedParticipantId = button.dataset.participant;
          if (this._selectedCopilotId === this._selectedParticipantId) {
            this._selectedCopilotId = undefined;
          }
          this._actionError = undefined;
          this._render();
        });
      });
      this.shadowRoot.querySelector("[data-copilot]")?.addEventListener(
        "change",
        (event) => {
          this._selectedCopilotId = event.currentTarget.value || undefined;
          if (this._selectedCopilotId) this._fairPlay = false;
          this._render();
        },
      );
      this.shadowRoot.querySelector("[data-fair-play]")?.addEventListener(
        "change",
        (event) => {
          this._fairPlay = event.currentTarget.checked;
          if (this._fairPlay) this._selectedCopilotId = undefined;
          this._render();
        },
      );
      this.shadowRoot.querySelector("[data-confirm-completion]")?.addEventListener(
        "click",
        () => this._completeTask(),
      );
      this.shadowRoot.querySelector("[data-close-picker]")?.addEventListener(
        "click",
        () => {
          if (this._actionBusy) return;
          this._selectedTaskId = undefined;
          this._selectedParticipantId = undefined;
          this._selectedCopilotId = undefined;
          this._fairPlay = false;
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
      const race = this._data?.raceState ?? { status: "demo" };
      const status = ["ready", "running", "finished", "legacy"].includes(race.status)
        ? race.status
        : "ready";
      const receivedLeaderboard = this._data?.leaderboard ?? [];
      const racers =
        status === "ready" && !race.race_id && receivedLeaderboard.length === 0
          ? this._participants.map((participant) => ({
              participant_id: participant.id,
              name: participant.name,
              avatar: participant.avatar,
              points: 0,
              rank: 1,
            }))
          : receivedLeaderboard;
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
      const taskChains = normalizeTaskChains(
        state.task_chains ?? race.task_chains,
      );
      const running = status === "running";
      const isAdmin = this._hass?.user?.is_admin === true;
      const selectedTask = openTasks.find(
        (task) => task.id === this._selectedTaskId,
      );
      const chainById = Object.fromEntries(
        taskChains.map((chain) => [chain.id, chain]),
      );
      const chainStatus = taskChains.length
        ? `<section class="chain-status" aria-labelledby="chain-status-title">
            <div class="section-heading">
              <div><span>ABLAUF</span>
                <strong id="chain-status-title">Aufgabenketten</strong></div>
              <small>${taskChains.length} aktiv</small>
            </div>
            <div class="chain-status-list">
              ${taskChains
                .map((chain) => {
                  const completed = chain.steps.filter(
                    (step) => step.status === "completed" || step.completed === true,
                  ).length;
                  return `<article>
                    <div><strong>${escapeHtml(chain.name)}</strong>
                      <small>${completed} von ${chain.steps.length} erledigt</small></div>
                    <ol aria-label="Fortschritt ${escapeHtml(chain.name)}">
                      ${chain.steps
                        .map((step, index) => {
                          const stepStatus =
                            step.status === "completed" || step.completed === true
                              ? "completed"
                              : step.status === "blocked" || step.blocked === true
                                ? "blocked"
                                : "ready";
                          const label = {
                            completed: "Erledigt",
                            blocked: "Blockiert",
                            ready: "Bereit",
                          }[stepStatus];
                          return `<li class="${stepStatus}" title="${label}">
                            <span class="sr-only">Schritt ${index + 1}: ${label}</span>
                          </li>`;
                        })
                        .join("")}
                    </ol>
                  </article>`;
                })
                .join("")}
            </div>
          </section>`
        : "";

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
              const bonuses =
                (Number(racer.fair_play_bonus) || 0) +
                (Number(racer.streak_bonus) || 0) +
                (Number(racer.copilot_points) || 0);
              return `
                <div class="lane" style="--lane: ${index};">
                  <div class="lane-heading">
                    <div class="driver">${avatar}<strong>${name}</strong>
                      ${racer.rank ? `<small>#${racer.rank}</small>` : ""}
                      ${
                        isAdmin && race.race_id
                          ? `<button class="remove-racer"
                              data-remove-race-participant="${escapeHtml(racer.participant_id)}"
                              aria-label="${name} als Teilnehmer entfernen"
                              title="Teilnehmer entfernen"
                              ${this._actionBusy ? "disabled" : ""}>×</button>`
                          : ""
                      }</div>
                    <span>${points} P${bonuses ? `<small> · ${bonuses} Bonus</small>` : ""}</span>
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
              const multiplier = Number(task.points_multiplier) || 1;
              const pointLabel =
                task.floor_id && multiplier > 1
                  ? `${Number(task.base_race_points) || 0} × ${multiplier} Räume = ${Number(task.race_points) || 0} Punkte`
                  : `${Number(task.race_points) || 0} Punkte`;
              const chain = task.chain_id ? chainById[task.chain_id] : null;
              return `
                <article class="task-card ${task.blocked ? "blocked" : "ready"}">
                  ${image}
                  <div class="task-copy">
                    <div>
                      <small>${task.blocked ? "BLOCKIERT" : chain ? "KETTE · BEREIT" : "NÄCHSTE AUFGABE"}</small>
                      <h3>${escapeHtml(task.name ?? "Aufgabe")}</h3>
                      <span>${pointLabel}${
                        task.floor_id && this._floors[task.floor_id]
                          ? ` · ${escapeHtml(this._floors[task.floor_id])}`
                          : task.area_id && this._areas[task.area_id]
                          ? ` · ${escapeHtml(this._areas[task.area_id])}`
                          : ""
                      }${chain ? ` · ${escapeHtml(chain.name)}` : ""}</span>
                    </div>
                    <button class="complete" data-complete-task="${escapeHtml(task.id)}"
                      ${this._actionBusy || task.blocked ? "disabled" : ""}
                      aria-disabled="${this._actionBusy || task.blocked ? "true" : "false"}"
                      title="${task.blocked ? "Erst den vorherigen Schritt erledigen" : "Aufgabe erledigen"}">
                      ${task.blocked ? "Blockiert" : "Erledigt"}</button>
                  </div>
                </article>`;
            })
            .join("")
        : `<div class="empty task-empty">Keine offenen Aufgaben für heute.</div>`;

      const selectedParticipant = this._participants.find(
        (participant) => participant.id === this._selectedParticipantId,
      );
      const participantPicker = this._selectedTaskId
        ? `<div class="picker-backdrop" role="presentation">
            <section class="picker" role="dialog" aria-modal="true"
              aria-labelledby="race-picker-title">
              <div class="picker-heading">
                <div><small>${running ? "RENNWERTUNG" : "ALLTAGSWERTUNG"}</small>
                  <h3 id="race-picker-title">${
                    running ? "Rennpunkte vergeben" : "Aufgabe erledigen"
                  }</h3></div>
                <button class="close" data-close-picker aria-label="Schließen"
                  ${this._actionBusy ? "disabled" : ""}>×</button>
              </div>
              <p class="picker-step"><strong>1</strong> Wer hat die Aufgabe erledigt?</p>
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
                          class="${restricted ? "restricted" : ""} ${
                            participant.id === this._selectedParticipantId
                              ? "selected"
                              : ""
                          }">
                          ${avatar}<strong>${escapeHtml(participant.name)}</strong>
                          ${restricted ? "<small>Nur Erwachsene</small>" : ""}
                        </button>`;
                      })
                      .join("")
                  : `<p>Keine aktiven Teilnehmer verfügbar.</p>`}
              </div>
              ${
                selectedParticipant && running
                  ? `<div class="bonus-panel">
                      <p class="picker-step"><strong>2</strong> Optionaler Team-Bonus</p>
                      <label>Copilot
                        <select data-copilot ${this._actionBusy ? "disabled" : ""}>
                          <option value="">Ohne Copilot</option>
                          ${this._participants
                            .filter(
                              (participant) =>
                                participant.id !== selectedParticipant.id &&
                                !(
                                  selectedTask?.adult_only &&
                                  participant.role !== "adult" &&
                                  !participant.can_do_restricted_tasks
                                ),
                            )
                            .map(
                              (participant) =>
                                `<option value="${escapeHtml(participant.id)}" ${
                                  participant.id === this._selectedCopilotId
                                    ? "selected"
                                    : ""
                                }>${escapeHtml(participant.name)}</option>`,
                            )
                            .join("")}
                        </select>
                      </label>
                      <label class="fair-play-option">
                        <input type="checkbox" data-fair-play
                          ${this._fairPlay ? "checked" : ""}
                          ${this._selectedCopilotId || this._actionBusy ? "disabled" : ""}>
                        <span><strong>Fair Play</strong>
                          <small>Bonus für besonders faires, selbstständiges Erledigen</small></span>
                      </label>
                      <p class="bonus-note">Copilot und Fair Play sind bewusst nicht kombinierbar.</p>
                    </div>
                    <button class="confirm-completion" data-confirm-completion
                      ${this._actionBusy ? "disabled" : ""}>
                      ${this._actionBusy ? "Punkte werden gespeichert …" : "Abschluss bestätigen"}
                    </button>`
                  : selectedParticipant
                    ? `<div class="normal-score-note">
                        <strong>Normale Alltagswertung</strong>
                        <span>Ohne laufendes Rennen gibt es den Alltagspunkt.
                          Renn-, Copilot-, Fair-Play- und Serienboni bleiben aus.</span>
                      </div>
                      <button class="confirm-completion" data-confirm-completion
                        ${this._actionBusy ? "disabled" : ""}>
                        ${this._actionBusy ? "Punkt wird gespeichert …" : "Als erledigt markieren"}
                      </button>`
                  : ""
              }
              ${this._actionBusy ? `<p class="action-status">Punkte werden gespeichert …</p>` : ""}
              ${this._actionError ? `<p class="action-error">${escapeHtml(this._actionError)}</p>` : ""}
            </section>
          </div>`
        : "";
      const lastCompletion = race.last_completion;
      const scoreFeedback =
        lastCompletion && status !== "ready"
          ? `<aside class="score-feedback">
              <span>LETZTE WERTUNG</span>
              <strong>${escapeHtml(lastCompletion.participant_name)}
                +${Number(lastCompletion.total_points) || 0}</strong>
              <small>${escapeHtml(lastCompletion.task_name)}${
                lastCompletion.copilot_name
                  ? ` · Copilot ${escapeHtml(lastCompletion.copilot_name)}
                    +${Number(lastCompletion.copilot_points) || 0}`
                  : lastCompletion.fair_play_bonus
                    ? ` · Fair Play +${Number(lastCompletion.fair_play_bonus)}`
                    : lastCompletion.streak_bonus
                      ? ` · Serie +${Number(lastCompletion.streak_bonus)}`
                      : ""
              }</small>
            </aside>`
          : "";
      const rewardSelection = race.reward_selection;
      const availableRewards = race.rewards ?? [];
      const champion = race.champion
        ? `<aside class="champion">
            <span>🏆 CHORE RACE CHAMPION</span>
            <strong>${escapeHtml(race.champion.name)}</strong>
            <small>${Number(race.champion.points) || 0} Punkte</small>
            ${
              rewardSelection
                ? `<div class="chosen-reward">
                    <ha-icon icon="${escapeHtml(
                      rewardSelection.reward_icon || "mdi:gift-outline",
                    )}"></ha-icon>
                    <span><small>GEWINNERWAHL</small>
                      <strong>${escapeHtml(rewardSelection.reward_name)}</strong></span>
                  </div>`
                : availableRewards.length
                  ? `<div class="reward-choice">
                      <small>Wähle deine Belohnung</small>
                      <div>${availableRewards
                        .map(
                          (reward) =>
                            `<button data-select-reward="${escapeHtml(reward.id)}"
                              ${this._actionBusy ? "disabled" : ""}>
                              <ha-icon icon="${escapeHtml(
                                reward.icon || "mdi:gift-outline",
                              )}"></ha-icon>
                              <span>${escapeHtml(reward.name)}</span>
                            </button>`,
                        )
                        .join("")}</div>
                    </div>`
                  : `<small>Belohnungen können im Planer angelegt werden.</small>`
            }
          </aside>`
        : "";
      const lastReward =
        !race.champion && race.last_reward_selection
          ? `<aside class="last-reward">
              <ha-icon icon="${escapeHtml(
                race.last_reward_selection.reward_icon || "mdi:gift-outline",
              )}"></ha-icon>
              <span><small>LETZTE GEWINNERWAHL</small>
                <strong>${escapeHtml(race.last_reward_selection.participant_name)}
                  · ${escapeHtml(race.last_reward_selection.reward_name)}</strong></span>
            </aside>`
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
          <div class="race-controls">
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
            isAdmin && race.race_id
              ? `<button class="race-control reset-race" data-reset-race
                  ${this._actionBusy ? "disabled" : ""}>Rennen zurücksetzen</button>`
              : ""
          }
          </div>
          ${
            this._actionError && !this._selectedTaskId
              ? `<p class="action-error race-action-error">${escapeHtml(this._actionError)}</p>`
              : ""
          }
          ${champion || lastReward || scoreFeedback}
          ${chainStatus}
          <div class="race-stage">
            <section class="stage-panel lanes-panel" aria-label="Rennstrecke">
              <div class="section-heading">
                <div>
                  <span>LIVE</span>
                  <strong>Rennstrecke</strong>
                </div>
                <small>${racers.length} ${
                  racers.length === 1 ? "Teilnehmer" : "Teilnehmer"
                }</small>
              </div>
              <div class="lanes">${lanes}</div>
            </section>
            <section class="stage-panel tasks-panel" aria-label="Offene Race-Aufgaben">
              <div class="section-heading">
                <div>
                  <span>HEUTE</span>
                  <strong>Offene Aufgaben</strong>
                </div>
                <small>${openTasks.length} offen</small>
              </div>
              <div class="tasks">
                ${taskCards}
              </div>
            </section>
          </div>
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
          border-radius: var(--ha-card-border-radius, 24px); padding: clamp(16px, 2.5vw, 24px);
          box-shadow: var(--ha-card-box-shadow, 0 18px 55px rgba(31, 38, 90, .12));
          font-family: var(--paper-font-body1_-_font-family, system-ui, sans-serif);
        }
        header, .team-copy, footer, .lane-heading, .driver { display: flex; align-items: center; }
        header { justify-content: space-between; gap: 16px; }
        .eyebrow { font-size: 11px; letter-spacing: .16em; font-weight: 800; color: var(--accent); }
        h2 { margin: 3px 0 0; color: var(--ink); font-size: clamp(23px, 4vw, 31px);
          line-height: 1; letter-spacing: -.04em; }
        .flag { position: relative; width: 42px; height: 42px; border-radius: 14px;
          background: color-mix(in srgb, var(--accent) 16%, transparent); transform: rotate(4deg); }
        .flag::before { content: ""; position: absolute; left: 12px; top: 8px;
          width: 3px; height: 27px; border-radius: 3px; background: var(--accent); }
        .flag i { position: absolute; left: 15px; top: 9px; width: 20px; height: 15px;
          background: repeating-conic-gradient(#172036 0 25%, #fff 0 50%) 0 / 8px 8px;
          clip-path: polygon(0 0, 100% 0, 82% 50%, 100% 100%, 0 100%); }
        .team { margin: 14px 0 12px; padding: 11px 14px; border: 1px solid var(--line);
          border-radius: 15px; background: var(--surface-raised); }
        .team-copy { justify-content: space-between; gap: 12px; color: var(--muted); font-size: 13px; }
        .team-copy strong { color: var(--ink); font-size: 19px; }
        .team-copy small { color: var(--muted); font-size: 12px; font-weight: 600; }
        .status-detail { display:block; margin-top:2px; color:var(--muted);
          font-size:11px; }
        .race-summary .team-copy strong { font-variant-numeric: tabular-nums; }
        .meter { height: 9px; margin-top: 12px; border-radius: 99px;
          overflow: hidden; background: color-mix(in srgb, var(--accent) 14%, transparent); }
        .meter i { display: block; width: var(--team-progress); height: 100%; border-radius: inherit;
          background: linear-gradient(90deg, var(--accent), #54a995); transition: width .7s cubic-bezier(.2, .8, .2, 1); }
        .race-stage { display:grid; grid-template-columns:minmax(0,1.08fr) minmax(240px,.92fr);
          gap:12px; align-items:start; }
        .stage-panel { min-width:0; padding:12px; border:1px solid var(--line);
          border-radius:16px; background:color-mix(in srgb,var(--surface-raised) 55%,transparent); }
        .section-heading { display:flex; align-items:center; justify-content:space-between;
          gap:10px; margin:0 1px 11px; }
        .section-heading > div { display:flex; align-items:baseline; gap:8px; min-width:0; }
        .section-heading span { color:var(--muted); font-size:9px; font-weight:800;
          letter-spacing:.14em; }
        .section-heading strong { overflow:hidden; color:var(--ink); font-size:14px;
          text-overflow:ellipsis; white-space:nowrap; }
        .section-heading small { flex:0 0 auto; color:var(--muted); font-size:10px; }
        .lanes { display: grid; gap: 10px; }
        .tasks { display:grid; grid-template-columns:1fr; gap:8px;
          max-height:min(47vh,380px); overflow:auto; overscroll-behavior:contain;
          scrollbar-width:thin; scrollbar-color:var(--line) transparent; }
        .task-card { min-width:0; min-height:62px; display:grid;
          grid-template-columns:52px minmax(0,1fr); overflow:hidden;
          border:1px solid var(--line); border-radius:12px;
          background:color-mix(in srgb,var(--surface-raised) 72%,var(--surface)); }
        .task-card.blocked { opacity:.72; }
        .task-card.blocked .task-image { filter:grayscale(.55); }
        .task-image, .task-icon { width:52px; height:100%; min-height:62px;
          object-fit:contain; }
        .task-image { padding:6px;
          background:color-mix(in srgb,var(--accent) 7%,var(--surface)); }
        .task-icon { display:grid; place-items:center;
          color:var(--accent); background:color-mix(in srgb,var(--accent) 12%,var(--surface)); }
        .task-icon ha-icon { --mdc-icon-size:34px; }
        .task-copy { min-width:0; display:flex; align-items:center; justify-content:space-between;
          gap:7px; padding:7px 9px; }
        .task-copy > div { min-width:0; }
        .task-copy small, .picker-heading small { color:var(--accent); font-size:8px;
          font-weight:800; letter-spacing:.12em; }
        .task-copy h3 { overflow:hidden; margin:2px 0 3px; color:var(--ink);
          font-size:14px; line-height:1.15; text-overflow:ellipsis; white-space:nowrap; }
        .picker h3 { margin:4px 0; color:var(--ink); font-size:19px; }
        .task-copy span { display:block; overflow:hidden; color:var(--muted);
          font-size:10px; line-height:1.25; text-overflow:ellipsis; white-space:nowrap; }
        button { min-height:48px; border:0; border-radius:14px; padding:0 18px;
          font:inherit; font-weight:750; cursor:pointer; touch-action:manipulation; }
        button:focus-visible { outline:3px solid color-mix(in srgb,var(--accent) 45%,white);
          outline-offset:2px; }
        button:disabled { cursor:wait; opacity:.6; }
        .complete { flex:0 0 auto; min-height:38px; padding:0 11px;
          border-radius:11px; color:white; background:var(--accent); font-size:11px; }
        .task-card.blocked .complete { color:var(--muted);
          background:var(--surface-raised); border:1px solid var(--line); }
        .chain-status { margin:0 0 12px; padding:10px 12px;
          border:1px solid var(--line); border-radius:14px;
          background:color-mix(in srgb,var(--surface-raised) 55%,transparent); }
        .chain-status-list { display:grid;
          grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:7px; }
        .chain-status-list article { display:grid; grid-template-columns:minmax(0,1fr) auto;
          align-items:center; gap:9px; min-width:0; padding:7px 9px;
          border:1px solid var(--line); border-radius:10px; background:var(--surface); }
        .chain-status-list article > div { display:grid; min-width:0; }
        .chain-status-list strong { overflow:hidden; color:var(--ink); font-size:11px;
          text-overflow:ellipsis; white-space:nowrap; }
        .chain-status-list small { color:var(--muted); font-size:9px; }
        .chain-status-list ol { display:flex; gap:4px; margin:0; padding:0; list-style:none; }
        .chain-status-list li { width:10px; height:10px; border-radius:50%;
          border:1px solid var(--line); background:var(--surface-raised); }
        .chain-status-list li.ready { border-color:var(--success-color,#16845b);
          background:var(--success-color,#16845b); }
        .chain-status-list li.blocked { border-color:var(--warning-color,#b36b00);
          background:color-mix(in srgb,var(--warning-color,#b36b00) 22%,var(--surface)); }
        .chain-status-list li.completed { border-color:var(--success-color,#16845b);
          background:color-mix(in srgb,var(--success-color,#16845b) 35%,var(--surface)); }
        .sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px;
          overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
        .race-controls { display:grid; grid-template-columns:repeat(2,minmax(0,1fr));
          gap:8px; margin:0 0 12px; }
        .race-control { width:100%; min-height:44px; margin:0; }
        .start-race { color:var(--ink);
          background:color-mix(in srgb,var(--accent) 18%,var(--surface-raised));
          border:1px solid color-mix(in srgb,var(--accent) 30%,var(--line));
          font-size:14px; }
        .stop-race { min-height:44px; color:var(--muted);
          background:transparent; border:1px solid var(--line); font-size:13px; }
        .reset-race { min-height:44px; color:var(--muted);
          background:color-mix(in srgb,var(--error-color,#db4437) 7%,transparent);
          border:1px solid color-mix(in srgb,var(--error-color,#db4437) 24%,var(--line));
          font-size:13px; }
        .race-action-error { margin:-6px 0 18px; }
        .race-hint { max-width:96px; text-align:right; font-size:9px !important;
          white-space:normal !important; }
        .score-feedback,.champion,.last-reward { display:grid; gap:2px; margin:0 0 12px;
          padding:10px 13px; border:1px solid var(--line); border-radius:14px;
          background:color-mix(in srgb,var(--accent) 10%,var(--surface-raised)); }
        .score-feedback { grid-template-columns:auto auto minmax(0,1fr);
          align-items:center; gap:8px; padding-block:8px; }
        .score-feedback small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .score-feedback span,.champion span { color:var(--accent); font-size:10px;
          font-weight:850; letter-spacing:.12em; }
        .score-feedback strong,.champion strong { color:var(--ink); font-size:16px; }
        .score-feedback small,.champion small { color:var(--muted); font-size:10px; }
        .champion { text-align:center; background:
          radial-gradient(circle at 50% 0%,rgba(255,193,7,.2),transparent 66%),
          var(--surface-raised); }
        .champion strong { font-size:26px; }
        .chosen-reward,.last-reward { display:flex; align-items:center; justify-content:center;
          gap:10px; margin-top:8px; padding:9px 11px; border:1px solid var(--line);
          border-radius:12px; background:var(--surface); text-align:left; }
        .chosen-reward ha-icon,.last-reward ha-icon { color:var(--accent);
          --mdc-icon-size:28px; }
        .chosen-reward span,.last-reward span { display:grid; gap:1px; }
        .chosen-reward span small,.last-reward span small { color:var(--muted);
          font-size:8px; font-weight:850; letter-spacing:.12em; }
        .chosen-reward span strong,.last-reward span strong { font-size:13px; }
        .last-reward { justify-content:flex-start; margin-bottom:12px; }
        .reward-choice { display:grid; gap:7px; margin-top:10px; }
        .reward-choice > div { display:flex; justify-content:center; flex-wrap:wrap; gap:7px; }
        .reward-choice button { display:flex; align-items:center; gap:6px; min-height:40px;
          padding:7px 11px; color:var(--ink); background:var(--surface);
          border:1px solid var(--line); border-radius:11px; font-size:11px; }
        .reward-choice button:hover { border-color:var(--accent);
          background:color-mix(in srgb,var(--accent) 9%,var(--surface)); }
        .reward-choice ha-icon { --mdc-icon-size:20px; }
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
        .participant-grid button.selected { border-color:var(--accent);
          box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 22%,transparent);
          background:color-mix(in srgb,var(--accent) 14%,var(--surface)); }
        .participant-grid button.restricted { cursor:not-allowed; opacity:.46; }
        .participant-grid button small { color:var(--muted); font-size:10px; }
        .participant-grid img, .participant-grid span { width:58px; height:58px;
          display:grid; place-items:center; object-fit:cover; border-radius:50%;
          color:white; background:var(--accent); font-size:22px; }
        .picker-step { display:flex; align-items:center; gap:8px; margin:12px 0 10px;
          color:var(--muted); font-size:12px; font-weight:700; }
        .picker-step > strong { display:grid; place-items:center; width:22px; height:22px;
          color:var(--ink); border:1px solid var(--line); border-radius:8px;
          background:color-mix(in srgb,var(--accent) 16%,var(--surface)); }
        .bonus-panel { margin-top:18px; padding-top:4px; border-top:1px solid var(--line); }
        .normal-score-note { display:grid; gap:4px; margin-top:18px; padding:12px 14px;
          border:1px solid var(--line); border-radius:14px; background:var(--surface-soft);
          color:var(--muted); font-size:12px; line-height:1.45; }
        .normal-score-note strong { color:var(--ink); font-size:13px; }
        .bonus-panel label { display:grid; gap:6px; margin:10px 0; color:var(--muted);
          font-size:12px; font-weight:750; }
        .bonus-panel select { width:100%; min-height:46px; padding:8px 10px;
          color:var(--ink); background:var(--surface-raised);
          border:1px solid var(--line); border-radius:12px; font:inherit; }
        .fair-play-option { grid-template-columns:auto 1fr !important;
          align-items:center; padding:11px 12px; border:1px solid var(--line);
          border-radius:12px; background:var(--surface-raised); }
        .fair-play-option input { width:22px; height:22px; }
        .fair-play-option span { display:grid; gap:2px; }
        .fair-play-option strong { color:var(--ink); }
        .fair-play-option small,.bonus-note { color:var(--muted); font-size:10px; }
        .bonus-note { margin:7px 0 0; }
        .confirm-completion { width:100%; margin-top:14px; color:white;
          background:var(--accent); }
        .action-status, .action-error { margin:14px 0 0; text-align:center; font-size:13px; }
        .action-status { color:var(--muted); }
        .action-error { color:var(--error-color,#db4437); }
        .lane-heading { justify-content: space-between; margin-bottom: 4px;
          color: var(--ink); font-size: 11px; font-variant-numeric: tabular-nums; }
        .lane-heading small { color:var(--muted); font-size:10px; font-weight:600; }
        .driver { gap: 8px; }
        .remove-racer { min-width:26px; min-height:26px; padding:0;
          border:1px solid var(--line); border-radius:9px;
          color:var(--muted); background:transparent; font-size:17px; line-height:1; }
        .remove-racer:hover { color:var(--error-color,#db4437);
          border-color:color-mix(in srgb,var(--error-color,#db4437) 38%,var(--line)); }
        .driver > span, .driver > img { width: 24px; height: 24px; border-radius: 50%; object-fit: cover;
          display: grid; place-items: center; background: var(--accent); color: white; font-size: 11px; font-weight: 800; }
        .track { position: relative; height: 38px; overflow: hidden; border-radius: 11px;
          background: linear-gradient(180deg, #3b4050, #272b38); box-shadow: inset 0 2px 7px rgba(0,0,0,.28); }
        .track-lines { position: absolute; inset: 18px 12px auto; height: 2px;
          background: repeating-linear-gradient(90deg, rgba(255,255,255,.55) 0 12px, transparent 12px 24px); }
        .finish { position: absolute; right: 9px; inset-block: 0; width: 8px; opacity: .75;
          background: repeating-conic-gradient(#fff 0 25%, #151923 0 50%) 0 / 8px 8px; }
        .racer { position: absolute; z-index: 2; inset: 7px auto auto 5px; width: calc(100% - 55px);
          transform: translateX(var(--race-shift)); transition: transform .85s cubic-bezier(.16, 1, .3, 1); }
        .car { position: relative; width: 44px; height: 21px; border-radius: 8px 12px 6px 6px;
          background: linear-gradient(
            145deg,
            hsl(calc(215 + var(--lane) * 42) 52% 62%),
            hsl(calc(215 + var(--lane) * 42) 48% 46%)
          );
          filter: drop-shadow(0 4px 3px rgba(0,0,0,.3)); }
        .car::before { content: ""; position: absolute; left: 11px; top: -6px; width: 22px; height: 9px;
          border-radius: 10px 11px 0 0; background: inherit; }
        .window { position: absolute; z-index: 1; left: 18px; top: -3px; width: 12px; height: 6px;
          border-radius: 7px 7px 2px 2px; background: #dff7ff; opacity: .9; }
        .wheel { position: absolute; bottom: -4px; width: 9px; height: 9px; border: 2px solid #aeb5c7;
          border-radius: 50%; background: #151923; }
        .wheel.one { left: 8px; } .wheel.two { right: 7px; }
        footer { justify-content: space-between; margin-top: 12px; padding-top: 10px;
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
        @container (max-width: 620px) {
          .race-stage { grid-template-columns:minmax(0,1fr) minmax(220px,.9fr); gap:8px; }
          .stage-panel { padding:10px; border-radius:15px; }
          .section-heading { margin-bottom:8px; }
          .task-card { min-height:58px; grid-template-columns:48px minmax(0,1fr); }
          .task-image, .task-icon { width:48px; min-height:58px; }
          .task-copy { gap:6px; padding:7px 8px; }
          .task-copy h3 { font-size:12px; }
          .task-copy span { font-size:9px; }
          .complete { min-height:34px; padding-inline:8px; font-size:10px; }
        }
        @container (max-width: 460px) {
          .race-stage { grid-template-columns:1fr; }
          .tasks { grid-template-columns:repeat(2,minmax(0,1fr));
            max-height:none; overflow:visible; }
          .score-feedback { grid-template-columns:1fr; gap:2px; }
          .score-feedback small { white-space:normal; }
        }
        @container (max-width: 420px) {
          ha-card { padding: 16px; border-radius: 20px; }
          .team { margin-top: 14px; }
          header { align-items: flex-start; }
          h2 { overflow-wrap: anywhere; }
          .team-copy { gap: 8px; }
          .lane-heading { gap: 8px; }
          .driver { min-width: 0; }
          .driver strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
          .tasks { grid-template-columns:1fr; }
          .race-controls { grid-template-columns:1fr; }
          .task-card { grid-template-columns:48px minmax(0,1fr); }
          .task-image, .task-icon { width:48px; }
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
      name: "Chore Race",
      description:
        "Live family race with task completion, teamwork bonuses and ranking.",
      preview: true,
    });
  }
})();
