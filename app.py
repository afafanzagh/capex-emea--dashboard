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
def load_default_data():
  data = {
      "Site": [
          "Casablanca Sidi Maarouf (Maroc)",
          "Rabat 6 (Maroc)",
          "Marrakech Medina (Maroc)",
          "Cotonou 6th Floor (Bénin)",
          "Tunis Carthage (Tunisie)",
          "Sofia Campus (Bulgarie)",
          "Paris Opéra (France)",
          "Antananarivo Analakely (Madagascar)",
      ],
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
      "Seats": [350, 200, 150, 180, 250, 400, 120, 220],
      "Surface_m2": [2400, 1400, 1000, 1250, 1750, 2800, 900, 1500],
      "Initial_Budget": [
          450000,
          280000,
          210000,
          310000,
          380000,
          620000,
          360000,
          250000,
      ],
      "Actual_Spend": [
          415000,
          265000,
          195000,
          290000,
          355000,
          590000,
          345000,
          235000,
      ],
      "Benchmark_CPS": [1200, 1200, 1200, 1500, 1300, 1800, 3200, 1000],
  }
  return pd.DataFrame(data)


st.sidebar.title("🎛️ Navigation & Paramètres")
uploaded_file = st.sidebar.file_uploader(
    "Importer le suivi Excel (BOQ / Dépenses)", type=["xlsx", "xls"]
)

if uploaded_file is not None:
  try:
    df = pd.read_excel(uploaded_file)
    st.sidebar.success("Fichier Excel chargé avec succès !")
  except Exception as e:
    st.sidebar.error(f"Erreur de lecture du fichier : {e}")
    df = load_default_data()
else:
  df = load_default_data()

df["Savings"] = df["Initial_Budget"] - df["Actual_Spend"]
df["Savings_Pct"] = (df["Savings"] / df["Initial_Budget"]) * 100
df["Cost_Per_Seat"] = df["Actual_Spend"] / df["Seats"]
df["Cost_Per_m2"] = df["Actual_Spend"] / df["Surface_m2"]

selected_country = st.sidebar.multiselect(
    "Filtrer par Pays",
    options=df["Country"].unique(),
    default=df["Country"].unique(),
)
filtered_df = df[df["Country"].isin(selected_country)]

st.title("🏢 Corporate Real Estate & Fit-Out Intelligence Dashboard")
st.markdown(
    "**Pilotage stratégique des CAPEX, Coûts par Siège (CPS) et Optimisation"
    " des Fournisseurs.**"
)
st.markdown("---")

col1, col2, col3, col4 = st.columns(4)
total_budget = filtered_df["Initial_Budget"].sum()
total_spend = filtered_df["Actual_Spend"].sum()
total_savings = filtered_df["Savings"].sum()
avg_cps = (
    filtered_df["Actual_Spend"].sum() / filtered_df["Seats"].sum()
    if filtered_df["Seats"].sum() > 0
    else 0
)

col1.metric("Budget Total Validé", f"{total_budget:,.0f} €")
col2.metric(
    "Dépenses Réelles",
    f"{total_spend:,.0f} €",
    delta=f"-{(total_budget - total_spend):,.0f} €",
    delta_color="normal",
)
col3.metric(
    "Économies Négociées",
    f"{total_savings:,.0f} €",
    delta=f"{(total_savings/total_budget)*100:.1f}%",
)
col4.metric("Coût Moyen par Siège (CPS)", f"{avg_cps:,.0f} € / poste")

st.markdown("---")

col_left, col_right = st.columns(2)
with col_left:
  st.subheader("📊 Comparatif Cost-per-Seat vs Benchmark")
  fig_cps = go.Figure()
  fig_cps.add_trace(
      go.Bar(
          x=filtered_df["Site"],
          y=filtered_df["Cost_Per_Seat"],
          name="Coût Réel / Siège (€)",
          marker_color="#1F4E78",
      )
  )
  fig_cps.add_trace(
      go.Scatter(
          x=filtered_df["Site"],
          y=filtered_df["Benchmark_CPS"],
          mode="lines+markers",
          name="Benchmark Marché (€)",
          line=dict(color="#D9534F", width=3),
      )
  )
  fig_cps.update_layout(xaxis_tickangle=-45, margin=dict(t=20, b=40, l=20, r=20))
  st.plotly_chart(fig_cps, use_container_width=True)

with col_right:
  st.subheader("🌍 Répartition des Dépenses par Pays")
  country_spend = (
      filtered_df.groupby("Country")["Actual_Spend"].sum().reset_index()
  )
  fig_pie = px.pie(
      country_spend,
      names="Country",
      values="Actual_Spend",
      hole=0.4,
      color_discrete_sequence=px.colors.qualitative.Prism,
  )
  fig_pie.update_layout(margin=dict(t=20, b=20, l=20, r=20))
  st.plotly_chart(fig_pie, use_container_width=True)

st.subheader("📋 Tableau de Synthèse Financière par Projet")
st.dataframe(
    filtered_df[[
        "Site",
        "Country",
        "Seats",
        "Surface_m2",
        "Initial_Budget",
        "Actual_Spend",
        "Cost_Per_Seat",
        "Cost_Per_m2",
        "Savings_Pct",
    ]].style.format({
        "Initial_Budget": "{:,.0f} €",
        "Actual_Spend": "{:,.0f} €",
        "Cost_Per_Seat": "{:,.2f} €",
        "Cost_Per_m2": "{:,.2f} €",
        "Savings_Pct": "{:.1f}%",
    }),
    use_container_width=True,
)

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
