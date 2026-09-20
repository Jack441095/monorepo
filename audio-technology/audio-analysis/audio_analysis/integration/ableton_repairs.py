"""Ableton repair templates for Mix Review Lab flags."""

from __future__ import annotations


ABLETON_REPAIR_LIBRARY = {
    "Low headroom": {
        "device_chain": "Utility on groups/master, then limiter ceiling check",
        "move": "Lower group or master gain with Utility until the loudest peak has safe headroom.",
        "target": "Leave roughly -6 dBFS peak headroom for a premaster, or at least avoid true-peak clipping.",
        "check": "Bypass only the Utility after level matching to confirm the balance did not change.",
    },
    "Clipping risk": {
        "device_chain": "Track meters, group meters, limiter/clipper bypass pass",
        "move": "Bypass clippers, saturators, and limiters from the master backwards until the clipping source is found.",
        "target": "No red meters or true-peak overs before export.",
        "check": "Export a short loud section and re-run the review before touching tone.",
    },
    "Low dynamics": {
        "device_chain": "Glue Compressor or Limiter on drum/bus/master",
        "move": "Back off threshold/drive or reduce limiter input by 1-3 dB, then recover level after the A/B.",
        "target": "More punch and crest without making the mix feel weak.",
        "check": "Compare at matched loudness; the revised version should hit cleaner without collapsing transients.",
    },
    "Low-mid build-up": {
        "device_chain": "EQ Eight on dense instruments, vocals, reverbs, and mix bus only if needed",
        "move": "Use a narrow-to-medium bell cut around 150-400 Hz on the source creating the cloud, not every track.",
        "target": "Clearer vocal/snare centre with warmth still intact.",
        "check": "Toggle the cut in context and make sure the mix does not turn thin.",
    },
    "Heavy sub": {
        "device_chain": "EQ Eight and Utility Bass Mono on kick, bass, and low effects",
        "move": "High-pass non-bass tracks, then balance kick and bass below 80 Hz while monitoring in mono.",
        "target": "A controlled sub foundation without masking the groove.",
        "check": "Listen quietly and on small speakers; the bass line should remain readable.",
    },
    "Low presence": {
        "device_chain": "EQ Eight or Saturator on vocal, snare, lead, or parallel presence bus",
        "move": "Add small 2-6 kHz presence or harmonic saturation to the lead element that needs to step forward.",
        "target": "More intelligibility without harshness.",
        "check": "A/B at low volume; the hook or vocal should read faster.",
    },
    "Perceived harshness": {
        "device_chain": "De-esser, Dynamic Tube/Saturator trim, or dynamic EQ-style automation",
        "move": "Tame harsh vocal/cymbal/lead peaks around 2-6 kHz before cutting the whole mix.",
        "target": "Less bite at normal volume while keeping clarity.",
        "check": "Loop the harshest phrase and check headphones plus small speakers.",
    },
    "Bright top end": {
        "device_chain": "EQ Eight shelf, De-esser, or reduced exciter/saturation send",
        "move": "Trim brittle air or sibilance on the source causing it, then check the master only last.",
        "target": "Top end stays open without fizz.",
        "check": "Compare against the reference at matched loudness for 20 seconds, then rest your ears.",
    },
    "Stereo imbalance": {
        "device_chain": "Utility, pan controls, return-track meters",
        "move": "Center-check key elements and reduce one-sided returns or widened layers.",
        "target": "Stable lead, snare, kick, and bass image.",
        "check": "Flip mono on Utility and confirm the centre does not pull left or right.",
    },
    "Mono risk": {
        "device_chain": "Utility mono switch, Utility Bass Mono, reduced wideners",
        "move": "Fold to mono, then reduce phasey wideners or stereo effects on elements that disappear.",
        "target": "Important elements survive mono playback.",
        "check": "Toggle mono during the chorus and watch for vocal, bass, or snare loss.",
    },
    "Very wide sides": {
        "device_chain": "Utility width, mid/side EQ Eight, return-track width trim",
        "move": "Reduce width on side-heavy pads, reverbs, or wideners until the centre locks in.",
        "target": "Wide feel with a dependable centre.",
        "check": "Small speaker and mono checks should keep the main musical idea intact.",
    },
    "Side Bass Mud": {
        "device_chain": "Utility Bass Mono below 120 Hz, EQ Eight side low cut",
        "move": "Mono the low end and remove sub energy from stereo effects/returns.",
        "target": "Low frequencies anchored in the centre.",
        "check": "Mono playback should keep bass weight instead of hollowing out.",
    },
    "Low-End Phase Cancellation": {
        "device_chain": "Utility phase invert, track delay, sample start alignment",
        "move": "Check kick and bass polarity/alignment, then adjust phase or timing until mono low end strengthens.",
        "target": "Kick and bass reinforce instead of cancel.",
        "check": "Use mono monitoring while toggling polarity and tiny timing moves.",
    },
    "Hot Mix": {
        "device_chain": "Master Utility, Limiter, Glue Compressor",
        "move": "Reduce master/input drive and ease limiter gain reduction before making tonal changes.",
        "target": "Cleaner loud sections with room for mastering.",
        "check": "The loudest chorus should feel less squeezed at matched volume.",
    },
    "Low-end heavy balance": {
        "device_chain": "EQ Eight, Utility mono, kick/bass group balance",
        "move": "Balance kick and bass against the vocal/snare before adding more top end.",
        "target": "Low end supports the song without swallowing the midrange.",
        "check": "Reference-match loudness and compare only the chorus low end.",
    },
    "Dark tonal balance": {
        "device_chain": "EQ Eight, Saturator, parallel brightness bus",
        "move": "Bring forward the vocal, snare, lead, or cymbal detail before adding a global high shelf.",
        "target": "Clearer mid/high focus without brittle master EQ.",
        "check": "Low-volume playback should reveal the main hook quickly.",
    },
    "Spiky transients": {
        "device_chain": "Clip gain, Drum Buss transient trim, Glue Compressor, clipper",
        "move": "Control only the loudest hits with clip gain or gentle clipping before bus compression.",
        "target": "Peaks sit closer to the body without dulling the groove.",
        "check": "The meters should jump less while drums still feel alive.",
    },
    "Uneven loudness": {
        "device_chain": "Clip gain, track automation, group Utility automation",
        "move": "Automate section levels before using more compression.",
        "target": "Verses, drops, and choruses transition with intentional level movement.",
        "check": "Listen through the section change without looking at meters.",
    },
}


def ableton_repair_templates(flags: list[dict], metrics: dict | None = None, *, limit: int = 5) -> list[dict]:
    repairs: list[dict] = []
    metrics = metrics or {}
    severity_order = {"high": 0, "medium": 1, "low": 2}
    for flag in sorted(flags, key=lambda item: severity_order.get(str(item.get("severity")), 3)):
        label = str(flag.get("label", "")).strip()
        template = ABLETON_REPAIR_LIBRARY.get(label)
        if not template:
            continue
        repairs.append(
            {
                "flag": label,
                "severity": str(flag.get("severity", "low")),
                "device_chain": template["device_chain"],
                "move": template["move"],
                "target": template["target"],
                "check": template["check"],
            }
        )
        if len(repairs) >= limit:
            break
    if not repairs:
        repairs.append(
            {
                "flag": "Reference listen",
                "severity": "listen",
                "device_chain": "Utility for level matching, Spectrum for a rough visual cross-check",
                "move": "Level-match with a reference and make one taste-based change at a time.",
                "target": f"Preserve the current technical pass around {metrics.get('technical_score', 'n/a')}/100.",
                "check": "Re-upload the revision only after the change still works in context.",
            }
        )
    return repairs
