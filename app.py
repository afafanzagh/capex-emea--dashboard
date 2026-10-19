import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Concentrix EMEA - Capex & Fit-Out Intelligence Dashboard",
    page_icon="🏢",
    layout="wide",
)

st.markdown(
    """
    <style>
    .main { background-color: #F8F9FA; }
    .stMetric { background-color: #FFFFFF; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    h1, h2, h3 { color: #1F4E78; font-family: 'Helvetica Neue', sans-serif; }
    </style>
""",
    unsafe_allow_html=True,
)


@st.cache_data
def load_data(uploaded_file=None):
  if uploaded_file is not None:
    try:
      # Lecture de l'onglet principal du suivi CAPEX
      df = pd.read_excel(uploaded_file, sheet_name="CPS Project Overview")
    except Exception:
      df = pd.read_excel(uploaded_file, sheet_name=0)
  else:
    # Fichier par défaut s'appuyant sur la structure exacte de votre fichier
    excel_path = "Concentrix_EMEA_Capex_CPS _Tracking_Final (6).xlsx"
    try:
      df = pd.read_excel(excel_path, sheet_name="CPS Project Overview")
    except Exception:
      # Données de secours si le fichier local n'est pas trouvé
      data = {
          "EMEA_Country": ["Morocco", "Morocco", "Benin", "Tunisia", "France"],
          "Concentrix Site": [
              "Casablanca Sidi Maarouf",
              "Rabat 6",
              "Cotonou 6th Floor",
              "Tunis Carthage",
              "Paris Opéra",
          ],
          "Number of seats (Latest project)": [350, 200, 180, 250, 120],
          "Site Area sqm": [2400, 1400, 1250, 1750, 900],
          "Total Cost ($)": [415000, 265000, 290000, 355000, 345000],
          "Cost Per Seat ($)\nLatest Project": [1185, 1325, 1611, 1420, 2875],
          "Completion Status": [
              "Completed",
              "Completed",
              "Pending",
              "Completed",
              "Completed",
          ],
      }
      return pd.DataFrame(data)

  # Nettoyage des lignes vides et adaptation des colonnes du fichier réel
  df = df.dropna(subset=[df.columns[1]])
  return df


st.sidebar.title("🎛️ Navigation & Paramètres")
uploaded_file = st.sidebar.file_uploader(
    "Importer le suivi Excel (BOQ / Dépenses)", type=["xlsx", "xls"]
)

df = load_data(uploaded_file)

# Détection intelligente des colonnes selon votre fichier Excel
col_country = (
    "EMEA_Country" if "EMEA_Country" in df.columns else df.columns[1]
)
col_site = (
    "Concentrix Site" if "Concentrix Site" in df.columns else df.columns[2]
)
col_seats = (
    "Number of seats (Latest project)"
    if "Number of seats (Latest project)" in df.columns
    else df.columns[5]
)
col_sqm = "Site Area sqm" if "Site Area sqm" in df.columns else df.columns[6]
col_total_cost = (
    "Total Cost ($)" if "Total Cost ($)" in df.columns else df.columns[11]
)
col_cps = (
    "Cost Per Seat ($)\nLatest Project"
    if "Cost Per Seat ($)\nLatest Project" in df.columns
    else df.columns[12]
)

# Standardisation pour les calculs
df_clean = pd.DataFrame()
df_clean["Country"] = df[col_country].astype(str)
df_clean["Site"] = df[col_site].astype(str)
df_clean["Seats"] = pd.to_numeric(df[col_seats], errors="coerce").fillna(0)
df_clean["Surface_m2"] = pd.to_numeric(df[col_sqm], errors="coerce").fillna(0)
df_clean["Total_Cost"] = pd.to_numeric(
    df[col_total_cost], errors="coerce"
).fillna(0)
df_clean["Cost_Per_Seat"] = pd.to_numeric(df[col_cps], errors="coerce").fillna(
    0
)

# Filtres par pays
countries = [c for c in df_clean["Country"].unique() if c != "nan" and c != ""]
selected_country = st.sidebar.multiselect(
    "Filtrer par Pays", options=countries, default=countries
)
filtered_df = df_clean[df_clean["Country"].isin(selected_country)]

# Header & KPIs
st.title("🏢 Corporate Real Estate & Fit-Out Intelligence Dashboard")
st.markdown(
    "**Pilotage stratégique des CAPEX, Coûts par Siège (CPS) et Analyse des"
    " Projets EMEA.**"
)
st.markdown("---")

col1, col2, col3, col4 = st.columns(4)
total_spend = filtered_df["Total_Cost"].sum()
total_seats = filtered_df["Seats"].sum()
total_surface = filtered_df["Surface_m2"].sum()
avg_cps = total_spend / total_seats if total_seats > 0 else 0

col1.metric("Dépenses Totales (CAPEX)", f"{total_spend:,.0f} $")
col2.metric("Total Sièges Opérationnels", f"{total_seats:,.0f} postes")
col3.metric("Surface Totale Aménagée", f"{total_surface:,.0f} m²")
col4.metric("Coût Moyen par Siège (CPS)", f"{avg_cps:,.2f} $ / poste")

st.markdown("---")

# Graphiques
col_left, col_right = st.columns(2)
with col_left:
  st.subheader("📊 Cost-per-Seat par Site")
  if not filtered_df.empty:
    fig_cps = px.bar(
        filtered_df,
        x="Site",
        y="Cost_Per_Seat",
        color="Country",
        text_auto=".2f",
        color_discrete_sequence=px.colors.qualitative.Prism,
    )
    fig_cps.update_layout(xaxis_tickangle=-45, margin=dict(t=20, b=40, l=20, r=20))
    st.plotly_chart(fig_cps, use_container_width=True)

with col_right:
  st.subheader("🌍 Répartition des CAPEX par Pays")
  if not filtered_df.empty:
    country_spend = (
        filtered_df.groupby("Country")["Total_Cost"].sum().reset_index()
    )
    fig_pie = px.pie(
        country_spend,
        names="Country",
        values="Total_Cost",
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Prism,
    )
    fig_pie.update_layout(margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig_pie, use_container_width=True)

# Tableau de Synthèse
st.subheader("📋 Tableau de Synthèse Financière par Projet")
st.dataframe(filtered_df, use_container_width=True)

# Annuaire Fournisseurs
st.markdown("---")
st.subheader("📇 Annuaire & Matrice des Fournisseurs Référencés")
suppliers_data = {
    "Pays": [
        "Maroc",
        "Maroc",
        "Bénin",
        "France",
        "Madagascar",
        "Tunisie",
        "Bulgarie",
    ],
    "Corps d'État": [
        "Mobilier & Agencement",
        "Électricité / Courants Forts",
        "Second Œuvre",
        "Cloisons & Acoustique",
        "Câblage LAN",
        "HVAC",
        "Sécurité / CCTV",
    ],
    "Fournisseur": [
        "Atlas Office & Design",
        "Electro Maroc Pro",
        "Cotonou Bâtiment Services",
        "Paris Space Fit-Out",
        "Madagascar Telecom Infra",
        "Tunis Climatisation SARL",
        "Sofia Security Systems",
    ],
    "Statut": [
        "Stratégique",
        "Tactique",
        "Stratégique",
        "Stratégique",
        "Backup",
        "Stratégique",
        "Tactique",
    ],
}
st.dataframe(pd.DataFrame(suppliers_data), use_container_width=True)
