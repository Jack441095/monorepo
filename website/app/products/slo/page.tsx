import { redirect } from "next/navigation";

// Naming unification (docs/NITE_DSP_WEBSITE_COMMERCIAL_ARCHITECTURE_V1.md §1):
// the display name is SLO; the legacy slug stays reachable via redirect so old
// links and search equity land on the canonical product page.
export default function SloRedirect() {
  redirect("/products/smart-sample-manager");
}
