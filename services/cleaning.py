"""
services/cleaning.py
=====================
Business cleaning logic ported from the original n8n JavaScript:

- Agency roster / member resolution (fuzzy match on cleaned key, including
  substring "contains" fallback, longest-key-first, exactly like the JS)
- Creation date derivation from the Trello Mongo-style card id
- Delivery date derivation (archived / done+approved -> last activity date)

This module has no Streamlit or network dependency, so it is fully unit
testable in isolation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from config import RESOURCES
from services.utils import clean_status, to_key


# ── ROSTER INDEX (built once at import time, mirrors the JS closure) ──
def _build_roster_index() -> Tuple[Dict[str, str], Dict[str, str], List[str]]:
    roster_map: Dict[str, str] = {}
    member_agency: Dict[str, str] = {}
    for agency, members in RESOURCES.items():
        for m in members:
            key = to_key(m)
            roster_map[key] = m
            member_agency[key] = agency
    # Longest keys first, exactly like the JS `.sort((a, b) => b.length - a.length)`
    roster_keys = sorted(roster_map.keys(), key=len, reverse=True)
    return roster_map, member_agency, roster_keys


_ROSTER_MAP, _MEMBER_AGENCY, _ROSTER_KEYS = _build_roster_index()


def resolve_member(raw_name: str) -> Optional[Dict[str, str]]:
    """
    Resolve a raw Trello member name/username to a canonical roster member.

    Mirrors the JS `resolveMember`:
    1. Exact match on cleaned key.
    2. Fallback: substring containment either way (only when the candidate
       key is at least 5 characters), longest roster keys checked first.

    Returns {"canonical": str, "agency": str} or None if no match.
    """
    key = to_key(raw_name)
    if not key:
        return None

    if key in _ROSTER_MAP:
        return {"canonical": _ROSTER_MAP[key], "agency": _MEMBER_AGENCY[key]}

    for rk in _ROSTER_KEYS:
        if rk in key or (len(key) >= 5 and key in rk):
            return {"canonical": _ROSTER_MAP[rk], "agency": _MEMBER_AGENCY[rk]}

    return None


def get_creation_date(card_id: Optional[str]) -> Optional[datetime]:
    """
    Derive the Trello card creation date from the first 4 bytes (8 hex chars)
    of its Mongo-style ObjectId, exactly like the JS `getCreationDate`.
    """
    if not card_id:
        return None
    try:
        ts = int(str(card_id)[:8], 16)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def get_delivery_date(
    archived: bool,
    status_text: str,
    last_activity_date: Optional[datetime],
) -> Optional[datetime]:
    """
    Derive the delivery date exactly like the JS `getDeliveryDate`:
    - if the card is archived and has a last-activity date -> that date
    - else if status cleans to 'done' and has a last-activity date -> that date
    - else None
    """
    if last_activity_date is None:
        return None
    if archived:
        return last_activity_date
    if clean_status(status_text) == "done":
        return last_activity_date
    return None
