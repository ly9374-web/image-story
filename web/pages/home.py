import streamlit as st

from web.nav import goto


def render():
    st.title("首页")
    st.caption("选择一个功能进入。")

    mode = str(st.session_state.get("auth_mode", "") or "").strip().lower()
    agent_mode = bool(st.session_state.get("agent_mode", False))

    col1, col2 = st.columns(2)
    with col1:
        if st.button("开始", use_container_width=True):
            goto("agentMain" if agent_mode else "main")
        if st.button("prompt", use_container_width=True):
            goto("agentSettings" if agent_mode else "settings")
    with col2:
        if st.button("记录", use_container_width=True):
            goto("records")
        if mode != "guest":
            if st.button("APIkey", use_container_width=True):
                goto("modelSettings")
