import type { Metadata } from "next";
import type { ReactNode } from "react";

// Sign-in link handling is a transient, token-bearing route: never indexed,
// and never a landing page. Client component, so metadata lives here.
export const metadata: Metadata = {
  title: "Sign In",
  description: "Completing your NITE DSP sign-in.",
  robots: { index: false, follow: false },
};

export default function AuthLayout({ children }: { children: ReactNode }) {
  return children;
}
