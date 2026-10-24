# train_models.py -- Fertilizer prediction training script
"""
Trains Random Forest (baseline) and XGBoost on Fertilizer_Prediction.csv.
Compares using Stratified 5-Fold Cross Validation (accuracy + macro-F1),
and saves the best pipeline, metrics, reference stats, and feature importances.
"""

import os
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

CSV_PATH = "Fertilizer_Prediction.csv"
NUMERIC_FEATURES = ["Temperature", "Humidity", "Moisture", "Nitrogen", "Phosphorous", "Potassium"]
CATEGORICAL_FEATURES = ["Soil Type", "Crop Type"]


def load_dataset(csv_path: str = CSV_PATH) -> pd.DataFrame:
    """Load and clean Fertilizer_Prediction.csv."""
    if not os.path.exists(csv_path):
        # Fallback if in different relative directory
        alt_paths = [
            os.path.join(os.path.dirname(__file__), "Fertilizer_Prediction.csv"),
            os.path.join("..", "Project", "AI-Fertilizer-Recommendation", "Fertilizer Prediction.csv"),
        ]
        for p in alt_paths:
            if os.path.exists(p):
                csv_path = p
                break

    df = pd.read_csv(csv_path)
    # Strip whitespace from column names
    df.columns = [c.strip() for c in df.columns]
    # Dataset spelling fix: Temparature -> Temperature
    if "Temparature" in df.columns and "Temperature" not in df.columns:
        df = df.rename(columns={"Temparature": "Temperature"})
    # Strip whitespace from string values
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].astype(str).str.strip()

    df = df.dropna().drop_duplicates().reset_index(drop=True)
    return df


def build_pipeline(classifier) -> Pipeline:
    """Compose preprocessing + classifier into an end-to-end pipeline."""
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
        ]
    )
    return Pipeline([("preprocessor", preprocessor), ("classifier", classifier)])


def train_and_evaluate():
    """Execute stratified 5-fold CV, compare models, and save best pipeline."""
    os.makedirs("models", exist_ok=True)
    df = load_dataset()
    print(f"Loaded dataset: {len(df)} samples across {df['Fertilizer Name'].nunique()} fertilizer classes.")

    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y_raw = df["Fertilizer Name"]

    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(y_raw)
    classes = label_encoder.classes_.tolist()
    n_classes = len(classes)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    candidates = {
        "Random Forest": build_pipeline(
            RandomForestClassifier(
                n_estimators=300,
                max_depth=8,
                random_state=42,
                class_weight="balanced",
            )
        )
    }

    if HAS_XGB:
        candidates["XGBoost"] = build_pipeline(
            XGBClassifier(
                n_estimators=200,
                max_depth=4,
                learning_rate=0.08,
                subsample=0.85,
                colsample_bytree=0.85,
                objective="multi:softprob",
                num_class=n_classes,
                eval_metric="mlogloss",
                random_state=42,
            )
        )

    cv_results = {}
    print("\n--- Model Evaluation (Stratified 5-Fold Cross-Validation) ---")
    for name, pipe in candidates.items():
        scoring = {"accuracy": "accuracy", "f1_macro": "f1_macro"}
        scores = cross_validate(pipe, X, y, cv=cv, scoring=scoring, n_jobs=1)
        acc_mean = float(np.mean(scores["test_accuracy"]))
        acc_std = float(np.std(scores["test_accuracy"]))
        f1_mean = float(np.mean(scores["test_f1_macro"]))
        f1_std = float(np.std(scores["test_f1_macro"]))
        cv_results[name] = {
            "accuracy_mean": round(acc_mean, 4),
            "accuracy_std": round(acc_std, 4),
            "f1_macro_mean": round(f1_mean, 4),
            "f1_macro_std": round(f1_std, 4),
        }
        print(f"{name:15s} | Accuracy: {acc_mean:.4f} (+/- {acc_std:.4f}) | Macro-F1: {f1_mean:.4f} (+/- {f1_std:.4f})")

    # Select best model based on CV accuracy then F1
    best_name = max(cv_results, key=lambda k: (cv_results[k]["accuracy_mean"], cv_results[k]["f1_macro_mean"]))
    print(f"\nBest model selected: {best_name}")

    # Holdout validation (honest split 75/25)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, stratify=y, random_state=42)
    eval_model = candidates[best_name]
    eval_model.fit(X_train, y_train)
    y_pred = eval_model.predict(X_test)

    clf_report = classification_report(y_test, y_pred, target_names=classes, output_dict=True, zero_division=0)
    conf_mat = confusion_matrix(y_test, y_pred).tolist()

    # Train final pipeline on 100% of data
    final_pipeline = candidates[best_name]
    final_pipeline.fit(X, y)

    # Calculate feature importances using Random Forest
    rf_pipeline = candidates["Random Forest"]
    rf_pipeline.fit(X, y)
    feature_names = rf_pipeline.named_steps["preprocessor"].get_feature_names_out().tolist()
    rf_clf = rf_pipeline.named_steps["classifier"]
    importances = {feat: round(float(imp), 4) for feat, imp in zip(feature_names, rf_clf.feature_importances_)}

    # Reference statistics for soil nutrient thresholds (p33, p66, min, max, mean)
    ref_stats = {}
    for col in NUMERIC_FEATURES:
        vals = df[col].astype(float)
        ref_stats[col] = {
            "min": float(vals.min()),
            "max": float(vals.max()),
            "mean": round(float(vals.mean()), 2),
            "p33": round(float(np.percentile(vals, 33)), 2),
            "p66": round(float(np.percentile(vals, 66)), 2),
        }

    # Save pipeline artifact
    model_payload = {
        "model": final_pipeline,
        "label_encoder": label_encoder,
        "best_model_name": best_name,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "soil_types": sorted(df["Soil Type"].unique().tolist()),
        "crop_types": sorted(df["Crop Type"].unique().tolist()),
        "classes": classes,
        "reference_stats": ref_stats,
        "feature_importances": importances,
    }
    joblib.dump(model_payload, "models/fertilizer_model.joblib")

    # Metrics JSON
    metrics_data = {
        "best_model": best_name,
        "cv_scores": cv_results,
        "holdout_accuracy": round(float(clf_report["accuracy"]), 4),
        "holdout_macro_f1": round(float(f1_score(y_test, y_pred, average="macro")), 4),
        "n_samples": len(df),
        "classes": classes,
        "classification_report": clf_report,
        "confusion_matrix": conf_mat,
        "feature_importances": importances,
        "reference_stats": ref_stats,
        "soil_types": sorted(df["Soil Type"].unique().tolist()),
        "crop_types": sorted(df["Crop Type"].unique().tolist()),
    }

    with open("models/metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2)

    with open("models/fertilizer_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2)

    print(f"Successfully saved model to models/fertilizer_model.joblib and metrics to models/metrics.json")
    print(f"CV accuracy: {cv_results[best_name]['accuracy_mean']:.4f}")
    return metrics_data


if __name__ == "__main__":
    train_and_evaluate()
