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
        <div
          role="note"
          className="mb-8 rounded-md border px-4 py-3 text-sm"
          style={{ borderColor: "#7c5a1a", background: "rgba(124,90,26,0.12)", color: "#e3b34d" }}
        >
          <strong>PROFESSIONAL REVIEW REQUIRED.</strong> This page is an AI-drafted structural
          placeholder, not legal advice, and has not been reviewed by a lawyer. It is not final
          and must not be relied on for a real purchase or dispute.
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
