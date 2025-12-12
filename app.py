import re
import urllib.parse
import pandas as pd
import streamlit as st
import plotly.express as px
import requests

st.set_page_config(page_title="Thomas Selassie – Fed LBR Banks", layout="wide")
LBR_URL = "https://www.federalreserve.gov/releases/lbr/current/"

# -------------------------
# Formatting helpers
# -------------------------
def format_assets_mil(mil):
    """Input is millions of dollars. Output as $M/$B/$T."""
    if pd.isna(mil):
        return "N/A"
    if mil >= 1_000_000:
        return f"${mil/1_000_000:.2f}T"
    if mil >= 1_000:
        return f"${mil/1_000:.2f}B"
    return f"${mil:,.0f}M"

def mil_to_dollars(mil):
    """Millions -> dollars"""
    return mil * 1_000_000

def clean_columns(cols):
    cleaned = []
    for c in cols:
        if isinstance(c, tuple):
            c = " ".join([str(x) for x in c if x and str(x) != "nan"])
        cleaned.append(str(c).strip())
    return cleaned

def find_col_any(cols, any_patterns):
    cols_l = [str(c).lower() for c in cols]
    for i, c in enumerate(cols_l):
        if any(p in c for p in any_patterns):
            return cols[i]
    return None

def to_number_safe(series: pd.Series) -> pd.Series:
    """
    Converts messy numeric strings like '3,813,431', '—', '', '$1,200' to floats.
    Blanks become NaN (no crash).
    """
    s = series.astype(str).str.strip()
    s = s.replace({"": pd.NA, "—": pd.NA, "-": pd.NA, "nan": pd.NA, "None": pd.NA})
    s = s.str.replace(",", "", regex=False)
    s = s.str.replace(r"[^\d\.]", "", regex=True)  # keep digits and dot only
    s = s.replace({"": pd.NA})
    return pd.to_numeric(s, errors="coerce")

# -------------------------
# Logos (Wikimedia direct file paths)
# -------------------------
LOGOS = {
    "JPMORGAN": "JPMorgan Chase logo 2008.svg",
    "BANK OF AMER": "Bank of America logo.svg",
    "CITI": "Citibank.svg",
    "WELLS FARGO": "Wells Fargo Bank.svg",
    "U S BK": "U.S. Bank logo.svg",
    "US BK": "U.S. Bank logo.svg",
    "CAPITAL ONE": "Capital One logo.svg",
    "GOLDMAN": "Goldman Sachs.svg",
    "PNC": "PNC Financial Services logo.svg",
    "TRUIST": "Truist logo.svg",
    "MELLON": "BNY Mellon logo.svg",
    "STATE STREET": "State Street Corporation logo.svg",
    "TD": "TD Bank logo.svg",
    "MORGAN STANLEY": "Morgan Stanley Logo 1.svg",
    "BMO": "BMO logo.svg",
    "FIFTH THIRD": "Fifth Third Bank logo.svg",
    "AMERICAN EXPRESS": "American Express logo.svg",
}

def logo_url(file, width=180):
    safe = urllib.parse.quote(file)
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{safe}?width={width}"

def get_logo(bank):
    name = str(bank).upper()
    for k, v in LOGOS.items():
        if k in name:
            return logo_url(v)
    return None

def short_name(bank):
    return re.sub(r"\s+", " ", str(bank).split("/")[0].strip())[:22]

# -------------------------
# Load data (robust)
# -------------------------
@st.cache_data(ttl=3600)
def load_lbr():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(LBR_URL, headers=headers, timeout=30)
    r.raise_for_status()

    tables = pd.read_html(r.text)

    # choose best candidate table
    best = None
    best_score = -1
    for t in tables:
        t = t.copy()
        t.columns = clean_columns(t.columns)
        cols = t.columns.tolist()

        score = 0
        if find_col_any(cols, ["rank"]):
            score += 2
        if find_col_any(cols, ["assets", "consol"]):
            score += 2
        if find_col_any(cols, ["location"]):
            score += 1

        if score > best_score:
            best, best_score = t, score

    df = best.copy()
    df.columns = clean_columns(df.columns)
    cols = df.columns.tolist()

    bank_col = cols[0]
    rank_col = find_col_any(cols, ["rank"])
    loc_col = find_col_any(cols, ["bank location", "location"])
    charter_col = find_col_any(cols, ["charter"])
    ibf_col = find_col_any(cols, ["ibf"])

    # detect assets columns (Fed can change exact text)
    assets_col = find_col_any(cols, ["consol assets", "consolidated assets", "consol", "assets"])
    dom_assets_col = find_col_any(cols, ["domestic assets"])

    rename = {bank_col: "Bank"}
    if rank_col: rename[rank_col] = "Rank"
    if loc_col: rename[loc_col] = "Location"
    if charter_col: rename[charter_col] = "Charter"
    if ibf_col: rename[ibf_col] = "IBF"
    if assets_col: rename[assets_col] = "Assets_Mil"
    if dom_assets_col: rename[dom_assets_col] = "DomesticAssets_Mil"

    df = df.rename(columns=rename)

    if "Assets_Mil" not in df.columns:
        raise KeyError(f"Could not detect consolidated assets column. Columns found: {list(df.columns)}")

    # safe numeric conversion
    df["Assets_Mil"] = to_number_safe(df["Assets_Mil"])
    if "DomesticAssets_Mil" in df.columns:
        df["DomesticAssets_Mil"] = to_number_safe(df["DomesticAssets_Mil"])

    if "Rank" in df.columns:
        df["Rank"] = pd.to_numeric(df["Rank"], errors="coerce")

    if "Location" in df.columns:
        df["State"] = df["Location"].astype(str).str.extract(r",\s*([A-Z]{2})\s*$", expand=False)

    df["Logo"] = df["Bank"].apply(get_logo)
    df["Short"] = df["Bank"].apply(short_name)

    # drop rows with no assets
    df = df[df["Assets_Mil"].notna()].copy()

    # also create dollar column for charts (fixes your “millions of millions” problem)
    df["Assets_$"] = df["Assets_Mil"].apply(mil_to_dollars)

    return df

try:
    df = load_lbr()
except Exception as e:
    st.error("Fed LBR page returned an unexpected format. Open Streamlit logs for details.")
    st.exception(e)
    st.stop()

# -------------------------
# UI
# -------------------------
st.title("Thomas Selassie – Fed LBR Large Commercial Banks Dashboard")
st.caption(
    "Source: Federal Reserve LBR current release. "
    "Fed reports assets in **millions**; this dashboard formats charts in real dollars ($B/$T)."
)

with st.sidebar:
    st.header("Filters")
    search = st.text_input("Search bank")
    top_n = st.slider("Top N banks", 4, min(50, len(df)), 15)
    states = sorted([s for s in df.get("State", pd.Series([])).dropna().unique().tolist() if isinstance(s, str)])
    state = st.selectbox("State (optional)", ["All"] + states)

filtered = df.copy()
if search:
    filtered = filtered[filtered["Bank"].astype(str).str.contains(search, case=False, na=False)]
if state != "All" and "State" in filtered.columns:
    filtered = filtered[filtered["State"] == state]

# sort
if "Rank" in filtered.columns and filtered["Rank"].notna().any():
    filtered = filtered.sort_values("Rank")
else:
    filtered = filtered.sort_values("Assets_Mil", ascending=False)

filtered = filtered.head(top_n)

# logo strip
st.subheader("Top Banks")
strip = filtered.head(min(10, len(filtered)))
cols = st.columns(len(strip))
for i, (_, r) in enumerate(strip.iterrows()):
    with cols[i]:
        if r["Logo"]:
            st.image(r["Logo"], width=70)
        st.caption(r["Short"])

# metrics
m1, m2, m3 = st.columns(3)
m1.metric("Banks shown", int(len(filtered)))
m2.metric("Total assets", format_assets_mil(filtered["Assets_Mil"].sum()))
m3.metric("Median assets", format_assets_mil(filtered["Assets_Mil"].median()))

# layout
left, right = st.columns([1.1, 1.4])

with left:
    st.subheader("Selected bank")
    row = filtered.iloc[0]
    if row["Logo"]:
        st.image(row["Logo"], width=120)

    st.markdown(f"### {row['Bank']}")
    if "Rank" in filtered.columns and pd.notna(row.get("Rank")):
        st.write(f"**Rank:** {int(row['Rank'])}")
    if "Location" in filtered.columns:
        st.write(f"**Location:** {row.get('Location','')}")
    if "Charter" in filtered.columns:
        st.write(f"**Charter:** {row.get('Charter','')}")
    if "IBF" in filtered.columns:
        st.write(f"**IBF:** {row.get('IBF','')}")
    st.write(f"**Assets:** {format_assets_mil(row['Assets_Mil'])}")

    st.subheader("Table")
    show_cols = [c for c in ["Rank", "Bank", "Location", "State", "Charter", "IBF", "Assets_Mil"] if c in filtered.columns]
    table_df = filtered[show_cols].reset_index(drop=True).copy()
    if "Assets_Mil" in table_df.columns:
        table_df = table_df.rename(columns={"Assets_Mil": "Assets (Mil $)"})
    st.dataframe(table_df, use_container_width=True, height=420)

with right:
    st.subheader("Charts")

    # BAR: use Assets_$ so x-axis shows $B/$T correctly
    bar_df = filtered.copy().sort_values("Assets_$")

    fig_bar = px.bar(
        bar_df,
        x="Assets_$",
        y="Bank",
        orientation="h",
        title="Top banks by consolidated assets",
        labels={"Assets_$": "Consolidated Assets (USD)", "Bank": ""},
        text="Assets_$"
    )

    fig_bar.update_traces(
        marker_color="#1F6AE1",
        texttemplate="%{text:$,.2s}",
        hovertemplate="<b>%{y}</b><br>Assets: %{x:$,.0f}<extra></extra>"
    )
    fig_bar.update_layout(
        xaxis_tickprefix="$",
        xaxis_tickformat="~s"
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # HIST: also use Assets_$ (real dollars)
    fig_hist = px.histogram(
        filtered,
        x="Assets_$",
        nbins=12,
        title="Distribution of assets (bank size spread)",
        labels={"Assets_$": "Assets (USD)"},
    )
    fig_hist.update_traces(marker_color="#0B2C5D")
    fig_hist.update_layout(xaxis_tickprefix="$", xaxis_tickformat="~s")
    st.plotly_chart(fig_hist, use_container_width=True)
