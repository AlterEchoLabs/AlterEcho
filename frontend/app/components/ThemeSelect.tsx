"use client";

import { useEffect, useRef } from "react";

export default function ThemeSelect() {
  const select = useRef<HTMLSelectElement>(null);
  useEffect(() => {
    if (select.current) select.current.value = document.documentElement.dataset.preference || "system";
  }, []);
  return <label className="theme-select"><span className="sr-only">Color theme</span>
    <select aria-label="Color theme" ref={select} defaultValue="system" onChange={(event) => {
      const preference = event.target.value;
      try { localStorage.setItem("alterecho-theme", preference); } catch { /* Storage may be disabled. */ }
      document.documentElement.dataset.preference = preference;
      document.documentElement.dataset.theme = preference === "system" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : preference;
    }}><option value="system">System</option><option value="dark">Dark</option><option value="light">Light</option></select>
  </label>;
}
