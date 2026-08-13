"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

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
  "smart-sample-manager": "Smart Sample Manager",
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
    <div className="surface-card p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium">{productName}</span>
        <span
          className="text-xs uppercase tracking-wide rounded-full px-2.5 py-1"
          style={{
            background: isBeta ? "rgba(124,90,26,0.15)" : "var(--surface-raised)",
            color: isBeta ? "#e3b34d" : "var(--muted)",
            border: `1px solid ${isBeta ? "#7c5a1a" : "var(--border-strong)"}`,
          }}
        >
          {isBeta ? "Beta" : entitlement.status}
        </span>
      </div>
      <p className="mt-1 text-xs font-mono" style={{ color: "var(--muted-dim)" }}>
        {entitlement.license_key}
      </p>
      {entitlement.expires_at && (
        <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
          {isBeta ? "Beta access" : "Access"} expires {new Date(entitlement.expires_at).toLocaleDateString()}
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-3">
        <button onClick={handleDownload} className="btn-secondary text-xs px-4 py-2" disabled={downloadState === "loading"}>
          {downloadState === "loading" ? "Preparing download…" : "Download for macOS"}
        </button>
      </div>
      {downloadState === "error" && (
        <p className="mt-2 text-xs" style={{ color: "#e3b34d" }}>
          No release available for this product yet -- check back soon.
        </p>
      )}
    </div>
  );
}

export default function AccountPage() {
  const [user, setUser] = useState<User | null>(null);
  const [entitlements, setEntitlements] = useState<Entitlement[]>([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [linkSent, setLinkSent] = useState(false);

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
      <div className="section text-center" style={{ color: "var(--muted-dim)" }}>
        Loading…
      </div>
    );
  }

  if (!user) {
    return (
      <div className="section">
        <div className="mx-auto px-6" style={{ maxWidth: "26rem" }}>
          <span className="eyebrow">Account</span>
          <h1 className="mt-2 text-2xl sm:text-3xl font-semibold tracking-tight">Sign in</h1>
          <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
            We&apos;ll email you a sign-in link -- no password needed.
          </p>
          {linkSent ? (
            <p className="mt-6 text-sm" style={{ color: "var(--muted)" }}>
              Check your email for a sign-in link. (Local staging: the link is printed to the
              backend console, since no real email account is configured yet.)
            </p>
          ) : (
            <form onSubmit={requestLink} className="mt-6 flex gap-2">
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
                className="flex-1 rounded-md border px-3 py-2 text-sm"
                style={{ borderColor: "var(--border-strong)", background: "var(--surface)", color: "var(--foreground)" }}
              />
              <button type="submit" className="btn-primary">
                Send link
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
        <div className="flex items-center justify-between">
          <div>
            <span className="eyebrow">Account</span>
            <h1 className="mt-1 text-2xl sm:text-3xl font-semibold tracking-tight">Your account</h1>
          </div>
          <button
            onClick={signOut}
            className="text-sm transition-colors"
            style={{ color: "var(--muted)" }}
          >
            Sign out
          </button>
        </div>
        <p className="mt-1 text-sm" style={{ color: "var(--muted-dim)" }}>
          {user.email}
        </p>

        <h2 className="mt-10 eyebrow">Your products</h2>
        {entitlements.length === 0 ? (
          <p className="mt-4 text-sm" style={{ color: "var(--muted-dim)" }}>
            No products yet. See{" "}
            <a href="/pricing" className="underline">
              pricing
            </a>
            .
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {entitlements.map((e) => (
              <EntitlementCard key={e.id} entitlement={e} />
            ))}
          </div>
        )}

        <p className="mt-10 text-sm" style={{ color: "var(--muted-dim)" }}>
          Need help? Contact{" "}
          <a href="mailto:nitedsp@outlook.com" className="underline">
            nitedsp@outlook.com
          </a>
          .
        </p>
      </div>
    </div>
  );
}
