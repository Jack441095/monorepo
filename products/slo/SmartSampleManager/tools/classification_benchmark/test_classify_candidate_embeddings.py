import classify_candidate_embeddings as module


def test_prior_audio_prediction_reads_current_receipt_fields():
    assert module.prior_audio_prediction(
        {"audio_class": "Kick", "audio_confidence": 0.91}
    ) == ("Kick", 0.91)


def test_prior_audio_prediction_reads_legacy_prediction_fields():
    assert module.prior_audio_prediction(
        {"old_audio_class": "Snare", "old_audio_confidence": 0.83}
    ) == ("Snare", 0.83)
