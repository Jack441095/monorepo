"""Minimal multi-page PDF writer (stdlib only, Latin-1 text)."""

from __future__ import annotations

from pathlib import Path

MARGIN_X = 54
MARGIN_TOP = 780
LINE_HEIGHT = 14
TITLE_SIZE = 16
BODY_SIZE = 11


def clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def pdf_escape(text: object) -> str:
    cleaned = clean_text(text)
    return cleaned.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def wrap_lines(text: str, *, width: int = 88) -> list[str]:
    words = clean_text(text).split()
    if not words:
        return [""]
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if len(candidate) <= width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines or [""]


class PdfBuilder:
    def __init__(self) -> None:
        self.pages: list[list[str]] = [[]]
        self.y = MARGIN_TOP

    def _cmds(self) -> list[str]:
        return self.pages[-1]

    def new_page(self) -> None:
        self.pages.append([])
        self.y = MARGIN_TOP

    def _ensure_space(self) -> None:
        if self.y - LINE_HEIGHT < 72:
            self.new_page()

    def text(self, line: str, *, size: int = BODY_SIZE, gap: int = 0) -> None:
        for part in wrap_lines(line):
            self._ensure_space()
            if gap:
                self.y -= gap
            self._cmds().append(f"/F1 {size} Tf")
            self._cmds().append(f"{MARGIN_X} {self.y} Td")
            self._cmds().append(f"({pdf_escape(part)}) Tj")
            self.y -= LINE_HEIGHT

    def blank(self, lines: int = 1) -> None:
        self.y -= LINE_HEIGHT * lines

    def build(self) -> bytes:
        # Objects: 1 Catalog, 2 Pages, 3 Font, then per page: Page + Contents
        font = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
        page_ids: list[int] = []
        content_ids: list[int] = []
        obj_id = 4
        page_objs: list[bytes] = []
        content_objs: list[bytes] = []
        for page_cmds in self.pages:
            page_ids.append(obj_id)
            obj_id += 1
            content_ids.append(obj_id)
            obj_id += 1
            stream_commands = ["BT", *page_cmds, "ET"]
            stream = "\n".join(stream_commands).encode("latin-1", errors="replace")
            content_objs.append(
                b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
            )
            page_objs.append(
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                b"/Resources << /Font << /F1 3 0 R >> >> /Contents "
                + str(content_ids[-1]).encode()
                + b" 0 R >>"
            )

        kids = " ".join(f"{pid} 0 R" for pid in page_ids)
        pages_obj = f"<< /Type /Pages /Kids [{kids}] /Count {len(self.pages)} >>".encode()
        catalog = b"<< /Type /Catalog /Pages 2 0 R >>"
        all_objects = [catalog, pages_obj, font, *page_objs, *content_objs]

        output = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, obj in enumerate(all_objects, start=1):
            offsets.append(len(output))
            output.extend(f"{index} 0 obj\n".encode("ascii"))
            output.extend(obj)
            output.extend(b"\nendobj\n")
        xref_at = len(output)
        output.extend(f"xref\n0 {len(all_objects) + 1}\n".encode("ascii"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        output.extend(
            f"trailer\n<< /Size {len(all_objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode(
                "ascii"
            )
        )
        return bytes(output)


def write_text_pdf(path: Path, lines: list[tuple[str, int]]) -> Path:
    """lines: (text, font_size). Use size 0 for a blank line."""
    builder = PdfBuilder()
    for text, size in lines:
        if size == 0:
            builder.blank()
        else:
            builder.text(text, size=size, gap=6 if size >= TITLE_SIZE else 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(builder.build())
    return path
