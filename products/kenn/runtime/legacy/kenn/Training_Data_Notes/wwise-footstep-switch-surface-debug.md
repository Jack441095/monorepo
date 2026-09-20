# Wwise Footstep Switch Surface Debug

Type: Game audio troubleshooting workflow
Tags: wwise, unity, unreal, game audio, footstep, footsteps, switch, switches, surface, material, terrain, animation, event, game object, profiler, trace, audiokinetic
Status: Approved
Source title: Wwise 101 - Using Switches and Profiling Game Syncs
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/courses/wwise101/

Short answer:
If footstep Switches work in Wwise but not in Unity or Unreal, debug the surface data path. The game must detect the material, set the correct Switch on the same footstep game object, then post the footstep Event after the Switch value is set.

Try this:
1. Confirm the Wwise Switch Group and Switch names exactly match the integration names.
2. Verify the game is detecting the surface or physical material correctly: grass, stone, wood, metal, water, carpet, or terrain layer.
3. Set the Switch on the same game object or emitter that posts the footstep Event.
4. Set the Switch before posting the Event; setting it after the Event can leave the previous surface audible.
5. Check animation timing so the Event fires on contact, not during the leg swing.
6. In the Wwise profiler, watch the footstep Event and Switch value together during movement over different materials.
7. Add temporary debug text in the engine showing the current surface and the Switch value being sent.
8. If every surface plays the same sound, inspect Wwise Switch Container assignments before blaming Ableton exports.

Check:
Do not use States for per-footstep surface changes unless the whole game mode or environment changes. Footstep surfaces are usually Switches because each Event chooses a variant based on a local material.

Why it matters:
Footstep bugs are often timing or object-scope bugs. KENN should tell the user to verify the surface trace, Switch assignment, game object, and Event order.

Related questions:
- My Wwise footsteps always play grass in Unity.
- Footstep Switches work in Wwise but not in Unreal. What should I check?
- Should surface footsteps use Switches or States?
