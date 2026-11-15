"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

export interface Keyed<T> { key: string | null; data: T | null; error: string | null; loading: boolean }

/**
 * Load data for a key and only ever expose results that belong to the CURRENT key.
 * A slow response for a previous selection is discarded instead of overwriting newer state,
 * which keeps the selected card, imagery and evidence describing the same site.
 */
export function useKeyed<T>(key: string | null, loader: (key: string) => Promise<T>): Keyed<T> {
  const [state, setState] = useState<{ key: string | null; data: T | null; error: string | null }>({ key: null, data: null, error: null });
  useEffect(() => {
    if (!key) return;
    let active = true;
    loader(key)
      .then((data) => { if (active) setState({ key, data, error: null }); })
      .catch((error: unknown) => { if (active) setState({ key, data: null, error: error instanceof Error ? error.message : "Unavailable" }); });
    return () => { active = false; };
    // loader identity is intentionally ignored: callers pass stable module functions
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const current = state.key === key;
  return { key, data: current ? state.data : null, error: current ? state.error : null, loading: Boolean(key) && !current };
}

function subscribeMedia(query: string) {
  return (callback: () => void) => {
    const media = window.matchMedia(query);
    media.addEventListener("change", callback);
    return () => media.removeEventListener("change", callback);
  };
}

export function useMediaQuery(query: string, serverValue = false): boolean {
  return useSyncExternalStore(subscribeMedia(query), () => window.matchMedia(query).matches, () => serverValue);
}

export const useReducedMotion = () => useMediaQuery("(prefers-reduced-motion: reduce)");
export const useNarrow = () => useMediaQuery("(max-width: 959px)");

let webglSupport: boolean | null = null;
export function hasWebGL(): boolean {
  if (webglSupport !== null) return webglSupport;
  try {
    const canvas = document.createElement("canvas");
    webglSupport = Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    webglSupport = false;
  }
  return webglSupport;
}

export function useWebGL(): boolean | null {
  return useSyncExternalStore(() => () => {}, () => hasWebGL(), () => null);
}
