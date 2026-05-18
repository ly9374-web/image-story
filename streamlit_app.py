import streamlit as st

from app.ui.theme import apply_dark_mode
from web.nav import back, goto, nav_init, nav_state
from web.pages.home import render as render_home
from web.pages.model_settings import render as render_model_settings
from web.pages.page2 import render as render_page2
from web.pages.records import render as render_records
from web.pages.settings import render as render_settings


PAGES = {
    "home": ("首页", render_home),
    "main": ("开始", render_page2),
    "settings": ("设置", render_settings),
    "records": ("记录", render_records),
    "modelSettings": ("模型", render_model_settings),
}


def _render_sidebar():
    st.sidebar.header("图像小说 Python")

    current = nav_state().page
    options = [key for key in PAGES.keys()]
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
    nav_init(default_page="home")

    _render_sidebar()

    page = nav_state().page
    _, render = PAGES.get(page, PAGES["home"])
    render()


if __name__ == "__main__":
    main()
