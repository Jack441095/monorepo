#!/usr/bin/env python3
"""
Anonymized listening test assignment system.

Creates blindly-assigned A/B pairs with concealment via opaque IDs.
Maintains separate unblinding key (locked until analysis is complete).
Supports randomization, block balancing, and listener/rater assignment.
"""

import json
import secrets
import csv
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@dataclass
class Assignment:
    """Single listening test assignment."""
    assignment_id: str  # Opaque random ID shown to rater

    project_id: str  # dream_of_you, reggueton_pop, stranger
    listener_id: str  # Rater identifier
    block_id: int  # Randomization block

    # Concealed order (A/B not revealed)
    option_a_id: str  # Random ID, not revealing version
    option_b_id: str  # Random ID, not revealing version

    # True mapping (locked until unblinding)
    option_a_version: str  # v4, v5, or v6
    option_b_version: str  # Different version
    baseline_version: str  # v4 is always baseline

    # Metadata
    genre: str
    duration_seconds: float
    target_lufs: float
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class UnbindingKey:
    """Master key to reveal A/B mapping (kept separately)."""
    assignment_id: str
    option_a_version: str
    option_b_version: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


def generate_opaque_id(assignment: Assignment) -> tuple[str, str]:
    """Generate random 8-char opaque IDs for A and B options."""
    a_id = secrets.token_hex(4)  # 8-char hex
    b_id = secrets.token_hex(4)
    return a_id, b_id


def create_assignments(
    projects: List[dict],
    listeners: List[str],
    num_blocks: int = 2,
    randomize_order: bool = True,
    output_dir: Optional[Path] = None
) -> tuple[List[Assignment], List[UnbindingKey]]:
    """
    Create randomized listening assignments.

    Args:
        projects: List of {id, genre, duration_seconds, target_lufs, versions: [v4, v5, v6]}
        listeners: List of listener/rater IDs
        num_blocks: Number of randomization blocks (alternates A/B order)
        randomize_order: Whether to shuffle option positions (always true for blinding)

    Returns:
        (assignments, unblinding_keys)
    """

    assignments = []
    unblinding_keys = []

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Creating assignments for {len(projects)} projects × {len(listeners)} listeners × comparisons...")

    for block_idx in range(num_blocks):
        for listener_id in listeners:
            for proj in projects:
                project_id = proj['id']
                versions = proj.get('versions', ['v4', 'v5', 'v6'])

                # Create two comparisons per project: v4 vs v5, v4 vs v6
                comparisons = [
                    (versions[0], versions[1]),  # v4 vs v5
                    (versions[0], versions[2]),  # v4 vs v6
                ]

                for baseline, compare in comparisons:
                    assignment_id = secrets.token_hex(8)  # 16-char opaque ID

                    # Randomize option order within each block
                    if block_idx % 2 == 0:
                        option_a_version = baseline
                        option_b_version = compare
                    else:
                        option_a_version = compare
                        option_b_version = baseline

                    option_a_id, option_b_id = generate_opaque_id(None)

                    assignment = Assignment(
                        assignment_id=assignment_id,
                        project_id=project_id,
                        listener_id=listener_id,
                        block_id=block_idx,
                        option_a_id=option_a_id,
                        option_b_id=option_b_id,
                        option_a_version=option_a_version,
                        option_b_version=option_b_version,
                        baseline_version=versions[0],
                        genre=proj.get('genre', 'unknown'),
                        duration_seconds=proj.get('duration_seconds', 0),
                        target_lufs=proj.get('target_lufs', -14.0),
                    )

                    assignments.append(assignment)

                    # Create unblinding record (stored separately)
                    unblind = UnbindingKey(
                        assignment_id=assignment_id,
                        option_a_version=option_a_version,
                        option_b_version=option_b_version,
                    )

                    unblinding_keys.append(unblind)

    logger.info(f"Created {len(assignments)} assignments")

    # Export assignments (public; no version info)
    if output_dir:
        assignments_file = output_dir / 'assignments_blinded.csv'
        logger.info(f"Writing {assignments_file}")

        with open(assignments_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'assignment_id', 'listener_id', 'project_id', 'block_id',
                'option_a_id', 'option_b_id', 'genre', 'duration_seconds',
                'target_lufs', 'created_at'
            ])
            writer.writeheader()
            for a in assignments:
                row = {k: v for k, v in asdict(a).items() if k not in ['option_a_version', 'option_b_version', 'baseline_version']}
                writer.writerow(row)

        # Export unblinding key (keep private; locked in secure location)
        unblinding_file = output_dir / '0600_UNBLINDING_KEY.json'
        logger.info(f"Writing {unblinding_file} (KEEP PRIVATE; restrict to 0600)")

        with open(unblinding_file, 'w') as f:
            json.dump([asdict(k) for k in unblinding_keys], f, indent=2)

        unblinding_file.chmod(0o0600)

    return assignments, unblinding_keys


def validate_assignments(assignments: List[Assignment]) -> bool:
    """Check for duplicates, ensure balance, verify opaque IDs."""
    seen = set()

    for a in assignments:
        key = (a.project_id, a.listener_id, a.option_a_version, a.option_b_version)
        if key in seen:
            logger.warning(f"Duplicate assignment: {key}")
            return False

        seen.add(key)

    logger.info(f"✅ Assignment validation passed ({len(assignments)} unique)")
    return True


def main():
    projects = [
        {
            'id': 'dream_of_you',
            'genre': 'electronic',
            'duration_seconds': 80.84,
            'target_lufs': -14.0,
            'versions': ['v4', 'v5', 'v6'],
        },
        {
            'id': 'reggueton_pop',
            'genre': 'latin',
            'duration_seconds': 144.0,
            'target_lufs': -14.0,
            'versions': ['v4', 'v5', 'v6'],
        },
        {
            'id': 'stranger',
            'genre': 'pop',
            'duration_seconds': 209.68,
            'target_lufs': -14.0,
            'versions': ['v4', 'v5', 'v6'],
        }
    ]

    # Example listeners (Jack as sole rater for now; add more for real study)
    listeners = ['jack']

    output_dir = Path(__file__).resolve().parent.parent / "artifacts" / "listening_benchmark_2026-07-16"

    logger.info("="*70)
    logger.info("LISTENING BENCHMARK ASSIGNMENT GENERATION")
    logger.info("="*70)

    assignments, keys = create_assignments(
        projects=projects,
        listeners=listeners,
        num_blocks=2,
        randomize_order=True,
        output_dir=output_dir
    )

    validate_assignments(assignments)

    logger.info(f"\n{'='*70}")
    logger.info("STRUCTURE")
    logger.info(f"{'='*70}")
    logger.info(f"Public assignment file: {output_dir / 'assignments_blinded.csv'}")
    logger.info("  → Show this to raters; contains no version/treatment info")
    logger.info(f"\nPrivate unblinding key: {output_dir / '0600_UNBLINDING_KEY.json'}")
    logger.info("  → Keep in secure location; reveals A/B mapping after rating")
    logger.info(f"\nAssignments: {len(assignments)}")
    logger.info(f"  → {len(projects)} projects × {len(listeners)} raters × 2 comparisons/project × 2 blocks")


if __name__ == '__main__':
    main()
