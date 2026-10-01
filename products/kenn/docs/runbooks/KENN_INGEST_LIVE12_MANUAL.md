# Ingesting the Ableton Live 12 Reference Manual

**Written:** 2026-09-30 · **Task:** C1 · **Status: the Live 11 manual is already in; this is the Live 12 swap**

Live 11's manual is already indexed: **1,436 `official_ableton_manual` chunks**, grounding 16/16. That is the wrong
edition for a Live 12 Suite install, and the Knowledge programme ranks the manual *above* curated notes — so KENN is
currently citing Live 11 documentation for a Live 12 product. Replacing it is a short job.

## The one thing that will silently go wrong

**Name the file exactly `live12-manual-en.pdf`.**

`build_index.py` matches a local PDF to its catalog entry by exact filename:

```python
entry = catalog.get(pdf.name) or {}
```

A renamed PDF **will be read and indexed** — an uncatalogued file defaults to `index_policy: index` — but it will not
get the authoritative class. Verified 30 Sept by calling the two functions with the real catalogue entry and with `{}`,
which is what `build_index.py:460` passes when the filename does not match:

| filename | `should_index_pdf` | `pdf_evidence_class` |
|---|---|---|
| `live12-manual-en.pdf` | `True` | `official_ableton_manual` |
| `Ableton Live 12 Reference Manual.pdf` | `True` | **`reference_document`** |

So you would end up with a larger index, the same `official_manual_chunk_count` it has now, and
`evaluate_ableton_manual_grounding.py` still failing — which looks exactly like the manual being useless rather than
misnamed.

**Do not fix that by editing the catalogue entry.** Adding a name to the catalogue to make the class appear is exactly
the move the plan forbids: the evidence class exists so a document's authority comes from a declaration a human made,
not from its filename.

## The sequence

From `products/kenn`, on the machine that runs the companion. Nothing leaves the Mac; the PDFs sit in the git-ignored
`apps/backend/src/kenn/Training_Data_PDF/`.

**1. Export the PDF from Live.** Live → *Help* → *Ableton Live 12 Reference Manual*, then export/save it as a PDF.

**2. Put it in place under the expected name.**

```bash
cd products/kenn
cp ~/Downloads/<whatever Live named it>.pdf apps/backend/src/kenn/Training_Data_PDF/live12-manual-en.pdf
```

Check it is ignored before going further — it is licensed Ableton material and must never be committed:

```bash
git check-ignore -v apps/backend/src/kenn/Training_Data_PDF/live12-manual-en.pdf   # expect: .gitignore line
```

**3. Rebuild the index.** `--include-local-manuals` is what allows a `local_opt_in` catalogue entry to be read at all;
without it the build prints `Skipping PDF live12-manual-en.pdf: local manual requires --include-local-manuals` and
carries on, which looks like a clean run.

```bash
python3 apps/backend/src/kenn/main.py build --include-local-manuals
```

**4. Qualify it.** This is the gate, and `--require-manual` is what makes it one:

```bash
python3 tooling/scripts/evaluate_ableton_manual_grounding.py --require-manual
```

Exit 0 means the manual is present *and* grounded. Exit 2 means it is not in the active index — check the build output
for the skip line in step 3 before anything else.

**5. Confirm the count moved.** It should be well above today's 1,436, and every case should still select
`official_ableton_manual`:

```bash
python3 -c "
import sys; sys.path.insert(0, 'apps/backend/src')
from collections import Counter
from kenn.core.chat_retrieval import load_chunks
c = load_chunks()
print('total', len(c))
for k, v in Counter(str(x.get('evidence_class') or '') for x in c).most_common(): print(f'  {k or \"(none)\":26} {v}')
"
```

## After it lands

- Re-run the three retrieval fixtures. The describe-it set is the one to watch: it scored **0.752** with the Live 11
  manual, and the plan's bet is that a Live 12 manual closes some of the gap to the 0.983 the device-named questions
  already reach. **If describe-it does not move, that bet is wrong** and the lever stays note wording — say so rather
  than re-approving notes to make a number go up.
- Tick C1's remaining half in the North Star with the new chunk count and the date.

## If something looks wrong

| Symptom | Cause |
|---|---|
| `manual_not_indexed`, exit 2 | `--include-local-manuals` missing, or the build skipped it — read the build output |
| Chunk count unchanged | filename does not match the catalogue entry exactly |
| `git check-ignore` prints nothing | the PDF is **not** ignored; do not commit it, fix `.gitignore` first |
| Grounding passes but recall falls | the manual added text without adding retrievable signal; report it rather than tuning |

## What is already here

- `apps/backend/src/kenn/Training_Data_PDF/live11-manual-en.pdf` — 96,881,315 bytes, 30 Sept. **Keep it** while you
  check the Live 12 one; if the export goes wrong you can rebuild against what already works.
- `download_training_pdfs.py --list --category ableton` shows what the catalogue expects, and `--category ableton`
  without `--list` will re-fetch Live 11's if it ever goes missing. It will not fetch Live 12's — that one is
  `local_opt_in` and has to come out of Live's Help menu.