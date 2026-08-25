import type { Metadata } from "next";
import Link from "next/link";
import { StatusDot } from "@/components/motion/StatusDot";
import { Reveal } from "@/components/motion/Reveal";
import { TiltSurface } from "@/components/motion/TiltSurface";
import { SubmitPrepDemo } from "@/components/demo/SubmitPrepDemo";
import { KennMixDemo } from "@/components/demo/KennMixDemo";

export const metadata: Metadata = {
  title: "Product Families — NITE DSP",
  description: "Focused tools for creative workflows by NITE DSP: document preparation intelligence, audio intelligence, and internal orchestration.",
  alternates: { canonical: "/products" },
};

export default function ProductsPage() {
  return (
    <>
      {/* Products Hero */}
      <section className="section product-hero">
        <div className="site-container">
          <span className="eyebrow">Product Families</span>
          <h1 className="section-title mt-4 text-foreground">Focused tools for creative workflows.</h1>
          <p className="body-large mt-6 max-w-2xl text-muted leading-relaxed">
            NITE DSP builds local-first software for creative work: starting with document preparation, then extending into audio intelligence for sample discovery and mix understanding.
          </p>
        </div>
      </section>

      {/* FAMILY 01: Workflow Intelligence */}
      <section className="section-rule bg-surface/10">
        <div className="site-container py-12 sm:py-16">
          <div className="flex items-center gap-3 mb-6">
            <span className="dsp-pill text-brand-blue-bright border-brand-blue/30 font-mono text-[10px] font-bold uppercase tracking-wider">
              FAMILY 01 // WORKFLOW INTELLIGENCE
            </span>
            <span className="text-xs text-muted-dim font-sans font-medium">Document Safety & Submission Readiness</span>
          </div>

          <TiltSurface maxTiltDeg={1.2}>
            <div className="surface-card p-8 sm:p-12 relative overflow-hidden border border-brand-blue/30 rounded-lg">
              <div className="absolute top-0 right-0 w-96 h-96 bg-gradient-to-bl from-brand-blue/10 via-brand-emerald/5 to-transparent pointer-events-none rounded-full blur-3xl" />

              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <span className="chip-neutral status-chip font-mono text-[10px] border-brand-blue-bright text-brand-blue-bright">
                    <StatusDot tone="live" live />
                    Private Beta RC1
                  </span>
                  <h2 className="mt-5 text-4xl font-bold text-foreground tracking-tight">NITE Submit</h2>
                  <p className="text-sm font-mono text-muted-dim mt-1.5">Submission Preparation Intelligence</p>
                </div>
                <Link href="/products/submit" className="btn-primary">
                  Explore NITE Submit &rarr;
                </Link>
              </div>

              <p className="mt-6 max-w-2xl text-base leading-relaxed text-muted font-sans">
                A local macOS document-preparation assistant that detects useful PDF details, explains uncertainty, and creates a safely named copy before submission. No upload or account required for local review.
              </p>

              <div className="mt-10 pt-8 border-t border-border/50 grid gap-6 sm:grid-cols-3 text-xs font-mono tnum">
                <div>
                  <span className="text-muted-dim block uppercase">CATEGORY</span>
                  <span className="text-foreground font-semibold mt-1 block">Workflow Intelligence</span>
                </div>
                <div>
                  <span className="text-muted-dim block uppercase">PLATFORM</span>
                  <span className="text-foreground font-semibold mt-1 block">macOS 13+ (Apple Silicon)</span>
                </div>
                <div>
                  <span className="text-muted-dim block uppercase">DATA PRIVACY</span>
                  <span className="text-foreground font-semibold mt-1 block">Local Check · 0 Uploads</span>
                </div>
              </div>
            </div>
          </TiltSurface>
        </div>
      </section>

      {/* FAMILY 02: Audio Intelligence */}
      <section className="section section-rule bg-surface/20">
        <div className="site-container py-12 sm:py-16">
          <div className="flex items-center gap-3 mb-6">
            <span className="dsp-pill text-brand-violet border-brand-violet/30 font-mono text-[10px] font-bold uppercase tracking-wider">
              FAMILY 02 // AUDIO INTELLIGENCE
            </span>
            <span className="text-xs text-muted-dim font-sans font-medium">Sample Discovery & Mix Understanding</span>
          </div>

          <div className="grid gap-8 md:grid-cols-2">
            {/* SLO */}
            <div className="surface-card depth-hover p-8 rounded-lg border border-border/60 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between gap-3">
                  <span className="status-chip text-[9px] uppercase font-mono tracking-wider px-2 py-0.5 rounded border border-amber-500/30 text-amber-400">
                    <StatusDot tone="warning" />
                    Private Beta / Research
                  </span>
                  <span className="text-[10px] font-mono text-muted-dim">AUDIO DSP</span>
                </div>
                <h3 className="mt-5 text-2xl font-bold text-foreground">SLO</h3>
                <p className="text-xs font-mono text-muted-dim mt-1">Sample Library Optimiser</p>
                <p className="mt-4 text-sm leading-relaxed text-muted font-sans">
                  An acoustic-similarity sample browser for macOS. Find sounds by how they sound, not just how they are named. Audition timbral matches and drag directly into Ableton Live or any DAW timeline.
                </p>
              </div>
              <div className="mt-8 pt-4 border-t border-border/40 flex items-center justify-between">
                <span className="text-[10px] font-mono text-muted-dim">TIMBRAL FEATURE SEARCH</span>
                <Link href="/products/smart-sample-manager" className="text-link text-xs font-sans">
                  View SLO &rarr;
                </Link>
              </div>
            </div>

            {/* KENN */}
            <div className="surface-card depth-hover p-8 rounded-lg border border-brand-violet/30 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between gap-3">
                  <span className="status-chip text-[9px] uppercase font-mono tracking-wider px-2 py-0.5 rounded border border-brand-violet/40 text-brand-violet">
                    <StatusDot tone="warning" />
                    In Development / Concept
                  </span>
                  <span className="text-[10px] font-mono text-muted-dim">AI AUDIO ASSISTANT</span>
                </div>
                <h3 className="mt-5 text-2xl font-bold text-foreground">KENN</h3>
                <p className="text-xs font-mono text-muted-dim mt-1">Mix Understanding Assistant</p>
                <p className="mt-4 text-sm leading-relaxed text-muted font-sans">
                  Explainable mix analysis that observes acoustic dimensions, explains reasoning, and suggests tweaks. KENN assists engineers—every final decision remains yours.
                </p>
              </div>
              <div className="mt-8 pt-4 border-t border-border/40 flex items-center justify-between">
                <span className="text-[10px] font-mono text-muted-dim">EXPLAINABLE MIX ADVICE</span>
                <Link href="/products/kenn" className="text-link text-xs font-sans">
                  Explore Concept &rarr;
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FAMILY 03: Internal Systems */}
      <section className="section section-rule">
        <div className="site-container py-12 sm:py-16">
          <div className="flex items-center gap-3 mb-6">
            <span className="dsp-pill text-muted-dim border-border-strong font-mono text-[10px] font-bold uppercase tracking-wider">
              FAMILY 03 // INTERNAL SYSTEMS
            </span>
            <span className="text-xs text-muted-dim font-sans font-medium">Orchestration & Operational Infrastructure</span>
          </div>

          <div className="surface-card p-8 rounded-lg border border-border/50 bg-surface-raised/40">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <span className="status-chip text-[9px] uppercase font-mono tracking-wider px-2 py-0.5 rounded border border-border/60 text-muted-dim">
                  Internal Operational Layer
                </span>
                <h3 className="mt-4 text-2xl font-bold text-foreground">Thursday</h3>
                <p className="text-xs font-mono text-muted-dim mt-1">NITE DSP Internal Orchestration System</p>
              </div>
              <Link href="/thursday" className="text-link text-xs font-sans">
                Internal Architecture &rarr;
              </Link>
            </div>

            <p className="mt-4 text-sm text-muted leading-relaxed max-w-2xl font-sans">
              Thursday is our internal infrastructure layer coordinating workflows and specialized agent execution across NITE DSP tools. Thursday is not a public commercial chatbot or customer-facing product.
            </p>
          </div>
        </div>
      </section>

      {/* Interactive Demonstrations */}
      <section className="section section-rule bg-surface/10">
        <div className="site-container">
          <Reveal>
            <div className="max-w-2xl">
              <span className="eyebrow block">Interactive Demonstrations</span>
              <h2 className="section-title mt-4">Experience the intelligence before it ships.</h2>
              <p className="mt-4 text-sm max-w-2xl text-muted font-sans">
                Simulated walkthroughs of how NITE DSP products think. Every demonstration runs entirely in your browser with illustrative data — nothing is uploaded, nothing is processed externally.
              </p>
            </div>
          </Reveal>

          <div className="mt-12 grid grid-cols-1 gap-8 lg:grid-cols-2 items-start">
            <Reveal>
              <div className="mb-4">
                <span className="text-[10px] font-mono font-bold text-brand-blue-bright uppercase block mb-1">WORKFLOW INTELLIGENCE</span>
                <h3 className="text-lg font-semibold text-foreground">Submit — prepare files safely</h3>
                <p className="text-xs text-muted mt-1 max-w-md font-sans">
                  Document intelligence that reviews important files locally and flags what needs attention before you submit.
                </p>
              </div>
              <SubmitPrepDemo />
            </Reveal>
            <Reveal delayMs={90}>
              <div className="mb-4">
                <span className="text-[10px] font-mono font-bold text-brand-violet uppercase block mb-1">AUDIO INTELLIGENCE</span>
                <h3 className="text-lg font-semibold text-foreground">KENN — mix review, explained</h3>
                <p className="text-xs text-muted mt-1 max-w-md font-sans">
                  An AI audio engineering assistant concept: analyse a mix, understand the acoustic reasoning, make better creative decisions.
                </p>
              </div>
              <KennMixDemo />
            </Reveal>
          </div>
        </div>
      </section>
    </>
  );
}
