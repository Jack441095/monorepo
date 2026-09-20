"""Signed-token invoice HTML and PDF delivery."""

from __future__ import annotations

import html
from urllib.parse import parse_qs, urlparse

from db import list_records
from invoice_pdf import invoice_pdf_bytes, invoice_pdf_filename, money
from invoice_tokens import verify_invoice_token


def invoice_authorized(handler, invoice_id: str, full_path: str) -> bool:
    if handler.authorized():
        return True
    token = parse_qs(urlparse(full_path).query).get("token", [""])[0]
    return verify_invoice_token(invoice_id, token)


def invoice_html(invoice: dict) -> bytes:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Invoice {html.escape(invoice.get('id', ''))}</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body class="invoice-page">
  <main class="invoice">
    <h1>Invoice</h1>
    <p><strong>Invoice:</strong> {html.escape(invoice.get('id', ''))}</p>
    <p><strong>Date:</strong> {html.escape(str(invoice.get('date', '')))}</p>
    <p><strong>Client:</strong> {html.escape(invoice.get('client', ''))}</p>
    <table>
      <thead><tr><th>Service</th><th>Hours</th><th>Rate</th><th>Total</th><th>Status</th></tr></thead>
      <tbody><tr><td>{html.escape(invoice.get('service', ''))}</td><td>{html.escape(str(invoice.get('hours', '')))}</td><td>{money(invoice.get('rate'))}</td><td>{money(invoice.get('total'))}</td><td>{html.escape(invoice.get('status', ''))}</td></tr></tbody>
    </table>
    <p class="status">Audio_Too · audio_too@outlook.com</p>
  </main>
</body>
</html>""".encode("utf-8")


def handle_invoice_get(handler, full_path: str) -> bool:
    parsed = urlparse(full_path)
    if not parsed.path.startswith("/invoice/"):
        return False
    invoice_ref = parsed.path.rsplit("/", 1)[-1]
    invoice_id = invoice_ref[:-4] if invoice_ref.endswith(".pdf") else invoice_ref
    if not invoice_authorized(handler, invoice_id, full_path):
        handler.send_bytes(401, b"Invalid or expired invoice link.", "text/plain; charset=utf-8")
        return True
    invoice = next(
        (item for item in list_records("invoices") if item.get("id") == invoice_id),
        None,
    )
    if not invoice:
        handler.send_bytes(404, b"Invoice not found", "text/plain; charset=utf-8")
        return True
    if invoice_ref.endswith(".pdf"):
        handler.send_bytes(
            200,
            invoice_pdf_bytes(invoice),
            "application/pdf",
            filename=invoice_pdf_filename(invoice),
        )
    else:
        handler.send_bytes(200, invoice_html(invoice), "text/html; charset=utf-8")
    return True
