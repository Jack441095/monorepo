import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import Image from "next/image";
import Link from "next/link";
import { AudioAnalysisDemo } from "@/components/AudioAnalysisDemo";
import { SloMapDemo } from "@/components/demo/SloMapDemo";
import { WaitlistForm } from "@/components/WaitlistForm";
import { LightField } from "@/components/motion/LightField";
import { Magnetic } from "@/components/motion/Magnetic";
import { Reveal } from "@/components/motion/Reveal";
import { TiltSurface } from "@/components/motion/TiltSurface";

export const metadata: Metadata = pageMetadata({
  title: "SLO: Sample Library Optimiser",
  description: "An acoustic-similarity sample browser and organizer for macOS. Fully offline, private, and built for professional music production workflows.",
  path: "/products/smart-sample-manager",
});

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
      <section className="section product-hero relative overflow-hidden">
        <LightField />
        <div className="site-container relative">
          <span className="eyebrow text-brand-violet-text">Audio Intelligence Family</span>
          <h1 className="section-title mt-4 text-foreground">SLO</h1>
          <p className="text-sm font-mono text-amber-400 mt-1">Sample Library Optimiser</p>
          <p className="body-large mt-6 font-sans">
            A professional, acoustic-similarity sample browser and organizer for macOS.
            By analysing raw audio signals rather than depending on folder structures or filenames, SLO provides absolute clarity over your sample library.
          </p>
          <p className="mt-4 text-sm font-semibold" style={{ color: "var(--brand-blue-bright)" }}>
            Accepting the first 50 beta testers.
          </p>
          <div className="mt-6 flex flex-wrap gap-4">
            <a href="#join-waitlist" className="btn-primary">
              <Magnetic>Claim your spot</Magnetic>
            </a>
            <Link href="/learn" className="btn-secondary">
              Read how it works
            </Link>
          </div>
        </div>
      </section>

      {/* Main App Frame Screenshot */}
      <section className="border-t" style={{ borderColor: "var(--border)" }}>
        <div className="site-container py-12 sm:py-20">
          <TiltSurface>
            <div className="product-frame">
              <div className="product-frame__bar" data-depth="1.5">
                <span>SLO // LIST VIEW</span>
                <span>2,450 SAMPLES INDEXED</span>
              </div>
              <div data-depth="3">
                {/* sizes matters here: without it Next assumes 100vw and ships
                    the 3840px variant for a slot never wider than the 72rem
                    content column. priority keeps this LCP image eager. */}
                <Image
                  src="/screenshots/main-browser.png"
                  alt="SLO list view showing sample browser layout, categorised tags, spectral analysis and transient points"
                  width={1599}
                  height={1057}
                  className="w-full h-auto block"
                  sizes="(max-width: 1200px) 100vw, 1152px"
                  priority
                />
              </div>
            </div>
          </TiltSurface>
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
              Producers gather thousands of samples over years, often mixed together across splice packs, recording sessions, and messy desktop folders. Finding a specific kick, snare, or synth stab involves endless folder clicking and memory recall.
            </p>
            <p>
              SLO solves this by listening to your files. It groups sounds that share acoustic characteristics (timbre, envelope, transient decay), so that clicking <strong>Find Similar</strong> surfaces nearby options instantly.
            </p>
          </div>
        </div>
      </section>

      {/* Interactive 2D Acoustic Similarity Map Demo */}
      <section className="section border-t bg-surface/30" style={{ borderColor: "var(--border)" }}>
        <div className="site-container grid gap-12 lg:grid-cols-[1fr_1.1fr] lg:items-center">
          <Reveal>
            <span className="eyebrow text-brand-blue-bright">TIMBRAL DISCOVERY MAP</span>
            <h2 className="section-title mt-4 text-foreground">Explore sounds by acoustic similarity.</h2>
            <p className="mt-6 leading-relaxed text-muted text-sm">
              Filenames like <code>XK29_0047.wav</code> reveal nothing about how a sample sounds. SLO extracts raw acoustic descriptors offline and plots your entire library on an intuitive 2D map.
            </p>
            <div className="mt-6 border-l-2 border-[#F0A23A] bg-[#F0A23A]/10 p-4 rounded-r text-xs leading-relaxed text-muted">
              <strong>Non-Destructive Local Indexing:</strong> SLO operates in 100% read-only mode. Your sample files are scanned locally on your Mac and cached in memory, your original directories and filenames are never altered.
            </div>
          </Reveal>
          <Reveal delayMs={90}>
            <SloMapDemo />
          </Reveal>
        </div>
      </section>

      {/* Acoustic Signal Processing Demo */}
      <section className="section border-t bg-surface/10" style={{ borderColor: "var(--border)" }}>
        <div className="site-container grid gap-12 lg:grid-cols-[1.1fr_1fr] lg:items-center">
          <Reveal delayMs={90} className="order-2 lg:order-1">
            <AudioAnalysisDemo />
          </Reveal>
          <Reveal className="order-1 lg:order-2">
            <span className="eyebrow">Acoustic Descriptor Engine</span>
            <h2 className="section-title mt-4 text-foreground">Bypass cryptic metadata.</h2>
            <p className="mt-6 leading-relaxed text-muted text-sm">
              SLO processes raw PCM audio frames offline, detects precise transient decay curves, calculates spectral centroid brightness, and automatically classifies the true musical role.
            </p>
          </Reveal>
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
                    <h4 className="font-semibold text-brand-violet-text text-xs">INTEGRATION PREVIEW & ROADMAP</h4>
                    <ul className="mt-2 list-disc pl-5 space-y-1.5">
                      <li>Ableton Live XMP Sidecars</li>
                      <li>Logic Pro database linking</li>
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

      {/* Waitlist */}
      <section id="join-waitlist" className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="site-container">
          <div className="grid gap-12 lg:grid-cols-[1fr_1fr] lg:items-start">
            <div>
              <span className="eyebrow text-brand-blue-bright">Limited Beta</span>
              <h2 className="section-title mt-4 text-foreground">Join the first 50.</h2>
              <p className="mt-4 text-sm leading-relaxed text-muted">
                SLO is opening to a small group of producers to shape the product before wider release.
                Claim your spot and you&apos;ll be the first to get access when the beta opens.
              </p>
              <ul className="mt-6 space-y-3 text-sm text-muted">
                <li className="flex gap-3 items-start">
                  <span className="text-brand-blue-bright font-bold">01</span>
                  <span>Join the waitlist. Your place is held</span>
                </li>
                <li className="flex gap-3 items-start">
                  <span className="text-brand-blue-bright font-bold">02</span>
                  <span>We&apos;ll email you when your beta access is ready</span>
                </li>
                <li className="flex gap-3 items-start">
                  <span className="text-brand-blue-bright font-bold">03</span>
                  <span>Test SLO with your own sample library and shape what ships</span>
                </li>
              </ul>
            </div>
            <WaitlistForm productId="smart-sample-manager" capacity={50} />
          </div>
        </div>
      </section>
    </>
  );
}
