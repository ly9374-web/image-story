from __future__ import annotations

import base64
import threading
import uuid
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from app.config import AppStorageKeys, settings, user_facing_error_message
from app.models import GeneratedMediaKind, Page2ConversationTurn
from app.services import chat_records, page2_service, system_prompts
from graph_view import GRAPH_HEIGHT_PX, GRAPH_NODE_SPACING, build_story_brain_graph_data
from story_brain import (
    apply_story_brain_updates,
    build_memory_pack,
    empty_story_brain,
    memory_pack_to_json,
    normalize_story_brain,
)
from web.nav import get_arg, goto
from web.components.page2_inline_editor import page2_inline_editor
from web.pages import url_favorites


_story_brain_graph_component = components.declare_component(
    "story_brain_graph",
    path=str(Path(__file__).resolve().parents[1] / "components" / "story_brain_graph"),
)

_story_brain_text_editor_component = components.declare_component(
    "page2_story_brain_text_editor",
    path=str(Path(__file__).resolve().parents[1] / "components" / "agent_story_brain_text_editor"),
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
    st.session_state.setdefault("page2_story_brain_suggested_updates", None)
    st.session_state.setdefault("page2_story_brain_update_error", "")
    st.session_state.setdefault("page2_story_brain_update_turn_id", "")
    st.session_state.setdefault("page2_story_brain_update_applied", False)
    st.session_state.setdefault("page2_story_brain_graph_edit_event_id", "")
    st.session_state.setdefault("page2_story_brain_graph_fullscreen", False)
    st.session_state.setdefault("page2_story_brain", empty_story_brain())
    st.session_state.setdefault("page2_story_brain_short", "")
    st.session_state.setdefault("page2_story_brain_enabled", True)
    st.session_state.setdefault("page2_story_brain_short_editor_nonce", 0)
    st.session_state.setdefault("page2_story_brain_short_update_notice", "")
    st.session_state.setdefault("page2_sb_bg_task", None)
    st.session_state.setdefault("page2_sb_bg_queue", [])
    st.session_state.setdefault("page2_sb_bg_error", "")


class _SbBgTask:
    """Story Brain 后台更新任务。后台线程只写 result/error/_done，主线程读取。"""

    def __init__(self, fn, args, apply_fn, label: str = ""):
        self._fn = fn
        self._args = args
        self._apply_fn = apply_fn
        self.label = label
        self.result = None
        self.error = None
        self._done = False
        self._thread: threading.Thread | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self.result = self._fn(*self._args)
        except Exception as exc:
            self.error = exc
        finally:
            self._done = True

    def is_done(self) -> bool:
        return self._done


def _clear_background_sb_task():
    """清空后台任务和队列（开新对话 / 加载记录时调用）。"""
    st.session_state.page2_sb_bg_task = None
    st.session_state.page2_sb_bg_queue = []
    st.session_state.page2_sb_bg_error = ""


def _drain_background_sb_task():
    """在处理新消息前调用：若后台任务完成则 apply 结果，并启动队列中下一个。"""
    _ensure_state()
    task = st.session_state.page2_sb_bg_task
    if task is None or not task.is_done():
        return

    if task.error is not None:
        st.session_state.page2_sb_bg_error = (
            "Story Brain 后台更新失败：" + user_facing_error_message(task.error)
        )
    elif task.result is not None:
        try:
            task._apply_fn(task.result)
            _upsert_record()
            st.session_state.page2_sb_bg_error = ""
        except Exception as exc:
            st.session_state.page2_sb_bg_error = (
                "Story Brain 后台更新应用失败：" + user_facing_error_message(exc)
            )

    st.session_state.page2_sb_bg_task = None

    queue = st.session_state.page2_sb_bg_queue
    if queue:
        next_task = queue.pop(0)
        st.session_state.page2_sb_bg_task = next_task
        next_task.start()


def _enqueue_background_sb_update(task: _SbBgTask):
    """回复后调用：若无任务在跑则直接启动，否则排队。"""
    _ensure_state()
    current = st.session_state.page2_sb_bg_task
    if current is None or current.is_done():
        st.session_state.page2_sb_bg_task = task
        task.start()
    else:
        st.session_state.page2_sb_bg_queue.append(task)


@st.fragment(run_every=2)
def _render_sb_bg_status():
    """轻量状态指示器，只读不写，2 秒轮询。"""
    _ensure_state()
    task = st.session_state.get("page2_sb_bg_task")
    if task is not None and not task.is_done():
        st.caption("Story Brain 后台更新中…")
    elif task is not None and task.is_done():
        st.caption("Story Brain 已更新，下一轮生效")
    err = st.session_state.get("page2_sb_bg_error", "")
    if err:
        st.error(err)


def start_new_conversation(reset_settings: bool = False):
    _ensure_state()
    if reset_settings:
        page2_service.reset_context_settings()
        st.session_state.pop("page2_prompt_record_select", None)
    st.session_state.page2_record_id = ""
    st.session_state.page2_loaded_record_id = ""
    st.session_state.page2_turns = []
    st.session_state.page2_generated_media = []
    st.session_state.page2_selected_media_id = ""
    st.session_state.page2_image_prompt = ""
    st.session_state.page2_image_prompt_mode = "normal"
    st.session_state.page2_image_prompt_subject = ""
    st.session_state.page2_video_prompt = "动起来"
    st.session_state.page2_story_brain = empty_story_brain()
    st.session_state.page2_story_brain_short = ""
    st.session_state.page2_story_brain_enabled = True
    st.session_state.page2_story_brain_graph_fullscreen = False
    st.session_state.page2_story_brain_memory_pack_json = ""
    st.session_state["page2_story_brain_short_update_notice"] = ""
    st.session_state.pop("page2_chat_input", None)
    st.session_state.pop("page2_first_reply_prompt_id", None)
    _clear_story_brain_update_suggestions()
    _clear_background_sb_task()


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
    st.session_state.page2_story_brain_short = str(getattr(record, "story_brain_short", "") or "").strip()
    _refresh_short_story_brain_editor()
    st.session_state.page2_selected_media_id = ""
    _clear_background_sb_task()

    if str(record.system_prompt or "").strip():
        ctx = page2_service.load_context_from_settings()
        ctx.system_prompt = record.system_prompt
        page2_service.save_context_to_settings(ctx)


def _latest_assistant_message(turns: list[Page2ConversationTurn]) -> str:
    for turn in reversed(turns):
        if turn.assistant_message:
            return turn.assistant_message
    return ""


def _conversation_started(turns: list[Page2ConversationTurn]) -> bool:
    """用户是否已在本对话中真正发言（自动开场消息不算）。"""
    return any(str(turn.user_message or "").strip() for turn in turns)


def _maybe_apply_first_reply_opening(turns: list[Page2ConversationTurn]) -> list[Page2ConversationTurn]:
    """首轮输出：新对话（用户尚未发言）时，把选中 prompt 的首轮输出直接作为开场 assistant 消息发送。

    - 点击「开始」/「新建对话」进入新对话后自动发送；
    - 未发言前切换 prompt 会用新 prompt 的首轮输出替换开场消息；
    - 切换到未设置首轮输出的 prompt 时清掉旧开场消息；
    - 已有记录或用户已发言时不做任何处理。
    """
    if str(st.session_state.get("page2_record_id", "") or ""):
        return turns
    if _conversation_started(turns):
        return turns

    prompt_state = system_prompts.load_state(
        hidden_space=bool(st.session_state.get("hidden_unlocked", False))
    )
    first_reply = system_prompts.selected_first_reply(prompt_state)
    selected_prompt_id = str(prompt_state.selected_record_id or "")
    applied_prompt_id = str(st.session_state.get("page2_first_reply_prompt_id", "") or "")

    if first_reply:
        if applied_prompt_id == selected_prompt_id:
            return turns
        st.session_state.page2_turns = [
            Page2ConversationTurn(
                user_message="",
                assistant_message=first_reply,
                is_loading=False,
            )
        ]
        st.session_state["page2_first_reply_prompt_id"] = selected_prompt_id
        return st.session_state.page2_turns

    if applied_prompt_id and turns:
        # 切换到未设置首轮输出的 prompt：清掉之前自动发送的开场消息
        st.session_state.page2_turns = []
        st.session_state.pop("page2_first_reply_prompt_id", None)
        return st.session_state.page2_turns

    return turns


def _turn_marker_html(turn_id: str, role: str, text: str) -> str:
    """双击编辑用隐藏 marker：供 page2_inline_editor 前端定位气泡并取到当前文本。"""
    payload = base64.b64encode(str(text or "").encode("utf-8")).decode("ascii")
    return (
        f'<div class="page2-turn-marker" data-turn-id="{turn_id}" '
        f'data-role="{role}" data-payload="{payload}" style="display:none;"></div>'
    )


def _apply_chat_edit(edit: dict):
    """双击编辑聊天消息：更新对应气泡文本；清空保存 = 删除该条消息。修改会持久化并进入后续上下文。"""
    turn_id = str(edit.get("turn_id", "") or "")
    role = str(edit.get("role", "") or "")
    text = str(edit.get("text", "") or "")
    if not turn_id or role not in ("user", "assistant"):
        return

    turns = st.session_state.page2_turns
    target = next((turn for turn in turns if turn.id == turn_id), None)
    if target is None:
        return

    if role == "user":
        if str(target.user_message or "") == text:
            return  # 组件值会保持到下次编辑，幂等跳过
        target.user_message = text
    else:
        if str(target.assistant_message or "") == text:
            return
        target.assistant_message = text or None

    # user / assistant 都被清空的 turn 从记录中移除
    st.session_state.page2_turns = [
        turn
        for turn in turns
        if str(turn.user_message or "").strip() or str(turn.assistant_message or "").strip()
    ]
    _clear_story_brain_update_suggestions()
    _upsert_record()


def _upsert_record():
    ctx = page2_service.load_context_from_settings()
    st.session_state.page2_record_id = page2_service.upsert_chat_record(
        record_id=st.session_state.page2_record_id,
        turns=st.session_state.page2_turns,
        generated_media=st.session_state.page2_generated_media,
        system_prompt=ctx.system_prompt,
        story_brain=st.session_state.page2_story_brain,
        story_brain_short=st.session_state.get("page2_story_brain_short", ""),
        scope=_chat_scope(),
    )


def _current_story_brain() -> dict:
    story_brain = normalize_story_brain(st.session_state.get("page2_story_brain"))
    st.session_state.page2_story_brain = story_brain
    return story_brain


def _refresh_short_story_brain_editor():
    st.session_state.page2_story_brain_short_editor_nonce = int(
        st.session_state.get("page2_story_brain_short_editor_nonce", 0) or 0
    ) + 1


def _current_short_story_brain() -> str:
    story_brain = str(st.session_state.get("page2_story_brain_short", "") or "").strip()
    st.session_state.page2_story_brain_short = story_brain
    return story_brain


def _roll_user_dice_message() -> str:
    return f"掷骰结果：“{page2_service.roll_point()}”"


def _save_short_story_brain_to_current_record(story_brain: str):
    st.session_state.page2_story_brain_short = str(story_brain or "").strip()
    _upsert_record()


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


def _render_short_story_brain_text_editor(value: str) -> str:
    result = _story_brain_text_editor_component(
        value=str(value or ""),
        key=(
            "page2_story_brain_text_editor_component_"
            + str(int(st.session_state.get("page2_story_brain_short_editor_nonce", 0) or 0))
        ),
        default=None,
    )
    if isinstance(result, str):
        return result
    return str(value or "")


def _completed_turn_count(turns: list[Page2ConversationTurn]) -> int:
    return sum(1 for turn in turns if str(turn.assistant_message or "").strip())


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


def render_sidebar_context():
    _ensure_state()
    _load_record_from_nav_if_needed()

    with st.sidebar:
        if st.button("新建对话", use_container_width=True):
            start_new_conversation()
            goto("main", push_history=False)

        record_id = str(st.session_state.get("page2_record_id", "") or "")
        if record_id:
            st.caption("记录 ID: " + record_id)

        st.divider()
        st.subheader("上下文设置")
        ctx = page2_service.load_context_from_settings()

        # 提供从「设置」里选择 system prompt 的入口
        prompt_state = system_prompts.load_state(
            hidden_space=bool(st.session_state.get("hidden_unlocked", False))
        )
        prompt_records = system_prompts.visible_records(prompt_state)
        prompt_labels = []
        prompt_by_label = {}
        selected_prompt_id = str(settings.get(AppStorageKeys.SELECTED_SYSTEM_PROMPT_RECORD_ID, "") or "")
        selected_prompt_index = None
        for index, record in enumerate(prompt_records):
            label = system_prompts.record_label(prompt_state, record, index)
            prompt_labels.append(label)
            prompt_by_label[label] = record
            if record.id == selected_prompt_id:
                selected_prompt_index = index

        if prompt_labels:
            if st.session_state.get("page2_prompt_record_select") not in prompt_labels:
                st.session_state.pop("page2_prompt_record_select", None)
            chosen_prompt_label = st.selectbox(
                "选择 prompt",
                options=prompt_labels,
                index=selected_prompt_index,
                placeholder="选择 prompt",
                key="page2_prompt_record_select",
            )
            chosen_prompt = prompt_by_label.get(chosen_prompt_label)
            if chosen_prompt is not None and chosen_prompt.id != selected_prompt_id:
                ctx.system_prompt = chosen_prompt.prompt
                settings.set(AppStorageKeys.SELECTED_SYSTEM_PROMPT_RECORD_ID, chosen_prompt.id)
                settings.set(AppStorageKeys.SYSTEM_PROMPT, chosen_prompt.prompt)
                page2_service.save_context_to_settings(ctx)
                st.session_state["page2_sidebar_system_prompt"] = chosen_prompt.prompt
        else:
            st.caption("暂无 prompt。")

        with st.container(border=True):
            if _chat_scope() == "guest":
                st.text_area(
                    "system prompt（游客仅可选择）",
                    value=ctx.system_prompt,
                    height=180,
                    disabled=True,
                    key="page2_sidebar_system_prompt",
                )
                system_prompt = ctx.system_prompt
            else:
                system_prompt = st.text_area(
                    "system prompt",
                    value=ctx.system_prompt,
                    height=180,
                    key="page2_sidebar_system_prompt",
                )
            context_turn_count = st.number_input(
                "上下文轮数",
                min_value=0,
                max_value=50,
                value=int(ctx.context_turn_count),
                key="page2_sidebar_context_turn_count",
            )
            selected_chat_model = st.selectbox(
                "聊天模型",
                options=["grok1", "grok2", "deepseek"],
                index=["grok1", "grok2", "deepseek"].index(ctx.selected_chat_model)
                if ctx.selected_chat_model in ["grok1", "grok2", "deepseek"]
                else 0,
                key="page2_sidebar_selected_chat_model",
            )
            story_brain_update_model = st.selectbox(
                "Story Brain 更新模型",
                options=["deepseek", "grok"],
                index=["deepseek", "grok"].index(ctx.story_brain_update_model)
                if ctx.story_brain_update_model in ["deepseek", "grok"]
                else 0,
                key="page2_sidebar_story_brain_update_model",
            )
            story_brain_mode = st.selectbox(
                "Story Brain 模式",
                options=page2_service.STORY_BRAIN_MODES,
                index=page2_service.STORY_BRAIN_MODES.index(ctx.story_brain_mode)
                if ctx.story_brain_mode in page2_service.STORY_BRAIN_MODES
                else 0,
                key="page2_sidebar_story_brain_mode",
            )
            story_brain_turns = st.number_input(
                "Story Brain 更新间隔",
                min_value=1,
                step=1,
                value=int(ctx.story_brain_turns),
                key="page2_sidebar_story_brain_turns",
            )
            temperature = st.slider(
                "temperature",
                min_value=0.0,
                max_value=2.0,
                value=float(ctx.temperature),
                step=0.05,
                key="page2_sidebar_temperature",
            )
            video_provider = st.selectbox(
                "图生视频",
                options=["domoai", "zhipu"],
                index=["domoai", "zhipu"].index(ctx.selected_video_generation_provider)
                if ctx.selected_video_generation_provider in ["domoai", "zhipu"]
                else 0,
                key="page2_sidebar_video_provider",
            )

        st.divider()
        unexpected_event_enabled = st.toggle(
            "意外情况",
            value=bool(ctx.unexpected_event_enabled),
            key="page2_sidebar_unexpected_event_enabled",
        )
        unexpected_event_threshold = st.slider(
            "意外发生点数",
            min_value=0,
            max_value=24,
            value=int(ctx.unexpected_event_threshold),
            step=1,
            key="page2_sidebar_unexpected_event_threshold",
        )

        if st.button("确认", type="primary", use_container_width=True, key="page2_sidebar_confirm_btn"):
            if _chat_scope() != "guest":
                ctx.system_prompt = system_prompt
            ctx.context_turn_count = int(context_turn_count)
            ctx.selected_chat_model = selected_chat_model
            ctx.story_brain_update_model = story_brain_update_model
            ctx.story_brain_mode = story_brain_mode
            ctx.story_brain_turns = int(story_brain_turns)
            ctx.unexpected_event_enabled = bool(unexpected_event_enabled)
            ctx.unexpected_event_threshold = int(unexpected_event_threshold)
            ctx.temperature = float(temperature)
            ctx.selected_video_generation_provider = video_provider
            page2_service.save_context_to_settings(ctx)
            if str(st.session_state.get("page2_record_id", "") or "") or _conversation_started(
                st.session_state.page2_turns
            ):
                _upsert_record()
            st.success("设置已保存")
            st.rerun()

        if str(st.session_state.get("page2_record_id", "") or "") or _conversation_started(
            st.session_state.page2_turns
        ):
            _upsert_record()


def _apply_short_sb_result(result: str):
    """drain 时 apply SHORT 模式后台结果。"""
    _save_short_story_brain_to_current_record(result)
    _refresh_short_story_brain_editor()


def _apply_long_sb_result(suggested_updates):
    """drain 时 apply LONG 模式后台结果到当前 Story Brain。"""
    updates = suggested_updates.get("suggested_updates") if isinstance(suggested_updates, dict) else []
    if updates:
        current_story_brain = _current_story_brain()
        updated_story_brain = apply_story_brain_updates(current_story_brain, suggested_updates)
        _save_story_brain_to_current_record(updated_story_brain)


def _render_chat_column():
    _drain_background_sb_task()
    # 双击编辑结果（组件值保持到下次编辑，_apply_chat_edit 内部幂等）
    edit_result = page2_inline_editor(key="page2_inline_editor")
    if edit_result:
        _apply_chat_edit(edit_result)
    turns = _maybe_apply_first_reply_opening(st.session_state.page2_turns)
    ctx = page2_service.load_context_from_settings()

    with st.container(key="page2_chat_canvas"):
        history = st.container(key="page2_chat_history")
        with history:
            for turn in turns:
                if turn.user_message:
                    with st.chat_message("user"):
                        st.markdown(turn.user_message)
                        st.markdown(
                            _turn_marker_html(turn.id, "user", turn.user_message),
                            unsafe_allow_html=True,
                        )
                if turn.assistant_message is not None:
                    with st.chat_message("assistant"):
                        st.markdown(turn.assistant_message or "")
                        st.markdown(
                            _turn_marker_html(turn.id, "assistant", turn.assistant_message or ""),
                            unsafe_allow_html=True,
                        )

        input_placeholder = "输入消息并回车发送" if turns else "输入“开始”以开始游戏"
        with st.container(key="page2_chat_composer"):
            user_text = st.chat_input(input_placeholder, key="page2_chat_input")
            dice_clicked = st.button(
                "",
                key="page2_chat_dice_btn",
                help="掷一次 0–24 点骰子并直接发送",
                icon=":material/casino:",
                type="tertiary",
            )

    if dice_clicked:
        user_text = _roll_user_dice_message()

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
        "点击关闭story brain" if story_brain_enabled else "点击开启story brain",
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
        _render_sb_bg_status()
        if ctx.story_brain_mode == page2_service.STORY_BRAIN_SHORT:
            notice = str(st.session_state.pop("page2_story_brain_short_update_notice", "") or "").strip()
            if notice:
                if notice.startswith("Story Brain 更新失败"):
                    st.error(notice)
                else:
                    st.success(notice)
            story_brain_short = _current_short_story_brain()
            next_story_brain_short = _render_short_story_brain_text_editor(story_brain_short)
            if next_story_brain_short != story_brain_short:
                _save_short_story_brain_to_current_record(next_story_brain_short)
                _refresh_short_story_brain_editor()
                st.rerun()
        else:
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
        if story_brain_enabled and ctx.story_brain_mode == page2_service.STORY_BRAIN_LONG and memory_pack_json:
            with st.expander("本轮将代入模型的 Story Brain Memory Pack"):
                st.code(memory_pack_json, language="json")
        return

    current_text = str(user_text).strip()
    _clear_story_brain_update_suggestions()
    previous_assistant_text = _latest_assistant_message(turns)
    memory_source_text = "\n\n".join(
        part for part in [previous_assistant_text.strip(), current_text] if part
    )
    story_brain = _current_story_brain()
    story_brain_short = _current_short_story_brain()
    if story_brain_enabled and ctx.story_brain_mode == page2_service.STORY_BRAIN_LONG:
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
                turns=turns,
                user_message=new_turn.user_message,
                story_brain=story_brain,
                story_brain_short=story_brain_short,
                story_brain_enabled=story_brain_enabled,
            )
        except Exception as exc:
            reply = "请求失败，请稍后重试。\n" + user_facing_error_message(exc)

    # 写回最后一条
    last = st.session_state.page2_turns[-1]
    last.assistant_message = reply
    last.is_loading = False
    _upsert_record()

    # 后台触发 Story Brain 更新（不阻塞，排队执行）
    if story_brain_enabled and not reply.startswith("请求失败"):
        completed_turn_count = _completed_turn_count(st.session_state.page2_turns)
        story_brain_turns = max(1, int(ctx.story_brain_turns))
        should_trigger = (
            completed_turn_count > 0
            and completed_turn_count % story_brain_turns == 0
        )
        if should_trigger:
            if ctx.story_brain_mode == page2_service.STORY_BRAIN_SHORT:
                sb_short_snapshot = _current_short_story_brain()
                turns_snapshot = list(st.session_state.page2_turns)
                task = _SbBgTask(
                    fn=lambda: page2_service.generate_short_story_brain(
                        ctx=ctx,
                        turns=turns_snapshot,
                        story_brain_short=sb_short_snapshot,
                    ),
                    args=(),
                    apply_fn=_apply_short_sb_result,
                    label="short",
                )
            else:
                sb_snapshot = _current_story_brain()
                memory_source_snapshot = str(memory_source_text)
                reply_snapshot = str(reply)
                task = _SbBgTask(
                    fn=lambda: page2_service.generate_story_brain_update_suggestions(
                        ctx=ctx,
                        current_text=memory_source_snapshot,
                        model_reply=reply_snapshot,
                        story_brain=sb_snapshot,
                    ),
                    args=(),
                    apply_fn=_apply_long_sb_result,
                    label="long",
                )
            _enqueue_background_sb_update(task)

    st.rerun()


def _render_url_preview_image(url: str) -> None:
    """显示「URL 收藏」里点「显示图片」选中的图片。"""
    try:
        st.image(url)
    except Exception:
        st.error("无法显示该 URL 的图片。")


def _render_media_column():
    media = st.session_state.page2_generated_media
    url_preview = url_favorites.get_preview_url("page2")

    if not media:
        if url_preview:
            _render_url_preview_image(url_preview)
        else:
            st.caption("暂无媒体记录。")
    else:
        options = []
        by_id = {}
        for item in media:
            kind = item.media_kind.value if hasattr(item.media_kind, "value") else str(item.media_kind)
            label = f"{kind.upper()} • {item.provider} • {str(item.created_at or '')}"
            options.append(label)
            by_id[label] = item.id

        preview_container = st.container()
        prompt_container = st.container()

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
        # 切换「选择记录」时清除 URL 收藏预览，恢复显示媒体记录
        if selected_id != selected_media_id:
            url_favorites.clear_preview_url("page2")
            url_preview = ""
        st.session_state.page2_selected_media_id = selected_id

        selected = None
        for item in media:
            if item.id == selected_id:
                selected = item
                break

        if url_preview:
            with preview_container:
                _render_url_preview_image(url_preview)
        elif selected is not None:
            kind = selected.media_kind.value if hasattr(selected.media_kind, "value") else str(selected.media_kind)
            with preview_container:
                if kind == GeneratedMediaKind.IMAGE.value:
                    if selected.image_data_base64:
                        st.image(_decode_image_base64(selected.image_data_base64))
                    elif selected.image_url_string:
                        st.image(selected.image_url_string)
                else:
                    url = selected.video_url_string or ""
                    if url:
                        st.video(url)
                    else:
                        st.warning("该视频记录没有 URL。")

        if not url_preview and selected is not None:
            kind = selected.media_kind.value if hasattr(selected.media_kind, "value") else str(selected.media_kind)
            with prompt_container:
                st.caption(f"{kind} • provider={selected.provider}")
                st.caption("prompt")
                st.code(
                    str(selected.prompt or ""),
                    language=None,
                    wrap_lines=True,
                    height=120,
                )

            if kind == GeneratedMediaKind.IMAGE.value:
                url = selected.image_url_string or ""
                if url:
                    url_favorites.render_url_display_with_copy(
                        url,
                        key=f"page2_media_url_copy_{selected.id}",
                        label="图片 URL（可复制）",
                    )
            else:
                url = selected.video_url_string or ""
                if url:
                    url_favorites.render_url_display_with_copy(
                        url,
                        key=f"page2_media_url_copy_{selected.id}",
                        label="视频 URL（可复制）",
                    )

            if st.button("删除当前记录", use_container_width=True):
                st.session_state.page2_generated_media = [m for m in media if m.id != selected_id]
                _upsert_record()
                st.rerun()

    st.divider()
    st.subheader("生成图片")

    latest = _latest_assistant_message(st.session_state.page2_turns)
    if not latest:
        st.caption("先在左侧生成一条助手回复，然后可以点击“生成图片prompt”。")

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

    if st.button("生成图片prompt", use_container_width=True, disabled=not latest):
        with st.spinner("正在生成图片prompt..."):
            try:
                prompt = page2_service.generate_image_prompt(latest, mode=mode, subject=subject)
                st.session_state.page2_image_prompt = prompt
                st.success("图片prompt已生成")
            except Exception as exc:
                _show_error(exc)

    prompt_text = st.text_area("图片prompt（可编辑）", value=st.session_state.page2_image_prompt, height=160)
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
                url_favorites.clear_preview_url("page2")
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
        url_favorites.render_url_favorites("page2")
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
        url_favorites.render_url_favorites("page2")
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
                url_favorites.clear_preview_url("page2")
                _upsert_record()
                st.success("视频已生成并保存到记录")
                st.rerun()
            except Exception as exc:
                _show_error(exc)

    url_favorites.render_url_favorites("page2")


def render():
    _ensure_state()
    _load_record_from_nav_if_needed()
    st.markdown(
        """
<style>
/* Page2: move content to top (remove Streamlit's default top padding) */
section[data-testid="stMain"] .block-container {
  padding-top: 32px !important;
  padding-bottom: 0px !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1])
    with left:
        _render_chat_column()
    with right:
        _render_media_column()
