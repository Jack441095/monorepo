"use client";

import { Suspense, useEffect, useState, useSyncExternalStore } from "react";
import { useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { consumeBuyIntent, startCheckout } from "@/lib/checkout";

type User = { id: string; email: string; created_at: string };
type Entitlement = {
  id: string;
  product_id: string;
  license_key: string;
  license_type: string;
  status: string;
  expires_at: string | null;
};

type PlatformId = "macos" | "windows" | "linux";

type PlatformOption = {
  id: PlatformId;
  label: string;
  architecture: string;
  description: string;
};

type DownloadInfo = {
  version: string;
  checksum_sha256: string;
  release_notes: string | null;
  download_url: string;
};

const PLATFORM_OPTIONS: PlatformOption[] = [
  { id: "macos", label: "macOS", architecture: "universal", description: "Universal Mac ZIP" },
  { id: "windows", label: "Windows", architecture: "x64", description: "64-bit Windows ZIP" },
  { id: "linux", label: "Linux", architecture: "x64", description: "64-bit Linux ZIP" },
];

// Release rows carry the authoritative architecture. SLO currently uses the
// existing universal macOS contract; the staged NITE Submit candidate is an
// Apple-Silicon arm64 build, so its account request must match that row rather
// than pretending the archive is universal.
function platformOptionsFor(productId: string): PlatformOption[] {
  if (productId !== "nite-submit") return PLATFORM_OPTIONS;
  return PLATFORM_OPTIONS.map((option) =>
    option.id === "macos"
      ? { ...option, architecture: "arm64", description: "Apple Silicon Mac ZIP" }
      : option,
  );
}

function detectRecommendedPlatform(): PlatformId | null {
  if (typeof navigator === "undefined") return null;
  const userAgent = navigator.userAgent.toLowerCase();
  if (userAgent.includes("mac")) return "macos";
  if (userAgent.includes("windows")) return "windows";
  if (userAgent.includes("linux")) return "linux";
  return null;
}

const noPlatformSubscription = () => () => {};
const noServerPlatform = (): PlatformId | null => null;

const PRODUCT_NAMES: Record<string, string> = {
  "smart-sample-manager": "SLO (Sample Library Optimiser)",
  "nite-submit": "NITE Submit",
};

function EntitlementCard({ entitlement }: { entitlement: Entitlement }) {
  const [downloadState, setDownloadState] = useState<Record<PlatformId, "idle" | "loading" | "error">>({
    macos: "idle",
    windows: "idle",
    linux: "idle",
  });
  const [downloadInfo, setDownloadInfo] = useState<Partial<Record<PlatformId, DownloadInfo>>>({});
  const recommendedPlatform = useSyncExternalStore(
    noPlatformSubscription,
    detectRecommendedPlatform,
    noServerPlatform,
  );
  const isBeta = entitlement.license_type === "beta";
  const productName = PRODUCT_NAMES[entitlement.product_id] ?? entitlement.product_id;
  const platformOptions = platformOptionsFor(entitlement.product_id);

  async function prepareDownload(option: PlatformOption) {
    setDownloadState((current) => ({ ...current, [option.id]: "loading" }));
    const res = await apiFetch(
      `/downloads/latest?product_id=${encodeURIComponent(entitlement.product_id)}&platform=${option.id}&architecture=${option.architecture}`
    );
    if (!res.ok) {
      setDownloadState((current) => ({ ...current, [option.id]: "error" }));
      return;
    }
    const data = await res.json();
    setDownloadInfo((current) => ({ ...current, [option.id]: data }));
    setDownloadState((current) => ({ ...current, [option.id]: "idle" }));
  }

  return (
    <div className="dsp-rack-panel p-6 border border-border-strong/60 rounded-xl shadow-[0_10px_30px_rgba(0,0,0,0.5)]">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <span className="dsp-led dsp-led--live" />
            <span className="font-semibold text-foreground text-base block">{productName}</span>
          </div>
          <span className="text-[10px] font-mono text-muted-dim block mt-1 uppercase tracking-wider">
            {isBeta ? "BETA ACCESS LICENCE" : `STATUS // ${entitlement.status}`}
          </span>
        </div>
        <span
          className="dsp-pill text-[10px] uppercase font-mono tracking-wider px-3 py-1"
          style={isBeta ? {
            background: "rgba(245, 158, 11, 0.12)",
            color: "var(--state-warning)",
            borderColor: "var(--state-warning-border)",
          } : {
            background: "var(--surface-raised)",
            color: "var(--brand-blue-bright)",
            borderColor: "var(--border-strong)",
          }}
        >
          {isBeta ? "Closed Beta" : entitlement.status}
        </span>
      </div>
      
      {/* LCD License Key Container */}
      <div className="mt-5 p-3.5 dsp-lcd-box rounded-lg flex items-center justify-between gap-3">
        <code className="text-xs font-mono tnum text-brand-blue-bright select-all tracking-wider font-bold">
          {entitlement.license_key}
        </code>
        <span className="text-[9px] font-mono text-muted-dim uppercase tracking-widest flex-none">LICENSE KEY</span>
      </div>

      {entitlement.expires_at && (
        <p className="mt-3 text-xs text-muted-dim tnum font-mono">
          Access expires: {new Date(entitlement.expires_at).toLocaleDateString()}
        </p>
      )}

      {/* Multi-Platform Download Modules (macOS, Windows, Linux) */}
      <div className="mt-6 space-y-3">
        <div className="flex items-center justify-between border-b border-border/40 pb-2">
          <p className="text-[11px] font-mono font-bold uppercase tracking-wider text-brand-blue-bright">
            PLATFORM BUILDS & EXECUTABLES
          </p>
          <span className="text-[10px] font-mono text-muted-dim">Select Target OS</span>
        </div>
        
        {platformOptions.map((option) => {
          const state = downloadState[option.id];
          const info = downloadInfo[option.id];
          const isRecommended = recommendedPlatform === option.id;
          return (
            <div key={option.id} className="rounded-lg border border-border/50 bg-surface/60 p-4 transition-all hover:border-border-strong">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-foreground text-sm font-mono">{option.label}</span>
                  <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-surface-raised border border-border/40 text-muted-dim">
                    {option.architecture}
                  </span>
                  <span className="text-xs text-muted-dim font-mono">{option.description}</span>
                </div>
                {isRecommended && (
                  <span className="text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-brand-blue/15 text-brand-blue-bright border border-brand-blue/30 font-bold">
                    RECOMMENDED FOR THIS DEVICE
                  </span>
                )}
              </div>

              <button
                type="button"
                onClick={() => prepareDownload(option)}
                className="btn-primary mt-3 text-xs px-4 py-2 font-mono font-semibold"
                disabled={state === "loading"}
              >
                {state === "loading" ? "PREPARING DOWNLOAD…" : `PREPARE ${option.label.toUpperCase()} ZIP`}
              </button>

              {state === "error" && (
                <div className="mt-3 p-2.5 rounded bg-surface-raised border border-border text-xs text-muted font-mono" role="status">
                  <span className="text-state-warning font-bold">STATUS // UNPUBLISHED</span> &mdash; No {option.label} release is published for this channel yet. Check back soon.
                </div>
              )}

              {info && (
                <div className="mt-3 space-y-2 text-xs text-muted font-mono p-3 dsp-lcd-box rounded" role="status">
                  <div className="flex justify-between items-baseline">
                    <span className="text-foreground font-bold">Version {info.version}</span>
                    <span className="text-[10px] text-muted-dim uppercase">SHA-256 Checksum</span>
                  </div>
                  <code className="block break-all p-2 rounded bg-[#020408] border border-border/40 text-[10px] text-brand-emerald select-all tnum">
                    {info.checksum_sha256}
                  </code>
                  <a
                    href={info.download_url}
                    download
                    className="inline-block mt-2 px-3 py-1.5 rounded bg-brand-blue text-accent-ink font-bold text-xs hover:bg-brand-blue-bright transition-all shadow-[0_0_10px_rgba(0,240,255,0.3)]"
                  >
                    DOWNLOAD {option.label.toUpperCase()} ZIP &rarr;
                  </a>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AccountPageInner() {
  const searchParams = useSearchParams();
  const purchasePending = searchParams.get("purchase") === "pending";

  const [user, setUser] = useState<User | null>(null);
  const [entitlements, setEntitlements] = useState<Entitlement[]>([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [linkSent, setLinkSent] = useState(false);
  const [pendingState, setPendingState] = useState<"waiting" | "timed-out">("waiting");

  useEffect(() => {
    apiFetch("/auth/me")
      .then(async (res) => {
        if (!res.ok) return null;
        return res.json();
      })
      .then((data) => setUser(data))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!user) return;
    apiFetch("/auth/entitlements")
      .then((res) => (res.ok ? res.json() : []))
      .then(setEntitlements);
  }, [user]);

  useEffect(() => {
    if (!user) return;
    if (consumeBuyIntent()) {
      startCheckout("active");
    }
  }, [user]);

  useEffect(() => {
    if (!user || !purchasePending || entitlements.length > 0) return;
    let cancelled = false;
    let attempts = 0;
    const poll = setInterval(async () => {
      attempts += 1;
      const res = await apiFetch("/auth/entitlements");
      const data = res.ok ? await res.json() : [];
      if (cancelled) return;
      if (data.length > 0) {
        setEntitlements(data);
        clearInterval(poll);
      } else if (attempts >= 10) {
        setPendingState("timed-out");
        clearInterval(poll);
      }
    }, 3000);
    return () => {
      cancelled = true;
      clearInterval(poll);
    };
  }, [user, purchasePending, entitlements.length]);

  async function requestLink(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch("/auth/request-link", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    setLinkSent(true);
  }

  async function signOut() {
    await apiFetch("/auth/logout", { method: "POST" });
    setUser(null);
    setEntitlements([]);
  }

  if (loading) {
    return (
      <div className="section text-center text-muted font-mono text-xs">
        Loading session...
      </div>
    );
  }

  if (!user) {
    return (
      <div className="section">
        <div className="mx-auto px-6 max-w-[28rem] surface-card p-8 border border-border">
          <span className="eyebrow">Account Portal</span>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-foreground">Sign in</h1>
          <p className="mt-2 text-xs text-muted leading-relaxed">
            Enter your email to request a secure passwordless sign-in link.
          </p>
          {linkSent ? (
            <p className="mt-6 text-sm text-brand-blue-bright font-mono" role="status">
              Check your email &mdash; a sign-in link has been sent.
            </p>
          ) : (
            <form onSubmit={requestLink} className="mt-6 flex flex-col gap-3">
              <div>
                <label htmlFor="email" className="sr-only">
                  Email address
                </label>
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full rounded border px-3.5 py-2.5 text-sm font-mono focus:border-brand-blue outline-none"
                  style={{ borderColor: "var(--border-strong)", background: "var(--background-inset)", color: "var(--foreground)" }}
                />
              </div>
              <button type="submit" className="btn-primary w-full">
                Send sign-in link
              </button>
            </form>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="section">
      <div className="mx-auto px-6" style={{ maxWidth: "42rem" }}>
        <div className="flex items-center justify-between border-b pb-6" style={{ borderColor: "var(--border)" }}>
          <div>
            <span className="eyebrow">User Dashboard</span>
            <h1 className="mt-1 text-2xl sm:text-3xl font-bold tracking-tight text-foreground">Your Account</h1>
            <p className="mt-1 text-xs text-muted-dim font-mono">{user.email}</p>
          </div>
          <button
            onClick={signOut}
            className="text-xs transition-colors hover:text-brand-red font-mono cursor-pointer"
            style={{ color: "var(--muted-dim)" }}
          >
            Sign out
          </button>
        </div>

        {purchasePending && entitlements.length === 0 && (
          <div className="mt-8 callout-warning">
            {pendingState === "timed-out" ? (
              <p className="text-sm">
                Confirming your purchase is taking longer than usual. Please refresh in a moment, or{" "}
                <a href="mailto:support@nitedsp.co.uk" className="underline font-semibold">
                  contact support
                </a>{" "}
                if it does not appear soon.
              </p>
            ) : (
              <p className="text-sm">
                Payment received. We are waiting for the server webhook to generate your licence key...
              </p>
            )}
          </div>
        )}

        <h2 className="mt-10 eyebrow text-xs">Licences & Downloads</h2>
        {entitlements.length === 0 ? (
          <p className="mt-4 text-sm text-muted" style={{ color: "var(--muted-dim)" }}>
            {purchasePending ? (
              "Your product will appear here as soon as the purchase webhook clears."
            ) : (
              <>
                No active licences. View{" "}
                <a href="/pricing" className="underline text-brand-blue-bright">
                  pricing plans
                </a>
                .
              </>
            )}
          </p>
        ) : (
          <div className="mt-4 space-y-4">
            {entitlements.map((e) => (
              <EntitlementCard key={e.id} entitlement={e} />
            ))}
          </div>
        )}

        <p className="mt-12 text-xs" style={{ color: "var(--muted-dim)" }}>
          Having account issues? Contact us at{" "}
          <a href="mailto:support@nitedsp.co.uk" className="underline hover:text-foreground font-mono">
            support@nitedsp.co.uk
          </a>
          .
        </p>
      </div>
    </div>
  );
}

export default function AccountPage() {
  return (
    <Suspense
      fallback={
        <div className="section text-center text-muted font-mono text-xs">
          Loading dashboard...
        </div>
      }
    >
      <AccountPageInner />
    </Suspense>
  );
}
