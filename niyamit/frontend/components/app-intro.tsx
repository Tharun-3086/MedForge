"use client";
import { useEffect, useRef, useState } from "react";
import { BrandMark } from "@/components/ui";

/** Decorative, once per tab; never waits for a network request. */
export function AppIntro() {
  const [visible, setVisible] = useState(false);
  const started = useRef(false);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (!started.current) {
      try {
        if (sessionStorage.getItem("niyamit-intro-seen")) return;
        sessionStorage.setItem("niyamit-intro-seen", "1");
      } catch { /* Restricted storage must not prevent opening the app. */ }
      started.current = true;
      setVisible(true);
    }
    const dismiss = () => setVisible(false);
    const timer = window.setTimeout(dismiss, 1400);
    window.addEventListener("pointerdown", dismiss, { once: true });
    window.addEventListener("keydown", dismiss, { once: true });
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("pointerdown", dismiss);
      window.removeEventListener("keydown", dismiss);
    };
  }, []);
  if (!visible) return null;
  return <div className="app-intro" aria-hidden="true"><div className="app-intro-content">
    <div className="app-intro-emblem"><BrandMark className="app-intro-logo" /></div>
    <span className="app-intro-name">Niyamit</span>
    <span className="app-intro-tagline">Your care, connected.</span>
  </div></div>;
}
