#!/usr/bin/env python3
"""Builds fixtures/real_corpus_v2 -- an expanded real-corpus benchmark corpus.

Reuses the exact same trusted folder-to-SLO-category mapping that produced
real_corpus_v1 (reverse-engineered from real_corpus_v1_manifest.json, since
the original v1 generator script was never committed to this repo), but
removes v1's 60-files/class and 15-files/vendor/class runtime caps -- using
ALL files in each already-trusted, already-mapped folder instead. Also adds
Black Lotus Audio x Dianna Artist Pack as a 14th vendor (Spoken Phrases +
Sung Phrases -> Vocal Phrase; "Misc Sounds" deliberately excluded -- that
folder name alone doesn't give confident category signal the way every
other mapped folder here does).

Produces two directory trees, matching real_corpus_v1's shape:
  - full_evidence/  -- files copied with their real original filenames,
    nested under <NN>__<subcategory>/ folders, so filename/folder evidence
    is intact (measures the taxonomy's normal, real-world behavior).
  - audio_only/     -- the same files copied flat with generic sequential
    names (sample_NNNNNN.wav), so filename/folder evidence is stripped
    (measures what the DSP/ML classifier alone can do).

Post-V2 correction (see FX_FOLEY_RISER_FORENSIC_AUDIT_V1.md, which found this
exact defect in V1's inherited mapping before V2 copied it forward unfixed):
two kinds of folders were blanket-labeled a single category despite actually
containing a mix, or containing individually-named stems that aren't that
category at all. Fixed here at the source rather than just documented again:
  - "Koan Sound Samples/Sentient/sentient_bass+drums+fx" was mapped to FX
    wholesale, but every file in it is an individually-named real instrument
    stem (Kick.wav, Hi-Hat.wav, Snare.wav, Bass Guitar.wav, Vox.wav, ...) --
    excluded entirely rather than force a single-category label onto content
    that is deliberately heterogeneous by design.
  - Drum Recollection's two "Percs & Fx"/"Percs & FX" folders are genuinely
    mixed (their own name says so): most files are named "...Perc.wav",
    a few "...Fx.wav". These are now split by filename keyword instead of
    blanket-mapped, via FILENAME_KEYWORD_SPLIT_FOLDERS below.

Post-fix addition (see SLO_ACCURACY_ROADMAP_V1.md's Stage 1): Synth, Synth
Loop, Vocal Loop, and Music Loop had zero real-corpus coverage in every prior
revision -- not proven weak, just never measured. Closed using the same
trusted-folder-name method as everything else here: KSHMR_Synth_Shots/
KSHMR_Synth_Loops/KSHMR_Vocals_Loops_and_Melodies/KSHMR_Song_Starters, plus
Minimal Audio's Synth Oneshots and "Melodic Loop"-named Melodics Loops folder
for Synth/Synth Loop cross-vendor diversity. Vocal Loop and Music Loop remain
single-vendor (KSHMR only) -- no other vendor in this library had a folder
confident enough to trust for these two; noted honestly in the report rather
than forcing a weaker match.

Does not touch, move, rename, or modify any file in the source tester
library -- read-only copies only.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

from source_family import candidate_source_family

SOURCE_ROOT = "/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing"
AUDIO_EXTS = (".wav", ".aif", ".aiff", ".flac")

# vendor -> {folder relative to vendor root: SLO expected_subcategory}
# Reverse-engineered from real_corpus_v1_manifest.json's full_evidence_relpath
# field, one entry per distinct trusted folder that manifest actually used.
MAPPING = {
    "MGF Mega Pack": {
        "Analogue Collection/Bass": "Bass One-Shot",
        "Analogue Collection/Perc": "Percussion",
        "Misc + Found Sound/Casiotone 501/Multis/Organ Pad": "Atmosphere",
        "Misc + Found Sound/Chromaphone/Percussion": "Percussion",
        "Misc + Found Sound/Household Percussion April 2016": "Percussion",
        "Misc + Found Sound/UTS Foley 2": "Foley",
        "Multisamples/Alpha Juno Jungle Bass Multis 1/Jungle Bass 2": "Bass One-Shot",
        "Multisamples/Alpha Juno Jungle Bass Multis 1/Jungle Bass 6": "Bass One-Shot",
        "Multisamples/DX21 Chorus Pack/Boc Pad 2": "Atmosphere",
        "Multisamples/MGF Alpha Juno Vol 8/Muffle Pad": "Atmosphere",
        "Multisamples/MGF DX11 Vol 4/DTROIT BASS": "Bass One-Shot",
        "Multisamples/MGF DX21 Vol 1/DTROIT Bass 1": "Bass One-Shot",
        "Multisamples/MGF JX3P Vol 5/Washboard Pad": "Atmosphere",
        "Multisamples/MGF Minilogue Vol 1/Toady Pad": "Atmosphere",
        "Multisamples/MGF Minilogue Vol 1/Traxx Bass": "Bass One-Shot",
        "Multisamples/MGF Sub Phatty 1/RGB Bass": "Bass One-Shot",
        "Retro Digital Collection/Bass": "Bass One-Shot",
    },
    "Sounds of KSHMR Vol.3": {
        "KSHMR_Drums/KSHMR_Acoustic_Drums/Hi-Hat": "Hi-Hat",
        "KSHMR_Drums/KSHMR_Acoustic_Drums/Impact": "Impact",
        "KSHMR_Drums/KSHMR_Acoustic_Drums/Kick": "Kick",
        "KSHMR_Drums/KSHMR_Acoustic_Drums/Percussion": "Percussion",
        "KSHMR_Drums/KSHMR_Acoustic_Drums/Snare": "Snare",
        "KSHMR_Drums/KSHMR_Claps/KSHMR_Church_Claps/Clap": "Clap",
        "KSHMR_VIP_Friends_of_KSHMR/BASSJACKERS": "Bass One-Shot",
        # Added to close the Synth/Synth Loop/Vocal Loop/Music Loop
        # zero-measurement gap flagged in SLO_ACCURACY_ROADMAP_V1.md --
        # these 4 classes had no real-corpus coverage at all before this.
        "KSHMR_Synths/KSHMR_Synth_Shots": "Synth",
        "KSHMR_Synths/KSHMR_Synth_Loops": "Synth Loop",
        "KSHMR_Vocals/KSHMR_Vocals_Loops_and_Melodies": "Vocal Loop",
        "KSHMR_Song_Starters/KSHMR_Song_Starters_Main": "Music Loop",
        "KSHMR_Song_Starters/KSHMR_Song_Starters_Hip_Hop": "Music Loop",
    },
    "Loaded Samples - Lo-Fi Memphis 2": {
        "DRUMS & PERC LOOPS": "Percussion",
        "DRUMS/FX": "FX",
        "DRUMS/Hats": "Hi-Hat",
        "DRUMS/Kicks & 808s": "Kick",
        "DRUMS/Perc": "Percussion",
        "DRUMS/Snares": "Snare",
        "MISC SAMPLES (Bass & More)": "Bass One-Shot",
        "VOCALS": "Vocal Phrase",
    },
    "Organic Drum Kit": {
        "1 Kicks": "Kick",
        "2 Snares": "Snare",
        "3 Claps": "Clap",
        "4 Hi-Hats/1 Closed Hats": "Hi-Hat",
        "4 Hi-Hats/2 Open Hats": "Hi-Hat",
        "5 Percussion/2 Cajon Box/1 Cajon Box/1 Bass Slap": "Bass One-Shot",
        "5 Percussion/2 Cajon Box/1 Cajon Box/2 Snare Slap": "Snare",
        "5 Percussion/3 Various Percussion": "Percussion",
        "5 Percussion/6 Wooden/2 Wooden Perc B": "Percussion",
        "5 Percussion/6 Wooden/3 Wooden Perc C": "Percussion",
        "8 Drum Loops/Percussion Loops": "Percussion",
        "Maschine Kits/Deep Impact Kit Samples": "Impact",
    },
    "Old Movies 1 - Vintage Collection (Drum Kit)": {
        "Foley & Percussion (Old Movies)": "Percussion",
        "Hats": "Hi-Hat",
        "Kicks": "Kick",
        "Noise & Texture (Old Movies)": "Atmosphere",
        "Snares": "Snare",
        "Vocal Elements (Old Movies)": "Vocal Phrase",
    },
    "Minimal Audio": {
        "ELEMENT/1 - Drums/1 - Drum Loops/2 - Kick Loops": "Kick",
        "ELEMENT/1 - Drums/2 - Kick": "Kick",
        "ELEMENT/1 - Drums/4 - Hats": "Hi-Hat",
        "ELEMENT/3 - Bass Loops": "Bass Loop",
        "ELEMENT/4 - Atmospheric Loops": "Atmosphere",
        "ELEMENT/5 - Deep Textures": "Atmosphere",
        "IMPULSE/1 - Impacts/1 - Impact - Full": "Impact",
        "IMPULSE/1 - Impacts/2 - Impact - Bass": "Impact",
        "IMPULSE/1 - Impacts/3 - Impact - Accents": "Impact",
        "IMPULSE/2 - Sweeps/1 - Risers": "Riser",
        "IMPULSE/4 - Future Drones": "Atmosphere",
        "MICROTECH/1 - Loops/1 - Kick - 172 BPM": "Kick",
        "MICROTECH/1 - Loops/2 - Snare - 172 BPM": "Snare",
        "MICROTECH/1 - Loops/3 - Perc - 172 BPM": "Percussion",
        "MICROTECH/1 - Loops/4 - Hi Hat - 172 BPM": "Hi-Hat",
        "MICROTECH/1 - Loops/5 - Glitch FX - 172 BPM": "FX",
        "MICROTECH/2 - One Shots/1 - Kick": "Kick",
        "MICROTECH/2 - One Shots/2 - Snare": "Snare",
        "MICROTECH/2 - One Shots/3 - Perc": "Percussion",
        "MICROTECH/2 - One Shots/4 - Hi Hat": "Hi-Hat",
        "OXIDE/2 - Impacts": "Impact",
        "OXIDE/4 - Atmospheres": "Atmosphere",
        "REFLECT/1 - Drums/1 - Loops/2 - Kick": "Kick",
        "REFLECT/1 - Drums/1 - Loops/4 - Hi Hats": "Hi-Hat",
        "REFLECT/1 - Drums/1 - Loops/5 - Foley Loops": "Foley",
        "REFLECT/1 - Drums/2 - Kick ": "Kick",
        "REFLECT/1 - Drums/3 - Snare": "Snare",
        "REFLECT/1 - Drums/4 - Claps": "Clap",
        "REFLECT/1 - Drums/5 - Hats & Cymbals": "Hi-Hat",
        "REFLECT/2 - Melodics/3 - Vocal Oneshots": "Vocal Phrase",
        "REFLECT/2 - Melodics/2 - Synth Oneshots": "Synth",
        "REFLECT/3 - Noise Textures": "Atmosphere",
        "REFLECT/4 - Bass Loops": "Bass Loop",
        # "Melodic Loop" filenames (e.g. "Melodic Loop - Gated Harmonics 1 -
        # C - 78 BPM.wav") are melodic/synth-instrument loops, not full-mix
        # song loops -- Synth Loop, not Music Loop.
        "ELEMENT/2 - Melodics/1 - Melodics Loops": "Synth Loop",
    },
    "Daniel Sadownick - Creative Percussion": {
        "RT_Daniel_Sadownick_Degraw_Session/one_shot/Percussion": "Percussion",
    },
    "Capsun ProAudio - City Pop": {
        "Loops/Drum_Loops/Hihat": "Hi-Hat",
        "Loops/Drum_Loops/Percussion": "Percussion",
        "One_Shots/Drum_One_Shots/Hihats": "Hi-Hat",
        "One_Shots/Drum_One_Shots/Kicks": "Kick",
        "One_Shots/Drum_One_Shots/Percussion": "Percussion",
        "One_Shots/Drum_One_Shots/Snares": "Snare",
    },
    "Black Octopus Sound - Pure Analog Sweeps IV (2021)": {
        "Xtra Analog Atmospheres": "Atmosphere",
    },
    "Breaks": {
        "Gems From The Crates/Claps": "Clap",
        "Gems From The Crates/Kicks": "Kick",
        "Gems From The Crates/Snares": "Snare",
        "The Drum Broker - International Breaks & Essential Kicks/"
        "The Drum Broker - Essential Kicks": "Kick",
    },
    "Drum Recollection": {
        "Essentials Drum Kit Vol. 001/Claps": "Clap",
        "Essentials Drum Kit Vol. 001/Hi Hats": "Hi-Hat",
        "Essentials Drum Kit Vol. 001/Open Hats": "Hi-Hat",
        "Essentials Drum Kit Vol. 001/Snares": "Snare",
        "Essentials Drumkit Vol. 002/Claps": "Clap",
        "Essentials Drumkit Vol. 002/Hi-Hats": "Hi-Hat",
        "Essentials Drumkit Vol. 002/Open Hats": "Hi-Hat",
        # "Essentials Drumkit Vol. 002/Percs & Fx" removed from this flat
        # mapping -- see FILENAME_KEYWORD_SPLIT_FOLDERS below.
        "Essentials Drumkit Vol. 002/Snares": "Snare",
        "New Wave Drum Kit Vol. 1/New Wave Drum Kit/Claps": "Clap",
        "New Wave Drum Kit Vol. 1/New Wave Drum Kit/Snares": "Snare",
        "New Wave Drum Kit Vol. 2/Claps": "Clap",
        "New Wave Drum Kit Vol. 2/Hi-Hats": "Hi-Hat",
        "New Wave Drum Kit Vol. 2/Kicks": "Kick",
        "New Wave Drum Kit Vol. 2/Open Hats": "Hi-Hat",
        # "New Wave Drum Kit Vol. 2/Percs & FX" removed from this flat
        # mapping -- see FILENAME_KEYWORD_SPLIT_FOLDERS below.
        "New Wave Drum Kit Vol. 2/Snares": "Snare",
        "Official Drum Kit Vol. 1/Claps": "Clap",
        "Official Drum Kit Vol. 1/Hi Hats": "Hi-Hat",
        "Official Drum Kit Vol. 1/Kicks": "Kick",
        "Official Drum Kit Vol. 1/Snares": "Snare",
        "Official Drum Kit Vol. 2/Claps": "Clap",
        "Official Drum Kit Vol. 2/Hi-Hats": "Hi-Hat",
        "Official Drum Kit Vol. 2/Kicks": "Kick",
        "Official Drum Kit Vol. 2/Snares": "Snare",
    },
    "Just Jared - OP1 Drums": {
        "FX": "FX",
        "Hihats": "Hi-Hat",
        "Kicks": "Kick",
        "Snares": "Snare",
    },
    "Koan Sound": {
        "Koan Sound Samples 2/Foley Pack 02": "Foley",
        "Koan Sound Samples/Bass Processed": "Bass One-Shot",
        "Koan Sound Samples/Foley Pack 01/Complex Foley": "Foley",
        "Koan Sound Samples/Foley Pack 01/Foley Drums": "Foley",
        "Koan Sound Samples/Foley Pack 01/Raw Foley": "Foley",
        "Koan Sound Samples/Foley Pack 02": "Foley",
        "Koan Sound Samples/Raw Moog Bass": "Bass One-Shot",
        # "Koan Sound Samples/Sentient/sentient_bass+drums+fx" deliberately
        # excluded -- see the module docstring's "Post-V2 correction" note.
    },
    "KRANE Samples": {
        "KRNE_SpliceSamplePack/Vox": "Vocal Phrase",
    },
    # New 14th vendor this pass. "Misc Sounds" deliberately excluded --
    # unlike every folder above, that name alone doesn't give confident
    # category signal (same bar applied throughout this session's other
    # trusted-label decisions).
    "Black Lotus Audio x Dianna Artist Pack": {
        "Spoken Phrases": "Vocal Phrase",
        "Sung Phrases": "Vocal Phrase",
    },
}

# Folders whose own name admits they're mixed-content ("Percs & Fx") and
# whose files confirm it (some literally named "...Perc.wav", others
# "...Fx.wav") -- these get a per-file category from a filename keyword
# instead of MAPPING's single per-folder category. Keyword checks are
# case-insensitive substring matches, tried in order; a file matching
# neither keyword is skipped (reported, not guessed) rather than defaulting
# to either category.
FILENAME_KEYWORD_SPLIT_FOLDERS = {
    ("Drum Recollection", "Essentials Drumkit Vol. 002/Percs & Fx"): [
        ("perc", "Percussion"),
        ("fx", "FX"),
    ],
    ("Drum Recollection", "New Wave Drum Kit Vol. 2/Percs & FX"): [
        ("perc", "Percussion"),
        ("fx", "FX"),
    ],
}


def find_audio_files(root):
    out = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith(AUDIO_EXTS) and not fn.startswith("."):
                out.append(os.path.join(dirpath, fn))
    out.sort()
    return out


def collect_manifest(source_root):
    """Collect provenance without copying, decoding, or hashing audio."""
    manifest = []
    sample_id_holder = [1]
    skipped_missing = []
    skipped_no_keyword_match = []

    def add_sample(src_file, subcat, vendor, relative_folder):
        sample_id = sample_id_holder[0]
        filename = os.path.basename(src_file)
        manifest.append(
            {
                "sample_id": sample_id,
                "expected_subcategory": subcat,
                "source_path": os.path.realpath(src_file),
                "source_vendor": vendor,
                "vendor_id": vendor,
                "pack_id": vendor,
                "source_family": candidate_source_family(
                    vendor, relative_folder, filename
                ),
                "label_authority": "TRUSTED_FOLDER_MAPPING",
                "original_filename": filename,
                "full_evidence_relpath": os.path.join(
                    subcat.replace(" ", "_"), f"{sample_id:06d}__{filename}"
                ),
                "audio_only_filename": (
                    f"sample_{sample_id:06d}{os.path.splitext(filename)[1].lower()}"
                ),
            }
        )
        sample_id_holder[0] += 1

    for vendor, folders in MAPPING.items():
        for relative_folder, subcat in folders.items():
            src_folder = os.path.join(source_root, vendor, relative_folder)
            if not os.path.isdir(src_folder):
                skipped_missing.append(src_folder)
                continue
            for src_file in find_audio_files(src_folder):
                add_sample(src_file, subcat, vendor, relative_folder)

    for (vendor, relative_folder), keyword_rules in FILENAME_KEYWORD_SPLIT_FOLDERS.items():
        src_folder = os.path.join(source_root, vendor, relative_folder)
        if not os.path.isdir(src_folder):
            skipped_missing.append(src_folder)
            continue
        for src_file in find_audio_files(src_folder):
            filename_lower = os.path.basename(src_file).lower()
            matched_cat = next(
                (
                    category
                    for keyword, category in keyword_rules
                    if keyword in filename_lower
                ),
                None,
            )
            if matched_cat is None:
                skipped_no_keyword_match.append(src_file)
                continue
            add_sample(src_file, matched_cat, vendor, relative_folder)

    return manifest, skipped_missing, skipped_no_keyword_match


def publish_manifest(manifest, manifest_path):
    """Atomically publish a manifest while preserving an existing one."""
    manifest_path = os.path.abspath(manifest_path)
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    backup = None
    stage = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        dir=os.path.dirname(manifest_path),
        prefix=f".{os.path.basename(manifest_path)}.staging-",
    )
    try:
        with stage:
            json.dump(manifest, stage, indent=2)
            stage.write("\n")
        if os.path.lexists(manifest_path):
            fd, backup = tempfile.mkstemp(
                prefix=f".{os.path.basename(manifest_path)}.previous-",
                dir=os.path.dirname(manifest_path),
            )
            os.close(fd)
            os.unlink(backup)
            os.replace(manifest_path, backup)
        os.replace(stage.name, manifest_path)
        return backup
    except Exception:
        if os.path.lexists(stage.name):
            os.unlink(stage.name)
        if backup and not os.path.lexists(manifest_path) and os.path.lexists(backup):
            os.replace(backup, manifest_path)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build or provenance-audit the SLO real-corpus V2 set"
    )
    parser.add_argument("--source-root", default=SOURCE_ROOT)
    parser.add_argument(
        "--output-dir",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "fixtures", "real_corpus_v2"
        ),
    )
    parser.add_argument(
        "--manifest-path",
        help="Manifest destination; defaults inside --output-dir",
    )
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Write only the provenance manifest; do not copy audio",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Allow replacement of an existing full corpus output directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect and report the plan without writing a manifest or audio",
    )
    args = parser.parse_args(argv)

    out_dir = os.path.abspath(args.output_dir)
    manifest_path = os.path.abspath(
        args.manifest_path or os.path.join(out_dir, "real_corpus_v2_manifest.json")
    )
    manifest, skipped_missing, skipped_no_keyword_match = collect_manifest(
        args.source_root
    )

    if args.dry_run:
        print(f"real_corpus_v2 dry-run: {len(manifest)} files")
        print(f"manifest destination: {manifest_path}")
        if skipped_missing:
            print(f"missing mapped folders: {len(skipped_missing)}")
        if skipped_no_keyword_match:
            print(f"unmatched split files: {len(skipped_no_keyword_match)}")
        return 0

    if args.manifest_only:
        backup = publish_manifest(manifest, manifest_path)
        if backup:
            print(f"Previous manifest preserved at {backup}")
        print(f"Manifest-only output written to: {manifest_path}")
        print(f"Collected {len(manifest)} files without copying or decoding audio.")
        return 0

    if os.path.isdir(out_dir) and not args.replace_existing:
        raise RuntimeError(
            f"Refusing to replace existing corpus output {out_dir!r}; "
            "pass --replace-existing explicitly"
        )

    full_dir = os.path.join(out_dir, "full_evidence")
    audio_dir = os.path.join(out_dir, "audio_only")
    for d in (full_dir, audio_dir):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)

    for item in manifest:
        sample_id = item["sample_id"]
        src_file = item["source_path"]
        subcat = item["expected_subcategory"]
        cat_dir = os.path.join(full_dir, subcat.replace(" ", "_"))
        os.makedirs(cat_dir, exist_ok=True)
        dest_full_name = os.path.basename(item["full_evidence_relpath"])
        full_evidence_relpath = os.path.join(subcat.replace(" ", "_"), dest_full_name)
        shutil.copy2(src_file, os.path.join(cat_dir, dest_full_name))

        audio_only_filename = item["audio_only_filename"]
        shutil.copy2(src_file, os.path.join(audio_dir, audio_only_filename))
        item["full_evidence_relpath"] = full_evidence_relpath

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    by_class = {}
    by_vendor = {}
    for row in manifest:
        by_class[row["expected_subcategory"]] = by_class.get(row["expected_subcategory"], 0) + 1
        by_vendor[row["source_vendor"]] = by_vendor.get(row["source_vendor"], 0) + 1

    print(f"real_corpus_v2: {len(manifest)} files across {len(by_class)} classes, "
          f"{len(by_vendor)} vendors")
    print("Per-class counts:")
    for c, n in sorted(by_class.items(), key=lambda x: -x[1]):
        print(f"  {c:<18} {n}")
    print("Per-vendor counts:")
    for v, n in sorted(by_vendor.items(), key=lambda x: -x[1]):
        print(f"  {v:<50} {n}")
    if skipped_missing:
        print(f"\nWARNING: {len(skipped_missing)} mapped folders not found on disk:")
        for p in skipped_missing:
            print(f"  MISSING: {p}")
    if skipped_no_keyword_match:
        print(f"\nWARNING: {len(skipped_no_keyword_match)} files in keyword-split folders "
              f"matched no keyword (excluded rather than guessed):")
        for p in skipped_no_keyword_match:
            print(f"  UNMATCHED: {p}")
    print(f"\nManifest written to: {manifest_path}")
    print(f"full_evidence/: {full_dir}")
    print(f"audio_only/:    {audio_dir}")


if __name__ == "__main__":
    sys.exit(main())
