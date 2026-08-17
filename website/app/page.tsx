import Image from "next/image";
import Link from "next/link";

const WORKFLOWS = [
  ["01", "Scan the library you already own", "SLO reads your local sample folders and builds a searchable view of the sounds, keys, tempos and categories already on your drives."],
  ["02", "Find a sound by its character", "Start from a sample you trust. Find Similar surfaces nearby timbres, transients and spectral balance instead of relying on filenames alone."],
  ["03", "Audition, compare, then drag", "Use the browser, map or split view to make a fast decision. Keep the sample path clear from library to your DAW."],
] as const;

const CAPABILITIES = [
  ["Precision Browser", "A dense, readable view of sample name, type, key, BPM and duration."],
  ["Visual Map", "A spatial view of sonic relationships across the scanned library."],
  ["Find Similar", "Choose a reference sample and explore related sounds by audio characteristics."],
  ["Local analysis", "Scanning and matching run on your Mac. Your sample library stays on your drive."],
] as const;

export default function HomePage() {
  return <>
    <section className="hero-grid overflow-hidden"><div className="site-container grid items-center gap-12 py-16 lg:grid-cols-[0.84fr_1.16fr] lg:py-24">
      <div className="relative z-10"><span className="eyebrow">NITE DSP / SLO</span><h1 className="hero-title mt-5">Your sample library, organised by sound.</h1><p className="hero-copy mt-6">SLO is a macOS sample browser for producers who know the sound they want but not the filename that contains it. Search, audition and compare your own library in one place.</p><div className="mt-9 flex flex-wrap gap-3"><Link href="/products/smart-sample-manager" className="btn-primary">View SLO</Link><Link href="/pricing" className="btn-secondary">See pricing</Link></div><p className="mt-6 text-xs" style={{ color: "var(--muted-dim)" }}>macOS · AU · VST3 · Standalone</p></div>
      <div className="product-frame product-frame--hero"><div className="product-frame__bar"><span>SMART SAMPLE MANAGER</span><span>LIST / MAP / SPLIT</span></div><Image src="/screenshots/main-browser.png" alt="SLO showing a searchable sample browser and selected sample detail panel" width={1599} height={1057} priority sizes="(max-width: 1024px) 100vw, 58vw" className="h-auto w-full" /></div>
    </div></section>

    <section className="section section-rule"><div className="site-container grid gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:items-start"><div><span className="eyebrow">The library problem</span><h2 className="section-title mt-4">Folders are good at storage. They are not good at recall.</h2></div><p className="body-large">A good library gathers years of purchases, resamples, edits and half-forgotten packs. SLO gives those sounds a view based on what they contain, so a useful kick, texture or transient is not lost behind a name you would never think to search for.</p></div></section>

    <section className="section section-rule"><div className="site-container"><div className="max-w-2xl"><span className="eyebrow">A working route to the right sound</span><h2 className="section-title mt-4">Less folder archaeology. More listening.</h2></div><ol className="workflow-list mt-12">{WORKFLOWS.map(([number, title, body]) => <li key={number} className="workflow-item"><span className="workflow-number">{number}</span><div><h3>{title}</h3><p>{body}</p></div></li>)}</ol></div></section>

    <section className="section section-rule"><div className="site-container grid gap-12 lg:grid-cols-[1.12fr_0.88fr] lg:items-center"><div className="product-frame product-frame--detail"><div className="product-frame__bar"><span>DISCOVERY VIEW</span><span>500 SAMPLES</span></div><Image src="/screenshots/main-browser.png" alt="SLO visual map and browser used together in split view" width={1599} height={1057} sizes="(max-width: 1024px) 100vw, 55vw" className="h-auto w-full" /></div><div><span className="eyebrow">Built for decisions, not dashboards</span><h2 className="section-title mt-4">The browser is detailed. The map is intuitive. Split view keeps both in reach.</h2><p className="mt-5 leading-relaxed" style={{ color: "var(--muted)" }}>Move between a precise list and a broad view of the library without abandoning the selected sound. SLO is designed around auditioning and comparison, not admin work.</p><Link href="/products/smart-sample-manager" className="text-link mt-7">Explore the SLO workflow <span aria-hidden="true">→</span></Link></div></div></section>

    <section className="section section-rule"><div className="site-container"><div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-end"><div className="max-w-2xl"><span className="eyebrow">What is in the product</span><h2 className="section-title mt-4">A focused set of tools for sample discovery.</h2></div><Link href="/products/smart-sample-manager" className="text-link">Product details <span aria-hidden="true">→</span></Link></div><div className="capability-grid mt-10">{CAPABILITIES.map(([title, body]) => <article key={title} className="capability"><h3>{title}</h3><p>{body}</p></article>)}</div></div></section>

    <section className="section section-rule"><div className="site-container cta-panel"><div><span className="eyebrow">SLO for macOS</span><h2 className="section-title mt-4">Find the sound. Keep making the track.</h2></div><div className="flex flex-wrap gap-3"><Link href="/pricing" className="btn-primary">See pricing</Link><Link href="/learn" className="btn-secondary">Read the docs</Link></div></div></section>
  </>;
}
