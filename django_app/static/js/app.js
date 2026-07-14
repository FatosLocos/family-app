(() => {
  const dialog = (id) => document.getElementById(id);
  const dialogs = () => document.querySelectorAll("dialog");
  const themeToggle = () => document.querySelector("[data-theme-toggle]");
  const networkStatus = () => document.querySelector("[data-network-status]");

  const applyTheme = () => {
    const saved = localStorage.getItem("family-app-theme");
    const theme = saved || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.dataset.theme = theme;
    const button = themeToggle();
    if (button) button.setAttribute("aria-pressed", String(theme === "dark"));
  };

  const refreshIcons = () => window.lucide?.createIcons({ attrs: { "stroke-width": 1.8 } });

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
    fields.forEach((field) => { field.dataset.confirmedValue = field.value; });
  };

  const restoreHomeControlValues = (fields) => {
    fields.forEach((field) => {
      if (field.dataset.confirmedValue !== undefined) field.value = field.dataset.confirmedValue;
      if (field.matches("[data-temperature-slider]")) updateTemperatureAppearance(field);
      if (field.matches("[data-color-value]")) updateColorPicker(field.closest("[data-color-picker]"));
    });
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

  const registerHomeControls = () => {
    document.addEventListener("submit", async (event) => {
      const form = event.target.closest(".home-controls form, form.hue-color-dialog-form, form.hue-effect-choice-form");
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
        markHomeControlValuesConfirmed(fields);
        if (triggers["family:toast"]) showToast(triggers["family:toast"]);
        if (triggers["family:home-control"]) {
          updateHomeControl(triggers["family:home-control"]);
          if (triggers["family:home-control"].refresh) window.setTimeout(() => window.location.reload(), 250);
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
    document.querySelectorAll(".home-controls input:not([type='hidden']), .home-controls input[data-color-value], .home-controls select, .hue-color-dialog-form input[data-color-value]").forEach((field) => {
      field.dataset.confirmedValue = field.value;
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
  };

  const registerHueSyncRefresh = () => {
    if (!document.querySelector("[data-hue-sync-pending]")) return;
    window.setTimeout(() => {
      if (!document.hidden && !document.querySelector(".home-search input:focus")) window.location.reload();
    }, 4000);
  };

  const applyHomeRealtimeEntity = (entity) => {
    const card = document.querySelector(`[data-home-entity-id="${CSS.escape(String(entity?.id || ""))}"]`);
    if (!card) return;
    const attributes = entity.attributes || {};
    card.classList.toggle("is-unavailable", !entity.is_available);
    setHomeCardState(card, entity.state);
    if (entity.source !== "sonos") return;
    const playback = card.querySelector("[data-sonos-playback]");
    if (playback) {
      const labels = { PLAYBACK_STATE_PLAYING: "Speelt af", PLAYBACK_STATE_BUFFERING: "Bufferen", PLAYBACK_STATE_PAUSED: "Gepauzeerd", PLAYBACK_STATE_IDLE: "Geen audio" };
      playback.textContent = labels[attributes.sonos_playback_state] || "Geen audio";
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
      nowPlaying.innerHTML = '<img alt="" data-sonos-artwork><div><strong data-sonos-title></strong><small data-sonos-artist></small><small data-sonos-album></small><small class="sonos-source" data-sonos-source></small><small data-sonos-progress></small></div>';
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
      text("[data-sonos-progress]", [attributes.sonos_position, attributes.sonos_duration].filter(Boolean).join(" / "));
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

  const registerForms = () => {
    document.querySelectorAll("form").forEach((form) => {
      form.addEventListener("input", () => setFormState(form));
      form.addEventListener("focusout", () => setFormState(form));
      form.addEventListener("submit", () => {
        if (form.getAttribute("method") !== "dialog" && !form.closest(".home-controls")) setSubmitting(form);
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
    registerForms();
    registerWishAutofill();
    registerAgendaEvents();
    registerHomeControls();
    registerHueRangeControls();
    registerHueColorPickers();
    registerHueSyncRefresh();
    registerHomeRealtime();
  });
  document.body.addEventListener("htmx:afterSwap", refreshIcons);
  if ("serviceWorker" in navigator) window.addEventListener("load", () => navigator.serviceWorker.register("/service-worker.js?v=5", { scope: "/" }).catch(() => {}));
})();
