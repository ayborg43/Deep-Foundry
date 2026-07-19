"use client";

import { useEffect } from "react";

// Registers the service worker in production builds only — in dev a SW
// caching layer just gets in the way of hot reload.
export function PwaRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      // Registration failure degrades to a normal web app.
    });
  }, []);
  return null;
}
