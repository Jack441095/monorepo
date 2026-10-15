"""Answer current-insert analysis requests using validated local feature frames.

Interpretation stays deterministic for this slice so unavailable routing or
audio cannot become invented measurements. The general language model remains
available for engineering knowledge outside these current-session requests.
"""

from __future__ import annotations

import re
from typing import Any

from kenn.core.live_analysis_host import AbletonAnalysisHost
from kenn.core.live_analysis_binding import answer_insert_binding, check_binding, wants_insert_binding
from kenn.core.live_paired_analysis import answer_paired_analysis, wants_paired_analysis
from kenn.plugin_handoff import live_context_summary


def wants_insert_grade(question: str) -> bool:
    """Recognise explicit insert targets; leave mix uploads and grading how-tos alone."""
    return bool(re.match(
        r"\s*(?:please\s+)?(?:(?:can|could|would) you\s+)?(?:grade|rate)\s+"
        r"(?:(?:this|current|selected)\s+(?:track|channel|bus|insert)\b|"
        r"(?:track|channel)\s+\d+\b|(?:the\s+)?(?:kick|bass|drums?|vocals?|synth|master)\b)",
        question.casefold(),
    ))


def wants_track_analysis(question: str) -> bool:
    """Recognise session analysis, leaving generic how-to questions to retrieval."""
    lowered = question.casefold()
    if re.match(r"\s*(?:how (?:do|can|should|to)|what is|explain)\b", lowered):
        # General engineering questions do not opt into session diagnosis.
        return False
    return wants_insert_grade(question) or wants_paired_analysis(question) or bool(re.search(r"\b(?:analyse|analyze|analysis|masking)\b|what should i change|(?:is|does).*sidechain", lowered))


def answer_track_analysis(question: str, *, session_id: str, plugin_session_id: str = "", host: AbletonAnalysisHost | None = None) -> dict[str, Any] | None:
    """Return evidence, advice, and at most one approval card; never execute it."""
    if not wants_track_analysis(question) and not wants_insert_binding(question):
        # Existing chat routes handle knowledge and explicit Live commands.
        return None
    reply: dict[str, Any] = {
        "ok": True, "route": "live_track_analysis", "answer_mode": "live_analysis",
        "sources": [], "found": True, "confidence": "unknown",
        "status": "analysed", "requires_confirmation": False, "proposal": None,
        "confirmation_token": "",
    }
    grade_request = wants_insert_grade(question)
    adapter = host or AbletonAnalysisHost()
    # Fresh topology can take time to read. Grade the window after that read so
    # a Pause, reset or expiry while waiting cannot publish an earlier score.
    state = adapter.observe() if grade_request else None
    context = live_context_summary(plugin_session_id or session_id, grade_owner=session_id if grade_request else "")
    if context and (context.get("conversation_id", "") not in ("", session_id)
                    or grade_request and (not session_id or context.get("conversation_id") != session_id)):
        # Legacy snapshots have no owner; continuous native publishers do. Never
        # borrow a known sibling's evidence or prepare a card from another chat.
        reply.update(status="clarification_required", answer="Selected insert belongs to another conversation. Open KENN from that insert and select its audio source again.")
        return reply
    if wants_insert_binding(question):
        return answer_insert_binding(question, owner=session_id, insert=plugin_session_id or session_id,
                                     state=adapter.observe(), context=context, adapter=adapter)
    if not grade_request and wants_paired_analysis(question):
        return answer_paired_analysis(question, owner=session_id, state=adapter.observe(), adapter=adapter)
    analysis: dict[str, Any] = {"schema": "kenn.live_track_analysis.v1", "measured": {}, "session": {}, "interpretations": [], "recommendations": [], "unavailable": [
        "Other tracks' isolated audio and kick/bass overlap",
        "Sidechain input, routing, gain-reduction envelope, and compressor settings",
        "Integrated LUFS and oversampled true peak",
    ]}
    reply["analysis"] = analysis
    if not context or "audio_age_seconds" not in context or (not grade_request and not context.get("freshness", {}).get("current_for_diagnosis")):
        # Retained or disabled meters cannot describe current playback.
        reply.update(status="clarification_required", answer="Play the passage with KENN's analysis enabled on the track you mean, then ask again with its exact name or number. I have no current audio measurement for this request.")
        return reply
    state = state if state is not None else adapter.observe()
    # The source selector calls it "selected"; the existing target resolver
    # calls the same explicit insert "this". Neither phrase chooses a sibling.
    target_question = re.sub(r"\bselected\s+(?=insert\b|track\b|channel\b|bus\b)", "this ", question, flags=re.I) if grade_request else question
    source_name = context.get("host_track_name", "")
    binding = check_binding(session_id, plugin_session_id or session_id, state, context)
    if binding and binding.get("stale"):
        # A stale explicit declaration cannot silently become an inferred identity.
        reply.update(status="clarification_required", answer="This insert's explicit association expired or changed. Play the passage and bind this insert to its actual track number again.")
        return reply
    resolution = adapter.resolve(target_question, state, source_name)
    if grade_request and binding and any(
        track.get("index") != binding["track_index"] and track.get("name")
        and re.search(r"(?<!\w)" + re.escape(str(track["name"])) + r"(?!\w)", target_question, re.I)
        for track in state.get("tracks", []) if isinstance(track, dict)
    ):
        # 'This insert' may use a declaration, but it cannot erase a second
        # explicit name such as Piano merely because that name is not a role.
        reply.update(status="clarification_required", answer="Select one insert to grade. This request names another track; its audio cannot inherit the selected insert's points.")
        return reply
    if binding and re.search(r"\b(?:this|current)\s+(?:track|channel|bus|insert)\b", target_question.casefold()) and not re.search(r"\b(?:track|channel)\s+\d+\b|\b(?:kick|bass|drums?|vocals?|synth|master)\b", target_question.casefold()):
        # 'This insert' may use the declaration; named comparisons still resolve independently.
        resolution = {"target": next((t for t in state["tracks"] if t.get("index") == binding["track_index"]), None), "source_matched": True}
    target = resolution.get("target")
    if binding and target is not None and target["index"] == binding["track_index"]:
        resolution["source_matched"] = True
    master_insert = source_name.casefold() == "master" and bool(re.search(r"\bmaster\b", question.casefold()))
    own_insert = master_insert or bool(re.search(r"\b(?:this|current)\s+(?:track|channel|bus|insert)\b", target_question.casefold()))
    if grade_request and re.search(r"\b(?:track|channel)\s+\d+\b", target_question.casefold()) and target is None:
        # An explicit unmatched number cannot fall back to 'this insert', even
        # if Live is offline and its topology cannot confirm that number.
        own_insert = False
    if target is None and not own_insert:
        # We can locate only tracks in the fresh snapshot, never guess from session IDs.
        reply.update(status="clarification_required", answer=resolution["reason"] + " KENN measures only the audio entering its own insert.")
        return reply
    if target is not None and not resolution.get("source_matched"):
        # Selecting a Live track does not grant access to that track's audio.
        reply.update(status="clarification_required", answer=f"Place KENN on track {target['index'] + 1} '{target['name']}', play the passage, and ask again. The current insert reports '{source_name or 'no host track name'}'; I cannot attribute its audio to that track.")
        return reply
    if target is None and state.get("status") == "connected" and source_name and not master_insert:
        # Duplicate or missing host-name matches must not bypass identity checks via 'this'.
        reply.update(status="clarification_required", answer=resolution["reason"] + " The host name does not uniquely identify this insert in Live.")
        return reply
    name = target["name"] if target else source_name or "current KENN insert"
    analysis["target"] = {"name": name, "track_index": target["index"] if target else None, "association": "explicit_revision_checked" if binding else "unique_host_name" if target else "insert_only"}
    analysis["session"] = ({"source": "fresh_live_snapshot", "track_index": target["index"], "name": target["name"],
                            **{k: target[k] for k in ("volume", "muted", "soloed") if k in target}}
                           if target else {"source": "unavailable"})
    if grade_request:
        from kenn.core.plugin_grade import selected_insert_grade_answer

        # Return before the advice/proposal policy: a grading question only
        # explains supported points and cannot ask the producer to move a fader.
        grading = context["grading"]
        reply.update(grading=grading, status=grading["status"],
                     confidence="high" if grading["status"] == "graded" else "unknown",
                     answer=selected_insert_grade_answer(grading, name))
        return reply
    if context["rms_dbfs"] <= -80.0:
        # Keep the existing -80 dBFS activity floor ahead of publication: quiet ratios and spectra cannot ground advice.
        reply.update(status="insufficient_signal", answer=f"The input at '{name}' is near silence; play an audible passage before judging tone or dynamics.")
        return reply
    measured = {k: context[k] for k in ("peak_dbfs", "rms_dbfs", "crest_db", "clipped_samples", "stereo_correlation", "stereo_width", "transient_ratio", "sample_rate", "analysed_samples", "spectrum_bands", "low_energy", "mid_energy", "high_energy", "measurement_window", "fft_spectra") if k in context}
    measured["sample_headroom_db"] = round(-context["peak_dbfs"], 2)
    measured["freshness"] = context["freshness"]
    measured["live_window"] = context["live_window"]
    analysis["measured"] = measured
    # Legacy publishers decay peak and smooth RMS/bands by 0.1 per callback;
    # preserve that scope rather than claiming the new worker's exact windows.
    analysis["measurement_scope"] = "Current insert; decaying sample peak, block-smoothed RMS/bands/correlation; clip count is the last block at |sample| >= 0.999. History is up to 12 sparse frames over 120 seconds. Spectrum uses the mono sum and can cancel opposite-phase stereo."
    continuous = bool(context.get("measurement_window"))
    if continuous:
        analysis["measurement_scope"] = "Current insert; one contiguous 100 ms window for sample peak, RMS, crest, correlation, width, clip count and stereo-power filter-bank bands. The transient ratio measures fast-envelope excess over sustain (1/15 ms and 50/100 ms attack/release). Gaps retire evidence until a full window recovers. Optional 2048/8192-sample stereo Hann-power FFTs carry separate sample bounds; host sample clocks permit explicitly bound paired comparisons. Local sample positions alone cannot align different inserts."
    rms_label = "100 ms RMS" if continuous else "smoothed RMS"
    lines = [f"Measured at '{name}': sample peak {context['peak_dbfs']:.1f} dBFS, {rms_label} {context['rms_dbfs']:.1f} dBFS, sample headroom {measured['sample_headroom_db']:.1f} dB."]
    if target:
        lines.append(f"Live reports track {target['index'] + 1} '{name}'" + (f", fader {target['volume']:.4f} (Live raw 0–1)." if isinstance(target.get('volume'), (int, float)) else "; its fader is unavailable.") )
    else:
        lines.append("Live track association is unavailable; this is an insert-only observation.")
    reply["confidence"] = "high"  # Confidence in the measurements, not artistic mix quality.
    if "crest_db" in context:
        lines.append(f"Meter crest factor is {context['crest_db']:.1f} dB; it cannot prove compression or limiting.")
    fft = (context.get("fft_spectra") or {}).get("low")
    if fft and fft["mean_square"] > 1e-8:
        lines.append(f"The {fft['size_samples']}-sample Hann-power FFT's strongest non-DC bin is {fft['peak_hz']:.1f} Hz, with {fft['bin_hz']:.2f} Hz bin spacing. This describes spectral power in its own interval; a strongest bin alone is not a resonance diagnosis or an EQ target.")
    ranges = context["live_window"].get("metric_ranges", {})
    if context["live_window"].get("sample_count", 0) >= 3:
        lines.append(f"Across {context['live_window']['sample_count']} sparse updates, RMS ranged {ranges['rms_dbfs']['min']:.1f} to {ranges['rms_dbfs']['max']:.1f} dBFS; this is a meter trend, not musical dynamic range.")
    if context.get("clipped_samples", 0) > 0:
        unit = "100 ms window" if continuous else "analysed block"
        lines.append(f"The last {unit} had {int(context['clipped_samples'])} sample frames at or near full scale (|sample| ≥ 0.999). Check upstream gain and distortion; a downstream fader cannot repair it.")
        analysis["recommendations"].append({"track": name, "issue": "near_full_scale_input", "evidence": {"clipped_samples": context["clipped_samples"]}, "change": "Lower upstream gain and replay the loudest passage", "expected_effect": "Reduce overload entering KENN", "confidence": "high", "trade_off": "Changes drive into upstream processors", "application": "manual"})
    if context["stereo_correlation"] < 0.0:
        analysis["interpretations"].append({"finding": "Possible mono cancellation", "evidence": {"stereo_correlation": context["stereo_correlation"]}, "confidence": "medium"})
        lines.append(f"Correlation is {context['stereo_correlation']:.2f}: mono cancellation is possible. Compare in mono before narrowing or removing stereo effects manually.")
        analysis["recommendations"].append({"track": name, "issue": "negative_correlation", "evidence": {"stereo_correlation": context["stereo_correlation"]}, "change": "Audition in mono, then reduce the contributing stereo effect if the part loses weight", "expected_effect": "Improve mono retention", "confidence": "medium", "trade_off": "May reduce intentional width", "application": "manual"})
    pair_request = bool(re.search(r"\b(?:masking|sidechain)\b", question.casefold()))
    if pair_request:
        # One insert's spectrum cannot establish overlap, ducking, or routing.
        lines.append("I cannot determine kick/bass masking or whether sidechain compression works from this insert alone. Which source triggers the compressor, and can you provide isolated kick/bass measurements or a matched bypass comparison? Routing and gain reduction are unavailable here.")
        reply["confidence"] = "unknown"
    elif measured["sample_headroom_db"] < 3.0:
        analysis["interpretations"].append({"finding": "Limited sample headroom at the insert", "evidence": {"sample_headroom_db": measured["sample_headroom_db"]}, "confidence": "medium"})
        # 3 dB is an audition reserve for downstream summing, not a universal peak target.
        # The 0.1 dB minimum keeps a rounded near-threshold proposal from being a no-op.
        delta_db = round(min(-0.1, measured["sample_headroom_db"] - 3.0), 1)
        recommendation = {"track": name, "issue": "limited_sample_headroom", "evidence": {"peak_dbfs": context["peak_dbfs"]},
                          "change": f"Audition a {abs(delta_db):.1f} dB fader reduction", "delta_db": delta_db,
                          "expected_effect": "Reduce this track's contribution to downstream summing",
                          "confidence": "medium", "trade_off": "Lowers mix balance; does not repair upstream distortion or guarantee master headroom", "application": "manual"}
        analysis["recommendations"].append(recommendation)
        lines.append(f"Suggestion (medium confidence): audition a {abs(delta_db):.1f} dB fader reduction for downstream summing room. It lowers this part in the mix and does not repair upstream distortion or guarantee master headroom.")
        if target and context.get("assistant_mode") in {"suggest", "assist", "auto"} and adapter.resolve(f"Analyse track {target['index'] + 1}", state, source_name).get("source_matched"):
            result = adapter.propose_reduction(target, state, delta_db=delta_db, session_id=session_id)
            if result.get("ok"):
                proposal = result["proposal"]
                recommendation["application"] = "confirmation_required"
                reply.update(status="confirmation_required", proposal=proposal, confirmation_token=proposal["confirmation_token"], requires_confirmation=True)
                lines.append(f"Proposed Live fader: {proposal['before_db']} → {proposal['after_db']} dB. Nothing has changed. Confirm the action card to apply; verified changes support Undo. In the native plug-in, enter 'lower track {target['index'] + 1} by {abs(delta_db):.1f} dB' in Control Live and confirm its proposal.")
            else:
                # A control failure leaves the evidence and manual audition useful.
                lines.append(result["error"])
        else:
            # A declaration alone does not grant fader authority, including duplicate/absent host names.
            lines.append("Adjust the fader manually, or use Control Live to request and confirm a supported track change.")
    else:
        lines.append("These levels alone do not justify an EQ or compressor change. For more strength, compare attack and sustain in context at matched loudness. Do you want more attack, body, or space against the other parts?")
    spectrum_label = "stereo-power filter-bank" if continuous else "mono-sum"
    lines.append(f"Unavailable: other tracks' audio, sidechain routing/settings, LUFS, and true peak. Tone bands are broad, uncalibrated {spectrum_label} energy estimates; they cannot prescribe a frequency boost.")
    reply["answer"] = " ".join(lines)
    return reply
