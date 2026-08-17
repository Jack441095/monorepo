export function LegalPage({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="section">
      <div className="mx-auto px-6" style={{ maxWidth: "42rem" }}>
        <div role="note" className="callout-warning mb-8">
          <strong>PRE-LAUNCH DRAFT.</strong> This page has not yet received professional legal
          review. It is provided for product review only and must be finalised before paid public launch.
        </div>
        <span className="eyebrow">Legal</span>
        <h1 className="mt-2 text-2xl sm:text-3xl font-semibold tracking-tight">{title}</h1>
        <div className="mt-6 space-y-4 text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
          {children}
        </div>
        <p className="mt-10 text-sm" style={{ color: "var(--muted-dim)" }}>
          Questions about this page? Contact{" "}
          <a href="mailto:nitedsp@outlook.com" className="underline">
            nitedsp@outlook.com
          </a>
          .
        </p>
      </div>
    </div>
  );
}
