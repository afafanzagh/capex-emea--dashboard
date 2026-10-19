import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Configuration de la page
st.set_page_config(
    page_title=(
        "Concentrix | EMEA Real Estate & Procurement Intelligence Suite"
    ),
    page_icon="🏢",
    layout="wide",
)

# Design Luxury Enterprise & Palette (Bleu Canard, Vert Canard, Rose Subtil)
st.markdown(
    """
    <style>
    .main { background-color: #F4F7F6; font-family: 'Inter', sans-serif; }
    .stMetric { background-color: #FFFFFF; padding: 18px; border-radius: 12px; box-shadow: 0 4px 12px rgba(31,78,120,0.08); border-left: 5px solid #008080; }
    h1, h2, h3 { color: #1F4E78; font-family: 'Helvetica Neue', sans-serif; font-weight: 700; }
    .stSidebar { background-color: #1F4E78; }
    </style>
""",
    unsafe_allow_html=True,
)


# -------------------------------------------------------------------------
# INITIALISATION DES DONNÉES ET GESTION DE SESSION
# -------------------------------------------------------------------------
@st.cache_data
def get_default_data():
  data = {
      "Country": [
          "Morocco",
          "Morocco",
          "Morocco",
          "Benin",
          "Tunisia",
          "Bulgaria",
          "France",
          "Madagascar",
      ],
      "Site": [
          "Casablanca Sidi Maarouf",
          "Rabat 6",
          "Marrakech Medina",
          "Cotonou 6th Floor",
          "Tunis Carthage",
          "Sofia Campus",
          "Paris Opéra",
          "Antananarivo Analakely",
      ],
      "Seats": [350, 200, 150, 180, 250, 400, 120, 220],
      "Surface_m2": [2400, 1400, 1000, 1250, 1750, 2800, 900, 1500],
      "Furniture_Cost": [95000, 58000, 42000, 65000, 85000, 140000, 95000, 55000],
      "Cabling_Telecom": [
          45000,
          28000,
          22000,
          35000,
          40000,
          70000,
          50000,
          30000,
      ],
      "HVAC_Cost": [75000, 45000, 35000, 55000, 65000, 110000, 70000, 45000],
      "Civil_Works": [
          120000,
          85000,
          65000,
          95000,
          110000,
          180000,
          90000,
          70000,
      ],
      "Security_Access": [
          30000,
          18000,
          15000,
          20000,
          25000,
          45000,
          25000,
          15000,
      ],
      "Logistics_PM": [50000, 31000, 26000, 20000, 35000, 45000, 15000, 20000],
      "Benchmark_CPS": [1200, 1200, 1200, 1500, 1300, 1800, 3200, 1000],
  }
  return pd.DataFrame(data)


if "df_projects" not in st.session_state:
  st.session_state.df_projects = get_default_data()

# -------------------------------------------------------------------------
# SIDEBAR : NAVIGATION, IMPORT & SAISIE DYNAMIQUE DE PROJET
# -------------------------------------------------------------------------
st.sidebar.title("🏢 Navigation Executive")
menu = st.sidebar.radio(
    "Aller vers :",
    [
        "📊 Dashboard & KPIs",
        "➕ Ajouter / Gérer un Projet",
        "🌍 Analyse & Benchmark par Pays",
        "📇 Annuaire Fournisseurs & Stratégie",
    ],
)

st.sidebar.markdown("---")
st.sidebar.subheader("📁 Connectivité Données")
uploaded_file = st.sidebar.file_uploader(
    "Importer le suivi Excel (BOQ / Dépenses)", type=["xlsx", "xls"]
)

if uploaded_file is not None:
  try:
    df_excel = pd.read_excel(uploaded_file, sheet_name=0)
    st.sidebar.success("Fichier Excel synchronisé avec succès !")
  except Exception as e:
    st.sidebar.error(f"Erreur de lecture : {e}")

# Consolidation des données
df = st.session_state.df_projects

# Calculs automatiques des coûts totaux et des KPIs par ligne
df["Total_Cost"] = (
    df["Furniture_Cost"]
    + df["Cabling_Telecom"]
    + df["HVAC_Cost"]
    + df["Civil_Works"]
    + df["Security_Access"]
    + df["Logistics_PM"]
)
df["Cost_Per_Seat"] = df["Total_Cost"] / df["Seats"]
df["Cost_Per_m2"] = df["Total_Cost"] / df["Surface_m2"]
df["Variance_Benchmark"] = df["Cost_Per_Seat"] - df["Benchmark_CPS"]

# Filtre par Pays global
countries = df["Country"].unique().tolist()
selected_countries = st.sidebar.multiselect(
    "Filtrer par Pays", options=countries, default=countries
)
filtered_df = df[df["Country"].isin(selected_countries)]


# -------------------------------------------------------------------------
# 1. TAB : DASHBOARD & KPIS EXÉCUTIFS
# -------------------------------------------------------------------------
if menu == "📊 Dashboard & KPIs":
  st.title("🏢 EMEA Real Estate & Fit-Out Executive Dashboard")
  st.markdown(
      "**Pilotage stratégique des CAPEX, analyse des Coûts par Siège (CPS) et"
      " maîtrise des postes budgétaires.**"
  )
  st.markdown("---")

  # KPI Cards
  col1, col2, col3, col4 = st.columns(4)
  total_capex = filtered_df["Total_Cost"].sum()
  total_seats = filtered_df["Seats"].sum()
  avg_cps = total_capex / total_seats if total_seats > 0 else 0
  avg_sqm_cost = (
      filtered_df["Total_Cost"].sum() / filtered_df["Surface_m2"].sum()
      if filtered_df["Surface_m2"].sum() > 0
      else 0
  )

  col1.metric("Total CAPEX Engagé", f"{total_capex:,.0f} $")
  col2.metric("Total Postes (Sièges)", f"{total_seats:,.0f} postes")
  col3.metric("Coût Moyen / Siège (CPS)", f"{avg_cps:,.2f} $ / poste")
  col4.metric("Coût Moyen / m²", f"{avg_sqm_cost:,.2f} $ / m²")

  st.markdown("---")

  # Graphiques principaux
  c1, c2 = st.columns(2)

  with c1:
    st.subheader("📊 Cost-per-Seat vs Marché Benchmark par Site")
    fig_bench = go.Figure()
    fig_bench.add_trace(
        go.Bar(
            x=filtered_df["Site"],
            y=filtered_df["Cost_Per_Seat"],
            name="Coût Réel / Siège ($)",
            marker_color="#1F4E78",
        )
    )
    fig_bench.add_trace(
        go.Scatter(
            x=filtered_df["Site"],
            y=filtered_df["Benchmark_CPS"],
            mode="lines+markers",
            name="Cible Benchmark ($)",
            line=dict(color="#D87093", width=3),
        )
    )
    fig_bench.update_layout(
        xaxis_tickangle=-30,
        margin=dict(t=20, b=20, l=20, r=20),
        legend=dict(orientation="h", y=1.15, x=0),
    )
    st.plotly_chart(fig_bench, use_container_width=True)

  with c2:
    st.subheader("🥧 Breakdown Global des Dépenses par Spend Category")
    spend_totals = {
        "Furniture": filtered_df["Furniture_Cost"].sum(),
        "Cabling & Telecom": filtered_df["Cabling_Telecom"].sum(),
        "HVAC": filtered_df["HVAC_Cost"].sum(),
        "Civil Works": filtered_df["Civil_Works"].sum(),
        "Security & Access": filtered_df["Security_Access"].sum(),
        "Logistics & PM": filtered_df["Logistics_PM"].sum(),
    }
    df_spend = pd.DataFrame(
        list(spend_totals.items()), columns=["Category", "Amount"]
    )
    fig_pie = px.pie(
        df_spend,
        names="Category",
        values="Amount",
        hole=0.45,
        color_discrete_sequence=px.colors.qualitative.Bold,
    )
    fig_pie.update_layout(margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig_pie, use_container_width=True)

  st.markdown("---")
  st.subheader("📋 Tableau Analytique Détaillé des Projets")
  st.dataframe(filtered_df, use_container_width=True)


# -------------------------------------------------------------------------
# 2. TAB : AJOUTER / GÉRER UN PROJET (INTERFACE EXCEL-TO-TOOL)
# -------------------------------------------------------------------------
elif menu == "➕ Ajouter / Gérer un Projet":
  st.title("➕ Enregistrement & Intégration de Nouveau Projet")
  st.markdown(
      "Ajoutez instantanément un nouveau projet fit-out. L'outil calcule"
      " automatiquement les ratios, les écarts de benchmark et met à jour"
      " l'ensemble des KPIs sans manipulation Excel manuelle."
  )
  st.markdown("---")

  with st.form("new_project_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
      p_country = st.selectbox(
          "Pays", ["Morocco", "Benin", "Tunisia", "France", "Bulgaria", "Madagascar"]
      )
      p_site = st.text_input("Nom du Site / Projet", "Casablanca Marina Center")
    with col2:
      p_seats = st.number_input(
          "Nombre de Sièges (Postes)", min_value=10, max_value=2000, value=250
      )
      p_surface = st.number_input(
          "Surface (m²)", min_value=50, max_value=20000, value=1600
      )
    with col3:
      p_benchmark = st.number_input(
          "CPS Cible Benchmark ($)", min_value=500, max_value=5000, value=1300
      )

    st.subheader("💰 Ventilation des Coûts par Spend Category ($)")
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
      f_furniture = st.number_input("Mobilier (Workstations, Sièges)", value=60000)
      f_cabling = st.number_input("Câblage LAN, Telecom & Server Room", value=35000)
    with sc2:
      f_hvac = st.number_input("Climatisation / HVAC", value=50000)
      f_civil = st.number_input("Civil Works & Finitions", value=90000)
    with sc3:
      f_security = st.number_input("Sécurité, CCTV & Contrôle d'accès", value=20000)
      f_logistics = st.number_input(
          "Logistique, Transport & Installation", value=25000
      )

    submitted = st.form_submit_button(
        "💾 Enregistrer et Calculer les KPIs Instantanément"
    )
    if submitted:
      new_row = {
          "Country": p_country,
          "Site": p_site,
          "Seats": p_seats,
          "Surface_m2": p_surface,
          "Furniture_Cost": f_furniture,
          "Cabling_Telecom": f_cabling,
          "HVAC_Cost": f_hvac,
          "Civil_Works": f_civil,
          "Security_Access": f_security,
          "Logistics_PM": f_logistics,
          "Benchmark_CPS": p_benchmark,
      }
      st.session_state.df_projects = pd.concat(
          [st.session_state.df_projects, pd.DataFrame([new_row])],
          ignore_index=True,
      )
      st.success(
          f"Projet '{p_site}' ajouté avec succès ! Les KPIs ont été recalculés."
      )


# -------------------------------------------------------------------------
# 3. TAB : ANALYSE & BENCHMARK PAR PAYS
# -------------------------------------------------------------------------
elif menu == "🌍 Analyse & Benchmark par Pays":
  st.title("🌍 Analyse Stratégique des Coûts par Pays & Benchmarking")
  st.markdown(
      "Évaluation comparative des coûts par poste de travail, analyse des"
      " écarts et recommandations d'optimisation."
  )
  st.markdown("---")

  country_agg = (
      filtered_df.groupby("Country")
      .agg(
          {
              "Seats": "sum",
              "Surface_m2": "sum",
              "Total_Cost": "sum",
              "Cost_Per_Seat": "mean",
              "Benchmark_CPS": "mean",
          }
      )
      .reset_index()
  )

  c_left, c_right = st.columns(2)
  with c_left:
    st.subheader("📊 Coût Moyen Réel par Siège vs Cible par Pays")
    fig_c_cps = px.bar(
        country_agg,
        x="Country",
        y=["Cost_Per_Seat", "Benchmark_CPS"],
        barmode="group",
        color_discrete_sequence=["#1F4E78", "#008080"],
    )
    st.plotly_chart(fig_c_cps, use_container_width=True)

  with c_right:
    st.subheader("💡 Recommandations & Analyse Procurement")
    for index, row in country_agg.iterrows():
      variance = row["Cost_Per_Seat"] - row["Benchmark_CPS"]
      status = (
          "⚠️ Dépassement budgétaire"
          if variance > 0
          else "✅ Performance optimale"
      )
      st.info(
          f"**{row['Country']}** : CPS Réel = **{row['Cost_Per_Seat']:.1f} $**"
          f" (Cible : {row['Benchmark_CPS']:.1f} $) — *{status}*"
      )

  st.markdown("---")
  st.subheader("📈 Tableau de Synthèse Agrégé par Pays")
  st.dataframe(country_agg, use_container_width=True)


# -------------------------------------------------------------------------
# 4. TAB : ANNUAIRE FOURNISSEURS & STRATÉGIE
# -------------------------------------------------------------------------
elif menu == "📇 Annuaire Fournisseurs & Stratégie":
  st.title("📇 Annuaire Stratégique & Matrice des Fournisseurs")
  st.markdown(
      "Gestion et classification des fournisseurs par catégorie (Strategic,"
      " Tactical, Backup) et par corps d'état."
  )
  st.markdown("---")

  suppliers_data = {
      "Country": [
          "Morocco",
          "Morocco",
          "Benin",
          "France",
          "Madagascar",
          "Tunisia",
          "Bulgaria",
      ],
      "Spend Category": [
          "Furniture",
          "Civil Works & Electrical",
          "Second Œuvre",
          "Acoustic & Partitions",
          "Cabling & Telecom",
          "HVAC",
          "Security & Access",
      ],
      "Supplier Name": [
          "Atlas Office & Design",
          "Electro Maroc Pro",
          "Cotonou Bâtiment Services",
          "Paris Space Fit-Out",
          "Madagascar Telecom Infra",
          "Tunis Climatisation SARL",
          "Sofia Security Systems",
      ],
      "Category Status": [
          "Strategic",
          "Tactical",
          "Strategic",
          "Strategic",
          "Backup",
          "Strategic",
          "Tactical",
      ],
      "SLA / Discount Validated": [
          "SLA 48h - 12% Remise Cadre",
          "SLA 24h - Garantie 3 ans",
          "SLA 72h - Paiement J+30",
          "SLA 24h - ISO 9001",
          "SLA 5 jours",
          "SLA 48h - Contrat Maintenance",
          "SLA 24h",
      ],
  }
  df_sup = pd.DataFrame(suppliers_data)

  # KPI Fournisseurs
  f_col1, f_col2, f_col3 = st.columns(3)
  f_col1.metric("Fournisseurs Référencés", len(df_sup))
  f_col2.metric(
      "Part Fournisseurs Stratégiques",
      f"{(len(df_sup[df_sup['Category Status']=='Strategic'])/len(df_sup))*100:.0f}%",
  )
  f_col3.metric("Pays Couverts", df_sup["Country"].nunique())

  st.markdown("---")
  st.dataframe(df_sup, use_container_width=True)
