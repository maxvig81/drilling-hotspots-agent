"""Resolve a named area (basin, country, or region) to a zoom bounding box.

Used by ``show_wells_map`` so users can say "zoom to the North Sea" or
"show wells in Brazil" and get a sensible map view. Matching is
case-insensitive and accepts a few common aliases.
"""
from __future__ import annotations

# label -> bbox [minLon, minLat, maxLon, maxLat]. Boxes are padded a little
# around each basin so all of its wells stay comfortably in view.
AREAS: dict[str, list[float]] = {
    "North Sea": [-3.5, 55.5, 8.0, 61.5],
    "Gulf of Mexico": [-97.5, 24.5, -84.5, 30.0],
    "Permian Basin": [-106.0, 29.5, -99.0, 34.0],
    "Ghawar / Persian Gulf": [46.5, 22.5, 52.5, 28.5],
    "Campos Basin": [-43.0, -24.5, -37.5, -20.0],
    "Niger Delta": [3.5, 2.8, 9.0, 6.6],
    "West Siberia": [68.0, 58.5, 78.0, 64.5],
    "Bohai Bay": [117.0, 36.8, 121.8, 40.4],
}

# alias -> canonical AREAS key
ALIASES: dict[str, str] = {
    "north sea": "North Sea",
    "norway": "North Sea",
    "norwegian": "North Sea",
    "uk": "North Sea",
    "united kingdom": "North Sea",
    "gulf of mexico": "Gulf of Mexico",
    "gom": "Gulf of Mexico",
    "permian": "Permian Basin",
    "permian basin": "Permian Basin",
    "west texas": "Permian Basin",
    "texas": "Permian Basin",
    "usa": "Gulf of Mexico",
    "united states": "Gulf of Mexico",
    "ghawar": "Ghawar / Persian Gulf",
    "persian gulf": "Ghawar / Persian Gulf",
    "saudi arabia": "Ghawar / Persian Gulf",
    "saudi": "Ghawar / Persian Gulf",
    "middle east": "Ghawar / Persian Gulf",
    "campos": "Campos Basin",
    "campos basin": "Campos Basin",
    "brazil": "Campos Basin",
    "niger delta": "Niger Delta",
    "nigeria": "Niger Delta",
    "west siberia": "West Siberia",
    "siberia": "West Siberia",
    "russia": "West Siberia",
    "bohai": "Bohai Bay",
    "bohai bay": "Bohai Bay",
    "china": "Bohai Bay",
}


def resolve_area(name: str) -> tuple[list[float], str] | None:
    """Return ``(bbox, label)`` for a named area, or ``None`` if unknown."""
    if not name:
        return None
    q = name.strip().lower()
    # Exact canonical match.
    for label, bbox in AREAS.items():
        if label.lower() == q:
            return list(bbox), label
    # Alias match.
    if q in ALIASES:
        label = ALIASES[q]
        return list(AREAS[label]), label
    # Substring / partial match against canonical labels and aliases.
    for label in AREAS:
        if q in label.lower() or label.lower().split(" /")[0] in q:
            return list(AREAS[label]), label
    for alias, label in ALIASES.items():
        if q in alias or alias in q:
            return list(AREAS[label]), label
    return None
