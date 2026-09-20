# ai/markov/melody/generation/phrase_scoring.py
"""Phrase-level scoring for best-of-K melody candidate reranking."""

from typing import Any, Dict, List, Optional, Tuple

from ai.markov.melody.beauty import lyrical_accept_score, score_lyrical_melody
from ai.markov.melody.generation.voiceleading_rerank import voiceleading_local_rerank_delta


def _scale_degree_distance(a: int, b: int) -> int:
    d = abs(int(a) - int(b)) % 7
    return int(min(d, 7 - d))


def _phrase_signature(ph: List[Tuple[int, float]]) -> Tuple[Tuple[int, ...], Tuple[float, ...]]:
    degs: List[int] = []
    rh: List[float] = []
    for d, dur in list(ph or []):
        if isinstance(d, int) and int(d) >= 0:
            degs.append(int(d) % 7)
        try:
            rr = float(dur)
        except Exception:
            rr = 0.5
        # coarse bucket to keep scoring robust.
        if rr <= 0.25 + 1e-9:
            rb = 0.25
        elif rr <= 0.5 + 1e-9:
            rb = 0.5
        elif rr <= 1.0 + 1e-9:
            rb = 1.0
        elif rr <= 2.0 + 1e-9:
            rb = 2.0
        else:
            rb = 4.0
        rh.append(float(rb))
    return tuple(degs), tuple(rh)


def _signature_similarity(
    a_deg: Tuple[int, ...],
    a_rh: Tuple[float, ...],
    b_deg: Tuple[int, ...],
    b_rh: Tuple[float, ...],
) -> float:
    if not a_deg or not b_deg:
        return 0.0
    n = max(1, min(len(a_deg), len(b_deg)))
    deg_match = 0.0
    for i in range(n):
        da = int(a_deg[i])
        db = int(b_deg[i])
        d = abs(int(da) - int(db))
        d = min(d, 7 - d)
        deg_match += max(0.0, 1.0 - 0.5 * float(d))
    deg_match /= float(n)

    m = max(1, min(len(a_rh), len(b_rh)))
    rh_match = 0.0
    for i in range(m):
        ra = float(a_rh[i])
        rb = float(b_rh[i])
        if abs(float(ra) - float(rb)) <= 1e-9:
            rh_match += 1.0
        elif abs(float(ra) - float(rb)) <= 0.5 + 1e-9:
            rh_match += 0.5
    rh_match /= float(m)
    return float(0.67 * deg_match + 0.33 * rh_match)


def _listener_memory_delta(
    ph: List[Tuple[int, float]],
    *,
    plan: Any,
    prior_phrases: List[List[Tuple[int, float]]],
    strength: float,
) -> float:
    if not ph or not prior_phrases:
        return 0.0
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return 0.0
    try:
        sr = str(getattr(plan, "section_role", "") or "").strip().lower()
        pr = str(getattr(plan, "phrase_role", "") or "").strip().lower()
    except Exception:
        sr = ""
        pr = ""
    chorusish = sr in {"b", "chorus", "hook", "tag"}

    sig = _phrase_signature(ph)
    prior_sig = [_phrase_signature(pp) for pp in list(prior_phrases or []) if pp]
    if not prior_sig:
        return 0.0

    sims = [float(_signature_similarity(sig[0], sig[1], p0, p1)) for (p0, p1) in prior_sig]
    if not sims:
        return 0.0

    out = 0.0
    recent = sims[-2:] if len(sims) >= 2 else sims
    max_recent = max(float(v) for v in recent)
    max_all = max(float(v) for v in sims)
    exact_recent = sum(1 for v in recent if float(v) >= 0.995)

    # Penalize immediate duplicate recycling.
    if exact_recent > 0:
        out -= 0.34 * float(exact_recent)
    elif max_recent >= 0.90:
        out -= 0.18 * float((max_recent - 0.90) / 0.10)

    # Allow recall in structural locations, but keep it intentional.
    anchor_sim = float(sims[0])
    if chorusish and pr in {"opening", "cadence"}:
        out += 0.30 * float(max(0.0, min(1.0, anchor_sim)))
    elif pr in {"continuation", "answer"} and max_recent >= 0.78:
        out -= 0.12 * float((max_recent - 0.78) / 0.22)

    # Too-similar-to-anything everywhere can feel copy-paste.
    if max_all >= 0.98 and not (chorusish and pr in {"opening", "cadence"}):
        out -= 0.10

    return float(out) * float(s)


def _score_chorus_topline_phrase(
    ph: List[Tuple[int, float]],
    *,
    plan: Any,
    strength: float,
) -> float:
    if not ph:
        return 0.0
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return 0.0
    try:
        sr = str(getattr(plan, "section_role", "") or "").strip().lower()
    except Exception:
        sr = ""
    if sr not in {"b", "chorus", "hook", "tag"}:
        return 0.0

    voiced = [(int(d), float(dur)) for d, dur in ph if isinstance(d, int) and int(d) >= 0]
    if not voiced:
        return 0.0

    degs = [int(d) % 7 for d, _ in voiced]
    durs = [float(dur) for _, dur in voiced]
    score = 0.0

    # Singable hooks usually use a small pitch vocabulary.
    uniq = len(set(int(d) for d in degs))
    if uniq <= 3:
        score += 0.34
    elif uniq == 4:
        score += 0.18
    else:
        score -= 0.07 * float(uniq - 4)

    # Reward repeating short hook cells.
    if len(degs) >= 4:
        head2 = tuple(int(x) for x in degs[:2])
        head3 = tuple(int(x) for x in degs[:3])
        two_hits = sum(1 for i in range(0, len(degs) - 1) if tuple(int(x) for x in degs[i:i + 2]) == head2)
        three_hits = sum(1 for i in range(0, len(degs) - 2) if tuple(int(x) for x in degs[i:i + 3]) == head3)
        score += 0.18 * float(max(0, two_hits - 1))
        score += 0.12 * float(max(0, three_hits - 1))

    # Singability: prefer mostly stepwise or small-skip motion.
    intervals = [abs(int(degs[i]) - int(degs[i - 1])) for i in range(1, len(degs))]
    if intervals:
        wrapped = [min(int(iv), 7 - int(iv)) for iv in intervals]
        step_frac = sum(1 for iv in wrapped if int(iv) <= 1) / float(len(wrapped))
        leap_frac = sum(1 for iv in wrapped if int(iv) >= 3) / float(len(wrapped))
        score += 0.26 * float(step_frac)
        score -= 0.24 * float(leap_frac)

    # Rhythm simplicity: too many tiny values makes toplines feel wordy.
    short_frac = sum(1 for dur in durs if float(dur) <= 0.25 + 1e-9) / float(len(durs))
    longish_frac = sum(1 for dur in durs if float(dur) >= 0.5 - 1e-9) / float(len(durs))
    score += 0.18 * float(longish_frac)
    score -= 0.16 * float(short_frac)

    # Symmetry helps hooks read quickly.
    if len(degs) >= 4:
        half = len(degs) // 2
        a = list(degs[:half])
        b = list(degs[half:half + half])
        if a and b:
            matches = sum(1 for x, y in zip(a, b) if int(x) == int(y))
            score += 0.22 * (float(matches) / float(min(len(a), len(b))))

    # Stable opening/landing anchors make chorus phrases easier to remember.
    try:
        anchor = getattr(plan, "hook_anchor_degree", None)
        anchor = int(anchor) % 7 if anchor is not None else None
    except Exception:
        anchor = None
    if anchor is None:
        anchor = 0
    if degs:
        d0 = min(abs(int(degs[0]) - int(anchor)), 7 - abs(int(degs[0]) - int(anchor)))
        d1 = min(abs(int(degs[-1]) - int(anchor)), 7 - abs(int(degs[-1]) - int(anchor)))
        score += 0.14 if int(d0) == 0 else (-0.04 * float(d0))
        score += 0.10 if int(d1) <= 1 else (-0.03 * float(d1))

    return float(score) * float(s)


def score_phrase_candidate(
    ph: List[Tuple[int, float]],
    *,
    current_degree: int,
    phrase_start_beat: float,
    beats_per_bar: float,
    chord_weights_per_bar: List[Dict[int, float]],
    plan: Any,
    entry_pen: float,
    leap_pen: float,
    leap_thr: int,
    cad_land: float,
    cad_app: float,
    cad_miss: float,
    occ_step_weights: Dict[int, float],
    grid: float,
    emotion: Any = None,
    prior_phrases: Optional[List[List[Tuple[int, float]]]] = None,
) -> float:
    """Cheap, deterministic score for one phrase candidate (higher = better)."""
    if not ph:
        return -1e9
    s = 0.0
    try:
        s -= float(entry_pen) * float(_scale_degree_distance(int(ph[0][0]), int(current_degree)))
    except Exception:
        pass
    try:
        prev_deg = None
        for i in range(0, len(ph)):
            d0 = ph[i][0]
            if not isinstance(d0, int) or int(d0) < 0:
                continue
            if prev_deg is not None:
                dist = _scale_degree_distance(int(d0), int(prev_deg))
                if int(dist) >= int(leap_thr):
                    s -= float(leap_pen) * float(dist)
            prev_deg = int(d0)
    except Exception:
        pass

    try:
        from audiogen_core.config import CONFIG

        mpp = CONFIG.composition.melody_phrase_planning
        vl_on = bool(getattr(CONFIG.composition, "melody_voiceleading_rerank_enabled", False))
        vl_strength = float(getattr(CONFIG.composition, "melody_voiceleading_rerank_strength", 0.60) or 0.60)
        sb_ct_bonus = float(mpp.rerank_strongbeat_chord_tone_bonus)
    except Exception:
        vl_on = False
        vl_strength = 0.60
        sb_ct_bonus = 0.10
    vl_strength = max(0.0, min(1.0, float(vl_strength)))
    if vl_on and vl_strength > 1e-6:
        try:
            s += voiceleading_local_rerank_delta(
                phrase=list(ph),
                start_degree=int(current_degree),
                start_beat=float(phrase_start_beat),
                beats_per_bar=float(beats_per_bar),
                chord_weights_per_bar=list(chord_weights_per_bar or []),
                strength=float(vl_strength),
            )
        except Exception:
            pass

    # Strong-beat chord-tone alignment: cheap proxy for melody↔harmony fit.
    # This is intentionally lightweight and only affects reranking, not the underlying Markov probs.
    sb_ct_bonus = max(0.0, min(0.50, float(sb_ct_bonus)))
    if sb_ct_bonus > 1e-9 and chord_weights_per_bar and beats_per_bar > 1e-9:
        try:
            t = float(phrase_start_beat)
            hits = 0
            den = 0
            for deg, dur in list(ph or []):
                if not isinstance(deg, int) or int(deg) < 0:
                    t += float(dur)
                    continue
                bar = int(float(t) // float(beats_per_bar))
                if bar < 0:
                    bar = 0
                if bar >= len(chord_weights_per_bar):
                    bar = len(chord_weights_per_bar) - 1
                beat_in_bar = float(t) - float(bar) * float(beats_per_bar)
                strong = (abs(float(beat_in_bar) - 0.0) < 1e-6) or (abs(float(beat_in_bar) - (float(beats_per_bar) / 2.0)) < 1e-6)
                if strong:
                    den += 1
                    cw = chord_weights_per_bar[bar] or {}
                    if cw and (int(deg) % 7) in cw:
                        hits += 1
                t += float(dur)
            if den > 0:
                s += float(sb_ct_bonus) * (float(hits) / float(den))
        except Exception:
            pass
    try:
        target = int(getattr(plan, "cadence_degree", 0) or 0) % 7
        last_deg = int(ph[-1][0]) % 7
        if last_deg == target:
            s += float(cad_land)
        else:
            d = abs(int(last_deg) - int(target))
            d = min(d, 7 - d)
            s -= float(cad_miss) * float(d)
        if len(ph) >= 2:
            prev_deg = int(ph[-2][0]) % 7
            if last_deg == target and min(abs(prev_deg - last_deg), 7 - abs(prev_deg - last_deg)) == 1:
                s += float(cad_app)
    except Exception:
        pass

    # Hook anchor: for chorus-like openings, prefer the phrase to begin on a stable
    # anchor degree (typically 0/2/4). This increases "hook clarity" without changing
    # the underlying Markov distributions.
    try:
        hook_anchor = getattr(plan, "hook_anchor_degree", None)
        if hook_anchor is not None:
            hook_anchor = int(hook_anchor) % 7
        pr = str(getattr(plan, "phrase_role", "") or "").strip().lower()
        sr = str(getattr(plan, "section_role", "") or "").strip().lower()
    except Exception:
        hook_anchor = None
        pr = ""
        sr = ""

    if hook_anchor is not None and pr == "opening" and sr in {"b", "chorus", "hook", "tag"}:
        try:
            first_voiced = next((int(d) % 7 for d, _dur in ph if isinstance(d, int) and int(d) >= 0), None)
        except Exception:
            first_voiced = None
        if first_voiced is not None:
            try:
                d = abs(int(first_voiced) - int(hook_anchor))
                d = min(d, 7 - d)
                # Small but meaningful: reward exact, penalize far.
                s += 0.35 if int(d) == 0 else -0.12 * float(d)
            except Exception:
                pass

    try:
        from audiogen_core.config import CONFIG

        mw = float(CONFIG.composition.melody_phrase_planning.rerank_masking_weight)
    except Exception:
        mw = 0.0
    mw = max(0.0, min(2.0, float(mw)))
    if mw > 1e-6 and occ_step_weights:
        try:
            t = float(phrase_start_beat)
            penalties = []
            for _deg, dur in ph:
                step = int(round(float(t) / float(grid)))
                w = float(occ_step_weights.get(int(step), 0.0) or 0.0)
                beat_in_bar = float(t % beats_per_bar)
                strong = (abs(beat_in_bar - 0.0) < 1e-6) or (abs(beat_in_bar - 2.0) < 1e-6)
                p = float(w) * (1.35 if strong else 1.0)
                penalties.append(p)
                t += float(dur)
            if penalties:
                s -= float(mw) * (sum(float(p) for p in penalties) / float(len(penalties)))
        except Exception:
            pass

    try:
        from audiogen_core.config import CONFIG

        topline_on = bool(getattr(CONFIG.composition, "chorus_topline_scorer_enabled", True))
        topline_strength = float(getattr(CONFIG.composition, "chorus_topline_scorer_strength", 0.72) or 0.72)
    except Exception:
        topline_on = True
        topline_strength = 0.72
    if topline_on:
        try:
            s += _score_chorus_topline_phrase(
                ph,
                plan=plan,
                strength=float(topline_strength),
            )
        except Exception:
            pass
    try:
        from audiogen_core.config import CONFIG

        mpp = CONFIG.composition.melody_phrase_planning
        mem_on = bool(mpp.listener_memory_enabled)
        mem_strength = float(mpp.listener_memory_strength)
    except Exception:
        mem_on = True
        mem_strength = 0.65
    if mem_on and prior_phrases:
        try:
            s += _listener_memory_delta(
                ph,
                plan=plan,
                prior_phrases=list(prior_phrases or []),
                strength=float(mem_strength),
            )
        except Exception:
            pass
    try:
        from audiogen_core.config import CONFIG

        mpp = CONFIG.composition.melody_phrase_planning
        lyrical_on = bool(mpp.lyrical_scorer_enabled)
        lyrical_strength = float(mpp.lyrical_scorer_strength)
    except Exception:
        lyrical_on = True
        lyrical_strength = 0.48
    if lyrical_on and lyrical_strength > 1e-6:
        try:
            cad = int(getattr(plan, "cadence_degree", 0) or 0)
            beauty, _components = score_lyrical_melody(list(ph or []), cadence_degree=int(cad))
            # Center around 0.50 so average-valid phrases remain neutral.
            s += float(lyrical_strength) * (float(beauty) - 0.50)
        except Exception:
            pass

    # --------------------------------------------------------------
    # Stage 3: unify "repair intent" into the phrase objective.
    # This stays cheap and deterministic: it only affects reranking.
    # --------------------------------------------------------------
    try:
        from audiogen_core.config import CONFIG

        mpp = CONFIG.composition.melody_phrase_planning
        obj_on = bool(mpp.phrase_objective_enabled)
        w_static = float(mpp.phrase_objective_static_run_weight)
        w_contour = float(mpp.phrase_objective_contour_weight)
        w_breath = float(mpp.phrase_objective_long_breath_weight)
    except Exception:
        obj_on = False
        w_static = 0.22
        w_contour = 0.16
        w_breath = 0.12
    if obj_on and (w_static > 1e-9 or w_contour > 1e-9 or w_breath > 1e-9):
        try:
            voiced = [int(d) % 7 for d, _dur in list(ph or []) if isinstance(d, int) and int(d) >= 0]
            durs = [float(dur) for _d, dur in list(ph or [])]
        except Exception:
            voiced = []
            durs = []

        # Emotion prior (best-effort, optional).
        repeat_mult = None
        wants_rise = None
        wants_fall = None
        long_breathed = None
        try:
            from data.emotion_melody_priors import emotion_melody_prior_for

            emo_name = str(getattr(emotion, "name", None) or emotion or "")
            prior = emotion_melody_prior_for(str(emo_name))
            repeat_mult = float(getattr(prior, "repeat_mult", 1.0))
            asc = float(getattr(prior, "ascending_mult", 1.0))
            desc = float(getattr(prior, "descending_mult", 1.0))
            wants_rise = asc > desc * 1.12
            wants_fall = desc > asc * 1.12
            long_breathed = float(getattr(prior, "long_rhythm_mult", 1.0)) >= float(getattr(prior, "short_rhythm_mult", 1.0)) * 1.20
        except Exception:
            repeat_mult = None
            wants_rise = None
            wants_fall = None
            long_breathed = None

        # Static-run avoidance: penalize long repeated degrees.
        if voiced and float(w_static) > 1e-9:
            try:
                run = 1
                max_run = 1
                for prev, cur in zip(voiced, voiced[1:]):
                    if int(prev) == int(cur):
                        run += 1
                    else:
                        max_run = max(int(max_run), int(run))
                        run = 1
                max_run = max(int(max_run), int(run))
                # Emotion-aware tolerance: lower repeat_mult -> stricter.
                thr = 4
                if repeat_mult is not None and float(repeat_mult) <= 0.82:
                    thr = 2
                elif repeat_mult is not None and float(repeat_mult) <= 0.92:
                    thr = 3
                overflow = max(0, int(max_run) - int(thr))
                if overflow > 0:
                    s -= float(w_static) * float(overflow)
            except Exception:
                pass

        # Contour tilt: prefer net ascent/descent when the prior/plan wants it.
        if voiced and float(w_contour) > 1e-9:
            try:
                contour = str(getattr(plan, "contour", "") or "").strip().lower()
            except Exception:
                contour = ""
            try:
                asc_n = sum(1 for i in range(1, len(voiced)) if int(voiced[i]) > int(voiced[i - 1]))
                desc_n = sum(1 for i in range(1, len(voiced)) if int(voiced[i]) < int(voiced[i - 1]))
                net = float(asc_n - desc_n)
                denom = float(max(1, len(voiced) - 1))
                net /= denom
                want_up = (contour == "asc") or (wants_rise is True)
                want_down = (contour == "desc") or (wants_fall is True)
                if want_up and not want_down:
                    s += float(w_contour) * float(net)
                elif want_down and not want_up:
                    s += float(w_contour) * float(-net)
            except Exception:
                pass

        # Long-breath preference: if the prior wants longer notes, penalize tiny durations.
        if durs and float(w_breath) > 1e-9 and long_breathed is True:
            try:
                short_frac = sum(1 for dur in durs if abs(float(dur)) <= 0.25 + 1e-9) / float(max(1, len(durs)))
                s -= float(w_breath) * float(short_frac)
            except Exception:
                pass
    return float(s)


def melody_accept_heuristic(mel: List[Tuple[int, float]]) -> float:
    """Cheap heuristic for live training export."""
    return lyrical_accept_score(list(mel or []))
