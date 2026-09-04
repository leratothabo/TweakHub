"use client";

import { useEffect } from "react";

/**
 * Registers public/sw.js — production builds only. Skipped in dev on
 * purpose: a service worker caching Next's dev-mode assets fights with
 * hot reload (you'd be debugging stale cached JS, not your actual
 * change), and dev is never what gets installed as a PWA anyway.
 */
export default function ServiceWorkerRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;

    navigator.serviceWorker.register("/sw.js").catch((err) => {
      // Non-fatal — the app works fine without the service worker, it
      // just loses offline-shell caching and "Add to Home Screen".
      console.warn("Service worker registration failed:", err);
    });
  }, []);

  return null;
}
