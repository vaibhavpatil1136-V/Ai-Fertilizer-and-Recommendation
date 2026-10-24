# app.py -- AgriCare AI Crop Doctor & Fertilizer Advisor
"""
Farmer-first, mobile-optimized AgriCare platform tailored for Maharashtra farmers.
Features:
  - Immediate home dashboard without login barrier
  - 3-step crop & symptom wizard (Fasal Chuna) with required active ingredients
  - Voice readout (Text-to-Speech) in Marathi, Hindi, and English
  - Maharashtra-only APMC mandi price trends (Bhav) with 3-year history & forecast
  - Leaf photo diagnosis, soil fertilizer advisor, product compare, and reports
"""

import os
import io
import json
import hashlib
from datetime import datetime
from PIL import Image
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from translations import TRANSLATIONS, ADVISORY_DATA
from products import PRODUCTS
from fertilizer_engine import npk_level
from model_helper import (
    predict_fertilizer,
    predict_leaf,
    preprocess_leaf,
    get_fertilizer_model_payload,
    get_metrics_payload,
    CROP_TO_SOIL_MAP,
    COTTON,
    TOMATO,
    SOYBEAN,
    WHEAT,
    MAIZE,
    PADDY,
)
from report_generator import generate_pdf_report, generate_csv_report
from ui_components import apply_custom_css, render_top_bar, render_back_button
from problem_solutions import SUPPORTED_CROPS, PROBLEM_OPTIONS, get_crop_solution
from price_trends import render_price_trend_page
from voice import render_voice_button, build_spoken_text

# 1. Page Configuration: Collapsed sidebar by default
st.set_page_config(
    page_title="AgriCare - AI Crop Doctor",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. Inject mobile-first styling & hide sidebar
apply_custom_css()

# 3. Session State Initialization
if "page" not in st.session_state:
    st.session_state["page"] = "home"
if "lang" not in st.session_state:
    st.session_state["lang"] = "मराठी"
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "history" not in st.session_state:
    st.session_state["history"] = []
if "logged_hashes" not in st.session_state:
    st.session_state["logged_hashes"] = set()
if "last_report_data" not in st.session_state:
    st.session_state["last_report_data"] = None
if "last_wizard_result" not in st.session_state:
    st.session_state["last_wizard_result"] = None
if "prefilled_soil_crop" not in st.session_state:
    st.session_state["prefilled_soil_crop"] = None

# Wizard States
if "wizard_step" not in st.session_state:
    st.session_state["wizard_step"] = 1
if "wizard_crop" not in st.session_state:
    st.session_state["wizard_crop"] = "Cotton"
if "wizard_problem" not in st.session_state:
    st.session_state["wizard_problem"] = None

lang = st.session_state["lang"]
t = TRANSLATIONS[lang]

# 4. Top Bar Header on every screen
render_top_bar()


# ==============================================================================
# ROUTE 1: HOME PAGE (No login wall, 2-column mobile cards)
# ==============================================================================
def render_home_page():
    # Show last result if logged in and exists
    if st.session_state.get("logged_in") and st.session_state.get("last_wizard_result"):
        last = st.session_state["last_wizard_result"]
        st.markdown(f"""
        <div style="background-color:#e8f5e9; border:1.5px solid #81c784; border-radius:12px; padding:14px 18px; margin-bottom:16px;">
            <div style="font-size:0.9rem; font-weight:700; color:#2e7d32;">{t['last_result_title']}</div>
            <div style="font-size:1.15rem; font-weight:bold; color:#1b5e20;">🌱 {last.get('crop')} - {last.get('problem')}</div>
            <div style="font-size:0.95rem; color:#333; margin-top:4px;">🧪 <strong>उपाय:</strong> {last.get('fertilizer')}</div>
        </div>
        """, unsafe_allow_html=True)

    # Hero headline
    st.markdown(f"<h2 style='text-align:center; color:#1b5e20; margin-top:4px; margin-bottom:20px;'>{t['hero_prompt']}</h2>", unsafe_allow_html=True)

    # Big 6 Action Cards in 2 Columns
    c1, c2 = st.columns(2)

    with c1:
        if st.button(t['nav_fasal_chuna'], key="card_btn_fasal", use_container_width=True):
            st.session_state["page"] = "fasal_chuna"
            st.session_state["wizard_step"] = 1
            st.rerun()

        if st.button(t['nav_bhav'], key="card_btn_bhav", use_container_width=True):
            st.session_state["page"] = "bhav"
            st.rerun()

        if st.button(t['nav_product_compare'], key="card_btn_compare", use_container_width=True):
            st.session_state["page"] = "compare"
            st.rerun()

    with c2:
        if st.button(t['nav_patta_photo'], key="card_btn_photo", use_container_width=True):
            st.session_state["page"] = "patta_photo"
            st.rerun()

        if st.button(t['nav_khat_salah'], key="card_btn_soil", use_container_width=True):
            st.session_state["page"] = "khat_salah"
            st.rerun()

        if st.button(t['nav_download_report'], key="card_btn_report", use_container_width=True):
            st.session_state["page"] = "report"
            st.rerun()

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    # Secondary Analytics / About Button
    if st.button(t['nav_about_model'], key="card_btn_about", use_container_width=True):
        st.session_state["page"] = "about"
        st.rerun()


# ==============================================================================
# ROUTE 2: FARMER WIZARD ("Fasal Chuna" - 3 Easy Steps)
# ==============================================================================
def render_fasal_chuna_wizard():
    render_back_button("home")

    step = st.session_state.get("wizard_step", 1)

    # -----------------------------
    # STEP 1: Choose Crop
    # -----------------------------
    if step == 1:
        st.markdown(f"### {t['step1_crop_title']}")
        st.caption(t['step1_crop_sub'])

        crop_cols = st.columns(2)
        for i, c_info in enumerate(SUPPORTED_CROPS):
            col_target = crop_cols[i % 2]
            crop_label = c_info["mr"] if lang == "मराठी" else (c_info["hi"] if lang == "हिन्दी" else c_info["en"])
            btn_text = f"{c_info['icon']} {crop_label}"

            with col_target:
                if st.button(btn_text, key=f"wizard_crop_{c_info['id']}", use_container_width=True):
                    st.session_state["wizard_crop"] = c_info["id"]
                    st.session_state["wizard_step"] = 2
                    st.rerun()

    # -----------------------------
    # STEP 2: Choose Problem
    # -----------------------------
    elif step == 2:
        sel_crop = st.session_state.get("wizard_crop", "Cotton")
        c_meta = next((c for c in SUPPORTED_CROPS if c["id"] == sel_crop), SUPPORTED_CROPS[0])
        c_name = c_meta["mr"] if lang == "मराठी" else (c_meta["hi"] if lang == "हिन्दी" else c_meta["en"])

        st.markdown(f"### {t['step2_problem_title'].format(crop=c_name)}")
        st.caption(t['step2_problem_sub'])

        prob_cols = st.columns(2)
        for i, p_info in enumerate(PROBLEM_OPTIONS):
            col_target = prob_cols[i % 2]
            prob_title = p_info["mr"] if lang == "मराठी" else (p_info["hi"] if lang == "हिन्दी" else p_info["en"])
            prob_desc = p_info["desc_mr"] if lang == "मराठी" else (p_info["desc_hi"] if lang == "हिन्दी" else p_info["desc_en"])
            btn_text = f"{p_info['icon']} {prob_title}\n\n({prob_desc})"

            with col_target:
                if st.button(btn_text, key=f"wizard_prob_{p_info['id']}", use_container_width=True):
                    st.session_state["wizard_problem"] = p_info["id"]
                    st.session_state["wizard_step"] = 3
                    st.rerun()

        st.markdown("---")
        # Option to jump to photo diagnosis if unsure
        if st.button(t['cant_find_photo_btn'], key="btn_wizard_to_photo", use_container_width=True):
            st.session_state["page"] = "patta_photo"
            st.rerun()

        if st.button("← दुसरे पीक निवडा (Change Crop)", key="btn_wizard_back_step1"):
            st.session_state["wizard_step"] = 1
            st.rerun()

    # -----------------------------
    # STEP 3: Actionable Result
    # -----------------------------
    elif step == 3:
        sel_crop = st.session_state.get("wizard_crop", "Cotton")
        sel_prob = st.session_state.get("wizard_problem", "yellowing")
        c_meta = next((c for c in SUPPORTED_CROPS if c["id"] == sel_crop), SUPPORTED_CROPS[0])
        c_name = c_meta["mr"] if lang == "मराठी" else (c_meta["hi"] if lang == "हिन्दी" else c_meta["en"])

        # Fetch crop-specific solution (guaranteed crop-restricted)
        solution = get_crop_solution(sel_crop, sel_prob, lang=lang)

        st.markdown(f"### {t['step3_result_title'].format(crop=c_name)}")

        # Result card with prominent sections
        st.markdown(f"""
        <div class="farmer-card">
            <h3>🌱 {c_name} - {solution.get('cause')}</h3>
            <p style="font-size:1.15rem; margin:10px 0;"><strong>{t['kya_karna_hai']}</strong></p>
            <ol style="margin: 6px 0 16px 20px; line-height: 1.6;">
                {"".join(f"<li>{step_txt}</li>" for step_txt in solution.get('action_steps', []))}
            </ol>
            <hr style="border:none; border-top:1.5px solid #c8e6c9; margin:14px 0;">
            <p style="font-size:1.15rem; margin:8px 0;">
                <strong>{t['konsa_khat_dawa']}</strong><br>
                <span style="font-size:1.3rem; font-weight:bold; color:#1b5e20;">🧪 {solution.get('fertilizer')}</span>
            </p>
            <div style="background-color:#f1f8e9; border:1.5px dashed #2e7d32; border-radius:10px; padding:14px; margin:12px 0;">
                <div style="font-weight:bold; color:#1b5e20;">{t['ingredients_check_tip']}</div>
                <div style="font-size:1.2rem; font-weight:700; color:#2e7d32; margin-top:4px;">🔍 {solution.get('required_ingredients')}</div>
            </div>
            <p style="margin:8px 0;"><strong>{t['dosage_label']}</strong> <code>{solution.get('dosage')}</code></p>
            <p style="margin:8px 0; color:#5d4037;"><strong>{t['savdhani_label']}</strong> {solution.get('precautions')}</p>
        </div>
        """, unsafe_allow_html=True)

        # Voice Button (Reads whole result aloud)
        result_data = {
            "crop": c_name,
            "problem": solution.get("cause"),
            "solution_steps": solution.get("action_steps"),
            "fertilizer": solution.get("fertilizer"),
            "required_ingredients": solution.get("required_ingredients"),
            "dosage": solution.get("dosage"),
            "precautions": solution.get("precautions"),
        }
        spoken_script = build_spoken_text(result_data, lang)
        render_voice_button(spoken_script, lang, key_prefix="wizard_voice")

        # Save to session state
        st.session_state["last_wizard_result"] = {
            "crop": c_name,
            "problem": solution.get("cause"),
            "fertilizer": solution.get("fertilizer"),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Save to history if logged in
        if st.session_state.get("logged_in"):
            entry_hash = hashlib.sha256(f"wizard_{sel_crop}_{sel_prob}".encode()).hexdigest()
            if entry_hash not in st.session_state.logged_hashes:
                st.session_state.logged_hashes.add(entry_hash)
                st.session_state.history.append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "Fasal Chuna Advice",
                    "crop": c_name,
                    "result": solution.get("fertilizer"),
                    "confidence": "Agronomic Protocol",
                    "details": solution.get("cause"),
                    "url": "",
                })

        st.markdown("<hr style='margin:20px 0;'>", unsafe_allow_html=True)
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            if st.button(f"💰 {c_name} चे महाराष्ट्र बाजार भाव पहा (Check Prices)", key="btn_goto_bhav", use_container_width=True):
                st.session_state["page"] = "bhav"
                st.rerun()
        with col_act2:
            if st.button("🔄 नवीन तपासणी करा (Start Again)", key="btn_wizard_restart", use_container_width=True):
                st.session_state["wizard_step"] = 1
                st.rerun()


# ==============================================================================
# ROUTE 3: LEAF PHOTO DIAGNOSIS ("Patta Photo")
# ==============================================================================
def render_patta_photo_page():
    render_back_button("home")

    st.markdown(f"## {t['leaf_title']}")
    st.caption(t['leaf_desc'])

    crop_options = list(ADVISORY_DATA.keys())
    selected_crop = st.selectbox(t['select_leaf_crop'], options=crop_options, index=0)

    tab_cam, tab_up = st.tabs([f"📸 {t['tab_camera']}", f"📁 {t['tab_upload']}"])

    img = None
    img_bytes = None

    with tab_cam:
        captured_file = st.camera_input(t['camera_prompt'], key="leaf_cam_input")
        if captured_file is not None:
            img_bytes = captured_file.getvalue()
            img = Image.open(io.BytesIO(img_bytes))

    with tab_up:
        uploaded_file = st.file_uploader(t['upload_prompt'], type=["jpg", "jpeg", "png"], key="leaf_up_input")
        if uploaded_file is not None:
            img_bytes = uploaded_file.getvalue()
            img = Image.open(io.BytesIO(img_bytes))

    if img is not None and img_bytes is not None:
        img_hash = hashlib.sha256(img_bytes).hexdigest()

        col_i1, col_i2 = st.columns([1, 1.2])
        with col_i1:
            st.image(img, caption="पानाचा फोटो (Input)", use_container_width=True)
            _, norm_arr = preprocess_leaf(img)
            st.image(norm_arr, caption=t['prep_preview'], use_container_width=True)

        with col_i2:
            with st.spinner(t['analyzing']):
                diag = predict_leaf(img, crop=selected_crop)

            status = diag.get("status", "ok")
            detected_label = diag.get("label", "Analyzed Leaf")
            confidence = diag.get("confidence")
            engine_name = diag.get("engine", "")
            crop_res = diag.get("crop", selected_crop)
            symptom_key = diag.get("symptom_key")

            # 1. UNCERTAIN (non-leaf or white photo)
            if status == "uncertain":
                st.warning(t['uncertain_warning'])
                render_voice_button(t['uncertain_warning'], lang, key_prefix="leaf_uncertain_audio")
                return

            # 2. HEALTHY
            if status == "healthy":
                st.success(t['healthy_note'])

            # 3. Advisory Card
            advisory_dict = ADVISORY_DATA.get(crop_res, {}).get(symptom_key, {}).get(lang)
            if not advisory_dict:
                crop_dict = ADVISORY_DATA.get(crop_res, {})
                first_sym = list(crop_dict.keys())[0] if crop_dict else None
                advisory_dict = crop_dict.get(first_sym, {}).get(lang, {})

            conf_str = f"{confidence}%" if confidence is not None else t['engine_rule']

            st.markdown(f"""
            <div class="farmer-card">
                <h3>{t['result_heading']}</h3>
                <p><strong>{t['detected_class']}:</strong> <code>{detected_label}</code></p>
                <p><strong>{t['engine_label']}:</strong> {engine_name} | <strong>{t['conf_label']}:</strong> <span class="metric-badge">{conf_str}</span></p>
                <p><strong>{t['status_label']}</strong> {advisory_dict.get('condition', detected_label)}</p>
                <p><strong>{t['cause_label']}</strong> {advisory_dict.get('cause', 'N/A')}</p>
                <hr style="border:none; border-top:1.5px solid #c8e6c9;">
                <p><strong>{t['fertilizer_label']}</strong><br>{advisory_dict.get('solution', 'N/A')}</p>
                <p><strong>{t['market_label']}</strong><br>🛒 <code>{advisory_dict.get('market_brands', 'N/A')}</code></p>
                <p><strong>{t['active_ingredients']}</strong><br>🔬 <code>{advisory_dict.get('ingredients', 'N/A')}</code></p>
                <p><strong>{t['tips_label']}</strong><br>💡 {advisory_dict.get('tips', 'N/A')}</p>
            </div>
            """, unsafe_allow_html=True)

            # Voice Button
            voice_script = build_spoken_text({
                "crop": crop_res,
                "problem": advisory_dict.get("condition", detected_label),
                "solution": advisory_dict.get("solution"),
                "fertilizer": advisory_dict.get("market_brands"),
                "required_ingredients": advisory_dict.get("ingredients"),
                "precautions": advisory_dict.get("tips"),
            }, lang)
            render_voice_button(voice_script, lang, key_prefix="leaf_diag_voice")

            # Deduplicated history log if logged in
            if st.session_state.get("logged_in") and img_hash not in st.session_state.logged_hashes:
                st.session_state.logged_hashes.add(img_hash)
                st.session_state.history.append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "Patta Photo",
                    "crop": crop_res,
                    "result": advisory_dict.get("condition", detected_label),
                    "confidence": conf_str,
                    "details": detected_label,
                    "url": "",
                })

            # Save for report
            st.session_state.last_report_data = {
                "type": "Leaf Photo Diagnosis",
                "crop": crop_res,
                "result": advisory_dict.get("condition", detected_label),
                "confidence": conf_str,
                "advisory": advisory_dict,
                "user": st.session_state.username,
            }

            # Jump to Soil Advisor
            mapped_soil = CROP_TO_SOIL_MAP.get(crop_res)
            if mapped_soil:
                if st.button(t['goto_soil_plan'], key="btn_jump_to_soil"):
                    st.session_state.prefilled_soil_crop = mapped_soil
                    st.session_state["page"] = "khat_salah"
                    st.rerun()


# ==============================================================================
# ROUTE 4: MARKET PRICE TRENDS ("Bhav" - Maharashtra)
# ==============================================================================
def render_bhav_page():
    render_back_button("home")
    def_crop = st.session_state.get("wizard_crop", "Cotton")
    render_price_trend_page(default_crop=def_crop, lang=lang)


# ==============================================================================
# ROUTE 5: SOIL & FERTILIZER ADVISOR ("Khat Salah")
# ==============================================================================
def render_khat_salah_page():
    render_back_button("home")

    st.markdown(f"## {t['fa_title']}")
    st.caption(t['fa_desc'])

    fert_payload = get_fertilizer_model_payload()
    ref_stats = fert_payload.get("reference_stats", {})
    crop_list = fert_payload.get("crop_types", ["Cotton", "Sugarcane", "Wheat", "Maize", "Paddy", "Oil seeds"])
    soil_list = fert_payload.get("soil_types", ["Clayey", "Loamy", "Sandy", "Black", "Red"])

    default_crop_idx = 0
    if st.session_state.get("prefilled_soil_crop") in crop_list:
        default_crop_idx = crop_list.index(st.session_state.prefilled_soil_crop)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"#### 🌦️ {t['input_env']}")
        crop_sel = st.selectbox(t['crop_type'], options=crop_list, index=default_crop_idx)
        soil_sel = st.selectbox(t['soil_type'], options=soil_list)

        temp_val = st.slider(t['temperature'], min_value=25.0, max_value=38.0, value=30.0, step=1.0)
        hum_val = st.slider(t['humidity'], min_value=50.0, max_value=72.0, value=60.0, step=1.0)
        moist_val = st.slider(t['moisture'], min_value=25.0, max_value=65.0, value=42.0, step=1.0)

    with c2:
        st.markdown(f"#### 🧪 {t['input_nutrients']}")
        n_val = st.slider(t['nitrogen'], min_value=4.0, max_value=42.0, value=20.0, step=1.0)
        p_val = st.slider(t['phosphorous'], min_value=0.0, max_value=42.0, value=18.0, step=1.0)
        k_val = st.slider(t['potassium'], min_value=0.0, max_value=19.0, value=0.0, step=1.0)

    st.markdown("---")
    if st.button(t['get_fert_btn'], key="btn_calc_khat", use_container_width=True):
        inputs = {
            "Temperature": temp_val,
            "Humidity": hum_val,
            "Moisture": moist_val,
            "Soil Type": soil_sel,
            "Crop Type": crop_sel,
            "Nitrogen": n_val,
            "Phosphorous": p_val,
            "Potassium": k_val,
        }

        with st.spinner("हिशोब सुरू आहे..."):
            result = predict_fertilizer(inputs)

        best_fert = result["best_fertilizer"]
        top_3 = result["top_3"]
        nutrients = result["nutrient_status"]
        product = PRODUCTS.get(best_fert, {})
        prod_lang = product.get(lang, product.get("English", {}))

        # Result Banner
        st.markdown(f"""
        <div class="farmer-card">
            <h3>{t['rec_fert_heading']}: <span style="color:#2e7d32;">{best_fert}</span></h3>
            <p><strong>{t['confidence_col']}:</strong> <span class="metric-badge">{result['confidence']}%</span></p>
        </div>
        """, unsafe_allow_html=True)

        # NPK status badges
        st.markdown(f"#### 🧪 {t['soil_npk_heading']}")
        c_n, c_p, c_k = st.columns(3)
        def badge(st_val):
            if st_val == "Low":
                return f"<span style='color:#c62828; font-weight:bold;'>{t['level_low']} (कमी)</span>"
            elif st_val == "Medium":
                return f"<span style='color:#f57f17; font-weight:bold;'>{t['level_medium']} (मध्यम)</span>"
            return f"<span style='color:#2e7d32; font-weight:bold;'>{t['level_high']} (भरपूर)</span>"

        with c_n:
            st.markdown(f"**Nitrogen (N):** {n_val} &nbsp; {badge(nutrients['Nitrogen']['status'])}", unsafe_allow_html=True)
        with c_p:
            st.markdown(f"**Phosphorous (P):** {p_val} &nbsp; {badge(nutrients['Phosphorous']['status'])}", unsafe_allow_html=True)
        with c_k:
            st.markdown(f"**Potassium (K):** {k_val} &nbsp; {badge(nutrients['Potassium']['status'])}", unsafe_allow_html=True)

        for gap in result.get("gap_warnings", []):
            st.warning(t['npk_gap_warning'].format(nutrient=gap, fert=best_fert))

        # Product details card
        st.markdown(f"""
        <div style="background:#ffffff; border:1.5px solid #a5d6a7; border-radius:12px; padding:18px; margin:16px 0;">
            <h4 style="color:#1b5e20; margin-top:0;">{prod_lang.get('title', best_fert)} (NPK {product.get('npk_ratio', '')})</h4>
            <p><strong>{t['composition_label']}:</strong> {prod_lang.get('composition', '')}</p>
            <p><strong>{t['ingredients_label']}:</strong> {prod_lang.get('ingredients', '')}</p>
            <p><strong>{t['brands_label']}:</strong> <code>{prod_lang.get('brands', product.get('brands', ''))}</code></p>
            <p><strong>{t['app_note_label']}:</strong> {prod_lang.get('application_note', '')}</p>
        </div>
        """, unsafe_allow_html=True)

        # Voice audio button
        spoken_script = (
            f"माती परीक्षणानुसार तुमच्या {crop_sel} पिकासाठी {best_fert} खताची शिफारस करण्यात आली आहे. "
            f"या खताचे प्रमाण एनपीके {product.get('npk_ratio', '')} आहे. "
            f"बाजारातून खरेदी करताना पाकिटावर घटक तपासा. "
            f"स्थानिक कृषी सल्लागाराच्या सल्ल्याने योग्य हप्त्यात खत द्या."
            if lang == "मराठी" else
            (f"मिट्टी परीक्षण के अनुसार आपकी {crop_sel} फसल के लिए {best_fert} उर्वरक की सिफारिश की गई है। "
             f"इसका एनपीके अनुपात {product.get('npk_ratio', '')} है।"
             if lang == "हिन्दी" else
             f"Soil-based fertilizer advisory for {crop_sel}. Recommended fertilizer is {best_fert} with NPK ratio {product.get('npk_ratio', '')}.")
        )
        render_voice_button(spoken_script, lang, key_prefix="soil_fert_voice")

        # Save for report
        st.session_state.last_report_data = {
            "type": "Soil & Fertilizer Advisory",
            "crop": crop_sel,
            "result": best_fert,
            "confidence": f"{result['confidence']}%",
            "soil_inputs": inputs,
            "nutrient_status": nutrients,
            "product_info": product,
            "user": st.session_state.username,
        }


# ==============================================================================
# ROUTE 6: PRODUCT COMPARE
# ==============================================================================
def render_compare_page():
    render_back_button("home")
    st.markdown(f"## {t['compare_title']}")
    st.caption(t['compare_desc'])

    all_ferts = list(PRODUCTS.keys())
    selected_ferts = st.multiselect(
        t['select_compare_ferts'],
        options=all_ferts,
        default=["Urea", "DAP", "10-26-26"]
    )

    if len(selected_ferts) < 2:
        st.warning("कृपया तुलनेसाठी किमान २ खते निवडा.")
        return

    # Chart
    npk_chart_data = []
    for f_name in selected_ferts:
        prod = PRODUCTS.get(f_name, {})
        npk_chart_data.append({"Fertilizer": f_name, "Nutrient": "Nitrogen (N)", "Percentage": prod.get("n", 0.0)})
        npk_chart_data.append({"Fertilizer": f_name, "Nutrient": "Phosphorous (P)", "Percentage": prod.get("p", 0.0)})
        npk_chart_data.append({"Fertilizer": f_name, "Nutrient": "Potassium (K)", "Percentage": prod.get("k", 0.0)})

    fig_npk = px.bar(
        pd.DataFrame(npk_chart_data),
        x="Fertilizer", y="Percentage", color="Nutrient", barmode="group",
        color_discrete_map={"Nitrogen (N)": "#2e7d32", "Phosphorous (P)": "#e65100", "Potassium (K)": "#1565c0"},
        template="plotly_white"
    )
    fig_npk.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=320)
    st.plotly_chart(fig_npk, use_container_width=True)

    # Table
    rows = []
    for f_name in selected_ferts:
        p = PRODUCTS.get(f_name, {})
        pl = p.get(lang, p.get("English", {}))
        rows.append({
            "खत (Fertilizer)": f_name,
            "NPK Ratio": p.get("npk_ratio", ""),
            "घटक (Active Ingredients)": pl.get("ingredients", ""),
            "उपयुक्तता (Best For)": pl.get("best_for", ""),
            "प्रसिद्ध ब्रँड्स": p.get("brands", ""),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)


# ==============================================================================
# ROUTE 7: REPORT DOWNLOAD (Login gated)
# ==============================================================================
def render_report_page():
    render_back_button("home")
    st.markdown(f"## {t['report_title']}")
    st.caption(t['report_desc'])

    if not st.session_state.get("logged_in"):
        st.info(f"🔒 {t['require_login_alert']}")
        return

    if st.session_state.last_report_data is None and not st.session_state.history:
        st.info(t['no_report_data'])
        return

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 📥 PDF अहवाल")
        if st.session_state.last_report_data is not None:
            pdf_bytes = generate_pdf_report(st.session_state.last_report_data, lang=lang)
            st.download_button(
                label=t['download_pdf'],
                data=pdf_bytes,
                file_name=f"AgriCare_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf",
                key="btn_dl_pdf_user"
            )
        else:
            st.info("आधी पीक सल्ला किंवा खत सल्ला तपासा.")

    with col2:
        st.markdown("#### 📥 CSV सारांश")
        if st.session_state.history:
            csv_str = generate_csv_report(st.session_state.history)
            st.download_button(
                label=t['download_csv'],
                data=csv_str.encode("utf-8-sig"),
                file_name=f"AgriCare_Session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                key="btn_dl_csv_user"
            )

    if st.session_state.history:
        st.markdown("---")
        st.subheader("🕒 तपासणी इतिहास")
        st.dataframe(pd.DataFrame(st.session_state.history), use_container_width=True)
        if st.button("🗑️ इतिहास पुसा (Clear History)", key="btn_clear_history_user"):
            st.session_state.history = []
            st.session_state.logged_hashes = set()
            st.session_state.last_report_data = None
            st.rerun()


# ==============================================================================
# ROUTE 8: ABOUT & MODEL INFO / ANALYTICS
# ==============================================================================
def render_about_page():
    render_back_button("home")
    st.markdown(f"## {t['about_title']}")
    st.caption(t['about_desc'])

    metrics = get_metrics_payload()

    st.warning(t['data_notice'])

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🧪 खत शिफारस मॉडेल (Fertilizer Model)")
        st.write(f"**सक्रिय मॉडेल:** `{metrics.get('best_model', 'XGBoost')}`")
        st.write(f"**प्रशिक्षण नोंदी:** `{metrics.get('n_samples', 99)}`")
        st.write(f"**५-पटीय CV अचूकता:** `{metrics.get('cv_scores', {}).get(metrics.get('best_model', 'XGBoost'), {}).get('accuracy_mean', 0.99) * 100:.1f}%`")
    with col2:
        st.markdown("#### 🍃 पानांच्या रोगाचे मॉडेल (Leaf Engine)")
        st.write("**आर्किटेक्चर:** `EfficientNet-B0 / HSV Chrominance Rules`")
        st.write("**आकारमान:** `224x224 RGB, ImageNet Normalized`")
        st.write("**अचूकता हमी:** `< 60% खात्री किंवा पानाचा रंग नसताना थेट चेतावणी (Uncertain)`")

    conf_mat = metrics.get("confusion_matrix")
    classes = metrics.get("classes")
    if conf_mat and classes:
        st.markdown("---")
        st.subheader(f"📊 {t['conf_matrix_heading']}")
        fig_cm = px.imshow(
            conf_mat, x=classes, y=classes,
            color_continuous_scale="Greens", text_auto=True,
            labels=dict(x="Predicted Class", y="Actual Class"),
            template="plotly_white"
        )
        fig_cm.update_layout(height=360, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_cm, use_container_width=True)


# ==============================================================================
# MAIN APPLICATION CONTROLLER
# ==============================================================================
def main():
    current_page = st.session_state.get("page", "home")

    if current_page == "home":
        render_home_page()
    elif current_page == "fasal_chuna":
        render_fasal_chuna_wizard()
    elif current_page == "patta_photo":
        render_patta_photo_page()
    elif current_page == "bhav":
        render_bhav_page()
    elif current_page == "khat_salah":
        render_khat_salah_page()
    elif current_page == "compare":
        render_compare_page()
    elif current_page == "report":
        render_report_page()
    elif current_page == "about":
        render_about_page()
    else:
        render_home_page()


if __name__ == "__main__":
    main()