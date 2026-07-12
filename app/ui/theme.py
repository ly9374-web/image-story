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

/* ===== Agent chat canvas ===== */
div[data-testid="stVerticalBlock"].st-key-agent_chat_canvas,
.st-key-agent_chat_canvas {
  --agent-chat-btn: 44px;
  --agent-controls-pad-right: 18px;
  height: calc(100dvh - 132px) !important;
  max-height: calc(100dvh - 132px) !important;
  min-height: calc(100dvh - 132px) !important;
  display: flex !important;
  flex-direction: column !important;
  position: relative !important;
  border-radius: 24px !important;
  padding: 14px !important;
  background: rgba(7, 16, 24, 0.58) !important;
  border: 1px solid rgba(96, 165, 250, 0.14) !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 16px 42px rgba(0, 0, 0, 0.50) !important;
  overflow: auto !important;
  overscroll-behavior: contain !important;
}

.st-key-agent_chat_history {
  flex: 1 1 auto !important;
  overflow: visible !important;
  padding-right: 6px !important;
  padding-bottom: calc(var(--agent-chat-btn) + 28px) !important;
}

.st-key-agent_chat_canvas::-webkit-scrollbar {
  width: 10px;
}
.st-key-agent_chat_canvas::-webkit-scrollbar-thumb {
  background: rgba(96, 165, 250, 0.18);
  border-radius: 999px;
  border: 2px solid rgba(0, 0, 0, 0);
  background-clip: padding-box;
}
.st-key-agent_chat_input {
  flex: 0 0 auto !important;
  position: sticky !important;
  bottom: 0 !important;
  z-index: 5 !important;
}
.st-key-agent_chat_input div[data-testid="stChatInput"] {
  border-radius: 18px !important;
  background: rgba(10, 21, 32, 0.80) !important;
  border: 1px solid rgba(96, 165, 250, 0.16) !important;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.48) !important;
}
.st-key-agent_chat_input div[data-testid="stChatInput"] textarea,
.st-key-agent_chat_input div[data-testid="stChatInput"] [contenteditable="true"] {
  padding-right: calc(var(--agent-chat-btn) + var(--agent-controls-pad-right)) !important;
}
.st-key-agent_chat_canvas [data-testid="stChatInputSubmitButton"] {
  width: var(--agent-chat-btn) !important;
  height: var(--agent-chat-btn) !important;
  min-width: var(--agent-chat-btn) !important;
  border-radius: 14px !important;
}

.agent-event {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin: 12px 0;
}

.agent-event-player {
  flex-direction: row-reverse;
}

.agent-event-avatar {
  width: 44px;
  height: 44px;
  flex: 0 0 44px;
  border-radius: 999px;
  margin-top: 2px;
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.10),
    0 8px 18px rgba(0, 0, 0, 0.55);
}

.agent-event-bubble {
  max-width: min(78%, 760px);
  padding: 14px 16px;
  border-radius: 20px;
  background: rgba(10, 14, 20, 0.58);
  border: 1px solid rgba(255, 255, 255, 0.10);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.45);
}

.agent-event-player .agent-event-bubble {
  box-shadow:
    0 0 0 1px rgba(139, 92, 246, 0.18),
    0 0 26px rgba(76, 29, 149, 0.35),
    0 12px 30px rgba(0, 0, 0, 0.55);
}

.agent-event-label {
  margin-bottom: 8px;
  color: #f8fafc;
  font-weight: 700;
  font-size: 0.92rem;
}

.agent-event-content {
  color: #e5e7eb;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.agent-event-player .agent-event-avatar {
  background: linear-gradient(135deg, #a855f7 0%, #0b0f14 85%);
}

.agent-event-npc1 .agent-event-avatar,
.agent-event-assistant .agent-event-avatar {
  background: linear-gradient(135deg, #ff4fd8 0%, #25b9ff 100%);
}

.agent-event-npc2 .agent-event-avatar {
  background: linear-gradient(135deg, #22c55e 0%, #14b8a6 100%);
}

.agent-event-npc3 .agent-event-avatar {
  background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%);
}

.agent-event-scene .agent-event-avatar {
  background: linear-gradient(135deg, #94a3b8 0%, #334155 100%);
}

.agent-event-judgement .agent-event-avatar {
  background: linear-gradient(135deg, #818cf8 0%, #4f46e5 100%);
}

.agent-event-error .agent-event-avatar,
.agent-event-system .agent-event-avatar {
  background: linear-gradient(135deg, #f87171 0%, #991b1b 100%);
}
</style>
        """,
        unsafe_allow_html=True,
    )


def apply_agent_mode_style(enabled: bool) -> None:
    if not enabled:
        return

    st.markdown(
        """
<style>
/* ===== Agent mode shell ===== */
:root {
  --agent-bg-0: #071015;
  --agent-bg-1: #081823;
  --agent-bg-2: #0d2030;
  --agent-panel: rgba(10, 21, 29, 0.86);
  --agent-surface: rgba(17, 32, 42, 0.78);
  --agent-surface-strong: rgba(12, 48, 78, 0.70);
  --agent-border: rgba(125, 184, 255, 0.18);
  --agent-accent: #38a3ff;
  --agent-accent-2: #7dd3fc;
  --agent-accent-soft: rgba(56, 163, 255, 0.18);
  --agent-text: #edf7ff;
  --agent-muted: rgba(237, 247, 255, 0.68);
}

html,
body,
.stApp,
section[data-testid="stMain"] {
  background:
    radial-gradient(circle at 22% 8%, rgba(14, 116, 144, 0.20), transparent 34%),
    radial-gradient(circle at 84% 24%, rgba(37, 99, 235, 0.18), transparent 32%),
    linear-gradient(145deg, var(--agent-bg-0) 0%, var(--agent-bg-1) 48%, var(--agent-bg-2) 100%) !important;
  color: var(--agent-text) !important;
  transition:
    background 420ms ease,
    color 240ms ease,
    border-color 240ms ease,
    box-shadow 240ms ease !important;
}

[data-testid="stSidebar"] > div {
  background:
    linear-gradient(180deg, rgba(9, 22, 31, 0.97), rgba(6, 14, 19, 0.99)) !important;
  border-right: 1px solid var(--agent-border) !important;
  transition: background 420ms ease, border-color 240ms ease !important;
}

[data-testid="stSidebar"] * {
  color: var(--agent-text) !important;
}

.stButton > button:not([kind="primary"]) {
  background: var(--agent-surface) !important;
  border-color: var(--agent-border) !important;
  color: var(--agent-text) !important;
  transition:
    background 180ms ease,
    border-color 180ms ease,
    box-shadow 180ms ease,
    transform 180ms ease !important;
}

.stButton > button:not([kind="primary"]):hover {
  border-color: rgba(125, 211, 252, 0.48) !important;
  box-shadow: 0 0 24px rgba(56, 163, 255, 0.22) !important;
}

.stButton > button[kind="primary"],
.st-key-agent_chat_canvas [data-testid="stChatInputSubmitButton"] {
  background: linear-gradient(180deg, #1d9bff 0%, #0b72d0 100%) !important;
  border-color: rgba(125, 211, 252, 0.58) !important;
  color: #f7fbff !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.20),
    0 12px 28px rgba(14, 116, 220, 0.30) !important;
}

.stButton > button[kind="primary"]:hover,
.st-key-agent_chat_canvas [data-testid="stChatInputSubmitButton"]:hover {
  background: linear-gradient(180deg, #38a3ff 0%, #0b86eb 100%) !important;
  border-color: rgba(186, 230, 253, 0.78) !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.26),
    0 0 28px rgba(56, 163, 255, 0.34) !important;
}

.stTextInput input,
.stTextArea textarea,
.stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div,
.stNumberInput input {
  background: var(--agent-panel) !important;
  border-color: var(--agent-border) !important;
  color: var(--agent-text) !important;
}

.stSlider [data-baseweb="slider"] > div {
  background-color: rgba(125, 184, 255, 0.20) !important;
}

.stSlider [role="slider"] {
  background: var(--agent-accent) !important;
  box-shadow: 0 0 18px rgba(56, 163, 255, 0.30) !important;
}

.stSelectbox div[data-baseweb="popover"],
.stMultiSelect div[data-baseweb="popover"] {
  background: var(--agent-panel) !important;
  border: 1px solid var(--agent-border) !important;
}

.stSelectbox [role="option"],
.stMultiSelect [role="option"] {
  color: var(--agent-text) !important;
}

.stSelectbox [role="option"]:hover,
.stMultiSelect [role="option"]:hover {
  background: var(--agent-accent-soft) !important;
}

.stCaption,
[data-testid="stCaptionContainer"] {
  color: var(--agent-muted) !important;
}

a,
a:visited,
[data-testid="stMarkdownContainer"] a {
  color: var(--agent-accent-2) !important;
}

[data-testid="stDivider"] hr,
hr {
  border-color: rgba(125, 184, 255, 0.15) !important;
}

[data-testid="stAlert"],
[data-testid="stExpander"],
details {
  background: var(--agent-panel) !important;
  border-color: var(--agent-border) !important;
  color: var(--agent-text) !important;
}

div[data-testid="stChatMessage"] {
  background: rgba(8, 18, 25, 0.72) !important;
  border-color: rgba(125, 184, 255, 0.14) !important;
}

div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  box-shadow:
    0 0 0 1px rgba(56, 163, 255, 0.18),
    0 0 26px rgba(37, 99, 235, 0.26),
    0 12px 30px rgba(0, 0, 0, 0.55) !important;
}

div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
  box-shadow:
    0 0 0 1px rgba(125, 211, 252, 0.16),
    0 0 26px rgba(56, 163, 255, 0.20),
    0 12px 30px rgba(0, 0, 0, 0.55) !important;
}

[data-testid="stChatMessageAvatarUser"] {
  background: linear-gradient(135deg, #38a3ff 0%, #071015 88%) !important;
}

[data-testid="stChatMessageAvatarAssistant"] {
  background: linear-gradient(135deg, #7dd3fc 0%, #2563eb 100%) !important;
}

.st-key-agent_chat_canvas {
  background: rgba(7, 16, 22, 0.62) !important;
  border-color: rgba(125, 184, 255, 0.16) !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 16px 42px rgba(0, 0, 0, 0.50),
    0 0 36px rgba(37, 99, 235, 0.08) !important;
}

.st-key-agent_chat_canvas::-webkit-scrollbar-thumb {
  background: rgba(125, 184, 255, 0.20);
}

.st-key-agent_chat_canvas::-webkit-scrollbar-thumb:hover {
  background: rgba(125, 184, 255, 0.30);
}

.st-key-agent_chat_input div[data-testid="stChatInput"] {
  background: var(--agent-panel) !important;
  border-color: rgba(125, 184, 255, 0.18) !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 10px 24px rgba(0, 0, 0, 0.48) !important;
}

.st-key-agent_chat_input div[data-testid="stChatInput"]:focus-within {
  border-color: rgba(125, 211, 252, 0.58) !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    0 0 28px rgba(56, 163, 255, 0.20),
    0 10px 24px rgba(0, 0, 0, 0.48) !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def apply_agent_transition_animation(token: str) -> None:
    token = str(token or "").strip()
    if not token:
        return

    st.markdown(
        f"""
<style>
@keyframes agent-blue-wash-{token} {{
  0% {{
    opacity: 0;
    backdrop-filter: saturate(1.0);
  }}
  18% {{
    opacity: 0.86;
    backdrop-filter: saturate(1.35);
  }}
  62% {{
    opacity: 0.58;
    backdrop-filter: saturate(1.22);
  }}
  100% {{
    opacity: 0;
    backdrop-filter: saturate(1.0);
  }}
}}

.agent-transition-overlay-{token} {{
  position: fixed;
  inset: 0;
  z-index: 1000002;
  pointer-events: none;
  background:
    radial-gradient(circle at 18% 22%, rgba(56, 189, 248, 0.95), transparent 34%),
    radial-gradient(circle at 72% 18%, rgba(37, 99, 235, 0.78), transparent 38%),
    radial-gradient(circle at 50% 76%, rgba(14, 165, 233, 0.58), transparent 42%),
    linear-gradient(135deg, rgba(5, 14, 28, 0.90), rgba(8, 47, 73, 0.88));
  animation: agent-blue-wash-{token} 1.2s ease-in-out forwards;
}}
</style>
<div class="agent-transition-overlay-{token}"></div>
        """,
        unsafe_allow_html=True,
    )
