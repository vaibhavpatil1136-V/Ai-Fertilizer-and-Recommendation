# ui_components.py -- Mobile-first UI layouts, custom CSS, top navigation bar and cards
"""
Provides responsive, high-contrast, mobile-first styling and header components.
Completely removes left sidebar and provides front-page card navigation for rural farmers.
"""

import streamlit as st
from auth import authenticate_user, register_user

CUSTOM_CSS = """
<style>
/* 1. Hide default Streamlit sidebar, menu, deploy button, footer */
[data-testid="stSidebar"], [data-testid="collapsedControl"] {
    display: none !important;
}
#MainMenu, footer, header, [data-testid="stToolbar"] {
    display: none !important;
}
.block-container {
    padding-top: 1rem !important;
    padding-bottom: 3rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    max-width: 900px !important;
}

/* 2. Global Typography & Mobile-first Sizing */
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 18px !important;
    color: #1a2e1a;
    background-color: #f8faf8;
}

/* 3. Big High-Contrast Touch Targets (Min 56px) */
.stButton > button {
    min-height: 56px !important;
    font-size: 1.15rem !important;
    font-weight: 700 !important;
    border-radius: 12px !important;
    background-color: #2e7d32 !important;
    color: #ffffff !important;
    border: none !important;
    width: 100% !important;
    box-shadow: 0 4px 8px rgba(46, 125, 50, 0.2) !important;
    transition: all 0.2s ease !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 12px 18px !important;
}
.stButton > button:hover {
    background-color: #1b5e20 !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 12px rgba(27, 94, 32, 0.3) !important;
}
.stButton > button:active {
    transform: translateY(1px) !important;
}

/* 4. Form inputs touch styling */
.stSelectbox, .stTextInput, .stSlider {
    font-size: 1.1rem !important;
    margin-bottom: 12px !important;
}
input[type="text"], input[type="password"] {
    min-height: 50px !important;
    font-size: 1.1rem !important;
    border-radius: 8px !important;
    border: 1.5px solid #a5d6a7 !important;
}

/* 5. Navigation & Action Cards */
.nav-card {
    background: #ffffff;
    border: 2px solid #c8e6c9;
    border-radius: 16px;
    padding: 20px 14px;
    text-align: center;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
    transition: all 0.2s ease;
    cursor: pointer;
    min-height: 140px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
}
.nav-card:hover {
    border-color: #2e7d32;
    background-color: #f1f8e9;
    transform: translateY(-3px);
}
.nav-icon {
    font-size: 2.5rem;
    margin-bottom: 8px;
}
.nav-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #1b5e20;
    line-height: 1.3;
}
.nav-sub {
    font-size: 0.85rem;
    color: #555555;
    margin-top: 4px;
}

/* 6. Top Bar */
.top-bar-container {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 4px 14px 4px;
    border-bottom: 2px solid #e0e0e0;
    margin-bottom: 16px;
}
.top-logo {
    font-size: 1.6rem;
    font-weight: 800;
    color: #2e7d32;
    text-decoration: none;
    letter-spacing: -0.5px;
}
.back-btn {
    display: inline-flex;
    align-items: center;
    background-color: #e8f5e9 !important;
    color: #2e7d32 !important;
    font-weight: 700 !important;
    padding: 6px 14px !important;
    border-radius: 8px !important;
    border: 1px solid #c8e6c9 !important;
    cursor: pointer;
    margin-bottom: 16px;
    min-height: 44px !important;
}

/* 7. Advisory Box */
.farmer-card {
    background-color: #ffffff;
    border: 2px solid #81c784;
    border-left: 8px solid #2e7d32;
    border-radius: 14px;
    padding: 20px;
    margin: 16px 0;
    box-shadow: 0 4px 12px rgba(46,125,50,0.1);
}
.farmer-card h3 {
    color: #1b5e20;
    margin-top: 0;
    font-size: 1.4rem;
}
</style>
"""


def apply_custom_css():
    """Inject high-contrast mobile CSS into Streamlit page."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_top_bar():
    """
    Renders top bar on every screen:
    Left: AgriCare Logo
    Right: Language Selector + small Login/Register corner popover.
    """
    col_logo, col_lang, col_auth = st.columns([1.8, 1.4, 1.3])

    with col_logo:
        # Clicking logo returns home
        if st.button("🌱 AgriCare", key="btn_logo_home", use_container_width=False):
            st.session_state["page"] = "home"
            st.rerun()

    with col_lang:
        lang_options = ["मराठी", "हिन्दी", "English"]
        curr_idx = lang_options.index(st.session_state.get("lang", "मराठी")) if st.session_state.get("lang") in lang_options else 0
        selected_lang = st.selectbox(
            "🌐 भाषा",
            options=lang_options,
            index=curr_idx,
            label_visibility="collapsed",
            key="global_lang_select"
        )
        if selected_lang != st.session_state.get("lang"):
            st.session_state["lang"] = selected_lang
            st.rerun()

    with col_auth:
        lang = st.session_state.get("lang", "मराठी")
        is_logged = st.session_state.get("logged_in", False)
        username = st.session_state.get("username", "")

        if is_logged:
            # Show username and logout in corner popover
            with st.popover(f"👤 {username[:8]}"):
                st.write(f"**{username}** (लॉगिन आहे)")
                if st.button("लॉगआउट (Logout)", key="top_logout_btn"):
                    st.session_state["logged_in"] = False
                    st.session_state["username"] = ""
                    st.rerun()
        else:
            # Small login/register popover
            btn_title = "लॉगिन" if lang == "मराठी" else ("लॉगिन" if lang == "हिन्दी" else "Login")
            with st.popover(f"🔑 {btn_title}"):
                auth_tab1, auth_tab2 = st.tabs(["लॉगिन (Login)", "नोंदणी (Register)"])

                with auth_tab1:
                    u_in = st.text_input("वापरकर्ता / फोन (User/Phone)", key="pop_login_user")
                    p_in = st.text_input("पासवर्ड (Password)", type="password", key="pop_login_pass")
                    if st.button("लॉगिन करा (Login)", key="pop_submit_login"):
                        if authenticate_user(u_in, p_in):
                            st.session_state["logged_in"] = True
                            st.session_state["username"] = u_in.strip()
                            st.success("लॉगिन यशस्वी!")
                            st.rerun()
                        else:
                            st.error("चुकीचा पासवर्ड किंवा नाव.")

                with auth_tab2:
                    reg_u = st.text_input("नवीन नाव / फोन", key="pop_reg_user")
                    reg_p = st.text_input("नवीन पासवर्ड", type="password", key="pop_reg_pass")
                    reg_phone = st.text_input("मोबाईल नंबर (ऐच्छिक)", key="pop_reg_phone")
                    if st.button("नवीन खाते तयार करा", key="pop_submit_reg"):
                        ok, msg = register_user(reg_u, reg_p, reg_phone)
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)

    st.markdown("<hr style='margin: 8px 0 16px 0; border: none; border-top: 1.5px solid #c8e6c9;'>", unsafe_allow_html=True)


def render_back_button(target_page: str = "home"):
    """Render a prominent '← Back / Home' button on inner pages."""
    lang = st.session_state.get("lang", "मराठी")
    label = "← मागे जा (Home)" if lang == "मराठी" else ("← वापस जाएं (Home)" if lang == "हिन्दी" else "← Back to Home")
    if st.button(label, key="btn_nav_back", use_container_width=False):
        st.session_state["page"] = target_page
        st.rerun()
