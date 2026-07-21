"""
app.py
======
Traffic Studio KPI Dashboard — now fully live.

Manager picks a date range (+ optional filters) -> the app calls the Trello
API directly, maps + cleans the cards in Python (ports of the original
n8n JavaScript), computes the same KPIs as before, and renders them with
the same layout/graphs/filters/navigation as the previous Google-Sheets
powered dashboard. No n8n, no Google Sheets, no intermediate storage.
"""

from __future__ import annotations

import base64
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import RESOURCES
from models import FilterSelection
from services.kpis import apply_filters, build_normalized_cards, compute_kpis
from services.mapper import map_cards_to_dataframe
from services.trello_api import TrelloAPIError, cached_fetch_cards_in_range

# ── BRAND ASSET (logo only — everything else below is unchanged) ──
APP_DIR = Path(__file__).parent


@st.cache_data(show_spinner=False)
def _load_logo_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _first_existing_logo_b64() -> str:
    # Prefer a transparent-background variant (looks better on the dark
    # sidebar) if present, otherwise fall back to the plain logo file.
    for name in ("klem_group_logo_transparent.png", "klem_group_logo.png"):
        p = APP_DIR / name
        if p.exists():
            return _load_logo_b64(str(p))
    return ""


_LOGO_B64 = _first_existing_logo_b64()

# ── PAGE CONFIG ───────────────────────────────────────────────
st.set_page_config(
    page_title="Traffic Studio · KPIs",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── STYLES (unchanged from the original dashboard) ────────────
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;600;700&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif !important;
    background-color: #0D1117 !important;
    color: #C9D1D9 !important;
}
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 2.5rem 4rem !important; max-width: 100% !important; }
section[data-testid="stSidebar"] {
    background: #161B22 !important;
    border-right: 1px solid #21262D !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] h4,
section[data-testid="stSidebar"] h5,
section[data-testid="stSidebar"] h6,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] .stMarkdown {
    color: #FFFFFF !important;
    opacity: 1 !important;
}
section[data-testid="stSidebar"] div[data-testid="stWidgetLabel"] > label {
    color: #FFFFFF !important;
    font-weight: 700 !important;
    opacity: 1 !important;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label {
    color: #FFFFFF !important;
    opacity: 1 !important;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label p {
    color: #FFFFFF !important;
    font-weight: 600 !important;
    opacity: 1 !important;
}
.page-title {
    font-size: 3rem; font-weight: 800;
    background: linear-gradient(135deg, #58A6FF 0%, #BC8CFF 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.metric-card {
    background: #161B22;
    border: 1px solid #21262D;
    border-radius: 12px;
    padding: 1.4rem 1.6rem;
}
.metric-label {
    font-size: 0.9rem;
    font-weight: 700;
    text-transform: uppercase;
    color: #8B949E;
}
.metric-value {
    font-size: 3.4rem;
    font-weight: 800;
    font-family: 'DM Mono', monospace;
    color: #FFFFFF;
}
.metric-sub {
    font-size: 0.85rem;
    color: #8B949E;
    margin-top: 0.2rem;
}
.section-title {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #8B949E;
    margin: 2.5rem 0 1rem 0;
    border-bottom: 1px solid #21262D;
    padding-bottom: 0.4rem;
}
div[data-testid="stPlotlyChart"] {
    background: #FFFFFF !important;
    border: 1px solid #D0D7DE !important;
    border-radius: 14px !important;
    padding: 10px 10px 4px 10px !important;
    box-shadow: 5px 6px 0px rgba(0, 0, 0, 0.65) !important;
}
.sidebar-logo {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 0.6rem;
}
.sidebar-logo img {
    height: 34px;
    width: auto;
}
</style>
""",
    unsafe_allow_html=True,
)

# ── CHART THEME (unchanged) ───────────────────────────────────
CHART_LAYOUT = dict(
    paper_bgcolor="#FFFFFF",
    plot_bgcolor="#FFFFFF",
    font=dict(family="DM Sans", color="#111111", size=12),
    margin=dict(l=20, r=20, t=40, b=20),
    legend=dict(bgcolor="#FFFFFF", bordercolor="#D0D7DE", borderwidth=1, font=dict(color="#111111")),
    xaxis=dict(gridcolor="#E5E7EB", zerolinecolor="#D0D7DE", linecolor="#B8C0CC",
               tickfont=dict(color="#111111"), title_font=dict(color="#111111")),
    yaxis=dict(gridcolor="#E5E7EB", zerolinecolor="#D0D7DE", linecolor="#B8C0CC",
               tickfont=dict(color="#111111"), title_font=dict(color="#111111")),
)

USER_COLOR_LIST = [
    '#F0E442', '#A0D468', '#4FC1E9', '#FFCEE4', '#1A2B5C', '#87CEFA', '#E9D700',
    '#FF8C00', '#BF5FFF', '#FF6347', '#3CB371', '#DDA0DD', '#CFA616', '#00BFFF',
    '#DAA520', '#6A5ACD',
]
EXTRA_COLORS = [
    '#20B2AA', '#FF6B6B', '#7B68EE', '#40E0D0', '#8A2BE2', '#FFB347', '#66CDAA',
    '#4682B4', '#FF69B4', '#B22222', '#228B22', '#4169E1', '#D2691E', '#9ACD32',
    '#9932CC', '#00CED1', '#C71585', '#5F9EA0', '#B8860B', '#DC143C', '#6B8E23',
    '#708090', '#FF7F50', '#2E8B57', '#00FA9A',
]
EXTENDED_MULTICOLOR = USER_COLOR_LIST + EXTRA_COLORS
NO_DATA_MESSAGE = "No data for this selection."

# ── PASSWORD ──────────────────────────────────────────────────
with st.sidebar:
    if _LOGO_B64:
        st.markdown(
            f'<div class="sidebar-logo"><img src="data:image/png;base64,{_LOGO_B64}" alt="KLEM Group" /></div>',
            unsafe_allow_html=True,
        )
    st.markdown("### Traffic Studio")
    password = st.text_input("🔒 Password", type="password")
    if password != st.secrets.get("DASHBOARD_PASSWORD", "Rahma_KLEM@"):
        st.warning("Please enter the password to access the dashboard.")
        st.stop()

# ── HELPERS ────────────────────────────────────────────────────
def show_no_data(message: str = NO_DATA_MESSAGE) -> None:
    st.info(message)


def hex_to_rgb(hex_color: str):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def generate_shades(base_color: str, n: int):
    if n <= 1:
        return [base_color]
    base_rgb = hex_to_rgb(base_color)
    shades = []
    for i in range(n):
        factor = 0.35 + (i / max(1, n - 1)) * 0.55
        r = int(base_rgb[0] * factor + 255 * (1 - factor) * 0.10)
        g = int(base_rgb[1] * factor + 255 * (1 - factor) * 0.10)
        b = int(base_rgb[2] * factor + 255 * (1 - factor) * 0.10)
        shades.append(rgb_to_hex((min(r, 255), min(g, 255), min(b, 255))))
    return shades


def category_color_map(values, palette=None):
    palette = palette or EXTENDED_MULTICOLOR
    vals = [str(v) if pd.notna(v) else "—" for v in pd.Series(values).tolist()]
    ordered = list(dict.fromkeys(vals))
    return {v: palette[i % len(palette)] for i, v in enumerate(ordered)}


def monochrome_color_map(values, base_color="#58A6FF"):
    vals = [str(v) if pd.notna(v) else "—" for v in pd.Series(values).tolist()]
    ordered = list(dict.fromkeys(vals))
    shades = generate_shades(base_color, len(ordered))
    return {v: shades[i] for i, v in enumerate(ordered)}


def scale_marker_sizes(series, min_size=10, max_size=24):
    s = pd.to_numeric(series, errors="coerce").fillna(0)
    if s.empty:
        return pd.Series([], dtype=float)
    s_min, s_max = s.min(), s.max()
    if s_max == s_min:
        return pd.Series([(min_size + max_size) / 2] * len(s), index=s.index)
    return min_size + (s - s_min) * (max_size - min_size) / (s_max - s_min)


def apply_figure_style(fig, height=None, showlegend=None, xaxis_tickangle=None):
    fig.update_layout(**CHART_LAYOUT)
    if height is not None:
        fig.update_layout(height=height)
    if showlegend is not None:
        fig.update_layout(showlegend=showlegend)
    if xaxis_tickangle is not None:
        fig.update_xaxes(tickangle=xaxis_tickangle)
    try:
        fig.update_traces(marker_line_width=0)
    except Exception:
        pass
    return fig


def safe_plot(data: pd.DataFrame, required_cols: list, plot_builder, empty_message=NO_DATA_MESSAGE):
    if data is None or data.empty or not all(c in data.columns for c in required_cols):
        show_no_data(empty_message)
        return
    try:
        fig = plot_builder(data.copy())
        if fig is None:
            show_no_data(empty_message)
            return
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        show_no_data(empty_message)


def safe_display_table(t: pd.DataFrame, empty_message=NO_DATA_MESSAGE):
    if t is None or t.empty:
        show_no_data(empty_message)
    else:
        st.dataframe(t, use_container_width=True, hide_index=True)


def build_delay_arrow_stripplot(data, category_col, value_col="Valeur", value_label="Délai moyen (jours)"):
    d = data.copy()
    if d.empty or category_col not in d.columns or value_col not in d.columns:
        return None
    d[category_col] = d[category_col].fillna("—").astype(str)
    d[value_col] = pd.to_numeric(d[value_col], errors="coerce").fillna(0)
    d = d.sort_values(value_col, ascending=True).reset_index(drop=True)

    cmap = category_color_map(d[category_col], EXTENDED_MULTICOLOR)
    d["marker_size"] = scale_marker_sizes(d[value_col], min_size=10, max_size=24)

    fig = go.Figure()
    max_val = float(d[value_col].max()) if not d.empty else 1.0
    arrow_len = max(max_val * 0.08, 0.6)

    for _, row in d.iterrows():
        fig.add_shape(type="line", x0=0, x1=row[value_col], y0=row[category_col], y1=row[category_col],
                      xref="x", yref="y", line=dict(color="#D8DEE8", width=2))

    for _, row in d.iterrows():
        start_x = max(row[value_col] - arrow_len, 0)
        fig.add_annotation(x=row[value_col], y=row[category_col], xref="x", yref="y",
                            ax=start_x, ay=row[category_col], axref="x", ayref="y",
                            text="", showarrow=True, arrowhead=3, arrowsize=1.15,
                            arrowwidth=2.6, arrowcolor=cmap[row[category_col]])

    fig.add_trace(go.Scatter(
        x=d[value_col], y=d[category_col], mode="markers+text",
        text=[f"{v:.0f}j" if float(v).is_integer() else f"{v:.1f}j" for v in d[value_col]],
        textposition="middle right", textfont=dict(color="#111111", size=11),
        marker=dict(size=d["marker_size"], color=[cmap[v] for v in d[category_col]],
                    line=dict(color="#FFFFFF", width=1.8), opacity=0.95),
        hovertemplate=f"{category_col}: %{{y}}<br>{value_label}: %{{x}}j<extra></extra>",
        showlegend=False,
    ))

    mean_val = d[value_col].mean()
    if pd.notna(mean_val):
        fig.add_vline(x=mean_val, line_dash="dash", line_color="#555555",
                      annotation_text=f"Moy. {mean_val:.1f}j", annotation_position="top")

    fig.update_layout(**CHART_LAYOUT, height=max(360, len(d) * 48), showlegend=False)
    fig.update_xaxes(title=value_label, rangemode="tozero", range=[0, max_val * 1.22 if max_val > 0 else 1])
    fig.update_yaxes(title=None, categoryorder="array", categoryarray=d[category_col].tolist())
    return fig


def split_dimension_column(data: pd.DataFrame, source_col="dimension", into=("Type", "Ressource"), sep=" / "):
    out = data.copy()
    for col in into:
        if col not in out.columns:
            out[col] = "—"
    if out.empty or source_col not in out.columns:
        return out
    parts = out[source_col].fillna("—").astype(str).str.split(sep, n=1, expand=True)
    if parts.shape[1] == 1:
        out[into[0]] = parts[0].fillna("—")
        out[into[1]] = "—"
    else:
        out[into[0]] = parts[0].fillna("—")
        out[into[1]] = parts[1].fillna("—").replace("", "—")
    out[into[0]] = out[into[0]].replace("", "—").fillna("—")
    return out


# ── SIDEBAR FILTERS ────────────────────────────────────────────
ALL_MEMBERS = sorted(m for members in RESOURCES.values() for m in members)

with st.sidebar:
    st.markdown("---")
    today = date.today()
    default_start = today - timedelta(days=7)

    start_date = st.date_input("📅 Start Date", value=default_start)
    end_date = st.date_input("📅 End Date", value=today)

    agencies_opt = ["All", "klem", "id36"]
    selected_agency = st.selectbox("🏢 Agency", agencies_opt)

    with st.expander("More filters (optional)"):
        selected_studio = st.selectbox("Studio", ["All", "studio klem", "studio id36"])
        selected_client = st.text_input("Client (exact name)", value="")
        selected_member = st.selectbox("Member", ["All"] + ALL_MEMBERS)
        selected_status = st.selectbox(
            "Status", ["All", "To do", "In progress", "Done", "In review", "Approved", "Not sure"]
        )

    st.markdown("---")
    view_mode = st.radio("📊 Display", ["Charts only", "Tables only"])

    if start_date > end_date:
        st.error("Start Date must be before End Date.")
        st.stop()

# ── LIVE FETCH + PIPELINE ─────────────────────────────────────
filters = FilterSelection(
    start_date=start_date,
    end_date=end_date,
    studio=None if selected_studio == "All" else selected_studio,
    client=None if not selected_client.strip() else selected_client.strip(),
    agency=None if selected_agency == "All" else selected_agency,
    member=None if selected_member == "All" else selected_member,
    status=None if selected_status == "All" else selected_status,
)

start_dt = datetime.combine(filters.start_date, datetime.min.time())
end_dt = datetime.combine(filters.end_date, datetime.max.time())

try:
    raw_cards = cached_fetch_cards_in_range(start_dt.isoformat(), end_dt.isoformat())
except TrelloAPIError as exc:
    st.error(f"Trello API error: {exc}")
    st.stop()

flat_df = map_cards_to_dataframe(raw_cards)
normalized_cards = build_normalized_cards(flat_df)
filtered_cards = apply_filters(normalized_cards, filters)
kpi_df = compute_kpis(filtered_cards)

kpi_df = kpi_df if not kpi_df.empty else pd.DataFrame(columns=["agency", "kpi", "dimension", "value"])

if filters.agency:
    scoped_kpi_df = kpi_df[kpi_df["agency"] == filters.agency]
else:
    scoped_kpi_df = kpi_df

# ── KPI HELPERS (operate on scoped_kpi_df instead of Google Sheet) ────
def get_kpi_rows(kpi: str) -> pd.DataFrame:
    r = scoped_kpi_df[scoped_kpi_df["kpi"] == kpi].copy()
    if r.empty:
        return pd.DataFrame(columns=["agency", "dimension", "value"])
    r["dimension"] = r["dimension"].fillna("—").astype(str).replace("", "—")
    r["value"] = pd.to_numeric(r["value"], errors="coerce").fillna(0)
    return r[["agency", "dimension", "value"]]


def get_val(kpi: str) -> int:
    r = get_kpi_rows(kpi)
    return int(r["value"].sum()) if not r.empty else 0


def get_table(kpi: str, rename_cols=None) -> pd.DataFrame:
    rename_cols = rename_cols or {}
    detail_label = rename_cols.get("Détail", "Détail")
    final_columns = ["Agence", detail_label, "Valeur"]

    r = get_kpi_rows(kpi)
    if r.empty:
        return pd.DataFrame(columns=final_columns)

    r = r.groupby("dimension", as_index=False, dropna=False)["value"].sum()
    r["Agence"] = filters.agency if filters.agency else "All"
    r = r[["Agence", "dimension", "value"]]
    r["value"] = pd.to_numeric(r["value"], errors="coerce").fillna(0).round().astype(int)
    r = r.rename(columns={"dimension": "Détail", "value": "Valeur"})
    r = r.rename(columns=rename_cols)

    for col in final_columns:
        if col not in r.columns:
            r[col] = 0 if col == "Valeur" else "—"

    return r[final_columns].sort_values("Valeur", ascending=False).reset_index(drop=True)


def show_table(kpi, rename_cols=None):
    safe_display_table(get_table(kpi, rename_cols or {}))


show_charts = view_mode == "Charts only"
show_tables = view_mode == "Tables only"

# ── HEADER ────────────────────────────────────────────────────
st.markdown('<div class="page-title">📊 KPI Dashboard</div>', unsafe_allow_html=True)
st.markdown(
    f"**Period:** {start_date} → {end_date} &nbsp;&nbsp;|&nbsp;&nbsp; "
    f"**Agency:** {selected_agency} &nbsp;&nbsp;|&nbsp;&nbsp; "
    f"**Cards loaded:** {len(raw_cards)}"
)

# ── METRIC CARDS ──────────────────────────────────────────────
total = get_val("nbre de briefs")
prio = get_val("nbre de briefs Priorité haute")
delay = get_val("délai de livraison moyen")
members_count = len(get_table("nbre de briefs par ressource", {"Détail": "Ressource"}))
pct = f"{round((prio / total) * 100)}%" if total else "—"

cols = st.columns(4)


def card(col, label, value, sub):
    col.markdown(
        f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-sub">{sub}</div>
    </div>
    """,
        unsafe_allow_html=True,
    )


card(cols[0], "Total Briefs", total, "cards in range")
card(cols[1], "Priorité Haute", prio, pct)
card(cols[2], "Délai Moyen", delay, "days")
card(cols[3], "Ressources actives", members_count, "members")

# ══════════════════════════════════════════════════════════════
# SECTION 1 — Briefs par Ressource
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">Briefs par Ressource</div>', unsafe_allow_html=True)
if show_charts:
    t = get_table("nbre de briefs par ressource", {"Détail": "Ressource"})
    safe_plot(t, ["Ressource", "Valeur"], lambda d: apply_figure_style(
        px.bar(d.sort_values("Valeur"), x="Valeur", y="Ressource", orientation="h", color="Ressource",
               color_discrete_map=monochrome_color_map(d["Ressource"], base_color="#7FB9FF"),
               labels={"Valeur": "Nombre de briefs", "Ressource": "Ressource"}),
        height=max(300, len(d) * 45), showlegend=False))
if show_tables:
    show_table("nbre de briefs par ressource", {"Détail": "Ressource"})

# ══════════════════════════════════════════════════════════════
# SECTION 2 — Briefs par Type de Livrable
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">Briefs par Type de Livrable</div>', unsafe_allow_html=True)
if show_charts:
    t = get_table("nbre de briefs par type de livrable", {"Détail": "Type de Livrable"})
    safe_plot(t, ["Type de Livrable", "Valeur"], lambda d: apply_figure_style(
        px.bar(d.sort_values("Type de Livrable"), x="Valeur", y="Type de Livrable", orientation="h",
               color="Type de Livrable",
               color_discrete_map=monochrome_color_map(d["Type de Livrable"], base_color="#E6B3FF"),
               labels={"Valeur": "Nombre de briefs", "Type de Livrable": "Type de livrable"}),
        height=max(300, len(d) * 45), showlegend=False))
if show_tables:
    show_table("nbre de briefs par type de livrable", {"Détail": "Type de Livrable"})

# ══════════════════════════════════════════════════════════════
# SECTION 3 — Briefs par Client
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">Briefs par Client</div>', unsafe_allow_html=True)
if show_charts:
    t = get_table("nbre de briefs par client", {"Détail": "Client"})
    safe_plot(t, ["Client", "Valeur"], lambda d: apply_figure_style(
        px.bar(d.sort_values("Client"), x="Client", y="Valeur", color="Client",
               color_discrete_map=monochrome_color_map(d["Client"], base_color="#99FF99"),
               labels={"Valeur": "Nombre de briefs", "Client": "Client"}),
        height=400, showlegend=False, xaxis_tickangle=-35))
if show_tables:
    show_table("nbre de briefs par client", {"Détail": "Client"})

# ══════════════════════════════════════════════════════════════
# SECTION 4 — Priorité Haute par Client
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">Priorité Haute par Client</div>', unsafe_allow_html=True)
if show_charts:
    t = get_table("nbre de briefs Priorité haute par client", {"Détail": "Client"})

    def build_priority_donut(d):
        total_prio = int(d["Valeur"].sum()) if not d.empty else 0
        fig = px.pie(d.sort_values("Valeur", ascending=False), names="Client", values="Valeur", color="Client",
                     color_discrete_map=monochrome_color_map(d["Client"], base_color="#FFC180"), hole=0.68)
        fig.update_traces(textinfo="percent+label", textfont=dict(color="#111111"),
                           hovertemplate="Client: %{label}<br>Priorité haute: %{value}<extra></extra>")
        fig.update_layout(**CHART_LAYOUT, height=430, showlegend=True,
                           annotations=[dict(text=f"<b>{total_prio}</b><br>briefs", x=0.5, y=0.5,
                                              font=dict(size=18, color="#111111"), showarrow=False)])
        return fig

    safe_plot(t, ["Client", "Valeur"], build_priority_donut)
if show_tables:
    show_table("nbre de briefs Priorité haute par client", {"Détail": "Client"})

# ══════════════════════════════════════════════════════════════
# SECTION 5 — Type de Livrable × Ressource
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">Type de Livrable × Ressource</div>', unsafe_allow_html=True)
if show_charts:
    raw = get_kpi_rows("nbre de briefs par type de livrable par ressource")
    raw = split_dimension_column(raw, source_col="dimension", into=("Type", "Ressource"), sep=" / ")
    if not raw.empty and all(c in raw.columns for c in ["Type", "Ressource", "value"]):
        pivot = raw.groupby(["Ressource", "Type"], as_index=False, dropna=False)["value"].sum()
        pivot["value"] = pd.to_numeric(pivot["value"], errors="coerce").fillna(0).round().astype(int)
        safe_plot(pivot, ["Ressource", "Type", "value"], lambda d: apply_figure_style(
            px.bar(d.sort_values("value", ascending=False), x="Ressource", y="value", color="Type",
                   color_discrete_map=category_color_map(d["Type"], EXTENDED_MULTICOLOR),
                   labels={"value": "Nombre de briefs", "Type": "Type de livrable", "Ressource": "Ressource"},
                   barmode="stack"),
            height=440, xaxis_tickangle=-30))
    else:
        show_no_data()
if show_tables:
    t = get_table("nbre de briefs par type de livrable par ressource")
    if not t.empty:
        t2 = split_dimension_column(t, source_col="Détail", into=("Type", "Ressource"), sep=" / ")
        for col in ["Agence", "Type", "Ressource", "Valeur"]:
            if col not in t2.columns:
                t2[col] = 0 if col == "Valeur" else "—"
        safe_display_table(t2[["Agence", "Type", "Ressource", "Valeur"]])
    else:
        show_no_data()

# ══════════════════════════════════════════════════════════════
# SECTION 6 — Délai de Livraison par Ressource
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">Délai de Livraison par Ressource</div>', unsafe_allow_html=True)
if show_charts:
    t = get_table("délai de livraison par ressource", {"Détail": "Ressource"})
    safe_plot(t, ["Ressource", "Valeur"], lambda d: build_delay_arrow_stripplot(
        d, category_col="Ressource", value_col="Valeur", value_label="Délai moyen (jours)"))
if show_tables:
    show_table("délai de livraison par ressource", {"Détail": "Ressource"})

# ══════════════════════════════════════════════════════════════
# SECTION 7 — Délai de Livraison par Client
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">Délai de Livraison par Client</div>', unsafe_allow_html=True)
if show_charts:
    t = get_table("délai de livraison par client", {"Détail": "Client"})
    safe_plot(t, ["Client", "Valeur"], lambda d: build_delay_arrow_stripplot(
        d, category_col="Client", value_col="Valeur", value_label="Délai moyen (jours)"))
if show_tables:
    show_table("délai de livraison par client", {"Détail": "Client"})
