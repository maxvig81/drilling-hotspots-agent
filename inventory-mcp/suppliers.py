"""Fictitious suppliers referential for spare-part purchase orders.

Each basin/region has a nominated supplier the warehouse reorders from. Emails
use the reserved ``.example`` TLD so nothing can ever be sent to a real address.
Synthetic demo data only.
"""
from __future__ import annotations

# region -> supplier company + procurement email + our receiving warehouse.
SUPPLIERS: dict[str, dict] = {
    "North Sea": {
        "company": "North Sea Oilfield Supplies Ltd.",
        "email": "procurement@northsea-oilfield.example",
        "warehouse": "Aberdeen Supply Base",
    },
    "Gulf of Mexico": {
        "company": "GulfCoast Oil Tools Inc.",
        "email": "orders@gulfcoast-oiltools.example",
        "warehouse": "Houston Distribution Center",
    },
    "Permian Basin": {
        "company": "Permian Wellhead Supply Co.",
        "email": "sales@permian-wellhead.example",
        "warehouse": "Midland Yard",
    },
    "Ghawar / Persian Gulf": {
        "company": "Arabian Drilling Equipment Est.",
        "email": "procurement@arabian-drilleq.example",
        "warehouse": "Dammam Central Store",
    },
    "Campos Basin": {
        "company": "Atlantico Oilfield Services Ltda.",
        "email": "compras@atlantico-oilfield.example",
        "warehouse": "Macae Logistics Hub",
    },
    "Niger Delta": {
        "company": "Delta Oilfield Trading Ltd.",
        "email": "orders@delta-oilfield.example",
        "warehouse": "Port Harcourt Warehouse",
    },
    "West Siberia": {
        "company": "SibNeft Equipment LLC",
        "email": "zakaz@sibneft-equip.example",
        "warehouse": "Surgut Depot",
    },
    "Bohai Bay": {
        "company": "BoHai Petro Supplies Co.",
        "email": "sales@bohai-petro.example",
        "warehouse": "Tianjin Marine Base",
    },
}

DEFAULT_SUPPLIER = {
    "company": "Global Oilfield Procurement Ltd.",
    "email": "orders@global-oilfield.example",
    "warehouse": "Central Supply Base",
}


def supplier_for_region(region: str | None) -> dict:
    if region:
        for key, sup in SUPPLIERS.items():
            if region.strip().lower() == key.lower() or region.strip().lower() in key.lower():
                return {"region": key, **sup}
    return {"region": region or "Unassigned", **DEFAULT_SUPPLIER}
