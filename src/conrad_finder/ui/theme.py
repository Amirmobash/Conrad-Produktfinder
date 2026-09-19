BRAND_ORANGE = "#F57C00"
BRAND_ORANGE_DARK = "#E66F00"
SOFT_ORANGE = "#FFF3E6"
TEXT = "#202124"
MUTED = "#6B7280"
BORDER = "#E5E7EB"

CSS = f"""
<style>
    .stApp {{
        background: #FFFFFF;
        color: {TEXT};
    }}

    [data-testid="stSidebar"] {{
        background: #FFF9F2;
        border-right: 1px solid {BORDER};
    }}

    .block-container {{
        max-width: 1480px;
        padding-top: 1.3rem;
        padding-bottom: 3rem;
    }}

    .hero {{
        padding: 1.35rem 1.5rem;
        border: 1px solid {BORDER};
        border-left: 6px solid {BRAND_ORANGE};
        border-radius: 16px;
        background: linear-gradient(90deg, #FFF8F0 0%, #FFFFFF 72%);
        margin-bottom: 1rem;
    }}

    .hero h1 {{
        margin: 0;
        font-size: 2rem;
        color: {TEXT};
    }}

    .hero p {{
        margin: .4rem 0 0 0;
        color: {MUTED};
    }}

    .metric-card {{
        border: 1px solid {BORDER};
        border-radius: 14px;
        padding: 1rem;
        background: #FFFFFF;
        min-height: 105px;
    }}

    .metric-label {{
        color: {MUTED};
        font-size: .85rem;
        margin-bottom: .25rem;
    }}

    .metric-value {{
        color: {TEXT};
        font-size: 1.35rem;
        font-weight: 700;
    }}

    .product-card {{
        border: 1px solid {BORDER};
        border-radius: 14px;
        padding: 1rem 1.05rem;
        background: #FFFFFF;
        margin: .45rem 0;
    }}

    .product-card strong {{
        color: {TEXT};
    }}

    .badge {{
        display: inline-block;
        background: {SOFT_ORANGE};
        color: {BRAND_ORANGE_DARK};
        border-radius: 999px;
        padding: .16rem .55rem;
        font-size: .78rem;
        font-weight: 650;
    }}

    .footer {{
        color: {MUTED};
        font-size: .82rem;
        text-align: center;
        border-top: 1px solid {BORDER};
        padding-top: 1rem;
        margin-top: 2rem;
    }}

    div.stButton > button[kind="primary"] {{
        background: {BRAND_ORANGE};
        border-color: {BRAND_ORANGE};
    }}

    div.stButton > button[kind="primary"]:hover {{
        background: {BRAND_ORANGE_DARK};
        border-color: {BRAND_ORANGE_DARK};
    }}
</style>
"""
