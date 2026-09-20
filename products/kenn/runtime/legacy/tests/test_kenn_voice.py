from kenn.core.voice_persona import format_kenn_voice


def test_kenn_voice_removes_pleasantries():
    """Verify format_kenn_voice strips pleasantries and greeting/small talk."""
    raw_answer = "Sure thing! Here you go. Use a shorter release time of 50ms. Hope this helps!"
    payload = {
        "confidence": "high",
        "grounding": {"score": 95},
        "sources": [{"label": "Release settings", "source": "settings.md"}],
    }
    
    formatted = format_kenn_voice(raw_answer, payload)
    assert "Sure thing" not in formatted
    assert "Here you go" not in formatted
    assert "Hope this helps" not in formatted
    assert formatted == "Use a shorter release time of 50ms."


def test_kenn_voice_uncertainty_phrasing():
    """Verify uncertainty phrasing is triggered when grounding score is low (< 90)."""
    raw_answer = "Apply a 2 dB cut around 250 Hz to clear mud."
    payload = {
        "confidence": "low",
        "grounding": {"score": 82},
        "sources": [{"label": "Equalization Tips", "source": "eq.md"}],
    }
    
    formatted = format_kenn_voice(raw_answer, payload)
    # Expected uncertainty phrase: "I'm 82% confident this is correct based on Equalization Tips; the manual states: Apply a 2 dB cut around 250 Hz to clear mud."
    assert "I'm 82% confident this is correct based on Equalization Tips" in formatted
    assert "the manual states: Apply a 2 dB cut around 250 Hz to clear mud." in formatted


def test_kenn_voice_length_contract():
    """Verify voice output length contract restricts word count to < 85 words and appends suffix."""
    # Construct a long text with 100+ words
    long_answer = (
        "Set the threshold to -18 dB. Set the ratio to 4:1. Set the attack time to 15 ms. "
        "Set the release time to 100 ms. Make sure the sidechain is filtered at 120 Hz. "
        "Verify the gain reduction is between 2 and 4 dB. This will ensure transparency. "
        "If you exceed 4 dB of gain reduction, you may hear audible pumping. "
        "Pumping can be avoided by backing off the threshold or lowering the ratio. "
        "Always listen at matched loudness. Equal loudness comparison is critical for mixing. "
        "Never trust uncalibrated monitors. Calibration ensures accuracy."
    )
    payload = {
        "confidence": "high",
        "grounding": {"score": 95},
        "sources": [{"label": "Compression Guide", "source": "comp.md"}],
    }
    
    formatted = format_kenn_voice(long_answer, payload)
    words = formatted.split()
    assert len(words) < 85
    assert formatted.endswith("Tell me more for additional details.")
