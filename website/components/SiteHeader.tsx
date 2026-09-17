"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

const NAV_LINKS = [
  { href: "/products", label: "Products" },
  { href: "/technology", label: "Technology" },
  { href: "/learn", label: "Learn" },
  { href: "/pricing", label: "Pricing" },
  { href: "/support", label: "Support" },
  { href: "/about", label: "About" },
  { href: "/services", label: "Services" },
];

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const navRef = useRef<HTMLDivElement>(null);
  const linkRefs = useRef<Array<HTMLAnchorElement | null>>([]);
  const [indicator, setIndicator] = useState({ x: 0, w: 0, ready: false });

  const measure = useCallback(() => {
    const container = navRef.current;
    if (!container) return;
    const activeIndex = NAV_LINKS.findIndex(
      (link) => pathname === link.href || pathname.startsWith(`${link.href}/`),
    );
    if (activeIndex === -1) {
      setIndicator((prev) => ({ ...prev, ready: false }));
      return;
    }
    const link = linkRefs.current[activeIndex];
    if (!link) return;
    // The indicator lives inside .nav-links (position:relative), so offsets
    // are measured relative to that container, not the viewport.
    const linkLeft = link.offsetLeft;
    setIndicator({ x: linkLeft, w: link.offsetWidth, ready: true });
  }, [pathname]);

  // Escape closes the mobile menu and hands focus back to the toggle, so a
  // keyboard user is never stranded inside an open menu (WCAG 2.1.2).
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      menuButtonRef.current?.focus();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  useEffect(() => {
    // Defer to rAF: keeps the effect body free of synchronous state updates
    // and lets the first paint land before the indicator positions itself.
    let raf = requestAnimationFrame(measure);
    const onFontsReady = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    };
    document.fonts?.ready.then(onFontsReady).catch(() => {});
    window.addEventListener("resize", measure);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", measure);
    };
  }, [measure]);

  return (
    <header
      className="border-b sticky top-0 z-40"
      style={{ borderColor: "var(--border)", backgroundColor: "color-mix(in srgb, var(--background) 75%, transparent)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}
    >
      <nav
        className="mx-auto flex items-center justify-between px-6 py-4"
        style={{ maxWidth: "var(--content-width)" }}
        aria-label="Primary"
      >
        <Link href="/" className="brand-mark text-xl leading-none" aria-label="NITE DSP home">
          NITE DSP
        </Link>
        <div
          ref={navRef}
          className="nav-links relative hidden sm:flex items-center gap-8 text-sm"
          style={{ color: "var(--muted)" }}
        >
          {NAV_LINKS.map((link, i) => (
            <Link
              key={link.href}
              ref={(el) => {
                linkRefs.current[i] = el;
              }}
              href={link.href}
              aria-current={
                pathname === link.href || pathname.startsWith(`${link.href}/`)
                  ? "page"
                  : undefined
              }
              className="hover:text-[color:var(--foreground)] transition-colors"
            >
              {link.label}
            </Link>
          ))}
          {/* Morphing active indicator, purely decorative; state is also
              conveyed via aria-current. Labels never move. */}
          <span
            aria-hidden="true"
            className="nav-indicator"
            style={{
              width: `${indicator.w}px`,
              transform: `translateX(${indicator.x}px)`,
              opacity: indicator.ready ? 1 : 0,
            }}
          />
        </div>
        <div className="flex items-center gap-3">
          {/* The hide-below-sm has to live on a wrapper, not on the Link:
              .btn-secondary sets `display` from unlayered CSS, which outranks
              Tailwind's layered `hidden` utility, so `hidden sm:inline-flex`
              on the Link itself left the Account button showing on phones
              next to the hamburger (and again inside the open menu). */}
          <span className="hidden sm:flex">
            <Link href="/account" className="btn-secondary">
              Account
            </Link>
          </span>
          <button
            ref={menuButtonRef}
            type="button"
            className="sm:hidden inline-flex items-center justify-center w-10 h-10 rounded-md border"
            style={{ borderColor: "var(--border-strong)" }}
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M3 6h18M3 12h18M3 18h18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            )}
          </button>
        </div>
      </nav>

      {open && (
        <div
          id="mobile-nav"
          className="sm:hidden border-t px-6 py-4 flex flex-col gap-1 text-sm"
          style={{ borderColor: "var(--border)", background: "var(--background)" }}
        >
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="py-2.5"
              style={{ color: "var(--muted)" }}
              onClick={() => setOpen(false)}
            >
              {link.label}
            </Link>
          ))}
          <Link href="/account" className="btn-secondary mt-3 text-center" onClick={() => setOpen(false)}>
            Account
          </Link>
        </div>
      )}
    </header>
  );
}
