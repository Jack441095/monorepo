Type: Game audio spatial implementation
Tags: wwise, spatial audio, rooms, portals, diffraction, transmission, room reverb, aperture, spread, obstruction
Status: Approved
Source title: Rooms and Portals Overview
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/library/edge/?id=spatial_audio_roomsportals_apioverview.html&source=SDK
Source version: Wwise SDK 2024.1 documentation reviewed 2026-07-01
Reviewed: 2026-07-01

# Wwise Spatial Audio Rooms and Portals


Short answer:
A Wwise Spatial Audio Room represents an acoustic environment, and a Portal is the opening connecting these environments. The system uses them to model propagation, diffraction, transmission, room coupling, and spatialized reverb through openings.

Try this:
1. Assign each distinct acoustic environment a Room and appropriate Room Auxiliary Bus.
2. Place Portals at real openings, orient and size them correctly, and update their open or closed state from gameplay.
3. Confirm listeners and emitters are assigned to the intended Rooms.
4. Use the Game Object 3D Viewer and Profiler to inspect propagation paths, diffraction, obstruction, wet paths, spread, and aperture.
5. Simplify geometry and validate transitions at doorways before increasing reflection or diffraction complexity.

Why it matters:
Without a correct Room and Portal graph, reverb and occluded sources can jump, leak through walls, or appear from the wrong direction. Portals let adjacent-room energy appear to arrive from the opening.

Common mistakes:
- Treating a Portal as only an on/off volume trigger instead of part of the propagation graph.
- Combining portal obstruction components with Spatial Audio diffraction in a way the integration documentation advises against.

When this does not apply:
Simple games may need only conventional auxiliary sends and obstruction. Spatial Audio complexity should be justified by the scene and platform CPU budget.

Related questions:
- What is the difference between a Wwise Room and Portal?
- Why does adjacent-room reverb come from the doorway in Wwise?
- How do Portal aperture and spread affect Wwise Spatial Audio?
- Why does sound leak through a closed Wwise Portal?
