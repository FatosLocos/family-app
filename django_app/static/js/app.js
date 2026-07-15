(() => {
  const dialog = (id) => document.getElementById(id);
  const dialogs = () => document.querySelectorAll("dialog");
  const themeToggle = () => document.querySelector("[data-theme-toggle]");
  const networkStatus = () => document.querySelector("[data-network-status]");
  const probeCommandResults = new Map();

  const applyTheme = () => {
    const saved = localStorage.getItem("family-app-theme");
    const theme = saved || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.dataset.theme = theme;
    const button = themeToggle();
    if (button) button.setAttribute("aria-pressed", String(theme === "dark"));
  };

  const refreshIcons = () => window.lucide?.createIcons({ attrs: { "stroke-width": 1.8 } });

  const updateSonosPlayToggle = (card, isPlaying) => {
    const button = card?.querySelector("[data-sonos-play-toggle]");
    if (!button) return;
    button.classList.toggle("is-playing", isPlaying);
    button.title = isPlaying ? "Pauzeren" : "Afspelen";
    button.setAttribute("aria-label", isPlaying ? "Pauzeren" : "Afspelen");
    const icon = document.createElement("i");
    icon.dataset.lucide = isPlaying ? "pause" : "play";
    button.replaceChildren(icon);
    refreshIcons();
  };

  const formatSonosTime = (value) => {
    const seconds = Math.max(0, Math.floor(Number(value) || 0));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainder = String(seconds % 60).padStart(2, "0");
    return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${remainder}` : `${minutes}:${remainder}`;
  };

  const renderSonosProgress = (nowPlaying, position, duration) => {
    const label = nowPlaying.querySelector("[data-sonos-progress-label]");
    const wrap = nowPlaying.querySelector("[data-sonos-progress-wrap]");
    const fill = nowPlaying.querySelector("[data-sonos-progress-fill]");
    const safeDuration = Math.max(0, Number(duration) || 0);
    const safePosition = Math.min(safeDuration || Number.MAX_SAFE_INTEGER, Math.max(0, Number(position) || 0));
    if (label) label.textContent = safeDuration ? `${formatSonosTime(safePosition)} / ${formatSonosTime(safeDuration)}` : "";
    if (wrap) {
      wrap.hidden = !safeDuration;
      wrap.setAttribute("aria-valuemin", "0");
      wrap.setAttribute("aria-valuenow", String(Math.floor(safePosition)));
      wrap.setAttribute("aria-valuemax", String(Math.floor(safeDuration)));
    }
    if (fill) fill.style.width = `${safeDuration ? (safePosition / safeDuration) * 100 : 0}%`;
  };

  const setSonosProgressBase = (nowPlaying, attributes) => {
    const position = Number(attributes.sonos_position_seconds || 0);
    const duration = Number(attributes.sonos_duration_seconds || 0);
    nowPlaying.dataset.sonosPositionSeconds = String(position);
    nowPlaying.dataset.sonosDurationSeconds = String(duration);
    nowPlaying.dataset.sonosPlaybackState = attributes.sonos_playback_state || "";
    nowPlaying.dataset.sonosProgressMeasuredAt = String(Date.now());
    renderSonosProgress(nowPlaying, position, duration);
  };

  const tickSonosProgress = () => {
    if (document.hidden) return;
    document.querySelectorAll("[data-sonos-now-playing]").forEach((nowPlaying) => {
      const position = Number(nowPlaying.dataset.sonosPositionSeconds || 0);
      const duration = Number(nowPlaying.dataset.sonosDurationSeconds || 0);
      const measuredAt = Number(nowPlaying.dataset.sonosProgressMeasuredAt || Date.now());
      const playing = nowPlaying.dataset.sonosPlaybackState === "PLAYBACK_STATE_PLAYING";
      const estimatedPosition = playing ? position + (Date.now() - measuredAt) / 1000 : position;
      renderSonosProgress(nowPlaying, estimatedPosition, duration);
    });
  };

  const renderCastProgress = (nowPlaying, position, duration) => {
    const label = nowPlaying.querySelector("[data-cast-progress-label]");
    const wrap = nowPlaying.querySelector("[data-cast-progress-wrap]");
    const fill = nowPlaying.querySelector("[data-cast-progress-fill]");
    const safeDuration = Math.max(0, Number(duration) || 0);
    const safePosition = Math.min(safeDuration || Number.MAX_SAFE_INTEGER, Math.max(0, Number(position) || 0));
    if (label) label.textContent = safeDuration ? `${formatSonosTime(safePosition)} / ${formatSonosTime(safeDuration)}` : "";
    if (wrap) {
      wrap.hidden = !safeDuration;
      wrap.setAttribute("aria-valuemin", "0");
      wrap.setAttribute("aria-valuenow", String(Math.floor(safePosition)));
      wrap.setAttribute("aria-valuemax", String(Math.floor(safeDuration)));
    }
    if (fill) fill.style.width = `${safeDuration ? (safePosition / safeDuration) * 100 : 0}%`;
  };

  const setCastProgressBase = (nowPlaying, attributes) => {
    const position = Number(attributes.cast_position || 0);
    const duration = Number(attributes.cast_duration || 0);
    nowPlaying.dataset.castPositionSeconds = String(position);
    nowPlaying.dataset.castDurationSeconds = String(duration);
    nowPlaying.dataset.castPlaybackState = attributes.cast_player_state || "";
    nowPlaying.dataset.castProgressMeasuredAt = String(Date.now());
    renderCastProgress(nowPlaying, position, duration);
  };

  const tickCastProgress = () => {
    if (document.hidden) return;
    document.querySelectorAll("[data-cast-now-playing]").forEach((nowPlaying) => {
      const position = Number(nowPlaying.dataset.castPositionSeconds || 0);
      const duration = Number(nowPlaying.dataset.castDurationSeconds || 0);
      const measuredAt = Number(nowPlaying.dataset.castProgressMeasuredAt || Date.now());
      const playing = nowPlaying.dataset.castPlaybackState === "PLAYING";
      const estimatedPosition = playing ? position + (Date.now() - measuredAt) / 1000 : position;
      renderCastProgress(nowPlaying, estimatedPosition, duration);
    });
  };

  const showToast = ({ message, level = "info" }) => {
    if (!message) return;
    let stack = document.querySelector(".toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toast-stack";
      stack.setAttribute("aria-live", "polite");
      document.querySelector(".app-main")?.prepend(stack);
    }
    const toast = document.createElement("div");
    toast.className = `toast toast-${level}`;
    const icon = document.createElement("i");
    icon.dataset.lucide = level === "error" ? "circle-alert" : "circle-check";
    toast.append(icon, document.createTextNode(message));
    stack.append(toast);
    refreshIcons();
    window.setTimeout(() => toast.remove(), 4200);
  };

  const setHomeCardState = (card, action) => {
    const state = card?.querySelector("[data-home-state]");
    const labels = { on: "Aan", off: "Uit", active: "Actief" };
    if (!state || !labels[action]) return;
    const dot = document.createElement("span");
    dot.className = `state-dot${action === "off" ? "" : " is-on"}`;
    state.replaceChildren(dot, document.createTextNode(labels[action]));
    if (action === "on" || action === "off") {
      const powerToggle = card.querySelector("[data-power-toggle]");
      const powerForm = powerToggle?.closest("form");
      const isOn = action === "on";
      powerToggle?.classList.toggle("is-on", isOn);
      if (powerToggle) {
        powerToggle.title = isOn ? "Uitschakelen" : "Inschakelen";
        powerToggle.setAttribute("aria-label", isOn ? "Uitschakelen" : "Inschakelen");
      }
      if (powerForm) powerForm.action = powerForm.action.replace(/\/(on|off)\/$/, isOn ? "/off/" : "/on/");
    }
  };

  const markHomeControlValuesConfirmed = (fields) => {
    fields.forEach((field) => {
      field.dataset.confirmedValue = field.value;
      if (field.type === "checkbox") field.dataset.confirmedChecked = String(field.checked);
    });
  };

  const restoreHomeControlValues = (fields) => {
    fields.forEach((field) => {
      if (field.dataset.confirmedValue !== undefined) field.value = field.dataset.confirmedValue;
      if (field.type === "checkbox" && field.dataset.confirmedChecked !== undefined) field.checked = field.dataset.confirmedChecked === "true";
      if (field.matches("[data-temperature-slider]")) updateTemperatureAppearance(field);
      if (field.matches("[data-color-value]")) updateColorPicker(field.closest("[data-color-picker]"));
    });
  };

  const finishPendingProbeControl = (payload) => {
    const commandId = String(payload?.command_id || "");
    if (!commandId) return;
    const forms = [...document.querySelectorAll(`[data-probe-command-id="${CSS.escape(commandId)}"]`)];
    if (!forms.length) {
      // A very fast local device can reply before the HTTP response has
      // attached the command id to its form. Keep that one result briefly.
      probeCommandResults.set(commandId, payload);
      window.setTimeout(() => {
        if (probeCommandResults.get(commandId) === payload) probeCommandResults.delete(commandId);
      }, 10000);
      return;
    }
    forms.forEach((form) => {
      const fields = [...form.querySelectorAll("input:not([type='hidden']), input[data-color-value], select")];
      if (payload.succeeded) markHomeControlValuesConfirmed(fields);
      else restoreHomeControlValues(fields);
      delete form.dataset.probeCommandId;
    });
    probeCommandResults.delete(commandId);
    if (!payload.succeeded) {
      showToast({ message: payload.error || "De lokale bediening kon niet worden uitgevoerd.", level: "error" });
    }
  };

  const updateHomeControl = ({ entity_id: entityId, action, value, state, member_light_ids: memberLightIds = [], sonos_group_id: sonosGroupId = "", sonos_volume: sonosVolume, sonos_muted: sonosMuted }) => {
    const card = document.querySelector(`[data-home-entity-id="${CSS.escape(String(entityId || ""))}"]`);
    const resultingState = state || { on: "on", off: "off", activate: "active", brightness: "on", color_temperature: "on", color: "on", effect: "on" }[action];
    if (!resultingState) return;
    setHomeCardState(card, resultingState);
    if (card && sonosVolume !== null && sonosVolume !== undefined) {
      const volume = card.querySelector("[data-sonos-volume]");
      if (volume) volume.textContent = `Volume ${sonosVolume}%`;
    }
    if (card && ["mute", "unmute"].includes(action)) {
      const muted = card.querySelector("[data-sonos-muted]");
      if (muted) {
        muted.textContent = sonosMuted ? "Gedempt" : "Geluid aan";
        muted.classList.toggle("is-muted", Boolean(sonosMuted));
      }
    }
    if (card && ["on", "off", "play_pause"].includes(action)) {
      const playback = card.querySelector("[data-sonos-playback]");
      if (playback) playback.textContent = resultingState === "on" ? "Speelt af" : "Gepauzeerd";
      updateSonosPlayToggle(card, resultingState === "on");
    }
    if (sonosGroupId && ["on", "off", "play_pause"].includes(action)) {
      document.querySelectorAll(`[data-sonos-group-id="${CSS.escape(String(sonosGroupId))}"]`).forEach((memberCard) => {
        if (memberCard !== card) setHomeCardState(memberCard, resultingState);
      });
    }
    memberLightIds.forEach((lightId) => {
      document.querySelectorAll(`[data-hue-light-id="${CSS.escape(String(lightId))}"]`).forEach((memberCard) => {
        setHomeCardState(memberCard, resultingState);
        if (action === "brightness" || action === "color_temperature") {
          const selector = action === "brightness" ? ".hue-brightness input" : ".hue-temperature input";
          const slider = memberCard.querySelector(selector);
          if (slider && value) {
            slider.value = value;
            slider.dataset.confirmedValue = value;
            if (slider.matches("[data-temperature-slider]")) updateTemperatureAppearance(slider);
          }
        }
        if (action === "color" && value) {
          const colorValue = memberCard.querySelector("[data-color-value]");
          if (colorValue) {
            colorValue.value = value;
            colorValue.dataset.confirmedValue = value;
            updateColorPicker(colorValue.closest("[data-color-picker]"));
          }
        }
      });
    });
    if (action === "brightness" && value) {
      const brightness = card?.querySelector(".hue-brightness input");
      if (brightness) {
        brightness.value = value;
        brightness.dataset.confirmedValue = value;
      }
    }
    if (action === "color" && value) {
      if (card?.matches("[data-hue-tint-card]")) {
        card.dataset.hueColor = value;
        card.dataset.hueColorList = value;
        card.dataset.hueTintMode = "color";
        refreshHomeCardTint(card);
      }
      memberLightIds.forEach((lightId) => {
        document.querySelectorAll(`[data-hue-light-id="${CSS.escape(String(lightId))}"]`).forEach((memberCard) => {
          memberCard.dataset.hueColor = value;
          memberCard.dataset.hueTintMode = "color";
          refreshHomeCardTint(memberCard);
        });
      });
    }
    if (action === "color_temperature" && value) {
      if (card?.matches("[data-hue-tint-card]")) {
        card.dataset.hueTemperature = value;
        card.dataset.hueTintMode = "temperature";
        refreshHomeCardTint(card);
      }
      memberLightIds.forEach((lightId) => {
        document.querySelectorAll(`[data-hue-light-id="${CSS.escape(String(lightId))}"]`).forEach((memberCard) => {
          memberCard.dataset.hueTemperature = value;
          memberCard.dataset.hueTintMode = "temperature";
          refreshHomeCardTint(memberCard);
        });
      });
    }
    if (action === "effect" && value) {
      const effectDialog = document.getElementById(`hue-effect-dialog-${entityId}`);
      effectDialog?.querySelectorAll("[data-hue-effect]").forEach((button) => {
        button.classList.toggle("is-active", button.dataset.hueEffect === value);
      });
    }
  };

  const updateSonosDialogControl = (form) => {
    const button = form.querySelector("button[type='submit'], button:not([type])");
    if (!button) return;
    const action = new URL(form.action, window.location.origin).pathname.split("/").filter(Boolean).at(-1) || "";
    if (action === "set_home_theater_eq") {
      const value = form.querySelector("input[name='value']")?.value;
      button.classList.toggle("is-active", value === "1");
      return;
    }
    if (action.startsWith("toggle_")) button.classList.toggle("is-active");
  };

  const registerHomeControls = () => {
    document.addEventListener("submit", async (event) => {
      const form = event.target.closest(".home-controls form, form.hue-color-dialog-form, form.hue-effect-choice-form, .sonos-controls-dialog form");
      if (!form || !window.fetch) return;
      event.preventDefault();
      const submitter = form.querySelector("button[type='submit'], button:not([type])");
      if (submitter?.disabled || form.dataset.pending === "true") return;
      const formData = new FormData(form);
      const fields = [...form.querySelectorAll("input:not([type='hidden']), input[data-color-value], select")];
      form.dataset.pending = "true";
      if (submitter) {
        submitter.disabled = true;
        submitter.setAttribute("aria-busy", "true");
      }
      fields.forEach((field) => { field.disabled = true; });
      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: formData,
          credentials: "same-origin",
          headers: { "HX-Request": "true", Accept: "text/html" },
        });
        const rawTrigger = response.headers.get("HX-Trigger");
        const triggers = rawTrigger ? JSON.parse(rawTrigger) : {};
        if (!response.ok) throw new Error("De bediening kon niet worden uitgevoerd.");
        if (triggers["family:toast"]?.level === "error") {
          restoreHomeControlValues(fields);
          showToast(triggers["family:toast"]);
          return;
        }
        const homeControl = triggers["family:home-control"];
        if (homeControl?.queued) {
          const commandId = String(homeControl.command_id || "");
          form.dataset.probeCommandId = commandId;
          const alreadyFinished = probeCommandResults.get(commandId);
          if (triggers["family:toast"]) showToast(triggers["family:toast"]);
          if (alreadyFinished) finishPendingProbeControl(alreadyFinished);
          return;
        }
        markHomeControlValuesConfirmed(fields);
        if (form.closest(".sonos-controls-dialog")) updateSonosDialogControl(form);
        if (triggers["family:toast"]) showToast(triggers["family:toast"]);
        if (homeControl) {
          updateHomeControl(homeControl);
          if (homeControl.refresh) window.setTimeout(() => window.location.reload(), 250);
        }
      } catch (error) {
        restoreHomeControlValues(fields);
        showToast({ message: error.message || "De bediening kon niet worden uitgevoerd.", level: "error" });
      } finally {
        delete form.dataset.pending;
        fields.forEach((field) => { field.disabled = false; });
        if (submitter) {
          submitter.disabled = false;
          submitter.removeAttribute("aria-busy");
        }
      }
    });
  };

  const updateTemperatureAppearance = (input) => {
    input.style.setProperty("--temperature-color", hueTemperatureColor(input.min, input.max, input.value));
  };

  const hueTemperatureColor = (minimum, maximum, value) => {
    const progress = Math.max(0, Math.min(1, (Number(value) - Number(minimum)) / (Number(maximum) - Number(minimum) || 1)));
    const cool = [244, 248, 255];
    const warm = [236, 166, 72];
    const color = cool.map((component, index) => Math.round(component + (warm[index] - component) * progress));
    return `rgb(${color.join(" ")})`;
  };

  const refreshHomeCardTint = (card) => {
    if (!card?.matches("[data-hue-tint-card]")) return;
    const colors = card.dataset.hueTintMode === "mixed"
      ? card.dataset.hueColorList.split(",").filter((color) => /^#[0-9a-f]{6}$/i.test(color)).slice(0, 4)
      : [card.dataset.hueTintMode === "temperature"
        ? hueTemperatureColor(card.dataset.hueTemperatureMin, card.dataset.hueTemperatureMax, card.dataset.hueTemperature)
        : card.dataset.hueColor].filter((color) => /^#[0-9a-f]{6}$/i.test(color) || color.startsWith("rgb("));
    if (!colors.length) {
      card.style.removeProperty("--home-hue-gradient");
      return;
    }
    const tint = (color) => `color-mix(in srgb, ${color} 14%, var(--surface))`;
    const stops = colors.length === 1
      ? `${tint(colors[0])} 0%, var(--surface) 76%`
      : colors.map((color, index) => `${tint(color)} ${(index / (colors.length - 1)) * 100}%`).join(", ");
    card.style.setProperty("--home-hue-gradient", `linear-gradient(135deg, ${stops})`);
  };

  const hexToHsv = (hex) => {
    const normalized = String(hex || "").trim().replace("#", "");
    if (!/^[0-9a-f]{6}$/i.test(normalized)) return { hue: 0, saturation: 0 };
    const rgb = [0, 2, 4].map((index) => Number.parseInt(normalized.slice(index, index + 2), 16) / 255);
    const maximum = Math.max(...rgb);
    const minimum = Math.min(...rgb);
    const delta = maximum - minimum;
    let hue = 0;
    if (delta) {
      if (maximum === rgb[0]) hue = 60 * (((rgb[1] - rgb[2]) / delta) % 6);
      else if (maximum === rgb[1]) hue = 60 * ((rgb[2] - rgb[0]) / delta + 2);
      else hue = 60 * ((rgb[0] - rgb[1]) / delta + 4);
    }
    return { hue: (hue + 360) % 360, saturation: maximum ? (delta / maximum) * 100 : 0 };
  };

  const hsvToHex = (hue, saturation, value = 100) => {
    const chroma = (value / 100) * (saturation / 100);
    const segment = hue / 60;
    const match = chroma * (1 - Math.abs((segment % 2) - 1));
    const [red, green, blue] = [[chroma, match, 0], [match, chroma, 0], [0, chroma, match], [0, match, chroma], [match, 0, chroma], [chroma, 0, match]][Math.floor(segment) % 6];
    const offset = value / 100 - chroma;
    return `#${[red, green, blue].map((component) => Math.round((component + offset) * 255).toString(16).padStart(2, "0")).join("")}`;
  };

  const updateColorPicker = (picker) => {
    const input = picker?.querySelector("[data-color-value]");
    const indicator = picker?.querySelector("[data-color-indicator]");
    if (!input || !indicator) return;
    const { hue, saturation } = hexToHsv(input.value);
    const angle = ((hue - 90) * Math.PI) / 180;
    const radius = (saturation / 100) * 41;
    indicator.style.left = `${50 + Math.cos(angle) * radius}%`;
    indicator.style.top = `${50 + Math.sin(angle) * radius}%`;
    indicator.style.backgroundColor = input.value;
  };

  const selectHueColor = (wheel, clientX, clientY) => {
    const picker = wheel.closest("[data-color-picker]");
    const input = picker?.querySelector("[data-color-value]");
    if (!picker || !input) return;
    const rect = wheel.getBoundingClientRect();
    const radius = Math.min(rect.width, rect.height) / 2;
    const horizontal = clientX - (rect.left + rect.width / 2);
    const vertical = clientY - (rect.top + rect.height / 2);
    const distance = Math.hypot(horizontal, vertical);
    if (distance > radius) return;
    const hue = (Math.atan2(vertical, horizontal) * 180 / Math.PI + 90 + 360) % 360;
    input.value = hsvToHex(hue, Math.min(100, (distance / radius) * 100));
    updateColorPicker(picker);
    input.closest("form")?.requestSubmit();
  };

  const registerHueColorPickers = () => {
    document.querySelectorAll("[data-color-picker]").forEach(updateColorPicker);
    document.addEventListener("click", (event) => {
      const wheel = event.target.closest("[data-color-wheel]");
      if (wheel && !wheel.disabled && wheel.closest("form")?.dataset.pending !== "true") selectHueColor(wheel, event.clientX, event.clientY);
    });
    document.addEventListener("keydown", (event) => {
      const wheel = event.target.closest("[data-color-wheel]");
      if (!wheel || wheel.disabled || wheel.closest("form")?.dataset.pending === "true" || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
      event.preventDefault();
      const picker = wheel.closest("[data-color-picker]");
      const input = picker?.querySelector("[data-color-value]");
      if (!input) return;
      const current = hexToHsv(input.value);
      const hue = (current.hue + (event.key === "ArrowLeft" ? -12 : event.key === "ArrowRight" ? 12 : 0) + 360) % 360;
      const saturation = Math.max(0, Math.min(100, current.saturation + (event.key === "ArrowDown" ? -10 : event.key === "ArrowUp" ? 10 : 0)));
      input.value = hsvToHex(hue, saturation);
      updateColorPicker(picker);
      input.closest("form")?.requestSubmit();
    });
  };

  const registerHueRangeControls = () => {
    document.querySelectorAll(".home-controls input:not([type='hidden']), .home-controls input[data-color-value], .home-controls select, .hue-color-dialog-form input[data-color-value], .sonos-controls-dialog select, .sonos-controls-dialog input").forEach((field) => {
      field.dataset.confirmedValue = field.value;
      if (field.type === "checkbox") field.dataset.confirmedChecked = String(field.checked);
    });
    document.querySelectorAll("[data-temperature-slider]").forEach(updateTemperatureAppearance);
    document.querySelectorAll("[data-hue-tint-card]").forEach(refreshHomeCardTint);
    document.addEventListener("input", (event) => {
      const temperature = event.target.closest("[data-temperature-slider]");
      if (temperature) updateTemperatureAppearance(temperature);
    });
    document.addEventListener("change", (event) => {
      const slider = event.target.closest("input[type='range'][data-auto-control]");
      if (!slider || slider.disabled) return;
      slider.closest("form")?.requestSubmit();
    });

    const temperatureIdleTimers = new WeakMap();
    const queueTemperatureUpdate = (form) => {
      window.clearTimeout(temperatureIdleTimers.get(form));
      temperatureIdleTimers.set(form, window.setTimeout(() => form.requestSubmit(), 1000));
    };
    document.addEventListener("click", (event) => {
      const button = event.target.closest("[data-temperature-step]");
      if (!button || button.disabled) return;
      const form = button.closest(".google-temperature-stepper");
      const input = form?.querySelector("[data-temperature-idle]");
      if (!form || !input) return;
      const next = Math.min(Number(input.max), Math.max(Number(input.min), Number(input.value || input.min) + Number(button.dataset.temperatureStep)));
      input.value = String(Math.round((next + Number.EPSILON) * 10) / 10);
      queueTemperatureUpdate(form);
    });
    document.addEventListener("input", (event) => {
      const input = event.target.closest("[data-temperature-idle]");
      if (input?.closest(".google-temperature-stepper")) queueTemperatureUpdate(input.closest("form"));
    });
    document.addEventListener("change", (event) => {
      const toggle = event.target.closest("[data-google-mode-toggle]");
      if (!toggle) return;
      const form = toggle.closest("form");
      const value = form?.querySelector("[data-google-mode-value]");
      if (!form || !value) return;
      value.value = toggle.checked ? "HEAT" : "OFF";
      form.requestSubmit();
    });
    document.addEventListener("change", (event) => {
      const toggle = event.target.closest("[data-google-eco-toggle]");
      if (!toggle) return;
      const form = toggle.closest("form");
      const value = form?.querySelector("[data-google-eco-value]");
      if (!form || !value) return;
      value.value = toggle.checked ? "MANUAL_ECO" : "OFF";
      form.requestSubmit();
    });
  };

  const registerHueSyncRefresh = () => {
    if (!document.querySelector("[data-hue-sync-pending]")) return;
    window.setTimeout(() => {
      if (!document.hidden && !document.querySelector(".home-search input:focus")) window.location.reload();
    }, 4000);
  };

  const formatHomeEventTime = (value) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("nl-NL", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(date);
  };

  const applyHomeRealtimeEntity = (entity) => {
    const card = document.querySelector(`[data-home-entity-id="${CSS.escape(String(entity?.id || ""))}"]`);
    if (!card) return;
    const attributes = entity.attributes || {};
    card.classList.toggle("is-unavailable", !entity.is_available);
    setHomeCardState(card, entity.state);
    if (entity.source === "google_home") {
      const temperature = card.querySelector("[data-google-temperature]");
      if (temperature && attributes.current_temperature !== null && attributes.current_temperature !== undefined) {
        temperature.textContent = `${Math.round(Number(attributes.current_temperature) * 10) / 10} °C`;
      }
      const humidity = card.querySelector("[data-google-humidity]");
      if (humidity && attributes.humidity !== null && attributes.humidity !== undefined) humidity.textContent = `${attributes.humidity}%`;
      const hvac = card.querySelector("[data-google-hvac]");
      if (hvac && attributes.hvac_status) {
        hvac.textContent = { HEATING: "Verwarmen", COOLING: "Koelen", OFF: "Uit" }[attributes.hvac_status] || attributes.hvac_status;
        hvac.classList.toggle("is-active", ["HEATING", "COOLING"].includes(attributes.hvac_status));
      }
      const connectivity = card.querySelector("[data-google-connectivity]");
      if (connectivity && attributes.google_connectivity) {
        const offline = attributes.google_connectivity === "OFFLINE";
        connectivity.textContent = offline ? "Niet verbonden" : "Verbonden";
        connectivity.classList.toggle("is-alert", offline);
      }
      const mode = card.querySelector("select[name='thermostat_mode']");
      if (mode && attributes.thermostat_mode) mode.value = attributes.thermostat_mode;
      const lastEvent = card.querySelector("[data-google-last-event]");
      const lastEventLabel = card.querySelector("[data-google-last-event-label]");
      const lastEventTime = card.querySelector("[data-google-last-event-time]");
      if (lastEvent && attributes.google_last_event) {
        lastEvent.hidden = false;
        if (lastEventLabel) lastEventLabel.textContent = attributes.google_last_event;
        if (lastEventTime && attributes.google_last_event_at) {
          lastEventTime.dateTime = attributes.google_last_event_at;
          lastEventTime.textContent = formatHomeEventTime(attributes.google_last_event_at);
        }
        showToast({ message: `${card.querySelector(".home-entity-heading strong")?.textContent || "Google Nest"}: ${attributes.google_last_event}`, level: "info" });
      }
      return;
    }
    if (entity.source === "home_connect") {
      const updateText = (selector, value) => {
        const element = card.querySelector(selector);
        if (element) element.textContent = value || "";
      };
      updateText("[data-home-connect-operation]", attributes.home_connect_operation || "Status onbekend");
      updateText("[data-home-connect-program]", attributes.home_connect_program || (attributes.home_connect_selected_program ? `Gekozen: ${attributes.home_connect_selected_program}` : ""));
      updateText("[data-home-connect-remaining]", attributes.home_connect_remaining_label ? `Nog ${attributes.home_connect_remaining_label}` : "");
      updateText("[data-home-connect-door]", attributes.home_connect_door_label);
      const progress = card.querySelector("[data-home-connect-progress]");
      if (progress && attributes.home_connect_program_progress !== null && attributes.home_connect_program_progress !== undefined) {
        progress.setAttribute("aria-valuenow", attributes.home_connect_program_progress);
        const fill = progress.querySelector("div > span");
        const label = progress.querySelector("strong");
        if (fill) fill.style.width = `${attributes.home_connect_program_progress}%`;
        if (label) label.textContent = `${attributes.home_connect_program_progress}%`;
      }
      const readiness = card.querySelector("[data-home-connect-start-status]");
      if (readiness) {
        const ready = Boolean(attributes.home_connect_can_start);
        readiness.classList.toggle("home-connect-remote-start-ready", ready);
        readiness.classList.toggle("home-connect-remote-start-note", !ready);
        readiness.textContent = ready ? "Remote Start klaar" : (attributes.home_connect_start_status || "Programma starten is nu niet beschikbaar.");
      }
      const lastEvent = card.querySelector("[data-home-connect-last-event]");
      if (lastEvent && attributes.home_connect_last_event) {
        lastEvent.hidden = false;
        const label = lastEvent.querySelector("[data-home-connect-last-event-label]");
        const timestamp = lastEvent.querySelector("[data-home-connect-last-event-time]");
        if (label) label.textContent = attributes.home_connect_last_event;
        if (timestamp && attributes.home_connect_last_event_at) {
          timestamp.dateTime = attributes.home_connect_last_event_at;
          timestamp.textContent = formatHomeEventTime(attributes.home_connect_last_event_at);
        }
        showToast({ message: `${card.querySelector(".home-entity-heading strong")?.textContent || "Home Connect"}: ${attributes.home_connect_last_event}`, level: "info" });
      }
      return;
    }
    if (entity.source === "google_cast") {
      const playback = card.querySelector("[data-cast-playback]");
      if (playback) {
        const labels = { PLAYING: "Speelt af", PAUSED: "Gepauzeerd", BUFFERING: "Bufferen", IDLE: "Gereed", UNKNOWN: "Gereed" };
        playback.textContent = labels[attributes.cast_player_state] || "Gereed";
        updateSonosPlayToggle(card, attributes.cast_player_state === "PLAYING");
      }
      const volume = card.querySelector("[data-cast-volume]");
      if (volume && attributes.cast_volume !== null && attributes.cast_volume !== undefined) {
        volume.textContent = attributes.cast_muted ? "Gedempt" : `Volume ${attributes.cast_volume}%`;
        const slider = card.querySelector(".sonos-volume input[type='range']");
        if (slider) {
          slider.value = attributes.cast_volume;
          slider.dataset.confirmedValue = attributes.cast_volume;
        }
      }
      let nowPlaying = card.querySelector("[data-cast-now-playing]");
      if (!nowPlaying && attributes.cast_title) {
        nowPlaying = document.createElement("div");
        nowPlaying.className = "sonos-now-playing cast-now-playing";
        nowPlaying.dataset.castNowPlaying = "";
        nowPlaying.innerHTML = '<div><strong data-cast-title></strong><small data-cast-artist></small><small data-cast-progress-label></small><span class="sonos-progress" data-cast-progress-wrap role="progressbar"><span><span data-cast-progress-fill></span></span></span></div>';
        const status = card.querySelector(".spotify-status");
        if (status) status.insertAdjacentElement("afterend", nowPlaying);
      }
      if (nowPlaying && attributes.cast_title) {
        const title = nowPlaying.querySelector("[data-cast-title]");
        const artist = nowPlaying.querySelector("[data-cast-artist]");
        if (title) title.textContent = attributes.cast_title;
        if (artist) artist.textContent = attributes.cast_artist || "";
        setCastProgressBase(nowPlaying, attributes);
      } else if (nowPlaying && !attributes.cast_title) {
        nowPlaying.remove();
      }
      return;
    }
    if (entity.source !== "sonos") return;
    const playback = card.querySelector("[data-sonos-playback]");
    if (playback) {
      const labels = { PLAYBACK_STATE_PLAYING: "Speelt af", PLAYBACK_STATE_BUFFERING: "Bufferen", PLAYBACK_STATE_PAUSED: "Gepauzeerd", PLAYBACK_STATE_IDLE: "Geen audio" };
      playback.textContent = labels[attributes.sonos_playback_state] || "Geen audio";
      updateSonosPlayToggle(card, attributes.sonos_playback_state === "PLAYBACK_STATE_PLAYING");
    }
    const volume = card.querySelector("[data-sonos-volume]");
    if (volume && attributes.sonos_volume !== null && attributes.sonos_volume !== undefined) {
      volume.textContent = `Volume ${attributes.sonos_volume}%`;
      const slider = card.querySelector(".sonos-volume input[type='range']");
      if (slider) {
        slider.value = attributes.sonos_volume;
        slider.dataset.confirmedValue = attributes.sonos_volume;
      }
    }
    const muted = card.querySelector("[data-sonos-muted]");
    if (muted) {
      muted.textContent = attributes.sonos_muted ? "Gedempt" : "Geluid aan";
      muted.classList.toggle("is-muted", Boolean(attributes.sonos_muted));
    }
    let nowPlaying = card.querySelector("[data-sonos-now-playing]");
    if (!nowPlaying && attributes.sonos_now_playing_title) {
      nowPlaying = document.createElement("div");
      nowPlaying.className = "sonos-now-playing";
      nowPlaying.dataset.sonosNowPlaying = "";
      nowPlaying.innerHTML = '<img alt="" data-sonos-artwork><div><strong data-sonos-title></strong><small data-sonos-artist></small><small data-sonos-album></small><small class="sonos-source" data-sonos-source></small><small data-sonos-progress-label></small><span class="sonos-progress" data-sonos-progress-wrap role="progressbar"><span><span data-sonos-progress-fill></span></span></span></div>';
      const status = card.querySelector(".sonos-status");
      if (status) status.insertAdjacentElement("afterend", nowPlaying);
    }
    if (nowPlaying && attributes.sonos_now_playing_title) {
      const text = (selector, value) => {
        const element = nowPlaying.querySelector(selector);
        if (element && value !== undefined) element.textContent = value || "";
      };
      text("[data-sonos-title]", attributes.sonos_now_playing_title);
      text("[data-sonos-artist]", attributes.sonos_now_playing_artist);
      text("[data-sonos-album]", attributes.sonos_now_playing_album);
      text("[data-sonos-source]", attributes.sonos_source_name);
      text("[data-sonos-progress-label]", [attributes.sonos_position, attributes.sonos_duration].filter(Boolean).join(" / "));
      setSonosProgressBase(nowPlaying, attributes);
      const artwork = nowPlaying.querySelector("[data-sonos-artwork]");
      if (artwork && attributes.sonos_now_playing_artwork) artwork.src = attributes.sonos_now_playing_artwork;
    } else if (nowPlaying && !attributes.sonos_now_playing_title) {
      nowPlaying.remove();
    }
  };

  const registerHomeRealtime = () => {
    const marker = document.querySelector("[data-home-realtime]");
    if (!marker || !window.WebSocket) return;
    const householdId = marker.dataset.householdId;
    if (!householdId) return;
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    let retryTimer;
    const connect = () => {
      const socket = new WebSocket(`${protocol}://${window.location.host}/ws/huis/${encodeURIComponent(householdId)}/`);
      socket.addEventListener("message", (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload?.type === "home.entity.updated") applyHomeRealtimeEntity(payload.entity);
          if (payload?.type === "home.control.result") finishPendingProbeControl(payload);
        } catch (_) {
          // Ignore malformed live events; the normal refresh remains available.
        }
      });
      socket.addEventListener("close", () => {
        if (!document.hidden) retryTimer = window.setTimeout(connect, 3000);
      });
      window.addEventListener("beforeunload", () => {
        window.clearTimeout(retryTimer);
        socket.close();
      }, { once: true });
    };
    connect();
  };

  const csrfToken = () => {
    const formToken = document.querySelector("input[name='csrfmiddlewaretoken']")?.value;
    if (formToken) return formToken;
    return document.cookie.split("; ").find((value) => value.startsWith("csrftoken="))?.split("=")[1] || "";
  };

  const registerGoogleLiveStreams = () => {
    document.querySelectorAll("[data-open-google-live]").forEach((button) => {
      button.addEventListener("click", async () => {
        const modal = button.nextElementSibling;
        if (!(modal instanceof HTMLDialogElement)) return;
        const status = modal.querySelector("[data-google-live-status]");
        const image = modal.querySelector("[data-google-live-image]");
        const stage = modal.querySelector(".google-live-stage");
        let video = modal.querySelector("[data-google-live-video]");
        if (!video && stage) {
          video = document.createElement("video");
          video.dataset.googleLiveVideo = "";
          video.autoplay = true;
          video.muted = true;
          video.playsInline = true;
          video.controls = true;
          video.hidden = true;
          stage.append(video);
        }
        openDialog(modal.id, button);
        if (status) {
          status.hidden = false;
          status.innerHTML = '<span class="google-live-loader" aria-hidden="true"></span><span>Livestream voorbereiden…</span>';
        }
        if (image) {
          image.hidden = true;
          image.removeAttribute("src");
        }
        if (video instanceof HTMLVideoElement) {
          video.hidden = true;
          video.pause();
          video.removeAttribute("src");
          video.load();
          video.onloadeddata = () => {
            if (status) status.hidden = true;
            video.hidden = false;
          };
          video.onerror = () => {
            if (status) {
              status.hidden = false;
              status.textContent = "Livestream kon niet worden geladen.";
            }
          };
        }
        try {
          const response = await fetch(button.dataset.liveStartUrl, { method: "POST", headers: { "X-CSRFToken": csrfToken(), Accept: "application/json" }, credentials: "same-origin" });
          const payload = await response.json();
          if (!response.ok) throw new Error(payload.error || "Livestream kon niet worden gestart.");
          if (video instanceof HTMLVideoElement) {
            video.src = `${payload.media_url}?session=${Date.now()}`;
            video.play().catch(() => {});
          }
        } catch (error) {
          if (status) status.textContent = error.message || "Livestream kon niet worden gestart.";
        }
      });
    });
    document.querySelectorAll(".google-live-dialog").forEach((modal) => {
      modal.addEventListener("close", () => {
        modal.querySelector("[data-google-live-image]")?.removeAttribute("src");
        const video = modal.querySelector("[data-google-live-video]");
        if (video instanceof HTMLVideoElement) {
          video.pause();
          video.removeAttribute("src");
          video.load();
        }
        const opener = [...document.querySelectorAll("[data-open-google-live]")].find((button) => button.nextElementSibling === modal);
        if (opener?.dataset.liveStopUrl) fetch(opener.dataset.liveStopUrl, { method: "POST", headers: { "X-CSRFToken": csrfToken() }, credentials: "same-origin" }).catch(() => {});
      });
    });
  };

  const refreshNetworkStatus = async () => {
    const status = networkStatus();
    if (!status) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 3500);
    try {
      // navigator.onLine is only a browser hint and is unreliable in embedded browsers.
      const response = await fetch("/healthz", { cache: "no-store", headers: { Accept: "application/json" }, signal: controller.signal });
      const connected = response.ok;
      status.hidden = connected;
      document.documentElement.toggleAttribute("data-offline", !connected);
    } catch (_) {
      // A blocked or cached browser fetch is not sufficient evidence that the app is offline.
      status.hidden = true;
      document.documentElement.toggleAttribute("data-offline", false);
    } finally {
      window.clearTimeout(timer);
    }
  };

  const openDialog = (target, trigger) => {
    const modal = dialog(target);
    if (!modal || modal.open) return;
    modal.dataset.returnFocus = trigger?.id || "";
    modal.showModal();
    modal.querySelector("input, select, textarea, button")?.focus({ preventScroll: true });
  };

  const closeDialog = (modal, restoreFocus = true) => {
    if (!modal?.open || modal.classList.contains("is-closing")) return;
    modal.classList.add("is-closing");
    window.setTimeout(() => {
      modal.close();
      modal.classList.remove("is-closing");
      const trigger = modal.dataset.returnFocus ? document.getElementById(modal.dataset.returnFocus) : null;
      if (restoreFocus) trigger?.focus({ preventScroll: true });
    }, 140);
  };

  const setFormState = (form) => {
    form.querySelectorAll("[required]").forEach((field) => {
      const isInvalid = !field.validity.valid && field.value !== "";
      field.classList.toggle("is-invalid", isInvalid);
      field.setAttribute("aria-invalid", String(isInvalid));
    });
  };

  const setSubmitting = (form) => {
    const submitter = form.querySelector("button[type='submit'], button:not([type])");
    if (!submitter || !form.checkValidity()) return;
    submitter.dataset.originalLabel = submitter.textContent;
    submitter.disabled = true;
    submitter.classList.add("is-pending");
    submitter.setAttribute("aria-busy", "true");
  };

  const registerHoverMenus = () => {
    const desktop = window.matchMedia("(min-width: 761px)");
    document.querySelectorAll("[data-hover-menu]").forEach((menu) => {
      let closeTimer;
      const clearTimer = () => window.clearTimeout(closeTimer);
      const open = () => {
        if (!desktop.matches) return;
        clearTimer();
        menu.open = true;
      };
      const close = () => {
        if (!desktop.matches) return;
        clearTimer();
        closeTimer = window.setTimeout(() => { menu.open = false; }, 260);
      };
      menu.addEventListener("pointerenter", open);
      menu.addEventListener("pointerleave", close);
      menu.addEventListener("focusin", clearTimer);
      menu.addEventListener("focusout", (event) => {
        if (!menu.contains(event.relatedTarget)) close();
      });
    });
  };

  const registerDialogs = () => {
    document.querySelectorAll("[data-open-dialog]").forEach((button, index) => {
      if (!button.id) button.id = `dialog-trigger-${index}`;
      button.addEventListener("click", () => openDialog(button.dataset.openDialog, button));
    });
    document.querySelectorAll("[data-close-dialog]").forEach((button) => {
      button.addEventListener("click", () => closeDialog(button.closest("dialog")));
    });
    dialogs().forEach((modal) => {
      modal.addEventListener("cancel", (event) => {
        event.preventDefault();
        closeDialog(modal);
      });
      modal.addEventListener("click", (event) => {
        if (event.target === modal) closeDialog(modal);
      });
    });
  };

  const registerSonosDialogTabs = () => {
    const categories = [
      { id: "now", label: "Nu", icon: "play", match: /afspeelpositie|afspeelmodus|^bron$|^tv en|slaaptimer/i },
      { id: "sound", label: "Geluid", icon: "audio-lines", match: /geluid afstellen|line-in|home-theatergeluid|uitvoer en kalibratie/i },
      { id: "music", label: "Muziek", icon: "music-2", match: /wekkers|wachtrij|favoriet|directe bron|muziekbibliotheek/i },
      { id: "speakers", label: "Speakers", icon: "speaker", match: /losse speakers|speakers groeperen|speakerinstellingen|^ruimte$/i },
      { id: "manage", label: "Beheer", icon: "settings-2", match: /fysieke speakeropstelling|stereopaar|room calibration|surround of sub|tv-autoplayruimte|tv-afstandsbediening/i },
    ];

    const categoryFor = (section) => {
      const text = section.querySelector("h3, summary")?.textContent?.trim() || "";
      return categories.find((category) => category.match.test(text))?.id || "manage";
    };

    document.querySelectorAll("[data-sonos-tabbed]").forEach((modal) => {
      if (modal.dataset.tabsReady === "true") return;
      const grid = modal.querySelector(".sonos-capability-grid");
      if (!grid) return;

      const sections = [...grid.children].filter((element) => element.tagName === "SECTION");
      const advanced = modal.querySelector(".sonos-advanced-controls");
      if (advanced) {
        sections.push(...[...advanced.children].filter((element) => element.tagName === "SECTION"));
        advanced.remove();
      }
      if (!sections.length) return;

      const tablist = document.createElement("div");
      tablist.className = "sonos-tablist";
      tablist.dataset.sonosTablist = "";
      tablist.setAttribute("role", "tablist");
      tablist.setAttribute("aria-label", "Extra Sonos-bediening");
      const panels = document.createElement("div");
      panels.className = "sonos-tab-panels";

      const grouped = new Map(categories.map((category) => [category.id, []]));
      sections.forEach((section) => grouped.get(categoryFor(section)).push(section));
      const visibleCategories = categories.filter((category) => grouped.get(category.id).length);

      visibleCategories.forEach((category, index) => {
        const tab = document.createElement("button");
        tab.type = "button";
        tab.className = "sonos-tab";
        tab.dataset.sonosTab = category.id;
        tab.id = `sonos-tab-${category.id}-${modal.id}`;
        tab.setAttribute("role", "tab");
        tab.setAttribute("aria-selected", String(index === 0));
        tab.setAttribute("aria-controls", `sonos-panel-${category.id}-${modal.id}`);
        tab.innerHTML = `<i data-lucide="${category.icon}"></i><span>${category.label}</span>`;
        tablist.append(tab);

        const panel = document.createElement("section");
        panel.className = "sonos-tab-panel";
        panel.dataset.sonosPanel = category.id;
        panel.id = `sonos-panel-${category.id}-${modal.id}`;
        panel.setAttribute("role", "tabpanel");
        panel.setAttribute("aria-labelledby", tab.id);
        panel.tabIndex = 0;
        panel.hidden = index !== 0;
        if (category.id === "manage") {
          const note = document.createElement("p");
          note.className = "sonos-advanced-note";
          note.textContent = "Wijzig hier alleen instellingen die niet nodig zijn voor dagelijkse bediening.";
          panel.append(note);
        }
        grouped.get(category.id).forEach((section) => panel.append(section));
        panels.append(panel);
      });

      const activate = (tab, focus = false) => {
        const target = tab.dataset.sonosTab;
        tablist.querySelectorAll("[data-sonos-tab]").forEach((candidate) => {
          const selected = candidate === tab;
          candidate.setAttribute("aria-selected", String(selected));
          candidate.tabIndex = selected ? 0 : -1;
        });
        panels.querySelectorAll("[data-sonos-panel]").forEach((panel) => { panel.hidden = panel.dataset.sonosPanel !== target; });
        if (focus) tab.focus({ preventScroll: true });
      };

      tablist.addEventListener("click", (event) => {
        const tab = event.target.closest("[data-sonos-tab]");
        if (tab) activate(tab);
      });
      tablist.addEventListener("keydown", (event) => {
        const tabs = [...tablist.querySelectorAll("[data-sonos-tab]")];
        const current = tabs.indexOf(document.activeElement);
        if (current < 0) return;
        const direction = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
        const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : direction ? (current + direction + tabs.length) % tabs.length : null;
        if (next === null) return;
        event.preventDefault();
        activate(tabs[next], true);
      });

      grid.replaceWith(tablist, panels);
      modal.classList.add("is-tabbed");
      modal.dataset.tabsReady = "true";
    });
    refreshIcons();
  };

  const registerForms = () => {
    document.querySelectorAll("form").forEach((form) => {
      form.addEventListener("input", () => setFormState(form));
      form.addEventListener("focusout", () => setFormState(form));
      form.addEventListener("submit", () => {
        if (form.getAttribute("method") !== "dialog" && !form.closest(".home-controls, .sonos-controls-dialog, .hue-color-dialog, .hue-effect-dialog")) setSubmitting(form);
      });
    });
  };

  const registerWishAutofill = () => {
    document.querySelectorAll("form[data-wish-autofill]").forEach((form) => {
      const urlField = form.elements.namedItem("url");
      const status = form.querySelector("[data-wish-metadata-status]");
      const preview = form.querySelector("[data-wish-image-preview]");
      const previewImage = preview?.querySelector("img");
      if (!urlField || !form.dataset.metadataUrl) return;
      let requestNumber = 0;
      let inputTimer;
      const showPreview = (imageUrl) => {
        if (!preview || !previewImage || !imageUrl) return;
        previewImage.src = imageUrl;
        preview.hidden = false;
      };
      previewImage?.addEventListener("error", () => { preview.hidden = true; });
      const fill = async () => {
        const url = urlField.value.trim();
        if (!/^https?:\/\//i.test(url)) return;
        const currentRequest = ++requestNumber;
        if (status) status.textContent = "Productgegevens ophalen…";
        try {
          const response = await fetch(`${form.dataset.metadataUrl}?url=${encodeURIComponent(url)}`, { headers: { Accept: "application/json" } });
          const metadata = await response.json();
          if (currentRequest !== requestNumber) return;
          if (!response.ok) throw new Error(metadata.error || "Productgegevens zijn niet beschikbaar.");
          ["title", "price", "category", "image_url"].forEach((name) => {
            const field = form.elements.namedItem(name);
            const value = metadata[name];
            if (field && value && (!field.value.trim() || field.dataset.autofilled === "true")) {
              field.value = value;
              field.dataset.autofilled = "true";
            }
          });
          showPreview(metadata.image_url);
          if (status) status.textContent = `Gevonden: ${metadata.title}${metadata.price ? ` · € ${metadata.price}` : ""}`;
        } catch (error) {
          if (currentRequest === requestNumber && status) status.textContent = error.message || "Productgegevens konden niet worden opgehaald.";
        }
      };
      urlField.addEventListener("input", () => {
        window.clearTimeout(inputTimer);
        if (/^https?:\/\//i.test(urlField.value.trim())) inputTimer = window.setTimeout(fill, 550);
      });
      urlField.addEventListener("change", fill);
      urlField.addEventListener("blur", fill);
      ["title", "price", "category", "image_url"].forEach((name) => {
        const field = form.elements.namedItem(name);
        field?.addEventListener("input", () => { delete field.dataset.autofilled; });
      });
    });
  };

  const registerAgendaEvents = () => {
    document.querySelectorAll(".agenda-event").forEach((button) => button.addEventListener("click", () => {
      const modal = dialog("event-detail-dialog");
      if (!modal) return;
      modal.querySelector("[data-event-detail-title]").textContent = button.dataset.eventTitle || "Afspraak";
      modal.querySelector("[data-event-detail-meta]").textContent = button.dataset.eventMeta || "";
      modal.querySelector("[data-event-detail-notes]").textContent = button.dataset.eventNotes || "";
      const edit = modal.querySelector("[data-event-detail-edit]");
      if (edit) {
        const editDialog = button.dataset.eventEditDialog;
        edit.hidden = !editDialog;
        edit.onclick = editDialog ? () => { closeDialog(modal, false); openDialog(editDialog, button); } : null;
      }
      openDialog("event-detail-dialog", button);
    }));
  };

  const registerDangerButtonConfirmation = () => {
    document.addEventListener("submit", (e) => {
      const dangerBtn = e.target.querySelector(".button-danger, .icon-button.destructive");
      if (dangerBtn && !window.confirm("Bent u zeker? Deze actie kan niet ongedaan worden gemaakt.")) {
        e.preventDefault();
      }
    }, true);
  };

  applyTheme();
  document.addEventListener("DOMContentLoaded", () => {
    refreshIcons();
    refreshNetworkStatus();
    window.addEventListener("online", refreshNetworkStatus);
    window.addEventListener("offline", refreshNetworkStatus);
    themeToggle()?.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      localStorage.setItem("family-app-theme", next);
      applyTheme();
    });
    registerDangerButtonConfirmation();
    document.querySelectorAll("[data-command-open]").forEach((button) => button.addEventListener("click", () => openDialog("command-palette", button)));
    document.querySelectorAll("[data-live-search]").forEach((input) => {
      let timer;
      input.addEventListener("input", () => {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => input.closest("form")?.requestSubmit(), 260);
      });
    });
    registerHoverMenus();
    registerDialogs();
    registerSonosDialogTabs();
    registerForms();
    registerWishAutofill();
    registerToastAutoDismiss();
    registerAgendaEvents();
    registerHomeControls();
    registerHueRangeControls();
    registerHueColorPickers();
    registerHueSyncRefresh();
    registerHomeRealtime();
    registerGoogleLiveStreams();
    document.querySelectorAll("[data-sonos-now-playing]").forEach((nowPlaying) => {
      nowPlaying.dataset.sonosProgressMeasuredAt = String(Date.now());
      renderSonosProgress(nowPlaying, nowPlaying.dataset.sonosPositionSeconds, nowPlaying.dataset.sonosDurationSeconds);
    });
    document.querySelectorAll("[data-cast-now-playing]").forEach((nowPlaying) => {
      nowPlaying.dataset.castProgressMeasuredAt = String(Date.now());
      renderCastProgress(nowPlaying, nowPlaying.dataset.castPositionSeconds, nowPlaying.dataset.castDurationSeconds);
    });
    window.setInterval(() => {
      tickSonosProgress();
      tickCastProgress();
    }, 250);
  });
  const registerToastAutoDismiss = () => {
    document.querySelectorAll(".toast").forEach((toast) => {
      if (toast.dataset.dismissTimer) return;
      toast.dataset.dismissTimer = "true";
      window.setTimeout(() => toast.remove(), 5000);
    });
  };
  document.body.addEventListener("htmx:afterSwap", () => {
    refreshIcons();
    registerForms();
    registerWishAutofill();
    registerHoverMenus();
    registerToastAutoDismiss();
  });
  document.body.addEventListener("htmx:responseError", (e) => {
    const status = e.detail?.xhr?.status;
    const messages = {
      404: "Gegevens niet gevonden. Controleer of het item nog bestaat.",
      500: "Serverfout. Probeer het opnieuw.",
      503: "Server is momenteel niet beschikbaar. Probeer later opnieuw.",
    };
    const message = messages[status] || "Aanvraag mislukt. Controleer je verbinding en probeer het opnieuw.";
    const toast = document.createElement("div");
    toast.className = "toast toast-error";
    toast.innerHTML = `<i data-lucide="circle-alert"></i>${message}`;
    document.querySelector(".toast-stack") || Object.assign(document.createElement("div"), { className: "toast-stack", "aria-live": "polite" }).appendChild(toast) && document.querySelector("main")?.parentElement?.insertBefore(document.querySelector(".toast-stack"), document.querySelector("main"));
    const stack = document.querySelector(".toast-stack");
    stack?.appendChild(toast);
    window.setTimeout(() => toast.remove(), 5000);
    refreshIcons();
  });
  const requestPushNotificationPermission = async () => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
    if (Notification.permission === "denied") return;
    if (Notification.permission === "granted") {
      await subscribeToPush();
      return;
    }
    const permission = await Notification.requestPermission();
    if (permission === "granted") {
      await subscribeToPush();
    }
  };

  const subscribeToPush = async () => {
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      if (subscription) return;
      const key = document.querySelector("meta[name='webpush-vapid-key']")?.content;
      if (!key) return;
      const newSubscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(key),
      });
      await fetch("/meldingen/push/abonneer/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subscription: newSubscription.toJSON() }),
      });
    } catch (error) {
      console.error("Failed to subscribe to push notifications:", error);
    }
  };

  const urlBase64ToUint8Array = (base64String) => {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/\-/g, "+").replace(/_/g, "/");
    const rawData = window.atob(base64);
    return new Uint8Array([...rawData].map((char) => char.charCodeAt(0)));
  };

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/service-worker.js?v=7", { scope: "/" }).catch(() => {});
      requestPushNotificationPermission();
    });
  }
})();
