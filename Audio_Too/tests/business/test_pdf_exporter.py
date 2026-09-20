"""Unit tests for Business PDF Invoice Exporter."""

from server.services.pdf_exporter import (
    InvoiceItem,
    InvoicePDFExporter,
    InvoiceSpec,
)


def test_invoice_totals_calculation():
    spec = InvoiceSpec(
        invoice_number="INV-2026-001",
        client_name="Acme Records",
        client_email="billing@acmerecords.com",
        issue_date="2026-07-30",
        due_date="2026-08-30",
        items=[
            InvoiceItem(description="Multitrack Mixing (10 Stems)", quantity=1, unit_price=450.0),
            InvoiceItem(description="Analog Mastering", quantity=1, unit_price=150.0),
        ],
        tax_rate=0.20,
        currency="GBP",
    )

    assert spec.subtotal == 600.0
    assert spec.tax_amount == 120.0
    assert spec.grand_total == 720.0


def test_invoice_html_rendering():
    spec = InvoiceSpec(
        invoice_number="INV-2026-002",
        client_name="John Producer",
        client_email="john@producer.com",
        issue_date="2026-07-30",
        due_date="2026-08-15",
        items=[
            InvoiceItem(description="Vocal Tuning & De-essing", quantity=2, unit_price=75.0),
        ],
        tax_rate=0.0,
        currency="GBP",
    )

    exporter = InvoicePDFExporter(spec)
    html = exporter.generate_html()

    assert "INV-2026-002" in html
    assert "John Producer" in html
    assert "£150.00" in html
    assert "AUDIO ENGINEERING COMPANY" in html


def test_invoice_pdf_rendering_produces_a_real_pdf():
    spec = InvoiceSpec(
        invoice_number="INV-2026-003",
        client_name="Jane Client",
        client_email="jane@client.com",
        issue_date="2026-07-30",
        due_date="2026-08-15",
        items=[
            InvoiceItem(description="Stereo Mastering", quantity=3, unit_price=50.0),
        ],
        tax_rate=0.20,
        currency="GBP",
    )

    exporter = InvoicePDFExporter(spec)
    pdf_bytes = exporter.generate_pdf()

    assert pdf_bytes.startswith(b"%PDF-")
    assert pdf_bytes.rstrip().endswith(b"%%EOF")
