import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import Link from "next/link";
import { LEARN_PAGES } from "@/lib/learn";

export const metadata: Metadata = pageMetadata({
  title: "Learn",
  description: "Guides, documentation, and insights from NITE DSP.",
  path: "/learn",
});

const INSIGHTS = [
  {
    slug: "why-filenames-fail",
    title: "Why filenames fail at scale",
    description: "Naming conventions were designed for human memory, not acoustic retrieval. Here's why they break down.",
  },
  {
    slug: "acoustic-timbre-search",
    title: "How acoustic timbre search works",
    description: "A plain-language explanation of the signal analysis that powers SLO's similarity engine.",
  },
  {
    slug: "local-first-creative-tools",
    title: "Why local-first matters for creative tools",
    description: "Cloud dependencies create latency, privacy risks, and lock-in. There's a better model.",
  },
];

export default function LearnHomePage() {
  return (
    <>
      <section className="section support-hero">
        <div className="site-container">
          <span className="eyebrow">Documentation &amp; Insights</span>
          <h1 className="section-title mt-4 text-foreground">Less setup. More sound.</h1>
          <p className="body-large mt-6">
            Product guides, technical documentation, and thinking from the team behind NITE DSP.
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
      <section className="section-rule">
        <div className="site-container py-12 sm:py-20">
          <div className="border-b pb-6" style={{ borderColor: "var(--border)" }}>
            <span className="eyebrow text-brand-blue-bright">Free Guides</span>
            <h2 className="mt-3 text-2xl font-bold text-foreground tracking-tight">Guides</h2>
            <p className="mt-2 text-sm text-muted">Practical resources you can use right now.</p>
          </div>
          <div className="learn-index mt-6">
            <Link href="/learn/guides/submission-scorecard" className="learn-index__item">
              <span className="font-mono text-[10px] text-muted-dim tracking-wider uppercase">INTERACTIVE</span>
              <span className="font-semibold text-foreground text-sm">Is your submission ready? (Scorecard)</span>
              <span className="text-xs text-muted hidden sm:block">Answer 8 questions and get a readiness score before you submit.</span>
              <span aria-hidden="true" className="text-muted-dim">&rarr;</span>
            </Link>
            <Link href="/learn/guides/submission-checklist" className="learn-index__item">
              <span className="font-mono text-[10px] text-muted-dim tracking-wider uppercase">FREE GUIDE</span>
              <span className="font-semibold text-foreground text-sm">The Student Submission Checklist</span>
              <span className="text-xs text-muted hidden sm:block">Eight checks to run before you hit submit. Catches the mistakes that lose marks.</span>
              <span aria-hidden="true" className="text-muted-dim">&rarr;</span>
            </Link>
          </div>
        </div>
      </section>
      <section className="section-rule">
        <div className="site-container py-12 sm:py-20">
          <div className="border-b pb-6" style={{ borderColor: "var(--border)" }}>
            <span className="eyebrow text-brand-blue-bright">Thinking</span>
            <h2 className="mt-3 text-2xl font-bold text-foreground tracking-tight">Insights</h2>
            <p className="mt-2 text-sm text-muted">Ideas and perspectives from the NITE DSP team on audio, tools, and creative workflows.</p>
          </div>

          <div className="learn-index mt-6">
            {INSIGHTS.map((a) => (
              <Link key={a.slug} href={`/learn/insights/${a.slug}`} className="learn-index__item">
                <span className="font-mono text-[10px] text-muted-dim tracking-wider uppercase">INSIGHT</span>
                <span className="font-semibold text-foreground text-sm">{a.title}</span>
                <span className="text-xs text-muted hidden sm:block">{a.description}</span>
                <span aria-hidden="true" className="text-muted-dim">&rarr;</span>
              </Link>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
