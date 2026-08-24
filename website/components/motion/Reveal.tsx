"use client";

import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";

/* Scroll reveal — short opacity + 14px rise, once, never blocking content.
   Hidden state is scoped under html.js (set by a tiny inline script in the
   root layout), so users without JavaScript always see every word. */

type RevealProps = {
  children: ReactNode;
  /** Stagger delay in ms — use sparingly (<=120ms). */
  delayMs?: number;
  className?: string;
};

export function Reveal({ children, delayMs = 0, className }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.classList.add("is-revealed");
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            el.classList.add("is-revealed");
            observer.disconnect();
          }
        }
      },
      { threshold: 0.12, rootMargin: "0px 0px -48px 0px" },
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`reveal ${className ?? ""}`}
      style={{ "--reveal-delay": `${delayMs}ms` } as CSSProperties}
    >
      {children}
    </div>
  );
}
