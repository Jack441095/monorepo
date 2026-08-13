import { LegalPage } from "@/lib/legal";

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy">
      <p>
        NITE DSP collects the minimum information needed to operate an
        account and license system: your email address, purchase records,
        and device identifiers used for license activation.
      </p>
      <p>
        We do not sell customer data. Audio files and sample libraries
        processed by our plugins are never uploaded -- all analysis runs
        locally on your machine.
      </p>
      <p>
        A real, lawyer-reviewed privacy policy covering UK/EU data
        protection obligations (GDPR) will replace this placeholder before
        public launch.
      </p>
    </LegalPage>
  );
}
