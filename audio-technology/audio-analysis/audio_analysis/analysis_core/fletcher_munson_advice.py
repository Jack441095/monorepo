"""Psychoacoustic mix advice engine based on ISO 226:2003 equal-loudness contours."""

from __future__ import annotations


def fm_mix_critique(
    metrics: dict, perceived: dict, flags: list[dict], phon_level: float = 60.0
) -> list[str]:
    """Generates detailed psychoacoustic mix critique advice based on equal-loudness contours."""
    advice: list[str] = []
    
    # Extract perceived band shares
    sub = perceived.get("sub", 0.0)
    bass = perceived.get("bass", 0.0)
    low_mids = perceived.get("low_mids", 0.0)
    presence = perceived.get("presence", 0.0)
    
    # 1. Monitoring Level Advice
    if phon_level < 50.0:
        advice.append(
            f"At a quiet listening level ({int(phon_level)} phon), human hearing is naturally less sensitive to the extreme low end. "
            f"Avoid boosting sub-bass to compensate for this physical roll-off; check your low-end balance at a louder level first."
        )
    elif phon_level >= 75.0:
        advice.append(
            f"At a loud monitoring level ({int(phon_level)} phon), your ears perceive low frequencies and highs much more linearly. "
            f"Be careful not to over-compress the mids or let the sub-bass overwhelm your master headroom."
        )
        
    # 2. Perceived Low-End vs Presence Balance
    low_end = sub + bass
    if low_end < 0.06 and presence > 0.28:
        advice.append(
            f"Perceived balance at {int(phon_level)} phon is top-heavy (Low-End: {low_end:.1%}, Presence: {presence:.1%}). "
            f"Your mix may sound brittle or fatiguing. Consider reinforcing the bass guitar or kick body."
        )
    elif low_end > 0.40 and presence < 0.12:
        advice.append(
            f"Perceived balance at {int(phon_level)} phon is bottom-heavy (Low-End: {low_end:.1%}, Presence: {presence:.1%}). "
            f"This can mask details in the vocal and snare. Try high-passing non-bass elements or boosting presence slightly."
        )
        
    # 3. Specific Band Perceived Extremes
    if presence > 0.35:
        advice.append(
            f"Perceived Presence ({presence:.1%}) is very high. Around {int(phon_level)} phon, the ear is highly sensitive to 2-6 kHz. "
            f"This can lead to listener fatigue. Watch out for sharp vocal sibilants or piercing synthesizer/guitar tones."
        )
    elif presence < 0.08:
        advice.append(
            f"Perceived Presence ({presence:.1%}) is low. Lead elements might feel distant or buried in the mix. "
            f"Try a gentle presence boost or clear low-mid masking to bring lead elements forward."
        )
        
    if low_mids > 0.25:
        advice.append(
            f"Perceived Low-Mids ({low_mids:.1%}) are thick. This range (150-400 Hz) easily clouds the mix. "
            f"Try dynamic EQ attenuation on pad sounds or reverbs to free up breathing room."
        )
        
    if sub > 0.15:
        advice.append(
            f"Perceived Sub-Bass ({sub:.1%}) is prominent. Sub-bass energy carries high power but low audibility at lower volumes. "
            f"Ensure your sub elements (below 60 Hz) are clean, mono-compatible, and tightly controlled."
        )
        
    return advice


def fm_frequency_repair_map(
    metrics: dict, perceived: dict, phon_level: float = 60.0
) -> list[dict]:
    """Generates suggested EQ repair moves based on equal-loudness contours."""
    repairs = []
    
    sub = perceived.get("sub", 0.0)
    presence = perceived.get("presence", 0.0)
    low_mids = perceived.get("low_mids", 0.0)
    
    if sub < 0.02 and phon_level < 50.0:
        repairs.append({
            "band": "sub",
            "suggested_move": "Add low-frequency harmonics",
            "details": "Sub-bass is almost imperceptible at quiet monitoring levels. Use subtle saturation on the bass to add higher harmonics (e.g. 100-200 Hz) that are easier to hear.",
            "priority": "watch"
        })
        
    if presence > 0.32:
        repairs.append({
            "band": "presence",
            "suggested_move": "Dynamic EQ cut (2.5 kHz)",
            "details": "Perceived presence is forward. Apply a dynamic EQ cut of 1.5 to 2.5 dB around 2-4 kHz to smooth out vocal or guitar harshness.",
            "priority": "watch"
        })
        
    if low_mids > 0.22:
        repairs.append({
            "band": "low_mids",
            "suggested_move": "High-pass effect returns / cut pads (250 Hz)",
            "details": "Perceived low-mids are masking the mix. High-pass delay/reverb returns at 150-200 Hz and check for overlapping instrument bodies.",
            "priority": "watch"
        })
        
    return repairs
