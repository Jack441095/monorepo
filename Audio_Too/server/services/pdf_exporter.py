"""Invoice and Project Estimate PDF/HTML Exporter for Business System.

Generates structured HTML & printable invoice documents for clients, featuring line items,
vat calculations, payment terms, and branding header.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class InvoiceItem:
    description: str
    quantity: float
    unit_price: float

    @property
    def total(self) -> float:
        return round(self.quantity * self.unit_price, 2)


@dataclass
class InvoiceSpec:
    invoice_number: str
    client_name: str
    client_email: str
    issue_date: str
    due_date: str
    items: list[InvoiceItem]
    tax_rate: float = 0.0  # e.g., 0.20 for 20% VAT
    currency: str = "GBP"

    @property
    def subtotal(self) -> float:
        return round(sum(item.total for item in self.items), 2)

    @property
    def tax_amount(self) -> float:
        return round(self.subtotal * self.tax_rate, 2)

    @property
    def grand_total(self) -> float:
        return round(self.subtotal + self.tax_amount, 2)


class InvoicePDFExporter:
    """Exporter generating styled HTML print invoices for audio engineering clients."""

    def __init__(self, spec: InvoiceSpec):
        self.spec = spec

    def generate_html(self) -> str:
        """Generate printable HTML markup for the invoice."""
        currency_symbol = "£" if self.spec.currency == "GBP" else "$"

        items_html = ""
        for item in self.spec.items:
            items_html += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #eee;">{item.description}</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">{item.quantity}</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">{currency_symbol}{item.unit_price:.2f}</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right; font-weight: bold;">{currency_symbol}{item.total:.2f}</td>
            </tr>
            """

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Invoice {self.spec.invoice_number}</title>
    <style>
        body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333; margin: 40px; }}
        .header {{ display: flex; justify-content: space-between; border-bottom: 2px solid #00f0ff; padding-bottom: 20px; }}
        .title {{ font-size: 28px; font-weight: bold; color: #111; }}
        .details {{ margin-top: 30px; display: flex; justify-content: space-between; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 30px; }}
        th {{ background: #f8f9fa; text-align: left; padding: 12px; border-bottom: 2px solid #ddd; }}
        .totals {{ margin-top: 30px; float: right; width: 300px; }}
        .totals row {{ display: flex; justify-content: space-between; padding: 6px 0; }}
        .grand-total {{ font-size: 18px; font-weight: bold; border-top: 2px solid #333; padding-top: 10px; margin-top: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="title">AUDIO ENGINEERING COMPANY</div>
            <div>Professional Mixing & Mastering Services</div>
        </div>
        <div style="text-align: right;">
            <div style="font-size: 20px; font-weight: bold;">INVOICE</div>
            <div>#{self.spec.invoice_number}</div>
        </div>
    </div>

    <div class="details">
        <div>
            <strong>Billed To:</strong><br>
            {self.spec.client_name}<br>
            {self.spec.client_email}
        </div>
        <div style="text-align: right;">
            <strong>Issue Date:</strong> {self.spec.issue_date}<br>
            <strong>Due Date:</strong> {self.spec.due_date}
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Description</th>
                <th style="text-align: right;">Qty</th>
                <th style="text-align: right;">Unit Price</th>
                <th style="text-align: right;">Total</th>
            </tr>
        </thead>
        <tbody>
            {items_html}
        </tbody>
    </table>

    <div class="totals">
        <div style="display: flex; justify-content: space-between; padding: 4px 0;">
            <span>Subtotal:</span>
            <span>{currency_symbol}{self.spec.subtotal:.2f}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 4px 0;">
            <span>Tax ({int(self.spec.tax_rate*100)}%):</span>
            <span>{currency_symbol}{self.spec.tax_amount:.2f}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 8px 0;" class="grand-total">
            <span>Grand Total:</span>
            <span>{currency_symbol}{self.spec.grand_total:.2f}</span>
        </div>
    </div>
</body>
</html>
"""
        return html

    def generate_pdf(self) -> bytes:
        """Render the invoice as an actual PDF (not just print-friendly HTML)."""
        from fpdf import FPDF, XPos, YPos

        currency_symbol = "£" if self.spec.currency == "GBP" else "$"
        next_line = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}

        pdf = FPDF(format="A4")
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        pdf.set_font("Helvetica", "B", 20)
        pdf.cell(0, 10, "AUDIO ENGINEERING COMPANY", **next_line)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 7, "Professional Mixing & Mastering Services", **next_line)
        pdf.ln(4)

        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, f"INVOICE #{self.spec.invoice_number}", **next_line)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 6, f"Billed to: {self.spec.client_name} ({self.spec.client_email})", **next_line)
        pdf.cell(0, 6, f"Issue date: {self.spec.issue_date}    Due date: {self.spec.due_date}", **next_line)
        pdf.ln(6)

        col_widths = (95, 25, 30, 30)
        pdf.set_font("Helvetica", "B", 11)
        for header, width in zip(("Description", "Qty", "Unit price", "Total"), col_widths):
            pdf.cell(width, 8, header, border="B")
        pdf.ln()

        pdf.set_font("Helvetica", "", 11)
        for item in self.spec.items:
            pdf.cell(col_widths[0], 8, item.description, border="B")
            pdf.cell(col_widths[1], 8, f"{item.quantity:g}", border="B", align="R")
            pdf.cell(col_widths[2], 8, f"{currency_symbol}{item.unit_price:.2f}", border="B", align="R")
            pdf.cell(col_widths[3], 8, f"{currency_symbol}{item.total:.2f}", border="B", align="R")
            pdf.ln()
        pdf.ln(4)

        pdf.set_font("Helvetica", "", 11)
        pdf.cell(160, 7, "Subtotal", align="R")
        pdf.cell(30, 7, f"{currency_symbol}{self.spec.subtotal:.2f}", align="R", **next_line)
        pdf.cell(160, 7, f"Tax ({int(self.spec.tax_rate * 100)}%)", align="R")
        pdf.cell(30, 7, f"{currency_symbol}{self.spec.tax_amount:.2f}", align="R", **next_line)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(160, 8, "Grand total", align="R")
        pdf.cell(30, 8, f"{currency_symbol}{self.spec.grand_total:.2f}", align="R", **next_line)

        return bytes(pdf.output())
