# voice.py -- Text-to-speech module using gTTS with Web Speech API browser fallback
"""
Voice audio generation and speech synthesis for rural farmers.
Supports English ('en'), Hindi ('hi'), and Marathi ('mr').
Generates MP3 audio in-memory and caches generated clips to prevent redundant API calls.
"""

import io
import re
import hashlib
from typing import Optional, Dict, Any
import streamlit as st

try:
    from gtts import gTTS
    HAS_GTTS = True
except ImportError:
    HAS_GTTS = False

_AUDIO_CACHE: Dict[str, bytes] = {}

LANG_CODE_MAP = {
    "English": "en",
    "हिन्दी": "hi",
    "मराठी": "mr"
}


def clean_text_for_speech(text: str, lang: str) -> str:
    """
    Sanitize markdown, bullet points, numbers, and symbols into natural spoken language.
    Replaces technical symbols with spoken equivalents.
    """
    if not text:
        return ""

    # Remove markdown links, code blocks, bold, italics, headers
    cleaned = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    cleaned = re.sub(r'[*#_`~]', ' ', cleaned)
    cleaned = re.sub(r'https?://\S+', '', cleaned)

    # Symbol translations based on language
    if lang == "मराठी":
        cleaned = cleaned.replace("₹", " रुपये ")
        cleaned = cleaned.replace("%", " टक्के ")
        cleaned = cleaned.replace("/acre", " प्रति एकर ")
        cleaned = cleaned.replace("kg", " किलो ")
        cleaned = cleaned.replace("gm", " ग्रॅम ")
        cleaned = cleaned.replace("ml", " मिली ")
        cleaned = cleaned.replace("N-P-K", " एन पी के ")
    elif lang == "हिन्दी":
        cleaned = cleaned.replace("₹", " रुपये ")
        cleaned = cleaned.replace("%", " प्रतिशत ")
        cleaned = cleaned.replace("/acre", " प्रति एकड़ ")
        cleaned = cleaned.replace("kg", " किलो ")
        cleaned = cleaned.replace("gm", " ग्राम ")
        cleaned = cleaned.replace("ml", " मिली ")
        cleaned = cleaned.replace("N-P-K", " एन पी के ")
    else:  # English
        cleaned = cleaned.replace("₹", " Rupees ")
        cleaned = cleaned.replace("%", " percent ")
        cleaned = cleaned.replace("/acre", " per acre ")
        cleaned = cleaned.replace("kg", " kilograms ")
        cleaned = cleaned.replace("gm", " grams ")
        cleaned = cleaned.replace("ml", " milliliters ")

    # Strip remaining emojis and non-standard symbols
    cleaned = re.sub(r'[^\w\s.,;:?!\u0900-\u097F]', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def build_spoken_text(data: Dict[str, Any], lang: str) -> str:
    """
    Construct a complete, natural-sounding voice script from structured result dictionary.
    """
    if "spoken_script" in data:
        return clean_text_for_speech(data["spoken_script"], lang)

    crop = data.get("crop", "")
    problem = data.get("problem") or data.get("condition") or data.get("result", "")
    solution = data.get("solution") or data.get("solution_steps", "")
    product = data.get("fertilizer") or data.get("market_brands", "")
    ingredients = data.get("required_ingredients") or data.get("ingredients", "")
    dosage = data.get("dosage", "")
    precautions = data.get("precautions") or data.get("tips", "")

    if isinstance(solution, list):
        solution_str = ". ".join(solution)
    else:
        solution_str = str(solution)

    if lang == "मराठी":
        script = f"शेतकरी मित्रांनो, तुमच्या {crop} पिकासाठी सल्ला ऐका. "
        if problem:
            script += f"समस्या आहे: {problem}. "
        if solution_str:
            script += f"उपाय: {solution_str}. "
        if product:
            script += f"शिफारस केलेले खत किंवा औषध: {product}. "
        if ingredients:
            script += f"बाजारातून खरेदी करताना पाकीटावर हे घटक नक्की तपासा: {ingredients}. "
        if dosage:
            script += f"डोस प्रमाण: {dosage}. "
        if precautions:
            script += f"काळजी घ्या: {precautions}. "
        script += "अधिक मार्गदर्शनासाठी स्थानिक कृषी विज्ञान केंद्राशी संपर्क साधा."

    elif lang == "हिन्दी":
        script = f"किसान भाइयों, आपकी {crop} फसल के लिए सलाह सुनिए. "
        if problem:
            script += f"समस्या है: {problem}. "
        if solution_str:
            script += f"उपाय: {solution_str}. "
        if product:
            script += f"सुझाया गया उर्वरक या दवा: {product}. "
        if ingredients:
            script += f"बाजार से खरीदते समय पैकेट पर यह घटक अवश्य जांचें: {ingredients}. "
        if dosage:
            script += f"मात्रा: {dosage}. "
        if precautions:
            script += f"सावधानी: {precautions}. "
        script += "ज्यादा जानकारी के लिए नजदीकी कृषि विज्ञान केंद्र से संपर्क करें."

    else:
        script = f"Farmer advisory for {crop}. "
        if problem:
            script += f"Identified issue: {problem}. "
        if solution_str:
            script += f"Recommended actions: {solution_str}. "
        if product:
            script += f"Recommended product: {product}. "
        if ingredients:
            script += f"Check the packet for these active ingredients: {ingredients}. "
        if dosage:
            script += f"Dosage: {dosage}. "
        if precautions:
            script += f"Precaution: {precautions}. "
        script += "Consult your local Krishi Vigyan Kendra for specialized assistance."

    return clean_text_for_speech(script, lang)


def generate_audio_bytes(text: str, lang: str, slow: bool = False) -> Optional[bytes]:
    """
    Synthesize speech using gTTS and return audio bytes.
    Uses memory caching by text hash.
    """
    if not HAS_GTTS or not text:
        return None

    lang_code = LANG_CODE_MAP.get(lang, "en")
    cache_key = hashlib.md5(f"{text}_{lang_code}_{slow}".encode("utf-8")).hexdigest()

    if cache_key in _AUDIO_CACHE:
        return _AUDIO_CACHE[cache_key]

    try:
        tts = gTTS(text=text, lang=lang_code, slow=slow)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        audio_bytes = fp.read()
        _AUDIO_CACHE[cache_key] = audio_bytes
        return audio_bytes
    except Exception as e:
        # Network timeout or gTTS error
        return None


def render_voice_button(text_content: str, lang: str, key_prefix: str = "voice") -> None:
    """
    Renders a voice listening section with Play button, speed toggle, and browser fallback.
    """
    spoken_script = clean_text_for_speech(text_content, lang)
    if not spoken_script:
        return

    col1, col2 = st.columns([2, 1])
    with col2:
        speed_choice = st.checkbox(
            "🐢 हळू बोला / धीरे बोलें / Slow" if lang in ["मराठी", "हिन्दी"] else "🐢 Slow",
            key=f"{key_prefix}_slow_chk"
        )

    with col1:
        play_label = "🔊 सल्ला ऐका (Sunao)" if lang == "मराठी" else ("🔊 सलाह सुनें (Sunao)" if lang == "हिन्दी" else "🔊 Listen to Advice")
        if st.button(play_label, key=f"{key_prefix}_play_btn", use_container_width=True):
            with st.spinner("आवाज तयार होत आहे..." if lang == "मराठी" else ("आवाज तैयार हो रही है..." if lang == "हिन्दी" else "Generating speech...")):
                audio_bytes = generate_audio_bytes(spoken_script, lang, slow=speed_choice)

                if audio_bytes:
                    st.audio(audio_bytes, format="audio/mp3", autoplay=True)
                else:
                    # Browser Web Speech API fallback
                    st.info("🌐 इंटरनेट उपलब्ध नसल्याने ब्राऊझर व्हॉईस वापरत आहोत." if lang == "मराठी" else ("🌐 इंटरनेट न होने पर ब्राउज़र वॉइस का उपयोग हो रहा है." if lang == "हिन्दी" else "Playing via browser speech synthesis."))
                    js_lang = "mr-IN" if lang == "मराठी" else ("hi-IN" if lang == "हिन्दी" else "en-US")
                    escaped_text = spoken_script.replace('"', '\\"').replace("'", "\\'")
                    st.components.v1.html(
                        f"""
                        <script>
                            if ('speechSynthesis' in window) {{
                                var msg = new SpeechSynthesisUtterance("{escaped_text}");
                                msg.lang = "{js_lang}";
                                msg.rate = {0.8 if speed_choice else 1.0};
                                window.speechSynthesis.cancel();
                                window.speechSynthesis.speak(msg);
                            }} else {{
                                alert("Speech synthesis not supported in this browser.");
                            }}
                        </script>
                        """,
                        height=0
                    )
