# NITE DSP Download & Update Architecture (Design Only)

Phase 3, Sections 38-45. **Design document — no download infrastructure is deployed.**

## Download flow (Section 38)

```text
CUSTOMER
    ↓
NITE DSP ACCOUNT (authenticated -- docs/NITE_DSP_ACCOUNT_ARCHITECTURE.md)
    ↓
ENTITLEMENT CHECK -- does this user have an active entitlement for this product?
    ↓ (yes)
SIGNED SHORT-LIVED URL -- generated server-side, expires in minutes, points directly
    at object storage (not proxied through the web server's own bandwidth)
    ↓
OBJECT STORAGE / CDN -- serves the actual installer bytes
```

Large installer files (the VST3/AU/Standalone bundle plus the ~24MB ONNX model, per
`docs/RELEASE_MANIFEST.md`) are never proxied through the application server — that would waste
server bandwidth/compute on what's fundamentally a static-file-serving problem, and object
storage + CDN is both cheaper and more reliable at this than a hand-rolled download endpoint.

## Release records (Section 39)

Schema already defined in `docs/NITE_DSP_DATABASE_SCHEMA.md`'s `releases` table: `product_id`,
`version`, `platform`, `architecture`, `channel`, `checksum_sha256`, `signature`, `storage_key`,
`release_notes`, `published_at`.

**Immutability** (Section 39/80): once a `releases` row's `published_at` is set and it's been
served to at least one customer, the release service must refuse to let `storage_key` be
overwritten for that row. This is an application-layer rule (the schema doesn't structurally
prevent an `UPDATE`, since Postgres has no "write-once" column constraint) — the release-
publishing code path must enforce it explicitly: publishing a new build always means inserting a
new `releases` row with a bumped version, never mutating an existing one. A checksum mismatch
between what a customer downloaded and what the release record claims should be treated as a
serious operational bug, not a possibility to design around after the fact.

## Download centre (Section 40)

```text
/downloads

Smart Sample Manager
    macOS
        Version 1.0.0
        [Download]
    Windows
        (not shown -- Windows release is not verified; see docs/WINDOWS_READINESS.md)
```

**Never show a platform that isn't actually ready.** This is a direct, literal implementation of
`releases`'s `platform` column combined with `docs/WINDOWS_READINESS.md`'s current UNVERIFIED
status — the download centre's query is simply "show releases that exist for this product," and
since no Windows release row will ever be inserted until Windows is genuinely verified, there's
no separate "hide Windows" logic needed; the absence is structural, not a manually-maintained
flag that could be forgotten.

## Update service (Section 44)

```text
GET /api/v1/releases/latest?product=smart-sample-manager&platform=macos&channel=stable

Response:
{
  "version": "1.0.1",
  "channel": "stable",
  "release_notes_url": "https://nitedsp.example/releases/smart-sample-manager/1.0.1",
  "minimum_supported_version": "1.0.0",
  "download_page_url": "https://nitedsp.example/downloads"
}
```

Public, read-only, no authentication needed (it reveals nothing sensitive — release metadata is
already public on the download page) and **never returns a direct storage URL or credentials** —
only a link to the download page, where the actual signed-URL flow (requiring entitlement
verification) takes over. This keeps the two concerns cleanly separated: "is there an update"
(public) vs. "give me the file" (requires proof of entitlement).

## Client-side update check (Section 45)

```text
Requirements:
    - Runs on a background thread (never the audio thread, never blocking plugin load --
      matches the same async-startup discipline established in docs/ASYNC_STARTUP.md)
    - Non-blocking, failure-silent (a network hiccup checking for updates must never
      surface as an error to the user, let alone disrupt the DAW session)
    - No forced update mid-session -- purely informational, user chooses when to act
    - User-controlled install -- clicking "update" opens the download page in a browser,
      the plugin never self-modifies its own binary while loaded in a host process
```

Given Phase 2's hard-won lessons about async lifetime bugs in this exact codebase
(`docs/ASYNC_STARTUP.md`'s three rounds of use-after-free fixes), **implementing this check must
follow the same engine-owned-thread pattern already established** (`initThread`/`sortThread` in
`SampleManagerEngine`) — not a fresh `juce::Thread::launch()` that reintroduces the same class of
bug this session spent considerable effort eliminating. Explicitly noting this here so a future
implementation pass doesn't have to rediscover it.

## Status

**Design only.** No object storage, CDN, release-publishing pipeline, or update-check client code
exists yet.
