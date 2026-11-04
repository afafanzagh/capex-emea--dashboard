"""
=====================================================================================
CONCENTRIX · EMEA PROCUREMENT & WORKPLACE STRATEGY
CapEx & Cost-Per-Seat (CPS) Tracker  —  Streamlit application (single file)
=====================================================================================
 
HOW TO RUN LOCALLY
------------------
1. Create / activate a virtual environment (optional but recommended):
       python -m venv .venv && source .venv/bin/activate      (Windows: .venv\\Scripts\\activate)
2. Install dependencies:
       pip install "streamlit>=1.50" pandas plotly openpyxl
3. Start the app:
       streamlit run app.py
4. Open http://localhost:8501
 
DEFAULT CREDENTIALS (change them before sharing the app!)
---------------------------------------------------------
   Admin     : password  ->  admin123
   Requester : access code -> country2025
Override with environment variables ADMIN_PASSWORD / REQUESTER_CODE, or with
.streamlit/secrets.toml:
       ADMIN_PASSWORD = "a-strong-password"
       REQUESTER_CODE = "a-shared-code"
 
OPTIONAL
--------
* Drop your official logo at ./assets/logo.png and it replaces the built-in wordmark.
* Data lives in ./concentrix_emea.db (SQLite). Override the path with CONCENTRIX_DB.
* On first launch a .streamlit/config.toml with the Canary Blue theme is created
  (applies from the next restart).
 
WORKFLOW
--------
Requester  -> submits a project via the form (status = Pending).
Admin      -> reviews in "Approvals", approves/rejects; manages projects, suppliers,
              documents and exports. Only *Approved* projects feed the dashboard.
 
NOTE: seed data is ILLUSTRATIVE, derived from the FY2025 EMEA review deck
(a subset of countries). Cabling / Security split of the deck's combined
"Cabling (Elec/Sec/AV)" lot (85/15) and supplier SLA scores are assumptions —
replace them with actual figures.
"""
 
from __future__ import annotations
 
import hmac
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
 
 
def _secret(name: str, default: str) -> str:
    """Read a credential from st.secrets, then env vars, then fall back to a default."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.getenv(name, default)
 
 
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
 
 
def money(v: float) -> str:
    """Compact currency format: $26.8M / $973K / $4,598."""
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
 
 
def sla_rag(score: float) -> str:
    if score >= 4:
        return "🟢 Green"
    if score >= 3:
        return "🟡 Amber"
    return "🔴 Red"
 
 
def flash(kind: str, msg: str) -> None:
    """Queue a message to display after the next rerun."""
    st.session_state["flash"] = (kind, msg)
 
 
def show_flash() -> None:
    item = st.session_state.pop("flash", None)
    if item:
        kind, msg = item
        getattr(st, kind)(msg)
 
 
def show_df(df: pd.DataFrame, **kw) -> None:
    """Render a dataframe full width (compatible with old and new Streamlit APIs)."""
    try:
        st.dataframe(df, width="stretch", hide_index=True, **kw)
    except TypeError:
        st.dataframe(df, use_container_width=True, hide_index=True, **kw)
 
 
def show_fig(fig: go.Figure, height: int = 430) -> None:
    """Apply the corporate chart style and render full width."""
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
 
 
def ensure_theme_config() -> None:
    """Create a Canary Blue Streamlit theme file on first run (applies at next restart)."""
    cfg = Path(".streamlit/config.toml")
    if cfg.exists():
        return
    try:
        cfg.parent.mkdir(exist_ok=True)
        cfg.write_text(
            '[theme]\nprimaryColor = "#00A4E4"\nbackgroundColor = "#FFFFFF"\n'
            'secondaryBackgroundColor = "#EAF6FC"\ntextColor = "#002D62"\nfont = "sans serif"\n'
        )
    except OSError:
        pass
 
 
# ======================================================================================
# 3. DATABASE LAYER (SQLite — persistent across sessions)
# ======================================================================================
PROJECT_FIELDS = [
    "country", "region", "project_name", "seats", "project_type",
    *SPEND_KEYS, "notes", "status",
]
SUPPLIER_FIELDS = ["name", "category", "tier", "market", "sla_score", "active", "notes"]
 
 
@contextmanager
def db():
    """Open a connection, commit on success, roll back on error, always close."""
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
 
# (country, region, project, seats, type, total $, (civil %, cabling %, hvac %, furniture %))
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
 
# (name, category, tier, market, SLA score — illustrative)
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
    """Create tables and seed initial mock data on first run."""
    with db() as c:
        c.executescript(SCHEMA)
        if c.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
            ts = now_iso()
            for country, region, name, seats, ptype, total, pct in SEED_PROJECTS:
                s = sum(pct)
                civil, cab, hvac, furn = (total * p / s for p in pct)
                # Deck groups Cabling/Elec/Sec/AV in one lot -> assume 85% cabling / 15% security
                c.execute(
                    """INSERT INTO projects (country, region, project_name, seats, project_type,
                       civil_works, cabling_elec_av, hvac, furniture, security_cctv, notes, status,
                       submitted_by, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (country, region, name, seats, ptype, round(civil), round(cab * 0.85), round(hvac),
                     round(furn), round(cab * 0.15), "Seed data (illustrative, FY2025 review)", "Approved",
                     "System (seed)", ts, ts),
                )
        if c.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0] == 0:
            ts = now_iso()
            c.executemany(
                """INSERT INTO suppliers (name, category, tier, market, sla_score, active, notes,
                   created_at, updated_at) VALUES (?,?,?,?,?,1,?,?,?)""",
                [(n, cat, t, m, s, "Seed data (SLA score illustrative)", ts, ts)
                 for n, cat, t, m, s in SEED_SUPPLIERS],
            )
 
 
# ---------- Projects CRUD ----------
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
    with db() as c:  # attachments are removed via ON DELETE CASCADE
        c.execute("DELETE FROM projects WHERE id=?", (pid,))
 
 
# ---------- Attachments ----------
def save_files(pid: int, files, user: str) -> int:
    """Persist uploaded files linked to a project. Returns number saved."""
    n = 0
    for f in files or []:
        data = f.getvalue()
        if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            st.warning(f"⚠️ '{f.name}' exceeds {MAX_UPLOAD_MB} MB and was skipped.")
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
 
 
# ---------- Suppliers CRUD ----------
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
    """Add total CapEx, CPS, RAG status and a display label to a projects DataFrame."""
    df = df.copy()
    df["total_capex"] = df[SPEND_KEYS].sum(axis=1)
    df["cps"] = df["total_capex"] / df["seats"]
    df["rag"] = df["cps"].apply(rag_status)
    df["label"] = df["country"] + " – " + df["project_name"]
    return df
 
 
def country_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate by country: seats, CapEx, weighted CPS (sum capex / sum seats) and spend mix."""
    g = df.groupby("country", as_index=False).agg(
        projects=("id", "count"), seats=("seats", "sum"), total_capex=("total_capex", "sum"),
        **{k: (k, "sum") for k in SPEND_KEYS})
    g["cps"] = g["total_capex"] / g["seats"]
    g["vs_target_pct"] = (g["cps"] / CPS_TARGET - 1) * 100
    g["rag"] = g["cps"].apply(rag_status)
    return g.sort_values("cps").reset_index(drop=True)
 
 
def spend_long(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """Return long-format spend per group (project label or country) incl. % share."""
    g = df.groupby(by, as_index=False)[SPEND_KEYS].sum()
    long = g.melt(id_vars=by, var_name="key", value_name="amount")
    long["Category"] = long["key"].map(SPEND_LABELS)
    long["share"] = long["amount"] / long.groupby(by)["amount"].transform("sum").replace(0, pd.NA) * 100
    long["share"] = long["share"].fillna(0).astype(float)
    return long
 
 
def build_excel(proj: pd.DataFrame, sup: pd.DataFrame) -> bytes:
    """Excel workbook: KPIs, projects, CPS by country, spend mix, suppliers."""
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
        for ws in xw.sheets.values():  # simple column auto-width
            for col in ws.columns:
                width = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 45)
    return buf.getvalue()
 
 
# ======================================================================================
# 5. UI: STYLING & BRANDING
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
# 6. AUTHENTICATION (simple RBAC)
# ======================================================================================
def login_screen() -> None:
    render_header()
    ADMIN_PW = _secret("ADMIN_PASSWORD", "admin123")
    REQ_CODE = _secret("REQUESTER_CODE", "country2025")
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        st.markdown("### 🔐 Sign in")
        with st.form("login"):
            role = st.radio("Access profile", ["Requester", "Admin"], horizontal=True,
                            help="Requester: submit project data. Admin: full management.")
            name = st.text_input("Your name / e-mail")
            secret = st.text_input("Password / access code", type="password")
            go_btn = st.form_submit_button("Sign in")
        if go_btn:
            attempts = st.session_state.get("attempts", 0)
            if attempts >= 5:
                st.error("Too many failed attempts. Reload the page to try again.")
            elif not name.strip():
                st.error("Please enter your name.")
            else:
                expected = ADMIN_PW if role == "Admin" else REQ_CODE
                if hmac.compare_digest(secret.encode(), expected.encode()):
                    st.session_state.update(role=role, user=name.strip(), attempts=0)
                    st.rerun()
                else:
                    st.session_state["attempts"] = attempts + 1
                    st.error("Invalid credentials.")
        if ADMIN_PW == "admin123" or REQ_CODE == "country2025":
            st.info("ℹ️ Default demo credentials are active — set ADMIN_PASSWORD / REQUESTER_CODE "
                    "before sharing this app.")
 
 
def sidebar_user_box() -> None:
    st.sidebar.markdown(
        f"<div style='background:#fff;border-radius:10px;padding:10px 14px;border-left:5px solid {CANARY}'>"
        f"<b style='color:{NAVY}'>{html.escape(st.session_state['user'])}</b><br>"
        f"<span style='font-size:.8rem'>Role: <b>{st.session_state['role']}</b></span></div>",
        unsafe_allow_html=True,
    )
    if st.sidebar.button("Sign out"):
        for k in ("role", "user", "page"):
            st.session_state.pop(k, None)
        st.rerun()
    st.sidebar.divider()
 
 
# ======================================================================================
# 7. SHARED FORMS
# ======================================================================================
def project_form(form_key: str, d: dict | None = None, submit_label: str = "Save",
                 allow_status: bool = False, clear: bool = False):
    """Project CapEx & specification form. Returns (submitted, data, files)."""
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
        tier = c2.selectbox("Marketplace tier / strategy *", SUPPLIER_TIERS,
                            index=SUPPLIER_TIERS.index(d.get("tier", "Tactical")))
        sla = c3.slider("Performance & SLA score (1–5)", 1.0, 5.0, float(d.get("sla_score", 3.0)), 0.1)
        active = c3.checkbox("Active supplier", value=bool(d.get("active", True)))
        notes = st.text_area("Notes", value=d.get("notes") or "", height=80)
        submitted = st.form_submit_button(label)
    return submitted, {"name": name.strip(), "category": category, "tier": tier, "market": market.strip(),
                       "sla_score": float(sla), "active": active, "notes": notes.strip()}
 
 
# ======================================================================================
# 8. REQUESTER VIEW
# ======================================================================================
def requester_page() -> None:
    render_header()
    show_flash()
    st.markdown("### 📝 Submit a new project")
    st.caption("Your submission is sent to EMEA Procurement for review (status: *Pending*). "
               "Figures must be in USD. CPS is calculated automatically on submission.")
    submitted, data, files = project_form("req_form", submit_label="📤 Submit project", clear=True)
    if submitted:
        errs = validate_project(data)
        if errs:
            for e in errs:
                st.error(e)
        else:
            data["status"] = "Pending"
            pid = insert_project(data, st.session_state["user"])
            n = save_files(pid, files, st.session_state["user"])
            flash("success", f"✅ Project #{pid} submitted ({n} file(s) attached). {project_result_msg(data)}")
            st.rerun()
 
    st.markdown("### 📋 My submissions")
    df = load_projects()
    mine = df[df["submitted_by"].fillna("").str.lower() == st.session_state["user"].lower()]
    if mine.empty:
        st.info("You have not submitted any project yet.")
    else:
        mine = enrich(mine)
        view = mine[["id", "country", "project_name", "seats", "project_type", "total_capex", "cps", "status",
                     "n_docs"]].rename(columns={"id": "ID", "country": "Country", "project_name": "Project",
                                                "seats": "Seats", "project_type": "Type",
                                                "total_capex": "Total CapEx", "cps": "CPS", "status": "Status",
                                                "n_docs": "Files"})
        show_df(view, column_config={"Total CapEx": st.column_config.NumberColumn(format="$%d"),
                                     "CPS": st.column_config.NumberColumn(format="$%d")})
 
 
# ======================================================================================
# 9. ADMIN VIEW — DASHBOARD
# ======================================================================================
def sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Sidebar filters (Country / Project Type / Seat range). Empty multiselect = all."""
    st.sidebar.markdown("### 🔎 Filters")
    countries = st.sidebar.multiselect("Country", sorted(df["country"].unique()), placeholder="All countries")
    types = st.sidebar.multiselect("Project type", PROJECT_TYPES, placeholder="All types")
    lo, hi = int(df["seats"].min()), int(df["seats"].max())
    rng = st.sidebar.slider("Seat count range", lo, hi, (lo, hi)) if lo < hi else (lo, hi)
    out = df
    if countries:
        out = out[out["country"].isin(countries)]
    if types:
        out = out[out["project_type"].isin(types)]
    out = out[out["seats"].between(rng[0], rng[1])]
    st.sidebar.caption(f"{len(out)} of {len(df)} approved projects selected")
    return out
 
 
def page_dashboard() -> None:
    st.markdown("## 📊 Portfolio Dashboard")
    base = enrich(load_projects("Approved"))
    sup = load_suppliers()
    if base.empty:
        st.info("No approved projects yet. Add projects or approve pending submissions.")
        return
    df = sidebar_filters(base)
    if df.empty:
        st.warning("No project matches the current filters.")
        return
 
    # ---- KPI cards ----
    total, seats = df["total_capex"].sum(), int(df["seats"].sum())
    wcps = total / seats
    delta = (wcps / CPS_TARGET - 1) * 100
    status = rag_status(wcps)
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        kpi_card("Total CapEx Portfolio", money(total), f"{len(df)} projects · {df['country'].nunique()} countries")
    with k2:
        kpi_card("Total Seats Delivered", f"{seats:,}", f"Avg {seats / len(df):,.0f} seats / project", NAVY)
    with k3:
        kpi_card("Weighted Avg CPS", f"${wcps:,.0f}", f"{delta:+.1f}% vs ${CPS_TARGET:,} benchmark · {RAG_ICONS[status]}",
                 RAG_COLORS[status])
    with k4:
        n_alert = int((df["rag"] == "Alert").sum())
        kpi_card("Projects in Alert", f"{n_alert}", f"CPS > ${CPS_TARGET:,}/seat", RED if n_alert else GREEN)
    st.write("")
 
    tabs = st.tabs(["💲 Cost per Seat", "🧱 Spend Breakdown", "🏭 Marketplace & Suppliers", "🗃️ Project Data"])
 
    # ---- Tab 1: CPS by country ----
    with tabs[0]:
        by = st.radio("View by", ["Country", "Project"], horizontal=True)
        if by == "Country":
            agg = country_summary(df).rename(columns={"country": "name"})
        else:
            agg = df.assign(name=df["label"])[["name", "seats", "total_capex", "cps", "rag"]].sort_values("cps")
            agg["vs_target_pct"] = (agg["cps"] / CPS_TARGET - 1) * 100
        fig = px.bar(
            agg, x="name", y="cps", color="rag", color_discrete_map=RAG_COLORS,
            text=agg["cps"].map(lambda v: f"${v:,.0f}"),
            hover_data={"seats": ":,", "total_capex": ":$,.0f", "cps": ":$,.0f", "rag": False},
            labels={"name": by, "cps": "CPS ($/seat)", "rag": "RAG", "seats": "Seats", "total_capex": "Total CapEx"},
            title=f"Cost per Seat by {by} vs ${CPS_TARGET:,} benchmark",
            category_orders={"name": list(agg["name"])},
        )
        fig.add_hline(y=CPS_TARGET, line_dash="dash", line_color=RED, annotation_text=f"Benchmark ${CPS_TARGET:,}")
        fig.add_hline(y=CPS_BEST, line_dash="dot", line_color=GREEN, annotation_text=f"Best-in-Class ${CPS_BEST:,}",
                      annotation_position="bottom right")
        fig.update_traces(textposition="outside")
        fig.update_xaxes(tickangle=-35, title=None)
        show_fig(fig, 480)
        st.caption("Country CPS is weighted (total CapEx ÷ total seats), so small high-cost sites do not distort "
                   "large hubs. RAG: Best-in-Class < $3.5K · On Target $3.5K–$5K · Alert > $5K.")
        table = agg.assign(Status=agg["rag"].map(RAG_ICONS))[
            ["name", "seats", "total_capex", "cps", "vs_target_pct", "Status"]].rename(columns={
                "name": by, "seats": "Seats", "total_capex": "Total CapEx ($)", "cps": "CPS ($/Seat)",
                "vs_target_pct": "vs $5K target"})
        show_df(table, column_config={
            "Seats": st.column_config.NumberColumn(format="%d"),
            "Total CapEx ($)": st.column_config.NumberColumn(format="$%d"),
            "CPS ($/Seat)": st.column_config.NumberColumn(format="$%d"),
            "vs $5K target": st.column_config.NumberColumn(format="%+.0f%%"),
        })
 
    # ---- Tab 2: spend breakdown ----
    with tabs[1]:
        grp = st.radio("Group by", ["Project", "Country"], horizontal=True, key="spend_grp")
        col = "label" if grp == "Project" else "country"
        long = spend_long(df, col)
        order = list(df.groupby(col)["total_capex"].sum().sort_values(ascending=False).index)
        a, b = st.columns(2)
        with a:
            f1 = px.bar(long, x=col, y="amount", color="Category", color_discrete_map=SPEND_COLORS,
                        title="Spend by category (USD, stacked)", barmode="stack",
                        category_orders={col: order}, labels={col: grp, "amount": "USD"})
            f1.update_xaxes(tickangle=-40, title=None)
            show_fig(f1, 470)
        with b:
            f2 = px.bar(long, x=col, y="share", color="Category", color_discrete_map=SPEND_COLORS,
                        title="Spend mix (% of project CapEx)", barmode="stack",
                        category_orders={col: order}, labels={col: grp, "share": "% of CapEx"})
            f2.update_xaxes(tickangle=-40, title=None)
            f2.update_yaxes(range=[0, 100])
            show_fig(f2, 470)
        c, d = st.columns([1, 1.6])
        with c:
            tot = df[SPEND_KEYS].sum().rename(index=SPEND_LABELS).reset_index()
            tot.columns = ["Category", "amount"]
            f3 = px.pie(tot, names="Category", values="amount", hole=0.55, color="Category",
                        color_discrete_map=SPEND_COLORS, title="Portfolio spend mix")
            f3.update_traces(textinfo="percent")
            show_fig(f3, 380)
        with d:
            st.markdown("**Percentage distribution by " + grp.lower() + "**")
            pct = long.pivot_table(index=col, columns="Category", values="share").reindex(order)
            pct = pct[[SPEND_LABELS[k] for k in SPEND_KEYS]].reset_index().rename(columns={col: grp})
            show_df(pct, column_config={SPEND_LABELS[k]: st.column_config.NumberColumn(format="%.1f%%")
                                        for k in SPEND_KEYS})
 
    # ---- Tab 3: suppliers ----
    with tabs[2]:
        supplier_analysis(sup)
 
    # ---- Tab 4: raw data ----
    with tabs[3]:
        view = df[["id", "country", "region", "project_name", "project_type", "seats", *SPEND_KEYS,
                   "total_capex", "cps", "rag"]].copy()
        view["rag"] = view["rag"].map(RAG_ICONS)
        view = view.rename(columns={**SPEND_LABELS, "id": "ID", "country": "Country", "region": "Region",
                                    "project_name": "Project", "project_type": "Type", "seats": "Seats",
                                    "total_capex": "Total CapEx", "cps": "CPS", "rag": "Status"})
        money_fmt = st.column_config.NumberColumn(format="$%d")
        show_df(view, column_config={**{v: money_fmt for v in SPEND_LABELS.values()},
                                     "Total CapEx": money_fmt, "CPS": money_fmt})
 
 
def supplier_analysis(sup: pd.DataFrame) -> None:
    act = sup[sup["active"]]
    if act.empty:
        st.info("No active supplier in the database.")
        return
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Active suppliers", len(act))
    m2.metric("Strategic partners", int((act["tier"] == "Strategic").sum()))
    m3.metric("Avg SLA score", f"{act['sla_score'].mean():.2f} / 5")
    m4.metric("SLA Red (<3.0)", int((act["sla_score"] < 3).sum()))
 
    a, b = st.columns(2)
    with a:
        tc = act["tier"].value_counts().reindex(SUPPLIER_TIERS).fillna(0).reset_index()
        tc.columns = ["Tier", "Suppliers"]
        f = px.pie(tc, names="Tier", values="Suppliers", hole=0.55, color="Tier", color_discrete_map=TIER_COLORS,
                   title="Active suppliers by marketplace tier")
        f.update_traces(textinfo="value+percent")
        show_fig(f, 380)
    with b:
        cc = act.groupby(["category", "tier"], as_index=False).size().rename(columns={"size": "Suppliers"})
        f = px.bar(cc, x="category", y="Suppliers", color="tier", color_discrete_map=TIER_COLORS,
                   barmode="stack", title="Category allocation by tier",
                   category_orders={"tier": SUPPLIER_TIERS, "category": SUPPLIER_CATEGORIES},
                   labels={"category": "Category", "tier": "Tier"})
        show_fig(f, 380)
 
    sc = act.groupby("category", as_index=False)["sla_score"].mean()
    f = px.bar(sc, x="category", y="sla_score", text=sc["sla_score"].map(lambda v: f"{v:.2f}"),
               title="Average SLA score by category", labels={"category": "Category", "sla_score": "SLA (1–5)"},
               color_discrete_sequence=[CANARY])
    f.add_hline(y=4, line_dash="dash", line_color=GREEN, annotation_text="Green ≥ 4")
    f.add_hline(y=3, line_dash="dash", line_color=RED, annotation_text="Red < 3")
    f.update_yaxes(range=[0, 5])
    f.update_traces(textposition="outside")
    show_fig(f, 340)
 
    # Coverage gaps: category without a Backup (or Strategic) supplier
    gaps = []
    for cat in SUPPLIER_CATEGORIES:
        have = set(act[act["category"] == cat]["tier"])
        missing = [t for t in SUPPLIER_TIERS if t not in have]
        if missing:
            gaps.append(f"**{cat}** — no {', '.join(missing)} supplier")
    if gaps:
        st.warning("⚠️ **Coverage gaps**\n\n" + "\n".join(f"- {g}" for g in gaps))
    else:
        st.success("Every category has Strategic, Tactical and Backup coverage.")
 
    t = act.assign(SLA=act["sla_score"].map(sla_rag))[["name", "category", "tier", "market", "sla_score", "SLA"]]
    t = t.rename(columns={"name": "Supplier", "category": "Category", "tier": "Tier", "market": "Market",
                          "sla_score": "SLA score"})
    show_df(t, column_config={"SLA score": st.column_config.ProgressColumn(min_value=1, max_value=5, format="%.1f")})
 
 
# ======================================================================================
# 10. ADMIN VIEW — PROJECT MANAGEMENT (CRUD + documents)
# ======================================================================================
def project_label(row) -> str:
    return f"#{row['id']} · {row['country']} – {row['project_name']} ({row['status']})"
 
 
def page_projects() -> None:
    st.markdown("## 🗂️ Project Management")
    show_flash()
    df = enrich(load_projects())
    user = st.session_state["user"]
 
    with st.expander("📋 All projects", expanded=True):
        q = st.text_input("Search (country, project, submitter)", placeholder="e.g. Tunisia")
        v = df
        if q:
            mask = v[["country", "project_name", "submitted_by"]].fillna("").apply(
                lambda s: s.str.contains(q, case=False)).any(axis=1)
            v = v[mask]
        show_df(
            v[["id", "country", "project_name", "project_type", "seats", "total_capex", "cps", "rag", "status",
               "n_docs", "submitted_by"]].assign(rag=lambda x: x["rag"].map(RAG_ICONS)).rename(columns={
                "id": "ID", "country": "Country", "project_name": "Project", "project_type": "Type",
                "seats": "Seats", "total_capex": "Total CapEx", "cps": "CPS", "rag": "RAG", "status": "Status",
                "n_docs": "Files", "submitted_by": "Submitted by"}),
            column_config={"Total CapEx": st.column_config.NumberColumn(format="$%d"),
                           "CPS": st.column_config.NumberColumn(format="$%d")})
 
    t_add, t_edit, t_del, t_doc = st.tabs(["➕ Add", "✏️ Edit", "🗑️ Delete", "📎 Documents"])
 
    with t_add:
        submitted, data, files = project_form("adm_add", submit_label="➕ Add project", clear=True)
        if submitted:
            errs = validate_project(data)
            if errs:
                for e in errs:
                    st.error(e)
            else:
                data["status"] = "Approved"
                pid = insert_project(data, user)
                save_files(pid, files, user)
                flash("success", f"✅ Project #{pid} added and approved. {project_result_msg(data)}")
                st.rerun()
 
    with t_edit:
        if df.empty:
            st.info("Nothing to edit yet.")
        else:
            pid = st.selectbox("Select project to edit", df["id"].tolist(), key="edit_sel",
                               format_func=lambda i: project_label(df[df["id"] == i].iloc[0]))
            rec = df[df["id"] == pid].iloc[0].to_dict()
            submitted, data, files = project_form(f"adm_edit_{pid}", rec, "💾 Save changes", allow_status=True)
            if submitted:
                errs = validate_project(data)
                if errs:
                    for e in errs:
                        st.error(e)
                else:
                    update_project(pid, data)
                    save_files(pid, files, user)
                    flash("success", f"✅ Project #{pid} updated. {project_result_msg(data)}")
                    st.rerun()
 
    with t_del:
        if df.empty:
            st.info("Nothing to delete.")
        else:
            pid = st.selectbox("Select project to delete", df["id"].tolist(), key="del_sel",
                               format_func=lambda i: project_label(df[df["id"] == i].iloc[0]))
            st.warning("Deleting a project also removes its attached documents. This cannot be undone.")
            confirm = st.checkbox("I confirm I want to permanently delete this project", key=f"delc_{pid}")
            if st.button("🗑️ Delete project", disabled=not confirm):
                delete_project(pid)
                flash("success", f"🗑️ Project #{pid} deleted.")
                st.rerun()
 
    with t_doc:
        manage_documents(df, user)
 
 
def manage_documents(df: pd.DataFrame, user: str) -> None:
    if df.empty:
        st.info("No project available.")
        return
    pid = st.selectbox("Project", df["id"].tolist(), key="doc_sel",
                       format_func=lambda i: project_label(df[df["id"] == i].iloc[0]))
    att = list_attachments(pid)
    if att.empty:
        st.caption("No document attached to this project yet.")
    for _, a in att.iterrows():
        c1, c2, c3 = st.columns([5, 1.6, 1.2])
        c1.markdown(f"📄 **{html.escape(a['filename'])}** · {a['size_bytes'] / 1024:,.0f} KB · "
                    f"{a['uploaded_by']} · {a['uploaded_at']}", unsafe_allow_html=True)
        c2.download_button("⬇️ Download", get_attachment_blob(int(a["id"])), file_name=a["filename"],
                           mime=a["mime"] or "application/octet-stream", key=f"dl_{a['id']}")
        if c3.button("Remove", key=f"rm_{a['id']}"):
            delete_attachment(int(a["id"]))
            flash("success", f"Removed '{a['filename']}'.")
            st.rerun()
    st.divider()
    ver = st.session_state.get("up_ver", 0)  # changing the key resets the uploader after saving
    new = st.file_uploader("Add documents", type=ALLOWED_UPLOADS, accept_multiple_files=True, key=f"up_{pid}_{ver}")
    if st.button("📎 Attach files", disabled=not new):
        n = save_files(pid, new, user)
        st.session_state["up_ver"] = ver + 1
        flash("success", f"📎 {n} file(s) attached to project #{pid}.")
        st.rerun()
 
 
# ======================================================================================
# 11. ADMIN VIEW — APPROVALS
# ======================================================================================
def page_approvals() -> None:
    st.markdown("## ✅ Pending Approvals")
    show_flash()
    pend = enrich(load_projects("Pending"))
    if pend.empty:
        st.success("No pending submission. 🎉")
        return
    for _, r in pend.iterrows():
        pid = int(r["id"])
        title = f"#{pid} · {r['country']} – {r['project_name']} · {RAG_ICONS[r['rag']]} · submitted by {r['submitted_by']}"
        with st.expander(title, expanded=True):
            a, b, c, d = st.columns(4)
            a.metric("Seats", f"{int(r['seats']):,}")
            b.metric("Total CapEx", money(r["total_capex"]))
            c.metric("CPS", f"${r['cps']:,.0f}", f"{(r['cps'] / CPS_TARGET - 1) * 100:+.0f}% vs target",
                     delta_color="inverse")
            d.metric("Type", r["project_type"])
            st.write({SPEND_LABELS[k]: f"${r[k]:,.0f}" for k in SPEND_KEYS})
            if r["notes"]:
                st.caption(f"📝 {r['notes']}")
            if int(r["n_docs"]):
                st.caption(f"📎 {int(r['n_docs'])} attached file(s) — see Projects › Documents")
            b1, b2, _ = st.columns([1, 1, 5])
            if b1.button("✅ Approve", key=f"ap_{pid}"):
                set_project_status(pid, "Approved")
                flash("success", f"Project #{pid} approved.")
                st.rerun()
            if b2.button("❌ Reject", key=f"rj_{pid}"):
                set_project_status(pid, "Rejected")
                flash("warning", f"Project #{pid} rejected.")
                st.rerun()
 
 
# ======================================================================================
# 12. ADMIN VIEW — SUPPLIERS
# ======================================================================================
def page_suppliers() -> None:
    st.markdown("## 🏭 Supplier Database & Evaluation")
    show_flash()
    sup = load_suppliers()
    f1, f2, f3 = st.columns(3)
    cat = f1.multiselect("Category", SUPPLIER_CATEGORIES, placeholder="All")
    tier = f2.multiselect("Tier", SUPPLIER_TIERS, placeholder="All")
    only_active = f3.checkbox("Active only", value=False)
    v = sup
    if cat:
        v = v[v["category"].isin(cat)]
    if tier:
        v = v[v["tier"].isin(tier)]
    if only_active:
        v = v[v["active"]]
    show_df(v.assign(SLA=v["sla_score"].map(sla_rag))[
        ["id", "name", "category", "tier", "market", "sla_score", "SLA", "active", "notes"]].rename(columns={
            "id": "ID", "name": "Supplier", "category": "Category", "tier": "Tier", "market": "Market",
            "sla_score": "SLA score", "active": "Active", "notes": "Notes"}),
        column_config={"SLA score": st.column_config.ProgressColumn(min_value=1, max_value=5, format="%.1f")})
 
    t_add, t_edit, t_del = st.tabs(["➕ Add supplier", "✏️ Edit supplier", "🗑️ Delete supplier"])
    with t_add:
        ok, d = supplier_form("sup_add", label="➕ Add supplier", clear=True)
        if ok:
            if not d["name"]:
                st.error("Supplier name is required.")
            else:
                insert_supplier(d)
                flash("success", f"✅ Supplier '{d['name']}' added.")
                st.rerun()
    fmt = lambda i: (lambda r: f"#{r['id']} · {r['name']} · {r['category']} · {r['tier']}")(
        sup[sup["id"] == i].iloc[0])
    with t_edit:
        if sup.empty:
            st.info("No supplier yet.")
        else:
            sid = st.selectbox("Select supplier", sup["id"].tolist(), key="sup_edit_sel", format_func=fmt)
            ok, d = supplier_form(f"sup_edit_{sid}", sup[sup["id"] == sid].iloc[0].to_dict(), "💾 Save changes")
            if ok:
                if not d["name"]:
                    st.error("Supplier name is required.")
                else:
                    update_supplier(sid, d)
                    flash("success", f"✅ Supplier '{d['name']}' updated.")
                    st.rerun()
    with t_del:
        if sup.empty:
            st.info("No supplier yet.")
        else:
            sid = st.selectbox("Select supplier to delete", sup["id"].tolist(), key="sup_del_sel", format_func=fmt)
            confirm = st.checkbox("I confirm the deletion", key=f"sup_delc_{sid}")
            if st.button("🗑️ Delete supplier", disabled=not confirm):
                delete_supplier(sid)
                flash("success", "🗑️ Supplier deleted.")
                st.rerun()
 
 
# ======================================================================================
# 13. ADMIN VIEW — EXPORT
# ======================================================================================
def page_export() -> None:
    st.markdown("## ⬇️ Export & Reports")
    base = enrich(load_projects("Approved"))
    if base.empty:
        st.info("No approved project to export.")
        return
    df = sidebar_filters(base)  # same filters as the dashboard
    if df.empty:
        st.warning("No project matches the current filters.")
        return
    sup = load_suppliers()
    st.caption(f"Exports reflect the sidebar filters: **{len(df)} project(s)**, {int(df['seats'].sum()):,} seats, "
               f"{money(df['total_capex'].sum())}.")
 
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    names = {**SPEND_LABELS, "country": "Country", "region": "Region", "project_name": "Project",
             "project_type": "Type", "seats": "Seats", "total_capex": "Total CapEx ($)", "cps": "CPS ($/Seat)",
             "rag": "RAG", "status": "Status", "notes": "Notes"}
    proj_csv = df[["country", "region", "project_name", "project_type", "seats", *SPEND_KEYS, "total_capex", "cps",
                   "rag", "status", "notes"]].rename(columns=names).to_csv(index=False).encode("utf-8-sig")
    cs = country_summary(df)
    for k in SPEND_KEYS:  # add % mix columns to the summary report
        cs[f"{SPEND_LABELS[k]} (%)"] = (cs[k] / cs["total_capex"] * 100).round(1)
    summary_csv = cs.rename(columns={**names, "projects": "Projects", "vs_target_pct": "vs $5K target (%)"}) \
        .to_csv(index=False).encode("utf-8-sig")
 
    c1, c2, c3 = st.columns(3)
    c1.download_button("📄 Projects (CSV)", proj_csv, f"projects_{stamp}.csv", "text/csv")
    c2.download_button("📄 Summary by country (CSV)", summary_csv, f"summary_by_country_{stamp}.csv", "text/csv")
    c3.download_button("📊 Full report (Excel)", build_excel(df, sup), f"emea_capex_report_{stamp}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.markdown("**Preview — summary by country**")
    show_df(cs[["country", "projects", "seats", "total_capex", "cps", "rag"]].assign(
        rag=cs["rag"].map(RAG_ICONS)).rename(columns={"country": "Country", "projects": "Projects",
                                                      "seats": "Seats", "total_capex": "Total CapEx ($)",
                                                      "cps": "CPS ($/Seat)", "rag": "Status"}),
            column_config={"Total CapEx ($)": st.column_config.NumberColumn(format="$%d"),
                           "CPS ($/Seat)": st.column_config.NumberColumn(format="$%d")})
 
 
# ======================================================================================
# 14. ADMIN SHELL & MAIN
# ======================================================================================
def admin_shell() -> None:
    n_pending = len(load_projects("Pending"))
    pages = {
        "dashboard": "📊 Dashboard",
        "projects": "🗂️ Projects",
        "approvals": f"✅ Approvals ({n_pending})" if n_pending else "✅ Approvals",
        "suppliers": "🏭 Suppliers",
        "export": "⬇️ Export",
    }
    page = st.sidebar.radio("Navigation", list(pages), format_func=pages.get, key="page")
    st.sidebar.divider()
    render_header()
    {"dashboard": page_dashboard, "projects": page_projects, "approvals": page_approvals,
     "suppliers": page_suppliers, "export": page_export}[page]()
 
 
def main() -> None:
    ensure_theme_config()
    init_db()
    inject_css()
    if not st.session_state.get("role"):
        login_screen()
        return
    st.sidebar.markdown(f"<h3 style='color:{NAVY};margin:0'>concentrix<span style='color:{CANARY}'>●</span></h3>",
                        unsafe_allow_html=True)
    sidebar_user_box()
    if st.session_state["role"] == "Admin":
        admin_shell()
    else:
        requester_page()
 
 
main()
 
