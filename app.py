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
# 0. PAGE CONFIG
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
                   created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                [(n, cat, t, m, s, 1, "Seed data", ts, ts) for n, cat, t, m, s in SEED_SUPPLIERS],
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

def
