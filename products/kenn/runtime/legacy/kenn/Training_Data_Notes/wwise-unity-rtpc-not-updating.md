# Wwise Unity RTPC Not Updating Or Wrong Scope

Type: Game audio troubleshooting workflow
Tags: wwise, unity, game audio, rtpc, game parameter, setrtpcvalue, game sync, update, not updating, game object, same game object, object scope, global, globally, scope, profiler, audiokinetic
Status: Approved
Source title: Wwise 101 - Using Game Parameters and Profiling Game Syncs
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/courses/wwise101/

Short answer:
If a Wwise RTPC or Game Parameter is not updating from Unity, verify the parameter name, value range, target game object, global vs object scope, update timing, and profiler trace. Treat it as a data-flow bug before changing curves in Wwise.

Global vs same game object:
Use a global RTPC when the value is truly project-wide, such as global music intensity. Use an object-scoped RTPC on the same game object that posts the Event when the value belongs to one emitter, character, vehicle, weapon, or ambience source. If the Event is posted on one game object but the RTPC is set on another, Wwise may receive both calls but the sound will not use the value you expect.

Try this:
1. Confirm Unity is setting the exact RTPC/Game Parameter name expected by Wwise.
2. Check whether the parameter is global or game-object scoped; object-scoped RTPCs must be set on the same object that posts the Event.
3. Clamp or normalize the Unity value into the range the Wwise curve expects, such as 0-100 health or 0-1 intensity.
4. Set an initial value before posting the Event if the sound depends on the RTPC at start.
5. Avoid writing the value once during setup if gameplay changes need continuous updates.
6. In the Wwise profiler, watch the game sync value during gameplay and confirm it changes on the intended object.
7. Check that a State or Switch is not overriding the same volume, filter, or bus behavior in a way that hides the RTPC effect.
8. Give the programmer a tiny test scene: one object, one Event, one RTPC, visible debug value, expected Wwise curve.

Check:
If the profiler shows no RTPC value change, the bug is in Unity naming, scope, timing, or object routing. If the profiler shows the value but the sound does not change, inspect the Wwise curve, target property, bus routing, and competing game syncs.

Why it matters:
RTPC problems often get misdiagnosed as bad sound design. KENN should ask whether the value reaches Wwise before recommending EQ, compression, or a new export.

Related questions:
- My Unity health RTPC is not changing the Wwise sound.
- Should I set a Wwise RTPC globally or on the same game object that posts the Event?
- Should I set an RTPC globally or on a game object?
- Why does my Wwise Game Parameter work in Authoring but not in Unity?
