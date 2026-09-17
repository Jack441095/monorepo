import type { Metadata } from "next";
import Link from "next/link";
import { AudioAnalysisDemo } from "@/components/AudioAnalysisDemo";
import { CtaButton } from "@/components/CtaButton";
import { SubmitPrepDemo } from "@/components/demo/SubmitPrepDemo";
import { SignalJourney } from "@/components/SignalJourney";
import { LightField } from "@/components/motion/LightField";
import { Magnetic } from "@/components/motion/Magnetic";
import { Reveal } from "@/components/motion/Reveal";
import { StatusDot } from "@/components/motion/StatusDot";
import { TiltSurface } from "@/components/motion/TiltSurface";
import { WorkflowFlow } from "@/components/motion/WorkflowFlow";
import { WaitlistCounter } from "@/components/WaitlistForm";

// The homepage previously inherited the layout default ("NITE DSP", no
// canonical), which it shared verbatim with every page that lacked its own
// metadata. `absolute` keeps the brand first here rather than running it
// through the "%s | NITE DSP" template.
export const metadata: Metadata = {
  title: { absolute: "NITE DSP | Intelligent tools for creative workflows" },
  description:
    "NITE DSP builds local-first macOS tools for producers and students: Submit for document preparation, SLO for acoustic sample search, and KENN for mix review.",
  alternates: { canonical: "/" },
  openGraph: {
    title: "NITE DSP | Intelligent tools for creative workflows",
    description:
      "Local-first macOS tools for producers and students: Submit, SLO, and KENN.",
    url: "/",
    siteName: "NITE DSP",
    type: "website",
  },
};

const ECOSYSTEM = [
  {
    name: "Submit",
    family: "Family 1 - General",
    line: "Prepare the right submission.",
    body: "Local macOS document-preparation assistant. Drop in a file, review detected fields, and save a safe copy. Local check, zero uploads.",
    href: "/products/submit",
    status: "Waitlist Open",
    tone: "success" as const,
    waitlistId: "submit",
  },
  {
    name: "SLO",
    family: "Family 2 - Audio",
    line: "Find sounds by how they sound.",
    body: "Search your sample library by acoustic timbre rather than cryptic folder names. Audition matches and drag straight to your DAW. First 50 beta spots are open now.",
    href: "/products/smart-sample-manager",
    status: "Waitlist Open",
    tone: "success" as const,
    waitlistId: "smart-sample-manager",
  },
  {
    name: "KENN",
    family: "Family 2 - Audio",
    line: "Your AI audio assistant for Ableton.",
    body: "Lives inside Ableton Live. Listens to your mix, explains what it hears, and helps you make better decisions. Closed beta, not for sale yet.",
    href: "/products/kenn",
    status: "Closed Beta",
    tone: "warning" as const,
    waitlistId: "kenn",
  },
  {
    name: "Thursday",
    family: "Family 3 - Internal",
    line: "Operational infrastructure.",
    body: "Internal operational layer coordinating workflows across NITE DSP tools. Internal infrastructure, not a public commercial chatbot.",
    href: "/thursday",
    status: "Internal",
    tone: "muted" as const,
  },
];

const STATUS_STYLE = {
  success: { borderColor: "rgba(16,185,129,0.4)", color: "var(--state-success)" },
  warning: { borderColor: "var(--state-warning-border)", color: "var(--state-warning)" },
  muted: { borderColor: "var(--border-strong)", color: "var(--muted)" },
} as const;

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
  ["Precision Browser", "A structured, spreadsheet-like interface highlighting timbral attributes, transient decay, musical key, and true category."],
  ["Acoustic Similarity Map", "Browse visually. High-dimensional acoustic vectors are plotted on a 2D coordinate plane, and close clusters share similar timbres."],
  ["Find Similar", "Select any reference sound and instantly query all acoustically matching files in your local database."],
  ["100% Offline Inference", "All mathematical models and feature extractions execute locally. Your audio files never leave your machine."],
] as const;

export default function HomePage() {
  return (
    <>
      {/* Homepage Hero, unified company proposition */}
      <section className="hero-grid overflow-hidden relative">
        <LightField />
        <div className="site-container relative py-16 lg:py-24 text-center" style={{ maxWidth: "56rem" }}>
          <span className="eyebrow">NITE DSP // INTELLIGENT CREATIVE TOOLS</span>
          <h1 className="hero-title mt-5">
            Tools built for the way you actually work.
          </h1>
          <p className="hero-copy mt-6 mx-auto">
            Document prep, sample discovery, mix feedback. Local-first macOS software
            that runs on your machine and stays out of your way.
          </p>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <Link href="/products" className="btn-primary">
              <Magnetic>Explore the products</Magnetic>
            </Link>
            <CtaButton state="BETA_REQUEST" label="Request beta access" secondary />
          </div>
          <p className="mt-6 text-xs" style={{ color: "var(--muted-dim)" }}>
            macOS 13+ &middot; Apple Silicon &middot; Local processing &middot; No uploads
          </p>
        </div>
      </section>

      {/* Product Ecosystem */}
      <section className="section section-rule">
        <div className="site-container">
          <Reveal>
            <div className="max-w-2xl">
              <span className="eyebrow">The Products</span>
              <h2 className="section-title mt-4">Three tools, one direction.</h2>
              <p className="mt-4 text-sm text-muted leading-relaxed font-sans">
                Document preparation, sample search, and mix feedback. Each one solves a real problem, runs offline, and doesn&apos;t phone home.
              </p>
            </div>
          </Reveal>
          <div className="spotlight-group mt-10 grid gap-6 sm:grid-cols-2">
            {ECOSYSTEM.map((p) => (
              <Reveal key={p.name}>
                <Link
                  href={p.href}
                  className="surface-card depth-hover p-6 rounded-lg border border-border/40 flex flex-col min-h-[15rem]"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[9px] font-mono font-bold uppercase tracking-wider text-brand-blue-bright">
                      {p.family}
                    </span>
                    <span
                      className="status-chip text-[9px] uppercase font-mono tracking-wider px-2 py-0.5 rounded border"
                      style={STATUS_STYLE[p.tone]}
                    >
                      <StatusDot tone={p.tone === "success" ? "live" : p.tone === "muted" ? "muted" : "warning"} />
                      {p.status}
                    </span>
                  </div>
                  <h3 className="text-xl font-bold text-foreground mt-3">{p.name}</h3>
                  <p className="mt-1 text-sm font-medium" style={{ color: "var(--brand-blue-bright)" }}>
                    {p.line}
                  </p>
                  <p className="mt-3 text-xs leading-relaxed text-muted font-sans">{p.body}</p>
                  {"waitlistId" in p && p.waitlistId && (
                    <div className="mt-3">
                      <WaitlistCounter productId={p.waitlistId} />
                    </div>
                  )}
                  <span className="text-link mt-auto pt-4 text-xs font-sans">Learn more <span aria-hidden="true">&rarr;</span></span>
                </Link>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* The NITE Signal Journey, company-level signal flow */}
      <SignalJourney />

      {/* Interactive Demonstrations */}
      <section className="section section-rule bg-surface/10">
        <div className="site-container">
          <Reveal>
            <span className="eyebrow">Product Demonstrations</span>
            <h2 className="section-title mt-4">See how the tools think.</h2>
            <p className="mt-4 text-sm max-w-2xl text-muted">
              Simulated walkthroughs running entirely in your browser with illustrative data:
              nothing is uploaded, nothing is processed externally.
            </p>
          </Reveal>

          <div className="mt-12 grid grid-cols-1 lg:grid-cols-[1.15fr_0.85fr] gap-8 items-center">
            <Reveal>
              <TiltSurface className="product-frame--hero">
                <SubmitPrepDemo />
              </TiltSurface>
            </Reveal>
            <Reveal delayMs={90}>
              <span className="u-label" style={{ color: "var(--brand-blue-bright)" }}>SUBMIT</span>
              <h3 className="mt-2 text-lg font-semibold text-foreground">
                Drop &rarr; Understand &rarr; Review &rarr; Prepare &rarr; Verify &rarr; Receipt
              </h3>
              <p className="mt-3 text-xs leading-relaxed text-muted">
                Submit reviews document structure locally, flags uncertain fields for your approval,
                and saves a safely named copy. It never submits work for you and never modifies your
                original file.
              </p>
              <Link href="/products/submit" className="text-link mt-4 inline-block text-xs">
                Explore Submit <span aria-hidden="true">&rarr;</span>
              </Link>
            </Reveal>
          </div>
        </div>
      </section>

      {/* The Core Problem & Audio-First Positioning */}
      <section className="section section-rule">
        <div className="site-container grid gap-12 lg:grid-cols-[0.8fr_1.2fr] lg:items-start">
          <Reveal>
            <span className="eyebrow">The Signal vs The Filename</span>
            <h2 className="section-title mt-4">Bypass folder structures. Rely on mathematical similarity.</h2>
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
            <h2 className="section-title mt-4">Hear the difference between your samples, not just the names.</h2>
            <p className="mt-6 leading-relaxed" style={{ color: "var(--muted)" }}>
              Click any filename to see how SLO scans the waveform, picks out the transient shape, and works out what kind of sound it actually is.
            </p>
            <div className="mt-8 flex flex-col gap-4 border-l-2 border-brand-violet pl-5">
              <div>
                <h3 className="font-semibold text-foreground text-sm">Acoustic feature extraction</h3>
                <p className="text-xs text-muted mt-1">We measure spectral centroid, transient rise time, and tonal stability directly from the raw waveform.</p>
              </div>
              <div>
                <h3 className="font-semibold text-foreground text-sm">100% Local Inference</h3>
                <p className="text-xs text-muted mt-1">Signal analysis and similarity calculations run entirely on your machine. Your audio never leaves.</p>
              </div>
            </div>
          </Reveal>
          <Reveal delayMs={90}>
            <AudioAnalysisDemo />
          </Reveal>
        </div>
      </section>

      {/* Workflow Steps, the connector traces signal progress as you read */}
      <section className="section section-rule">
        <div className="site-container">
          <Reveal>
            <div className="max-w-2xl">
              <span className="eyebrow">How It Works</span>
              <h2 className="section-title mt-4">From raw drives to instant results.</h2>
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
                <span className="eyebrow">Features</span>
                <h2 className="section-title mt-4">Built for the way producers actually work.</h2>
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
            <p className="mt-2 text-sm text-muted">Both waitlists are open. First 50 spots each.</p>
          </div>
          <div className="flex flex-wrap gap-3 relative z-10">
            <Link href="/products/submit#join-waitlist" className="btn-primary">
              Join Submit waitlist
            </Link>
            <Link href="/products/smart-sample-manager#join-waitlist" className="btn-secondary">
              Join SLO waitlist
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
