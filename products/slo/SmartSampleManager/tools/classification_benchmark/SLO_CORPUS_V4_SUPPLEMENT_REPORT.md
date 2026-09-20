# SLO corpus v4 supplement report

Date: 2026-09-11

## Supplement

The granularity, escape-recovery, and domain-label CSVs contributed 185 new
conflict-free, readable files after excluding 1,261 rows already in corpus v3,
8 exact-content duplicates, 20 missing files, and 6 conflicting paths. The
resulting corpus has 1,510 rows and 31 labels.

## Collection-held-out result

| metric | corpus v3 | corpus v4 |
| --- | ---: | ---: |
| eligible classes | 25 | **27** |
| accuracy | 57.01% | 56.49% |
| macro-F1 | 49.37 | 47.55 |
| coverage @90% precision | 24.2% | **25.6%** |
| coverage @95% precision | 15.6% | 13.0% |

The supplement adds useful support for Impact, Bass Reese, Bass Hit, Foley,
and related classes, but the flat centroid model becomes less accurate as the
taxonomy broadens. This is a taxonomy/model-structure finding, not a reason to
discard the labels.

A first family-to-class centroid cascade was also tested on the same
collection-held-out folds. It reached **45.59% accuracy** and **37.54 macro-F1**
across eight seeds, well below the flat v4 incumbent. The family bottleneck is
too lossy in this form: a mistake at family level prevents the specialist from
recovering. Close this hard-cascade route; any future factorised model must be
multi-task or soft-gated and must beat the flat incumbent on the same grouped
protocol before it can affect rename decisions.

### Escape-recovered v4b follow-up

The fixed escape-hatch workflow recovered 9 labels from notes and produced 43
additional full-taxonomy rows beyond the original v4 supplement. The resulting
1,553-row corpus (27 eligible classes, 80 collections) scores **55.71% accuracy**
and **47.73 macro-F1**, with coverage at 95% precision of **13.4%**. This is
useful ground-truth recovery, but it does not improve the incumbent and is not
promoted as a production model. The same hard cascade falls to **44.53% / 37.49**
and remains closed.

A soft version was tested separately: exact-class scores remain primary, with
fixed auxiliary family/form probability bonuses and no hard gate. On v3 the
best fixed arm improved accuracy by only **+0.44pp** (57.01% to 57.45%), below
the +2pp promotion gate. On escape-recovered v4b the best arm improved by
**+0.54pp** and still remained below v3. Keep the factorised fields for
explanation and future multi-task training, but do not replace the incumbent
with this prototype scorer.

Finally, multiple prototypes per exact class were tested to address negative
silhouette classes without changing labels. Two prototypes reduced v3 accuracy
by **1.48pp** and three reduced it by **2.33pp**; v4b showed the same direction.
This closes the centroid-refinement route. The remaining remedy for incoherent
classes is taxonomy repair plus new breadth-first labels, not more centroids.

### New-domain policy audit

An independent OOF audit of 221 eligible v4b supplement rows across 36
collections scored the actual decision paths: audio-only **53.79%** accuracy,
filename override below the audio gate **56.96%**, and trusted-name override
precision **73.71%**. No class clears the 95% auto-action gate on this harder
population. The existing 386 candidate suggestions therefore remain strictly
review-only; this audit does not authorise automatic renaming.

## Decision

Keep v3 as the review incumbent. Do not freeze or deploy a v4 flat model. Use
the v4 labels to build specialist or factorised heads (family/form and FX/bass
subtrees), with separate collection-held-out gates before they can contribute
to rename decisions.
