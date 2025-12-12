import re
import pandas as pd
import streamlit as st
import plotly.express as px

LBR_URL = "https://www.federalreserve.gov/releases/lbr/current/"

st.set_page_config(page_title="Thomas Selassie – Fed LBR Banks Dashboard", layout="wide")

st.title("Thomas Selassie – Fed LBR Large Commercial Banks Dashboard")
st.caption(
    "Source: Federal Reserve 'Large Commercial Banks (LBR) – Current release'. "
    "This app parses the ranked bank table and updates when the Fed updates the page."
)

@st.cache_data(ttl=60 * 60)
def load_lbr_tables(url: str) -> list[pd.DataFrame]:
    # The LBR page contains one or more HTML tables.
    # pandas.read_html is the simplest + robust way to pull them.
    return pd.read_html(url)

@st.cache_data(ttl=60 * 60)
def load_lbr_df(url: str) -> pd.DataFrame:
    tables = load_lbr_tables(url)

    # The first big table on the page is typically the ranked list with columns like:
    # Bank Name / Holding Co Name, Nat'l Rank, Bank ID, Bank Location, Charter, Consol Assets (Mil $), etc.
    # We'll pick the table that contains "Nat'l Rank" and "Consol Assets".
    target = None
    for t in tables:
        cols = [str(c).lower() for c in t.columns]
        if any("rank" in c for c in cols) and any("consol" in c or "assets" in c for c in cols):
            target = t
            break

    if target is None:
        # fallback: take the largest table
        target = max(tables, key=lambda x: x.shape[0] * x.shape[1])

    df = target.copy()

    # Clean column names
    df.columns = [str(c).strip() for c in df.columns]

    # Try to standardize important columns
    # The page uses "Consol Assets (Mil $)" and "Domestic Assets (Mil $)"
    def find_col(patterns):
        for c in df.columns:
            cl = c.lower()
            if any(p in cl for p in patterns):
                return c
        return None

    col_bank = df.columns[0]  # usually "Bank Name / Holding Co Name"
    col_rank = find_col(["rank"])
    col_loc  = find_col(["location"])
    col_char = find_col(["charter"])
    col_assets = find_col(["consol assets", "consolidated assets", "consol"])
    col_dom_assets = find_col(["domestic assets"])

    # Parse numeric assets columns (remove commas)
    for c in [col_assets, col_dom_assets]:
        if c and c in df.columns:
            df[c] = (
                df[c].astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(r"[^\d\.]", "", regex=True)
            )
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Derive State from "CITY, ST" in location (if present)
    if col_loc and col_loc in df.columns:
        df["State"] = (
            df[col_loc].astype(str)
            .str.extract(r",\s*([A-Z]{2})\s*$", expand=False)
        )
    else:
        df["State"] = None

    # Make friendly column names (keep originals too)
    rename_map = {}
    if col_bank: rename_map[col_bank] = "Bank / Holding Company"
    if col_rank: rename_map[col_rank] = "National Rank"
    if col_loc:  rename_map[col_loc]  = "Location"
    if col_char: rename_map[col_char] = "Charter"
    if col_assets: rename_map[col_assets] = "Consolidated Assets (Mil $)"
    if col_dom_assets: rename_map[col_dom_assets] = "Domestic Assets (Mil $)"

    df = df.rename(columns=rename_map)

    # Ensure rank numeric when possible
    if "National Rank" in df.columns:
        df["National Rank"] = pd.to_numeric(df["National Rank"], errors="coerce")

    return df


df = load_lbr_df(LBR_URL)

with st.sidebar:
    st.header("Filters")

    search = st.text_input("Search bank / holding company", "")

    states = sorted([s for s in df["State"].dropna().unique().tolist() if isinstance(s, str)])
    state = st.selectbox("State (optional)", ["All"] + states)

    # Charter and IBF often exist on the table
    charter_vals = []
    if "Charter" in df.columns:
        charter_vals = sorted(df["Charter"].dropna().astype(str).unique().tolist())
    charter = st.selectbox("Charter (optional)", ["All"] + charter_vals) if charter_vals else "All"

    ibf_col = None
    for c in df.columns:
        if str(c).strip().upper() == "IBF":
            ibf_col = c
            break
    ibf = st.selectbox("IBF (optional)", ["All", "Y", "N"]) if ibf_col else "All"

    top_n = st.slider("Top N banks", 10, min(200, len(df)), 50)

    # Assets slider
    assets_col = "Consolidated Assets (Mil $)" if "Consolidated Assets (Mil $)" in df.columns else None
    if assets_col and df[assets_col].notna().any():
        a_min = float(df[assets_col].min())
        a_max = float(df[assets_col].max())
        assets_range = st.slider(
            "Consolidated Assets range (Mil $)",
            min_value=float(max(0, a_min)),
            max_value=float(a_max),
            value=(float(max(0, a_min)), float(a_max)),
        )
    else:
        assets_range = None

filtered = df.copy()

if search.strip():
    filtered = filtered[filtered["Bank / Holding Company"].astype(str).str.contains(search, case=False, na=False)]

if state != "All":
    filtered = filtered[filtered["State"] == state]

if charter != "All" and "Charter" in filtered.columns:
    filtered = filtered[filtered["Charter"].astype(str) == charter]

if ibf_col and ibf != "All":
    filtered = filtered[filtered[ibf_col].astype(str).str.upper() == ibf]

if assets_range and "Consolidated Assets (Mil $)" in filtered.columns:
    lo, hi = assets_range
    filtered = filtered[
        (filtered["Consolidated Assets (Mil $)"] >= lo) &
        (filtered["Consolidated Assets (Mil $)"] <= hi)
    ]

# Limit to top N by rank if present, else by assets
if "National Rank" in filtered.columns and filtered["National Rank"].notna().any():
    filtered = filtered.sort_values("National Rank").head(top_n)
elif "Consolidated Assets (Mil $)" in filtered.columns:
    filtered = filtered.sort_values("Consolidated Assets (Mil $)", ascending=False).head(top_n)
else:
    filtered = filtered.head(top_n)

# --- Layout ---
col1, col2 = st.columns([1.1, 1.2], gap="large")

with col1:
    st.subheader("Summary")
    st.metric("Banks shown", int(len(filtered)))

    if "Consolidated Assets (Mil $)" in filtered.columns and filtered["Consolidated Assets (Mil $)"].notna().any():
        st.metric("Total consolidated assets (Mil $)", f"{filtered['Consolidated Assets (Mil $)'].sum():,.0f}")
        st.metric("Median assets (Mil $)", f"{filtered['Consolidated Assets (Mil $)'].median():,.0f}")

    st.subheader("Table")
    show_cols = [c for c in [
        "National Rank",
        "Bank / Holding Company",
        "Location",
        "Charter",
        "Consolidated Assets (Mil $)",
        "Domestic Assets (Mil $)",
        "State",
        ibf_col
    ] if c and c in filtered.columns]

    st.dataframe(
        filtered[show_cols].reset_index(drop=True),
        use_container_width=True,
        height=520
    )

with col2:
    st.subheader("Charts")

    if "Consolidated Assets (Mil $)" in filtered.columns and filtered["Consolidated Assets (Mil $)"].notna().any():
        # Top banks bar
        top_bar = filtered.sort_values("Consolidated Assets (Mil $)", ascending=False).head(15)
        fig1 = px.bar(
            top_bar,
            x="Consolidated Assets (Mil $)",
            y="Bank / Holding Company",
            orientation="h",
            title="Top 15 by Consolidated Assets",
        )
        fig1.update_layout(height=420, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig1, use_container_width=True)

        # Distribution
        fig2 = px.histogram(
            filtered,
            x="Consolidated Assets (Mil $)",
            nbins=30,
            title="Distribution of Consolidated Assets (Mil $)",
        )
        fig2.update_layout(height=320)
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Assets column not detected on this release page format.")
