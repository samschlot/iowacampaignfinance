"""
Iowa Campaign Finance Disclosure Viewer
----------------------------------------
Requirements:
    pip install streamlit pdfplumber plotly pandas pgeocode

Run:
    streamlit run iowa_campaign_finance.py

Note: pgeocode downloads a small (~3MB) zip code database on first run
and caches it permanently — no repeated downloads needed.
"""

import io
import re
import streamlit as st
import pdfplumber
import pandas as pd

st.set_page_config(page_title="Iowa Campaign Finance Viewer", page_icon="🗳️", layout="wide")

st.markdown("""
<style>
    .metric-card { background:#f8f9fa; border:1px solid #dee2e6; border-radius:8px; padding:16px 20px; margin-bottom:10px; }
    .metric-label { font-size:0.75rem; color:#6c757d; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:4px; }
    .metric-value        { font-size:1.5rem; font-weight:700; color:#212529; }
    .metric-value.green  { color:#198754; }
    .metric-value.red    { color:#dc3545; }
    .metric-value.blue   { color:#0d6efd; }
    .section-header { font-size:1.05rem; font-weight:600; color:#343a40; border-bottom:2px solid #dee2e6; padding-bottom:6px; margin:28px 0 14px; }
    .committee-title { font-size:1.9rem; font-weight:700; color:#212529; margin-bottom:2px; }
    .report-meta { font-size:0.85rem; color:#6c757d; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
#  ZIP CODE GEOCODING  (via pgeocode — downloads once, caches forever)
# =============================================================================

@st.cache_resource(show_spinner="Loading zip code database…")
def load_geocoder():
    try:
        import pgeocode
        return pgeocode.Nominatim("us")
    except ImportError:
        return None

def zip_to_latlon(zipcode, geocoder):
    if geocoder is None:
        return None
    try:
        result = geocoder.query_postal_code(str(zipcode).zfill(5))
        if result is not None and not pd.isna(result.latitude):
            return (float(result.latitude), float(result.longitude))
    except Exception:
        pass
    return None


# =============================================================================
#  US CITIES OVER ~50,000 POPULATION  (for map labels)
# =============================================================================

MAJOR_CITIES = [
    # Iowa — all significant cities
    ("Des Moines",       41.5868,  -93.6250),
    ("Cedar Rapids",     41.9779,  -91.6656),
    ("Davenport",        41.5236,  -90.5776),
    ("Sioux City",       42.4999,  -96.4003),
    ("Iowa City",        41.6611,  -91.5302),
    ("Waterloo",         42.4928,  -92.3426),
    ("Ames",             42.0347,  -93.6200),
    ("West Des Moines",  41.5772,  -93.7113),
    ("Ankeny",           41.7317,  -93.6002),
    ("Council Bluffs",   41.2619,  -95.8608),
    ("Dubuque",          42.5006,  -90.6646),
    ("Johnston",         41.6775,  -93.6974),
    ("Urbandale",        41.6267,  -93.7122),
    # Major US cities
    ("New York",         40.7128,  -74.0060),
    ("Los Angeles",      34.0522, -118.2437),
    ("Chicago",          41.8781,  -87.6298),
    ("Houston",          29.7604,  -95.3698),
    ("Phoenix",          33.4484, -112.0740),
    ("Philadelphia",     39.9526,  -75.1652),
    ("San Antonio",      29.4241,  -98.4936),
    ("San Diego",        32.7157, -117.1611),
    ("Dallas",           32.7767,  -96.7970),
    ("Austin",           30.2672,  -97.7431),
    ("San Jose",         37.3382, -121.8863),
    ("Fort Worth",       32.7555,  -97.3308),
    ("Columbus",         39.9612,  -82.9988),
    ("Indianapolis",     39.7684,  -86.1581),
    ("Charlotte",        35.2271,  -80.8431),
    ("San Francisco",    37.7749, -122.4194),
    ("Seattle",          47.6062, -122.3321),
    ("Denver",           39.7392, -104.9903),
    ("Washington DC",    38.9072,  -77.0369),
    ("Nashville",        36.1627,  -86.7816),
    ("Oklahoma City",    35.4676,  -97.5164),
    ("El Paso",          31.7619, -106.4850),
    ("Boston",           42.3601,  -71.0589),
    ("Portland",         45.5051, -122.6750),
    ("Las Vegas",        36.1699, -115.1398),
    ("Memphis",          35.1495,  -90.0490),
    ("Louisville",       38.2527,  -85.7585),
    ("Baltimore",        39.2904,  -76.6122),
    ("Milwaukee",        43.0389,  -87.9065),
    ("Albuquerque",      35.0844, -106.6504),
    ("Tucson",           32.2226, -110.9747),
    ("Fresno",           36.7378, -119.7871),
    ("Sacramento",       38.5816, -121.4944),
    ("Kansas City",      39.0997,  -94.5786),
    ("Atlanta",          33.7490,  -84.3880),
    ("Omaha",            41.2565,  -95.9345),
    ("Colorado Springs", 38.8339, -104.8214),
    ("Raleigh",          35.7796,  -78.6382),
    ("Minneapolis",      44.9778,  -93.2650),
    ("Tampa",            27.9506,  -82.4572),
    ("New Orleans",      29.9511,  -90.0715),
    ("Wichita",          37.6872,  -97.3301),
    ("Baton Rouge",      30.4515,  -91.1871),
    ("Salt Lake City",   40.7608, -111.8910),
    ("Tucson",           32.2226, -110.9747),
    ("Tallahassee",      30.4518,  -84.2807),
    ("Richmond",         37.5407,  -77.4360),
    ("Spokane",          47.6587, -117.4260),
    ("Rochester",        43.1566,  -77.6088),
    ("Grand Rapids",     42.9634,  -85.6681),
    ("Knoxville",        35.9606,  -83.9207),
    ("Providence",       41.8240,  -71.4128),
    ("Chattanooga",      35.0456,  -85.3097),
    ("Fort Lauderdale",  26.1224,  -80.1373),
    ("Huntsville",       34.7304,  -86.5861),
    ("Jackson MS",       32.2988,  -90.1848),
    ("Little Rock",      34.7465,  -92.2896),
    ("Sioux Falls",      43.5473,  -96.7283),
    ("Springfield MO",   37.2090,  -93.2923),
    ("Fort Collins",     40.5853, -105.0844),
    ("Eugene",           44.0521, -123.0868),
    ("Peoria IL",        40.6936,  -89.5890),
    ("Jackson WY",       43.4799, -110.7624),
    ("Miami",            25.7617,  -80.1918),
    ("Pittsburgh",       40.4406,  -79.9959),
    ("St. Louis",        38.6270,  -90.1994),
    ("Cincinnati",       39.1031,  -84.5120),
    ("Cleveland",        41.4993,  -81.6944),
    ("Buffalo",          42.8864,  -78.8784),
    ("St. Paul",         44.9537,  -93.0900),
    ("Madison",          43.0731,  -89.4012),
    ("Lincoln",          40.8136,  -96.7026),
    ("Akron",            41.0814,  -81.5190),
    ("Birmingham",       33.5186,  -86.8104),
    ("Norfolk",          36.8508,  -76.2859),
    ("Reno",             39.5296, -119.8138),
    ("Bala Cynwyd",      40.0087,  -75.2413),
]


# =============================================================================
#  PARSING
# =============================================================================

MONEY_RE          = re.compile(r"\$([\d,]+\.\d{2})")
IOWA_FOOTER_RE    = re.compile(r"^IOWA ETHICS AND CAMPAIGN")
EXP_LINE_RE       = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4})\s+.+?\s+\$([\d,]+\.\d{2})\s*$")
CONTRIB_LINE_RE   = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+.+?\s+(None|Self)\s+\$([\d,]+\.\d{2})\s*$")
INLINE_PURPOSE_RE = re.compile(
    r"(Web Fees|Office Supplies|Travel|Advertising|Bank Charges|"
    r"Printing & Reproduction|Consultant Services|Other Expenditure|"
    r"Meals Reimbursement|Political Contribution|Professional Fees|"
    r"Fund-Raiser \(Holding\)|Printing)"
)
PURPOSE_FRAGMENTS = {
    "Consultant","Other","Printing &","Fund-Raiser","Professional","Meals","Political",
    "Services","Expenditure","Reproduction","(Holding)","Fees","Contribution","Reimbursement",
}
HEADER_SKIP_RE = re.compile(
    r"^(Eddie Andrews|Committee Type:|County:|District:|Committee Code:|"
    r"Political Party:|Report Date:|Candidate Name:|Treasurer|Last Name:|"
    r"Address:|City:|Chairperson|Statement of|Additional Assets|Generated On|"
    r"Contribution |Name and Address|Date Committee|Expenditure |"
    r"Schedule [A-Z]\d?:|DR-2 |Filed Date|Statutory|Adjusted|Postmark|"
    r"Amendment|E-Mail:|Grand Total|Total Regular|Total Fundraiser|Total Amount|"
    r"Sub-Total|Loans In|Status:)"
)

def parse_money(s):
    m = MONEY_RE.search(s)
    return float(m.group(1).replace(",","")) if m else 0.0

def is_city_line(s):
    return bool(re.search(r",\s+[A-Z]{2}\s+\d{5}", s))

def is_exp_skip(s):
    return (not s or IOWA_FOOTER_RE.match(s)
            or s.startswith("Expenditure Expenditure")
            or s.startswith("Date Committee")
            or re.match(r"^\d+ of \d+$", s)
            or HEADER_SKIP_RE.match(s)
            or s.startswith("Total Amount"))

def is_purpose_fragment(s):
    return s in PURPOSE_FRAGMENTS

def is_check_name_line(s):
    return bool(re.match(r"^\d{4}\s+(.+)$", s) and "Check" not in s)

def extract_name_from_check_line(s):
    m = re.match(r"^\d{4}\s+(.+)$", s)
    return m.group(1).strip() if m else s

def _tokens_to_purpose(tokens):
    joined = " ".join(tokens)
    if "Consultant" in joined:   return "Consultant Services"
    if "Printing" in joined:     return "Printing & Reproduction"
    if "Fund-Raiser" in joined:  return "Fund-Raiser (Holding)"
    if "Professional" in joined: return "Professional Fees"
    if "Meals" in joined:        return "Meals Reimbursement"
    if "Political" in joined:    return "Political Contribution"
    if "Other" in joined or "Expenditure" in joined: return "Other Expenditure"
    return joined or "Other"

def extract_lines(pdf_bytes):
    lines = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            lines.extend((page.extract_text() or "").splitlines())
    return lines

def parse_summary_fields(lines):
    d = {"committee_name":"","report_date":"","filed_date":"","political_party":"",
         "cash_start":0.0,"receipts":0.0,"expenditures":0.0,"cash_end":0.0,
         "unpaid_bills":0.0,"outstanding_loans":0.0}
    for i, line in enumerate(lines):
        s = line.strip()
        if "DR-2 Disclosure Summary Page DR-2" in s:
            for j in range(i+1, min(i+5, len(lines))):
                cand = lines[j].strip()
                if cand and not cand.startswith("Generated On"):
                    d["committee_name"] = re.split(r"\s{2,}|Status:", cand)[0].strip()
                    break
        if s.startswith("Report Date:"):
            m = re.search(r"Report Date:\s*(\S+)", s)
            if m: d["report_date"] = m.group(1)
        if s.startswith("Political Party:"):
            m = re.search(r"Political Party:\s*(\S+)", s)
            if m: d["political_party"] = m.group(1)
        if "Filed Date" in s:
            m = re.search(r"Filed Date\s+(\d{1,2}/\d{1,2}/\d{4})", s)
            if m: d["filed_date"] = m.group(1)
        for label, key in [
            ("Cash On Hand At Start Of Period","cash_start"),
            ("Schedule A: Cash Contributions Total","receipts"),
            ("Schedule B: Expenditure Total","expenditures"),
            ("Cash on Hand at End of Period","cash_end"),
            ("Schedule D: Unpaid Bills","unpaid_bills"),
            ("Schedule F2: Outstanding Loans","outstanding_loans"),
        ]:
            if label.lower() in s.lower():
                d[key] = parse_money(s)
    return d

def parse_contributions(lines):
    contribs = []
    in_section = False
    for i, line in enumerate(lines):
        s = line.strip()
        if "Schedule A: Contributions" in s or "Sch-A" in s:
            in_section = True; continue
        if in_section and "Schedule B: Expenditures" in s:
            break
        if not in_section: continue

        if re.match(r"^\d{2}/\d{2}/\d{4}\s+Unitemized\s+\$", s):
            date_m = re.match(r"(\d{2}/\d{2}/\d{4})", s)
            contribs.append({"date":date_m.group(1) if date_m else "","name":"Unitemized",
                              "state":"","zipcode":"","amount":parse_money(s)})
            continue

        m = CONTRIB_LINE_RE.match(s)
        if m:
            date = m.group(1)
            amount = float(m.group(3).replace(",",""))
            name = ""
            for k in range(i-1, max(i-6,-1), -1):
                cand = lines[k].strip()
                if cand and not HEADER_SKIP_RE.match(cand) and not CONTRIB_LINE_RE.match(cand) and not IOWA_FOOTER_RE.match(cand):
                    name = cand; break
            state, zipcode = "", ""
            if i+1 < len(lines):
                city_line = lines[i+1].strip()
                m2 = re.search(r",\s+([A-Z]{2})\s+(\d{5})", city_line)
                if m2:
                    state   = m2.group(1)
                    zipcode = m2.group(2)
            contribs.append({"date":date,"name":name or "Unknown",
                              "state":state,"zipcode":zipcode,"amount":amount})
    return contribs

def parse_expenditures(lines):
    exp_list = []
    in_section = False
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if "Schedule B: Expenditures" in s and "Sch-B" in s:
            in_section = True; i += 1; continue
        if in_section and s.startswith("Total Amount"):
            break
        if not in_section or is_exp_skip(s):
            i += 1; continue

        if EXP_LINE_RE.match(s):
            m = EXP_LINE_RE.match(s)
            date   = m.group(1)
            amount = float(m.group(2).replace(",",""))
            name = ""
            pre_purpose = []
            for k in range(i-1, max(i-6,-1), -1):
                cand = lines[k].strip()
                if not cand or is_exp_skip(cand) or EXP_LINE_RE.match(cand): break
                if is_city_line(cand): break
                if re.match(r"^\d{4}\s+Check", cand) or re.match(r"^0+\d+$", cand): continue
                if is_purpose_fragment(cand):
                    pre_purpose.insert(0, cand)
                elif is_check_name_line(cand):
                    name = extract_name_from_check_line(cand); break
                else:
                    name = cand; break

            inline_m = INLINE_PURPOSE_RE.search(s)
            inline_purpose = inline_m.group(1) if inline_m else ""

            post_purpose = []
            city_found = False
            desc = ""
            j = i + 1
            while j < len(lines) and j < i+6:
                cand = lines[j].strip()
                if not cand or is_exp_skip(cand) or EXP_LINE_RE.match(cand): break
                if is_city_line(cand):
                    city_found = True; j += 1; continue
                if city_found:
                    desc = cand; break
                if is_purpose_fragment(cand):
                    post_purpose.append(cand)
                j += 1

            if inline_purpose:
                full_purpose = inline_purpose
            else:
                full_purpose = _tokens_to_purpose(pre_purpose + post_purpose)

            if desc.lower().startswith(full_purpose.lower() + " - "):
                description = desc
            elif desc and desc.lower() not in full_purpose.lower():
                description = f"{full_purpose} - {desc}"
            elif desc:
                description = desc
            else:
                description = full_purpose

            exp_list.append({"date":date,"name":name or "Unknown",
                              "purpose":full_purpose,"amount":amount,"description":description})
        i += 1
    return exp_list

def parse_disclosure(pdf_bytes):
    lines = extract_lines(pdf_bytes)
    return {**parse_summary_fields(lines),
            "contributions":     parse_contributions(lines),
            "expenditures_list": parse_expenditures(lines)}


# =============================================================================
#  HELPERS
# =============================================================================

def fmt_cur(v): return f"${v:,.2f}"
def fmt_pct(v): return f"{v:.1f}%"

def metric_card(label, value, color=""):
    cls = ("metric-value " + color).strip()
    return (f'<div class="metric-card"><div class="metric-label">{label}</div>'
            f'<div class="{cls}">{value}</div></div>')


# =============================================================================
#  APP
# =============================================================================

st.title("🗳️ Iowa Campaign Finance Disclosure Viewer")
st.caption("Upload an Iowa Ethics & Campaign Disclosure Board DR-2 PDF to generate a summary report.")

uploaded = st.file_uploader("Upload DR-2 Disclosure PDF", type=["pdf"])

if not uploaded:
    st.info("Upload a DR-2 disclosure PDF above to get started.")
    st.stop()

with st.spinner("Parsing disclosure…"):
    d = parse_disclosure(uploaded.read())

contributions = d["contributions"]
exp_list      = d["expenditures_list"]
receipts      = d["receipts"]
expenditures  = d["expenditures"]
debts         = d["unpaid_bills"] + d["outstanding_loans"]
itemized      = [c for c in contributions if c["name"] != "Unitemized"]
n_contribs    = len(itemized)
avg_contrib   = receipts / n_contribs if n_contribs else 0.0
burn_rate     = (expenditures / receipts * 100) if receipts else 0.0

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f'<div class="committee-title">{d["committee_name"]}</div>', unsafe_allow_html=True)
meta = []
if d["filed_date"]:      meta.append(f"Filed: {d['filed_date']}")
if d["political_party"]: meta.append(f"Party: {d['political_party']}")
if meta:
    st.markdown(f'<div class="report-meta">{" &nbsp;|&nbsp; ".join(meta)}</div>', unsafe_allow_html=True)

# ── Top Lines ─────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">📊 Top Lines</div>', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(metric_card("Cash on Hand at Start of Period", fmt_cur(d["cash_start"])), unsafe_allow_html=True)
    st.markdown(metric_card("Receipts", fmt_cur(receipts), "green"), unsafe_allow_html=True)
    st.markdown(metric_card("Number of Contributions", f"{n_contribs:,}"), unsafe_allow_html=True)
with c2:
    st.markdown(metric_card("Cash on Hand (End of Period)", fmt_cur(d["cash_end"]), "blue"), unsafe_allow_html=True)
    st.markdown(metric_card("Expenditures", fmt_cur(expenditures), "red"), unsafe_allow_html=True)
    st.markdown(metric_card("Average Contribution", fmt_cur(avg_contrib)), unsafe_allow_html=True)
with c3:
    st.markdown(metric_card("Burn Rate", fmt_pct(burn_rate), "red" if burn_rate > 80 else ""), unsafe_allow_html=True)
    st.markdown(metric_card("Debts", fmt_cur(debts), "red" if debts > 0 else ""), unsafe_allow_html=True)

# ── Contributions ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">💰 Contributions Summary</div>', unsafe_allow_html=True)

if contributions:
    contrib_df = pd.DataFrame(contributions)
    pivot = (contrib_df.groupby("name")["amount"].sum().reset_index()
             .rename(columns={"name":"Contributor","amount":"Total"})
             .sort_values("Total", ascending=False))

    st.subheader("Top Donors ($10,000+)")
    top = pivot[pivot["Total"] >= 10_000].copy()
    if top.empty:
        st.info("No contributors donated $10,000 or more in this period.")
    else:
        top["Total"] = top["Total"].apply(fmt_cur)
        st.dataframe(top.reset_index(drop=True), use_container_width=True, hide_index=True)

    st.subheader("Other Notable Donors")
    st.caption("Pre-populated with all itemized contributors under $10,000. Add notes as needed.")
    notable = pivot[(pivot["Total"] < 10_000) & (pivot["Contributor"] != "Unitemized")].copy()
    notable_init = pd.DataFrame({
        "Name":         notable["Contributor"].astype(str).tolist(),
        "Contribution": notable["Total"].apply(fmt_cur).tolist(),
        "Notes":        [""] * len(notable),
    })
    st.data_editor(notable_init, use_container_width=True, num_rows="dynamic",
                   column_config={
                       "Name":         st.column_config.TextColumn("Name"),
                       "Contribution": st.column_config.TextColumn("Contribution", disabled=True),
                       "Notes":        st.column_config.TextColumn("Notes"),
                   }, hide_index=True, key="notable_donors")
else:
    st.warning("No contribution data could be parsed.")

# ── Expenditures ──────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">💸 Expenditures Summary</div>', unsafe_allow_html=True)

if exp_list:
    exp_df = pd.DataFrame(exp_list)
    exp_pivot = (exp_df.groupby("purpose")["amount"].sum().reset_index()
                 .rename(columns={"purpose":"Purpose","amount":"Total"})
                 .sort_values("Total", ascending=False))

    st.caption("Expand any category to see itemized line items, ordered by amount.")
    for _, row in exp_pivot.iterrows():
        with st.expander(f"**{row['Purpose']}** — {fmt_cur(row['Total'])}"):
            items = (exp_df[exp_df["purpose"] == row["Purpose"]]
                     [["amount","name","date","description"]]
                     .copy().sort_values("amount", ascending=False))
            items["amount"] = items["amount"].apply(fmt_cur)
            items.columns = ["Amount","Payee","Date","Description"]
            st.dataframe(items.reset_index(drop=True), use_container_width=True, hide_index=True)

    try:
        import plotly.express as px
        fig = px.bar(exp_pivot, x="Total", y="Purpose", orientation="h",
                     text=exp_pivot["Total"].apply(fmt_cur),
                     title="Expenditures by Category",
                     labels={"Total":"Amount","Purpose":""},
                     color="Total", color_continuous_scale="Reds")
        fig.update_layout(showlegend=False, coloraxis_showscale=False,
                          yaxis={"categoryorder":"total ascending"},
                          margin=dict(l=10,r=10,t=40,b=10),
                          height=max(300, len(exp_pivot)*36+60))
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        pass
else:
    st.warning("No expenditure data could be parsed.")

# ── Geographic Analysis ───────────────────────────────────────────────────────
st.markdown('<div class="section-header">🗺️ Geographic Analysis</div>', unsafe_allow_html=True)

try:
    import plotly.graph_objects as go

    geocoder = load_geocoder()
    if geocoder is None:
        st.warning("Install pgeocode (`pip install pgeocode`) to enable the map.")
        st.stop()

    # Geocode each contribution with a zip code
    geo_rows = []
    for c in contributions:
        if c["name"] == "Unitemized" or not c.get("zipcode"):
            continue
        coords = zip_to_latlon(c["zipcode"], geocoder)
        if coords:
            geo_rows.append({**c, "lat": coords[0], "lon": coords[1]})

    if not geo_rows:
        st.info("No geocodable addresses found in this disclosure.")
    else:
        geo_df = pd.DataFrame(geo_rows)

        # Aggregate by zip
        map_df = (geo_df.groupby(["zipcode","lat","lon","state"])
                  .agg(total=("amount","sum"), count=("amount","count"))
                  .reset_index())

        map_df["hover"] = map_df.apply(
            lambda r: (f"ZIP: {r['zipcode']}<br>State: {r['state']}<br>"
                       f"Total: {fmt_cur(r['total'])}<br>Contributions: {int(r['count'])}"),
            axis=1
        )

        # Scale dot size between 8 and 28 px
        max_total = map_df["total"].max()
        map_df["size"] = map_df["total"].apply(
            lambda v: 8 + (v / max_total) * 20
        )

        fig_map = go.Figure()

        # ── Contribution dots ─────────────────────────────────────────────────
        fig_map.add_trace(go.Scattergeo(
            lat=map_df["lat"],
            lon=map_df["lon"],
            text=map_df["hover"],
            hoverinfo="text",
            mode="markers",
            name="Contributions",
            marker=dict(
                size=map_df["size"],
                color=map_df["total"],
                colorscale=[
                    [0.0, "#c8e6c9"],
                    [0.4, "#66bb6a"],
                    [0.7, "#2e7d32"],
                    [1.0, "#1b5e20"],
                ],
                cmin=map_df["total"].min(),
                cmax=map_df["total"].max(),
                colorbar=dict(
                    title=dict(text="$ Amount", side="right"),
                    thickness=14,
                    len=0.55,
                    y=0.5,
                ),
                line=dict(width=0.5, color="white"),
                opacity=0.88,
            ),
        ))

        # ── City name labels ──────────────────────────────────────────────────
        city_lats  = [c[1] for c in MAJOR_CITIES]
        city_lons  = [c[2] for c in MAJOR_CITIES]
        city_names = [c[0] for c in MAJOR_CITIES]

        fig_map.add_trace(go.Scattergeo(
            lat=city_lats,
            lon=city_lons,
            text=city_names,
            mode="text",
            name="Cities",
            textfont=dict(size=9, color="#000000"),
            hoverinfo="skip",
            showlegend=False,
        ))

        fig_map.update_layout(
            geo=dict(
                scope="usa",
                projection_type="albers usa",
                showland=True,
                landcolor="#f5f5f5",
                showlakes=True,
                lakecolor="#d4eaf7",
                showrivers=True,
                rivercolor="#d4eaf7",
                subunitcolor="#cccccc",
                subunitwidth=0.8,
                countrycolor="#aaaaaa",
                bgcolor="white",
                # Default view centered on Iowa; user can zoom out with toolbar
                center=dict(lat=42.0, lon=-93.5),
                lonaxis=dict(range=[-97.5, -89.5]),
                lataxis=dict(range=[40.2, 43.8]),
            ),
            margin=dict(l=0, r=0, t=10, b=0),
            height=520,
            paper_bgcolor="white",
            legend=dict(orientation="h", y=-0.02),
        )

        st.plotly_chart(fig_map, use_container_width=True)
        st.caption(
            "Dot size and color reflect contribution total per ZIP code. "
            "Use the Plotly toolbar (top-right of map) to zoom out and pan across the US."
        )

        # ── By-State Table ────────────────────────────────────────────────────
        st.subheader("Contributions by State")
        state_df = (geo_df.groupby("state")["amount"]
                    .sum().reset_index()
                    .rename(columns={"state":"State","amount":"Amount"})
                    .sort_values("Amount", ascending=False))

        total_mapped = state_df["Amount"].sum()
        state_df["% of Contributions"] = (state_df["Amount"] / receipts * 100).apply(fmt_pct)
        state_df["Amount"] = state_df["Amount"].apply(fmt_cur)
        st.dataframe(state_df.reset_index(drop=True), use_container_width=True, hide_index=True)

        unmapped = receipts - total_mapped
        if unmapped > 0.01:
            st.caption(
                f"Note: {fmt_cur(unmapped)} in contributions ({unmapped/receipts*100:.1f}%) "
                f"could not be mapped — unitemized or missing address data."
            )

except ImportError:
    st.warning("Install plotly (`pip install plotly`) to enable geographic analysis.")

st.markdown("<br>", unsafe_allow_html=True)
