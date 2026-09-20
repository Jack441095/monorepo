# KENN

**Kernel Engineering Neural Network** — local retrieval assistant for **audio engineering** advice with an **Ableton Live** specialty. Code lives in `KENN/`; use `./ableton` (or `./audio-too ableton`) as the launcher.

A small local Ableton help chatbot that answers from PDF source material.

This first version is retrieval-based, not a trained language model. It reads your PDFs, builds a searchable local index, and returns relevant source-backed notes. That is the right starting point before training or fine-tuning anything.

## Folder Structure

```text
Training_Data_PDF/   PDF source files
Training_Data_Notes/ Markdown tips and workflow notes
Training_Data_Sources/ Source attribution records
Training_Data_Transcripts/ Local transcript files, not indexed directly
build_index.py       Builds the local pure-Python knowledge index
chat.py              Terminal chatbot
data/index/          Generated search index
chats/               Optional saved chat logs
```

## Setup

From this folder:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Improve Answer Quality

The chatbot is retrieval-based: it only answers well when the index contains **focused, approved** notes for that topic.

If a question returns drum or manual noise instead of the right workflow (for example “process bass”):

1. Add a note in `Training_Data_Notes/` with clear `Tags:` (`bass`, `sub`, `saturation`, etc.).
2. Fill in **Short answer** and **Try this** in your own words (see `bass-processing-basics.md` for a template).
3. Set `Status: Approved` (draft notes are not indexed).
4. Rebuild: `./ableton build`
5. Ask with specific device names when possible (“Saturator on sub bass”, “sidechain bass to kick”).

Ranking now prefers notes whose tags/topics match the question and downranks unrelated drum content when you ask about bass, vocals, and similar topics.

## Improve The Data

Add your own `.md` notes in `Training_Data_Notes/`. The bot gives these practical notes priority when they match the question.

Good note format:

```text
# Topic Name

Type: Beginner explanation
Tags: topic, related terms
Status: Draft
Source: Manual, standard, transcript, or Audio_Too studio practice
Reviewed: YYYY-MM-DD

Short answer:
One or two plain-English sentences.

Try this:
1. A practical step.
2. Another practical step.

Why it matters:
A short explanation of when or why to use it.

Common mistakes:
- A tempting wrong move and the symptom it causes.

When this does not apply:
The exception or missing evidence that should trigger a follow-up question.

Related questions:
- A useful follow-up question
```

Run `python main.py build` again after adding or editing notes.

## Research Sources

Use source tracking for YouTube videos, tutorials, articles, and other references. This stores attribution and creates a note template, but it does not scrape transcripts. Write the production lesson in your own words.

Save a source:

```bash
./ableton add-source "https://youtube.com/watch?v=..." "title: Sound Design Tip" "creator: Virtual Riot"
```

Create a note from that source:

```bash
./ableton new-note "Resampling Bass Sound Design" "source: <source-id>" "tags: resampling, bass, sound design"
```

List saved sources:

```bash
./ableton sources
```

## Web tips (curated fetch)

You can import **public web pages you choose** into draft notes. This is not a bulk scraper: it checks `robots.txt`, blocks YouTube/social hosts, saves a text cache, and creates a **Draft** note you must review and approve.

Fetch one article:

```bash
./ableton fetch-web "https://www.ableton.com/en/blog/your-article-slug/" "title: My Tip Title" "creator: Ableton" "tags: mixing, workflow"
```

Curated pack (edit `Training_Data_Sources/web_sources.json` first):

```bash
./ableton list-web-pack
./ableton import-web-pack "limit: 3"
```

Or use **Transcript Review** in the control panel: **Fetch web page → draft note** / **Import web pack**.

After reviewing drafts:

```bash
./ableton approve-note your-draft.md
./ableton build
```

**Important:** Only fetch pages you are allowed to use. Rewrite notes in your own words before approving. Category/listing pages are poor sources — use specific tutorial articles.

Put transcript files in `KENN/Training_Data_Transcripts/`, or pass a path to a transcript anywhere on your machine. Supported input is plain `.txt` or `.vtt`-style text.

Create a basic note draft from a local transcript file you have permission to use:

```bash
./ableton import-transcript "Training_Data_Transcripts/my-transcript.txt" "title: Resampling Bass Notes" "source: <source-id>" "tags: resampling, bass, sound design"
```

Create a more formal educational note draft from the transcript:

```bash
./ableton paraphrase-transcript "Training_Data_Transcripts/my-transcript.txt" "title: Formal Resampling Lesson" "source: <source-id>" "tags: resampling, bass, sound design"
```

Process every unprocessed transcript in the transcript folder:

```bash
./ableton paraphrase-all-transcripts "creator: Virtual Riot" "tags: sound design, drums, ableton"
```

Generated transcript notes start as `Status: Draft`, so they are not indexed into the chatbot until you approve them. This keeps messy or inaccurate transcript drafts out of the agent.

Check the pipeline:

```bash
./ableton transcripts
```

Approve a reviewed note:

```bash
./ableton approve-note virtual-riot-delay-fade-mode.md
```

### Train the chatbot from local transcripts

The chatbot is **not** a neural model you fine-tune. “Training” means: **paraphrase transcripts → review → approve → rebuild the search index**.

Improved professional paraphrasing (filters YouTube chatter, builds real Short answer / Try this steps):

```bash
./ableton paraphrase-all-transcripts "creator: Virtual Riot" "tags: sound design, ableton" "force: yes"
./ableton train-chatbot "force: yes" "approve: yes" "build: yes"
```

Or step by step:

```bash
./ableton paraphrase-transcript "Training_Data_Transcripts/my-transcript.txt" "title: Delay Fade Mode" "force: yes"
./ableton approve-note my-note.md
./ableton build
```

Import suggested Ableton blog URLs:

```bash
./ableton import-web-pack "suggested: yes" "limit: 4"
```

Then rebuild:

```bash
./ableton build
```

This stores the transcript separately and creates a structured note with attribution, useful terms, key ideas, practical steps, and a formal explanation. The raw transcript is not added directly to the searchable chatbot notes.

## Build The Knowledge Base

```bash
python main.py build
```

This reads every `.pdf` in `Training_Data_PDF/` and creates the local index in `data/index/`.

## Ask A Question

One question:

```bash
python main.py ask "How do I freeze and flatten a track in Ableton Live?"
```

Interactive chat:

```bash
python main.py chat
```

You can also run `python main.py` to start interactive chat.

Save chat logs:

```bash
python main.py chat --save
```

## Web Chat

Start the local web app:

```bash
python main.py web
```

Then open:

```text
http://127.0.0.1:8090
```

From the top-level `Audio_Too` folder, you can also run:

```bash
./ableton web
```

## Desktop Companion (macOS)

For a native desktop window around the local KENN experience—including chat,
Mix Review, multi-stem AutoMix uploads, job status, and delivery downloads—build
and open the companion:

```bash
studio/kenn/desktop_companion/build_macos_app.sh
open "studio/kenn/desktop_companion/dist/KENN Desktop Companion.app"
```

It connects to an already-running KENN server or starts one from this checkout.
It also starts one local AutoMix worker for desktop uploads. If the app is closed
during a render, reopening it uses the same desktop worker identity so any
recoverable claimed job can be resumed by that worker. The companion is a local
test/control surface; DAW bus metering, automation, and host undo remain in the
VST3/AU plug-in.

## Current Design

- Runs locally.
- Uses your PDFs as the knowledge source.
- Gives source file and page references.
- Uses a pure-Python BM25-style search index, so it avoids sklearn architecture issues.
- Uses retrieval first and can optionally use a configured local or
  OpenAI-compatible LLM for rewrites and structured planning.
- Keeps deterministic project/audio measurements separate from AI explanation.

## Sensible Next Upgrades

1. Add more source PDFs and notes.
2. Add a small web chat UI.
3. Add better chunking by manual sections/headings.
4. Add a local embedding model for stronger search.
5. Add a local small LLM later, using the retrieved notes as context.
