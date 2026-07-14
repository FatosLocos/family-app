"use client";

import { RefreshCw, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";

export function PwaRegister() {
  const [offline, setOffline] = useState(false);
  const [waitingWorker, setWaitingWorker] = useState<ServiceWorker | null>(null);

  useEffect(() => {
    setOffline(!navigator.onLine);

    const onOnline = () => setOffline(false);
    const onOffline = () => setOffline(true);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);

    if (process.env.NODE_ENV === "development") {
      if ("serviceWorker" in navigator) {
        navigator.serviceWorker.getRegistrations().then((registrations) => {
          registrations.forEach((registration) => void registration.unregister());
        }).catch(() => {});
      }
      if ("caches" in window) {
        caches.keys().then((keys) => {
          keys.forEach((key) => void caches.delete(key));
        }).catch(() => {});
      }
      return () => {
        window.removeEventListener("online", onOnline);
        window.removeEventListener("offline", onOffline);
      };
    }

    if (!("serviceWorker" in navigator) || (window.location.protocol !== "https:" && window.location.hostname !== "localhost")) {
      return () => {
        window.removeEventListener("online", onOnline);
        window.removeEventListener("offline", onOffline);
      };
    }

    navigator.serviceWorker.register("/sw.js").then((registration) => {
      if (registration.waiting) setWaitingWorker(registration.waiting);

      registration.addEventListener("updatefound", () => {
        const worker = registration.installing;
        if (!worker) return;
        worker.addEventListener("statechange", () => {
          if (worker.state === "installed" && navigator.serviceWorker.controller) {
            setWaitingWorker(worker);
          }
        });
      });
    }).catch(() => {
      // PWA support is progressive; the app remains fully usable without a service worker.
    });

    let refreshing = false;
    const onControllerChange = () => {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    };
    navigator.serviceWorker.addEventListener("controllerchange", onControllerChange);

    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      navigator.serviceWorker.removeEventListener("controllerchange", onControllerChange);
    };
  }, []);

  if (!offline && !waitingWorker) return null;

  return (
    <div className="pwa-status" role="status" aria-live="polite">
      {offline ? (
        <>
          <WifiOff size={17} />
          <span>Offline. Laatst geopende pagina's blijven beschikbaar.</span>
        </>
      ) : (
        <>
          <RefreshCw size={17} />
          <span>Nieuwe versie beschikbaar.</span>
          <button className="button" type="button" onClick={() => waitingWorker?.postMessage({ type: "SKIP_WAITING" })}>
            Vernieuwen
          </button>
        </>
      )}
    </div>
  );
}
