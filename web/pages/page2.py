from __future__ import annotations

import base64
import tempfile
import uuid
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from app.api.media_clients import CloudinaryUploader
from app.config import AppStorageKeys, settings, user_facing_error_message
from app.models import GeneratedMediaKind, Page2ConversationTurn
from app.services import chat_records, page2_service, stored_urls, system_prompts
from graph_view import GRAPH_HEIGHT_PX, GRAPH_NODE_SPACING, build_story_brain_graph_data
from story_brain import (
    apply_story_brain_updates,
    build_memory_pack,
    empty_story_brain,
    memory_pack_to_json,
    normalize_story_brain,
)
from web.nav import get_arg, goto


_story_brain_graph_component = components.declare_component(
    "story_brain_graph",
    path=str(Path(__file__).resolve().parents[1] / "components" / "story_brain_graph"),
)


def _chat_scope() -> str | None:
    mode = str(st.session_state.get("auth_mode", "") or "").strip().lower()
    return "guest" if mode == "guest" else None


def _decode_image_base64(b64: str) -> bytes:
    return base64.b64decode(b64.encode("ascii"))


def _show_error(exc: Exception):
    st.error(user_facing_error_message(exc))


def _ensure_state():
    st.session_state.setdefault("page2_record_id", "")
    st.session_state.setdefault("page2_loaded_record_id", "")
    st.session_state.setdefault("page2_turns", [])
    st.session_state.setdefault("page2_generated_media", [])
    st.session_state.setdefault("page2_selected_media_id", "")
    st.session_state.setdefault("page2_image_prompt", "")
    st.session_state.setdefault("page2_image_prompt_mode", "normal")
    st.session_state.setdefault("page2_image_prompt_subject", "")
    st.session_state.setdefault("page2_video_prompt", "动起来")
    st.session_state.setdefault("page2_url_hidden_space", False)
    st.session_state.setdefault("page2_story_brain_suggested_updates", None)
    st.session_state.setdefault("page2_story_brain_update_error", "")
    st.session_state.setdefault("page2_story_brain_update_turn_id", "")
    st.session_state.setdefault("page2_story_brain_update_applied", False)
    st.session_state.setdefault("page2_story_brain_graph_edit_event_id", "")
    st.session_state.setdefault("page2_story_brain_graph_fullscreen", False)
    st.session_state.setdefault("page2_story_brain", empty_story_brain())
    st.session_state.setdefault("page2_story_brain_enabled", True)


def _load_record_from_nav_if_needed():
    record_id = str(get_arg("record_id", "") or "").strip()
    if not record_id:
        return

    if st.session_state.page2_loaded_record_id == record_id:
        return

    record = chat_records.load_record_by_id(record_id, scope=_chat_scope())
    if record is None:
        st.warning("记录不存在或加载失败。")
        return

    st.session_state.page2_record_id = record.id
    st.session_state.page2_loaded_record_id = record.id
    st.session_state.page2_turns = list(record.turns or [])
    st.session_state.page2_generated_media = list(record.generated_images or [])
    st.session_state.page2_story_brain = normalize_story_brain(record.story_brain)
    st.session_state.page2_selected_media_id = ""

    if str(record.system_prompt or "").strip():
        ctx = page2_service.load_context_from_settings()
        ctx.system_prompt = record.system_prompt
        page2_service.save_context_to_settings(ctx)


def _latest_assistant_message(turns: list[Page2ConversationTurn]) -> str:
    for turn in reversed(turns):
        if turn.assistant_message:
            return turn.assistant_message
    return ""


def _upsert_record():
    ctx = page2_service.load_context_from_settings()
    st.session_state.page2_record_id = page2_service.upsert_chat_record(
        record_id=st.session_state.page2_record_id,
        turns=st.session_state.page2_turns,
        generated_media=st.session_state.page2_generated_media,
        system_prompt=ctx.system_prompt,
        story_brain=st.session_state.page2_story_brain,
        scope=_chat_scope(),
    )


def _current_story_brain() -> dict:
    story_brain = normalize_story_brain(st.session_state.get("page2_story_brain"))
    st.session_state.page2_story_brain = story_brain
    return story_brain


def _save_story_brain_to_current_record(story_brain: dict):
    st.session_state.page2_story_brain = normalize_story_brain(story_brain)
    _upsert_record()


def _new_story_brain_id(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex[:10]


def _story_brain_text(value) -> str:
    return str(value or "").strip()


def _story_brain_lists(story_brain: dict) -> tuple[list, list, list]:
    characters = story_brain.setdefault("characters", [])
    relationships = story_brain.setdefault("relationships", [])
    events = story_brain.setdefault("events", [])
    return characters, relationships, events


def _save_story_brain_and_refresh(story_brain: dict):
    _save_story_brain_to_current_record(story_brain)
    st.session_state["page2_story_brain_enabled"] = True
    st.session_state["show_story_brain"] = True
    st.rerun()


def _story_brain_collection_for_target(target_type: str) -> str:
    if target_type == "character":
        return "characters"
    if target_type == "relationship":
        return "relationships"
    if target_type == "event":
        return "events"
    return ""


def _apply_story_brain_graph_edit(story_brain: dict, edit_event: dict) -> bool:
    if not isinstance(edit_event, dict):
        return False
    if edit_event.get("action") != "edit":
        return False

    collection_key = _story_brain_collection_for_target(str(edit_event.get("target_type", "")))
    if not collection_key:
        return False

    data = edit_event.get("data")
    if not isinstance(data, dict):
        return False

    collection = story_brain.setdefault(collection_key, [])
    if not isinstance(collection, list):
        return False

    target_id = _story_brain_text(edit_event.get("target_id"))
    target_index = edit_event.get("target_index")

    selected_index = None
    if target_id:
        for index, item in enumerate(collection):
            if isinstance(item, dict) and _story_brain_text(item.get("id")) == target_id:
                selected_index = index
                break

    if selected_index is None:
        try:
            target_index = int(target_index)
        except Exception:
            target_index = -1
        if 0 <= target_index < len(collection):
            selected_index = target_index

    if selected_index is None:
        return False

    item = collection[selected_index]
    if not isinstance(item, dict):
        return False

    candidate = {
        **item,
        **data,
    }
    if collection_key == "events":
        event_type = _story_brain_text(candidate.get("type"))
        trigger = _story_brain_text(candidate.get("trigger"))
        if event_type == "伏笔" and not trigger:
            return False
        if event_type != "伏笔":
            candidate["trigger"] = ""

    collection[selected_index] = candidate
    _save_story_brain_to_current_record(story_brain)
    return True


def _render_story_brain_graph_component(story_brain: dict, *, height: int, key: str):
    graph_data = build_story_brain_graph_data(
        story_brain,
        node_spacing=GRAPH_NODE_SPACING,
        height=height,
    )
    return _story_brain_graph_component(
        graph=graph_data,
        height=height,
        key=key,
        default=None,
    )


def _handle_story_brain_graph_event(story_brain: dict, graph_event: dict):
    event_id = ""
    if isinstance(graph_event, dict):
        event_id = _story_brain_text(graph_event.get("event_id"))

    if event_id and event_id != st.session_state.get("page2_story_brain_graph_edit_event_id"):
        st.session_state["page2_story_brain_graph_edit_event_id"] = event_id
        action = _story_brain_text(graph_event.get("action"))
        if action == "fullscreen":
            st.session_state["page2_story_brain_graph_fullscreen"] = True
            st.session_state["page2_story_brain_enabled"] = True
            st.session_state["show_story_brain"] = True
            st.rerun()
        if action != "edit":
            return
        if _apply_story_brain_graph_edit(story_brain, graph_event):
            st.session_state["story_brain_notice"] = "已保存图谱节点修改。"
            st.session_state["page2_story_brain_enabled"] = True
            st.session_state["show_story_brain"] = True
            st.rerun()
        st.warning("未能保存图谱节点修改，请确认节点仍存在。")


def _render_story_brain_fullscreen_graph(story_brain: dict):
    if not st.session_state.get("page2_story_brain_graph_fullscreen"):
        return

    st.markdown(
        """
        <style>
          .st-key-page2_story_brain_fullscreen_overlay {
            position: fixed;
            inset: 0;
            z-index: 999999;
            box-sizing: border-box;
            padding: 18px;
            overflow: auto;
            background: #0b0f14;
          }
          .st-key-page2_story_brain_fullscreen_overlay iframe {
            border-radius: 8px;
          }
          .st-key-page2_story_brain_fullscreen_close_btn {
            position: fixed;
            top: 14px;
            right: 18px;
            z-index: 1000000;
            width: 36px;
          }
          .st-key-page2_story_brain_fullscreen_close_btn button {
            min-height: 32px;
            padding: 0;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.92);
            color: #111827;
            font-size: 18px;
            line-height: 1;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )
    fullscreen_height = 900
    with st.container(key="page2_story_brain_fullscreen_overlay"):
        if st.button("x", key="page2_story_brain_fullscreen_close_btn", help="关闭 Story Brain 全屏"):
            st.session_state["page2_story_brain_graph_fullscreen"] = False
            st.rerun()
        graph_event = _render_story_brain_graph_component(
            story_brain,
            height=fullscreen_height,
            key="page2_story_brain_graph_component_fullscreen",
        )
        _handle_story_brain_graph_event(story_brain, graph_event)


def _render_story_brain_graph(story_brain: dict):
    graph_event = _render_story_brain_graph_component(
        story_brain,
        height=GRAPH_HEIGHT_PX,
        key="page2_story_brain_graph_component",
    )
    _handle_story_brain_graph_event(story_brain, graph_event)
    _render_story_brain_fullscreen_graph(story_brain)


def _clear_story_brain_update_suggestions():
    st.session_state["page2_story_brain_suggested_updates"] = None
    st.session_state["page2_story_brain_update_error"] = ""
    st.session_state["page2_story_brain_update_turn_id"] = ""
    st.session_state["page2_story_brain_update_applied"] = False


def _render_story_brain_update_suggestions():
    suggested_updates = st.session_state.get("page2_story_brain_suggested_updates")
    update_error = str(st.session_state.get("page2_story_brain_update_error", "") or "").strip()
    success_message = st.session_state.pop("page2_story_brain_update_success", "")
    if success_message:
        st.success(success_message)

    if not update_error and suggested_updates is None:
        return

    with st.expander("Story Brain 更新建议"):
        if update_error:
            st.error(update_error)
            return

        if not isinstance(suggested_updates, dict):
            st.error("Story Brain 更新建议格式异常。")
            return

        updates = suggested_updates.get("suggested_updates")
        if not isinstance(updates, list):
            st.error("Story Brain 更新建议缺少 suggested_updates 数组。")
            st.json(suggested_updates)
            return

        if not updates:
            st.info("本轮没有发现需要更新的 Story Brain 记忆")
            st.json(suggested_updates)
            return

        if st.session_state.get("page2_story_brain_update_applied"):
            st.success("已自动应用到 Story Brain。")
        st.json(suggested_updates)


def _character_label(item, index: int) -> str:
    name = _story_brain_text(item.get("name") if isinstance(item, dict) else "")
    return f"{index + 1}. {name or '未命名角色'}"


def _relationship_label(item, index: int) -> str:
    if not isinstance(item, dict):
        return f"{index + 1}. 未命名关系"
    from_name = _story_brain_text(item.get("from"))
    to_name = _story_brain_text(item.get("to"))
    rel_type = _story_brain_text(item.get("type"))
    name = f"{from_name or '?'} -> {to_name or '?'}"
    if rel_type:
        name += f"（{rel_type}）"
    return f"{index + 1}. {name}"


def _event_label(item, index: int) -> str:
    if not isinstance(item, dict):
        return f"{index + 1}. 未命名事件"
    event_type = _story_brain_text(item.get("type"))
    title = _story_brain_text(item.get("title"))
    content = _story_brain_text(item.get("content"))
    name = title or content[:24] or "未命名事件"
    return f"{index + 1}. {event_type + '：' if event_type else ''}{name}"


def _ensure_selectbox_value(key: str, options: list[int]):
    if not options:
        st.session_state.pop(key, None)
        return
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]


def _render_story_brain_character_editor(story_brain: dict):
    characters, _, _ = _story_brain_lists(story_brain)

    with st.expander("角色编辑"):
        if not characters:
            st.info("暂无角色，请先新增角色")

        if st.button("新增角色", key="story_brain_add_character_btn", use_container_width=True):
            characters.append(
                {
                    "id": _new_story_brain_id("char"),
                    "name": "",
                    "speech_style": "",
                    "behavior_style": "",
                    "status": "",
                    "other": "",
                    "goal": "",
                    "secret": "",
                }
            )
            _save_story_brain_and_refresh(story_brain)

        if not characters:
            return

        options = list(range(len(characters)))
        select_key = "story_brain_character_select"
        _ensure_selectbox_value(select_key, options)
        selected_index = st.selectbox(
            "选择角色",
            options=options,
            format_func=lambda index: _character_label(characters[index], index),
            key=select_key,
        )

        character = characters[selected_index] if isinstance(characters[selected_index], dict) else {}
        record_id = _story_brain_text(character.get("id")) or f"character_{selected_index}"
        record_key = f"{record_id}_{selected_index}"

        name = st.text_input("name", value=_story_brain_text(character.get("name")), key=f"story_brain_character_name_{record_key}")
        speech_style = st.text_area(
            "speech_style",
            value=_story_brain_text(character.get("speech_style")),
            key=f"story_brain_character_speech_style_{record_key}",
        )
        behavior_style = st.text_area(
            "behavior_style",
            value=_story_brain_text(character.get("behavior_style")),
            key=f"story_brain_character_behavior_style_{record_key}",
        )
        status = st.text_area(
            "状态（身体状态 / 伤势 / 当前姿势）",
            value=_story_brain_text(character.get("status")),
            key=f"story_brain_character_status_{record_key}",
        )
        other = st.text_area("other", value=_story_brain_text(character.get("other")), key=f"story_brain_character_other_{record_key}")
        goal = st.text_area("goal", value=_story_brain_text(character.get("goal")), key=f"story_brain_character_goal_{record_key}")
        secret = st.text_area("secret", value=_story_brain_text(character.get("secret")), key=f"story_brain_character_secret_{record_key}")

        save_col, delete_col = st.columns(2)
        with save_col:
            if st.button("保存角色修改", key=f"story_brain_save_character_{record_key}", use_container_width=True):
                characters[selected_index] = {
                    **character,
                    "id": _story_brain_text(character.get("id")) or _new_story_brain_id("char"),
                    "name": name,
                    "speech_style": speech_style,
                    "behavior_style": behavior_style,
                    "status": status,
                    "other": other,
                    "goal": goal,
                    "secret": secret,
                }
                _save_story_brain_and_refresh(story_brain)

        with delete_col:
            st.warning("删除角色不会自动删除关系和事件引用，可能存在失效关系或事件引用。")
            if st.button("删除这个角色", key=f"story_brain_delete_character_{record_key}", use_container_width=True):
                characters.pop(selected_index)
                st.session_state["story_brain_notice"] = "已删除角色。可能存在失效关系或事件引用。"
                _save_story_brain_and_refresh(story_brain)


def _render_story_brain_relationship_editor(story_brain: dict):
    characters, relationships, _ = _story_brain_lists(story_brain)
    character_names = [
        _story_brain_text(item.get("name"))
        for item in characters
        if isinstance(item, dict) and _story_brain_text(item.get("name"))
    ]

    with st.expander("关系编辑"):
        if not relationships:
            st.info("暂无关系，请先新增关系")

        if st.button("新增关系", key="story_brain_add_relationship_btn", use_container_width=True):
            relationships.append(
                {
                    "id": _new_story_brain_id("rel"),
                    "from": character_names[0] if character_names else "",
                    "to": character_names[1] if len(character_names) > 1 else "",
                    "type": "",
                    "detail": "",
                }
            )
            _save_story_brain_and_refresh(story_brain)

        if not relationships:
            return

        options = list(range(len(relationships)))
        select_key = "story_brain_relationship_select"
        _ensure_selectbox_value(select_key, options)
        selected_index = st.selectbox(
            "选择 relationship",
            options=options,
            format_func=lambda index: _relationship_label(relationships[index], index),
            key=select_key,
        )

        relationship = relationships[selected_index] if isinstance(relationships[selected_index], dict) else {}
        record_id = _story_brain_text(relationship.get("id")) or f"relationship_{selected_index}"
        record_key = f"{record_id}_{selected_index}"

        current_from = _story_brain_text(relationship.get("from"))
        current_to = _story_brain_text(relationship.get("to"))

        if character_names:
            from_options = list(character_names)
            if current_from and current_from not in from_options:
                from_options.insert(0, current_from)
            to_options = list(character_names)
            if current_to and current_to not in to_options:
                to_options.insert(0, current_to)

            from_value = st.selectbox(
                "from",
                options=from_options,
                index=from_options.index(current_from) if current_from in from_options else 0,
                key=f"story_brain_relationship_from_{record_key}",
            )
            to_value = st.selectbox(
                "to",
                options=to_options,
                index=to_options.index(current_to) if current_to in to_options else 0,
                key=f"story_brain_relationship_to_{record_key}",
            )
        else:
            from_value = st.text_input("from", value=current_from, key=f"story_brain_relationship_from_{record_key}")
            to_value = st.text_input("to", value=current_to, key=f"story_brain_relationship_to_{record_key}")

        rel_type = st.text_input("type", value=_story_brain_text(relationship.get("type")), key=f"story_brain_relationship_type_{record_key}")
        detail = st.text_area("detail", value=_story_brain_text(relationship.get("detail")), key=f"story_brain_relationship_detail_{record_key}")

        save_col, delete_col = st.columns(2)
        with save_col:
            if st.button("保存关系修改", key=f"story_brain_save_relationship_{record_key}", use_container_width=True):
                relationships[selected_index] = {
                    **relationship,
                    "id": _story_brain_text(relationship.get("id")) or _new_story_brain_id("rel"),
                    "from": from_value,
                    "to": to_value,
                    "type": rel_type,
                    "detail": detail,
                }
                _save_story_brain_and_refresh(story_brain)

        with delete_col:
            if st.button("删除这个关系", key=f"story_brain_delete_relationship_{record_key}", use_container_width=True):
                relationships.pop(selected_index)
                _save_story_brain_and_refresh(story_brain)


def _render_story_brain_event_editor(story_brain: dict):
    characters, _, events = _story_brain_lists(story_brain)
    character_names = [
        _story_brain_text(item.get("name"))
        for item in characters
        if isinstance(item, dict) and _story_brain_text(item.get("name"))
    ]
    event_type_options = ["伏笔", "主线", "限制"]

    with st.expander("事件编辑"):
        if not events:
            st.info("暂无事件，请先新增事件")

        if st.button("新增事件", key="story_brain_add_event_btn", use_container_width=True):
            events.append(
                {
                    "id": _new_story_brain_id("event"),
                    "type": "伏笔",
                    "title": "",
                    "content": "",
                    "status": "",
                    "trigger": "",
                    "related_characters": [],
                }
            )
            _save_story_brain_and_refresh(story_brain)

        if not events:
            return

        options = list(range(len(events)))
        select_key = "story_brain_event_select"
        _ensure_selectbox_value(select_key, options)
        selected_index = st.selectbox(
            "选择 event",
            options=options,
            format_func=lambda index: _event_label(events[index], index),
            key=select_key,
        )

        event = events[selected_index] if isinstance(events[selected_index], dict) else {}
        record_id = _story_brain_text(event.get("id")) or f"event_{selected_index}"
        record_key = f"{record_id}_{selected_index}"

        current_type = _story_brain_text(event.get("type"))
        type_value = st.selectbox(
            "type",
            options=event_type_options,
            index=event_type_options.index(current_type) if current_type in event_type_options else 0,
            key=f"story_brain_event_type_{record_key}",
        )
        title = st.text_input("title", value=_story_brain_text(event.get("title")), key=f"story_brain_event_title_{record_key}")
        content = st.text_area("content", value=_story_brain_text(event.get("content")), key=f"story_brain_event_content_{record_key}")
        status = st.text_input("status", value=_story_brain_text(event.get("status")), key=f"story_brain_event_status_{record_key}")
        trigger = ""
        if type_value == "伏笔":
            trigger = st.text_area(
                "trigger（什么时候且只有什么时候会触发这个伏笔，必填）",
                value=_story_brain_text(event.get("trigger")),
                key=f"story_brain_event_trigger_{record_key}",
            )

        current_related = [
            _story_brain_text(item)
            for item in (event.get("related_characters") if isinstance(event.get("related_characters"), list) else [])
            if _story_brain_text(item)
        ]
        related_options = list(character_names)
        for name in current_related:
            if name not in related_options:
                related_options.append(name)
        related_characters = st.multiselect(
            "related_characters",
            options=related_options,
            default=[name for name in current_related if name in related_options],
            key=f"story_brain_event_related_characters_{record_key}",
        )

        save_col, delete_col = st.columns(2)
        with save_col:
            if st.button("保存事件修改", key=f"story_brain_save_event_{record_key}", use_container_width=True):
                if type_value == "伏笔" and not _story_brain_text(trigger):
                    st.error("伏笔必须填写 trigger。")
                    st.stop()
                events[selected_index] = {
                    **event,
                    "id": _story_brain_text(event.get("id")) or _new_story_brain_id("event"),
                    "type": type_value,
                    "title": title,
                    "content": content,
                    "status": status,
                    "trigger": trigger if type_value == "伏笔" else "",
                    "related_characters": related_characters,
                }
                _save_story_brain_and_refresh(story_brain)

        with delete_col:
            if st.button("删除这个事件", key=f"story_brain_delete_event_{record_key}", use_container_width=True):
                events.pop(selected_index)
                _save_story_brain_and_refresh(story_brain)


def _render_story_brain_editors(story_brain: dict):
    notice = st.session_state.pop("story_brain_notice", "")
    if notice:
        st.warning(notice)

    _render_story_brain_character_editor(story_brain)
    _render_story_brain_relationship_editor(story_brain)
    _render_story_brain_event_editor(story_brain)


def _render_sidebar_context():
    with st.sidebar:
        st.subheader("会话")
        if st.button("新建会话", use_container_width=True):
            st.session_state.page2_record_id = ""
            st.session_state.page2_loaded_record_id = ""
            st.session_state.page2_turns = []
            st.session_state.page2_generated_media = []
            st.session_state.page2_story_brain = empty_story_brain()
            st.session_state.page2_selected_media_id = ""
            _clear_story_brain_update_suggestions()
            goto("main", push_history=False)

        if st.session_state.page2_record_id:
            st.caption("记录 ID: " + st.session_state.page2_record_id)

        st.divider()
        st.subheader("上下文设置")
        ctx = page2_service.load_context_from_settings()

        # 提供从「设置」里选择 system prompt 记录的入口
        prompt_state = system_prompts.load_state(hidden_space=False)
        prompt_records = system_prompts.visible_records(prompt_state)
        prompt_options = ["(使用当前)"] + [r.title for r in prompt_records]
        chosen = st.selectbox("选择 prompt 记录", options=prompt_options, index=0)
        if chosen != "(使用当前)":
            for record in prompt_records:
                if record.title == chosen:
                    ctx.system_prompt = record.prompt
                    settings.set(AppStorageKeys.SELECTED_SYSTEM_PROMPT_RECORD_ID, record.id)
                    settings.set(AppStorageKeys.SYSTEM_PROMPT, record.prompt)
                    break
            page2_service.save_context_to_settings(ctx)

        with st.form("page2_context_form", border=True):
            if _chat_scope() == "guest":
                st.text_area("system prompt（游客仅可选择）", value=ctx.system_prompt, height=180, disabled=True)
                system_prompt = ctx.system_prompt
            else:
                system_prompt = st.text_area("system prompt", value=ctx.system_prompt, height=180)
            context_turn_count = st.number_input("上下文轮数", min_value=0, max_value=50, value=int(ctx.context_turn_count))
            selected_chat_model = st.selectbox(
                "聊天模型",
                options=["grok1", "grok2", "deepseek"],
                index=["grok1", "grok2", "deepseek"].index(ctx.selected_chat_model)
                if ctx.selected_chat_model in ["grok1", "grok2", "deepseek"]
                else 0,
            )
            story_brain_update_model = st.selectbox(
                "Story Brain 更新模型",
                options=["deepseek", "grok"],
                index=["deepseek", "grok"].index(ctx.story_brain_update_model)
                if ctx.story_brain_update_model in ["deepseek", "grok"]
                else 0,
            )
            temperature = st.slider("temperature", min_value=0.0, max_value=2.0, value=float(ctx.temperature), step=0.05)
            video_provider = st.selectbox(
                "图生视频",
                options=["domoai", "zhipu"],
                index=["domoai", "zhipu"].index(ctx.selected_video_generation_provider)
                if ctx.selected_video_generation_provider in ["domoai", "zhipu"]
                else 0,
            )

            saved = st.form_submit_button("保存", use_container_width=True, type="primary")

        if saved:
            if _chat_scope() != "guest":
                ctx.system_prompt = system_prompt
            ctx.context_turn_count = int(context_turn_count)
            ctx.selected_chat_model = selected_chat_model
            ctx.story_brain_update_model = story_brain_update_model
            ctx.temperature = float(temperature)
            ctx.selected_video_generation_provider = video_provider
            page2_service.save_context_to_settings(ctx)
            st.success("已保存")
            _upsert_record()
            st.rerun()


def _render_chat_column():
    turns = st.session_state.page2_turns

    with st.container(key="page2_chat_canvas"):
        history = st.container(key="page2_chat_history")
        with history:
            for turn in turns:
                with st.chat_message("user"):
                    st.markdown(turn.user_message or "")
                if turn.assistant_message is not None:
                    with st.chat_message("assistant"):
                        st.markdown(turn.assistant_message or "")

        input_placeholder = "输入消息并回车发送" if turns else "输入“开始”以开始游戏"
        user_text = st.chat_input(input_placeholder, key="page2_chat_input")

    undo_clicked = st.button(
        "",
        key="page2_chat_undo_btn",
        help=None,
        icon=":material/undo:",
        type="tertiary",
        disabled=not bool(turns),
        use_container_width=True,
    )

    if "show_story_brain" not in st.session_state:
        st.session_state["show_story_brain"] = False

    story_brain_enabled = bool(st.session_state.get("page2_story_brain_enabled", True))
    story_brain_clicked = st.button(
        "Story Brain 已打开" if story_brain_enabled else "Story Brain 已关闭",
        key="page2_story_brain_btn",
        use_container_width=True,
    )
    if story_brain_clicked:
        story_brain_enabled = not story_brain_enabled
        st.session_state["page2_story_brain_enabled"] = story_brain_enabled
        st.session_state["show_story_brain"] = story_brain_enabled
        if not story_brain_enabled:
            st.session_state["page2_story_brain_graph_fullscreen"] = False
            st.session_state["page2_story_brain_memory_pack_json"] = ""

    if story_brain_enabled:
        st.subheader("Story Brain")
        story_brain = _current_story_brain()
        _render_story_brain_graph(story_brain)
        _render_story_brain_editors(story_brain)
        with st.expander("查看原始 Story Brain JSON"):
            st.json(story_brain)

    if undo_clicked and turns:
        st.session_state.page2_turns = turns[:-1]
        _clear_story_brain_update_suggestions()
        _upsert_record()
        st.rerun()

    if not user_text:
        memory_pack_json = str(st.session_state.get("page2_story_brain_memory_pack_json", "") or "")
        if story_brain_enabled and memory_pack_json:
            with st.expander("本轮将代入模型的 Story Brain Memory Pack"):
                st.code(memory_pack_json, language="json")
        if story_brain_enabled:
            _render_story_brain_update_suggestions()
        return

    current_text = str(user_text).strip()
    _clear_story_brain_update_suggestions()
    previous_assistant_text = _latest_assistant_message(turns)
    memory_source_text = "\n\n".join(
        part for part in [previous_assistant_text.strip(), current_text] if part
    )
    story_brain = _current_story_brain()
    if story_brain_enabled:
        memory_pack = build_memory_pack(
            current_text=memory_source_text,
            story_brain=story_brain,
        )
        memory_pack_json = memory_pack_to_json(memory_pack, max_chars=1500)
        st.session_state["page2_story_brain_memory_pack_json"] = memory_pack_json
        with st.expander("本轮将代入模型的 Story Brain Memory Pack"):
            st.code(memory_pack_json, language="json")
    else:
        st.session_state["page2_story_brain_memory_pack_json"] = ""

    ctx = page2_service.load_context_from_settings()

    new_turn = Page2ConversationTurn(
        user_message=current_text,
        assistant_message=None,
        is_loading=True,
    )
    st.session_state.page2_turns = turns + [new_turn]
    _upsert_record()

    with st.spinner("正在请求模型..."):
        try:
            reply = page2_service.send_message(
                ctx=ctx,
                turns=st.session_state.page2_turns,
                user_message=new_turn.user_message,
                story_brain=story_brain,
                story_brain_enabled=story_brain_enabled,
            )
        except Exception as exc:
            reply = "请求失败，请稍后重试。\n" + user_facing_error_message(exc)

    # 写回最后一条
    last = st.session_state.page2_turns[-1]
    last.assistant_message = reply
    last.is_loading = False
    _upsert_record()

    if story_brain_enabled and not reply.startswith("请求失败"):
        with st.spinner("正在分析 Story Brain 更新建议..."):
            try:
                suggested_updates = page2_service.generate_story_brain_update_suggestions(
                    ctx=ctx,
                    current_text=memory_source_text,
                    model_reply=reply,
                    story_brain=_current_story_brain(),
                )
                updates = suggested_updates.get("suggested_updates") if isinstance(suggested_updates, dict) else []
                if updates:
                    current_story_brain = _current_story_brain()
                    updated_story_brain = apply_story_brain_updates(current_story_brain, suggested_updates)
                    _save_story_brain_to_current_record(updated_story_brain)
                st.session_state["page2_story_brain_suggested_updates"] = suggested_updates
                st.session_state["page2_story_brain_update_error"] = ""
                st.session_state["page2_story_brain_update_turn_id"] = last.id
                st.session_state["page2_story_brain_update_applied"] = bool(updates)
            except Exception as exc:
                st.session_state["page2_story_brain_suggested_updates"] = None
                st.session_state["page2_story_brain_update_error"] = user_facing_error_message(exc)
                st.session_state["page2_story_brain_update_turn_id"] = last.id
                st.session_state["page2_story_brain_update_applied"] = False

    st.rerun()


def _render_media_column():
    st.subheader("图片 / 视频")

    media = st.session_state.page2_generated_media
    if not media:
        st.caption("暂无媒体记录。")
    else:
        options = []
        by_id = {}
        for item in media:
            kind = item.media_kind.value if hasattr(item.media_kind, "value") else str(item.media_kind)
            label = f"{kind.upper()} • {item.provider} • {str(item.created_at or '')}"
            options.append(label)
            by_id[label] = item.id

        selected_media_id = str(st.session_state.get("page2_selected_media_id", "") or "")
        selected_index = 0
        if selected_media_id:
            for index, label in enumerate(options):
                if by_id.get(label) == selected_media_id:
                    selected_index = index
                    break

        selected_label = st.selectbox(
            "选择记录",
            options=options,
            index=selected_index,
            label_visibility="collapsed",
        )
        selected_id = by_id.get(selected_label, "")
        st.session_state.page2_selected_media_id = selected_id

        selected = None
        for item in media:
            if item.id == selected_id:
                selected = item
                break

        if selected is not None:
            kind = selected.media_kind.value if hasattr(selected.media_kind, "value") else str(selected.media_kind)
            st.caption(f"{kind} • provider={selected.provider}")
            st.text_area("prompt", value=str(selected.prompt or ""), height=120, disabled=True)

            if kind == GeneratedMediaKind.IMAGE.value:
                if selected.image_data_base64:
                    st.image(_decode_image_base64(selected.image_data_base64))
                elif selected.image_url_string:
                    st.image(selected.image_url_string)

                url = selected.image_url_string or ""
                if url:
                    st.text_input("图片 URL（可复制）", value=url)

            else:
                url = selected.video_url_string or ""
                if url:
                    st.video(url)
                    st.text_input("视频 URL（可复制）", value=url)
                else:
                    st.warning("该视频记录没有 URL。")

            if st.button("删除当前记录", use_container_width=True):
                st.session_state.page2_generated_media = [m for m in media if m.id != selected_id]
                _upsert_record()
                st.rerun()

    st.divider()
    st.subheader("生成图片")

    latest = _latest_assistant_message(st.session_state.page2_turns)
    if not latest:
        st.caption("先在左侧生成一条助手回复，然后可以从最近回复生成图片 prompt。")

    mode = st.selectbox(
        "prompt 模式",
        options=["normal", "first_person", "closeup"],
        index=["normal", "first_person", "closeup"].index(st.session_state.page2_image_prompt_mode),
    )
    st.session_state.page2_image_prompt_mode = mode
    subject = ""
    if mode in ["first_person", "closeup"]:
        subject = st.text_input("主体", value=st.session_state.page2_image_prompt_subject)
        st.session_state.page2_image_prompt_subject = subject

    if st.button("从最近助手回复生成图片 prompt", use_container_width=True, disabled=not latest):
        with st.spinner("正在生成图片 prompt..."):
            try:
                prompt = page2_service.generate_image_prompt(latest, mode=mode, subject=subject)
                st.session_state.page2_image_prompt = prompt
                st.success("图片 prompt 已生成")
            except Exception as exc:
                _show_error(exc)

    prompt_text = st.text_area("图片 prompt（可编辑）", value=st.session_state.page2_image_prompt, height=160)
    st.session_state.page2_image_prompt = prompt_text

    provider = st.selectbox(
        "图片生成 provider",
        options=["grok", "grokQuality", "grokPro", "flux", "nanoPro", "nano"],
        index=0,
    )
    image_urls_raw = st.text_area("参考图片 URL（每行一个，可选）", value="", height=90)
    image_urls = [line.strip() for line in image_urls_raw.splitlines() if line.strip()]

    if st.button("生成图片", type="primary", use_container_width=True):
        with st.spinner("正在生成图片..."):
            try:
                record = page2_service.generate_image(provider=provider, prompt=prompt_text, image_urls=image_urls)
                st.session_state.page2_generated_media = media + [record]
                st.session_state.page2_selected_media_id = record.id
                _upsert_record()
                st.success("图片已生成并保存到记录")
                st.rerun()
            except Exception as exc:
                _show_error(exc)

    st.divider()
    st.subheader("图生视频")
    st.caption("从上面的媒体列表里选择一张图片作为输入。")

    image_candidates = [m for m in media if (m.media_kind.value if hasattr(m.media_kind, "value") else str(m.media_kind)) == GeneratedMediaKind.IMAGE.value]
    if not image_candidates:
        st.caption("暂无可用图片。")
        return

    candidate_labels = []
    label_to_id = {}
    for item in image_candidates:
        label = f"{item.provider} • {str(item.created_at or '')} • {item.prompt[:24] if item.prompt else ''}"
        candidate_labels.append(label)
        label_to_id[label] = item.id

    selected_media_id = str(st.session_state.get("page2_selected_media_id", "") or "")
    selected_image_index = len(image_candidates) - 1
    if selected_media_id:
        for index, item in enumerate(image_candidates):
            if item.id == selected_media_id:
                selected_image_index = index
                break

    selected_label = st.selectbox(
        "选择输入图片",
        options=candidate_labels,
        index=selected_image_index,
    )
    source_id = label_to_id.get(selected_label, "")
    source = None
    for item in image_candidates:
        if item.id == source_id:
            source = item
            break
    if source is None:
        return

    video_prompt = st.text_input("视频 prompt", key="page2_video_prompt")
    ctx = page2_service.load_context_from_settings()
    if str(ctx.selected_video_generation_provider or "") == "zhipu":
        seconds = st.selectbox("时长（秒）", options=[5, 10], index=0)
    else:
        seconds = st.number_input("时长（秒）", min_value=1, max_value=10, value=5)

    if st.button("生成视频", use_container_width=True):
        with st.spinner("正在生成视频（可能需要较长时间）..."):
            try:
                video_record = page2_service.generate_video_from_image(
                    ctx=ctx,
                    source_record=source,
                    prompt=video_prompt,
                    seconds=int(seconds),
                )
                st.session_state.page2_generated_media = media + [video_record]
                st.session_state.page2_selected_media_id = video_record.id
                _upsert_record()
                st.success("视频已生成并保存到记录")
                st.rerun()
            except Exception as exc:
                _show_error(exc)

    st.divider()
    st.subheader("URL 收藏")

    url_state = stored_urls.load_state(hidden_space=bool(st.session_state.page2_url_hidden_space))
    st.session_state.page2_url_hidden_space = url_state.hidden_space

    url_input = st.text_input("新增 URL 或输入口令解锁隐藏空间", value="")
    add_col1, add_col2 = st.columns([1, 1])
    with add_col1:
        if st.button("新增", use_container_width=True):
            try:
                url_state = stored_urls.add_url(url_state, url_input)
                st.session_state.page2_url_hidden_space = url_state.hidden_space
                st.rerun()
            except Exception as exc:
                _show_error(exc)
    with add_col2:
        uploaded = st.file_uploader("上传图片获取 URL（Cloudinary）", type=["png", "jpg", "jpeg", "webp"])
        if uploaded is not None and st.button("上传并复制 URL", use_container_width=True):
            with st.spinner("上传中..."):
                try:
                    suffix = Path(uploaded.name).suffix or ".png"
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(uploaded.getvalue())
                        tmp_path = tmp.name
                    secure_url = CloudinaryUploader.upload_image(tmp_path)
                    st.success("上传成功（URL 可复制）")
                    st.text_input("URL", value=secure_url)
                except Exception as exc:
                    _show_error(exc)

    visible = stored_urls.visible_records(url_state)
    if visible:
        url_labels = []
        url_by_label = {}
        for r in visible:
            prefix = "隐藏：" if r in url_state.hidden_records else ""
            label = f"{prefix}{r.title}: {r.url}"
            url_labels.append(label)
            url_by_label[label] = r
        chosen = st.selectbox("收藏列表", options=url_labels)
        r = url_by_label.get(chosen)
        if r is not None:
            st.text_input("选中 URL（可复制）", value=r.url)
            if st.button("删除选中 URL", use_container_width=True):
                stored_urls.delete_url(url_state, r.id)
                st.success("已删除")
                st.rerun()
    else:
        st.caption("暂无收藏。")


def render():
    _ensure_state()
    _load_record_from_nav_if_needed()
    st.markdown(
        """
<style>
/* Page2: move content to top (remove Streamlit's default top padding) */
section[data-testid="stMain"] .block-container {
  padding-top: 16px !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )

    _render_sidebar_context()

    left, right = st.columns([1, 1])
    with left:
        _render_chat_column()
    with right:
        _render_media_column()
