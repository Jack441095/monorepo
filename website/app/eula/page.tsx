import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import { LegalPage } from "@/lib/legal";

export const metadata: Metadata = pageMetadata({
  title: "End User License Agreement",
  description:
    "Licence terms for NITE DSP software: what a perpetual licence grants, device limits, and restrictions.",
  path: "/eula",
});

export default function EulaPage() {
  return (
    <LegalPage title="End User License Agreement">
      <p>
        Each NITE DSP product license grants a perpetual, non-exclusive,
        non-transferable right to install and use the software on up to
        the number of devices specified by your license tier
        (currently 3 for SLO), for as long as you own a
        valid license.
      </p>
      <p>
        You may not redistribute, sublicense, reverse-engineer, or resell
        the software. NITE DSP may revoke a license found to be
        fraudulently obtained or in breach of these terms.
      </p>
    </LegalPage>
  );
}
