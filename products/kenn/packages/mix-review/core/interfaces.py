"""Small product-owned interfaces for local Mix Review execution.

The boundary accepts the analyzer and validator as callables. That keeps the
current Audio_Too bridge usable while making the product contract independent
of its database, upload, agent, and integration modules.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Callable, Mapping


AudioValidator = Callable[[bytes, str], Mapping[str, Any]]
AudioAnalyzer = Callable[..., Mapping[str, Any]]


def _outside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return True
    return False


@dataclass(frozen=True)
class MixReviewBoundary:
    """Dependency-injected local execution boundary.

    Audio bytes are read only for the analyzer call. This class does not write
    audio, reports, databases, uploads, or runtime state. ``runtime_root`` is
    metadata for the caller and must be outside the product checkout.
    """

    product_root: Path
    runtime_root: Path
    max_upload_bytes: int
    decodable_suffixes: frozenset[str]

    def __post_init__(self) -> None:
        product = self.product_root.expanduser().resolve()
        runtime = self.runtime_root.expanduser().resolve()
        if not _outside(runtime, product):
            raise ValueError("Mix Review runtime state must be outside the product checkout")
        object.__setattr__(self, "product_root", product)
        object.__setattr__(self, "runtime_root", runtime)

    def analyze_path(
        self,
        path: Path,
        *,
        validate: AudioValidator,
        analyze: AudioAnalyzer,
        **options: Any,
    ) -> dict[str, Any]:
        resolved = path.expanduser().resolve()
        receipt: dict[str, Any] = {
            "schema": "kenn.mix_review.local_receipt.v2",
            "status": "rejected",
            "source": {"filename": resolved.name, "sha256": ""},
            "audio_uploaded": False,
            "external_network": False,
            "storage": "memory_only",
            "runtime_dir": str(self.runtime_root),
        }
        if not resolved.is_file():
            receipt["error"] = "Local audio path is not a file."
            return receipt
        if resolved.suffix.lower() not in self.decodable_suffixes:
            receipt["error"] = "File extension is not a supported audio format."
            return receipt
        if resolved.stat().st_size > self.max_upload_bytes:
            receipt["error"] = "Local audio file exceeds the Mix Review size limit."
            return receipt

        payload = resolved.read_bytes()
        receipt["source"]["sha256"] = hashlib.sha256(payload).hexdigest()
        validation = dict(validate(payload, resolved.name))
        if not validation.get("ok"):
            receipt["error"] = str(validation.get("error") or "Audio validation failed.")
            return receipt
        try:
            report = dict(analyze(payload, filename=resolved.name, **options))
        except Exception as exc:  # never turn an analyzer exception into success
            receipt["status"] = "failed"
            receipt["error"] = f"{type(exc).__name__}: {exc}"
            return receipt
        receipt["status"] = "completed" if report.get("ok", True) else "failed"
        receipt["analysis"] = report
        if receipt["status"] != "completed":
            receipt["error"] = str(report.get("error") or "Mix Review analysis failed.")
        return receipt
