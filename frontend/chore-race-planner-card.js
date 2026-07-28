(() => {
  const escapeHtml = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  const messageFor = (error) =>
    error?.message ??
    error?.body?.message ??
    error?.code ??
    "Die Änderung konnte nicht gespeichert werden.";

  const today = () => {
    const date = new Date();
    date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    return date.toISOString().slice(0, 10);
  };

  class ChoreRacePlannerCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._config = {};
      this._hass = undefined;
      this._loading = true;
      this._saving = false;
      this._notice = "";
      this._error = "";
      this._data = { participants: [], choreTypes: [], tasks: [], areas: [] };
    }

    static getStubConfig() {
      return { title: "Chore Race Planer", max_width: 960 };
    }

    setConfig(config) {
      this._config = { ...config };
      this._render();
    }

    set hass(hass) {
      const firstConnection = !this._hass && hass;
      this._hass = hass;
      if (firstConnection && this.isConnected) this._load();
    }

    connectedCallback() {
      this._render();
      if (this._hass) this._load();
    }

    getCardSize() {
      return 8;
    }

    async _load() {
      if (!this._hass?.callWS) return;
      this._loading = true;
      this._render();
      try {
        const [participants, choreTypes, tasks, areas] = await Promise.all([
          this._hass.callWS({ type: "chore_race/get_participants" }),
          this._hass.callWS({ type: "chore_race/get_chore_types" }),
          this._hass.callWS({ type: "chore_race/get_tasks" }),
          this._hass.callWS({ type: "config/area_registry/list" }),
        ]);
        this._data = {
          participants,
          choreTypes,
          tasks,
          areas: [...areas].sort((a, b) =>
            String(a.name).localeCompare(String(b.name), "de"),
          ),
        };
        this._error = "";
      } catch (error) {
        this._error = messageFor(error);
      } finally {
        this._loading = false;
        this._render();
      }
    }

    async _submit(type, payload, successMessage) {
      this._saving = true;
      this._notice = "";
      this._error = "";
      this._render();
      try {
        await this._hass.callWS({ type, ...payload });
        this._notice = successMessage;
        await this._load();
      } catch (error) {
        this._error = messageFor(error);
      } finally {
        this._saving = false;
        this._render();
      }
    }

    _bindEvents() {
      this.shadowRoot.querySelector('[data-action="refresh"]')?.addEventListener(
        "click",
        () => this._load(),
      );

      this.shadowRoot
        .querySelector('[data-form="participant"]')
        ?.addEventListener("submit", (event) => {
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          const personEntityId = values.get("person_entity_id") || null;
          const person = personEntityId
            ? this._hass?.states?.[personEntityId]
            : undefined;
          this._submit(
            "chore_race/create_participant",
            {
              name: values.get("name").trim(),
              person_entity_id: personEntityId,
              avatar: person?.attributes?.entity_picture || null,
            },
            "Teilnehmer wurde angelegt.",
          );
        });

      this.shadowRoot
        .querySelector('[name="person_entity_id"]')
        ?.addEventListener("change", (event) => {
          const person = this._hass?.states?.[event.currentTarget.value];
          const nameInput = this.shadowRoot.querySelector(
            '[data-form="participant"] [name="name"]',
          );
          if (person && nameInput) {
            nameInput.value =
              person.attributes?.friendly_name ||
              person.entity_id.replace(/^person\./, "");
          }
        });

      this.shadowRoot
        .querySelector('[data-form="chore"]')
        ?.addEventListener("submit", (event) => {
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          this._submit(
            "chore_race/create_chore_type",
            {
              name: values.get("name").trim(),
              default_race_points: Number(values.get("points")),
              icon: values.get("icon").trim() || null,
              difficulty: values.get("difficulty") || null,
            },
            "Aufgabentyp wurde angelegt.",
          );
        });

      this.shadowRoot
        .querySelector('[data-form="task"]')
        ?.addEventListener("submit", (event) => {
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          this._submit(
            "chore_race/create_task",
            {
              chore_type_id: values.get("chore_type_id"),
              date: values.get("date"),
              area_id: values.get("area_id") || null,
              preferred_participant_id:
                values.get("preferred_participant_id") || null,
            },
            "Aufgabe wurde für den gewählten Tag eingeplant.",
          );
        });
    }

    _participantOptions() {
      return this._data.participants
        .filter((item) => item.active)
        .map(
          (item) =>
            `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`,
        )
        .join("");
    }

    _personOptions() {
      return Object.values(this._hass?.states ?? {})
        .filter((entity) => entity.entity_id.startsWith("person."))
        .sort((a, b) =>
          String(a.attributes?.friendly_name ?? a.entity_id).localeCompare(
            String(b.attributes?.friendly_name ?? b.entity_id),
            "de",
          ),
        )
        .map((entity) => {
          const label =
            entity.attributes?.friendly_name ||
            entity.entity_id.replace(/^person\./, "");
          return `<option value="${escapeHtml(entity.entity_id)}">${escapeHtml(label)}</option>`;
        })
        .join("");
    }

    _choreOptions() {
      return this._data.choreTypes
        .filter((item) => item.active)
        .map(
          (item) =>
            `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)} · ${item.default_race_points} P</option>`,
        )
        .join("");
    }

    _areaOptions() {
      return this._data.areas
        .map(
          (item) =>
            `<option value="${escapeHtml(item.area_id)}">${escapeHtml(item.name)}</option>`,
        )
        .join("");
    }

    _taskList() {
      const choreById = Object.fromEntries(
        this._data.choreTypes.map((item) => [item.id, item]),
      );
      const participantById = Object.fromEntries(
        this._data.participants.map((item) => [item.id, item]),
      );
      const areaById = Object.fromEntries(
        this._data.areas.map((item) => [item.area_id, item]),
      );
      const tasks = [...this._data.tasks]
        .filter((task) => task.status === "open")
        .sort((a, b) => a.date.localeCompare(b.date))
        .slice(0, 8);

      if (!tasks.length) {
        return '<p class="empty">Noch keine offenen Aufgaben eingeplant.</p>';
      }
      return tasks
        .map((task) => {
          const chore = choreById[task.chore_type_id];
          const participant = participantById[task.preferred_participant_id];
          const area = areaById[task.area_id];
          const details = [
            task.date,
            area?.name,
            participant?.name,
            `${task.race_points} P`,
          ]
            .filter(Boolean)
            .map(escapeHtml)
            .join(" · ");
          return `<li>
            <span class="task-icon">${escapeHtml(chore?.icon || "✓")}</span>
            <span><strong>${escapeHtml(chore?.name || "Aufgabe")}</strong>
              <small>${details}</small></span>
          </li>`;
        })
        .join("");
    }

    _render() {
      if (!this.shadowRoot) return;
      const disabled = this._saving ? "disabled" : "";
      const hasChores = this._data.choreTypes.some((item) => item.active);
      this.shadowRoot.innerHTML = `
        <style>${this._styles()}</style>
        <ha-card>
          <header>
            <div><span class="eyebrow">VERWALTUNG</span>
              <h2>${escapeHtml(this._config.title || "Chore Race Planer")}</h2></div>
            <button class="refresh" data-action="refresh" title="Neu laden"
              ${disabled}>↻</button>
          </header>
          ${this._loading ? '<div class="loading">Live-Daten werden geladen …</div>' : ""}
          ${this._notice ? `<p class="notice">${escapeHtml(this._notice)}</p>` : ""}
          ${this._error ? `<p class="error">${escapeHtml(this._error)}</p>` : ""}
          <div class="forms">
            <form data-form="participant">
              <h3><span>1</span> Teilnehmer</h3>
              <label>Home-Assistant-Person<select name="person_entity_id">
                <option value="">Keine – Namen manuell eingeben</option>
                ${this._personOptions()}
              </select></label>
              <label>Name<input required maxlength="100" name="name"
                placeholder="z. B. Lina"></label>
              <button ${disabled}>Teilnehmer anlegen</button>
            </form>
            <form data-form="chore">
              <h3><span>2</span> Aufgabentyp</h3>
              <label>Bezeichnung<input required maxlength="100" name="name"
                placeholder="z. B. Geschirrspüler"></label>
              <div class="row">
                <label>Punkte<input required min="0" max="1000" value="3"
                  type="number" name="points"></label>
                <label>Schwierigkeit<select name="difficulty">
                  <option value="">Keine</option><option value="easy">Leicht</option>
                  <option value="medium">Mittel</option><option value="hard">Schwer</option>
                </select></label>
              </div>
              <label>Icon<input maxlength="255" name="icon"
                placeholder="mdi:dishwasher"></label>
              <button ${disabled}>Aufgabentyp anlegen</button>
            </form>
            <form data-form="task">
              <h3><span>3</span> Aufgabe einplanen</h3>
              <label>Aufgabentyp<select required name="chore_type_id">
                <option value="">Bitte wählen</option>${this._choreOptions()}
              </select></label>
              <div class="row">
                <label>Datum<input required type="date" name="date" value="${today()}"></label>
                <label>Raum<select name="area_id"><option value="">Ohne Raum</option>
                  ${this._areaOptions()}</select></label>
              </div>
              <label>Bevorzugte Person<select name="preferred_participant_id">
                <option value="">Noch offen</option>${this._participantOptions()}
              </select></label>
              <button ${disabled} ${hasChores ? "" : "disabled"}>Aufgabe einplanen</button>
            </form>
          </div>
          <section class="tasks"><h3>Offene Aufgaben</h3><ul>${this._taskList()}</ul></section>
        </ha-card>`;
      this._bindEvents();
    }

    _styles() {
      const maxWidth = Math.min(
        1400,
        Math.max(360, Number(this._config.max_width) || 960),
      );
      const accent = /^#[0-9a-f]{6}$/i.test(this._config.accent_color)
        ? this._config.accent_color
        : "#74829a";
      return `
        :host { display:block; --ink:var(--primary-text-color,#172036);
          width:min(100%,${maxWidth}px); margin-inline:auto;
          --muted:var(--secondary-text-color,#667085); --accent:${accent};
          --surface:var(--ha-card-background,var(--card-background-color,#fbfbff));
          --surface-raised:var(--secondary-background-color,#f5f4ff);
          --line:var(--divider-color,rgba(105,92,255,.18)); }
        * { box-sizing:border-box; }
        ha-card { display:block; color:var(--ink); padding:clamp(18px,3vw,28px);
          border-radius:24px; background:linear-gradient(145deg,var(--surface),
            color-mix(in srgb,var(--surface) 92%,var(--accent)));
          box-shadow:0 18px 55px rgba(31,38,90,.14);
          font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif); }
        header { display:flex; align-items:center; justify-content:space-between; gap:16px; }
        .eyebrow { color:var(--accent); font-size:11px; font-weight:800; letter-spacing:.16em; }
        h2 { margin:4px 0 0; font-size:clamp(23px,5vw,32px); line-height:1; }
        h3 { margin:0 0 14px; font-size:15px; }
        h3 span { display:inline-grid; place-items:center; width:24px; height:24px;
          margin-right:7px; border-radius:8px; color:#fff; background:var(--accent); }
        .refresh { width:42px; height:42px; padding:0; font-size:22px; border-radius:14px; }
        .forms { display:grid; grid-template-columns:1fr;
          gap:14px; margin-top:20px; align-items:start; }
        form,.tasks { padding:16px; border:1px solid var(--line);
          border-radius:18px; background:var(--surface-raised); }
        label { display:grid; gap:6px; margin:10px 0; color:var(--muted);
          font-size:12px; font-weight:700; }
        input,select { width:100%; min-height:42px; padding:9px 11px; color:var(--ink);
          background:var(--surface); border:1px solid var(--line); border-radius:10px; font:inherit; }
        input:focus,select:focus { outline:3px solid rgba(105,92,255,.17);
          border-color:var(--accent); }
        button { min-height:42px; padding:9px 14px; color:var(--ink);
          background:color-mix(in srgb,var(--accent) 28%,var(--surface));
          border:1px solid color-mix(in srgb,var(--accent) 55%,var(--line));
          border-radius:11px; font:inherit; font-weight:750; cursor:pointer; }
        button:hover { background:color-mix(in srgb,var(--accent) 38%,var(--surface)); }
        form button { width:100%; margin-top:6px; }
        button:disabled { cursor:not-allowed; opacity:.45; }
        .row { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
        .loading,.notice,.error { margin:14px 0 0; padding:10px 12px; border-radius:10px;
          font-size:13px; }
        .loading { color:#4338ca; background:#eeecff; }
        .notice { color:#08775c; background:#ddfbf1; }
        .error { color:#a61b1b; background:#fee9e7; }
        .tasks { margin-top:14px; }
        ul { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px;
          margin:0; padding:0; list-style:none; }
        li { display:flex; gap:10px; align-items:center; padding:10px; border-radius:12px;
          background:color-mix(in srgb,var(--surface-raised) 92%,var(--accent)); }
        li small { display:block; margin-top:3px; color:var(--muted); font-size:11px; }
        .task-icon { display:grid; place-items:center; flex:0 0 32px; height:32px;
          color:#fff; background:var(--accent); border-radius:10px; }
        .empty { margin:0; padding:14px; color:var(--muted); text-align:center; }
        @media (max-width:520px) { .row,ul { grid-template-columns:1fr; } }
      `;
    }
  }

  if (!customElements.get("chore-race-planner-card")) {
    customElements.define("chore-race-planner-card", ChoreRacePlannerCard);
    window.customCards = window.customCards || [];
    window.customCards.push({
      type: "chore-race-planner-card",
      name: "Chore Race Planer",
      description: "Teilnehmer, Aufgabentypen und Aufgaben verwalten.",
      preview: true,
    });
  }
})();
