"use client";

import { Suspense, useEffect, useState } from "react";
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

const PRODUCT_NAMES: Record<string, string> = {
  "smart-sample-manager": "SLO (Sample Library Optimiser)",
};

function EntitlementCard({ entitlement }: { entitlement: Entitlement }) {
  const [downloadState, setDownloadState] = useState<"idle" | "loading" | "error">("idle");
  const isBeta = entitlement.license_type === "beta";
  const productName = PRODUCT_NAMES[entitlement.product_id] ?? entitlement.product_id;

  async function handleDownload() {
    setDownloadState("loading");
    const res = await apiFetch(
      `/downloads/latest?product_id=${encodeURIComponent(entitlement.product_id)}&platform=macos&architecture=universal`
    );
    if (!res.ok) {
      setDownloadState("error");
      return;
    }
    const data = await res.json();
    setDownloadState("idle");
    window.location.href = data.download_url;
  }

  return (
    <div className="surface-card p-6 border border-border">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <span className="font-semibold text-foreground text-base block">{productName}</span>
          <span className="text-xs font-mono text-muted-dim block mt-0.5 uppercase tracking-wider">{isBeta ? "Beta Access" : entitlement.status}</span>
        </div>
        <span
          className="text-[10px] uppercase font-mono tracking-wider rounded border px-3 py-1"
          style={isBeta ? {
            background: "var(--state-warning-bg)",
            color: "var(--state-warning)",
            borderColor: "var(--state-warning-border)",
          } : {
            background: "var(--surface-raised)",
            color: "var(--muted)",
            borderColor: "var(--border-strong)",
          }}
        >
          {isBeta ? "Beta" : entitlement.status}
        </span>
      </div>
      
      <div className="mt-4 p-3 bg-background-inset rounded border border-border/40 flex items-center justify-between">
        <code className="text-xs font-mono tnum text-brand-blue-bright select-all">
          {entitlement.license_key}
        </code>
        <span className="text-[9px] font-mono text-muted-dim uppercase">LICENSE KEY</span>
      </div>

      {entitlement.expires_at && (
        <p className="mt-3 text-xs text-muted-dim tnum">
          Access expires: {new Date(entitlement.expires_at).toLocaleDateString()}
        </p>
      )}

      <div className="mt-6">
        <button 
          type="button"
          onClick={handleDownload} 
          className="btn-primary text-xs px-4 py-2" 
          disabled={downloadState === "loading"}
        >
          {downloadState === "loading" ? "Preparing download…" : "Download for macOS"}
        </button>
      </div>

      {downloadState === "error" && (
        <p className="mt-3 text-xs text-muted" role="status">
          No release available for this product yet &mdash; check back soon.
        </p>
      )}
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
                <a href="mailto:nitedsp@outlook.com" className="underline font-semibold">
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
          <a href="mailto:nitedsp@outlook.com" className="underline hover:text-foreground font-mono">
            nitedsp@outlook.com
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
