"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api";

function VerifyInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<"pending" | "error">(token ? "pending" : "error");

  useEffect(() => {
    if (!token) return;
    apiFetch("/auth/verify", { method: "POST", body: JSON.stringify({ token }) }).then((res) => {
      if (res.ok) {
        router.replace("/account");
      } else {
        setStatus("error");
      }
    });
  }, [token, router]);

  if (status === "error") {
    return (
      <div className="p-6 border border-brand-red bg-[rgba(239,68,68,0.05)] rounded-md text-sm text-brand-red font-mono">
        This sign-in link is invalid or has expired.
      </div>
    );
  }
  return (
    <div className="p-6 border border-border bg-[#0D1322] rounded-md text-sm text-brand-blue-bright font-mono animate-pulse">
      Signing you in…
    </div>
  );
}

export default function VerifyPage() {
  return (
    <div className="section">
      <div className="mx-auto px-6 max-w-[28rem] text-center">
        <Suspense fallback={
          <div className="p-6 border border-border bg-[#0D1322] rounded-md text-sm text-muted-dim font-mono">
            Loading verification…
          </div>
        }>
          <VerifyInner />
        </Suspense>
      </div>
    </div>
  );
}
