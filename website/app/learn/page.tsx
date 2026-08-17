import type { Metadata } from "next";
import Link from "next/link";
import { LEARN_PAGES } from "@/lib/learn";

export const metadata: Metadata = {
  title: "Learn",
  description: "Guides and documentation for NITE DSP products.",
  alternates: { canonical: "/learn" },
};

export default function LearnHomePage() {
  return (
    <>
      <section className="section support-hero">
      <div className="site-container">
        <span className="eyebrow">Learn</span>
        <h1 className="section-title mt-4">Less setup. More sound.</h1>
        <p className="body-large mt-6">
          Straight answers for installing, activating, scanning, and finding your way around
          Smart Sample Manager.
        </p>
      </div>
      </section>

      <section className="section-rule">
        <div className="site-container py-12 sm:py-20">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div>
              <span className="eyebrow">Smart Sample Manager</span>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight">Start with the essentials.</h2>
            </div>
            <Link href="/learn/smart-sample-manager/getting-started" className="btn-primary">
              Start with Getting Started
            </Link>
          </div>
          <div className="learn-index mt-10">
            {LEARN_PAGES.map((p) => (
              <Link key={p.slug} href={`/learn/smart-sample-manager/${p.slug}`} className="learn-index__item">
                <span className="font-mono text-xs" style={{ color: "var(--accent-signal)" }}>GUIDE</span>
                <span className="font-medium">{p.title}</span>
                <span aria-hidden="true" style={{ color: "var(--muted-dim)" }}>→</span>
              </Link>
            ))}
          </div>
          <p className="mt-8 max-w-xl text-sm" style={{ color: "var(--muted)" }}>
            The guides describe the current macOS build and label experimental workflows where
            appropriate.
          </p>
        </div>
      </section>
    </>
  );
}
