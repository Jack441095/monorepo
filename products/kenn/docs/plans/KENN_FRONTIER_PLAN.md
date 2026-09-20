# Getting KENN to Frontier Level Inside Live

**Roadmap · Shenrendao AI · KENN Mix Assistant**

KENN already reasons, retrieves and drives Ableton. What it does not yet do is answer fast
enough to feel like a collaborator, or present one coherent product across the browser and the
plug-in. This is the plan to close both gaps — AU and VST3 together.

| | |
|---|---|
| **Target** | Frontier-model intelligence |
| **Inference** | Hybrid local + GPU |
| **Drafted** | 15 September 2026 |
| **Baseline** | `develop` @ 16d8d09 |

### Measured baseline

| Metric | Value | Source |
|---|---:|---|
| Plan one step | **10.2 s** | Measured, real Live task |
| Planner p95 | **12.0 s** | Qwen3-4b, 66 samples |
| Tool surface | **65** | MCP tools already wired |
| Test suite | **1214** | Passing |

---

## 01 · The diagnosis

You asked whether the plug-in needs rebuilding because it is still on the old UX. **It does not —
and a rebuild would not help.** That is the single most important fact in this plan.

**Three front-ends.** KENN is not one product with one skin. It is three codebases that happen to
share a server: the web UX (a bundled Vue app), the JUCE plug-in (hand-written C++ widgets), and
the Live remote script. They diverge independently, and nothing keeps them in step.

**Why the rebuild won't work.** The plug-in editor is built entirely from native JUCE components —
`Label`, `TextButton`, `TextEditor`, `ComboBox`, `Slider`. There is no webview anywhere in it, and
the build explicitly compiles the browser out with `JUCE_WEB_BROWSER=0`. Recompiling reproduces the
same hand-written UI byte for byte.

The screenshot in question is the *server's* web UX in a browser. The plug-in has never rendered
that interface and cannot, as currently configured.

**The real choice.** Either maintain two designs forever, or make the plug-in host the web UX in a
webview and ship one front-end twice. Recommendation: the webview. It collapses three surfaces into
two, and every UX improvement then lands in Live for free.

**Good news.** AU is already configured — `FORMATS VST3 AU` is in the build today. AU is a
packaging, signing and validation problem, not a porting one.

---

## 02 · The latency gap

Frontier feel is mostly a latency property. A model that answers in ten seconds reads as a batch
job no matter how good the answer is. This is the budget to design against.

**Today — one planned step: 10,186 ms**

**Target — question to applied change: 1,500 ms**

| Stage | Budget |
|---|---:|
| Intent + route (local small model) | 80 ms |
| Live snapshot (batched OSC) | 120 ms |
| Retrieval (warm) | 60 ms |
| Plan + reason (remote GPU) | 900 ms |
| Confirm + apply to Live | 340 ms |
| **Total** | **1,500 ms** |

The target is 14.7% of today's measured time. First token on screen is a separate, harder
commitment — **300 ms**, met by streaming, not by waiting for the plan to finish.

> ### Where the time actually goes
>
> The 10.2 s is not all model time. Profiling a warm turn found the retrieval index being
> re-validated on every request — a SHA-256 over 10 MB of artifacts plus a re-parse of 2,808 chunk
> records, 89 ms a call, several calls per answer. On a cache-hit answer that was 99% of the wall
> time.
>
> That one is already fixed (89.5 ms → 0.07 ms). The lesson generalises: **measure before buying a
> bigger model.** Some of the gap is arithmetic, not intelligence.

---

## 03 · Four phases

Sequenced by dependency, not by appetite. Each phase has an exit criterion that can be checked by
running something, so "done" is never a judgement call.

### Phase 0 — One front-end, two shells
*2–3 weeks*

Stop maintaining two designs. This unblocks every visual improvement for the rest of the plan.

- Flip `JUCE_WEB_BROWSER=1` and link `juce_gui_extra`; replace the editor body with a
  `juce::WebBrowserComponent` pointed at the local KENN server.
- Keep a native fallback panel for when the server is not running — the plug-in must never show a
  blank webview inside someone's session.
- Move the endpoint/session/connection controls into the web UX so there is one place to configure
  KENN.
- Bridge parameter changes both ways (target LUFS, mode) so the host automation lane and the web UI
  never disagree.
- Fix the confirmation-gate-reads-as-failure bug before anyone else sees it.

**Exit criterion.** Open KENN in Live 12 as AU and as VST3; both render the same interface as the
browser, and a device insertion can be proposed, confirmed and undone from inside the plug-in
window.

### Phase 1 — Make it feel instant
*3–4 weeks*

Hit the 1,500 ms budget above. Mostly engineering, not model work.

- Stream every answer. First token at 300 ms matters more than total time — the plug-in currently
  waits for a complete response before showing anything.
- Run retrieval and the Live snapshot concurrently with intent routing instead of in series.
- Continue the OSC batching pass — independent reads should never serialise. Two round trips were
  being discarded outright in the connection probe.
- Put a latency budget assertion in the qualification suite so a regression fails CI rather than
  being noticed in a session.
- Instrument per-stage timings end to end and publish them in the receipt, so "KENN feels slow"
  becomes a number.

**Exit criterion.** `KENN_REAL_LIVE_ASSISTANT_TASK.json` records p95 planning latency under
1,500 ms and first-token under 300 ms across the full task set.

### Phase 2 — Frontier-level reasoning
*5–7 weeks*

The hybrid split: a small local model for anything that must be instant or work offline, the big
model for anything that must be right.

- **Local tier** — intent classification, command parsing, safety gating, offline fallback. Must
  survive the network being gone mid-session.
- **Remote tier** — mix diagnosis, multi-step planning, arrangement reasoning, running on the GPU
  host.
- Write the routing policy as code with an explicit degradation ladder, not as scattered
  conditionals. Every request must have a defined answer to "what happens if the GPU is unreachable
  right now".
- Replace the per-task model sprawl in `.env` with one declared model map, and warm every model in
  it — the keep-alive currently warms only the rewrite model.
- Feed the session snapshot into the prompt as structured state, not prose. KENN's advantage over a
  generic chatbot is that it can see the actual set.
- Move from single confirmation-gated steps to multi-step plans with one approval for the whole
  plan.

**Exit criterion.** A blind A/B against a frontier API on the existing hard-case and holdout sets,
scored by the current adjudication harness, with no statistically significant quality gap — at the
latency budget from Phase 1.

### Phase 3 — Ship it as real plug-ins
*3–4 weeks*

Everything between "builds on your machine" and "someone else installs it".

- Fix the universal-binary option — it is currently a no-op, so the architecture flag does nothing
  whichever way it is set.
- Run `pluginval` at strictness 10 and `auval` in CI, on both formats, as a merge gate.
- Developer ID signing, hardened runtime, notarisation and stapling for the AU and VST3 bundles.
- Build an installer that places both formats correctly and installs the AbletonOSC remote script
  in one step.
- Decide the Windows position explicitly — VST3 only, and what that costs. It is a real decision,
  not an oversight to discover later.

**Exit criterion.** A notarised installer on a clean machine with no developer tools produces a
working KENN in Live 12, both formats, with no Gatekeeper prompt.

---

## 04 · AU and VST3, side by side

The formats differ in ways that bite late. Worth settling now.

| Concern | VST3 | Audio Unit | Position |
|---|---|---|---|
| Build config | `FORMATS VST3` | `FORMATS AU` | Both already declared. No porting work. |
| Validation | pluginval | auval + pluginval | AU validation is stricter and non-negotiable — Live will refuse a plug-in that fails auval. |
| Webview host | WKWebView | WKWebView | Same on macOS. Windows VST3 would add WebView2 as a second runtime to support. |
| Install path | `~/Library/Audio/Plug-Ins/VST3` | `~/Library/Audio/Plug-Ins/Components` | Installer handles both; currently a manual copy. |
| Architecture | arm64 + x86_64 | arm64 + x86_64 | Universal for shipping. Note the x86_64 toolchain on this machine is currently broken, so universal builds fail locally. |
| State | Shared `AudioProcessorValueTreeState` | Shared `AudioProcessorValueTreeState` | Session recall must survive a Live project reopen in either format. |

---

## 05 · Found on the way in

Concrete defects turned up while investigating. The first one is visible in the reported screenshot
and undermines trust more than any missing feature.

### OPEN · A working safety gate renders as "Failed"

The server returns `{"ok": false, "error": "Explicit confirmation is required…"}` for the normal,
expected confirmation gate. The web UI treats any `ok: false` as a thrown error, sets
`actionStatus = "error"`, and paints a red **Failed** badge — on a card that is simultaneously
offering an "Apply to Live 12" button.

KENN is behaving correctly and telling the user it broke. Give the confirmation gate its own status
distinct from failure.

> `apps/backend/src/kenn/core/clip_audition_service.py:268` · `clip_duplication_service.py:208` · `clip_rename_service.py:120`

### OPEN · The universal-binary option does nothing

The block force-sets `CMAKE_OSX_ARCHITECTURES` to `arm64;x86_64`, then the `KENN_BUILD_UNIVERSAL`
branches below try to set the same cache variable *without* `FORCE`. CMake ignores a non-forced set
on an existing cache entry, so both branches are dead and the build is always universal regardless
of the flag.

Worth fixing before Phase 3 — a native-arch build is roughly half the compile time, and x86_64
currently fails on this machine anyway.

> `plugins/kenn-vst3-au/CMakeLists.txt:5–14` (uncommitted working-tree change)

### OPEN · Duplicate keys in .env silently pick the slow model

`load_env()` is first-wins, and both `AUDIO_TOO_LLM_MODEL` and `AUDIO_TOO_LLM_TIMEOUT` appear
twice. KENN runs `qwen2.5-coder:7b` at a 60 s timeout; the `qwen2.5:0.5b` / 15 s lines below are
dead. A code-tuned model is also an odd choice for audio-engineering prose.

> `.env:4–7`

### FIXED · Index re-validated on every request

Memoised against a size/mtime fingerprint. Cache-hit answers went from 71–90 ms to under 1 ms;
first answer from 1,102 ms to 82 ms. Four regression tests added, full suite green.

> `apps/backend/src/kenn/retrieval/index_store.py` · `apps/backend/src/kenn/tests/test_index_store_validation_cache.py`

### FIXED · Connection probe threw away two OSC round trips

`probe_connection()` queried track count and names, then immediately overwrote both results with a
second bypassing pair. Up to 1.5 s wasted per Test-button click against a stalled Live. Removed,
and the surviving pair batched into one exchange.

> `apps/backend/src/kenn/ableton_osc_bridge.py`

---

## 06 · Risks worth naming now

**Webview in a DAW.** A webview inside a plug-in editor is a real memory and startup cost,
multiplied by every instance in a set. Budget a hard instance cap and a lightweight idle state, and
test with twenty instances open before committing.

**Remote inference in a studio.** Hybrid means KENN is partly a network service. Sessions happen on
hotel wifi and in rooms with no internet. The degradation ladder is not a nice-to-have — decide now
what KENN still does with the GPU unreachable, and make that the tested default rather than the sad
path.

**Audio thread discipline.** Nothing added in this plan may touch the audio thread. The existing
TSan stress target is the guard; keep it in CI as the plug-in grows.

**Quality regression.** Hybrid routing makes answer quality depend on which tier served it. Tag
every answer with its tier in the receipt, or the evaluation numbers stop meaning anything.

---

## 07 · What I'd do first

In order, before committing to the full plan.

1. **This week.** Fix the "Failed" badge. It is small, it is visible, and it makes a correct system
   look broken.
2. **Then.** Spike the webview editor behind a build flag. One day of work answers the biggest open
   question in the plan — whether one front-end across browser and plug-in is actually viable —
   before anything is scheduled around it.
3. **Then.** Instrument the full turn end to end. Publish per-stage timings. Only then decide how
   much of the 10.2 s is the model and how much is us.

---

*Baselines measured 15 September 2026 on `develop` @ 16d8d09.*
