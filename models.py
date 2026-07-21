"""
models.py
=========
Typed data structures shared across the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


@dataclass
class FilterSelection:
    """Filters chosen by the manager in the Streamlit sidebar."""

    start_date: date
    end_date: date
    studio: Optional[str] = None
    client: Optional[str] = None
    agency: Optional[str] = None
    member: Optional[str] = None
    status: Optional[str] = None


@dataclass
class NormalizedCard:
    """A single Trello card after mapping + cleaning, ready for KPI computation."""

    card_id: str
    name: str
    url: str
    labels: List[str] = field(default_factory=list)
    members_raw: List[str] = field(default_factory=list)
    resolved_members: List[Dict[str, str]] = field(default_factory=list)  # [{canonical, agency}]
    archived: bool = False
    status_raw: str = ""
    status_clean: str = "other"
    priority_raw: str = ""
    priority_haute_flag: bool = False
    is_high_priority: bool = False
    client_raw: str = ""
    client_clean: str = "unknown"
    studio: str = ""
    agence_commanditaire: str = ""
    devis_mm_valide: Any = ""
    date_livraison_interne: Any = ""
    demandeur: str = ""
    last_activity_date: Optional[datetime] = None
    creation_date: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    delivery_days: Optional[int] = None


@dataclass
class KPIRow:
    """One row of the long-format KPI table consumed by the dashboard."""

    agency: str
    kpi: str
    dimension: str
    value: Any
