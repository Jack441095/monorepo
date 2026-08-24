import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Products & Research",
  description: "Audio production tools and ongoing digital signal processing R&D by NITE DSP.",
  alternates: { canonical: "/products" },
};

const PRODUCTS = [
  {
    name: "SLO",
    fullName: "Sample Library Optimiser",
    slug: "smart-sample-manager",
    status: "Private Beta",
    statusColor: "var(--brand-blue-bright)",
    description: "An acoustic-similarity sample browser and organizer for macOS. Groups sounds by how they actually sound, bypassing folder layout dependencies and cryptic filenames. Fully offline and private.",
    primary: true,
  },
  {
    name: "NITE Submit",
    fullName: "Autonomous Version Management",
    slug: null,
    status: "Parked / In Development",
    statusColor: "var(--muted-dim)",
    description: "An autonomous developer tools interface mapping and submitting builds to release streams. Currently parked while focusing on the core audio engine.",
    primary: false,
  },
  {
    name: "KENN",
    fullName: "Audio Classification Engine",
    slug: null,
    status: "Prototype / R&D",
    statusColor: "var(--state-warning)",
    description: "Our core deep learning classification engine mapping audio signals to complex instrument taxonomies. Functioning internally inside active research prototypes.",
    primary: false,
  },
  {
    name: "Layer Alignment",
    fullName: "Spectral Phase Corrector",
    slug: null,
    status: "Research",
    statusColor: "var(--state-warning)",
    description: "R&D project mapping and aligning phase relationships of multi-mic recordings using custom DSP filters. In active exploration.",
    primary: false,
  },
];

export default function ProductsPage() {
  const flagship = PRODUCTS.find((p) => p.primary)!;
  const standardProducts = PRODUCTS.filter((p) => !p.primary);

  return (
    <>
      {/* Products Hero */}
      <section className="section product-hero">
        <div className="site-container">
          <span className="eyebrow">Products & Research</span>
          <h1 className="section-title mt-4 text-foreground">Tools for finding the next idea.</h1>
          <p className="body-large mt-6">
            NITE DSP builds focused digital signal processing tools for professional music production. We develop tools that stay out of the way when the creative flow is moving.
          </p>
        </div>
      </section>

      {/* Flagship Highlight Section */}
      <section className="section-rule bg-[#0D1322]/10">
        <div className="site-container py-12 sm:py-20">
          <span className="eyebrow block mb-6">Flagship Experience</span>
          <div className="surface-card p-8 sm:p-12 relative overflow-hidden border border-brand-blue/30 rounded-lg">
            <div className="absolute top-0 right-0 w-96 h-96 bg-gradient-to-bl from-brand-blue/10 via-brand-violet/5 to-transparent pointer-events-none rounded-full blur-3xl" />
            
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <span className="chip-neutral font-mono text-[10px] border-brand-blue-bright text-brand-blue-bright">
                  {flagship.status}
                </span>
                <h2 className="mt-5 text-4xl font-bold text-foreground tracking-tight">{flagship.name}</h2>
                <p className="text-sm font-mono text-muted-dim mt-1.5">{flagship.fullName}</p>
              </div>
              <Link href={`/products/${flagship.slug}`} className="btn-primary">
                Explore SLO Flagship
              </Link>
            </div>

            <p className="mt-6 max-w-2xl text-base leading-relaxed text-muted">
              {flagship.description}
            </p>

            <div className="mt-10 pt-8 border-t border-border/50 grid gap-6 sm:grid-cols-3 text-xs font-mono">
              <div>
                <span className="text-muted-dim block uppercase">PLATFORM</span>
                <span className="text-foreground font-semibold mt-1 block">macOS 12+ (Apple Silicon Native)</span>
              </div>
              <div>
                <span className="text-muted-dim block uppercase">FORMATS</span>
                <span className="text-foreground font-semibold mt-1 block">AU &middot; VST3 &middot; Standalone</span>
              </div>
              <div>
                <span className="text-muted-dim block uppercase">DATA PRIVACY</span>
                <span className="text-foreground font-semibold mt-1 block">Local Scan / No Audio Uploads</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Research and Prototypes Grid */}
      <section className="section section-rule">
        <div className="site-container">
          <span className="eyebrow block">Research & R&D Labs</span>
          <h2 className="section-title mt-4">Active prototypes and parked projects.</h2>
          <p className="mt-4 text-sm max-w-2xl text-muted">
            We actively document our technology stack and prototypes. These are not commercial releases, but represent our core technical engineering estate.
          </p>

          <div className="mt-10 grid gap-6 md:grid-cols-3">
            {standardProducts.map((p) => (
              <div key={p.name} className="surface-card p-6 flex flex-col justify-between min-h-[16rem]">
                <div>
                  <div className="flex justify-between items-center gap-2">
                    <span 
                      className="text-[9px] uppercase font-mono tracking-wider px-2 py-0.5 rounded border"
                      style={{ borderColor: p.statusColor, color: p.statusColor }}
                    >
                      {p.status}
                    </span>
                  </div>
                  <h3 className="mt-5 text-xl font-semibold text-foreground">{p.name}</h3>
                  <p className="text-[11px] font-mono text-muted-dim mt-1">{p.fullName}</p>
                  <p className="mt-4 text-xs leading-relaxed text-muted">
                    {p.description}
                  </p>
                </div>
                <div className="mt-6 pt-4 border-t border-border/40">
                  <span className="text-[10px] font-mono text-muted-dim">R&D CLASSIFIED INVENTORY</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
