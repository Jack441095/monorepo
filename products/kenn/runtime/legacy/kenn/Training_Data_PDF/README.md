# Training PDFs (local only)

PDF manuals are **not stored in git** (except the small generated checklist). After clone:

```bash
# EBU standards + any catalog URLs (skips files you already have)
./ableton download-pdfs --category standards

# Optional: Live 11 manual from Ableton CDN (~90 MB)
./ableton download-pdfs --category ableton

# Your own Live 12 manual — export from Live Help or your Ableton account
# Save as: live12-manual-en.pdf

# Optional guides you own (e.g. Beginner Ableton Live Tips.pdf)

# Regenerate the small in-repo checklist, then build the search index
./ableton build-checklist
./ableton build
```

See `docs/PDF_AND_SOURCE_COLLECTION.md` and `Training_Data_Sources/pdf_sources.json` for the full catalog.
