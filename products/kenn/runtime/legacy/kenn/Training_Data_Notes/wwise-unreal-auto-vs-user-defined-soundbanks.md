Type: Game audio implementation
Tags: wwise, unreal, auto-defined soundbanks, user-defined soundbanks, packaging, memory, event assets
Status: Approved
Source title: Understanding Auto-Defined and User-Defined SoundBanks
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/public-library/2024.1.9_8920/?id=unreal_using_soundbanks_concepts.html&source=UE4
Source version: Wwise 2024.1.9
Reviewed: 2026-07-01

# Wwise Unreal Auto-Defined vs User-Defined SoundBanks


Short answer:
For current Wwise Unreal integrations, start with auto-defined SoundBanks unless the project has a measured reason for manual bank control. Auto-defined banks create one structure bank per Event and keep media external, giving Unreal granular dependency loading. User-defined banks load their included Event structures and media as a unit.

Try this:
1. Confirm whether Enable Auto Defined SoundBanks is active in Wwise Project Settings.
2. Profile a representative level and record bank memory, media memory, load count, and load time.
3. Use auto-defined banks for granular Event-driven loading and simpler dependency management.
4. Consider user-defined banks for deliberately grouped small assets or a proven loading strategy, understanding that requesting one Event can load the entire bank.
5. Test packaged builds, not only Play In Editor, and inspect duplicated or missing media before adopting a hybrid layout.

Why it matters:
Bank strategy changes memory use, packaging, file size, and loading behaviour. A complex manual scheme can introduce duplicated or missing assets without producing a real performance gain.

Common mistakes:
- Applying advice from pre-2022.1 Event-Based Packaging workflows to a current auto-defined integration.
- Comparing only bank file sizes while ignoring external media and simultaneous Event loads.

When this does not apply:
Legacy integrations and projects with custom loading code may require user-defined banks. Verify the Wwise integration version and the engine team's loading contract first.

Related questions:
- Should my Wwise Unreal project use auto-defined SoundBanks?
- Why does loading one user-defined bank use more memory than expected?
- Can Wwise Unreal use auto-defined and user-defined banks together?
- Why is media stored outside an auto-defined SoundBank?
