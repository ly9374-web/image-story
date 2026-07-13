import streamlit as st

from app.services import agent_prompts, hidden_space


def _label_for_record(state: agent_prompts.AgentPromptState, record, index: int) -> str:
    title = str(record.title or "").strip() or "未命名 Agent 记录"
    updated_at = str(record.updated_at or "").strip()
    prefix = "隐藏：" if agent_prompts.record_space(state, record.id) == "hidden" else ""
    suffix = f"    {updated_at}" if updated_at else ""
    return f"{index + 1}. {prefix}{title}{suffix}"


def _record_prompt_values(record) -> dict:
    values = {}
    for field_name, _ in agent_prompts.PROMPT_FIELDS:
        values[field_name] = getattr(record, field_name, "") if record is not None else ""
        if field_name == "player_parser_prompt" and not str(values[field_name] or "").strip():
            values[field_name] = agent_prompts.DEFAULT_PLAYER_ROUTE_PROMPT
        if field_name == "action_scheduler_prompt" and not str(values[field_name] or "").strip():
            values[field_name] = agent_prompts.DEFAULT_ACTION_DECISION_PROMPT
        if field_name == "scene_descriptor_prompt" and not str(values[field_name] or "").strip():
            values[field_name] = agent_prompts.DEFAULT_SCENE_DESCRIPTOR_PROMPT
        if field_name == "story_brain_generator_prompt" and not str(values[field_name] or "").strip():
            values[field_name] = agent_prompts.DEFAULT_STORY_BRAIN_GENERATOR_PROMPT
    values["npc1_name"] = getattr(record, "npc1_name", "NPC1") if record is not None else "NPC1"
    values["npc2_name"] = getattr(record, "npc2_name", "NPC2") if record is not None else "NPC2"
    values["npc3_name"] = getattr(record, "npc3_name", "NPC3") if record is not None else "NPC3"
    values["default_story_brain"] = getattr(record, "default_story_brain", "") if record is not None else ""
    return values


def _field_key(field_name: str, record_key: str) -> str:
    return f"agent_prompt_{field_name}_{record_key}"


def _set_if_empty(key: str, current_value: str, generated_value: str, placeholders=()) -> bool:
    generated_text = str(generated_value or "").strip()
    if not generated_text:
        return False

    current_text = str(st.session_state.get(key, current_value) or "").strip()
    if current_text and current_text not in placeholders:
        return False

    st.session_state[key] = generated_text
    return True


def _append_if_missing(key: str, current_value: str, suffix: str) -> bool:
    suffix_text = str(suffix or "").strip()
    if not suffix_text:
        return False

    current_text = str(st.session_state.get(key, current_value) or "").strip()
    if suffix_text in current_text:
        return False

    st.session_state[key] = "\n\n".join(part for part in [current_text, suffix_text] if part)
    return True


def _apply_generated_values(record_key: str, prompt_values: dict) -> tuple[int, int] | None:
    pending = st.session_state.get("agent_prompt_generated_values")
    if not isinstance(pending, dict) or pending.get("record_key") != record_key:
        return None

    values = pending.get("values")
    if not isinstance(values, dict):
        st.session_state.pop("agent_prompt_generated_values", None)
        return None

    filled = 0
    skipped = 0
    fields = [
        ("npc1_name", prompt_values.get("npc1_name", "NPC1"), ("NPC1",)),
        ("npc1_prompt", prompt_values.get("npc1_prompt", ""), ()),
        ("npc2_name", prompt_values.get("npc2_name", "NPC2"), ("NPC2",)),
        ("npc2_prompt", prompt_values.get("npc2_prompt", ""), ()),
        ("npc3_name", prompt_values.get("npc3_name", "NPC3"), ("NPC3",)),
        ("npc3_prompt", prompt_values.get("npc3_prompt", ""), ()),
    ]

    for field_name, current_value, placeholders in fields:
        if _set_if_empty(_field_key(field_name, record_key), current_value, values.get(field_name, ""), placeholders):
            filled += 1
        else:
            skipped += 1

    default_story_brain = str(values.get("default_story_brain") or "").strip()
    if default_story_brain:
        st.session_state[_field_key("default_story_brain", record_key)] = default_story_brain
        filled += 1

    action_scheduler_prompt = prompt_values.get("action_scheduler_prompt", "")
    relationship_rules = str(values.get("relationship_rules") or "").strip()
    if _append_if_missing(
        _field_key("action_scheduler_prompt", record_key),
        action_scheduler_prompt,
        relationship_rules,
    ):
        filled += 1
    elif relationship_rules:
        skipped += 1

    st.session_state.pop("agent_prompt_generated_values", None)
    return filled, skipped


def _render_generator_body(record_key: str):
    model = st.selectbox(
        "模型",
        options=["grok2", "deepseek"],
        format_func=lambda item: "Grok" if item == "grok2" else "DeepSeek",
        key="agent_prompt_generator_model",
    )
    story = st.text_area(
        "大致故事",
        height=340,
        placeholder="描述世界观、角色关系、玩家身份、剧情基调，以及希望 3 个 NPC 如何互动。",
        key="agent_prompt_generator_story",
    )

    col1, col2 = st.columns(2)
    with col1:
        generate = st.button("生成", type="primary", use_container_width=True)
    with col2:
        close = st.button("关闭", use_container_width=True)

    if close:
        st.session_state.agent_prompt_generator_open = False
        st.session_state.pop("agent_prompt_generator_record_key", None)
        st.rerun()

    if not generate:
        return

    with st.spinner("正在生成 Agent prompt..."):
        try:
            generated = agent_prompts.generate_prompt_from_story(story, model=model)
        except agent_prompts.GeneratedPromptParseError as exc:
            st.error(str(exc))
            if str(exc.raw_text or "").strip():
                st.text_area("模型原始输出", value=exc.raw_text, height=220, disabled=True)
            return
        except Exception as exc:
            st.error(str(exc))
            return

    st.session_state.agent_prompt_generated_values = {
        "record_key": record_key,
        "values": generated.to_form_values(),
    }
    st.session_state.agent_prompt_generator_open = False
    st.session_state.pop("agent_prompt_generator_record_key", None)
    st.rerun()


def _render_generator_dialog(record_key: str):
    if hasattr(st, "dialog"):
        @st.dialog("自动生成prompt")
        def _dialog():
            _render_generator_body(record_key)

        _dialog()
        return

    st.warning("当前 Streamlit 版本不支持弹窗，已改为页面内生成面板。")
    with st.expander("自动生成prompt", expanded=True):
        _render_generator_body(record_key)


def render():
    st.title("Agent Prompt")
    st.caption("编辑 Agent 模式专用 prompt。")

    mode = str(st.session_state.get("auth_mode", "") or "").strip().lower()
    is_guest = mode == "guest"

    if "agent_prompt_hidden_space" not in st.session_state:
        st.session_state.agent_prompt_hidden_space = False
    if "agent_prompt_hp_nonce" not in st.session_state:
        st.session_state.agent_prompt_hp_nonce = 0

    state = agent_prompts.load_state(hidden_space=bool(st.session_state.agent_prompt_hidden_space))

    with st.sidebar:
        st.subheader("Agent Prompt")
        passcode = st.text_input(
            "隐藏空间口令",
            type="password",
            placeholder="输入口令切换隐藏模式",
            key=f"agent_prompt_hp_{st.session_state.agent_prompt_hp_nonce}",
        )
        if passcode:
            if hidden_space.is_valid_passcode(passcode):
                st.session_state.agent_prompt_hidden_space = not bool(st.session_state.agent_prompt_hidden_space)
                st.session_state.agent_prompt_hp_nonce += 1
                st.rerun()
            else:
                st.warning("隐藏空间口令不正确。")

    records = agent_prompts.visible_records(state)
    labels = [_label_for_record(state, record, index) for index, record in enumerate(records)]
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
        st.session_state.agent_prompt_generator_open = False
        st.session_state.pop("agent_prompt_generator_record_key", None)
        state = agent_prompts.select_record(state, selected_record.id)
        st.rerun()

    with right:
        record_key = selected_record.id if selected_record else "new"
        header_cols = st.columns([1, 1])
        with header_cols[0]:
            st.subheader("编辑" if not is_guest else "预览")
        with header_cols[1]:
            if st.button("自动生成prompt", use_container_width=True, disabled=is_guest):
                st.session_state.agent_prompt_generator_open = True
                st.session_state.agent_prompt_generator_record_key = record_key

        if (
            st.session_state.get("agent_prompt_generator_open")
            and st.session_state.get("agent_prompt_generator_record_key") == record_key
        ):
            _render_generator_dialog(record_key)

        title_value = selected_record.title if selected_record else ""
        prompt_values = _record_prompt_values(selected_record)
        generated_result = _apply_generated_values(record_key, prompt_values)
        if generated_result is not None:
            filled, skipped = generated_result
            st.success(f"已填入 {filled} 个空字段；{skipped} 个已有内容的字段未覆盖。")

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
                key=_field_key("npc1_name", record_key),
            )
        with name_cols[1]:
            edited_npc2_name = st.text_input(
                "NPC2 显示名",
                value=prompt_values.get("npc2_name", "NPC2"),
                disabled=is_guest,
                key=_field_key("npc2_name", record_key),
            )
        with name_cols[2]:
            edited_npc3_name = st.text_input(
                "NPC3 显示名",
                value=prompt_values.get("npc3_name", "NPC3"),
                disabled=is_guest,
                key=_field_key("npc3_name", record_key),
            )

        edited_values = {}
        for field_name, label in agent_prompts.PROMPT_FIELDS:
            edited_values[field_name] = st.text_area(
                label,
                value=prompt_values.get(field_name, ""),
                height=320,
                disabled=is_guest,
                key=_field_key(field_name, record_key),
            )
        edited_default_story_brain = st.text_area(
            "默认story brain",
            value=prompt_values.get("default_story_brain", ""),
            height=320,
            disabled=is_guest,
            key=_field_key("default_story_brain", record_key),
        )

        b1, b2, b3 = st.columns(3)
        save = b1.button("保存", type="primary", use_container_width=True, disabled=is_guest)
        new_record = b2.button("新建prompt", use_container_width=True, disabled=is_guest)
        delete = b3.button("删除", use_container_width=True, disabled=is_guest or not selected_record)

        if save:
            agent_prompts.save_prompt_record(
                state,
                record_id=selected_record.id if selected_record else "",
                title=title,
                npc1_name=edited_npc1_name,
                npc2_name=edited_npc2_name,
                npc3_name=edited_npc3_name,
                default_story_brain=edited_default_story_brain,
                **edited_values,
            )
            st.success("已保存 Agent prompt")
            st.rerun()

        if new_record:
            agent_prompts.save_prompt_record(
                state,
                record_id="",
                title="",
                npc1_name="NPC1",
                npc2_name="NPC2",
                npc3_name="NPC3",
                npc1_prompt="",
                npc2_prompt="",
                npc3_prompt="",
                player_parser_prompt=agent_prompts.DEFAULT_PLAYER_ROUTE_PROMPT,
                action_scheduler_prompt=agent_prompts.DEFAULT_ACTION_DECISION_PROMPT,
                scene_descriptor_prompt=agent_prompts.DEFAULT_SCENE_DESCRIPTOR_PROMPT,
                story_brain_generator_prompt=agent_prompts.DEFAULT_STORY_BRAIN_GENERATOR_PROMPT,
                default_story_brain="",
            )
            st.success("已新建 Agent prompt")
            st.rerun()

        if delete and selected_record:
            agent_prompts.delete_record(state, selected_record.id)
            st.success("已删除 Agent prompt 记录")
            st.rerun()
