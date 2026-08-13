import { LegalPage } from "@/lib/legal";

export default function TermsPage() {
  return (
    <LegalPage title="Terms of Service">
      <p>
        By using the NITE DSP website or purchasing NITE DSP products, you
        agree to use the software and services in accordance with the
        applicable license terms (see our EULA) and not to attempt to
        circumvent license activation or resell licenses outside of an
        authorized channel.
      </p>
      <p>
        Purchases are processed by a Merchant of Record on our behalf, who
        handles payment processing and applicable sales tax.
      </p>
    </LegalPage>
  );
}
