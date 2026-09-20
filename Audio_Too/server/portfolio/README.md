# Portfolio

This folder contains the standalone portfolio content shown from the hub.

- `portfolio_data.json`: codebase, stats, and audio entries rendered by `/portfolio`.
- `audio/`: drag-and-drop music, mix, master, podcast, and sound design examples (`.wav` preferred).
- `images/`: screenshots, cover art, and project images.

Add audio by placing a `.wav` file in `audio/`, then use Dashboard → Portfolio → Refresh → Publish audio.
The dashboard writes the `portfolio_data.json` entry for you. You can still add entries manually:

```json
{
  "title": "Track or project name",
  "description": "Mixed, mastered, produced, or edited by Audio_Too.",
  "src": "/portfolio/audio/my-track.wav"
}
```

Add screenshots or cover art to `images/` and reference them with paths like:

```text
/portfolio/images/project-screenshot.png
```
