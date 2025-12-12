import re
import urllib.parse
import pandas as pd
import streamlit as st
import plotly.express as px
import requests

# =========================
# SETTINGS
# =========================
LBR_URL = "https://www.federalreserve.gov/releases/lbr/current/"  # current LBR release page :contentReference[oaicite:2]{index=2}

# Finance-style colors
PRIMARY = "#0B2C5D"   # navy
ACCENT = "#1F6AE1"    # blue
BG = "#F5F7FB"        # light gray background

st.set_page_config(page_title="Thomas Selassie – Fed LBR Banks", layout="wide")

st.markdown(
    f"""
    <style>
      .block-container {{ padding-top: 1.1rem; }}
      h1,h2,h3 {{ color: {PRIMARY}; letter-spacing: -0.4px; }}
      section[data-testid="stSidebar"] {{ background: {BG}; }}
      div[data-testid="stMetric"] {{
          background: white;
          border: 1px solid rgba(15, 23, 42, 0.08);
          border-radius: 14px;
          padding: 12px;
      }}
      .card {{
          background: white;
          border: 1px solid rgba(15, 23, 42, 0.08);
          border-radius: 16px;
          padding: 14px 16px;
      }}
    </style>
    """,
    unsafe_allow_html=True
)

st.title("Thomas Selassie – Fed LBR Large Commercial Banks Dashboard")
st.caption(
    "Source: Federal Reserve LBR (Large Commercial Banks) current release. "
    "This dashboard parses the ranked bank table and updates when the Fed updates the page."
)

# =========================
# LOGOS (ONLY your listed banks)
# Use Wikimedia Commons Special:FilePath so Streamlit gets a renderable image. :contentReference[oaicite:3]{index=3}
# =========================
BANK_LOGO_FILES = {
    "JPMORGAN CHASE": "JPMorgan Chase logo 2008.svg",
    "BANK OF AMER": "Bank of America logo.svg",
    "CITIBANK": "Citi.svg",
    "WELLS FARGO": "Wells Fargo Bank.svg",
    "U S BK": "U.S. Bank logo.svg",
    "US BK": "U.S. Bank logo.svg",
    "CAPITAL ONE": "Capital One logo.svg",
    "GOLDMAN SACHS": "Goldman Sachs.svg",
    "PNC": "PNC Financial Services logo.svg",
    "TRUIST": "Truist Financial logo.svg",
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

def commons_logo_url(file_name: str, width: int = 160) -> str:
    # Special:FilePath returns the actual media file (and can resize via width). :contentReference[oaicite:4]{index=4}
    safe = urllib.parse.quote(file_name)
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{safe}?width={width}"

def bank_logo_url(bank_full_name: str) -> str | None:
    if not bank_full_name:
        return None
    u = str(bank_full_name).upper()
    for key, file_name in BANK_LOGO_FILES.items():
        if key in u:
            return commons_logo_url(file_name, width=180)
    return None

def short_bank_name(bank_full_name: str) -> str:
    # Fed names often look like "BANK A/BANK HOLDCO" — use the left side for display
    left = str(bank_full_name).split("/")[0].strip()
    left = re.sub(r"\s+", " ", left)
    return left[:26] + ("…" if len(left) > 26 else "")

# =========================
# DATA LOAD (robust)
# =========================
@st.cache_data(ttl=60 * 60)
def fetch_lbr_html(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}  # avoids some hosted-env blocks
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text

def find_col(cols, must_contain_any):
    cols_l = [c.lower() for c in cols]
    for i, c in enumerate(cols_l):
        if any(p in c for p in must_contain_any):
            return cols[i]
    return None

@st.cache_data(ttl=60 * 60)
def load_lbr_df(url: str) -> pd.DataFrame:
    html = fetch_lbr_html(url)
    tables = pd.read_html(html)

    # The current page includes the ranked bank table with columns like:
    # Bank Name / Holding Co Name, Nat'l Rank, Bank Location, Consol Assets... :contentReference[oaicite:5]{index=5}
    # We’ll choose the best candidate by looking for rank + assets.
    best = None
    best_score = -1
    for t in tables:
        cols = [str(c).strip() for c in t.columns]
        score = 0
        if find_col(cols, ["rank"]): score += 2
        if find_col(cols, ["consol", "assets"]): score += 2
        if find_col(cols, ["bank location", "location"]): score += 1
        if score > best_score:
            best, best_score = t, score

    df = best.copy()
    df.columns = [str(c).strip() for c in df.columns]

    col_bank = df.columns[0]
    col_rank = find_col(df.columns, ["rank"])
    col_loc = find_col(df.columns, ["bank location", "location"])
    col_charter = find_col(df.columns, ["charter"])
    col_assets = find_col(df.columns, ["consol assets", "consolidated assets", "consol"])
    col_dom_assets = find_col(df.columns, ["domestic assets"])
    col_ibf = find_col(df.columns, ["ibf"])

    rename = {col_bank: "Bank"}
    if col_rank: rename[col_rank] = "Rank"
    if col_loc: rename[col_loc] = "Location"
    if col_charter: rename[col_charter] = "Charter"
    if col_assets: rename[col_assets] = "Assets (Mil $)"
    if col_dom_assets: rename[col_dom_assets] = "Domestic Assets (Mil $)"
    if col_ibf: rename[col_ibf] = "IBF"

    df = df.rename(columns=rename)

    # Clean numerics
    for c in ["Assets (Mil $)", "Domestic Assets (Mil $)"]:
        if c in df.columns:
            df[c] = (
                df[c].astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(r"[^\d\.]", "", regex=True)
            )
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if "Rank" in df.columns:
        df["Rank"] = pd.to_numeric(df["Rank"], errors="coerce")

    # State from "CITY, ST"
    if "Location" in df.columns:
        df["State"] = df["Location"].astype(str).str.extract(r",\s*([A-Z]{2})\s*$", expand=False)

    # Logos + short label
    df["Logo"] = df["Bank"].astype(str).apply(bank_logo_url)
    df["Short"] = df["Bank"].astype(str).apply(short_bank_name)

    return df

try:
    df = load_lbr_df(LBR_URL)
except Exception as e:
    st.error("Could not load the Fed LBR page right now.")
    st.exception(e)
    st.stop()

# =========================
# SIDEBAR FILTERS
# =========================
with st.sidebar:
    st.header("Filters")
    search = st.text_input("Search bank", "")
    top_n = st.slider("Top N banks", 5, min(50, len(df)), 15)

    states = sorted([s for s in df.get("State", pd.Series([])).dropna().unique().tolist() if isinstance(s, str)])
    state = st.selectbox("State (optional)", ["All"] + states)

# Apply filters
filtered = df.copy()
if search.strip():
    filtered = filtered[filtered["Bank"].astype(str).str.contains(search, case=False, na=False)]
if state != "All" and "State" in filtered.columns:
    filtered = filtered[filtered["State"] == state]

if "Rank" in filtered.columns and filtered["Rank"].notna().any():
    filtered = filtered.sort_values("Rank").head(top_n)
elif "Assets (Mil $)" in filtered.columns:
    filtered = filtered.sort_values("Assets (Mil $)", ascending=False).head(top_n)
else:
    filtered = filtered.head(top_n)

# =========================
# TOP LOGO STRIP (cool look)
# =========================
st.subheader("Top Banks")
logo_cols = st.columns(min(10, len(filtered)))
top_strip = (
    filtered.sort_values("Assets (Mil $)", ascending=False).head(len(logo_cols))
    if "Assets (Mil $)" in filtered.columns else filtered.head(len(logo_cols))
)

for i, (_, r) in enumerate(top_strip.iterrows()):
    with logo_cols[i]:
        if isinstance(r.get("Logo"), str) and r["Logo"]:
            st.image(r["Logo"], width=58)
        st.caption(r.get("Short", ""))

# =========================
# METRICS
# =========================
m1, m2, m3 = st.columns(3)
m1.metric("Banks shown", int(len(filtered)))

if "Assets (Mil $)" in filtered.columns and filtered["Assets (Mil $)"].notna().any():
    m2.metric("Total assets (Mil $)", f"{filtered['Assets (Mil $)'].sum():,.0f}")
    m3.metric("Median assets (Mil $)", f"{filtered['Assets (Mil $)'].median():,.0f}")
else:
    m2.metric("Total assets (Mil $)", "N/A")
    m3.metric("Median assets (Mil $)", "N/A")

# =========================
# MAIN LAYOUT
# =========================
left, right = st.columns([1.15, 1.35], gap="large")

with left:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Selected bank")

    if len(filtered) > 0:
        row = filtered.iloc[0]
        if isinstance(row.get("Logo"), str) and row["Logo"]:
            st.image(row["Logo"], width=92)

        st.markdown(f"### {row.get('Bank','')}")
        if "Rank" in filtered.columns:
            st.write(f"**Rank:** {int(row['Rank'])}" if pd.notna(row.get("Rank")) else "**Rank:** N/A")
        if "Location" in filtered.columns:
            st.write(f"**Location:** {row.get('Location','')}")
        if "Charter" in filtered.columns:
            st.write(f"**Charter:** {row.get('Charter','')}")
        if "IBF" in filtered.columns:
            st.write(f"**IBF:** {row.get('IBF','')}")
        if "Assets (Mil $)" in filtered.columns and pd.notna(row.get("Assets (Mil $)")):
            st.write(f"**Assets (Mil $):** {row['Assets (Mil $)']:,.0f}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("Table")
    show_cols = [c for c in ["Rank", "Bank", "Location", "Charter", "IBF", "Assets (Mil $)", "Domestic Assets (Mil $)"] if c in filtered.columns]
    st.dataframe(filtered[show_cols].reset_index(drop=True), use_container_width=True, height=520)

with right:
    st.subheader("Charts")

    if "Assets (Mil $)" in filtered.columns and filtered["Assets (Mil $)"].notna().any():
        top15 = filtered.sort_values("Assets (Mil $)", ascending=False).head(15)

        fig_bar = px.bar(
            top15.sort_values("Assets (Mil $)"),
            x="Assets (Mil $)",
            y="Bank",
            orientation="h",
            title="Top banks by consolidated assets (Mil $)",
            color_discrete_sequence=[ACCENT],
        )
        fig_bar.update_layout(
            height=440,
            plot_bgcolor="white",
            paper_bgcolor="white",
            font=dict(color=PRIMARY),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        fig_hist = px.histogram(
            filtered,
            x="Assets (Mil $)",
            nbins=25,
            title="Distribution of assets (Mil $)",
            color_discrete_sequence=[PRIMARY],
        )
        fig_hist.update_layout(
            height=320,
            plot_bgcolor="white",
            paper_bgcolor="white",
            font=dict(color=PRIMARY),
        )
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("Assets column not detected on this release page format.")

st.caption(
    "Logos are served from Wikimedia Commons using Special:FilePath (resized via width), which is recommended for hotlinking files."
)  # :contentReference[oaicite:6]{index=6}


