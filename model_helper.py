# model_helper.py -- Inference engines for Soil Fertilizer model & Leaf Doctor
"""
Provides model loading and inference pipelines:
1. predict_fertilizer(inputs: dict) -> top-3 fertilizers with probabilities,
   NPK nutrient statuses (using fertilizer_engine.npk_level), and feature importances.
2. predict_leaf(image: Image.Image, crop: str) -> real CNN or rule-based fallback,
   handling healthy leaves and uncertain non-leaf photos.
3. preprocess_and_predict(image, crop) -> backward-compatible entry point.
"""

import os
import json
import joblib
import numpy as np
import pandas as pd
from PIL import Image
from typing import Dict, Any, Tuple, Optional, List

from fertilizer_engine import npk_level, evaluate_soil_nutrients
from products import PRODUCTS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FERTILIZER_MODEL_PATH = os.path.join(BASE_DIR, "models", "fertilizer_model.joblib")
FERTILIZER_METRICS_PATH = os.path.join(BASE_DIR, "models", "metrics.json")
LEAF_WEIGHTS_PT = os.path.join(BASE_DIR, "models", "leaf_model.pt")
LEAF_WEIGHTS_ALT = os.path.join(BASE_DIR, "models", "leaf_effnet_b0.pt")
LEAF_CLASSES_JSON = os.path.join(BASE_DIR, "models", "leaf_classes.json")

# Standard Crop identifiers
COTTON = "Cotton (कापूस / कपास)"
TOMATO = "Tomato (टोमॅटो / टमाटर)"
SOYBEAN = "Soybean (सोयाबीन / सोयाबीन)"
WHEAT = "Wheat (गहू / गेहूं)"
MAIZE = "Maize (मका / मक्का)"
PADDY = "Paddy / Rice (भात / धान)"

# Soil Model Crop Mapping: Map Leaf Doctor crop keys to Soil CSV crop classes
CROP_TO_SOIL_MAP = {
    COTTON: "Cotton",
    SOYBEAN: "Oil seeds",  # Soybean maps directly to Oil seeds in CSV
    WHEAT: "Wheat",
    MAIZE: "Maize",
    PADDY: "Paddy",
    TOMATO: None,  # Tomato not in 99-row CSV, user selects substitute
}

# Standard symptom keys matching translations.py
DISEASE_CATALOG = [
    {
        "id": "cotton_nitrogen",
        "crop": COTTON,
        "symptom_key": "Yellowing lower leaves (खालची पाने पिवळी पडणे / निचली पत्तियां पीली होना)",
        "label": "Cotton - Nitrogen Deficiency",
    },
    {
        "id": "cotton_lalya",
        "crop": COTTON,
        "symptom_key": "Reddish leaves / Lalya (पाने लाल पडणे - लाल्या रोग / पत्तियां लाल पड़ना)",
        "label": "Cotton - Lalya (Magnesium Deficiency / Pest Attack)",
    },
    {
        "id": "cotton_healthy",
        "crop": COTTON,
        "symptom_key": "Healthy leaf (निरोगी पान / स्वस्थ पत्ती)",
        "label": "Cotton - Healthy Leaf",
    },
    {
        "id": "tomato_early_blight",
        "crop": TOMATO,
        "symptom_key": "Dark concentric spots on leaves (पानांवर काळे-तपकिरी गोल डाग / पत्तियों पर काले छल्लेदार धब्बे)",
        "label": "Tomato - Early Blight (Alternaria Solani)",
    },
    {
        "id": "tomato_leaf_curl",
        "crop": TOMATO,
        "symptom_key": "Leaf curling and stunted growth (पाने आकसणे व वाढ खुंटणे / पत्तियां मुड़ना और बौनापन)",
        "label": "Tomato - Leaf Curl Viral Disease",
    },
    {
        "id": "tomato_healthy",
        "crop": TOMATO,
        "symptom_key": "Healthy leaf (निरोगी पान / स्वस्थ पत्ती)",
        "label": "Tomato - Healthy Leaf",
    },
    {
        "id": "soybean_mosaic",
        "crop": SOYBEAN,
        "symptom_key": "Yellow mosaic patches on leaves (पानांवर पिवळे-हिरवे चट्टे / पत्तियों पर पीला मोज़ेक)",
        "label": "Soybean - Yellow Mosaic Virus",
    },
    {
        "id": "soybean_healthy",
        "crop": SOYBEAN,
        "symptom_key": "Healthy leaf (निरोगी पान / स्वस्थ पत्ती)",
        "label": "Soybean - Healthy Leaf",
    },
    {
        "id": "wheat_rust",
        "crop": WHEAT,
        "symptom_key": "Yellow/orange pustules / Rust (पानांवर पिवळा तांबेरा / पत्तियों पर पीला रतुआ)",
        "label": "Wheat - Yellow Stripe Rust",
    },
    {
        "id": "wheat_healthy",
        "crop": WHEAT,
        "symptom_key": "Healthy leaf (निरोगी पान / स्वस्थ पत्ती)",
        "label": "Wheat - Healthy Leaf",
    },
    {
        "id": "maize_blight",
        "crop": MAIZE,
        "symptom_key": "Long elliptical grayish lesions / Leaf blight (पानांवर लांबट करपा डाग / पत्तियों पर लंबा झुलसा धब्बे)",
        "label": "Maize - Turcicum Leaf Blight",
    },
    {
        "id": "maize_healthy",
        "crop": MAIZE,
        "symptom_key": "Healthy leaf (निरोगी पान / स्वस्थ पत्ती)",
        "label": "Maize - Healthy Leaf",
    },
    {
        "id": "paddy_blight",
        "crop": PADDY,
        "symptom_key": "Wavy margins and tip drying / Bacterial Blight (पानांच्या कडा व शेंडे वाळणे - करपा / पत्तियों के किनारे सूखना - झुलसा)",
        "label": "Paddy - Bacterial Leaf Blight",
    },
    {
        "id": "paddy_healthy",
        "crop": PADDY,
        "symptom_key": "Healthy leaf (निरोगी पान / स्वस्थ पत्ती)",
        "label": "Paddy - Healthy Leaf",
    },
]

BY_ID = {c["id"]: c for c in DISEASE_CATALOG}


# ==============================================================================
# Model Loading (Cached)
# ==============================================================================
_cached_fert_model = None


def get_fertilizer_model_payload():
    """Load trained fertilizer model and metadata once."""
    global _cached_fert_model
    if _cached_fert_model is not None:
        return _cached_fert_model

    if not os.path.exists(FERTILIZER_MODEL_PATH):
        # Auto-train if missing
        from train_models import train_and_evaluate
        train_and_evaluate()

    if os.path.exists(FERTILIZER_MODEL_PATH):
        _cached_fert_model = joblib.load(FERTILIZER_MODEL_PATH)
        return _cached_fert_model
    return None


def get_metrics_payload():
    """Load evaluation metrics JSON."""
    if os.path.exists(FERTILIZER_METRICS_PATH):
        with open(FERTILIZER_METRICS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ==============================================================================
# Soil Fertilizer Prediction
# ==============================================================================
def predict_fertilizer(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Predict fertilizer from soil & environmental metrics.
    inputs expects:
      Temperature, Humidity, Moisture, Soil Type, Crop Type, Nitrogen, Phosphorous, Potassium
    Returns top-3 recommendations, probabilities, nutrient statuses, and gap warnings.
    """
    payload = get_fertilizer_model_payload()
    if payload is None:
        raise FileNotFoundError("Fertilizer model not found at models/fertilizer_model.joblib")

    model = payload["model"]
    classes = payload["classes"]
    ref_stats = payload.get("reference_stats", {})

    # Construct dataframe matching feature names
    cols = ["Temperature", "Humidity", "Moisture", "Soil Type", "Crop Type", "Nitrogen", "Phosphorous", "Potassium"]
    row_data = {c: [inputs[c]] for c in cols}
    input_df = pd.DataFrame(row_data)

    # Inference probabilities
    proba = model.predict_proba(input_df)[0]
    top_indices = np.argsort(proba)[::-1][:3]

    top_3 = []
    for idx in top_indices:
        fert_name = str(classes[idx])
        prob_val = round(float(proba[idx]), 4)
        top_3.append({
            "fertilizer": fert_name,
            "probability": prob_val,
            "percentage": round(prob_val * 100, 1),
            "product_info": PRODUCTS.get(fert_name, {}),
        })

    best_fert = top_3[0]["fertilizer"]
    best_prob = top_3[0]["percentage"]

    # Soil nutrient status (with npk_level using <= bug fix)
    nutrient_status = evaluate_soil_nutrients(
        float(inputs["Nitrogen"]),
        float(inputs["Phosphorous"]),
        float(inputs["Potassium"]),
        ref_stats
    )

    # Check N-P-K nutrient gaps in the best recommendation
    gap_warnings = []
    rec_product = PRODUCTS.get(best_fert, {})
    if nutrient_status["Nitrogen"]["status"] == "Low" and rec_product.get("n", 0.0) == 0:
        gap_warnings.append("Nitrogen (N)")
    if nutrient_status["Phosphorous"]["status"] == "Low" and rec_product.get("p", 0.0) == 0:
        gap_warnings.append("Phosphorous (P)")
    if nutrient_status["Potassium"]["status"] == "Low" and rec_product.get("k", 0.0) == 0:
        gap_warnings.append("Potassium (K)")

    return {
        "best_fertilizer": best_fert,
        "confidence": best_prob,
        "top_3": top_3,
        "nutrient_status": nutrient_status,
        "gap_warnings": gap_warnings,
        "feature_importances": payload.get("feature_importances", {}),
    }


# ==============================================================================
# Leaf Image Analysis
# ==============================================================================
def preprocess_leaf(image: Image.Image) -> Tuple[Image.Image, np.ndarray]:
    """Resize image to 224x224 and scale RGB to 0-1."""
    rgb_img = image.convert("RGB").resize((224, 224), Image.Resampling.BILINEAR)
    arr = np.asarray(rgb_img, dtype=np.float32) / 255.0
    return rgb_img, arr


def color_features(image: Image.Image) -> Dict[str, float]:
    """
    Extract chrominance and leaf area features using HSV and RGB channels.
    Accurately identifies green vegetation vs background or non-leaf objects.
    """
    img, arr = preprocess_leaf(image)
    hsv = np.asarray(img.convert("HSV"), dtype=np.float32)

    hue = hsv[..., 0] * 360.0 / 255.0
    sat = hsv[..., 1] / 255.0
    val = hsv[..., 2] / 255.0

    # Leaf pixels: has color saturation and reasonable brightness (not pure white / black / grey)
    leaf_mask = (sat > 0.18) & (val > 0.15) & (val < 0.98)
    total_pixels = 224 * 224
    leaf_pixel_ratio = float(leaf_mask.sum()) / float(total_pixels)
    valid_leaf_count = max(int(leaf_mask.sum()), 1)

    def leaf_frac(mask):
        return float((mask & leaf_mask).sum()) / valid_leaf_count

    green_mask = (hue >= 65) & (hue < 170)
    yellow_mask = (hue >= 38) & (hue < 65) & (val > 0.50)
    red_mask = ((hue < 22) | (hue > 335)) & (sat > 0.30)
    brown_mask = (hue >= 10) & (hue < 38) & (val <= 0.55)

    return {
        "leaf_pixel_ratio": round(leaf_pixel_ratio, 3),
        "green": leaf_frac(green_mask),
        "yellow": leaf_frac(yellow_mask),
        "red": leaf_frac(red_mask),
        "brown": leaf_frac(brown_mask),
        "r_std": float(np.std(arr[..., 0])),
        "hue_std": float(np.std(hue[leaf_mask])) if leaf_mask.any() else 0.0,
    }


def _rule_based_diagnosis(image: Image.Image, crop: str) -> Dict[str, Any]:
    """
    Color-variance heuristic fallback when trained PyTorch weights are not present.
    Labels result clearly as 'Estimated (color-rule based, not a trained model)'
    and does NOT return a fake confidence percentage.
    """
    f = color_features(image)

    # 1. Non-leaf or low vegetation check (e.g. plain white image, desktop screenshot)
    if f["leaf_pixel_ratio"] < 0.18 or (f["green"] < 0.08 and f["yellow"] < 0.08 and f["red"] < 0.08 and f["brown"] < 0.08):
        return {
            "status": "uncertain",
            "class_id": None,
            "crop": crop,
            "symptom_key": None,
            "label": "Uncertain / Non-leaf Image",
            "confidence": None,
            "engine": "Estimated (color-rule based, not a trained model)",
            "features": f,
            "top_3": [],
        }

    # 2. Healthy Leaf Check: strong green foliage, very low disease discoloration
    abnormal = f["yellow"] + f["red"] + f["brown"]
    if f["green"] >= 0.72 and abnormal < 0.15:
        # Find healthy entry for this crop
        healthy_id = f"{crop.split()[0].lower()}_healthy"
        target_entry = BY_ID.get(healthy_id, {
            "id": "healthy",
            "crop": crop,
            "symptom_key": "Healthy leaf (निरोगी पान / स्वस्थ पत्ती)",
            "label": f"{crop} - Healthy Leaf",
        })
        return {
            "status": "healthy",
            "class_id": target_entry["id"],
            "crop": crop,
            "symptom_key": target_entry["symptom_key"],
            "label": target_entry["label"],
            "confidence": None,
            "engine": "Estimated (color-rule based, not a trained model)",
            "features": f,
            "top_3": [],
        }

    # 3. Disease patterns by crop
    scores = {}
    if crop == COTTON:
        scores["cotton_nitrogen"] = f["yellow"] / 0.30
        scores["cotton_lalya"] = f["red"] / 0.22
    elif crop == TOMATO:
        scores["tomato_early_blight"] = (f["brown"] / 0.20) * 0.6 + (min(1.0, f["r_std"] / 0.22)) * 0.4
        scores["tomato_leaf_curl"] = (f["yellow"] / 0.28) * 0.6 + (min(1.0, f["hue_std"] / 55.0)) * 0.4
    elif crop == SOYBEAN:
        scores["soybean_mosaic"] = (f["yellow"] / 0.25) * 0.7 + (min(1.0, f["hue_std"] / 45.0)) * 0.3
    elif crop == WHEAT:
        scores["wheat_rust"] = (f["yellow"] + f["red"] * 0.5) / 0.30
    elif crop == MAIZE:
        scores["maize_blight"] = f["brown"] / 0.25
    elif crop == PADDY:
        scores["paddy_blight"] = (f["yellow"] + f["brown"]) / 0.35
    else:
        # Default across all
        scores["cotton_nitrogen"] = f["yellow"]
        scores["cotton_lalya"] = f["red"]

    if not scores or max(scores.values()) < 0.25:
        return {
            "status": "uncertain",
            "class_id": None,
            "crop": crop,
            "symptom_key": None,
            "label": "Uncertain / Low Leaf Contrast",
            "confidence": None,
            "engine": "Estimated (color-rule based, not a trained model)",
            "features": f,
            "top_3": [],
        }

    best_id = max(scores, key=scores.get)
    rec_class = BY_ID.get(best_id, DISEASE_CATALOG[0])

    return {
        "status": "ok",
        "class_id": best_id,
        "crop": rec_class["crop"],
        "symptom_key": rec_class["symptom_key"],
        "label": rec_class["label"],
        "confidence": None,  # Rule-based does NOT return a fake confidence percentage
        "engine": "Estimated (color-rule based, not a trained model)",
        "features": f,
        "top_3": [{"label": BY_ID[k]["label"], "score": round(min(1.0, v), 2)} for k, v in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]],
    }


def _load_leaf_cnn():
    """Attempt loading trained PyTorch weights."""
    pt_path = LEAF_WEIGHTS_PT if os.path.exists(LEAF_WEIGHTS_PT) else LEAF_WEIGHTS_ALT
    if not (os.path.exists(pt_path) and os.path.exists(LEAF_CLASSES_JSON)):
        return None, None

    try:
        # pyrefly: ignore[missing-import]
        import torch
        # pyrefly: ignore[missing-import]
        from torchvision import models
        with open(LEAF_CLASSES_JSON, "r", encoding="utf-8") as f:
            classes = json.load(f)

        net = models.efficientnet_b0(weights=None)
        in_features = net.classifier[1].in_features
        net.classifier[1] = torch.nn.Sequential(
            torch.nn.Dropout(p=0.3, inplace=True),
            torch.nn.Linear(in_features, len(classes))
        )
        net.load_state_dict(torch.load(pt_path, map_location="cpu"))
        net.eval()
        return net, classes
    except Exception as e:
        print(f"Leaf CNN weights found but failed to load: {e}")
        return None, None


def _predict_cnn(model, classes, image: Image.Image, crop: str) -> Dict[str, Any]:
    """Inference with real EfficientNet-B0 softmax confidence."""
    # pyrefly: ignore[missing-import]
    import torch
    f = color_features(image)

    # 1. Non-leaf or low vegetation check
    if f["leaf_pixel_ratio"] < 0.18 or (f["green"] < 0.08 and f["yellow"] < 0.08 and f["red"] < 0.08 and f["brown"] < 0.08):
        return {
            "status": "uncertain",
            "class_id": None,
            "crop": crop,
            "symptom_key": None,
            "label": "Uncertain / Non-leaf Image",
            "confidence": None,
            "engine": "EfficientNet-B0 (Trained Weights)",
            "features": f,
            "top_3": [],
        }

    _, arr = preprocess_leaf(image)
    mean, std = np.array([0.485, 0.456, 0.406]), np.array([0.229, 0.224, 0.225])
    norm_tensor = torch.tensor(((arr - mean) / std).transpose(2, 0, 1)[None], dtype=torch.float32)

    with torch.no_grad():
        logits = model(norm_tensor)[0]
        probs = torch.softmax(logits, dim=0).cpu().numpy()

    top_idxs = np.argsort(probs)[::-1][:3]
    top_3 = []
    for idx in top_idxs:
        cid = classes[idx]
        display_label = BY_ID.get(cid, {}).get("label", cid)
        top_3.append({
            "class_id": cid,
            "label": display_label,
            "probability": round(float(probs[idx]), 4),
            "percentage": round(float(probs[idx]) * 100, 1),
        })

    best = top_3[0]
    best_cid = best["class_id"]
    confidence_val = best["percentage"]

    # Rule: If confidence < 60% -> uncertain
    if confidence_val < 60.0:
        return {
            "status": "uncertain",
            "class_id": best_cid,
            "crop": crop,
            "symptom_key": None,
            "label": "Uncertain Prediction",
            "confidence": confidence_val,
            "engine": "EfficientNet-B0 (Trained Weights)",
            "features": f,
            "top_3": top_3,
        }

    rec = BY_ID.get(best_cid, DISEASE_CATALOG[0])
    is_healthy = "healthy" in best_cid.lower()

    return {
        "status": "healthy" if is_healthy else "ok",
        "class_id": best_cid,
        "crop": rec.get("crop", crop),
        "symptom_key": rec.get("symptom_key", "Healthy leaf (निरोगी पान / स्वस्थ पत्ती)"),
        "label": rec.get("label", best["label"]),
        "confidence": confidence_val,
        "engine": "EfficientNet-B0 (Trained Weights)",
        "features": f,
        "top_3": top_3,
    }


def predict_leaf(image: Image.Image, crop: str = COTTON) -> Dict[str, Any]:
    """
    High-level leaf diagnosis.
    Chooses CNN if trained weights exist, else falls back to rule-based analysis.
    """
    net, classes = _load_leaf_cnn()
    if net is not None and classes:
        return _predict_cnn(net, classes, image, crop)
    return _rule_based_diagnosis(image, crop)


def preprocess_and_predict(image: Image.Image, crop: Optional[str] = None):
    """
    Backward-compatible wrapper for app.py.
    Returns:
      (crop_key, symptom_key, detected_label, confidence)
    """
    if crop is None:
        crop = COTTON
    diag = predict_leaf(image, crop)

    crop_key = diag.get("crop") or crop
    symptom_key = diag.get("symptom_key") or "Healthy leaf (निरोगी पान / स्वस्थ पत्ती)"
    detected_label = diag.get("label") or "Analyzed Leaf"
    confidence = diag.get("confidence")

    return crop_key, symptom_key, detected_label, confidence