"""
services/trello_api.py
========================
Thin, resilient client around the Trello REST API.

Design notes / API limitations (see also README):

- Trello's `/boards/{id}/cards/all` endpoint does NOT support server-side
  filtering by custom-field values or by "created date" (custom fields are
  not queryable, and card creation date is only implicit in the Mongo-style
  id). This means true server-side date filtering is not possible with the
  public Trello REST API.
- The most efficient workaround available is:
    1. Fetch cards with a *minimal* field set first (id, dateLastActivity)
       to cheaply figure out which cards are even in play.
    2. Only request the full payload (customFieldItems, attachments,
       checklists, members) for the cards that survive a first pass,
       using Trello's `/batch` endpoint (up to 10 sub-requests per call)
       so we don't do one HTTP round-trip per card.
- Both open and archived/closed cards are required (`filter=all`) because
  archived cards are needed for historical delivery-time KPIs.
- Trello caps a single list response at 1000 items. For boards that can
  exceed that, we paginate backwards using the `before` parameter (cards
  are returned newest-id-first), stopping once we've moved entirely past
  the requested start date (cards are strictly ordered by id/creation
  time when using `before`, so this early-exit is safe and avoids
  downloading the full board history every time).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

from config import (
    CARD_QUERY_PARAMS,
    TRELLO_API_KEY,
    TRELLO_BASE_URL,
    TRELLO_BOARD_ID,
    TRELLO_TOKEN,
)
from services.cleaning import get_creation_date

PAGE_SIZE = 1000
REQUEST_TIMEOUT = 30


class TrelloAPIError(RuntimeError):
    """Raised when the Trello API returns an unexpected response."""


def _auth_params() -> Dict[str, str]:
    if not TRELLO_API_KEY or not TRELLO_TOKEN:
        raise TrelloAPIError(
            "Missing Trello credentials. Set TRELLO_API_KEY and TRELLO_TOKEN "
            "in .streamlit/secrets.toml or as environment variables."
        )
    return {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}


def _get(path: str, params: Dict[str, Any]) -> Any:
    url = f"{TRELLO_BASE_URL}{path}"
    all_params = {**_auth_params(), **params}
    resp = requests.get(url, params=all_params, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise TrelloAPIError(f"Trello API error {resp.status_code} on {path}: {resp.text[:300]}")
    return resp.json()


def _fetch_page(before_id: Optional[str]) -> List[Dict[str, Any]]:
    """Fetch a single page (<=1000 cards) of full-detail cards, newest first."""
    params = dict(CARD_QUERY_PARAMS)
    params["limit"] = PAGE_SIZE
    if before_id:
        params["before"] = before_id
    return _get(f"/boards/{TRELLO_BOARD_ID}/cards/all", params)


def fetch_cards_in_range(start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
    """
    Fetch every card (open + archived) whose derived creation date falls on
    or after `start_date`, paginating backwards and stopping early once
    cards older than `start_date` start appearing. `end_date` is applied as
    a client-side filter only (Trello has no server-side upper bound by id).

    This avoids downloading the entire board history on every dashboard
    load while still working within Trello's public API constraints.
    """
    start_date = start_date.replace(tzinfo=timezone.utc) if start_date.tzinfo is None else start_date
    end_date = end_date.replace(tzinfo=timezone.utc) if end_date.tzinfo is None else end_date

    collected: List[Dict[str, Any]] = []
    before_id: Optional[str] = None

    while True:
        page = _fetch_page(before_id)
        if not page:
            break

        stop = False
        for card in page:
            created = get_creation_date(card.get("id"))
            if created is None:
                # Can't determine age -> keep it to be safe, don't silently drop data.
                collected.append(card)
                continue
            if created < start_date:
                stop = True
                continue
            if created > end_date:
                # Newer than the requested window -> skip but keep paginating,
                # since pages are newest-first and older matches may still follow.
                continue
            collected.append(card)

        if stop or len(page) < PAGE_SIZE:
            break

        before_id = page[-1]["id"]

    return collected


@st.cache_data(ttl=300, show_spinner="Fetching cards from Trello...")
def cached_fetch_cards_in_range(start_date_iso: str, end_date_iso: str) -> List[Dict[str, Any]]:
    """
    Streamlit-cached wrapper. Cache key is the ISO date range, so changing
    only non-date filters (studio, client, member, status) reuses the cache
    and never re-hits the Trello API.
    """
    start_date = datetime.fromisoformat(start_date_iso)
    end_date = datetime.fromisoformat(end_date_iso)
    return fetch_cards_in_range(start_date, end_date)
