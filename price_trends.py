# price_trends.py -- Maharashtra-only Mandi Price Trends & Forecasting Engine
"""
Market Price Trend ('Bhav') module strictly for Maharashtra state.
Fetches real data from Agmarknet (data.gov.in) with Maharashtra filter,
falling back to local historical CSV data when offline or missing API key.
Calculates 3-year seasonal trends, month-over-month changes, best selling windows,
and next-month price estimates against Government MSP / FRP.
"""

import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from voice import render_voice_button, build_spoken_text

CSV_FALLBACK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mandi_prices_maharashtra.csv")

# Crop to Agmarknet commodity name mapping
CROP_COMMODITY_MAP = {
    "Cotton": "Cotton",
    "Soybean": "Soyabean",
    "Wheat": "Wheat",
    "Maize": "Maize",
    "Paddy": "Paddy(Dhan)(Common)",
    "Sugarcane": "Sugarcane",
    "Ground Nuts": "Groundnut",
    "Pulses": "Arhar (Tur/Red Gram)",
    "Millets": "Bajra(Pearl Millet/Cumbu)",
    "Barley": "Barley (Jau)",
    "Tobacco": "Tobacco",
    "Tomato": "Tomato",
}

# Maharashtra Government MSP / FRP Rates (₹ per quintal)
MAHARASHTRA_MSP = {
    "Cotton": 7521,        # Cotton (Long Staple) MSP 2024-25
    "Soybean": 4892,       # Soyabean Yellow MSP 2024-25
    "Wheat": 2275,         # Wheat RMS 2024-25
    "Maize": 2225,         # Maize MSP 2024-25
    "Paddy": 2300,         # Paddy (Common) MSP 2024-25
    "Ground Nuts": 6783,   # Groundnut in shell MSP 2024-25
    "Pulses": 7550,        # Tur / Arhar MSP 2024-25
    "Millets": 2625,       # Bajra MSP 2024-25
    "Barley": 1850,        # Barley MSP 2024-25
    "Sugarcane": 340,      # FRP per quintal at 10.25% sugar recovery
    "Tobacco": 5000,       # Indicative reference
    "Tomato": 1800,        # Cost benchmark
}

MAHARASHTRA_DISTRICTS = [
    "All Maharashtra (State Average)",
    "Pune",
    "Nashik",
    "Nagpur",
    "Latur",
    "Solapur",
    "Kolhapur",
    "Jalgaon",
    "Akola",
    "Amravati",
    "Sangli",
    "Yavatmal",
    "Chhatrapati Sambhajinagar",
]

MONTH_NAMES_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_NAMES_MR = ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"]
MONTH_NAMES_HI = ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_agmarknet_maharashtra(commodity: str) -> Optional[pd.DataFrame]:
    """
    Fetch live mandi rates from data.gov.in Agmarknet API.
    Guaranteed filter: filters[state]=Maharashtra
    """
    api_key = os.environ.get("AGMARKNET_API_KEY")
    if not api_key:
        try:
            if hasattr(st, "secrets") and "AGMARKNET_API_KEY" in st.secrets:
                api_key = st.secrets["AGMARKNET_API_KEY"]
        except Exception:
            api_key = None

    if not api_key:
        return None

    # Official data.gov.in Agmarknet endpoint
    url = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
    params = {
        "api-key": api_key,
        "format": "json",
        "limit": "200",
        "filters[state]": "Maharashtra",  # ALWAYS Maharashtra only
        "filters[commodity]": commodity,
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            records = data.get("records", [])
            if records:
                df = pd.DataFrame(records)
                # Strict validation: Drop any row where state != Maharashtra
                if "state" in df.columns:
                    df = df[df["state"].str.lower() == "maharashtra"]
                return df
    except Exception:
        pass
    return None


def load_maharashtra_mandi_data(crop: str, district: Optional[str] = None) -> Tuple[pd.DataFrame, bool]:
    """
    Load mandi data for the crop strictly within Maharashtra.
    Tries Agmarknet first, falls back to local CSV with a 'Sample data' flag.
    """
    commodity = CROP_COMMODITY_MAP.get(crop, crop)
    df_live = fetch_agmarknet_maharashtra(commodity)

    if df_live is not None and not df_live.empty:
        # Normalize live dataframe
        df_live["crop"] = crop
        df_live["state"] = "Maharashtra"
        if "modal_price" in df_live.columns:
            df_live["modal_price"] = pd.to_numeric(df_live["modal_price"], errors="coerce")
        return df_live, False

    # Fallback to local Maharashtra CSV
    if os.path.exists(CSV_FALLBACK_PATH):
        df_local = pd.read_csv(CSV_FALLBACK_PATH)
        # Strict validation: Drop any row where state != Maharashtra
        df_local = df_local[df_local["state"].str.lower() == "maharashtra"]
        # Filter by crop
        df_crop = df_local[df_local["crop"] == crop].copy()
        if district and district != "All Maharashtra (State Average)":
            df_dist = df_crop[df_crop["district"].str.lower() == district.lower()]
            if not df_dist.empty:
                df_crop = df_dist
        return df_crop, True

    return pd.DataFrame(), True


def compute_3year_trends(df: pd.DataFrame, current_month: int) -> Dict[str, Any]:
    """
    Compute monthly average modal price (₹/quintal) for the LAST 3 YEARS,
    month-over-month changes, best/worst month, and next-month estimate.
    """
    if df.empty or "modal_price" not in df.columns:
        return {}

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "modal_price"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month

    # Get the last 3 available years
    available_years = sorted(df["year"].unique())
    if len(available_years) >= 3:
        years = available_years[-3:]
    else:
        years = available_years

    # Group by year and month
    monthly_avg = df.groupby(["year", "month"])["modal_price"].mean().reset_index()

    # Build monthly matrix for chart
    chart_data = []
    for yr in years:
        yr_df = monthly_avg[monthly_avg["year"] == yr]
        month_map = dict(zip(yr_df["month"], yr_df["modal_price"]))
        for m in range(1, 13):
            val = month_map.get(m, np.nan)
            chart_data.append({
                "Year": str(yr),
                "Month": m,
                "MonthName": MONTH_NAMES_EN[m - 1],
                "Price": round(val) if not np.isnan(val) else None
            })

    # This month price in each of the last 3 years
    cur_m_prices = {}
    for yr in years:
        price_row = monthly_avg[(monthly_avg["year"] == yr) & (monthly_avg["month"] == current_month)]
        if not price_row.empty:
            cur_m_prices[yr] = round(float(price_row["modal_price"].values[0]))
        else:
            cur_m_prices[yr] = None

    # Next month % changes: (next_month - cur_month) / cur_month * 100
    next_m = (current_month % 12) + 1
    pct_changes = {}
    for yr in years:
        p_cur = cur_m_prices.get(yr)
        next_row = monthly_avg[(monthly_avg["year"] == yr) & (monthly_avg["month"] == next_m)]
        if p_cur and not next_row.empty:
            p_next = float(next_row["modal_price"].values[0])
            change = ((p_next - p_cur) / p_cur) * 100.0
            pct_changes[yr] = round(change, 1)
        else:
            pct_changes[yr] = None

    valid_changes = [c for c in pct_changes.values() if c is not None]
    avg_next_change = round(float(np.mean(valid_changes)), 1) if valid_changes else 0.0

    # Best and worst months overall
    all_month_avg = df.groupby("month")["modal_price"].mean()
    best_month_num = int(all_month_avg.idxmax()) if not all_month_avg.empty else current_month
    worst_month_num = int(all_month_avg.idxmin()) if not all_month_avg.empty else current_month

    # Latest price and next month estimate
    latest_yr = years[-1] if years else 2025
    latest_price = cur_m_prices.get(latest_yr)
    if latest_price is None:
        valid_prices = [p for p in cur_m_prices.values() if p is not None]
        latest_price = round(float(np.mean(valid_prices))) if valid_prices else 3000

    next_month_estimate = round(latest_price * (1.0 + (avg_next_change / 100.0)))

    # Direction verdict
    if avg_next_change > 2.0:
        verdict = "📈 भाव वाढण्याची शक्यता (Price Rise Expected)"
        verdict_icon = "📈"
        verdict_action = "hold"
    elif avg_next_change < -2.0:
        verdict = "📉 भाव घसरण्याची शक्यता (Price Drop Expected)"
        verdict_icon = "📉"
        verdict_action = "sell"
    else:
        verdict = "➖ भाव स्थिर राहण्याचा अंदाज (Stable Prices Expected)"
        verdict_icon = "➖"
        verdict_action = "stable"

    # Top 3 mandis in Maharashtra with highest recent prices
    top_mandis = []
    if "mandi" in df.columns:
        mandi_avg = df.groupby(["district", "mandi"])["modal_price"].mean().reset_index()
        mandi_avg = mandi_avg.sort_values(by="modal_price", ascending=False).head(3)
        for _, r in mandi_avg.iterrows():
            top_mandis.append({
                "district": r["district"],
                "mandi": r["mandi"],
                "price": round(float(r["modal_price"]))
            })

    return {
        "years": years,
        "chart_data": chart_data,
        "current_month": current_month,
        "next_month": next_m,
        "cur_m_prices": cur_m_prices,
        "pct_changes": pct_changes,
        "avg_next_change": avg_next_change,
        "latest_price": latest_price,
        "next_month_estimate": next_month_estimate,
        "best_month": best_month_num,
        "worst_month": worst_month_num,
        "verdict": verdict,
        "verdict_icon": verdict_icon,
        "verdict_action": verdict_action,
        "top_mandis": top_mandis,
    }


def render_price_trend_page(default_crop: str = "Cotton", lang: str = "English") -> None:
    """
    Render Market Price Trend ('Bhav') page for Maharashtra.
    """
    heading = "💰 बाजार भाव कल (महाराष्ट्र APMC)" if lang == "मराठी" else ("💰 मंडी भाव रुझान (महाराष्ट्र)" if lang == "हिन्दी" else "💰 Market Price Trends (Maharashtra APMC)")
    caption = "महाराष्ट्रातील शेतकरी बांधवांसाठी मागील ३ वर्षांचे भाव, पुढील महिन्याचा अंदाज आणि विकण्याची योग्य वेळ." if lang == "मराठी" else ("महाराष्ट्र के किसानों हेतु पिछले 3 वर्षों के भाव, अगले महीने का अनुमान और बेचने का सही समय।" if lang == "हिन्दी" else "Historical 3-year prices, next-month seasonal estimates, and selling advice for Maharashtra farmers.")

    st.markdown(f"## {heading}")
    st.caption(caption)

    col1, col2 = st.columns(2)
    with col1:
        crop_list = list(CROP_COMMODITY_MAP.keys())
        crop_idx = crop_list.index(default_crop) if default_crop in crop_list else 0
        selected_crop = st.selectbox(
            "पीक निवडा / फसल चुनें / Select Crop",
            options=crop_list,
            index=crop_idx,
            key="bhav_crop_sel"
        )
    with col2:
        selected_dist = st.selectbox(
            "जिल्हा / APMC बाजार समिती (महाराष्ट्र)",
            options=MAHARASHTRA_DISTRICTS,
            index=0,
            key="bhav_dist_sel"
        )

    # Special handling for Sugarcane (sold via factories at FRP)
    if selected_crop == "Sugarcane":
        frp = MAHARASHTRA_MSP.get("Sugarcane", 340)
        sugarcane_note = (
            f"ℹ️ **ऊस (Sugarcane) बाबत महत्त्वाची नोंद:** ऊस खुल्या बाजार समितीत (APMC) लिलावात विकला जात नाही. "
            f"तो साखर कारखान्यांना केंद्र शासनाच्या रास्त व किफायतशीर भावाने (FRP) दिला जातो. "
            f"चालू वर्षाचा केंद्र शासन निर्धारित FRP: **₹{frp} प्रति क्विंटल** (१०.२५% साखर उताऱ्यास). "
            f"कारखान्यांचा अंतिम दर साखरेच्या सरासरी उताऱ्यानुसार ठरतो."
            if lang == "मराठी" else
            (f"ℹ️ **गन्ना (Sugarcane) हेतु सूचना:** गन्ना खुली मंडियों में नहीं बिकता, यह सीधे चीनी मिलों को सरकार द्वारा तय FRP दर पर दिया जाता है। "
             f"वर्तमान सरकारी FRP दर: **₹{frp} प्रति क्विंटल** (10.25% रिकवरी पर)।"
             if lang == "हिन्दी" else
             f"ℹ️ **Sugarcane Market Notice:** Sugarcane is not traded via open APMC auctions. It is procured directly by sugar factories at Government Fair and Remunerative Price (FRP). Current Statutory FRP: **₹{frp} / quintal** at 10.25% sugar recovery.")
        )
        st.info(sugarcane_note)
        render_voice_button(sugarcane_note, lang, key_prefix="sugarcane_note")
        return

    # Load data
    with st.spinner("महाराष्ट्रातील बाजार भाव लोड होत आहेत..." if lang == "मराठी" else "महाराष्ट्र मंडी भाव लोड हो रहे हैं..."):
        df, is_sample = load_maharashtra_mandi_data(selected_crop, selected_dist)

    if is_sample:
        sample_label = "📍 नमुना डेटा वापरला आहे (Sample Maharashtra Data - Actual Agmarknet live sync available with API key)"
        st.caption(f"`{sample_label}`")

    if df.empty:
        st.warning("या पिकासाठी महाराष्ट्रातील भाव माहिती उपलब्ध नाही. कृपया दुसरे पीक निवडा.")
        return

    current_month = datetime.now().month
    trends = compute_3year_trends(df, current_month)

    if not trends or not trends.get("chart_data"):
        st.warning("भाव विश्लेषणासाठी पुरेसा डेटा नाही.")
        return

    cur_m_name = (MONTH_NAMES_MR if lang == "मराठी" else (MONTH_NAMES_HI if lang == "हिन्दी" else MONTH_NAMES_EN))[current_month - 1]
    next_m_name = (MONTH_NAMES_MR if lang == "मराठी" else (MONTH_NAMES_HI if lang == "हिन्दी" else MONTH_NAMES_EN))[(current_month % 12)]

    # 1. Metric Cards: This month price across last 3 years
    st.markdown(f"#### 📅 या {cur_m_name} महिन्यात महाराष्ट्रातील मागील ३ वर्षांचे भाव (₹/क्विंटल)")
    card_cols = st.columns(3)
    years = trends["years"]
    for i, yr in enumerate(years):
        with card_cols[i % 3]:
            p = trends["cur_m_prices"].get(yr)
            st.metric(
                label=f"{yr} ({cur_m_name})",
                value=f"₹{p}" if p else "N/A"
            )

    # 2. Plotly 3-Year Monthly Line Chart
    st.markdown("---")
    st.markdown(f"#### 📈 मागील ३ वर्षांचा मासिक भाव आलेख (Jan - Dec)")

    chart_df = pd.DataFrame(trends["chart_data"])
    chart_df = chart_df.dropna(subset=["Price"])

    fig = px.line(
        chart_df,
        x="MonthName",
        y="Price",
        color="Year",
        markers=True,
        labels={"MonthName": "महिना (Month)", "Price": "सरासरी भाव (₹/क्विंटल)", "Year": "वर्ष (Year)"},
        color_discrete_sequence=["#81c784", "#388e3c", "#1b5e20"],
        template="plotly_white"
    )

    # Add MSP horizontal reference line
    msp_val = MAHARASHTRA_MSP.get(selected_crop)
    if msp_val:
        fig.add_hline(
            y=msp_val,
            line_dash="dash",
            line_color="#d32f2f",
            annotation_text=f"शासकीय हमीभाव (MSP) ₹{msp_val}",
            annotation_position="bottom right"
        )

    fig.update_layout(
        height=360,
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis=dict(tickmode="array", tickvals=MONTH_NAMES_EN),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)

    # 3. Next Month Seasonal % Change Card
    st.markdown("---")
    st.markdown(f"#### 🔮 पुढील महिन्यात ({next_m_name}) भाव किती वाढला/घटला?")
    ch_cols = st.columns(len(years) + 1)
    for i, yr in enumerate(years):
        with ch_cols[i]:
            pct = trends["pct_changes"].get(yr)
            if pct is not None:
                color = "green" if pct >= 0 else "red"
                symbol = "↑" if pct >= 0 else "↓"
                st.markdown(f"**{yr}:** <span style='color:{color}; font-size:1.15rem; font-weight:bold;'>{symbol} {abs(pct)}%</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"**{yr}:** N/A")

    with ch_cols[-1]:
        avg_ch = trends["avg_next_change"]
        color = "#2e7d32" if avg_ch >= 0 else "#c62828"
        symbol = "↑" if avg_ch >= 0 else "↓"
        st.markdown(f"**३ वर्षांची सरासरी:** <span style='color:{color}; font-size:1.25rem; font-weight:bold;'>{symbol} {abs(avg_ch)}%</span>", unsafe_allow_html=True)

    # 4. Actionable Verdict & Next-Month Estimate
    best_m_name = (MONTH_NAMES_MR if lang == "मराठी" else (MONTH_NAMES_HI if lang == "हिन्दी" else MONTH_NAMES_EN))[trends["best_month"] - 1]
    worst_m_name = (MONTH_NAMES_MR if lang == "मराठी" else (MONTH_NAMES_HI if lang == "हिन्दी" else MONTH_NAMES_EN))[trends["worst_month"] - 1]

    st.markdown(f"""
    <div style="background-color:#ffffff; border:2px solid #2e7d32; border-radius:10px; padding:18px; margin:16px 0;">
        <h3 style="color:#1b5e20; margin:0 0 10px 0;">{trends['verdict_icon']} {trends['verdict']}</h3>
        <p style="font-size:1.1rem; margin:6px 0;">
            🎯 <strong>पुढील महिन्याचा अंदाजित भाव ({next_m_name}):</strong> 
            <span style="font-size:1.4rem; font-weight:bold; color:#2e7d32;">₹{trends['next_month_estimate']}</span> प्रति क्विंटल
        </p>
        <p style="color:#666666; font-size:0.9rem; margin:4px 0;">
            ⚠️ <em>सूचना: हा ३ वर्षांच्या हंगामावर आधारित अंदाज आहे, पक्का दर नाही. बाजारातील आवक व आंतरराष्ट्रीय स्थितीनुसार भाव बदलू शकतात.</em>
        </p>
        <hr style="margin:12px 0;">
        <p style="margin:6px 0;">
            🏆 <strong>महाराष्ट्रात विकण्यासाठी सर्वोत्तम महिना:</strong> <span style="font-weight:bold; color:#1b5e20;">{best_m_name}</span> (सरासरी उच्चांकी भाव)<br>
            📉 <strong>आवक जास्त असणारा महिना (कमी भाव):</strong> <span style="font-weight:bold; color:#c62828;">{worst_m_name}</span> (हंगामातील आवक दाब)
        </p>
    </div>
    """, unsafe_allow_html=True)

    # 5. Top 3 Mandis with Highest Rates
    if trends["top_mandis"]:
        st.markdown(f"#### 🏛️ महाराष्ट्रातील सर्वाधिक भाव देणाऱ्या प्रमुख बाजार समित्या ({selected_crop})")
        m_cols = st.columns(len(trends["top_mandis"]))
        for i, m_info in enumerate(trends["top_mandis"]):
            with m_cols[i]:
                st.markdown(f"""
                <div style="background:#f1f8e9; border:1px solid #c5e1a5; border-radius:8px; padding:12px; text-align:center;">
                    <div style="font-weight:bold; color:#33691e;">{m_info['mandi']}</div>
                    <div style="color:#558b2f; font-size:0.85rem;">जिल्हा: {m_info['district']}</div>
                    <div style="font-size:1.3rem; font-weight:bold; color:#1b5e20; margin-top:4px;">₹{m_info['price']} /q</div>
                </div>
                """, unsafe_allow_html=True)

    # 6. Spoken Text & Audio Play Button
    spoken_summary = (
        f"महाराष्ट्रातील {selected_crop} पिकाचा बाजार भाव अहवाल. "
        f"सध्या {cur_m_name} महिन्यात सरासरी भाव {trends['latest_price']} रुपये प्रति क्विंटल आहे. "
        f"पुढील महिन्यात {next_m_name} मध्ये भाव {abs(trends['avg_next_change'])} टक्के {'वाढण्याची' if trends['avg_next_change'] >= 0 else 'घटण्याची'} शक्यता आहे. "
        f"अंदाजित भाव {trends['next_month_estimate']} रुपये प्रति क्विंटल राहू शकतो. "
        f"महाराष्ट्रात माल विकण्यासाठी सर्वोत्तम महिना {best_m_name} मानला जातो. "
        f"सरकारी हमीभाव {msp_val} रुपये प्रति क्विंटल आहे."
        if lang == "मराठी" else
        (f"महाराष्ट्र में {selected_crop} फसल का मंडी भाव रुझान. "
         f"वर्तमान {cur_m_name} माह में औसत भाव {trends['latest_price']} रुपये प्रति क्विंटल है. "
         f"अगले महीने {next_m_name} में भाव {abs(trends['avg_next_change'])} प्रतिशत {'बढ़ने' if trends['avg_next_change'] >= 0 else 'घटने'} का अनुमान है. "
         f"अंदाजित भाव {trends['next_month_estimate']} रुपये प्रति क्विंटल हो सकता है. "
         f"फसल बेचने का सर्वोत्तम महीना {best_m_name} है. "
         f"सरकारी न्यूनतम समर्थन मूल्य {msp_val} रुपये प्रति क्विंटल है."
         if lang == "हिन्दी" else
         f"Market price report for {selected_crop} in Maharashtra. "
         f"Current average price in {cur_m_name} is {trends['latest_price']} rupees per quintal. "
         f"Next month estimate is {trends['next_month_estimate']} rupees per quintal with a {abs(trends['avg_next_change'])} percent seasonal change. "
         f"Historically, the best month to sell in Maharashtra is {best_m_name}. Government MSP is {msp_val} rupees per quintal.")
    )

    st.markdown("---")
    render_voice_button(spoken_summary, lang, key_prefix="bhav_audio")
