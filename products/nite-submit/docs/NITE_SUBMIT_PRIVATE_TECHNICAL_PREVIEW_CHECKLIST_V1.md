# NITE Submit — Private Technical Preview Checklist V1

**Build:** 0.2.0 · PRIVATE BETA RC1
**Audience:** Owner + 1–3 trusted private testers
**Scope:** Local technical preview only; not public/commercial release

## Handoff gate

- [x] Build created and present: `artifacts/Submit-0.2.0-macOS.app` (fresh
  release artifact verified)
- [x] Tester ZIP exists: `artifacts/Submit-0.2.0-macOS.zip`
- [x] ZIP checksum recorded in the handoff and release manifest:
  `33b9ad1f2956f45fa54d3884a131f266d334a8c8ed3bf2117fa0fe294fd24817`
- [x] ZIP integrity test passes (`unzip -tq`)
- [x] App bundle verification passes
- [x] App launches locally from the current artifact
- [x] First core workflow has packaged-build evidence in
  `NITE_SUBMIT_RELEASE_REPORT.md`: load PDF → review/edit → approve → create
  byte-identical renamed copy
- [x] Known issues and signing limitation are recorded
- [x] Tester instructions attached:
  `docs/customer/NITE_SUBMIT_PRIVATE_TECHNICAL_PREVIEW_V1.md`
- [x] Privacy-safe feedback template attached:
  `docs/NITE_SUBMIT_PRIVATE_FEEDBACK_TEMPLATE_V1.md`

## Validation receipt

- `swift run nitesubmit-tests` → **247/247 checks passed**
- `tools/verify_app_bundle.sh artifacts/Submit-0.2.0-macOS.app` → **PASS**
- `unzip -tq artifacts/Submit-0.2.0-macOS.zip` → **PASS**
- App UI smoke → **PASS**; the real Berklee sample produced one regular,
  byte-identical result under `test_results/app_ui_smoke_current/`; the source
  was not renamed, uploaded, or modified
- The release manifest is regenerated after the verified commit and records a
  clean private-beta source revision; the artifact remains ad-hoc signed and
  not notarised.

## Owner send gate

Before sending, the owner must attach the exact ZIP and this README, keep the
distribution to the named trusted testers, and tell each tester to verify the
checksum before opening. Do not publish the archive, enable a public download,
run production deployment, or describe this as notarised or commercially ready.
