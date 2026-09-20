# PX-H - Synthetic User-Journey Report

## Status

**PASS WITH LIMITATIONS**

The corpus is useful for ranking experiments and finding complexity regressions. It is not human research and must not be presented as such.

## Required Closeout

### SCENARIOS

**135** scenarios: 9 archetypes x 15 tasks.

### ARCHETYPES

**9** synthetic archetypes: beginner producer, intermediate electronic producer, professional producer, mix engineer, sound designer, Ableton power user, large sample-library user, keyboard accessibility user, and NITE DSP company owner.

### BIGGEST FRICTION POINT

The recurring modelled friction is the transition from intent to a trustworthy useful result: search, audition, evidence interpretation, and decision are spread across controls or products. The current SLO keyboard/MAP gap is the clearest concrete implementation failure; the current KENN risk is too many findings without a ranked decision path.

### BIGGEST STEP REDUCTION

The largest modelled reduction was `find_complementary_clap`: approximately 9 current steps to 5 proposed steps per baseline scenario. This is a synthetic comparison only. It supports a human test hypothesis, not a usability claim.

### BEST PROPOSED WORKFLOW

KENN measured issue -> evidence-backed SLO candidate search -> instant audition -> user chooses -> KENN fit check -> user decides. It reduces tool switching while keeping product boundaries and user authority intact.

### WORST PROPOSED FEATURE

`chatbot_first_plugin` grew from approximately 8 to 11 modelled steps and introduced more decisions and context switching. It is the clearest feature to drop or park.

## Corpus Distribution

- Promotion candidates: 81 scenarios.
- Continue R&D: 45 scenarios.
- Drop/Park: 9 chatbot-first scenarios.

The complete machine-readable corpus is [synthetic_corpus.json](../user_journeys/synthetic_corpus.json). The generator is [synthetic_user_journey_lab.py](../user_journeys/synthetic_user_journey_lab.py).

## Friction Metrics

Each scenario records steps, clicks, keystrokes, context switches, decision points, wait milliseconds, and error recovery for current and proposed workflows. These are deterministic estimates. They are useful for comparison because the same assumptions are applied to both sides; they are not observed timings.

## Anti-Features / Things Not To Build

- Chatbot-first plugin UI.
- An always-visible confidence number on every KENN issue.
- A forced ecosystem dashboard that duplicates SLO, KENN, and Thursday surfaces.
- Automatic destructive mix changes without preview, decision, and undo.
- A new MAP mode before keyboard and performance behavior are complete.

## Real Human Testing Backlog

Recruit no one from this programme. A later moderated study should include:

- Beginner and professional producers using 5,000-25,000 sample libraries.
- A mix engineer evaluating KENN evidence and no-action behavior.
- An Ableton power user completing audition-to-drag.
- A keyboard-accessibility user completing search, MAP, audition, and drag without a mouse.

Tasks should include find kick, find complement, use Find Similar, diagnose a harsh chorus, compare a reference, recover a scan failure, navigate a large MAP, reject a KENN proposal, approve a Thursday action, switch locale, and use three instances.

Measure task completion, time to useful result, decision reversals, error recovery, context switches, subjective trust, and observed confusion. Compare top-three issue presentation with all-findings and no-action states. Treat the synthetic corpus as task selection input only.

## Promotion Gate

A workflow can move to production engineering only after human friction is demonstrated, technical path and performance risk are understood, accessibility passes, and the product boundary remains coherent.
