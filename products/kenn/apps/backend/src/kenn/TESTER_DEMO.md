# KENN Tester Demo

Use this when sharing KENN without sending code.

## Start the local demo

From the repo root:

```bash
cd /path/to/Audio_Too
source .venv/bin/activate
./scripts/run_kenn_tester_demo.sh
```

Leave that terminal open.

## Create the public KENN link

In a second terminal:

```bash
./scripts/kenn_tester_tunnel.sh
```

Wait for the `https://...trycloudflare.com` URL. That URL points directly to the KENN tester page.

For a stable domain-backed URL, use the named tunnel guide in `docs/KENN_PERMANENT_DEMO.md`.

## What to send testers

```text
Here is the KENN tester demo:
<paste Cloudflare URL>

Try either:
- Ask a production, Ableton, mixing, mastering, or game-audio question.
- Upload a WAV in Mix Review for level, dynamics, stereo, and translation notes.

After each answer or review, please mark Useful or Needs work and leave a short note if something feels wrong or missing.
```

## Review tester feedback

```bash
python3 scripts/kenn_feedback_report.py
```

For machine-readable output:

```bash
python3 scripts/kenn_feedback_report.py --json
```

## Turn feedback into repairs

List feedback that testers marked as Needs work:

```bash
./scripts/kenn_feedback_repair.py list
```

Show one item:

```bash
./scripts/kenn_feedback_repair.py show <feedback-id>
```

Create a draft repair note:

```bash
./scripts/kenn_feedback_repair.py draft <feedback-id>
```

Edit the generated note in `KENN/Training_Data_Notes/`. Replace the placeholders with a clean production note, then validate it:

```bash
./scripts/kenn_feedback_repair.py validate <feedback-id>
```

Approve the edited note, rebuild KENN, and retest the original question:

```bash
./scripts/kenn_feedback_repair.py approve <feedback-id> --build --retest
```

## Draft knowledge from reviews and feedback

Recent Mix Review session reports and Needs work feedback can be turned into draft KENN notes:

```bash
./scripts/kenn_knowledge_candidates.py
```

Write draft notes into `KENN/Training_Data_Notes/`:

```bash
./scripts/kenn_knowledge_candidates.py --write
```

Review each generated draft, replace rough placeholders where needed, change `Status: Draft` to `Status: Approved`, then rebuild:

```bash
./ableton build
```

## Check demo readiness

```bash
./scripts/kenn_demo_doctor.py
```

To check a public tunnel:

```bash
./scripts/kenn_demo_doctor.py --url https://your-link.trycloudflare.com
```

## Upload safety

The tester server is scoped to KENN on port `8090` and includes:

- WAV upload size limit from Mix Review Lab (`150 MB`)
- Lightweight rate limits for chat, suggestions, feedback, reports, and WAV analysis
- Public saved-reference/history endpoints disabled
- A visible upload privacy note in the Mix Review form

Clean old uploaded WAVs and reports with a dry run first:

```bash
./scripts/kenn_cleanup_mix_reviews.py --days 14
```

Delete matching old reviews only after reviewing the dry run:

```bash
./scripts/kenn_cleanup_mix_reviews.py --days 14 --yes
```

## What is included

- KENN chat
- Mix Review WAV analysis
- Clear Mix Review sections: Fix first, Fix next, Leave alone, Listening checks
- Full Session Report in each Mix Review HTML report
- Per-track KENN memory from the latest Mix Review session report
- Latest Mix Review context carried into follow-up chat questions
- AudioGen loop/full-song controls and recent render history
- Tester feedback capture for answers and mix reviews
- Knowledge candidate drafting from real reviews and tester feedback
- Approved notes for vocals, 808 translation, distorted masters, harsh hats, game-audio loudness, and mix-review revision priorities
- Upload privacy note, endpoint rate limits, and cleanup tooling

## What is intentionally hidden

- Dashboard/admin pages
- Saved reference management
- Recent review history
- Internal business tools

## Stop sharing

Press `Ctrl+C` in the Cloudflare terminal, then press `Ctrl+C` in the Audio_Too server terminal.
