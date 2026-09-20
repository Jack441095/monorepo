# KENN Live Suggestion — Max for Live device (Stage L near-term MVP)

Read-only. This device reads a small slice of the current track's live state
(track name, device chain, key parameter values) and asks KENN for a
grounded, cited suggestion — displayed as text inside Ableton. **Nothing
here writes to your session.** You read the suggestion and, if you agree,
you apply it yourself the normal way (drag the fader, change the plugin
parameter). See `docs/AUDIO_MVP_MASTER_PLAN.md` Stage L (Sec.L4/Sec.L5) for
the full design and why the MVP stops there.

## What exists here today

- `live_state_reader.js` — a Max `[js]` object using the LiveAPI to read the
  selected track's name, device chain, and parameter values.
- `live_suggestion_client.js` — a Max `[node.script]` object that takes that
  state, POSTs it to the local server, and outputs KENN's answer.
- The Python side (`business/app/routes/ableton_routes.py`'s
  `/api/ableton/live-suggestion`, backed by
  `audio_analysis.integration.kenn_handoff.explain_live_session_state`) is
  built, tested, and running as part of the normal server — nothing extra to
  set up there.

## What does NOT exist here yet, and needs your own Ableton/Max environment

I (the assistant) cannot run Max or Ableton, so **none of the JS above has
been executed inside a real session** — it's written from Cycling '74's
documented LiveAPI/Node-for-Max conventions, not verified against a live
patch. There is also no `.amxd` device file in this folder: a Max for Live
device is a binary patcher file built inside Max's own patching editor, not
something expressible as a text file I can generate directly. Building the
actual `.amxd` is a short manual step, below.

## Building the device (you'll need Max 8+ and Ableton Live, ~15 minutes)

1. **Start the local server** the device will talk to:
   `cd Audio_Too && python main.py server` (or `./audio-too server`) —
   confirm it's up by visiting `http://127.0.0.1:8090` in a browser.
2. **Create a new Max for Live MIDI or Audio Effect device** (Ableton's
   "Max for Live" browser panel → drag a blank device onto a track, or
   `File > New Max for Live Effect` from within Max).
3. **Add a `[js live_state_reader.js]` object**, pointed at this folder's
   `live_state_reader.js` (either place the file next to the `.amxd` or set
   Max's search path to include this folder). Wire a `[button]` (or a
   `live.text` button styled "Ask KENN") into its inlet so a click triggers
   `bang()`.
4. **Add a `[node.script live_suggestion_client.js]` object**, same folder.
   Run `npm install max-api` inside `studio/m4l/live_suggestion/` first —
   Max 8+ bundles Node itself, but the `max-api` package used by the script
   is not preinstalled.
5. **Wire the `[js]` object's outlet to the `[node.script]` object's
   inlet** (both emit/expect the same `live_state_json` / `error` message
   pattern — Max routes messages by their first symbol automatically when
   using `Max.addHandler`/`outlet(0, "tag", ...)`, no extra routing object
   needed).
6. **Add a `[comment]` or `[live.text]` display object** wired to the
   `[node.script]` object's `suggestion`/`error` outlet messages, so KENN's
   answer shows up in the device's UI.
7. **Test it**: select a track with a device or two already loaded, click
   the button, and confirm you see a real KENN answer (or an honest "not
   confident" message if the retrieval is a `weak_match`) within a couple of
   seconds. If you get "Could not reach the local server," confirm step 1's
   server is actually running and listening on 8090.
8. Save the device as `KENN Live Suggestion.amxd` in this folder once it
   works, so it's checked in and reproducible.

## Known open questions (flagged, not resolved, per this plan's own
"don't assert what you haven't checked" rule)

- Exact reliability of Node for Max's HTTP client under real DAW load isn't
  benchmarked anywhere in this codebase.
- The property names used in `live_state_reader.js` (`"name"`, `"devices"`,
  `"parameters"`, `"value"`) come from Cycling '74's documented LOM schema
  but haven't been confirmed against your actual Live 12.1 installation —
  if a property comes back empty/undefined, check Cycling '74's own LOM
  reference for the exact property name on your Live version.
- If you ever want to distribute this device to someone other than
  yourself, check Max's current commercial-distribution terms first (not
  relevant for your own local use, which is the only thing this MVP is
  built for).
