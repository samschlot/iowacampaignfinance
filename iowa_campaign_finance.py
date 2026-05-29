"""
Iowa Campaign Finance Disclosure Viewer
----------------------------------------
Requirements:
    pip install streamlit pdfplumber plotly pandas pgeocode reportlab

Run:
    streamlit run iowa_campaign_finance.py
"""

import io, re, json
import ssl
import streamlit as st
import pdfplumber
import pandas as pd

# Fix for Mac Python SSL certificate verification issue
ssl._create_default_https_context = ssl._create_unverified_context
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, PageBreak, HRFlowable, KeepTogether, Image as RLImage)


# =============================================================================
#  PDF EXPORT
# =============================================================================

def build_pdf_report(d, contributions, exp_df_with_cats,
                     receipts, expenditures, debts, n_contribs, avg_contrib, burn_rate,
                     loans=None, notes_df=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.75*inch, rightMargin=0.75*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch,
        title=d["committee_name"],
    )

    base = getSampleStyleSheet()
    IOWA_BLUE  = colors.HexColor("#0d6efd")
    DARK       = colors.HexColor("#212529")
    MID        = colors.HexColor("#6c757d")
    LIGHT_GRAY = colors.HexColor("#f8f9fa")
    RULE_COLOR = colors.HexColor("#dee2e6")

    title_style = ParagraphStyle("T2", parent=base["Normal"],
        fontSize=22, fontName="Helvetica-Bold", textColor=DARK, spaceAfter=4, leading=26)
    meta_style  = ParagraphStyle("Meta", parent=base["Normal"],
        fontSize=9, textColor=MID, spaceAfter=16)
    section_style = ParagraphStyle("Sec", parent=base["Normal"],
        fontSize=13, fontName="Helvetica-Bold", textColor=DARK, spaceBefore=6, spaceAfter=8)
    sub_style = ParagraphStyle("Sub", parent=base["Normal"],
        fontSize=10, fontName="Helvetica-Bold", textColor=DARK, spaceBefore=10, spaceAfter=4)
    body_style = ParagraphStyle("Body", parent=base["Normal"],
        fontSize=9, textColor=DARK, leading=13)
    small_style = ParagraphStyle("Small", parent=base["Normal"],
        fontSize=8, textColor=MID, leading=11)

    def rule():
        return HRFlowable(width="100%", thickness=0.5, color=RULE_COLOR, spaceAfter=8, spaceBefore=4)

    def section_header(text):
        return [rule(), Paragraph(text, section_style)]

    def currency(v): return f"${v:,.2f}"
    def pct(v):      return f"{v:.1f}%"

    def data_table(headers, rows, col_widths=None, right_cols=None):
        right_cols = right_cols or []
        all_rows = [[Paragraph(f"<b>{h}</b>", small_style) for h in headers]]
        for row in rows:
            all_rows.append([Paragraph(str(c), small_style) for c in row])
        tw = 7.0*inch
        if col_widths is None:
            col_widths = [tw / len(headers)] * len(headers)
        t = Table(all_rows, colWidths=col_widths, repeatRows=1)
        style = [
            ("BACKGROUND",    (0,0), (-1,0),  colors.black),
            ("TEXTCOLOR",     (0,0), (-1,0),  colors.white),
            ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1), 8),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, LIGHT_GRAY]),
            ("GRID",          (0,0), (-1,-1), 0.3, RULE_COLOR),
            ("LEFTPADDING",   (0,0), (-1,-1), 5),
            ("RIGHTPADDING",  (0,0), (-1,-1), 5),
            ("TOPPADDING",    (0,0), (-1,-1), 3),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ]
        for col in right_cols:
            style.append(("ALIGN", (col,0), (col,-1), "RIGHT"))
        t.setStyle(TableStyle(style))
        return t

    story = []

    # ── COVER ─────────────────────────────────────────────────────────────────
    story.append(Paragraph(d["committee_name"], title_style))
    meta_parts = []
    if d.get("filed_date"):      meta_parts.append(f"Filed: {d['filed_date']}")
    if d.get("political_party"): meta_parts.append(f"Party: {d['political_party']}")
    if meta_parts:
        story.append(Paragraph(" · ".join(meta_parts), meta_style))

    # ── TOP LINES ─────────────────────────────────────────────────────────────
    story += section_header("Top Lines")
    burn_color = "#dc3545" if burn_rate > 80 else "#212529"
    debt_color = "#dc3545" if debts > 0 else "#212529"
    loans_color = "#0d6efd" if d.get("loans_received", 0) > 0 else "#212529"
    metrics = [
        ("Cash on Hand — Start of Period",              currency(d["cash_start"]),               "#212529"),
        ("Cash on Hand — End of Period",                currency(d["cash_end"]),                 "#0d6efd"),
        ("Receipts (Contributions + Loans + Sales)",    currency(receipts),                      "#198754"),
        ("Loans Received",                              currency(d.get("loans_received", 0)),    loans_color),
        ("Expenditures",                                currency(expenditures),                  "#dc3545"),
        ("Number of Contributions (incl. loans)",       f"{n_contribs:,}",                       "#212529"),
        ("Average Contribution",                        currency(avg_contrib),                   "#212529"),
        ("Burn Rate",                                   pct(burn_rate),                          burn_color),
        ("Debts",                                       currency(debts),                         debt_color),
    ]
    for i in range(0, len(metrics), 2):
        pair = metrics[i:i+2]
        row_data = []
        for label, value, col in pair:
            row_data.append(Paragraph(
                f'<font size="7" color="#6c757d">{label.upper()}</font><br/>'
                f'<font size="13" color="{col}"><b>{value}</b></font>',
                body_style))
        if len(row_data) == 1:
            row_data.append(Paragraph("", body_style))
        t = Table([row_data], colWidths=[3.5*inch, 3.5*inch])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), LIGHT_GRAY),
            ("BOX",           (0,0),(-1,-1), 0.5, RULE_COLOR),
            ("INNERGRID",     (0,0),(-1,-1), 0.5, RULE_COLOR),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("TOPPADDING",    (0,0),(-1,-1), 8),
            ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ]))
        story.append(t)
        story.append(Spacer(1, 3))

    # ── CONTRIBUTIONS ─────────────────────────────────────────────────────────
    story.append(PageBreak())
    story += section_header("Contributions Summary")

    if contributions:
        contrib_df = pd.DataFrame(contributions)
        pivot = (contrib_df.groupby("name")["amount"].sum().reset_index()
                 .rename(columns={"name":"Contributor","amount":"Total"})
                 .sort_values("Total", ascending=False))

        story.append(Paragraph("Top Donors ($10,000+)", sub_style))
        top = pivot[pivot["Total"] >= 10_000]
        if top.empty:
            story.append(Paragraph("No contributors donated $10,000 or more.", body_style))
        else:
            rows = [(r["Contributor"], currency(r["Total"])) for _, r in top.iterrows()]
            story.append(data_table(["Contributor","Total"],
                                    rows, [5.0*inch, 2.0*inch], right_cols=[1]))
        story.append(Spacer(1, 10))

        story.append(Paragraph("Other Notable Donors", sub_style))
        eligible = pivot[(pivot["Total"] < 10_000) &
                         (~pivot["Contributor"].isin(["Unitemized","Unknown"]))]
        notable = (pd.concat([eligible.head(10), eligible[eligible["Total"] >= 1_000]])
                   .drop_duplicates("Contributor").sort_values("Total", ascending=False))
        if notable.empty:
            story.append(Paragraph("No additional notable donors.", body_style))
        else:
            # Merge in any notes from the editable table
            if notes_df is not None and not notes_df.empty:
                notes_lookup = dict(zip(notes_df["Name"], notes_df.get("Notes", [""] * len(notes_df))))
            else:
                notes_lookup = {}

            def make_note_cell(name):
                """Return a Paragraph with clickable hyperlinks for PDF export.
                Supports [link text](https://url) and bare https:// URLs."""
                import re as _re
                note = notes_lookup.get(name, "")
                if not note:
                    return Paragraph("", small_style)

                # Process markdown links: [text](url) -> <link href="url">text</link>
                def md_link_replace(m):
                    txt, url = m.group(1), m.group(2)
                    return '<link href="' + url + '"><font color="#0d6efd"><u>' + txt + '</u></font></link>'

                note_html = _re.sub(
                    r'\[([^\]]+)\]\((https?://[^\)]+)\)',
                    md_link_replace,
                    note
                )

                # Process bare URLs not inside an existing link tag
                def bare_url_replace(m):
                    url = m.group(1)
                    return '<link href="' + url + '"><font color="#0d6efd"><u>' + url + '</u></font></link>'

                note_html = _re.sub(
                    r'(?<!["\(])(https?://[^\s<>"\)]+)',
                    bare_url_replace,
                    note_html
                )

                return Paragraph(note_html, small_style)

                        # Build table with notes column
            has_notes = any(notes_lookup.get(r["Contributor"], "") for _, r in notable.iterrows())
            if has_notes:
                headers = ["Contributor", "Total", "Notes"]
                col_w   = [2.5*inch, 1.3*inch, 3.2*inch]
                all_rows = [[Paragraph(f"<b>{h}</b>", small_style) for h in headers]]
                for _, r in notable.iterrows():
                    all_rows.append([
                        Paragraph(str(r["Contributor"]), small_style),
                        Paragraph(currency(r["Total"]), small_style),
                        make_note_cell(r["Contributor"]),
                    ])
            else:
                headers = ["Contributor", "Total"]
                col_w   = [5.0*inch, 2.0*inch]
                all_rows = [[Paragraph(f"<b>{h}</b>", small_style) for h in headers]]
                for _, r in notable.iterrows():
                    all_rows.append([
                        Paragraph(str(r["Contributor"]), small_style),
                        Paragraph(currency(r["Total"]), small_style),
                    ])

            IOWA_BLUE  = colors.HexColor("#0d6efd")
            LIGHT_GRAY = colors.HexColor("#f8f9fa")
            RULE_COLOR = colors.HexColor("#dee2e6")
            t = Table(all_rows, colWidths=col_w, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,0),  colors.black),
                ("TEXTCOLOR",     (0,0), (-1,0),  colors.white),
                ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
                ("FONTSIZE",      (0,0), (-1,-1), 8),
                ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, LIGHT_GRAY]),
                ("GRID",          (0,0), (-1,-1), 0.3, RULE_COLOR),
                ("LEFTPADDING",   (0,0), (-1,-1), 5),
                ("RIGHTPADDING",  (0,0), (-1,-1), 5),
                ("TOPPADDING",    (0,0), (-1,-1), 3),
                ("BOTTOMPADDING", (0,0), (-1,-1), 3),
                ("ALIGN",         (1,0), (1,-1),  "RIGHT"),
                ("VALIGN",        (0,0), (-1,-1), "TOP"),
            ]))
            story.append(t)

    # ── LOANS RECEIVED ────────────────────────────────────────────────────────
    if loans and d.get("loans_received", 0) > 0:
        story.append(Spacer(1, 8))
        story += section_header("Loans Received")

        # Summary row
        loans_summary = [
            ("Total Loans Received This Period", currency(d.get("loans_received", 0))),
            ("Outstanding Loans End of Period",  currency(d.get("outstanding_loans", 0))),
        ]
        summary_data = [[
            Paragraph(
                f'<font size="7" color="#6c757d">{lbl.upper()}</font><br/>'
                f'<font size="11" color="#0d6efd"><b>{val}</b></font>',
                body_style)
            for lbl, val in loans_summary
        ]]
        ls_t = Table(summary_data, colWidths=[3.5*inch, 3.5*inch])
        ls_t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), LIGHT_GRAY),
            ("BOX",           (0,0),(-1,-1), 0.5, RULE_COLOR),
            ("INNERGRID",     (0,0),(-1,-1), 0.5, RULE_COLOR),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("TOPPADDING",    (0,0),(-1,-1), 8),
            ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ]))
        story.append(ls_t)
        story.append(Spacer(1, 8))

        # Loan detail table
        loan_rows = [(currency(l["amount"]), l["name"], l.get("relationship",""), l["date"])
                     for l in loans]
        story.append(data_table(
            ["Amount", "Lender", "Relationship", "Date"],
            loan_rows,
            [1.4*inch, 3.0*inch, 1.2*inch, 1.4*inch],
            right_cols=[0]
        ))

    # ── EXPENDITURES ──────────────────────────────────────────────────────────
    story.append(PageBreak())
    story += section_header("Expenditures Summary")

    exp_pivot = (exp_df_with_cats.groupby("eff_cat")["amount"].sum().reset_index()
                 .rename(columns={"eff_cat":"Category","amount":"Total"})
                 .sort_values("Total", ascending=False))

    for idx, cat_row in exp_pivot.iterrows():
        cat   = cat_row["Category"]
        total = cat_row["Total"]
        items = (exp_df_with_cats[exp_df_with_cats["eff_cat"] == cat]
                 .sort_values("amount", ascending=False))

        story.append(Paragraph(f"<b>{cat}</b> — {currency(total)}", sub_style))

        big = items[items["amount"] >= 1000]
        if not big.empty:
            rows = [(currency(r["amount"]), r["name"], r["date"]) for _, r in big.iterrows()]
            story.append(data_table(["Amount","Payee","Date"],
                                    rows, [1.4*inch, 3.8*inch, 1.8*inch], right_cols=[0]))

        small = items[items["amount"] < 1000]
        if not small.empty:
            n, tot = len(small), small["amount"].sum()
            story.append(Paragraph(
                f'<i>{n} smaller expense{"s" if n!=1 else ""} totalling {currency(tot)}</i>',
                small_style))
        story.append(Spacer(1, 6))

    # ── GEO SUMMARY ───────────────────────────────────────────────────────────
    story.append(PageBreak())
    story += section_header("Geographic Summary — Contributions by State")

    if contributions:
        cdf = pd.DataFrame(contributions)

        # Try to render map image via plotly + kaleido
        map_img_bytes = None
        iowa_img_bytes = None
        try:
            import plotly.graph_objects as go

            geo_rows = []
            unique_zips_pdf = [c["zipcode"] for c in contributions
                               if c["name"] not in ("Unitemized","Unknown") and c.get("zipcode")]
            zip_coords_pdf = batch_geocode(unique_zips_pdf)
            for c in contributions:
                if c["name"] in ("Unitemized","Unknown") or not c.get("zipcode"):
                    continue
                coords = zip_coords_pdf.get(str(c["zipcode"]).zfill(5))
                if coords:
                    geo_rows.append({**c, "lat": coords[0], "lon": coords[1]})

            if geo_rows:
                gdf = pd.DataFrame(geo_rows)
                map_df = (gdf.groupby(["zipcode","lat","lon","state"])
                          .agg(total=("amount","sum"), count=("amount","count"))
                          .reset_index())
                mx = map_df["total"].max()
                map_df["size"] = map_df["total"].apply(lambda v: 5 + (v/mx)*12)

                def _make_map_fig(city_labels, lon_range, lat_range, height, width,
                                  title_text=None, proj_scale=1.0, proj_center=None):
                    """Build a Plotly geo figure for PDF export."""
                    fig = go.Figure()
                    fig.add_trace(go.Scattergeo(
                        lat=map_df["lat"], lon=map_df["lon"],
                        text=map_df.apply(
                            lambda r: f"ZIP: {r['zipcode']}<br>State: {r['state']}<br>"
                                      f"Total: {currency(r['total'])}", axis=1),
                        hoverinfo="text", mode="markers",
                        marker=dict(
                            size=map_df["size"], color=map_df["total"],
                            colorscale=[[0,"#c8e6c9"],[0.4,"#66bb6a"],[0.7,"#2e7d32"],[1,"#1b5e20"]],
                            cmin=map_df["total"].min(), cmax=mx,
                            colorbar=dict(title=dict(text="$",side="right"), thickness=10, len=0.5),
                            line=dict(width=0.5, color="white"), opacity=0.88,
                        ),
                    ))
                    if city_labels:
                        fig.add_trace(go.Scattergeo(
                            lat=[c[1] for c in city_labels],
                            lon=[c[2] for c in city_labels],
                            text=[c[0] for c in city_labels],
                            mode="text",
                            textfont=dict(size=7, color="#000000"),
                            hoverinfo="skip", showlegend=False,
                        ))
                    geo_dict = dict(
                        scope="usa", projection_type="albers usa",
                        showland=True, landcolor="#f5f5f5",
                        showlakes=True, lakecolor="#d4eaf7",
                        showrivers=True, rivercolor="#d4eaf7",
                        subunitcolor="#cccccc", subunitwidth=0.8,
                        bgcolor="white",
                        projection=dict(scale=proj_scale),
                    )
                    if proj_center:
                        geo_dict["center"] = proj_center
                    fig.update_layout(
                        geo=geo_dict,
                        title=dict(text=title_text, x=0.5, font=dict(size=11)) if title_text else None,
                        margin=dict(l=0, r=0, t=30 if title_text else 10, b=0),
                        height=height, width=width,
                        paper_bgcolor="white",
                    )
                    return fig

                # National labels: only Des Moines from Iowa, plus major US cities
                IOWA_CITY_NAMES = {"Des Moines","Cedar Rapids","Davenport",
                                   "Sioux City","Iowa City","Waterloo","Dubuque"}
                national_labels = [c for c in MAJOR_CITIES if c[0] not in
                                   (IOWA_CITY_NAMES - {"Des Moines"})]
                iowa_labels = [c for c in MAJOR_CITIES if c[0] in IOWA_CITY_NAMES]

                # Full US map — use projection center, not lat/lon range
                fig_us = _make_map_fig(
                    city_labels=national_labels,
                    lon_range=[-124, -68], lat_range=[23, 50],
                    height=340, width=720,
                    title_text="Contributions — National View",
                )
                buf_us = io.BytesIO()
                fig_us.write_image(buf_us, format="png", scale=2)
                map_img_bytes = buf_us.getvalue()

                # Iowa zoomed map — use projection scale+center rather than ranges
                # scale=4 zooms in ~4x on Iowa; center puts Iowa in the middle
                fig_ia = _make_map_fig(
                    city_labels=iowa_labels,
                    lon_range=[-96.8, -90.1], lat_range=[40.4, 43.6],
                    height=340, width=720,
                    title_text="Contributions — Iowa Detail",
                    proj_scale=4.0,
                    proj_center=dict(lat=42.0, lon=-93.5),
                )
                buf_ia = io.BytesIO()
                fig_ia.write_image(buf_ia, format="png", scale=2)
                iowa_img_bytes = buf_ia.getvalue()
        except Exception as _kaleido_err:
            pass  # kaleido not installed or geocoder unavailable — skip map image

        if map_img_bytes:
            story.append(RLImage(io.BytesIO(map_img_bytes), width=7.0*inch, height=3.3*inch))
            story.append(Spacer(1, 6))
        if 'iowa_img_bytes' in dir() and iowa_img_bytes:
            story.append(RLImage(io.BytesIO(iowa_img_bytes), width=7.0*inch, height=3.3*inch))
            story.append(Spacer(1, 8))

        # By-state table
        state_df = (cdf[~cdf["state"].isin(["","Unknown"])]
                    .groupby("state")["amount"].sum().reset_index()
                    .rename(columns={"state":"State","amount":"Amount"})
                    .sort_values("Amount", ascending=False))
        if not state_df.empty:
            cdf_pdf = pd.DataFrame(contributions)
            state_counts_pdf = (cdf_pdf[~cdf_pdf["state"].isin(["","Unknown","Unitemized"])]
                                .groupby("state")["amount"].count().reset_index()
                                .rename(columns={"state":"State","amount":"# Contributions"}))
            state_df = state_df.merge(state_counts_pdf, on="State", how="left")
            state_df["% of Contributions"] = (state_df["Amount"]/receipts*100).apply(pct)
            state_df = state_df.head(10)
            rows = [(r["State"], int(r["# Contributions"]), currency(r["Amount"]), r["% of Contributions"])
                    for _, r in state_df.iterrows()]
            story.append(data_table(
                ["State","# Contributions","Amount","% of Contributions"],
                rows, [1.0*inch, 1.5*inch, 2.5*inch, 2.0*inch], right_cols=[1,2,3]))

        if not map_img_bytes:
            story.append(Spacer(1,6))
            story.append(Paragraph(
                "Map image unavailable — install kaleido (`pip install kaleido`) to include it.",
                small_style))

    doc.build(story)
    return buf.getvalue()

st.set_page_config(page_title="Iowa Campaign Finance Viewer", page_icon="🗳️", layout="wide")

st.markdown("""
<style>
    .metric-card { background:#f8f9fa; border:1px solid #dee2e6; border-radius:8px;
                   padding:16px 20px; margin-bottom:10px; }
    .metric-label { font-size:0.75rem; color:#6c757d; text-transform:uppercase;
                    letter-spacing:0.06em; margin-bottom:4px; }
    .metric-value        { font-size:1.5rem; font-weight:700; color:#212529; }
    .metric-value.green  { color:#198754; }
    .metric-value.red    { color:#dc3545; }
    .metric-value.blue   { color:#0d6efd; }
    .section-header { font-size:1.05rem; font-weight:600; color:#343a40;
                      border-bottom:2px solid #dee2e6; padding-bottom:6px; margin:28px 0 14px; }
    .committee-title { font-size:1.9rem; font-weight:700; color:#212529; margin-bottom:2px; }
    .report-meta { font-size:0.85rem; color:#6c757d; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
#  CITY LABELS
# =============================================================================
MAJOR_CITIES = [
    # Iowa — only the most prominent
    ("Des Moines",     41.5868, -93.6250),
    ("Cedar Rapids",   41.9779, -91.6656),
    ("Davenport",      41.5236, -90.5776),
    ("Sioux City",     42.4999, -96.4003),
    ("Iowa City",      41.6611, -91.5302),
    ("Waterloo",       42.4928, -92.3426),
    ("Dubuque",        42.5006, -90.6646),
    # Major US cities only
    ("New York",       40.7128, -74.0060),
    ("Los Angeles",    34.0522,-118.2437),
    ("Chicago",        41.8781, -87.6298),
    ("Houston",        29.7604, -95.3698),
    ("Phoenix",        33.4484,-112.0740),
    ("Philadelphia",   39.9526, -75.1652),
    ("San Antonio",    29.4241, -98.4936),
    ("San Diego",      32.7157,-117.1611),
    ("Dallas",         32.7767, -96.7970),
    ("San Francisco",  37.7749,-122.4194),
    ("Seattle",        47.6062,-122.3321),
    ("Denver",         39.7392,-104.9903),
    ("Washington DC",  38.9072, -77.0369),
    ("Boston",         42.3601, -71.0589),
    ("Atlanta",        33.7490, -84.3880),
    ("Miami",          25.7617, -80.1918),
    ("Minneapolis",    44.9778, -93.2650),
    ("Kansas City",    39.0997, -94.5786),
    ("Omaha",          41.2565, -95.9345),
    ("St. Louis",      38.6270, -90.1994),
    ("Nashville",      36.1627, -86.7816),
    ("Las Vegas",      36.1699,-115.1398),
    ("Portland",       45.5051,-122.6750),
    ("Salt Lake City", 40.7608,-111.8910),
    ("Sioux Falls",    43.5473, -96.7283),
]



# =============================================================================
#  ZIP GEOCODER  — cached so it only downloads once per session
# =============================================================================
def load_geocoder():
    """Load pgeocode geocoder — no caching so installs are picked up immediately."""
    try:
        import pgeocode
        return pgeocode.Nominatim("us")
    except ImportError:
        return None

def batch_geocode(zipcodes: list) -> dict:
    """
    Geocode a list of unique zip codes in one vectorised call.
    Returns dict {zipcode: (lat, lon)} for all successfully resolved zips.
    """
    try:
        import pgeocode
        nomi = pgeocode.Nominatim("us")
        unique = list(set(str(z).zfill(5) for z in zipcodes if z))
        if not unique:
            return {}
        # query_postal_code accepts a list and returns a DataFrame
        # with the postal_code column matching our input order
        results = nomi.query_postal_code(unique)
        out = {}
        # results.postal_code aligns with our unique list
        for _, row in results.iterrows():
            z = str(row.get("postal_code", "")).zfill(5)
            if z and not pd.isna(row["latitude"]) and not pd.isna(row["longitude"]):
                out[z] = (float(row["latitude"]), float(row["longitude"]))
        return out
    except Exception:
        return {}


# =============================================================================
#  PARSING
# =============================================================================
MONEY_RE       = re.compile(r"\$([\d,]+\.\d{2})")
IOWA_FOOTER_RE = re.compile(r"^IOWA ETHICS AND CAMPAIGN")
CITY_LINE_RE   = re.compile(r".+,\s+[A-Z]{2}\s+\d{5}")
EXP_DATA_RE    = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4})\s+.+?\s+\$([\d,]+\.\d{2})\s*$")
# Handles: DATE [Check # ] ADDRESS [Relation] $AMT
CONTRIB_DATA_RE = re.compile(
    r"^(\d{2}/\d{2}/\d{4})\s+(?:Check #\s+)?(.+?)\s+"
    r"(?:(None|Self|Brother|Sister|Spouse|Father|Mother|Son|Daughter|"
    r"Aunt|Uncle|Cousin|Friend|Employer|Employee)\s+)?"
    r"\$([\d,]+\.\d{2})\s*$"
)
# Andrews-style single-line unitemized: "MM/DD/YYYY Unitemized $X.XX"
UNITEMIZED_RE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+Unitemized\s+\$([\d,]+\.\d{2})\s*$")

HEADER_SKIP_RE = re.compile(
    r"^(Committee Type:|County:|District:|Committee Code:|Political Party:|"
    r"Report Date:|Candidate Name:|Treasurer|Last Name:|Address:|City:|"
    r"Chairperson|Statement of|Additional Assets|Generated On|"
    r"Contribution Contribution|Name and Address|Date Committee|"
    r"Expenditure Expenditure|Schedule [A-Z]\d?:|DR-2 |Filed Date|"
    r"Statutory|Adjusted|Postmark|Amendment|E-Mail:|Grand Total|"
    r"Total Regular|Total Fundraiser|Total Amount|Sub-Total|Loans In|"
    r"Status:|Sch-)"
)
PURPOSE_WORDS = {
    "Other","Expenditure","Consultant","Services","Salary &","Gratuity",
    "Mileage","Travel","Charitable","Contributions","Fundraiser","Food",
    "Printing &","Reproduction","Bank Charges","Advertising","Professional",
    "Fees","Political","Contribution","Reimbursement","Meals",
}

def parse_money(s):
    m = MONEY_RE.search(s); return float(m.group(1).replace(",","")) if m else 0.0

def is_skip(s):
    return not s or IOWA_FOOTER_RE.match(s) or HEADER_SKIP_RE.match(s) or re.match(r"^\d+ of \d+$", s)

def is_purpose(s):
    if s in PURPOSE_WORDS: return True
    stripped = re.sub(r"^Check #\s*\d*\s*", "", s).strip()
    return stripped in PURPOSE_WORDS

def extract_lines(pdf_bytes):
    lines = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            lines.extend((page.extract_text() or "").splitlines())
    return lines

def parse_summary_fields(lines):
    d = {"committee_name":"","report_date":"","filed_date":"","political_party":"",
         "cash_start":0.0,"cash_contributions":0.0,"loans_received":0.0,
         "property_sales":0.0,"receipts":0.0,"expenditures":0.0,"cash_end":0.0,
         "unpaid_bills":0.0,"outstanding_loans":0.0}
    for i, line in enumerate(lines):
        s = line.strip()
        if "DR-2 Disclosure Summary Page DR-2" in s:
            for j in range(i+1, min(i+5, len(lines))):
                cand = lines[j].strip()
                if cand and not cand.startswith("Generated On"):
                    d["committee_name"] = re.split(r"\s{2,}|Status:", cand)[0].strip(); break
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
            ("Schedule A: Cash Contributions Total","cash_contributions"),
            ("Schedule F1: Loans Received Total","loans_received"),
            ("Schedule H2: Campaign Property Sales","property_sales"),
            ("Schedule B: Expenditure Total","expenditures"),
            ("Cash on Hand at End of Period","cash_end"),
            ("Schedule D: Unpaid Bills","unpaid_bills"),
            ("Schedule F2: Outstanding Loans","outstanding_loans"),
        ]:
            if label.lower() in s.lower(): d[key] = parse_money(s)
    # Composite receipts = cash contributions + loans received + property sales
    d["receipts"] = d["cash_contributions"] + d["loans_received"] + d["property_sales"]
    return d

def parse_contributions(lines):
    contribs = []
    in_section = False
    for i, line in enumerate(lines):
        s = line.strip()
        if "Schedule A: Contributions" in s or "Sch-A" in s:
            in_section = True; continue
        if in_section and "Schedule B: Expenditures" in s: break
        if not in_section: continue

        # Andrews-style single-line unitemized
        m_u = UNITEMIZED_RE.match(s)
        if m_u:
            contribs.append({"date":m_u.group(1),"name":"Unitemized",
                              "state":"","zipcode":"","amount":float(m_u.group(2).replace(",",""))})
            continue

        m = CONTRIB_DATA_RE.match(s)
        if not m: continue
        date   = m.group(1)
        amount = float(m.group(4).replace(",",""))

        # Walk back for name
        name = ""
        for k in range(i-1, max(i-7,-1), -1):
            cand = lines[k].strip()
            if not cand or is_skip(cand): continue
            if CONTRIB_DATA_RE.match(cand) or UNITEMIZED_RE.match(cand): break
            if CITY_LINE_RE.match(cand): continue
            if cand == "Check #" or re.match(r"^\d+$", cand): continue
            if is_purpose(cand): continue
            name = cand; break

        if not name or is_purpose(name): name = "Unknown"
        if name.lower().startswith("unitemized"): name = "Unitemized"

        state = zipcode = ""
        # City/state may be on line i+1 (normal) or i+2 (when check number is on i+1)
        for offset in (1, 2):
            if i + offset < len(lines):
                m2 = re.search(r",\s+([A-Z]{2})\s+(\d{5})", lines[i + offset])
                if m2:
                    state, zipcode = m2.group(1), m2.group(2)
                    break
        contribs.append({"date":date,"name":name,"state":state,"zipcode":zipcode,"amount":amount})
    return contribs

def parse_loans(lines):
    """
    Parse Schedule F1: Loans Received.

    The table layout (from actual PDF x-positions) is:
      Col 1 — Date Incurred     x ≈ 38
      Col 2 — Name / Address    x ≈ 102  (lender name appears one line above the date row)
      Col 3 — Relationship      x ≈ 302
      Col 4 — Amount of Loan    x ≈ 518

    A single entry looks like (in extracted text order):
        Lahn, Zach                     ← name line (no date on this line)
        5/22/2026  PO Box 129  Self  $500,000.00
        Belle Plaine IA 52208          ← city/state line
    """
    loans = []
    in_section = False
    i = 0
    while i < len(lines):
        s = lines[i].strip()

        # Section boundaries — must match the actual schedule header (has "Sch-F1"),
        # NOT the summary line "Schedule F1: Loans Received Total $X"
        if "Schedule F1: Loans Received" in s and "Sch-F1" in s:
            in_section = True; i += 1; continue
        if in_section and re.match(
                r"^(Total Received|Total Unpaid|Total Loans Paid|Total Forgiven|"
                r"Total Outstanding|Schedule F2:|Schedule B:|Schedule G:|Schedule D:)", s):
            break
        if not in_section or is_skip(s): i += 1; continue

        # A data row starts with a date followed by address text and ends with $amount
        # Pattern: DATE  <address words>  [RELATIONSHIP]  $AMOUNT
        date_m = re.match(r"^(\d{1,2}/\d{1,2}/\d{4})\s+(.+?)\s+\$([\d,]+\.\d{2})\s*$", s)
        if date_m:
            date      = date_m.group(1)
            mid_text  = date_m.group(2).strip()
            amount    = float(date_m.group(3).replace(",", ""))

            # Relationship keyword typically ends the mid_text
            relationship = ""
            rel_m = re.search(r"\b(Self|Spouse|Family|PAC|Other)\b", mid_text, re.I)
            if rel_m:
                relationship = rel_m.group(1)

            # Name is on the line immediately before the date row
            # (walk back skipping blank / header lines)
            name = ""
            for k in range(i - 1, max(i - 6, -1), -1):
                cand = lines[k].strip()
                if not cand or is_skip(cand): continue
                # Stop if we hit another data row or a section header
                if re.match(r"^(\d{1,2}/\d{1,2}/\d{4})", cand): break
                if CITY_LINE_RE.match(cand): continue
                if is_purpose(cand): continue
                # This should be the lender name
                name = cand
                break

            # State / zip from the city line after the date row
            state = zipcode = ""
            if i + 1 < len(lines):
                m2 = re.search(r",?\s+([A-Z]{2})\s+(\d{5})", lines[i + 1])
                if m2:
                    state, zipcode = m2.group(1), m2.group(2)

            loans.append({
                "date":         date,
                "name":         name or "Unknown",
                "relationship": relationship,
                "state":        state,
                "zipcode":      zipcode,
                "amount":       amount,
            })
        i += 1
    return loans

def parse_expenditures(lines):
    exp_list = []
    in_section = False
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if "Schedule B: Expenditures" in s and "Sch-B" in s:
            in_section = True; i += 1; continue
        if in_section and s.startswith("Total Amount"): break
        if not in_section or is_skip(s): i += 1; continue

        m = EXP_DATA_RE.match(s)
        if m:
            date   = m.group(1)
            amount = float(m.group(2).replace(",",""))
            name = ""
            for k in range(i-1, max(i-7,-1), -1):
                cand = lines[k].strip()
                if not cand or is_skip(cand): continue
                if EXP_DATA_RE.match(cand): break
                if CITY_LINE_RE.match(cand): continue
                if cand == "Check #" or re.match(r"^\d+$", cand): continue
                if is_purpose(cand): continue
                name = cand; break

            desc = ""
            j = i + 1
            city_found = False
            while j < len(lines) and j < i + 6:
                cand = lines[j].strip()
                if not cand or is_skip(cand): j += 1; continue
                if EXP_DATA_RE.match(cand): break
                if CITY_LINE_RE.match(cand): city_found = True; j += 1; continue
                if city_found:
                    if not re.match(r"^\d+$", cand) and not is_purpose(cand):
                        desc = cand; break
                j += 1

            exp_list.append({"date":date,"name":name or "Unknown",
                              "category":desc or "Other","amount":amount})
        i += 1
    return exp_list

def parse_disclosure(pdf_bytes):
    lines = extract_lines(pdf_bytes)
    return {**parse_summary_fields(lines),
            "contributions":     parse_contributions(lines),
            "loans":             parse_loans(lines),
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
st.caption("Upload an Iowa Ethics & Campaign Disclosure Board DR-2 PDF.")

uploaded = st.file_uploader("Upload DR-2 Disclosure PDF", type=["pdf"])
if not uploaded:
    st.info("Upload a DR-2 disclosure PDF above to get started.")
    st.stop()

# Parse once per file, cache in session state
file_id = uploaded.name + str(uploaded.size)
if st.session_state.get("file_id") != file_id:
    with st.spinner("Parsing disclosure…"):
        d = parse_disclosure(uploaded.read())
    st.session_state["file_id"]   = file_id
    st.session_state["disclosure"] = d
    # Build initial expenditure category map: category -> list of indices
    st.session_state["exp_categories"] = {
        e["category"]: e["category"] for e in d["expenditures_list"]
    }
    # Reset any edits
    st.session_state.pop("exp_overrides", None)
    st.session_state.pop("merged_cats", None)

d             = st.session_state["disclosure"]
contributions = d["contributions"]
loans         = d.get("loans", [])
exp_list      = d["expenditures_list"]
receipts      = d["receipts"]          # cash contributions + loans received + property sales
expenditures  = d["expenditures"]
debts         = d["unpaid_bills"] + d["outstanding_loans"]
n_contribs    = len(contributions) + len(loans)   # includes loans
itemized      = [c for c in contributions if c["name"] not in ("Unitemized","Unknown")]
avg_contrib   = receipts / n_contribs if n_contribs else 0.0
burn_rate     = (expenditures / receipts * 100) if receipts else 0.0


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f'<div class="committee-title">{d["committee_name"]}</div>', unsafe_allow_html=True)
meta = []
if d["filed_date"]:      meta.append(f"Filed: {d['filed_date']}")
if d["political_party"]: meta.append(f"Party: {d['political_party']}")
if meta:
    st.markdown(f'<div class="report-meta">{" &nbsp;|&nbsp; ".join(meta)}</div>',
                unsafe_allow_html=True)

# ── Top Lines ─────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">📊 Top Lines</div>', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(metric_card("Cash on Hand at Start of Period", fmt_cur(d["cash_start"])), unsafe_allow_html=True)
    st.markdown(metric_card("Receipts (Contributions + Loans + Sales)", fmt_cur(receipts), "green"), unsafe_allow_html=True)
    st.markdown(metric_card("Number of Contributions (including loans)", f"{n_contribs:,}"), unsafe_allow_html=True)
with c2:
    st.markdown(metric_card("Cash on Hand (End of Period)", fmt_cur(d["cash_end"]), "blue"), unsafe_allow_html=True)
    st.markdown(metric_card("Expenditures", fmt_cur(expenditures), "red"), unsafe_allow_html=True)
    st.markdown(metric_card("Average Contribution", fmt_cur(avg_contrib)), unsafe_allow_html=True)
with c3:
    st.markdown(metric_card("Loans Received", fmt_cur(d["loans_received"]), "blue" if d["loans_received"] > 0 else ""), unsafe_allow_html=True)
    st.markdown(metric_card("Burn Rate", fmt_pct(burn_rate), "red" if burn_rate > 80 else ""), unsafe_allow_html=True)
    st.markdown(metric_card("Debts", fmt_cur(debts), "red" if debts > 0 else ""), unsafe_allow_html=True)


# ── Contributions ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">💰 Contributions Summary</div>', unsafe_allow_html=True)

if contributions:
    contrib_df = pd.DataFrame(contributions)
    pivot = (contrib_df.groupby("name")["amount"].sum().reset_index()
             .rename(columns={"name":"Contributor","amount":"Total"})
             .sort_values("Total", ascending=False))

    # Top donors >= $10,000
    st.subheader("Top Donors ($10,000+)")
    top = pivot[pivot["Total"] >= 10_000].copy()
    if top.empty:
        st.info("No contributors donated $10,000 or more in this period.")
    else:
        top_d = top.copy(); top_d["Total"] = top_d["Total"].apply(fmt_cur)
        st.dataframe(top_d.reset_index(drop=True), use_container_width=True, hide_index=True)

    # Notable donors: top 10 under $10k AND anyone $1,000+, excluding Unitemized/Unknown
    st.subheader("Other Notable Donors")
    st.caption("Top contributors under $10,000 — anyone $1,000+ is always included. Add notes as needed.")
    eligible = pivot[
        (pivot["Total"] < 10_000) &
        (~pivot["Contributor"].isin(["Unitemized","Unknown"]))
    ].copy().sort_values("Total", ascending=False)

    # Include: top 10 OR >= $1,000
    top10 = eligible.head(10)
    over1k = eligible[eligible["Total"] >= 1_000]
    notable = pd.concat([top10, over1k]).drop_duplicates("Contributor").sort_values("Total", ascending=False)

    notable_init = pd.DataFrame({
        "Name":         notable["Contributor"].astype(str).tolist(),
        "Contribution": notable["Total"].apply(fmt_cur).tolist(),
        "Notes":        [""] * len(notable),
    })
    st.data_editor(notable_init, use_container_width=True, num_rows="dynamic",
                   column_config={
                       "Name":         st.column_config.TextColumn("Name"),
                       "Contribution": st.column_config.TextColumn("Contribution", disabled=True),
                       "Notes":        st.column_config.TextColumn(
                           "Notes",
                           help="Add notes. Use [link text](https://url.com) for hyperlinks in PDF export."
                       ),
                   }, hide_index=False, key="notable_donors")
else:
    st.warning("No contribution data could be parsed.")


# ── Loans Received ────────────────────────────────────────────────────────────
if loans or d.get("loans_received", 0) > 0:
    st.markdown('<div class="section-header">🏦 Loans Received</div>', unsafe_allow_html=True)
    lc1, lc2 = st.columns(2)
    with lc1:
        st.markdown(metric_card("Total Loans Received This Period", fmt_cur(d["loans_received"]), "blue"), unsafe_allow_html=True)
    with lc2:
        st.markdown(metric_card("Outstanding Loans End of Period", fmt_cur(d["outstanding_loans"]), "red" if d["outstanding_loans"] > 0 else ""), unsafe_allow_html=True)

    if loans:
        loans_df = pd.DataFrame(loans)
        loans_df["amount_fmt"] = loans_df["amount"].apply(fmt_cur)
        display_loans = loans_df[["date","name","relationship","amount_fmt"]].rename(columns={
            "date":"Date","name":"Lender","relationship":"Relationship","amount_fmt":"Amount"
        })
        st.dataframe(display_loans.reset_index(drop=True), use_container_width=True, hide_index=True)
    else:
        st.info(f"Loan total of {fmt_cur(d['loans_received'])} found in summary. "
                "No individual loan line items were parsed from Schedule F1.")


# ── Expenditures ──────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">💸 Expenditures Summary</div>', unsafe_allow_html=True)

# Initialize exp_df so PDF export can always access it
exp_df = pd.DataFrame(exp_list).reset_index(drop=True) if exp_list else pd.DataFrame()
if exp_list:
    exp_df["idx"] = exp_df.index  # stable row ID

    # Load per-row overrides from session state
    if "exp_overrides" not in st.session_state:
        st.session_state["exp_overrides"] = {}   # idx -> new_category string
    if "merged_cats" not in st.session_state:
        st.session_state["merged_cats"] = {}     # old_cat -> new_cat (merge map)

    overrides  = st.session_state["exp_overrides"]
    merged     = st.session_state["merged_cats"]

    # Apply overrides and merges to get effective category for each row
    def effective_cat(row):
        if str(row["idx"]) in overrides:
            return overrides[str(row["idx"])].title()
        cat = row["category"].title()
        return merged.get(cat, cat)

    exp_df["eff_cat"] = exp_df.apply(effective_cat, axis=1)

    # All current category names (for dropdowns)
    all_cats = sorted(exp_df["eff_cat"].unique().tolist())

    # ── Merge categories tool ─────────────────────────────────────────────────
    with st.expander("🔀 Merge categories"):
        st.caption("Select two or more categories to combine them under one name.")
        cats_to_merge = st.multiselect("Categories to merge", all_cats, key="merge_select")
        new_name = st.text_input("New combined name", key="merge_name")
        if st.button("Apply merge", key="apply_merge"):
            if len(cats_to_merge) >= 2 and new_name.strip():
                for c in cats_to_merge:
                    st.session_state["merged_cats"][c] = new_name.strip()
                st.rerun()
            else:
                st.warning("Select at least 2 categories and enter a name.")

    # Refresh after potential rerun
    exp_df["eff_cat"] = exp_df.apply(effective_cat, axis=1)
    all_cats = sorted(exp_df["eff_cat"].unique().tolist())

    # ── Add new category ──────────────────────────────────────────────────────
    with st.expander("➕ Add a new category"):
        new_cat_name = st.text_input("New category name", key="new_cat_input")
        if st.button("Create category", key="create_cat"):
            if new_cat_name.strip() and new_cat_name.strip() not in all_cats:
                # Just adds to dropdown options — user assigns rows to it below
                all_cats = sorted(all_cats + [new_cat_name.strip()])
                st.success(f"Category '{new_cat_name.strip()}' created. Assign expenses to it below.")
                st.rerun()

    # ── Pivot & display ───────────────────────────────────────────────────────
    exp_pivot = (exp_df.groupby("eff_cat")["amount"].sum().reset_index()
                 .rename(columns={"eff_cat":"Category","amount":"Total"})
                 .sort_values("Total", ascending=False))

    st.caption("Auto-itemized above $1,000. Re-categorize smaller items using the dropdown.")

    for _, row in exp_pivot.iterrows():
        cat   = row["Category"]
        total = row["Total"]
        items = exp_df[exp_df["eff_cat"] == cat].sort_values("amount", ascending=False).copy()

        with st.expander(f"**{cat}** — {fmt_cur(total)}"):
            auto_items  = items[items["amount"] >= 1000]
            small_items = items[items["amount"] <  1000]

            # Auto-itemized (>= $1,000) — read-only
            if not auto_items.empty:
                st.markdown("**Itemized (≥ $1,000)**")
                disp = auto_items[["amount","name","date"]].copy()
                disp["amount"] = disp["amount"].apply(fmt_cur)
                disp.columns = ["Amount","Payee","Date"]
                st.dataframe(disp.reset_index(drop=True), use_container_width=True, hide_index=True)

            # Small items — re-categorizable
            if not small_items.empty:
                st.markdown("**Smaller expenses — re-categorize as needed**")
                for _, r in small_items.iterrows():
                    col_a, col_b, col_c = st.columns([2, 2, 3])
                    col_a.write(fmt_cur(r["amount"]))
                    col_b.write(r["name"])
                    current = effective_cat(r)
                    chosen = col_c.selectbox(
                        "Category",
                        options=all_cats,
                        index=all_cats.index(current) if current in all_cats else 0,
                        key=f"cat_{r['idx']}",
                        label_visibility="collapsed",
                    )
                    if chosen != current:
                        st.session_state["exp_overrides"][str(r["idx"])] = chosen
                        st.rerun()

    # Bar chart — top 20 categories
    try:
        import plotly.express as px
        chart_df = exp_pivot.head(20)
        fig = px.bar(chart_df, x="Total", y="Category", orientation="h",
                     text=chart_df["Total"].apply(fmt_cur),
                     title="Top Expenditure Categories",
                     labels={"Total":"Amount","Category":""},
                     color="Total", color_continuous_scale="Reds")
        fig.update_layout(showlegend=False, coloraxis_showscale=False,
                          yaxis={"categoryorder":"total ascending"},
                          margin=dict(l=10,r=10,t=40,b=10),
                          height=max(300, min(20,len(exp_pivot))*36+60))
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

    try:
        import pgeocode as _pgeocode_test
        _pgeocode_ok = True
    except ImportError:
        _pgeocode_ok = False

    if not _pgeocode_ok:
        st.warning(
            "pgeocode not found in Streamlit's Python. Install it with:\n\n"
            "`/Library/Frameworks/Python.framework/Versions/3.13/bin/pip3 install pgeocode`"
        )
    else:
        # Batch geocode all unique zips in one call — fast even for 1000+ rows
        unique_zips = [c["zipcode"] for c in contributions
                       if c["name"] not in ("Unitemized","Unknown") and c.get("zipcode")]
        zip_coords = batch_geocode(unique_zips)

        geo_rows = []
        for c in contributions:
            if c["name"] in ("Unitemized","Unknown") or not c.get("zipcode"):
                continue
            coords = zip_coords.get(str(c["zipcode"]).zfill(5))
            if coords:
                geo_rows.append({**c, "lat": coords[0], "lon": coords[1]})

        # ── By-state table — built from parsed addresses, always shown ──────────
        all_contrib_df = pd.DataFrame(contributions)
        state_df = (all_contrib_df[~all_contrib_df["state"].isin(["","Unknown","Unitemized"])]
                    .groupby("state")["amount"].sum().reset_index()
                    .rename(columns={"state":"State","amount":"Amount"})
                    .sort_values("Amount", ascending=False))

        # ── Map — only shown if geocoding succeeded ────────────────────────────
        if not geo_rows:
            st.info("Map unavailable — zip code geocoding returned no results. "
                    "The state table below is still populated from parsed addresses.")
        else:
            geo_df = pd.DataFrame(geo_rows)
            map_df = (geo_df.groupby(["zipcode","lat","lon","state"])
                      .agg(total=("amount","sum"), count=("amount","count"))
                      .reset_index())
            map_df["hover"] = map_df.apply(
                lambda r: (f"ZIP: {r['zipcode']}<br>State: {r['state']}<br>"
                           f"Total: {fmt_cur(r['total'])}<br>Contributions: {int(r['count'])}"),
                axis=1)
            mx = map_df["total"].max()
            map_df["size"] = map_df["total"].apply(lambda v: 5 + (v/mx)*12)

            fig_map = go.Figure()
            fig_map.add_trace(go.Scattergeo(
                lat=map_df["lat"], lon=map_df["lon"],
                text=map_df["hover"], hoverinfo="text", mode="markers",
                marker=dict(
                    size=map_df["size"], color=map_df["total"],
                    colorscale=[[0,"#c8e6c9"],[0.4,"#66bb6a"],[0.7,"#2e7d32"],[1,"#1b5e20"]],
                    cmin=map_df["total"].min(), cmax=mx,
                    colorbar=dict(title=dict(text="$ Amount",side="right"),
                                  thickness=14, len=0.55, y=0.5),
                    line=dict(width=0.5, color="white"), opacity=0.88,
                ),
            ))
            fig_map.add_trace(go.Scattergeo(
                lat=[c[1] for c in MAJOR_CITIES],
                lon=[c[2] for c in MAJOR_CITIES],
                text=[c[0] for c in MAJOR_CITIES],
                mode="text",
                textfont=dict(size=9, color="#000000"),
                hoverinfo="skip", showlegend=False,
            ))
            fig_map.update_layout(
                geo=dict(
                    scope="usa", projection_type="albers usa",
                    showland=True, landcolor="#f5f5f5",
                    showlakes=True, lakecolor="#d4eaf7",
                    showrivers=True, rivercolor="#d4eaf7",
                    subunitcolor="#cccccc", subunitwidth=0.8,
                    countrycolor="#aaaaaa", bgcolor="white",
                    center=dict(lat=42.0, lon=-93.5),
                    lonaxis=dict(range=[-96.8,-90.1]),
                    lataxis=dict(range=[40.4,43.6]),
                ),
                margin=dict(l=0,r=0,t=10,b=0), height=520,
                paper_bgcolor="white",
            )
            st.plotly_chart(fig_map, use_container_width=True)
            st.caption("Dot size and color reflect total per ZIP. Use the toolbar to zoom to the full US.")

        # Always show by-state table
        st.subheader("Contributions by State")
        if state_df.empty:
            st.info("No state data found — addresses may be missing from this disclosure.")
        else:
            total_mapped = state_df["Amount"].sum()
            # Add contribution count per state
            state_counts = (all_contrib_df[~all_contrib_df["state"].isin(["","Unknown","Unitemized"])]
                            .groupby("state")["amount"].count().reset_index()
                            .rename(columns={"state":"State","amount":"# Contributions"}))
            state_df = state_df.merge(state_counts, on="State", how="left")
            # Filter to states representing >1% of contributions
            state_df = state_df[state_df["Amount"] / receipts * 100 > 1.0]
            state_df["% of Contributions"] = (state_df["Amount"]/receipts*100).apply(fmt_pct)
            state_df["Amount"] = state_df["Amount"].apply(fmt_cur)
            state_df = state_df[["State","# Contributions","Amount","% of Contributions"]]
            st.dataframe(state_df.reset_index(drop=True), use_container_width=True, hide_index=True)
            unmapped = receipts - total_mapped
            if unmapped > 0.01:
                st.caption(f"Note: {fmt_cur(unmapped)} ({unmapped/receipts*100:.1f}%) "
                           f"not mapped — unitemized or missing address.")

except Exception as _geo_err:
    st.error(f"Geographic analysis error: {_geo_err}")


# ── Export PDF ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">📄 Export Report</div>', unsafe_allow_html=True)

if st.button("Generate PDF Report", type="primary"):
    with st.spinner("Building PDF…"):
        try:
            # Grab edited notable donors table from session state
            # Streamlit data_editor stores edits as {"edited_rows":{}, "added_rows":[], "deleted_rows":[]}
            # We rebuild the full table by applying edits to the original notable_init
            try:
                _edits = st.session_state.get("notable_donors", None)
                if _edits is not None and isinstance(_edits, dict) and "edited_rows" in _edits:
                    # Reconstruct from the base notable table
                    _eligible = pivot[(pivot["Total"] < 10_000) &
                                      (~pivot["Contributor"].isin(["Unitemized","Unknown"]))]
                    _notable_base = (pd.concat([_eligible.head(10),
                                                _eligible[_eligible["Total"] >= 1_000]])
                                     .drop_duplicates("Contributor")
                                     .sort_values("Total", ascending=False))
                    notes_df = pd.DataFrame({
                        "Name": _notable_base["Contributor"].astype(str).tolist(),
                        "Contribution": _notable_base["Total"].apply(fmt_cur).tolist(),
                        "Notes": [""] * len(_notable_base),
                    })
                    # Apply edits
                    for row_idx, edits in _edits.get("edited_rows", {}).items():
                        for col, val in edits.items():
                            notes_df.at[int(row_idx), col] = val
                    # Apply added rows
                    for added in _edits.get("added_rows", []):
                        notes_df = pd.concat([notes_df, pd.DataFrame([added])],
                                             ignore_index=True)
                else:
                    notes_df = None
            except Exception:
                notes_df = None
            pdf_bytes = build_pdf_report(
                d=d,
                contributions=contributions,
                exp_df_with_cats=exp_df,
                receipts=receipts,
                expenditures=expenditures,
                debts=debts,
                n_contribs=n_contribs,
                avg_contrib=avg_contrib,
                burn_rate=burn_rate,
                loans=loans,
                notes_df=notes_df,
            )
            safe_name = re.sub(r"[^\w\s-]", "", d["committee_name"]).strip().replace(" ", "_")
            st.download_button(
                label="⬇️ Download PDF",
                data=pdf_bytes,
                file_name=f"{safe_name}_report.pdf",
                mime="application/pdf",
            )
            st.success("PDF ready — click the button above to download.")
        except Exception as e:
            st.error(f"PDF generation failed: {e}")

st.markdown("<br>", unsafe_allow_html=True)
