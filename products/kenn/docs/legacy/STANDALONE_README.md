# KENN collaboration package

This directory is the imported standalone KENN package inside the canonical
NITE DSP monorepo. Its original standalone layout is preserved temporarily so
the frontend, SLO integration, plugin, Ableton integrations, and backend can
be reviewed together before shared runtime modules are reconciled.

The canonical Git repository is now `Nite-DSP/monorepo`. Do not treat this
directory as a second repository or push changes to the archived standalone
checkout without an explicit promotion decision.

KENN is an audio-engineering assistant with an Ableton Live specialty. This
package retains the original standalone structure while migration work is
reviewed on the monorepo integration branch.

Start with [`GETTING_STARTED.md`](GETTING_STARTED.md), use
[`PRODUCT_MAP.md`](PRODUCT_MAP.md) to find each subsystem, and follow
[`CONTRIBUTING.md`](CONTRIBUTING.md) when collaborating through GitHub.

**Status: pre-beta, audited.** See `docs/KENN_CURRENT_STATE_SUMMARY.md`,
`docs/KENN_BETA_GAP_MATRIX.md`, and `docs/KNOWN_ISSUES.md` for the full audit.
In short:

- **`apps/legacy-web/`** -- the chat/dashboard front-end `apps/backend/src/kenn/server.py` serves
  (`STATIC_ROOT`). Integrated from a colleague's redesign; nav links to a
  larger multi-product business dashboard that isn't part of this repo
  were removed (Mix Review/AutoMix/AudioGen are already inline widgets on
  this same page). Live-verified: real streamed, cited chat answers
  through the exact request shape this UI sends.
- **`packages/mix-review/`** -- standalone and KENN-owned
  (`packages/mix-review/core/local_engine.py`), no external runtime dependency.
  Measures a bounded set of fault families (clipping, headroom, silence/
  truncation, channel imbalance, phase/polarity & mono compatibility, DC
  offset, an approximate loudness estimate) with unit-test coverage
  against synthetic fixtures. Not yet through human listening review or a
  real-mix benchmark.
- **`packages/chat/`, `apps/backend/src/kenn/`** -- chat now answers real, in-scope
  mix-engineering questions with cited sources, backed by a real
  BM25-indexed knowledge base (232 approved notes under
  `apps/backend/src/kenn/Training_Data_Notes/`, generated index not committed --
  run `python3 apps/backend/src/kenn/main.py build` after cloning). Semantic
  (embedding) search isn't active yet (missing a model download). The
  deeper `apps/backend/src/kenn/server.py` and `core/tool_registry.py` entry points
  (Ableton control, specialist tools) remain blocked by ~15 missing
  sibling modules from the old monorepo -- not part of this beta.
- **`packages/automix/`** -- disabled for beta. Its safety boundary (approval gate,
  receipt contract) is KENN-owned and intact, but the render engine it calls
  is external and absent.
- **`plugins/kenn-vst3-au/`** -- targets both VST3 and Audio Unit from one JUCE
  target. Builds clean (Xcode Command Line Tools alone, no full Xcode
  needed). Its real-time metering (peak, RMS, correlation, width, crest,
  clipped samples) is self-contained C++ with zero Python/network
  dependency, and its concurrency is tool-verified data-race-free
  (ThreadSanitizer). Deeper features ("Ask KENN," Mix Review upload,
  AutoMix handoff) call `apps/backend/src/kenn/server.py` -- now working, and the
  compiled plugin binary was live-verified reaching it and getting a real,
  cited answer. Not yet loaded inside an actual DAW.
- **`apps/desktop/macos/`** -- builds cleanly, but its first-run flow
  requires locating an external `Audio_Too` repository by design; blocked
  for beta.

Do not treat this README, any prior report, or any filename as proof a
capability works. See `docs/KENN_BETA_READINESS_REPORT.md` for the current
recommendation.
