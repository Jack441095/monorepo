# SLO Security and Privacy Audit V1

## Positive findings

- Core scan/classification is local/offline; no telemetry or audio upload path was found in the shipping scan/classification code.
- Cache storage is local SQLite with explicit versioning, corruption handling, and path overrides.
- Imported metadata is sanitized before destination construction.
- The security regression script passed.
- Owner/customer audio and protected labels were not accessed.

## Risks and blockers

- Licensing contains a development HTTP localhost default and network POST path; production must fail closed to a configured HTTPS service.
- Bundles are ad-hoc signed, so distribution trust is not established.
- Research/benchmark scripts contain stale absolute corpus paths; they are not shipping runtime but should be clearly isolated from release tooling.
- Move-based sorting can alter user files; privacy-safe beta must default to review/read-only.

## Decision

Privacy posture is **PASS WITH LIMITATIONS** for local classification. Security/distribution is **BLOCKED** until HTTPS licensing, signed/notarized artifacts, installer provenance, and a threat-model review are complete.
