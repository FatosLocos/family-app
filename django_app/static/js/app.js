(() => {
  const applyTheme = () => {
    const saved = localStorage.getItem("family-app-theme");
    document.documentElement.dataset.theme = saved || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  };
  const icons = () => window.lucide?.createIcons({ attrs: { "stroke-width": 1.8 } });
  const dialog = (id) => document.getElementById(id);

  applyTheme();
  document.addEventListener("DOMContentLoaded", () => {
    icons();
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => button.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      localStorage.setItem("family-app-theme", next);
    }));
    document.querySelectorAll("[data-open-dialog]").forEach((button) => button.addEventListener("click", () => dialog(button.dataset.openDialog)?.showModal()));
    document.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => button.closest("dialog")?.close()));
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
        edit.onclick = editDialog ? () => { modal.close(); dialog(editDialog)?.showModal(); } : null;
      }
      modal.showModal();
    }));
    document.querySelectorAll("[data-command-open]").forEach((button) => button.addEventListener("click", () => dialog("command-palette")?.showModal()));
    document.querySelectorAll("[data-live-search]").forEach((input) => {
      let timer;
      input.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(() => input.closest("form")?.requestSubmit(), 260);
      });
    });
  });
  document.body.addEventListener("htmx:afterSwap", icons);
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/static/js/sw.js").catch(() => {}));
  }
})();
