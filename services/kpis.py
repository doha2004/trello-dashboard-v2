"""
services/kpis.py
==================
Python port of the original n8n JavaScript KPI-calculation loop.

Pipeline:
    flat DataFrame (from mapper.map_cards_to_dataframe)
        -> list[NormalizedCard]  (build_normalized_cards)
        -> optional filtering    (apply_filters)
        -> long-format KPI table (compute_kpis), same shape as the old
           Google Sheet: columns = [agency, kpi, dimension, value]

The bucket structure and every KPI formula mirror the JS exactly:
  - nbre de briefs
  - nbre de briefs Priorité haute
  - délai de livraison moyen
  - nbre de briefs par ressource
  - nbre de briefs par type de livrable
  - nbre de briefs par client
  - nbre de briefs Priorité haute par client
  - nbre de briefs par type de livrable par ressource
  - délai de livraison par ressource
  - délai de livraison par client
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from config import RESOURCES
from models import FilterSelection, KPIRow, NormalizedCard
from services.cleaning import get_creation_date, get_delivery_date, resolve_member
from services.utils import (
    avg,
    clean_boolean,
    clean_dimension,
    clean_priority,
    clean_status,
    days_between,
)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return pd.to_datetime(value, utc=True, errors="coerce").to_pydatetime()
    except Exception:
        return None


def build_normalized_cards(df: pd.DataFrame) -> List[NormalizedCard]:
    """
    Convert the flat mapper DataFrame into NormalizedCard objects, resolving
    members, computing creation/delivery dates, and cleaning status/priority
    -- exactly like the JS "MAIN LOOP" section, minus the KPI aggregation
    itself (kept separate here for testability/reuse).

    Cards that resolve to zero known agency members are dropped, matching
    the JS `if (!resolved.length) continue;`.
    """
    if df is None or df.empty:
        return []

    normalized: List[NormalizedCard] = []

    for _, card in df.iterrows():
        card_id = str(card.get("Card ID", ""))
        raw_members = [m.strip() for m in str(card.get("Members", "") or "").split(",") if m.strip()]

        resolved = []
        seen = set()
        for raw in raw_members:
            match = resolve_member(raw)
            if not match:
                continue
            dedupe_key = f"{match['agency']}|{match['canonical']}"
            if dedupe_key not in seen:
                seen.add(dedupe_key)
                resolved.append(match)

        if not resolved:
            continue

        labels = [
            clean_dimension(l, "no label")
            for l in str(card.get("Labels", "") or "").split(",")
            if l.strip() or True
        ]
        labels = [l for l in labels if l]

        status_raw = card.get("Status", "")
        priority_raw = card.get("Priority", "")
        priorite_haute_flag = clean_boolean(card.get("Priorité Haute", False))
        is_high_priority = priorite_haute_flag or clean_priority(priority_raw) == "high"
        archived = bool(card.get("Archived", False))

        last_activity = _parse_datetime(card.get("Last Activity Date"))
        creation_date = get_creation_date(card_id)
        delivery_date = get_delivery_date(archived, status_raw, last_activity)

        delivery_days = None
        status_clean = clean_status(status_raw)
        if status_clean == "done" and creation_date and delivery_date:
            delivery_days = days_between(creation_date, delivery_date)

        normalized.append(
            NormalizedCard(
                card_id=card_id,
                name=str(card.get("Card Name", "")),
                url=str(card.get("Card URL", "")),
                labels=labels,
                members_raw=raw_members,
                resolved_members=resolved,
                archived=archived,
                status_raw=str(status_raw),
                status_clean=status_clean,
                priority_raw=str(priority_raw),
                priority_haute_flag=priorite_haute_flag,
                is_high_priority=is_high_priority,
                client_raw=str(card.get("Client", "")),
                client_clean=clean_dimension(card.get("Client", ""), "unknown"),
                studio=str(card.get("STUDIO", "")),
                agence_commanditaire=str(card.get("Agence commanditaire", "")),
                devis_mm_valide=card.get("Devis MM validé", ""),
                date_livraison_interne=card.get("Date de livraison interne", ""),
                demandeur=str(card.get("Demandeur (AM / SMM)", "")),
                last_activity_date=last_activity,
                creation_date=creation_date,
                delivery_date=delivery_date,
                delivery_days=delivery_days,
            )
        )

    return normalized


def apply_filters(cards: List[NormalizedCard], filters: FilterSelection) -> List[NormalizedCard]:
    """
    Apply the manager's sidebar selections. Date range filtering is applied
    on the card creation date (consistent with how `trello_api` already
    scoped the fetch); the remaining filters are simple equality checks on
    cleaned dimensions.
    """
    out = []
    for c in cards:
        if c.creation_date is None:
            continue
        creation_date_only = c.creation_date.date()
        if creation_date_only < filters.start_date or creation_date_only > filters.end_date:
            continue
        if filters.studio and clean_dimension(c.studio, "") != clean_dimension(filters.studio, ""):
            continue
        if filters.client and c.client_clean != clean_dimension(filters.client, "unknown"):
            continue
        if filters.status and c.status_raw and clean_status(filters.status) != c.status_clean:
            continue
        if filters.agency and not any(m["agency"] == filters.agency for m in c.resolved_members):
            continue
        if filters.member and not any(
            m["canonical"].lower() == filters.member.lower() for m in c.resolved_members
        ):
            continue
        out.append(c)
    return out


def _init_bucket(members: List[str]) -> Dict[str, Any]:
    return {
        "total_cards": 0,
        "high_priority": 0,
        "by_client": defaultdict(int),
        "by_label": defaultdict(int),
        "high_priority_by_client": defaultdict(int),
        "delivery_days": [],
        "delivery_by_client": defaultdict(list),
        "by_member": {m: 0 for m in members},
        "by_label_by_member": defaultdict(int),
        "delivery_by_member": {m: [] for m in members},
    }


def compute_kpis(cards: List[NormalizedCard]) -> pd.DataFrame:
    """
    Aggregate normalized cards into the long-format KPI table
    (columns: agency, kpi, dimension, value), mirroring the JS
    "MAIN LOOP" + "OUTPUT" sections exactly.
    """
    agencies = {agency: _init_bucket(members) for agency, members in RESOURCES.items()}

    for card in cards:
        agencies_on_card = {m["agency"] for m in card.resolved_members}

        # ── CARD LEVEL ──
        for agency in agencies_on_card:
            b = agencies[agency]
            b["total_cards"] += 1
            b["by_client"][card.client_clean] += 1
            if card.is_high_priority:
                b["high_priority"] += 1
                b["high_priority_by_client"][card.client_clean] += 1
            for label in card.labels:
                b["by_label"][label] += 1
            if card.status_clean == "done" and card.delivery_days is not None:
                b["delivery_days"].append(card.delivery_days)
                b["delivery_by_client"][card.client_clean].append(card.delivery_days)

        # ── MEMBER LEVEL ──
        for m in card.resolved_members:
            b = agencies[m["agency"]]
            canonical = m["canonical"]
            b["by_member"][canonical] = b["by_member"].get(canonical, 0) + 1
            for label in card.labels:
                key = f"{label}\x00{canonical}"
                b["by_label_by_member"][key] += 1
            if card.status_clean == "done" and card.delivery_days is not None:
                b["delivery_by_member"].setdefault(canonical, []).append(card.delivery_days)

    rows: List[KPIRow] = []

    def push(agency: str, kpi: str, dimension: str, value: Any) -> None:
        rows.append(KPIRow(agency=agency, kpi=kpi, dimension=dimension, value=value))

    for agency, b in agencies.items():
        push(agency, "nbre de briefs", "", b["total_cards"])
        push(agency, "nbre de briefs Priorité haute", "", b["high_priority"])
        push(agency, "délai de livraison moyen", "", avg(b["delivery_days"]))

        for member, v in b["by_member"].items():
            push(agency, "nbre de briefs par ressource", member, v)

        for label, v in b["by_label"].items():
            push(agency, "nbre de briefs par type de livrable", label, v)

        for client, v in b["by_client"].items():
            push(agency, "nbre de briefs par client", client, v)

        for client, v in b["high_priority_by_client"].items():
            push(agency, "nbre de briefs Priorité haute par client", client, v)

        for key, v in b["by_label_by_member"].items():
            label, member = key.split("\x00")
            push(agency, "nbre de briefs par type de livrable par ressource", f"{label} / {member}", v)

        for member, arr in b["delivery_by_member"].items():
            push(agency, "délai de livraison par ressource", member, avg(arr))

        for client, arr in b["delivery_by_client"].items():
            push(agency, "délai de livraison par client", client, avg(arr))

    if not rows:
        return pd.DataFrame(columns=["agency", "kpi", "dimension", "value"])

    df = pd.DataFrame([r.__dict__ for r in rows])
    # `avg()` returns None for empty series. Once placed in a pandas column
    # this can silently become NaN, so check both explicitly and coerce to 0
    # for display, matching how the original sheet rendered blank cells.
    df["value"] = df["value"].apply(lambda v: 0 if v is None or v == "" or pd.isna(v) else v)
    return df
