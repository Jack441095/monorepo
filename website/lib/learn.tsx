import Link from "next/link";

export const LEARN_PAGES = [
  { slug: "getting-started", title: "Getting Started" },
  { slug: "installation", title: "Installation" },
  { slug: "find-similar", title: "Find Similar" },
  { slug: "visual-map", title: "Visual Map" },
  { slug: "ableton-integration", title: "Ableton Integration (Experimental)" },
  { slug: "troubleshooting", title: "Troubleshooting" },
  { slug: "faq", title: "FAQ" },
] as const;

const BASE = "/learn/smart-sample-manager";

export function LearnLayout({
  slug,
  title,
  children,
}: {
  slug: (typeof LEARN_PAGES)[number]["slug"];
  title: string;
  children: React.ReactNode;
}) {
  const index = LEARN_PAGES.findIndex((p) => p.slug === slug);
  const prev = index > 0 ? LEARN_PAGES[index - 1] : null;
  const next = index >= 0 && index < LEARN_PAGES.length - 1 ? LEARN_PAGES[index + 1] : null;

  return (
    <div className="section">
      <div className="mx-auto px-6" style={{ maxWidth: "var(--content-width)" }}>
        <nav aria-label="Breadcrumb" className="text-sm" style={{ color: "var(--muted-dim)" }}>
          <Link href="/learn" className="hover:text-[color:var(--foreground)] transition-colors">
            Learn
          </Link>{" "}
          / <span style={{ color: "var(--muted)" }}>SLO</span> /{" "}
          <span style={{ color: "var(--foreground)" }}>{title}</span>
        </nav>

        <div className="mt-8 grid gap-10 lg:grid-cols-[16rem_1fr]">
          <aside className="hidden lg:block">
            <div className="sticky top-24">
              <span className="eyebrow">On this topic</span>
              <ul className="mt-3 space-y-1 text-sm">
                {LEARN_PAGES.map((p) => (
                  <li key={p.slug}>
                    <Link
                      href={`${BASE}/${p.slug}`}
                      className="block rounded-md px-2 py-1.5 transition-colors"
                      style={{
                        color: p.slug === slug ? "var(--foreground)" : "var(--muted)",
                        background: p.slug === slug ? "var(--surface-raised)" : "transparent",
                      }}
                      aria-current={p.slug === slug ? "page" : undefined}
                    >
                      {p.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </aside>

          <div className="min-w-0">
            <h1 className="text-2xl sm:text-4xl font-semibold tracking-tight text-balance">
              {title}
            </h1>
            <div className="mt-8 space-y-8 text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
              {children}
            </div>

            <div className="mt-16 pt-8 border-t flex flex-wrap items-center justify-between gap-4" style={{ borderColor: "var(--border)" }}>
              {prev ? (
                <Link href={`${BASE}/${prev.slug}`} className="btn-secondary">
                  &larr; {prev.title}
                </Link>
              ) : (
                <span />
              )}
              {next ? (
                <Link href={`${BASE}/${next.slug}`} className="btn-secondary">
                  {next.title} &rarr;
                </Link>
              ) : (
                <span />
              )}
            </div>

            <p className="mt-8 text-sm" style={{ color: "var(--muted-dim)" }}>
              Still stuck?{" "}
              <a href="mailto:support@nitedsp.co.uk" className="underline">
                Contact NITE DSP support
              </a>
              .
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export function LearnH2({ children }: { children: React.ReactNode }) {
  return (
    <h2
      className="text-lg font-semibold tracking-tight"
      style={{ color: "var(--foreground)" }}
    >
      {children}
    </h2>
  );
}
