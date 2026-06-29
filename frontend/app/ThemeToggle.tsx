"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

// The toggle: light/dark, persisted to localStorage. Until the user makes an explicit choice we
// follow the OS preference (the initial value is resolved before paint by the inline script in
// layout.tsx, and we keep tracking system changes here while no choice is stored).
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setTheme((document.documentElement.dataset.theme as Theme) || "dark");

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onSystem = (e: MediaQueryListEvent) => {
      if (localStorage.getItem("theme")) return; // user has chosen — stop following the OS
      const next: Theme = e.matches ? "dark" : "light";
      document.documentElement.dataset.theme = next;
      setTheme(next);
    };
    mq.addEventListener("change", onSystem);
    return () => mq.removeEventListener("change", onSystem);
  }, []);

  const toggle = () => {
    const next: Theme = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch { /* private mode — runtime toggle still works */ }
    setTheme(next);
  };

  const label = theme === "light" ? "Switch to dark mode" : "Switch to light mode";

  return (
    <button type="button" className="themeToggle" onClick={toggle} aria-label={label} title={label}>
      {/* render the icon only after mount so SSR and first paint agree (size is reserved either way) */}
      {mounted ? (theme === "light" ? <SunIcon /> : <MoonIcon />) : null}
    </button>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" />
    </svg>
  );
}
