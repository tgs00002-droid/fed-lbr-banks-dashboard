import re
import urllib.parse
import pandas as pd
import streamlit as st
import plotly.express as px
import requests

# =============================
# PAGE CONFIG
# =============================
st.set_page_config(
    page_title="Thomas Selassie – Fed LBR Banks",
    layout="wide"
)

LBR_URL = "https://www.federalreserve.gov/releases/lbr/current/"

# =============================
# HELPERS
# =============================
def format_assets(mil):
    if pd.isna(mil):
        return "N/A"
    if mil >= 1_000_000:
        return f"${mil/1_000_000:.2f}T"
    if mil >= 1_000:
        return f"${mil/1_000:.2f}B"
    return f"${mil:,.0f}M"

def clean_columns(cols):
    """Safely flatten multi-index columns"""
    cleaned = []
    for c in cols:
        if isinstance(c, tuple):
            c = " ".join([str(x) for x in c if x])
        cleaned.append(str(c).strip())
    return cleaned

def short_name(name):
    return name.split("/")[0][:22]

# =============================
# LOGOS (STABLE WIKIMEDIA)
# =============================
LOGOS = {
    "JPMORGAN": "JPMorgan Chase logo 2008.svg",
    "BANK OF AMER": "Bank of America logo.svg",
    "CITI": "Citibank.svg",
    "WELLS FARGO": "Wells Fargo Bank.svg",
    "U S BK": "U.S. Bank logo.svg",
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

def logo_url(file):
    safe = urllib.parse.quote(file)
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{safe}?width=180"

def get_logo(bank):
    name = bank.upper()
    for k, v in LOGOS.items():
        if k in name:
            return logo_url(v)
    return None

# =============================
# LOAD DATA (LOCKED)
# =============================
@st.cache_data(ttl=3600)
def load_lbr():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(LBR_URL, headers=headers, timeout=30)
    r.raise_for_status()

    tables = pd.read_html(r.text)
    df = tables[0].copy()

    # FIX: multi-index safe
    df.columns = clean_columns(df.columns)

    df.rename(columns={
        df.columns[0]: "Bank",
        "Nat'l Rank": "Rank",
        "Consol Assets (Mil $)": "Assets",
        "Domestic Assets (Mil $)": "Domestic Assets",
        "Bank Location": "Location",
        "Charter": "Charter",
        "IBF": "IBF",
    }, inplace=True)

    df["Assets"] = df["Assets"].astype(str).str.replace(",", "").astype(float)
    df["Rank"] = pd.to_numeric(df["Rank"], errors="coerce")
    df["State"] = df["Location"].str.extract(r",\s*([A-Z]{2})$")
    df["Logo"] = df["Bank"].apply(get_logo)
    df["Short"] = df["Bank"].apply(short_name)

    return df

df = load_lbr()

# =============================
# SIDEBAR
# =============================
with st.sidebar:
    st.header("Filters")
    search = st.text_input("Search bank")
    top_n = st.slider("Top N banks", 5, 50, 15)
    state = st.selectbox("State (optional)", ["All"] + sorted(df["State"].dropna().unique()))

filtered = df.copy()
if search:
    filtered = filtered[filtered["Bank"].str.contains(search, case=False)]
if state != "All":
    filtered = filtered[filtered["State"] == state]

filtered = filtered.sort_values("Rank").head(top_n)

# =============================
# HEADER
# =============================
st.title("Thomas Selassie – Fed LBR Large Commercial Banks Dashboard")
st.caption(
    "Source: Federal Reserve Large Commercial Banks (LBR). "
    "Assets shown in billions (B) and trillions (T)."
)

# =============================
# LOGO STRIP
# =============================
st.subheader("Top Banks")
cols = st.columns(len(filtered))
for i, (_, r) in enumerate(filtered.iterrows()):
    with cols[i]:
        if r["Logo"]:
            st.image(r["Logo"])
        st.caption(r["Short"])

# =============================
# METRICS
# =============================
m1, m2, m3 = st.columns(3)
m1.metric("Banks shown", len(filtered))
m2.metric("Total assets", format_assets(filtered["Assets"].sum()))
m3.metric("Median assets", format_assets(filtered["Assets"].median()))

# =============================
# CONTENT
# =============================
left, right = st.columns([1.1, 1.4])

with left:
    bank = filtered.iloc[0]

    if bank["Logo"]:
        st.image(bank["Logo"], width=120)

    st.markdown(f"### {bank['Bank']}")
    st.write(f"**Rank:** {int(bank['Rank'])}")
    st.write(f"**Location:** {bank['Location']}")
    st.write(f"**Charter:** {bank['Charter']}")
    st.write(f"**IBF:** {bank['IBF']}")
    st.write(f"**Assets:** {format_assets(bank['Assets'])}")

    st.subheader("Table")
    st.dataframe(
        filtered[["Rank", "Bank", "Location", "Assets"]],
        use_container_width=True,
        height=420
    )

with right:
    st.subheader("Charts")

    fig_bar = px.bar(
        filtered.sort_values("Assets"),
        x="Assets",
        y="Bank",
        orientation="h",
        labels={"Assets": "Assets (Millions USD)", "Bank": ""},
    )
    fig_bar.update_traces(marker_color="#1F6AE1")
    st.plotly_chart(fig_bar, use_container_width=True)

    fig_hist = px.histogram(
        filtered,
        x="Assets",
        nbins=12,
        title="Distribution of assets (bank size spread)",
    )
    st.plotly_chart(fig_hist, use_container_width=True)
