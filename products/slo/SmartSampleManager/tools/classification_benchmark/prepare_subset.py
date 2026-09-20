import argparse
import hashlib
import json
import os
import shutil
import tempfile
from collections import defaultdict

from build_real_corpus_v2 import SOURCE_ROOT
from source_family import candidate_source_family


FROZEN_TAXONOMY_CLASSES = {
    "Kick", "Snare", "Hi-Hat", "Clap", "Percussion", "Bass One-Shot",
    "Bass Loop", "Synth", "Synth Loop", "Vocal Phrase", "Vocal Loop",
    "Impact", "Riser", "Foley", "FX", "Atmosphere", "Music Loop"
}
MINIMUM_FIVE_FOLD_SUPPORT = 5

def get_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def find_audio_recursive(path):
    audio_files = []
    for root, dirs, files in os.walk(path):
        for f in files:
            if f.lower().endswith((".wav", ".aif", ".aiff", ".flac")) and not f.startswith('.'):
                audio_files.append(os.path.join(root, f))
    audio_files.sort()
    return audio_files


def validate_class_coverage(
    class_counts,
    class_families=None,
    family_classes=None,
    minimum=MINIMUM_FIVE_FOLD_SUPPORT,
):
    """Reject a subset that cannot support a complete grouped scorecard."""
    missing = sorted(FROZEN_TAXONOMY_CLASSES.difference(class_counts))
    insufficient = sorted(
        (name, class_counts.get(name, 0))
        for name in FROZEN_TAXONOMY_CLASSES
        if class_counts.get(name, 0) < minimum
    )
    insufficient_families = []
    if class_families is not None:
        insufficient_families = sorted(
            (name, len(class_families.get(name, set())))
            for name in FROZEN_TAXONOMY_CLASSES
            if len(class_families.get(name, set())) < minimum
        )
    mixed_families = []
    if family_classes is not None:
        mixed_families = sorted(
            (family, sorted(labels))
            for family, labels in family_classes.items()
            if len(labels) > 1
        )
    if missing or insufficient or insufficient_families or mixed_families:
        raise RuntimeError(
            "Cannot publish classification subset: frozen 17-class coverage "
            f"is incomplete; missing={missing}, insufficient={insufficient}, "
            f"insufficient_families={insufficient_families}, "
            f"mixed_families={mixed_families[:5]}"
        )

def collect_subset_plan(corpus_dir, dest_dir, base_dir, target_count, ood_target):
    """Build and validate a copy plan without mutating the destination."""
    selected_items = []
    planned_copies = []
    class_counts = defaultdict(int)
    class_families = defaultdict(set)
    family_classes = defaultdict(set)
    
    # Define mapping paths
    sounds_of_kshmr = os.path.join(corpus_dir, "Sounds of KSHMR Vol.3")
    
    # Standard mappings
    std_mappings = [
        ("KSHMR_Drums/KSHMR_Kicks", "Kick"),
        ("KSHMR_Drums/KSHMR_Snares", "Snare"),
        ("KSHMR_Drums/KSHMR_Claps", "Clap"),
        ("KSHMR_Drums/KSHMR_Cymbals", "Hi-Hat"),
        ("KSHMR_Drums/KSHMR_Percussion", "Percussion"),
        ("KSHMR_Synths/KSHMR_Bass_Shots", "Bass One-Shot"),
        ("KSHMR_Synths/KSHMR_Bass_PsyTrance", "Bass Loop"),
        ("KSHMR_Synths/KSHMR_Synth_Shots", "Synth"),
        ("KSHMR_Synths/KSHMR_Synth_Loops", "Synth Loop"),
        ("KSHMR_Vocals/KSHMR_Vocals_Loops_and_Melodies", "Vocal Loop"),
        ("KSHMR_Vocals/KSHMR_Vocals_Words_And_Phrases", "Vocal Phrase"),
        ("KSHMR_FX_Elements/KSHMR_Impacts", "Impact"),
        ("KSHMR_FX_Elements/KSHMR_Ambiance_and_Foley", "Foley"),
        ("KSHMR_FX_Elements/KSHMR_Glitches_and_Industrial", "FX"),
        # Map sweeps/lazers containing "Riser" or "Sweep" to Riser
        ("KSHMR_FX_Elements/KSHMR_Sweeps_and_Lazers", "Riser"),
        # Map song starters / action loops to Music Loop
        ("KSHMR_Song_Starters", "Music Loop"),
        ("KSHMR_FX_Elements/KSHMR_Ambiance_and_Foley", "Atmosphere")
    ]
    
    # Walk and collect
    for subpath, subcat in std_mappings:
        full_subpath = os.path.join(sounds_of_kshmr, subpath)
        if not os.path.exists(full_subpath):
            continue
        
        audio_files = find_audio_recursive(full_subpath)
        for src_file in audio_files:
            filename = os.path.basename(src_file)
            
            # Apply naming filters for special subclasses
            if subcat == "Riser" and not ("riser" in filename.lower() or "sweep" in filename.lower()):
                continue
            if subcat == "Atmosphere" and not ("ambience" in filename.lower() or "atmos" in filename.lower() or "texture" in filename.lower()):
                continue
            if subcat == "Foley" and ("ambience" in filename.lower() or "atmos" in filename.lower()):
                continue
                
            if class_counts[subcat] >= target_count:
                break
                
            # Copy file with unique name prefix to avoid collisions
            dest_filename = f"{len(selected_items):04d}_{filename}"
            dest_file = os.path.join(dest_dir, dest_filename)
            planned_copies.append((src_file, dest_file))
            
            sha = get_sha256(src_file)
            family = candidate_source_family("KSHMR", subpath, filename)
            
            selected_items.append({
                "sample_id": len(selected_items) + 1,
                "sha256": sha,
                "filename": dest_filename,
                "local_relative_path": os.path.relpath(dest_file, base_dir),
                "vendor_id": "KSHMR",
                "pack_id": "Sounds_of_KSHMR_Vol3",
                "source_family": family,
                "expected_subcategory": subcat,
                "label_authority": "TRUSTED_PACK_LABEL",
                "label_confidence": "HIGH",
                "ambiguous": False,
                "ood": False,
                "notes": f"Real KSHMR sample mapped to {subcat}"
            })
            class_counts[subcat] += 1
            class_families[subcat].add(family)
            family_classes[family].add(subcat)
            
    # OOD folders
    ood_folders = [
        "KSHMR_Live_Instruments/KSHMR_Main_Instruments",
        "KSHMR_Live_Instruments/KSHMR_Orchestral_Instruments",
        "KSHMR_FX_Elements/KSHMR_Animals",
        "KSHMR_FX_Elements/KSHMR_White_Noise"
    ]
    
    ood_count = 0
    for subpath in ood_folders:
        full_subpath = os.path.join(sounds_of_kshmr, subpath)
        if not os.path.exists(full_subpath):
            continue
            
        audio_files = find_audio_recursive(full_subpath)
        for src_file in audio_files:
            if ood_count >= ood_target:
                break
                
            filename = os.path.basename(src_file)
            dest_filename = f"{len(selected_items):04d}_{filename}"
            dest_file = os.path.join(dest_dir, dest_filename)
            planned_copies.append((src_file, dest_file))
            
            sha = get_sha256(src_file)
            family = candidate_source_family("KSHMR", subpath, filename)
            
            selected_items.append({
                "sample_id": len(selected_items) + 1,
                "sha256": sha,
                "filename": dest_filename,
                "local_relative_path": os.path.relpath(dest_file, base_dir),
                "vendor_id": "KSHMR",
                "pack_id": "Sounds_of_KSHMR_Vol3",
                "source_family": family,
                "expected_subcategory": "OOD",
                "label_authority": "OWNER_VERIFIED",
                "label_confidence": "HIGH",
                "ambiguous": False,
                "ood": True,
                "notes": "Real-world acoustic OOD sample"
            })
            ood_count += 1
            
    # Do not silently publish a partial taxonomy dataset.  In particular,
    # Atmosphere can be sparse under filename filtering; a one-file class
    # cannot support a complete five-fold scorecard.
    validate_class_coverage(class_counts, class_families, family_classes)

    return selected_items, planned_copies, class_counts, ood_count


def publish_subset(selected_items, planned_copies, dest_dir, manifest_path):
    """Publish a validated subset using a staged directory and atomic swaps.

    Existing output remains untouched if planning or copying fails. If a
    previous output exists, it is moved to a uniquely named sibling backup
    before the new directory is installed, so the replacement is recoverable.
    """
    destination_parent = os.path.dirname(os.path.abspath(dest_dir))
    manifest_parent = os.path.dirname(os.path.abspath(manifest_path))
    os.makedirs(destination_parent, exist_ok=True)
    os.makedirs(manifest_parent, exist_ok=True)

    stage_dir = tempfile.mkdtemp(
        prefix=f".{os.path.basename(dest_dir)}.staging-",
        dir=destination_parent,
    )
    manifest_stage = None
    backup_dir = None
    manifest_backup = None
    installed_stage = False
    try:
        for src_file, dest_file in planned_copies:
            shutil.copy2(src_file, os.path.join(stage_dir, os.path.basename(dest_file)))

        manifest_stage = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=manifest_parent,
            prefix=f".{os.path.basename(manifest_path)}.staging-",
        )
        with manifest_stage:
            json.dump(selected_items, manifest_stage, indent=4)
            manifest_stage.write("\n")
        manifest_stage_path = manifest_stage.name

        if os.path.lexists(manifest_path):
            manifest_fd, manifest_backup = tempfile.mkstemp(
                prefix=f".{os.path.basename(manifest_path)}.previous-",
                dir=manifest_parent,
            )
            os.close(manifest_fd)
            os.unlink(manifest_backup)
            os.replace(manifest_path, manifest_backup)

        if os.path.lexists(dest_dir):
            backup_dir = tempfile.mkdtemp(
                prefix=f".{os.path.basename(dest_dir)}.previous-",
                dir=destination_parent,
            )
            os.rmdir(backup_dir)
            os.replace(dest_dir, backup_dir)

        os.replace(stage_dir, dest_dir)
        installed_stage = True
        os.replace(manifest_stage_path, manifest_path)
        return backup_dir
    except Exception:
        if os.path.lexists(manifest_stage.name if manifest_stage else ""):
            os.unlink(manifest_stage.name)
        if installed_stage and os.path.lexists(dest_dir):
            os.replace(dest_dir, stage_dir)
        if os.path.isdir(stage_dir):
            shutil.rmtree(stage_dir)
        if backup_dir and not os.path.lexists(dest_dir) and os.path.lexists(backup_dir):
            os.replace(backup_dir, dest_dir)
        if manifest_backup and not os.path.lexists(manifest_path) and os.path.lexists(manifest_backup):
            os.replace(manifest_backup, manifest_path)
        raise


def build_subset(corpus_dir, dest_dir, manifest_path, target_count=100, ood_target=250, dry_run=False):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    selected_items, planned_copies, class_counts, ood_count = collect_subset_plan(
        corpus_dir, dest_dir, base_dir, target_count, ood_target
    )
    if not dry_run:
        backup_dir = publish_subset(selected_items, planned_copies, dest_dir, manifest_path)
        if backup_dir:
            print(f"Previous subset preserved at {backup_dir}")
    return {
        "selected_count": len(selected_items),
        "known_count": len(selected_items) - ood_count,
        "ood_count": ood_count,
        "class_counts": dict(sorted(class_counts.items())),
        "dry_run": dry_run,
    }


def main(argv=None):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(
        description="Prepare a validated SLO classification scan subset"
    )
    parser.add_argument("--corpus-dir", default=SOURCE_ROOT)
    parser.add_argument(
        "--output-dir",
        default=os.path.join(base_dir, "fixtures", "scan_subset"),
    )
    parser.add_argument(
        "--manifest-path",
        default=os.path.join(base_dir, "dataset_manifest.json"),
    )
    parser.add_argument("--target-count", type=int, default=100)
    parser.add_argument("--ood-target", type=int, default=250)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report the plan without copying or replacing files",
    )
    args = parser.parse_args(argv)
    result = build_subset(
        args.corpus_dir,
        args.output_dir,
        args.manifest_path,
        args.target_count,
        args.ood_target,
        args.dry_run,
    )
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
