import streamlit as st

from app.config import AppStorageKeys, settings
from web.nav import back


FIELDS = [
    (
        "输入 Grok 聊天 API Key（会本地持久化保存）",
        AppStorageKeys.XAI_CHAT_API_KEY,
        "XAI_CHAT_API_KEY",
    ),
    (
        "输入 Grok 生图 API Key（会本地持久化保存）",
        AppStorageKeys.XAI_IMAGE_API_KEY,
        "XAI_IMAGE_API_KEY",
    ),
    (
        "输入 Replicate API Token（会本地持久化保存）",
        AppStorageKeys.REPLICATE_API_TOKEN,
        "REPLICATE_API_TOKEN",
    ),
    (
        "输入 DeepSeek API Key（会本地持久化保存）",
        AppStorageKeys.DEEPSEEK_API_KEY,
        "DEEPSEEK_API_KEY",
    ),
    (
        "输入 DomoAI API Key（会本地持久化保存）",
        AppStorageKeys.DOMOAI_API_KEY,
        "DOMOAI_API_KEY",
    ),
    (
        "输入 智谱 API Key（会本地持久化保存）",
        AppStorageKeys.ZHIPU_API_KEY,
        "ZHIPU_API_KEY",
    ),
]


def render():
    st.title("模型")

    with st.form("model_settings_form", border=True):
        values = {}
        for label_text, key, placeholder in FIELDS:
            values[key] = st.text_input(
                label_text,
                value=str(settings.get(key, "") or ""),
                placeholder=placeholder,
                type="password",
            )

        debug_enabled = st.checkbox(
            "打印调试日志",
            value=settings.bool(AppStorageKeys.DEBUG_LOG_ENABLED, False),
            help="关闭后不会在控制台打印请求体、响应体和调试信息，可减少卡顿。",
        )

        c1, c2 = st.columns(2)
        with c1:
            cancel = st.form_submit_button("取消", use_container_width=True)
        with c2:
            save = st.form_submit_button("确定", use_container_width=True, type="primary")

    if cancel:
        back()
        return

    if save:
        for _label_text, key, _placeholder in FIELDS:
            settings.set(key, str(values.get(key, "") or "").strip())
        settings.set(AppStorageKeys.DEBUG_LOG_ENABLED, bool(debug_enabled))
        st.success("已保存")

        back()

