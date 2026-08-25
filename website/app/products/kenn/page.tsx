import type { Metadata } from "next";
import Link from "next/link";
import { CtaButton } from "@/components/CtaButton";
import { KennMixDemo } from "@/components/demo/KennMixDemo";
import { LightField } from "@/components/motion/LightField";
import { Reveal } from "@/components/motion/Reveal";
import { StatusDot } from "@/components/motion/StatusDot";
import { TiltSurface } from "@/components/motion/TiltSurface";

export const metadata: Metadata = {
  title: "KENN — Understand Your Mix",
  description:
    "KENN analyses your mix locally and explains what it hears — so you make the changes. In development at NITE DSP.",
  alternates: { canonical: "/products/kenn" },
};

const STAGES = [
  {
    title: "Analyse",
    body: "KENN measures your mix locally: spectral balance across bands, transient behaviour, stereo energy distribution, and loudness relationships between elements.",
  },
  {
    title: "Detect",
    body: "Patterns worth attention are identified — a masked vocal range, low-mid buildup, transients that disappear in the chorus — based on measurable characteristics, not taste.",
  },
  {
    title: "Explain",
    body: "Every finding comes with reasoning: what was measured, how it compares to common mixing practice, and why it might matter for your track.",
  },
  {
    title: "Recommend",
    body: "You get suggested areas to address — with the evidence behind them. You make every creative decision. KENN never renders audio on its own.",
  },
];
// __PART2__

const BOUNDARIES = [
  ["KENN does not mix your song", "It never processes or renders your audio into a finished mix. It reads analysis data and explains it."],
  ["No black-box verdicts", "Findings are tied to measurements you can inspect — not an opaque score."],
  ["Your stems stay local", "Analysis runs on your machine. Audio files are never uploaded."],
];

export default function KennPage() {
  return (
    <>
      {/* Hero */}
      <section className="section product-hero relative overflow-hidden">
        <LightField />
        <div className="site-container relative">
          <span className="eyebrow text-brand-violet">Audio Intelligence Family</span>
          <h1 className="section-title mt-4 text-foreground">Understand your mix.</h1>
          <p className="text-sm font-mono text-brand-violet mt-1">
            Audio Engineering Intelligence Assistant
          </p>
          <p className="body-large mt-6 font-sans">
            KENN listens to your mix the way an engineer would ask questions of it: what is the
            spectral balance doing, where are elements fighting, what deserves attention. Then it
            explains — clearly, with evidence — so you decide what to change.
          </p>
          <div className="mt-8 flex flex-wrap gap-4 items-center">
            <CtaButton state="NOTIFY_ME" label="Notify me at launch" />
            <span
              className="status-chip text-[10px] uppercase font-mono tracking-wider px-2 py-0.5 rounded border inline-flex items-center gap-1"
              style={{ borderColor: "var(--state-warning-border)", color: "var(--state-warning)" }}
            >
              <StatusDot tone="warning" />
              In Development
            </span>
          </div>
        </div>
      </section>

      {/* Workflow: Analyse → Detect → Explain → Recommend */}
      <section className="section section-rule">
        <div className="site-container">
          <Reveal>
            <div className="max-w-2xl">
              <span className="eyebrow">How KENN Works</span>
              <h2 className="section-title mt-4">Four stages. Full visibility.</h2>
            </div>
          </Reveal>
          <ol className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {STAGES.map((s, i) => (
              <li key={s.title} className="surface-card p-6 rounded-lg border border-border/40">
                <span className="u-data" style={{ color: "var(--brand-blue-bright)" }}>
                  0{i + 1}
                </span>
                <h3 className="mt-3 text-sm font-semibold text-foreground">{s.title}</h3>
                <p className="mt-2 text-xs leading-relaxed text-muted">{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Interactive concept demo */}
      <section className="section section-rule bg-surface/10">
        <div className="site-container grid gap-12 lg:grid-cols-[0.85fr_1.15fr] lg:items-center">
          <Reveal>
            <span className="eyebrow">Concept Demonstration</span>
            <h2 className="section-title mt-4">Mix review, explained.</h2>
            <p className="mt-4 text-sm leading-relaxed text-muted">
              A simulated walkthrough of how KENN will present findings: each observation shown with
              its measurement and plain-language reasoning.
            </p>
            <p className="mt-3 text-xs" style={{ color: "var(--muted-dim)" }}>
              Simulated demonstration with illustrative data. Runs entirely in your browser — no
              audio is processed or uploaded.
            </p>
          </Reveal>
          <Reveal delayMs={90}>
            <TiltSurface maxTiltDeg={1.2}>
              <KennMixDemo />
            </TiltSurface>
          </Reveal>
        </div>
      </section>

      {/* Boundaries + CTA */}
      <section className="section section-rule">
        <div className="site-container">
          <Reveal>
            <span className="eyebrow">Operational Boundary</span>
            <h2 className="section-title mt-4">What KENN will not do.</h2>
          </Reveal>
          <div className="capability-grid spotlight-group mt-10">
            {BOUNDARIES.map(([title, body]) => (
              <article key={title} className="capability">
                <h3 className="text-foreground">{title}</h3>
                <p>{body}</p>
              </article>
            ))}
          </div>
          <div className="cta-panel depth-hover mt-14">
            <div>
              <h2 className="section-title mt-4 text-foreground">Be first to know.</h2>
              <p className="mt-2 text-sm text-muted">
                KENN is in active development. Join the notify list and we&apos;ll email you when
                beta access opens.
              </p>
            </div>
            <div className="flex flex-wrap gap-3 relative z-10">
              <CtaButton state="NOTIFY_ME" />
              <Link href="/trust" className="btn-secondary">
                How we handle your data
              </Link>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}

