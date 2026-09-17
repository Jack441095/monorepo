import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import Link from "next/link";
import { Reveal } from "@/components/motion/Reveal";

export const metadata: Metadata = pageMetadata({
  title: "Services",
  description: "Freelance audio engineering, DSP development, and research contracts from Jack Knowlton at NITE DSP.",
  path: "/services",
});

const SERVICES = [
  {
    id: "dsp",
    eyebrow: "Signal Processing",
    title: "DSP & Audio Engineering",
    body: "Custom DSP work: feature extraction pipelines, timbral analysis systems, acoustic classification models, and real-time audio processing for macOS and Linux. 12 years of hands-on audio engineering experience applied to code.",
    points: [
      "Spectral and timbral feature extraction (MFCC, centroid, chroma, onset)",
      "Sample library analysis and classification systems",
      "Real-time signal processing in C++ or Python",
      "Audio ML pipelines: training, evaluation, deployment",
      "Ableton Live integration via Max for Live or MIDI Remote Scripts",
      "Wwise integration and interactive audio systems",
    ],
    accent: "var(--brand-violet-text)",
    border: "rgba(139,92,246,0.25)",
  },
  {
    id: "web",
    eyebrow: "Digital Design & Development",
    title: "Website & Product Design",
    body: "End-to-end website and web app work: design, frontend build, and deployment. Focused on creative industry clients: labels, studios, producers, and audio software companies.",
    points: [
      "Brand identity and visual design for audio businesses",
      "Next.js / React frontend development",
      "Landing pages, marketing sites, and product pages",
      "Waitlist and early-access launch infrastructure",
      "Dark-mode-first, performance-optimised builds",
      "Deployed to Vercel, Netlify, or your own infrastructure",
    ],
    accent: "var(--brand-blue-bright)",
    border: "rgba(59,130,246,0.25)",
  },
  {
    id: "research",
    eyebrow: "Technical Research",
    title: "Research Contracts",
    body: "Structured research engagements for audio AI and music technology problems. Suitable for labels, publishers, academic groups, or tool developers who need expertise without hiring full-time.",
    points: [
      "Acoustic similarity and music information retrieval (MIR)",
      "Local-first AI audio systems: architecture and evaluation",
      "Benchmark design and measurement for audio classification",
      "Literature review and state-of-the-art assessments",
      "Technical writing: specs, white papers, implementation guides",
      "Research-to-prototype handoffs for engineering teams",
    ],
    accent: "var(--state-success)",
    border: "rgba(16,185,129,0.25)",
  },
];

export default function ServicesPage() {
  return (
    <>
      <section className="section product-hero">
        <div className="site-container">
          <span className="eyebrow">Freelance &amp; Contract Work</span>
          <h1 className="section-title mt-4 text-foreground">
            Audio engineering, DSP, and product work for hire.
          </h1>
          <p className="body-large mt-6 max-w-2xl text-muted leading-relaxed">
            12 years in professional audio: studios, game audio, and now AI audio tools.
            Available for DSP contracts, website builds, and research engagements.
          </p>
          <div className="mt-8">
            <a href="mailto:nitedsp@outlook.com" className="btn-primary">
              Get in touch &rarr;
            </a>
          </div>
        </div>
      </section>

      {SERVICES.map((s, i) => (
        <section
          key={s.id}
          className="section-rule"
          style={{ background: i % 2 === 1 ? "var(--surface-raised)" : undefined }}
        >
          <div className="site-container py-12 sm:py-16">
            <Reveal>
              <div className="max-w-3xl">
                <span className="eyebrow" style={{ color: s.accent }}>{s.eyebrow}</span>
                <h2 className="section-title mt-4 text-foreground">{s.title}</h2>
                <p className="mt-4 text-base leading-relaxed text-muted">{s.body}</p>
              </div>
            </Reveal>
            <Reveal>
              <div
                className="mt-8 surface-card rounded-lg border p-8"
                style={{ borderColor: s.border }}
              >
                <ul className="grid gap-3 sm:grid-cols-2">
                  {s.points.map((pt) => (
                    <li key={pt} className="flex gap-3 text-sm text-muted">
                      <span style={{ color: s.accent, flexShrink: 0 }}>&#x2192;</span>
                      {pt}
                    </li>
                  ))}
                </ul>
              </div>
            </Reveal>
          </div>
        </section>
      ))}

      <section className="section section-rule">
        <div className="site-container">
          <div className="cta-panel depth-hover">
            <div>
              <span className="eyebrow">Work Together</span>
              <h2 className="section-title mt-4 text-foreground">Let&apos;s talk about your project.</h2>
              <p className="mt-2 text-sm text-muted max-w-lg">
                Send a brief description of what you need and I&apos;ll come back within 24 hours.
                Day rate and project rates available.
              </p>
            </div>
            <div className="flex flex-wrap gap-3 relative z-10">
              <a href="mailto:nitedsp@outlook.com" className="btn-primary">
                Get in touch &rarr;
              </a>
              <Link href="/about" className="btn-secondary">
                About Jack
              </Link>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
