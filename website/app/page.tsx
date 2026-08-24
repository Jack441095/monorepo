import Image from "next/image";
import Link from "next/link";
import { AudioAnalysisDemo } from "@/components/AudioAnalysisDemo";
import { SignalJourney } from "@/components/SignalJourney";
import { LightField } from "@/components/motion/LightField";
import { Magnetic } from "@/components/motion/Magnetic";
import { Reveal } from "@/components/motion/Reveal";
import { TiltSurface } from "@/components/motion/TiltSurface";
import { WorkflowFlow } from "@/components/motion/WorkflowFlow";

const WORKFLOWS = [
  [
    "01",
    "Scan your local sample drives",
    "SLO indexes your existing directories, extracting features directly from the audio signal. It caches results locally, making subsequent rescans instantaneous."
  ],
  [
    "02",
    "Bypass cryptically named folders",
    "Search by sonic timbre, spectral balance, and transients instead of folder tags or cryptic names. Discover forgotten gems buried deep in old directories."
  ],
  [
    "03",
    "Compare and drag to timeline",
    "Audition samples side-by-side inside the precision browser, map, or split view. Drag your selected sound straight into Ableton Live or any other DAW timeline."
  ],
] as const;

const CAPABILITIES = [
  ["Precision Browser", "A dense, structured layout highlighting name, category, key, BPM, and length."],
  ["Visual Map", "Browse visually. Sounds are plotted based on acoustic similarity—close clusters share similar timbres."],
  ["Find Similar", "Select a reference sample and immediately view all acoustically matching sounds in your library."],
  ["Local Analysis", "Sample analysis runs locally on your Mac. Your audio is not uploaded for classification."],
] as const;

export default function HomePage() {
  return (
    <>
      {/* Homepage Hero */}
      <section className="hero-grid overflow-hidden relative">
        <LightField />
        <div className="site-container relative grid items-center gap-12 py-16 lg:grid-cols-[0.85fr_1.15fr] lg:py-24">
          <div className="relative z-10">
            <span className="eyebrow">NITE DSP // FLAGSHIP</span>
            <h1 className="hero-title mt-5">Your sample library, organised by sound.</h1>
            <p className="hero-copy mt-6">
              SLO (Sample Library Optimiser) is a professional macOS sample browser that analyses actual audio signals rather than relying on folder structures or filenames.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Link href="/products/smart-sample-manager" className="btn-primary">
                <Magnetic>Explore SLO</Magnetic>
              </Link>
              <Link href="/pricing" className="btn-secondary">
                View pricing
              </Link>
            </div>
            <p className="mt-6 text-xs" style={{ color: "var(--muted-dim)" }}>
              macOS &middot; VST3 &middot; AU &middot; Standalone &middot; Native Apple Silicon
            </p>
          </div>

          <TiltSurface className="relative z-10 product-frame--hero">
            <div className="product-frame">
              <div className="product-frame__bar" data-depth="1.5">
                <span>SLO // SAMPLE LIBRARY OPTIMISER</span>
                <span>SPLIT VIEW</span>
              </div>
              <div data-depth="3">
                <Image
                  src="/screenshots/main-browser.png"
                  alt="SLO flagship interface showing a searchable sample browser and selected sample details panel"
                  width={1599}
                  height={1057}
                  priority
                  sizes="(max-width: 1024px) 100vw, 58vw"
                  className="h-auto w-full block"
                />
              </div>
            </div>
          </TiltSurface>
        </div>
      </section>

      {/* The NITE Signal Journey — company-level signal flow */}
      <SignalJourney />

      {/* The Core Problem & Audio-First Positioning */}
      <section className="section section-rule">
        <div className="site-container grid gap-12 lg:grid-cols-[0.8fr_1.2fr] lg:items-start">
          <Reveal>
            <span className="eyebrow">The Signal vs The Filename</span>
            <h2 className="section-title mt-4">Folders are for storage. Not for discovery.</h2>
          </Reveal>
          <Reveal delayMs={90}>
            <p className="body-large">
              A sample&apos;s filename is often meaningless (e.g. <code>XK29_0047.wav</code>). Standard folder trees hide your best sounds in nested archives.
            </p>
            <p className="mt-6 text-base leading-relaxed" style={{ color: "var(--muted)" }}>
              SLO bypasses metadata dependencies entirely. By analysing the spectral and transient characteristics of the audio itself, it automatically categorises your library (e.g. identifying a kick, snare, or synth pad) and places similar timbres close together.
            </p>
          </Reveal>
        </div>
      </section>

      {/* Interactive Audio-First Demo Section */}
      <section className="section section-rule bg-surface/30">
        <div className="site-container grid gap-12 lg:grid-cols-[1fr_1.1fr] lg:items-center">
          <Reveal>
            <span className="eyebrow">Interactive Demo</span>
            <h2 className="section-title mt-4">See how SLO listens to your files.</h2>
            <p className="mt-6 leading-relaxed" style={{ color: "var(--muted)" }}>
              Click any cryptic filename to see how the local DSP engine scans the waveform, identifies key transient structures, and classifies the sound into its true instrument category.
            </p>
            <div className="mt-8 flex flex-col gap-4 border-l-2 border-brand-violet pl-5">
              <div>
                <h4 className="font-semibold text-foreground text-sm">Audio analysis, not text guesses</h4>
                <p className="text-xs text-muted mt-1">We don&apos;t match words or tag descriptions. SLO compares timbral character directly.</p>
              </div>
              <div>
                <h4 className="font-semibold text-foreground text-sm">Fully local metadata</h4>
                <p className="text-xs text-muted mt-1">Scanning takes place locally on your Mac. Your audio files are never uploaded for classification.</p>
              </div>
            </div>
          </Reveal>
          <Reveal delayMs={90}>
            <AudioAnalysisDemo />
          </Reveal>
        </div>
      </section>

      {/* Workflow Steps — the connector traces signal progress as you read */}
      <section className="section section-rule">
        <div className="site-container">
          <Reveal>
            <div className="max-w-2xl">
              <span className="eyebrow">Precision Engineering</span>
              <h2 className="section-title mt-4">Streamline your sample library workflow.</h2>
            </div>
          </Reveal>
          <WorkflowFlow steps={WORKFLOWS} />
        </div>
      </section>

      {/* Key Capabilities */}
      <section className="section section-rule">
        <div className="site-container">
          <div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-end">
            <Reveal>
              <div className="max-w-2xl">
                <span className="eyebrow">System Capabilities</span>
                <h2 className="section-title mt-4">An instrument built for audio producers.</h2>
              </div>
            </Reveal>
            <Link href="/products/smart-sample-manager" className="text-link">
              Read SLO specifications <span aria-hidden="true">&rarr;</span>
            </Link>
          </div>
          <div className="capability-grid spotlight-group mt-10">
            {CAPABILITIES.map(([title, body]) => (
              <article key={title} className="capability">
                <h3 className="text-foreground">{title}</h3>
                <p>{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* Bottom CTA Panel */}
      <section className="section section-rule">
        <div className="site-container cta-panel depth-hover">
          <div>
            <span className="eyebrow">Get Started</span>
            <h2 className="section-title mt-4 text-foreground">Find the sound. Finish the track.</h2>
          </div>
          <div className="flex flex-wrap gap-3 relative z-10">
            <Link href="/pricing" className="btn-primary">
              <Magnetic>See pricing</Magnetic>
            </Link>
            <Link href="/learn" className="btn-secondary">
              Read guides
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
