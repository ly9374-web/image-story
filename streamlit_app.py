import time

import streamlit as st

from app.ui.theme import apply_agent_mode_style, apply_agent_transition_animation, apply_dark_mode
from web.nav import back, goto, nav_init, nav_state
from web.pages.agent_chat import (
    prepare_from_navigation as prepare_agent_chat_from_navigation,
    render as render_agent_chat,
    render_sidebar_context as render_agent_sidebar_context,
)
from web.pages.agent_settings import render as render_agent_settings
from web.pages.home import render as render_home
from web.pages.model_settings import render as render_model_settings
from web.pages.page2 import render as render_page2, render_sidebar_context as render_page2_sidebar_context
from web.pages.records import render as render_records
from web.pages.settings import render as render_settings
from web.pages.signin_page import render as render_signin


PAGES = {
    "signin": ("登录", render_signin),
    "home": ("首页", render_home),
    "main": ("开始", render_page2),
    "settings": ("设置", render_settings),
    "agentMain": ("Agent", render_agent_chat),
    "agentSettings": ("Agent Prompt", render_agent_settings),
    "records": ("记录", render_records),
    "modelSettings": ("APIkey", render_model_settings),
}

_GUEST_COUNTDOWN_CSS = """
<style>
.ly-guest-countdown {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 10px;
  z-index: 9999;
  display: flex;
  justify-content: center;
  pointer-events: none;
}
.ly-guest-countdown > div {
  pointer-events: none;
  padding: 8px 14px;
  border-radius: 999px;
  background: rgba(17, 24, 39, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.10);
  color: #e5e7eb;
  font-size: 14px;
}
</style>
"""


@st.fragment(run_every=1)
def _render_guest_countdown():
    expires_at = float(st.session_state.get("guest_expires_at") or 0.0)
    remaining = int(expires_at - time.time())
    if remaining <= 0:
        st.session_state.auth_ok = False
        st.session_state.auth_mode = ""
        st.session_state.user_id = ""
        st.session_state.pop("guest_expires_at", None)
        st.warning("游客试用已结束，请重新登录。")
        goto("signin", push_history=False)
        st.rerun()

    mm = remaining // 60
    ss = remaining % 60
    clock = f"{mm:02d}:{ss:02d}"

    st.markdown(_GUEST_COUNTDOWN_CSS, unsafe_allow_html=True)
    st.markdown(
        f'<div class="ly-guest-countdown"><div>此次游客试用还剩 {clock}</div></div>',
        unsafe_allow_html=True,
    )


def _render_sidebar():
    current = nav_state().page
    agent_mode = bool(st.session_state.get("agent_mode", False))
    st.sidebar.header("图像小说 · Agent" if agent_mode else "图像小说")
    can_go_back = current == "home" or bool(nav_state().history)
    if st.sidebar.button("返回", use_container_width=True, disabled=not can_go_back):
        if current == "home":
            st.session_state.auth_ok = False
            st.session_state.auth_mode = ""
            st.session_state.user_id = ""
            st.session_state.pop("guest_expires_at", None)
            st.session_state.nav_history = []
            goto("signin", push_history=False)
        else:
            back()

    agent_label = "退出 agent" if agent_mode else "agent"
    if st.sidebar.button(agent_label, use_container_width=True, type="primary" if agent_mode else "secondary"):
        st.session_state.agent_transition_token = str(int(time.time() * 1000))
        if agent_mode:
            st.session_state.agent_transition_direction = "out"
            previous = st.session_state.get("agent_previous_page")
            previous_kwargs = dict(st.session_state.get("agent_previous_page_kwargs") or {})
            st.session_state.agent_mode = False
            st.session_state.pop("agent_previous_page", None)
            st.session_state.pop("agent_previous_page_kwargs", None)
            if current in {"agentMain", "agentSettings"}:
                if isinstance(previous, str) and previous:
                    goto(
                        previous,
                        push_history=False,
                        **previous_kwargs,
                    )
                else:
                    goto("home", push_history=False)
            st.rerun()
        else:
            st.session_state.agent_transition_direction = "in"
            st.session_state.agent_previous_page = current
            st.session_state.agent_previous_page_kwargs = dict(st.session_state.get("nav_page_kwargs") or {})
            st.session_state.agent_mode = True
            goto("home", push_history=False)

    if current == "main":
        render_page2_sidebar_context()
    if current == "agentMain":
        render_agent_sidebar_context()


def main():
    st.set_page_config(page_title="图像小说", layout="wide")
    apply_dark_mode()
    nav_init(default_page="signin")
    st.session_state.setdefault("agent_mode", False)

    if "auth_ok" not in st.session_state:
        st.session_state.auth_ok = False
    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = ""
    if "user_id" not in st.session_state:
        st.session_state.user_id = ""
    if bool(st.session_state.auth_ok) and not str(st.session_state.auth_mode or "").strip():
        st.session_state.auth_mode = "user"
        st.session_state.user_id = st.session_state.user_id or "1"

    if nav_state().page != "signin" and not bool(st.session_state.auth_ok):
        goto("signin", push_history=False)

    # Guest 10-minute countdown (fragment refresh every second, not full-page rerun)
    if (
        bool(st.session_state.auth_ok)
        and str(st.session_state.auth_mode or "").strip().lower() == "guest"
        and nav_state().page != "signin"
    ):
        _render_guest_countdown()

    if nav_state().page == "modelSettings" and str(st.session_state.auth_mode or "").strip().lower() == "guest":
        st.warning("游客模式无法访问「APIkey」。")
        goto("home", push_history=False)

    apply_agent_mode_style(
        bool(st.session_state.get("agent_mode", False)) and nav_state().page != "signin"
    )
    transition_token = str(st.session_state.get("agent_transition_token", "") or "")
    transition_direction = str(st.session_state.get("agent_transition_direction", "in") or "in")
    consumed_token = str(st.session_state.get("agent_transition_consumed_token", "") or "")
    consumed_direction = str(st.session_state.get("agent_transition_consumed_direction", "") or "")
    if (
        transition_token
        and (transition_token != consumed_token or transition_direction != consumed_direction)
        and nav_state().page != "signin"
    ):
        apply_agent_transition_animation(transition_token, transition_direction)
        st.session_state.agent_transition_consumed_token = transition_token
        st.session_state.agent_transition_consumed_direction = transition_direction

    page = nav_state().page
    if page == "agentMain":
        prepare_agent_chat_from_navigation()

    if page != "signin":
        _render_sidebar()

    _, render = PAGES.get(page, PAGES["home"])
    render()


if __name__ == "__main__":
    main()
