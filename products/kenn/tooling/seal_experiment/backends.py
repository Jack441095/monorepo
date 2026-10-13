"""Synthetic dry runs and process-isolated CUDA operations; neither changes serving."""

from __future__ import annotations

import importlib.metadata
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .records import digest, read, text_hash, write


def tree_hash(path: Path) -> str:
    """Hash artifacts by relative name and bytes without putting their contents in a manifest."""
    import hashlib
    result = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        result.update(item.relative_to(path).as_posix().encode() + b"\0")
        with item.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                result.update(chunk)
    return result.hexdigest()


class FixtureBackend:
    """Exercise selection, policy updates and retention; synthetic scores are not model results."""

    is_fixture = True
    base_checkpoint = "fixture-base"
    remaining_seconds = 3600

    def __init__(self, manifest: dict):
        self.manifest = {**manifest, "generator": {"name": "synthetic-fixture", "revision": "v1"}}
        self.states = {self.base_checkpoint: {"adapted": False, "policy_round": 0}}
        self.calls = []

    @staticmethod
    def identity(checkpoint):
        return checkpoint

    @staticmethod
    def serialize(payload):
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    def fixture_approvals(self, edit):
        return {digest(edit): {"verdict": "approved", "reviewer": "synthetic-fixture-only",
                "reviewed_at": "fixture", "supported": True, "numbers_units_correct": True,
                "no_contradictions": True, "shared_weights_allowed": True}}

    def propose(self, checkpoint, source_id, source, seed, limits):
        state = self.states[checkpoint]
        self.calls.append(("propose", checkpoint, seed))
        return {"examples": [{"kind": "qa", "messages": [
            {"role": "user", "content": f"Explain the training fixture {source_id}, variant {seed}, round {state['policy_round']}?"},
            {"role": "assistant", "content": source["text"]}],
            "support": [{"source_id": source_id, "sha256": source["sha256"], "excerpt": source["text"]}]}]}

    def train(self, checkpoint, messages, output, limits, *, policy=False):
        self.calls.append(("train", checkpoint, output.name, policy))
        state = self.states[checkpoint]
        cp = "fixture-" + digest({"start": checkpoint, "messages": messages, "policy": policy})[:24]
        self.states[cp] = {"adapted": False if policy else True,
                           "policy_round": state["policy_round"] + int(policy)}
        result = {"checkpoint": cp, "steps": limits.policy_steps if policy else limits.steps,
                  "seconds": None, "gpu_seconds": None, "peak_gpu_memory_gb": None,
                  "training_tokens": None, "padded_token_budget": limits.training_tokens,
                  "synthetic": True, "start_checkpoint": checkpoint}
        write(output / "training.json", result)
        return result

    def answer(self, checkpoint, task):
        learned = self.states[checkpoint]["adapted"] or task["split"] == "retention"
        return {"text": task["accepted_answers"][0] if learned else "Unlearned synthetic fixture.",
                "truncated": False, "abstained": False, "fallback": False,
                "prompt_tokens": None, "output_tokens": None, "provider_calls": 0,
                "first_visible_seconds": None, "complete_seconds": None,
                "load_seconds": None, "prefill_seconds": None, "decode_seconds": None,
                "peak_memory_gb": None, "memory_pressure": None, "model_switches": 0,
                "condition": "synthetic", "cache_hit": False}


class CudaBackend:
    """Use existing optional training libraries in fresh, time-bounded GPU 1 processes."""

    is_fixture = False
    base_checkpoint = "base"
    remaining_seconds = 3600
    serialize = staticmethod(FixtureBackend.serialize)

    def __init__(self, base_model: Path, manifest: dict, work: Path):
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "1":
            raise ValueError("real trials require CUDA_VISIBLE_DEVICES=1 (physical GPU 1)")
        root = Path(__file__).resolve().parents[2]
        files = manifest.get("source_files", {})
        if not files or digest(files) != manifest.get("source_sha256"):
            raise ValueError("baseline lacks an intact source manifest")
        for name, sha in files.items():
            path = (root / name).resolve()
            if not path.is_relative_to(root) or not path.is_file() or text_hash(path.read_text()) != sha:
                raise ValueError(f"code differs from the pinned baseline: {name}")
        self.base_model = base_model.resolve()
        self.work = work
        if not self.base_model.is_dir():
            raise ValueError("base model must be an existing local HF directory")
        base_sha = tree_hash(self.base_model)
        if base_sha != manifest.get("hf_checkpoint_sha256"):
            raise ValueError("local HF checkpoint does not match the pinned manifest")
        attestation = manifest.get("same_checkpoint_attestation") or {}
        if not (attestation.get("reviewer") and attestation.get("reviewed_at")
                and attestation.get("hf_checkpoint_sha256") == base_sha
                and attestation.get("served_model_digest") == manifest.get("model_digest")):
            raise ValueError("reviewed HF→served GGUF checkpoint equivalence is required")
        config = read(self.base_model / "config.json")
        if config.get("model_type") != "qwen3" or config.get("hidden_size") != 2560:
            raise ValueError("pilot preserves Qwen3 4B; supplied checkpoint is a different model")
        packages = {name: importlib.metadata.version(name) for name in ("torch", "transformers", "peft", "safetensors")}
        self.manifest = {**manifest, "packages": packages,
                         "generator": {"name": "Qwen3-4B-Instruct-2507", "checkpoint_sha256": base_sha,
                                       "runtime": "transformers-cuda-offline", "packages": packages}}

    def identity(self, checkpoint):
        return self.manifest["hf_checkpoint_sha256"] if checkpoint == "base" else tree_hash(Path(checkpoint))

    @staticmethod
    def fixture_approvals(edit):
        # Human review remains mandatory; production data can never inherit fixture attestations.
        return {}

    def _operation(self, kind, checkpoint, limits=None, **kwargs):
        start_sha = self.identity(checkpoint)
        request = {"kind": kind, "base_model": str(self.base_model),
                   "adapter": None if checkpoint == "base" else checkpoint,
                   "limits": limits, **kwargs}
        key = digest({"request": request, "checkpoint_sha256": start_sha})
        # Preserve each execution receipt, including repeated attempts after human review.
        path = self.work / "operations" / f"{key[:16]}-{uuid.uuid4().hex}.request.json"
        response_path = path.with_suffix(".response.json")
        request["response_path"] = str(response_path.resolve())
        write(path, request)
        env = {**os.environ, "CUDA_VISIBLE_DEVICES": "1", "HF_HUB_OFFLINE": "1",
               "TRANSFORMERS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false", "KENN_LIVE_BACKEND": "fake"}
        # sys.path edits in the CLI do not reach a child interpreter. Pin our local modules explicitly.
        root = Path(__file__).resolve().parents[2]
        env["PYTHONPATH"] = os.pathsep.join([str(root / "tooling"), str(root / "apps/backend/src"),
                                          env.get("PYTHONPATH", "")])
        log = path.with_suffix(".log")
        timeout = min(self.remaining_seconds, (limits or {}).get("operation_seconds", 300))
        if timeout <= 0:
            raise TimeoutError("pilot exhausted its wall-clock budget before starting a worker")
        operation_started = time.monotonic()

        def receipt(value):
            value.update(operation_kind=kind, operation_wall_seconds=time.monotonic() - operation_started,
                         operation_purpose=kwargs.get("purpose"), start_checkpoint_sha256=start_sha)
            write(response_path, value)
            return value
        # The command is fixed by trusted tooling. Generated self-edits never supply executable text.
        with log.open("w") as stream:
            process = subprocess.Popen([sys.executable, "-m", "seal_experiment.cuda_worker", str(path.resolve())],
                env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Terminate the process group, including workers, so a timed-out trial cannot keep training.
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                receipt({"status": "timeout", "gpu_seconds": None})
                raise TimeoutError(f"{kind} exceeded {timeout:g} s; process group stopped") from None
        if code:
            receipt({"status": "failed", "exit_code": code})
            raise RuntimeError(f"{kind} worker failed; inspect {log.name}")
        if self.identity(checkpoint) != start_sha:
            receipt({"status": "checkpoint_mutation"})
            raise RuntimeError("trial mutated its starting checkpoint")
        result = receipt(read(response_path))
        self.remaining_seconds -= time.monotonic() - operation_started
        if self.remaining_seconds <= 0:
            raise TimeoutError("pilot exhausted its wall-clock budget")
        return result

    def propose(self, checkpoint, source_id, source, seed, limits):
        from dataclasses import asdict
        from .records import generation_prompt
        response = self._operation("generate", checkpoint, asdict(limits),
            messages=generation_prompt(source_id, source, limits.examples), seed=seed,
            max_tokens=limits.generated_tokens, temperature=0.7, purpose="self_edit")
        if response["truncated"]:
            raise ValueError("truncated self-edit cannot become a training target")
        # Invalid JSON is rejected; repairing it with another model would hide extra generator cost.
        return json.loads(response["text"])

    def train(self, checkpoint, messages, output, limits, *, policy=False):
        from dataclasses import asdict
        config = asdict(limits)
        request_sha = digest({"start": self.identity(checkpoint), "messages": messages,
                              "limits": config, "policy": policy, "backend": self.manifest})
        saved = output / "training.json"
        if saved.exists():
            result = read(saved)
            if (result.get("request_sha256") != request_sha
                    or not Path(result["checkpoint"]).is_dir()
                    or self.identity(result["checkpoint"]) != result.get("checkpoint_sha256")):
                raise ValueError("saved training artifact changed; use a new run directory")
            # Review resumes reuse an immutable completed trial rather than silently retraining it.
            return {**result, "reused_training_artifact": True}
        if (output / "adapter").exists():
            raise ValueError("incomplete adapter has no training receipt; use a new run directory")
        result = self._operation("train", checkpoint, config, messages=messages,
                                 output=str(output.resolve()), policy=policy,
                                 purpose="policy" if policy else "adaptation", seed=0)
        result["checkpoint"] = str(output.resolve() / "adapter")
        result.update(request_sha256=request_sha, checkpoint_sha256=self.identity(result["checkpoint"]))
        write(output / "training.json", result)
        return result

    def answer(self, checkpoint, task):
        limits = self.evaluation_limits
        response = self._operation("generate", checkpoint, limits,
            messages=task["messages"], seed=task.get("seed", 0),
            max_tokens=self.manifest["generation"]["max_tokens"],
            temperature=self.manifest["generation"]["temperature"], purpose="evaluation")
        return response
