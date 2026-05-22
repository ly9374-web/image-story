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

/* ===== Chat (st.chat_message) ===== */
div[data-testid="stChatMessage"] {
  align-items: flex-start !important;
  gap: 14px !important;
  padding: 16px 18px !important;
  margin: 12px 0 !important;
  border-radius: 22px !important;
  background: rgba(10, 14, 20, 0.58) !important;
  border: 1px solid rgba(255, 255, 255, 0.10) !important;
}

/* Role glows (preferred: container-level using :has) */
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  box-shadow:
    0 0 0 1px rgba(139, 92, 246, 0.18),
    0 0 26px rgba(76, 29, 149, 0.35),
    0 12px 30px rgba(0, 0, 0, 0.55) !important;
}
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
  box-shadow:
    0 0 0 1px rgba(56, 189, 248, 0.16),
    0 0 26px rgba(56, 189, 248, 0.22),
    0 12px 30px rgba(0, 0, 0, 0.55) !important;
}

/* Fallback role glows (content-level, works without :has) */
[data-testid="stChatMessageAvatarUser"] + [data-testid="stChatMessageContent"] {
  border-radius: 18px !important;
  box-shadow: 0 0 22px rgba(76, 29, 149, 0.22) !important;
}
[data-testid="stChatMessageAvatarAssistant"] + [data-testid="stChatMessageContent"] {
  border-radius: 18px !important;
  box-shadow: 0 0 22px rgba(56, 189, 248, 0.18) !important;
}

/* Put user avatar on the right (match reference image) */
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  flex-direction: row-reverse !important;
}
/* Fallback ordering without :has */
[data-testid="stChatMessageAvatarUser"] {
  order: 2 !important;
}
[data-testid="stChatMessageAvatarUser"] + [data-testid="stChatMessageContent"] {
  order: 1 !important;
}

/* Avatar: use 2-color gradients (no concentric rings) */
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"] {
  width: 44px !important;
  height: 44px !important;
  border-radius: 999px !important;
  align-self: flex-start !important;
  margin-top: 2px !important;
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.10),
    0 8px 18px rgba(0, 0, 0, 0.55) !important;
}
[data-testid="stChatMessageAvatarUser"] {
  background: linear-gradient(135deg, #a855f7 0%, #0b0f14 85%) !important;
}
[data-testid="stChatMessageAvatarAssistant"] {
  background: linear-gradient(135deg, #ff4fd8 0%, #25b9ff 100%) !important;
}

/* Hide default icons so only the gradient orb remains */
[data-testid="stChatMessageAvatarUser"] svg,
[data-testid="stChatMessageAvatarAssistant"] svg {
  display: none !important;
}

/* ===== Page2 chat canvas (custom layout) ===== */
div[data-testid="stVerticalBlock"].st-key-page2_chat_canvas,
.st-key-page2_chat_canvas {
  /* Fixed canvas height; content overflow scrolls inside this container */
  --page2-chat-pad: 14px;
  --page2-chat-btn: 44px;
  --page2-chat-gap: 10px;
  /* Undo button positioning knobs (tweak these) */
  --page2-undo-gap-x: 4px;          /* space between undo and submit */
  --page2-undo-bottom-pad: 4px;     /* extra bottom offset inside canvas */
  --page2-undo-nudge-y: var(--page2-chat-btn); /* negative = move up, positive = move down */
  --page2-undo-nudge-x: 30px;       /* positive = move right */
  --page2-controls-pad-right: 18px; /* extra breathing room for text */
  /* Shorten canvas a bit so it doesn't feel "infinite" */
  height: calc(100dvh - 95px) !important;
  max-height: calc(100dvh - 95px) !important;
  min-height: calc(100dvh - 95px) !important;
  flex: 0 0 auto !important;
  display: flex !important;
  flex-direction: column !important;
  position: relative !important;
  border-radius: 26px !important;
  padding: 14px !important;
  background: rgba(10, 14, 20, 0.55) !important;
  border: 1px solid rgba(255, 255, 255, 0.10) !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    0 16px 40px rgba(0, 0, 0, 0.55) !important;
  overflow: auto !important;
  overscroll-behavior: contain !important;
}

.st-key-page2_chat_history {
  flex: 1 1 auto !important;
  overflow: visible !important;
  padding-right: 6px !important;
  /* Reserve space for the sticky input bar */
  padding-bottom: calc(var(--page2-chat-btn) + (var(--page2-chat-pad) * 2)) !important;
}

/* Subtle, consistent scrollbars (webkit) */
.st-key-page2_chat_canvas::-webkit-scrollbar {
  width: 10px;
}
.st-key-page2_chat_canvas::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  border: 2px solid rgba(0, 0, 0, 0);
  background-clip: padding-box;
}
.st-key-page2_chat_canvas::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.26);
  border: 2px solid rgba(0, 0, 0, 0);
  background-clip: padding-box;
}

/* Make chat input look like a bottom bar inside canvas */
.st-key-page2_chat_input {
  flex: 0 0 auto !important;
  position: sticky !important;
  bottom: 0 !important;
  z-index: 5 !important;
}
.st-key-page2_chat_input div[data-testid="stChatInput"] {
  border-radius: 18px !important;
  background: rgba(10, 14, 20, 0.72) !important;
  border: 1px solid rgba(255, 255, 255, 0.10) !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 10px 24px rgba(0, 0, 0, 0.50) !important;
}
.st-key-page2_chat_input div[data-testid="stChatInput"] textarea,
.st-key-page2_chat_input div[data-testid="stChatInput"] [contenteditable="true"] {
  /* Reserve right-side space for submit button only */
  padding-right: calc(var(--page2-chat-btn) + var(--page2-controls-pad-right)) !important;
}

/* Normalize submit button size so undo can match it */
.st-key-page2_chat_canvas [data-testid="stChatInputSubmitButton"] {
  width: var(--page2-chat-btn) !important;
  height: var(--page2-chat-btn) !important;
  min-width: var(--page2-chat-btn) !important;
  border-radius: 14px !important;
}

/* Undo button: visually dock to the left of the submit button */
.st-key-page2_chat_undo_btn {
  margin-top: 10px !important;
  margin-bottom: 0 !important;
}
.st-key-page2_chat_undo_btn button {
  width: 100% !important; /* match inputbar width */
  min-width: 100% !important;
  border-radius: 14px !important;
  background: rgba(220, 38, 38, 0.30) !important; /* red */
  border: 1px solid rgba(248, 113, 113, 0.55) !important;
  box-shadow: 0 10px 20px rgba(0, 0, 0, 0.45) !important;
  padding: 0 !important;
}
.st-key-page2_chat_undo_btn button:hover {
  background: rgba(220, 38, 38, 0.42) !important;
  border-color: rgba(252, 165, 165, 0.85) !important;
}
.st-key-page2_chat_undo_btn button:disabled {
  opacity: 0.45 !important;
}
/* Keep undo button visible even if icon/text structure changes across Streamlit versions */
.st-key-page2_chat_undo_btn button > div > p {
  margin: 0 !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )
