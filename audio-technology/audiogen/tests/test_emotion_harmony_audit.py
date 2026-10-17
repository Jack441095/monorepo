def test_emotion_harmony_audit_is_clean():
    """
    Regression test: emotion harmony data should remain internally consistent.

    This catches accidental chord-symbol typos, empty pools, and pop/EDM harmony
    budget regressions that can make the emotional profiles sound "off".
    """
    from data.music_data import EMOTIONS
    from data.audit import audit_all_emotions

    issues = audit_all_emotions(EMOTIONS)
    assert issues == []

