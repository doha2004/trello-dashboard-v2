# Traffic Studio KPI Dashboard — Live Trello Edition

Fully live version of the dashboard. No n8n, no Google Sheets, no
intermediate storage. On every dashboard load / filter change, the app:

```
Manager opens Streamlit
        ↓
Picks Start Date / End Date (+ optional Studio, Client, Agency, Member, Status)
        ↓
Python calls the Trello REST API directly (services/trello_api.py)
        ↓
Fetches only the cards relevant to the date range (paginated, early-exit)
        ↓
Maps custom fields -> flat rows (services/mapper.py)
        ↓
Cleans & normalizes -> NormalizedCard objects (services/kpis.py + services/cleaning.py)
        ↓
Computes KPIs in Python (services/kpis.py)
        ↓
Renders the same layout/graphs/tables as before (app.py)
```

## Project structure

```
dashboard/
├── app.py                     # Streamlit UI (same layout/graphs/filters as before)
├── config.py                  # Credentials, custom-field maps, option maps, roster
├── models.py                  # FilterSelection, NormalizedCard, KPIRow dataclasses
├── services/
│   ├── trello_api.py          # Trello REST client + windowed fetch + caching
│   ├── mapper.py               # Raw Trello JSON -> flat DataFrame
│   ├── cleaning.py             # Member resolution, creation/delivery date logic
│   ├── kpis.py                  # Normalization + KPI aggregation (the JS "MAIN LOOP" ported)
│   └── utils.py                 # Text normalization primitives (accents, keys, booleans...)
├── requirements.txt
└── .streamlit/secrets.toml.example
```

## Setup

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Get Trello credentials:
   - API key: https://trello.com/app-key
   - Token: generate from the same page (click "Token" link), authorizing
     read access to the board.
   - Board id: open the board, add `.json` to the URL, or use
     `GET /1/members/me/boards` to list your boards' ids.

3. Copy the secrets template and fill it in:
   ```bash
   mkdir -p .streamlit
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```
   Edit `.streamlit/secrets.toml`:
   ```toml
   TRELLO_API_KEY = "..."
   TRELLO_TOKEN = "..."
   TRELLO_BOARD_ID = "..."
   DASHBOARD_PASSWORD = "..."
   ```
   `secrets.toml` is already covered by the usual `.gitignore` conventions —
   never commit it.

4. Run:
   ```bash
   streamlit run app.py
   ```

## What was preserved from the original dashboard

- Layout, color palette, metric cards, section order and titles.
- All chart types (horizontal bars, stacked bars, donut, arrow strip plots).
- All KPI formulas and dimensions (per resource, per client, per label,
  priority, delivery time).
- The "Charts only / Tables only" toggle and Agency selector.

## What changed

- The `Week` selectbox became `Start Date` / `End Date` date pickers (the
  KPIs are no longer snapshots written once a week — they're computed live
  for the exact window you choose).
- New optional filters: Studio, Client, Member, Status (all filter the
  underlying cards before KPIs are aggregated; Agency continues to work as
  before).
- Data source: Google Sheets → direct Trello REST calls, cached in-memory
  by Streamlit (`st.cache_data`, 5 minute TTL) instead of persisted anywhere.

## Business logic ported 1:1 from the original JavaScript

| JS function | Python equivalent | Behavior |
|---|---|---|
| `cleanText` | `services/utils.clean_text` | Strip accents, lowercase, strip emoji/punctuation, collapse whitespace |
| `toKey` | `services/utils.to_key` | `cleanText` + strip digits/spaces (used for fuzzy member matching) |
| `cleanBoolean` | `services/utils.clean_boolean` | true/1/yes/oui → True |
| `cleanPriority` | `services/utils.clean_priority` | high/highest/urgent → "high" |
| `cleanStatus` | `services/utils.clean_status` | done/completed/approved/termine/archive → "done" |
| `cleanDimension` | `services/utils.clean_dimension` | cleaned text or fallback |
| `resolveMember` | `services/cleaning.resolve_member` | Exact key match, then longest-key-first substring fallback |
| `getCreationDate` | `services/cleaning.get_creation_date` | First 4 bytes of Trello card id → Unix timestamp |
| `getDeliveryDate` | `services/cleaning.get_delivery_date` | Archived or Done/Approved → Last Activity Date |
| `daysBetween` / `avg` | `services/utils.days_between` / `avg` | Same rounding/negative-guard behavior |
| "MAIN LOOP" (card+member level buckets) | `services/kpis.compute_kpis` | Same bucket structure, same KPI names/dimensions |

All of the above were smoke-tested against synthetic Trello payloads to
confirm identical outputs to the JS logic (accent stripping, fuzzy member
matching, status/priority classification, delivery-day math).

## Trello API limitations & workaround

Trello's public REST API has two hard constraints relevant here:

1. **No server-side filtering by custom field value or by card-creation
   date.** Custom fields aren't queryable, and "creation date" only exists
   implicitly, embedded in the first 4 bytes of the Mongo-style card id.
2. **A single list call caps out at 1000 cards** (`limit` param, max 1000).

Workaround implemented in `services/trello_api.py`:

- A single endpoint (`/boards/{id}/cards/all` with `filter=all`) already
  returns full card payloads (custom fields, members, attachments,
  checklists) in one shot — no need for a separate lightweight pass +
  per-card batch calls.
- Cards are paginated **backwards** using Trello's `before` cursor (results
  are returned newest-id-first). For each page, the app decodes each card's
  creation date from its id and **stops paginating as soon as it has moved
  entirely past the requested start date** — so a dashboard load for "last
  7 days" does not walk the entire board history, even on large boards.
- `end_date` is applied client-side (Trello has no upper-bound-by-id
  filter), by skipping cards newer than the window while continuing to
  paginate for older matches.
- The whole windowed fetch is wrapped in `st.cache_data(ttl=300)` keyed on
  the (start_date, end_date) ISO strings — so changing only the optional
  filters (Studio/Client/Member/Status/Agency) re-uses the cached raw
  fetch and re-runs only the (cheap, in-memory) Python cleaning/KPI step,
  with zero extra Trello API calls.

If the board grows extremely large and even the windowed pagination becomes
slow, the next optimization step would be a lightweight incremental sync
(store only `id` + `dateLastActivity` somewhere and diff), but that
re-introduces persistent storage, which was explicitly out of scope here.

## Notes on rate limits

Trello enforces per-key and per-token rate limits (roughly 100
requests/10s per key, 300/10s per token at time of writing — verify current
limits in Trello's developer docs, as these can change). The pagination
strategy above keeps calls proportional to the size of the selected date
window, not the size of the whole board, which keeps normal usage well
under these limits.
