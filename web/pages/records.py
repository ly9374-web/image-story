import streamlit as st

from app.services import chat_records
from app.services import hidden_space
from web.nav import goto


def _label(item):
    title = item.title or "未命名聊天"
    updated_at = item.updated_at or ""
    return f"{title}    {updated_at}"


def render():
    st.title("记录")

    if "records_hidden_space" not in st.session_state:
        st.session_state.records_hidden_space = False

    with st.sidebar:
        st.subheader("聊天记录")
        passcode = st.text_input("隐藏空间口令", type="password", placeholder="输入口令显示隐藏记录")
        if passcode:
            st.session_state.records_hidden_space = hidden_space.unlock(
                bool(st.session_state.records_hidden_space),
                passcode,
            )
        st.caption("提示：把聊天标题改成以「隐藏：」开头，可在未解锁时隐藏。")

    mode = str(st.session_state.get("auth_mode", "") or "").strip().lower()
    scope = "guest" if mode == "guest" else None
    items = chat_records.load_index_sorted(scope=scope)
    if not bool(st.session_state.records_hidden_space):
        items = [i for i in items if not str(i.title or "").strip().startswith("隐藏：")]

    if not items:
        st.info("暂无聊天记录。去「开始」发一条消息后会自动保存。")
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

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if st.button("打开", type="primary", use_container_width=True):
            goto("main", record_id=item.id)
    with c2:
        new_title = st.text_input("重命名", value=item.title or "", key="records_rename_title")
        if st.button("保存名称", use_container_width=True):
            chat_records.rename_record(item.id, new_title, scope=scope)
            st.success("已重命名")
            st.rerun()
    with c3:
        if st.button("删除", use_container_width=True):
            chat_records.delete_record(item.id, scope=scope)
            st.success("已删除")
            st.rerun()
