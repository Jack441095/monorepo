# SLO Filename Token Taxonomy V1

Every risk level below is **measured**, not assumed: each token was scored
against the by-ear corpus — how often does a file containing this token actually
carry the class the token implies?

| token | fires | intended | hit % | what it actually is |
|---|---|---|---|---|
| `bd` | 4 | Kick | **100%** | — |
| `clp` | 6 | Clap | **100%** | — |
| `clap` | 91 | Clap | 97% | — |
| `kick` | 80 | Kick | 89% | — |
| `snare` | 102 | Snare | 87% | — |
| `crash` | 7 | Crash | 86% | — |
| `cymbal` | 12 | Crash | 83% | — |
| `tom` | 11 | Percussion | 82% | — |
| `hat` | 40 | Hi-Hat | 78% | — |
| `fx` | 26 | SFX | 77% | — |
| `impact` | 7 | Impact | 71% | — |
| `foley` | 26 | Foley | 69% | — |
| `rim` | 12 | Rimshot | 67% | — |
| `808` | 29 | 808 | 55% | — |
| `reese` | 10 | Reese Bass | 50% | — |
| `shaker` | 14 | Percussion | 43% | usually Percussion **Loop** |
| `top` | 10 | Top Loop | 40% | half are Hi-Hat Loop |
| `perc` | 58 | Percussion | 29% | usually Percussion **Loop** |
| `snap` | 7 | Clap | **14%** | **Foley** |
| `sub` | 18 | Sub Bass | **11%** | Reese / Synth Bass |
| `loop` | 112 | Loop | 2% | a *specific* loop type |
| `bass` | 30 | Bass | 0% | a *specific* bass type |
| **`sd`** | 8 | Snare | **0%** | **KICK — 6 of 8** |
| `hit` | 6 | Impact | 0% | Foley |
| `chord` | 12 | Chord Loop | 0% | Synth |
| `texture` | 6 | Atmosphere | 0% | — |

## Two kinds of failure, and they are not the same

**Identity error** — the token names the wrong thing entirely. `sd` → Snare is
wrong 100% of the time and six of its eight files are **Kicks**. `snap` → Clap
is wrong 86% of the time. These are dangerous and were **removed from the
shipped detector**.

**Granularity error** — the token names the right *family* at the wrong
resolution. `perc` is usually a Percussion **Loop**; `loop` is a specific kind of
loop. The family claim is useful; the exact claim is not. These keep their family
and lose their exact class.

## Risk levels

| level | tokens | policy |
|---|---|---|
| **low** (≥80%) | bd, clp, clap, kick, snare, crash, cymbal, tom | may contribute an exact class, still needs audio agreement |
| **medium** (50–79%) | hat, fx, impact, foley, rim, 808, reese, and all unmeasured shorthand (snr, sn, kik, hh, chh, ohh, bs, lp) | needs audio agreement |
| **high** (<50%) | shaker, top, perc, snap, sub, loop, bass, sd, hit, chord, texture | family only, **never an exact class**, never auto-rename |

Unmeasured producer shorthand (`snr`, `kik`, `hh`, `chh`, `ohh`) defaults to
**medium**: plausible, but there is no evidence it holds on real libraries, and
inventing a high confidence for it would be the same mistake in a new place.
