from __future__ import annotations

import streamlit as st


def apply_dark_mode() -> None:
    """
    Force a consistent dark theme across the whole app.
    Streamlit's theme config covers most widgets; this CSS patch handles the rest
    (sidebar, separators, some widget surfaces, and general typography contrast).
    """
    st.markdown(
        """
<style>
/* ===== Night mode (global) ===== */
:root {
  --nm-bg: #0b0f14;
  --nm-panel: #111827;
  --nm-surface: #1f2937;
  --nm-surface-2: #2a2f3a;
  --nm-border: rgba(255, 255, 255, 0.12);
  --nm-text: #e5e7eb;
  --nm-text-2: #9ca3af;
  --nm-text-3: rgba(229, 231, 235, 0.72);
}

html, body {
  background: var(--nm-bg) !important;
  color: var(--nm-text) !important;
}

/* App background */
.stApp {
  background: var(--nm-bg) !important;
  color: var(--nm-text) !important;
}

/* Sidebar */
[data-testid="stSidebar"] > div {
  background: var(--nm-panel) !important;
}
[data-testid="stSidebar"] * {
  color: var(--nm-text) !important;
}

/* Headers / captions */
.stMarkdown, .stCaption, .st-emotion-cache-1c7y2kd, .st-emotion-cache-16idsys {
  color: var(--nm-text) !important;
}
.stCaption, [data-testid="stCaptionContainer"] {
  color: var(--nm-text-2) !important;
}

/* Dividers */
[data-testid="stDivider"] hr, hr {
  border-color: var(--nm-border) !important;
}

/* Inputs (text/textarea/select) */
.stTextInput input,
.stTextArea textarea,
.stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div {
  background: var(--nm-surface) !important;
  color: var(--nm-text) !important;
  border-color: var(--nm-border) !important;
}

/* Placeholders */
.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
  color: var(--nm-text-3) !important;
}

/* Labels */
label, .stTextInput label, .stTextArea label, .stSelectbox label, .stRadio label {
  color: var(--nm-text) !important;
}

/* Radio/checkbox text */
[data-testid="stRadio"] * , [data-testid="stCheckbox"] * {
  color: var(--nm-text) !important;
}

/* Buttons */
.stButton > button {
  border-color: var(--nm-border) !important;
}
.stButton > button:not([kind="primary"]) {
  background: var(--nm-surface) !important;
  color: var(--nm-text) !important;
}

/* Info/warn/error/success blocks */
[data-testid="stAlert"] {
  background: rgba(31, 41, 55, 0.85) !important;
  border: 1px solid var(--nm-border) !important;
  color: var(--nm-text) !important;
}

/* Tables/dataframes surfaces */
[data-testid="stDataFrame"], [data-testid="stTable"] {
  background: var(--nm-surface) !important;
  border: 1px solid var(--nm-border) !important;
}

/* Make code blocks readable */
pre, code {
  background: rgba(31, 41, 55, 0.65) !important;
  color: var(--nm-text) !important;
  border-color: var(--nm-border) !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )

