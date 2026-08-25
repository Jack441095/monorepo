import { LegalPage } from "@/lib/legal";

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy">
      <p>
        NITE Submit does not require an account and processes assignment PDFs locally on your Mac.
        If you use a NITE DSP account, we use your email address to send a magic sign-in link and
        operate account, purchase, entitlement, and licence services.
      </p>
      <p>
        SLO analyses samples locally on your computer. Website account, payment, licensing, and
        download requests are separate from local product analysis. NITE DSP does not need to upload
        assignment documents, sample audio, or library contents for these local workflows.
      </p>
      <p>
        Payment processing is designed to use Paddle as Merchant of Record. Transactional email can
        be delivered through Resend when configured. The service is hosted on Railway. This page is
        still a launch draft: analytics, advertising cookies, retention periods, deletion procedures,
        and the final legal entity details require owner and legal confirmation before paid checkout.
      </p>
      <p>
        We do not sell customer data. For privacy questions, contact
        {" "}<a href="mailto:support@nitedsp.co.uk" className="underline">support@nitedsp.co.uk</a>.
      </p>
    </LegalPage>
  );
}
