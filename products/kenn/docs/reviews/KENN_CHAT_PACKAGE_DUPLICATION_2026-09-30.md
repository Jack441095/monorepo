# KENN chat package duplication: which copy is canonical

**Checked:** 2026-09-30 · **Status:** analysis only, for Jack (Track F row F4). Nothing removed, moved or edited.

Track F4 says there are two `chat` packages and that tooling loads the wrong one under the bare
name `app`. All three parts of that are true, and the situation is worse than the row suggests:
the two copies are not in sync, CI only runs the smaller one, and several documents already point
at `chat/` for files that only exist in `packages/chat/`.

**Recommendation: `packages/chat/` is canonical and `chat/` should be removed.** That contradicts
what CI runs today, so the CI flip is step 1 of the removal plan and it is the one step that can
turn the build red. The alternative (keep `chat/`, port 41 tests and 3 endpoints forward) is a
bigger job and leaves the product without the surface its own docs promise.

## The three claims

| Claim | Verdict | Measured |
|---|---|---|
| (a) Both copies exist | true | `products/kenn/chat/` = 11 files; `products/kenn/packages/chat/` = 23 files |
| (b) Each has `app.py`, `eval_runner.py`, `index_runtime.py` | true | All three present in both. `index_runtime.py` is byte-identical (SHA-256 `3fed593f22d4…`); `app.py` and `eval_runner.py` are not |
| (c) Something loads the wrong one under the bare name `app` | true, and it is worse than a wrong load — two copies of `app` can be collected in one pytest process and it refuses to run at all | See "How the wrong copy loads" |

## Measured facts

### File inventory

`products/kenn/chat/`, 11 files, all tracked:

```
    538  .env.example                 883  Dockerfile
     40  .gitignore                  3157  README.md
  19867  app.py                       995  build_runtime_index.py
  15131  eval_runner.py              1636  index_runtime.py
     92  requirements.txt
  10700  tests/test_app.py           1380  tests/test_eval_runner.py
```

`products/kenn/packages/chat/`, 23 files, all tracked. Same 9 non-test files plus:

```
   1473  evals/ableton_assistant_cases.json
  14902  evals/ableton_assistant_holdout.json
   6677  evals/ableton_deliberative_adversarial.json
   5780  evals/ableton_deliberative_holdout.json
    519  evals/adversarial_audio_cases.json
    677  evals/audio_reasoning_cases.json
   1622  tests/test_chat_hard_case_benchmark.py
   2538  tests/test_eval_chat_coverage.py
   5394  tests/test_golden_knowledge_eval.py
   4390  tests/test_llm_quality_benchmark.py
   3294  tests/test_public_api.py
   4658  tests/test_security_and_abuse.py
```

There is no `evals/` directory in `chat/`, and no `tests/fixtures/` in either tree (three documents
cite one).

### Which files are identical

| File | `chat/` | `packages/chat/` | |
|---|---|---|---|
| `.env.example` | `8ef8bac0648d` | `8ef8bac0648d` | identical |
| `.gitignore` | `d5d13b6b8b67` | `d5d13b6b8b67` | identical |
| `Dockerfile` | `92ef98afd5a5` | `92ef98afd5a5` | identical |
| `index_runtime.py` | `3fed593f22d4` | `3fed593f22d4` | identical |
| `app.py` | `e186b314065a` | `35143a653bb8` | **differs**, 310 insertions / 17 deletions |
| `eval_runner.py` | `6d47c2e557b4` | `d6f3bf1c6542` | **differs**, 1 line |
| `build_runtime_index.py` | `d379edb20e5c` | `c9d61ef88123` | **differs**, 4 lines |
| `requirements.txt` | `fd4678d6b515` | `0ac585be2519` | **differs**, 4 lines |
| `README.md` | `8ea50dc3b4c8` | `79988d9f76d7` | **differs**, 26 lines |
| `tests/test_app.py` | `9cf014e779a2` | `07b89a9b10d4` | **differs**, 19 vs 378 lines |
| `tests/test_eval_runner.py` | `76eab8b374b8` | `0df1e09b2eeb` | **differs** |

### What the differences actually do

**`app.py` — `packages/chat/` is a strict superset, 310 insertions.** Both wrappers read the *same*
retrieval engine; I confirmed each resolves `ENGINE_ROOT` to `products/kenn/apps/backend/src`
when imported on its own. The difference is the public surface and the honesty of the failure path:

- 3 endpoints exist only in `packages/chat/`: `POST /chat` (public envelope with `request_id`,
  `schema_version`, `analysis_version`), `POST /mix-review` (WAV upload, multipart, base64 JSON or
  raw body; 50 MB `MAX_PUBLIC_UPLOAD_BYTES`; 44-byte minimum; calls
  `packages/mix-review/core/local_engine.analyze_wav` with a 60 s timeout), and `POST /feedback`
  (1–5 rating, appended to `.runtime/feedback.jsonl`).
- An `X-Request-ID` HTTP middleware, absent from `chat/`.
- `/health` reports a different payload: `chat/` returns `service: "kenn-chat"`,
  `scope: "mix_advice_only"`, `llm_enabled: false`, `audio_upload: false`. `packages/chat/` returns
  `service: "kenn-public-api"`, `version: "1.0.0-beta"`, `schema_version: "kenn.public_api.v1"`,
  a `features` map (7 booleans), a `privacy` string and `retrieval` status. This exact difference is
  what commit `a4777b72` was written about.
- `MIX_ADVICE_TERMS` grows from 93 terms to 122 — `cutoff`, `filter`, `freeze`, `warp`, `808`,
  `dialogue`, `spectral`, `clipper`, `repitch`, and 21 more. Widening the scope gate is a behaviour
  change: questions containing those words stop abstaining.
- `_contains_mix_advice_term` falls back to `kenn.core.chat_retrieval.normalized_terms`, so
  misspellings that correct to an approved term now pass the gate.
- `_scope_reason` adds a `business_pricing_query` rejection with its own abstention message.
- `route_query` is no longer stubbed to a constant `"production"`. `packages/chat/` supplies
  `_retrieval_only_route`, which returns `"ableton"` only when `route_query` says `ableton` **and**
  the question literally names `ableton|live|midi|clip|scene|warp|automation|arrangement|osc`.
  So Ableton questions keep the Ableton answer shape; in `chat/` they are rendered as generic
  production advice.
- A `SystemExit` handler. `chat_retrieval.py` calls `SystemExit("Index not found...")` when no
  index is built, which would kill a request thread; `packages/chat/` catches it and returns an
  `intent: "engine_unavailable"` abstention instead.

**`build_runtime_index.py` — the two copies build the index from different engines.**

| | `chat/` | `packages/chat/` |
|---|---|---|
| `REPO_ROOT` | `SERVICE_ROOT.parents[2]` (the monorepo root) | `SERVICE_ROOT.parents[1]` (the product root) |
| default `ENGINE_ROOT` | `<monorepo>/Audio_Too/studio/kenn` | `<product>/apps/backend/src` |

`<monorepo>/Audio_Too/studio/kenn` exists in this worktree, so the `chat/` default is not a broken
path — it silently indexes the **external `Audio_Too` kenn tree** rather than the repository-owned
`apps/backend/src/kenn`. That is the exact staleness `docs/KNOWN_ISSUES.md` ISSUE-06 and the
comment at `packages/chat/requirements.txt` describe. Two `build_runtime_index.py` runs therefore
can produce different indexes from different corpora, and nothing records which one ran.

**`requirements.txt` — `chat/` still points outside the repo.**

```
chat/:            --requirement ../apps/backend/requirements.txt
packages/chat/:   --requirement ../apps/backend/src/kenn/requirements.txt
```

The `packages/chat/` comment on lines 1–4 says the old path "previously pointed outside the repo at
a sibling Audio_Too checkout", but the file it replaced reads `../apps/backend/requirements.txt`,
not an `Audio_Too` path. Whatever the history, the `chat/` line does not resolve from
`products/kenn/chat/` — `products/kenn/apps/backend/requirements.txt` does exist, so it installs,
but it is not the file `packages/chat/` documents as canonical.

**`eval_runner.py` — one line, cosmetic.** The receipt's `engine` field:
`"Audio_Too/studio/kenn (read-only dependency)"` in `chat/`, `"KENN/apps/backend/src/kenn
(repository-owned, read-only evaluation path)"` in `packages/chat/`.

**`packages/chat/README.md` tells you to run the other copy.** Its "Local run" block says `cd chat`,
and later "Run the service from `chat/`" — while the file itself lives in `packages/chat/`. The
`chat/` README says `cd products/kenn/chat`, which is correct for where it lives. `packages/chat/`'s
README is the one written for the old standalone `kenn-app` root layout and never updated.

### Tests

| | `chat/tests` | `packages/chat/tests` |
|---|---|---|
| files | 2 | 8 |
| test functions | 16 | 41 |
| collected by pytest | 39 | 65 |
| result in this worktree | **38 passed, 1 skipped** | **57 passed, 8 failed** |

Run with `python3 -m pytest -q <dir> -p no:cacheprovider`. 38 is the number the engineering plan
quotes as "chat 38", so the plan's chat figure is `chat/tests`, not `packages/chat/tests`.

Only `packages/chat/tests` covers the public API: `/chat`, `/mix-review` (success, non-WAV
rejection), `/feedback`, `/health`, path-traversal filename rejection, oversized-upload rejection,
corrupt-header safety, XSS in a chat answer, prompt-injection abstention, no stack-trace or path
leakage, and that uploaded audio bytes are not written to disk. `chat/tests` covers none of that.

The 8 `packages/chat/tests` failures are `test_specialist_keyword_stays_retrieval_only`,
`test_specific_reverb_setting_is_kept_visible_in_advice`,
`test_specific_eq_eight_insertion_keeps_ableton_track_workflow_visible`,
`test_specific_pink_noise_measurement_is_interpreted_as_bounded_advice`,
`test_real_engine_hard_case_benchmark_passes_without_storing_content`,
`test_full_chat_coverage_receipt_passes`, `test_full_evaluation_receipt_passes` and
`test_golden_benchmark_cases`. Every one asserts `found is True` from the real engine. **This
worktree ships no knowledge index at all**: `apps/backend/src/kenn/data/index/versions` does not
exist, no `chunks.jsonl` exists anywhere under the product, and the retrieval log says
`embedding index does not exist … retrieval mode is explicitly BM25-only until the index is
rebuilt`. `KENN_PROGRESS.md:38` already records 2 of these as known failures. **I cannot tell you
whether the other 6 pass once the index is built** — see "What I could not determine".

### How the two copies got here

- `f4a90d2c` (2026-09-20, "Finalize canonical KENN monorepo organization") added
  `packages/chat/`: 23 files, 2,868 lines.
- `95e420d0` (2026-09-21, "Prepare KENN production hardening review (#22)") added `chat/`: 11 files,
  1,543 lines. The same commit also made 3 small edits to `packages/chat/` (a `retrieval_status`
  import and one dict key in `app.py`, a trailing blank line removed from 3 test files).

So `chat/` is the **later, deliberately reduced** copy: a trimmed port created a day after the full
one, with the public-beta endpoints, the 6 eval packs and 6 test files left behind. Both trees have
only ever been touched 2 and 3 times respectively. The most recent commit on either is `a4777b72`
(2026-09-30, `chat/`); `packages/chat/`'s is `90b78809` (2026-09-26), a 3-line edit to one eval
JSON file.

## How the wrong copy loads

`sys.modules` is keyed by bare module name. Two `app.py` files in two directories both want the key
`app`, and `sys.path` order decides which one wins **once per process**. Measured, on this worktree:

```
# tooling's PYTHONPATH
PYTHONPATH=apps/backend/src:packages/chat python3 -c "import app; print(app.__file__)"
  -> products/kenn/packages/chat/app.py

# chat/tests' own setup
sys.path.insert(0, 'chat'); import app
  -> products/kenn/chat/app.py
```

Six tooling scripts put `packages/chat` on `sys.path` and then `import app` at module level:

| Script | sys.path line | `import app` |
|---|---|---|
| `tooling/scripts/build_human_review_packet.py` | 29 | 31 |
| `tooling/scripts/eval_chat_coverage.py` | 20 | 22 |
| `tooling/scripts/evaluate_chat_hard_cases.py` | 19 | 21 |
| `tooling/scripts/evaluate_retrieval_modes.py` | 19 | (via `eval_chat_coverage`) |
| `tooling/scripts/evaluate_session_grounded_advice.py` | 16 | — |
| `tooling/scripts/measure_use_it_when_lines.py` | 10 | — |

Plus three shells and one bundler that name the path rather than importing:
`tooling/scripts/start_server.sh:16`, `tooling/scripts/qualify_internal_beta.py:610` and `:721-722`,
`tooling/scripts/build_kenn_app.py:47` (in `CODE_TREES`, i.e. what ships in the bundled app) and
`:148` (the bundled app's `PYTHONPATH`), `tooling/scripts/run_tests_on_box.py:117`.

Not one of them names `products/kenn/chat`. **Every bare-`app` import in the repository resolves to
`packages/chat/app.py`.** Under the plan's phrasing, tooling does not load "the wrong one" by path
mistake — `packages/chat` is what tooling always loaded, and `chat/` is the copy tooling never
touches.

### What `a4777b72` fixed, and what it left

`a4777b72` added 5 lines to `chat/tests/test_app.py` and 3 to `chat/tests/test_eval_runner.py`:

```python
if "app" in sys.modules and Path(sys.modules["app"].__file__).resolve().parent != SERVICE_ROOT:
    del sys.modules["app"]
```

Its message names the symptom precisely: "tooling scripts have already loaded packages/chat's
app.py as `app`, and this import then returned the public API: the health test read
`kenn-public-api` instead of `kenn-chat`. CI runs each suite in its own process, so it only showed
when they were run together."

That fix is **partly effective and now mostly inert**:

- It only helps `chat/tests`. `packages/chat/tests` has no such guard, so the asymmetry is the
  reverse of what you'd want.
- It fixes nothing when pytest itself is the thing that collides. Neither `tests/` directory has an
  `__init__.py`, so the *test module* basenames `test_app` and `test_eval_runner` are also duplicated
  in `sys.modules`. Measured, both orders fail at collection:

```
$ python3 -m pytest -q --collect-only chat/tests packages/chat/tests
ERROR packages/chat/tests/test_app.py
  import file mismatch: imported module 'test_app' has this __file__ attribute:
    .../chat/tests/test_app.py
  which is not the same as the test file we want to collect:
    .../packages/chat/tests/test_app.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules

$ python3 -m pytest -q --collect-only packages/chat/tests chat/tests
ERROR chat/tests/test_app.py
  import file mismatch: ... the same clash, reversed ...
```

  Same result for `pytest -q chat packages/chat`. So a bare `pytest -q` from the product root cannot
  collect both trees — which is exactly the discovery mode that caused the bug the commit was
  written for (`docs/reports/ABLETON_ASSISTANT_CURRENT_STATE.md:535` records a gate that ran bare
  `pytest -q` and auto-discovered unrelated content).
- It is not currently needed for the gate. `qualify_internal_beta.py:610` puts `packages/chat` on
  `PYTHONPATH` and then runs one pytest process per target (`chat/tests` among them). I emulated that
  process: nothing imports `app` before the test module, and `chat/` is inserted at position 0, so
  `import app` still resolves to `chat/app.py`. The guard is belt-and-braces.

The commit treats the symptom. The two roots are still there: two `app.py` files wanting one module
name, and two `test_app.py`/`test_eval_runner.py` pairs wanting one test-module name.

## CI and tooling: what runs which path

`.github/workflows/kenn-core.yml` (the monorepo's KENN workflow) triggers on `products/kenn/**` and
runs, in its `python` job on `macos-14`:

```
line 38:  PYTHON=python bash tooling/scripts/ci_verification.sh      (working-directory: products/kenn)
```

`products/kenn/.github/workflows/kenn-ci.yml` runs the **same script** at line 36. Its own header
(lines 1–2) says it only applies to the standalone `kenn-app` repo, because GitHub reads only the
root `.github/` in the monorepo. Either way, both entry points land in the same script.

`tooling/scripts/ci_verification.sh`:

| Step | Line | Command | Which copy |
|---|---|---|---|
| 2/8 | 16 | `compileall -q apps/backend/src packages tooling/scripts chat automix` | byte-compiles **both** (`packages` covers `packages/chat`) |
| 3/8 | 19 | `pytest -q apps/backend/src/kenn/tests` | — |
| 4/8 | 22 | `pytest -q chat/tests` | **`chat/` only** |
| 5/8 | 25 | `pytest -q packages/mix-review` | — |
| 6/8 | 28 | `pytest -q automix/tests` | — |
| 7/8 | 31 | `pytest -q packages/automix/tests` | — |

**Line 22 is the whole problem in one line.** 41 of the 57 chat tests in this product are never run
by CI, including every test for `/mix-review`, `/feedback`, upload limits, path traversal and
prompt-injection safety. Step 2 compiles `packages/chat/app.py` and `chat/app.py` side by side and
passes, which proves neither is the one being executed.

Three other places reproduce `ci_verification.sh`'s step 4 by hand:

| File | Line | Value |
|---|---|---|
| `tooling/scripts/qualify_internal_beta.py` | 504 | `_SUITE_TARGETS = (..., "chat/tests", "mix-review/tests", "automix/tests")` |
| `tooling/scripts/run_tests_on_box.py` | 35 | `TARGETS = (..., "chat/tests", "mix-review/tests", "automix/tests")` |
| `apps/backend/src/kenn/tests/test_internal_beta_gate.py` | 357 | the same 4-tuple, asserted against `qualify_internal_beta` |

Two of those three also still name `mix-review/tests` and `automix/tests`, the pre-`packages/` paths.
`mix-review/` and `automix/` are duplicated the same way `chat/` is (both exist, both with
`adapter.py`, both with tests). **F4 covers only chat; the same decision is owed for those two.**

Deploy: `chat/Dockerfile` and `packages/chat/Dockerfile` are byte-identical, and both contain

```
line 17:  COPY products/kenn/chat /app/products/kenn/chat
line 21:      && python /app/products/kenn/chat/build_runtime_index.py
line 23:  WORKDIR /app/products/kenn/chat
line 25:  CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
```

So the container image builds and serves **`chat/`**, with `KENN_ENGINE_ROOT=/app/Audio_Too/studio/kenn`
set at line 7 to match `chat/`'s external-engine default. It cannot be trivially repointed at
`packages/chat` by editing one path: the file needs its `COPY`, `RUN`, `WORKDIR` and engine default
changed together.

## Where the duplication has already broken things

These are wrong **today**, before any removal, because a document names `chat/` for a file that only
exists in `packages/chat/`:

| Document | Line | Cites | Reality |
|---|---|---|---|
| `docs/runbooks/OPERATIONS.md` | 85 | `pytest chat/tests/test_public_api.py` | no such file in `chat/`; exists only in `packages/chat/tests/` |
| `docs/beta/PUBLIC_BETA_SECURITY_NOTES.md` | 30 | `chat/tests/test_security_and_abuse.py`, "7 security constraints" | exists only in `packages/chat/tests/` |
| `docs/CHANGELOG.md` | 78 | `chat/tests/test_security_and_abuse.py` | same |
| `docs/specs/KENN_BETA_GAP_MATRIX.md` | 316 | `chat/tests/test_app.py::test_missing_knowledge_index_abstains_instead_of_crashing` | that test name is in `packages/chat/tests/test_app.py` only |
| `docs/reports/KENN_SYSTEM_VERIFICATION_REPORT.md` | 69–70 | `chat/tests/test_llm_quality_benchmark.py`, `chat/tests/test_golden_knowledge_eval.py` | both exist only in `packages/chat/tests/` |
| `docs/plans/KENN_STUDIO_ASSISTANT_ROADMAP.md` | 465 | `chat/evals` harness | no `evals/` in `chat/` |

And two are wrong in the other direction: `docs/reports/KENN_KNOWLEDGE_BASE_AUDIT.md:18` cites gold
fixtures in `chat/tests/fixtures/`, and neither tree has a `fixtures/` directory.

`packages/chat/README.md` compounds it by telling the reader to `cd chat`.

The practical cost: a reader who follows the runbooks runs a copy that has none of the endpoints or
safety tests, and a reader who follows the products map runs a different copy again.

## Recommendation

**Make `packages/chat/` canonical; remove `chat/`.**

Against the criteria in the order they were set:

**1. CI workflows and documented commands.** This is the one criterion where `chat/` wins, and it
should be said plainly: `ci_verification.sh:22` runs `chat/tests`, and so do the three target lists
in `qualify_internal_beta.py`, `run_tests_on_box.py` and `test_internal_beta_gate.py`. The
Dockerfile serves `chat/`. Against that, every *runtime* path — `start_server.sh`, the six tooling
scripts that `import app`, the bundled-app `CODE_TREES` and its `PYTHONPATH`, and
`qualify_internal_beta.py`'s own `PYTHONPATH` — names `packages/chat`, and none names `chat/`. So
`chat/` owns CI while `packages/chat/` owns the product. CI is a single line to change; the tooling
is 13 call sites that would all break in the other direction.

**2. More tests.** `packages/chat/tests` is 41 test functions and 65 collected against `chat/`'s 16
and 39 — 8 files against 2. The extra 25 are the only coverage of `/mix-review`, `/feedback`,
`/chat`, the 50 MB upload ceiling, path traversal, XSS, prompt injection and "audio bytes not
persisted to disk". Choosing `chat/` means deleting those tests or porting them forward, and
choosing it first means the public API ships untested in the meantime.

**3. Docs and plans.** `packages/chat` is named in 5 markdown files (6 occurrences) and is listed as
the product's chat service in `docs/PRODUCT_MAP.md:11` and `products/kenn/README.md:13`.
`chat/` is named in 3 markdown files (5 occurrences) plus ~15 more that use the bare `chat/tests`
string, and 6 of those are already broken by pointing at files that live in `packages/chat/`. The
docs are not merely split; the `chat/` side is the broken half.

**4. Recent commits.** `chat/` has the more recent commit (`a4777b72`, 30 Sept) but only 2 in its
life; `packages/chat/` has 3. The `chat/` commits are the production-hardening port and the shadowing
fix. `packages/chat/`'s most recent is a 3-line eval-data edit. This criterion is close to a tie and
should not decide it.

Two facts cut the same way and are not in the stated criteria but matter more than any of them:
`chat/build_runtime_index.py` builds its index from the external `Audio_Too/studio/kenn` tree while
`packages/chat`'s builds from the repository-owned `apps/backend/src/kenn`, so the two copies do not
even agree on what KENN's knowledge base is; and `packages/chat/app.py` is the only copy that catches
the `SystemExit` the retrieval layer raises when no index is built, which turns a process-killing
error into an honest abstention.

**If Jack decides to keep `chat/` instead**, the cost is: port 25 test functions and 6 test files
across, port 3 endpoints and the request-ID middleware across, move 6 eval JSON packs across, copy
`_retrieval_only_route` and the `business_pricing_query` and `SystemExit` handling across, decide
whether the 29 new `MIX_ADVICE_TERMS` change the abstention boundary on purpose, repoint the
Dockerfile, and rewrite the 13 tooling call sites that already point the other way. That is the bulk
of the work either way; picking `packages/chat` is the direction that needs no porting.

## Removal plan, in order

1. **Understand the 8 `packages/chat/tests` failures before touching anything.** Build the index
   (`python3 apps/backend/src/kenn/main.py build` from `products/kenn`) and run
   `python3 -m pytest -q packages/chat/tests`. Find out how many of the 8 are index-starvation and
   how many are real. Nothing else in this plan is safe to start until this number is known, because
   step 2 turns them into CI failures.
2. **Flip `tooling/scripts/ci_verification.sh:22`** from `pytest -q chat/tests` to
   `pytest -q packages/chat/tests`. Run the full script. This is the moment the two trees' collision
   stops being possible at all, because the backend suite, the chat suite and the packages suites now
   touch disjoint module names.
3. **Flip the three hand-written target lists** to match step 2:
   `tooling/scripts/qualify_internal_beta.py:504`, `tooling/scripts/run_tests_on_box.py:35`, and
   `apps/backend/src/kenn/tests/test_internal_beta_gate.py:357` (the last one asserts equality
   against the first, so all three move together or the gate test fails).
4. **Delete `products/kenn/chat/`** — 11 files. `app.py`, `eval_runner.py`, `index_runtime.py`,
   `build_runtime_index.py`, `Dockerfile`, `README.md`, `requirements.txt`, `.env.example`,
   `.gitignore`, `tests/test_app.py`, `tests/test_eval_runner.py`.
5. **Fix `packages/chat/Dockerfile`**, which is currently a copy of the deleted one: line 15
   `COPY Audio_Too/requirements.txt …` and line 16 `COPY Audio_Too/studio/kenn …` are the external
   engine; line 17 the `COPY products/kenn/chat`; line 21 the `build_runtime_index.py` path; line 23
   `WORKDIR`; and line 7 `KENN_ENGINE_ROOT=/app/Audio_Too/studio/kenn`, which must be repointed at
   the copied engine or dropped so the in-tree default applies.
6. **Fix `packages/chat/README.md`**: the "Local run" `cd chat` (line 27) and "Run the service from
   `chat/`" (line 57) both need to name `packages/chat`.
7. **Fix the 6 already-broken document references** listed in the table above, so the docs stop
   pointing at `chat/` for `packages/chat/` files.
8. **Fix the remaining `chat/` references** — the full list is below.
9. **Add `__init__.py` to `packages/chat/tests/`** only if any single process is ever going to
   collect both that directory and another `test_app.py`. With step 2 in place nothing does, so this
   is optional; without step 2 it is mandatory.
10. **Run the whole gate**, not just the chat suite: `ci_verification.sh`,
    `qualify_internal_beta.py --run-suite`, and one `pytest` process per target. Then decide
    separately whether `mix-review/` and `automix/` get the same treatment.

## Everything that breaks, file and line

### Code and CI

| File | Line | Now | Becomes |
|---|---|---|---|
| `tooling/scripts/ci_verification.sh` | 16 | `compileall -q apps/backend/src packages tooling/scripts chat automix` | drop `chat` |
| `tooling/scripts/ci_verification.sh` | 22 | `pytest -q chat/tests` | `pytest -q packages/chat/tests` |
| `tooling/scripts/qualify_internal_beta.py` | 504 | `"chat/tests"` in `_SUITE_TARGETS` | `"packages/chat/tests"` |
| `tooling/scripts/run_tests_on_box.py` | 35 | `"chat/tests"` in `TARGETS` | `"packages/chat/tests"` |
| `apps/backend/src/kenn/tests/test_internal_beta_gate.py` | 357 | 4-tuple with `"chat/tests"` | `"packages/chat/tests"` |
| `packages/chat/Dockerfile` | 7 | `KENN_ENGINE_ROOT=/app/Audio_Too/studio/kenn` | in-tree engine, or drop |
| `packages/chat/Dockerfile` | 15–16 | `COPY Audio_Too/…` | copy from `apps/backend/src/kenn`, or delete |
| `packages/chat/Dockerfile` | 17 | `COPY products/kenn/chat …` | `COPY products/kenn/packages/chat …` |
| `packages/chat/Dockerfile` | 21 | `python /app/products/kenn/chat/build_runtime_index.py` | `…/packages/chat/…` |
| `packages/chat/Dockerfile` | 23 | `WORKDIR /app/products/kenn/chat` | `…/packages/chat` |
| `packages/chat/README.md` | 27 | `cd chat` | `cd packages/chat` |
| `packages/chat/README.md` | 57 | "Run the service from `chat/`" | `packages/chat/` |

Unchanged, and worth recording as *not* breakage — these already say `packages/chat` and must stay:
`build_human_review_packet.py:29`, `eval_chat_coverage.py:20`, `evaluate_chat_hard_cases.py:19`,
`evaluate_retrieval_modes.py:19`, `evaluate_session_grounded_advice.py:16`,
`measure_use_it_when_lines.py:10`, `eval_ableton_assistant.py:45`, `eval_deliberative_planner.py:22`,
`run_deliberative_bakeoff.py:27-28`, `run_deliberative_ollama.py:32`,
`run_deliberative_transformers_bakeoff.py:45-46`, `qualify_internal_beta.py:610,721,722`,
`start_server.sh:16`, `build_kenn_app.py:47,148`, `run_tests_on_box.py:117`,
`tooling/evaluation/README.md:11,23`, `docs/PRODUCT_MAP.md:11`, `products/kenn/README.md:13`,
`apps/backend/src/kenn/tests/test_internal_beta_gate.py:426-427`,
`apps/backend/src/kenn/tests/test_transformers_bakeoff_runner.py:105-106`.

The `evals/` hashes at `test_internal_beta_gate.py:426-427` and
`test_transformers_bakeoff_runner.py:105-106` are SHA-256 digests of
`packages/chat/evals/ableton_deliberative_{holdout,adversarial}.json`. Those files survive, so the
digests stay valid — but if a path string in either test is rewritten, the digest is computed over the
file contents, not the path, so a path edit alone is safe.

### Docs

Live guidance — must change:

| File | Line |
|---|---|
| `products/kenn/BETA_SCOPE.md` | 15, 47 |
| `products/kenn/docs/ABLETON_ASSISTANT_TESTER_GUIDE.md` | 11 |
| `products/kenn/docs/runbooks/OPERATIONS.md` | 85 |
| `products/kenn/docs/beta/PUBLIC_BETA_SECURITY_NOTES.md` | 30 |
| `products/kenn/docs/plans/KENN_STUDIO_ASSISTANT_ROADMAP.md` | 59, 465 |
| `products/kenn/docs/specs/KENN_BETA_GAP_MATRIX.md` | 98, 109, 113, 201, 316 |
| `products/kenn/docs/KNOWN_ISSUES.md` | 64, 222, 224 |
| `products/kenn/docs/deep-review/01-system-map.md` | 20 |
| `products/kenn/EVIDENCE_RECEIPTS.md` | 32, 33 |

Historical receipts — cite numbers that were true on their date; rewrite only if a reader would
otherwise run the command:

| File | Line |
|---|---|
| `products/kenn/docs/research/KENN_FULL_PRODUCT_TRUTH_REPORT.md` | 20 |
| `products/kenn/docs/reports/KENN_BETA_READINESS_REPORT.md` | 38, 274, 280 |
| `products/kenn/docs/reports/KENN_CURRENT_STATE_AUDIT.md` | 26, 117, 124 |
| `products/kenn/docs/reports/KENN_CURRENT_STATE_SUMMARY.md` | 65 |
| `products/kenn/docs/reports/KENN_KNOWLEDGE_BASE_AUDIT.md` | 18 |
| `products/kenn/docs/reports/KENN_SYSTEM_VERIFICATION_REPORT.md` | 69, 70 |
| `products/kenn/docs/reports/ABLETON_ASSISTANT_CURRENT_STATE.md` | 196, 379, 535 |
| `products/kenn/docs/evidence/KENN_FULL_AUDIT_2026-09-01.md` | 72, 143, 151 |
| `products/kenn/docs/evidence/KENN_CLEAN_INSTALL_VERIFICATION_2026-09-07.md` | 39 |
| `products/kenn/docs/plans/KENN_BETA_ROLLBACK_PLAN.md` | 100, 103 |
| `products/kenn/BETA_BLOCKERS.md` | 20 |
| `products/kenn/docs/plans/historical_prompts/KENN_KNOWLEDGE_BASE_5000_NOTE_SCALEUP_PROMPT_V1.md` | 31, 94 |
| `products/kenn/docs/plans/historical_prompts/KENN_KNOWLEDGE_BASE_HYGIENE_FIX_PROMPT_V1.md` | 32, 54, 91 |

### Not affected

`mix-review/adapter.py`, `packages/mix-review/*`, `automix/adapter.py`, `packages/automix/*`, and
`apps/backend/src/kenn/server.py:479-486` (which puts a *third* `app` — `business/app/` — on
`sys.path` so `app` resolves as a package). That third one is a separate ambiguity from this task and
should not be bundled into it.

## Risk: what could silently stop running

- **The biggest one is the reverse of what it looks like.** Nothing at runtime is currently using
  `chat/app.py` except CI, so deleting it changes no answer KENN gives. The thing that could
  silently stop is the **41 tests that were never running** — including the 50 MB upload ceiling, the
  path-traversal rejection, the prompt-injection abstention and "uploaded audio bytes are not
  written to disk". They have been dead weight since `f4a90d2c`; step 2 revives them and they may not
  be green. Find out in step 1.
- **A silent index swap.** `chat/build_runtime_index.py` and `packages/chat/build_runtime_index.py`
  default to two different engines. If a container is built from the `chat/` Dockerfile today and one
  from the `packages/chat/` path tomorrow, the two produce different indexes from different corpora
  with no marker in either receipt. Fix the Dockerfile in the same change that deletes `chat/`, never
  in a later one.
- **A `SystemExit` reaching a request thread.** If the wrong copy is ever what gets imported after
  the deletion — an old `.pyc`, a stale `PYTHONPATH` on a box, a leftover bundle from
  `build_kenn_app.py` — the surviving `app.py` catches it and abstains, but only the surviving copy
  has that handler. Search for cached bundles before assuming a clean environment.
- **`packages/chat/.runtime/feedback.jsonl` and `kenn.db`.** `.gitignore:105-106` covers both
  `.runtime/` paths, so nothing is committed, but a developer's local `packages/chat/.runtime/` will
  keep receiving writes after `chat/` is gone. Harmless; do not add it to git by accident.
- **The stale `PYTHONPATH` entries in `docs/runbooks/OPERATIONS.md:85`** (`PYTHONPATH=source:chat`)
  will point at a deleted directory. On most shells `PYTHONPATH` entries that do not exist are
  ignored, so the command will appear to work while silently losing the chat path — and it was
  already pointing at the wrong tree (see the broken-reference table).
- **The pytest basename clash is not fixed by the deletion alone.** Deleting `chat/` removes one half
  of the `test_app`/`test_eval_runner` clash, which is enough. But if anyone later reintroduces a
  second directory with a `test_app.py` and no `__init__.py`, the same collection error returns.
- **`mix-review/` and `automix/` are still duplicated** and three of the four target lists still name
  the pre-`packages/` paths. Fixing chat and leaving those makes the gate half-migrated, and a later
  reader may reasonably assume the whole target list was reviewed.
- **The Dockerfile may already be dead.** `.dockerignore:5` excludes `products/` from the build
  context, and the Dockerfile's `COPY products/kenn/chat` needs it. If the image is not built from
  the monorepo root today, editing that Dockerfile changes nothing and gives false confidence. I
  could not determine which; check before spending time on step 5.

## What I could not determine, and how I checked

- **Whether the 8 failing `packages/chat/tests` pass with a real index.** This worktree has no index:
  `apps/backend/src/kenn/data/index/versions` does not exist, no `chunks.jsonl` exists anywhere
  under the product, and the run logs `retrieval mode is explicitly BM25-only until the index is
  rebuilt`. I ran with `KENN_CHAT_INDEX_DIR` pointed at an empty temporary directory to avoid
  writing into the tree, then removed that directory and the two `.runtime/` directories the runs
  created (`git status` is clean). I did not build the index — that needs the approved corpus and is
  not this task.
- **Whether the `Dockerfile` is still built anywhere.** `.dockerignore:5` excludes `products/`, and
  `railway.json` at the repo root is a Nixpacks config for `npm run build`, not for this image. I
  searched for a build that invokes it and found none in the workflows.
- **Which copy a real deployment runs.** Nothing in the repo runs `chat/app.py` except
  `ci_verification.sh:22`, the three target lists, and the `chat/Dockerfile`. There is no running
  service, process supervisor or LaunchAgent in the tree that names either path, so the deployed
  answer depends on infrastructure outside this repository.
- **The order in which the `sys.modules` clash bit in production.** `a4777b72`'s message says
  "tooling scripts have already loaded packages/chat's app.py", and
  `docs/reports/ABLETON_ASSISTANT_CURRENT_STATE.md:535` records the bare-`pytest -q` gate that
  would have produced it, but that report is dated 2026-09-05 and `a4777b72` is 2026-09-30. I
  reproduced the mechanism (`import app` under `packages/chat`, then `sys.path.insert(0, 'chat')`,
  then `import app` returns the same module object) but not the original failing run.
- **Why the reduced copy was made.** `f4a90d2c` and `95e420d0` are bulk consolidation commits and
  neither message mentions the duplication. There is no note, ADR or issue explaining the intent, so
  the reason `chat/` omits the public-beta endpoints is unknown. If that reason was deliberate —
  for example "the beta surface is not ready to ship" — it should be recorded before step 4, because
  it would change the recommendation.
