import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import Link from "next/link";
import { KennChatWidget } from "@/components/KennChatWidget";
import { KennMixDemo } from "@/components/demo/KennMixDemo";
import { LightField } from "@/components/motion/LightField";
import { Reveal } from "@/components/motion/Reveal";
import { TiltSurface } from "@/components/motion/TiltSurface";
import { WaitlistForm } from "@/components/WaitlistForm";

export const metadata: Metadata = pageMetadata({
  title: "KENN: AI Audio Assistant for Ableton Live",
  description: "KENN is an AI-powered audio assistant that lives inside Ableton Live. It listens, explains, and helps you make better mixing decisions. In development at NITE DSP.",
  path: "/products/kenn",
});

const STAGES = [
  {
    title: "Listen",
    body: "KENN analyses your session locally: spectral balance, transient behaviour, stereo energy, and how elements interact across your mix.",
  },
  {
    title: "Understand",
    body: "It identifies patterns worth your attention. A masked vocal, low-mid buildup, transients that disappear in the chorus. Based on measurements, not taste.",
  },
  {
    title: "Explain",
    body: "Every finding comes with reasoning. What was measured, how it compares to common practice, and why it might matter for your track.",
  },
  {
    title: "Assist",
    body: "Ask KENN questions about your mix and get clear, evidence-backed answers. It helps you think through decisions without making them for you.",
  },
];

const BOUNDARIES = [
  ["KENN does not mix your song", "It never processes or renders your audio. It reads analysis data and explains what it finds."],
  ["No black-box verdicts", "Findings are tied to measurements you can inspect, not an opaque score."],
  ["Your stems stay local", "Analysis runs on your machine. Audio files are never uploaded."],
];

export default function KennPage() {
  return (
    <>
      {/* Hero */}
      <section className="section product-hero relative overflow-hidden">
        <LightField />
        <div className="site-container relative">
          <span className="eyebrow text-brand-violet-text">Audio Intelligence Family</span>
          <h1 className="section-title mt-4 text-foreground">Your AI audio assistant for Ableton.</h1>
          <p className="text-sm font-mono text-brand-violet-text mt-1">
            AI Audio Assistant
          </p>
          <p className="body-large mt-6 font-sans">
            KENN lives inside Ableton Live and helps you understand what&apos;s happening in your mix.
            It listens, explains what it hears with real evidence, and answers your questions so you
            can make better decisions faster.
          </p>
          <div className="mt-4">
            <span className="status-chip text-[9px] uppercase font-mono tracking-wider px-2 py-0.5 rounded border border-brand-violet/40 text-brand-violet-text">
              Closed Beta &mdash; not for sale yet
            </span>
          </div>
          <div className="mt-8 flex flex-wrap gap-4">
            <Link href="#join-waitlist" className="btn-primary">
              Request beta access
            </Link>
          </div>
        </div>
      </section>

      {/* Workflow */}
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
              A simulated walkthrough of how KENN presents findings. Each observation is shown with
              its measurement and plain-language reasoning.
            </p>
            <p className="mt-3 text-xs" style={{ color: "var(--muted-dim)" }}>
              Simulated demonstration with illustrative data. Runs entirely in your browser.
            </p>
          </Reveal>
          <Reveal delayMs={90}>
            <TiltSurface maxTiltDeg={1.2}>
              <KennMixDemo />
            </TiltSurface>
          </Reveal>
        </div>
      </section>

      {/* Live text Q&A */}
      <section className="section section-rule">
        <div className="site-container">
          <div className="max-w-2xl">
            <span className="eyebrow">Try it now</span>
            <h2 className="section-title mt-4">Ask KENN about the mix.</h2>
            <p className="mt-4 text-sm leading-relaxed text-muted">
              A small retrieval-only advice demo. Source-backed mix-engineering guidance,
              with an explicit boundary when the approved knowledge isn&apos;t enough.
            </p>
          </div>
          <div className="mt-8">
            <KennChatWidget />
          </div>
        </div>
      </section>

      {/* Boundaries */}
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
        </div>
      </section>

      {/* Waitlist */}
      <section id="join-waitlist" className="section section-rule">
        <div className="site-container">
          <div className="grid gap-12 lg:grid-cols-[1fr_1fr] lg:items-start">
            <div>
              <span className="eyebrow text-brand-violet-text">Early Access</span>
              <h2 className="section-title mt-4 text-foreground">Join the first 50.</h2>
              <p className="mt-4 text-sm leading-relaxed text-muted">
                KENN is in active development. We&apos;re opening early access to a small group
                of producers and engineers who want to help shape the product.
              </p>
              <ul className="mt-6 space-y-3 text-sm text-muted">
                <li className="flex gap-3 items-start">
                  <span className="text-brand-violet-text font-bold">01</span>
                  <span>Join the waitlist. Your place is held</span>
                </li>
                <li className="flex gap-3 items-start">
                  <span className="text-brand-violet-text font-bold">02</span>
                  <span>We&apos;ll email you when your beta access is ready</span>
                </li>
                <li className="flex gap-3 items-start">
                  <span className="text-brand-violet-text font-bold">03</span>
                  <span>Test KENN inside Ableton Live and shape what ships</span>
                </li>
              </ul>
            </div>
            <WaitlistForm productId="kenn" capacity={50} />
          </div>
        </div>
      </section>
    </>
  );
}
