# Smart Sample Manager — Beta Troubleshooting

Phase 5.5, Section 41. Never suggests installing Homebrew, a dylib, or any developer tool as a
customer fix -- if a customer needs to install a developer dependency to run the product, that's
a packaging bug (see `docs/RUNTIME_DEPENDENCY_STRATEGY.md`, `docs/CLEAN_MACHINE_VALIDATION.md`),
not a support answer.

## Plugin not appearing in my DAW

Rescan your plugin folders in your DAW's preferences. If it still doesn't appear, confirm the
installer completed successfully and that your DAW supports the format you installed (VST3/AU).

## Activation failure

Confirm you're using the exact license key from your account page, and that you have an active
internet connection for the first activation (subsequent offline use is supported, see below).
If you've already activated on your maximum number of devices, deactivate one from your account
page first.

## Library scan issues

Very large libraries take longer on first scan -- this is expected. If a scan appears stuck,
check whether it's still making progress (file count increasing) before assuming it's frozen.

## Missing waveform preview

Confirm the sample file itself plays correctly outside the plugin -- a corrupted or
unsupported-format file may fail analysis while the rest of your library scans normally
(Smart Sample Manager is designed to skip and report bad files, not stop the whole scan --
`docs/TEST_COVERAGE_AUDIT.md`'s malformed-audio handling).

## "Find Similar" unavailable

This requires your library to have been scanned/analyzed first. If scanning hasn't completed
yet, wait for it to finish.

## Model load failure

This would indicate a packaging problem -- the ML model ships bundled with the plugin and should
never require a separate download or install. If you see this, please report it via the feedback
route in your account/download email with your OS version and Smart Sample Manager version.

## Database/cache issues

Smart Sample Manager automatically detects and rebuilds a corrupted local cache without losing
your source audio files (`docs/TEST_COVERAGE_AUDIT.md`'s `TestResilience` coverage) -- if you
see repeated cache-rebuild messages, this indicates something is corrupting the cache
repeatedly, which is worth reporting.

## Download issues

Download links expire after a short time for security -- if a link doesn't work, go back to your
account page and request a fresh one.

## Offline license behavior

Once activated, Smart Sample Manager continues to work offline for up to 14 days without
re-checking with the license server, then attempts to re-validate the next time you're online.
It will not suddenly stop working mid-session due to a temporary internet outage.
