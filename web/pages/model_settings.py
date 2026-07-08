import streamlit as st

from app.config import AppStorageKeys, has_streamlit_secret, settings
from web.nav import back


FIELDS = [
    (
        "输入 Grok 聊天 API Key（会本地持久化保存）",
        AppStorageKeys.XAI_CHAT_API_KEY,
        "GROK_CHAT_API_KEY",
        "GROK_CHAT_API_KEY",
    ),
    (
        "输入 Grok 生图 API Key（会本地持久化保存）",
        AppStorageKeys.XAI_IMAGE_API_KEY,
        "GROK_IMAGE_API_KEY",
        "GROK_IMAGE_API_KEY",
    ),
    (
        "输入 Replicate API Token（会本地持久化保存）",
        AppStorageKeys.REPLICATE_API_TOKEN,
        "REPLICATE_API_TOKEN",
        "REPLICATE_API_TOKEN",
    ),
    (
        "输入 DeepSeek API Key（会本地持久化保存）",
        AppStorageKeys.DEEPSEEK_API_KEY,
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_API_KEY",
    ),
    (
        "输入 DomoAI API Key（会本地持久化保存）",
        AppStorageKeys.DOMOAI_API_KEY,
        "DOMOAI_API_KEY",
        "DOMOAI_API_KEY",
    ),
    (
        "输入 智谱 API Key（会本地持久化保存）",
        AppStorageKeys.ZHIPU_API_KEY,
        "ZHIPU_API_KEY",
        "ZHIPU_API_KEY",
    ),
    (
        "输入 Cloudinary API Key（会本地持久化保存）",
        AppStorageKeys.CLOUDINARY_API_KEY,
        "CLOUDINARY_API_KEY",
        "CLOUDINARY_API_KEY",
    ),
]


def _pending_key(storage_key: str) -> str:
    return f"model_settings_pending_{storage_key}"


def _flash_key(storage_key: str) -> str:
    return f"model_settings_flash_{storage_key}"


def _key_status(storage_key: str, secret_name: str) -> str:
    saved = str(settings.get(storage_key, "") or "").strip()
    if saved:
        return "已填入"

    if has_streamlit_secret(secret_name):
        return "已配置默认 Key"

    return "未填写"


def _save_single(storage_key: str):
    pending = str(st.session_state.get(_pending_key(storage_key), "") or "").strip()
    if not pending:
        return
    settings.set(storage_key, pending)
    st.session_state[_pending_key(storage_key)] = ""
    st.session_state[_flash_key(storage_key)] = "saved"


def _delete_single(storage_key: str):
    settings.set(storage_key, "")
    st.session_state[_pending_key(storage_key)] = ""
    st.session_state[_flash_key(storage_key)] = "deleted"


def render():
    st.title("模型")

    st.caption("已保存的 Key 不会在 UI 中显示；如需更新请重新输入，或点击删除清空。")

    debug_enabled = st.checkbox(
        "打印调试日志",
        value=settings.bool(AppStorageKeys.DEBUG_LOG_ENABLED, False),
        help="关闭后不会在控制台打印请求体、响应体和调试信息，可减少卡顿。",
    )

    st.subheader("API Keys")
    st.caption("在输入框里按回车会立即保存该 Key。")

    for label_text, key, placeholder, secret_name in FIELDS:
        st.markdown(f"**{label_text}**")
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            st.text_input(
                "输入新值（回车保存；留空表示不修改）",
                value=str(st.session_state.get(_pending_key(key), "") or ""),
                placeholder=placeholder,
                type="password",
                label_visibility="collapsed",
                key=_pending_key(key),
                on_change=_save_single,
                args=(key,),
            )
        with c2:
            st.caption(_key_status(key, secret_name))
        with c3:
            st.button(
                "删除",
                use_container_width=True,
                type="secondary",
                key=f"model_settings_delete_btn_{key}",
                on_click=_delete_single,
                args=(key,),
            )

        flash = st.session_state.pop(_flash_key(key), None)
        if flash == "saved":
            st.success("已保存")
        elif flash == "deleted":
            st.success("已删除")

        st.divider()

    st.subheader("其他")
    if st.button("返回", use_container_width=True):
        settings.set(AppStorageKeys.DEBUG_LOG_ENABLED, bool(debug_enabled))
        back()
