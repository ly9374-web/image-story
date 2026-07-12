import streamlit as st

from app.config import AppStorageKeys, settings
from app.services import hidden_space, system_prompts


def render():
    st.title("设置")

    mode = str(st.session_state.get("auth_mode", "") or "").strip().lower()
    is_guest = mode == "guest"

    if "settings_hidden_space" not in st.session_state:
        st.session_state.settings_hidden_space = False
    if "settings_hp_nonce" not in st.session_state:
        st.session_state.settings_hp_nonce = 0

    state = system_prompts.load_state(hidden_space=bool(st.session_state.settings_hidden_space))

    with st.sidebar:
        st.subheader("System Prompt")
        passcode = st.text_input(
            "隐藏空间口令",
            type="password",
            placeholder="输入口令切换隐藏模式",
            key=f"settings_hp_{st.session_state.settings_hp_nonce}",
        )
        if passcode:
            if hidden_space.is_valid_passcode(passcode):
                st.session_state.settings_hidden_space = not bool(st.session_state.settings_hidden_space)
                st.session_state.settings_hp_nonce += 1
                st.rerun()
            else:
                st.warning("隐藏空间口令不正确。")
        st.caption("当前使用的 prompt 会同步到 Page2。")

    records = system_prompts.visible_records(state)
    record_labels = [
        system_prompts.record_label(state, record, index, unnamed="未命名记录")
        for index, record in enumerate(records)
    ]
    record_by_label = dict(zip(record_labels, records))

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
            options = record_labels
            selected_label = st.radio(
                "选择记录",
                options=options,
                index=options.index(default_label) if default_label in options else 0,
                label_visibility="collapsed",
            )

    selected_record = record_by_label.get(selected_label) if selected_label else None
    if selected_record is not None and selected_record.id and selected_record.id != state.selected_record_id:
        settings.set(AppStorageKeys.SELECTED_SYSTEM_PROMPT_RECORD_ID, selected_record.id)
        settings.set(AppStorageKeys.SYSTEM_PROMPT, str(selected_record.prompt or ""))
        state.selected_record_id = selected_record.id
        st.rerun()

    with c2:
        record_key = selected_record.id if selected_record else "new"
        st.subheader("编辑" if not is_guest else "预览")
        title_value = selected_record.title if selected_record else ""
        prompt_value = selected_record.prompt if selected_record else str(settings.get(AppStorageKeys.SYSTEM_PROMPT, "") or "")

        title = st.text_input(
            "记录名称",
            value=title_value,
            placeholder="留空将使用默认名称",
            disabled=is_guest,
            key=f"system_prompt_title_{record_key}",
        )
        prompt = st.text_area(
            "prompt",
            value=prompt_value,
            height=320,
            disabled=is_guest,
            key=f"system_prompt_body_{record_key}",
        )

        b1, b2, b3 = st.columns(3)
        save = b1.button("保存", type="primary", use_container_width=True, disabled=is_guest)
        new_record = b2.button("新建prompt", use_container_width=True, disabled=is_guest)
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
                title="",
                prompt="",
            )
            st.success("已新建 prompt")
            st.rerun()

        if delete and selected_record:
            state = system_prompts.delete_record(state, selected_record.id)
            st.success("已删除")
            st.rerun()
