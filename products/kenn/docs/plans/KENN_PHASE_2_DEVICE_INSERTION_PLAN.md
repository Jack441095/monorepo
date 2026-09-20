# KENN Phase 2 — Safe Ableton Device Insertion

## Purpose

Make a request such as `add EQ on track 4` usable through the same GLM-like
workflow already implemented for existing EQ bands:

`natural language → exact target → proposal → explicit confirmation → one Live write → readback → receipt → undo`

This plan is for the next milestone. It does not authorize a Live change by
itself.

## Current evidence

- The real KENN bridge returns a fresh four-track snapshot from Live.
- The current real snapshot resolves track 4 to `4-Audio`, whose device list
  contains the verified native `EQ Eight` retained for parameter/readback
  tests. A separate disposable qualification used `3-Audio`, which is now
  restored to an empty device list.
- Existing EQ-band control creates a confirmation-only proposal and performs
  no write before confirmation.
- The typed insertion contract is now implemented in the Python service and
  command gateway. The active route uses the pinned, vendored AbletonOSC
  `insert_device` extension; the older private `KENN_Bridge` capability token
  is not part of this route and must not be treated as an additional
  prerequisite.

## Scope

Initial insertion support is limited to the allow-listed native device
`EQ Eight` on one exact audio track. No plug-in search, third-party device
loading, racks, chains, or routing changes are included. Compound EQ edits
are a separate typed operation and never bundle implicitly with insertion.

## Safety contract

1. Resolve the one-based user track number to exactly one Live track index and
   name in a fresh snapshot.
2. Accept only the exact device definition `EQ Eight` from a fixed allow-list.
3. Refuse when an EQ Eight already exists on the target track unless the user
   explicitly requests a second instance and the proposal identifies its
   insertion position.
4. Bind the proposal to the complete target-track fingerprint, including the
   ordered device list and insertion position.
5. Require a single-use, expiring confirmation token and idempotency key.
6. Before writing, refresh Live and reject any changed track identity,
   device-order change, or stale proposal.
7. Insert only through the typed KENN service; direct bridge insertion remains
   unavailable as an unauthorised shortcut.
8. Read back the ordered device list and verify the new device name and index.
9. Return a receipt containing the before/after device lists and an exact undo
   proposal that removes only the device created by that receipt.
10. If insertion succeeds but readback fails, return a failed receipt and do
    not claim success. Recovery must be explicit and identity-bound.

## Implementation sequence

### A. AbletonOSC insertion endpoint — installed and real-write verified

- Add a narrowly scoped insertion request that the typed service can invoke.
- Keep the existing direct OSC mutation deny-list in place for untrusted
  callers; the typed KENN service is the only production caller for this
  allow-listed endpoint.
- Use the vendored AbletonOSC `insert_device` extension, installed at the
  configured User Library, and return the created device's Live name, index,
  and a stable post-insert snapshot fingerprint.
- The first implementation searched only top-level browser children and could
  not find native `EQ Eight`. It now walks nested browser items, selects the
  requested Live track before loading, and reports failure if the device count
  does not increase.

### B. Python safety service — implemented, fake-Live verified

- Add `propose_device_insertion()` and
  `execute_device_insertion()` to `LiveActionService`.
- Add a dedicated versioned proposal/receipt operation while preserving the
  existing parameter-action contracts.
- Add insertion-specific stale checks, idempotency, confirmation binding,
  readback verification, and explicit failure receipts.
- Add `propose_undo()` support that targets the created device identity only.

### C. Command gateway and plug-in — proposal path implemented

- Change `insert_device` from `unsupported` to proposal-only when the request
  resolves to the exact allow-listed EQ Eight target.
- Keep all insertion requests out of the generic Ask KENN path; only Control
  Live may create a proposal.
- Display the track number/name, device definition, insertion position,
  before/after device list, and the fact that nothing has changed.
- Reuse the native confirmation dialog and show the verified receipt after
  execution.

### D. Tests and qualification — complete for the initial device

- Fake-Live tests for proposal-only behavior, duplicate EQ refusal, stale
  track/device order, invalid device names, confirmation replay, failed
  insertion, readback mismatch, and identity-bound undo.
- Server contract tests for proposal, confirmation, failure, and undo.
- Bridge tests proving the direct unauthorised insertion path remains denied.
- Real qualification on a disposable Live set only: insert one EQ Eight,
  verify identity and ordering, undo it, verify restoration, then test stale
  and replay rejection.
- The real insertion lifecycle is complete: disposable `3-Audio` changed from
  `[]` to `[EQ Eight]`, the KENN receipt reported verified post-insert
  readback, an exact replay was rejected, and identity-bound undo restored
  `[]`. The retained `EQ Eight` on `4-Audio` is used for parameter tests.

## Exit criteria

Phase 2 is complete only when all of the following are evidenced:

- No insertion occurs before explicit confirmation.
- Exactly one allow-listed EQ Eight is inserted on the requested track.
- The post-insert Live snapshot verifies the new device identity and order.
- The receipt contains a verified undo path.
- Undo removes only the created device and restores the prior device list.
- A stale, duplicated, replayed, offline, or mismatched request performs no
  unverified write.
- The full focused test suite, native build, and disposable real-Live test
  pass.

## Runtime status and immediate next action

The runtime gate for read-only context is complete: the local KENN companion
was reloaded, the real insertion was confirmed and read back as
`4-Audio -> [EQ Eight]`, and the vendored AbletonOSC runtime exposes the
standard `insert_device` extension that the typed Python service calls. The
Python insertion path passes the full focused suite, including proposal-only
insertion, duplicate refusal, verified readback, replay protection, and
identity-bound undo against a fake Live client.

The initial insertion qualification gate is complete. The next gate is
broader device-matrix coverage: discover parameters from the live device,
choose one exact reversible control, and repeat the same proposal,
confirmation, readback, replay, and identity-bound undo lifecycle. The
compound EQ operation has also passed that real lifecycle on `4-Audio`, with
both values restored after qualification.
