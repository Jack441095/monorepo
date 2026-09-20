# MIDI Routing and External Sync

Type: Recording workflow
Tags: midi, routing, external instrument, midi out, midi in, sync, clock, ableton link, rewire, hardware, ableton
Status: Approved
Source: Ableton Live 12 Manual
Reviewed: 2026-07-01

Short answer:
MIDI in Live routes from a physical or virtual input to a MIDI track, which then feeds a software instrument or sends MIDI out to hardware. The External Instrument device handles hardware synth routing — it sends MIDI out and returns audio in a single rack. Ableton Link syncs Live's tempo with other devices on the same network wirelessly.

Try this:
1. For a hardware synth: create an Audio track and a MIDI track. On the MIDI track, set MIDI To to your interface's MIDI output port and channel. On the Audio track, set its input to the interface channel where the synth audio returns.
2. Simpler alternative: use the External Instrument device on a single MIDI track. It handles MIDI out and audio return in one device, avoiding the two-track setup.
3. For clock sync out (to a drum machine or sequencer): Preferences → Link / Tempo / MIDI → MIDI tab → set your MIDI output port to Sync = On. Live will send MIDI clock.
4. For clock sync in (Live following external hardware): set a MIDI input port to Sync = On. Press the EXT button in the transport bar. Live's tempo now follows the incoming clock.
5. For wireless tempo sync between apps or machines: enable Ableton Link in Preferences → Link / Tempo / MIDI. Any Link-enabled app on the same Wi-Fi will lock to the same tempo and beat phase.
6. To route MIDI between tracks internally: set the MIDI To of one track to another track name. Useful for feeding arpeggiators or effects into an instrument on a different track.

Why it matters:
Hardware synths, drum machines, and modular rigs need explicit MIDI routing and audio return paths. Getting this wrong means either no sound, latency offset, or clock drift.

Common mistakes:
- Forgetting to set latency compensation for hardware synths — go to Preferences → Audio and set Hardware Latency to the round-trip delay.
- Sending MIDI clock while also having EXT mode on — creates a clock loop.
- Not selecting the correct MIDI channel — hardware synths default to channel 1 but may be set differently.

When this does not apply:
Software instruments on internal tracks don't need MIDI routing configuration — they receive MIDI directly from the track's input.

Related questions:
- How do I connect a hardware synth to Ableton?
- How do I sync Ableton to a drum machine?
- What is Ableton Link?
- How do I send MIDI clock from Ableton?
- How do I route MIDI between tracks in Ableton?
