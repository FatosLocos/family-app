"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const searchSelector = "form[data-instant-search]";

export function InstantSearchEnhancer() {
  const router = useRouter();
  const timeoutRef = useRef<number | null>(null);
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    function clearTimer() {
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }

    function update(form: HTMLFormElement, delay: number) {
      clearTimer();
      form.dataset.pending = "true";
      setAnnouncement("Zoeken wordt bijgewerkt.");
      timeoutRef.current = window.setTimeout(() => {
        const url = new URL(form.getAttribute("action") || window.location.pathname, window.location.origin);
        const params = new URLSearchParams(window.location.search);
        const formData = new FormData(form);
        const keys = new Set<string>();
        formData.forEach((_, key) => keys.add(key));
        keys.forEach((key) => params.delete(key));
        formData.forEach((value, key) => {
          if (typeof value === "string" && value.trim()) params.append(key, value);
        });
        url.search = params.toString();
        router.replace(`${url.pathname}${url.search}`);
        window.setTimeout(() => {
          form.dataset.pending = "false";
          setAnnouncement("Zoekresultaten bijgewerkt.");
        }, 450);
      }, delay);
    }

    function onInput(event: Event) {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || !target.closest(searchSelector)) return;
      update(target.closest(searchSelector) as HTMLFormElement, 260);
    }

    function onChange(event: Event) {
      const target = event.target;
      if (!(target instanceof HTMLSelectElement) || !target.closest(searchSelector)) return;
      update(target.closest(searchSelector) as HTMLFormElement, 0);
    }

    function onSubmit(event: SubmitEvent) {
      const form = event.target;
      if (!(form instanceof HTMLFormElement) || !form.matches(searchSelector)) return;
      event.preventDefault();
      update(form, 0);
    }

    document.addEventListener("input", onInput);
    document.addEventListener("change", onChange);
    document.addEventListener("submit", onSubmit);
    return () => {
      clearTimer();
      document.removeEventListener("input", onInput);
      document.removeEventListener("change", onChange);
      document.removeEventListener("submit", onSubmit);
    };
  }, [router]);

  return <span className="sr-only" aria-live="polite" aria-atomic="true">{announcement}</span>;
}
