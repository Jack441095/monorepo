import math
import json
from pathlib import Path
import numpy as np

try:
    from scipy.optimize import minimize
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


def log_spaced_boundaries(start_freq: float = 20.0, end_freq: float = 20000.0, num_bands: int = 40) -> list[float]:
    log_start = math.log10(start_freq)
    log_end = math.log10(end_freq)
    step = (log_end - log_start) / num_bands
    return [10 ** (log_start + i * step) for i in range(num_bands + 1)]


def generate_profile(slope: float, bass_boost_db: float = 0.0, mids_boost_db: float = 0.0, highs_roll_off: float = -6.0) -> list[float]:
    """Programmatically generate a standard 40-band log-spaced energy profile."""
    boundaries = log_spaced_boundaries(20.0, 20000.0, 40)
    centers = [math.sqrt(boundaries[i] * boundaries[i+1]) for i in range(40)]
    levels_db = []
    for fc in centers:
        octaves = math.log2(fc / 1000.0)
        db = slope * octaves
        
        # Sub roll-off below 30 Hz
        if fc < 30.0:
            db -= 12.0 * math.log2(30.0 / fc)
        # Bass boost/cut around 60-150 Hz
        if 60.0 <= fc <= 150.0:
            db += bass_boost_db
        # Mid boost/scoop around 200-1000 Hz
        if 200.0 <= fc <= 1000.0:
            db += mids_boost_db
        # High roll-off above 15000 Hz
        if fc > 15000.0:
            db += highs_roll_off * math.log2(fc / 15000.0)
            
        levels_db.append(db)
        
    linear = [10 ** (db / 10.0) for db in levels_db]
    total = sum(linear) or 1.0
    return [round(v / total, 5) for v in linear]


# Seeding 20 target profiles dynamically
GENRE_SEED_PROFILES = {
    "pop": {
        "name": "Pop",
        "profile": generate_profile(-3.5, bass_boost_db=1.0, mids_boost_db=0.0),
        "crest_factor_db": 8.0,
        "lufs_max": -10.0,
        "lra_min": 4.0,
        "stereo_correlation": 0.85,
    },
    "hip_hop": {
        "name": "Hip Hop / Rap",
        "profile": generate_profile(-4.5, bass_boost_db=4.0, highs_roll_off=-12.0),
        "crest_factor_db": 9.0,
        "lufs_max": -9.0,
        "lra_min": 3.0,
        "stereo_correlation": 0.80,
    },
    "rock": {
        "name": "Rock / Alternative",
        "profile": generate_profile(-3.0, mids_boost_db=2.0),
        "crest_factor_db": 7.0,
        "lufs_max": -9.0,
        "lra_min": 5.0,
        "stereo_correlation": 0.82,
    },
    "edm": {
        "name": "EDM / Dance",
        "profile": generate_profile(-4.0, bass_boost_db=3.0, highs_roll_off=-6.0),
        "crest_factor_db": 7.5,
        "lufs_max": -8.0,
        "lra_min": 3.5,
        "stereo_correlation": 0.88,
    },
    "jazz": {
        "name": "Jazz / Blues",
        "profile": generate_profile(-3.5, mids_boost_db=1.0),
        "crest_factor_db": 11.0,
        "lufs_max": -14.0,
        "lra_min": 8.0,
        "stereo_correlation": 0.80,
    },
    "orchestral": {
        "name": "Classical / Orchestral",
        "profile": generate_profile(-4.0, mids_boost_db=1.5, highs_roll_off=-9.0),
        "crest_factor_db": 14.0,
        "lufs_max": -16.0,
        "lra_min": 12.0,
        "stereo_correlation": 0.75,
    },
    "acoustic": {
        "name": "Acoustic / Singer-Songwriter",
        "profile": generate_profile(-3.0, mids_boost_db=0.5),
        "crest_factor_db": 10.0,
        "lufs_max": -13.0,
        "lra_min": 7.0,
        "stereo_correlation": 0.85,
    },
    "cinematic": {
        "name": "Cinematic / Soundstripe",
        "profile": generate_profile(-4.5, bass_boost_db=2.0, mids_boost_db=1.0),
        "crest_factor_db": 12.0,
        "lufs_max": -14.0,
        "lra_min": 10.0,
        "stereo_correlation": 0.78,
    },
    "lo_fi": {
        "name": "Lo-Fi Beats",
        "profile": generate_profile(-5.0, bass_boost_db=2.5, highs_roll_off=-18.0),
        "crest_factor_db": 8.0,
        "lufs_max": -12.0,
        "lra_min": 4.0,
        "stereo_correlation": 0.80,
    },
    "club": {
        "name": "Club / Techno",
        "profile": generate_profile(-4.2, bass_boost_db=3.5, highs_roll_off=-6.0),
        "crest_factor_db": 7.0,
        "lufs_max": -8.0,
        "lra_min": 3.0,
        "stereo_correlation": 0.85,
    },
    "podcast": {
        "name": "Podcast / Voice",
        "profile": generate_profile(-3.5, mids_boost_db=3.0, highs_roll_off=-12.0),
        "crest_factor_db": 12.0,
        "lufs_max": -16.0,
        "lra_min": 9.0,
        "stereo_correlation": 0.90,
    },
    "pop_rap": {
        "name": "Pop Rap",
        "profile": generate_profile(-4.0, bass_boost_db=2.5, highs_roll_off=-9.0),
        "crest_factor_db": 8.0,
        "lufs_max": -9.0,
        "lra_min": 4.0,
        "stereo_correlation": 0.82,
    },
    "metal": {
        "name": "Metal / Hardcore",
        "profile": generate_profile(-2.8, mids_boost_db=1.5, bass_boost_db=1.0),
        "crest_factor_db": 6.0,
        "lufs_max": -8.0,
        "lra_min": 4.0,
        "stereo_correlation": 0.80,
    },
    "folk": {
        "name": "Folk / Country",
        "profile": generate_profile(-3.2, mids_boost_db=0.8),
        "crest_factor_db": 9.5,
        "lufs_max": -12.0,
        "lra_min": 6.5,
        "stereo_correlation": 0.84,
    },
    "blues": {
        "name": "Blues",
        "profile": generate_profile(-3.2, mids_boost_db=1.2),
        "crest_factor_db": 10.0,
        "lufs_max": -13.0,
        "lra_min": 7.0,
        "stereo_correlation": 0.82,
    },
    "ambient": {
        "name": "Ambient",
        "profile": generate_profile(-5.0, bass_boost_db=1.5, highs_roll_off=-12.0),
        "crest_factor_db": 13.0,
        "lufs_max": -18.0,
        "lra_min": 12.0,
        "stereo_correlation": 0.85,
    },
    "synthwave": {
        "name": "Synthwave / Retro",
        "profile": generate_profile(-3.8, bass_boost_db=2.5, highs_roll_off=-6.0),
        "crest_factor_db": 7.5,
        "lufs_max": -9.0,
        "lra_min": 4.5,
        "stereo_correlation": 0.85,
    },
    "reggae": {
        "name": "Reggae / Dub",
        "profile": generate_profile(-4.5, bass_boost_db=4.5, highs_roll_off=-15.0),
        "crest_factor_db": 9.5,
        "lufs_max": -11.0,
        "lra_min": 5.0,
        "stereo_correlation": 0.80,
    },
    "latin": {
        "name": "Latin / Reggaeton",
        "profile": generate_profile(-3.4, bass_boost_db=1.5, highs_roll_off=-6.0),
        "crest_factor_db": 7.5,
        "lufs_max": -9.0,
        "lra_min": 4.0,
        "stereo_correlation": 0.85,
    },
    "techno": {
        "name": "Techno / House",
        "profile": generate_profile(-4.0, bass_boost_db=3.0),
        "crest_factor_db": 7.0,
        "lufs_max": -8.0,
        "lra_min": 3.0,
        "stereo_correlation": 0.86,
    },
    "premaster": {
        "name": "Premaster Target",
        "profile": generate_profile(-3.8),
        "crest_factor_db": 8.0,
        "lufs_max": -12.0,
        "lra_min": 5.0,
        "stereo_correlation": 0.85,
    },
}


def _load_seed_profile_library() -> dict[str, dict]:
    library_path = Path(__file__).resolve().parent.parent / "reference_profiles" / "genre_archetypes.json"
    try:
        payload = json.loads(library_path.read_text(encoding="utf-8"))
        profiles = payload.get("profiles", {})
        if len(profiles) >= 20 and all(len(item.get("profile", [])) == 40 for item in profiles.values()):
            return profiles
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return GENRE_SEED_PROFILES


GENRE_SEED_PROFILES = _load_seed_profile_library()


def bell_filter_db(f: np.ndarray, fc: float, gain: float, q: float) -> np.ndarray:
    """peaking/bell filter frequency response in dB."""
    ratio = f / fc
    # Avoid division by zero
    ratio = np.maximum(1e-5, ratio)
    diff = ratio - (1.0 / ratio)
    return gain / (1.0 + (q * diff) ** 2)


def eq_cost(params: list[float], frequencies: np.ndarray, target_db: np.ndarray) -> float:
    """L2 distance between matching target curves and parametric curves."""
    total_response = np.zeros_like(frequencies)
    for i in range(4):
        fc = params[i * 3]
        gain = params[i * 3 + 1]
        q = params[i * 3 + 2]
        total_response += bell_filter_db(frequencies, fc, gain, q)
    return float(np.sum((total_response - target_db) ** 2))


def solve_parametric_eq(mix_log_bands: list[float], ref_log_bands: list[float]) -> list[dict]:
    """Solve for a 4-band parametric EQ match. Returns list of band dicts."""
    if len(mix_log_bands) != 40 or len(ref_log_bands) != 40:
        raise ValueError("EQ matching requires two normalized 40-band profiles")
    boundaries = log_spaced_boundaries(20.0, 20000.0, 40)
    frequencies = np.array([math.sqrt(boundaries[i] * boundaries[i+1]) for i in range(40)], dtype=np.float32)
    
    # Calculate difference in dB: 20 * log10(ref / mix)
    mix_arr = np.array(mix_log_bands, dtype=np.float32)
    ref_arr = np.array(ref_log_bands, dtype=np.float32)
    
    diff_db = 20.0 * np.log10(np.maximum(1e-5, ref_arr) / np.maximum(1e-5, mix_arr))
    
    # Subtract average level offset to keep the EQ curve purely tonal
    diff_db = diff_db - np.mean(diff_db)
    
    if SCIPY_AVAILABLE:
        bands = solve_parametric_eq_scipy(frequencies, diff_db)
    else:
        bands = solve_parametric_eq_fallback(frequencies, diff_db)
    return constrain_parametric_bands(bands)


def constrain_parametric_bands(bands: list[dict]) -> list[dict]:
    """Clamp solver output and prevent more than two materially overlapping bells."""
    constrained = [
        {
            "freq": round(max(20.0, min(20_000.0, float(band["freq"]))), 1),
            "gain": round(max(-6.0, min(6.0, float(band["gain"]))), 1),
            "q": round(max(0.3, min(8.0, float(band["q"]))), 2),
        }
        for band in bands[:8]
    ]

    def active_at(band: dict, frequency: float) -> bool:
        half_octaves = 0.5 / max(float(band["q"]), 0.3)
        low = float(band["freq"]) / (2.0 ** half_octaves)
        high = float(band["freq"]) * (2.0 ** half_octaves)
        return low <= frequency <= high

    for _ in range(64):
        offenders = []
        for frequency in [float(band["freq"]) for band in constrained]:
            active = [band for band in constrained if active_at(band, frequency)]
            if len(active) > 2:
                offenders.extend(active)
        if not offenders:
            break
        broadest = min(offenders, key=lambda band: float(band["q"]))
        broadest["q"] = round(min(8.0, float(broadest["q"]) + 0.15), 2)
    return constrained


def solve_parametric_eq_scipy(frequencies: np.ndarray, target_db: np.ndarray) -> list[dict]:
    bounds = [
        (30.0, 200.0), (-6.0, 6.0), (0.3, 8.0),       # Band 1: Lows
        (200.0, 1000.0), (-6.0, 6.0), (0.3, 8.0),     # Band 2: Low-Mids
        (1000.0, 5000.0), (-6.0, 6.0), (0.3, 8.0),    # Band 3: Mids/Presence
        (5000.0, 18000.0), (-6.0, 6.0), (0.3, 8.0),   # Band 4: Highs/Air
    ]
    init_params = [
        80.0, 0.0, 0.7,
        300.0, 0.0, 0.9,
        2500.0, 0.0, 0.7,
        10000.0, 0.0, 0.7,
    ]
    try:
        res = minimize(eq_cost, init_params, args=(frequencies, target_db), bounds=bounds, method="L-BFGS-B")
        fit_params = res.x
    except Exception:
        return solve_parametric_eq_fallback(frequencies, target_db)
        
    bands = []
    for i in range(4):
        idx = i * 3
        bands.append({
            "freq": round(float(fit_params[idx]), 1),
            "gain": round(float(fit_params[idx+1]), 1),
            "q": round(float(fit_params[idx+2]), 2),
        })
    return bands


def solve_parametric_eq_fallback(frequencies: np.ndarray, target_db: np.ndarray) -> list[dict]:
    """Pure Python/NumPy coordinate descent solver fallback."""
    params = [
        80.0, 0.0, 0.7,
        300.0, 0.0, 0.9,
        2500.0, 0.0, 0.7,
        10000.0, 0.0, 0.7,
    ]
    bounds = [
        (30.0, 200.0), (-6.0, 6.0), (0.3, 8.0),
        (200.0, 1000.0), (-6.0, 6.0), (0.3, 8.0),
        (1000.0, 5000.0), (-6.0, 6.0), (0.3, 8.0),
        (5000.0, 18000.0), (-6.0, 6.0), (0.3, 8.0),
    ]
    
    # Coordinate descent optimization
    for _iter in range(3):
        for p_idx in range(12):
            low, high = bounds[p_idx]
            best_val = params[p_idx]
            best_cost = eq_cost(params, frequencies, target_db)
            
            # Grid search 15 points
            steps = 15
            for step in range(steps):
                val = low + (high - low) * step / (steps - 1)
                old_val = params[p_idx]
                params[p_idx] = val
                cost = eq_cost(params, frequencies, target_db)
                if cost < best_cost:
                    best_cost = cost
                    best_val = val
                else:
                    params[p_idx] = old_val
            params[p_idx] = best_val
            
    bands = []
    for i in range(4):
        idx = i * 3
        bands.append({
            "freq": round(float(params[idx]), 1),
            "gain": round(float(params[idx+1]), 1),
            "q": round(float(params[idx+2]), 2),
        })
    return bands


def compute_tonal_balance_score(mix_log_bands: list[float], ref_log_bands: list[float]) -> float:
    """Compare spectrum to a perceptually weighted tolerance envelope."""
    if not mix_log_bands or not ref_log_bands or len(mix_log_bands) != len(ref_log_bands):
        return 0.0
    
    # Calculate difference in dB
    mix_arr = np.array(mix_log_bands, dtype=np.float32)
    ref_arr = np.array(ref_log_bands, dtype=np.float32)
    
    diff_db = 20.0 * np.log10(np.maximum(1e-5, ref_arr) / np.maximum(1e-5, mix_arr))
    # Subtract average offset
    diff_db = diff_db - np.mean(diff_db)
    
    centers = [
        math.sqrt(a * b)
        for a, b in zip(log_spaced_boundaries()[:-1], log_spaced_boundaries()[1:])
    ]

    def perceptual_weight(frequency: float) -> float:
        if frequency < 60.0 or frequency >= 12_000.0:
            return 0.6
        if frequency < 150.0:
            return 0.9
        if frequency < 400.0:
            return 1.3
        if frequency < 2_000.0:
            return 1.1
        if frequency < 6_000.0:
            return 1.4
        return 1.0

    scores = []
    weights = []
    for diff, frequency in zip(diff_db, centers):
        abs_diff = abs(diff)
        if abs_diff <= 1.5:
            scores.append(1.0)
        elif abs_diff >= 6.0:
            scores.append(0.0)
        else:
            scores.append(1.0 - (abs_diff - 1.5) / 4.5)
        weights.append(perceptual_weight(frequency))

    avg_score = float(np.average(scores, weights=weights))
    return round(avg_score * 100.0, 1)


def build_reference_envelope(profiles: list[list[float]]) -> dict[str, list[float]]:
    """Build a level-invariant mean/std envelope from normalized 40-band profiles."""
    valid = [np.asarray(profile, dtype=np.float64) for profile in profiles if len(profile) == 40]
    if not valid:
        raise ValueError("At least one 40-band profile is required")
    db_profiles = []
    for profile in valid:
        profile = np.maximum(profile, 1e-8)
        profile = profile / max(float(np.sum(profile)), 1e-8)
        profile_db = 20.0 * np.log10(profile)
        db_profiles.append(profile_db - np.mean(profile_db))
    matrix = np.vstack(db_profiles)
    return {
        "mean_db": np.mean(matrix, axis=0).round(4).tolist(),
        "std_db": np.std(matrix, axis=0).round(4).tolist(),
        "sample_count": len(valid),
    }


def compute_tonal_balance_envelope_score(
    mix_log_bands: list[float],
    envelope: dict[str, list[float]],
) -> float:
    """Score a mix against mean ± standard deviation, falling to zero 6 dB outside."""
    if len(mix_log_bands) != 40:
        return 0.0
    mean_db = np.asarray(envelope.get("mean_db", []), dtype=np.float64)
    std_db = np.asarray(envelope.get("std_db", []), dtype=np.float64)
    if len(mean_db) != 40 or len(std_db) != 40:
        return 0.0
    mix = np.maximum(np.asarray(mix_log_bands, dtype=np.float64), 1e-8)
    mix_db = 20.0 * np.log10(mix / max(float(np.sum(mix)), 1e-8))
    mix_db -= np.mean(mix_db)
    outside_db = np.maximum(np.abs(mix_db - mean_db) - std_db, 0.0)
    band_scores = np.clip(1.0 - outside_db / 6.0, 0.0, 1.0)
    centers = np.sqrt(np.asarray(log_spaced_boundaries()[:-1]) * np.asarray(log_spaced_boundaries()[1:]))
    weights = np.asarray([
        0.6 if f < 60.0 or f >= 12_000.0 else
        0.9 if f < 150.0 else
        1.3 if f < 400.0 else
        1.1 if f < 2_000.0 else
        1.4 if f < 6_000.0 else 1.0
        for f in centers
    ])
    return round(float(np.average(band_scores, weights=weights)) * 100.0, 1)


def classify_reference_profile(profile: list[float], metrics: dict | None = None) -> dict:
    """Categorize an uploaded reference against the nearest curated genre fingerprint."""
    if len(profile) != 40:
        return {"genre_key": "", "genre_name": "Uncategorised", "confidence": 0.0, "distance_db": None}
    source = np.maximum(np.asarray(profile, dtype=np.float64), 1e-8)
    source_db = 20.0 * np.log10(source / max(float(np.sum(source)), 1e-8))
    source_db -= np.mean(source_db)
    metrics = metrics or {}
    ranked = []
    for key, seed in GENRE_SEED_PROFILES.items():
        target = np.maximum(np.asarray(seed["profile"], dtype=np.float64), 1e-8)
        target_db = 20.0 * np.log10(target / max(float(np.sum(target)), 1e-8))
        target_db -= np.mean(target_db)
        spectral_distance = float(np.sqrt(np.mean((source_db - target_db) ** 2)))
        macro_penalty = 0.0
        if metrics.get("crest_factor_db") is not None:
            macro_penalty += abs(float(metrics["crest_factor_db"]) - float(seed["crest_factor_db"])) * 0.08
        if metrics.get("integrated_lufs") not in {None, "", "n/a"}:
            macro_penalty += abs(float(metrics["integrated_lufs"]) - float(seed["lufs_max"])) * 0.05
        ranked.append((spectral_distance + macro_penalty, key, seed))
    distance, key, seed = min(ranked, key=lambda row: row[0])
    confidence = max(0.0, min(1.0, 1.0 - distance / 12.0))
    return {
        "genre_key": key,
        "genre_name": seed["name"],
        "confidence": round(confidence, 3),
        "distance_db": round(distance, 3),
    }


def map_40_to_7_bands(bands_40: list[float]) -> dict[str, float]:
    boundaries_40 = log_spaced_boundaries(20.0, 20000.0, 40)
    centers = [math.sqrt(boundaries_40[i] * boundaries_40[i+1]) for i in range(40)]
    
    std_bands = {
        "sub": (20, 60),
        "bass": (60, 150),
        "low_mids": (150, 400),
        "mids": (400, 2000),
        "presence": (2000, 6000),
        "sibilance": (6000, 8000),
        "air": (8000, 16000),
    }
    
    out = {k: 0.0 for k in std_bands}
    for idx, fc in enumerate(centers):
        val = bands_40[idx]
        for name, (low, high) in std_bands.items():
            if low <= fc < high:
                out[name] += val
                break
                
    total = sum(out.values()) or 1.0
    return {k: round(v / total, 4) for k, v in out.items()}
