import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { AudioAnalysisDemo } from "@/components/AudioAnalysisDemo";

export const metadata: Metadata = {
  title: "SLO — Sample Library Optimiser",
  description:
    "An acoustic-similarity sample browser and organizer for macOS. Fully offline, private, and built for professional music production workflows.",
  alternates: { canonical: "/products/smart-sample-manager" },
};

const WORKFLOW_STEPS = [
  {
    title: "1. Scan & Index",
    body: "Point SLO at your sample directories. The offline DSP engine reads the raw audio files, extracts key acoustic descriptors, and builds a local cached database. Subsequent indexing is near-instantaneous.",
  },
  {
    title: "2. Visual Mapping",
    body: "Browse visually. SLO plots your samples on a 2D canvas based on timbral similarity. Discover clusters of matching hats, sub kicks, or ambient textures without searching folders.",
  },
  {
    title: "3. Find Similar",
    body: "Select a sample you like, click Find Similar, and SLO instantly searches your library for acoustically related tamber. SLO works with sound, not text keywords, so there are no textual search prompts.",
  },
  {
    title: "4. DAW Drag-and-Drop",
    body: "Once you identify the sound, drag it directly from the SLO browser or visual map into Ableton Live, Logic Pro, Reaper, or any sampler. Your original directory structure remains completely unchanged.",
  },
];

const FAQ = [
  {
    q: "Does SLO support Logic, Reaper, or other DAWs?",
    a: "SLO is compiled as a Standalone application, Audio Unit (AU) plugin, and VST3 plugin (with AU validated on our current test systems, and VST3 qualification in progress). While the experimental metadata sidecar writer is designed for Ableton Live workflows, the core search and classification features work as a companion tool alongside any DAW.",
  },
  {
    q: "Does SLO modify, rename, or move my files?",
    a: "During the private beta, SLO operates in read-only classification mode and does not automatically move, rename, or delete your samples. Your files remain untouched, serving as a virtual browser for your library.",
  },
  {
    q: "Does any audio data leave my computer?",
    a: "Sample analysis and similarity calculations run locally on your Mac. While user activation and licensing check-ins require a network connection to our platform services, your audio files are never uploaded for classification.",
  },
  {
    q: "Is Windows supported?",
    a: "Not yet. SLO is currently macOS-only (runs on macOS 12+ and is fully optimized for M1/M2/M3 chips). A Windows build is on our long-term roadmap, but is not currently available.",
  },
];

const SOFTWARE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "SLO (Sample Library Optimiser)",
  applicationCategory: "MultimediaApplication",
  operatingSystem: "macOS",
  description:
    "An acoustic-similarity sample browser and organizer for VST3, AU, and Standalone hosts.",
};

export default function SmartSampleManagerPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(SOFTWARE_JSON_LD) }}
      />
      
      {/* Product Hero */}
      <section className="section product-hero">
        <div className="site-container">
          <span className="eyebrow">Flagship Product</span>
          <h1 className="section-title mt-4 text-foreground">SLO</h1>
          <p className="text-sm font-mono text-brand-blue-bright mt-1">Sample Library Optimiser</p>
          <p className="body-large mt-6">
            A professional, acoustic-similarity sample browser and organizer for macOS. 
            By analysing raw audio signals rather than depending on folder structures or filenames, SLO provides absolute clarity over your sample library.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Link href="/pricing" className="btn-primary">
              See pricing
            </Link>
            <Link href="/account" className="btn-secondary">
              Sign in to download
            </Link>
          </div>
        </div>
      </section>

      {/* Main App Frame Screenshot */}
      <section className="border-t" style={{ borderColor: "var(--border)" }}>
        <div className="site-container py-12 sm:py-20">
          <div className="product-frame product-frame--hero">
            <div className="product-frame__bar">
              <span>SLO // LIST VIEW</span>
              <span>2,450 SAMPLES INDEXED</span>
            </div>
            <Image
              src="/screenshots/main-browser.png"
              alt="SLO list view showing sample browser layout, categorised tags, spectral analysis and transient points"
              width={1599}
              height={1057}
              className="w-full h-auto"
              priority
            />
          </div>
          <p className="mt-4 text-xs" style={{ color: "var(--muted-dim)" }}>
            SLO flagship standalone application showing the browser, transient analyzer, and spectral centroid metrics.
          </p>
        </div>
      </section>

      {/* Rationale & Problem Statement */}
      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="site-container grid gap-12 lg:grid-cols-[0.8fr_1.2fr] lg:items-start">
          <div>
            <span className="eyebrow">The Sample Library Problem</span>
            <h2 className="section-title mt-4">Organised by ear, not by folder.</h2>
          </div>
          <div className="space-y-6 text-base leading-relaxed text-muted">
            <p>
              Producers gather thousands of samples over years—often mixed together across splice packs, recording sessions, and messy desktop folders. Finding a specific kick, snare, or synth stab involves endless folder clicking and memory recall.
            </p>
            <p>
              SLO solves this by listening to your files. It groups sounds that share acoustic characteristics (timbre, envelope, transient decay), so that clicking <strong>Find Similar</strong> surfaces nearby options instantly.
            </p>
          </div>
        </div>
      </section>

      {/* Interactive Demonstration */}
      <section className="section border-t bg-[#0D1322]/20" style={{ borderColor: "var(--border)" }}>
        <div className="site-container grid gap-12 lg:grid-cols-[1fr_1.1fr] lg:items-center">
          <div>
            <span className="eyebrow">Acoustic Signal Processing</span>
            <h2 className="section-title mt-4">Bypass cryptic filenames.</h2>
            <p className="mt-6 leading-relaxed text-muted text-sm">
              Filenames like <code>XK29_0047.wav</code> reveal nothing about their sound. SLO processes the raw samples offline, identifies transients, measures centroid weight, and detects the true musical role.
            </p>
            <div className="mt-6 callout-warning">
              <strong>Beta Safety Note:</strong> During the private beta, SLO operates in read-only classification mode and does not automatically rearrange your files or rename your samples.
            </div>
          </div>
          <div>
            <AudioAnalysisDemo />
          </div>
        </div>
      </section>

      {/* Detailed Workflow */}
      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="site-container">
          <span className="eyebrow">Workflow Integration</span>
          <h2 className="section-title mt-4">Built around how you produce.</h2>
          <div className="mt-10 grid gap-6 sm:grid-cols-2">
            {WORKFLOW_STEPS.map((step) => (
              <div key={step.title} className="surface-card p-6">
                <h3 className="font-semibold text-foreground">{step.title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-muted">
                  {step.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* System Requirements & DAW Support */}
      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="site-container">
          <div className="grid gap-12 lg:grid-cols-[0.8fr_1.2fr]">
            <div>
              <span className="eyebrow">Specifications</span>
              <h2 className="section-title mt-4">System compatibility.</h2>
              <div className="mt-8 flex flex-wrap gap-2.5 text-sm">
                {["macOS 12+", "Apple Silicon Native", "Intel Core", "VST3", "AU", "Standalone"].map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full border px-4 py-1.5 font-mono text-xs"
                    style={{ borderColor: "var(--border-strong)", color: "var(--muted)" }}
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
            
            <div className="space-y-6">
              <div className="surface-card p-6">
                <h3 className="font-semibold text-foreground">DAW Support & Status</h3>
                <div className="mt-4 grid gap-4 sm:grid-cols-2 text-sm text-muted">
                  <div>
                    <h4 className="font-semibold text-brand-blue-bright text-xs">VERIFIED & FULLY SUPPORTED</h4>
                    <ul className="mt-2 list-disc pl-5 space-y-1.5">
                      <li>Standalone Application</li>
                      <li>Audio Unit (AU) validation</li>
                      <li>VST3 Host Compatibility</li>
                    </ul>
                  </div>
                  <div>
                    <h4 className="font-semibold text-brand-red text-xs">EXPERIMENTAL METADATA WRITER</h4>
                    <ul className="mt-2 list-disc pl-5 space-y-1.5">
                      <li>Ableton Live XMP Integration</li>
                      <li>Logic Pro indexing</li>
                    </ul>
                  </div>
                </div>
                <p className="mt-6 text-xs text-muted-dim">
                  Ableton Live integration writes metadata to sidecar XMP files that Ableton reads. This feature remains in active validation.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto px-6" style={{ maxWidth: "42rem" }}>
          <span className="eyebrow text-center block">FAQ</span>
          <h2 className="mt-4 text-2xl sm:text-3xl font-semibold tracking-tight text-center text-foreground">Common Questions</h2>
          <dl className="mt-10 space-y-8">
            {FAQ.map((item) => (
              <div key={item.q} className="border-b pb-6" style={{ borderColor: "var(--border)" }}>
                <dt className="font-semibold text-foreground text-sm">{item.q}</dt>
                <dd className="mt-3 text-sm leading-relaxed text-muted">
                  {item.a}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* Bottom Action */}
      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="site-container text-center">
          <div className="max-w-xl mx-auto flex flex-col items-center">
            <h2 className="text-2xl font-bold text-foreground">Get started with SLO</h2>
            <p className="mt-3 text-sm text-muted">Analyse your sample library. Find the right timbre instantly.</p>
            <div className="mt-8 flex gap-3">
              <Link href="/pricing" className="btn-primary">
                See pricing
              </Link>
              <Link href="/learn" className="btn-secondary">
                Read guides
              </Link>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
