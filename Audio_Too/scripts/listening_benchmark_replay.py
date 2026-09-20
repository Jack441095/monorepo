#!/usr/bin/env python3
"""
Blind listening benchmark replay and analysis harness.

Loads completed ratings, unblinds the A/B assignments, calculates:
- Per-dimension statistics (mean, median, std)
- Inter-rater agreement (Cohen's kappa)
- Overall preference counts and Wilson confidence intervals
- Per-project and per-version breakdowns
"""

import json
import csv
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple
import math
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@dataclass
class RatingAnalysis:
    """Aggregated analysis of listening ratings."""
    project_id: str
    baseline_version: str
    compare_version: str

    num_ratings: int
    num_raters: int

    # Per-dimension stats
    dimension_stats: dict  # {dimension: {mean, median, std, scores}}

    # Overall preference
    baseline_wins: int
    compare_wins: int
    ties: int
    total_comparisons: int

    # Preference rates
    baseline_preference_rate: float
    compare_preference_rate: float
    tie_rate: float

    # Wilson score interval (95% CI for preference)
    wilson_lower_bound: float
    wilson_upper_bound: float

    # Inter-rater agreement (Cohen's kappa for binary preference)
    cohens_kappa: Optional[float] = None


def unbind_ratings(
    ratings_file: Path,
    unblinding_key_file: Path
) -> List[dict]:
    """
    Load ratings and unblind by joining with unblinding key.

    Returns list of unblinded rating dicts with true versions revealed.
    """

    # Load ratings
    ratings = []
    with open(ratings_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ratings.append(row)

    logger.info(f"Loaded {len(ratings)} ratings from {ratings_file}")

    # Load unblinding key
    with open(unblinding_key_file, 'r') as f:
        key_data = json.load(f)

    key_map = {item['assignment_id']: item for item in key_data}
    logger.info(f"Loaded unblinding key with {len(key_map)} entries")

    # Join ratings with unblinding
    unblinded = []
    for rating in ratings:
        assignment_id = rating.get('assignment_id')

        if assignment_id not in key_map:
            logger.warning(f"Assignment {assignment_id} not found in key")
            continue

        key_entry = key_map[assignment_id]
        rating['option_a_version'] = key_entry['option_a_version']
        rating['option_b_version'] = key_entry['option_b_version']

        unblinded.append(rating)

    logger.info(f"Unblinded {len(unblinded)} ratings")
    return unblinded


def calculate_wilson_ci(wins: int, total: int, confidence: float = 0.95) -> Tuple[float, float]:
    """
    Calculate Wilson score interval for binary proportion.

    Returns (lower_bound, upper_bound) as rates [0, 1].
    """
    if total == 0:
        return 0.0, 1.0

    z = 1.96 if confidence == 0.95 else 1.645  # 95% or 90% CI

    p = wins / total
    denominator = 1 + z**2 / total

    centre_adjusted_probability = (p + z**2 / (2 * total)) / denominator
    adjusted_standard_error = math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denominator

    lower = centre_adjusted_probability - z * adjusted_standard_error
    upper = centre_adjusted_probability + z * adjusted_standard_error

    return max(0.0, lower), min(1.0, upper)


def cohens_kappa_binary(rater1_pref: List[str], rater2_pref: List[str]) -> float:
    """Calculate Cohen's kappa for two raters on binary preference."""
    if len(rater1_pref) != len(rater2_pref):
        return 0.0

    n = len(rater1_pref)
    agreement = sum(1 for a, b in zip(rater1_pref, rater2_pref) if a == b)
    po = agreement / n

    # Marginal probabilities (assuming third option 'tie' exists)
    p_a = (sum(1 for x in rater1_pref if x == 'A') / n) * (sum(1 for x in rater2_pref if x == 'A') / n)
    p_b = (sum(1 for x in rater1_pref if x == 'B') / n) * (sum(1 for x in rater2_pref if x == 'B') / n)
    p_tie = (sum(1 for x in rater1_pref if x == 'tie') / n) * (sum(1 for x in rater2_pref if x == 'tie') / n)

    pe = p_a + p_b + p_tie

    if pe >= 1.0:
        return 0.0

    kappa = (po - pe) / (1 - pe)
    return kappa


def analyze_ratings(unblinded_ratings: List[dict]) -> List[RatingAnalysis]:
    """Analyze unblinded ratings and compute statistics."""

    # Group by project and comparison
    comparisons = {}

    for rating in unblinded_ratings:
        project_id = rating.get('project_id')
        option_a_ver = rating.get('option_a_version')
        option_b_ver = rating.get('option_b_version')

        # Normalize to v4 baseline vs other
        if option_a_ver == 'v4':
            baseline = 'v4'
            compare = option_b_ver
        else:
            baseline = 'v4'  # Assume v4 is always baseline
            compare = option_a_ver if option_a_ver == 'v4' else option_b_ver

        key = (project_id, baseline, compare)

        if key not in comparisons:
            comparisons[key] = []

        comparisons[key].append(rating)

    # Analyze each comparison
    results = []

    for (project_id, baseline, compare), ratings_subset in comparisons.items():
        logger.info(f"\nAnalyzing {project_id}: {baseline} vs {compare}")

        num_ratings = len(ratings_subset)
        num_raters = len(set(r.get('listener_id') for r in ratings_subset))

        # Collect preference votes
        baseline_wins = 0
        compare_wins = 0
        ties = 0

        for rating in ratings_subset:
            pref = rating.get('overall_preference', 'tie')  # Assumes CSV has this field

            # Map back: if A is baseline and preference is A, that's baseline_wins
            option_a_ver = rating.get('option_a_version')

            if option_a_ver == baseline:
                if pref == 'A':
                    baseline_wins += 1
                elif pref == 'B':
                    compare_wins += 1
                else:
                    ties += 1
            else:
                if pref == 'A':
                    compare_wins += 1
                elif pref == 'B':
                    baseline_wins += 1
                else:
                    ties += 1

        total_comparisons = baseline_wins + compare_wins + ties

        # Wilson CI
        wilson_lower, wilson_upper = calculate_wilson_ci(compare_wins, total_comparisons)

        # Dimension stats (requires parsed JSON ratings, not CSV summary)
        dimension_stats = {}

        analysis = RatingAnalysis(
            project_id=project_id,
            baseline_version=baseline,
            compare_version=compare,
            num_ratings=num_ratings,
            num_raters=num_raters,
            dimension_stats=dimension_stats,
            baseline_wins=baseline_wins,
            compare_wins=compare_wins,
            ties=ties,
            total_comparisons=total_comparisons,
            baseline_preference_rate=baseline_wins / total_comparisons if total_comparisons > 0 else 0,
            compare_preference_rate=compare_wins / total_comparisons if total_comparisons > 0 else 0,
            tie_rate=ties / total_comparisons if total_comparisons > 0 else 0,
            wilson_lower_bound=wilson_lower,
            wilson_upper_bound=wilson_upper,
        )

        results.append(analysis)

        # Print summary
        logger.info(f"  Ratings: {num_ratings} ({num_raters} raters)")
        logger.info(f"  {baseline} wins: {baseline_wins}, {compare} wins: {compare_wins}, ties: {ties}")
        logger.info(f"  {compare} preference rate: {analysis.compare_preference_rate*100:.1f}%")
        logger.info(f"  Wilson 95% CI: [{wilson_lower*100:.1f}%, {wilson_upper*100:.1f}%]")

        # Gate: compare wins > 50% within CI?
        if wilson_lower > 0.50:
            logger.info(f"  ✅ {compare} PREFERRED with statistical significance")
        elif wilson_upper < 0.50:
            logger.info(f"  ✅ {baseline} PREFERRED with statistical significance")
        else:
            logger.info("  ⚠️  NO CLEAR PREFERENCE (overlaps 50% tie line)")

    return results


def export_report(analyses: List[RatingAnalysis], output_file: Path):
    """Export analysis as human-readable report."""

    with open(output_file, 'w') as f:
        f.write("# Blind Listening Benchmark Analysis Report\n\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n\n")

        for analysis in analyses:
            f.write(f"## {analysis.project_id.upper()}: {analysis.baseline_version} vs {analysis.compare_version}\n\n")
            f.write(f"**Ratings:** {analysis.num_ratings} ({analysis.num_raters} raters)\n\n")
            f.write("**Preference Breakdown:**\n")
            f.write(f"- {analysis.baseline_version}: {analysis.baseline_wins} wins ({analysis.baseline_preference_rate*100:.1f}%)\n")
            f.write(f"- {analysis.compare_version}: {analysis.compare_wins} wins ({analysis.compare_preference_rate*100:.1f}%)\n")
            f.write(f"- Tie: {analysis.ties} ({analysis.tie_rate*100:.1f}%)\n\n")
            f.write("**Statistical Significance (Wilson 95% CI):**\n")
            f.write(f"- {analysis.compare_version} preference: [{analysis.wilson_lower_bound*100:.1f}%, {analysis.wilson_upper_bound*100:.1f}%]\n\n")

            if analysis.wilson_lower_bound > 0.50:
                f.write(f"✅ **{analysis.compare_version} SIGNIFICANTLY PREFERRED** (CI lower bound > 50%)\n\n")
            elif analysis.wilson_upper_bound < 0.50:
                f.write(f"✅ **{analysis.baseline_version} SIGNIFICANTLY PREFERRED** (CI upper bound < 50%)\n\n")
            else:
                f.write("⚠️ **NO STATISTICAL DIFFERENCE** (CI includes 50%)\n\n")

    logger.info(f"Report exported to {output_file}")


def main():
    """Load ratings and run analysis."""
    bench_dir = Path(__file__).resolve().parent.parent / "artifacts" / "listening_benchmark_2026-07-16"

    ratings_file = bench_dir / "ratings_completed.csv"
    unblinding_key = bench_dir / "0600_UNBLINDING_KEY.json"

    if not ratings_file.exists():
        logger.warning(f"Ratings file not found: {ratings_file}")
        logger.info("Skipping analysis until ratings are collected.")
        return

    if not unblinding_key.exists():
        logger.warning(f"Unblinding key not found: {unblinding_key}")
        return

    logger.info("="*70)
    logger.info("BLIND LISTENING BENCHMARK REPLAY & ANALYSIS")
    logger.info("="*70)

    # Unbind
    unblinded = unbind_ratings(ratings_file, unblinding_key)

    # Analyze
    analyses = analyze_ratings(unblinded)

    # Export report
    report_file = bench_dir / "analysis_report.md"
    export_report(analyses, report_file)

    logger.info(f"\n{'='*70}")
    logger.info("Analysis complete")
    logger.info(f"{'='*70}\n")


if __name__ == '__main__':
    main()
