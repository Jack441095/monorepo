# KENN Desktop Companion

Native macOS shell for the local KENN server. It embeds the existing KENN chat,
Mix Review, stem upload, AutoMix status, and download workflows in one desktop
window, so those workflows can be exercised without a DAW.

## Build and run

From the repository root:

```bash
studio/kenn/desktop_companion/build_macos_app.sh
open "studio/kenn/desktop_companion/dist/KENN Desktop Companion.app"
```

The app connects to an already-running `http://127.0.0.1:8090` server or starts
`studio/kenn/kenn/server.py` itself. It also starts one local AutoMix worker, so
multi-stem uploads made in the companion can progress to a render. Launch it from
this repository; for another checkout, pass `--repo-root=/absolute/path/to/Audio_Too`
to the executable or set `KENN_REPO_ROOT`.

The companion deliberately does not replace the VST3/AU: DAW-only bus metering,
parameter automation, and target apply/undo stay in the plug-in. The desktop app
is the direct test surface for chat, WAV file selection, Mix Review, AutoMix, job
polling, and downloads.
