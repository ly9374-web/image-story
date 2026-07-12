import json

import streamlit as st

from app.services import agent_records
from app.services import chat_records
from app.services import hidden_space
from web.nav import goto


def _label(item):
    title = item.title or "未命名聊天"
    updated_at = item.updated_at or ""
    return f"{title}    {updated_at}"


def _debug_text(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value or "")


def _render_debug_text(label: str, value, key: str, height: int = 180):
    st.text_area(
        label,
        value=_debug_text(value),
        height=height,
        disabled=True,
        key=key,
    )


def _render_agent_debug_record(record):
    st.divider()
    st.subheader("调试记录")
    debug_logs = list(getattr(record, "debug_logs", []) or [])
    if not debug_logs:
        st.info("这条 Agent 记录还没有调试日志。旧记录需要重新跑一轮后才会生成。")
        return

    st.caption(f"共 {len(debug_logs)} 次模型调用")
    for index, entry in enumerate(debug_logs):
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or f"调用 {index + 1}")
        round_number = entry.get("round")
        suffix = f" · round={round_number}" if round_number is not None else ""
        with st.expander(f"{index + 1}. {label}{suffix}", expanded=index == len(debug_logs) - 1):
            meta = {
                "at": entry.get("at", ""),
                "model": entry.get("model", ""),
                "selected_chat_model": entry.get("selected_chat_model", ""),
                "temperature": entry.get("temperature", ""),
                "metadata": entry.get("metadata", {}),
            }
            key_prefix = f"records_agent_debug_{record.id}_{index}"
            _render_debug_text("Meta", meta, f"{key_prefix}_meta", height=130)
            _render_debug_text("System Prompt", entry.get("system_prompt"), f"{key_prefix}_system_prompt")
            context_messages = entry.get("context_messages")
            if context_messages:
                _render_debug_text("Context Messages", context_messages, f"{key_prefix}_context_messages")
            _render_debug_text("User Prompt", entry.get("user_prompt"), f"{key_prefix}_user_prompt")
            if entry.get("error"):
                _render_debug_text("Error", entry.get("error"), f"{key_prefix}_error")
            _render_debug_text("Output", entry.get("output"), f"{key_prefix}_output")


def render():
    agent_mode = bool(st.session_state.get("agent_mode", False))
    st.title("Agent 记录" if agent_mode else "记录")

    if "records_hidden_space" not in st.session_state:
        st.session_state.records_hidden_space = False
    if "records_debug_record_id" not in st.session_state:
        st.session_state.records_debug_record_id = ""

    with st.sidebar:
        st.subheader("Agent 聊天记录" if agent_mode else "聊天记录")
        passcode = st.text_input("隐藏空间口令", type="password", placeholder="输入口令显示隐藏记录")
        if passcode:
            st.session_state.records_hidden_space = hidden_space.unlock(
                bool(st.session_state.records_hidden_space),
                passcode,
            )
        st.caption("提示：把聊天标题改成以「隐藏：」开头，可在未解锁时隐藏。")

    mode = str(st.session_state.get("auth_mode", "") or "").strip().lower()
    scope = "guest" if mode == "guest" else None
    items = (
        agent_records.load_index_sorted(scope=scope)
        if agent_mode
        else chat_records.load_index_sorted(scope=scope)
    )
    if not bool(st.session_state.records_hidden_space):
        items = [i for i in items if not str(i.title or "").strip().startswith("隐藏：")]

    if not items:
        st.info("暂无 Agent 聊天记录。去「开始」发一条消息后会自动保存。" if agent_mode else "暂无聊天记录。去「开始」发一条消息后会自动保存。")
        return

    labels = [_label(item) for item in items]
    label_to_item = {labels[i]: items[i] for i in range(len(items))}

    selected = st.radio(
        "选择记录",
        options=labels,
        label_visibility="collapsed",
    )
    item = label_to_item.get(selected)
    if item is None:
        return

    action_columns = st.columns([1, 1, 1, 1] if agent_mode else [1, 1, 1])
    c1 = action_columns[0]
    c2 = action_columns[1]
    c3 = action_columns[2]
    with c1:
        if st.button("打开", type="primary", use_container_width=True):
            goto("agentMain" if agent_mode else "main", record_id=item.id)
    with c2:
        new_title = st.text_input("重命名", value=item.title or "", key="records_rename_title")
        if st.button("保存名称", use_container_width=True):
            if agent_mode:
                agent_records.rename_record(item.id, new_title, scope=scope)
            else:
                chat_records.rename_record(item.id, new_title, scope=scope)
            st.success("已重命名")
            st.rerun()
    with c3:
        if st.button("删除", use_container_width=True):
            if agent_mode:
                agent_records.delete_record(item.id, scope=scope)
            else:
                chat_records.delete_record(item.id, scope=scope)
            st.success("已删除")
            st.rerun()

    if agent_mode:
        with action_columns[3]:
            if st.button("调试记录", use_container_width=True):
                st.session_state.records_debug_record_id = item.id

        if st.session_state.records_debug_record_id == item.id:
            record = agent_records.load_record_by_id(item.id, scope=scope)
            if record is None:
                st.warning("Agent 记录不存在或加载失败。")
            else:
                _render_agent_debug_record(record)
