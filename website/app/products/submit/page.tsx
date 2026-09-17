import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import Link from "next/link";
import { LightField } from "@/components/motion/LightField";
import { Reveal } from "@/components/motion/Reveal";
import { WaitlistForm } from "@/components/WaitlistForm";

export const metadata: Metadata = pageMetadata({
  title: "NITE Submit: Document Prep Intelligence",
  description: "The safest way to verify and prepare files before submission. Fully local document validation for macOS.",
  path: "/products/submit",
});

const FEATURES = [
  {
    title: "Metadata & Naming Check",
    body: "Apply the naming pattern supplied by your department, review every detected field, and prepare a safe copy before submitting.",
  },
  {
    title: "7z, ZIP & TAR Batch Packaging",
    body: "Compress multi-asset submissions (PDF, WAV audio stems, MP4 videos, DOCX) into clean .7z (LZMA2), .zip, or .tar.gz archives with SHA-256 receipts.",
  },
  {
    title: "AES-256 Archive Encryption",
    body: "Optionally protect your submission packages with AES-256 header and content encryption directly on-device before uploading to portal systems.",
  },
  {
    title: "Zero-Upload Validation",
    body: "Files are processed locally on your Mac. Document contents are not uploaded; only an optional user-initiated update check uses the network.",
  },
];

export default function SubmitProductPage() {
  return (
    <>
      {/* Product Hero */}
      <section className="section product-hero relative overflow-hidden">
        <LightField />
        <div className="site-container relative">
          <span className="eyebrow text-brand-blue-bright">Workflow Intelligence Family</span>
          <h1 className="section-title mt-4 text-foreground">NITE Submit</h1>
          <p className="text-sm font-mono text-brand-blue-bright mt-1">Submission Preparation Intelligence</p>
          <p className="body-large mt-6 font-sans">
            The safest way to prepare important files before submission. Drop in a document, review structural metadata, correct errors, and save a clean copy. Fully offline, local-first, and optimized for macOS.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Link href="#join-waitlist" className="btn-primary">
              Join the waitlist
            </Link>
            <Link href="/pricing" className="btn-secondary">
              View pricing
            </Link>
          </div>
        </div>
      </section>

      {/* Workflow, six steps */}
      <section className="section section-rule">
        <div className="site-container">
          <Reveal>
            <div className="max-w-2xl">
              <span className="eyebrow">The Submit Workflow</span>
              <h2 className="section-title mt-4">Six steps. Zero guesswork.</h2>
              <p className="mt-4 text-sm text-muted leading-relaxed">
                Every stage is visible and under your control. Submit never submits work for you, 
                it prepares a verified copy so you can submit with confidence.
              </p>
            </div>
          </Reveal>
          <ol className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {[
              ["01", "Drop", "Add a PDF from your Mac. Nothing is uploaded, the file is read in memory."],
              ["02", "Understand", "Submit reads structure and metadata locally: names, dates, course codes, templates."],
              ["03", "Review", "Flagged fields and uncertainties are shown for your approval. Nothing changes silently."],
              ["04", "Prepare", "Confirm corrections before anything is written. You approve every change."],
              ["05", "Verify", "Naming and format checks run against your chosen pattern before export."],
              ["06", "Receipt", "A safely named copy is saved alongside your untouched original draft."],
            ].map(([n, title, body]) => (
              <li key={n} className="surface-card p-6 rounded-lg border border-border/40">
                <span className="u-data" style={{ color: "var(--brand-blue-bright)" }}>{n}</span>
                <h3 className="mt-3 text-sm font-semibold text-foreground">{title}</h3>
                <p className="mt-2 text-xs leading-relaxed text-muted">{body}</p>
              </li>
            ))}
          </ol>
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

      {/* Waitlist */}
      <section id="join-waitlist" className="section section-rule">
        <div className="site-container">
          <div className="grid gap-12 lg:grid-cols-[1fr_1fr] lg:items-start">
            <div>
              <span className="eyebrow text-brand-blue-bright">Private Beta</span>
              <h2 className="section-title mt-4 text-foreground">Join the first 50.</h2>
              <p className="mt-4 text-sm leading-relaxed text-muted">
                Submit is opening to a small group of professionals to shape the product before wider release.
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
                  <span>Test Submit with your own documents and shape what ships</span>
                </li>
              </ul>
            </div>
            <WaitlistForm productId="submit" capacity={50} />
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
