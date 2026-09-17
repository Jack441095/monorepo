import type { Metadata } from "next";
import type { ReactNode } from "react";

// app/account/page.tsx is a client component and so cannot export metadata of
// its own. This layout supplies it: a real title instead of the inherited
// site default, plus a page-level noindex to sit alongside the robots.txt
// disallow (app/robots.ts) — the account area is session-gated and has no
// public search value.
export const metadata: Metadata = {
  title: "Account",
  description: "Sign in to manage your NITE DSP licences and downloads.",
  robots: { index: false, follow: false },
};

export default function AccountLayout({ children }: { children: ReactNode }) {
  return children;
}
