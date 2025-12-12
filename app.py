import re
import pandas as pd
import streamlit as st
import plotly.express as px
import requests

LBR_URL = "https://www.federalreserve.gov/releases/lbr/current/"

# --------- BANK LOGO HELPERS ---------
# Uses Clearbit logo endpoint: https://logo.clearbit.com/<domain>
# Add more banks/domains over time as needed.
BANK_DOMAIN_MAP = {
    # Mega banks / well-known
    "JPMORGAN CHASE": "chase.com",
    "BANK OF AMERICA": "bankofamerica.com",
    "WELLS FARGO": "wellsfargo.com",
    "CITIBANK": "citi.com",
    "GOLDMAN SACHS": "goldmansachs.com",
    "MORGAN STANLEY": "morganstanley.com",
    "PNC": "pnc.com",
    "TRUIST": "truist.com",
    "U.S. BANK": "usbank.com",
    "US BANK": "usbank.com",
    "CAPITAL ONE": "capitalone.com",
    "TD BANK": "td.com",
    "BANK OF NEW YORK MELLON": "bnymellon.com",
    "BNY MELLON": "bnymellon.com",
    "STATE STREET": "statestreet.com",
    "FIFTH THIRD": "53.com",
    "KEYBANK": "key.com",
    "CITIZENS": "citizensbank.com",
    "HUNTINGTON": "huntington.com",
    "REGIONS": "regions.com",
    "ALLY": "ally.com",
    "AMEX": "americanexpress.com",
    "AMERICAN EXPRESS": "americanexpress.com",
    "M&T": "mtb.com",
    "SANTANDER": "santanderbank.com",
    "BMO": "bmo.com",
    # Add more as you see them in the table
}

def normalize_name(name: str) -> str:
    name = (name or "").upper()
    name = re.sub(r"\s+", " ", name).strip()
    return name

def bank_logo_url(bank_name: str) -> str | None:
    """
    Return a logo URL if we can infer a domain from the bank name.
    Uses simple keyword matching against BANK_DOMAIN_MAP keys.
    """
    n = normalize_name(bank_name)
    for key, domain in BANK_DOMAIN_MAP.items():
        if key in n:
            return f"https://logo.clearbit.com/{domain}"
    return None


# --------- STREAMLIT PAGE ---------
st.set_page_config(page_title="Thomas Selassie – Fed LBR Banks Dashboard", layout="wide")

st.title("Thomas Selassie – Fed LBR Large Commercial Banks Dashboard")
st.caption(
    "Source: Federal Reserve 'Large Commercial Banks (LBR) – current release'. "
    "This app parses the ranked bank table and updates whenever the Fed updates the page."
)

# --------- DATA LOADERS ---------
@st.cache_data(ttl=60 * 60)
def load_lbr_tables(url: str) -> list[pd.DataFrame]:
    # Fix for Streamlit Cloud HTTPError: fetch HTML with requests + browser UA, then parse
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    html = r.text

    # Parse tables from HTML string
    return pd.read_html(html)

@st.cache_data(ttl=60 * 60)
def load_lbr_df(url: str) -> pd.DataFrame:
    tables = load_lbr_tables(url)

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

    col_bank = df.columns[0]  # usually Bank Name / Holding Co Name
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

    # Add Logo URL column
    if "Bank / Holding Company" in df.columns:
        df["Logo"] = df["Bank / Holding Company"].astype(str).apply(bank_logo_url)
    else:
        df["Logo"] = None

    return df

# Load data
try:
    df = load_lbr_df(LBR_URL)
except Exception as e:
    st.error("Could not load the Federal Reserve LBR page right now.")
    st.exception(e)
    st.stop()

# --------- SIDEBAR FILTERS ---------
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

# Apply filters
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

# Limit to top N by rank if available, else by assets
if "National Rank" in filtered.columns and filtered["National Rank"].notna().any():
    filtered = filtered.sort_values("National Rank").head(top_n)
elif "Consolidated Assets (Mil $)" in filtered.columns:
    filtered = filtered.sort_values("Consolidated Assets (Mil $)", ascending=False).head(top_n)
else:
    filtered = filtered.head(top_n)

# --------- MAIN LAYOUT ---------
col1, col2 = st.columns([1.15, 1.25], gap="large")

with col1:
    st.subheader("Summary")
    st.metric("Banks shown", int(len(filtered)))

    if "Consolidated Assets (Mil $)" in filtered.columns and filtered["Consolidated Assets (Mil $)"].notna().any():
        st.metric("Total consolidated assets (Mil $)", f"{filtered['Consolidated Assets (Mil $)'].sum():,.0f}")
        st.metric("Median assets (Mil $)", f"{filtered['Consolidated Assets (Mil $)'].median():,.0f}")

    # Selected bank "card" with logo (first row of filtered)
    st.subheader("Selected bank")
    if len(filtered) > 0:
        row = filtered.iloc[0]
        bank_name = str(row.get("Bank / Holding Company", ""))
        logo = row.get("Logo", None)

        cA, cB = st.columns([0.2, 0.8])
        with cA:
            if isinstance(logo, str) and logo:
                st.image(logo, width=70)
            else:
                st.write("")

        with cB:
            st.markdown(f"### {bank_name}")
            loc = row.get("Location", "")
            st.write(f"**Location:** {loc}")
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

        st.caption("Logos: shown when a matching bank domain is known (via Clearbit logo endpoint).")
    else:
        st.info("Assets column not detected on this release page format.")
