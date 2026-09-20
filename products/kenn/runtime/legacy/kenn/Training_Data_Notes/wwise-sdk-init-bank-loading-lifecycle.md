Type: Game audio implementation
Tags: wwise, sdk, init bank, loadbank, unloadbank, media, events, game syncs, loading lifecycle
Status: Approved
Source title: Loading Banks; Managing SoundBanks
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/library/2024.1.5_8803/?id=soundengine__banks__loading.html&source=SDK
Source version: Wwise SDK 2024.1.9
Reviewed: 2026-07-01

# Wwise SDK Init Bank and Media Loading Lifecycle


Short answer:
Load the generated Init bank before other SoundBanks because it carries project-wide structures such as bus hierarchy and Game Sync information. Before posting an Event, its structures and required media must be available through the project's chosen explicit or integration-managed loading path.

Try this:
1. Verify the Init bank was generated for the correct platform and language and loaded successfully at startup.
2. Map each gameplay Event to the bank structures and loose or embedded media it requires.
3. Choose one coherent explicit or integration-managed loading strategy; do not mix APIs without understanding their compatibility.
4. Log bank load results and distinguish missing structures, missing media, and a posted Event that produces no active voice.
5. Stop dependent voices before unloading and test reload, language changes, and level transitions.

Why it matters:
Posting an Event is not proof that every referenced structure and media file is ready. Clear lifecycle ownership prevents silent Events and unload races.

Common mistakes:
- Forgetting to regenerate or deploy Init after changing buses, States, Switches, or RTPC definitions.
- Unloading a bank while active Events or media dependencies still rely on it.

When this does not apply:
Unity and Unreal integrations can manage much of this lifecycle automatically. Use their documented asset model unless the project intentionally owns bank loading in code.

Related questions:
- Why must the Wwise Init bank load before other banks?
- Can a Wwise Event post successfully while its media is missing?
- When is it safe to unload a Wwise SoundBank?
- What is the difference between bank structure data and loose media?
