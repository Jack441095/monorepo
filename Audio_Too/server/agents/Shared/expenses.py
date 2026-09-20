"""Expense tracking and profit reporting for Audio_Too.

Tracks business expenses, generates profit reports, and analyses
spending by category, project, and client.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Callable


def _today() -> date:
    return date.today()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


EXPENSE_CATEGORIES = [
    "Studio rent",
    "Equipment",
    "Software",
    "Plugins",
    "Marketing",
    "Travel",
    "Utilities",
    "Insurance",
    "Subscriptions",
    "Freelance/Contractors",
    "Office",
    "Education",
    "Other",
]


def _parse_expense(text: str) -> dict:
    """Parse natural language expense entry.

    Understands: "Studio rent December £500", "bought Waves plugin £200",
    "travel to session £15.50", "Spotify £9.99 monthly"

    Returns a dict with parsed fields.
    """
    result: dict = {}

    # Amount — £500, £15.50, 200 quid, etc.
    m = re.search(r"\u00a3?(\d+(?:\.\d{1,2})?)\s*(?:quid|gbp|pounds?)?", text, re.IGNORECASE)
    if m:
        result["amount"] = float(m.group(1))

    # Date — "December", "today", "yesterday", or ISO date
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        result["date"] = m.group(1)
    elif "yesterday" in text.lower():
        result["date"] = (_today() - timedelta(days=1)).isoformat()
    elif "today" in text.lower():
        result["date"] = _today().isoformat()
    else:
        # Month names — "December", "jan", "feb 2026"
        months = {
            "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
            "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        for month_name, month_num in months.items():
            if month_name in text.lower():
                year_match = re.search(r"(20\d{2})", text)
                year = int(year_match.group(1)) if year_match else _today().year
                result["date"] = f"{year}-{month_num:02d}-01"
                break

    # Default date to today if none found
    if "date" not in result:
        result["date"] = _today().isoformat()

    # Category matching
    category_keywords = {
        "Studio rent": ["rent", "studio", "lease", "space"],
        "Equipment": ["equipment", "gear", "mic", "microphone", "monitor", "speaker", "headphone",
                       "cable", "stand", "interface", "preamp", "desk", "chair"],
        "Software": ["software", "ableton", "logic", "pro tools", "cubase", "fl studio", "daw"],
        "Plugins": ["plugin", "waves", "izotope", "fabfilter", "soundtoys", "valhalla",
                     "serum", "kontakt", "omnisphere", "nexus"],
        "Marketing": ["marketing", "ad", "ads", "instagram", "facebook", "google", "social",
                       "promotion", "sponsor"],
        "Travel": ["travel", "train", "uber", "taxi", "petrol", "fuel", "parking", "toll"],
        "Utilities": ["electric", "electricity", "broadband", "internet", "phone", "water"],
        "Insurance": ["insurance"],
        "Subscriptions": ["subscription", "spotify", "netflix", "apple", "monthly", "annual"],
        "Freelance/Contractors": ["freelance", "contractor", "session musician", "vocalist",
                                   "engineer", "producer hire", "mastering"],
        "Office": ["office", "stationery", "printer", "paper", "ink"],
        "Education": ["course", "tutorial", "masterclass", "workshop", "training"],
    }
    text_lower = text.lower()
    best_category = "Other"
    best_score = 0
    for cat, keywords in category_keywords.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            best_category = cat
    result["category"] = best_category

    # Recurring
    if any(w in text_lower for w in ["monthly", "weekly", "annual", "yearly", "subscription", "recurring"]):
        result["recurring"] = "monthly" if "monthly" in text_lower or "subscription" in text_lower else "other"

    # Project / client reference
    m = re.search(r"(?:project|for)\s+(\w[\w\s]*)", text, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        stop_words = r"\b(on|in|at|the|a|an|my|our|their|this|that)\b"
        if not re.match(stop_words, candidate, re.IGNORECASE):
            result["project"] = candidate[:50]

    # Description = everything that's not amount/date/category
    desc = text
    # Remove amount
    desc = re.sub(r"\u00a3?\d+(?:\.\d{1,2})?\s*(?:quid|gbp|pounds?)?", "", desc, flags=re.IGNORECASE)
    # Remove date references
    desc = re.sub(r"(\d{4}-\d{2}-\d{2}|yesterday|today|december|january|february|march|april|may|june|july|august|september|october|november)", "", desc, flags=re.IGNORECASE)
    desc = desc.strip().strip(",").strip()
    if desc:
        result["description"] = desc[:200]
    else:
        result["description"] = text[:200]

    return result


def add_expense(
    list_records: Callable[[str], list[dict]],
    add_record: Callable[[str, dict], dict],
    text: str,
) -> str:
    """Add an expense record from natural language text."""
    details = _parse_expense(text)

    if not details.get("amount"):
        return (
            "Could not find an amount in the text.\n"
            'Try: ./agent expense add "Studio rent December £500"\n'
            "or: ./agent expense add \"Waves plugin £199\""
        )

    record = add_record("expenses", details)

    return (
        f"\U0001f4b2 Expense Recorded\n"
        f"{'=' * 35}\n"
        f"  Amount: \u00a3{record.get('amount', 0):.2f}\n"
        f"  Category: {record.get('category', 'Other')}\n"
        f"  Date: {record.get('date') or 'Today'}\n"
        f"  Description: {record.get('description', '')}\n"
        f"{'  Project: ' + record.get('project', '') if record.get('project') else ''}"
        f"{'  Recurring: ' + record.get('recurring', '') if record.get('recurring') else ''}"
        f"\n  ID: {record.get('id')}"
    )


def list_expenses(
    list_records: Callable[[str], list[dict]],
    filter_category: str | None = None,
    limit: int = 20,
) -> str:
    """List expenses, optionally filtered by category."""
    all_expenses = list_records("expenses")

    if filter_category:
        needle = filter_category.lower()
        all_expenses = [
            e for e in all_expenses
            if needle in e.get("category", "").lower()
        ]

    # Sort by date desc
    all_expenses.sort(key=lambda e: e.get("date", ""), reverse=True)
    all_expenses = all_expenses[:limit]

    if not all_expenses:
        msg = "No expenses recorded yet."
        if filter_category:
            msg = f"No expenses found for category: {filter_category}"
        return msg

    total = sum(float(e.get("amount", 0) or 0) for e in all_expenses)
    lines = [
        f"\U0001f4b2 Expenses{f' — {filter_category}' if filter_category else ''}",
        f"{'=' * 40}",
    ]
    for e in all_expenses:
        date_str = e.get("date", "?")
        cat = e.get("category", "Other")
        amount = float(e.get("amount", 0) or 0)
        desc = e.get("description", "")
        lines.append(f"  {date_str}  \u00a3{amount:>8.2f}  [{cat:<20}] {desc[:50]}")
    lines.append(f"\n  Total shown: \u00a3{total:.2f} ({len(all_expenses)} expense(s))")
    return "\n".join(lines)


def expenses_by_category(list_records: Callable[[str], list[dict]]) -> str:
    """Show expenses grouped by category."""
    all_expenses = list_records("expenses")
    if not all_expenses:
        return "No expenses recorded yet."

    by_category: dict[str, float] = defaultdict(float)
    by_month: dict[str, float] = defaultdict(float)
    for e in all_expenses:
        cat = e.get("category", "Other")
        amount = float(e.get("amount", 0) or 0)
        by_category[cat] += amount
        date_str = e.get("date", "")
        if date_str and len(date_str) >= 7:
            month_key = date_str[:7]
            by_month[month_key] += amount

    total = sum(by_category.values())
    lines = ["\U0001f4ca Expenses by Category", "=" * 40]
    for cat, amount in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
        pct = (amount / total * 100) if total else 0
        lines.append(f"  {cat:<22} \u00a3{amount:>8.2f}  ({pct:5.1f}%)")
    lines.append(f"\n  Total: \u00a3{total:.2f}")

    if by_month:
        lines.append("\n  By Month:")
        for month, amount in sorted(by_month.items(), reverse=True)[:12]:
            lines.append(f"    {month}: \u00a3{amount:.2f}")

    return "\n".join(lines)


def profit_report(
    list_records: Callable[[str], list[dict]],
    year: int | None = None,
) -> str:
    """Show revenue, expenses, and profit (monthly breakdown)."""
    year = year or _today().year

    invoices = list_records("invoices")
    expenses = list_records("expenses")
    sessions = list_records("sessions")

    # Revenue by month from paid invoices
    revenue_by_month: dict[str, float] = defaultdict(float)
    for inv in invoices:
        status = (inv.get("status") or "").lower()
        if status not in ("paid", "sent"):
            continue
        date_str = inv.get("date", "")
        if date_str and len(date_str) >= 7 and date_str.startswith(str(year)):
            month_key = date_str[:7]
            revenue_by_month[month_key] += float(inv.get("total", 0) or 0)

    # Also count session revenue (from scheduled sessions with rates)
    session_revenue_by_month: dict[str, float] = defaultdict(float)
    for s in sessions:
        if not s.get("date") or not s.get("rate"):
            continue
        date_str = str(s.get("date", ""))
        if date_str and len(date_str) >= 7 and date_str.startswith(str(year)):
            month_key = date_str[:7]
            duration_str = str(s.get("duration", ""))
            # Parse duration like "3h", "2 hours", "4"
            dur_match = re.search(r"(\d+)", duration_str)
            hours = float(dur_match.group(1)) if dur_match else 0
            rate = float(s.get("rate", 0) or 0)
            session_revenue_by_month[month_key] += hours * rate

    # Merge revenue sources
    all_months = set(revenue_by_month.keys()) | set(session_revenue_by_month.keys())

    # Expenses by month
    expense_by_month: dict[str, float] = defaultdict(float)
    for e in expenses:
        date_str = str(e.get("date", ""))
        if date_str and len(date_str) >= 7 and date_str.startswith(str(year)):
            month_key = date_str[:7]
            expense_by_month[month_key] += float(e.get("amount", 0) or 0)
            all_months.add(month_key)

    if not all_months:
        return f"No revenue or expense data for {year}."

    lines = [
        f"\U0001f4c8 Profit Report — {year}",
        f"{'=' * 50}",
        f"{'Month':<10} {'Revenue':>10} {'Expenses':>10} {'Profit':>10} {'Margin':>8}",
        f"{'-' * 50}",
    ]

    total_revenue = 0.0
    total_expenses = 0.0
    for month in sorted(all_months):
        rev = (revenue_by_month.get(month, 0) or 0) + (session_revenue_by_month.get(month, 0) or 0)
        exp = expense_by_month.get(month, 0) or 0
        profit = rev - exp
        margin = (profit / rev * 100) if rev > 0 else 0
        total_revenue += rev
        total_expenses += exp
        lines.append(f"{month:<10} \u00a3{rev:>8.2f} \u00a3{exp:>8.2f} \u00a3{profit:>8.2f} {margin:>7.1f}%")

    total_profit = total_revenue - total_expenses
    total_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
    lines.append(f"{'-' * 50}")
    lines.append(f"{'TOTAL':<10} \u00a3{total_revenue:>8.2f} \u00a3{total_expenses:>8.2f} \u00a3{total_profit:>8.2f} {total_margin:>7.1f}%")

    return "\n".join(lines)
