"use client";

import { useCallback, useSyncExternalStore } from "react";

/** Simple / Detailed reading mode, shared by every page and remembered in this browser. Simple is the default. */
export type DetailMode = "simple" | "detailed";
const KEY = "alterecho-detail";
const EVENT = "alterecho-detail-change";

function read(): DetailMode {
  try { return localStorage.getItem(KEY) === "detailed" ? "detailed" : "simple"; } catch { return "simple"; }
}

function subscribe(callback: () => void) {
  window.addEventListener(EVENT, callback);
  window.addEventListener("storage", callback);
  return () => { window.removeEventListener(EVENT, callback); window.removeEventListener("storage", callback); };
}

export function useDetailMode(): [DetailMode, (mode: DetailMode) => void] {
  const mode = useSyncExternalStore(subscribe, read, () => "simple" as DetailMode);
  const set = useCallback((next: DetailMode) => {
    try { localStorage.setItem(KEY, next); } catch { /* private mode: keep the in-memory choice for this page */ }
    window.dispatchEvent(new Event(EVENT));
  }, []);
  return [mode, set];
}
