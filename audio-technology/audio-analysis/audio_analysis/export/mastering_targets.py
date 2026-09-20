"""Stage 11.4 — Mastering delivery-context targets.

A small, dependency-free config module defining target loudness/peak specs
for the delivery contexts a mastering handoff commonly needs to target:
``streaming``, ``cd``, ``vinyl``, and ``broadcast``.

Every numeric target below is grounded in a real, citable industry
reference rather than invented. Two kinds of sources are used, and each
target says which kind it is:

  - **Formal standard** — a published spec from a standards body (ITU-R,
    EBU) or format spec (IEC/Red Book). These are not negotiable within
    that context.
  - **Documented industry convention** — a number with no single governing
    body, but that is consistently repeated across mastering-engineer
    references (cited by name below) as the practical target. These are
    marked ``is_formal_standard=False`` so a caller can tell the
    difference between "the law" and "what everyone actually does".

Sources (see each ``MasteringTarget.citation`` for the specific claim):

  1. ITU-R BS.1770-4 — "Algorithms to measure audio programme loudness and
     true-peak audio level". Defines the K-weighted loudness (LUFS/LKFS)
     and true-peak (dBTP) measurement algorithms every target below is
     expressed in.
  2. EBU R128 (2014) — "Loudness normalisation and permitted maximum level
     of audio signals", https://tech.ebu.ch/docs/r/r128-2014.pdf. Defines
     the broadcast target of -23.0 LUFS integrated (+/-0.5 LU tolerance,
     widened to +/-1.0 LU for less predictable live-mixed material) and a
     maximum true peak level of -1.0 dBTP.
  3. Spotify's published loudness-normalization spec
     (https://support.spotify.com/us/artists/article/loudness-normalization/)
     and the cross-platform convergence documented by iZotope's "How to
     master for streaming platforms" guide — streaming platforms (Spotify,
     YouTube, Tidal, Amazon) normalize toward -14 LUFS integrated with a
     -1 dBTP true-peak ceiling (Amazon Music is the one outlier at
     -2 dBTP). Apple Music normalizes to -16 LUFS, applying negative gain
     to anything hotter — -14 LUFS/-1 dBTP is the documented "safe for all
     platforms" cross-platform target, not a single-vendor number.
  4. IEC 60908 ("Red Book") — the Compact Disc Digital Audio format
     specification: 16-bit / 44.1 kHz linear PCM. Red Book itself mandates
     no loudness target at all ("loudness is as mastered") — only the
     encoded sample format. The true-peak DAC-reconstruction ceiling of
     -0.3 dBTP and the -9 LUFS "don't go louder than this or you lose the
     mix" convention are documented industry practice (mastering.to's "CD
     mastering" guide; Disc Makers' "How Many LUFS Should My Master Be?"),
     not part of IEC 60908 itself.
  5. Vinyl cutting conventions — no formal body governs vinyl cutting
     levels (it is an analogue, mechanical process), but the physical
     constraints and the numbers used to work within them are documented
     consistently by mastering/cutting-engineer references (Masterdisk's
     "Mastering For Vinyl", Sage Audio's "Mastering for Vinyl", the
     Critical Listening Lab "Vinyl" cutting-constraints page, and
     Furnace Mfg's vinyl audio-prep guide):
       - Sub-bass/bass content below ~150 Hz is summed to mono because the
         cutting stylus reproduces the L-R *difference* signal as vertical
         (depth) groove modulation; strong out-of-phase bass drives the
         stylus out of the groove ("unplayable" cuts).
       - High frequencies above ~15 kHz get a gentle roll-off, and
         sibilance (~3-10 kHz) gets extra de-essing beyond what a digital
         master needs, because high-frequency energy at high level can
         overheat/mistrack the cutting head.
       - Cut masters run quieter and less limited than a streaming/CD
         master (commonly cited as roughly -14 to -18 LUFS integrated,
         i.e. materially louder headroom than a -9 LUFS CD master) so the
         groove retains enough dynamic range and pitch/depth room to cut
         cleanly — a brickwalled master does not translate to a louder,
         safely-cuttable record, it just forces the cutting engineer to
         turn the whole cut down further.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MasteringTarget:
    """Target loudness/peak/EQ spec for one delivery context."""

    context: str
    integrated_lufs_target: float
    true_peak_ceiling_dbtp: float
    is_formal_standard: bool
    standard_name: str
    citation: str
    tolerance_lu: float | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)
    # Vinyl-specific physical cutting constraints (empty for other contexts).
    mono_below_hz: float | None = None
    high_freq_rolloff_start_hz: float | None = None
    sibilance_deess_band_hz: tuple[float, float] | None = None


STREAMING = MasteringTarget(
    context="streaming",
    integrated_lufs_target=-14.0,
    true_peak_ceiling_dbtp=-1.0,
    is_formal_standard=False,
    standard_name="Cross-platform streaming convention (Spotify/YouTube/Tidal)",
    citation=(
        "Spotify loudness-normalization spec (support.spotify.com/us/artists/"
        "article/loudness-normalization) targets -14 LUFS; iZotope's "
        "'How to master for streaming platforms' documents -14 LUFS / -1 dBTP "
        "as the safe cross-platform target (Apple Music re-normalizes to "
        "-16 LUFS on playback; Amazon Music is the outlier at -2 dBTP)."
    ),
    tolerance_lu=1.0,
    notes=(
        "-14 LUFS/-1 dBTP will not be turned up (risking limiter-added "
        "distortion audible after normalization) or turned down "
        "unnecessarily by any major platform's normalizer.",
    ),
)

CD = MasteringTarget(
    context="cd",
    integrated_lufs_target=-9.0,
    true_peak_ceiling_dbtp=-0.3,
    is_formal_standard=False,
    standard_name="IEC 60908 (Red Book) container + documented CD mastering convention",
    citation=(
        "IEC 60908 (Red Book) mandates only the 16-bit/44.1kHz linear PCM "
        "container -- 'loudness is as mastered', no integrated-loudness "
        "requirement. The -0.3 dBTP true-peak ceiling guards against "
        "inter-sample overs on CD players' oversampling DAC reconstruction "
        "(mastering.to 'Mastering for CD'). -9 LUFS is the documented "
        "convention ceiling before a master audibly loses dynamic range/mix "
        "definition (Disc Makers 'How Many LUFS Should My Master Be?'; "
        "Remasterify 'Mastering with a LUFS Meter')."
    ),
    tolerance_lu=None,
    notes=(
        "Unlike streaming/broadcast, there is no format-level loudness "
        "target for CD -- -9 LUFS integrated is a competitive-loudness "
        "convention, not a Red Book requirement.",
    ),
)

VINYL = MasteringTarget(
    context="vinyl",
    integrated_lufs_target=-16.0,
    true_peak_ceiling_dbtp=-3.0,
    is_formal_standard=False,
    standard_name="Vinyl cutting-engineer conventions (no formal governing body)",
    citation=(
        "Masterdisk 'Mastering For Vinyl' and Sage Audio 'Mastering for "
        "Vinyl' document mono bass below ~150 Hz (the cutting stylus "
        "reproduces L-R difference as vertical groove modulation; "
        "out-of-phase bass at high level de-rails the stylus), a gentle "
        "high-frequency roll-off from ~15 kHz, and extra de-essing in the "
        "~3-10 kHz sibilance band (cutting-head overheating/mistracking). "
        "Furnace Mfg's vinyl audio-prep guide and Gearspace mastering-forum "
        "consensus put a safe pre-master peak around -3 to -6 dBFS/dBTP and "
        "an integrated loudness materially below CD level (roughly -14 to "
        "-18 LUFS) so the cut retains dynamic range instead of forcing the "
        "cutting engineer to turn the whole lacquer down."
    ),
    tolerance_lu=2.0,
    notes=(
        "These are physical, not purely loudness, constraints: a hot vinyl "
        "master does not cut louder, it just gets attenuated by the cutting "
        "engineer -- brickwall limiting is actively counterproductive here.",
        "mono_below_hz, high_freq_rolloff_start_hz, and "
        "sibilance_deess_band_hz below are the constraints a renderer/"
        "delivery pipeline should actually apply for a vinyl-targeted print "
        "(e.g. via the renderer's existing mono_below_frequency DSP call).",
    ),
    mono_below_hz=150.0,
    high_freq_rolloff_start_hz=15000.0,
    sibilance_deess_band_hz=(3000.0, 10000.0),
)

BROADCAST = MasteringTarget(
    context="broadcast",
    integrated_lufs_target=-23.0,
    true_peak_ceiling_dbtp=-1.0,
    is_formal_standard=True,
    standard_name="EBU R128 (2014)",
    citation=(
        "EBU R128 'Loudness normalisation and permitted maximum level of "
        "audio signals' (tech.ebu.ch/docs/r/r128-2014.pdf): Programme "
        "Loudness target -23.0 LUFS integrated, +/-0.5 LU tolerance "
        "(widened to +/-1.0 LU for less predictable/live-mixed material); "
        "Maximum True Peak Level -1.0 dBTP. Both the LUFS and dBTP "
        "measurement algorithms are themselves defined by ITU-R BS.1770-4."
    ),
    tolerance_lu=0.5,
    notes=(
        "US broadcast (ATSC A/85 / the CALM Act) instead targets -24 LKFS "
        "+/-2 dB -- a distinct formal standard, not represented separately "
        "here since this module's 'broadcast' context follows the EBU R128 "
        "figure the task specification names explicitly.",
    ),
)


MASTERING_TARGETS: dict[str, MasteringTarget] = {
    t.context: t for t in (STREAMING, CD, VINYL, BROADCAST)
}


def get_mastering_target(context: str) -> MasteringTarget:
    """Look up a :class:`MasteringTarget` by delivery context name.

    Raises ``ValueError`` (not KeyError) with the valid options listed, so
    a caller building an error response has a usable message directly.
    """
    key = (context or "").strip().lower()
    try:
        return MASTERING_TARGETS[key]
    except KeyError as exc:
        valid = ", ".join(sorted(MASTERING_TARGETS))
        raise ValueError(f"Unknown mastering context '{context}'. Expected one of: {valid}.") from exc


def target_as_dict(target: MasteringTarget) -> dict:
    """Serialize a :class:`MasteringTarget` to a plain dict (for JSON payloads)."""
    return {
        "context": target.context,
        "integrated_lufs_target": target.integrated_lufs_target,
        "true_peak_ceiling_dbtp": target.true_peak_ceiling_dbtp,
        "tolerance_lu": target.tolerance_lu,
        "is_formal_standard": target.is_formal_standard,
        "standard_name": target.standard_name,
        "citation": target.citation,
        "notes": list(target.notes),
        "mono_below_hz": target.mono_below_hz,
        "high_freq_rolloff_start_hz": target.high_freq_rolloff_start_hz,
        "sibilance_deess_band_hz": (
            list(target.sibilance_deess_band_hz) if target.sibilance_deess_band_hz else None
        ),
    }
