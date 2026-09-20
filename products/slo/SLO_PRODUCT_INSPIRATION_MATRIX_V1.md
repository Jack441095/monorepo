# SLO product inspiration matrix V1

Date: 2026-09-11

This is a product-design reference, not an instruction to install or depend on
any commercial plugin. The goal is to borrow useful interaction patterns while
keeping SLO's evidence, provenance, rejection, and reversible-rename rules.

## Patterns worth borrowing

| Pattern | Reference products | SLO adaptation | Guardrail |
|---|---|---|---|
| Aspect-weighted similarity | Sononym, Splice Similar Sounds | Search separately by spectrum, timbre, pitch, amplitude, and temporal shape. The first SLO implementation is `aspect_similarity.py`. | Similarity is not class probability. Keep each aspect visible and calibrated separately. |
| Query by example | Sononym, Splice, XLN XO | Drop or audition a sample and ask for nearby sounds in the local library. | Search results only; never rename from similarity alone. |
| Natural-language discovery | Splice Describe a Sound, Soundly | Use text as a discovery query that maps to filters and review candidates. | Text can suggest; it cannot override waveform evidence or create a class. |
| Structured facets | Loopcloud, Splice | Filter by one-shot/loop, BPM, key, family, pitch, brightness, length, and rejection state. | Preserve unknown/uncertain values rather than filling every facet. |
| Visual similarity space | XLN XO, Algonaut Atlas | Show clusters and nearest neighbours for exploration and label-queue design. | A cluster is not a taxonomy; cluster boundaries need human interpretation. |
| Duplicate and canonical grouping | Waves COSMOS, sample browsers | Group byte-identical and near-identical files, choose a canonical path, and keep aliases. | Hash identity must precede acoustic similarity; never delete automatically. |
| Context-aware audition | COSMOS, Loopcloud, Splice | Preview at project BPM/key and compare source/reference side by side. | Preview transformations must never change source audio. |
| Spectral region inspection | iZotope RX, Steinberg SpectraLayers | Show the time/frequency region supporting a transient, pitch glide, tonal body, or noise tail. | Treat regions as evidence, not a semantic label. |
| Human notes and collections | Soundly, Sononym, ADSR | Save reviewer notes, bookmarks, accepted/rejected suggestions, and custom collections. | Store provenance and reviewer identity; do not silently promote notes into gold labels. |
| Progressive disclosure | Most mature sample browsers | Start with family/form/confidence, reveal the physical evidence and disagreement reason on demand. | Keep rejection and uncertainty prominent rather than hiding them behind a score. |

## Product features SLO should build next

1. **Evidence facets:** expose the existing definition card as filters and
   explanation fields: pitch confidence, form hint, periodicity, transient
   density, low-end weight, noisiness, clipping, and stereo character.
2. **Query-by-example:** use the existing 2,048-D embeddings plus aspect
   similarity for local search, with no semantic auto-renaming.
3. **Review collections:** make `review`, `suggest`, `never-act`, and
   `taxonomy-gap` first-class queues with notes and immutable provenance.
4. **Canonical duplicate groups:** use content hashes first, then audio
   similarity for near-duplicates; show all paths before any user decision.
5. **Context preview:** add non-destructive tempo/key preview and A/B comparison
   for loops and one-shots.
6. **Feedback capture:** every accept, correct, reject, or “not in list” action
   should become a typed event that can later feed a labelled evaluation set.

## Patterns not to copy blindly

- opaque commercial tags as ground truth;
- auto-renaming from a nearest-neighbour result;
- cloud-only indexing of a private sample library;
- forcing every file into a category;
- using natural-language descriptions to invent unsupported classes;
- deleting duplicates without a reversible journal;
- treating a 2-D visual map as proof that a taxonomy split is real.

## Current implementation status

- physical definition cards: implemented and evaluated;
- aspect-specific similarity: implemented as a review/search aid;
- review evidence packet: implemented for all 386 current suggestions;
- query-by-example search: implemented over the 7,315-file local embedding
  cache, with optional physical/aspect evidence and no policy actions;
- exact canonical duplicate groups: implemented by byte-level SHA-256, with
  deterministic canonical paths and aliases retained for review;
- review collections: implemented as immutable action-specific queues joined
  to the existing physical evidence packet;
- typed feedback ledger: implemented as append-only events with required notes
  for `not_in_list` and explicit duplicate/correction fields;
- structured evidence facets: implemented for card caches and review
  collections, preserving unknown values instead of coercing them to false;
- context preview planning: implemented for non-destructive BPM/pitch plans;
  target-key alignment remains explicitly unavailable unless a trusted source
  key or explicit semitone shift is supplied;
- visual similarity space: implemented as a deterministic 2-D PCA map over the
  testing embedding cache; no clusters or taxonomy are inferred;
- controlled natural-language discovery: implemented as a local vocabulary
  resolver over existing facets/classes, with unsupported terms retained;
- conservative acoustic near-duplicate candidates: implemented separately from
  exact hashes, with a high cosine threshold and review-only output;
- rename duplicate guard audit: implemented as an independent preflight that
  flags exact aliases and acoustic candidates without rewriting the plan;
- local review workspace: implemented as a localhost-only API/browser over the
  derived queues, controlled search, and append-only feedback ledger;
- review workspace safety joins: implemented, exposing content identity,
  duplicate flags, and approval-gate status per item;
- workspace similarity endpoint: implemented for content-deduplicated
  query-by-example search;
- end-state readiness snapshot: implemented as a cross-receipt consistency
  check for review-only/approval status;
- approval gate audit: implemented as a fail-closed preflight for class
  qualification, signatures, collisions, and duplicate flags;
- apply-boundary hardening: the rename executor now requires a matching
  duplicate-guard receipt for any mutating `--apply` invocation;
- content-addressed cache identity: implemented as a complete SHA-256
  manifest, separating stable audio identity from path aliases;
- content-addressed embedding index: implemented, retaining all path aliases
  while pointing them to one model-versioned embedding identity;
- content-aware query-by-example: implemented, attaching stable content IDs and
  aliases to every similarity result when the index is supplied;
- alias-deduplicated similarity results: implemented as an explicit opt-in so
  moved/exact-copy files do not crowd out distinct sounds;
- stale-cache protection: implemented by verifying the query file's current
  bytes against its indexed content hash before similarity search;
- production classifier and rename policy: unchanged;
- external plugins or commercial datasets: not installed or imported;
- human calibration of aspect scores: still required before policy use.

## Reference links

- Sononym similarity search: https://www.sononym.net/docs/manual/similarity-search/
- Splice Similar Sounds: https://splice.com/blog/introducing-similar-sounds/
- Splice Describe a Sound: https://support.splice.com/en/articles/13764370-how-to-use-describe-a-sound-in-the-splice-desktop-app
- Loopcloud features: https://www.loopcloud.com/cloud/features
- XLN XO similarity space: https://support.xlnaudio.com/hc/en-us/articles/16920363887645-Interface-Overview
- Soundly local search and collections: https://getsoundly.com/
- Waves COSMOS: https://www.waves.com/plugins/cosmos-sample-finder
- iZotope RX: https://www.izotope.com/products/rx-advanced
- Steinberg SpectraLayers: https://www.steinberg.net/spectralayers/
