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

  const refreshNetworkStatus = () => {
    const status = networkStatus();
    if (!status) return;
    status.hidden = navigator.onLine;
    document.documentElement.toggleAttribute("data-offline", !navigator.onLine);
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
        if (form.getAttribute("method") !== "dialog") setSubmitting(form);
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
    registerAgendaEvents();
  });
  document.body.addEventListener("htmx:afterSwap", refreshIcons);
  if ("serviceWorker" in navigator) window.addEventListener("load", () => navigator.serviceWorker.register("/service-worker.js", { scope: "/" }).catch(() => {}));
})();
