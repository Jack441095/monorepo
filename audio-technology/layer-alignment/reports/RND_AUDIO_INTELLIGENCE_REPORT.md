# R&D-A — Audio Intelligence Core Report

## Scope
Read-only audit of the canonical SLO repository and Audio_Too KENN/AutoMix surfaces. No production repository was modified.

## Observed

| Capability | Verified implementation | Consumers / status | R&D disposition |
|---|---|---|---|
| Sample rate and channel handling | SLO `SmartSampleManager/Source/SampleManagerEngine.cpp`; PANNs path normalises to 32 kHz mono, 5 s | SLO classifier; production path | Shared adapter candidate, with explicit channel policy |
| Peak, RMS, crest factor | Audio_Too `business/app/automix_worker.py`, `automix_kenn_explain.py`; SLO DSP fallback uses level-like features | AutoMix/creative mix workflows; SLO fallback | Share definitions, keep product thresholds local |
| Spectral energy / balance | Audio_Too `business/app/automix_worker.py` and reference spectral-match path; SLO acoustic fallback | KENN/AutoMix; SLO classifier | Strongest shared primitive candidate |
| LUFS / loudness | Audio_Too mix and delivery/reporting surfaces; exact implementation varies by workflow | Delivery and mix evaluation | Share measurement contract only after parity test |
| Stereo width, correlation, mono checks | Audio_Too AutoMix reference-width and mono-compatibility paths | KENN/AutoMix | Share channel metrics, retain intervention policy in KENN |
| Transient/onset/BPM | SLO `SampleManagerEngine.cpp::estimateBpmFromAudio`; onset-energy ODF + autocorrelation | Experimental SLO BPM | Product-owned until real-loop validation improves |
| Embedding/classification | SLO `AcousticClassifier` + frozen PANNs CNN10 512-D embedding and linear head | SLO only | Product-owned representation for now |
| OOD/confidence | SLO `AcousticClassifier` centroid cosine gate + temperature-scaled confidence | SLO only | Product-owned; could share calibration utilities later |
| DC, noise floor, silence, pitch, key, chroma, loop analysis | No complete cross-product implementation verified in the audited surfaces | Unverified or product-specific | Gap inventory; do not assume absence from whole workspace |

## Duplication Summary

The clearest duplication is level/spectral/stereo measurement expressed independently in SLO C++ and Audio_Too Python. The duplication is conceptual rather than proven byte-for-byte: data types, sample-rate assumptions, windowing, and thresholds differ. A premature common framework would risk changing frozen SLO behavior.

## Shared core decision

**SHARED CORE: LIMITED**

Best shared primitives:

- `AudioBufferView`-like non-owning view with sample rate and channel count.
- Deterministic peak, RMS, crest factor, DC offset, and silence metrics.
- Windowed spectrum and named band-energy summaries.
- Stereo correlation, mid/side energy, and mono-collapse metrics.
- Versioned feature schema with units, validity, and confidence fields.

Keep product-owned:

- SLO taxonomy, filename evidence hierarchy, classifier head, and OOD gate.
- KENN diagnosis language, severity policy, and any processing recommendation.
- Thursday orchestration and external action policy.

## Biggest duplication

Spectral and level measurement across the SLO C++ classifier fallback and Audio_Too AutoMix/KENN workflows.

## Most valuable new primitive

A versioned, allocation-free `AudioAnalysisSnapshot` contract that carries sample-rate/channel metadata, scalar level metrics, band energies, stereo metrics, and validity flags. It should be implemented first in an isolated compatibility harness, not inserted into production code during this sprint.

## Accuracy and safety note

No shared implementation was promoted. The SLO classifier is frozen and Audio_Too has an active writer. A promotion candidate must first pass cross-language parity fixtures at 44.1/48/96 kHz and mono/stereo, then an audio-thread allocation test.

## Recommendation

**Production promotion: not yet.** Design and parity test a narrow measurement contract next; avoid a giant platform.
