"""Prepare numbered specialist review cards without granting training permission."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .records import Limits, digest, validate_example, words, text_hash, write


ROOT = Path(__file__).resolve().parents[2]

# S2 fixes the row counts; changing them creates a different reviewed experiment.
COVERAGE = {"technical", "numeric_units", "followup", "missing_evidence",
            "conflicting_sources", "hallucinated_devices", "proposal_policy"}
COUNTS = {"train": 8, "reward": 24, "retention": 12, "final": 24}


def prepare(spec: dict) -> tuple[dict, dict, dict]:
    """Return unapproved development data, reserved final tasks and a split receipt.

    Callers group related facts and task templates before writing variants. Alias
    checks catch renamed groups; semantic independence still needs human review.
    """
    if spec.get("schema") != "kenn.seal.specialist_draft.v1":
        raise ValueError("expected kenn.seal.specialist_draft.v1")
    groups = spec["groups"]
    assignments, aliases, templates = {}, {}, {}
    # Freeze ownership first. A renamed chapter or template cannot move its variants
    # across partitions merely because its display name changed.
    for group in groups:
        split = group["split"]
        if split not in COUNTS or group["family"] in assignments:
            raise ValueError("unknown partition or repeated family")
        assignments[group["family"]] = split
        for mapping, key in ((aliases, "related_facts"), (templates, "task_templates")):
            if not group.get(key):
                raise ValueError("each family needs related facts and task templates")
            for alias in group[key]:
                if alias in mapping and mapping[alias] != split:
                    raise ValueError("related fact or task template crosses partitions")
                mapping[alias] = split
    if sum(split == "train" for split in assignments.values()) != 4:
        raise ValueError("specialist packet requires four training contexts")

    data = {"schema": "kenn.seal.dataset.v1", "sources": {}, "tasks": [],
            "ordinary_examples": [], "approvals": {}}
    sealed = {"schema": "kenn.seal.sealed.v1", "tasks": []}
    ids, contents, questions, count = set(), {}, set(), Counter()
    for group in groups:
        split, sid = group["split"], group["id"]
        if sid in data["sources"] or not group["references"]:
            raise ValueError("sources need unique IDs and supporting references")
        if group.get("privacy") != "public":
            # Preparation must not relabel private/session material as public evidence.
            raise ValueError("sources require an explicit public privacy declaration")
        if not group["text"].strip():
            raise ValueError("source context must not be empty")
        sha = text_hash(group["text"])
        if sha in contents and contents[sha] != split:
            raise ValueError("identical source content crosses partitions")
        contents[sha] = split
        source = {"family": group["family"], "split": split, "text": group["text"],
                  "sha256": sha, "privacy": "public", "license": "rights review pending",
                  "training_permission": False, "origin": {
                      "kind": group["origin_kind"], "references": group["references"],
                      "live_version": group["live_version"], "review": "owner review pending",
                      "claimed_license": group.get("license", "unrecorded")}}
        data["sources"][sid] = source
        if split == "train" and len(group["variants"]) != 2:
            raise ValueError("each training context needs two ordinary targets")
        for variant in group["variants"]:
            question = variant["question"]
            if any(not isinstance(value, str) or not value.strip()
                   for value in (question, variant["answer"])):
                raise ValueError("questions and reference answers must be nonempty text")
            history = variant.get("history", [])
            if not isinstance(history, list) or any(
                    not isinstance(message, dict) or set(message) != {"role", "content"}
                    or message["role"] not in {"system", "user", "assistant"}
                    or not isinstance(message["content"], str) or not message["content"].strip()
                    for message in history):
                raise ValueError("history must contain valid role/content messages")
            # Normalized words also catch case/punctuation-only duplicates that a
            # raw prompt hash would miss. They do not prove semantic independence.
            fingerprint = tuple(sorted(words(question)))
            if fingerprint in questions:
                raise ValueError("duplicate question wording")
            questions.add(fingerprint)
            messages = [{"role": "user", "content": question}]
            if split == "train":
                example = {"kind": variant["kind"], "messages": [*history,
                           *messages, {"role": "assistant", "content": variant["answer"]}],
                           "support": [{"source_id": sid, "sha256": sha, "excerpt": group["text"]}]}
                data["ordinary_examples"].append(example)
            else:
                task_id = variant["id"]
                if task_id in ids or variant["coverage"] not in COVERAGE:
                    raise ValueError("duplicate task ID or unknown coverage")
                ids.add(task_id)
                task = {"id": task_id, "family": group["family"], "split": split,
                        "coverage": variant["coverage"], "scope": "knowledge_only",
                        "source_ids": [sid], "question": question,
                        "messages": [{"role": "system", "content":
                            "State uncertainty when evidence is missing. Do not invent devices or claim actions."},
                            *history, *messages],
                        "accepted_answers": [variant["answer"]]}
                (sealed["tasks"] if split == "final" else data["tasks"]).append(task)
            count[split] += 1
    if dict(count) != COUNTS:
        raise ValueError("specialist packet requires 8 ordinary, 24 reward, 12 retention and 24 final rows")
    for tasks in (data["tasks"], sealed["tasks"]):
        split = "final" if tasks is sealed["tasks"] else "reward"
        if not COVERAGE.issubset({t["coverage"] for t in tasks if t["split"] == split}):
            raise ValueError("reward and final partitions need all seven coverage categories")
    data["sealed_sha256"] = digest(sealed)
    data["sealed_questions"] = [sorted(words(t["question"])) for t in sealed["tasks"]]
    seen = set()
    for example in data["ordinary_examples"]:
        validate_example(example, data["sources"], data, seen)
    overlaps = []
    prompts = [(g["split"], v["question"]) for g in groups for v in g["variants"]]
    for index, (split, question) in enumerate(prompts):
        for other_split, other in prompts[index + 1:]:
            left, right = words(question), words(other)
            # Punctuation-only prompts have no lexical evidence to compare; they
            # still remain unapproved and cannot earn semantic independence here.
            similarity = len(left & right) / len(left | right) if left | right else 0.0
            # 0.35 Jaccard similarity is a review flag, not an approval threshold.
            # Store hashes here: final wording belongs only in the reserved packet.
            if split != other_split and similarity >= 0.35:
                overlaps.append({"splits": [split, other_split],
                                 "question_sha256": [text_hash(question), text_hash(other)],
                                 "jaccard": similarity})
    return data, sealed, {"schema": "kenn.seal.preparation.v1", "counts": dict(count),
        "assignments": assignments, "related_facts": aliases, "task_templates": templates,
        "spec_sha256": digest(spec), "dataset_sha256": digest(data), "sealed_sha256": digest(sealed),
        "lexical_overlap_flags": overlaps, "semantic_review": "pending", "training_allowed": False,
        "scope": "unapproved knowledge-only draft; paired KENN retrieval captures remain pending"}


def emit(spec: dict, output: Path) -> dict:
    """Write a new local draft and four-card pages; final wording stays under reserved/."""
    output = output.resolve()
    if output.is_relative_to(ROOT.parents[1]) and not output.is_relative_to(ROOT / ".runtime"):
        # Rights-pending text belongs outside tracked files even for direct callers.
        raise ValueError("output must be outside the Git checkout or under ignored products/kenn/.runtime/")
    if output.exists():
        # A fresh identity preserves the content an owner may already have reviewed.
        raise ValueError("packet directory already exists; prepare a new version")
    data, sealed, receipt = prepare(spec)
    # Claim the directory exclusively so simultaneous preparation cannot overwrite review cards.
    output.mkdir(parents=True, exist_ok=False)
    write(output / "data.draft.json", data)
    write(output / "reserved" / "sealed.draft.json", sealed)
    write(output / "preparation.json", receipt)
    # The input specification contains final prompts/answers as well as development rows.
    write(output / "reserved" / "spec.draft.json", spec)
    for split in COUNTS:
        cards = []
        for sid, source in data["sources"].items():
            if source["split"] != split:
                continue
            references = ", ".join(source["origin"]["references"])
            context = [f"Source: {sid}: {source['family']}",
                       f"Source text SHA-256: `{source['sha256']}`",
                       f"Source record SHA-256: `{digest(source)}`",
                       f"References: {references}",
                       f"Origin: {source['origin']['kind']}; Live version: {source['origin']['live_version']}"]
            cards.append([*context, "", source["text"]])
            targets = ([e for e in data["ordinary_examples"] if e["support"][0]["source_id"] == sid]
                       if split == "train" else
                       [t for t in [*data["tasks"], *sealed["tasks"]] if sid in t["source_ids"]])
            for target in targets:
                question = target["question"] if "question" in target else target["messages"][-2]["content"]
                answer = (target["accepted_answers"][0] if "accepted_answers" in target
                          else target["messages"][-1]["content"])
                history = target["messages"][:-2] if split == "train" else target["messages"][1:-1]
                cards.append([*context, f"Question: {question}", f"History: {history}",
                              f"Reference answer: {answer}",
                              f"Target record SHA-256: `{digest(target)}`"])
        folder = output / ("reserved/review" if split == "final" else "review")
        folder.mkdir(parents=True, exist_ok=True)
        # Four cards per page caps review work even when one source has many variants.
        for start in range(0, len(cards), 4):
            lines = [f"# {split.title()} review packet {start // 4 + 1}", "",
                     "Draft only. Review factual support, wording, units and rights separately.",
                     "No owner grades or shared-weight permission have been recorded.", ""]
            for number, card in enumerate(cards[start:start + 4], start + 1):
                lines += [f"## {number}. Review card", "", *card, ""]
            (folder / f"{split}-{start // 4 + 1:02d}.md").write_text("\n".join(lines), encoding="utf-8")
    for steps in (4, 8, 16):
        # S3 allocates 2048 padded tokens per optimizer step across B/C/D.
        limits = Limits(contexts=4, examples=2, steps=steps, policy_steps=steps,
                        training_tokens=steps * 2048)
        limits.validate()
        manifest = limits.manifest()
        manifest["reasons"]["specialist_overrides"] = (
            f"S3 development budget: {steps} optimizer steps; four contexts, two examples/context; "
            f"{steps * 2048} padded training tokens; policy steps no greater than inner steps.")
        write(output / f"limits-{steps}.json", manifest)
    return receipt
