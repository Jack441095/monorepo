# Wwise Game Audio Basics

Type: Game audio workflow
Tags: wwise, game audio, interactive, sound design, loudness, middleware, audiokinetic
Status: Approved

Short answer:
Wwise is middleware between your game engine and sound assets: you design events (play this sound with these rules), mix on buses, and ship banks the runtime loads. Treat loudness and voice limits as part of design, not an afterthought at master.

Try this:
1. Map gameplay actions to Wwise Events (footstep, UI click, music stinger) instead of calling raw files from code.
2. Use a simple bus tree: Master → SFX / Music / VO / UI, with shared reverbs on aux buses where needed.
3. Set reference loudness early (meters on master bus; align with your platform target and EBU/streaming notes for linear content).
4. Profile voice counts and streaming settings on target hardware before content lock.
5. Build SoundBanks per level or mode; document what each bank contains for the programming team.
6. Keep a linear mix reference (WAV) for music/VO when directors ask for “radio ready” outside the game mix.

Why it matters:
Game audio fails when events are unorganized or buses clip on device. A clear Wwise structure saves iteration time and matches how Audio_Too clients think about delivery—just with interactive rules instead of one static bounce.

Related questions:
- What is the difference between Wwise Events and game objects?
- How do I limit loudness for mobile games?
- Should game dialogue be mixed like podcast speech?
