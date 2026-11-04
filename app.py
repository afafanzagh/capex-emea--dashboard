"""
=====================================================================================
CONCENTRIX · EMEA PROCUREMENT & WORKPLACE STRATEGY
CapEx & Cost-Per-Seat (CPS) Tracker — Streamlit application (single file)
=====================================================================================
"""

from __future__ import annotations

import html
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ======================================================================================
# 0. PAGE CONFIG  (must be the first Streamlit call)
# ======================================================================================
st.set_page_config(
    page_title="Concentrix EMEA · CapEx & CPS Tracker",
    page_icon="🟦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ======================================================================================
# 1. CONSTANTS & CONFIGURATION
# ======================================================================================
DB_PATH = Path(os.getenv("CONCENTRIX_DB", "concentrix_emea.db"))
LOGO_PATH = Path("assets/logo.png")

# --- Brand palette ---
CANARY = "#00A4E4"
NAVY = "#002D62"
SLATE = "#1F2D3D"
LIGHT_BG = "#EAF6FC"
GREY = "#9AA5B1"
GREEN, AMBER, RED = "#2E9E5B", "#F2A900", "#D64545"

# --- Business rules ---
CPS_TARGET = 5000   # $/seat benchmark
CPS_BEST = 3500     # below = Best-in-Class

SPEND_LABELS = {
    "civil_works": "Civil Works",
    "cabling_elec_av": "Cabling, Electrical & AV",
    "hvac": "HVAC",
    "furniture": "Furniture",
    "security_cctv": "Security & CCTV",
}
SPEND_KEYS = list(SPEND_LABELS)
SPEND_COLORS = {
    "Civil Works": NAVY,
    "Cabling, Electrical & AV": CANARY,
    "HVAC": "#7FD1F2",
    "Furniture": "#6C7A89",
    "Security & CCTV": AMBER,
}

PROJECT_TYPES = ["Warm Shell", "Grey Shell"]
PROJECT_STATUSES = ["Approved", "Pending", "Rejected"]
REGIONS = ["French Region", "MET Region", "UK Region", "DACH", "MLH & NorBal", "Netherlands", "Other"]
COUNTRIES = sorted([
    "Albania", "Benin", "Bulgaria", "Egypt", "France", "Germany", "Ghana", "Greece", "Ireland",
    "Kosovo", "Latvia", "Madagascar", "Morocco", "Netherlands", "Nigeria", "Poland", "Portugal",
    "Romania", "Senegal", "South Africa", "Spain", "Suriname", "Tunisia", "Turkey", "United Kingdom",
])
SUPPLIER_CATEGORIES = ["Cabling/Electrical", "HVAC", "Civil Works", "Furniture", "Security/CCTV"]
SUPPLIER_TIERS = ["Strategic", "Tactical", "Backup"]
TIER_COLORS = {"Strategic": NAVY, "Tactical": CANARY, "Backup": GREY}
RAG_COLORS = {"Best-in-Class": GREEN, "On Target": AMBER, "Alert": RED}
RAG_ICONS = {"Best-in-Class": "🟢 Best-in-Class", "On Target": "🟡 On Target", "Alert": "🔴 Alert"}

ALLOWED_UPLOADS = ["pdf", "xlsx", "xls", "csv", "docx", "doc", "png", "jpg", "jpeg", "msg", "eml"]
MAX_UPLOAD_MB = 10

# ======================================================================================
# 2. SMALL HELPERS
# ======================================================================================
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def money(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:,.2f}M"
    if abs(v) >= 10_000:
        return f"${v / 1_000:,.0f}K"
    return f"${v:,.0f}"

def rag_status(cps: float) -> str:
    if cps < CPS_BEST:
        return "Best-in-Class"
    if cps <= CPS_TARGET:
        return "On Target"
    return "Alert"

def show_df(df: pd.DataFrame, **kw) -> None:
    try:
        st.dataframe(df, width="stretch", hide_index=True, **kw)
    except TypeError:
        st.dataframe(df, use_container_width=True, hide_index=True, **kw)

def show_fig(fig: go.Figure, height: int = 430) -> None:
    fig.update_layout(
        template="plotly_white",
        font=dict(family="Segoe UI, Arial, sans-serif", color=NAVY),
        height=height,
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="left", x=0),
        title=dict(font=dict(size=16, color=NAVY)),
    )
    try:
        st.plotly_chart(fig, width="stretch")
    except Exception:
        st.plotly_chart(fig, use_container_width=True)

# ======================================================================================
# 3. DATABASE LAYER
# ======================================================================================
PROJECT_FIELDS = [
    "country", "region", "project_name", "seats", "project_type",
    *SPEND_KEYS, "notes", "status",
]
SUPPLIER_FIELDS = ["name", "category", "tier", "market", "sla_score", "active", "notes"]

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country TEXT NOT NULL,
    region TEXT,
    project_name TEXT NOT NULL,
    seats INTEGER NOT NULL CHECK (seats > 0),
    project_type TEXT NOT NULL CHECK (project_type IN ('Warm Shell','Grey Shell')),
    civil_works REAL NOT NULL DEFAULT 0,
    cabling_elec_av REAL NOT NULL DEFAULT 0,
    hvac REAL NOT NULL DEFAULT 0,
    furniture REAL NOT NULL DEFAULT 0,
    security_cctv REAL NOT NULL DEFAULT 0,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'Pending',
    submitted_by TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    mime TEXT,
    size_bytes INTEGER,
    data BLOB NOT NULL,
    uploaded_by TEXT,
    uploaded_at TEXT
);
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    tier TEXT NOT NULL CHECK (tier IN ('Strategic','Tactical','Backup')),
    market TEXT,
    sla_score REAL NOT NULL DEFAULT 3 CHECK (sla_score BETWEEN 1 AND 5),
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);
"""

SEED_PROJECTS = [
    ("Madagascar", "French Region", "Madagascar – Main Hub", 950, "Grey Shell", 4_087_000, (34.3, 35.0, 11.6, 19.2)),
    ("Tunisia", "French Region", "Tunisia – Tunis Site", 601, "Warm Shell", 3_408_000, (41.0, 42.1, 3.0, 13.9)),
    ("Turkey", "MET Region", "Turkey – YDA Center", 820, "Warm Shell", 3_292_000, (22.2, 33.0, 28.5, 16.4)),
    ("Ghana", "UK Region", "Ghana – Site Expansion", 514, "Grey Shell", 1_395_000, (10.8, 31.6, 25.5, 32.2)),
    ("South Africa", "UK Region", "South Africa – Helix 7F", 420, "Grey Shell", 1_045_000, (39.6, 13.7, 18.1, 28.6)),
    ("Kosovo", "DACH", "Kosovo – Single Floor", 290, "Grey Shell", 973_000, (43.4, 25.5, 12.3, 18.8)),
    ("Portugal", "MLH & NorBal", "Portugal – Site 1", 414, "Warm Shell", 414 * 1772, (25, 35, 18, 22)),
    ("Latvia", "MLH & NorBal", "Latvia – Site 1", 85, "Warm Shell", 85 * 1920, (24, 36, 16, 24)),
    ("Suriname", "Netherlands", "Suriname – Site 1", 363, "Warm Shell", 363 * 1979, (26, 34, 18, 22)),
    ("Poland", "MLH & NorBal", "Poland – Site 1", 82, "Grey Shell", 82 * 5917, (36, 30, 14, 20)),
    ("United Kingdom", "UK Region", "UK – Site 1", 72, "Grey Shell", 72 * 9585, (34, 28, 16, 22)),
    ("France", "French Region", "France – MicroSite", 50, "Grey Shell", 50 * 14094, (38, 26, 14, 22)),
]

SEED_SUPPLIERS = [
    ("Neurone", "Cabling/Electrical", "Strategic", "MA", 4.5),
    ("Synapse", "Cabling/Electrical", "Strategic", "ALB", 4.2),
    ("Quantum Tech", "Cabling/Electrical", "Strategic", "BEN", 3.8),
    ("Moficlim", "HVAC", "Strategic", "MA", 4.6),
    ("STIM", "HVAC", "Strategic", "TUN", 4.0),
    ("Automatic Term SRL", "HVAC", "Strategic", "RO", 4.3),
    ("B.E.A.M", "Civil Works", "Strategic", "ALB", 4.1),
    ("OfficeWorks", "Civil Works", "Strategic", "UK/IE", 4.4),
    ("Giant Leap", "Civil Works", "Strategic", "ZA", 3.9),
    ("KBAC", "Civil Works", "Strategic", "MDG", 4.0),
    ("Dromeas", "Furniture", "Strategic", "GR/ALB", 4.2),
    ("Kinnarps", "Furniture", "Strategic", "Nordics", 4.7),
    ("Keceli", "Furniture", "Strategic", "TR/BEN", 3.7),
    ("BL Concept", "Furniture", "Strategic", "MA", 4.0),
    ("ART Engineering", "Cabling/Electrical", "Tactical", "RO", 3.6),
    ("East Coast ICT", "Cabling/Electrical", "Tactical", "ZA", 3.4),
    ("Adtech Media", "Cabling/Electrical", "Tactical", "GH", 3.1),
    ("SCI", "HVAC", "Tactical", "BEN", 3.3),
    ("HTO Romania", "HVAC", "Tactical", "RO", 3.8),
    ("Davinte", "Civil Works", "Tactical", "UK", 3.5),
    ("Thinkspace", "Civil Works", "Tactical", "ZA", 3.6),
    ("HTO", "Civil Works", "Tactical", "RO", 3.7),
    ("MAD", "Civil Works", "Tactical", "RO", 3.2),
    ("Trin Furniture", "Furniture", "Tactical", "ALB", 3.5),
    ("COS", "Furniture", "Tactical", "RO", 3.4),
    ("MDB Design", "Furniture", "Tactical", "RO", 3.6),
    ("ART Engineering", "Cabling/Electrical", "Backup", "RO", 3.6),
    ("ABEC Advanced", "Cabling/Electrical", "Backup", "ZA", 3.3),
    ("Sococlim", "HVAC", "Backup", "MA", 3.7),
    ("Eastlake", "Civil Works", "Backup", "UK", 2.8),
    ("Bidvest Protea Coin", "Security/CCTV", "Backup", "ZA", 4.0),
    ("Integrated Solutions", "Security/CCTV", "Backup", "ZA", 3.5),
]

def init_db() -> None:
    with db() as c:
        c.executescript(SCHEMA)
        if c.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
            ts = now_iso()
            for country, region, name, seats, ptype, total, pct in SEED_PROJECTS:
                s = sum(pct)
                civil, cab, hvac, furn = (total * p / s for p in pct)
                c.execute(
                    """INSERT INTO projects (country, region, project_name, seats, project_type,
                       civil_works, cabling_elec_av, hvac, furniture, security_cctv, notes, status,
                       submitted_by, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (country, region, name, seats, ptype, round(civil), round(cab * 0.85), round(hvac),
                     round(furn), round(cab * 0.15), "Seed data (illustrative)", "Approved",
                     "System (seed)", ts, ts),
                )
        if c.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0] == 0:
            ts = now_iso()
            c.executemany(
                """INSERT INTO suppliers (name, category, tier, market, sla_score, active, notes,
                   created_at, updated_at) VALUES (?,?,?,?,?,1,?,?,?)""",
                [(n, cat, t, m, s, "Seed data", ts, ts) for n, cat, t, m, s in SEED_SUPPLIERS],
            )

def load_projects(status: str | None = None) -> pd.DataFrame:
    q = ("SELECT p.*, (SELECT COUNT(*) FROM attachments a WHERE a.project_id = p.id) AS n_docs "
         "FROM projects p")
    params: list = []
    if status:
        q += " WHERE p.status = ?"
        params.append(status)
    with db() as c:
        return pd.read_sql_query(q + " ORDER BY p.id", c, params=params)

def insert_project(d: dict, submitted_by: str) -> int:
    ts = now_iso()
    cols = PROJECT_FIELDS + ["submitted_by", "created_at", "updated_at"]
    vals = [d[f] for f in PROJECT_FIELDS] + [submitted_by, ts, ts]
    with db() as c:
        cur = c.execute(
            f"INSERT INTO projects ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
        return cur.lastrowid

def update_project(pid: int, d: dict) -> None:
    sets = ", ".join(f"{f}=?" for f in PROJECT_FIELDS) + ", updated_at=?"
    with db() as c:
        c.execute(f"UPDATE projects SET {sets} WHERE id=?", [d[f] for f in PROJECT_FIELDS] + [now_iso(), pid])

def set_project_status(pid: int, status: str) -> None:
    with db() as c:
        c.execute("UPDATE projects SET status=?, updated_at=? WHERE id=?", (status, now_iso(), pid))

def delete_project(pid: int) -> None:
    with db() as c:
        c.execute("DELETE FROM projects WHERE id=?", (pid,))

def save_files(pid: int, files, user: str) -> int:
    n = 0
    for f in files or []:
        data = f.getvalue()
        if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            continue
        with db() as c:
            c.execute(
                "INSERT INTO attachments (project_id, filename, mime, size_bytes, data, uploaded_by, uploaded_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (pid, os.path.basename(f.name), f.type, len(data), data, user, now_iso()),
            )
        n += 1
    return n

def list_attachments(pid: int) -> pd.DataFrame:
    with db() as c:
        return pd.read_sql_query(
            "SELECT id, filename, mime, size_bytes, uploaded_by, uploaded_at FROM attachments "
            "WHERE project_id=? ORDER BY id", c, params=[pid])

def get_attachment_blob(aid: int) -> bytes:
    with db() as c:
        return c.execute("SELECT data FROM attachments WHERE id=?", (aid,)).fetchone()[0]

def delete_attachment(aid: int) -> None:
    with db() as c:
        c.execute("DELETE FROM attachments WHERE id=?", (aid,))

def load_suppliers() -> pd.DataFrame:
    with db() as c:
        df = pd.read_sql_query("SELECT * FROM suppliers ORDER BY id", c)
    df["active"] = df["active"].astype(bool)
    return df

def insert_supplier(d: dict) -> None:
    ts = now_iso()
    with db() as c:
        c.execute(
            "INSERT INTO suppliers (name, category, tier, market, sla_score, active, notes, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (d["name"], d["category"], d["tier"], d["market"], d["sla_score"], int(d["active"]), d["notes"], ts, ts))

def update_supplier(sid: int, d: dict) -> None:
    with db() as c:
        c.execute(
            "UPDATE suppliers SET name=?, category=?, tier=?, market=?, sla_score=?, active=?, notes=?, "
            "updated_at=? WHERE id=?",
            (d["name"], d["category"], d["tier"], d["market"], d["sla_score"], int(d["active"]), d["notes"],
             now_iso(), sid))

def delete_supplier(sid: int) -> None:
    with db() as c:
        c.execute("DELETE FROM suppliers WHERE id=?", (sid,))

# ======================================================================================
# 4. ANALYTICS HELPERS
# ======================================================================================
def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["total_capex"] = df[SPEND_KEYS].sum(axis=1)
    df["cps"] = df["total_capex"] / df["seats"]
    df["rag"] = df["cps"].apply(rag_status)
    df["label"] = df["country"] + " – " + df["project_name"]
    return df

def country_summary(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("country", as_index=False).agg(
        projects=("id", "count"), seats=("seats", "sum"), total_capex=("total_capex", "sum"),
        **{k: (k, "sum") for k in SPEND_KEYS})
    g["cps"] = g["total_capex"] / g["seats"]
    g["vs_target_pct"] = (g["cps"] / CPS_TARGET - 1) * 100
    g["rag"] = g["cps"].apply(rag_status)
    return g.sort_values("cps").reset_index(drop=True)

def spend_long(df: pd.DataFrame, by: str) -> pd.DataFrame:
    g = df.groupby(by, as_index=False)[SPEND_KEYS].sum()
    long = g.melt(id_vars=by, var_name="key", value_name="amount")
    long["Category"] = long["key"].map(SPEND_LABELS)
    long["share"] = long["amount"] / long.groupby(by)["amount"].transform("sum").replace(0, pd.NA) * 100
    long["share"] = long["share"].fillna(0).astype(float)
    return long

def build_excel(proj: pd.DataFrame, sup: pd.DataFrame) -> bytes:
    rename = {**SPEND_LABELS, "country": "Country", "region": "Region", "project_name": "Project",
              "seats": "Seats", "project_type": "Project Type", "total_capex": "Total CapEx ($)",
              "cps": "CPS ($/Seat)", "rag": "RAG", "status": "Status", "notes": "Notes",
              "submitted_by": "Submitted By"}
    cols = ["id", "country", "region", "project_name", "project_type", "seats", *SPEND_KEYS,
            "total_capex", "cps", "rag", "status", "submitted_by", "notes"]
    p = proj[cols].rename(columns={**rename, "id": "ID"})
    cs = country_summary(proj).rename(columns={**rename, "projects": "Projects", "vs_target_pct": "vs $5K target (%)"})
    kpi = pd.DataFrame({
        "KPI": ["Total CapEx ($)", "Total seats", "Weighted avg CPS ($/seat)", "CPS benchmark ($/seat)", "Projects"],
        "Value": [proj["total_capex"].sum(), proj["seats"].sum(),
                  proj["total_capex"].sum() / max(proj["seats"].sum(), 1), CPS_TARGET, len(proj)],
    })
    s = sup.drop(columns=["created_at", "updated_at"], errors="ignore").rename(columns={
        "name": "Supplier", "category": "Category", "tier": "Tier", "market": "Market",
        "sla_score": "SLA Score", "active": "Active", "notes": "Notes", "id": "ID"})
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        kpi.to_excel(xw, sheet_name="Summary", index=False)
        p.to_excel(xw, sheet_name="Projects", index=False)
        cs.to_excel(xw, sheet_name="CPS by Country", index=False)
        s.to_excel(xw, sheet_name="Suppliers", index=False)
        for ws in xw.sheets.values():
            for col in ws.columns:
                width = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 45)
    return buf.getvalue()

# ======================================================================================
# 5. UI & STYLING
# ======================================================================================
def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{ background:#F6FAFD; }}
        .block-container {{ padding-top: 1.2rem; max-width: 1400px; }}
        [data-testid="stSidebar"] {{ background:{LIGHT_BG}; border-right:3px solid {CANARY}; }}
        h1,h2,h3,h4 {{ color:{NAVY}; }}
        .cx-banner {{ background:linear-gradient(100deg,{NAVY} 0%,#00457F 55%,{CANARY} 100%);
            border-radius:14px; padding:18px 26px; margin-bottom:18px; display:flex;
            align-items:center; justify-content:space-between; color:#fff; }}
        .cx-logo {{ font-size:2rem; font-weight:800; letter-spacing:-1px; color:#fff; line-height:1; }}
        .cx-logo .dot {{ color:{CANARY}; background:#fff; border-radius:50%; display:inline-block;
            width:.5em; height:.5em; margin-left:3px; }}
        .cx-sub {{ font-size:.82rem; letter-spacing:.14em; text-transform:uppercase; opacity:.9; margin-top:6px; }}
        .cx-title {{ font-size:1.25rem; font-weight:600; text-align:right; }}
        .cx-title small {{ display:block; font-weight:400; opacity:.85; font-size:.8rem; }}
        .kpi {{ background:#fff; border-radius:12px; padding:16px 18px; border-left:6px solid {CANARY};
            box-shadow:0 2px 8px rgba(0,45,98,.08); height:100%; }}
        .kpi-t {{ font-size:.78rem; text-transform:uppercase; letter-spacing:.08em; color:#4A5B6D; font-weight:600; }}
        .kpi-v {{ font-size:1.9rem; font-weight:800; color:{NAVY}; line-height:1.2; }}
        .kpi-s {{ font-size:.82rem; color:#4A5B6D; }}
        div.stButton > button, div.stFormSubmitButton > button, div.stDownloadButton > button {{
            background:{NAVY}; color:#fff !important; border:none; border-radius:8px; font-weight:600; }}
        div.stButton > button p, div.stFormSubmitButton > button p, div.stDownloadButton > button p {{ color:#fff !important; }}
        div.stButton > button:hover, div.stFormSubmitButton > button:hover, div.stDownloadButton > button:hover {{
            background:{CANARY}; color:{NAVY} !important; }}
        div.stButton > button:hover p, div.stFormSubmitButton > button:hover p,
        div.stDownloadButton > button:hover p {{ color:{NAVY} !important; }}
        .stTabs [data-baseweb="tab-list"] {{ gap:6px; }}
        .stTabs [data-baseweb="tab"] {{ background:#fff; border-radius:8px 8px 0 0; padding:8px 18px;
            color:{NAVY}; font-weight:600; }}
        .stTabs [aria-selected="true"] {{ background:{CANARY}; color:{NAVY}; }}
        div[data-testid="stForm"] {{ background:#fff; border:1px solid #D6E6F2; border-radius:12px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_header(subtitle: str = "EMEA Procurement & Workplace Strategy") -> None:
    if LOGO_PATH.exists():
        c1, c2 = st.columns([1, 4])
        c1.image(str(LOGO_PATH), width=190)
        c2.markdown(f"<h2 style='margin:0'>{html.escape(subtitle)}</h2>", unsafe_allow_html=True)
        return
    st.markdown(
        f"""<div class="cx-banner">
             <div><div class="cx-logo">concentrix<span class="dot"></span></div>
                  <div class="cx-sub">{html.escape(subtitle)}</div></div>
             <div class="cx-title">CapEx &amp; Cost-Per-Seat Tracker
                  <small>Annual CapEx Review · FY2025 · USD</small></div>
         </div>""",
        unsafe_allow_html=True,
    )

def kpi_card(title: str, value: str, sub: str = "", accent: str = CANARY) -> None:
    st.markdown(
        f'<div class="kpi" style="border-left-color:{accent}"><div class="kpi-t">{title}</div>'
        f'<div class="kpi-v">{value}</div><div class="kpi-s">{sub}</div></div>',
        unsafe_allow_html=True,
    )

# ======================================================================================
# 6. SHARED FORMS & MODALS
# ======================================================================================
def project_form(form_key: str, d: dict | None = None, submit_label: str = "Save",
                 allow_status: bool = False, clear: bool = False):
    d = d or {}
    with st.form(form_key, clear_on_submit=clear):
        c1, c2, c3 = st.columns(3)
        c_opts = ["Select…"] + COUNTRIES
        cur_country = d.get("country")
        c_idx = c_opts.index(cur_country) if cur_country in c_opts else 0
        country_sel = c1.selectbox("Country *", c_opts, index=c_idx)
        other = c1.text_input("Other country (if not listed)",
                              value=cur_country if cur_country and cur_country not in c_opts else "")
        cur_region = d.get("region")
        r_idx = REGIONS.index(cur_region) if cur_region in REGIONS else 0
        region = c1.selectbox("Region", REGIONS, index=r_idx)

        name = c2.text_input("Project name / Site *", value=d.get("project_name", ""))
        seats = c2.number_input("Number of seats *", min_value=1, step=1, value=int(d.get("seats", 100)))
        ptype = c2.selectbox("Project type *", PROJECT_TYPES,
                             index=PROJECT_TYPES.index(d.get("project_type", "Warm Shell")))
        notes = c3.text_area("Notes / assumptions", value=d.get("notes") or "", height=190)

        st.markdown("**Spend categories (USD $)**")
        cols = st.columns(5)
        spend = {}
        for col, key in zip(cols, SPEND_KEYS):
            spend[key] = col.number_input(SPEND_LABELS[key], min_value=0.0, step=1000.0, format="%.0f",
                                         value=float(d.get(key, 0.0)))
        status = d.get("status", "Pending")
        if allow_status:
            status = st.selectbox("Status", PROJECT_STATUSES, index=PROJECT_STATUSES.index(status))
        files = st.file_uploader(
            f"📎 Attach supporting quotes / PDFs / Excel (max {MAX_UPLOAD_MB} MB each)",
            type=ALLOWED_UPLOADS, accept_multiple_files=True)
        submitted = st.form_submit_button(submit_label)

    data = {
        "country": (other.strip() or (country_sel if country_sel != "Select…" else "")),
        "region": region, "project_name": name.strip(), "seats": int(seats), "project_type": ptype,
        **{k: float(v) for k, v in spend.items()}, "notes": notes.strip(), "status": status,
    }
    return submitted, data, files

def validate_project(d: dict) -> list[str]:
    errs = []
    if not d["country"]:
        errs.append("Please select (or type) a country.")
    if not d["project_name"]:
        errs.append("Project name / site is required.")
    if d["seats"] < 1:
        errs.append("Number of seats must be at least 1.")
    if sum(d[k] for k in SPEND_KEYS) <= 0:
        errs.append("Enter at least one spend category greater than 0.")
    return errs

def project_result_msg(d: dict) -> str:
    total = sum(d[k] for k in SPEND_KEYS)
    cps = total / d["seats"]
    return f"Total CapEx {money(total)} · CPS ${cps:,.0f}/seat · {RAG_ICONS[rag_status(cps)]}"

def supplier_form(form_key: str, d: dict | None = None, label: str = "Save supplier", clear: bool = False):
    d = d or {}
    with st.form(form_key, clear_on_submit=clear):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Supplier name *", value=d.get("name", ""))
        market = c1.text_input("Market / country code", value=d.get("market") or "")
        category = c2.selectbox("Category *", SUPPLIER_CATEGORIES,
                                index=SUPPLIER_CATEGORIES.index(d.get("category", SUPPLIER_CATEGORIES[0])))
        tier = c2.selectbox("Marketplace Tier *", SUPPLIER_TIERS,
                            index=SUPPLIER_TIERS.index(d.get("tier", "Strategic")))
        score = c3.number_input("SLA Score (1.0 - 5.0)", min_value=1.0, max_value=5.0, step=0.1,
                                value=float(d.get("sla_score", 4.0)))
        active = c3.checkbox("Active supplier", value=bool(d.get("active", True)))
        notes = st.text_area("Notes", value=d.get("notes") or "")
        submitted = st.form_submit_button(label)
    data = {
        "name": name.strip(), "category": category, "tier": tier, "market": market.strip(),
        "sla_score": float(score), "active": int(active), "notes": notes.strip()
    }
    return submitted, data

# ======================================================================================
# 7. MAIN APP VIEWS
# ======================================================================================
def main() -> None:
    init_db()
    inject_css()

    # Sidebar: Role switcher (Direct access without email/password)
    st.sidebar.markdown("### 🟦 Concentrix Navigation")
    role = st.sidebar.radio("Select Role Mode", ["Requester", "Admin"], index=0)
    st.sidebar.markdown(f"**Current Mode:** `{role}`")
    st.sidebar.divider()

    st.sidebar.markdown("### 📌 Views")
    menu_options = ["Dashboard & KPIs", "Submit New Project", "Suppliers Database"]
    if role == "Admin":
        menu_options.insert(1, "Manage Projects & Approvals")
    
    choice = st.sidebar.radio("Navigation", menu_options)
    st.sidebar.divider()
    st.sidebar.info("💡 **Tip:** Use the filters on each page to refine country, project type, or spend analysis.")

    # Load Data
    proj_all = enrich(load_projects())
    sup_df = load_suppliers()

    # ----------------------------------------------------------------------------------
    # VIEW 1: DASHBOARD & KPIS
    # ----------------------------------------------------------------------------------
    if choice == "Dashboard & KPIs":
        render_header("EMEA Workplace Strategy & CapEx Intelligence")
        
        # Approved projects only for official dashboard
        df_appr = proj_all[proj_all["status"] == "Approved"]
        
        if df_appr.empty:
            st.warning("⚠️ No approved projects available in the database yet. Switch to Admin mode to approve pending projects.")
            return

        # Sidebar Filters
        st.sidebar.markdown("### 🔍 Global Filters")
        sel_countries = st.sidebar.multiselect("Countries", sorted(df_appr["country"].unique()), default=[])
        sel_types = st.sidebar.multiselect("Project Type", PROJECT_TYPES, default=[])
        sel_regions = st.sidebar.multiselect("Regions", sorted(df_appr["region"].dropna().unique()), default=[])

        df_f = df_appr.copy()
        if sel_countries:
            df_f = df_f[df_f["country"].isin(sel_countries)]
        if sel_types:
            df_f = df_f[df_f["project_type"].isin(sel_types)]
        if sel_regions:
            df_f = df_f[df_f["region"].isin(sel_regions)]

        if df_f.empty:
            st.error("No projects match the selected filter criteria.")
            return

        # Top KPI Cards
        tot_capex = df_f["total_capex"].sum()
        tot_seats = int(df_f["seats"].sum())
        w_cps = tot_capex / max(tot_seats, 1)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            kpi_card("Total CapEx", money(tot_capex), f"{len(df_f)} projects evaluated")
        with c2:
            kpi_card("Total Seats Delivered", f"{tot_seats:,}", "EMEA Portfolio")
        with c3:
            kpi_card("Weighted Avg CPS", f"${w_cps:,.0f}", f"Target: ≤ ${CPS_TARGET:,}", 
                     accent=GREEN if w_cps <= CPS_TARGET else RED)
        with c4:
            kpi_card("CPS Benchmark", f"${CPS_TARGET:,}", "Standard Target", accent=NAVY)

        st.markdown("<br>", unsafe_allow_html=True)

        # Tabs for analytics
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Cost Per Seat (CPS)", "🏗️ Spend Breakdown", "🌍 Marketplace Analysis", "📥 Export & Reports"])

        with tab1:
            st.subheader("Cost Per Seat (CPS) by Country & RAG Status")
            cs = country_summary(df_f)
            
            fig_cps = px.bar(
                cs, x="country", y="cps", color="rag",
                color_discrete_map={"Best-in-Class": GREEN, "On Target": AMBER, "Alert": RED},
                text=cs["cps"].apply(lambda v: f"${v:,.0f}"),
                labels={"country": "Country", "cps": "CPS ($ / Seat)"},
                title="Cost Per Seat vs. Target ($5,000 Benchmark)"
            )
            fig_cps.add_hline(y=CPS_TARGET, line_dash="dash", line_color=RED, annotation_text="Target $5,000")
            fig_cps.update_traces(textposition="outside")
            show_fig(fig_cps)

            st.markdown("### Country Summary Data Table")
            show_df(cs[["country", "projects", "seats", "total_capex", "cps", "rag"]])

        with tab2:
            st.subheader("CapEx Spend Category Breakdown")
            long_s = spend_long(df_f, "country")
            fig_spend = px.bar(
                long_s, x="country", y="amount", color="Category",
                color_discrete_map=SPEND_COLORS,
                labels={"country": "Country", "amount": "Spend ($)", "Category": "Spend Category"},
                title="Spend Distribution by Category & Country"
            )
            show_fig(fig_spend)

            st.markdown("### Spend Category Percentage Share")
            fig_pct = px.bar(
                long_s, x="country", y="share", color="Category",
                color_discrete_map=SPEND_COLORS, barmode="stack",
                labels={"country": "Country", "share": "Share (%)", "Category": "Spend Category"},
                title="Relative Spend Share (%) by Country"
            )
            show_fig(fig_pct)

        with tab3:
            st.subheader("Supplier Marketplace & Vendor Strategy")
            if sup_df.empty:
                st.info("No suppliers recorded in database.")
            else:
                sc1, sc2 = st.columns(2)
                with sc1:
                    fig_tier = px.pie(
                        sup_df, names="tier", color="tier",
                        color_discrete_map=TIER_COLORS,
                        title="Supplier Breakdown by Strategic Tier"
                    )
                    show_fig(fig_tier, height=350)
                with sc2:
                    fig_cat = px.bar(
                        sup_df, x="category", color="tier",
                        color_discrete_map=TIER_COLORS,
                        title="Suppliers by Technical Category & Tier"
                    )
                    show_fig(fig_cat, height=350)

                st.markdown("### Active Supplier Directory")
                show_df(sup_df)

        with tab4:
            st.subheader("Export Reports & Data")
            st.markdown("Download complete analytics, project details, and vendor databases formatted for executive reporting.")
            excel_data = build_excel(df_f, sup_df)
            st.download_button(
                label="📥 Download Full Executive Excel Report",
                data=excel_data,
                file_name=f"Concentrix_EMEA_CapEx_Tracker_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    # ----------------------------------------------------------------------------------
    # VIEW 2: SUBMIT NEW PROJECT
    # ----------------------------------------------------------------------------------
    elif choice == "Submit New Project":
        render_header("Project Submission & Cost Intake")
        st.markdown("Submit a new country project with detailed seat count, shell specification, and spend category breakdown.")

        submitted, data, files = project_form("submit_proj", submit_label="Submit Project for Approval", clear=True)
        if submitted:
            errs = validate_project(data)
            if errs:
                for e in errs:
                    st.error(f"❌ {e}")
            else:
                pid = insert_project(data, submitted_by=f"{role} User")
                if files:
                    save_files(pid, files, user=f"{role} User")
                st.success(f"✅ Project successfully submitted for approval! {project_result_msg(data)}")

    # ----------------------------------------------------------------------------------
    # VIEW 3: MANAGE PROJECTS & APPROVALS (Admin only)
    # ----------------------------------------------------------------------------------
    elif choice == "Manage Projects & Approvals":
        render_header("Project Management & Approvals Dashboard")
        
        all_p = load_projects()
        if all_p.empty:
            st.info("No projects found in database.")
        else:
            status_filter = st.selectbox("Filter by Status", ["All", "Pending", "Approved", "Rejected"])
            filtered_p = all_p if status_filter == "All" else all_p[all_p["status"] == status_filter]

            for _, row in filtered_p.iterrows():
                pid = int(row["id"])
                with st.expander(f"[{row['status']}] {row['country']} — {row['project_name']} ({row['seats']} seats, {money(row[SPEND_KEYS].sum())})"):
                    col1, col2, col3 = st.columns(3)
                    col1.markdown(f"**Region:** {row['region']}")
                    col1.markdown(f"**Type:** {row['project_type']}")
                    col1.markdown(f"**Submitted By:** {row.get('submitted_by', 'N/A')}")
                    
                    total_s = sum(row[k] for k in SPEND_KEYS)
                    cps_val = total_s / max(row["seats"], 1)
                    col2.markdown(f"**Total CapEx:** {money(total_s)}")
                    col2.markdown(f"**CPS:** ${cps_val:,.0f}/seat")
                    col2.markdown(f"**RAG Status:** {rag_status(cps_val)}")

                    # Action buttons
                    bc1, bc2, bc3 = col3.columns(3)
                    if bc1.button("✅ Approve", key=f"app_{pid}"):
                        set_project_status(pid, "Approved")
                        st.success("Project approved!")
                        st.rerun()
                    if bc2.button("⏳ Pending", key=f"pend_{pid}"):
                        set_project_status(pid, "Pending")
                        st.rerun()
                    if bc3.button("❌ Reject", key=f"rej_{pid}"):
                        set_project_status(pid, "Rejected")
                        st.rerun()

                    # Attached documents
                    docs = list_attachments(pid)
                    if not docs.empty:
                        st.markdown("**Attached Files:**")
                        for _, doc in docs.iterrows():
                            aid = int(doc["id"])
                            blob = get_attachment_blob(aid)
                            st.download_button(f"📥 {doc['filename']}", data=blob, file_name=doc['filename'], key=f"dl_{aid}")

                    # Edit Form expander
                    with st.form(f"edit_form_{pid}"):
                        st.markdown("### Edit Project Details")
                        sub_e, edit_data, new_files = project_form(f"inner_edit_{pid}", d=row.to_dict(), submit_label="Update Project", allow_status=True)
                        if sub_e:
                            update_project(pid, edit_data)
                            if new_files:
                                save_files(pid, new_files, user=f"{role} User")
                            st.success("Project updated successfully!")
                            st.rerun()

                    if st.button("🗑️ Delete Project", key=f"del_{pid}"):
                        delete_project(pid)
                        st.warning("Project deleted.")
                        st.rerun()

    # ----------------------------------------------------------------------------------
    # VIEW 4: SUPPLIERS DATABASE
    # ----------------------------------------------------------------------------------
    elif choice == "Suppliers Database":
        render_header("Supplier Marketplace & Strategy Database")
        st.markdown("Manage supplier tiers (`Strategic`, `Tactical`, `Backup`), SLA scores, and market allocations.")

        if role == "Admin":
            with st.expander("➕ Add New Supplier"):
                sub_sup, sup_data = supplier_form("new_supplier", label="Add Supplier", clear=True)
                if sub_sup:
                    if not sup_data["name"]:
                        st.error("Supplier name is required.")
                    else:
                        insert_supplier(sup_data)
                        st.success(f"Supplier '{sup_data['name']}' added successfully!")
                        st.rerun()

        sup_df = load_suppliers()
        if sup_df.empty:
            st.info("No suppliers found.")
        else:
            cat_filter = st.selectbox("Filter by Category", ["All"] + SUPPLIER_CATEGORIES)
            df_s_filtered = sup_df if cat_filter == "All" else sup_df[sup_df["category"] == cat_filter]
            show_df(df_s_filtered)

            if role == "Admin":
                st.markdown("### Edit / Remove Suppliers")
                sup_to_edit = st.selectbox("Select Supplier to Edit", sup_df["name"].tolist())
                if sup_to_edit:
                    row_s = sup_df[sup_df["name"] == sup_to_edit].iloc[0]
                    sid = int(row_s["id"])
                    with st.form(f"edit_sup_{sid}"):
                        sub_upd, upd_data = supplier_form(f"form_upd_{sid}", d=row_s.to_dict(), label="Update Supplier")
                        if sub_upd:
                            update_supplier(sid, upd_data)
                            st.success("Supplier updated!")
                            st.rerun()
                    if st.button("🗑️ Delete Supplier", key=f"del_sup_{sid}"):
                        delete_supplier(sid)
                        st.warning("Supplier deleted.")
                        st.rerun()

if __name__ == "__main__":
    main()
   
   
