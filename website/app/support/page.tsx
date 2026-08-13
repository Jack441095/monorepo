import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Support",
  description: "Getting started, activation, and troubleshooting for Smart Sample Manager.",
  alternates: { canonical: "/support" },
};

const GETTING_STARTED = [
  { step: "Sign in", body: "Go to your account and enter your email. You'll get a sign-in link -- no password to remember." },
  { step: "Download", body: "From your account, download the installer for Smart Sample Manager." },
  { step: "Install", body: "Run the installer and follow the prompts." },
  { step: "Activate", body: "Open Smart Sample Manager and enter the license key shown on your account page." },
  { step: "Add a library", body: "Point it at a folder of samples. The first scan analyzes everything locally -- nothing leaves your machine." },
  { step: "Explore", body: "Use Find Similar to jump between related sounds, or browse the visual map." },
];

const TROUBLESHOOTING = [
  {
    q: "Plugin isn't appearing in my DAW",
    a: "Rescan your plugin folders in your DAW's preferences. Confirm your DAW supports the format you installed (VST3 or AU).",
  },
  {
    q: "Activation isn't working",
    a: "Double-check you're using the exact license key from your account page, and that you have an internet connection for the first activation. If you've hit your device limit, deactivate one from your account page first.",
  },
  {
    q: "A scan seems stuck",
    a: "Large libraries take longer on the first pass -- check whether the file count is still increasing before assuming it's frozen.",
  },
  {
    q: "\"Find Similar\" isn't available yet",
    a: "This needs your library to finish scanning first. Give it a moment if you just added samples.",
  },
  {
    q: "Does it work offline?",
    a: "Yes. Once activated, Smart Sample Manager keeps working offline for up to 14 days without checking back in, then quietly re-validates the next time you're online.",
  },
  {
    q: "I moved to a new computer",
    a: "Deactivate the license on the old machine from your account page, then activate on the new one.",
  },
];

export default function SupportPage() {
  return (
    <>
      <section className="section">
        <div className="mx-auto px-6" style={{ maxWidth: "42rem" }}>
          <span className="eyebrow">Support</span>
          <h1 className="mt-3 text-3xl sm:text-4xl font-semibold tracking-tight">
            Getting started
          </h1>
          <ol className="mt-8 space-y-6">
            {GETTING_STARTED.map((item, i) => (
              <li key={item.step} className="flex gap-4">
                <span
                  className="flex-none w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold"
                  style={{ background: "var(--surface-raised)", border: "1px solid var(--border-strong)" }}
                  aria-hidden="true"
                >
                  {i + 1}
                </span>
                <div>
                  <div className="font-medium">{item.step}</div>
                  <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
                    {item.body}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto px-6" style={{ maxWidth: "42rem" }}>
          <span className="eyebrow">Troubleshooting</span>
          <h2 className="mt-3 text-2xl sm:text-3xl font-semibold tracking-tight">Common issues</h2>
          <dl className="mt-8 space-y-6">
            {TROUBLESHOOTING.map((item) => (
              <div key={item.q}>
                <dt className="font-medium">{item.q}</dt>
                <dd className="mt-2 text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
                  {item.a}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section className="section border-t" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto px-6 text-center" style={{ maxWidth: "42rem" }}>
          <h2 className="text-xl font-semibold tracking-tight">Still stuck?</h2>
          <p className="mt-3 text-sm" style={{ color: "var(--muted)" }}>
            Email us directly and we'll help you sort it out.
          </p>
          <a href="mailto:nitedsp@outlook.com" className="btn-primary mt-6">
            nitedsp@outlook.com
          </a>
        </div>
      </section>
    </>
  );
}
