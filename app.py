import re
import pandas as pd
import streamlit as st
import plotly.express as px
import requests

LBR_URL = "https://www.federalreserve.gov/releases/lbr/current/"

# -------------------------------
# BANK LOGOS (domain map)
# Uses Clearbit logo endpoint: https://logo.clearbit.com/<domain>
# Matching is substring-based to handle long Fed bank names like:
# "JPMORGAN CHASE BK NA/JPMORGAN CHASE & CO"
# -------------------------------
BANK_DOMAIN_MAP = {
    "JPMORGAN": "chase.com",
    "CHASE": "chase.com",
    "BANK OF AMERICA": "bankofamerica.com",
    "WELLS FARGO": "wellsfargo.com",
    "CITIBANK": "citi.com",
    "CITIGROUP": "citi.com",
    "CAPITAL ONE": "capitalone.com",
    "GOLDMAN SACHS": "goldmansachs.com",
    "MORGAN STANLEY": "morganstanley.com",
    "PNC": "pnc.com",
    "TRUIST": "truist.com",
    "U S BK": "usbank.com",
    "U.S. BK": "usbank.com",
    "US BK": "usbank.com",
    "US BANK": "usbank.com",
    "BANK OF NY MELLON": "bnymellon.com",
    "NEW YORK MELLON": "bnymellon.com",
    "BNY MELLON": "bnymellon.com",
    "STATE STREET": "statestreet.com",
    "TD BK": "td.com",
    "TD BANK": "td.com",
    "FIFTH THIRD": "53.com",
    "KEYBANK": "key.com",
    "HUNTINGTON": "huntington.com",
    "REGIONS": "regions.com",
    "ALLY": "ally.com",
    "CITIZENS": "citizensbank.com",
    "M&T": "mtb.com",
    "SANTANDER": "santanderbank.com",
    "BMO": "bmo.com",
}

def bank_logo_url(bank_name: str) -> str | None:
    n = (bank_name or "").upper()
    n = re.sub(r"\s+", " ", n).strip()
    for key, domain in BANK_DOMAIN_MAP.items():
        if key in n:
            return f"https://logo.clearbit.com/{domain}"
    return None

def short_bank_label(bank_name: str) -> str:
    # Keep it readable for captions
    if not bank_name:
        return ""
    s = str(bank_name).split("/")[0].strip()
    s = re.sub(r"\s+", " ", s)
    return s[:22] + ("…" if len(s) > 22 else "")


# -------------------------------
# PAGE CONFIG + STYLE
# -------------------------------
st.set_page_config(page_title="Thomas Selassie – Fed LBR Banks Dashboard", layout="wide")

st.title("Thomas Selassie – Fed LBR Large Commercial Banks Dashboard")
st.caption(
    "Source: Federal Reserve 'Large Commercial Banks (LBR) – current release'. "
    "This app parses the ranked bank table and updates whenever the Fed updates the page."
)

# Light UI polish (safe HTML)
st.markdown(
    """
    <style>
      .block-container { padding-top: 1.2rem; }
      h1 { letter-spacing: -0.5px; }
      .stMetric { border-radius: 14px; }
    </style>
    """,
    unsafe_allow_html=True
)

# -------------------------------
# DATA LOADERS
# -------------------------------
@st.cache_data(ttl=60 * 60)
def fetch_html(url: str) -> str:
    # Streamlit Cloud sometimes blocks direct pandas.read_html(url)
    # so we fetch HTML with a browser-like user agent first.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text

@st.cache_data(ttl=60 * 60)
def load_lbr_df(url: str) -> pd.DataFrame:
    html = fetch_html(url)
    tables = pd.read_html(html)

    # Pick the most likely ranked bank table
    target = None
    for t in tables:
        cols = [str(c).lower() for c in t.columns]
        if any("rank" in c for c in cols) and any(("consol" in c) or ("assets" in c) for c in cols):
            target = t
            break

    if target is None:
        target = max(tables, key=lambda x: x.shape[0] * x.shape[1])

    df = target.copy()
    df.columns = [str(c).strip() for c in df.columns]

    def find_col(patterns):
        for c in df.columns:
            cl = str(c).lower()
            if any(p in cl for p in patterns):
                return c
        return None

    col_bank = df.columns[0]
    col_rank = find_col(["rank"])
    col_loc  = find_col(["location"])
    col_char = find_col(["charter"])
    col_assets = find_col(["consol assets", "consolidated assets", "consol"])
    col_dom_assets = find_col(["domestic assets"])
    col_ibf = None
    for c in df.columns:
        if str(c).strip().upper() == "IBF":
            col_ibf = c
            break

    # Clean numeric columns
    for c in [col_assets, col_dom_assets]:
        if c and c in df.columns:
            df[c] = (
                df[c].astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(r"[^\d\.]", "", regex=True)
            )
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Derive State from location like "CITY, ST"
    if col_loc and col_loc in df.columns:
        df["State"] = df[col_loc].astype(str).str.extract(r",\s*([A-Z]{2})\s*$", expand=False)
    else:
        df["State"] = None

    rename_map = {}
    if col_bank: rename_map[col_bank] = "Bank / Holding Company"
    if col_rank: rename_map[col_rank] = "National Rank"
    if col_loc:  rename_map[col_loc]  = "Location"
    if col_char: rename_map[col_char] = "Charter"
    if col_assets: rename_map[col_assets] = "Consolidated Assets (Mil $)"
    if col_dom_assets: rename_map[col_dom_assets] = "Domestic Assets (Mil $)"
    if col_ibf: rename_map[col_ibf] = "IBF"

    df = df.rename(columns=rename_map)

    if "National Rank" in df.columns:
        df["National Rank"] = pd.to_numeric(df["National Rank"], errors="coerce")

    # Logo column
    if "Bank / Holding Company" in df.columns:
        df["Logo"] = df["Bank / Holding Company"].astype(str).apply(bank_logo_url)
        df["Short Name"] = df["Bank / Holding Company"].astype(str).apply(short_bank_label)
    else:
        df["Logo"] = None
        df["Short Name"] = ""

    return df


# Load data with friendly failure message
try:
    df = load_lbr_df(LBR_URL)
except Exception as e:
    st.error("Could not load the Federal Reserve LBR page right now.")
    st.info("If this persists, the Fed site may be temporarily blocking requests from Streamlit Cloud.")
    st.exception(e)
    st.stop()


# -------------------------------
# SIDEBAR FILTERS
# -------------------------------
with st.sidebar:
    st.header("Filters")

    search = st.text_input("Search bank / holding company", "")

    states = sorted([s for s in df["State"].dropna().unique().tolist() if isinstance(s, str)])
    state = st.selectbox("State (optional)", ["All"] + states)

    charter_vals = []
    if "Charter" in df.columns:
        charter_vals = sorted(df["Charter"].dropna().astype(str).unique().tolist())
    charter = st.selectbox("Charter (optional)", ["All"] + charter_vals) if charter_vals else "All"

    ibf = st.selectbox("IBF (optional)", ["All", "Y", "N"]) if "IBF" in df.columns else "All"

    top_n = st.slider("Top N banks", 10, min(200, len(df)), 50)

    assets_col = "Consolidated Assets (Mil $)" if "Consolidated Assets (Mil $)" in df.columns else None
    assets_range = None
    if assets_col and df[assets_col].notna().any():
        a_min = float(df[assets_col].min())
        a_max = float(df[assets_col].max())
        assets_range = st.slider(
            "Consolidated Assets range (Mil $)",
            min_value=float(max(0, a_min)),
            max_value=float(a_max),
            value=(float(max(0, a_min)), float(a_max)),
        )


# -------------------------------
# APPLY FILTERS
# -------------------------------
filtered = df.copy()

if search.strip():
    filtered = filtered[filtered["Bank / Holding Company"].astype(str).str.contains(search, case=False, na=False)]

if state != "All":
    filtered = filtered[filtered["State"] == state]

if charter != "All" and "Charter" in filtered.columns:
    filtered = filtered[filtered["Charter"].astype(str) == charter]

if ibf != "All" and "IBF" in filtered.columns:
    filtered = filtered[filtered["IBF"].astype(str).str.upper() == ibf]

if assets_range and "Consolidated Assets (Mil $)" in filtered.columns:
    lo, hi = assets_range
    filtered = filtered[
        (filtered["Consolidated Assets (Mil $)"] >= lo) &
        (filtered["Consolidated Assets (Mil $)"] <= hi)
    ]

# Limit to top N
if "National Rank" in filtered.columns and filtered["National Rank"].notna().any():
    filtered = filtered.sort_values("National Rank").head(top_n)
elif "Consolidated Assets (Mil $)" in filtered.columns:
    filtered = filtered.sort_values("Consolidated Assets (Mil $)", ascending=False).head(top_n)
else:
    filtered = filtered.head(top_n)


# -------------------------------
# TOP LOGOS ROW (looks very polished)
# -------------------------------
st.subheader("Top Banks (Logos)")
top_logo_df = (
    filtered.sort_values("Consolidated Assets (Mil $)", ascending=False)
    if "Consolidated Assets (Mil $)" in filtered.columns else filtered
).head(8)

logo_cols = st.columns(8)
for i, (_, r) in enumerate(top_logo_df.iterrows()):
    with logo_cols[i]:
        url = r.get("Logo")
        name = r.get("Short Name", "")
        if isinstance(url, str) and url:
            st.image(url, width=56)
        st.caption(name)


# -------------------------------
# MAIN LAYOUT
# -------------------------------
col1, col2 = st.columns([1.15, 1.25], gap="large")

with col1:
    st.subheader("Summary")
    st.metric("Banks shown", int(len(filtered)))

    if "Consolidated Assets (Mil $)" in filtered.columns and filtered["Consolidated Assets (Mil $)"].notna().any():
        st.metric("Total consolidated assets (Mil $)", f"{filtered['Consolidated Assets (Mil $)'].sum():,.0f}")
        st.metric("Median assets (Mil $)", f"{filtered['Consolidated Assets (Mil $)'].median():,.0f}")

    st.subheader("Selected bank")
    if len(filtered) > 0:
        row = filtered.iloc[0]
        bank_name = str(row.get("Bank / Holding Company", ""))
        logo = row.get("Logo", None)

        cA, cB = st.columns([0.18, 0.82])
        with cA:
            if isinstance(logo, str) and logo:
                st.image(logo, width=90)
            else:
                st.write("")
        with cB:
            st.markdown(f"### {bank_name}")
            st.write(f"**Location:** {row.get('Location', '')}")
            if "Charter" in filtered.columns:
                st.write(f"**Charter:** {row.get('Charter', '')}")
            if "IBF" in filtered.columns:
                st.write(f"**IBF:** {row.get('IBF', '')}")
            if "Consolidated Assets (Mil $)" in filtered.columns:
                val = row.get("Consolidated Assets (Mil $)", None)
                if pd.notna(val):
                    st.write(f"**Consolidated Assets (Mil $):** {val:,.0f}")

    st.subheader("Table")
    show_cols = [c for c in [
        "National Rank",
        "Bank / Holding Company",
        "Location",
        "State",
        "Charter",
        "IBF",
        "Consolidated Assets (Mil $)",
        "Domestic Assets (Mil $)",
    ] if c in filtered.columns]

    st.dataframe(
        filtered[show_cols].reset_index(drop=True),
        use_container_width=True,
        height=540
    )

with col2:
    st.subheader("Charts")

    if "Consolidated Assets (Mil $)" in filtered.columns and filtered["Consolidated Assets (Mil $)"].notna().any():
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

        fig2 = px.histogram(
            filtered,
            x="Consolidated Assets (Mil $)",
            nbins=30,
            title="Distribution of Consolidated Assets (Mil $)",
        )
        fig2.update_layout(height=320)
        st.plotly_chart(fig2, use_container_width=True)

        st.caption("Logos appear when a known bank domain matches the bank name (via Clearbit logo endpoint).")
    else:
        st.info("Assets column not detected on this release page format.")
