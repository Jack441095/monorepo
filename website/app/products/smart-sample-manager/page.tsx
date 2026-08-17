import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Smart Sample Manager",
  description:
    "Find acoustically similar samples in your library, explore it visually, and stay organized inside Ableton Live -- fully offline.",
  alternates: { canonical: "/products/smart-sample-manager" },
};

const WORKFLOWS = [
  {
    title: "Find Similar",
    experimental: false,
    body: "Select a sound. Smart Sample Manager surfaces acoustically similar samples from your whole library -- by how they sound, not by filename or folder. This compares audio content directly; it isn't a text search, so there's no \"type a description and find a sound\" mode.",
  },
  {
    title: "Visual map",
    experimental: false,
    body: "Your library laid out as a 2D map, positioned by sonic similarity. Sounds near each other on the map tend to sound alike -- a different way to browse than scrolling a folder tree.",
  },
  {
    title: "Ableton workflow",
    experimental: true,
    body: "Tags and reorganization can write into standard XMP metadata that Ableton Live's own sample browser reads directly, so your library stays organized inside Ableton too. This feature is marked experimental in the current build while we finish validating it against a range of libraries -- it's not an official Ableton partnership or integration.",
  },
  {
    title: "Fully offline",
    experimental: false,
    body: "Every scan, every embedding, every similarity match runs locally. No sample audio, filename, or library path is ever uploaded during ordinary use.",
  },
];

const FAQ = [
  {
    q: "Does it work with Logic, Reaper, or other DAWs?",
    a: "Smart Sample Manager ships as VST3, AU, and a Standalone app, so it loads in any host that supports those formats. The Ableton XMP workflow is Ableton-specific; other hosts get the same Find Similar / visual map / organization features without that particular metadata integration.",
  },
  {
    q: "Can I type a description and find a sound?",
    a: "No -- similarity is based on the audio itself (acoustic similarity), not natural-language text search. Select a sample you already have, and it finds sounds like it.",
  },
  {
    q: "Does anything get uploaded?",
    a: "No. Scanning, analysis, and matching all happen on your machine. See our privacy notes for detail.",
  },
  {
    q: "Is Windows supported?",
    a: "Not yet. Smart Sample Manager is macOS-only for now (VST3/AU/Standalone). Windows is on the roadmap, not currently available.",
  },
];

const SOFTWARE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "Smart Sample Manager",
  applicationCategory: "MultimediaApplication",
  operatingSystem: "macOS",
  description:
    "An acoustic-similarity sample browser and organizer for VST3, AU, and Standalone hosts.",
  // Deliberately no "offers"/price field -- pricing is not yet human-approved
  // (see app/pricing/page.tsx). Do not add one until it is.
};

export default function SmartSampleManagerPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(SOFTWARE_JSON_LD) }}
      />
      <section className="section product-hero">
        <div className="site-container">
          <span className="eyebrow">Product</span>
          <h1 className="section-title mt-4">Smart Sample Manager</h1>
          <p className="body-large mt-6">
            An acoustic-similarity sample browser and organizer for VST3, AU, and Standalone
            hosts. It listens to your library the way you do, groups what sounds alike, and gets
            out of the way.
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

      <section className="border-t" style={{ borderColor: "var(--border)" }}>
        <div className="site-container py-12 sm:py-20">
          <div className="product-frame product-frame--hero">
            <div className="product-frame__bar"><span>SMART SAMPLE MANAGER</span><span>ACTUAL APP</span></div>
            <Image
              src="/screenshots/main-browser.png"
              alt="Smart Sample Manager's main window, showing the sample browser, search field, colour-coded slots, and the sample metadata panel"
              width={1599}
              height={1057}
              className="w-full h-auto"
              priority
            />
          </div>
          <p className="mt-4 text-xs" style={{ color: "var(--muted-dim)" }}>
            The actual Smart Sample Manager window, shown before a library has been scanned.
          </p>
        </div>
      </section>

      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto px-6" style={{ maxWidth: "var(--content-width)" }}>
          <span className="eyebrow">Workflow</span>
          <h2 className="mt-3 text-2xl sm:text-3xl font-semibold tracking-tight">
            Built around how you actually dig for sounds.
          </h2>
          <div className="mt-10 grid gap-6 sm:grid-cols-2">
            {WORKFLOWS.map((item) => (
              <div key={item.title} className="surface-card p-6">
                <h3 className="font-medium">
                  {item.title}
                  {item.experimental && <span className="badge-experimental ml-2">Experimental</span>}
                </h3>
                <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
                  {item.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto px-6" style={{ maxWidth: "var(--content-width)" }}>
          <span className="eyebrow">Requirements</span>
          <h2 className="mt-3 text-2xl sm:text-3xl font-semibold tracking-tight">
            What it runs on.
          </h2>
          <div className="mt-8 flex flex-wrap gap-3 text-sm">
            {["macOS", "VST3", "AU", "Standalone"].map((tag) => (
              <span
                key={tag}
                className="rounded-full border px-4 py-1.5"
                style={{ borderColor: "var(--border-strong)", color: "var(--muted)" }}
              >
                {tag}
              </span>
            ))}
          </div>
          <p className="mt-4 text-sm" style={{ color: "var(--muted-dim)" }}>
            Windows support is planned but not yet available.
          </p>
        </div>
      </section>

      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto px-6" style={{ maxWidth: "var(--content-width)" }}>
          <span className="eyebrow">Compatibility</span>
          <h2 className="mt-3 text-2xl sm:text-3xl font-semibold tracking-tight">
            Where it&apos;s been tested.
          </h2>
          <p className="mt-4 max-w-2xl text-sm" style={{ color: "var(--muted)" }}>
            We&apos;d rather tell you exactly what&apos;s been verified than list every major DAW as
            supported before we&apos;ve confirmed it.
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            <div className="surface-card p-6">
              <h3 className="font-medium" style={{ color: "var(--foreground)" }}>
                Verified
              </h3>
              <ul className="mt-3 space-y-1.5 text-sm" style={{ color: "var(--muted)" }}>
                <li>Standalone app</li>
                <li>Audio Unit (AU) -- passes Apple&apos;s own AU validation</li>
              </ul>
            </div>
            <div className="surface-card p-6">
              <h3 className="font-medium" style={{ color: "var(--foreground)" }}>
                In progress
              </h3>
              <ul className="mt-3 space-y-1.5 text-sm" style={{ color: "var(--muted)" }}>
                <li>VST3 in individual DAWs</li>
                <li>Ableton Live</li>
                <li>Logic Pro</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto px-6" style={{ maxWidth: "42rem" }}>
          <span className="eyebrow">FAQ</span>
          <h2 className="mt-3 text-2xl sm:text-3xl font-semibold tracking-tight">Questions</h2>
          <dl className="mt-8 space-y-6">
            {FAQ.map((item) => (
              <div key={item.q}>
                <dt className="font-medium">{item.q}</dt>
                <dd className="mt-2 text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
                  {item.a}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto px-6 text-center" style={{ maxWidth: "var(--content-width)" }}>
          <Link href="/pricing" className="btn-primary">
            See pricing
          </Link>
        </div>
      </section>
    </>
  );
}
