import type { Metadata } from "next";
import Link from "next/link";
import { FilesOrganizerDemo } from "@/components/demo/FilesOrganizerDemo";
import { LightField } from "@/components/motion/LightField";
import { Reveal } from "@/components/motion/Reveal";

export const metadata: Metadata = {
  title: "NITE Files: C++ Library Folder Cleaner",
  description: "General-purpose library folder cleaner powered by a high-performance C++17 core engine. Sort photos by EXIF date, music by ID3 tag, and documents by category with 100% local safety.",
  alternates: { canonical: "/products/files" },
};

const FEATURES = [
  {
    title: "C++17 Multi-Threaded Engine",
    body: "Built on std::filesystem for instant, zero-latency scanning of folders containing thousands of files. Portable C++ core for macOS and Windows.",
  },
  {
    title: "EXIF Photo & ID3 Music Parsing",
    body: "Automatically extract capture dates & camera models from photo headers, or artist, album, and track metadata from audio files for structured sub-trees.",
  },
  {
    title: "Category Auto-Grouping",
    body: "Instantly categorize mixed folders into clean sub-directories: Documents/, Audio/, Video/, Images/, Archives/, and Code/.",
  },
  {
    title: "Dry-Run Preview & Rollback Safety",
    body: "Never worry about lost files. Preview all proposed relocations side-by-side, verify SHA-256 checksums, and perform one-click transactional rollbacks anytime.",
  },
];

export default function NiteFilesPage() {
  return (
    <>
      {/* Product Hero */}
      <section className="section product-hero relative overflow-hidden">
        <LightField />
        <div className="site-container relative">
          <span className="eyebrow text-brand-emerald">Workflow Intelligence Family</span>
          <h1 className="section-title mt-4 text-foreground">NITE Files</h1>
          <p className="text-sm font-mono text-brand-emerald mt-1">C++17 Library Folder Cleaner & Metadata Organizer</p>
          <p className="body-large mt-6 font-sans">
            Transform messy downloads, photo dumps, and media collections into clean, organized library folder structures. Powered by a local-first C++17 engine with EXIF/ID3 metadata parsing and non-destructive dry-run previews.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Link href="/products" className="btn-primary">
              Explore Product Family &rarr;
            </Link>
          </div>
        </div>
      </section>

      {/* Interactive Web Showcase Demo */}
      <section className="section section-rule bg-surface/10">
        <div className="site-container">
          <Reveal>
            <span className="eyebrow">Interactive Showcase</span>
            <h2 className="section-title mt-4">Experience the C++ engine.</h2>
          </Reveal>
          <div className="mt-8">
            <FilesOrganizerDemo />
          </div>
        </div>
      </section>

      {/* Feature Grid */}
      <section className="section section-rule">
        <div className="site-container">
          <Reveal>
            <span className="eyebrow">Local Analysis</span>
            <h2 className="section-title mt-4">Safe library organization.</h2>
          </Reveal>

          <div className="mt-10 grid gap-6 sm:grid-cols-2">
            {FEATURES.map((f) => (
              <div key={f.title} className="surface-card p-6 border border-border/40 rounded-lg">
                <h3 className="font-semibold text-foreground text-sm">{f.title}</h3>
                <p className="mt-3 text-xs leading-relaxed text-muted">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Safety Notice */}
      <section className="section section-rule bg-surface/10">
        <div className="site-container" style={{ maxWidth: "42rem" }}>
          <span className="eyebrow block text-center">Operational Boundary</span>
          <h2 className="mt-4 text-xl sm:text-2xl font-semibold tracking-tight text-center text-foreground">100% Local-First Privacy</h2>
          <p className="mt-4 text-xs leading-relaxed text-muted text-center">
            NITE Files processes file structures and metadata headers entirely on your local hardware. Zero files or telemetry are uploaded. Every organization plan generates a dry-run preview before execution.
          </p>
        </div>
      </section>
    </>
  );
}

