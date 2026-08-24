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
    return <p className="text-sm" style={{ color: "var(--state-error)" }}>This sign-in link is invalid or has expired.</p>;
  }
  return <p className="text-sm" style={{ color: "var(--muted-dim)" }}>Signing you in…</p>;
}

export default function VerifyPage() {
  return (
    <div className="section text-center">
      <div className="mx-auto px-6" style={{ maxWidth: "26rem" }}>
        <Suspense fallback={<p className="text-sm" style={{ color: "var(--muted-dim)" }}>Signing you in…</p>}>
          <VerifyInner />
        </Suspense>
      </div>
    </div>
  );
}
