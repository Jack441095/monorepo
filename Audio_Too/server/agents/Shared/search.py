"""Full-text search across all Audio_Too record types.

Searches leads, projects, clients, invoices, enquiries, drafts, and
followups with relevance ranking and previews.
"""

from __future__ import annotations

from typing import Callable


def _score_match(query_words: set[str], text: str) -> float:
    """Score how well text matches a query (0.0 to 1.0)."""
    text_lower = text.lower()
    matches = sum(1 for w in query_words if w in text_lower)
    if not matches:
        return 0.0
    # Bonus for exact phrase match
    full_query = " ".join(query_words)
    exact_bonus = 1.5 if full_query in text_lower else 1.0
    return round((matches / len(query_words)) * exact_bonus, 3)


def _preview(text: str, max_len: int = 80) -> str:
    """Shorten text to a preview string."""
    t = str(text).strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def _search_table(
    records: list[dict],
    query_words: set[str],
    search_fields: list[str],
    label_field: str | None = None,
) -> list[dict]:
    """Search a list of records and return ranked matches."""
    results: list[dict] = []
    for record in records:
        best_score = 0.0
        best_preview = ""
        for field in search_fields:
            value = str(record.get(field, ""))
            score = _score_match(query_words, value)
            if score > best_score:
                best_score = score
                best_preview = _preview(value)
        if best_score > 0:
            label = record.get(label_field or "id", str(record.get("id", "?")))
            results.append({
                "score": best_score,
                "id": record.get("id", ""),
                "label": str(label),
                "preview": best_preview,
                "record": record,
            })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def search_all(
    list_records: Callable[[str], list[dict]],
    query: str,
    filter_type: str | None = None,
) -> str:
    """Search all record types and return formatted results."""
    query_words = set(query.lower().split())

    searchable: dict[str, tuple[str, list[dict], list[str], str | None]] = {}

    if not filter_type or filter_type == "leads":
        searchable["Leads"] = (
            "lead",
            list_records("leads"),
            ["lead", "contact", "service_fit", "source", "next_action", "notes"],
            "lead",
        )
    if not filter_type or filter_type == "projects":
        searchable["Projects"] = (
            "project",
            list_records("projects"),
            ["project", "client", "service", "waiting_on", "next_action", "notes"],
            "project",
        )
    if not filter_type or filter_type == "clients":
        searchable["Clients"] = (
            "name",
            list_records("clients"),
            ["name", "contact", "notes"],
            "name",
        )
    if not filter_type or filter_type == "invoices":
        searchable["Invoices"] = (
            "id",
            list_records("invoices"),
            ["client", "service", "notes", "total", "status"],
            "client",
        )
    if not filter_type or filter_type == "enquiries":
        searchable["Enquiries"] = (
            "name",
            list_records("enquiries"),
            ["name", "email", "service", "message"],
            "name",
        )
    if not filter_type or filter_type == "drafts":
        searchable["Drafts"] = (
            "id",
            list_records("drafts"),
            ["recipient", "subject", "body", "type"],
            "subject",
        )
    if not filter_type or filter_type == "followups":
        searchable["Followups"] = (
            "subject",
            list_records("followups"),
            ["subject", "notes", "owner"],
            "subject",
        )

    all_results: list[tuple[str, list[dict]]] = []
    total_matches = 0
    for table_name, (label_field, records, fields, display_field) in searchable.items():
        matches = _search_table(records, query_words, fields, display_field)
        if matches:
            all_results.append((table_name, matches))
            total_matches += len(matches)

    all_results.sort(key=lambda x: sum(r["score"] for r in x[1]), reverse=True)

    if not all_results:
        return f"No results found for: {query}"

    lines = [
        f"\U0001f50d Search Results for: {query}",
        f"  {total_matches} match(es) found",
        "",
    ]

    for table_name, matches in all_results:
        lines.append(f"  [{table_name}] ({len(matches)}):")
        for match in matches[:5]:  # Show top 5 per table
            lines.append(f"    - {match['label']}  ({match['preview']})")
        if len(matches) > 5:
            lines.append(f"    ... and {len(matches) - 5} more")
        lines.append("")

    return "\n".join(lines)
