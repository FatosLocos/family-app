"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

type ThemePreference = "system" | "light" | "dark";
type AppliedTheme = "light" | "dark";

export function ThemeToggle() {
  const [preference, setPreference] = useState<ThemePreference>("system");
  const [, setAppliedTheme] = useState<AppliedTheme>("light");

  useEffect(() => {
    const saved = window.localStorage.getItem("family-app-theme");
    const initialPreference = saved === "dark" || saved === "light" || saved === "system" ? saved : "system";
    const media = window.matchMedia("(prefers-color-scheme: dark)");

    function syncTheme(nextPreference: ThemePreference) {
      const nextApplied = resolveTheme(nextPreference, media);
      applyTheme(nextPreference, nextApplied);
      setPreference(nextPreference);
      setAppliedTheme(nextApplied);
    }

    syncTheme(initialPreference);

    const onChange = () => {
      if ((window.localStorage.getItem("family-app-theme") ?? "system") === "system") {
        syncTheme("system");
      }
    };

    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  function chooseTheme(nextPreference: ThemePreference) {
    const nextApplied = resolveTheme(nextPreference, window.matchMedia("(prefers-color-scheme: dark)"));
    window.localStorage.setItem("family-app-theme", nextPreference);
    applyTheme(nextPreference, nextApplied);
    setPreference(nextPreference);
    setAppliedTheme(nextApplied);
  }

  return (
    <div className="theme-toggle" role="group" aria-label="Thema kiezen" data-preference={preference}>
      <span className="theme-slider-thumb" aria-hidden="true" />
      {themeOptions.map(({ value, label, Icon }) => (
        <button
          aria-label={`Thema: ${label}`}
          aria-pressed={preference === value}
          className="theme-option"
          data-active={preference === value ? "true" : undefined}
          key={value}
          onClick={() => chooseTheme(value)}
          title={`Thema: ${label}`}
          type="button"
        >
          <Icon size={17} />
        </button>
      ))}
    </div>
  );
}

const themeOptions: Array<{ value: ThemePreference; label: string; Icon: typeof Monitor }> = [
  { value: "system", label: "Systeem", Icon: Monitor },
  { value: "light", label: "Licht", Icon: Sun },
  { value: "dark", label: "Donker", Icon: Moon },
];

function resolveTheme(preference: ThemePreference, media: MediaQueryList): AppliedTheme {
  if (preference === "system") return media.matches ? "dark" : "light";
  return preference;
}

function applyTheme(preference: ThemePreference, theme: AppliedTheme) {
  document.documentElement.dataset.themePreference = preference;
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}
