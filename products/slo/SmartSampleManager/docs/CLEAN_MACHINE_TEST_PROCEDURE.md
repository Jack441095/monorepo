# Clean Machine Test Procedure

Phase 5.5, Sections 37-40, 60-61. Exact steps for when a genuinely clean macOS machine/VM
becomes available. This document does NOT claim the test has been passed -- see
`docs/CLEAN_MACHINE_VALIDATION.md` for current (BLOCKED) status.

## Before you start

- **Get a NITE DSP account with an entitlement first.** An admin needs to issue you a beta
  license via `POST /admin/entitlements/issue` before step 1 -- without this, you have nothing
  to sign in with or download. Ask whoever is running this test to confirm your email has been
  issued one.
- **Know the URLs**: sign-in / account / downloads all happen at `https://nitedsp.co.uk/account`
  (once hosted -- `docs/RAILWAY_DEPLOYMENT.md`). Until then, substitute the local staging URL
  you were given.
- **The identity codes "NDSP" and "AtSm"** referenced below are Smart Sample Manager's
  plugin-manufacturer and plugin codes (`docs/FINAL_PRODUCT_IDENTITY.md`) -- they're how your
  DAW identifies this specific plugin. You don't need to understand them, just recognize them
  in `auval`'s output as confirmation it found the right plugin.

## Prerequisites for the machine itself

- Never had Homebrew installed (no `/opt/homebrew` or `/usr/local/Cellar`)
- Never had this source repository cloned/built on it
- No manually-installed ONNX Runtime, TagLib, or libsodium via any other means (MacPorts, manual
  `.pkg`, etc.)
- A real signed, notarized installer for Smart Sample Manager (not a dev build copied from the
  build folder -- Section 40's "test real user paths")

## Procedure

```text
1. DOWNLOAD BETA INSTALLER
   -- sign in at https://nitedsp.co.uk/account (magic link, no password), find Smart Sample
      Manager under "Your products", click download. Not scp'd from a dev machine.

2. INSTALL
   -- run the installer as a real user would; note any Gatekeeper prompt text verbatim

3. VERIFY GATEKEEPER
   -- in Terminal: `spctl --assess --type execute "<path to app/plugin>"`
      (e.g. `spctl --assess --type execute "/Applications/Smart Sample Manager.app"`)
      should report "accepted", not rejected

4. VERIFY AU SCAN
   -- open Logic Pro (or in Terminal: `auval -v aumf NDSP AtSm`), confirm the plugin is found
      and validates without the "NDSP"/"AtSm" codes showing as a different/missing plugin

5. VERIFY VST3 SCAN
   -- open a VST3 host (Ableton Live, Reaper), rescan plugins, confirm Smart Sample Manager
      appears and loads

6. LAUNCH STANDALONE
   -- in Terminal: `open "/Applications/Smart Sample Manager.app"`, confirm no crash, no
      missing-library dialog

7. SIGN IN / ACTIVATE
   -- inside the plugin/app, sign in with the same account from step 1, then enter the license
      key shown on your account page to activate

8. ADD SAMPLE LIBRARY
   -- point at a real folder of audio files

9. SCAN
   -- confirm scanning completes and reports a sane sample count

10. PREVIEW
    -- confirm audio preview/playback works

11. FIND SIMILAR
    -- select a sample, confirm results return

12. VISUAL MAP
    -- confirm the UMAP similarity map renders

13. ABLETON WORKFLOW WHERE AVAILABLE
    -- confirm XMP tags written by Smart Sample Manager are visible in Ableton's own browser

14. SAVE DAW PROJECT
    -- save a project referencing the plugin

15. QUIT DAW

16. REOPEN
    -- confirm the DAW reopens the project with the plugin correctly recalled (not shown as
       missing/offline)

17. DISCONNECT INTERNET

18. VERIFY OFFLINE LICENSE
    -- confirm the plugin still loads/functions with no network connection, per the 14-day
       offline grace period (docs/LICENSING_IMPLEMENTATION.md)
```

## Recording results

Use `docs/DAW_VALIDATION_MATRIX.md` for the DAW-specific rows (steps 4-5, 13-16). Record exact
commands run and their output for steps 3-4 (Gatekeeper/AU validation) as evidence, not just a
pass/fail checkbox -- consistent with Section 31's "record commands/results."

## Automatable pre-check (non-destructive)

`scripts/clean_machine_acceptance.py` (Phase 5.5, this document's companion) checks the
mechanical preconditions (bundle exists, dependency linkage, code-sign status, version) that can
be verified without a human driving a DAW -- run it first to catch an obviously broken artifact
before spending time on the manual DAW-workflow steps above. This script has no dependency on
the rest of the repository being cloned -- copy it to the clean machine alongside
`check_homebrew_dependencies.py` (it calls that script internally) and run:

```bash
python3 clean_machine_acceptance.py "/Applications/Smart Sample Manager.app"
```

using an absolute path to the installed bundle. Requires Python 3 (preinstalled on macOS) --
nothing else.
