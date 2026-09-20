Type: Game audio implementation
Tags: wwise, unity, soundbank folder, addressables workflow, moving to addressables, import location, auto-defined soundbanks, AkBank, Wwise Picker, player build, packaging
Status: Approved
Source title: Managing SoundBanks
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/public-library/2024.1.8_8893/?id=pg_managing_soundbanks.html&source=Unity
Source version: Wwise Unity Integration 2024.1.8
Reviewed: 2026-07-01

# Wwise Unity Soundbanks and Addressables


Short answer:
Wwise Unity SoundBank folder location, importing, packaging, and loading depend on whether the project uses the Wwise Addressables package. A folder that works without Addressables can fail after moving workflows if Unity does not import or address it correctly. Auto-defined SoundBanks are supported and enabled by default in current integrations; AkBank remains available for explicit bank operations.

Try this:
1. Confirm the Unity integration version and whether the project uses Wwise Addressables.
2. Set the generated SoundBank location according to that workflow; Addressables requires a location Unity can import correctly.
3. Generate banks from the Wwise Picker and inspect the Unity import or Addressables groups.
4. Verify Init and Event dependencies load in a clean player build, not only in the Editor.
5. Use AkBank or custom loading only when the lifecycle is explicit, then test unload and scene transitions.

Why it matters:
A correct Wwise authoring project can still ship missing audio if Unity never imports, addresses, packages, or loads the generated dependencies.

Common mistakes:
- Copying a non-Addressables SoundBank path into an Addressables project.
- Disabling auto-defined banks without replacing their dependency and loading behaviour.

When this does not apply:
Custom Unity build pipelines and older integrations can use different folder and bank strategies. Follow the documentation matching the installed integration.

Related questions:
- Where should Wwise SoundBanks live in a Unity Addressables project?
- Are auto-defined SoundBanks enabled by default in Wwise Unity?
- When should I use AkBank in Unity?
- Why does a Wwise Event work in the Unity Editor but fail in a player build?
