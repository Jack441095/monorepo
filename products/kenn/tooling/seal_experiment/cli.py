"""Reproducible local commands for snapshots, dry runs, reviewed trials and sealed scoring."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import urllib.request
from dataclasses import asdict
from pathlib import Path

from .backends import CudaBackend, FixtureBackend, tree_hash
from .experiment import PendingReview, blind_packet, evaluate, grade_packet, run
from .measurements import distribution, known_sum, product_report
from .records import Limits, digest, read, text_hash, validate_dataset, words, write

ROOT = Path(__file__).resolve().parents[2]
MODEL = "qwen3:4b-instruct-2507-q4_K_M"


def snapshot(output: Path, model: str = MODEL) -> dict:
    """Read local model/index identities without loading a model or changing any provider."""
    if model != MODEL:
        raise ValueError("this pilot preserves the owner's Qwen3 4B choice")

    def request(endpoint, body=None):
        req = urllib.request.Request("http://127.0.0.1:11434/api/" + endpoint,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response)

    tag = next(m for m in request("tags")["models"] if m["name"] == model)
    shown = request("show", {"model": model})
    index_root = ROOT / "apps/backend/src/kenn/data/index"
    index_version = (index_root / "CURRENT").read_text().strip()
    index = index_root / "versions" / index_version
    if index.parent != index_root / "versions" or not index.is_dir():
        raise ValueError("CURRENT does not identify a local index version")
    code = {}
    tracked = subprocess.run(["git", "ls-files", "--", "apps/backend/src/kenn", "tooling"],
        cwd=ROOT, check=True, text=True, capture_output=True).stdout.splitlines()
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "--",
                                "apps/backend/src/kenn", "tooling"],
        cwd=ROOT, check=True, text=True, capture_output=True).stdout.splitlines()
    for name in set(tracked + untracked):
        path = ROOT / name
        if path.is_file() and path.suffix == ".py":
            code[name] = text_hash(path.read_text())
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                              text=True, capture_output=True).stdout.strip()
    hardware = {"system": platform.system(), "architecture": platform.machine(),
                "chip": None, "memory_bytes": None}
    if platform.system() == "Darwin":
        hardware["chip"] = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], check=True,
                                          text=True, capture_output=True).stdout.strip()
        hardware["memory_bytes"] = int(subprocess.run(["sysctl", "-n", "hw.memsize"], check=True,
                                                      text=True, capture_output=True).stdout)
    manifest = {"schema": "kenn.seal.baseline.v1", "model_name": model,
        "model_digest": tag["digest"], "model_details": tag["details"],
        "runtime": "ollama-native", "runtime_version": request("version")["version"],
        "source_revision": revision, "source_files": code, "source_sha256": digest(code),
        "index_version": index_version, "index_sha256": tree_hash(index),
        "template_sha256": text_hash(shown.get("template", "")),
        "system_sha256": text_hash(shown.get("system", "")),
        "tokenizer_identity": {"embedded_in_model_digest": tag["digest"],
                               "model_metadata_sha256": digest(shown.get("model_info", {}))},
        "generation": {"temperature": 0.35, "max_tokens": 128, "think": False,
                       "cache_enabled": False},
        "hardware": hardware,
        "hf_checkpoint_sha256": None, "same_checkpoint_attestation": None,
        "experimental_serving_enabled": False, "measured_answers": False,
        "scope": "read-only asset baseline; task messages and retrieval results must be pinned in dataset"}
    write(output, manifest)
    return manifest


def fixture_dataset() -> tuple[dict, dict]:
    """Owned synthetic contracts, never production notes, owner grades or evidence of learning."""
    data = {"schema": "kenn.seal.dataset.v1", "synthetic": True, "sources": {},
            "tasks": [], "ordinary_examples": [], "approvals": {}}

    def approve(value):
        data["approvals"][digest(value)] = {"verdict": "approved", "reviewer": "synthetic-fixture-only",
            "reviewed_at": "fixture", "supported": True, "numbers_units_correct": True,
            "no_contradictions": True, "shared_weights_allowed": True}

    def source(name, split, text):
        row = {"text": text, "sha256": text_hash(text), "family": name, "split": split,
               "license": "owned synthetic test fixture", "privacy": "public", "training_permission": True}
        data["sources"][name] = row
        approve(row)
        return row

    for index in range(2):
        sid = f"train-{index}"
        row = source(sid, "train", f"Synthetic training fact {index}: release is 100 ms.")
        example = {"kind": "qa", "messages": [
            {"role": "user", "content": f"Describe the training-only release fixture {index}?"},
            {"role": "assistant", "content": row["text"]}],
            "support": [{"source_id": sid, "sha256": row["sha256"], "excerpt": row["text"]}]}
        data["ordinary_examples"].append(example)
        approve(example)
    sealed = {"schema": "kenn.seal.sealed.v1", "tasks": []}
    families = ("technical", "numeric_units", "followup", "missing_evidence", "conflicting_sources",
                "hallucinated_devices", "proposal_policy")
    for split in ("reward", "final", "retention"):
        for index, family in enumerate(families):
            sid = f"{split}-{family}"
            row = source(sid, split, f"Independent synthetic {split} reference {family}.")
            question = f"What does {split} reference {family} require in case {index}?"
            task = {"id": sid, "family": sid, "coverage": family, "split": split,
                    "scope": "knowledge_only", "source_ids": [sid], "question": question,
                    "messages": [{"role": "user", "content": question}], "accepted_answers": [row["text"]]}
            approve(task)
            (sealed["tasks"] if split == "final" else data["tasks"]).append(task)
    data["sealed_sha256"] = digest(sealed)
    data["sealed_questions"] = [sorted(words(t["question"])) for t in sealed["tasks"]]
    return data, sealed


def summarize(result: dict, output: Path) -> dict:
    """Keep learning, inference and total compute separate; missing measurements remain null."""
    arms = {}
    for arm, report in result["reports"].items():
        rows = report["rows"]
        seconds = known_sum([r["response"].get("complete_seconds") for r in rows])
        correct = sum(r["correct"] and r["usefulness"] == 2 and r["unsupported_claims"] == 0
                      and r["policy_violation"] is False for r in rows)
        complete_correct = sum(r["reward"] > 0 for r in rows)
        timing = distribution([r["response"].get("complete_seconds") for r in rows])
        visible = distribution([r["response"].get("first_visible_seconds") for r in rows])
        arms[arm] = {"reviewed_correct_useful": correct, "task_count": len(rows),
            "grounded_complete_correct_useful": complete_correct,
            "reward": report["reward"], "needs_owner_review": sum(r["review_status"] == "needs_owner_review" for r in rows),
            "correct_useful_per_inference_second": complete_correct / seconds if seconds else None,
            "complete_p50_seconds": timing["p50"], "complete_p95_seconds": timing["p95"],
            "complete_timing_measured": timing["measured"],
            "first_visible_p50_seconds": visible["p50"], "first_visible_p95_seconds": visible["p95"],
            "prompt_tokens": known_sum([r["response"].get("prompt_tokens") for r in rows]),
            "output_tokens": known_sum([r["response"].get("output_tokens") for r in rows]),
            "provider_calls": sum(r["response"]["provider_calls"] for r in rows),
            "truncated": sum(r["response"]["truncated"] for r in rows),
            "unsupported_claims": sum(r["unsupported_claims"] for r in rows)
                if all(r["unsupported_claims"] is not None for r in rows) else None,
            "abstentions": sum(r["response"]["abstained"] for r in rows),
            "fallbacks": sum(r["response"]["fallback"] for r in rows),
            "condition": sorted({r["response"]["condition"] for r in rows})}
    operations = [read(p) for p in (output / "operations").glob("*.response.json")]
    training = [p for p in operations if p.get("operation_kind") == "train" and "steps" in p]
    inference = [p for p in operations if "provider_calls" in p]
    summary = {"schema": "kenn.seal.summary.v1", "status": result["status"], "arms": arms,
        "learning": {"examples_by_arm": {"B": "reviewed ordinary", "C": "reviewed synthetic, fixed policy",
                                         "D": "reviewed synthetic, learned self-edit policy"},
                     "matched_inner_steps": result["limits"]["values"]["steps"],
                     "matched_token_ceiling": result["limits"]["values"]["training_tokens"],
                     "per_trial_max_tokens": result["limits"]["values"]["steps"] * result["limits"]["values"]["max_length"],
                     "actual_tokens_matched": False,
                     "steps_to_target_quality": None, "data_efficiency_advantage": None},
        "compute": {"gpu_training_seconds": sum(p["gpu_seconds"] for p in training) if training else None,
                    "gpu_generation_wall_seconds": sum(p["complete_seconds"] for p in inference) if inference else None,
                    "self_edit_generation_seconds": sum(p["complete_seconds"] for p in inference
                                                           if p.get("operation_purpose") == "self_edit") if inference else None,
                    "evaluation_generation_seconds": sum(p["complete_seconds"] for p in inference
                                                            if p.get("operation_purpose") == "evaluation") if inference else None,
                    "training_tokens": sum(p["training_tokens"] for p in training) if training else None,
                    "failed_or_timed_out_operations": sum("status" in p for p in operations),
                    "total_pipeline_seconds": result["seconds"], "recorded_operations": len(operations)},
        "proxy_calibration": result["proxy_calibration"], "amortization_usage_count": None,
        "M3_product_measurements": "unmeasured: cold/warm, cache hits, visible timing, pressure, switches, owner correctness",
        "SEAL_value_over_ordinary_finetuning": "unmeasured" if result["status"] == "dry_run" else "requires sealed review and product measurements",
        "promotion": "disabled"}
    write(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    base = sub.add_parser("snapshot")
    base.add_argument("--out", type=Path, required=True)
    demo = sub.add_parser("dry-run")
    demo.add_argument("--out", type=Path, required=True)
    pilot = sub.add_parser("run")
    pilot.add_argument("--data", type=Path, required=True)
    pilot.add_argument("--baseline", type=Path, required=True)
    pilot.add_argument("--base-model", type=Path, required=True)
    pilot.add_argument("--limits", type=Path)
    pilot.add_argument("--approvals", type=Path)
    pilot.add_argument("--labels", type=Path)
    pilot.add_argument("--out", type=Path, required=True)
    pilot.add_argument("--proxy-screen", type=float, default=0.0)
    final = sub.add_parser("final")
    final.add_argument("--data", type=Path, required=True)
    final.add_argument("--sealed", type=Path, required=True)
    final.add_argument("--baseline", type=Path, required=True)
    final.add_argument("--base-model", type=Path, required=True)
    final.add_argument("--out", type=Path, required=True)
    owner = sub.add_parser("grade")
    owner.add_argument("--packet", type=Path, required=True)
    owner.add_argument("--grades", type=Path, required=True)
    owner.add_argument("--out", type=Path, required=True)
    product = sub.add_parser("product-report")
    product.add_argument("--receipts", type=Path, required=True)
    product.add_argument("--data", type=Path, required=True)
    product.add_argument("--sealed", type=Path)
    product.add_argument("--labels", type=Path)
    product.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    # Artifacts may contain reviewed licensed text and weights; put them in KENN's ignored runtime tree
    # or outside the Git checkout rather than making accidental git publication easy.
    out = args.out.resolve()
    if out.is_relative_to(ROOT.parents[1]) and not out.is_relative_to(ROOT / ".runtime"):
        parser.error("output must be outside the Git checkout or under ignored products/kenn/.runtime/")
    if args.command == "snapshot":
        result = snapshot(out)
        print(json.dumps({k: result[k] for k in ("model_name", "model_digest", "index_version", "source_revision")}))
        return 0
    if args.command == "dry-run":
        data, sealed = fixture_dataset()
        write(out / "fixture-data.json", data)
        write(out / "fixture-sealed.json", sealed)
        backend = FixtureBackend({"model_name": MODEL, "measurement_scope": "synthetic only"})
        result = run(data, backend, out, Limits())
        summary = summarize(result, out)
        print(json.dumps({"status": summary["status"], "promotion": summary["promotion"],
                          "summary": str(out / "summary.json")}))
        return 0
    if args.command == "grade":
        result = grade_packet(args.packet, read(args.grades), out)
        print(json.dumps({"scope": result["scope"], "graded_cards": result["graded_cards"],
                          "total_cards": result["total_cards"], "promotion": result["promotion"]}))
        return 0
    if args.command == "product-report":
        result = product_report(read(args.receipts), read(args.data),
            read(args.labels) if args.labels else {}, out, read(args.sealed) if args.sealed else None)
        print(json.dumps({"groups": len(result["groups"]), "promotion": result["promotion"]}))
        return 0
    data = read(args.data)
    if data.get("synthetic"):
        parser.error("synthetic fixture data is forbidden in real training and evaluation")
    manifest = read(args.baseline)
    if manifest.get("model_name") != MODEL or manifest.get("experimental_serving_enabled") is not False:
        parser.error("baseline must preserve Qwen3 4B and disable experimental serving")
    backend = CudaBackend(args.base_model, manifest, out)
    if args.command == "final":
        if (out / "sealed-final.json").exists():
            parser.error("sealed final evaluation is one-shot; use recorded answers for later owner grading")
        recorded = read(out / "run.json")
        sealed = read(args.sealed)
        validate_dataset(data, sealed)
        if digest(data) != recorded["dataset_sha256"] or backend.manifest != recorded["baseline"]:
            parser.error("final evaluation must use the recorded dataset and pinned backend")
        if not sealed["tasks"] or any(t["split"] != "final" for t in sealed["tasks"]):
            parser.error("sealed file must contain final tasks only")
        backend.evaluation_limits = recorded["limits"]["values"]
        backend.remaining_seconds = recorded["limits"]["values"]["run_seconds"]
        # Reserve the one-shot boundary before calling a provider, even if the run later fails.
        write(out / "sealed-final.json", {"status": "started", "tuning_allowed": False})
        reports = {arm: evaluate(backend, cp, sealed["tasks"], {}, out / f"{arm}-sealed.evaluation.json", data["sources"])
                   for arm, cp in recorded["arms"].items()}
        blind_packet(reports, out / "blind-final.json", 0)
        write(out / "sealed-final.json", {"status": "needs_owner_review", "reports": reports,
                                          "promotion": "disabled", "tuning_allowed": False})
        print("Sealed answers recorded; blind owner review and M3 product measurements remain required.")
        return 0
    limits = Limits(**read(args.limits)) if args.limits else Limits()
    backend.evaluation_limits = asdict(limits)
    try:
        result = run(data, backend, out, limits,
            approvals=read(args.approvals) if args.approvals else {},
            labels=read(args.labels) if args.labels else {}, proxy_screen=args.proxy_screen)
    except PendingReview as exc:
        print(str(exc))
        return 2
    summarize(result, out)
    print("Development trials recorded; sealed evaluation remains separate. Serving is unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
