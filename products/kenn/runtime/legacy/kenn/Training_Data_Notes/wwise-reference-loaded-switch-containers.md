Type: Game audio optimization
Tags: wwise, unreal, reference-loaded switch container, switch, memory, streaming, prefetch, map dependency
Status: Approved
Source title: Optimizing Memory Usage with Reference-Loaded Switch Containers
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/public-library/2024.1.8_8893/?id=using_features_reference_load_switch_container.html&source=UE4
Source version: Wwise Unreal Integration 2024.1.8
Reviewed: 2026-07-01

# Wwise Reference-Loaded Switch Containers


Short answer:
Reference-loaded Switch Containers let the Wwise Unreal integration load only media referenced by Switch or State values used in the current map, rather than loading every possible branch when the Event asset loads.

Try this:
1. Identify deep Switch Containers with many mutually exclusive branches.
2. Measure their loaded media and prefetch memory before changing the loading model.
3. Enable reference loading on suitable Events and ensure Unreal assets actually reference the needed Switch values.
4. Verify all required branches in packaged maps, including streamed media and media with prefetch chunks.
5. Compare memory usage, open stream count, load latency, and missing-media warnings before and after.

Why it matters:
Large nested containers can load many resources that a map never uses. Reference loading makes dependency use more granular, including when large music media is streamed.

Common mistakes:
- Enabling reference loading without creating engine references for all runtime Switch values.
- Assuming streamed files have no memory cost when they use prefetch chunks.

When this does not apply:
This feature is specific to supported Switch Container Events and integration workflows. Confirm compatibility for the project's Wwise and Unreal versions.

Related questions:
- Why does one Wwise Switch Container load every surface sound?
- Can reference-loaded Switch Containers reduce prefetch memory?
- Why is a referenced Wwise Switch branch missing in a packaged map?
- Does streaming remove all memory cost from a Wwise Switch Container?
