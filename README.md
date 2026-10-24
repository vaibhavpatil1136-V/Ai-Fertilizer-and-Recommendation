# AgriCare - AI Crop Doctor & Fertilizer Advisor 🌱

An upgraded, production-grade Machine Learning and Agronomic Advisory platform built with Streamlit, Scikit-Learn, XGBoost, and PyTorch (EfficientNet-B0).

---## 🌟 Key Features

1. **Farmer-First Mobile UX (No Login Wall)**:
   - Starts directly on the Dashboard/Home page without login friction.
   - Clean top bar with language selector (**मराठी / हिन्दी / English**) and a compact **Login / Register** popover.
   - Big touch targets (min 56px) and large fonts (min 18px) designed for low-literacy farmers on mobile phones.
   - Front 2-column card grid with 6 core services:
     1. 🌱 **Fasal Chuna** (3-click Crop & Advisory Wizard)
     2. 📸 **Patta Photo** (Leaf Diagnosis with Camera & Upload)
     3. 💰 **Bhav** (Maharashtra APMC Market Price Trends)
     4. 🧪 **Khat Salah** (Soil & Fertilizer Advisor)
     5. 🛒 **Product Compare**
     6. 📄 **Report Download** (login-gated)
     *Secondary*: ℹ️ About & Model Analytics.

2. **Step-by-Step "Fasal Chuna" Wizard**:
   - Step 1: Crop Selection from 11 supported Maharashtra crops with big pictorial cards.
   - Step 2: Problem selection using visual symptom cards (Yellowing, Leaf Spots, Stunted Growth, Pest/Insects, Poor Flowering, Water Stress, or Unknown).
   - Step 3: Actionable, concise result in the farmer's language:
     - ✅ What to do (numbered short steps)
     - 🧪 Recommended fertilizer/medicine
     - 🛒 Active ingredients & NPK ratio to look for on commercial labels
     - ⚖️ Practical per-acre or per-pump dosage
     - ⚠️ Safety precautions
     - 🔊 Voice readout button.

3. **Maharashtra-Only Market Price Trends ("Bhav")**:
   - Strictly restricted to Maharashtra APMC mandis (Pune, Nashik, Nagpur, Kolhapur, Sangli, Solapur, Latur, Jalgaon, Amravati, Akola, Yavatmal, Chhatrapati Sambhajinagar, etc.).
   - Fetches live Agmarknet data via `data.gov.in` (`filters[state]=Maharashtra`) with automatic fallback to historical APMC records (`data/mandi_prices_maharashtra.csv`).
   - 3-year monthly price comparison line chart (Plotly).
   - Historical card showing prices for the current month across the last 3 years.
   - Month-over-month seasonal percentage changes and next-month price forecast with Government MSP / FRP reference benchmarks.
   - Top 3 highest-paying mandis in Maharashtra for the chosen crop.

4. **Multi-Language Voice (Text-to-Speech)**:
   - 🔊 "Sunao / सुनाओ / Listen" button on all advisory and market result cards.
   - Dual-engine speech system:
     - `gTTS` generating in-memory MP3 audio with slow/normal speed toggle and MD5 caching.
     - Automatic fallback to browser-native Web Speech API (`speechSynthesis`).
     - Script cleaner that converts currency and percentages to natural spoken words (e.g. "रुपये प्रति क्विंटल", "टक्के").

5. **Secure SQLite Authentication**:
   - Standalone SQLite user store (`users.db`) with salted passwords (`bcrypt` / salted SHA-256).
   - Public access to advice, market trends, and leaf diagnosis; authentication only required for saving history and downloading reports.

6. **AI Soil & Leaf Doctor ML Models**:
   - Preserves all trained XGBoost/RandomForest models on `Fertilizer_Prediction.csv` (top-3 recommendations, NPK boundary checks).
   - Dual-mode leaf diagnosis (camera/upload) with non-leaf image rejection.

---

## 🚀 Quickstart & Setup

### 1. Installation
```bash
# Windows
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch Streamlit
```bash
streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 🧪 Running Unit Tests
```bash
python -m pytest tests/test_pipeline.py -v
```
All 10 test suites validate:
1. Fertilizer model top-3 probabilistic predictions.
2. Potassium boundary logic ($K=0 \implies \text{Low}$).
3. Non-leaf / blank photo rejection.
4. Advisory data integrity in 3 languages.
5. Multilingual translations dictionary.
6. Product catalog specifications.
7. SQLite user registration & authentication.
8. Crop-specific problem-solution mapping & ingredient specifications.
9. Maharashtra-only Bhav calculations, seasonal changes & MSP benchmarks.
10. Spoken text cleaning and natural language synthesis.

---

## 📁 Project Architecture

```
crop_ai_project/
├── app.py                      # Main Streamlit web application & card router
├── ui_components.py            # High-contrast mobile CSS, top bar, & navigation cards
├── auth.py                     # SQLite auth (bcrypt/salted sha256) & user database
├── price_trends.py             # Maharashtra-only APMC price trend & forecast engine
├── problem_solutions.py        # 11-crop x 7-problem agronomic advice & label ingredients
├── voice.py                    # Multilingual gTTS & Web Speech API speech engine
├── model_helper.py             # Inference pipeline for fertilizer & leaf models
├── fertilizer_engine.py        # Nutrient calculation logic
├── products.py                 # Multilingual product catalog & official URLs
├── translations.py             # Multilingual UI strings & extended ADVISORY_DATA
├── report_generator.py         # PDF and CSV report generator
├── train_models.py             # Stratified 5-Fold CV training for fertilizer models
├── Fertilizer_Prediction.csv   # Field training dataset (99 samples)
├── data/
│   └── mandi_prices_maharashtra.csv # Historical Maharashtra APMC price records
├── models/
│   ├── fertilizer_model.joblib # Production ML pipeline artifact
│   └── metrics.json            # Honest CV & holdout evaluation metrics
├── tests/
│   └── test_pipeline.py        # Automated test suite (10 test suites)
└── requirements.txt            # Pinned dependencies (gTTS, bcrypt, plotly, etc.)
```
��─ tests/
│   └── test_pipeline.py        # Automated test suite
└── requirements.txt            # Pinned production dependencies
```
