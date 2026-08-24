"use client";

import Link from "next/link";
import { useState } from "react";

const NAV_LINKS = [
  { href: "/products", label: "Products" },
  { href: "/learn", label: "Learn" },
  { href: "/pricing", label: "Pricing" },
  { href: "/support", label: "Support" },
];

export function SiteHeader() {
  const [open, setOpen] = useState(false);

  return (
    <header
      className="border-b sticky top-0 z-40"
      style={{ borderColor: "var(--border)", backgroundColor: "rgba(7, 10, 18, 0.75)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}
    >
      <nav
        className="mx-auto flex items-center justify-between px-6 py-4"
        style={{ maxWidth: "var(--content-width)" }}
        aria-label="Primary"
      >
        <Link href="/" className="brand-mark text-xl leading-none" aria-label="NITE DSP home">
          NITE DSP
        </Link>
        <div className="hidden sm:flex items-center gap-8 text-sm" style={{ color: "var(--muted)" }}>
          {NAV_LINKS.map((link) => (
            <Link key={link.href} href={link.href} className="hover:text-[color:var(--foreground)] transition-colors">
              {link.label}
            </Link>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <Link href="/account" className="hidden sm:inline-flex btn-secondary">
            Account
          </Link>
          <button
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
