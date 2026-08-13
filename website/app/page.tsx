import Link from "next/link";

const FEATURES = [
  {
    title: "Find Similar",
    description:
      "Select a sound. Instantly surface acoustically similar samples from your entire library -- by how they sound, not what they're named.",
  },
  {
    title: "Visual map",
    description:
      "See your whole library laid out by sonic similarity. Nearby sounds are related -- explore by ear, not by folder.",
  },
  {
    title: "Ableton workflow (experimental)",
    description:
      "Tags and organization can write straight into Ableton's own sample browser via XMP metadata -- no separate catalog to maintain. Marked experimental in the current build.",
  },
  {
    title: "Fully offline",
    description:
      "Every scan and every match happens on your machine. Nothing about your library ever leaves your drive.",
  },
];

export default function HomePage() {
  return (
    <>
      {/* Hero */}
      <section className="section">
        <div className="mx-auto px-6 text-center" style={{ maxWidth: "var(--content-width)" }}>
          <span className="eyebrow">NITE DSP</span>
          <h1 className="mt-4 text-4xl sm:text-6xl font-semibold tracking-tight text-balance">
            Your samples. Actually organised.
          </h1>
          <p className="mt-6 text-lg sm:text-xl mx-auto max-w-2xl" style={{ color: "var(--muted)" }}>
            Smart Sample Manager finds, explores, and rediscovers the sounds already sitting on
            your drive -- by how they actually sound, not what someone named the file five years
            ago.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
            <Link href="/products/smart-sample-manager" className="btn-primary">
              See Smart Sample Manager
            </Link>
            <Link href="/pricing" className="btn-secondary">
              Pricing
            </Link>
          </div>
        </div>
      </section>

      {/* The problem */}
      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto px-6" style={{ maxWidth: "var(--content-width)" }}>
          <div className="max-w-2xl">
            <span className="eyebrow">The problem</span>
            <h2 className="mt-3 text-2xl sm:text-3xl font-semibold tracking-tight">
              Your best sounds are buried in a library you stopped trusting years ago.
            </h2>
            <p className="mt-4" style={{ color: "var(--muted)" }}>
              Folders full of "kick_final_v3.wav." Duplicate one-shots scattered across three
              drives. A sound you know you have somewhere, but can&apos;t find by name because you
              never named it right in the first place.
            </p>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto px-6" style={{ maxWidth: "var(--content-width)" }}>
          <div className="max-w-2xl">
            <span className="eyebrow">How it helps</span>
            <h2 className="mt-3 text-2xl sm:text-3xl font-semibold tracking-tight">
              Organisation that works by ear.
            </h2>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2">
            {FEATURES.map((feature) => (
              <div key={feature.title} className="surface-card p-6">
                <h3 className="font-medium">{feature.title}</h3>
                <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Formats */}
      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto px-6" style={{ maxWidth: "var(--content-width)" }}>
          <span className="eyebrow">Compatibility</span>
          <h2 className="mt-3 text-2xl sm:text-3xl font-semibold tracking-tight">
            Runs where you already work.
          </h2>
          <div className="mt-8 flex flex-wrap gap-3 text-sm">
            {["VST3", "AU", "Standalone", "macOS"].map((tag) => (
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
            Windows support is on the roadmap, not yet available.
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto px-6 text-center" style={{ maxWidth: "var(--content-width)" }}>
          <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight">
            Stop scrolling. Start finding.
          </h2>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
            <Link href="/products/smart-sample-manager" className="btn-primary">
              See Smart Sample Manager
            </Link>
            <Link href="/support" className="btn-secondary">
              Support
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
