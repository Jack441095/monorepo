import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { StatusDot } from "@/components/motion/StatusDot";
import { Reveal } from "@/components/motion/Reveal";
import { TiltSurface } from "@/components/motion/TiltSurface";
import { SubmitPrepDemo } from "@/components/demo/SubmitPrepDemo";
import { KennMixDemo } from "@/components/demo/KennMixDemo";
import { KennChatWidget } from "@/components/KennChatWidget";
import { SloMapDemo } from "@/components/demo/SloMapDemo";

/* Phase 3 of the portfolio-readiness build (see
   docs/NITE_DSP_PORTFOLIO_READINESS_AUDIT_V1.md, the source of truth for
   every claim, number, and framing decision on this page).

   This route is deliberately unlisted: no SiteHeader nav entry, no
   sitemap.ts entry, robots.ts disallow + page-level noindex/nofollow below.
   It is a portfolio of work for employers/collaborators/technical
   reviewers, not a sales surface, no pricing, checkout, or purchase-intent
   CTA appears anywhere on this page, even for Submit and SLO which are real
   commercial products elsewhere on this site.

   Phase 5 added the access gate this comment used to say was still
   outstanding: proxy.ts puts the route behind HTTP Basic Auth on a single
   shared password (PORTFOLIO_PASSWORD), and fails closed when it is
   unset. */

export const metadata: Metadata = {
  title: { absolute: "Jack Gandy | NITE DSP" },
  description:
    "Portfolio of work behind NITE DSP: a native macOS product in private beta, a JUCE ML plugin, an AI mix-review system with a self-auditing evaluation harness, and the commercial infrastructure behind all of it.",
  robots: { index: false, follow: false },
};

type EvidenceKind = "MEASURED" | "SYNTHETIC BENCHMARK" | "SANDBOX ONLY" | "UNQUALIFIED";

const EVIDENCE_COLOR: Record<EvidenceKind, string> = {
  MEASURED: "var(--brand-blue-bright)",
  "SYNTHETIC BENCHMARK": "var(--brand-violet)",
  "SANDBOX ONLY": "var(--muted)",
  UNQUALIFIED: "var(--state-warning)",
};

function EvidenceTag({ kind }: { kind: EvidenceKind }) {
  return (
    <span
      className="dsp-pill px-2 py-0.5 whitespace-nowrap"
      style={{ color: EVIDENCE_COLOR[kind], borderColor: "var(--border-strong)" }}
    >
      {kind}
    </span>
  );
}

type StatusLabel =
  | "Shipping product, private beta"
  | "R&D prototype"
  | "Internal tool"
  | "Live infrastructure"
  | "Future concept";

const STATUS_TONE: Record<StatusLabel, "live" | "warning" | "muted"> = {
  "Shipping product, private beta": "live",
  "R&D prototype": "warning",
  "Internal tool": "muted",
  "Live infrastructure": "live",
  "Future concept": "muted",
};

function StatusLabelChip({ label }: { label: StatusLabel }) {
  const tone = STATUS_TONE[label];
  return (
    <span
      className="chip-neutral"
      style={tone === "live" ? { color: "var(--foreground)", borderColor: "var(--border-strong)" } : undefined}
    >
      <StatusDot tone={tone} live={tone === "live"} />
      {label}
    </span>
  );
}

/* One caveat line, visually distinct from a plain evidence stat, the
   device the audit calls for: numbers never appear without the context
   that keeps them honest. */
function Caveat({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="mt-3 text-xs leading-relaxed"
      style={{ color: "var(--muted-dim)", borderLeft: "2px solid var(--border-strong)", paddingLeft: "0.85rem" }}
    >
      {children}
    </p>
  );
}

const EVIDENCE_STRIP: Array<{ value: string; label: string }> = [
  { value: "252/252", label: "Submit automated tests passing" },
  { value: "819", label: "Thursday regression/adversarial tests" },
  { value: "184", label: "AudioGen dedicated test files" },
  { value: "11", label: "repos, zero secrets ever committed" },
];

type ProjectEntry = {
  name: string;
  family: string;
  statusLabel: StatusLabel;
  description: string;
  evidence: Array<{ text: React.ReactNode; tag: EvidenceKind }>;
  caveat?: React.ReactNode;
  stack: string;
  href?: { url: string; label: string };
  visual: "screenshot" | "audio" | "none";
};

const PROJECTS: ProjectEntry[] = [
  {
    name: "KENN",
    family: "AI mix review",
    statusLabel: "R&D prototype",
    description:
      "A JUCE C++ DAW plugin plus a chat assistant that reviews a mix, explains its acoustic reasoning, and applies suggestions in Ableton via a live OSC bridge.",
    evidence: [
      {
        text: "V2-D evaluation: 1.000 precision/recall on 3 qualified fault families, clipping, headroom, persistent L/R imbalance, with a 0% false-flag rate on healthy mixes.",
        tag: "MEASURED",
      },
      {
        text: "80.3% abstention rate, it reports “not confident enough to flag” far more often than it guesses.",
        tag: "MEASURED",
      },
    ],
    caveat:
      "Recall outside those 3 qualified fault families is only 57.1%. This is a narrow, rigorously measured evaluation tool, not a general-purpose mixing assistant, and an earlier internal benchmark honestly reported a version that flagged all 50 healthy controls as “not qualified” rather than shipping it.",
    stack: "JUCE (C++) plugin · Python core · fine-tuned LoRA adapter, quantized MLX model · Ableton Live OSC integration",
    href: { url: "/products/kenn", label: "See the KENN product page" },
    visual: "none",
  },
  {
    name: "SLO",
    family: "Sample Library Optimiser",
    statusLabel: "R&D prototype",
    description:
      "A native macOS plugin (AU/VST3/Standalone) that browses a sample library by acoustic similarity, a 2D map of how sounds actually sound, not how they're named.",
    evidence: [
      {
        text: "96.54% benchmark accuracy on 1,272 clean + 250 out-of-distribution samples.",
        tag: "SYNTHETIC BENCHMARK",
      },
      {
        text: "A stricter, leakage-controlled evaluation of the same classifier found only 76.4% overall accuracy, and just 5.9% audio-only accuracy, because the production classifier currently leans on filename/folder metadata rather than the sound itself.",
        tag: "MEASURED",
      },
    ],
    stack: "JUCE (C++) · PANNs CNN10 ONNX embeddings, 16-class taxonomy · real-time-safe audio thread (no file I/O, inference, or scanning on it)",
    visual: "screenshot",
  },
  {
    name: "AudioGen",
    family: "Music generation engine",
    statusLabel: "Internal tool",
    description:
      "An in-house music generation engine, Markov and neural-phrase components, not a wrapper around a third-party API, with a durable job pipeline that chains directly into KENN's mix review.",
    evidence: [
      {
        text: "184 dedicated test files covering harmony, melody, arrangement, groove, mixing, LUFS, and MIDI export.",
        tag: "MEASURED",
      },
      { text: "158 real generated loop renders, all playable, plus 3 full-song renders.", tag: "MEASURED" },
    ],
    caveat:
      "Every logged render used the “joy” mood setting. The other six moods the interface exposes were never actually rendered, so mood/style diversity is unqualified, not validated either way.",
    stack: "Python generation engine · durable job queue (leasing, heartbeats, retries, immutable event log)",
    visual: "audio",
  },
  {
    name: "Thursday",
    family: "Internal AI-agent orchestration",
    statusLabel: "Internal tool",
    description:
      "An internal orchestration layer used to help build NITE DSP itself: specialist-agent dispatch, sandboxed execution, human-approval gating, and crash recovery, with explicit permission boundaries on what agents can and can't touch.",
    evidence: [
      { text: "819 automated regression and adversarial tests, plus documented crash-recovery drills.", tag: "SANDBOX ONLY" },
    ],
    caveat:
      "All of that qualification evidence runs against a synthetic environment, not real repositories or real customer actions. Kept deliberately high-level here: this is systems-design and AI-safety context, not an architecture walkthrough.",
    stack: "Internal infrastructure, architecture and permission details are intentionally not published here.",
    href: { url: "/thursday", label: "Internal architecture overview" },
    visual: "none",
  },
];

/* Real generated output, not a mockup, copied from
   Audio_Too/business/portfolio/audio/ and transcoded to AAC for web
   delivery (same audio, smaller file). Every entry here matches a row in
   Audio_Too/data/audiogen_render_history.json verbatim (id, bars,
   created_at). All 161 logged renders used the "joy" mood setting, that's
   true of every track below too; see the caveat on the AudioGen card. */
type AudioTrack = { src: string; title: string; bars: number; kind: "loop" | "full song"; createdAt: string };

const AUDIOGEN_TRACKS: AudioTrack[] = [
  { src: "/portfolio/audio/kenn-audiogen-joy-20260804-205044.m4a", title: "Joy chorus, take 1", bars: 4, kind: "loop", createdAt: "2026-08-04 20:51" },
  { src: "/portfolio/audio/kenn-audiogen-joy-20260805-163026.m4a", title: "Joy chorus, take 2", bars: 8, kind: "loop", createdAt: "2026-08-05 16:30" },
  { src: "/portfolio/audio/kenn-audiogen-joy-20260806-175222.m4a", title: "Joy chorus, take 3", bars: 8, kind: "loop", createdAt: "2026-08-06 17:55" },
  { src: "/portfolio/audio/kenn-audiogen-joy-20260811-093826.m4a", title: "Joy chorus, take 4", bars: 8, kind: "loop", createdAt: "2026-08-11 09:38" },
  { src: "/portfolio/audio/kenn-full-song-joy-20260807-022814.m4a", title: "Joy, full song render", bars: 4, kind: "full song", createdAt: "2026-08-07 02:30" },
];

const STACK_GROUPS: Array<{ area: string; items: string }> = [
  { area: "Submit", items: "Swift · AppKit · PDFKit, zero third-party dependencies" },
  { area: "SLO plugin / KENN plugin", items: "C++ (JUCE framework) · ONNX Runtime for on-device inference" },
  { area: "KENN core / AudioGen engine", items: "Python" },
  {
    area: "Commercial platform",
    items: "Next.js · Tailwind CSS · Railway (hosting) · Paddle (payments) · Ed25519 (device-bound licensing)",
  },
];

export default function PortfolioPage() {
  return (
    <>
      {/* Hero, no product logos, one sentence of who this is and what stage
          NITE DSP is at. */}
      <section className="section product-hero">
        <div className="site-container">
          <span className="eyebrow">Portfolio, private, shared by direct link</span>
          <h1 className="hero-title mt-4 text-foreground">
            I build audio and file-intelligence software the way I&rsquo;d want it built for me.
          </h1>
          <p className="body-large mt-6">
            Offline where it matters. Tested adversarially. Honest about what&rsquo;s proven.
          </p>
          <p className="mt-8 max-w-2xl text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
            NITE DSP is a solo-founder audio and file-intelligence software company. It&rsquo;s pre-revenue:
            one product (Submit) is in private beta, several more are working R&amp;D prototypes, and all of
            it runs on a genuinely live commercial platform, payments, licensing, deployment, built and
            operated end to end. This page isn&rsquo;t a store window. It&rsquo;s the evidence behind the
            claims: test counts, benchmark methodology, and the honest gaps between what&rsquo;s measured and
            what isn&rsquo;t.
          </p>
        </div>
      </section>

      {/* Evidence strip, small, factual, mono-numeral. Not marketing badges. */}
      <section className="section-rule">
        <div className="site-container py-8">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-6">
            {EVIDENCE_STRIP.map((s) => (
              <div key={s.label}>
                <div className="font-mono tnum text-2xl sm:text-3xl font-semibold text-foreground">{s.value}</div>
                <div className="mt-1 text-[11px] uppercase tracking-wide break-words" style={{ color: "var(--muted-dim)" }}>
                  {s.label}
                </div>
              </div>
            ))}
            <div>
              <div className="flex items-center gap-2 font-mono text-lg sm:text-xl font-semibold text-foreground">
                <StatusDot tone="live" live />
                LIVE
              </div>
              <div className="mt-1 text-[11px] uppercase tracking-wide" style={{ color: "var(--muted-dim)" }}>
                www.nitedsp.co.uk, DNS/TLS verified
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Featured case studies (max 2), Submit and Commercial Infrastructure,
          the strongest real evidence trails in the estate. */}
      <section className="section section-rule">
        <div className="site-container">
          <span className="eyebrow">Featured case studies</span>
          <h2 className="section-title mt-4 text-foreground">The two strongest evidence trails.</h2>

          <div className="mt-12 flex flex-col gap-8">
            {/* Submit */}
            <Reveal>
              <div className="surface-card p-8 sm:p-10 rounded-lg border" style={{ borderColor: "var(--border-strong)" }}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <StatusLabelChip label="Shipping product, private beta" />
                    <h3 className="mt-4 text-3xl font-bold text-foreground tracking-tight">Submit</h3>
                    <p className="text-xs font-mono mt-1" style={{ color: "var(--muted-dim)" }}>
                      Document Prep Intelligence
                    </p>
                  </div>
                  <Link href="/products/submit" className="btn-secondary">
                    See the live product page &rarr;
                  </Link>
                </div>

                <p className="mt-6 max-w-2xl text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
                  A native macOS app that reviews PDF and Word submissions locally, verifies identifying
                  details against what the document actually contains, and writes a safely renamed copy
                  before you submit it. It never submits anything for you.
                </p>

                <div className="mt-8 grid gap-5 sm:grid-cols-2">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono tnum text-sm text-foreground">252/252</span>
                      <EvidenceTag kind="MEASURED" />
                    </div>
                    <p className="mt-1 text-xs" style={{ color: "var(--muted-dim)" }}>
                      automated tests passing (latest snapshot)
                    </p>
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono tnum text-sm text-foreground">98–100%</span>
                      <EvidenceTag kind="SYNTHETIC BENCHMARK" />
                    </div>
                    <p className="mt-1 text-xs" style={{ color: "var(--muted-dim)" }}>
                      field precision across a 209-case synthetic corpus
                    </p>
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono tnum text-sm text-foreground">21 documents</span>
                      <EvidenceTag kind="MEASURED" />
                    </div>
                    <p className="mt-1 text-xs" style={{ color: "var(--muted-dim)" }}>
                      real-document validation, a separate, much smaller number from the synthetic corpus above, not blended into it
                    </p>
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono tnum text-sm text-foreground">203/203</span>
                      <EvidenceTag kind="MEASURED" />
                    </div>
                    <p className="mt-1 text-xs" style={{ color: "var(--muted-dim)" }}>
                      write-load check, zero collisions, byte-identical output
                    </p>
                  </div>
                </div>

                <p className="mt-6 text-xs" style={{ color: "var(--muted-dim)" }}>
                  Swift, AppKit, PDFKit, zero third-party dependencies, fully offline by design,
                  SHA-256-verified rename/copy.
                </p>

                <p className="mt-6 text-xs italic" style={{ color: "var(--muted-dim)" }}>
                  No screenshots of the shipping app exist yet, see the interactive simulation in the
                  demos section below, which runs the same verification logic live in your browser.
                </p>
              </div>
            </Reveal>

            {/* Commercial Infrastructure */}
            <Reveal delayMs={90}>
              <div className="surface-card p-8 sm:p-10 rounded-lg border" style={{ borderColor: "var(--border-strong)" }}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <StatusLabelChip label="Live infrastructure" />
                    <h3 className="mt-4 text-3xl font-bold text-foreground tracking-tight">
                      Commercial infrastructure
                    </h3>
                    <p className="text-xs font-mono mt-1" style={{ color: "var(--muted-dim)" }}>
                      Payments, licensing, CI/CD, the platform behind everything else on this page
                    </p>
                  </div>
                  <a
                    href="https://www.nitedsp.co.uk"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-secondary"
                  >
                    See the live site &rarr;
                  </a>
                </div>

                <p className="mt-6 max-w-2xl text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
                  The production platform behind every product on this page: a live website and backend,
                  real payments plumbing, cryptographic device-bound licensing, and manual-trigger
                  validation pipelines across the estate.
                </p>

                <div className="mt-8 grid gap-5 sm:grid-cols-2">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm text-foreground">Railway, DNS/TLS verified</span>
                      <EvidenceTag kind="MEASURED" />
                    </div>
                    <p className="mt-1 text-xs" style={{ color: "var(--muted-dim)" }}>
                      production website + backend, smoke-tested routes
                    </p>
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm text-foreground">HMAC-SHA256</span>
                      <EvidenceTag kind="MEASURED" />
                    </div>
                    <p className="mt-1 text-xs" style={{ color: "var(--muted-dim)" }}>
                      Paddle payments, mandatory webhook signature verification
                    </p>
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm text-foreground">Ed25519</span>
                      <EvidenceTag kind="MEASURED" />
                    </div>
                    <p className="mt-1 text-xs" style={{ color: "var(--muted-dim)" }}>
                      device-bound licensing, race-safe activation limits
                    </p>
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono tnum text-sm text-foreground">0 / 11 repos</span>
                      <EvidenceTag kind="MEASURED" />
                    </div>
                    <p className="mt-1 text-xs" style={{ color: "var(--muted-dim)" }}>
                      secrets ever committed, across every repository in the estate
                    </p>
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm text-foreground">4 pipelines</span>
                      <EvidenceTag kind="MEASURED" />
                    </div>
                    <p className="mt-1 text-xs" style={{ color: "var(--muted-dim)" }}>
                      manual-trigger validation pipelines (not continuous CI) across platform + product builds
                    </p>
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm text-foreground">Full commerce journey</span>
                      <EvidenceTag kind="SANDBOX ONLY" />
                    </div>
                    <p className="mt-1 text-xs" style={{ color: "var(--muted-dim)" }}>
                      purchase → webhook → entitlement → signed download, rehearsed end to end on staging
                    </p>
                  </div>
                </div>

                <div className="mt-8">
                  <TiltSurface>
                    <div className="product-frame">
                      <div className="product-frame__bar">
                        <span>NITEDSP.CO.UK // PRODUCTION BUILD</span>
                        <span>DESKTOP VIEWPORT</span>
                      </div>
                      {/* unoptimized on purpose: /portfolio/* sits behind the
                          Basic-Auth proxy, and Next's image optimizer refetches
                          the source server-side without the visitor's
                          credentials -- it got a 401 and served a 400, so this
                          image never rendered at all. */}
                      <div className="relative w-full overflow-hidden" style={{ maxHeight: "22rem" }}>
                        <Image
                          src="/portfolio/website-home-1440.jpg"
                          alt="Live NITE DSP marketing site homepage, production build, desktop viewport"
                          width={1440}
                          height={5071}
                          className="w-full h-auto block"
                          style={{ objectFit: "cover", objectPosition: "top" }}
                          unoptimized
                        />
                      </div>
                    </div>
                  </TiltSurface>
                  <p className="mt-3 text-xs" style={{ color: "var(--muted-dim)" }}>
                    Real screenshot of the live production site (not a mockup), cropped to the top of the
                    page, full-page capture available on request.
                  </p>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* Project cards, KENN, SLO, AudioGen, Thursday. */}
      <section className="section section-rule bg-surface/10">
        <div className="site-container">
          <span className="eyebrow">Other work</span>
          <h2 className="section-title mt-4 text-foreground">R&amp;D, internal tools, and infrastructure.</h2>
          <p className="mt-4 max-w-2xl text-sm" style={{ color: "var(--muted)" }}>
            Prototype, validated on internal benchmarks, not yet in front of real users.
          </p>

          <div className="mt-12 grid gap-8 md:grid-cols-2">
            {PROJECTS.map((p) => (
              <Reveal key={p.name}>
                <div
                  className="surface-card depth-hover p-8 rounded-lg border flex flex-col justify-between h-full"
                  style={{ borderColor: "var(--border)" }}
                >
                  <div>
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <StatusLabelChip label={p.statusLabel} />
                      <span className="text-[10px] font-mono uppercase" style={{ color: "var(--muted-dim)" }}>
                        {p.family}
                      </span>
                    </div>
                    <h3 className="mt-5 text-2xl font-bold text-foreground">{p.name}</h3>
                    <p className="mt-4 text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
                      {p.description}
                    </p>

                    <div className="mt-6 flex flex-col gap-3">
                      {p.evidence.map((e, i) => (
                        <div key={i} className="flex items-start gap-2 flex-wrap">
                          <EvidenceTag kind={e.tag} />
                          <span className="text-xs leading-relaxed" style={{ color: "var(--muted)" }}>
                            {e.text}
                          </span>
                        </div>
                      ))}
                    </div>

                    {p.caveat && <Caveat>{p.caveat}</Caveat>}

                    {p.visual === "screenshot" && p.name === "SLO" && (
                      <div className="mt-6">
                        <div className="rounded-lg overflow-hidden border" style={{ borderColor: "var(--border-strong)" }}>
                          <Image
                            src="/screenshots/main-browser.png"
                            alt="SLO's SmartSampleManager plugin GUI in an empty, unscanned state"
                            width={1599}
                            height={1057}
                            className="w-full h-auto block"
                            sizes="(max-width: 1024px) 100vw, 560px"
                          />
                        </div>
                        <p className="mt-2 text-[11px]" style={{ color: "var(--muted-dim)" }}>
                          Early build, captured before population: this is the only screenshot in
                          the repo, and it shows the browser in its empty, pre-scan state rather
                          than a full library.
                        </p>
                      </div>
                    )}

                    {p.visual === "audio" && (
                      <div className="mt-6">
                        <p className="text-[10px] font-mono uppercase tracking-wider" style={{ color: "var(--muted-dim)" }}>
                          No UI screenshot exists yet, here&rsquo;s what it actually produces
                        </p>
                        <div className="mt-3 flex flex-col gap-3">
                          {AUDIOGEN_TRACKS.map((t) => (
                            <div
                              key={t.src}
                              className="rounded-lg border p-3 sm:p-4"
                              style={{ borderColor: "var(--border)", background: "var(--surface)" }}
                            >
                              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                                <span className="text-xs font-semibold text-foreground">{t.title}</span>
                                <span className="font-mono tnum text-[10px]" style={{ color: "var(--muted-dim)" }}>
                                  {t.kind} · {t.bars} bars · {t.createdAt}
                                </span>
                              </div>
                              <audio
                                controls
                                preload="none"
                                src={t.src}
                                aria-label={`${t.title}, ${t.kind}, ${t.bars} bars`}
                                className="mt-2 w-full"
                                style={{ height: "2rem" }}
                              />
                            </div>
                          ))}
                        </div>
                        <p className="mt-3 text-[11px]" style={{ color: "var(--muted-dim)" }}>
                          Real renders from the engine, transcoded for web delivery, not remastered or
                          hand-picked for quality, just picked to span different capture dates. Every one
                          uses the &ldquo;joy&rdquo; mood setting (see caveat above).
                        </p>
                      </div>
                    )}
                  </div>

                  <div className="mt-8 pt-4 border-t flex items-center justify-between flex-wrap gap-3" style={{ borderColor: "var(--border)" }}>
                    <span className="text-[10px] font-mono" style={{ color: "var(--muted-dim)" }}>
                      {p.stack}
                    </span>
                    {p.href && (
                      <Link href={p.href.url} className="text-link text-xs">
                        {p.href.label} &rarr;
                      </Link>
                    )}
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Technical stack, plain list, no logos-as-decoration. */}
      <section className="section-rule">
        <div className="site-container py-12 sm:py-16">
          <span className="eyebrow">Technical stack</span>
          <h2 className="section-title mt-4 text-foreground">What&rsquo;s actually running.</h2>
          <div className="mt-10 workflow-list">
            {STACK_GROUPS.map((g) => (
              <div
                key={g.area}
                className="grid sm:grid-cols-[14rem_1fr] gap-2 sm:gap-8 py-5 border-b"
                style={{ borderColor: "var(--border)" }}
              >
                <span className="text-sm font-semibold text-foreground">{g.area}</span>
                <span className="font-mono text-xs leading-relaxed" style={{ color: "var(--muted)" }}>
                  {g.items}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Audio engineering background. */}
      <section className="section-rule">
        <div className="site-container py-12 sm:py-16" style={{ maxWidth: "48rem" }}>
          <span className="eyebrow">Background</span>
          <h2 className="section-title mt-4 text-foreground">Why these products exist.</h2>
          <p className="mt-6 text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
            Every product here comes out of hands-on time mixing and producing audio, not a market
            analysis. Submit exists because document submission workflows are a specific, familiar,
            error-prone chore, the kind of thing that&rsquo;s easy to get quietly wrong under deadline
            pressure. SLO and KENN both target problems that only show up once you&rsquo;ve actually spent
            hours digging through a badly-organised sample library or trying to explain, out loud, why a
            mix doesn&rsquo;t feel finished yet. Building the tools honestly, offline by default, tested
            adversarially, explicit about what they don&rsquo;t know, is a direct consequence of having
            been the frustrated user first.
          </p>
        </div>
      </section>

      {/* Selected demos, the real, working interactive components, reused
          as-is rather than screenshots for the projects that don't have any. */}
      <section className="section section-rule bg-surface/10">
        <div className="site-container">
          <span className="eyebrow">Selected demos</span>
          <h2 className="section-title mt-4 text-foreground">Working code, not mockups.</h2>
          <p className="mt-4 max-w-2xl text-sm" style={{ color: "var(--muted)" }}>
            Simulated walkthroughs of how each product thinks, running entirely in your browser with
            illustrative data, nothing is uploaded, nothing is processed externally. These are the same
            claim-safe demo components used elsewhere on this site, not new mockups built for this page.
          </p>

          <div className="mt-12 grid grid-cols-1 gap-10 lg:grid-cols-3 items-start">
            <Reveal>
              <div className="mb-4">
                <span className="text-[10px] font-mono font-bold uppercase block mb-1 text-[color:var(--brand-blue-bright)]">
                  Submit
                </span>
                <h3 className="text-lg font-semibold text-foreground">Prepare files safely</h3>
                <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
                  Local document review, verified fields, and a safely renamed output preview.
                </p>
              </div>
              <SubmitPrepDemo />
            </Reveal>
            <Reveal delayMs={80}>
              <div className="mb-4">
                <span className="text-[10px] font-mono font-bold uppercase block mb-1 text-[color:var(--brand-violet)]">
                  KENN
                </span>
                <h3 className="text-lg font-semibold text-foreground">Mix review, explained</h3>
                <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
                  Analyse a mix and see the acoustic reasoning behind each flagged issue.
                </p>
              </div>
              <KennMixDemo />
            </Reveal>
            <Reveal delayMs={160}>
              <div className="mb-4">
                <span className="text-[10px] font-mono font-bold uppercase block mb-1 text-[color:var(--brand-blue-bright)]">
                  SLO
                </span>
                <h3 className="text-lg font-semibold text-foreground">Browse by similarity</h3>
                <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
                  A 2D acoustic similarity map, the same interaction model as the plugin&rsquo;s browser.
                </p>
              </div>
              <SloMapDemo />
            </Reveal>
          </div>
        </div>
      </section>

      {/* KENN's scoped live retrieval surface. */}
      <section className="section section-rule">
        <div className="site-container">
          <span className="eyebrow">KENN, audio engineering advice</span>
          <h2 className="section-title mt-4 text-foreground">Tested mix-advice demo.</h2>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
            Ask a text-only mix-engineering question and inspect the answer&rsquo;s confidence and approved
            source metadata. KENN abstains when the scope or evidence boundary is not met.
          </p>
          <div className="mt-10 max-w-4xl">
            <KennChatWidget />
          </div>
          <Caveat>
            Local receipt: 34/34 diagnostic cases, 6/6 multi-turn cases, and 30/30 negative-advice guards
            pass with LLMs disabled. The website proxy is wired, but no public KENN endpoint is configured
            yet. This is retrieval from KENN&rsquo;s approved knowledge, not audio analysis, a guarantee, or a
            replacement for an engineer&rsquo;s judgement.
          </Caveat>
        </div>
      </section>

      {/* CV / contact, direct, no form friction, no purchase or pricing CTA. */}
      <section className="section-rule">
        <div className="site-container py-16 sm:py-20" style={{ maxWidth: "40rem" }}>
          <span className="eyebrow">Get in touch</span>
          <h2 className="section-title mt-4 text-foreground">Jack Gandy at NITE DSP.</h2>
          <p className="mt-6 text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
            This page exists to show the work directly. If it&rsquo;s relevant to something you&rsquo;re
            hiring for or building, the fastest path is email, CV available on request, no form to fill
            in first.
          </p>
          <div className="mt-8">
            <a href="mailto:support@nitedsp.co.uk?subject=Portfolio%20inquiry" className="btn-primary">
              Email me &rarr;
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
