"""Stage 11.2 — mix session documentation.

Generates a Markdown (and, best-effort, PDF) mix session document from a
real rendered mix: what AutoMix decided, the final measured metrics, and
KENN's cited rationale for the notable parameter choices -- the kind of
notes an engineer could actually hand a client or keep in a session
archive.

This module does not invent any explanation text of its own. Parameter
rationale is generated exclusively by re-using
``audio_analysis.integration.kenn_handoff.annotate_mix_plan_with_kenn``
(Stage 9's KENN handoff, already grounded/cited against
``studio/kenn/kenn/Training_Data_Notes/`` via KENN's real retrieval
pipeline) -- this module only formats that output into Markdown/PDF, it
never asks an LLM to write prose from scratch.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ..integration.kenn_handoff import annotate_mix_plan_with_kenn
from ..mixdown.mix_validator import verify_render_output


def _plan_of(render_result: dict) -> Any:
    plan = render_result.get("mix_plan")
    if plan is None:
        raise ValueError("render_result has no 'mix_plan' -- cannot document a mix with no decisions.")
    return plan


def _compute_final_metrics(render_result: dict) -> dict:
    """Re-derive the same validation metrics used to gate delivery (Stage 7.5).

    Reuses ``mix_validator.verify_render_output`` -- the exact function
    ``mix_delivery._atomic_write_verified_wav`` already runs before a
    mixdown is allowed to ship -- so the numbers in the session doc are
    identical to the numbers that gated the actual release, not a second,
    possibly-divergent measurement path.
    """
    left = render_result.get("left")
    right = render_result.get("right")
    wav_bytes = render_result.get("mixdown_wav_bytes")
    sample_rate = int(render_result.get("sample_rate", 44100))
    if left is None or right is None or wav_bytes is None:
        return {"ok": False, "reasons": ["render_result missing left/right/mixdown_wav_bytes"], "metrics": {}}

    plan = render_result.get("mix_plan")
    target_lufs = getattr(plan, "target_lufs", None)
    bus = getattr(plan, "bus", None)
    ceiling_db = getattr(bus, "limiter_ceiling_db", -1.0) if bus is not None else -1.0

    return verify_render_output(
        np.asarray(left, dtype=np.float64),
        np.asarray(right, dtype=np.float64),
        sample_rate,
        wav_bytes,
        target_lufs=target_lufs,
        measured_lufs=render_result.get("measured_lufs"),
        ceiling_db=ceiling_db,
    )


def _fmt(value: Any, spec: str = ".2f", suffix: str = "") -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):{spec}}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def _stem_rows(plan: Any) -> list[dict]:
    rows = []
    for stem in getattr(plan, "stems", []) or []:
        comp = getattr(stem, "compressor", None) or {}
        rows.append({
            "stem_name": getattr(stem, "stem_name", ""),
            "instrument": getattr(stem, "instrument", ""),
            "gain_db": getattr(stem, "gain_db", 0.0),
            "pan": getattr(stem, "pan", 0.0),
            "compressor_ratio": comp.get("ratio"),
            "reverb_send": getattr(stem, "reverb_send", 0.0),
            "stereo_width": getattr(stem, "stereo_width", 1.0),
        })
    return rows


def build_session_document_data(
    render_result: dict,
    *,
    delivery_status: dict | None = None,
    project_id: str = "",
    client_name: str = "",
    mix_review_report: dict | None = None,
    kenn_explanations: list[dict] | None = None,
    session_id: str = "",
    allow_llm: bool = False,
    max_kenn_items: int = 6,
) -> dict:
    """Gather every real, already-computed value the document needs.

    Kept separate from the Markdown formatter below so tests (and any
    other caller, e.g. a mastering-handoff bundle) can assert on the
    structured data without re-parsing rendered Markdown.
    """
    plan = _plan_of(render_result)
    final_validation = _compute_final_metrics(render_result)

    if kenn_explanations is None:
        # Stage 9 reuse -- the only source of rationale text in this module.
        kenn_explanations = annotate_mix_plan_with_kenn(
            plan, max_items=max_kenn_items, session_id=session_id, allow_llm=allow_llm
        )

    return {
        "project_id": project_id,
        "client_name": client_name,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "genre": getattr(plan, "genre", ""),
        "mix_goal": getattr(plan, "mix_goal", ""),
        "target_lufs": getattr(plan, "target_lufs", None),
        "measured_lufs": render_result.get("measured_lufs"),
        "sample_rate": render_result.get("sample_rate"),
        "final_validation": final_validation,
        "decisions_log": list(getattr(plan, "decisions_log", []) or []),
        "stems": _stem_rows(plan),
        "bus": {
            "limiter_ceiling_db": getattr(plan.bus, "limiter_ceiling_db", None),
            "limiter_threshold_db": getattr(plan.bus, "limiter_threshold_db", None),
            "bus_compressor": getattr(plan.bus, "bus_compressor", None),
            "saturation_drive_db": getattr(plan.bus, "saturation_drive_db", None),
        },
        "mix_review_flags": (mix_review_report or {}).get("flags", []),
        "kenn_explanations": kenn_explanations,
        "refinement": render_result.get("refinement"),
        "delivery_status": delivery_status,
    }


def render_session_markdown(data: dict) -> str:
    """Format the structured data from :func:`build_session_document_data` as Markdown."""
    lines: list[str] = []
    title = f"Mix Session Notes — {data['project_id']}" if data["project_id"] else "Mix Session Notes"
    lines.append(f"# {title}")
    lines.append("")
    if data.get("client_name"):
        lines.append(f"**Client:** {data['client_name']}  ")
    lines.append(f"**Generated:** {data['generated_at_utc']}  ")
    lines.append(f"**Genre:** {data['genre']}  ")
    lines.append(f"**Mix Goal:** {data['mix_goal']}  ")
    lines.append("")

    lines.append("## Final Metrics")
    lines.append("")
    val = data["final_validation"]
    metrics = val.get("metrics", {})
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Target Loudness | {_fmt(data['target_lufs'], suffix=' LUFS')} |")
    lines.append(f"| Measured Integrated Loudness | {_fmt(data['measured_lufs'], suffix=' LUFS')} |")
    lines.append(f"| Loudness Deviation from Target | {_fmt(metrics.get('lufs_diff'), '+.2f', suffix=' LU')} |")
    lines.append(f"| True Peak | {_fmt(metrics.get('true_peak_dbtp'), suffix=' dBTP')} |")
    lines.append(f"| Sample Peak | {_fmt(metrics.get('peak_dbfs'), suffix=' dBFS')} |")
    lines.append(f"| Crest Factor (Dynamic Range) | {_fmt(metrics.get('crest_factor_db'), suffix=' dB')} |")
    lines.append(f"| Phase Correlation | {_fmt(metrics.get('phase_correlation'), '.2f')} |")
    lines.append(f"| Pre-Release Validation | {'PASSED' if val.get('ok') else 'FAILED'} |")
    lines.append("")
    if val.get("reasons"):
        lines.append("**Validation notes:**")
        for reason in val["reasons"]:
            lines.append(f"- {reason}")
        lines.append("")

    if data.get("mix_review_flags"):
        lines.append("### Mix Review Flags")
        lines.append("")
        for flag in data["mix_review_flags"]:
            label = flag.get("id") or flag.get("label") or str(flag)
            lines.append(f"- {label}")
        lines.append("")

    if data.get("refinement"):
        ref = data["refinement"]
        lines.append("### Multi-Pass Refinement")
        lines.append("")
        if ref.get("applied"):
            lines.append(
                f"AutoMix ran a second pass: score improved from "
                f"{_fmt(ref.get('first_score'), '.1f')} to {_fmt(ref.get('second_score'), '.1f')}, "
                f"applying: \"{ref.get('instruction', '')}\""
            )
        else:
            lines.append(
                f"AutoMix evaluated a second pass but kept the original render "
                f"(scores: {_fmt(ref.get('first_score'), '.1f')} vs {_fmt(ref.get('second_score'), '.1f')})."
            )
        lines.append("")

    lines.append("## AutoMix Decisions Log")
    lines.append("")
    if data["decisions_log"]:
        for entry in data["decisions_log"]:
            lines.append(f"- {entry}")
    else:
        lines.append("_No decision log entries recorded for this render._")
    lines.append("")

    lines.append("## Stem Summary")
    lines.append("")
    lines.append("| Stem | Instrument | Gain | Pan | Comp Ratio | Reverb Send | Width |")
    lines.append("|---|---|---|---|---|---|---|")
    for stem in data["stems"]:
        lines.append(
            f"| {stem['stem_name']} | {stem['instrument']} | {_fmt(stem['gain_db'], '+.1f', ' dB')} "
            f"| {_fmt(stem['pan'], '+.2f')} | "
            f"{(_fmt(stem['compressor_ratio'], '.1f') + ':1') if stem['compressor_ratio'] is not None else 'n/a'} | "
            f"{_fmt(stem['reverb_send'] * 100 if stem['reverb_send'] else 0.0, '.0f', '%')} | "
            f"{_fmt(stem['stereo_width'], '.2f')} |"
        )
    lines.append("")

    bus = data["bus"]
    lines.append("## Master Bus")
    lines.append("")
    lines.append(f"- Limiter ceiling: {_fmt(bus.get('limiter_ceiling_db'), suffix=' dBFS')}")
    lines.append(f"- Limiter threshold offset: {_fmt(bus.get('limiter_threshold_db'), suffix=' dB')}")
    if bus.get("bus_compressor"):
        ratio = bus["bus_compressor"].get("ratio")
        lines.append(f"- Glue compressor ratio: {_fmt(ratio, '.1f')}:1")
    lines.append("")

    lines.append("## KENN Rationale")
    lines.append("")
    lines.append(
        "_Sourced from AutoMix's real parameter values via KENN's retrieval-grounded "
        "answer pipeline (`kenn.core.chat_answer`) — every claim below is cited to a "
        "note under `studio/kenn/kenn/Training_Data_Notes/`, not generated freeform._"
    )
    lines.append("")
    if data["kenn_explanations"]:
        for item in data["kenn_explanations"]:
            subject = " ".join(p for p in (item.get("instrument"), item.get("stem_name")) if p).strip() or "the mix"
            lines.append(f"**{item['parameter'].title()} — {subject}** ({item.get('value')})")
            lines.append("")
            lines.append(f"> {item.get('question', '')}")
            lines.append("")
            lines.append(item.get("answer", "").strip() or "_No answer returned._")
            sources = item.get("sources") or []
            if sources:
                src_names = ", ".join(
                    s.get("source", "") if isinstance(s, dict) else str(s) for s in sources
                )
                lines.append("")
                lines.append(f"*Sources: {src_names}*")
            lines.append("")
    else:
        lines.append("_No KENN explanations were generated for this render._")
        lines.append("")

    if data.get("delivery_status"):
        ds = data["delivery_status"]
        lines.append("## Delivery")
        lines.append("")
        lines.append(f"- Version: {ds.get('version')}")
        if ds.get("wav_path"):
            lines.append(f"- WAV: `{ds['wav_path']}`")
        if ds.get("zip_path"):
            lines.append(f"- Package: `{ds['zip_path']}`")
        lines.append("")

    return "\n".join(lines)


def generate_session_markdown(render_result: dict, **kwargs) -> str:
    """Convenience one-shot: gather data + render Markdown in one call.

    ``**kwargs`` are forwarded to :func:`build_session_document_data`
    (``delivery_status``, ``project_id``, ``client_name``,
    ``mix_review_report``, ``kenn_explanations``, ``session_id``,
    ``allow_llm``, ``max_kenn_items``).
    """
    data = build_session_document_data(render_result, **kwargs)
    return render_session_markdown(data)


# ---------------------------------------------------------------------------
# Optional PDF export
# ---------------------------------------------------------------------------
#
# No PDF library is available in this environment (reportlab/fpdf/weasyprint
# are all absent), so this is a small, dependency-free, hand-rolled PDF
# writer: plain monospace text pages built directly from the PDF object
# syntax (a valid minimal PDF does not require a layout engine, just a
# correctly-formed object graph, xref table, and trailer). Markdown syntax
# characters are left as-is (session notes rendered in a monospace font
# read fine with '#'/'-'/'|' visible) rather than attempting Markdown
# layout, which is out of scope for a dependency-free writer.

_PDF_PAGE_WIDTH = 612.0  # US Letter, points
_PDF_PAGE_HEIGHT = 792.0
_PDF_MARGIN = 48.0
_PDF_FONT_SIZE = 9.0
_PDF_LINE_HEIGHT = 12.0
_PDF_CHARS_PER_LINE = 100


def _pdf_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _wrap_line(line: str, width: int) -> list[str]:
    if len(line) <= width:
        return [line]
    out = []
    while len(line) > width:
        out.append(line[:width])
        line = line[width:]
    out.append(line)
    return out


def _paginate(markdown_text: str) -> list[list[str]]:
    all_lines: list[str] = []
    for raw_line in markdown_text.split("\n"):
        all_lines.extend(_wrap_line(raw_line, _PDF_CHARS_PER_LINE) or [""])

    usable_height = _PDF_PAGE_HEIGHT - 2 * _PDF_MARGIN
    lines_per_page = max(1, int(usable_height // _PDF_LINE_HEIGHT))

    pages = []
    for i in range(0, len(all_lines), lines_per_page):
        pages.append(all_lines[i:i + lines_per_page])
    return pages or [[]]


def _pdf_content_stream(lines: list[str]) -> bytes:
    y = _PDF_PAGE_HEIGHT - _PDF_MARGIN
    parts = [f"BT /F1 {_PDF_FONT_SIZE:.1f} Tf {_PDF_LINE_HEIGHT:.1f} TL {_PDF_MARGIN:.1f} {y:.1f} Td"]
    first = True
    for line in lines:
        escaped = _pdf_escape(line)
        if first:
            parts.append(f"({escaped}) Tj")
            first = False
        else:
            parts.append(f"T* ({escaped}) Tj")
    parts.append("ET")
    return ("\n".join(parts)).encode("latin-1", errors="replace")


def session_markdown_to_pdf_bytes(markdown_text: str) -> bytes:
    """Render Markdown session notes to a minimal, valid, dependency-free PDF.

    Structurally valid per the PDF 1.4 object model (catalog, pages tree,
    one Helvetica font resource shared by every page, one content stream
    per page, correct xref byte offsets and trailer) -- verified in tests
    by round-tripping the output through ``pypdf`` (a real PDF parser) and
    confirming every page's extracted text matches the source lines.
    """
    pages_lines = _paginate(markdown_text)
    num_pages = len(pages_lines)

    objects: dict[int, bytes] = {}
    # 1: Catalog, 2: Pages, 3: Font. Pages start at object 4, alternating
    # Page/Content: page N -> object (4 + 2*N), its content -> (5 + 2*N).
    page_obj_ids = [4 + 2 * i for i in range(num_pages)]
    content_obj_ids = [5 + 2 * i for i in range(num_pages)]

    kids = " ".join(f"{oid} 0 R" for oid in page_obj_ids)
    objects[1] = "<< /Type /Catalog /Pages 2 0 R >>".encode("latin-1")
    objects[2] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {num_pages} >>"
    ).encode("latin-1")
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    for i, lines in enumerate(pages_lines):
        page_id = page_obj_ids[i]
        content_id = content_obj_ids[i]
        stream = _pdf_content_stream(lines)
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {_PDF_PAGE_WIDTH:.0f} {_PDF_PAGE_HEIGHT:.0f}] "
            f"/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("latin-1")
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"\nendstream"
        )

    max_obj_id = max(objects)
    buf = bytearray()
    buf += b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets: dict[int, int] = {}
    for obj_id in range(1, max_obj_id + 1):
        body = objects.get(obj_id)
        if body is None:
            continue
        offsets[obj_id] = len(buf)
        buf += f"{obj_id} 0 obj\n".encode("latin-1")
        buf += body
        buf += b"\nendobj\n"

    xref_start = len(buf)
    buf += f"xref\n0 {max_obj_id + 1}\n".encode("latin-1")
    buf += b"0000000000 65535 f \n"
    for obj_id in range(1, max_obj_id + 1):
        offset = offsets.get(obj_id, 0)
        buf += f"{offset:010d} 00000 n \n".encode("latin-1")

    buf += (
        f"trailer\n<< /Size {max_obj_id + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF"
    ).encode("latin-1")

    return bytes(buf)


def generate_session_pdf(markdown_text: str, output_path: str | Path) -> Path:
    """Write the PDF export of a session doc to disk and return the path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(session_markdown_to_pdf_bytes(markdown_text))
    return output_path
