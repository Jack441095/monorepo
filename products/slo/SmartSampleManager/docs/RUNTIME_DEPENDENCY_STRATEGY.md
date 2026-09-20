# SmartSampleManager — Runtime Dependency Distribution Strategy

Phase 2, Sections 8-10. Addresses `docs/COMMERCIAL_RELEASE_BLOCKERS.md` P0 #3 — TagLib, ONNX
Runtime, and libsodium currently resolve via Homebrew `find_library`/`find_path`
(`CMakeLists.txt:53-58,101-102`), meaning a customer machine without Homebrew cannot run the app
at all.

## STATUS: IMPLEMENTED AND LOCALLY VERIFIED — not yet clean-machine tested

The dynamic-bundling approach below (originally documented as design-only, deferred pending a
clean machine) **has now been implemented** for all three dependencies, applied uniformly to
VST3/AU/Standalone via a new `cmake/BundleAppleDeps.cmake` helper invoked from a `POST_BUILD`
step in `CMakeLists.txt`. What changed the calculus: a genuinely strong local proxy for the
clean-machine test became available — temporarily hiding this machine's own Homebrew `/usr/local/opt/{taglib,onnxruntime,libsodium}` symlinks (the actual paths the binaries would
resolve dependencies through) and confirming the built app still launches and initializes ONNX
Runtime + CoreML correctly using *only* the bundled copies. This is not a substitute for a truly
clean machine (a machine that's never had Homebrew installed at all could still differ in ways
this proxy can't catch — different SDK versions, missing system frameworks, Gatekeeper/
quarantine behavior on a fresh download, etc.) but it's strong enough evidence to implement now
rather than continue blocking on hardware access, while still being explicit that the clean-machine
gate in `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md` remains a real, separate requirement before shipping.

**A real, unrelated crash was found and fixed while doing this work** — see
`docs/ASYNC_STARTUP.md`'s "second regression" section. It was a genuine use-after-free in the
async-startup code from earlier in this session, surfaced by a clean VST3 build (this
implementation work happened to be what finally triggered a truly clean rebuild), not caused by
the dependency-bundling logic itself.

## Current state (verified against `CMakeLists.txt`)

```cmake
find_path(TAGLIB_INCLUDE_DIR NAMES tag.h ... PATHS /usr/local/include /opt/homebrew/include)
find_library(TAGLIB_LIBRARY NAMES tag ... PATHS /usr/local/lib /opt/homebrew/lib)
find_path(ONNXRUNTIME_INCLUDE_DIR NAMES onnxruntime_cxx_api.h ...)
find_library(ONNXRUNTIME_LIBRARY NAMES onnxruntime ...)
find_path(SODIUM_INCLUDE_DIR NAMES sodium.h ...)
find_library(SODIUM_LIBRARY NAMES sodium ...)
```

All three resolve to whatever Homebrew has installed at build time (`/usr/local/lib` on Intel,
`/opt/homebrew/lib` on Apple Silicon) and link dynamically against those paths. The resulting
binaries have no `@rpath`-relative reference to a bundled copy — they hardcode the Homebrew
absolute path (verifiable with `otool -L` on any built artifact), which is why a machine without
that exact Homebrew layout can't load the plugin.

## Per-dependency strategy

| Dependency | License | Link type | Bundle location | Rpath | Customer requirement | Attribution requirement |
|---|---|---|---|---|---|---|
| **TagLib** | LGPL-2.1-only OR MPL-1.1 | **Dynamic** (required — see below) | `Contents/Frameworks/libtag.dylib` inside each plugin bundle (VST3/AU/Standalone) | `@rpath/libtag.dylib` referenced from the binary; `@loader_path/../Frameworks` added as an rpath search path | None (fully self-contained) | LGPL requires the library's own license text be included; add to `docs/THIRD_PARTY_LICENSES.md`-derived notices, not to source code |
| **ONNX Runtime** | MIT | **Dynamic** (see below — do not statically link) | `Contents/Frameworks/libonnxruntime.dylib` inside each plugin bundle | `@rpath/libonnxruntime.dylib` | None | MIT notice in third-party notices file |
| **libsodium** | ISC | **Dynamic, bundled** (originally planned as static — see implementation note below for why this changed) | `Contents/Frameworks/libsodium.dylib` inside each plugin bundle | `@rpath/libsodium.dylib` | None | ISC notice in third-party notices file |

## Why dynamic (not static) for TagLib

TagLib is LGPL-2.1-or-MPL-1.1. `docs/THIRD_PARTY_LICENSES.md` already established this build
links it dynamically, which is the simpler LGPL-compliance path — LGPL permits static linking
too, but only if the *relinkable object files* (or an equivalent mechanism) are provided to
recipients, which is extra packaging/legal overhead this product doesn't need. **Recommendation:
keep dynamic, just bundle the `.dylib` inside the app/plugin bundle instead of relying on
Homebrew's copy.** This is the standard, low-risk path for a JUCE plugin shipping an LGPL
dependency — no source-code obligation is triggered by *using* a dynamically-linked LGPL library
from a closed-source host, only by *modifying TagLib itself* (not done here).

## Why dynamic (not static) for ONNX Runtime

ONNX Runtime is MIT-licensed, so static linking would be legally fine. The practical reason to
keep it dynamic is size and CoreML execution-provider compatibility: ONNX Runtime's CoreML EP
(`coreml_provider_factory.h`, already used in `SampleManagerEngine::init()`) is distributed as
part of the same shared library build Homebrew provides; statically linking would require
building ONNX Runtime from source with matching CoreML EP flags — a much larger, slower,
higher-risk build-system change than bundling the existing `.dylib`. **Recommendation: bundle
the dynamic library, don't attempt a from-source static build for this pass.**

## Why libsodium was originally considered for static linking (superseded — see implementation note above)

libsodium is small (a few hundred KB) and ISC-licensed (fully permissive, no static-linking
caveat), which made a `FetchContent`-based static build an attractive option in the original
design pass, avoiding a Homebrew build-time dependency entirely rather than just bundling its
output at package time. **This was reconsidered during implementation** — see "What's still not
done" / the implementation note above — because libsodium's upstream repo lacks native CMake
support, making a clean `FetchContent_MakeAvailable()` integration meaningfully riskier than
reusing the dynamic-bundling mechanism already required for TagLib and ONNX Runtime. Revisit if a
well-maintained CMake port of libsodium becomes worth adopting later.

## Implementation (as actually built — `CMakeLists.txt`, `cmake/BundleAppleDeps.cmake`)

For all three libraries (TagLib, ONNX Runtime, **and** libsodium — see the note below on why
libsodium ended up dynamically bundled rather than statically FetchContent-built, a scope
decision made during implementation, not in the original design):

1. A `POST_BUILD` custom command per plugin format target (`SmartSampleManager_Standalone`,
   `_VST3`, `_AU`) invokes `cmake -P cmake/BundleAppleDeps.cmake`, passing the bundle's
   `Contents/` dir, the built executable's path, and the three dependency paths.
2. The script copies each `.dylib` into `<bundle>/Contents/Frameworks/`.
3. **Critical detail discovered during implementation, not anticipated in the original design**:
   a Homebrew dylib's own embedded install name (`LC_ID_DYLIB`, queried via `otool -D`) is often
   a *different path* than the one `find_library()` resolved — e.g. `find_library()` resolves
   `libtag.dylib` via the `/usr/local/lib/libtag.dylib` symlink, but the compiled binary's actual
   `LC_LOAD_DYLIB` entry references `/usr/local/opt/taglib/lib/libtag.2.dylib` (the dylib's own
   self-reported install name, baked in at Homebrew's own build time). `install_name_tool -change`
   must match that exact embedded path or the rewrite silently no-ops. The script queries each
   dylib's real install name via `otool -D` rather than assuming it matches the `find_library()`
   path.
4. `install_name_tool -change <real-install-name> @rpath/<libname> <bundle-executable>` rewrites
   the consumer's load command; `install_name_tool -id @rpath/<libname> <bundled-copy>` gives the
   bundled copy a self-consistent identity; `install_name_tool -add_rpath
   @loader_path/../Frameworks` is added once (idempotency-checked via `otool -l`, since this
   command re-runs on every incremental build).
5. A CMake Makefiles-generator gotcha found during implementation: passing a semicolon-delimited
   list through `-D` to a `cmake -P` script inside a `POST_BUILD` custom command does **not** get
   shell-escaped by the generator — `/bin/sh` splits on the literal `;`, breaking the invocation
   into separate malformed commands. Worked around by passing a comma-delimited string instead
   and converting it back to a real CMake list inside the script.
6. Re-signing after `install_name_tool` modification (codesigning must happen *after* any binary
   modification) is **not yet done** — this build is unsigned/ad-hoc-signed by JUCE's own default
   flow, same as before. Ties into the signing/notarization work in `docs/MACOS_RELEASE_PROCESS.md`,
   still gated on Apple Developer credentials.

### Why libsodium ended up dynamically bundled, not statically FetchContent-built

The original design recommended a `FetchContent`-based static build for libsodium (small,
permissive ISC license, no static-linking caveat). During implementation this was reconsidered:
libsodium's upstream repository doesn't have first-class CMake support (autotools-based), so a
`FetchContent_MakeAvailable()` the same way `umappp`/`hnswlib`/`dr_libs` are pulled in wouldn't
work without either a third-party CMake port (an extra, unvetted dependency) or wiring up an
`ExternalProject_Add`-style autotools invocation (meaningfully more fragile than the uniform
dynamic-bundling mechanism already needed for the other two). Bundling it dynamically alongside
TagLib/ONNX Runtime reuses the exact same, already-implemented-and-verified mechanism — simpler
and lower-risk than introducing a second, different dependency-acquisition pattern for one small
library.

## What's still not done

**Codesigning after modification** and **the real clean-machine test** (a machine that has
literally never had Homebrew installed, not this development machine with Homebrew hidden) —
both still gated on Apple Developer credentials / a provisioned clean VM per
`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`. The local hidden-Homebrew-symlink proxy used to verify
this implementation (see STATUS above) is strong evidence the mechanism works, not a substitute
for that real test.

## Clean-machine test definition (for when the above is implemented)

```text
Machine has never had: Homebrew, CMake, ONNX Runtime, TagLib, libsodium
↓
Install the built .pkg/.dmg (once an installer exists -- see docs/INSTALLER_ARCHITECTURE.md)
↓
Launch Standalone -- does it start without a dylib-not-found crash?
↓
Load VST3/AU in a host -- does it scan/load without a missing-library error?
↓
Scan a real sample -- does TagLib metadata read/write work?
↓
Confirm embedding generation works -- does ONNX Runtime + CoreML EP load?
```
