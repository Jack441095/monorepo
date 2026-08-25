"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

/**
 * Thin entry point into the existing download experience. The real
 * entitlement + build-download UI lives on /account (EntitlementCard →
 * /downloads/latest). This component never duplicates it: signed-in users
 * are routed straight there; everyone else gets sign-in or beta-request.
 */
export function DownloadRouter() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;
    apiFetch("/auth/me")
      .then((res) => {
        if (cancelled) return;
        if (res.ok) {
          router.replace("/account");
        } else {
          setChecking(false);
        }
      })
      .catch(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (checking) {
    return (
      <div className="surface-card p-8 rounded-lg border border-border/40 text-center">
        <p className="text-sm text-muted" role="status">
          Checking your account…
        </p>
      </div>
    );
  }

  return (
    <div className="surface-card p-8 rounded-lg border border-border/40 text-center">
      <h2 className="text-lg font-semibold text-foreground">Sign in to download.</h2>
      <p className="mt-3 text-sm text-muted leading-relaxed">
        Your licences and platform builds live in your account area.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <Link href="/account" className="btn-primary">
          Sign in
        </Link>
        <Link href="/beta" className="btn-secondary">
          Request beta access
        </Link>
      </div>
    </div>
  );
}
