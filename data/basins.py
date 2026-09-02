"""Definitions of the world oil & gas basins used to place synthetic wells.

Each basin scatters wells around a centre point within a rough bounding box.
Coordinates are approximate and only meant to look realistic on a world map for
demo purposes -- they are NOT real well locations.
"""
from __future__ import annotations

# name, country, region label, centre (lon, lat), spread in degrees
# (lon_spread, lat_spread), offshore flag, dominant hydrocarbon, field prefix.
BASINS = [
    {
        "key": "north_sea",
        "name": "North Sea",
        "country": "Norway / United Kingdom",
        "region": "North Sea",
        "center": (2.0, 58.5),
        "spread": (3.2, 2.2),
        "offshore": True,
        "dominant": "oil",
        "prefix": "NS",
    },
    {
        "key": "gulf_of_mexico",
        "name": "Gulf of Mexico",
        "country": "United States",
        "region": "Gulf of Mexico",
        "center": (-91.0, 27.2),
        "spread": (4.0, 2.0),
        "offshore": True,
        "dominant": "oil",
        "prefix": "GOM",
    },
    {
        "key": "permian",
        "name": "Permian Basin",
        "country": "United States",
        "region": "West Texas",
        "center": (-102.5, 31.8),
        "spread": (2.6, 1.8),
        "offshore": False,
        "dominant": "oil",
        "prefix": "PB",
    },
    {
        "key": "ghawar",
        "name": "Ghawar / Persian Gulf",
        "country": "Saudi Arabia",
        "region": "Eastern Province",
        "center": (49.6, 25.4),
        "spread": (2.4, 2.6),
        "offshore": False,
        "dominant": "oil",
        "prefix": "GHW",
    },
    {
        "key": "campos",
        "name": "Campos Basin",
        "country": "Brazil",
        "region": "Offshore Rio de Janeiro",
        "center": (-40.2, -22.4),
        "spread": (2.2, 1.8),
        "offshore": True,
        "dominant": "oil",
        "prefix": "CMP",
    },
    {
        "key": "niger_delta",
        "name": "Niger Delta",
        "country": "Nigeria",
        "region": "Niger Delta",
        "center": (6.2, 4.7),
        "spread": (2.4, 1.6),
        "offshore": True,
        "dominant": "oil",
        "prefix": "ND",
    },
    {
        "key": "west_siberia",
        "name": "West Siberia",
        "country": "Russia",
        "region": "Khanty-Mansi",
        "center": (73.0, 61.5),
        "spread": (4.0, 2.4),
        "offshore": False,
        "dominant": "gas",
        "prefix": "WS",
    },
    {
        "key": "bohai_bay",
        "name": "Bohai Bay",
        "country": "China",
        "region": "Bohai Sea",
        "center": (119.4, 38.6),
        "spread": (2.0, 1.6),
        "offshore": True,
        "dominant": "oil",
        "prefix": "BOH",
    },
]

BASIN_BY_KEY = {b["key"]: b for b in BASINS}
