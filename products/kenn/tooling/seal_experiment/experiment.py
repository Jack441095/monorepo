"""Explicit inner adaptation and outer ReST-EM loops with independent reference tasks."""

from __future__ import annotations

import math
import random
import time
from pathlib import Path

from .records import (Limits, digest, proxy_score, read, reviewed,
                      self_edit, text_hash, validate_dataset, validate_example, write)


class PendingReview(RuntimeError):
    """Generated data is saved for review; no unreviewed target may reach training."""


def normalized(text: str) -> str:
    return " ".join(text.split())


def grade(answer: str, references: list[str], label: dict) -> dict:
    """Accept content-bound human grades or exact reviewed targets; never self-grade prose."""
    exact = normalized(answer) in {normalized(a) for a in references}
    if label:
        if (not label.get("reviewer") or not label.get("reviewed_at")
                or type(label.get("correct")) is not bool
                or type(label.get("usefulness")) is not int or not 0 <= label["usefulness"] <= 2
                or type(label.get("unsupported_claims")) is not int or label["unsupported_claims"] < 0
                or type(label.get("policy_violation")) is not bool):
            raise ValueError("owner grade needs reviewer/date, boolean correctness/policy and integer usefulness/claims")
        return {**label, "review_status": "human"}
    # A nonmatching answer may be correct, but it earns no selection reward before independent review.
    return {"correct": exact, "usefulness": 2 if exact else 0,
            "unsupported_claims": 0 if exact else None, "policy_violation": False if exact else None,
            "review_status": "reviewed_exact" if exact else "needs_owner_review"}


def reward(row: dict) -> float:
    return float(row["correct"] and row["usefulness"] == 2 and row["unsupported_claims"] == 0
                 and row["policy_violation"] is False and row["response"]["truncated"] is False
                 and (row["gate"] is None or row["gate"]["accepted"]))


def evaluate(backend, checkpoint: str, tasks: list[dict], labels: dict, output: Path,
             sources: dict | None = None) -> dict:
    """Score exact reviewed answers or independent human labels; unknown prose earns zero."""
    rows = []
    for task in tasks:
        response = backend.answer(checkpoint, task)
        answer = response["text"]
        key = digest({"task": digest(task), "answer_sha256": text_hash(answer)})
        judged = grade(answer, task["accepted_answers"], labels.get(key, {}))
        gate = None
        if task["scope"] == "frozen_retrieval":
            # Replay the existing checker unchanged. Its acceptance is recorded beside correctness,
            # never used to declare a fluent but incorrect answer successful.
            from kenn.core.chat_grounding import generated_answer_validation
            gate = generated_answer_validation(task["question"],
                [(r["score"], r["chunk"]) for r in task["results"]], answer,
                route=task["route"], confidence=task["confidence"], answer_mode=task["answer_mode"],
                timeline_context=task.get("timeline_context"),
                additional_evidence_text=task.get("additional_evidence_text"), question=task["question"])
        row = {"task_id": task["id"], "family": task["family"], "split": task["split"],
                     "scope": task["scope"], "task_sha256": digest(task), "label_key": key, "response": response,
                     **judged, "gate": gate, "question": task["question"], "reference": task["accepted_answers"],
                     "evidence": task.get("results") or [
                         {"source_id": sid, "sha256": sources[sid]["sha256"], "excerpt": sources[sid]["text"]}
                         for sid in task["source_ids"] if sources is not None], "source_ids": task["source_ids"]}
        row["reward"] = reward(row)
        rows.append(row)
    report = {"schema": "kenn.seal.evaluation.v1", "checkpoint": backend.identity(checkpoint),
              "reward": sum(r["reward"] for r in rows) / len(rows), "rows": rows}
    write(output, report)
    return report


def rescore(report: dict, labels: dict) -> dict:
    """Apply owner labels to saved answers while preserving earlier signed grades."""
    rows = []
    for original in report["rows"]:
        row = dict(original)
        if row["label_key"] in labels:
            row.update(grade(row["response"]["text"], row["reference"], labels[row["label_key"]]))
            row["reward"] = reward(row)
        rows.append(row)
    return {**report, "rows": rows, "reward": sum(r["reward"] for r in rows) / len(rows)}


def correlation(pairs: list[dict]) -> dict:
    """Report proxy/reward Pearson association only when both measured quantities vary."""
    if len(pairs) < 3:
        # Two points always fit a line; the pilot must not present that as useful calibration.
        return {"n": len(pairs), "pearson": None, "reason": "need at least three measured trials"}
    x, y = [p["proxy"] for p in pairs], [p["gain"] for p in pairs]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sx, sy = sum((v - mx) ** 2 for v in x), sum((v - my) ** 2 for v in y)
    if not sx or not sy:
        # Constant quality scores cannot predict differences in learning.
        return {"n": len(pairs), "pearson": None, "reason": "constant proxy or reward"}
    return {"n": len(pairs), "pearson": sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sx * sy),
            "reason": "descriptive pilot association, not proof of a cheaper reward"}


def run(data: dict, backend, output: Path, limits: Limits, *, approvals: dict | None = None,
        labels: dict | None = None, proxy_screen: float = 0.0, seed: int = 0) -> dict:
    """Save reviewable trials; resume only with the same dataset, backend and budgets."""
    limits.validate()
    validate_dataset(data)
    if not 0 <= proxy_screen <= 1:
        raise ValueError("proxy screen must be in 0..1")
    approvals, labels = approvals or {}, labels or {}
    output.mkdir(parents=True, exist_ok=True)
    identity = {"schema": "kenn.seal.run.v1", "dataset_sha256": digest(data),
                "baseline": backend.manifest, "limits": limits.manifest(), "seed": seed,
                "proxy_screen": proxy_screen, "experimental_serving_enabled": False}
    identity_path = output / "identity.json"
    if identity_path.exists() and read(identity_path) != identity:
        raise ValueError("resume would mix changed data, runtime, model, code or budgets")
    write(identity_path, identity)
    started = time.monotonic()
    # Review pauses do not consume GPU time, but completed/failed operations from previous attempts do.
    prior_seconds = sum(read(p).get("operation_wall_seconds", 0)
                        for p in (output / "operations").glob("*.response.json"))
    reward_tasks = [t for t in data["tasks"] if t["split"] == "reward"]
    retention_tasks = [t for t in data["tasks"] if t["split"] == "retention"]
    contexts = sorted((k, v) for k, v in data["sources"].items() if v["split"] == "train")[:limits.contexts]
    if not contexts or not data["ordinary_examples"]:
        raise ValueError("training contexts and ordinary reviewed examples are required")
    events, pairs, retained = [], [], []
    progress = {}

    def budget():
        remaining = limits.run_seconds - prior_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("pilot exhausted its wall-clock budget")
        backend.remaining_seconds = remaining

    def score(checkpoint, name, tasks=reward_tasks):
        budget()
        path = output / f"{name}.evaluation.json"
        saved = read(path) if path.exists() else None
        if (saved and saved["checkpoint"] == backend.identity(checkpoint)
                and [r["task_sha256"] for r in saved["rows"]] == [digest(t) for t in tasks]):
            # Content-bound grades survive review pauses without paying for stochastic new answers.
            result = rescore(saved, labels)
            write(path, result)
        else:
            result = evaluate(backend, checkpoint, tasks, labels, path, data["sources"])
        progress[name] = result
        if not backend.is_fixture and any(r["review_status"] == "needs_owner_review" for r in result["rows"]):
            write(output / "progress.json", {"reports": progress})
            blind_packet(progress, output / "blind-progress.json", seed)
            write(output / "status.json", {"status": "pending_reward_review", "packet": "blind-progress.json"})
            raise PendingReview("Independent reward/retention grades required: blind-progress.json")
        budget()
        return result

    def train(checkpoint, messages, name, policy=False):
        budget()
        trial = output / name
        result = backend.train(checkpoint, messages, trial, limits, policy=policy)
        events.append({"kind": "policy" if policy else "adaptation", "name": name,
                       "start_checkpoint": backend.identity(checkpoint), "result": result})
        write(output / "events.json", events)
        budget()
        return result["checkpoint"]

    def training_messages(edits):
        messages, seen = [], set()
        for edit, _ in edits:
            for example in edit["payload"]["examples"]:
                validate_example(example, data["sources"], data, seen)
                messages.append(example["messages"])
        return messages

    def generate(checkpoint, name, candidate_seed):
        edits = []
        for index, (source_id, source) in enumerate(contexts):
            budget()
            path = output / f"{name}.context-{index}.edit.json"
            if path.exists():
                edit = read(path)
                # Resume a pending human review without regenerating the text they just reviewed.
                expected = self_edit(edit["payload"], source_id=source_id, source=source,
                    policy=backend.identity(checkpoint), seed=candidate_seed + index, data=data,
                    limits=limits, generator=backend.manifest["generator"])
                if edit != expected:
                    raise ValueError("stale candidate or changed policy checkpoint")
            else:
                payload = backend.propose(checkpoint, source_id, source, candidate_seed + index, limits)
                edit = self_edit(payload, source_id=source_id, source=source,
                    policy=backend.identity(checkpoint), seed=candidate_seed + index, data=data,
                    limits=limits, generator=backend.manifest["generator"])
                write(path, edit)
            review_map = {**approvals, **backend.fixture_approvals(edit)}
            proxy = proxy_score(edit, review_map)
            write(path.with_suffix(".screen.json"), proxy)
            if not reviewed(edit, review_map):
                write(output / "status.json", {"status": "pending_review", "edit": path.name,
                                              "approval_key": digest(edit), "training_started_for_edit": False})
                raise PendingReview(f"Review {path.name}; approval key {digest(edit)}")
            edits.append((edit, proxy))
        return edits

    base = backend.base_checkpoint
    arms = {"A": base}
    reports = {"A": score(base, "A-base")}
    base_retention = score(base, "A-retention", retention_tasks)
    ordinary = [e["messages"] for e in data["ordinary_examples"]]
    if len(ordinary) > limits.contexts * limits.examples:
        raise ValueError("ordinary examples exceed the same example ceiling as synthetic arms")
    arms["B"] = train(base, ordinary, "B-ordinary")
    reports["B"] = score(arms["B"], "B-ordinary")
    c_edits = generate(base, "C-fixed-policy", seed)
    c_messages = training_messages(c_edits)
    arms["C"] = train(base, c_messages, "C-synthetic")
    reports["C"] = score(arms["C"], "C-synthetic")

    policy = base
    for iteration in range(limits.iterations):
        # Recompute the reference baseline after every outer update. Comparing θ′ to the
        # original model would credit policy drift as if it were useful adaptation.
        prefix = f"D-iteration-{iteration}"
        policy_reward = score(policy, f"{prefix}-policy")["reward"]
        selected = []
        candidates = []
        for candidate in range(limits.candidates):
            name = f"{prefix}-candidate-{candidate}"
            edits = generate(policy, name, seed + 1000 * (iteration + 1) + 100 * candidate)
            proxy = sum(p["score"] for _, p in edits) / len(edits)
            if proxy < proxy_screen:
                events.append({"kind": "proxy_screen", "name": name, "proxy": proxy,
                               "reward": None, "reason": "screened; learning improvement unmeasured"})
                continue
            messages = training_messages(edits)
            # Every candidate starts from this iteration's immutable policy, never a previous trial.
            checkpoint = train(policy, messages, name)
            gain = score(checkpoint, name)["reward"] - policy_reward
            retention = score(checkpoint, f"{name}-retention", retention_tasks)
            pairs.append({"iteration": iteration, "candidate": candidate, "proxy": proxy, "gain": gain})
            candidates.append({"name": name, "gain": gain, "proxy": proxy,
                               "retention": retention["reward"]})
            if gain >= limits.min_reward_gain and retention["reward"] >= base_retention["reward"]:
                for edit, _ in edits:
                    # Outer SFT targets the selected context→self-edit generation, not inner QA answers.
                    selected.append(edit["prompt"] + [{"role": "assistant", "content":
                                    backend.serialize(edit["payload"])}])
        if selected:
            checkpoint_before_update = policy
            policy = train(policy, selected, f"{prefix}-policy-update", policy=True)
            updated = score(policy, f"{prefix}-updated-retention", retention_tasks)
            if updated["reward"] < base_retention["reward"]:
                # A disposable update can be rejected without discarding its forgetting evidence.
                policy = checkpoint_before_update
                events.append({"kind": "policy_retention_rollback", "iteration": iteration,
                               "rejected_retention": updated})
        else:
            # No improvement is a valid result; do not teach the policy its own failed edits.
            events.append({"kind": "no_policy_update", "iteration": iteration})
        retained.append({"iteration": iteration, "candidates": candidates,
                         "policy": score(policy, f"{prefix}-retention", retention_tasks)})
        write(output / "events.json", events)

    final_edits = generate(policy, "D-learned-policy-resample", seed + 100000)
    final_messages = training_messages(final_edits)
    arms["D"] = train(policy, final_messages, "D-final-adaptation")
    reports["D"] = score(arms["D"], "D-final-adaptation")
    # Final evaluation is a separate command. Policy selection never opens its prompts or labels.
    result = {**identity, "status": "dry_run" if backend.is_fixture else "development_complete",
              "arms": arms, "reports": reports, "events": events, "retention": retained,
              "proxy_pairs": pairs, "proxy_calibration": correlation(pairs),
              "arm_retention": {arm: score(cp, f"{arm}-end-retention", retention_tasks) for arm, cp in arms.items()},
              "seconds": prior_seconds + time.monotonic() - started,
              "recommendation": "no promotion: sealed owner review and M3 product measurements remain required"}
    write(output / "run.json", result)
    write(output / "status.json", {"status": result["status"]})
    blind_packet(reports, output / "blind-development.json", seed)
    return result


def blind_packet(reports: dict, output: Path, seed: int) -> None:
    cards, key = [], {}
    for arm, report in reports.items():
        for row in report["rows"]:
            card_id = digest({"arm": arm, "label": row["label_key"]})[:16]
            cards.append({"id": card_id, "question": row["question"],
                          "answer": row["response"]["text"], "reference": row["reference"],
                          "source_ids": row["source_ids"], "evidence": row["evidence"],
                          "grade": None})
            key[card_id] = {"arm": arm, "label_key": row["label_key"]}
    random.Random(seed).shuffle(cards)
    write(output, {"schema": "kenn.seal.blind_review.v1", "cards": cards})
    # Keep the answer key separate so the owner can grade without seeing model identities.
    write(output.with_name(output.stem + ".key.json"), key)


def grade_packet(packet_path: Path, grades: dict, output: Path) -> dict:
    """Bind blind card grades to saved answers, then rescore without invoking a provider."""
    packet = read(packet_path)
    key = read(packet_path.with_name(packet_path.stem + ".key.json"))
    cards = {c["id"]: c for c in packet["cards"]}
    if set(grades) - set(cards):
        raise ValueError("unknown blind card id")
    final = packet_path.stem == "blind-final"
    source_name = {"blind-final": "sealed-final.json", "blind-progress": "progress.json",
                   "blind-product": "product-review.json", "blind-development": "run.json"}.get(packet_path.stem)
    if source_name is None:
        raise ValueError("unknown review packet name")
    source = read(packet_path.parent / source_name)
    for arm, report in source["reports"].items():
        for row in report["rows"]:
            card_id = digest({"arm": arm, "label": row["label_key"]})[:16]
            card = cards[card_id]
            if (card["answer"] != row["response"]["text"] or card["question"] != row["question"]
                    or card["reference"] != row["reference"] or card["evidence"] != row["evidence"]
                    or key[card_id] != {"arm": arm, "label_key": row["label_key"]}):
                raise ValueError("blind packet changed since answers were recorded")
    labels = {}
    for card_id, label in grades.items():
        card = cards[card_id]
        grade(card["answer"], card["reference"], label)
        label_key = key[card_id]["label_key"]
        if label_key in labels and labels[label_key] != label:
            raise ValueError("identical task/answer received conflicting blind grades")
        labels[label_key] = label
    reports = {}
    for arm, report in source["reports"].items():
        reports[arm] = rescore(report, labels)
    label_path = output / "owner-labels.json"
    write(label_path, {**(read(label_path) if label_path.exists() else {}), **labels})
    scope = "sealed" if final else "product" if packet_path.stem == "blind-product" else "development"
    result = {"schema": "kenn.seal.owner_review.v1", "scope": scope,
              "packet_sha256": digest(packet), "graded_cards": len(grades), "total_cards": len(cards),
              "reports": reports, "promotion": "disabled"}
    write(output / "owner-reviewed.json", result)
    return result
