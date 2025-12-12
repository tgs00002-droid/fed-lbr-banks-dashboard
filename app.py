import re
import urllib.parse
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.io as pio
import requests

# =========================
# SETTINGS
# =========================
LBR_URL = "https://www.federalreserve.gov/releases/lbr/current/"
st.set_page_config(page_title="Thomas Selassie – Fed LBR Banks", layout="wide")

# =========================
# STYLE / THEME
# =========================
PRIMARY = "#0B2C5D"   # Navy
ACCENT  = "#1F6AE1"   # Blue
BG      = "#F5F7FB"

pio.templates.default = "plotly_white"

st.markdown(
    f"""
    <style>
      .block-container {{ padding-top: 1.1rem; }}
      section[data-testid="stSidebar"] {{ background: {BG}; }}
      h1,h2,h3 {{ color: {PRIMARY}; letter-spacing: -0.4px; }}

      div[data-testid="stMetric"] {{
        background: white;
        border: 1px solid rgba(15,23,42,0.12);
        border-radius: 14px;
        padding: 14px;
      }}

      img {{ image-rendering: -webkit-optimize-contrast; }}
    </style>
    """,
    unsafe_allow_html=True
)

st.title("Thomas Selassie – Fed LBR Large Commercial Banks Dashboard")
st.caption(
    "Source: Federal Reserve Large Commercial Banks (LBR) – current release. "
    "Values are shown in billions (B) and trillions (T)."
)

# =========================
# FORMAT HELPERS
# =========================
def format_assets(value_mil):
    """Input: millions of dollars → Output: $X.XXB / $X.XXT"""
    if pd.isna(value_mil):
        return "N/A"
    if value_mil >= 1_000_000:
        return f"${value_mil/1_000_000:.2f}T"
    elif value_mil >= 1_000:
        return f"${value_mil/1_000:.2f}B"
    else:
        return f"${value_mil:,.0f}M"

def short_bank_name(name):
    return re.sub(r"\s+", " ", name.split("/")[0].strip())[:24]

# =========================
# BANK LOGOS (WIKIMEDIA)
# =========================
BANK_LOGO_FILES = {
    "JPMORGAN CHASE": "JPMorgan Chase logo 2008.svg",
    "BANK OF AMER": "Bank of America logo.svg",
    "CITIBANK": "Citibank.svg",
    "WELLS FARGO": "Wells Fargo Bank.svg",
    "U S BK": "U.S. Bank logo.svg",
    "US BK": "U.S. Bank logo.svg",
    "CAPITAL ONE": "Capital One logo.svg",
    "GOLDMAN SACHS": "Goldman Sachs.svg",
    "PNC": "PNC Financial Services logo.svg",
    "TRUIST": "Truist logo.svg",
    "BANK OF NY MELLON": "BNY Mellon logo.svg",
    "STATE STREET": "State Street Corporation logo.svg",
    "TD BK": "TD Bank logo.svg",
    "TD BANK": "TD Bank logo.svg",
    "MORGAN STANLEY": "Morgan Stanley Logo 1.svg",
    "BMO": "BMO logo.svg",
    "FIRST-CITIZENS": "First Citizens BancShares logo.svg",
    "CITIZENS BK": "Citizens Financial Group logo.svg",
    "FIFTH THIRD": "Fifth Third Bank logo.svg",
    "AMERICAN EXPRESS": "American Express logo.svg",
}

def logo_url(file, width=200):
    safe = urllib.parse.quote(file)
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{safe}?width={width}"

def bank_logo(bank_name):
    u = bank_name.upper()
    for key, file in BANK_LOGO_FILES.items():
        if key in u:
            return logo_url(file)
    return None

# =========================
# LOAD FED DATA (ROBUST)
# =========================
@st.cache_data(ttl=3600)
def load_lbr():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(LBR_URL, headers=headers, timeout=30)
    r.raise_for_status()
    tables = pd.read_html(r.text)

    df = tables[0].copy()
    df.columns = [c.strip() for c in df.columns]

    df.rename(columns={
        df.columns[0]: "Bank",
        "Nat'l Rank": "Rank",
        "Consol Assets (Mil $)": "Assets",
        "Domestic Assets (Mil $)": "Domestic Assets",
        "Charter": "Charter",
        "IBF": "IBF",
        "Bank Location": "Location"
    }, inplace=True)

    for c in ["Assets", "Domestic Assets"]:
        df[c] = (
            df[c].astype(str)
            .str.replace(",", "", regex=False)
            .astype(float)
        )

    df["Rank"] = pd.to_numeric(df["Rank"], errors="coerce")
    df["State"] = df["Location"].str.extract(r",\s*([A-Z]{2})$")
    df["Logo"] = df["Bank"].apply(bank_logo)
    df["Short"] = df["Bank"].apply(short_bank_name)

    return df

df = load_lbr()

# =========================
# SIDEBAR FILTERS
# =========================
with st.sidebar:
    st.header("Filters")
    search = st.text_input("Search bank")
    top_n = st.slider("Top N banks", 4, min(50, len(df)), 15)
    state = st.selectbox("State (optional)", ["All"] + sorted(df["State"].dropna().unique()))

filtered = df.copy()
if search:
    filtered = filtered[filtered["Bank"].str.contains(search, case=False)]
if state != "All":
    filtered = filtered[filtered["State"] == state]

filtered = filtered.sort_values("Rank").head(top_n)

# =========================
# LOGO STRIP
# =========================
st.subheader("Top Banks")
cols = st.columns(len(filtered))
for i, (_, r) in enumerate(filtered.iterrows()):
    with cols[i]:
        if r["Logo"]:
            st.image(r["Logo"], use_container_width=True)
        st.caption(r["Short"])

# =========================
# METRICS (FORMATTED)
# =========================
m1, m2, m3 = st.columns(3)
m1.metric("Banks shown", len(filtered))
m2.metric("Total assets", format_assets(filtered["Assets"].sum()))
m3.metric("Median assets", format_assets(filtered["Assets"].median()))

# =========================
# MAIN CONTENT
# =========================
left, right = st.columns([1.15, 1.35])

with left:
    st.subheader("Selected bank")
    row = filtered.iloc[0]

    if row["Logo"]:
        st.image(row["Logo"], width=120)

    st.markdown(f"### {row['Bank']}")
    st.write(f"**Rank:** {int(row['Rank'])}")
    st.write(f"**Location:** {row['Location']}")
    st.write(f"**Charter:** {row['Charter']}")
    st.write(f"**IBF:** {row['IBF']}")
    st.write(f"**Assets:** {format_assets(row['Assets'])}")

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
    fig_bar.update_traces(marker_color=ACCENT)
    fig_bar.update_layout(height=420)
    st.plotly_chart(fig_bar, use_container_width=True)

    fig_hist = px.histogram(
        filtered,
        x="Assets",
        nbins=12,
        title="Distribution of assets (bank size spread)",
    )
    fig_hist.update_traces(marker_color=PRIMARY)
    st.plotly_chart(fig_hist, use_container_width=True)
