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

  const TASK_IMAGE_BASE = "/local/chore-race-icons";
  const TASK_IMAGES = [
    ["tidy-up", "Aufräumen", "tidy-up.png", "mdi:package-variant"],
    ["mop-floor", "Boden wischen", "mop-floor.png", "mdi:broom"],
    ["dust", "Abstauben", "dust.png", "mdi:feather"],
    ["organic-waste", "Bio-Müll", "organic-waste.png", "mdi:trash-can"],
    ["general-waste", "Restmüll", "general-waste.png", "mdi:delete"],
    ["paper", "Papier", "paper.png", "mdi:file-document"],
    ["plastic", "Plastik", "plastic.png", "mdi:bottle-soda"],
    ["clean-bathroom", "Bad reinigen", "clean-bathroom.png", "mdi:shower"],
    ["clean-toilet", "WC reinigen", "clean-toilet.png", "mdi:toilet"],
    ["laundry", "Wäsche", "laundry.png", "mdi:washing-machine"],
    ["dishwasher", "Geschirrspüler", "dishwasher.png", "mdi:dishwasher"],
    ["vacuum", "Staubsaugen", "vacuum.png", "mdi:vacuum"],
    ["clean-windows", "Fenster putzen", "clean-windows.png", "mdi:squeegee"],
    ["make-bed", "Bett machen", "make-bed.png", "mdi:bed"],
    ["cooking", "Kochen", "cooking.png", "mdi:pot-steam"],
    ["mow-lawn", "Rasen mähen", "mow-lawn.png", "mdi:lawn-mower"],
    ["feed-pets", "Tiere füttern", "feed-pets.png", "mdi:bowl-mix"],
  ];

  const today = () => {
    const date = new Date();
    date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    return date.toISOString().slice(0, 10);
  };

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
        active: chain.active !== false,
        steps: (Array.isArray(chain.steps) ? chain.steps : [])
          .filter((step) => step && typeof step === "object")
          .map((step, stepIndex) => ({
            ...step,
            id: String(step.id ?? `step-${stepIndex + 1}`),
            depends_on: Array.isArray(step.depends_on)
              ? step.depends_on.map(String)
              : step.depends_on
                ? [String(step.depends_on)]
                : [],
            sort_order: Number(step.sort_order ?? stepIndex),
          }))
          .sort((a, b) => a.sort_order - b.sort_order),
      }));
  };

  class ChoreRacePlannerCardEditor extends HTMLElement {
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
              value="${escapeHtml(this._config?.max_width ?? 960)}">
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
      this._data = {
        participants: [],
        choreTypes: [],
        tasks: [],
        areas: [],
        floors: [],
        recurrenceRules: [],
        rewards: [],
        taskChains: [],
      };
    }

    static getStubConfig() {
      return { title: "Chore Race Planer", max_width: 960 };
    }

    static getConfigElement() {
      return document.createElement("chore-race-planner-card-editor");
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
        const [participants, choreTypes, tasks, places, rewards] = await Promise.all([
          this._hass.callWS({ type: "chore_race/get_participants" }),
          this._hass.callWS({ type: "chore_race/get_chore_types" }),
          this._hass.callWS({ type: "chore_race/get_tasks" }),
          this._hass.callWS({ type: "chore_race/get_areas" }),
          this._hass.callWS({ type: "chore_race/get_rewards" }),
        ]);
        let recurrenceRules = [];
        let taskChains = [];
        try {
          recurrenceRules = await this._hass.callWS({
            type: "chore_race/get_recurrence_rules",
          });
        } catch (_error) {
          // Older backends do not expose recurrence management yet.
        }
        try {
          taskChains = normalizeTaskChains(
            await this._hass.callWS({ type: "chore_race/get_task_chains" }),
          );
        } catch (_error) {
          // Task chains are optional while older installations are upgraded.
        }
        this._data = {
          participants,
          choreTypes,
          tasks,
          recurrenceRules,
          rewards,
          taskChains,
          areas: places.filter((item) => item.kind !== "floor").sort((a, b) =>
            String(a.name).localeCompare(String(b.name), "de"),
          ),
          floors: places.filter((item) => item.kind === "floor").sort((a, b) =>
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

    async _submit(service, payload, successMessage) {
      return this._submitWS(
        `chore_race/${service}`,
        payload,
        successMessage,
      );
    }

    async _submitWS(type, payload, successMessage) {
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
        .querySelector('[data-form="reward"]')
        ?.addEventListener("submit", (event) => {
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          this._submit(
            "create_reward",
            {
              name: values.get("name").trim(),
              icon: values.get("icon") || "mdi:gift-outline",
              sort_order: Number(values.get("sort_order")) || 0,
            },
            "Belohnung wurde angelegt.",
          );
        });

      this.shadowRoot
        .querySelector('[data-form="task-chain"]')
        ?.addEventListener("submit", (event) => {
          event.preventDefault();
          const form = event.currentTarget;
          const values = new FormData(form);
          const steps = this._chainPayload(form);
          if (steps.length < 2) {
            const firstOptional = form.querySelectorAll(
              '[name="step_chore_type_id"]',
            )[1];
            firstOptional?.setCustomValidity(
              "Eine Aufgabenkette benötigt mindestens zwei Schritte.",
            );
            firstOptional?.reportValidity();
            firstOptional?.setCustomValidity("");
            return;
          }
          this._submitWS(
            "chore_race/create_task_chain",
            {
              name: values.get("name").trim(),
              task_date: values.get("task_date"),
              steps,
            },
            "Aufgabenkette wurde angelegt.",
          );
        });

      this.shadowRoot.querySelectorAll("[data-edit-chain]").forEach((form) => {
        form.addEventListener("submit", (event) => {
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          const steps = this._chainPayload(event.currentTarget);
          if (steps.length < 2) {
            const firstOptional = event.currentTarget.querySelectorAll(
              '[name="step_chore_type_id"]',
            )[1];
            firstOptional?.setCustomValidity(
              "Eine Aufgabenkette benötigt mindestens zwei Schritte.",
            );
            firstOptional?.reportValidity();
            firstOptional?.setCustomValidity("");
            return;
          }
          this._submitWS(
            "chore_race/update_task_chain",
            {
              chain_id: event.currentTarget.dataset.editChain,
              name: values.get("name").trim(),
              active: values.get("active") === "on",
              steps,
            },
            "Aufgabenkette wurde aktualisiert.",
          );
        });
      });
      this.shadowRoot.querySelectorAll("[data-delete-chain]").forEach((button) => {
        button.addEventListener("click", () => {
          if (
            !window.confirm(
              "Diese Aufgabenkette wirklich deaktivieren oder löschen? Bereits erledigte Aufgaben bleiben historisch erhalten.",
            )
          ) {
            return;
          }
          this._submitWS(
            "chore_race/delete_task_chain",
            { chain_id: button.dataset.deleteChain },
            "Aufgabenkette wurde entfernt.",
          );
        });
      });

      this.shadowRoot.querySelectorAll("[data-reward-action]").forEach((button) => {
        button.addEventListener("click", () => {
          const rewardId = button.dataset.rewardId;
          const action = button.dataset.rewardAction;
          if (action === "delete") {
            if (!window.confirm("Diese unbenutzte Belohnung endgültig löschen?")) return;
            this._submit(
              "delete_reward",
              { reward_id: rewardId },
              "Belohnung wurde gelöscht.",
            );
            return;
          }
          this._submit(
            "update_reward",
            {
              reward_id: rewardId,
              active: action === "activate",
            },
            action === "activate"
              ? "Belohnung wurde aktiviert."
              : "Belohnung wurde deaktiviert.",
          );
        });
      });

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
            "create_participant",
            {
              name: values.get("name").trim(),
              person_entity_id: personEntityId,
              avatar: person?.attributes?.entity_picture || null,
              role: values.get("role"),
              can_do_restricted_tasks:
                values.get("can_do_restricted_tasks") === "on",
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
            "create_chore_type",
            {
              name: values.get("name").trim(),
              default_race_points: Number(values.get("points")),
              icon: values.get("icon")?.trim() || "mdi:check",
              image: values.get("image") || null,
              difficulty: values.get("difficulty") || null,
              streak_enabled: values.get("streak_enabled") === "on",
              streak_max_bonus: Number(values.get("streak_max_bonus") || 0),
              default_copilot_points: Number(
                values.get("default_copilot_points") || 0,
              ),
              adult_only: values.get("adult_only") === "on",
            },
            "Aufgabentyp wurde angelegt.",
          );
        });

      this.shadowRoot.querySelectorAll('[name="icon"]').forEach((select) => {
        select.addEventListener("change", (event) => {
          event.currentTarget
            .closest("form")
            ?.querySelector(".icon-preview ha-icon")
            ?.setAttribute("icon", event.currentTarget.value);
        });
      });
      this.shadowRoot.querySelectorAll('[name="image"]').forEach((input) => {
        input.addEventListener("change", (event) => {
          if (!event.currentTarget.checked) return;
          const iconSelect = event.currentTarget
            .closest("form")
            ?.querySelector('[name="icon"]');
          const fallback = event.currentTarget.dataset.fallback;
          if (iconSelect && fallback) {
            iconSelect.value = fallback;
            iconSelect.dispatchEvent(new Event("change"));
          }
          const preview = event.currentTarget
            .closest("form")
            ?.querySelector("[data-image-preview]");
          if (preview) {
            preview.querySelector("img")?.setAttribute(
              "src",
              event.currentTarget.value,
            );
            const label = event.currentTarget
              .closest(".image-option")
              ?.querySelector("span")?.textContent;
            const previewLabel = preview.querySelector("[data-preview-label]");
            if (previewLabel && label) previewLabel.textContent = label;
          }
        });
      });

      const schedule = this.shadowRoot.querySelector('[name="schedule"]');
      const updateScheduleFields = () => {
        const recurring = schedule?.value !== "once";
        const intervalField = this.shadowRoot.querySelector(
          '[data-field="interval"]',
        );
        const weekdaysField = this.shadowRoot.querySelector(
          '[data-field="weekdays"]',
        );
        const dateLabel = this.shadowRoot.querySelector('[data-label="date"]');
        const preview = this.shadowRoot.querySelector("[data-schedule-preview]");
        if (intervalField) {
          intervalField.hidden = !["days", "completion_interval"].includes(
            schedule?.value,
          );
        }
        if (weekdaysField) weekdaysField.hidden = schedule?.value !== "weekdays";
        if (dateLabel) {
          dateLabel.firstChild.textContent = recurring ? "Startdatum" : "Datum";
        }
        if (preview) {
          const date = this.shadowRoot.querySelector('[name="date"]')?.value;
          const interval =
            this.shadowRoot.querySelector('[name="interval"]')?.value || "2";
          const descriptions = {
            once: `Einmalig am ${date || "gewählten Tag"}`,
            days: `Alle ${interval} Tage ab ${date || "dem Startdatum"}`,
            weekdays: "An den ausgewählten Wochentagen",
            completion_interval: `${interval} Tage nach der letzten Erledigung`,
            monthly: `Jeden Monat ab ${date || "dem Startdatum"}`,
            yearly: `Jedes Jahr ab ${date || "dem Startdatum"}`,
          };
          preview.textContent = descriptions[schedule?.value ?? "once"];
        }
      };
      schedule?.addEventListener("change", updateScheduleFields);
      this.shadowRoot
        .querySelector('[name="date"]')
        ?.addEventListener("change", updateScheduleFields);
      this.shadowRoot
        .querySelector('[name="interval"]')
        ?.addEventListener("input", updateScheduleFields);
      this.shadowRoot
        .querySelectorAll('[name="weekdays"]')
        .forEach((input) => input.addEventListener("change", updateScheduleFields));
      updateScheduleFields();

      const pointsForms = [
        this.shadowRoot.querySelector('[data-form="task"]'),
        ...this.shadowRoot.querySelectorAll("[data-edit-task]"),
      ].filter(Boolean);
      pointsForms.forEach((form) => {
        form
          .querySelector('[name="chore_type_id"]')
          ?.addEventListener("change", () => this._updatePointsPreview(form));
        form
          .querySelector('[name="location_id"]')
          ?.addEventListener("change", () => this._updatePointsPreview(form));
        form
          .querySelector('[name="race_points"]')
          ?.addEventListener("input", () => this._updatePointsPreview(form));
        this._updatePointsPreview(form);
      });

      this.shadowRoot.querySelectorAll("[data-edit-chore]").forEach((form) => {
        form.addEventListener("submit", (event) => {
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          this._submit(
            "update_chore_type",
            {
              chore_type_id: event.currentTarget.dataset.editChore,
              name: values.get("name").trim(),
              default_race_points: Number(values.get("points")),
              icon: values.get("icon") || null,
              image: values.get("image") || null,
              difficulty: values.get("difficulty") || null,
              streak_enabled: values.get("streak_enabled") === "on",
              streak_max_bonus: Number(values.get("streak_max_bonus") || 0),
              default_copilot_points: Number(
                values.get("default_copilot_points") || 0,
              ),
              adult_only: values.get("adult_only") === "on",
              confirmation_required:
                values.get("confirmation_required") === "on",
            },
            "Aufgabentyp wurde aktualisiert.",
          );
        });
      });
      this.shadowRoot.querySelectorAll("[data-disable-chore]").forEach((button) => {
        button.addEventListener("click", () => {
          if (!window.confirm("Diesen Aufgabentyp wirklich deaktivieren?")) return;
          this._submit(
            "update_chore_type",
            { chore_type_id: button.dataset.disableChore, active: false },
            "Aufgabentyp wurde deaktiviert.",
          );
        });
      });
      this.shadowRoot.querySelectorAll("[data-enable-chore]").forEach((button) => {
        button.addEventListener("click", () =>
          this._submit(
            "update_chore_type",
            { chore_type_id: button.dataset.enableChore, active: true },
            "Aufgabentyp wurde aktiviert.",
          ),
        );
      });
      this.shadowRoot.querySelectorAll("[data-delete-chore]").forEach((button) => {
        button.addEventListener("click", () => {
          if (
            !window.confirm(
              "Diesen unbenutzten Aufgabentyp endgültig löschen?",
            )
          ) {
            return;
          }
          this._submit(
            "delete_chore_type",
            { chore_type_id: button.dataset.deleteChore },
            "Aufgabentyp wurde gelöscht.",
          );
        });
      });
      this.shadowRoot.querySelectorAll("[data-toggle-rule]").forEach((button) => {
        button.addEventListener("click", () =>
          this._submitWS(
            "chore_race/update_recurrence_rule",
            {
              rule_id: button.dataset.toggleRule,
              active: button.dataset.active !== "true",
            },
            "Wiederholungsregel wurde aktualisiert.",
          ),
        );
      });
      this.shadowRoot.querySelectorAll("[data-delete-rule]").forEach((button) => {
        button.addEventListener("click", () => {
          if (!window.confirm("Diese Wiederholungsregel endgültig entfernen?")) return;
          this._submitWS(
            "chore_race/delete_recurrence_rule",
            { rule_id: button.dataset.deleteRule },
            "Wiederholungsregel wurde entfernt.",
          );
        });
      });

      this.shadowRoot
        .querySelector('[data-form="task"]')
        ?.addEventListener("submit", (event) => {
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          const schedule = values.get("schedule");
          const location = this._locationPayload(values.get("location_id"));
          const common = {
            chore_type_id: values.get("chore_type_id"),
            ...location,
            preferred_participant_id:
              values.get("preferred_participant_id") || null,
          };
          if (schedule !== "once") {
            this._submit(
              "create_recurrence_rule",
              {
                ...common,
                start_date: values.get("date"),
                frequency: schedule,
                interval:
                  ["days", "completion_interval"].includes(schedule)
                    ? Number(values.get("interval"))
                    : 1,
                weekdays: values.getAll("weekdays").map(Number),
              },
              "Wiederkehrende Aufgabe wurde gespeichert.",
            );
            return;
          }
          this._submit(
            "create_task",
            {
              ...common,
              date: values.get("date"),
            },
            "Aufgabe wurde für den gewählten Tag eingeplant.",
          );
        });
      this.shadowRoot.querySelectorAll("[data-edit-task]").forEach((form) => {
        form.addEventListener("submit", (event) => {
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          const location = this._locationPayload(values.get("location_id"));
          this._submit(
            "update_task",
            {
              task_id: event.currentTarget.dataset.editTask,
              chore_type_id: values.get("chore_type_id"),
              date: values.get("date"),
              ...location,
              preferred_participant_id:
                values.get("preferred_participant_id") || null,
              race_points: Number(values.get("race_points")),
              blocked: values.get("blocked") === "on",
            },
            "Offene Aufgabe wurde aktualisiert.",
          );
        });
      });
      this.shadowRoot.querySelectorAll("[data-delete-task]").forEach((button) => {
        button.addEventListener("click", () => {
          if (!window.confirm("Diese offene Aufgabe endgültig löschen?")) return;
          this._submit(
            "delete_task",
            { task_id: button.dataset.deleteTask },
            "Offene Aufgabe wurde gelöscht.",
          );
        });
      });
    }

    _participantOptions(selectedId = null) {
      return this._data.participants
        .filter((item) => item.active || item.id === selectedId)
        .map(
          (item) =>
            `<option value="${escapeHtml(item.id)}" ${
              item.id === selectedId ? "selected" : ""
            }>${escapeHtml(item.name)}${item.active ? "" : " (inaktiv)"}</option>`,
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

    _choreOptions(selectedId = null) {
      return this._data.choreTypes
        .filter((item) => item.active || item.id === selectedId)
        .map(
          (item) =>
            `<option value="${escapeHtml(item.id)}" ${
              item.id === selectedId ? "selected" : ""
            }>${escapeHtml(item.name)} · ${item.default_race_points} P${
              item.active ? "" : " (inaktiv)"
            }</option>`,
        )
        .join("");
    }

    _locationPayload(value) {
      const [kind, id] = String(value || "").split(":", 2);
      return {
        area_id: kind === "area" && id ? id : null,
        floor_id: kind === "floor" && id ? id : null,
      };
    }

    _floorAreaCount(floorId) {
      return this._data.areas.filter((area) => area.floor_id === floorId).length;
    }

    _updatePointsPreview(form) {
      const preview = form?.querySelector("[data-points-preview]");
      if (!preview) return;
      const choreId = form.querySelector('[name="chore_type_id"]')?.value;
      const chore = this._data.choreTypes.find((item) => item.id === choreId);
      if (!chore) {
        preview.textContent = "Aufgabentyp wählen, um die Punkte zu berechnen.";
        preview.classList.remove("warning");
        return;
      }
      const baseInput = form.querySelector('[name="race_points"]');
      const basePoints = Number(
        baseInput?.value ?? chore.default_race_points ?? 0,
      );
      const location = this._locationPayload(
        form.querySelector('[name="location_id"]')?.value,
      );
      if (!location.floor_id) {
        preview.textContent = `${basePoints} ${
          basePoints === 1 ? "Punkt" : "Punkte"
        } für diese Aufgabe`;
        preview.classList.remove("warning");
        return;
      }
      const floor = this._data.floors.find(
        (item) => item.floor_id === location.floor_id,
      );
      const areaCount = this._floorAreaCount(location.floor_id);
      if (!areaCount) {
        preview.textContent = `${floor?.name || "Diese Etage"} enthält noch keine zugeordneten Räume.`;
        preview.classList.add("warning");
        return;
      }
      const total = basePoints * areaCount;
      preview.textContent = `${basePoints} ${
        basePoints === 1 ? "Punkt" : "Punkte"
      } × ${areaCount} ${areaCount === 1 ? "Raum" : "Räume"} = ${total} Punkte`;
      preview.classList.remove("warning");
    }

    _locationOptions(areaId = null, floorId = null) {
      const selected = floorId
        ? `floor:${floorId}`
        : areaId
          ? `area:${areaId}`
          : "";
      const floors = this._data.floors
        .map(
          (item) =>
            `<option value="floor:${escapeHtml(item.floor_id)}" ${
              selected === `floor:${item.floor_id}` ? "selected" : ""
            }>${escapeHtml(item.name)}</option>`,
        )
        .join("");
      const areas = this._data.areas
        .map(
          (item) =>
            `<option value="area:${escapeHtml(item.area_id)}" ${
              selected === `area:${item.area_id}` ? "selected" : ""
            }>${escapeHtml(item.name)}</option>`,
        )
        .join("");
      return `<option value="" ${selected ? "" : "selected"}>Ohne Ort</option>
        ${floors ? `<optgroup label="Etagen">${floors}</optgroup>` : ""}
        ${areas ? `<optgroup label="Räume">${areas}</optgroup>` : ""}`;
    }

    _iconOptions(selectedIcon = "mdi:check") {
      const options = [
        ["mdi:check", "Allgemein"],
        ["mdi:dishwasher", "Geschirrspüler"],
        ["mdi:broom", "Kehren / Putzen"],
        ["mdi:vacuum", "Staubsaugen"],
        ["mdi:washing-machine", "Wäsche"],
        ["mdi:trash-can-outline", "Müll"],
        ["mdi:trash-can", "Bio-Müll"],
        ["mdi:delete", "Restmüll"],
        ["mdi:file-document", "Papier"],
        ["mdi:bottle-soda", "Plastik"],
        ["mdi:package-variant", "Aufräumen"],
        ["mdi:feather", "Abstauben"],
        ["mdi:shower", "Bad reinigen"],
        ["mdi:toilet", "Bad / WC"],
        ["mdi:bed", "Bett / Schlafzimmer"],
        ["mdi:food-apple-outline", "Küche / Essen"],
        ["mdi:flower", "Garten"],
        ["mdi:dog", "Haustier"],
        ["mdi:toy-brick-outline", "Spielzeug"],
      ];
      if (selectedIcon && !options.some(([value]) => value === selectedIcon)) {
        options.unshift([selectedIcon, "Aktuelles Symbol"]);
      }
      return options
        .map(
          ([value, label]) =>
            `<option value="${value}" ${
              value === selectedIcon ? "selected" : ""
            }>${label}</option>`,
        )
        .join("");
    }

    _choreTypeList() {
      if (!this._data.choreTypes.length) {
        return '<p class="empty">Noch keine Aufgabentypen angelegt.</p>';
      }
      return this._data.choreTypes
        .map((item) => {
          const difficultyOptions = [
            ["", "Keine"],
            ["easy", "Leicht"],
            ["medium", "Mittel"],
            ["hard", "Schwer"],
          ]
            .map(
              ([value, label]) =>
                `<option value="${value}" ${item.difficulty === value ? "selected" : ""}>${label}</option>`,
            )
            .join("");
          return `<li class="manageable ${item.active ? "" : "inactive"}">
            <span class="task-icon">${this._choreVisual(item)}</span>
            <details>
              <summary><strong>${escapeHtml(item.name)}</strong>
                <small>${item.default_race_points} Punkte · ${item.active ? "Aktiv" : "Inaktiv"}${
                  item.adult_only ? " · Nur Erwachsene" : ""
                }${item.streak_enabled ? ` · Serie bis +${item.streak_max_bonus}` : ""}${
                  item.confirmation_required ? " · Bestätigung" : ""
                }</small>
                <span class="edit-hint"><ha-icon icon="mdi:pencil"></ha-icon>
                  Bearbeiten</span>
              </summary>
              <form class="compact-form" data-edit-chore="${escapeHtml(item.id)}">
                <label>Name<input name="name" required maxlength="100"
                  value="${escapeHtml(item.name)}"></label>
                <div class="row">
                  <label>Punkte<input name="points" type="number" min="0" max="1000"
                    required value="${item.default_race_points}"></label>
                  <label>Schwierigkeit<select name="difficulty">${difficultyOptions}</select></label>
                </div>
                <input type="hidden" name="icon"
                  value="${escapeHtml(item.icon || "mdi:check")}">
                <details class="image-picker compact-picker">
                  <summary>${this._taskImagePreview(item.image)}
                    <span><strong>Aufgabenbild ändern</strong>
                    <small>${TASK_IMAGES.length} Motive anzeigen</small></span></summary>
                  <div>${this._taskImagePicker(item.image)}</div>
                </details>
                <fieldset class="race-options">
                  <legend>Rennwertung</legend>
                  <label class="check"><input name="streak_enabled" type="checkbox"
                    ${item.streak_enabled ? "checked" : ""}> Serienbonus aktiv</label>
                  <div class="row">
                    <label>Maximaler Serienbonus<input name="streak_max_bonus"
                      type="number" min="0" max="1000"
                      value="${Number(item.streak_max_bonus) || 0}"></label>
                    <label>Copilot-Punkte<input name="default_copilot_points"
                      type="number" min="0" max="1000"
                      value="${Number(item.default_copilot_points) || 0}"></label>
                  </div>
                </fieldset>
                <label class="check"><input name="adult_only" type="checkbox"
                  ${item.adult_only ? "checked" : ""}> Nur Erwachsene</label>
                <label class="check"><input name="confirmation_required" type="checkbox"
                  ${item.confirmation_required ? "checked" : ""}> Bestätigung erforderlich</label>
                <div class="actions"><button>Speichern</button>
                  ${
                    item.active
                      ? `<button type="button" class="secondary" data-disable-chore="${escapeHtml(item.id)}">Deaktivieren</button>`
                      : `<button type="button" class="secondary" data-enable-chore="${escapeHtml(item.id)}">Aktivieren</button>
                         <button type="button" class="danger" data-delete-chore="${escapeHtml(item.id)}">Endgültig löschen</button>`
                  }</div>
              </form>
            </details>
          </li>`;
        })
        .join("");
    }

    _rewardList() {
      if (!this._data.rewards.length) {
        return '<p class="empty">Noch keine Belohnungen angelegt.</p>';
      }
      return this._data.rewards
        .map(
          (reward) => `<li class="${reward.active ? "" : "inactive"}">
            <span class="task-icon"><ha-icon icon="${escapeHtml(
              reward.icon || "mdi:gift-outline",
            )}"></ha-icon></span>
            <span><strong>${escapeHtml(reward.name)}</strong>
              <small>${reward.active ? "Für Gewinner auswählbar" : "Inaktiv"}</small></span>
            <span class="rule-actions">
              <button class="secondary" data-reward-action="${
                reward.active ? "deactivate" : "activate"
              }" data-reward-id="${escapeHtml(reward.id)}">
                ${reward.active ? "Deaktivieren" : "Aktivieren"}</button>
              ${
                reward.active
                  ? ""
                  : `<button class="danger" data-reward-action="delete"
                      data-reward-id="${escapeHtml(reward.id)}">Löschen</button>`
              }
            </span>
          </li>`,
        )
        .join("");
    }

    _recurrenceRuleList() {
      const choreById = Object.fromEntries(
        this._data.choreTypes.map((item) => [item.id, item]),
      );
      const areaById = Object.fromEntries(
        this._data.areas.map((item) => [item.area_id, item.name]),
      );
      const floorById = Object.fromEntries(
        this._data.floors.map((item) => [item.floor_id, item.name]),
      );
      if (!this._data.recurrenceRules.length) {
        return '<p class="empty">Noch keine verwaltbaren Wiederholungsregeln.</p>';
      }
      const frequency = {
        days: (rule) => `Alle ${rule.interval || 1} Tage`,
        weekdays: (rule) => {
          const names = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
          return (rule.weekdays || []).map((day) => names[day]).join(", ");
        },
        completion_interval: (rule) =>
          `${rule.interval || 1} Tage nach Erledigung`,
        monthly: () => "Monatlich",
        yearly: () => "Jährlich",
      };
      return `<ul>${this._data.recurrenceRules
        .map((rule) => {
          const location =
            floorById[rule.floor_id] || areaById[rule.area_id] || "";
          return `<li class="${rule.active ? "" : "inactive"}">
          <span class="task-icon"><ha-icon icon="mdi:calendar-sync"></ha-icon></span>
          <span><strong>${escapeHtml(choreById[rule.chore_type_id]?.name || "Aufgabe")}</strong>
            <small>${escapeHtml(frequency[rule.frequency]?.(rule) || rule.frequency)}
              · ab ${escapeHtml(rule.start_date)}${location ? ` · ${escapeHtml(location)}` : ""}
              · ${rule.active ? "Aktiv" : "Pausiert"}</small></span>
          <span class="rule-actions">
            <button class="secondary" data-toggle-rule="${escapeHtml(rule.id)}"
              data-active="${rule.active}">${rule.active ? "Pausieren" : "Aktivieren"}</button>
            <button class="danger" data-delete-rule="${escapeHtml(rule.id)}">Entfernen</button>
          </span>
        </li>`;
        })
        .join("")}</ul>`;
    }

    _chainStepFields(chain = null) {
      const steps = chain?.steps?.length
        ? chain.steps
        : [
            { id: "step-1", chore_type_id: "", depends_on: [], sort_order: 0 },
            { id: "step-2", chore_type_id: "", depends_on: ["step-1"], sort_order: 1 },
            { id: "step-3", chore_type_id: "", depends_on: ["step-2"], sort_order: 2 },
          ];
      return steps
        .map((step, index) => {
          const previous = steps.slice(0, index);
          const dependency = step.depends_on?.[0] ?? "";
          return `<fieldset class="chain-step" data-chain-step>
            <legend>Schritt ${index + 1}</legend>
            <input type="hidden" name="step_id" value="${escapeHtml(step.id)}">
            <div class="chain-step-grid">
              <label>Aufgabe<select name="step_chore_type_id" ${index === 0 ? "required" : ""}>
                <option value="">${index === 0 ? "Bitte wählen" : "Kein weiterer Schritt"}</option>
                ${this._choreOptions(step.chore_type_id)}
              </select></label>
              <label>Startet nach<select name="step_depends_on" ${
                index === 0 ? "disabled" : ""
              }>
                <option value="">Ohne Abhängigkeit</option>
                ${previous
                  .map(
                    (candidate, previousIndex) =>
                      `<option value="${escapeHtml(candidate.id)}" ${
                        candidate.id === dependency ? "selected" : ""
                      }>Schritt ${previousIndex + 1}</option>`,
                  )
                  .join("")}
              </select></label>
            </div>
            <p>${index === 0
              ? "Dieser Schritt ist sofort bereit."
              : "Nur frühere Schritte können gewählt werden – dadurch entstehen keine Zyklen."}</p>
          </fieldset>`;
        })
        .join("");
    }

    _chainPayload(form) {
      const steps = [...form.querySelectorAll("[data-chain-step]")]
        .map((fieldset, index) => {
          const choreTypeId = fieldset.querySelector(
            '[name="step_chore_type_id"]',
          )?.value;
          if (!choreTypeId) return null;
          const id =
            fieldset.querySelector('[name="step_id"]')?.value || `step-${index + 1}`;
          const dependency = fieldset.querySelector(
            '[name="step_depends_on"]',
          )?.value;
          return {
            id,
            chore_type_id: choreTypeId,
            depends_on: dependency ? [dependency] : [],
            sort_order: index,
          };
        })
        .filter(Boolean);
      const includedIds = new Set(steps.map((step) => step.id));
      steps.forEach((step) => {
        step.depends_on = step.depends_on.filter((id) => includedIds.has(id));
      });
      return steps;
    }

    _taskChainList() {
      if (!this._data.taskChains.length) {
        return '<p class="empty">Noch keine Aufgabenketten angelegt.</p>';
      }
      const choreById = Object.fromEntries(
        this._data.choreTypes.map((item) => [item.id, item]),
      );
      const tasksByChain = this._data.tasks.reduce((result, task) => {
        if (task.chain_id) (result[task.chain_id] ??= []).push(task);
        return result;
      }, {});
      return `<ul class="chain-list">${this._data.taskChains
        .map((chain) => {
          const tasks = tasksByChain[chain.id] ?? [];
          const completed = tasks.filter((task) => task.status === "completed").length;
          const blocked = tasks.filter(
            (task) => task.status === "open" && task.blocked,
          ).length;
          const ready = tasks.filter(
            (task) => task.status === "open" && !task.blocked,
          ).length;
          return `<li class="manageable chain-item ${chain.active ? "" : "inactive"}">
            <span class="task-icon"><ha-icon icon="mdi:link-variant"></ha-icon></span>
            <details>
              <summary><strong>${escapeHtml(chain.name)}</strong>
                <small>${chain.steps.length} Schritte · ${ready} bereit · ${blocked} blockiert · ${completed} erledigt</small>
                <span class="edit-hint"><ha-icon icon="mdi:pencil"></ha-icon>
                  Bearbeiten</span>
              </summary>
              <ol class="chain-preview" aria-label="Schritte von ${escapeHtml(chain.name)}">
                ${chain.steps
                  .map((step, index) => {
                    const task = tasks.find(
                      (item) => item.chain_step_id === step.id,
                    );
                    const status =
                      task?.status === "completed"
                        ? "completed"
                        : task?.blocked
                          ? "blocked"
                          : "ready";
                    const label = {
                      completed: "Erledigt",
                      blocked: "Blockiert",
                      ready: "Bereit",
                    }[status];
                    return `<li class="chain-preview-step ${status}">
                      <span aria-hidden="true">${index + 1}</span>
                      <strong>${escapeHtml(
                        step.name ||
                          choreById[step.chore_type_id]?.name ||
                          "Aufgabe",
                      )}</strong>
                      <small class="status-badge">${label}</small>
                    </li>`;
                  })
                  .join("")}
              </ol>
              <form class="compact-form" data-edit-chain="${escapeHtml(chain.id)}">
                <label>Name<input required maxlength="100" name="name"
                  value="${escapeHtml(chain.name)}"></label>
                <label class="check"><input name="active" type="checkbox"
                  ${chain.active ? "checked" : ""}> Aufgabenkette aktiv</label>
                <div class="chain-editor">${this._chainStepFields(chain)}</div>
                <div class="actions">
                  <button>Änderungen speichern</button>
                  <button type="button" class="danger"
                    data-delete-chain="${escapeHtml(chain.id)}">Aufgabenkette löschen</button>
                </div>
              </form>
            </details>
          </li>`;
        })
        .join("")}</ul>`;
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
      const floorById = Object.fromEntries(
        this._data.floors.map((item) => [item.floor_id, item]),
      );
      const tasks = [...this._data.tasks]
        .filter((task) => task.status === "open")
        .sort((a, b) => a.date.localeCompare(b.date));

      if (!tasks.length) {
        return '<p class="empty">Noch keine offenen Aufgaben eingeplant.</p>';
      }
      return tasks
        .map((task) => {
          const chore = choreById[task.chore_type_id];
          const participant = participantById[task.preferred_participant_id];
          const area = areaById[task.area_id];
          const floor = floorById[task.floor_id];
          const multiplier = Number(task.points_multiplier) || 1;
          const pointLabel =
            task.floor_id && multiplier > 1
              ? `${task.base_race_points ?? task.race_points} × ${multiplier} Räume = ${task.race_points} P`
              : `${task.race_points} P`;
          const details = [
            task.date,
            floor?.name || area?.name,
            participant?.name,
            pointLabel,
          ]
            .filter(Boolean)
            .map(escapeHtml)
            .join(" · ");
          return `<li class="manageable">
            <span class="task-icon">${this._choreVisual(chore)}</span>
            <details>
              <summary><strong>${escapeHtml(chore?.name || "Aufgabe")}</strong>
                <small>${details}${task.blocked ? " · Blockiert" : ""}</small>
                <span class="edit-hint"><ha-icon icon="mdi:pencil"></ha-icon>
                  Bearbeiten</span>
              </summary>
              <form class="compact-form" data-edit-task="${escapeHtml(task.id)}">
                <label>Aufgabentyp<select required name="chore_type_id">
                  ${this._choreOptions(task.chore_type_id)}
                </select></label>
                <div class="row">
                  <label>Datum<input required type="date" name="date"
                    value="${escapeHtml(task.date)}"></label>
                  <label>Basispunkte<input required type="number" min="0" max="1000"
                    name="race_points"
                    value="${task.base_race_points ?? task.race_points}"></label>
                </div>
                <div class="row">
                  <label>Ort<select name="location_id">
                    ${this._locationOptions(task.area_id, task.floor_id)}
                  </select></label>
                  <label>Bevorzugte Person<select name="preferred_participant_id">
                    <option value="">Noch offen</option>
                    ${this._participantOptions(task.preferred_participant_id)}
                  </select></label>
                </div>
                <label class="check"><input name="blocked" type="checkbox"
                  ${task.blocked ? "checked" : ""}> Aufgabe blockieren</label>
                <p class="points-preview" data-points-preview></p>
                ${
                  task.source === "recurring"
                    ? '<p class="schedule-preview">Diese Änderung betrifft nur diese konkrete Aufgabe, nicht ihre Wiederholungsregel.</p>'
                    : ""
                }
                <div class="actions">
                  <button>Änderungen speichern</button>
                  <button type="button" class="danger"
                    data-delete-task="${escapeHtml(task.id)}">Aufgabe löschen</button>
                </div>
              </form>
            </details>
          </li>`;
        })
        .join("");
    }

    _choreVisual(chore) {
      if (chore?.image) {
        const image = chore.image.replace(
          /^\/chore-race-assets\//,
          `${TASK_IMAGE_BASE}/`,
        );
        return `<img src="${escapeHtml(image)}" alt="">`;
      }
      return `<ha-icon icon="${escapeHtml(chore?.icon || "mdi:check")}"></ha-icon>`;
    }

    _taskImagePicker(selectedImage = undefined) {
      const normalizedImage = selectedImage?.replace(
        /^\/chore-race-assets\//,
        `${TASK_IMAGE_BASE}/`,
      );
      const effectiveImage =
        normalizedImage || `${TASK_IMAGE_BASE}/${TASK_IMAGES[0][2]}`;
      return `${TASK_IMAGES.map(
        ([id, label, file, fallback]) => {
          const image = `${TASK_IMAGE_BASE}/${file}`;
          return `
          <label class="image-option">
            <input type="radio" name="image"
              value="${escapeHtml(image)}"
              data-id="${escapeHtml(id)}" data-fallback="${escapeHtml(fallback)}"
              ${image === effectiveImage ? "checked" : ""}>
            <img src="${escapeHtml(image)}" alt="">
            <span>${escapeHtml(label)}</span>
          </label>`;
        },
      ).join("")}`;
    }

    _taskImagePreview(selectedImage = undefined) {
      const normalizedImage = selectedImage?.replace(
        /^\/chore-race-assets\//,
        `${TASK_IMAGE_BASE}/`,
      );
      const selected =
        TASK_IMAGES.find(
          ([, , file]) => `${TASK_IMAGE_BASE}/${file}` === normalizedImage,
        ) ?? TASK_IMAGES[0];
      const image = `${TASK_IMAGE_BASE}/${selected[2]}`;
      return `<span class="selected-image" data-image-preview>
        <img src="${escapeHtml(image)}" alt="">
        <span data-preview-label>${escapeHtml(selected[1])}</span>
      </span>`;
    }

    _render() {
      if (!this.shadowRoot) return;
      const disabled = this._saving ? "disabled" : "";
      const hasChores = this._data.choreTypes.some((item) => item.active);
      this.shadowRoot.innerHTML = `
        <style>${this._styles()}</style>
        <ha-card>
          <header>
            <div><span class="eyebrow">CHORE RACE · VERWALTUNG</span>
              <h2>${escapeHtml(this._config.title || "Chore Race Planer")}</h2>
              <p class="subtitle">Familie, Aufgaben und Zeitpläne an einem Ort.</p></div>
            <button class="refresh" data-action="refresh" title="Neu laden"
              ${disabled}>↻</button>
          </header>
          ${this._loading ? '<div class="loading">Live-Daten werden geladen …</div>' : ""}
          ${this._notice ? `<p class="notice">${escapeHtml(this._notice)}</p>` : ""}
          ${this._error ? `<p class="error">${escapeHtml(this._error)}</p>` : ""}
          <nav class="overview" aria-label="Planer-Übersicht">
            <span><strong>${this._data.participants.filter((item) => item.active).length}</strong> Teilnehmer</span>
            <span><strong>${this._data.choreTypes.filter((item) => item.active).length}</strong> Aufgabentypen</span>
            <span><strong>${this._data.tasks.filter((item) => item.status === "open").length}</strong> offene Aufgaben</span>
            <span><strong>${this._data.taskChains.filter((item) => item.active).length}</strong> Aufgabenketten</span>
          </nav>
          <div class="forms">
            <form data-form="participant" class="create-panel">
              <div class="section-head"><span class="step">1</span><div>
                <h3>Teilnehmer</h3><p>Person aus Home Assistant übernehmen oder neu benennen.</p>
              </div></div>
              <label>Home-Assistant-Person<select name="person_entity_id">
                <option value="">Keine – Namen manuell eingeben</option>
                ${this._personOptions()}
              </select></label>
              <label>Name<input required maxlength="100" name="name"
                placeholder="z. B. Lina"></label>
              <div class="row">
                <label>Rolle<select name="role">
                  <option value="child">Kind</option>
                  <option value="adult">Erwachsen</option>
                </select></label>
                <label class="check"><input type="checkbox"
                  name="can_do_restricted_tasks"> Eingeschränkte Aufgaben erlaubt</label>
              </div>
              <button ${disabled}>Teilnehmer anlegen</button>
            </form>
            <form data-form="chore" class="create-panel">
              <div class="section-head"><span class="step">2</span><div>
                <h3>Aufgabentyp</h3><p>Motiv, Wertung und Schwierigkeit festlegen.</p>
              </div></div>
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
              <input type="hidden" name="icon"
                value="${escapeHtml(TASK_IMAGES[0][3])}">
              <details class="image-picker">
                <summary>${this._taskImagePreview()}
                  <span><strong>Aufgabenbild</strong>
                    <small>${TASK_IMAGES.length} Motive anzeigen</small></span></summary>
                <div>${this._taskImagePicker()}</div>
              </details>
              <details class="advanced-options">
                <summary>Rennwertung festlegen</summary>
                <fieldset class="race-options">
                  <label class="check"><input name="streak_enabled"
                    type="checkbox"> Serienbonus aktiv</label>
                  <div class="row">
                    <label>Maximaler Serienbonus<input name="streak_max_bonus"
                      type="number" min="0" max="1000" value="0"></label>
                    <label>Copilot-Punkte<input name="default_copilot_points"
                      type="number" min="0" max="1000" value="1"></label>
                  </div>
                  <label class="check"><input name="adult_only"
                    type="checkbox"> Nur Erwachsene</label>
                </fieldset>
              </details>
              <button ${disabled}>Aufgabentyp anlegen</button>
            </form>
            <section class="types"><div class="list-head"><div><h3>Aufgabentypen</h3>
              <p>Bestehende Vorlagen ansehen und bearbeiten.</p></div>
              <span>${this._data.choreTypes.length}</span></div>
              <ul>${this._choreTypeList()}</ul></section>
            <form data-form="task" class="create-panel task-panel">
              <div class="section-head"><span class="step">3</span><div>
                <h3>Aufgabe einplanen</h3><p>Einmaligen Termin oder Wiederholung erstellen.</p>
              </div></div>
              <label>Aufgabentyp<select required name="chore_type_id">
                <option value="">Bitte wählen</option>${this._choreOptions()}
              </select></label>
              <div class="row">
                <label data-label="date">Datum<input required type="date" name="date" value="${today()}"></label>
                <label>Ort<select name="location_id">
                  ${this._locationOptions()}</select></label>
              </div>
              <label>Bevorzugte Person<select name="preferred_participant_id">
                <option value="">Noch offen</option>${this._participantOptions()}
              </select></label>
              <div class="row">
                <label>Wiederholung<select name="schedule">
                  <option value="once">Einmalig</option>
                  <option value="days">Alle N Tage</option>
                  <option value="weekdays">Bestimmte Wochentage</option>
                  <option value="completion_interval">Nach letzter Erledigung</option>
                  <option value="monthly">Einmal pro Monat</option>
                  <option value="yearly">Einmal pro Jahr</option>
                </select></label>
                <label data-field="interval">Intervall in Tagen<input type="number" name="interval"
                  min="1" max="365" value="2"></label>
              </div>
              <fieldset class="weekday-picker" data-field="weekdays" hidden>
                <legend>Wochentage</legend>
                ${["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
                  .map(
                    (name, day) =>
                      `<label><input type="checkbox" name="weekdays" value="${day}"
                        ${day < 5 ? "checked" : ""}><span>${name}</span></label>`,
                  )
                  .join("")}
              </fieldset>
              <p class="schedule-preview" data-schedule-preview></p>
              <p class="points-preview" data-points-preview></p>
              <button ${disabled} ${hasChores ? "" : "disabled"}>Aufgabe einplanen</button>
            </form>
          </div>
          <section class="chains">
            <div class="list-head"><div><h3>Aufgabenketten</h3>
              <p>Mehrere Aufgaben in eine klare, zyklusfreie Reihenfolge bringen.</p></div>
              <span>${this._data.taskChains.length}</span></div>
            <form data-form="task-chain" class="compact-form chain-create">
              <div class="chain-basics">
                <label>Name<input required maxlength="100" name="name"
                  placeholder="z. B. Küche fertig machen"></label>
                <label>Startdatum<input required type="date" name="task_date"
                  value="${today()}"></label>
              </div>
              <div class="chain-editor">${this._chainStepFields()}</div>
              <p class="chain-help">Schritte werden von oben nach unten ausgeführt.
                Ein Schritt wird erst freigegeben, wenn sein Vorgänger erledigt ist.</p>
              <button ${disabled} ${hasChores ? "" : "disabled"}>
                Aufgabenkette anlegen</button>
            </form>
            ${this._taskChainList()}
          </section>
          <section class="rewards"><div class="list-head"><div><h3>Belohnungen</h3>
            <p>Der eindeutige Rennsieger darf nach dem Zieleinlauf einmal wählen.</p></div>
            <span>${this._data.rewards.filter((item) => item.active).length}</span></div>
            <form data-form="reward" class="compact-form reward-form">
              <div class="reward-fields">
                <label>Bezeichnung<input required maxlength="100" name="name"
                  placeholder="z. B. Filmabend"></label>
                <label>Motiv<select name="icon">
                  <option value="mdi:movie-open">Filmabend</option>
                  <option value="mdi:ice-cream">Eis essen</option>
                  <option value="mdi:food-pizza">Wunschessen</option>
                  <option value="mdi:weather-night">Länger aufbleiben</option>
                  <option value="mdi:gamepad-variant">Spielezeit</option>
                  <option value="mdi:crown">Champion-Wunsch</option>
                </select></label>
                <label>Reihenfolge<input type="number" name="sort_order"
                  min="0" max="1000" value="${this._data.rewards.length}"></label>
              </div>
              <button ${disabled}>Belohnung anlegen</button>
            </form>
            <ul>${this._rewardList()}</ul>
          </section>
          <section class="rules"><div class="list-head"><div><h3>Wiederholungsregeln</h3>
            <p>Automatische Zeitpläne pausieren oder verwalten.</p></div>
            <span>${this._data.recurrenceRules.length}</span></div>
            ${this._recurrenceRuleList()}</section>
          <section class="tasks"><div class="list-head"><div><h3>Offene Aufgaben</h3>
            <p>Geplante Aufgaben prüfen und korrigieren.</p></div>
            <span>${this._data.tasks.filter((item) => item.status === "open").length}</span></div>
            <ul>${this._taskList()}</ul></section>
        </ha-card>`;
      this._bindEvents();
    }

    _styles() {
      const maxWidth = Math.min(
        1400,
        Math.max(280, Number(this._config.max_width) || 960),
      );
      const accent = /^#[0-9a-f]{6}$/i.test(this._config.accent_color)
        ? this._config.accent_color
        : "#74829a";
      return `
        :host { display:block; min-width:0; container-type:inline-size;
          --ink:var(--primary-text-color,#172036);
          width:min(100%,${maxWidth}px); margin-inline:auto;
          --muted:var(--secondary-text-color,#667085); --accent:${accent};
          --surface:var(--ha-card-background,var(--card-background-color,#fbfbff));
          --surface-raised:var(--secondary-background-color,#f4f5f7);
          --panel:color-mix(in srgb,var(--surface-raised) 58%,var(--surface));
          --accent-soft:color-mix(in srgb,var(--accent) 10%,var(--surface));
          --line:color-mix(in srgb,var(--divider-color,rgba(120,130,145,.22)) 80%,transparent);
          --shadow:0 16px 42px rgba(12,20,35,.08); }
        * { box-sizing:border-box; }
        ha-card { display:block; overflow:hidden; color:var(--ink);
          padding:clamp(16px,2.4vw,26px);
          border:1px solid var(--line); border-radius:22px; background:var(--surface);
          box-shadow:var(--ha-card-box-shadow,var(--shadow));
          font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif); }
        header { position:relative; display:flex; align-items:center;
          justify-content:space-between; gap:16px; padding:2px 2px 16px; }
        header::after { content:""; position:absolute; right:56px; bottom:0; left:2px;
          height:1px; background:linear-gradient(90deg,var(--line),transparent); }
        .eyebrow { color:var(--accent); font-size:10px; font-weight:800; letter-spacing:.15em; }
        h2 { margin:4px 0 0; font-size:clamp(24px,4vw,32px); line-height:1.05;
          letter-spacing:-.025em; }
        h3 { margin:0; font-size:16px; }
        .subtitle,.section-head p,.list-head p { margin:5px 0 0; color:var(--muted);
          font-size:12px; line-height:1.45; }
        .refresh { flex:0 0 40px; width:40px; height:40px; min-height:40px;
          padding:0; font-size:20px; border-radius:12px; }
        .overview { display:grid; grid-template-columns:repeat(4,minmax(0,1fr));
          gap:8px; margin-top:14px; }
        .overview span { padding:9px 11px; color:var(--muted); background:var(--panel);
          border:1px solid var(--line); border-radius:12px; font-size:10px;
          letter-spacing:.01em; }
        .overview strong { display:block; margin-bottom:1px; color:var(--ink);
          font-size:17px; line-height:1.1; }
        .forms { display:grid; grid-template-columns:1fr;
          gap:12px; margin-top:12px; align-items:start; }
        form,.tasks,.types,.rules,.rewards,.chains { padding:15px; border:1px solid var(--line);
          border-radius:16px; background:var(--panel); }
        .section-head { display:flex; align-items:flex-start; gap:9px; margin-bottom:10px; }
        .step { display:grid; place-items:center; flex:0 0 24px; height:24px; color:var(--ink);
          background:var(--accent-soft);
          border:1px solid color-mix(in srgb,var(--accent) 24%,var(--line));
          border-radius:8px; font-size:11px; font-weight:800; }
        .list-head { display:flex; align-items:flex-start; justify-content:space-between;
          gap:12px; margin-bottom:10px; }
        .list-head > span { min-width:30px; padding:5px 8px; color:var(--muted);
          background:var(--surface); border:1px solid var(--line); border-radius:99px;
          text-align:center; font-size:11px; font-weight:700; }
        label { display:grid; gap:5px; margin:8px 0; color:var(--muted);
          font-size:11px; font-weight:700; }
        input,select { width:100%; min-height:38px; padding:7px 10px; color:var(--ink);
          background:color-mix(in srgb,var(--surface) 92%,transparent);
          border:1px solid var(--line); border-radius:9px; font:inherit; font-size:12px; }
        input:focus,select:focus { outline:2px solid color-mix(in srgb,var(--accent) 18%,transparent);
          border-color:var(--accent); }
        button { min-height:38px; padding:8px 13px; color:var(--ink);
          background:var(--surface); border:1px solid var(--line);
          border-radius:10px; font:inherit; font-size:12px; font-weight:750;
          cursor:pointer; transition:background .16s ease,border-color .16s ease,transform .16s ease; }
        button:hover { background:var(--accent-soft);
          border-color:color-mix(in srgb,var(--accent) 34%,var(--line)); }
        button:active { transform:translateY(1px); }
        form button { width:100%; margin-top:4px; }
        .create-panel > button { color:color-mix(in srgb,var(--ink) 88%,var(--accent));
          background:var(--accent-soft);
          border-color:color-mix(in srgb,var(--accent) 28%,var(--line)); }
        button:disabled { cursor:not-allowed; opacity:.45; }
        .row { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
        .check { display:flex; flex-direction:row; align-items:center; }
        .check input { width:18px; min-height:18px; }
        .weekday-picker { display:grid; grid-template-columns:repeat(7,minmax(0,1fr));
          gap:5px; margin:8px 0; padding:8px; border:1px solid var(--line);
          border-radius:11px; }
        .weekday-picker legend { padding:0 5px; color:var(--muted);
          font-size:10px; font-weight:800; }
        .weekday-picker label { position:relative; display:grid; place-items:center;
          min-height:36px; margin:0; cursor:pointer; }
        .weekday-picker input { position:absolute; opacity:0; pointer-events:none; }
        .weekday-picker span { display:grid; place-items:center; width:100%; height:32px;
          color:var(--muted); border:1px solid var(--line); border-radius:9px;
          background:var(--surface); font-size:10px; }
        .weekday-picker input:checked + span { color:var(--ink);
          border-color:color-mix(in srgb,var(--accent) 42%,var(--line));
          background:var(--accent-soft); }
        .advanced-options { margin:8px 0; }
        .advanced-options > summary { padding:8px 10px; color:var(--muted);
          background:var(--surface); border:1px solid var(--line);
          border-radius:9px; font-size:11px; font-weight:750; }
        .race-options { display:grid; gap:2px; margin:8px 0 0; padding:8px 10px;
          border:1px solid var(--line); border-radius:12px; }
        .race-options legend { padding:0 5px; color:var(--muted);
          font-size:11px; font-weight:800; }
        .task-icon ha-icon { width:20px; height:20px; }
        .task-icon img { width:30px; height:30px; object-fit:contain; }
        .image-picker { margin:8px 0; padding:0; border:0; }
        .image-picker > summary { padding:8px 10px; color:var(--ink);
          background:var(--surface); border:1px solid var(--line);
          border-radius:10px; font-size:11px; }
        .image-picker > summary { display:grid; grid-template-columns:auto 1fr;
          align-items:center; gap:10px; list-style:none; }
        .image-picker > summary::-webkit-details-marker { display:none; }
        .selected-image { display:flex; align-items:center; gap:8px; min-width:0; }
        .selected-image img { width:36px; height:36px; flex:0 0 36px; object-fit:contain;
          padding:3px; background:var(--surface-raised); border-radius:10px; }
        .selected-image > span { max-width:90px; overflow:hidden; color:var(--muted);
          font-size:10px; text-overflow:ellipsis; white-space:nowrap; }
        .image-picker > summary small { display:block; margin-top:3px;
          color:var(--muted); font-weight:400; }
        .image-picker[open] > summary { margin-bottom:8px; border-color:var(--accent); }
        .image-picker > div { display:grid;
          grid-template-columns:repeat(auto-fit,minmax(92px,1fr)); gap:8px; }
        .image-option { position:relative; display:grid; justify-items:center; gap:4px;
          min-width:0; padding:6px 5px; border:1px solid var(--line);
          border-radius:12px; background:var(--surface); cursor:pointer; }
        .image-option:has(input:checked) { border-color:var(--accent);
          box-shadow:0 0 0 2px color-mix(in srgb,var(--accent) 20%,transparent); }
        .image-option input { position:absolute; opacity:0; pointer-events:none; }
        .image-option img { width:50px; height:50px; object-fit:contain; }
        .image-option > ha-icon { width:44px; height:44px; }
        .image-option span { min-width:0; color:var(--muted); font-size:10px;
          text-align:center; overflow-wrap:anywhere; }
        .compact-picker { margin-block:10px; }
        .compact-picker .image-option img { width:44px; height:44px; }
        .loading,.notice,.error { margin:14px 0 0; padding:10px 12px; border-radius:10px;
          font-size:13px; }
        .loading { color:var(--primary-text-color);
          background:color-mix(in srgb,var(--info-color,#3b82f6) 14%,var(--surface)); }
        .notice { color:var(--primary-text-color);
          background:color-mix(in srgb,var(--success-color,#22a06b) 14%,var(--surface)); }
        .error { color:var(--primary-text-color);
          background:color-mix(in srgb,var(--error-color,#db4437) 14%,var(--surface)); }
        .schedule-preview { margin:4px 0 10px; color:var(--muted); font-size:12px; }
        .points-preview { margin:4px 0 10px; padding:9px 11px;
          color:var(--primary-text-color);
          background:color-mix(in srgb,var(--accent) 9%,var(--surface));
          border:1px solid color-mix(in srgb,var(--accent) 18%,var(--line));
          border-radius:10px; font-size:12px; font-weight:650; }
        .points-preview.warning { color:var(--error-color,#db4437);
          background:color-mix(in srgb,var(--error-color,#db4437) 8%,var(--surface));
          border-color:color-mix(in srgb,var(--error-color,#db4437) 22%,var(--line)); }
        [hidden] { display:none !important; }
        .tasks,.types,.rules,.rewards,.chains { margin-top:12px; }
        .reward-form { margin:0 0 10px; padding:10px; }
        .reward-fields { display:grid; grid-template-columns:2fr 1.4fr .7fr; gap:8px; }
        .reward-fields label { margin:0; }
        .chain-create { margin:0 0 10px; padding:10px; }
        .chain-basics,.chain-step-grid { display:grid;
          grid-template-columns:minmax(0,1.5fr) minmax(140px,1fr); gap:8px; }
        .chain-basics label,.chain-step-grid label { margin-block:0; }
        .chain-editor { display:grid; gap:7px; margin:9px 0; }
        .chain-step { min-width:0; margin:0; padding:8px 10px;
          border:1px solid var(--line); border-radius:11px; background:var(--surface); }
        .chain-step legend { padding:0 5px; color:var(--muted);
          font-size:10px; font-weight:800; }
        .chain-step p,.chain-help { margin:5px 0 0; color:var(--muted);
          font-size:10px; line-height:1.35; }
        .chain-list { margin-top:8px; }
        .chain-item > details[open] { width:100%; }
        .chain-preview { display:grid; grid-template-columns:1fr; gap:5px;
          margin:10px 0 0; padding:0; list-style:none; }
        .chain-preview-step { display:grid;
          grid-template-columns:24px minmax(0,1fr) auto; gap:7px; align-items:center;
          min-height:36px; padding:6px 8px; }
        .chain-preview-step > span { display:grid; place-items:center; width:23px;
          height:23px; border:1px solid var(--line); border-radius:8px;
          color:var(--muted); font-size:10px; font-weight:800; }
        .status-badge { margin:0 !important; padding:4px 7px; border-radius:99px;
          color:var(--muted); background:var(--surface-raised); font-weight:750 !important; }
        .chain-preview-step.ready .status-badge {
          color:var(--success-color,#16845b);
          background:color-mix(in srgb,var(--success-color,#16845b) 12%,var(--surface)); }
        .chain-preview-step.blocked .status-badge {
          color:var(--warning-color,#b36b00);
          background:color-mix(in srgb,var(--warning-color,#b36b00) 13%,var(--surface)); }
        .chain-preview-step.completed { opacity:.68; }
        .chain-preview-step.completed strong { text-decoration:line-through; }
        ul { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px;
          margin:0; padding:0; list-style:none; }
        li { display:flex; gap:10px; align-items:center; min-width:0; padding:9px 10px;
          border:1px solid var(--line); border-radius:11px; background:var(--surface);
          transition:border-color .16s ease,background .16s ease; }
        li:hover { border-color:color-mix(in srgb,var(--accent) 28%,var(--line));
          background:color-mix(in srgb,var(--accent) 3%,var(--surface)); }
        li > span:nth-child(2),li details { min-width:0; flex:1; }
        li.inactive { opacity:.68; }
        summary { cursor:pointer; }
        summary small { font-weight:400; }
        .manageable > details > summary { position:relative; padding-right:100px; }
        .edit-hint { position:absolute; top:50%; right:0; display:inline-flex;
          align-items:center; gap:4px; padding:5px 8px; color:var(--accent);
          border-radius:8px; font-size:10px; font-weight:750;
          transform:translateY(-50%); }
        .edit-hint ha-icon { width:15px; height:15px; }
        .compact-form { margin-top:10px; padding:11px; border:1px solid var(--line);
          border-radius:11px;
          background:color-mix(in srgb,var(--surface-raised) 74%,var(--surface)); }
        .actions,.rule-actions { display:flex; flex-wrap:wrap; gap:6px; }
        .actions button,.rule-actions button { width:auto; margin:0; }
        button.secondary { background:var(--surface); }
        button.danger { color:var(--primary-text-color);
          background:color-mix(in srgb,var(--error-color,#db4437) 14%,var(--surface)); }
        li small { display:block; margin-top:2px; color:var(--muted); font-size:10px;
          line-height:1.35; }
        .task-icon { display:grid; place-items:center; flex:0 0 34px; height:34px;
          color:var(--ink); background:color-mix(in srgb,var(--accent) 14%,var(--surface));
          border:1px solid color-mix(in srgb,var(--accent) 24%,var(--line)); border-radius:10px; }
        .empty { margin:0; padding:14px; color:var(--muted); text-align:center; }
        @media (prefers-reduced-motion:reduce) {
          *,*::before,*::after { animation-duration:.001ms !important;
            animation-iteration-count:1 !important; scroll-behavior:auto !important;
            transition-duration:.001ms !important; }
        }
        @container (min-width:760px) {
          .forms { grid-template-columns:repeat(2,minmax(0,1fr)); }
          .forms > .types,.forms > [data-form="task"] { grid-column:1/-1; }
          li.manageable:has(> details[open]) { grid-column:1/-1; }
        }
        @container (min-width:880px) {
          .forms { grid-template-columns:repeat(12,minmax(0,1fr)); }
          .forms > [data-form="participant"] { grid-column:span 5; }
          .forms > [data-form="chore"] { grid-column:span 7; }
          .forms > .types,.forms > [data-form="task"] { grid-column:1/-1; }
          .types ul { grid-template-columns:repeat(3,minmax(0,1fr)); }
          .types li.manageable:has(> details[open]) { grid-column:1/-1; }
        }
        @container (max-width:520px) {
          .row,ul { grid-template-columns:1fr; }
          ha-card { padding:14px; border-radius:17px; }
          header { align-items:flex-start; }
          h2 { overflow-wrap:anywhere; }
          .subtitle { max-width:28ch; }
          .overview { grid-template-columns:repeat(3,minmax(0,1fr)); gap:5px; }
          .overview span { min-width:0; padding:8px 6px; text-align:center;
            overflow-wrap:anywhere; }
          .overview strong { font-size:16px; }
          form,.tasks,.types,.rules,.rewards,.chains { padding:12px; }
          .reward-fields { grid-template-columns:1fr; }
          .overview { grid-template-columns:repeat(2,minmax(0,1fr)); }
          .chain-basics,.chain-step-grid { grid-template-columns:1fr; }
          .rule-actions { width:100%; padding-left:38px; }
          .manageable > details > summary { padding-right:32px; }
          .edit-hint { padding:4px; font-size:0; }
          .edit-hint ha-icon { width:18px; height:18px; }
          .image-picker > div { grid-template-columns:repeat(2,minmax(0,1fr)); }
        }
      `;
    }
  }

  if (!customElements.get("chore-race-planner-card")) {
    if (!customElements.get("chore-race-planner-card-editor")) {
      customElements.define(
        "chore-race-planner-card-editor",
        ChoreRacePlannerCardEditor,
      );
    }
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
