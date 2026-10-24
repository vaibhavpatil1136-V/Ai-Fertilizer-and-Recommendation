# tests/test_pipeline.py -- Automated unit and integration test suite
"""
Unit tests validating:
1. Fertilizer prediction pipeline returns top-3 valid classes with correct probability distribution.
2. Potassium bug fix: K = 0 correctly classifies as 'Low', not 'Medium'.
3. Non-leaf / plain white images are identified as 'uncertain'.
4. Multilingual ADVISORY_DATA and TRANSLATIONS dictionary completeness and consistency across all 3 languages.
5. Products database covers all 7 fertilizer classes with valid manufacturer URLs and NPK ratings.
6. SQLite Authentication: user registration, salted hashing, and login validation.
7. Crop-to-Problem Wizard: crop-specific restriction, solution steps, active ingredients, dosage, precautions.
8. Maharashtra Price Trends: strictly Maharashtra data, 3-year monthly trend, next-month seasonal %, MSP, and estimates.
9. Voice text sanitizer: cleans markdown and converts symbols to spoken words across English, Marathi, Hindi.
"""

import pytest
import numpy as np
import pandas as pd
from PIL import Image

from model_helper import predict_fertilizer, predict_leaf, COTTON, TOMATO, SOYBEAN
from fertilizer_engine import npk_level
from translations import TRANSLATIONS, ADVISORY_DATA
from products import PRODUCTS
from auth import register_user, authenticate_user
from problem_solutions import SUPPORTED_CROPS, PROBLEM_OPTIONS, get_crop_solution
from price_trends import (
    load_maharashtra_mandi_data,
    compute_3year_trends,
    MAHARASHTRA_MSP,
    CROP_COMMODITY_MAP,
)
from voice import clean_text_for_speech, build_spoken_text

EXPECTED_FERTILIZERS = {"Urea", "DAP", "28-28", "14-35-14", "20-20", "17-17-17", "10-26-26"}
LANGUAGES = ["English", "मराठी", "हिन्दी"]
ADVISORY_KEYS = ["condition", "cause", "solution", "market_brands", "ingredients", "tips"]


def test_fertilizer_prediction_returns_top3_valid_classes():
    sample_input = {
        "Temperature": 26.0,
        "Humidity": 52.0,
        "Moisture": 38.0,
        "Soil Type": "Sandy",
        "Crop Type": "Maize",
        "Nitrogen": 37.0,
        "Phosphorous": 0.0,
        "Potassium": 0.0,
    }
    result = predict_fertilizer(sample_input)
    assert "top_3" in result, "Missing top_3 in prediction result"
    assert len(result["top_3"]) == 3, f"Expected 3 candidates, got {len(result['top_3'])}"

    for cand in result["top_3"]:
        assert cand["fertilizer"] in EXPECTED_FERTILIZERS, f"Invalid fertilizer returned: {cand['fertilizer']}"
        assert 0.0 <= cand["probability"] <= 1.0, f"Probability out of range: {cand['probability']}"

    assert result["best_fertilizer"] in EXPECTED_FERTILIZERS
    assert result["confidence"] > 0.0


def test_potassium_npk_level_bug_fix():
    p33 = 0.0
    p66 = 10.0

    # The bug fix ensures 0.0 <= 0.0 returns Low
    status_zero = npk_level(0.0, p33, p66)
    assert status_zero == "Low", f"Potassium bug regression! Expected 'Low' for K=0, but got '{status_zero}'"

    status_med = npk_level(5.0, p33, p66)
    assert status_med == "Medium"

    status_high = npk_level(15.0, p33, p66)
    assert status_high == "High"


def test_non_leaf_and_white_image_gives_uncertain():
    white_arr = np.ones((224, 224, 3), dtype=np.uint8) * 255
    white_img = Image.fromarray(white_arr)
    diag_white = predict_leaf(white_img, crop=COTTON)
    assert diag_white["status"] == "uncertain", f"Expected 'uncertain' for plain white image, got {diag_white['status']}"

    black_arr = np.zeros((224, 224, 3), dtype=np.uint8)
    black_img = Image.fromarray(black_arr)
    diag_black = predict_leaf(black_img, crop=COTTON)
    assert diag_black["status"] == "uncertain", f"Expected 'uncertain' for black image, got {diag_black['status']}"


def test_advisory_data_integrity_and_languages():
    assert len(ADVISORY_DATA) >= 6, f"Expected at least 6 crops in ADVISORY_DATA, found {len(ADVISORY_DATA)}"

    for crop_name, symptoms in ADVISORY_DATA.items():
        assert len(symptoms) >= 1, f"Crop '{crop_name}' has no symptoms defined"
        healthy_found = any("healthy" in sym.lower() or "निरोगी" in sym for sym in symptoms.keys())
        assert healthy_found, f"Crop '{crop_name}' lacks a 'Healthy leaf' symptom entry"

        for sym_name, lang_dict in symptoms.items():
            for lang in LANGUAGES:
                assert lang in lang_dict, f"Missing language '{lang}' in crop '{crop_name}', symptom '{sym_name}'"
                entry = lang_dict[lang]
                for key in ADVISORY_KEYS:
                    assert key in entry, f"Missing key '{key}' in crop '{crop_name}', symptom '{sym_name}', lang '{lang}'"
                    assert len(str(entry[key]).strip()) > 0


def test_translations_dictionary_keys():
    en_keys = set(TRANSLATIONS["English"].keys())
    mr_keys = set(TRANSLATIONS["मराठी"].keys())
    hi_keys = set(TRANSLATIONS["हिन्दी"].keys())

    missing_in_mr = en_keys - mr_keys
    missing_in_hi = en_keys - hi_keys

    assert len(missing_in_mr) == 0, f"Missing Marathi translation keys: {missing_in_mr}"
    assert len(missing_in_hi) == 0, f"Missing Hindi translation keys: {missing_in_hi}"


def test_products_catalog_coverage():
    assert set(PRODUCTS.keys()) == EXPECTED_FERTILIZERS, f"PRODUCTS does not match all 7 fertilizers: {set(PRODUCTS.keys())}"

    for fert_name, data in PRODUCTS.items():
        assert "npk_ratio" in data
        assert "manufacturer_url" in data
        assert data["manufacturer_url"].startswith("http")
        assert "brands" in data
        for lang in LANGUAGES:
            assert lang in data, f"PRODUCTS['{fert_name}'] missing language '{lang}'"
            prod_lang = data[lang]
            assert "title" in prod_lang
            assert "composition" in prod_lang
            assert "ingredients" in prod_lang
            assert "best_for" in prod_lang
            assert "application_note" in prod_lang


def test_auth_registration_and_login():
    """Verify user registration and authentication via SQLite and salted hashing."""
    test_user = "testfarmer_987"
    test_pass = "kisanPass123"

    # Register user
    ok, msg = register_user(test_user, test_pass, phone="9876543210")
    # Even if user exists from previous run, login must succeed
    auth_ok = authenticate_user(test_user, test_pass)
    assert auth_ok is True, "Authentication failed for newly registered user"

    # Invalid password check
    auth_bad = authenticate_user(test_user, "wrongPassword")
    assert auth_bad is False, "Authentication succeeded with incorrect password"


def test_crop_problem_solution_mapping():
    """Verify crop-specific solutions, action steps, active ingredients, and dosage."""
    assert len(SUPPORTED_CROPS) >= 11, "Must support at least 11 crops"

    # Cotton Yellowing
    cotton_sol = get_crop_solution("Cotton", "yellowing", lang="मराठी")
    assert "युरिया" in cotton_sol["fertilizer"] or "१९:१९:१९" in cotton_sol["fertilizer"]
    assert "नत्र" in cotton_sol["required_ingredients"] or "Nitrogen" in cotton_sol["required_ingredients"]
    assert len(cotton_sol["action_steps"]) >= 2
    assert "डोस" in cotton_sol["dosage"] or "किलो" in cotton_sol["dosage"] or "ग्रॅम" in cotton_sol["dosage"]

    # Guarantee Cotton selection never returns Tomato/Soybean advice
    assert "टोमॅटो" not in cotton_sol["cause"]
    assert "सोयाबीन" not in cotton_sol["cause"]


def test_maharashtra_price_trends_calculation():
    """Verify Maharashtra-only mandi prices, 3-year trends, next-month change %, and estimates."""
    df, is_sample = load_maharashtra_mandi_data("Cotton", district="Nagpur")
    assert not df.empty, "Failed to load Maharashtra Cotton mandi data"
    # Verify strict Maharashtra isolation:
    assert (df["state"].str.lower() == "maharashtra").all(), "Found non-Maharashtra records!"

    trends = compute_3year_trends(df, current_month=10)
    assert "years" in trends and len(trends["years"]) >= 3
    assert "pct_changes" in trends
    assert "next_month_estimate" in trends
    assert trends["next_month_estimate"] > 1000, f"Unrealistic estimate: {trends['next_month_estimate']}"
    assert "Cotton" in MAHARASHTRA_MSP
    assert MAHARASHTRA_MSP["Cotton"] > 5000


def test_voice_script_cleaning():
    """Verify that speech cleaner converts technical markdown, rupees, and percent symbols into spoken words."""
    raw_text = "Apply 19:19:19 fertilizer at ₹450 with 15% discount [Buy](https://link.com) *now*."
    cleaned = clean_text_for_speech(raw_text, lang="मराठी")
    assert "रुपये" in cleaned
    assert "टक्के" in cleaned
    assert "http" not in cleaned
    assert "*" not in cleaned
    assert "[" not in cleaned
