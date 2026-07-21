"""
config.py
=========
Central configuration for the Trello-powered Streamlit dashboard.

Holds:
- Trello credentials (loaded from Streamlit secrets / environment)
- Board id
- Custom field id -> name mapping
- Option id -> text mapping (for list-type custom fields)
- Agency roster (source of truth for member -> agency resolution)

Nothing here performs I/O except reading Streamlit secrets, so this module
is safe to import from anywhere.
"""

from __future__ import annotations

import os
from typing import Dict, List

try:
    import streamlit as st
    _SECRETS = st.secrets
except Exception:  # pragma: no cover - allows import outside Streamlit runtime
    _SECRETS = {}


def _get_secret(name: str, default: str = "") -> str:
    """Read a value from Streamlit secrets first, then environment variables.

    Falls back gracefully (instead of raising) when no secrets.toml exists
    yet, e.g. during local scripting/testing outside `streamlit run`.
    """
    try:
        if name in _SECRETS:
            return str(_SECRETS[name])
    except Exception:
        pass
    return os.environ.get(name, default)


# ── TRELLO CREDENTIALS ────────────────────────────────────────────────
# Store these in .streamlit/secrets.toml as:
#   TRELLO_API_KEY = "..."
#   TRELLO_TOKEN = "..."
#   TRELLO_BOARD_ID = "..."
TRELLO_API_KEY: str = _get_secret("TRELLO_API_KEY")
TRELLO_TOKEN: str = _get_secret("TRELLO_TOKEN")
TRELLO_BOARD_ID: str = _get_secret("TRELLO_BOARD_ID")

TRELLO_BASE_URL = "https://api.trello.com/1"

# ── CUSTOM FIELD ID -> NAME MAPPING ───────────────────────────────────
CUSTOM_FIELD_MAP: Dict[str, str] = {
    "68b1894909255d09242ba86b": "STUDIO",
    "686e79492274732bf52f5446": "Priorité Haute",
    "686e86d2d74eb4db7e1333d9": "Brief incomplet",
    "686e783a3563305a06e98e23": "Agence commanditaire",
    "686e836fc8ea665cc9cf7739": "Client",
    "686e77987fe385eabf9019f9": "Status",
    "686e86023355f62c1ae8f1e6": "Devis MM validé",
    "686e8b67e9f0e2f3486e1138": "Date de livraison interne",
    "686f79086abd90a2bf88c26a": "Demandeur (AM / SMM)",
    "698f545d3a23c8072050f05d": "Priority",
}

# ── OPTION ID -> TEXT MAPPING (list-type custom fields) ───────────────
OPTION_MAP: Dict[str, str] = {
    # STUDIO
    "68b1894909255d09242ba86c": "studio id36",
    "68b1894909255d09242ba86d": "studio klem",
    # Agence commanditaire
    "686e783a3563305a06e98e24": "KLEM Group",
    "686e783a3563305a06e98e25": "klem",
    "686e783a3563305a06e98e26": "id36",
    "686e783a3563305a06e98e27": "1896",
    # Status
    "686e77987fe385eabf9019fa": "To do",
    "686e77987fe385eabf9019fb": "In progress",
    "686e77987fe385eabf9019fc": "Done",
    "686e77987fe385eabf9019fd": "In review",
    "686e77987fe385eabf9019fe": "Approved",
    "686e77987fe385eabf9019ff": "Not sure",
    # Priority
    "698f545d3a23c8072050f05e": "Highest",
    "698f545d3a23c8072050f05f": "High",
    "698f545d3a23c8072050f060": "Medium",
    "698f545d3a23c8072050f061": "Low",
    "698f545d3a23c8072050f062": "Lowest",
    "698f545d3a23c8072050f063": "Not sure",
    # Client
    "686e85b371569a11a14f7299": "_avant-vente",
    "686e85bf27668b2d565e1879": "_interne",
    "686e84adac3ab0378942bb29": "ALLIANCES",
    "686e837e8b4dea7cbf96db86": "BEL",
    "6877c4dfccd1fade5a143f9d": "CAF",
    "686e849e934c98a1c5568c14": "CARREFOUR",
    "686e83eea3880948f930551d": "IKEA",
    "686e8430ecaa3792574309e1": "LDA - Boutiques",
    "686e841a42ce2f04a2fcee3a": "LDA - Chergui",
    "686e840c9f6261ba3030f851": "LDA - Corp",
    "686e8437419e1227263f9690": "LDA - Domex",
    "686e842727695b6cb4cdd415": "LDA - Paysager",
    "686e83852a7191f2c92ebdbb": "LEMO - Ecomm",
    "686e838eb161555716a8d3f3": "LEMO - Sidi Ali",
    "686e8397d6ed16f4b8b19cee": "LEMO - Aïn Atlas",
    "686e83b816fe3fe42f6b9201": "LEMO - Oulmès",
    "686e83a7a991f4bf9e1e220f": "LEMO - Purifya",
    "686e83b11189958806f56128": "LEMO - Vitalya",
    "686e847862633f544d7f53cc": "MASTERCARD",
    "686e83ffb8397c6c0c140fa5": "MDJS",
    "686e84c264c3c76ebf012773": "ONDA",
    "686e84c647cda1fc30790c4d": "ONMT",
    "686e83f701c0427fea672cab": "SISAL",
    "686e84882f965679cc53ff97": "SMEIA",
    "686e846d89bb6c8eccd071b5": "TMP",
    "686e9821493d8cf27df9e442": "TMG",
    "686e9824a8b57a8723f727e1": "AEZO",
    "686e982986edc9a5e58c0638": "APTF",
    "687e204f307d537b027a834f": "LEMO CORP",
}

# ── AGENCY ROSTER — SOURCE OF TRUTH ───────────────────────────────────
RESOURCES: Dict[str, List[str]] = {
    "id36": [
        "Amajid Ayoub",
        "Hicham Cherkaoui",
        "Mossaab Ajgoun",
        "Salah Eddine Mardas",
        "Amine Zouhri",
    ],
    "klem": [
        "Abdelaziz Lyassar",
        "Abdellah Khdim",
        "Abdessamad Chemsi",
        "Ahmed Kaabouri",
        "Amine Griouani",
        "Amine Khdim",
        "El Moumni Mohamed",
        "Mohamed Cherkaoui",
        "Ouakour Abdessamad",
    ],
}

# Fields requested from Trello for each card
CARD_FIELDS = [
    "id",
    "name",
    "desc",
    "url",
    "shortUrl",
    "labels",
    "idList",
    "idBoard",
    "closed",
    "due",
    "dueComplete",
    "start",
    "dateLastActivity",
    "badges",
]

CARD_QUERY_PARAMS = {
    "members": "true",
    "member_fields": "fullName,username",
    "customFieldItems": "true",
    "attachments": "true",
    "checklists": "all",
    "fields": ",".join(CARD_FIELDS),
    "filter": "all",  # open + archived (closed) cards
}
