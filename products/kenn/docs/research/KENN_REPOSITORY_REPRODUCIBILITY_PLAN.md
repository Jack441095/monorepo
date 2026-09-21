# KENN repository reproducibility plan

Date: 2026-09-21
Baseline: `3667e0e996c976e96110afa32e5e1f5a0163ffc7`
Working branch: `kenn-production-hardening`
Canonical source commit: `f118fda61da6f72b39b97b13828c7e4fd9fcc284`

## Decision

`products/kenn/apps/backend/src/kenn` is the only active Python backend. The
reviewed product boundary is the source, tests, configuration, and durable
evidence under `apps`, `packages`, `plugins`, `integrations`, `tooling`,
`docs`, and `assets`, plus the root launch/build files. The native wrapper also
requires the 13 portable C++ source files under
`audio-technology/audio-analysis/audio_analysis/dsp_engine/native`.

Local migration snapshots, databases, indexes, model weights, corpora,
dependency directories, build output, and user uploads are not source inputs.
They remain on disk but are excluded from commits.

## Canonical source manifest

| Path | Files identified before first source commit | Purpose |
|---|---:|---|
| `apps/backend` | 388 | Python backend, routes, contracts, fixtures, and tests |
| `apps/frontend` | 78 | Vue client, lockfile, unit tests, and build configuration |
| `apps/desktop` | 5 | macOS desktop companion source |
| `apps/legacy-web` | 8 | Preserved browser client source |
| `packages` | 50 | Chat, Mix Review, AutoMix, and common contracts |
| `plugins` | 27 | JUCE VST3/AU source and tests |
| `integrations` | 57 | AbletonOSC vendor boundary and Remote Script source |
| `tooling` | 200 | Benchmarks, qualification, packaging, and native wrapper |
| `docs` | 213 | Product, operations, architecture, and durable evidence |
| `assets` | 2 | Small product assets |
| Product root files | 5 | Environment example, ownership, Makefile, runner, ignore rules |
| Shared native kernel source | 13 | C++ kernels linked by the native wrapper |
| Repository workflow | 1 | Native sanitizer, wheel, and plug-in CI |

The count is an inventory observation, not a permanent gate. The durable gate
is that every required path is tracked and a clean checkout can execute the
verification commands below without relying on files outside the checkout.

## Generated and local-only manifest

The following are explicitly excluded:

- `.venv`, `node_modules`, `dist`, `build`, CMake caches, pytest caches,
  bytecode, compiled libraries, and package metadata;
- `apps/backend/src/kenn/data`, `chats`, `artifacts`, and `logs`;
- local training notes, transcripts, sources, PDFs, and licensed manuals;
- databases, model weights, audio uploads, archives, and local runtime state;
- `products/kenn/kenn`, `runtime/legacy`, and `standalone`, which are local
  migration/reference snapshots rather than active runtime owners;
- empty or generated retired launch directories at the KENN product root.

The exclusion rules are recorded in the repository and product `.gitignore`
files. In particular, Mix Review uploads are excluded at their exact data
path so portable native kernel source remains reviewable.

## Symlink analysis

The two compatibility links are tracked and now resolve inside the product:

| Link | Previous target | Canonical target | Clean-checkout result |
|---|---|---|---|
| `source` | `../../Audio_Too/studio/kenn` | `apps/backend/src/kenn` | Resolves to the active backend |
| `vst3-plugin` | `../../Audio_Too/studio/vst3_plugins/KENNMixAssistant` | `plugins/kenn-vst3-au` | Resolves to the active plug-in source |

No clean checkout is permitted to depend on the former sibling checkout.

## Duplicate-tree ownership

The local comparison trees are materially divergent:

- canonical versus `runtime/legacy/kenn`: 47 one-sided entries and 63
  differing files;
- canonical versus product-root `kenn`: 346 one-sided entries and 100
  differing files;
- canonical versus the partial `standalone` snapshot: 585 one-sided entries
  and 339 differing files, including generated cache content.

They are not aliases and must not receive active fixes. They were not deleted
or overwritten. Any future recovery from these trees requires a file-level
contract review into the canonical owner, followed by canonical tests.

## Clean-checkout gates

Run from a detached clean worktree made from the reviewed commit:

```bash
git worktree add --detach /tmp/kenn-clean-checkout <reviewed-commit>
cd /tmp/kenn-clean-checkout/products/kenn

test -f apps/backend/src/kenn/server.py
test -f source/server.py
test -f vst3-plugin/CMakeLists.txt

python3 -m venv /tmp/kenn-clean-venv
/tmp/kenn-clean-venv/bin/python -m pip install -r apps/backend/requirements.txt
PYTHONPATH=apps/backend/src /tmp/kenn-clean-venv/bin/python -m pytest -q \
  apps/backend/src/kenn/tests

PATH=/Users/Ganders4/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH \
  npm --prefix apps/frontend ci
PATH=/Users/Ganders4/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH \
  npm --prefix apps/frontend test
PATH=/Users/Ganders4/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH \
  npm --prefix apps/frontend run build

cmake -S tooling/native/fft_poc -B /tmp/kenn-fft-clean \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build /tmp/kenn-fft-clean --parallel 2
ctest --test-dir /tmp/kenn-fft-clean --output-on-failure

cmake -S ../../audio-technology/audio-analysis/audio_analysis/dsp_engine/native \
  -B /tmp/kenn-automix-clean -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build /tmp/kenn-automix-clean --parallel 2
ctest --test-dir /tmp/kenn-automix-clean --output-on-failure
```

The JUCE plug-in build is a separate network/toolchain gate because a fresh
configure may fetch JUCE.

## Fresh-checkout results

A detached worktree at source commit `f118fda61da6f72b39b97b13828c7e4fd9fcc284`
was verified on macOS ARM64 using new dependency/build directories:

| Gate | Result |
|---|---|
| Internal compatibility links | Passed; both targets resolved within the checkout |
| Fresh Python 3.13 virtual environment and requirements install | Passed |
| Canonical backend suite | 1,166 passed, 121 skipped, 4 warnings |
| Fresh frontend `npm ci`, unit suite, and production build | Passed; 5 tests and 131 transformed modules |
| FFT proof-of-concept Release build | Passed; 2/2 CTest tests |
| Shared AutoMix native kernel Release build | Passed; 1/1 CTest test |
| Fresh JUCE configure and Release build | Passed; JUCE was fetched into the isolated build directory |
| JUCE plug-in native suite | Passed; 9/9 CTest tests, including realtime thread-safety and performance |

The 121 backend skips are expected evidence of the source boundary: the
approved local retrieval corpus, model files, and generated index are not
committed. A clean source checkout therefore cannot qualify semantic retrieval
or corpus-dependent evaluations. It must report the BM25-only/unavailable mode
explicitly rather than presenting those local assets as reproducible source.

After the core workflow and retrieval diagnostics were added, a second detached
checkout at `5647a85` was installed and exercised from scratch. The consolidated
core script passed with 1,170 backend tests and 121 expected skips, 38 scoped-chat
tests and one explicit approved-corpus skip, 64 Mix Review tests, both four-test
AutoMix boundaries, and validation of all 50 JSON receipts. The locked frontend
install reported zero vulnerabilities, passed 5 tests, and built 131 modules.
The corpus-dependent chat case still runs and passes in the indexed developer
environment; it does not borrow that untracked index in clean CI.

## Remaining decisions and blockers

1. The approved retrieval corpus is deliberately not distributed. A clean
   checkout therefore proves the explicit BM25/no-index fallback, not a
   production semantic index.
2. Python dependencies use bounded requirements rather than a fully resolved,
   cross-platform lock. A supported-platform constraints policy is still
   required before release.
3. The local branch started 376 commits ahead of and 141 commits behind
   `origin/main`. Publishing must use a review branch; direct replacement of
   remote `main` is unsafe.
4. Real Ableton qualification remains external to repository reconstruction
   and requires Live plus AbletonOSC.
5. Historical migration trees should be archived or removed only after an
   owner confirms their backup and retention policy.

## Change grouping

The source-control review should remain split into short, descriptive commits:

1. canonical product source and repository boundaries;
2. clean-checkout or runtime fixes discovered by verification;
3. retrieval/project-graph changes with their focused tests;
4. refreshed qualification receipts and final report updates.

Every commit must be independently inspectable and must exclude unrelated
workspace files.
