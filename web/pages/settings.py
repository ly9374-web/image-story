import streamlit as st

from app.config import AppStorageKeys, settings
from app.models import SystemPromptRecord
from app.services import system_prompts


def _label_for_record(state: system_prompts.PromptState, record: SystemPromptRecord):
    space = system_prompts.record_space(state, record.id)
    prefix = "隐藏：" if space == "hidden" else ""
    return prefix + (record.title or "未命名记录")


def render():
    st.title("设置")

    mode = str(st.session_state.get("auth_mode", "") or "").strip().lower()
    is_guest = mode == "guest"

    if "settings_hidden_space" not in st.session_state:
        st.session_state.settings_hidden_space = False

    state = system_prompts.load_state(hidden_space=bool(st.session_state.settings_hidden_space))

    with st.sidebar:
        st.subheader("System Prompt")
        passcode = st.text_input("隐藏空间口令", type="password", placeholder="输入口令解锁隐藏记录")
        if passcode:
            state = system_prompts.unlock_hidden_space(state, passcode)
            st.session_state.settings_hidden_space = state.hidden_space
        st.caption("当前使用的 prompt 会同步到 Page2。")

    records = system_prompts.visible_records(state)
    record_by_label = {_label_for_record(state, r): r for r in records}

    c1, c2 = st.columns([1, 2])
    with c1:
        st.subheader("记录")
        if not records:
            st.info("暂无记录。右侧输入 prompt 后点保存会自动创建。")
            selected_label = None
        else:
            default_record_id = state.selected_record_id
            default_label = None
            for label, record in record_by_label.items():
                if record.id == default_record_id:
                    default_label = label
                    break
            options = list(record_by_label.keys())
            selected_label = st.radio(
                "选择记录",
                options=options,
                index=options.index(default_label) if default_label in options else 0,
                label_visibility="collapsed",
            )

    selected_record = record_by_label.get(selected_label) if selected_label else None
    if is_guest and selected_record is not None:
        if selected_record.id and selected_record.id != state.selected_record_id:
            settings.set(AppStorageKeys.SELECTED_SYSTEM_PROMPT_RECORD_ID, selected_record.id)
            settings.set(AppStorageKeys.SYSTEM_PROMPT, str(selected_record.prompt or ""))
            state.selected_record_id = selected_record.id

    with c2:
        st.subheader("编辑" if not is_guest else "预览")
        title_value = selected_record.title if selected_record else ""
        prompt_value = selected_record.prompt if selected_record else str(settings.get(AppStorageKeys.SYSTEM_PROMPT, "") or "")

        title = st.text_input(
            "记录名称",
            value=title_value,
            placeholder="留空将使用默认名称",
            disabled=is_guest,
        )
        prompt = st.text_area("prompt", value=prompt_value, height=320, disabled=is_guest)

        b1, b2, b3 = st.columns(3)
        save = b1.button("保存", type="primary", use_container_width=True, disabled=is_guest)
        new_record = b2.button("另存为新记录", use_container_width=True, disabled=is_guest)
        delete = b3.button("删除", use_container_width=True, disabled=is_guest or not selected_record)

        if save:
            state = system_prompts.save_prompt(
                state,
                record_id=selected_record.id if selected_record else "",
                title=title,
                prompt=prompt,
            )
            st.success("已保存")
            st.rerun()

        if new_record:
            state = system_prompts.save_prompt(
                state,
                record_id="",
                title=title,
                prompt=prompt,
            )
            st.success("已创建新记录")
            st.rerun()

        if delete and selected_record:
            state = system_prompts.delete_record(state, selected_record.id)
            st.success("已删除")
            st.rerun()
