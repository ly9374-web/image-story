import streamlit as st
import time

from app.ui.theme import apply_dark_mode
from web.nav import back, goto, nav_init, nav_state
from web.pages.home import render as render_home
from web.pages.model_settings import render as render_model_settings
from web.pages.page2 import render as render_page2
from web.pages.records import render as render_records
from web.pages.settings import render as render_settings
from web.pages.signin_page import render as render_signin


PAGES = {
    "signin": ("登录", render_signin),
    "home": ("首页", render_home),
    "main": ("开始", render_page2),
    "settings": ("设置", render_settings),
    "records": ("记录", render_records),
    "modelSettings": ("模型", render_model_settings),
}


def _render_sidebar():
    st.sidebar.header("图像小说 Python")

    current = nav_state().page
    mode = str(st.session_state.get("auth_mode", "") or "").strip().lower()
    options = [key for key in PAGES.keys() if key != "signin"]
    if mode == "guest" and "modelSettings" in options:
        options = [k for k in options if k != "modelSettings"]
    labels = {key: PAGES[key][0] for key in options}

    selected = st.sidebar.radio(
        "导航",
        options=options,
        format_func=lambda k: labels.get(k, k),
        index=options.index(current) if current in options else 0,
    )
    if selected != current:
        goto(selected)

    st.sidebar.divider()

    if st.sidebar.button("返回", use_container_width=True, disabled=not nav_state().history):
        back()


def main():
    st.set_page_config(page_title="图像小说 Python", layout="wide")
    apply_dark_mode()
    nav_init(default_page="signin")

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

    # Guest 10-minute countdown (auto-refresh every second)
    if (
        bool(st.session_state.auth_ok)
        and str(st.session_state.auth_mode or "").strip().lower() == "guest"
        and nav_state().page != "signin"
    ):
        expires_at = float(st.session_state.get("guest_expires_at") or 0.0)
        remaining = int(expires_at - time.time())
        if remaining <= 0:
            st.session_state.auth_ok = False
            st.session_state.auth_mode = ""
            st.session_state.user_id = ""
            st.session_state.pop("guest_expires_at", None)
            st.warning("游客试用已结束，请重新登录。")
            goto("signin", push_history=False)

        mm = max(0, remaining) // 60
        ss = max(0, remaining) % 60
        clock = f"{mm:02d}:{ss:02d}"

        try:
            from streamlit import st_autorefresh  # type: ignore

            st_autorefresh(interval=1000, key="guest_countdown_refresh")
        except Exception:
            pass

        st.markdown(
            """
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
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="ly-guest-countdown"><div>此次游客试用还剩 {clock}</div></div>',
            unsafe_allow_html=True,
        )

    if nav_state().page == "modelSettings" and str(st.session_state.auth_mode or "").strip().lower() == "guest":
        st.warning("游客模式无法访问「模型」。")
        goto("home", push_history=False)

    if nav_state().page != "signin":
        _render_sidebar()

    page = nav_state().page
    _, render = PAGES.get(page, PAGES["home"])
    render()


if __name__ == "__main__":
    main()
