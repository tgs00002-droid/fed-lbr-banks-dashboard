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
# THEME / STYLE
# =========================
PRIMARY = "#0B2C5D"   # navy
ACCENT  = "#1F6AE1"   # blue
BG      = "#F5F7FB"

pio.templates.default = "plotly_white"

st.markdown(
    f"""
    <style>
      .block-container {{ padding-top: 1.1rem; }}
      section[data-testid="stSidebar"] {{ background: {BG}; }}
      h1,h2,h3 {{ color: {PRIMARY}; letter-spacing: -0.4px; }}

      /* Card look */
      .card {{
        background: white;
        border: 1px solid rgba(15,23,42,0.10);
        border-radius: 16px;
        padding: 14px 16px;
      }}

      /* Make captions slightly smaller */
      .stCaption {{ color: rgba(15,23,42,0.70); }}

      /* Reduce extra whitespace around images */
      img {{ image-rendering: -webkit-optimize-contrast; }}
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
# LOGOS (Wikimedia Commons Special:FilePath)
# Tip: using ?width= makes a PNG-like render and looks cleaner in Streamlit.
# =========================
BANK_LOGO_FILES = {
    "JPMORGAN CHASE": "JPMorgan Chase logo 2008.svg",
    "BANK OF AMER": "Bank of America logo.svg",
    "CITIBANK": "Citibank.svg",
    "CITIGROUP": "Citibank.svg",
    "WELLS FARGO": "Wells Fargo Bank.svg",
    "U S BK": "U.S. Bank logo.svg",
    "US BK": "U.S. Bank logo.svg",
    "US BANK": "U.S. Bank logo.svg",
    "CAPITAL ONE": "Capital One logo.svg",
    "GOLDMAN SACHS": "Goldman Sachs.svg",
    "PNC": "PNC Financial Services logo.svg",
    "TRUIST": "Truist logo.svg",
    "BANK OF NY MELLON": "BNY Mellon logo.svg",
    "BNY MELLON": "BNY Mellon logo.svg",
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

def commons_logo_url(file_name: str, width: int = 220) -> str:
    safe = urllib.parse.quote(file_name)
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{safe}?width={width}"

@st.cache_data(ttl=24 * 60 * 60)
def url_ok(url: str) -> bool:
    """Check if a URL returns 200. Prevents broken image icons."""
    try:
        r = requests.get(url, timeout=15)
        return r.status_code == 200 and (len(r.content) > 0)
    except Exception:
        return False

def bank_logo_url(bank_full_name: str) -> str | None:
    if not bank_full_name:
        return None
    u = str(bank_full_name).upper()

    for key, file_name in BANK_LOGO_FILES.items():
        if key in u:
            candidate = commons_logo_url(file_name, width=240)
            if url_ok(candidate):
                return candidate

    # Fallback: no logo (prevents broken image)
    return None

def short_bank_name(bank_full_name: str) -> str:
    left = str(bank_full_name).split("/")[0].strip()
    left = re.sub(r"\s+", " ", left)
    return left[:22] + ("…" if len(left) > 22 else "")

# =========================
# DATA LOAD (robust)
# =========================
@st.cache_data(ttl=60 * 60)
def fetch_lbr_html(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text

def find_col(cols, patterns):
    cols_l = [str(c).lower() for c in cols]
    for i, c in enumerate(cols_l):
        if any(p in c for p in patterns):
            return cols[i]
    return None

@st.cache_data(ttl=60 * 60)
def load_lbr_df(url: str) -> pd.DataFrame:
    html = fetch_lbr_html(url)
    tables = pd.read_html(html)

    # pick best table containing rank + consolidated assets
    best = None
    best_score = -1
    for t in tables:
        cols = [str(c).strip() for c in t.columns]
        score = 0
        if find_col(cols, ["rank"]): score += 2
        if find_col(cols, ["consol", "assets"]): score += 2
        if find_col(cols, ["location"]): score += 1
        if score > best_score:
            best, best_score = t, score

    df = best.copy()
    df.columns = [str(c).strip() for c in df.columns]

    col_bank = df.columns[0]
    col_rank = find_col(df.columns, ["rank"])
    col_loc  = find_col(df.columns, ["bank location", "location"])
    col_char = find_col(df.columns, ["charter"])
    col_assets = find_col(df.columns, ["consol assets", "consolidated assets", "consol"])
    col_dom_assets = find_col(df.columns, ["domestic assets"])
    col_ibf = find_col(df.columns, ["ibf"])

    rename = {col_bank: "Bank"}
    if col_rank: rename[col_rank] = "Rank"
    if col_loc: rename[col_loc] = "Location"
    if col_char: rename[col_char] = "Charter"
    if col_assets: rename[col_assets] = "Assets (Mil $)"
    if col_dom_assets: rename[col_dom_assets] = "Domestic Assets (Mil $)"
    if col_ibf: rename[col_ibf] = "IBF"

    df = df.rename(columns=rename)

    # clean numeric
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

    if "Location" in df.columns:
        df["State"] = df["Location"].astype(str).str.extract(r",\s*([A-Z]{2})\s*$", expand=False)

    df["Logo"] = df["Bank"].astype(str).apply(bank_logo_url)
    df["Short"] = df["Bank"].astype(str).apply(short_bank_name)

    return df

df = load_lbr_df(LBR_URL)

# =========================
# FILTERS
# =========================
with st.sidebar:
    st.header("Filters")
    search = st.text_input("Search bank", "")
    top_n = st.slider("Top N banks", 5, min(50, len(df)), 15)
    states = sorted([s for s in df.get("State", pd.Series([])).dropna().unique().tolist() if isinstance(s, str)])
    state = st.selectbox("State (optional)", ["All"] + states)

filtered = df.copy()
if search.strip():
    filtered = filtered[filtered["Bank"].astype(str).str.contains(search, case=False, na=False)]
if state != "All" and "State" in filtered.columns:
    filtered = filtered[filtered["State"] == state]

# sort + limit
if "Rank" in filtered.columns and filtered["Rank"].notna().any():
    filtered = filtered.sort_values("Rank").head(top_n)
elif "Assets (Mil $)" in filtered.columns:
    filtered = filtered.sort_values("Assets (Mil $)", ascending=False).head(top_n)
else:
    filtered = filtered.head(top_n)

# =========================
# TOP LOGO STRIP (clean + consistent)
# =========================
st.subheader("Top Banks")

strip = filtered.sort_values("Assets (Mil $)", ascending=False).head(min(10, len(filtered))) \
        if "Assets (Mil $)" in filtered.columns else filtered.head(min(10, len(filtered)))

cols = st.columns(len(strip))
for i, (_, r) in enumerate(strip.iterrows()):
    with cols[i]:
        logo = r.get("Logo")
        if isinstance(logo, str) and logo:
            st.image(logo, use_container_width=True)  # clean scaling
        else:
            st.markdown("<div style='height:52px'></div>", unsafe_allow_html=True)  # keeps alignment
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
            st.image(row["Logo"], width=120)

        st.markdown(f"### {row.get('Bank','')}")
        st.write(f"**Rank:** {int(row['Rank'])}" if pd.notna(row.get("Rank")) else "**Rank:** N/A")
        st.write(f"**Location:** {row.get('Location','')}" if "Location" in filtered.columns else "")
        st.write(f"**Charter:** {row.get('Charter','')}" if "Charter" in filtered.columns else "")
        st.write(f"**IBF:** {row.get('IBF','')}" if "IBF" in filtered.columns else "")
        if "Assets (Mil $)" in filtered.columns and pd.notna(row.get("Assets (Mil $)")):
            st.write(f"**Assets (Mil $):** {row['Assets (Mil $)']:,.0f}")

    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("Table")
    show_cols = [c for c in ["Rank", "Bank", "Location", "State", "Charter", "IBF", "Assets (Mil $)", "Domestic Assets (Mil $)"] if c in filtered.columns]
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
        )
        fig_bar.update_traces(marker_color=ACCENT)
        fig_bar.update_layout(
            height=440,
            font=dict(color=PRIMARY),
            xaxis_tickformat=",",
            margin=dict(l=20, r=20, t=60, b=20),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        # Cleaner histogram: fewer bins + comma formatting
        fig_hist = px.histogram(
            filtered,
            x="Assets (Mil $)",
            nbins=12,
            title="Distribution of assets (how bank sizes are spread out)",
        )
        fig_hist.update_traces(marker_color=PRIMARY)
        fig_hist.update_layout(
            height=320,
            font=dict(color=PRIMARY),
            xaxis_tickformat=",",
            margin=dict(l=20, r=20, t=60, b=20),
        )
        st.plotly_chart(fig_hist, use_container_width=True)

    else:
        st.info("Assets column not detected on this release page format.")
