"""Small standard-library PDF renderer for Audio_Too invoices."""

from __future__ import annotations

from pathlib import Path

BUSINESS_NAME = "Audio_Too"
BUSINESS_EMAIL = "audio_too@outlook.com"


def money(value: object) -> str:
    try:
        return f"GBP {float(value or 0):.2f}"
    except (TypeError, ValueError):
        return "GBP 0.00"


def clean_text(value: object) -> str:
    text = str(value or "").replace("£", "GBP ")
    return " ".join(text.split())


def pdf_escape(text: object) -> str:
    cleaned = clean_text(text)
    return cleaned.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def invoice_lines(invoice: dict) -> list[str]:
    invoice_id = clean_text(invoice.get("id")) or "Draft"
    service = clean_text(invoice.get("service")) or "Audio service"
    hours = clean_text(invoice.get("hours")) or "-"
    rate = money(invoice.get("rate"))
    total = money(invoice.get("total"))
    status = clean_text(invoice.get("status")) or "Draft"
    return [
        BUSINESS_NAME,
        BUSINESS_EMAIL,
        "",
        f"Invoice: {invoice_id}",
        f"Date: {clean_text(invoice.get('date'))}",
        f"Client: {clean_text(invoice.get('client'))}",
        f"Status: {status}",
        "",
        "Service",
        f"{service}",
        f"Hours/Qty: {hours}",
        f"Rate: {rate}",
        f"Total: {total}",
        "",
        "Payment due: confirm before sending",
        "Payment method: confirm before sending",
        "",
        "Notes",
        clean_text(invoice.get("notes")) or "Draft invoice created by the Audio_Too local agent.",
    ]


def invoice_pdf_bytes(invoice: dict) -> bytes:
    lines = invoice_lines(invoice)
    commands = ["BT", "/F1 12 Tf", "72 770 Td"]
    first = True
    for line in lines:
        if first:
            first = False
        else:
            commands.append("0 -20 Td")
        size = 18 if line == BUSINESS_NAME else 12
        commands.append(f"/F1 {size} Tf")
        commands.append(f"({pdf_escape(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref_at = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


def invoice_pdf_filename(invoice: dict) -> str:
    invoice_id = clean_text(invoice.get("id")) or "draft"
    client = clean_text(invoice.get("client")) or "client"
    safe = "-".join(part for part in f"invoice-{invoice_id}-{client}".lower().split() if part)
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in safe).strip("-")
    return f"{safe or 'invoice'}.pdf"


def write_invoice_pdf(invoice: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / invoice_pdf_filename(invoice)
    path.write_bytes(invoice_pdf_bytes(invoice))
    return path
