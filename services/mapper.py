"""
services/mapper.py
====================
Maps raw Trello card JSON into flat dict rows (same shape as the original
n8n "Base fields + custom fields" mapping step), then into `NormalizedCard`
objects ready for KPI aggregation.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from config import CUSTOM_FIELD_MAP, OPTION_MAP


def map_card_to_row(card: Dict[str, Any]) -> Dict[str, Any]:
    """
    Equivalent of the original n8n mapping node: flattens a raw Trello card
    (with customFieldItems, members, labels, badges) into one flat dict,
    resolving custom field ids/option ids to human-readable names.
    """
    row: Dict[str, Any] = {
        "Card ID": card.get("id", ""),
        "Card Name": card.get("name", ""),
        "Card URL": card.get("url") or card.get("shortUrl", ""),
        "Card Description": card.get("desc", ""),
        "Labels": ", ".join(l.get("name", "") for l in (card.get("labels") or [])),
        "Members": ", ".join(
            m.get("fullName") or m.get("username", "") for m in (card.get("members") or [])
        ),
        "Due Date": card.get("due", ""),
        "Attachment Count": (card.get("badges") or {}).get("attachments", 0),
        "Checklist Item Total Count": (card.get("badges") or {}).get("checkItems", 0),
        "Checklist Item Completed Count": (card.get("badges") or {}).get("checkItemsChecked", 0),
        "Vote Count": (card.get("badges") or {}).get("votes", 0),
        "Comment Count": (card.get("badges") or {}).get("comments", 0),
        "Last Activity Date": card.get("dateLastActivity", ""),
        "List ID": card.get("idList", ""),
        "Board ID": card.get("idBoard", ""),
        "Archived": card.get("closed", False),
        "Start Date": card.get("start", ""),
        "Due Complete": card.get("dueComplete", False),
        # Custom field defaults
        "STUDIO": "",
        "Priorité Haute": False,
        "Brief incomplet": False,
        "Agence commanditaire": "",
        "Client": "",
        "Status": "",
        "Devis MM validé": "",
        "Date de livraison interne": "",
        "Demandeur (AM / SMM)": "",
        "Priority": "",
    }

    for cf in card.get("customFieldItems") or []:
        field_name = CUSTOM_FIELD_MAP.get(cf.get("idCustomField", ""))
        if not field_name:
            continue

        id_value = cf.get("idValue")
        value = cf.get("value") or {}

        if id_value:
            row[field_name] = OPTION_MAP.get(id_value, id_value)
        elif "checked" in value:
            row[field_name] = str(value["checked"]).lower() == "true"
        elif "date" in value:
            row[field_name] = value["date"]
        elif "number" in value:
            row[field_name] = value["number"]
        elif "text" in value:
            row[field_name] = value["text"]

    return row


def map_cards_to_dataframe(cards: List[Dict[str, Any]]) -> pd.DataFrame:
    """Vectorized-friendly wrapper: maps a list of raw cards into a flat DataFrame."""
    if not cards:
        return pd.DataFrame()
    rows = [map_card_to_row(c) for c in cards]
    return pd.DataFrame(rows)
