import { LegalPage } from "@/lib/legal";

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy">
      <p>
        NITE DSP uses your email address to send a magic sign-in link and to operate your account.
        The account and licensing service stores purchase and entitlement records, license keys, and
        device identifiers used to manage activations.
      </p>
      <p>
        SLO analyses samples locally on your computer. Website account, payment,
        licensing, and download requests are separate from that local analysis. This product review
        found no website feature that uploads sample audio or library contents.
      </p>
      <p>
        Payment processing is designed to use Paddle as Merchant of Record. Transactional email can
        be delivered through Resend when that service is configured. The service is hosted on Railway.
        This page does not currently describe analytics, advertising cookies, retention periods, or
        deletion procedures because those operational details require owner and legal confirmation.
      </p>
      <p>
        We do not sell customer data. For privacy questions, contact
        {" "}<a href="mailto:nitedsp@outlook.com" className="underline">nitedsp@outlook.com</a>.
      </p>
    </LegalPage>
  );
}
