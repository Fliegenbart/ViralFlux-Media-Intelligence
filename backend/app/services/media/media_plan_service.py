"""Media-Plan CSV ingestion + lookup helpers.

Used by the ``cockpit/media-plan/*`` routes and by the snapshot builder
(EUR integration in regions / primaryRecommendation / Hero kacheln).

CSV contract
------------
Headers (case-insensitive, arbitrary order):
    iso_week        e.g. ``2026-W17`` or ``2026-17``
    bundesland      2-letter code (BW, BY, …) or ``DE`` for national
    channel         free-form tag (TV, Digital, Radio, Print, OOH, …)
    eur             numeric, thousand-separator ``.`` or ``,`` tolerated

We also accept a couple of pragmatic aliases (``week``, ``bl``, ``budget``)
because PMs paste heterogenous export formats. All rows that fail
validation show up in ``errors`` with a human-readable reason — the
upload endpoint returns them as a preview before committing.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.database import MediaPlanEntry


VALID_BUNDESLAND_CODES: frozenset[str] = frozenset({
    "SH", "HH", "NI", "HB", "NW", "HE", "RP", "SL",
    "BW", "BY", "BE", "BB", "MV", "SN", "ST", "TH",
    "DE",  # national / unallocated
})

# Pragmatic header aliases so a human CSV export "works".
HEADER_ALIASES: dict[str, str] = {
    "iso_week": "iso_week",
    "isoweek": "iso_week",
    "week": "iso_week",
    "kw": "iso_week",
    "bundesland": "bundesland",
    "bundesland_code": "bundesland",
    "bl": "bundesland",
    "region": "bundesland",
    "channel": "channel",
    "kanal": "channel",
    "eur": "eur",
    "eur_amount": "eur",
    "budget": "eur",
    "betrag": "eur",
    "amount": "eur",
}

# Accepts "2026-W17", "2026W17", "2026-17", "2026/17", "KW17/2026", "17/2026".
# We use a permissive regex that captures both numeric groups and resolve
# which one is the year vs. the week heuristically (year >= 1000).
_ISO_WEEK_RE = re.compile(
    r"^\s*(?:KW\s*)?(\d{1,4})\s*[-/W]+\s*(\d{1,4})\s*$",
    re.IGNORECASE,
)


def parse_iso_week(value: str) -> tuple[int, int] | None:
    """Return ``(year, week)`` from any of the documented inputs, or ``None``."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    m = _ISO_WEEK_RE.match(text)
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    # Year is whichever group is >= 1000. Week must be 1..53.
    if a >= 1000 and 1 <= b <= 53:
        return a, b
    if b >= 1000 and 1 <= a <= 53:
        return b, a
    return None


def parse_eur(value: str) -> float | None:
    """Parse a euro amount; tolerate ``.``/``,`` decimal and thousand separators.

    Heuristics (pragmatic, not spec-perfect):
    * Mixed ``,`` and ``.``: the right-most mark is the decimal separator,
      the other one is the thousands separator.
    * Only ``,``: treat as German decimal when ≤2 digits follow, else as
      thousand separator ("12,500" → 12500; "12,50" → 12.50).
    * Only ``.`` with exactly 3 digits after the final dot: German
      thousand separator ("12.500" → 12500). Otherwise (e.g. "12.5")
      decimal dot ("12.5" → 12.5).
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Strip currency markers.
    text = re.sub(r"[€\s]", "", text)
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        after = text.rsplit(",", 1)[1]
        if len(after) <= 2 and after.isdigit():
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "." in text:
        # Ambiguous: "12.500" could be decimal or thousand. We pick
        # thousand separator when the fragment after the last dot is
        # exactly 3 digits AND the input looks integer-ish (no other
        # dots, no funky characters). That covers the common German
        # export "12.500" for 12500.
        parts = text.split(".")
        if len(parts) >= 2 and all(p.isdigit() for p in parts):
            last = parts[-1]
            # One dot: ambiguous.
            if len(parts) == 2 and len(last) == 3:
                # German thousand: "12.500" → 12500
                text = "".join(parts)
            # Multiple dots ("12.500.000"): always thousand separators.
            elif len(parts) >= 3:
                text = "".join(parts)
            # else: leave as-is ("12.5" stays decimal).
    try:
        value_f = float(text)
    except (TypeError, ValueError):
        return None
    if value_f < 0:
        return None
    return round(value_f, 2)


@dataclass
class ParsedRow:
    iso_week_year: int
    iso_week: int
    bundesland_code: str | None
    channel: str | None
    eur_amount: float


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    total_eur: float = 0.0
    iso_weeks: set[tuple[int, int]] = field(default_factory=set)
    bundesland_codes: set[str] = field(default_factory=set)

    def as_summary(self) -> dict[str, Any]:
        return {
            "row_count": len(self.rows),
            "error_count": len(self.errors),
            "total_eur": round(self.total_eur, 2),
            "iso_weeks": sorted(
                f"{y}-W{w:02d}" for y, w in self.iso_weeks
            ),
            "bundesland_codes": sorted(self.bundesland_codes),
            "errors": self.errors[:25],  # truncate for UI
        }


def parse_csv(body: bytes | str) -> ParseResult:
    """Parse CSV bytes / text into ``ParseResult``.

    Never raises on malformed input — returns errors in the result so the
    UI can render a row-by-row preview.
    """
    result = ParseResult()
    if isinstance(body, bytes):
        try:
            text = body.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = body.decode("latin-1")
            except Exception:
                result.errors.append({"row": 0, "reason": "decode_failed"})
                return result
    else:
        text = body

    # Try to sniff the dialect (comma vs. semicolon). PMs from Excel
    # typically get "," in de_DE exports.
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        class _Default(csv.excel):
            delimiter = ","
        dialect = _Default

    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        result.errors.append({"row": 0, "reason": "empty_file"})
        return result

    raw_header = [c.strip().lower() for c in rows[0]]
    header_map: dict[int, str] = {}
    for idx, col in enumerate(raw_header):
        canonical = HEADER_ALIASES.get(col)
        if canonical:
            header_map[idx] = canonical

    required = {"iso_week", "bundesland", "eur"}
    missing = required - set(header_map.values())
    if missing:
        result.errors.append({
            "row": 1,
            "reason": f"missing_required_columns: {', '.join(sorted(missing))}",
            "found_headers": raw_header,
        })
        return result

    for line_no, row in enumerate(rows[1:], start=2):
        record: dict[str, Any] = {}
        for idx, cell in enumerate(row):
            canonical = header_map.get(idx)
            if canonical:
                record[canonical] = cell.strip()
        iso_raw = record.get("iso_week", "")
        bl_raw = str(record.get("bundesland", "")).strip().upper()
        chan_raw = record.get("channel", "") or None
        eur_raw = record.get("eur", "")

        parsed_week = parse_iso_week(iso_raw)
        if parsed_week is None:
            result.errors.append({"row": line_no, "reason": f"invalid_iso_week: {iso_raw!r}"})
            continue
        if bl_raw not in VALID_BUNDESLAND_CODES:
            result.errors.append({
                "row": line_no,
                "reason": f"invalid_bundesland: {bl_raw!r}",
            })
            continue
        eur_val = parse_eur(eur_raw)
        if eur_val is None:
            result.errors.append({"row": line_no, "reason": f"invalid_eur: {eur_raw!r}"})
            continue

        y, w = parsed_week
        result.rows.append(
            ParsedRow(
                iso_week_year=y,
                iso_week=w,
                bundesland_code=bl_raw,
                channel=(chan_raw or None),
                eur_amount=eur_val,
            )
        )
        result.total_eur += eur_val
        result.iso_weeks.add((y, w))
        result.bundesland_codes.add(bl_raw)

    return result


def commit_plan(
    db: Session,
    *,
    client: str,
    rows: Iterable[ParsedRow],
    replace_current: bool = True,
) -> dict[str, Any]:
    """Persist parsed rows. By default wipes the client's existing plan first."""
    upload_id = uuid.uuid4().hex
    if replace_current:
        db.query(MediaPlanEntry).filter(MediaPlanEntry.client == client).delete(
            synchronize_session=False
        )
    inserted = 0
    for row in rows:
        entry = MediaPlanEntry(
            client=client,
            iso_week_year=row.iso_week_year,
            iso_week=row.iso_week,
            bundesland_code=row.bundesland_code,
            channel=row.channel,
            eur_amount=row.eur_amount,
            upload_id=upload_id,
        )
        db.add(entry)
        inserted += 1
    db.commit()
    return {"upload_id": upload_id, "inserted": inserted, "client": client}


def current_plan_rows(
    db: Session,
    *,
    client: str,
    iso_year: int | None = None,
    iso_week: int | None = None,
) -> list[MediaPlanEntry]:
    """Return all plan rows for a client, optionally constrained to one ISO week."""
    q = db.query(MediaPlanEntry).filter(MediaPlanEntry.client == client)
    if iso_year is not None:
        q = q.filter(MediaPlanEntry.iso_week_year == iso_year)
    if iso_week is not None:
        q = q.filter(MediaPlanEntry.iso_week == iso_week)
    return q.order_by(
        MediaPlanEntry.iso_week_year.asc(),
        MediaPlanEntry.iso_week.asc(),
        MediaPlanEntry.bundesland_code.asc().nullsfirst(),
    ).all()


def clear_plan(db: Session, *, client: str) -> int:
    """Hard-delete all plan rows for the client. Returns row count."""
    n = db.query(MediaPlanEntry).filter(MediaPlanEntry.client == client).delete(
        synchronize_session=False
    )
    db.commit()
    return int(n or 0)


def current_iso_week(today: date) -> tuple[int, int]:
    """Return the ISO year/week tuple for a date (shim for snapshot builder)."""
    y, w, _ = today.isocalendar()
    return int(y), int(w)


def aggregate_by_bundesland(
    rows: Iterable[MediaPlanEntry],
) -> dict[str, float]:
    """Sum eur_amount per bundesland_code; DE / None rows land in ``"DE"``."""
    totals: dict[str, float] = {}
    for r in rows:
        code = (r.bundesland_code or "DE").upper()
        totals[code] = round(totals.get(code, 0.0) + float(r.eur_amount), 2)
    return totals
