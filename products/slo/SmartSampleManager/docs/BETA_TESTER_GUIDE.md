# Smart Sample Manager — Private Beta Tester Guide

Phase 5.5, Section 40. Written ahead of an actual beta distribution -- ready the moment
`docs/PRIVATE_BETA_RC.md`'s gate passes. Only covers functionality actually verified to exist
and pass in this project's test suites; nothing here is aspirational.

## 1. Create/sign into your NITE DSP account

Go to your account page and enter your email. You'll get a sign-in link (no password needed) --
click it to finish signing in.

## 2. Access your beta entitlement

Once signed in, your account page lists the products you have access to. Smart Sample Manager
should appear there marked as beta access, with an expiry date if one applies.

## 3. Download

From your account, download the macOS installer for Smart Sample Manager.

## 4. Install

Run the installer and follow the prompts. (Installer details will be finalized once macOS
signing/notarization is complete -- see `docs/MACOS_SIGNING_VALIDATION.md`.)

## 5. Activate

Open Smart Sample Manager (as a plugin in your DAW, or as the standalone app) and enter the
license key from your account page when prompted. Activation works offline after the first
successful check -- see "Offline use" below.

## 6. Add a sample library

Point Smart Sample Manager at a folder of audio samples. It will scan and analyze them locally
-- nothing is uploaded (see `docs/SECURITY_MODEL.md`'s privacy notes).

## 7. Indexing

The first scan of a library builds an internal index (embeddings + a similarity search
structure). Subsequent scans of the same library are faster, since only new/changed files are
re-analyzed.

## 8. Searching your library

Browse your indexed samples directly in the plugin UI.

## 9. Find Similar

Select a sample and use Find Similar to surface acoustically similar sounds from your library,
based on audio content -- not filenames or tags.

## 10. Visual map

The library can also be viewed as a 2D similarity map (UMAP projection), where visually nearby
samples sound similar.

## 11. Ableton workflow

Smart Sample Manager writes XMP metadata compatible with Ableton Live's sample browser tagging,
so reorganized/tagged samples remain organized inside Ableton's own browser too. This is a
compatibility feature, not an official Ableton partnership or integration.

## 12. Deactivation

To move your license to a new machine, deactivate it from your account page (or from within the
plugin, if exposed there) before activating on the new machine -- this frees up an activation
slot.

## 13. Reporting problems

See `docs/BETA_TROUBLESHOOTING.md` first. If that doesn't resolve it, use the feedback route in
your account/download email -- a single support contact, not a community platform
(Section 64).
