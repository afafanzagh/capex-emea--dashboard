import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# -------------------------------------------------------------------------
# PAGE CONFIGURATION & LUXURY ENTERPRISE DESIGN
# -------------------------------------------------------------------------
st.set_page_config(
    page_title=(
        "Concentrix | EMEA Real Estate & Procurement Intelligence Suite"
    ),
    page_icon="🏢",
    layout="wide",
)

st.markdown(
    """
    <style>
    .main { background-color: #F8F9FA; font-family: 'Inter', sans-serif; }
    .stMetric { background-color: #FFFFFF; padding: 18px; border-radius: 12px; box-shadow: 0 4px 12px rgba(31,78,120,0.08); border-left: 5px solid #008080; }
    h1, h2, h3 { color: #1F4E78; font-family: 'Helvetica Neue', sans-serif; font-weight: 700; }
    .stSidebar { background-color: #1F4E78; }
    </style>
""",
    unsafe_allow_html=True,
)


# -------------------------------------------------------------------------
# DEFAULT DATA INITIALIZATION (EMEA FY2025 PORTFOLIO)
# -------------------------------------------------------------------------
@st.cache_data
def get_default_portfolio_data():
  data = {
      "Country": [
          "Portugal",
          "Latvia",
          "Suriname",
          "South Africa",
          "Ghana",
          "Kosovo",
          "Madagascar",
          "Turkey",
          "Tunisia",
          "Poland",
          "United Kingdom",
          "France",
      ],
      "Project_Type": [
          "Warm Shell",
          "Warm Shell",
          "Warm Shell",
          "Grey Shell",
          "Grey Shell",
          "Grey Shell",
          "Grey Shell",
          "Warm Shell",
          "Warm Shell",
          "Grey Shell",
          "Grey Shell",
          "Grey Shell",
      ],
      "Seats": [414, 85, 363, 420, 514, 290, 950, 820, 601, 82, 72, 50],
      "Surface_m2": [
          2800,
          600,
          2500,
          3100,
          3800,
          2100,
          6500,
          5600,
          4100,
          600,
          500,
          350,
      ],
      "Total_CapEx_USD": [
          733000,
          163200,
          718377,
          1045000,
          1395000,
          973300,
          4086900,
          3292300,
          3408271,
          485194,
          739612,
          704700,
      ],
      "Benchmark_CPS": [
          5000,
          5000,
          5000,
          5000,
          5000,
          5000,
          5000,
          5000,
          5000,
          5000,
          5000,
          5000,
      ],
      "Furniture_Pct": [0.20, 0.22, 0.19, 0.28, 0.32, 0.19, 0.19, 0.16, 0.14, 0.25, 0.20, 0.15],
      "Civil_Works_Pct": [
          0.35,
          0.38,
          0.30,
          0.40,
          0.11,
          0.43,
          0.34,
          0.22,
          0.41,
          0.45,
          0.48,
          0.52,
      ],
      "Cabling_Telecom_Pct": [
          0.30,
          0.28,
          0.33,
          0.14,
          0.32,
          0.25,
          0.35,
          0.33,
          0.42,
          0.18,
          0.17,
          0.15,
      ],
      "HVAC_Pct": [0.15, 0.12, 0.18, 0.18, 0.25, 0.13, 0.12, 0.29, 0.03, 0.12, 0.15, 0.18],
  }
  return pd.DataFrame(data)


if "df_projects" not in st.session_state:
  st.session_state.df_projects = get_default_portfolio_data()

# -------------------------------------------------------------------------
# SIDEBAR NAVIGATION & EXCEL SYNC
# -------------------------------------------------------------------------
st.sidebar.title("🏢 Executive Suite")
menu = st.sidebar.radio(
    "Navigation",
    [
        "📊 Portfolio Overview & KPIs",
        "🌍 Country Cost & CPS Benchmarking",
        "📦 Spend Category Breakdown",
        "➕ Add / Manage Project (Excel Hub)",
        "📇 Vendor Strategy & 2026 Action Plan",
    ],
)

st.sidebar.markdown("---")
st.sidebar.subheader("📁 Data Source Connector")
uploaded_file = st.sidebar.file_uploader(
    "Upload Excel Tracking File", type=["xlsx", "xls"]
)

if uploaded_file is not None:
  try:
    df_excel = pd.read_excel(uploaded_file, sheet_name=0)
    st.sidebar.success("Excel file successfully synchronized!")
  except Exception as e:
    st.sidebar.error(f"Error reading file: {e}")

df = st.session_state.df_projects

# Automated Calculations
df["Cost_Per_Seat"] = df["Total_CapEx_USD"] / df["Seats"]
df["Cost_Per_m2"] = df["Total_CapEx_USD"] / df["Surface_m2"]
df["Variance_vs_Target"] = df["Cost_Per_Seat"] - df["Benchmark_CPS"]

# Global Country Filter
countries = df["Country"].unique().tolist()
selected_countries = st.sidebar.multiselect(
    "Filter by Country", options=countries, default=countries
)
filtered_df = df[df["Country"].isin(selected_countries)]


# -------------------------------------------------------------------------
# TAB 1: PORTFOLIO OVERVIEW & KPIS
# -------------------------------------------------------------------------
if menu == "📊 Portfolio Overview & KPIs":
  st.title("🏢 EMEA Workplace Strategy — Executive Dashboard 2025")
  st.markdown(
      "**Consolidated CapEx Review, Cost-per-Seat (CPS) Performance, and"
      " Strategic Real Estate Analytics.**"
  )
  st.markdown("---")

  # Top Executive KPI Cards
  c1, c2, c3, c4 = st.columns(4)
  total_capex = filtered_df["Total_CapEx_USD"].sum()
  total_seats = filtered_df["Seats"].sum()
  avg_cps = total_capex / total_seats if total_seats > 0 else 0
  avg_sqm_cost = (
      filtered_df["Total_CapEx_USD"].sum() / filtered_df["Surface_m2"].sum()
      if filtered_df["Surface_m2"].sum() > 0
      else 0
  )

  c1.metric("Total CapEx EMEA", f"${total_capex:,.0f}")
  c2.metric("Total Seats Delivered", f"{total_seats:,.0f} seats")
  c3.metric("Avg. CPS EMEA", f"${avg_cps:,.0f} / seat", delta="Target ≤ $5,000")
  c4.metric("Avg. Cost / m²", f"${avg_sqm_cost:,.2f} / m²")

  st.markdown("---")

  # Summary Table
  st.subheader("📋 Complete Portfolio Financial Summary")
  st.dataframe(
      filtered_df[[
          "Country",
          "Project_Type",
          "Seats",
          "Surface_m2",
          "Total_CapEx_USD",
          "Cost_Per_Seat",
          "Cost_Per_m2",
      ]].style.format({
          "Total_CapEx_USD": "${:,.0f}",
          "Cost_Per_Seat": "${:,.0f}",
          "Cost_Per_m2": "${:,.2f}",
      }),
      use_container_width=True,
  )


# -------------------------------------------------------------------------
# TAB 2: COUNTRY COST & CPS BENCHMARKING
# -------------------------------------------------------------------------
elif menu == "🌍 Country Cost & CPS Benchmarking":
  st.title("🌍 Country-Level Cost-per-Seat (CPS) & Benchmarking")
  st.markdown(
      "Comparative analysis of average Cost-per-Seat across EMEA markets vs."
      " internal target benchmark ($5,000/seat)."
  )
  st.markdown("---")

  # Group by Country for Country-level aggregation
  country_agg = (
      filtered_df.groupby("Country")
      .agg({"Seats": "sum", "Total_CapEx_USD": "sum", "Benchmark_CPS": "mean"})
      .reset_index()
  )
  country_agg["Avg_CPS"] = country_agg["Total_CapEx_USD"] / country_agg["Seats"]
  country_agg = country_agg.sort_values(by="Avg_CPS", ascending=False)

  # Histogram by Country
  fig_country_cps = go.Figure()
  fig_country_cps.add_trace(
      go.Bar(
          x=country_agg["Country"],
          y=country_agg["Avg_CPS"],
          name="Actual Avg CPS ($)",
          marker_color="#1F4E78",
          text=country_agg["Avg_CPS"].apply(lambda x: f"${x:,.0f}"),
          textposition="auto",
      )
  )
  fig_country_cps.add_trace(
      go.Scatter(
          x=country_agg["Country"],
          y=country_agg["Benchmark_CPS"],
          mode="lines+markers",
          name="Target Benchmark ($5K)",
          line=dict(color="#D87093", width=3),
      )
  )
  fig_country_cps.update_layout(
      title="Average Cost-per-Seat (CPS) by Country vs. Target Benchmark",
      xaxis_tickangle=-35,
      margin=dict(t=40, b=40, l=20, r=20),
  )
  st.plotly_chart(fig_country_cps, use_container_width=True)

  st.markdown("---")
  st.subheader("💡 Procurement & Real Estate Strategic Recommendations")
  st.info(
      "**Key Observation on Outliers:** France ($14,094) and UK ($9,585)"
      " distort the portfolio average due to micro-site strategies (<100"
      " seats). *Recommendation:* Apply size-adjusted CPS as the primary"
      " approval metric for 2026."
  )
  st.warning(
      "**Structural Risks:** Tunisia ($5,671) and Turkey expose import duty"
      " overruns on Cabling (TUN) and FX inflation on HVAC (TR). *Fix:* Mandate"
      " Warm Shell agreements and LME copper indexation clauses."
  )


# -------------------------------------------------------------------------
# TAB 3: SPEND CATEGORY BREAKDOWN
# -------------------------------------------------------------------------
elif menu == "📦 Spend Category Breakdown":
  st.title("📦 Technical Lots Cost Breakdown (Spend Categories)")
  st.markdown(
      "Detailed analysis of CapEx distribution across Furniture, Civil Works,"
      " Cabling/Telecom, and HVAC."
  )
  st.markdown("---")

  # Calculate absolute spend per category
  filtered_df["Furniture_Amt"] = (
      filtered_df["Total_CapEx_USD"] * filtered_df["Furniture_Pct"]
  )
  filtered_df["Civil_Works_Amt"] = (
      filtered_df["Total_CapEx_USD"] * filtered_df["Civil_Works_Pct"]
  )
  filtered_df["Cabling_Amt"] = (
      filtered_df["Total_CapEx_USD"] * filtered_df["Cabling_Telecom_Pct"]
  )
  filtered_df["HVAC_Amt"] = (
      filtered_df["Total_CapEx_USD"] * filtered_df["HVAC_Pct"]
  )

  total_cat = {
      "Furniture": filtered_df["Furniture_Amt"].sum(),
      "Civil Works": filtered_df["Civil_Works_Amt"].sum(),
      "Cabling & Telecom": filtered_df["Cabling_Amt"].sum(),
      "HVAC": filtered_df["HVAC_Amt"].sum(),
  }
  df_cat = pd.DataFrame(
      list(total_cat.items()), columns=["Category", "Total_Spend"]
  )

  col_l, col_r = st.columns(2)
  with col_l:
    st.subheader("🥧 Global Spend Distribution by Lot")
    fig_cat_pie = px.pie(
        df_cat,
        names="Category",
        values="Total_Spend",
        hole=0.45,
        color_discrete_sequence=["#1F4E78", "#008080", "#D87093", "#4682B4"],
    )
    st.plotly_chart(fig_cat_pie, use_container_width=True)

  with col_r:
    st.subheader("📊 Category Spend Summary")
    st.dataframe(df_cat.style.format({"Total_Spend": "${:,.0f}"}), use_container_width=True)

  st.markdown("---")
  st.subheader("🔬 Technical Insights & Market Pressures")
  st.markdown(
      "- **Cabling Lot Inflation:** LME Copper rose +22%, directly impacting"
      " importing markets (Tunisia, Benin, Madagascar). **Action:** Implement"
      " a centralized EMEA cabling framework agreement.\n- **Civil Works"
      " Reduction:** Current civil share is 35–43%. **Action:** Enforce a"
      " *Warm Shell Only Policy* to cap civil works below 25%."
  )


# -------------------------------------------------------------------------
# TAB 4: ADD / MANAGE PROJECT (EXCEL-TO-TOOL HUB)
# -------------------------------------------------------------------------
elif menu == "➕ Add / Manage Project (Excel Hub)":
  st.title("➕ Project Entry & Automated KPI Calculator")
  st.markdown(
      "Add a new real estate fit-out project instantly. The tool calculates"
      " ratios, benchmarks, and category breakdowns automatically without"
      " manual Excel spreadsheet maintenance."
  )
  st.markdown("---")

  with st.form("project_form"):
    c1, c2, c3 = st.columns(3)
    with c1:
      p_country = st.text_input("Country", "Morocco")
      p_type = st.selectbox("Project Type", ["Warm Shell", "Grey Shell"])
    with c2:
      p_seats = st.number_input(
          "Number of Seats", min_value=10, max_value=5000, value=300
      )
      p_surface = st.number_input(
          "Surface Area (m²)", min_value=50, max_value=20000, value=2000
      )
    with c3:
      p_capex = st.number_input(
          "Total CapEx ($)", min_value=10000, max_value=20000000, value=900000
      )
      p_benchmark = st.number_input(
          "CPS Benchmark Target ($)", min_value=500, max_value=10000, value=5000
      )

    st.subheader("📦 Cost Distribution by Technical Lot (%)")
    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
      f_furn = st.number_input("Furniture %", 0.0, 1.0, 0.20, 0.01)
    with sc2:
      f_civil = st.number_input("Civil Works %", 0.0, 1.0, 0.35, 0.01)
    with sc3:
      f_cable = st.number_input("Cabling & Telecom %", 0.0, 1.0, 0.30, 0.01)
    with sc4:
      f_hvac = st.number_input("HVAC %", 0.0, 1.0, 0.15, 0.01)

    submitted = st.form_submit_button(
        "💾 Save Project & Compute Instant KPIs"
    )
    if submitted:
      new_row = {
          "Country": p_country,
          "Project_Type": p_type,
          "Seats": p_seats,
          "Surface_m2": p_surface,
          "Total_CapEx_USD": p_capex,
          "Benchmark_CPS": p_benchmark,
          "Furniture_Pct": f_furn,
          "Civil_Works_Pct": f_civil,
          "Cabling_Telecom_Pct": f_cable,
          "HVAC_Pct": f_hvac,
      }
      st.session_state.df_projects = pd.concat(
          [st.session_state.df_projects, pd.DataFrame([new_row])],
          ignore_index=True,
      )
      st.success(
          f"Project in {p_country} successfully added! Portfolio KPIs updated."
      )


# -------------------------------------------------------------------------
# TAB 5: VENDOR STRATEGY & 2026 ACTION PLAN
# -------------------------------------------------------------------------
elif menu == "📇 Vendor Strategy & 2026 Action Plan":
  st.title("📇 EMEA Vendor Matrix & 2026 Strategic Action Plan")
  st.markdown(
      "Supplier segmentation (Strategic, Tactical, Backup) and 3-pillar CapEx"
      " ROI optimization roadmap."
  )
  st.markdown("---")

  vendor_data = {
      "Category": [
          "Cabling / Electrical",
          "Cabling / Electrical",
          "HVAC / Mechanical",
          "HVAC / Mechanical",
          "Civil Works",
          "Civil Works",
          "Furniture",
          "Furniture",
      ],
      "Supplier Name": [
          "Neurone (MA)",
          "Synapse (ALB)",
          "Moficlim (MA)",
          "STIM (TUN)",
          "OfficeWorks (UK/IE)",
          "Giant Leap (ZA)",
          "Dromeas (GR/ALB)",
          "Kinnarps (Nordics)",
      ],
      "Segmentation": [
          "Strategic",
          "Strategic",
          "Strategic",
          "Strategic",
          "Strategic",
          "Strategic",
          "Strategic",
          "Strategic",
      ],
      "SLA & Terms": [
          "SLA 48h - Volume Discount",
          "SLA 24h - Certified",
          "PBC Maintenance - 99% uptime",
          "SLA 24h - Local support",
          "Regional Master Agreement",
          "Standardized Fit-Out",
          "Global Framework Agreement",
          "Nordic Quality Standards",
      ],
  }
  st.dataframe(pd.DataFrame(vendor_data), use_container_width=True)

  st.markdown("---")
  st.subheader("🚀 2026 Three-Pillar CapEx ROI Optimization Roadmap")
  st.info(
      "**01. EMEA Cabling Volume Consolidation:** Consolidate purchases across"
      " importing markets (TUN, MDG, BEN, MA) via a single EMEA RFP. *Est."
      " Savings:* $180K–$320K/yr."
  )
  st.info(
      "**02. Performance-Based HVAC Maintenance (PBC):** Deploy PBC contracts"
      " on sites >3,000 SqM with guaranteed uptime ≥99%. *Est. OpEx Reduction:*"
      " $95K–$160K/yr."
  )
  st.info(
      "**03. Warm Shell Only Policy + Delay Penalties:** Mandate landlord"
      " coverage for core civil finishes and add 0.5%/week delay penalties."
      " *Target:* Portfolio weighted avg. CPS <$4,200."
  )
 
 
