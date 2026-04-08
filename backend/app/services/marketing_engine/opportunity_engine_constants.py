"""Shared constants for the marketing opportunity engine."""

from __future__ import annotations

LEGACY_TO_WORKFLOW = {
    "NEW": "DRAFT",
    "URGENT": "DRAFT",
    "SENT": "APPROVED",
    "CONVERTED": "ACTIVATED",
}

WORKFLOW_TO_LEGACY = {
    "DRAFT": "NEW",
    "READY": "NEW",
    "APPROVED": "SENT",
    "ACTIVATED": "CONVERTED",
    "DISMISSED": "DISMISSED",
    "EXPIRED": "EXPIRED",
}

WORKFLOW_STATUSES = {
    "DRAFT",
    "READY",
    "APPROVED",
    "ACTIVATED",
    "DISMISSED",
    "EXPIRED",
}

ALLOWED_TRANSITIONS = {
    "DRAFT": {"READY", "DISMISSED"},
    "READY": {"APPROVED", "DISMISSED"},
    "APPROVED": {"ACTIVATED", "DISMISSED"},
    "ACTIVATED": {"EXPIRED", "DISMISSED"},
    "DISMISSED": set(),
    "EXPIRED": set(),
}

BUNDESLAND_NAMES = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}

REGION_NAME_TO_CODE = {name.lower(): code for code, name in BUNDESLAND_NAMES.items()}

FORECAST_PLAYBOOK_MAP = {
    "Influenza A": "ERKAELTUNGSWELLE",
    "Influenza B": "HALSSCHMERZ_HUNTER",
    "RSV A": "SINUS_DEFENDER",
    "SARS-CoV-2": "HALSSCHMERZ_HUNTER",
}
