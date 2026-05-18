"""Pure formatting helpers for Eve's Textual UI."""

from __future__ import annotations

import re
import shlex
from typing import Any

STYLE_TAG_RE = re.compile(r"\[(?:/?(?:primary|success|warning|error|b|dim)|/)\]")


def command_label(args: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in args)


def glyph_for_status(status: str) -> str:
    if status in {"running", "provisioned", "installed", "succeeded"}:
        return "●"
    if status in {"stopped", "removed", "missing", "absent"}:
        return "○"
    if status in {"failed", "error"}:
        return "!"
    if status in {"changing", "provisioning", "running-op"}:
        return "…"
    return "?"


def markup_for_status(status: str) -> str:
    if status in {"running", "provisioned", "installed", "succeeded"}:
        return f"[success]{status}[/]"
    if status in {"stopped", "removed", "missing", "absent"}:
        return f"[warning]{status}[/]"
    if status in {"failed", "error"}:
        return f"[error]{status}[/]"
    if status in {"changing", "provisioning"}:
        return f"[primary]{status}[/]"
    return status


def display_state(status: str) -> str:
    return "new" if status == "unknown" else status


def plain_log_line(message: str) -> str:
    return STYLE_TAG_RE.sub("", message)


def package_source_label(selected_by: Any) -> str:
    if not isinstance(selected_by, list) or not selected_by:
        return "available"
    labels: list[str] = []
    bundles: list[str] = []
    for source in selected_by:
        source_text = str(source)
        if source_text == "direct":
            labels.append("extra")
        elif source_text.startswith("bundle:"):
            bundles.append(source_text.split(":", 1)[1])
    if bundles:
        labels.append("bundle: " + ", ".join(bundles))
    return "; ".join(labels) if labels else "selected"


def package_summary_label(summary: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, label in (
        ("failed", "failed"),
        ("installed", "installed"),
        ("missing", "missing"),
        ("unknown", "unknown"),
        ("removed", "removed"),
        ("reinstalled", "reinstalled"),
    ):
        count = int(summary.get(key, 0) or 0)
        if count:
            parts.append(f"{count} {label}")
    return " / ".join(parts) if parts else "none selected"


def format_aggregate(counts: dict[str, int]) -> str:
    return (
        f"[success]● {counts.get('running', 0)} running[/]  "
        f"[warning]○ {counts.get('stopped', 0)} stopped[/]  "
        f"[error]! {counts.get('failed', 0)} failed[/]  "
        f"? {counts.get('other', 0)} unknown"
    )
