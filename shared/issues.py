"""Shared failure/issue taxonomy for the Drilling Hotspots Agent ecosystem.

The same failure codes are used across the three data sources so the agent can
reason across them:

* the **wells** dataset raises alerts with these codes,
* the **parts inventory** links each part to the issue codes it addresses,
* the **crew** referential maps each issue to the maintenance specialty needed.

Keeping the taxonomy in one place lets each MCP server resolve a free-text
problem description (English or French, e.g. "annulus overpressure" /
"surpression de l'anneau") to a canonical issue code.
"""
from __future__ import annotations

# code -> definition
ISSUES: dict[str, dict] = {
    "OVERPRESSURE": {
        "label": "Annulus overpressure",
        "specialty": "WELL_INTEGRITY",
        "keywords": ["annulus", "annular", "overpressure", "over pressure",
                     "anneau", "surpression", "pression annulaire", "casing pressure"],
    },
    "PRESSURE_DECLINE": {
        "label": "Wellhead pressure decline",
        "specialty": "WELL_INTEGRITY",
        "keywords": ["pressure decline", "declining pressure", "low pressure",
                     "déclin", "baisse de pression", "chute de pression"],
    },
    "CORROSION": {
        "label": "Corrosion inhibitor low",
        "specialty": "WELL_INTEGRITY",
        "keywords": ["corrosion", "corrosive", "corrosif", "métal", "rust"],
    },
    "ESP_FAILURE_RISK": {
        "label": "ESP failure risk",
        "specialty": "ARTIFICIAL_LIFT",
        "keywords": ["esp", "pump", "pompe", "artificial lift", "motor", "moteur",
                     "electric submersible"],
    },
    "GAS_LOCK": {
        "label": "Gas lock / low intake",
        "specialty": "ARTIFICIAL_LIFT",
        "keywords": ["gas lock", "gaslock", "low intake", "gazage", "gas interference"],
    },
    "SAND_PRODUCTION": {
        "label": "Sand production",
        "specialty": "SAND_CONTROL",
        "keywords": ["sand", "sable", "sanding", "solids", "erosion"],
    },
    "SCALE_BUILDUP": {
        "label": "Scale build-up",
        "specialty": "FLOW_ASSURANCE",
        "keywords": ["scale", "tartre", "deposit", "dépôt", "scaling"],
    },
    "HIGH_WATER_CUT": {
        "label": "High water cut",
        "specialty": "FLOW_ASSURANCE",
        "keywords": ["water cut", "water", "venue d'eau", "eau", "watercut", "wor"],
    },
    "H2S_DETECTED": {
        "label": "H2S detected",
        "specialty": "HSE_SOUR",
        "keywords": ["h2s", "sour", "sulfide", "sulphide", "hydrogène sulfuré",
                     "hydrogen sulfide", "acid gas"],
    },
}

# Human-readable specialty labels.
SPECIALTY_LABELS: dict[str, str] = {
    "WELL_INTEGRITY": "Well integrity",
    "ARTIFICIAL_LIFT": "Artificial lift (ESP)",
    "SAND_CONTROL": "Sand control",
    "FLOW_ASSURANCE": "Flow assurance",
    "HSE_SOUR": "HSE / sour service",
    "GENERAL": "General well services",
}

ISSUE_CODES = list(ISSUES)


def label_for(code: str) -> str:
    return ISSUES.get(code, {}).get("label", code)


def specialty_for(code: str) -> str | None:
    return ISSUES.get(code, {}).get("specialty")


def resolve_issue(text: str) -> str | None:
    """Resolve a code, label, or free-text description to a canonical code.

    Matching is case-insensitive and accepts English or French keywords.
    """
    if not text:
        return None
    q = text.strip().lower()
    # Direct code match.
    for code in ISSUES:
        if q == code.lower():
            return code
    # Exact label match.
    for code, d in ISSUES.items():
        if q == d["label"].lower():
            return code
    # Keyword / substring match (longest keyword first for specificity).
    best = None
    best_len = 0
    for code, d in ISSUES.items():
        for kw in [d["label"].lower(), *d["keywords"]]:
            if kw in q and len(kw) > best_len:
                best, best_len = code, len(kw)
    return best
