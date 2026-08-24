import type { Metadata } from "next";
import Link from "next/link";
import { LEARN_PAGES } from "@/lib/learn";

export const metadata: Metadata = {
  title: "Learn",
  description: "Guides and documentation for SLO by NITE DSP.",
  alternates: { canonical: "/learn" },
};

export default function LearnHomePage() {
  return (
    <>
      <section className="section support-hero">
        <div className="site-container">
          <span className="eyebrow">Documentation</span>
          <h1 className="section-title mt-4 text-foreground">Less setup. More sound.</h1>
          <p className="body-large mt-6">
            Everything you need to know about installing, activating, scanning, and finding your way around SLO.
          </p>
        </div>
      </section>

      <section className="section-rule">
        <div className="site-container py-12 sm:py-20">
          <div className="flex flex-wrap items-end justify-between gap-6 border-b pb-6" style={{ borderColor: "var(--border)" }}>
            <div>
              <span className="eyebrow text-brand-blue-bright">Flagship Browser</span>
              <h2 className="mt-3 text-2xl font-bold text-foreground tracking-tight">SLO Guide Index</h2>
            </div>
            <Link href="/learn/smart-sample-manager/getting-started" className="btn-primary">
              Getting Started Guide
            </Link>
          </div>
          
          <div className="learn-index mt-6">
            {LEARN_PAGES.map((p) => (
              <Link key={p.slug} href={`/learn/smart-sample-manager/${p.slug}`} className="learn-index__item">
                <span className="font-mono text-[10px] text-muted-dim tracking-wider uppercase">GUIDE // {p.slug.toUpperCase()}</span>
                <span className="font-semibold text-foreground text-sm">{p.title}</span>
                <span aria-hidden="true" className="text-muted-dim">&rarr;</span>
              </Link>
            ))}
          </div>
          
          <p className="mt-10 max-w-2xl text-xs text-muted-dim leading-relaxed">
            The documentation describes SLO version 1.x running on macOS. Features marked as Experimental (e.g. Ableton metadata write operations) remain under validation.
          </p>
        </div>
      </section>
    </>
  );
}
