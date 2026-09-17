import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import { LegalPage } from "@/lib/legal";

export const metadata: Metadata = pageMetadata({
  title: "Refund Policy",
  description:
    "Refund terms for NITE DSP purchases, including the 14-day window and how refunds are processed.",
  path: "/refund-policy",
});

export default function RefundPolicyPage() {
  return (
    <LegalPage title="Refund Policy">
      <p>
        For the planned NITE Submit paid experiment, contact support
        within 14 days of purchase for a full refund, no questions asked.
      </p>
      <p>
        Refunds will be processed through the Merchant of Record and typically
        appear within 5-10 business days, depending on your payment
        method. Refunding a purchase revokes the associated license.
      </p>
    </LegalPage>
  );
}
