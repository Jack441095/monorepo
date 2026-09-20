# Podcast audio analysis

Spoken-word / podcast analysis and engineering (the specialization — see
`plan.md` §15). Advice-only: it interprets the standard analysis metrics for
*dialogue delivery* and suggests fixes. It applies no DSP.

## Run it on a file

```bash
python scripts/podcast_check.py <audio-file> [--target apple|spotify|mono|youtube] [--html out.html]
```

Decodes the file (wav/mp3/flac via the mix-review decoders), computes metrics,
and prints a readiness report; `--html` writes the shareable report.

## API

```python
from audio_analysis.podcast import analyze_podcast, render_podcast_report_html
report = analyze_podcast(metrics, target="apple")   # metrics = analyze_wav(...)['metrics']
html = render_podcast_report_html(report, title="Episode 12")
```

## What it checks

Loudness on platform target (Apple −16 / Spotify −14 / mono −19 / YouTube),
true-peak + clipping, level consistency (leveling need), low-end rumble,
low-mid mud, sibilance/de-ess, presence/intelligibility, and mono/phase.

## Test corpus (royalty-free)

Fetch a starter set of **public-domain** clips (safe to publish in before/after
case studies) into `data/podcast_test_corpus/` (gitignored):

```bash
python scripts/fetch_podcast_test_corpus.py --count 8
```

Sources, and what each is good for:

| Source | License | Use |
| --- | --- | --- |
| **LibriVox** (via archive.org) | Public domain | Clean read speech — the "known-good" baseline the analyzer should pass. Fetched by the script. |
| **Mozilla Common Voice** (commonvoice.mozilla.org) | CC0 | Messy real-mic recordings — best for testing the *fixing* flags (rumble/noise/level). Needs their download form (not automated). |
| **US Gov / NASA audio** | Public domain | Real spoken word you can publish. |
| **Internet Archive** CC podcasts | CC-BY / CC0 (per item) | Real podcast structure. Check each item's license. |

## Calibration honesty

The band-proportion thresholds in `podcast_analysis.py`
(`PODCAST_BAND_HEURISTICS`) are conservative **heuristics**, not calibrated —
`analyze_podcast(...)["calibrated"]` is `False`. Calibrate them against a real,
rights-cleared dialogue corpus before making accuracy claims (same no-faked-data
discipline as the mix listening benchmark).
