import os, re, shutil, json

ROOT = "/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing"
OUT = "/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo/SmartSampleManager/tools/classification_benchmark/fixtures/vocal_loop_crossvendor_v1"

manifest = []
sid = 1

def add(path, subcat, vendor, has_signal, signal_type):
    global sid
    manifest.append({
        "sample_id": sid, "source_path": path, "expected_subcategory": subcat,
        "vendor": vendor, "has_signal": has_signal, "signal_type": signal_type,
    })
    sid += 1

# Lo-Fi Memphis: BPM-suffixed -> Loop ground truth; short(<2s) non-BPM -> Phrase ground truth
lfm_dir = os.path.join(ROOT, "Loaded Samples - Lo-Fi Memphis 2/VOCALS")
short_nobpm = {"Fuck a Hoe 1.wav", "Fuck a Hoe 2.wav", "Yeah hoe.wav", "Pimp a bitch.wav"}
for f in os.listdir(lfm_dir):
    if not f.lower().endswith(".wav"):
        continue
    full = os.path.join(lfm_dir, f)
    if re.search(r"\[\d+\s*BPM\]", f, re.IGNORECASE):
        add(full, "Vocal Loop", "Loaded Samples", True, "bpm_key_suffix")
    elif f in short_nobpm:
        add(full, "Vocal Phrase", "Loaded Samples", False, "duration_lt_2s")
    # else: ambiguous, excluded

# Bright Lights: explicit "loop" word + BPM+key
bl_file = os.path.join(ROOT, "Bright Lights Vocal Sample Pack/Bright_Lights_Vocal_Sample_Pack/Backing_Vocals/BL_C#m_120_BVs_loop_GirlGroup_HighHarm.wav")
if os.path.exists(bl_file):
    add(bl_file, "Vocal Loop", "Bright Lights", True, "loop_word+bpm_key_suffix")

# Minimal Audio: vendor-asserted one-shots (folder name), regardless of key-only suffix presence
ma_dir = os.path.join(ROOT, "Minimal Audio/REFLECT/2 - Melodics/3 - Vocal Oneshots")
for f in os.listdir(ma_dir):
    if f.lower().endswith(".wav"):
        add(os.path.join(ma_dir, f), "Vocal Phrase", "Minimal Audio", False, "vendor_folder_asserted_oneshot")

os.makedirs(OUT, exist_ok=True)
full_dir = os.path.join(OUT, "full_evidence")
os.makedirs(full_dir, exist_ok=True)
subcat_folder = {"Vocal Loop": "Vocal", "Vocal Phrase": "Vocal"}

for m in manifest:
    ext = os.path.splitext(m["source_path"])[1]
    orig_name = os.path.basename(m["source_path"])
    dest_dir = os.path.join(full_dir, subcat_folder[m["expected_subcategory"]])
    os.makedirs(dest_dir, exist_ok=True)
    dest_name = f"{m['sample_id']:04d}__{orig_name}"
    dest = os.path.join(dest_dir, dest_name)
    shutil.copy2(m["source_path"], dest)
    m["full_evidence_relpath"] = os.path.relpath(dest, full_dir)

with open(os.path.join(OUT, "vocal_loop_crossvendor_v1_manifest.json"), "w") as f:
    json.dump(manifest, f, indent=2)

loop_n = sum(1 for m in manifest if m["expected_subcategory"] == "Vocal Loop")
phrase_n = sum(1 for m in manifest if m["expected_subcategory"] == "Vocal Phrase")
vendors = set(m["vendor"] for m in manifest)
print(f"Total: {len(manifest)} (Vocal Loop: {loop_n}, Vocal Phrase: {phrase_n})")
print(f"Vendors: {vendors}")
print(f"Output: {full_dir}")
