import streamlit as st

from app.services import agent_prompts


def _label_for_record(record, index: int) -> str:
    title = str(record.title or "").strip() or "未命名 Agent 记录"
    updated_at = str(record.updated_at or "").strip()
    suffix = f"    {updated_at}" if updated_at else ""
    return f"{index + 1}. {title}{suffix}"


def _record_prompt_values(record) -> dict:
    values = {}
    for field_name, _ in agent_prompts.PROMPT_FIELDS:
        values[field_name] = getattr(record, field_name, "") if record is not None else ""
    values["npc1_name"] = getattr(record, "npc1_name", "NPC1") if record is not None else "NPC1"
    values["npc2_name"] = getattr(record, "npc2_name", "NPC2") if record is not None else "NPC2"
    values["npc3_name"] = getattr(record, "npc3_name", "NPC3") if record is not None else "NPC3"
    return values


def render():
    st.title("Agent Prompt")
    st.caption("编辑 Agent 模式专用 prompt。")

    mode = str(st.session_state.get("auth_mode", "") or "").strip().lower()
    is_guest = mode == "guest"

    state = agent_prompts.load_state()
    records = state.records
    labels = [_label_for_record(record, index) for index, record in enumerate(records)]
    label_to_record = {labels[index]: records[index] for index in range(len(records))}

    left, right = st.columns([1, 2])
    with left:
        st.subheader("记录")
        if not records:
            st.info("暂无 Agent prompt 记录。右侧填写后点保存会自动创建。")
            selected_label = None
        else:
            default_record = agent_prompts.selected_record(state)
            default_label = None
            for label, record in label_to_record.items():
                if default_record is not None and record.id == default_record.id:
                    default_label = label
                    break
            selected_label = st.radio(
                "选择记录",
                options=labels,
                index=labels.index(default_label) if default_label in labels else 0,
                label_visibility="collapsed",
            )

    selected_record = label_to_record.get(selected_label) if selected_label else None
    if selected_record is not None and selected_record.id != state.selected_record_id:
        state = agent_prompts.select_record(state, selected_record.id)

    with right:
        st.subheader("编辑" if not is_guest else "预览")
        title_value = selected_record.title if selected_record else ""
        prompt_values = _record_prompt_values(selected_record)

        title = st.text_input(
            "记录名称",
            value=title_value,
            placeholder="留空将使用默认名称",
            disabled=is_guest,
            key=f"agent_prompt_title_{selected_record.id if selected_record else 'new'}",
        )

        st.caption("NPC 前端显示名（内部调度仍使用 NPC1 / NPC2 / NPC3）")
        name_cols = st.columns(3)
        with name_cols[0]:
            edited_npc1_name = st.text_input(
                "NPC1 显示名",
                value=prompt_values.get("npc1_name", "NPC1"),
                disabled=is_guest,
                key=f"agent_prompt_npc1_name_{selected_record.id if selected_record else 'new'}",
            )
        with name_cols[1]:
            edited_npc2_name = st.text_input(
                "NPC2 显示名",
                value=prompt_values.get("npc2_name", "NPC2"),
                disabled=is_guest,
                key=f"agent_prompt_npc2_name_{selected_record.id if selected_record else 'new'}",
            )
        with name_cols[2]:
            edited_npc3_name = st.text_input(
                "NPC3 显示名",
                value=prompt_values.get("npc3_name", "NPC3"),
                disabled=is_guest,
                key=f"agent_prompt_npc3_name_{selected_record.id if selected_record else 'new'}",
            )

        edited_values = {}
        record_key = selected_record.id if selected_record else "new"
        for field_name, label in agent_prompts.PROMPT_FIELDS:
            edited_values[field_name] = st.text_area(
                label,
                value=prompt_values.get(field_name, ""),
                height=320,
                disabled=is_guest,
                key=f"agent_prompt_{field_name}_{record_key}",
            )

        b1, b2, b3 = st.columns(3)
        save = b1.button("保存", type="primary", use_container_width=True, disabled=is_guest)
        new_record = b2.button("另存为新记录", use_container_width=True, disabled=is_guest)
        delete = b3.button("删除", use_container_width=True, disabled=is_guest or not selected_record)

        if save:
            agent_prompts.save_prompt_record(
                state,
                record_id=selected_record.id if selected_record else "",
                title=title,
                npc1_name=edited_npc1_name,
                npc2_name=edited_npc2_name,
                npc3_name=edited_npc3_name,
                **edited_values,
            )
            st.success("已保存 Agent prompt")
            st.rerun()

        if new_record:
            agent_prompts.save_prompt_record(
                state,
                record_id="",
                title=title,
                npc1_name=edited_npc1_name,
                npc2_name=edited_npc2_name,
                npc3_name=edited_npc3_name,
                **edited_values,
            )
            st.success("已创建 Agent prompt 记录")
            st.rerun()

        if delete and selected_record:
            agent_prompts.delete_record(state, selected_record.id)
            st.success("已删除 Agent prompt 记录")
            st.rerun()
