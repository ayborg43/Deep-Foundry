"use client";

import { useEffect } from "react";

import {
  AUTH_SESSION_CHANGED_EVENT,
  expireSession,
  getSessionRemainingMs,
  getTokens,
  touchSession,
} from "@/lib/auth";

const ACTIVITY_WRITE_INTERVAL_MS = 15_000;

export function SessionTimeout() {
  useEffect(() => {
    let timeoutId: number | null = null;
    let lastActivityWrite = 0;

    function clearTimer() {
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
        timeoutId = null;
      }
    }

    function scheduleTimeout() {
      clearTimer();
      if (!getTokens()) return;
      const remaining = getSessionRemainingMs();
      if (remaining === null) return;
      if (remaining <= 0) {
        expireSession();
        return;
      }
      timeoutId = window.setTimeout(expireSession, remaining);
    }

    function recordActivity() {
      const now = Date.now();
      if (now - lastActivityWrite < ACTIVITY_WRITE_INTERVAL_MS) return;
      lastActivityWrite = now;
      touchSession();
      scheduleTimeout();
    }

    function checkVisibleSession() {
      if (document.visibilityState === "visible") scheduleTimeout();
    }

    scheduleTimeout();
    const activityEvents: (keyof WindowEventMap)[] = [
      "keydown",
      "pointerdown",
      "scroll",
      "touchstart",
      "wheel",
    ];
    for (const eventName of activityEvents) {
      window.addEventListener(eventName, recordActivity, { passive: true });
    }
    window.addEventListener("storage", scheduleTimeout);
    window.addEventListener(AUTH_SESSION_CHANGED_EVENT, scheduleTimeout);
    document.addEventListener("visibilitychange", checkVisibleSession);

    return () => {
      clearTimer();
      for (const eventName of activityEvents) {
        window.removeEventListener(eventName, recordActivity);
      }
      window.removeEventListener("storage", scheduleTimeout);
      window.removeEventListener(AUTH_SESSION_CHANGED_EVENT, scheduleTimeout);
      document.removeEventListener("visibilitychange", checkVisibleSession);
    };
  }, []);

  return null;
}
