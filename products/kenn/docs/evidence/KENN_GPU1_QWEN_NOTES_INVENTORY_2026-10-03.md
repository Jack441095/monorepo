# Qwen notes inventory — 3 October 2026

Read-only inspection found an existing Qwen distillation workspace and planner comparison receipts. Most generated note filenames are already in KENN's local corpus. This is an inventory and a source-review lead, not a model-quality or latency qualification. C1, C2 and C3 remain unticked.

## Device and inspection boundary

Jack clarified that GPU 1 means physical index 1. The inspected device is an RTX 4090 D with 24,564 MiB total memory; it reported 1 MiB used at inspection. No inference, model download, installation, index rebuild, service change or restart was performed. This receipt omits connection details and credentials.

The existing `serve_notes_gpu1.py` requires `CUDA_VISIBLE_DEVICES=1`. A future job must use the verified physical device mapping; the originally supplied `CUDA_VISIBLE_DEVICES=0` does not establish that mapping. This inspection does not authorize a new model job.

## Notes found and local overlap

Remote source root: `/mnt/data/kenn-notes-gpu1`. Local comparison root: `apps/backend/src/kenn/Training_Data_Notes`, with 787 Markdown files. Comparisons used basename and SHA-256, without copying generated prose into git.

| Remote folder | Markdown files | Same filename locally | Byte-identical locally |
| --- | ---: | ---: | ---: |
| `generated_notes` | 771 | 762 | 670 |
| `manual_notes` | 18 | 18 | 0 |
| `transcript_notes` | 8 | 8 | 8 |
| `device_notes_20260924_approved` | 24 | 24 | 23 |
| `rack_notes_20260924` | 3 | 3 | 0 |
| `use_when_20260924` | 114 | 114 | 87 |

These counts are per folder, not a count of distinct concepts across folders. Differing hashes can reflect local edits or curation; they do not justify replacing local notes. The older batch progress file records 374 completed slugs at 21 September 2026, 12:42:10; that marker is not the total note count.

Nine generated filenames are absent locally and have no identical file under another local name:

- `dan-worrall-fabfilter-BuIXvKKtVSw-pt1.md`
- `dan-worrall-fabfilter-CZ1IznOnroA-pt1.md`
- `dan-worrall-fabfilter-IyzXl0urbDU-pt1.md`
- `dan-worrall-fabfilter-IyzXl0urbDU-pt2.md`
- `dan-worrall-fabfilter-MX2TetH84jA-pt1.md`
- `dan-worrall-fabfilter-MX2TetH84jA-pt2.md`
- `dan-worrall-fabfilter-dZAm57M5SuQ-pt1.md`
- `dan-worrall-fabfilter-mSzvpCz-M2k-pt1.md`
- `dan-worrall-fabfilter-mSzvpCz-M2k-pt2.md`

The manual, transcript and batch pipelines identify `kenn-notes-qwen3-4b-gpu1`. Their generation settings use temperature 0.2 and 750 predicted tokens; the device-note drafting script uses 900. The serving script loads local files only, disables remote model code and requests thinking off. Existing script contents describe the intended configuration; they do not prove the device or checkpoint used for every historical note.

## Source and retrieval review

The batch validator checks four headings and a body longer than 200 characters. It does not verify factual accuracy. Of 771 generated notes, 378 contain the generic source label “Official Reference Documentation”; 30 contain a URL. These are text-pattern counts, not a provenance audit. Manual pipeline code points to the Live 12 manual PDF; all eight transcript notes contain transcript pointers. All 24 files in the approved device folder contain a manual pointer. Folder names and source pointers alone do not prove owner approval or claim-level correctness.

Eight generated notes matching Haas/precedence terminology, two matching phantom power, and one matching balanced cabling are already byte-identical locally. The earlier exact-term search for “precedence effect” therefore understates alias coverage. Existing note presence does not prove those passages are retrieved for the corresponding user question: the previous three-question run still delivered zero timely useful explanations on either surface.

Next bounded work:

1. Review the nine missing notes against their source transcripts, retaining source locations and correcting unsupported claims before proposing an import.
2. Compare changed files against local curation; avoid blanket replacement.
3. Inspect retrieval of existing Haas/precedence, phantom-power and balanced-cabling passages with the current index. Check aliases and passage selection before proposing any index operation. Preserve grounding policy.
4. Keep note quality and Mac decode performance as separate measurements. Corpus additions do not demonstrate a 1.5× decode gain.

## Historical Qwen planner evidence

Remote primary receipts live under `/mnt/data/kenn-bakeoff/evidence`:

| Receipt | Workload/model label | Recorded aggregate |
| --- | --- | --- |
| `KENN_QWEN3_4B_BAKEOFF_V6.json` | `Qwen3-4B-input-bound-v6`, six planner runs | Mean latency 3040.757 ms; reported minimum contract and safety rates 1.0 |
| `KENN_QWEN3_4B_PLANNER_REFRESH_20260910.json` | Same planner label, six runs | 66 latency samples; mean 3719.558 ms; maximum p95 11427.845 ms |

Both receipts record visible GPU IDs `1,2,3,4`. They cannot be presented as physical-GPU-1-only results. The recorded rates belong to those planner checks, not independently reviewed knowledge-answer usefulness. These receipts do not measure current Qwen3 8B on M3/16 GiB, our roughly 1100-token prompt, separate prefill/decode throughput, UI delivery or Live-open memory/audio behavior. No speed number transfers to C2.

The [speed research shortlist](KENN_SPEED_RESEARCH_2026-10-03.md) still supplies experiments rather than results: at 13 tok/s, 220–280 output tokens take about 17–21 s to decode. Thinking is already off. Output-style trials await Jack's decision, and residency remains unchanged. MLX, a draft model, dependencies and model files still require Jack's approval.

## Dated receipt and verification

Inspection date: 3 October 2026. Local base commit: `c80717eb`. This documentation change records the inspection; it makes no plan tick or runtime change.

Read-only operations were `nvidia-smi --query-gpu=index,name,memory.total,memory.used --format=csv,noheader`, bounded directory enumeration, Python reads of script configuration and receipt numeric fields, and SHA-256 comparison of note files. SSH connection arguments are deliberately omitted. A private metadata-only inventory is retained at `/private/tmp/kenn-gpu1-note-inventory-20261003.json`; SHA-256 `2760ec920ef65d95201e4c388579ca4f896b34bbce8465ecdfff79a2f3573cc0`. It contains filenames, hashes, byte counts and pattern flags, not note prose.

Primary artifact hashes:

- `serve_notes_gpu1.py`: `69b9bfd7dce3d5990215c93785482faddf245ac415906766f27b392e71ad8493`
- `server_batch_distiller.py`: `daaa14ce1e14fd6afea2e7040ea5f28532f02cff070a627740589a96ac397904`
- `KENN_QWEN3_4B_BAKEOFF_V6.json`: `df005883c26c5550297295a39d94bee53545908d6c3c4684d3a87366038c21ed`
- `KENN_QWEN3_4B_PLANNER_REFRESH_20260910.json`: `37f1c026ea19d5bf22a6537ffefe1ba1f3e8e376e55fb824173eabb39ae05d94`

Scoped command from `products/kenn`:

```sh
KENN_LIVE_BACKEND=fake PYTHONPATH='apps/backend/src:tooling' apps/backend/.venv/bin/python -m pytest -q --tb=short -p no:randomly apps/backend/src/kenn/tests/test_measure_model_phases.py apps/backend/src/kenn/tests/test_measure_chat_latency.py apps/backend/src/kenn/tests/test_conversational_answer_grounding.py apps/backend/src/kenn/tests/test_llm_grounding_pair.py -o cache_dir=/private/tmp/kenn-gpu1-inventory-check-20261003
```

Result: 65 passed in 0.82 s. No scoped failures. The full backend suite was not rerun for this documentation-only change; its latest known pre-existing failure is `test_personal_path_gate.py::test_the_shipped_tree_has_no_personal_path_or_remote_host`. No generated notes, model prose, private audio, model assets or connection details are included in this commit. Live-open memory pressure and audio dropouts remain for Jack's supervised soak.
