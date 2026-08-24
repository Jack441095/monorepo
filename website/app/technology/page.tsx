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
