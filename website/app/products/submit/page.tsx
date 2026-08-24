import type { Metadata } from "next";
import Link from "next/link";
import { LightField } from "@/components/motion/LightField";
import { Reveal } from "@/components/motion/Reveal";

export const metadata: Metadata = {
  title: "NITE Submit — Document Prep Intelligence",
  description: "The safest way to verify and prepare files before submission. Fully local document validation for macOS.",
  alternates: { canonical: "/products/submit" },
};

const FEATURES = [
  {
    title: "Metadata & Naming Check",
    body: "Ensure your file conforms precisely to department naming conventions, project patterns, and required templates before submitting.",
  },
  {
    title: "Evidence-Based Review",
    body: "Submit scans document structures locally, highlights verified entries, and flags uncertain fields for your approval before writing copies.",
  },
  {
    title: "Zero-Upload Validation",
    body: "Files are processed entirely in memory on your Mac. No document contents are uploaded, maintaining complete intellectual privacy.",
  },
  {
    title: "Correct Naming Exports",
    body: "Create named, verified duplicates of your project documents with a single click, leaving your original draft files untouched.",
  },
];

export default function SubmitProductPage() {
  return (
    <>
      {/* Product Hero */}
      <section className="section product-hero relative overflow-hidden">
        <LightField />
        <div className="site-container relative">
          <span className="eyebrow">Product Releases</span>
          <h1 className="section-title mt-4 text-foreground">NITE Submit</h1>
          <p className="text-sm font-mono text-brand-blue-bright mt-1">Submission Preparation Intelligence</p>
          <p className="body-large mt-6">
            The safest way to prepare important files before submission. Drop in a document, review structural metadata, correct errors, and save a clean copy. Fully offline, private, and optimized for macOS.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Link href="/pricing" className="btn-primary">
              View Licensing
            </Link>
            <Link href="/account" className="btn-secondary">
              Sign in to download
            </Link>
          </div>
        </div>
      </section>

      {/* Feature Grid */}
      <section className="section section-rule">
        <div className="site-container">
          <Reveal>
            <span className="eyebrow">Local Analysis</span>
            <h2 className="section-title mt-4">Safe document preparation.</h2>
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
          <h2 className="mt-4 text-xl sm:text-2xl font-semibold tracking-tight text-center text-foreground">Important Disclaimer</h2>
          <p className="mt-4 text-xs leading-relaxed text-muted text-center">
            NITE Submit checks file details and naming formats. It does not submit work on your behalf, nor can it guarantee department-specific criteria match generic presets. Always run a final manual check on your files.
          </p>
        </div>
      </section>
    </>
  );
}
