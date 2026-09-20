#!/usr/bin/env python3
"""
Listening benchmark scorecard definition and validation.

Structured rating form for blind listening test with:
- Per-dimension 0–10 scales (balance, lead, low-end, masking, punch, depth, width, artifacts, intent, overall)
- Confidence indicators
- Optional free-text reasons
- Strict schema validation
"""

import json
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class DimensionRating:
    """Single dimension rating (0–10)."""
    dimension: str  # balance, lead, low_end, masking, punch, depth, width, artifacts, intent
    score: int  # 0–10
    confidence: int  # 0–5 (0=guessing, 5=very confident)
    notes: Optional[str] = None


@dataclass
class OverallPreference:
    """Overall preference verdict."""
    preference: str  # 'A', 'B', or 'tie'
    confidence: int  # 0–5
    notes: Optional[str] = None


@dataclass
class ListeningRating:
    """Complete listening test rating for one assignment."""
    assignment_id: str
    listener_id: str
    project_id: str

    # Dimensions
    balance: DimensionRating  # Tonal balance, avoiding mud or harshness
    lead_focus: DimensionRating  # Clarity and prominence of focal element
    low_end: DimensionRating  # Kick/bass clarity, translation, not boomy/muddy
    masking: DimensionRating  # Separation of competing elements
    punch: DimensionRating  # Impact, dynamics, transient clarity
    depth: DimensionRating  # Sense of distance/dimension from effects
    width: DimensionRating  # Stereo image, not phasey
    artifacts: DimensionRating  # Absence of clicks, pumping, distortion, artifacts
    intent_preservation: DimensionRating  # Does the mix honor the producer's rough balance?

    # Overall preference
    overall: OverallPreference

    # Metadata
    playback_environment: str  # Studio, headphones, car, etc.
    listening_date: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_minutes: Optional[float] = None  # How long the rater spent
    notes: Optional[str] = None


SCORECARD_SCHEMA = {
    "type": "object",
    "properties": {
        "assignment_id": {"type": "string"},
        "listener_id": {"type": "string"},
        "project_id": {"type": "string"},
        "balance": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "enum": ["balance"]},
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 5},
                "notes": {"type": ["string", "null"]}
            },
            "required": ["dimension", "score", "confidence"]
        },
        "lead_focus": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "enum": ["lead_focus"]},
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 5},
                "notes": {"type": ["string", "null"]}
            },
            "required": ["dimension", "score", "confidence"]
        },
        "low_end": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "enum": ["low_end"]},
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 5},
                "notes": {"type": ["string", "null"]}
            },
            "required": ["dimension", "score", "confidence"]
        },
        "masking": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "enum": ["masking"]},
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 5},
                "notes": {"type": ["string", "null"]}
            },
            "required": ["dimension", "score", "confidence"]
        },
        "punch": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "enum": ["punch"]},
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 5},
                "notes": {"type": ["string", "null"]}
            },
            "required": ["dimension", "score", "confidence"]
        },
        "depth": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "enum": ["depth"]},
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 5},
                "notes": {"type": ["string", "null"]}
            },
            "required": ["dimension", "score", "confidence"]
        },
        "width": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "enum": ["width"]},
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 5},
                "notes": {"type": ["string", "null"]}
            },
            "required": ["dimension", "score", "confidence"]
        },
        "artifacts": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "enum": ["artifacts"]},
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 5},
                "notes": {"type": ["string", "null"]}
            },
            "required": ["dimension", "score", "confidence"]
        },
        "intent_preservation": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "enum": ["intent_preservation"]},
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 5},
                "notes": {"type": ["string", "null"]}
            },
            "required": ["dimension", "score", "confidence"]
        },
        "overall": {
            "type": "object",
            "properties": {
                "preference": {"type": "string", "enum": ["A", "B", "tie"]},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 5},
                "notes": {"type": ["string", "null"]}
            },
            "required": ["preference", "confidence"]
        },
        "playback_environment": {"type": "string"},
        "listening_date": {"type": "string"},
        "duration_minutes": {"type": ["number", "null"]},
        "notes": {"type": ["string", "null"]}
    },
    "required": [
        "assignment_id", "listener_id", "project_id",
        "balance", "lead_focus", "low_end", "masking", "punch",
        "depth", "width", "artifacts", "intent_preservation", "overall",
        "playback_environment"
    ]
}


DIMENSION_GUIDANCE = {
    "balance": "How well are the different elements (vocals, drums, bass, instruments) balanced relative to each other? Does the mix feel cohesive or is one element too loud/quiet?",
    "lead_focus": "Is the focal element (usually lead vocal or main instrument) clear and prominent without being overwhelming? Can you hear it over the supporting elements?",
    "low_end": "Does the kick/bass have clarity? Is the low end punchy but not boomy? Does it translate (would it sound good on small speakers)?",
    "masking": "Are competing elements (like simultaneous vocals + guitars, or kick + bass) separated enough? Or do they disappear into each other?",
    "punch": "Does the mix have impact and dynamics? Are transients clear or is everything squashed? Does it have energy?",
    "depth": "Is there a sense of dimension from reverb/delay effects? Or does everything feel flat/dry? Good depth makes the mix feel less claustrophobic.",
    "width": "Is the stereo image appropriate and stable? Does the mix feel too narrow/centered, too wide/phasey, or well-placed?",
    "artifacts": "Do you hear any undesirable sounds: clicks, zippering, pumping, distortion, aliasing, or other digital artifacts?",
    "intent_preservation": "Does this mix preserve what the producer intended with the rough balance? Or has the personality/intent been lost in the processing?",
}


def create_blank_scorecard(assignment_id: str, listener_id: str, project_id: str) -> dict:
    """Create a blank scorecard template for a rater to fill in."""
    return {
        "assignment_id": assignment_id,
        "listener_id": listener_id,
        "project_id": project_id,
        "instructions": "Rate each dimension 0–10. 0=poor/bad, 5=neutral/acceptable, 10=excellent/ideal. Confidence: 0=guessing, 5=very confident.",
        "dimension_guidance": DIMENSION_GUIDANCE,
        "balance": {"dimension": "balance", "score": None, "confidence": None, "notes": None},
        "lead_focus": {"dimension": "lead_focus", "score": None, "confidence": None, "notes": None},
        "low_end": {"dimension": "low_end", "score": None, "confidence": None, "notes": None},
        "masking": {"dimension": "masking", "score": None, "confidence": None, "notes": None},
        "punch": {"dimension": "punch", "score": None, "confidence": None, "notes": None},
        "depth": {"dimension": "depth", "score": None, "confidence": None, "notes": None},
        "width": {"dimension": "width", "score": None, "confidence": None, "notes": None},
        "artifacts": {"dimension": "artifacts", "score": None, "confidence": None, "notes": None},
        "intent_preservation": {"dimension": "intent_preservation", "score": None, "confidence": None, "notes": None},
        "overall": {"preference": None, "confidence": None, "notes": None},
        "playback_environment": None,
        "listening_date": datetime.now().isoformat(),
        "duration_minutes": None,
        "notes": None
    }


def validate_rating(rating_dict: dict) -> tuple[bool, List[str]]:
    """Validate a completed rating against the schema. Returns (is_valid, errors)."""
    errors = []

    # Check required fields
    required_fields = [
        "assignment_id", "listener_id", "project_id",
        "playback_environment"
    ]
    for field_name in required_fields:
        if field_name not in rating_dict or rating_dict[field_name] is None:
            errors.append(f"Missing required field: {field_name}")

    # Check dimension scores
    dimensions = [
        "balance", "lead_focus", "low_end", "masking", "punch",
        "depth", "width", "artifacts", "intent_preservation"
    ]
    for dim in dimensions:
        if dim not in rating_dict or rating_dict[dim] is None:
            errors.append(f"Missing dimension: {dim}")
            continue

        d = rating_dict[dim]
        if "score" not in d or d["score"] is None or not (0 <= d["score"] <= 10):
            errors.append(f"{dim}: score must be 0–10")
        if "confidence" not in d or d["confidence"] is None or not (0 <= d["confidence"] <= 5):
            errors.append(f"{dim}: confidence must be 0–5")

    # Check overall preference
    if "overall" not in rating_dict or rating_dict["overall"] is None:
        errors.append("Missing overall preference")
    else:
        o = rating_dict["overall"]
        if "preference" not in o or o["preference"] not in ["A", "B", "tie"]:
            errors.append("Overall preference must be 'A', 'B', or 'tie'")
        if "confidence" not in o or o["confidence"] is None or not (0 <= o["confidence"] <= 5):
            errors.append("Overall confidence must be 0–5")

    return len(errors) == 0, errors


def main():
    """Generate blank scorecards for example assignments."""
    from pathlib import Path

    output_dir = Path(__file__).resolve().parent.parent / "artifacts" / "listening_benchmark_2026-07-16"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Generating blank scorecard template...")

    blank = create_blank_scorecard("example-assignment-id", "jack", "dream_of_you")

    scorecard_file = output_dir / "blank_scorecard_template.json"
    with open(scorecard_file, 'w') as f:
        json.dump(blank, f, indent=2)

    logger.info(f"✅ Blank scorecard template: {scorecard_file}")

    # Save schema
    schema_file = output_dir / "scorecard_schema.json"
    with open(schema_file, 'w') as f:
        json.dump(SCORECARD_SCHEMA, f, indent=2)

    logger.info(f"✅ Scorecard schema: {schema_file}")


if __name__ == '__main__':
    main()
