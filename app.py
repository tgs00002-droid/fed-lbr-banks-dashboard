import re
import pandas as pd
import streamlit as st
import plotly.express as px
import requests

# ===============================
# SETTINGS
# ===============================
LBR_URL = "https://www.federalreserve.gov/releases/lbr/current/"

st.set_page_config(
    page_title="Thomas Selassie – Fed LBR Banks Dashboard",
    layout="wide"
)

# ===============================
# COLOR THEME (Finance style)
# ===============================
PRIMARY_COLOR = "#0B2C5D"   # Navy
ACCENT_COLOR = "#1F6AE1"    # Blue
SOFT_GRAY = "#F4F6F9"

st.markdown(
    f"""
    <style>
    .block-container {{
        padding-top: 1.2rem;
    }}
    h1 {{
        color: {PRIMARY_COLOR};
        letter-spacing: -0.6px;
    }}
    h2, h3 {{
        color: {PRIMARY_COLOR};
    }}
    .stMetric {{
        background-color: {SOFT_GRAY};
        padding: 12px;
        border-radius: 12px;
    }}
    </style>
    """,
    unsafe_allow_html=True
)

# ===============================
# TITLE
# ===============================
st.title("Thomas Selassie – Fed LBR Large Commercial Banks Dashboard")
st.caption(
    "Source: Federal Reserve Large Commercial Banks (LBR) – current release. "
    "Dashboard auto-updates when the Fed updates the table."
)

# ===============================
# FIXED BANK LOGOS (TOP LBR)
# ===============================
BANK_LOGO_MAP = {
    "JPMORGAN CHASE": "https://upload.wikimedia.org/wikipedia/commons/0/0e/JPMorgan_Chase_logo.svg",
    "BANK OF AMER": "https://upload.wikimedia.org/wikipedia/commons/2/20/Bank_of_America_logo.svg",
    "CITIBANK": "https://upload.wikimedia.org/wikipedia/commons/5/5a/Citibank.svg",
    "WELLS FARGO": "https://upload.wikimedia.org/wikipedia/commons/b/b3/Wells_Fargo_Bank.svg",
    "U S BK": "https://upload.wikimedia.org/wikipedia/commons/0/01/U.S._Bank_logo.svg",
    "US BK": "https://upload.wikimedia.org/wikipedia/commons/0/01/U.S._Bank_logo.svg",
    "CAPITAL ONE": "https://upload.wikimedia.org/wikipedia/commons/9/98/Capital_One_logo.svg",
    "GOLDMAN SACHS": "https://upload.wikimedia.org/wikipedia/commons/6/61/Goldman_Sachs.svg",
    "PNC": "https://upload.wikimedia.org/wikipedia/commons/5/5a/PNC_Financial_Services_logo.svg",
    "TRUIST": "https://upload.wikimedia.org/wikipedia/commons/5/51/Truist_logo.svg",
    "BANK OF NY MELLON": "https://upload.wikimedia.org/wikipedia/commons/0/09/BNY_Mellon_logo.svg",
    "STATE STREET": "https://upload.wikimedia.org/wikipedia/commons/6/6f/State_Street_Corporation_logo.svg",
    "TD BK": "https://upload.wikimedia.org/wikipedia/commons/6/6f/TD_Bank_logo.svg",
    "TD BANK": "https://upload.wikimedia.org/wikipedia/commons/6/6f/TD_Bank_logo.svg",
    "MORGAN STANLEY": "https://upload.wikimedia.org/wikipedia/commons/3/3e/Morgan_Stanley_Logo_1.svg",
    "BMO": "https://upload.wikimedia.org/wikipedia/commons/5/5a/BMO_logo.svg",
    "FIRST-CITIZENS": "https://upload.wikimedia.org/wikipedia/commons/2/25/First_Citizens_BancShares_logo.svg",
    "CITIZENS BK": "https://upload.wikimedia.org/wikipedia/commons/8/8b/Citizens_Financial_Group_logo.svg",
    "FIFTH THIRD": "https://upload.wikimedia.org/wikipedia/commons/3/3b/Fifth_Third_Bank_logo.svg",
    "AMERICAN EXPRESS": "https://upload.wikimedia.org/wikipedia/commons/3/30/American_Express_logo.svg",
}

def bank_logo_url(bank_name):
    if not bank_name:
        return None
    name = bank_name.upper()
    for key, url in BANK_LOGO_MAP.items():
        if key in name:
            return url
    return None

def short_name(bank_name):
    return bank_name.split("/")[0][:28]

# ===============================
# LOAD FED DATA (SAFE)
# ===============================
@st.cache_data(ttl=3600)
def load_data():
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    r = requests.get(LBR_URL, headers=headers, timeout=30)
    r.raise_for_status()
    tables = pd.read_html(r.text)

    df = tables[0].copy()
    df.columns = [c.strip() for c in df.columns]

    df.rename(columns={
        df.columns[0]: "Bank",
        "Nat'l Rank": "Rank",
        "Consol Assets (Mil $)": "Assets"
    }, inplace=True)

    df["Assets"] = (
        df["Assets"].astype(str)
        .str.replace(",", "", regex=False)
        .astype(float)
    )

    df["Logo"] = df["Bank"].apply(bank_logo_url)
    df["Short"] = df["Bank"].apply(short_name)

    return df

df = load_data()

# ===============================
# SIDEBAR
# ===============================
with st.sidebar:
    st.header("Filters")

    search = st.text_input("Search bank")
    top_n = st.slider("Top N banks", 5, 50, 15)

# ===============================
# FILTER
# ===============================
filtered = df.copy()
if search:
    filtered = filtered[filtered["Bank"].str.contains(search, case=False)]

filtered = filtered.sort_values("Rank").head(top_n)

# ===============================
# LOGO ROW
# ===============================
st.subheader("Top Banks")
logo_cols = st.columns(len(filtered))

for i, (_, r) in enumerate(filtered.iterrows()):
    with logo_cols[i]:
        if r["Logo"]:
            st.image(r["Logo"], width=55)
        st.caption(r["Short"])

# ===============================
# METRICS
# ===============================
c1, c2, c3 = st.columns(3)

c1.metric("Banks shown", len(filtered))
c2.metric("Total Assets (Mil $)", f"{filtered['Assets'].sum():,.0f}")
c3.metric("Median Assets (Mil $)", f"{filtered['Assets'].median():,.0f}")

# ===============================
# MAIN LAYOUT
# ===============================
left, right = st.columns([1.1, 1.3])

with left:
    st.subheader("Selected Bank")
    row = filtered.iloc[0]

    if row["Logo"]:
        st.image(row["Logo"], width=90)

    st.markdown(f"### {row['Bank']}")
    st.write(f"**Rank:** {int(row['Rank'])}")
    st.write(f"**Assets (Mil $):** {row['Assets']:,.0f}")

    st.subheader("Table")
    st.dataframe(
        filtered[["Rank", "Bank", "Assets"]],
        use_container_width=True,
        height=420
    )

with right:
    st.subheader("Top Banks by Assets")

    fig = px.bar(
        filtered.sort_values("Assets"),
        x="Assets",
        y="Bank",
        orientation="h",
        color_discrete_sequence=[ACCENT_COLOR],
        labels={"Assets": "Consolidated Assets (Mil $)", "Bank": ""}
    )

    fig.update_layout(
        height=520,
        plot_bgcolor="white",
        paper_bgcolor="white"
    )

    st.plotly_chart(fig, use_container_width=True)
