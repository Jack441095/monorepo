import type { Metadata } from "next";
import { LightField } from "@/components/motion/LightField";
import { Reveal } from "@/components/motion/Reveal";

export const metadata: Metadata = {
  title: "Technology & DSP Architecture",
  description: "Acoustic signal processing, local dimension reduction, and vectorised search engines by NITE DSP.",
  alternates: { canonical: "/technology" },
};

const PIPELINE_STEPS = [
  {
    step: "01",
    name: "Windowed Spectral Analysis",
    details: "Raw PCM audio buffers are windowed using Hann functions and processed via standard Fast Fourier Transforms (FFT) at 2048-sample window lengths, establishing high-resolution frequency domain mapping.",
  },
  {
    step: "02",
    name: "Mel-Frequency Spacing",
    details: "Power spectra are mapped onto the Mel scale, reflecting the logarithmic pitch spacing of human hearing and extracting 13 mel-frequency cepstral coefficients (MFCCs) to map timbral character.",
  },
  {
    step: "03",
    name: "Transient Signature Extraction",
    details: "Sub-band energy changes are tracked across frames to identify transient onset rise times and decay envelopes, determining the structural envelopes of sounds.",
  },
  {
    step: "04",
    name: "Acoustic Dimension Reduction",
    details: "MFCC vectors and envelope parameters are combined into high-dimensional signatures. Local dimension reduction models map these down to a coordinates grid, placing similar sounds near each other.",
  },
] as const;

export default function TechnologyPage() {
  return (
    <>
      {/* Hero Section */}
      <section className="section product-hero relative overflow-hidden">
        <LightField />
        <div className="site-container relative">
          <span className="eyebrow">Technical Estate</span>
          <h1 className="section-title mt-4 text-foreground">The science behind NITE DSP.</h1>
          <p className="body-large mt-6">
            We build creative tools around actual audio signals. By doing math on your local CPU cores rather than sending files to remote servers, we guarantee absolute privacy and zero workflow latency.
          </p>
        </div>
      </section>

      {/* Signal Journey Layout */}
      <section className="section section-rule">
        <div className="site-container">
          <Reveal>
            <div className="max-w-2xl">
              <span className="eyebrow">DSP Engine</span>
              <h2 className="section-title mt-4">The Local Extraction Pipeline</h2>
              <p className="mt-4 text-sm text-muted">
                How SLO reads, analyses, and understands audio signals without relying on file names.
              </p>
            </div>
          </Reveal>

          {/* Schematic Signal Flow */}
          <div className="product-frame my-12 p-6 bg-surface-raised flex items-center justify-center border border-border-strong/40 rounded-lg">
            <div className="w-full overflow-x-auto">
              <svg className="mx-auto block min-w-[800px]" width="820" height="150" viewBox="0 0 820 150" fill="none" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <linearGradient id="flow-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="var(--brand-blue)" />
                    <stop offset="50%" stopColor="var(--brand-violet)" stopOpacity="0.8" />
                    <stop offset="100%" stopColor="var(--brand-blue-bright)" />
                  </linearGradient>
                  <filter id="glow" x="-10%" y="-10%" width="120%" height="120%">
                    <feGaussianBlur stdDeviation="4" result="blur" />
                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                  </filter>
                </defs>

                {/* Connecting Lines */}
                <path d="M 125 75 L 205 75" stroke="url(#flow-grad)" strokeWidth="2" strokeDasharray="4 4" />
                <path d="M 295 75 L 375 75" stroke="url(#flow-grad)" strokeWidth="2" />
                <path d="M 465 75 L 545 75" stroke="url(#flow-grad)" strokeWidth="2" strokeDasharray="4 4" />
                <path d="M 635 75 L 715 75" stroke="url(#flow-grad)" strokeWidth="2" />

                {/* Node 1: RAW PCM */}
                <g transform="translate(15, 30)">
                  <rect width="110" height="90" rx="8" fill="var(--surface)" stroke="var(--border-strong)" strokeWidth="1" />
                  <path d="M 20 45 Q 35 15 50 45 T 80 45 T 90 45" stroke="var(--brand-blue)" strokeWidth="1.5" fill="none" />
                  <circle cx="50" cy="45" r="3" fill="var(--brand-blue-bright)" filter="url(#glow)" />
                  <text x="55" y="76" textAnchor="middle" fill="var(--foreground)" className="font-mono text-[9px] uppercase tracking-wider font-semibold">01 / RAW PCM</text>
                </g>

                {/* Node 2: FFT WINDOW */}
                <g transform="translate(185, 30)">
                  <rect width="110" height="90" rx="8" fill="var(--surface)" stroke="var(--border-strong)" strokeWidth="1" />
                  {/* FFT bins */}
                  <line x1="30" y1="55" x2="30" y2="35" stroke="var(--brand-violet)" strokeWidth="2" />
                  <line x1="42" y1="55" x2="42" y2="25" stroke="var(--brand-violet)" strokeWidth="2" />
                  <line x1="54" y1="55" x2="54" y2="15" stroke="var(--brand-violet)" strokeWidth="2" />
                  <line x1="66" y1="55" x2="66" y2="30" stroke="var(--brand-violet)" strokeWidth="2" />
                  <line x1="78" y1="55" x2="78" y2="40" stroke="var(--brand-violet)" strokeWidth="2" />
                  <text x="55" y="76" textAnchor="middle" fill="var(--foreground)" className="font-mono text-[9px] uppercase tracking-wider font-semibold">02 / FFT BINS</text>
                </g>

                {/* Node 3: MEL SPACING */}
                <g transform="translate(355, 30)">
                  <rect width="110" height="90" rx="8" fill="var(--surface)" stroke="var(--border-strong)" strokeWidth="1" />
                  {/* Mel Curve */}
                  <path d="M 25 50 C 45 48 70 30 85 20" stroke="var(--brand-blue-bright)" strokeWidth="1.5" fill="none" />
                  <line x1="35" y1="50" x2="35" y2="47" stroke="var(--muted-dim)" strokeWidth="1" />
                  <line x1="50" y1="50" x2="50" y2="42" stroke="var(--muted-dim)" strokeWidth="1" />
                  <line x1="65" y1="50" x2="65" y2="32" stroke="var(--muted-dim)" strokeWidth="1" />
                  <line x1="80" y1="50" x2="80" y2="23" stroke="var(--muted-dim)" strokeWidth="1" />
                  <text x="55" y="76" textAnchor="middle" fill="var(--foreground)" className="font-mono text-[9px] uppercase tracking-wider font-semibold">03 / MEL SCALE</text>
                </g>

                {/* Node 4: MFCC VECTOR */}
                <g transform="translate(525, 30)">
                  <rect width="110" height="90" rx="8" fill="var(--surface)" stroke="var(--border-strong)" strokeWidth="1" />
                  {/* Matrix vector */}
                  <rect x="25" y="20" width="60" height="6" rx="2" fill="var(--brand-blue)" opacity="0.3" />
                  <rect x="25" y="30" width="45" height="6" rx="2" fill="var(--brand-blue)" opacity="0.6" />
                  <rect x="25" y="40" width="55" height="6" rx="2" fill="var(--brand-blue)" />
                  <text x="55" y="76" textAnchor="middle" fill="var(--foreground)" className="font-mono text-[9px] uppercase tracking-wider font-semibold">04 / MFCC VECTOR</text>
                </g>

                {/* Node 5: 2D MAP */}
                <g transform="translate(695, 30)">
                  <rect width="110" height="90" rx="8" fill="var(--surface)" stroke="var(--border-strong)" strokeWidth="1" />
                  {/* Scatter plot */}
                  <circle cx="35" cy="25" r="2.5" fill="var(--brand-blue-bright)" />
                  <circle cx="45" cy="40" r="3.5" fill="var(--brand-violet)" filter="url(#glow)" />
                  <circle cx="75" cy="30" r="2" fill="var(--brand-blue-bright)" />
                  <circle cx="65" cy="45" r="2.5" fill="var(--brand-blue)" />
                  <circle cx="80" cy="50" r="3" fill="var(--brand-violet)" />
                  <text x="55" y="76" textAnchor="middle" fill="var(--foreground)" className="font-mono text-[9px] uppercase tracking-wider font-semibold">05 / similarity MAP</text>
                </g>
              </svg>
            </div>
          </div>

          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {PIPELINE_STEPS.map((p) => (
              <div key={p.step} className="surface-card p-6 border border-border/40 rounded-lg flex flex-col justify-between min-h-[14rem]">
                <div>
                  <span className="font-mono text-xs text-brand-blue-bright font-semibold">{p.step}</span>
                  <h3 className="mt-3 font-semibold text-foreground text-sm">{p.name}</h3>
                  <p className="mt-2 text-xs leading-relaxed text-muted">{p.details}</p>
                </div>
                <span className="text-[9px] font-mono text-muted-dim tracking-wider uppercase pt-4 border-t border-border/30 mt-4">
                  CORE PIPELINE STAGE
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Under the hood metrics */}
      <section className="section section-rule bg-surface/10">
        <div className="site-container grid gap-12 lg:grid-cols-[0.8fr_1.2fr] lg:items-start">
          <Reveal>
            <span className="eyebrow">Hardware Optimisation</span>
            <h2 className="section-title mt-4">Built for local performance.</h2>
          </Reveal>
          <Reveal delayMs={90}>
            <div className="space-y-8">
              <div className="surface-card p-6 border border-border/40 rounded-lg">
                <h3 className="font-semibold text-foreground text-base">C++ Vectorised Similarity Checks</h3>
                <p className="mt-3 text-sm leading-relaxed text-muted">
                  The similarity engine uses hardware-accelerated dot product instructions (using Apple Silicon NEON registers and Intel AVX instruction sets) to check up to 10,000 files in under 2 milliseconds.
                </p>
              </div>

              <div className="surface-card p-6 border border-border/40 rounded-lg">
                <h3 className="font-semibold text-foreground text-base">Local SQLite Index Architecture</h3>
                <p className="mt-3 text-sm leading-relaxed text-muted">
                  A local database is written to <code>~/Library/Application Support/NITE/SLO/</code>. Instead of altering your original library directory structure, the virtual browser indexes files safely in read-only mode.
                </p>
              </div>

              <div className="surface-card p-6 border border-border/40 rounded-lg">
                <h3 className="font-semibold text-foreground text-base">Zero Cloud Telemetry</h3>
                <p className="mt-3 text-sm leading-relaxed text-muted">
                  We believe your creative library is your competitive advantage. By running 100% offline signal classification in memory, your original works remain on your hard drives and never touch external servers.
                </p>
              </div>
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
